#!/usr/bin/env python3
"""
Simple Real-Time Arbitrage Monitor
Shows ONLY real spreads as they happen. No dashboard, just terminal output.
"""

import asyncio
import time
import ccxt.async_support as ccxt

EXCHANGES = ["binance", "bybit", "okx", "kucoin"]
SYMBOLS = ["BTC/USDT", "ETH/USDT", "ETH/BTC", "SOL/USDT", "XRP/USDT"]
MIN_SPREAD = 0.01  # 0.01%

async def monitor():
    # Connect to exchanges
    clients = {}
    for name in EXCHANGES:
        try:
            cls = getattr(ccxt, name)
            ex = cls({"enableRateLimit": True})
            await ex.load_markets()
            clients[name] = ex
            print(f"Connected: {name}")
        except Exception as e:
            print(f"Failed {name}: {e}")

    if len(clients) < 2:
        print("Need at least 2 exchanges. Exiting.")
        return

    print(f"\nMonitoring {len(SYMBOLS)} pairs across {len(clients)} exchanges...")
    print(f"Minimum spread to report: {MIN_SPREAD}%")
    print("=" * 70)

    found_count = 0

    while True:
        for symbol in SYMBOLS:
            prices = {}

            for name, ex in clients.items():
                if symbol not in ex.symbols:
                    continue
                try:
                    ticker = await ex.fetch_ticker(symbol)
                    prices[name] = {
                        "bid": ticker.get("bid"),
                        "ask": ticker.get("ask"),
                        "last": ticker.get("last")
                    }
                except Exception:
                    pass

            # Check all pairs
            names = list(prices.keys())
            for i in range(len(names)):
                for j in range(len(names)):
                    if i == j:
                        continue
                    buy_ex = names[i]
                    sell_ex = names[j]

                    buy_price = prices[buy_ex].get("ask")
                    sell_price = prices[sell_ex].get("bid")

                    if not buy_price or not sell_price or buy_price <= 0:
                        continue

                    spread = ((sell_price - buy_price) / buy_price) * 100

                    if spread >= MIN_SPREAD:
                        found_count += 1
                        print(f"\n[{found_count}] {symbol}")
                        print(f"    Buy  on {buy_ex:10s} @ ${buy_price:>12,.2f}")
                        print(f"    Sell on {sell_ex:10s} @ ${sell_price:>12,.2f}")
                        print(f"    SPREAD: {spread:.4f}%")
                        print("-" * 50)

        print(f"\rScanned... Found {found_count} opportunities so far. (Ctrl+C to stop)", end="", flush=True)
        await asyncio.sleep(2)

    # Cleanup
    for ex in clients.values():
        await ex.close()

if __name__ == "__main__":
    try:
        asyncio.run(monitor())
    except KeyboardInterrupt:
        print("\nStopped.")
