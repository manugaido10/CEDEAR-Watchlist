"""Price/CCL-derived instrumentation for reversal signals and near-misses (Fase B1).

"Registrar ahora, decidir después" (docs/ROADMAP_CONFIABILITY.md): these fields
are written to signals.jsonl and near_misses.jsonl for later analysis. They are
NEVER read by any gate, the score or the ranking.

Every field is always present in the record; None means "not computable"
(insufficient bars, missing columns, non-finite input, or the field does not
apply — e.g. USD-implied metrics for argentine stocks). Values are finite
floats or None: no NaN/inf ever reaches the JSONL.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Dict, Optional

import numpy as np
import pandas as pd

from data.models import AssetType, CCLSeries

MA200_WINDOW = 200

_ROUND_PCT = 4       # pct / ratio fields
_ROUND_SLOPE = 6     # normalized MA slope (~1e-3 magnitude)
_ROUND_LEVEL = 2     # RSI, weekly strength, ATR multiples


@dataclass(frozen=True)
class PriceInstrumentation:
    weekly_strength: Optional[float] = None
    ma50w_slope: Optional[float] = None
    atr_pct_14: Optional[float] = None           # ATR14 / close (Wilder)
    stop_dist_pct: Optional[float] = None        # (entry − invalidation) / entry
    stop_dist_atr: Optional[float] = None        # (entry − invalidation) / ATR14, price units
    ma200_dist_pct: Optional[float] = None       # (close − MA200) / MA200, signed
    rsi_14_usd_implied: Optional[float] = None
    weekly_strength_usd_implied: Optional[float] = None
    ma200_dist_pct_usd_implied: Optional[float] = None

    def to_record(self) -> Dict[str, Optional[float]]:
        return asdict(self)


def _finite(value: Optional[float], ndigits: int) -> Optional[float]:
    if value is None:
        return None
    v = float(value)
    if not math.isfinite(v):
        return None
    return round(v, ndigits)


def _ma200_dist_pct(close: np.ndarray) -> Optional[float]:
    if len(close) < MA200_WINDOW:
        return None
    window = np.asarray(close[-MA200_WINDOW:], dtype=float)
    if not np.all(np.isfinite(window)):
        return None
    ma200 = float(np.mean(window))
    if ma200 <= 0:
        return None
    return (float(window[-1]) - ma200) / ma200


def _usd_metrics(close: pd.Series, ccl_series: Optional[CCLSeries]) -> Dict[str, Optional[float]]:
    from analysis.reversal.fx_context import usd_implied_closes
    from analysis.reversal.reversal_scanner import _compute_rsi, _weekly_trend_details

    out: Dict[str, Optional[float]] = {
        "rsi_14_usd_implied": None,
        "weekly_strength_usd_implied": None,
        "ma200_dist_pct_usd_implied": None,
    }
    if ccl_series is None or ccl_series.data is None:
        return out
    usd = usd_implied_closes(close, ccl_series.data)
    if usd is None:
        return out
    out["rsi_14_usd_implied"] = _finite(_compute_rsi(usd.to_numpy()), _ROUND_LEVEL)
    out["weekly_strength_usd_implied"] = _finite(
        _weekly_trend_details(pd.DataFrame({"close": usd})).weekly_strength, _ROUND_LEVEL,
    )
    out["ma200_dist_pct_usd_implied"] = _finite(_ma200_dist_pct(usd.to_numpy()), _ROUND_PCT)
    return out


def compute_price_instrumentation(
    df: pd.DataFrame,
    asset_type: AssetType,
    ccl_series: Optional[CCLSeries],
    entry_price: float,
    invalidation: Optional[float],
) -> PriceInstrumentation:
    """Compute all Fase B1 price/CCL fields for one ticker.

    df: the scanner's prepared daily frame (lower-case columns, sorted, ffilled).
    invalidation: support × (1 − INVALIDATION_BUFFER), or None when there is no
        support within range (stop distances are then None).
    USD-implied fields apply to CEDEARs with a CCL series only.
    """
    from analysis.reversal.reversal_scanner import _compute_atr, _weekly_trend_details

    close = df["close"].astype(float)
    close_arr = close.to_numpy()

    weekly = _weekly_trend_details(df)

    atr: Optional[float] = None
    if "high" in df.columns and "low" in df.columns:
        atr = _compute_atr(df["high"].to_numpy(), df["low"].to_numpy(), close_arr)
    if atr is not None and atr <= 0:
        atr = None

    last = float(close_arr[-1]) if len(close_arr) else float("nan")
    atr_pct = atr / last if atr is not None and math.isfinite(last) and last > 0 else None

    stop_dist_pct: Optional[float] = None
    stop_dist_atr: Optional[float] = None
    if invalidation is not None and math.isfinite(entry_price) and entry_price > 0:
        stop_gap = entry_price - invalidation
        stop_dist_pct = stop_gap / entry_price
        if atr is not None:
            stop_dist_atr = stop_gap / atr

    usd = (
        _usd_metrics(close, ccl_series)
        if asset_type == AssetType.CEDEAR
        else {"rsi_14_usd_implied": None,
              "weekly_strength_usd_implied": None,
              "ma200_dist_pct_usd_implied": None}
    )

    return PriceInstrumentation(
        weekly_strength=_finite(weekly.weekly_strength, _ROUND_LEVEL),
        ma50w_slope=_finite(weekly.ma50w_slope, _ROUND_SLOPE),
        atr_pct_14=_finite(atr_pct, _ROUND_PCT),
        stop_dist_pct=_finite(stop_dist_pct, _ROUND_PCT),
        stop_dist_atr=_finite(stop_dist_atr, _ROUND_LEVEL),
        ma200_dist_pct=_finite(_ma200_dist_pct(close_arr), _ROUND_PCT),
        rsi_14_usd_implied=usd["rsi_14_usd_implied"],
        weekly_strength_usd_implied=usd["weekly_strength_usd_implied"],
        ma200_dist_pct_usd_implied=usd["ma200_dist_pct_usd_implied"],
    )
