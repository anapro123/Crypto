"""
Fee Calculator: Computes all trading costs including:
- Trading fees (maker/taker)
- Withdrawal/deposit fees
- Network/gas fees
- Slippage estimates
"""

import logging
from typing import Dict

from config.settings import settings

logger = logging.getLogger(__name__)


class FeeCalculator:
    DEFAULT_FEES = {
        "binance": {"maker": 0.0, "taker": 0.0, "withdrawal": 0.0, "deposit": 0.0},
        "bybit": {"maker": 0.0, "taker": 0.0, "withdrawal": 0.0, "deposit": 0.0},
        "okx": {"maker": 0.0, "taker": 0.0, "withdrawal": 0.0, "deposit": 0.0},
        "kucoin": {"maker": 0.0, "taker": 0.0, "withdrawal": 0.0, "deposit": 0.0},
        "kraken": {"maker": 0.0, "taker": 0.0, "withdrawal": 0.0, "deposit": 0.0},
        "coinbase": {"maker": 0.0, "taker": 0.0, "withdrawal": 0.0, "deposit": 0.0},
        "bitget": {"maker": 0.0, "taker": 0.0, "withdrawal": 0.0, "deposit": 0.0},
        "gateio": {"maker": 0.0, "taker": 0.0, "withdrawal": 0.0, "deposit": 0.0},
        "mexc": {"maker": 0.0, "taker": 0.0, "withdrawal": 0.0, "deposit": 0.0},
    }

    NETWORK_FEES = {
        "BTC": 5.0,
        "ETH": 3.0,
        "USDT": {"ERC20": 8.0, "TRC20": 1.0, "BEP20": 0.5, "SOL": 0.1},
        "default": 2.0
    }

    def __init__(self):
        self.fees = self.DEFAULT_FEES.copy()

    def get_trading_fee(self, exchange: str, side: str = "taker") -> float:
        ex_fees = self.fees.get(exchange.lower(), self.fees["binance"])
        return ex_fees.get(side, ex_fees["taker"])

    def get_withdrawal_fee(self, exchange: str, asset: str = "") -> float:
        ex_fees = self.fees.get(exchange.lower(), self.fees["binance"])
        return ex_fees.get("withdrawal", 1.0)

    def calculate_cross_exchange_fees(self, buy_exchange: str, sell_exchange: str,
                                       symbol: str, buy_price: float, sell_price: float) -> Dict:
        base, quote = symbol.split("/")
        buy_fee_pct = self.get_trading_fee(buy_exchange, "taker")
        sell_fee_pct = self.get_trading_fee(sell_exchange, "taker")
        total_trading_fee_pct = buy_fee_pct + sell_fee_pct

        withdrawal_fee = self.get_withdrawal_fee(buy_exchange, base)
        network_fee = self.get_network_fee(base)
        deposit_fee = 0.0

        assumed_trade_size = 10000.0
        slippage = self.estimate_slippage(symbol, assumed_trade_size)

        trade_value = assumed_trade_size
        fixed_fee_pct = ((withdrawal_fee + network_fee + deposit_fee) / trade_value) * 100
        total_fee_pct = total_trading_fee_pct + fixed_fee_pct + slippage

        return {
            "trading_fee_pct": total_trading_fee_pct,
            "withdrawal_fee_usd": withdrawal_fee,
            "network_fee_usd": network_fee,
            "deposit_fee_usd": deposit_fee,
            "slippage_pct": slippage,
            "total_fee_pct": total_fee_pct
        }

    def get_network_fee(self, asset: str, network: str = "default") -> float:
        fees = self.NETWORK_FEES.get(asset, self.NETWORK_FEES["default"])
        if isinstance(fees, dict):
            return fees.get(network, fees.get("ERC20", 2.0))
        return fees

    def estimate_slippage(self, symbol: str, trade_size_usd: float,
                          available_liquidity: float = 0) -> float:
        if available_liquidity <= 0:
            if trade_size_usd < 1000:
                return 0.05
            elif trade_size_usd < 10000:
                return 0.10
            elif trade_size_usd < 50000:
                return 0.25
            else:
                return 0.50

        ratio = trade_size_usd / available_liquidity
        slippage = ratio * 0.5
        return min(slippage, 5.0)

    def calculate_net_profit(self, gross_profit_pct: float, fees: Dict,
                             trade_size: float = 10000.0) -> float:
        total_fee_pct = fees["total_fee_pct"]
        net_pct = gross_profit_pct - total_fee_pct
        return trade_size * (net_pct / 100)
