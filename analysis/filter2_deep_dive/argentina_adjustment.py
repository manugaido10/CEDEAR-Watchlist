"""Filter 2 — Técnica 4: Argentina risk adjustment.

Produces ArgentinaAdjustment with argentina_penalty ∈ [0, 25].
This block only subtracts — it never discards a ticker.

For CEDEARs (DISENO_FILTRO_2.md §5.1):
  ccl_vol_penalty  (0-10): CCL volatility over last 30 days
  premium_penalty  (0-10): CEDEAR/underlying implied-ARS premium
  liquidity_penalty (0-5): CEDEAR traded value vs. underlying traded value

For Argentine stocks (DISENO_FILTRO_2.md §5.2):
  ccl_vol_penalty  (0-8): CCL volatility (same computation, different cap)
  a3_flag_penalty  (5-10): if argentina_risk_flags.yaml marks the ticker a3

Underlying prices (for premium + liquidity) fetched via yfinance, cached 1 day.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Set, Tuple

import numpy as np
import yaml

from data.cache import Cache
from data.models import AssetType, TickerBundle
from data.prices import fetch_prices

from .filter2_models import ArgentinaAdjustment
from .filter2_thresholds import (
    A3_PENALTY_BASE,
    A3_PENALTY_MAX,
    ARGENTINA_MAX_PENALTY,
    CCL_VOL_ARGENTINA_MAX_PTS,
    CCL_VOL_CEDEAR_MAX_PTS,
    CCL_VOL_HIGH_THRESHOLD,
    CCL_VOL_LOOKBACK_DAYS,
    CCL_VOL_LOW_THRESHOLD,
    PREMIUM_ALIGNED_THRESHOLD,
    PREMIUM_CHEAP_PTS,
    PREMIUM_CHEAP_THRESHOLD,
    PREMIUM_EXPENSIVE_THRESHOLD,
    PREMIUM_MAX_PTS,
    UNDERLYING_LOOKBACK_DAYS,
)

logger = logging.getLogger(__name__)

_DEFAULT_FLAGS_PATH = Path(__file__).parent.parent / "argentina_risk_flags.yaml"
_flags_cache: Optional[Dict[str, Dict[str, str]]] = None

_EXCLUSIONS_PATH = Path(__file__).parent.parent.parent / "data" / "sources" / "yfinance_exclusions.json"
_excluded_underlyings_cache: Optional[Set[str]] = None


def _load_excluded_underlyings() -> Set[str]:
    global _excluded_underlyings_cache
    if _excluded_underlyings_cache is None:
        try:
            raw = json.loads(_EXCLUSIONS_PATH.read_text())
            _excluded_underlyings_cache = set(raw.get("excluded_underlyings", {}).keys())
        except Exception:
            _excluded_underlyings_cache = set()
    return _excluded_underlyings_cache


def _load_risk_flags(path: Path = _DEFAULT_FLAGS_PATH) -> Dict[str, Dict[str, str]]:
    global _flags_cache
    if _flags_cache is not None:
        return _flags_cache
    if not path.exists():
        logger.warning("argentina_risk_flags.yaml not found at %s", path)
        _flags_cache = {}
        return _flags_cache
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    _flags_cache = data.get("tickers") or {}
    return _flags_cache


def clear_flags_cache() -> None:
    global _flags_cache
    _flags_cache = None


# ── CCL volatility ─────────────────────────────────────────────────────────────

def _ccl_vol_penalty(bundle: TickerBundle, max_pts: float) -> Tuple[float, Dict[str, Any]]:
    """Compute penalty from CCL volatility over CCL_VOL_LOOKBACK_DAYS."""
    if bundle.ccl_series is None or bundle.ccl_series.data.empty:
        return 0.0, {"ccl_vol": None, "note": "CCL series unavailable"}

    series = bundle.ccl_series.data.astype(float)
    lookback = min(CCL_VOL_LOOKBACK_DAYS, len(series))
    if lookback < 5:
        return 0.0, {"ccl_vol": None, "note": "insufficient CCL data"}

    recent = series.iloc[-lookback:]
    mean_ccl = float(recent.mean())
    std_ccl = float(recent.std())

    if mean_ccl < 1e-6:
        return 0.0, {"ccl_vol": None, "note": "CCL mean near-zero"}

    vol_ratio = std_ccl / mean_ccl

    # Linear map: [LOW, HIGH] → [0, max_pts]
    if vol_ratio <= CCL_VOL_LOW_THRESHOLD:
        penalty = 0.0
    elif vol_ratio >= CCL_VOL_HIGH_THRESHOLD:
        penalty = max_pts
    else:
        t = (vol_ratio - CCL_VOL_LOW_THRESHOLD) / (CCL_VOL_HIGH_THRESHOLD - CCL_VOL_LOW_THRESHOLD)
        penalty = max_pts * t

    return round(penalty, 2), {
        "ccl_vol_ratio": round(vol_ratio, 4),
        "ccl_mean": round(mean_ccl, 2),
        "ccl_std": round(std_ccl, 2),
    }


# ── Underlying price fetch ─────────────────────────────────────────────────────

def _get_underlying_prices(symbol_underlying: str, cache: Cache) -> Optional[Any]:
    """Fetch underlying stock prices, using Cache. Returns DataFrame or None."""
    cached = cache.load_prices(symbol_underlying)
    if cached is not None and not cached.empty:
        import pandas as pd
        last_bar = pd.Timestamp(cached.index[-1]).date()
        from datetime import date, timedelta
        if last_bar >= (date.today() - timedelta(days=3)):
            return cached

    df = fetch_prices(symbol_underlying, lookback_days=UNDERLYING_LOOKBACK_DAYS)
    if df is not None:
        cache.save_prices(symbol_underlying, df)
    return df


# ── CEDEAR premium ─────────────────────────────────────────────────────────────

def _premium_penalty(
    bundle: TickerBundle,
    underlying_df: Optional[Any],
) -> Tuple[float, Dict[str, Any]]:
    """Compute CEDEAR/underlying implied-ARS premium penalty."""
    meta = bundle.metadata

    if underlying_df is None or underlying_df.empty:
        return 0.0, {"premium": None, "note": "underlying prices unavailable"}
    if bundle.ccl_series is None:
        return 0.0, {"premium": None, "note": "CCL unavailable"}
    if meta.cedears_per_underlying is None or meta.cedears_per_underlying <= 0:
        return 0.0, {"premium": None, "note": "cedears_per_underlying not set"}
    if bundle.prices_ars is None or bundle.prices_ars.data.empty:
        return 0.0, {"premium": None, "note": "prices_ars unavailable"}

    underlying_close_usd = float(underlying_df["close"].iloc[-1])
    ccl_spot = bundle.ccl_series.spot
    cedears_per_underlying = meta.cedears_per_underlying
    actual_ars = float(bundle.prices_ars.data["close"].iloc[-1])

    # implied_ars = underlying_usd / cedears_per_underlying * ccl_spot
    implied_ars = underlying_close_usd / cedears_per_underlying * ccl_spot

    if implied_ars < 1e-6:
        return 0.0, {"premium": None, "note": "implied ARS price near-zero"}

    premium = actual_ars / implied_ars - 1.0

    # Map premium to penalty
    abs_prem = abs(premium)
    if abs_prem < PREMIUM_ALIGNED_THRESHOLD:
        penalty = 0.0
    elif premium > PREMIUM_EXPENSIVE_THRESHOLD:
        # Paying more than subyacente → max penalty
        t = min((premium - PREMIUM_EXPENSIVE_THRESHOLD) / 0.10 + 1.0, 1.0)
        penalty = PREMIUM_MAX_PTS * t
    elif premium < PREMIUM_CHEAP_THRESHOLD:
        # CEDEAR trading at discount (low demand signal)
        penalty = PREMIUM_CHEAP_PTS
    else:
        # Intermediate zone: linear scale
        t = abs_prem / PREMIUM_EXPENSIVE_THRESHOLD
        penalty = PREMIUM_MAX_PTS * t * 0.6  # less severe in intermediate zone

    penalty = min(penalty, PREMIUM_MAX_PTS)

    return round(penalty, 2), {
        "underlying_close_usd": round(underlying_close_usd, 4),
        "implied_ars": round(implied_ars, 2),
        "actual_ars": round(actual_ars, 2),
        "premium_pct": round(premium * 100, 2),
        "ccl_spot": round(ccl_spot, 2),
    }


# ── CEDEAR liquidity ───────────────────────────────────────────────────────────

def _liquidity_penalty(
    bundle: TickerBundle,
    underlying_df: Optional[Any],
) -> Tuple[float, Dict[str, Any]]:
    """Compute liquidity ratio penalty: CEDEAR daily USD value / underlying daily USD value."""
    if underlying_df is None or underlying_df.empty:
        return 0.0, {"liquidity_ratio": None, "note": "underlying unavailable"}
    if bundle.prices_ars is None or bundle.prices_ars.data.empty:
        return 0.0, {"liquidity_ratio": None, "note": "prices_ars unavailable"}
    if bundle.ccl_series is None:
        return 0.0, {"liquidity_ratio": None, "note": "CCL unavailable"}

    import numpy as np_inner

    ccl_spot = bundle.ccl_series.spot
    cedear_df = bundle.prices_ars.data

    lookback = min(LIQUIDITY_LOOKBACK_DAYS, len(cedear_df))
    cedear_recent = cedear_df.iloc[-lookback:]
    cedear_daily_ars = cedear_recent["close"].astype(float) * cedear_recent["volume"].astype(float)
    cedear_daily_usd = cedear_daily_ars / ccl_spot if ccl_spot > 0 else cedear_daily_ars
    cedear_median_usd = float(np_inner.median(cedear_daily_usd.values))

    lookback_u = min(LIQUIDITY_LOOKBACK_DAYS, len(underlying_df))
    under_recent = underlying_df.iloc[-lookback_u:]
    under_daily_usd = under_recent["close"].astype(float) * under_recent["volume"].astype(float)
    under_median_usd = float(np_inner.median(under_daily_usd.values))

    if under_median_usd < 1e-6:
        return 0.0, {"liquidity_ratio": None, "note": "underlying volume near-zero"}

    ratio = cedear_median_usd / under_median_usd

    if ratio >= LIQUIDITY_HIGH_THRESHOLD:
        penalty = 0.0
    elif ratio <= LIQUIDITY_LOW_THRESHOLD:
        penalty = LIQUIDITY_MAX_PTS
    else:
        # Log-linear interpolation between LOW and HIGH thresholds
        import math
        lo = math.log10(max(LIQUIDITY_LOW_THRESHOLD, 1e-10))
        hi = math.log10(LIQUIDITY_HIGH_THRESHOLD)
        t = (hi - math.log10(ratio)) / (hi - lo)
        penalty = LIQUIDITY_MAX_PTS * max(0.0, min(t, 1.0))

    return round(penalty, 2), {
        "cedear_median_usd_day": round(cedear_median_usd, 0),
        "underlying_median_usd_day": round(under_median_usd, 0),
        "liquidity_ratio": round(ratio, 6),
    }


# ── Main entry point ───────────────────────────────────────────────────────────

def compute_argentina_adjustment(
    bundle: TickerBundle,
    cache: Cache,
    flags_path: Optional[Path] = None,
) -> ArgentinaAdjustment:
    """Compute Argentina risk adjustment for a survivor.

    For CEDEARs: CCL vol + premium + liquidity (cap 25).
    For Argentine stocks: CCL vol + A3 flag (cap 25).
    """
    warnings: list[str] = []
    meta = bundle.metadata
    symbol = meta.symbol_ars
    flags = _load_risk_flags(flags_path or _DEFAULT_FLAGS_PATH)

    if meta.asset_type == AssetType.CEDEAR:
        # CCL volatility
        ccl_pen, ccl_info = _ccl_vol_penalty(bundle, CCL_VOL_CEDEAR_MAX_PTS)

        # Underlying prices needed for premium + liquidity
        underlying_df: Optional[Any] = None
        if meta.symbol_underlying:
            if meta.symbol_underlying in _load_excluded_underlyings():
                logger.debug("%s: underlying %s skipped (in yfinance exclusions list)", symbol, meta.symbol_underlying)
            else:
                try:
                    underlying_df = _get_underlying_prices(meta.symbol_underlying, cache)
                except Exception as exc:
                    warnings.append(f"underlying fetch failed for {meta.symbol_underlying}: {exc}")

        prem_pen, prem_info = _premium_penalty(bundle, underlying_df)
        # _liquidity_penalty removed: compares BYMA vs NYSE/NASDAQ volumes — markets
        # incomparable in scale. Filter 1 C4 already discards genuinely illiquid CEDEARs.
        # Re-enable if a Cocos-native liquidity source becomes available (e.g. pyCocos).

        total = min(ccl_pen + prem_pen, ARGENTINA_MAX_PENALTY)
        premium_pct = prem_info.get("premium_pct")

        breakdown: Dict[str, Any] = {
            "asset_type": "cedear",
            "ccl_vol": ccl_info,
            "premium": prem_info,
        }

        return ArgentinaAdjustment(
            ccl_vol_penalty=ccl_pen,
            premium_penalty=prem_pen,
            premium_pct=premium_pct / 100.0 if premium_pct is not None else None,
            total_penalty=round(total, 2),
            breakdown=breakdown,
            warnings=warnings,
        )

    else:
        # Argentine stock: CCL vol + A3 flag
        ccl_pen, ccl_info = _ccl_vol_penalty(bundle, CCL_VOL_ARGENTINA_MAX_PTS)

        a3_flag = False
        a3_penalty = 0.0
        a3_reason = ""
        ticker_flags = flags.get(symbol, {})
        if "a3" in ticker_flags:
            a3_flag = True
            a3_reason = str(ticker_flags["a3"])
            a3_penalty = A3_PENALTY_BASE
            logger.debug("%s: A3 flag active — penalty %.0f: %s", symbol, a3_penalty, a3_reason)

        total = min(ccl_pen + a3_penalty, ARGENTINA_MAX_PENALTY)
        breakdown = {
            "asset_type": "argentine_stock",
            "ccl_vol": ccl_info,
            "a3_flag": a3_flag,
            "a3_reason": a3_reason,
        }

        return ArgentinaAdjustment(
            ccl_vol_penalty=ccl_pen,
            a3_flag=a3_flag,
            a3_penalty=a3_penalty,
            a3_reason=a3_reason,
            total_penalty=round(total, 2),
            breakdown=breakdown,
            warnings=warnings,
        )
