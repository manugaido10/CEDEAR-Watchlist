"""Pure PnL calculations for tracked positions.

No I/O against the positions log here — these functions consume a Position
and external price/MEP inputs, and return plain dicts.
"""

from __future__ import annotations

import logging
from typing import Optional

import pandas as pd
import yfinance as yf

from data.positions_log import Position

logger = logging.getLogger(__name__)

_MERVAL_SYMBOL = "^MERV"

# Cocos Capital round-trip commission per leg (buy side and sell side each).
COMMISSION_RATE = 0.00555


def compute_realized_pnl(position: Position, mep_at_close: float) -> dict:
    if position.status != "closed" or position.close_price_ars is None:
        raise ValueError(f"compute_realized_pnl called on non-closed position {position.symbol}")

    invested = position.open_price_ars * position.qty
    gross_pnl_ars = (position.close_price_ars - position.open_price_ars) * position.qty
    buy_commission_ars = COMMISSION_RATE * invested
    sell_commission_ars = COMMISSION_RATE * position.close_price_ars * position.qty
    commission_ars = buy_commission_ars + sell_commission_ars
    pnl_ars = gross_pnl_ars - commission_ars
    pnl_pct = pnl_ars / invested * 100.0
    pnl_usd = pnl_ars / mep_at_close if mep_at_close > 0 else float("nan")

    return {
        "gross_pnl_ars": gross_pnl_ars,
        "commission_ars": commission_ars,
        "pnl_ars": pnl_ars,
        "pnl_pct": pnl_pct,
        "pnl_usd": pnl_usd,
        "realized": True,
    }


def compute_floating_pnl(position: Position, current_price_ars: float, mep_now: float) -> dict:
    # Buy commission is already sunk into the cost the user paid at entry.
    # For "should I sell now?" only the prospective sell-leg cost is live.
    invested = position.open_price_ars * position.qty
    gross_pnl_ars = (current_price_ars - position.open_price_ars) * position.qty
    sell_commission_ars = COMMISSION_RATE * current_price_ars * position.qty
    pnl_ars = gross_pnl_ars - sell_commission_ars
    pnl_pct = pnl_ars / invested * 100.0
    pnl_usd = pnl_ars / mep_now if mep_now > 0 else float("nan")

    return {
        "gross_pnl_ars": gross_pnl_ars,
        "sell_commission_ars": sell_commission_ars,
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
