"""
Arbitrage Detection Engine:
- Cross-exchange arbitrage
- Triangular arbitrage
- Multi-hop path finding
"""

import logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
import networkx as nx

from core.market_data import NormalizedOrderBook, MarketDataManager
from fees.fee_calculator import FeeCalculator
from config.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class ArbitrageOpportunity:
    id: str = ""
    type: str = ""
    symbol: str = ""
    buy_exchange: str = ""
    sell_exchange: str = ""
    buy_price: float = 0.0
    sell_price: float = 0.0
    spread_pct: float = 0.0
    gross_profit_pct: float = 0.0
    trading_fees_pct: float = 0.0
    withdrawal_fee_usd: float = 0.0
    network_fee_usd: float = 0.0
    slippage_pct: float = 0.0
    net_profit_pct: float = 0.0
    net_profit_usd: float = 0.0
    required_capital: float = 0.0
    liquidity_score: float = 0.0
    execution_time_ms: float = 0.0
    confidence_score: float = 0.0
    timestamp: datetime = field(default_factory=datetime.utcnow)
    buy_depth: float = 0.0
    sell_depth: float = 0.0
    composite_score: float = 0.0

    def __post_init__(self):
        if not self.id:
            ts = int(self.timestamp.timestamp())
            self.id = f"{self.type}_{self.buy_exchange}_{self.sell_exchange}_{self.symbol}_{ts}"


class ArbitrageDetector:
    def __init__(self, market_data: MarketDataManager, fee_calculator: FeeCalculator):
        self.market_data = market_data
        self.fee_calc = fee_calculator
        self._last_opportunities: Dict[str, ArbitrageOpportunity] = {}

    async def scan_cross_exchange(self, order_books: Dict[str, Dict[str, NormalizedOrderBook]]) -> List[ArbitrageOpportunity]:
        opportunities = []
        by_symbol: Dict[str, Dict[str, NormalizedOrderBook]] = {}

        for exchange, symbols in order_books.items():
            for symbol, ob in symbols.items():
                if symbol not in by_symbol:
                    by_symbol[symbol] = {}
                by_symbol[symbol][exchange] = ob

        for symbol, exchange_obs in by_symbol.items():
            if len(exchange_obs) < 2:
                continue

            best_ask = None
            best_bid = None
            ask_exchange = None
            bid_exchange = None

            for exchange, ob in exchange_obs.items():
                if ob.best_ask and (best_ask is None or ob.best_ask < best_ask):
                    best_ask = ob.best_ask
                    ask_exchange = exchange
                if ob.best_bid and (best_bid is None or ob.best_bid > best_bid):
                    best_bid = ob.best_bid
                    bid_exchange = exchange

            if not best_ask or not best_bid or ask_exchange == bid_exchange:
                continue

            spread_pct = ((best_bid - best_ask) / best_ask) * 100
            if spread_pct < settings.filters.min_profit_pct:
                continue

            fees = self.fee_calc.calculate_cross_exchange_fees(
                ask_exchange, bid_exchange, symbol, best_ask, best_bid
            )
            net_profit_pct = spread_pct - fees["total_fee_pct"] - fees["slippage_pct"]
            if net_profit_pct <= 0:
                continue

            buy_ob = exchange_obs[ask_exchange]
            sell_ob = exchange_obs[bid_exchange]
            buy_liquidity = buy_ob.get_liquidity_at_price(best_ask, "ask", 0.05)
            sell_liquidity = sell_ob.get_liquidity_at_price(best_bid, "bid", 0.05)
            max_trade = min(buy_liquidity, sell_liquidity)

            if max_trade < settings.filters.min_liquidity_depth:
                continue

            required_capital = max_trade
            net_profit_usd = required_capital * (net_profit_pct / 100)
            confidence = self._calculate_confidence(
                spread_pct, buy_liquidity, sell_liquidity, ask_exchange, bid_exchange
            )

            opp = ArbitrageOpportunity(
                type="cross_exchange", symbol=symbol,
                buy_exchange=ask_exchange, sell_exchange=bid_exchange,
                buy_price=best_ask, sell_price=best_bid,
                spread_pct=spread_pct, gross_profit_pct=spread_pct,
                trading_fees_pct=fees["trading_fee_pct"],
                withdrawal_fee_usd=fees["withdrawal_fee_usd"],
                network_fee_usd=fees["network_fee_usd"],
                slippage_pct=fees["slippage_pct"],
                net_profit_pct=net_profit_pct, net_profit_usd=net_profit_usd,
                required_capital=required_capital,
                liquidity_score=min(buy_liquidity, sell_liquidity) / 10000,
                confidence_score=confidence,
                buy_depth=buy_liquidity, sell_depth=sell_liquidity
            )
            opportunities.append(opp)

        return opportunities

    async def scan_triangular(self, order_books: Dict[str, Dict[str, NormalizedOrderBook]]) -> List[ArbitrageOpportunity]:
        opportunities = []

        for exchange, symbols in order_books.items():
            graph = nx.DiGraph()

            for symbol, ob in symbols.items():
                if not ob.best_bid or not ob.best_ask:
                    continue
                base, quote = symbol.split("/")
                graph.add_edge(quote, base, rate=1.0 / ob.best_ask, symbol=symbol, side="buy")
                graph.add_edge(base, quote, rate=ob.best_bid, symbol=symbol, side="sell")

            for start_currency in settings.filters.base_currencies:
                if start_currency not in graph:
                    continue
                for neighbor1 in graph.neighbors(start_currency):
                    for neighbor2 in graph.neighbors(neighbor1):
                        if graph.has_edge(neighbor2, start_currency):
                            cycle = [start_currency, neighbor1, neighbor2, start_currency]
                            amount = 1.0
                            path_details = []
                            total_slippage = 0.0

                            for i in range(len(cycle) - 1):
                                from_curr = cycle[i]
                                to_curr = cycle[i + 1]
                                edge_data = graph[from_curr][to_curr]
                                rate = edge_data["rate"]
                                symbol = edge_data["symbol"]

                                if symbol in symbols:
                                    ob = symbols[symbol]
                                    depth = ob.get_liquidity_at_price(
                                        ob.best_ask if edge_data["side"] == "buy" else ob.best_bid,
                                        edge_data["side"], 0.1
                                    )
                                    slip = self.fee_calc.estimate_slippage(symbol, amount, depth)
                                    total_slippage += slip

                                amount *= rate
                                path_details.append({"from": from_curr, "to": to_curr, "symbol": symbol, "rate": rate})

                            profit_pct = (amount - 1.0) * 100
                            trading_fees = self.fee_calc.get_trading_fee(exchange) * 3
                            net_profit_pct = profit_pct - trading_fees - total_slippage

                            if net_profit_pct > settings.filters.min_profit_pct:
                                opp = ArbitrageOpportunity(
                                    id=f"tri_{exchange}_{'_'.join(cycle)}_{int(datetime.utcnow().timestamp())}",
                                    type="triangular",
                                    symbol=" -> ".join(cycle),
                                    buy_exchange=exchange, sell_exchange=exchange,
                                    buy_price=1.0, sell_price=amount,
                                    spread_pct=profit_pct, gross_profit_pct=profit_pct,
                                    trading_fees_pct=trading_fees,
                                    slippage_pct=total_slippage,
                                    net_profit_pct=net_profit_pct,
                                    net_profit_usd=1000 * (net_profit_pct / 100),
                                    required_capital=1000.0,
                                    confidence_score=max(0, 100 - total_slippage * 10),
                                    timestamp=datetime.utcnow()
                                )
                                opportunities.append(opp)

        return opportunities

    async def scan_multi_hop(self, order_books: Dict[str, Dict[str, NormalizedOrderBook]], max_hops: int = 3) -> List[ArbitrageOpportunity]:
        opportunities = []

        for exchange, symbols in order_books.items():
            graph = nx.DiGraph()

            for symbol, ob in symbols.items():
                if not ob.best_bid or not ob.best_ask:
                    continue
                base, quote = symbol.split("/")
                weight_buy = -np.log(1.0 / ob.best_ask)
                graph.add_edge(quote, base, weight=weight_buy, symbol=symbol, rate=1.0 / ob.best_ask)
                weight_sell = -np.log(ob.best_bid)
                graph.add_edge(base, quote, weight=weight_sell, symbol=symbol, rate=ob.best_bid)

            try:
                for source in settings.filters.base_currencies:
                    if source not in graph:
                        continue
                    try:
                        path = nx.bellman_ford_path(graph, source, source, weight="weight")
                        if len(path) > 2 and len(path) <= max_hops + 1:
                            amount = 1.0
                            for i in range(len(path) - 1):
                                edge = graph[path[i]][path[i + 1]]
                                amount *= edge["rate"]

                            profit_pct = (amount - 1.0) * 100
                            if profit_pct > settings.filters.min_profit_pct:
                                opp = ArbitrageOpportunity(
                                    id=f"multi_{exchange}_{'_'.join(path)}",
                                    type="multi_hop",
                                    symbol=" -> ".join(path),
                                    buy_exchange=exchange, sell_exchange=exchange,
                                    buy_price=1.0, sell_price=amount,
                                    spread_pct=profit_pct,
                                    net_profit_pct=profit_pct * 0.95,
                                    confidence_score=70.0,
                                    timestamp=datetime.utcnow()
                                )
                                opportunities.append(opp)
                    except nx.NetworkXNoPath:
                        continue
            except Exception as e:
                logger.debug(f"Multi-hop scan error on {exchange}: {e}")

        return opportunities

    def _calculate_confidence(self, spread_pct: float, buy_depth: float, sell_depth: float,
                              buy_ex: str, sell_ex: str) -> float:
        score = 50.0
        score += min(spread_pct * 20, 20)
        min_depth = min(buy_depth, sell_depth)
        if min_depth > 50000:
            score += 15
        elif min_depth > 10000:
            score += 10
        elif min_depth > 5000:
            score += 5
        tier1 = {"binance", "coinbase", "kraken"}
        if buy_ex in tier1 and sell_ex in tier1:
            score += 10
        return min(score, 100.0)

    def detect_changes(self, new_opportunities: List[ArbitrageOpportunity]) -> Tuple[List[ArbitrageOpportunity], List[ArbitrageOpportunity], List[ArbitrageOpportunity]]:
        new_dict = {opp.id: opp for opp in new_opportunities}
        old_dict = self._last_opportunities

        new_ids = set(new_dict.keys()) - set(old_dict.keys())
        disappeared_ids = set(old_dict.keys()) - set(new_dict.keys())
        common_ids = set(new_dict.keys()) & set(old_dict.keys())

        new_opps = [new_dict[i] for i in new_ids]
        disappeared_opps = [old_dict[i] for i in disappeared_ids]
        updated_opps = []

        for oid in common_ids:
            if abs(new_dict[oid].net_profit_pct - old_dict[oid].net_profit_pct) > 0.05:
                updated_opps.append(new_dict[oid])

        self._last_opportunities = new_dict
        return new_opps, updated_opps, disappeared_opps
