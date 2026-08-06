"""
Backtesting Engine for arbitrage strategies.
Simulates trades on historical data to validate strategies.
"""

import logging
from typing import List
from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from core.arbitrage_detector import ArbitrageOpportunity

logger = logging.getLogger(__name__)


@dataclass
class BacktestTrade:
    timestamp: datetime
    opportunity: ArbitrageOpportunity
    executed: bool
    actual_profit_usd: float = 0.0
    reason: str = ""


@dataclass
class BacktestResult:
    strategy_name: str
    start_date: datetime
    end_date: datetime
    total_opportunities: int = 0
    executed_trades: int = 0
    total_profit_usd: float = 0.0
    total_loss_usd: float = 0.0
    win_rate: float = 0.0
    avg_profit_per_trade: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    trades: List[BacktestTrade] = field(default_factory=list)

    @property
    def net_pnl(self) -> float:
        return self.total_profit_usd - self.total_loss_usd

    @property
    def profit_factor(self) -> float:
        return self.total_profit_usd / self.total_loss_usd if self.total_loss_usd > 0 else float("inf")


class BacktestEngine:
    def __init__(self, execution_delay_ms: float = 500,
                 fill_rate: float = 0.95,
                 failure_rate: float = 0.05,
                 price_drift_pct: float = 0.02):
        self.execution_delay_ms = execution_delay_ms
        self.fill_rate = fill_rate
        self.failure_rate = failure_rate
        self.price_drift_pct = price_drift_pct
        self.results: List[BacktestResult] = []

    def run_backtest(self, opportunities: List[ArbitrageOpportunity],
                     strategy_name: str = "default") -> BacktestResult:
        if not opportunities:
            logger.warning("No opportunities provided for backtest")
            return BacktestResult(strategy_name=strategy_name,
                                  start_date=datetime.utcnow(),
                                  end_date=datetime.utcnow())

        result = BacktestResult(
            strategy_name=strategy_name,
            start_date=opportunities[0].timestamp,
            end_date=opportunities[-1].timestamp
        )

        for opp in opportunities:
            result.total_opportunities += 1
            trade = self._simulate_trade(opp)
            result.trades.append(trade)

            if trade.executed:
                result.executed_trades += 1
                if trade.actual_profit_usd > 0:
                    result.total_profit_usd += trade.actual_profit_usd
                else:
                    result.total_loss_usd += abs(trade.actual_profit_usd)

        if result.executed_trades > 0:
            result.win_rate = sum(1 for t in result.trades if t.executed and t.actual_profit_usd > 0) / result.executed_trades
            result.avg_profit_per_trade = result.net_pnl / result.executed_trades

        result.max_drawdown = self._calculate_max_drawdown(result.trades)
        self.results.append(result)
        logger.info(f"Backtest complete: {result}")
        return result

    def _simulate_trade(self, opp: ArbitrageOpportunity) -> BacktestTrade:
        import random

        if random.random() < self.failure_rate:
            return BacktestTrade(
                timestamp=opp.timestamp, opportunity=opp, executed=False,
                actual_profit_usd=0.0,
                reason="Execution failed (simulated network/exchange error)"
            )

        filled_amount = opp.required_capital * self.fill_rate
        drift_factor = 1 - (self.price_drift_pct / 100)
        actual_profit = opp.net_profit_usd * self.fill_rate * drift_factor
        noise = random.uniform(-0.1, 0.1)
        actual_profit *= (1 + noise)

        return BacktestTrade(
            timestamp=opp.timestamp, opportunity=opp, executed=True,
            actual_profit_usd=actual_profit, reason="Executed successfully"
        )

    def _calculate_max_drawdown(self, trades: List[BacktestTrade]) -> float:
        equity = 0.0
        peak = 0.0
        max_dd = 0.0

        for trade in trades:
            if trade.executed:
                equity += trade.actual_profit_usd
                if equity > peak:
                    peak = equity
                dd = (peak - equity) / peak if peak > 0 else 0
                max_dd = max(max_dd, dd)

        return max_dd * 100

    def generate_report(self, result: BacktestResult) -> str:
        lines = [
            "=" * 60,
            f"BACKTEST REPORT: {result.strategy_name}",
            "=" * 60,
            f"Period: {result.start_date} to {result.end_date}",
            f"Total Opportunities: {result.total_opportunities}",
            f"Executed Trades: {result.executed_trades}",
            f"Win Rate: {result.win_rate:.2%}",
            "",
            "P&L Summary:",
            f"  Gross Profit: ${result.total_profit_usd:,.2f}",
            f"  Gross Loss:   ${result.total_loss_usd:,.2f}",
            f"  Net P&L:      ${result.net_pnl:,.2f}",
            f"  Avg per Trade: ${result.avg_profit_per_trade:,.2f}",
            f"  Profit Factor: {result.profit_factor:.2f}",
            "",
            "Risk Metrics:",
            f"  Max Drawdown: {result.max_drawdown:.2f}%",
            "=" * 60
        ]
        return "\n".join(lines)

    def export_to_csv(self, result: BacktestResult, filepath: str):
        data = []
        for trade in result.trades:
            data.append({
                "timestamp": trade.timestamp,
                "symbol": trade.opportunity.symbol,
                "type": trade.opportunity.type,
                "buy_exchange": trade.opportunity.buy_exchange,
                "sell_exchange": trade.opportunity.sell_exchange,
                "expected_profit": trade.opportunity.net_profit_usd,
                "actual_profit": trade.actual_profit_usd if trade.executed else 0,
                "executed": trade.executed,
                "reason": trade.reason
            })

        df = pd.DataFrame(data)
        df.to_csv(filepath, index=False)
        logger.info(f"Backtest exported to {filepath}")
