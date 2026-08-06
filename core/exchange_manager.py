"""
Exchange Manager: Handles all exchange connections via CCXT async.
Implements rate limiting, retry logic, and connection pooling.
"""

import asyncio
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime

import ccxt.async_support as ccxt
from tenacity import retry, stop_after_attempt, wait_exponential

from config.settings import settings, ExchangeConfig

logger = logging.getLogger(__name__)


@dataclass
class ExchangeStatus:
    name: str
    connected: bool
    latency_ms: float = 0.0
    last_ping: Optional[datetime] = None
    error: Optional[str] = None


class ExchangeManager:
    def __init__(self):
        self.exchanges: Dict[str, ccxt.Exchange] = {}
        self.statuses: Dict[str, ExchangeStatus] = {}
        self._semaphores: Dict[str, asyncio.Semaphore] = {}
        self._lock = asyncio.Lock()

    async def initialize(self):
        tasks = []
        for ex_config in settings.exchanges:
            if ex_config.enabled:
                tasks.append(self._connect_exchange(ex_config))
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info(f"Initialized {len(self.exchanges)} exchanges")

    async def _connect_exchange(self, config: ExchangeConfig):
        try:
            exchange_class = getattr(ccxt, config.name)
            exchange = exchange_class({
                "apiKey": config.api_key,
                "secret": config.api_secret,
                "password": config.password,
                "sandbox": config.sandbox,
                "enableRateLimit": True,
                "options": {"defaultType": "spot"}
            })

            start = asyncio.get_event_loop().time()
            await exchange.load_markets()
            latency = (asyncio.get_event_loop().time() - start) * 1000

            async with self._lock:
                self.exchanges[config.name] = exchange
                self.statuses[config.name] = ExchangeStatus(
                    name=config.name,
                    connected=True,
                    latency_ms=latency,
                    last_ping=datetime.utcnow()
                )
                self._semaphores[config.name] = asyncio.Semaphore(
                    settings.scanner.max_concurrent_requests
                )

            logger.info(f"Connected to {config.name} (latency: {latency:.1f}ms)")

        except Exception as e:
            logger.error(f"Failed to connect {config.name}: {e}")
            self.statuses[config.name] = ExchangeStatus(
                name=config.name, connected=False, error=str(e)
            )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    async def fetch_order_book(self, exchange_name: str, symbol: str, limit: int = 20):
        if exchange_name not in self.exchanges:
            return None

        async with self._semaphores[exchange_name]:
            exchange = self.exchanges[exchange_name]
            try:
                start = asyncio.get_event_loop().time()
                ob = await exchange.fetch_order_book(symbol, limit=limit)
                latency = (asyncio.get_event_loop().time() - start) * 1000

                if exchange_name in self.statuses:
                    self.statuses[exchange_name].latency_ms = latency
                    self.statuses[exchange_name].last_ping = datetime.utcnow()

                return ob
            except ccxt.RateLimitExceeded:
                logger.warning(f"Rate limit hit on {exchange_name}, backing off...")
                await asyncio.sleep(2)
                raise
            except Exception as e:
                logger.error(f"Error fetching order book from {exchange_name}: {e}")
                raise

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    async def fetch_ticker(self, exchange_name: str, symbol: str):
        if exchange_name not in self.exchanges:
            return None

        async with self._semaphores[exchange_name]:
            exchange = self.exchanges[exchange_name]
            try:
                return await exchange.fetch_ticker(symbol)
            except Exception as e:
                logger.error(f"Error fetching ticker from {exchange_name}: {e}")
                raise

    async def fetch_all_tickers(self, exchange_name: str):
        if exchange_name not in self.exchanges:
            return {}

        async with self._semaphores[exchange_name]:
            exchange = self.exchanges[exchange_name]
            try:
                return await exchange.fetch_tickers()
            except Exception as e:
                logger.warning(f"Batch ticker fetch failed for {exchange_name}: {e}")
                return {}

    def get_common_symbols(self) -> List[str]:
        if not self.exchanges:
            return []

        common = None
        for name, exchange in self.exchanges.items():
            symbols = set(exchange.symbols)
            if common is None:
                common = symbols
            else:
                common &= symbols

        base_currencies = set(settings.filters.base_currencies)
        filtered = []
        for sym in common:
            for base in base_currencies:
                if sym.endswith(f"/{base}"):
                    filtered.append(sym)
                    break

        return sorted(filtered)

    async def close(self):
        tasks = [ex.close() for ex in self.exchanges.values()]
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("All exchange connections closed")

    def get_statuses(self) -> List[ExchangeStatus]:
        return list(self.statuses.values())
