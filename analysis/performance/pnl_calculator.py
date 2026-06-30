"""Pure PnL calculations for tracked positions.

No I/O against the positions log here — these functions consume a Position
and external price/CCL inputs, and return plain dicts.
"""

from __future__ import annotations

import logging
from typing import Optional

import pandas as pd
import yfinance as yf

from data.positions_log import Position

logger = logging.getLogger(__name__)

_MERVAL_SYMBOL = "^MERV"


def compute_realized_pnl(position: Position, ccl_at_close: float) -> dict:
    if position.status != "closed" or position.close_price_ars is None:
        raise ValueError(f"compute_realized_pnl called on non-closed position {position.symbol}")

    pnl_ars = (position.close_price_ars - position.open_price_ars) * position.qty
    pnl_pct = (position.close_price_ars / position.open_price_ars - 1.0) * 100.0
    pnl_usd = pnl_ars / ccl_at_close if ccl_at_close > 0 else float("nan")

    return {
        "pnl_ars": pnl_ars,
        "pnl_pct": pnl_pct,
        "pnl_usd": pnl_usd,
        "realized": True,
    }


def compute_floating_pnl(position: Position, current_price_ars: float, ccl_now: float) -> dict:
    pnl_ars = (current_price_ars - position.open_price_ars) * position.qty
    pnl_pct = (current_price_ars / position.open_price_ars - 1.0) * 100.0
    pnl_usd = pnl_ars / ccl_now if ccl_now > 0 else float("nan")

    return {
        "pnl_ars": pnl_ars,
        "pnl_pct": pnl_pct,
        "pnl_usd": pnl_usd,
        "realized": False,
        "current_price_ars": current_price_ars,
    }


def compute_merval_return(open_date: str, close_date: str) -> Optional[float]:
    """Percent return of ^MERV between open_date and close_date (inclusive of close).

    Returns None when yfinance cannot supply enough data — a missing benchmark must
    not break the performance report.
    """
    try:
        start = pd.Timestamp(open_date)
        end = pd.Timestamp(close_date) + pd.Timedelta(days=1)
        df = yf.download(
            _MERVAL_SYMBOL,
            start=start,
            end=end,
            progress=False,
            auto_adjust=False,
        )
        if df is None or df.empty or "Close" not in df.columns:
            return None
        closes = df["Close"].dropna()
        if len(closes) < 2:
            return None
        first = float(closes.iloc[0])
        last = float(closes.iloc[-1])
        if first <= 0:
            return None
        return (last / first - 1.0) * 100.0
    except Exception as exc:
        logger.warning("Merval return fetch failed for %s..%s: %s", open_date, close_date, exc)
        return None
