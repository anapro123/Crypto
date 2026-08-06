"""
Alert Manager: Handles all notification channels.
Supports Desktop, Telegram, Discord, Email, and Webhook.
"""

import asyncio
import logging
import json
from typing import List, Dict
from dataclasses import dataclass
from datetime import datetime

import aiohttp
from plyer import notification

from config.settings import settings, AlertConfig
from core.arbitrage_detector import ArbitrageOpportunity

logger = logging.getLogger(__name__)


@dataclass
class AlertEvent:
    event_type: str
    opportunity: ArbitrageOpportunity
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()


class AlertManager:
    def __init__(self):
        self.config: AlertConfig = settings.alerts
        self._session: aiohttp.ClientSession = None
        self._last_alert_time: Dict[str, datetime] = {}
        self._alert_cooldown_seconds = 30

    async def initialize(self):
        self._session = aiohttp.ClientSession()

    async def shutdown(self):
        if self._session:
            await self._session.close()

    def _should_alert(self, opportunity: ArbitrageOpportunity) -> bool:
        key = opportunity.id
        now = datetime.utcnow()
        if key in self._last_alert_time:
            elapsed = (now - self._last_alert_time[key]).total_seconds()
            if elapsed < self._alert_cooldown_seconds:
                return False
        self._last_alert_time[key] = now
        return True

    async def send_alert(self, event: AlertEvent):
        if not self.config.enabled:
            return

        opp = event.opportunity
        if opp.net_profit_pct < self.config.min_profit_pct:
            return
        if not self._should_alert(opp):
            return

        message = self._format_message(event)
        tasks = []

        if self.config.desktop_enabled:
            tasks.append(self._send_desktop(message))
        if self.config.telegram_enabled:
            tasks.append(self._send_telegram(message))
        if self.config.discord_enabled:
            tasks.append(self._send_discord(message))
        if self.config.email_enabled:
            tasks.append(self._send_email(message))
        if self.config.webhook_enabled:
            tasks.append(self._send_webhook(event))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def _format_message(self, event: AlertEvent) -> str:
        opp = event.opportunity
        emoji = {"new": "NEW", "updated": "UPD", "disappeared": "GONE", "threshold": "ALERT"}.get(event.event_type, "INFO")
        return (
            f"[{emoji}] Arbitrage: {event.event_type.upper()}\n"
            f"Pair: {opp.symbol}\n"
            f"Type: {opp.type.replace(\'_\', \' \').title()}\n"
            f"Buy: {opp.buy_exchange} @ ${opp.buy_price:,.2f}\n"
            f"Sell: {opp.sell_exchange} @ ${opp.sell_price:,.2f}\n"
            f"Spread: {opp.spread_pct:.3f}%\n"
            f"Net Profit: {opp.net_profit_pct:.3f}% (${opp.net_profit_usd:,.2f})\n"
            f"Confidence: {opp.confidence_score:.0f}%\n"
            f"Required Capital: ${opp.required_capital:,.2f}"
        )

    async def _send_desktop(self, message: str):
        try:
            notification.notify(title="Crypto Arbitrage Alert", message=message, timeout=10)
        except Exception as e:
            logger.error(f"Desktop notification failed: {e}")

    async def _send_telegram(self, message: str):
        try:
            url = f"https://api.telegram.org/bot{self.config.telegram_bot_token}/sendMessage"
            payload = {"chat_id": self.config.telegram_chat_id, "text": message, "parse_mode": "HTML"}
            async with self._session.post(url, json=payload) as resp:
                if resp.status != 200:
                    logger.warning(f"Telegram alert failed: {resp.status}")
        except Exception as e:
            logger.error(f"Telegram alert failed: {e}")

    async def _send_discord(self, message: str):
        try:
            payload = {"content": message, "username": "Arbitrage Bot"}
            async with self._session.post(self.config.discord_webhook_url, json=payload) as resp:
                if resp.status not in (200, 204):
                    logger.warning(f"Discord alert failed: {resp.status}")
        except Exception as e:
            logger.error(f"Discord alert failed: {e}")

    async def _send_email(self, message: str):
        try:
            import aiosmtplib
            from email.mime.text import MIMEText

            msg = MIMEText(message)
            msg["Subject"] = f"Arbitrage Alert - {datetime.utcnow().strftime(\'%Y-%m-%d %H:%M:%S\')}"
            msg["From"] = self.config.email_username
            msg["To"] = ", ".join(self.config.email_recipients)

            await aiosmtplib.send(
                msg, hostname=self.config.email_smtp_host, port=self.config.email_smtp_port,
                username=self.config.email_username, password=self.config.email_password, start_tls=True
            )
        except Exception as e:
            logger.error(f"Email alert failed: {e}")

    async def _send_webhook(self, event: AlertEvent):
        try:
            payload = {
                "event_type": event.event_type,
                "timestamp": event.timestamp.isoformat(),
                "opportunity": {
                    "id": event.opportunity.id,
                    "type": event.opportunity.type,
                    "symbol": event.opportunity.symbol,
                    "buy_exchange": event.opportunity.buy_exchange,
                    "sell_exchange": event.opportunity.sell_exchange,
                    "net_profit_pct": event.opportunity.net_profit_pct,
                    "net_profit_usd": event.opportunity.net_profit_usd,
                    "confidence_score": event.opportunity.confidence_score
                }
            }
            async with self._session.post(self.config.webhook_url, json=payload) as resp:
                if resp.status not in (200, 201, 202):
                    logger.warning(f"Webhook alert failed: {resp.status}")
        except Exception as e:
            logger.error(f"Webhook alert failed: {e}")

    async def notify_status_change(self, exchange: str, status: str, error: str = None):
        message = f"Exchange Status Change: {exchange}\nStatus: {status}"
        if error:
            message += f"\nError: {error}"
        if self.config.desktop_enabled:
            await self._send_desktop(message)
