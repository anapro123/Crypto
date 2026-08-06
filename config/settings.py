"""
Central configuration for the Crypto Arbitrage Scanner.
Supports YAML/JSON config files and environment variables.
"""

import os
import yaml
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from dotenv import load_dotenv

load_dotenv()


@dataclass
class ExchangeConfig:
    name: str
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    password: Optional[str] = None
    sandbox: bool = False
    enabled: bool = True
    rate_limit: int = 100
    timeout: int = 10
    markets: List[str] = field(default_factory=list)


@dataclass
class FilterConfig:
    base_currencies: List[str] = field(default_factory=lambda: ["USDT", "BTC", "ETH"])
    min_profit_pct: float = 0.1
    min_trade_volume_usd: float = 10000.0
    max_slippage_pct: float = 0.5
    supported_exchanges: List[str] = field(default_factory=list)
    market_type: str = "spot"
    blockchains: List[str] = field(default_factory=list)
    max_spread_pct: float = 2.0
    min_liquidity_depth: float = 5000.0


@dataclass
class AlertConfig:
    enabled: bool = True
    min_profit_pct: float = 0.2
    desktop_enabled: bool = True
    telegram_enabled: bool = False
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    discord_enabled: bool = False
    discord_webhook_url: str = ""
    email_enabled: bool = False
    email_smtp_host: str = "smtp.gmail.com"
    email_smtp_port: int = 587
    email_username: str = ""
    email_password: str = ""
    email_recipients: List[str] = field(default_factory=list)
    webhook_enabled: bool = False
    webhook_url: str = ""


@dataclass
class ScannerConfig:
    scan_interval_seconds: float = 2.0
    max_concurrent_requests: int = 50
    orderbook_depth: int = 20
    cache_ttl_seconds: float = 1.0
    paper_trading: bool = True
    log_level: str = "INFO"


class Settings:
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or os.getenv("CONFIG_PATH", "config.yaml")
        self.exchanges: List[ExchangeConfig] = []
        self.filters = FilterConfig()
        self.alerts = AlertConfig()
        self.scanner = ScannerConfig()
        self._load()

    def _load(self):
        if os.path.exists(self.config_path):
            with open(self.config_path, "r") as f:
                data = yaml.safe_load(f) or {}

            for ex_data in data.get("exchanges", []):
                self.exchanges.append(ExchangeConfig(**ex_data))

            if "filters" in data:
                self.filters = FilterConfig(**data["filters"])
            if "alerts" in data:
                self.alerts = AlertConfig(**data["alerts"])
            if "scanner" in data:
                self.scanner = ScannerConfig(**data["scanner"])
        else:
            default_exchanges = [
                "binance", "bybit", "okx", "kucoin",
                "kraken", "coinbase", "bitget", "gateio", "mexc"
            ]
            for name in default_exchanges:
                self.exchanges.append(ExchangeConfig(
                    name=name,
                    api_key=os.getenv(f"{name.upper()}_API_KEY"),
                    api_secret=os.getenv(f"{name.upper()}_API_SECRET")
                ))

    def to_dict(self) -> Dict:
        return {
            "exchanges": [vars(ex) for ex in self.exchanges],
            "filters": vars(self.filters),
            "alerts": vars(self.alerts),
            "scanner": vars(self.scanner)
        }


settings = Settings()
