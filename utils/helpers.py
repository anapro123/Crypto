"""
Utility helpers for logging, data formatting, and common operations.
"""

import logging
import sys
from datetime import datetime
from typing import Any, Dict

import colorlog


def setup_logging(log_level: str = "INFO", log_file: str = None):
    """Configure colored logging with optional file output."""

    formatter = colorlog.ColoredFormatter(
        "%(log_color)s%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        log_colors={
            'DEBUG': 'cyan',
            'INFO': 'green',
            'WARNING': 'yellow',
            'ERROR': 'red',
            'CRITICAL': 'bold_red',
        }
    )

    handler = colorlog.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))
    root_logger.handlers = []
    root_logger.addHandler(handler)

    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)

    return root_logger


def format_currency(value: float, symbol: str = "$") -> str:
    """Format currency value with appropriate precision."""
    if value >= 1_000_000:
        return f"{symbol}{value/1_000_000:.2f}M"
    elif value >= 1_000:
        return f"{symbol}{value/1_000:.2f}k"
    elif value >= 1:
        return f"{symbol}{value:.2f}"
    else:
        return f"{symbol}{value:.6f}"


def safe_divide(a: float, b: float, default: float = 0.0) -> float:
    """Safe division with default fallback."""
    try:
        return a / b if b != 0 else default
    except (TypeError, ZeroDivisionError):
        return default


def truncate_datetime(dt: datetime) -> str:
    """Truncate datetime to readable format."""
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def merge_dicts(base: Dict, override: Dict) -> Dict:
    """Deep merge two dictionaries."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_dicts(result[key], value)
        else:
            result[key] = value
    return result
