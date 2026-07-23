"""Early accumulation scanner — detects tickers in silent accumulation before momentum is obvious.

See docs/DECISIONS.md #13 for the full design rationale.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional, Set, Tuple

import numpy as np
from scipy.stats import linregress

from data.models import AssetType, FetchStatus, TickerBundle
from analysis.filter2_deep_dive.filter2_models import FundamentalState

logger = logging.getLogger(__name__)

# ── Thresholds ─────────────────────────────────────────────────────────────────

MIN_BARS = 60
REGRESSION_LOOKBACK = 40        # daily bars for linear regression (C1)
R_SQUARED_MIN = 0.60            # C1: minimum R² for consistent trend
HIGH_52W_MAX_PCT = 0.85         # C2: price must be below this fraction of 52W high
SWING_LOW_LOOKBACK = 40         # invalidation: bars to look back for swing low
INVALIDATION_BUFFER = 0.015     # 1.5% below support level
SUPPORT_PROXIMITY_MAX = 0.10    # 10% max distance to support for invalidation
SLOPE_REF = 0.002               # reference slope_normalized → 35 pts (0.2%/day)
MAX_OPPORTUNITIES = 5           # cap output at top-5 by score


# ── Output model ───────────────────────────────────────────────────────────────

@dataclass
class AccumulationOpportunity:
    symbol: str
    name: str
    asset_type: str               # "cedear" | "argentine_stock"
    score: float                  # 0-100
    slope_normalized: float       # daily slope / mean_price (relative %)
    r_squared: float              # regression R²
    volume_ratio: float           # vol_4w_recent / vol_4w_prior
    pct_of_52w_high: float        # current_price / 52w_high
    invalidation_level_ars: float
    invalidation_rationale: str
    warnings: List[str] = field(default_factory=list)


# ── Regression ────────────────────────────────────────────────────────────────

def _regression(close: np.ndarray) -> Tuple[float, float]:
    """Return (slope_normalized, r_squared) over the last REGRESSION_LOOKBACK bars."""
    window = close[-REGRESSION_LOOKBACK:]
    x = np.arange(len(window), dtype=float)
    slope, _, r, _, _ = linregress(x, window.astype(float))
    r_squared = float(r ** 2)
    mean_price = float(np.mean(window))
    slope_normalized = float(slope) / mean_price if mean_price > 1e-10 else 0.0
    return slope_normalized, r_squared


# ── 52-week high ──────────────────────────────────────────────────────────────

def _pct_of_52w_high(close: np.ndarray) -> float:
    """Return current_price / max(close over last 252 bars)."""
    lookback = min(252, len(close))
    high_52w = float(np.max(close[-lookback:]))
    last = float(close[-1])
    if high_52w < 1e-10:
        return 1.0
    return last / high_52w


# ── Volume ratio ──────────────────────────────────────────────────────────────

def _volume_ratio(volume: np.ndarray) -> Tuple[float, bool]:
    """Return (vol_4w_recent / vol_4w_prior, data_sufficient).

    vol_4w_recent = mean of last 20 trading days
    vol_4w_prior  = mean of days 21-40 before today
    Returns (1.0, False) if fewer than 40 bars available.
    """
    if len(volume) < 40:
        return 1.0, False
    recent = float(np.mean(volume[-20:]))
    prior = float(np.mean(volume[-40:-20]))
    if prior < 1e-10:
        return 1.0, False
    return recent / prior, True


# ── Invalidation level ────────────────────────────────────────────────────────

def _find_invalidation(close: np.ndarray) -> Tuple[float, str]:
    """Nearest support below current price within 10%, minus 1.5% buffer.

    Checks MA50, MA200, swing low (last 40 bars).
    Fallback: MA50 × 0.97 if no support found within 10%.
    """
    n = len(close)
    last = float(close[-1])

    candidates: List[Tuple[float, str]] = []
    if n >= 50:
        candidates.append((float(np.mean(close[-50:])), "MA50"))
    if n >= 200:
        candidates.append((float(np.mean(close[-200:])), "MA200"))

    lookback = min(SWING_LOW_LOOKBACK, n - 1)
    if lookback > 0:
        swing_low = float(np.min(close[-(lookback + 1):-1]))
        candidates.append((swing_low, "swing_low"))

    valid = [
        (level, stype)
        for level, stype in candidates
        if level < last and (last - level) / last <= SUPPORT_PROXIMITY_MAX
    ]

    if valid:
        best_level, best_type = max(valid, key=lambda x: x[0])
    else:
        ma50 = float(np.mean(close[-50:])) if n >= 50 else last * 0.90
        best_level = ma50 * 0.97
        best_type = "MA50×0.97 (fallback)"

    invalidation = best_level * (1.0 - INVALIDATION_BUFFER)
    rationale = (
        f"{best_type} at {best_level:.2f} ARS"
        f" — stop {INVALIDATION_BUFFER:.1%} below ({invalidation:.2f} ARS)"
    )
    return round(invalidation, 2), rationale


# ── Fundamentals gate ─────────────────────────────────────────────────────────

def _fundamentals_ok(bundle: TickerBundle) -> bool:
    """Return False only if fundamentals are explicitly deteriorating."""
    if bundle.fundamentals is None:
        return True  # no data → skip criterion (benefit of doubt)

    try:
        from analysis.filter2_deep_dive.fundamental_quality import score_fundamental_quality
        result = score_fundamental_quality(bundle)
        return result.fundamental_state != FundamentalState.DETERIORATING
    except Exception:
        return True  # scoring failed → don't discard


# ── Score ─────────────────────────────────────────────────────────────────────

def _compute_score(
    slope_normalized: float,
    r_squared: float,
    volume_ratio: float,
    pct_of_52w_high: float,
) -> float:
    """Accumulation score 0-100 per DECISIONS.md #13."""
    # Slope (0-35): SLOPE_REF=0.002 → 35 pts, linear, capped
    slope_pts = min(max(slope_normalized / SLOPE_REF * 35.0, 0.0), 35.0)

    # R² (0-25): 0.60 → 0 pts, 1.0 → 25 pts, linear
    r2_pts = min(max((r_squared - R_SQUARED_MIN) / (1.0 - R_SQUARED_MIN) * 25.0, 0.0), 25.0)

    # Volume growth (0-20): 1.0x → 0 pts, ≥2.0x → 20 pts, linear
    vol_pts = min(max((volume_ratio - 1.0) / (2.0 - 1.0) * 20.0, 0.0), 20.0)

    # Distance from 52W high (0-20): 85% → 0 pts, 50% → 20 pts, linear
    dist_pts = min(max((HIGH_52W_MAX_PCT - pct_of_52w_high) / (HIGH_52W_MAX_PCT - 0.50) * 20.0, 0.0), 20.0)

    return round(min(slope_pts + r2_pts + vol_pts + dist_pts, 100.0), 1)


# ── Per-ticker evaluation ─────────────────────────────────────────────────────

def _evaluate_bundle(
    bundle: TickerBundle,
    momentum_symbols: Set[str],
) -> Optional[AccumulationOpportunity]:
    symbol = bundle.metadata.symbol_ars
    name = bundle.metadata.name
    asset_type = bundle.metadata.asset_type.value

    if bundle.prices_ars is None or bundle.prices_ars.data.empty:
        logger.debug("%s: skipped — no price data", symbol)
        return None

    if bundle.status in (FetchStatus.MISSING, FetchStatus.ERROR):
        logger.debug("%s: skipped — fetch status %s", symbol, bundle.status)
        return None

    df = bundle.prices_ars.data.copy()
    df.columns = [c.lower() for c in df.columns]
    df = df.sort_index()

    for col in ["open", "high", "low", "close", "volume"]:
        if col in df.columns:
            df[col] = df[col].astype(float).ffill()

    if len(df) < MIN_BARS:
        logger.debug("%s: skipped — only %d bars (need %d)", symbol, len(df), MIN_BARS)
        return None

    close = df["close"].values

    # ── C5: not already in momentum ranking ───────────────────────────────────
    if symbol in momentum_symbols:
        logger.debug("%s: skipped — already in momentum ranking (C5)", symbol)
        return None

    # ── C1: consistent uptrend — positive slope AND R² > 0.60 ────────────────
    if len(close) < REGRESSION_LOOKBACK:
        logger.debug("%s: skipped — fewer than %d bars for regression", symbol, REGRESSION_LOOKBACK)
        return None

    slope_normalized, r_squared = _regression(close)
    if slope_normalized <= 0:
        logger.debug("%s: skipped — slope ≤ 0 (%.6f) (C1)", symbol, slope_normalized)
        return None
    if r_squared <= R_SQUARED_MIN:
        logger.debug("%s: skipped — R²=%.3f ≤ %.2f (C1)", symbol, r_squared, R_SQUARED_MIN)
        return None

    # ── C2: price below 85% of 52-week high ───────────────────────────────────
    pct_high = _pct_of_52w_high(close)
    if pct_high >= HIGH_52W_MAX_PCT:
        logger.debug("%s: skipped — %.1f%% of 52W high ≥ 85%% (C2)", symbol, pct_high * 100)
        return None

    # ── C3: volume growing ────────────────────────────────────────────────────
    warnings: List[str] = []
    vol = df["volume"].values
    vol_ratio, vol_sufficient = _volume_ratio(vol)
    if not vol_sufficient:
        warnings.append("Fewer than 40 volume bars: C3 skipped, volume_ratio set to 1.0")
    elif vol_ratio <= 1.0:
        logger.debug("%s: skipped — volume_ratio=%.3f ≤ 1.0 (C3)", symbol, vol_ratio)
        return None

    # ── C4: fundamentals not deteriorating (skipped for Argentine stocks) ─────
    if bundle.metadata.asset_type != AssetType.ARGENTINE_STOCK:
        if not _fundamentals_ok(bundle):
            logger.debug("%s: skipped — fundamentals deteriorating (C4)", symbol)
            return None

    # ── Score and invalidation ─────────────────────────────────────────────────
    score = _compute_score(slope_normalized, r_squared, vol_ratio, pct_high)
    invalidation_level, invalidation_rationale = _find_invalidation(close)

    return AccumulationOpportunity(
        symbol=symbol,
        name=name,
        asset_type=asset_type,
        score=score,
        slope_normalized=round(slope_normalized, 6),
        r_squared=round(r_squared, 4),
        volume_ratio=round(vol_ratio, 3),
        pct_of_52w_high=round(pct_high, 4),
        invalidation_level_ars=invalidation_level,
        invalidation_rationale=invalidation_rationale,
        warnings=warnings,
    )


# ── Main entry point ──────────────────────────────────────────────────────────

def scan_accumulation(
    bundles: List[TickerBundle],
    momentum_symbols: Optional[Set[str]] = None,
) -> List[AccumulationOpportunity]:
    """Scan all bundles for early accumulation opportunities.

    Returns up to MAX_OPPORTUNITIES results sorted by score descending.
    """
    if momentum_symbols is None:
        momentum_symbols = set()

    opportunities: List[AccumulationOpportunity] = []

    for bundle in bundles:
        try:
            opp = _evaluate_bundle(bundle, momentum_symbols)
            if opp is not None:
                opportunities.append(opp)
        except Exception as exc:
            logger.error("Error evaluating %s: %s", bundle.metadata.symbol_ars, exc)

    opportunities.sort(key=lambda x: x.score, reverse=True)

    if len(opportunities) > MAX_OPPORTUNITIES:
        logger.info(
            "scan_accumulation: %d signals found, capping at top %d by score",
            len(opportunities),
            MAX_OPPORTUNITIES,
        )
        opportunities = opportunities[:MAX_OPPORTUNITIES]

    return opportunities
