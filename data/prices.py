from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Set

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

DEFAULT_LOOKBACK_DAYS = 730  # ~500 trading days; covers MA200 with comfortable margin
MIN_BARS_EXPECTED = 400

_EXCLUSIONS_PATH = Path(__file__).parent / "sources" / "yfinance_exclusions.json"
_excluded_ars_cache: Optional[Set[str]] = None


def _is_excluded_ars(symbol_ars: str) -> bool:
    global _excluded_ars_cache
    if _excluded_ars_cache is None:
        try:
            raw = json.loads(_EXCLUSIONS_PATH.read_text())
            _excluded_ars_cache = set(raw.get("excluded_ars", {}).keys())
        except Exception:
            _excluded_ars_cache = set()
    return symbol_ars in _excluded_ars_cache


def fetch_prices(symbol_ars: str, lookback_days: int = DEFAULT_LOOKBACK_DAYS) -> Optional[pd.DataFrame]:
    """Fetch OHLCV data for a BYMA pesos-segment ticker (e.g. 'GGAL.BA').

    Always fetches the pesos segment (DECISIONS.md 2026-06-20 c). MEP segment
    tickers (e.g. GGALD.BA) are excluded at the universe level by
    refresh_universe.py, not here — this function has no way to distinguish
    legitimate tickers ending in D (e.g. YPFD.BA) from MEP variants.

    Returns a DataFrame with columns [open, high, low, close, volume] and a
    timezone-naive DatetimeIndex. Returns None if yfinance fails entirely.
    """
    if _is_excluded_ars(symbol_ars):
        logger.debug("%s: skipped (in yfinance exclusions list)", symbol_ars)
        return None

    end = datetime.today()
    start = end - timedelta(days=lookback_days)

    try:
        ticker = yf.Ticker(symbol_ars)
        df = ticker.history(
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            auto_adjust=True,
        )
    except Exception as exc:
        logger.error("yfinance raised exception for %s: %s", symbol_ars, exc)
        return None

    if df is None or df.empty:
        logger.warning("yfinance returned empty data for %s", symbol_ars)
        return None

    df.columns = [c.lower() for c in df.columns]
    df.index = pd.to_datetime(df.index).tz_localize(None)

    available = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
    return df[available].sort_index()
