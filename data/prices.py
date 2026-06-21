from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

DEFAULT_LOOKBACK_DAYS = 730  # ~500 trading days; covers MA200 with comfortable margin
MIN_BARS_EXPECTED = 400


def fetch_prices(symbol_ars: str, lookback_days: int = DEFAULT_LOOKBACK_DAYS) -> Optional[pd.DataFrame]:
    """Fetch OHLCV data for a BYMA pesos-segment ticker (e.g. 'GGAL.BA').

    Always fetches the pesos segment (DECISIONS.md 2026-06-20 c). MEP segment
    tickers (e.g. GGALD.BA) are excluded at the universe level by
    refresh_universe.py, not here — this function has no way to distinguish
    legitimate tickers ending in D (e.g. YPFD.BA) from MEP variants.

    Returns a DataFrame with columns [open, high, low, close, volume] and a
    timezone-naive DatetimeIndex. Returns None if yfinance fails entirely.
    """
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
