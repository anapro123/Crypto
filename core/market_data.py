"""
Market Data Manager: Fetches, caches, and normalizes market data.
"""

import asyncio
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict

from core.exchange_manager import ExchangeManager
from config.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class OrderBookLevel:
    price: float
    amount: float


@dataclass
class NormalizedOrderBook:
    exchange: str
    symbol: str
    timestamp: datetime
    bids: List[OrderBookLevel] = field(default_factory=list)
    asks: List[OrderBookLevel] = field(default_factory=list)

    @property
    def best_bid(self) -> Optional[float]:
        return self.bids[0].price if self.bids else None

    @property
    def best_ask(self) -> Optional[float]:
        return self.asks[0].price if self.asks else None

    @property
    def spread(self) -> Optional[float]:
        if self.best_bid and self.best_ask:
            return self.best_ask - self.best_bid
        return None

    @property
    def spread_pct(self) -> Optional[float]:
        if self.best_bid and self.best_ask and self.best_bid > 0:
            return (self.spread / self.best_bid) * 100
        return None

    def get_liquidity_at_price(self, price: float, side: str = "ask", tolerance_pct: float = 0.1) -> float:
        levels = self.asks if side == "ask" else self.bids
        total = 0.0
        for level in levels:
            if abs(level.price - price) / price <= tolerance_pct / 100:
                total += level.amount * level.price
        return total


class MarketDataCache:
    def __init__(self, ttl_seconds: float = 1.0):
        self._cache: Dict[str, Dict[str, tuple]] = defaultdict(dict)
        self._ttl = ttl_seconds
        self._lock = asyncio.Lock()

    def _make_key(self, exchange: str, symbol: str) -> str:
        return f"{exchange}:{symbol}"

    async def get(self, exchange: str, symbol: str) -> Optional[NormalizedOrderBook]:
        key = self._make_key(exchange, symbol)
        async with self._lock:
            if key in self._cache[exchange]:
                data, timestamp = self._cache[exchange][key]
                if datetime.utcnow() - timestamp < timedelta(seconds=self._ttl):
                    return data
        return None

    async def set(self, exchange: str, symbol: str, data: NormalizedOrderBook):
        key = self._make_key(exchange, symbol)
        async with self._lock:
            self._cache[exchange][key] = (data, datetime.utcnow())

    async def get_all(self, exchange: str) -> Dict[str, NormalizedOrderBook]:
        async with self._lock:
            result = {}
            for key, (data, timestamp) in list(self._cache[exchange].items()):
                if datetime.utcnow() - timestamp < timedelta(seconds=self._ttl):
                    result[key.split(":")[1]] = data
            return result


class MarketDataManager:
    def __init__(self, exchange_manager: ExchangeManager):
        self.exchange_manager = exchange_manager
        self.cache = MarketDataCache(settings.scanner.cache_ttl_seconds)

    async def fetch_order_books(self, symbols: List[str]) -> Dict[str, Dict[str, NormalizedOrderBook]]:
        tasks = []
        task_map = []

        for exchange_name in self.exchange_manager.exchanges:
            for symbol in symbols:
                cached = await self.cache.get(exchange_name, symbol)
                if cached:
                    continue

                tasks.append(
                    self.exchange_manager.fetch_order_book(
                        exchange_name, symbol, settings.scanner.orderbook_depth
                    )
                )
                task_map.append((exchange_name, symbol))

        if not tasks:
            result = {}
            for ex in self.exchange_manager.exchanges:
                result[ex] = await self.cache.get_all(ex)
            return result

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for (exchange_name, symbol), ob_data in zip(task_map, results):
            if isinstance(ob_data, Exception):
                logger.warning(f"Failed to fetch {symbol} from {exchange_name}: {ob_data}")
                continue
            if not ob_data:
                continue

            normalized = self._normalize_order_book(exchange_name, symbol, ob_data)
            await self.cache.set(exchange_name, symbol, normalized)

        final_result = {}
        for exchange_name in self.exchange_manager.exchanges:
            final_result[exchange_name] = await self.cache.get_all(exchange_name)

        return final_result

    def _normalize_order_book(self, exchange: str, symbol: str, data: dict) -> NormalizedOrderBook:
        bids = [OrderBookLevel(price=b[0], amount=b[1]) for b in data.get("bids", [])[:20]]
        asks = [OrderBookLevel(price=a[0], amount=a[1]) for a in data.get("asks", [])[:20]]

        ts = data.get("timestamp")
        if ts:
            timestamp = datetime.utcfromtimestamp(ts / 1000)
        else:
            timestamp = datetime.utcnow()

        return NormalizedOrderBook(
            exchange=exchange, symbol=symbol, timestamp=timestamp,
            bids=bids, asks=asks
        )

    async def fetch_tickers_batch(self, symbols: List[str]) -> Dict[str, Dict[str, dict]]:
        result = {}
        for exchange_name in self.exchange_manager.exchanges:
            try:
                all_tickers = await self.exchange_manager.fetch_all_tickers(exchange_name)
                filtered = {sym: data for sym, data in all_tickers.items() if sym in symbols}
                result[exchange_name] = filtered
            except Exception as e:
                logger.warning(f"Batch ticker fetch failed for {exchange_name}: {e}")
                result[exchange_name] = {}
                for symbol in symbols:
                    try:
                        ticker = await self.exchange_manager.fetch_ticker(exchange_name, symbol)
                        if ticker:
                            result[exchange_name][symbol] = ticker
                    except Exception as e2:
                        logger.debug(f"Individual ticker fetch failed: {e2}")
        return result
