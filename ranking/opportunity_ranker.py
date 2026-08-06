"""
Opportunity Ranker: Filters, scores, and ranks arbitrage opportunities.
"""

import logging
from typing import List
from dataclasses import dataclass

from core.arbitrage_detector import ArbitrageOpportunity
from config.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class RankingWeights:
    roi_weight: float = 0.35
    net_profit_weight: float = 0.25
    liquidity_weight: float = 0.15
    confidence_weight: float = 0.15
    speed_weight: float = 0.10


class OpportunityRanker:
    def __init__(self, weights: RankingWeights = None):
        self.weights = weights or RankingWeights()

    def filter_opportunities(self, opportunities: List[ArbitrageOpportunity]) -> List[ArbitrageOpportunity]:
        filtered = []
        for opp in opportunities:
            if opp.net_profit_pct < settings.filters.min_profit_pct:
                continue
            if opp.slippage_pct > settings.filters.max_slippage_pct:
                continue
            if opp.required_capital < settings.filters.min_trade_volume_usd:
                continue
            min_depth = min(opp.buy_depth, opp.sell_depth)
            if min_depth < settings.filters.min_liquidity_depth:
                continue
            if settings.filters.supported_exchanges:
                if opp.buy_exchange not in settings.filters.supported_exchanges:
                    continue
                if opp.sell_exchange not in settings.filters.supported_exchanges:
                    continue
            filtered.append(opp)
        return filtered

    def rank_opportunities(self, opportunities: List[ArbitrageOpportunity]) -> List[ArbitrageOpportunity]:
        if not opportunities:
            return []

        max_roi = max(opp.net_profit_pct for opp in opportunities)
        max_profit = max(opp.net_profit_usd for opp in opportunities)
        max_liquidity = max(opp.liquidity_score for opp in opportunities) or 1.0

        scored_opportunities = []

        for opp in opportunities:
            roi_score = opp.net_profit_pct / max_roi if max_roi > 0 else 0
            profit_score = opp.net_profit_usd / max_profit if max_profit > 0 else 0
            liquidity_score = opp.liquidity_score / max_liquidity
            confidence_score = opp.confidence_score / 100.0
            speed_score = 1.0 / (1.0 + opp.execution_time_ms / 1000.0)

            composite = (
                roi_score * self.weights.roi_weight +
                profit_score * self.weights.net_profit_weight +
                liquidity_score * self.weights.liquidity_weight +
                confidence_score * self.weights.confidence_weight +
                speed_score * self.weights.speed_weight
            )

            opp.composite_score = composite
            scored_opportunities.append((composite, opp))

        scored_opportunities.sort(key=lambda x: x[0], reverse=True)
        return [opp for _, opp in scored_opportunities]

    def get_top_opportunities(self, opportunities: List[ArbitrageOpportunity],
                              n: int = 50) -> List[ArbitrageOpportunity]:
        filtered = self.filter_opportunities(opportunities)
        ranked = self.rank_opportunities(filtered)
        return ranked[:n]
