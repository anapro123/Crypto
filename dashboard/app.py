"""
Flask Dashboard with Server-Sent Events for real-time updates.
"""

import asyncio
import json
import logging
import threading
from datetime import datetime
from typing import List

from flask import Flask, render_template, jsonify
from flask_sse import sse

from core.arbitrage_detector import ArbitrageOpportunity

logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config["REDIS_URL"] = "redis://localhost:6379/0"
app.register_blueprint(sse, url_prefix="/stream")

_latest_opportunities: List[ArbitrageOpportunity] = []
_exchange_statuses = []
_scan_stats = {
    "total_scans": 0,
    "last_scan_time": None,
    "avg_scan_time_ms": 0
}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/opportunities")
def get_opportunities():
    data = [_opp_to_dict(opp) for opp in _latest_opportunities[:100]]
    return jsonify({
        "opportunities": data,
        "count": len(data),
        "timestamp": datetime.utcnow().isoformat()
    })


@app.route("/api/status")
def get_status():
    return jsonify({
        "exchanges": [
            {
                "name": s.name,
                "connected": s.connected,
                "latency_ms": s.latency_ms,
                "last_ping": s.last_ping.isoformat() if s.last_ping else None,
                "error": s.error
            }
            for s in _exchange_statuses
        ],
        "stats": _scan_stats
    })


@app.route("/api/stats")
def get_stats():
    if not _latest_opportunities:
        return jsonify({"message": "No data yet"})

    profits = [opp.net_profit_usd for opp in _latest_opportunities]
    rois = [opp.net_profit_pct for opp in _latest_opportunities]

    return jsonify({
        "total_opportunities": len(_latest_opportunities),
        "avg_profit_usd": sum(profits) / len(profits) if profits else 0,
        "max_profit_usd": max(profits) if profits else 0,
        "avg_roi_pct": sum(rois) / len(rois) if rois else 0,
        "max_roi_pct": max(rois) if rois else 0,
        "by_type": _group_by_type(_latest_opportunities)
    })


def _group_by_type(opportunities: List[ArbitrageOpportunity]) -> dict:
    result = {}
    for opp in opportunities:
        result[opp.type] = result.get(opp.type, 0) + 1
    return result


def _opp_to_dict(opp: ArbitrageOpportunity) -> dict:
    return {
        "id": opp.id,
        "type": opp.type,
        "symbol": opp.symbol,
        "buy_exchange": opp.buy_exchange,
        "sell_exchange": opp.sell_exchange,
        "buy_price": round(opp.buy_price, 8),
        "sell_price": round(opp.sell_price, 8),
        "spread_pct": round(opp.spread_pct, 4),
        "net_profit_pct": round(opp.net_profit_pct, 4),
        "net_profit_usd": round(opp.net_profit_usd, 2),
        "required_capital": round(opp.required_capital, 2),
        "confidence_score": round(opp.confidence_score, 1),
        "liquidity_score": round(opp.liquidity_score, 2),
        "timestamp": opp.timestamp.isoformat(),
        "composite_score": getattr(opp, "composite_score", 0)
    }


def update_opportunities(opportunities: List[ArbitrageOpportunity]):
    global _latest_opportunities
    _latest_opportunities = opportunities


def update_statuses(statuses: list):
    global _exchange_statuses
    _exchange_statuses = statuses


def update_stats(stats: dict):
    global _scan_stats
    _scan_stats.update(stats)


def run_dashboard(host="0.0.0.0", port=5000, debug=False):
    def _run():
        app.run(host=host, port=port, debug=debug, use_reloader=False)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    logger.info(f"Dashboard running at http://{host}:{port}")
    return thread
