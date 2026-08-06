#!/usr/bin/env python3
"""
Crypto Arbitrage Scanner - Main Entry Point

This is the main orchestrator that:
1. Initializes all components
2. Runs the continuous scanning loop
3. Manages alerts and dashboard updates
4. Handles graceful shutdown
"""

import asyncio
import signal
import sys
import time
import logging
from datetime import datetime
from typing import List

from config.settings import settings
from core.exchange_manager import ExchangeManager
from core.market_data import MarketDataManager
from core.arbitrage_detector import ArbitrageDetector
from fees.fee_calculator import FeeCalculator
from ranking.opportunity_ranker import OpportunityRanker
from alerts.alert_manager import AlertManager
from dashboard.app import run_dashboard, update_opportunities, update_statuses, update_stats
from utils.helpers import setup_logging
from backtest.engine import BacktestEngine

logger = logging.getLogger(__name__)


class ArbitrageScanner:
    def __init__(self):
        self.running = False
        self.exchange_manager = ExchangeManager()
        self.market_data = None
        self.fee_calculator = FeeCalculator()
        self.detector = None
        self.ranker = OpportunityRanker()
        self.alert_manager = AlertManager()
        self.backtest_engine = BacktestEngine()

        # Statistics
        self.scan_count = 0
        self.total_scan_time = 0.0
        self.all_time_opportunities: List = []

    async def initialize(self):
        """Initialize all components."""
        logger.info("=" * 60)
        logger.info("Crypto Arbitrage Scanner Starting...")
        logger.info("=" * 60)

        # Setup exchanges
        logger.info("Connecting to exchanges...")
        await self.exchange_manager.initialize()

        if not self.exchange_manager.exchanges:
            logger.error("No exchanges connected! Check API keys and network.")
            sys.exit(1)

        # Initialize dependent components
        self.market_data = MarketDataManager(self.exchange_manager)
        self.detector = ArbitrageDetector(self.market_data, self.fee_calculator)
        await self.alert_manager.initialize()

        # Start dashboard
        if settings.scanner.paper_trading:
            logger.info("Running in PAPER TRADING mode")

        run_dashboard(host='0.0.0.0', port=5000)

        # Get common symbols
        common_symbols = self.exchange_manager.get_common_symbols()
        logger.info(f"Found {len(common_symbols)} common trading pairs")
        logger.info(f"Base currencies: {settings.filters.base_currencies}")

        return common_symbols

    async def scan_cycle(self, symbols: List[str]):
        """Execute one full scan cycle."""
        start_time = time.time()

        try:
            # Fetch order books
            order_books = await self.market_data.fetch_order_books(symbols)

            # Detect opportunities
            cross_opps = await self.detector.scan_cross_exchange(order_books)
            tri_opps = await self.detector.scan_triangular(order_books)
            multi_opps = await self.detector.scan_multi_hop(order_books)

            all_opps = cross_opps + tri_opps + multi_opps

            # Rank and filter
            ranked = self.ranker.get_top_opportunities(all_opps, n=100)

            # Detect changes
            new, updated, disappeared = self.detector.detect_changes(ranked)

            # Send alerts
            for opp in new:
                await self.alert_manager.send_alert(
                    type('Event', (), {'event_type': 'new', 'opportunity': opp})()
                )

            for opp in updated:
                await self.alert_manager.send_alert(
                    type('Event', (), {'event_type': 'updated', 'opportunity': opp})()
                )

            # Update dashboard
            update_opportunities(ranked)
            update_statuses(self.exchange_manager.get_statuses())

            # Update stats
            scan_time = (time.time() - start_time) * 1000
            self.scan_count += 1
            self.total_scan_time += scan_time
            self.all_time_opportunities.extend(new)

            update_stats({
                'total_scans': self.scan_count,
                'last_scan_time': datetime.utcnow().isoformat(),
                'avg_scan_time_ms': self.total_scan_time / self.scan_count
            })

            # Log summary
            if ranked:
                best = ranked[0]
                logger.info(
                    f"Scan #{self.scan_count} | {len(ranked)} ops | "
                    f"Best: {best.symbol} {best.net_profit_pct:.3f}% | "
                    f"Time: {scan_time:.0f}ms"
                )
            else:
                logger.debug(f"Scan #{self.scan_count} | No opportunities | Time: {scan_time:.0f}ms")

        except Exception as e:
            logger.error(f"Scan cycle error: {e}", exc_info=True)

    async def run(self):
        """Main scanning loop."""
        symbols = await self.initialize()

        # Limit symbols for performance (prioritize high-volume pairs)
        priority_symbols = [s for s in symbols if any(
            x in s for x in ['BTC/USDT', 'ETH/USDT', 'ETH/BTC', 'SOL/USDT', 'BNB/USDT', 'XRP/USDT']
        )]
        other_symbols = [s for s in symbols if s not in priority_symbols]

        # Scan priority symbols every cycle, others every 5 cycles
        scan_symbols = priority_symbols[:50]  # Top 50 priority pairs

        self.running = True
        cycle = 0

        logger.info(f"Starting scan loop with {len(scan_symbols)} symbols")
        logger.info(f"Interval: {settings.scanner.scan_interval_seconds}s")

        while self.running:
            cycle += 1

            # Rotate symbols occasionally
            if cycle % 5 == 0 and other_symbols:
                extra = other_symbols[:20]
                current_symbols = list(set(scan_symbols + extra))
            else:
                current_symbols = scan_symbols

            await self.scan_cycle(current_symbols)

            # Wait for next scan
            await asyncio.sleep(settings.scanner.scan_interval_seconds)

    async def shutdown(self):
        """Graceful shutdown."""
        logger.info("Shutting down scanner...")
        self.running = False
        await self.exchange_manager.close()
        await self.alert_manager.shutdown()
        logger.info("Shutdown complete")

    def signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}")
        asyncio.create_task(self.shutdown())
        sys.exit(0)


async def main():
    """Entry point."""
    setup_logging(
        log_level=settings.scanner.log_level,
        log_file="logs/scanner.log"
    )

    scanner = ArbitrageScanner()

    # Register signal handlers
    signal.signal(signal.SIGINT, scanner.signal_handler)
    signal.signal(signal.SIGTERM, scanner.signal_handler)

    try:
        await scanner.run()
    except KeyboardInterrupt:
        await scanner.shutdown()
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
        await scanner.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
