#!/usr/bin/env python3
"""
Real Data Diagnostic Tool
Fetches actual order books from exchanges and shows raw spreads.
Run this to verify your setup is getting real data.
"""

import asyncio
import sys
import logging

# Setup basic logging
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

async def test_real_data():
    """Test fetching real order books and calculating spreads."""

    try:
        import ccxt.async_support as ccxt
    except ImportError:
        print("ERROR: ccxt not installed. Run: pip install ccxt")
        return

    # Test with major exchanges (no API key needed for public data)
    exchanges_to_test = ["binance", "bybit", "okx", "kucoin", "kraken"]
    symbol = "BTC/USDT"

    print("=" * 70)
    print("REAL DATA DIAGNOSTIC")
    print("=" * 70)
    print(f"Fetching {symbol} order books from exchanges...")
    print("(This uses public market data - no API key needed)")
    print("=" * 70)

    results = {}

    for name in exchanges_to_test:
        try:
            exchange_class = getattr(ccxt, name)
            ex = exchange_class({"enableRateLimit": True})

            print(f"\nConnecting to {name}...", end=" ")
            await ex.load_markets()

            if symbol not in ex.symbols:
                print(f"SKIPPED ({symbol} not available)")
                await ex.close()
                continue

            ob = await ex.fetch_order_book(symbol, limit=5)
            await ex.close()

            bid = ob["bids"][0][0] if ob["bids"] else None
            ask = ob["asks"][0][0] if ob["asks"] else None

            if bid and ask:
                results[name] = {"bid": bid, "ask": ask}
                print(f"OK | Bid: ${bid:,.2f} | Ask: ${ask:,.2f}")
            else:
                print("EMPTY ORDER BOOK")

        except ccxt.NetworkError as e:
            print(f"NETWORK ERROR: {e}")
        except ccxt.ExchangeError as e:
            print(f"EXCHANGE ERROR: {e}")
        except Exception as e:
            print(f"FAILED: {type(e).__name__}: {e}")

    print("\n" + "=" * 70)
    print("ARBITRAGE ANALYSIS")
    print("=" * 70)

    if len(results) < 2:
        print("ERROR: Need at least 2 exchanges to find arbitrage.")
        print("Your IP might be blocked, or exchanges are unreachable.")
        return

    # Find best arbitrage
    best_spread = 0
    best_pair = None

    exchanges = list(results.keys())
    for i, buy_ex in enumerate(exchanges):
        for sell_ex in exchanges:
            if buy_ex == sell_ex:
                continue

            buy_price = results[buy_ex]["ask"]  # We pay the ask
            sell_price = results[sell_ex]["bid"]  # We get the bid

            if buy_price > 0:
                spread_pct = ((sell_price - buy_price) / buy_price) * 100

                # Estimate fees (taker fees ~0.1% each side = 0.2% total)
                net_spread = spread_pct - 0.2

                status = "PROFIT" if net_spread > 0 else "NO PROFIT"
                color = "*** " if net_spread > 0 else ""

                print(f"{color}Buy {symbol} on {buy_ex} @ ${buy_price:,.2f}")
                print(f"{color}Sell on {sell_ex} @ ${sell_price:,.2f}")
                print(f"{color}Spread: {spread_pct:.4f}% | After fees: {net_spread:.4f}% | {status}")
                print("-" * 50)

                if net_spread > best_spread:
                    best_spread = net_spread
                    best_pair = (buy_ex, sell_ex)

    print("\n" + "=" * 70)
    if best_pair and best_spread > 0:
        print(f"BEST OPPORTUNITY: {best_pair[0]} -> {best_pair[1]}")
        print(f"NET PROFIT: {best_spread:.4f}%")
        print("\nYour scanner WOULD catch this if it's running!")
    else:
        print("No profitable arbitrage found right now.")
        print("This is NORMAL - markets are usually efficient.")
        print("Try again in a few minutes or during high volatility.")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(test_real_data())
