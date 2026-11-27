"""Volume ratio over *valid* sessions (P2, docs/HALLAZGOS_2026-11-27.md §1.5).

yfinance emits phantom bars (flat OHLC, volume 0) on days nothing traded, and the
.BA series carries bars on NYSE-closed days that say nothing about local demand for
a US-underlying CEDEAR. ``vol_ratio_clean`` is the 5d/20d ratio computed over the
last 5 / 20 *valid* sessions. Recorded only — the gate still uses ``vol_ratio``.

Exclusion rules for a bar on day d:
  1. d is a phantom day (>= PHANTOM_DAY_THRESHOLD of tickers with a bar that day
     have a flat, zero-volume bar): every flat zero-volume bar is excluded.
  2. NYSE closed on d and the underlying is US-listed / an ADR: the whole bar is
     excluded (this is what reproduces the §1.5 reference ratios: ADI/UGP on
     2026-11-26 carry small real volume that is not representative).
  Otherwise the bar counts, including zero-volume bars of illiquid papers.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Iterable, Optional

import numpy as np
import pandas as pd

from data.market_calendar import nyse_closed
from data.models import AssetType, TickerBundle

logger = logging.getLogger(__name__)

PHANTOM_DAY_THRESHOLD = 0.30
PHANTOM_MIN_TICKERS = 20      # below this the cross-section is not meaningful
PHANTOM_LOOKBACK_BARS = 120   # only recent days can fall inside a 20-session window


def _flat_zero_mask(df: pd.DataFrame) -> pd.Series:
    return (
        (df["open"] == df["high"]) & (df["high"] == df["low"])
        & (df["low"] == df["close"]) & (df["volume"] == 0)
    )


def _normalized(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    d = df.copy()
    d.columns = [c.lower() for c in d.columns]
    if not {"open", "high", "low", "close", "volume"} <= set(d.columns):
        return None
    return d


def compute_phantom_days(
    bundles: Iterable[TickerBundle],
    threshold: float = PHANTOM_DAY_THRESHOLD,
    min_tickers: int = PHANTOM_MIN_TICKERS,
) -> frozenset:
    """Days where >= threshold of tickers with a bar have a flat, zero-volume bar."""
    with_bar: dict = {}
    flat: dict = {}
    for b in bundles:
        if b.prices_ars is None or b.prices_ars.data.empty:
            continue
        d = _normalized(b.prices_ars.data.tail(PHANTOM_LOOKBACK_BARS))
        if d is None:
            continue
        d = d.dropna(subset=["close"])
        mask = _flat_zero_mask(d)
        for ts, is_flat in zip(d.index, mask.values):
            day = ts.date() if hasattr(ts, "date") else ts
            with_bar[day] = with_bar.get(day, 0) + 1
            if is_flat:
                flat[day] = flat.get(day, 0) + 1
    phantom = frozenset(
        day for day, n in with_bar.items()
        if n >= min_tickers and flat.get(day, 0) / n >= threshold
    )
    if phantom:
        logger.info("volume_sessions: phantom days detected: %s", sorted(str(x) for x in phantom))
    return phantom


def has_us_underlying(bundle: TickerBundle) -> bool:
    """CEDEAR whose underlying trades in the US (or is an ADR).

    The universe leaves ``symbol_underlying`` empty for papers whose underlying is
    only listed abroad (XETRA, LSE, ...), so a set value means a US ticker.
    """
    m = bundle.metadata
    return m.asset_type == AssetType.CEDEAR and bool(m.symbol_underlying)


def valid_session_mask(
    df: pd.DataFrame, phantom_days: frozenset, us_underlying: bool
) -> np.ndarray:
    """Boolean array aligned with df rows: True = valid session."""
    flat0 = _flat_zero_mask(df).values
    keep = np.ones(len(df), dtype=bool)
    for i, ts in enumerate(df.index):
        day: date = ts.date() if hasattr(ts, "date") else ts
        if flat0[i] and day in phantom_days:
            keep[i] = False
        elif us_underlying and nyse_closed(day):
            keep[i] = False
    return keep


def volume_ratio_clean(
    df: pd.DataFrame, phantom_days: frozenset, us_underlying: bool
) -> Optional[float]:
    """5/20 ratio over the last 5 / 20 valid sessions; None if < 20 valid sessions."""
    d = _normalized(df)
    if d is None:
        return None
    d = d.tail(PHANTOM_LOOKBACK_BARS)  # a 20-session window never needs older bars
    vol = d["volume"].values[valid_session_mask(d, phantom_days, us_underlying)]
    if len(vol) < 20:
        return None
    avg_20 = float(np.mean(vol[-20:]))
    if avg_20 < 1e-10:
        return None
    return float(np.mean(vol[-5:])) / avg_20
