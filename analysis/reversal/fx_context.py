"""FX decomposition context for reversal signals (Decision #31, Roadmap Fase A2).

Purpose
-------
A CEDEAR's ARS price mixes two orthogonal moves: the underlying asset (in USD)
and the peso itself (CCL). A "signal" measured in ARS may actually be measuring
FX drift. This module records, per opportunity at scan time:

    pct_change_ars_{5,20}d          — actual CEDEAR move in ARS
    pct_change_ccl_{5,20}d          — CCL move over the SAME calendar dates
    pct_change_usd_implied_{5,20}d  — (1 + ars) / (1 + ccl) − 1
                                      (asset-only move, assuming perfect arbitrage)

Plus the ratio + underlying symbol so downstream analyses can join or normalize.

Design notes
------------
- CCL lookups are aligned to the EXACT bar dates used for the ARS pct_change
  (5 or 20 bars back), never "5 calendar days ago" — otherwise weekends and
  holidays contaminate the decomposition.
- Argentine stocks (no CCL, no ratio, no underlying) return None: A2 does not
  apply to them.
- Insufficient bars for a window yield None for that window only (5d may
  succeed when 20d fails); other fields still populate.
- All errors are contained: the caller (scan_reversals) wraps the whole call
  in try/except with logger.warning, following the analyst_revision pattern.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

import pandas as pd

from data.models import AssetType, TickerBundle

logger = logging.getLogger(__name__)

_DEFAULT_WINDOWS_BARS: Tuple[int, ...] = (5, 20)


def _pct_change_bars(closes: pd.Series, n_bars: int) -> Optional[float]:
    """Return close[-1] / close[-n_bars-1] − 1, or None if insufficient bars."""
    if len(closes) < n_bars + 1:
        return None
    now = float(closes.iloc[-1])
    then = float(closes.iloc[-n_bars - 1])
    if then == 0.0:
        return None
    return now / then - 1.0


def _ccl_pct_change_aligned(
    ccl_series: pd.Series,
    price_index: pd.DatetimeIndex,
    n_bars: int,
) -> Optional[float]:
    """Return CCL % change between the same calendar dates as the ARS bars.

    Uses price_index[-1] and price_index[-n_bars-1] as the two anchor dates.
    CCL series is forward-filled per data/ccl.py, so any calendar date has a
    value. Returns None if either lookup fails or the earlier value is 0.
    """
    if len(price_index) < n_bars + 1:
        return None
    now_ts = pd.Timestamp(price_index[-1])
    then_ts = pd.Timestamp(price_index[-n_bars - 1])
    try:
        ccl_now = float(ccl_series.asof(now_ts))
        ccl_then = float(ccl_series.asof(then_ts))
    except Exception:
        return None
    if pd.isna(ccl_now) or pd.isna(ccl_then) or ccl_then == 0.0:
        return None
    return ccl_now / ccl_then - 1.0


def _implied_usd(pct_ars: Optional[float], pct_ccl: Optional[float]) -> Optional[float]:
    """Implicit underlying-USD move assuming perfect CEDEAR arbitrage."""
    if pct_ars is None or pct_ccl is None:
        return None
    denom = 1.0 + pct_ccl
    if denom == 0.0:
        return None
    return (1.0 + pct_ars) / denom - 1.0


def build_fx_enrichment(
    bundle: TickerBundle,
    windows_bars: Tuple[int, ...] = _DEFAULT_WINDOWS_BARS,
) -> Optional[Dict]:
    """Compile per-opportunity FX context. Returns None when A2 does not apply.

    A2 does not apply when: bundle is not a CEDEAR, OR bundle has no CCL series
    attached, OR the ARS price frame has no close column.
    """
    md = bundle.metadata
    if md.asset_type != AssetType.CEDEAR:
        return None
    if bundle.ccl_series is None or bundle.prices_ars is None:
        return None

    df = bundle.prices_ars.data
    if df is None or df.empty or "close" not in [c.lower() for c in df.columns]:
        return None

    closes = df["close"] if "close" in df.columns else df["Close"]
    closes = closes.astype(float)
    ccl = bundle.ccl_series.data

    enrichment: Dict = {
        "ccl_at_scan": round(float(bundle.ccl_series.spot), 2),
        "underlying_symbol": md.symbol_underlying,
        "cedears_per_underlying": md.cedears_per_underlying,
    }

    for n in windows_bars:
        pct_ars = _pct_change_bars(closes, n)
        pct_ccl = _ccl_pct_change_aligned(ccl, closes.index, n)
        pct_usd = _implied_usd(pct_ars, pct_ccl)
        enrichment[f"pct_change_ars_{n}d"] = round(pct_ars, 4) if pct_ars is not None else None
        enrichment[f"pct_change_ccl_{n}d"] = round(pct_ccl, 4) if pct_ccl is not None else None
        enrichment[f"pct_change_usd_implied_{n}d"] = (
            round(pct_usd, 4) if pct_usd is not None else None
        )

    return enrichment


def build_fx_enrichments(
    bundle_map: Dict[str, TickerBundle],
    opportunities: List,
) -> Dict[str, Dict]:
    """Batch wrapper. Returns {symbol_ars: enrichment_dict} for CEDEARs only.

    Argentine stocks (and any bundle where build_fx_enrichment returns None)
    are silently absent from the returned dict — signals for those tickers
    will simply not carry the fx_context field.
    """
    out: Dict[str, Dict] = {}
    for opp in opportunities:
        bundle = bundle_map.get(opp.symbol)
        if bundle is None:
            continue
        try:
            enrichment = build_fx_enrichment(bundle)
        except Exception as exc:
            logger.warning(
                "fx_context: enrichment failed for %s — %s", opp.symbol, exc
            )
            continue
        if enrichment is not None:
            out[opp.symbol] = enrichment
    return out
