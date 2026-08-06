# Crypto Arbitrage Scanner

A production-ready, modular cryptocurrency arbitrage detection system that continuously scans multiple exchanges to identify profitable trading opportunities.

## Features

- **Multi-Exchange Support**: Binance, Bybit, OKX, KuCoin, Kraken, Coinbase, Bitget, Gate.io, MEXC
- **Arbitrage Types**: Cross-exchange, Triangular, Multi-hop path finding
- **Real-Time Dashboard**: Flask-based web UI with live updates
- **Smart Alerts**: Desktop, Telegram, Discord, Email, Webhook
- **Fee Calculation**: Trading, withdrawal, network, and slippage costs
- **Opportunity Ranking**: ROI, liquidity, confidence scoring
- **Backtesting Engine**: Validate strategies on historical data
- **Paper Trading Mode**: Test without real money
- **Async Architecture**: Low-latency concurrent API requests

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure

Copy `.env.example` to `.env` and add your API keys (optional for public data scanning).

Edit `config.yaml` to customize filters, exchanges, and alerts.

### 3. Run

```bash
python main.py
```

### 4. View Dashboard

Open http://localhost:5000 in your browser.

## Project Structure

```
crypto_arbitrage/
├── config/
│   ├── __init__.py
│   └── settings.py
├── core/
│   ├── __init__.py
│   ├── exchange_manager.py
│   ├── market_data.py
│   └── arbitrage_detector.py
├── fees/
│   ├── __init__.py
│   └── fee_calculator.py
├── ranking/
│   ├── __init__.py
│   └── opportunity_ranker.py
├── alerts/
│   ├── __init__.py
│   └── alert_manager.py
├── dashboard/
│   ├── __init__.py
│   ├── app.py
│   └── templates/
│       └── index.html
├── backtest/
│   ├── __init__.py
│   └── engine.py
├── utils/
│   ├── __init__.py
│   └── helpers.py
├── data/
├── logs/
├── main.py
├── config.yaml
├── .env.example
├── requirements.txt
└── README.md
```

## API Endpoints

- `GET /api/opportunities` - Live arbitrage opportunities
- `GET /api/status` - Exchange connection statuses
- `GET /api/stats` - Scanner statistics

## Paper Trading vs Live

Set `paper_trading: true` in config to simulate trades without execution.
Set to `false` and implement execution logic in `main.py` for live trading.

## Docker Deployment

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
EXPOSE 5000
CMD ["python", "main.py"]
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `BINANCE_API_KEY` | Binance API key |
| `BYBIT_API_KEY` | Bybit API key |
| `OKX_API_KEY` | OKX API key |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token for alerts |
| `DISCORD_WEBHOOK_URL` | Discord webhook URL |
| `CONFIG_PATH` | Path to config file |

## License

MIT
