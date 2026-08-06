#!/usr/bin/env python3
"""
Demo Mode: Injects fake arbitrage opportunities into the dashboard
so you can see the UI working without waiting for real market conditions.
Run this INSTEAD of main.py for testing.
"""

import asyncio
import random
from datetime import datetime
from core.arbitrage_detector import ArbitrageOpportunity
from dashboard.app import run_dashboard, update_opportunities, update_statuses, update_stats
from core.exchange_manager import ExchangeStatus

# Start dashboard
run_dashboard(host='0.0.0.0', port=5000)

# Fake exchange statuses
statuses = [
    ExchangeStatus(name="binance", connected=True, latency_ms=12.0),
    ExchangeStatus(name="bybit", connected=True, latency_ms=18.0),
    ExchangeStatus(name="okx", connected=True, latency_ms=24.0),
    ExchangeStatus(name="kucoin", connected=True, latency_ms=31.0),
    ExchangeStatus(name="kraken", connected=True, latency_ms=45.0),
    ExchangeStatus(name="coinbase", connected=True, latency_ms=38.0),
    ExchangeStatus(name="bitget", connected=True, latency_ms=22.0),
    ExchangeStatus(name="gateio", connected=False, latency_ms=0.0, error="Timeout"),
    ExchangeStatus(name="mexc", connected=True, latency_ms=56.0),
]
update_statuses(statuses)

update_stats({
    'total_scans': 1427,
    'last_scan_time': datetime.utcnow().isoformat(),
    'avg_scan_time_ms': 142.5
})

PAIRS = [
    ("BTC/USDT", "binance", "bybit", 0.42, 0.38),
    ("ETH/USDT", "okx", "kucoin", 0.31, 0.28),
    ("ETH/BTC", "kraken", "binance", 0.55, 0.51),
    ("SOL/USDT", "mexc", "bybit", 0.67, 0.62),
    ("BTC/USDT", "gateio", "bitget", 0.28, 0.25),
    ("XRP/USDT", "kucoin", "mexc", 0.89, 0.85),
    ("BNB/USDT", "binance", "okx", 0.19, 0.17),
    ("ADA/USDT", "bybit", "kraken", 0.35, 0.32),
]

TYPES = ["cross_exchange", "triangular", "multi_hop"]

async def generate_fake_data():
    """Generate realistic fake arbitrage data every 3 seconds."""
    while True:
        num_opps = random.randint(3, 12)
        opportunities = []

        for i in range(num_opps):
            pair, buy_ex, sell_ex, spread, net = random.choice(PAIRS)

            # Add some randomness
            spread += random.uniform(-0.05, 0.15)
            net = spread * random.uniform(0.85, 0.95)

            buy_price = random.uniform(20000, 70000) if "BTC" in pair else random.uniform(1000, 4000)
            sell_price = buy_price * (1 + spread / 100)
            capital = random.choice([5000, 10000, 15000, 20000, 50000])

            opp = ArbitrageOpportunity(
                type=random.choice(TYPES) if random.random() > 0.6 else "cross_exchange",
                symbol=pair,
                buy_exchange=buy_ex,
                sell_exchange=sell_ex,
                buy_price=round(buy_price, 2),
                sell_price=round(sell_price, 2),
                spread_pct=round(spread, 3),
                gross_profit_pct=round(spread, 3),
                trading_fees_pct=round(spread - net, 3),
                net_profit_pct=round(net, 3),
                net_profit_usd=round(capital * (net / 100), 2),
                required_capital=capital,
                liquidity_score=round(random.uniform(0.5, 5.0), 2),
                confidence_score=round(random.uniform(65, 98), 1),
                buy_depth=round(random.uniform(10000, 100000), 2),
                sell_depth=round(random.uniform(10000, 100000), 2),
                timestamp=datetime.utcnow()
            )
            opportunities.append(opp)

        # Sort by net profit descending
        opportunities.sort(key=lambda x: x.net_profit_pct, reverse=True)

        update_opportunities(opportunities)
        print(f"[{datetime.utcnow().strftime('%H:%M:%S')}] Injected {len(opportunities)} fake opportunities")

        await asyncio.sleep(3)

if __name__ == "__main__":
    print("=" * 60)
    print("CRYPTO ARBITRAGE SCANNER - DEMO MODE")
    print("=" * 60)
    print("Dashboard: http://localhost:5000")
    print("This generates FAKE data for testing the UI.")
    print("Press Ctrl+C to stop.")
    print("=" * 60)

    try:
        asyncio.run(generate_fake_data())
    except KeyboardInterrupt:
        print("\nDemo stopped.")
