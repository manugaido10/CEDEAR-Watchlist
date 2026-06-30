"""Tactical reversal scanner — independent of the momentum pipeline.

Scans the full universe for mean-reversion opportunities: oversold tickers
with price near a relevant support level and at least one reversal catalyst.
See docs/DECISIONS.md #11 for the full design rationale.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

from data.models import AssetType, FetchStatus, TickerBundle
from analysis.filter2_deep_dive.filter2_models import FundamentalState

logger = logging.getLogger(__name__)

# ── Thresholds ─────────────────────────────────────────────────────────────────

MIN_BARS = 60           # minimum daily bars required
RSI_PERIOD = 14
RSI_LOW = 25.0          # lower bound of target RSI range
RSI_HIGH = 45.0         # upper bound of target RSI range
VOL_RATIO_THRESHOLD = 0.80   # vol_5d / vol_20d must be < this
SUPPORT_PROXIMITY_MAX = 0.05  # price must be within 5% of a support
SWING_LOW_LOOKBACK = 40      # bars to look back for swing low
DIVERGENCE_LOOKBACK = 10     # bars to look back for RSI divergence
MA200_PROXIMITY = 0.02       # 2% proximity for MA200 catalyst
INVALIDATION_BUFFER = 0.015  # 1.5% below support

# Weekly trend thresholds
WEEKLY_STRENGTH_NEUTRAL_MIN = 8.0   # weekly_strength >= this → positive/neutral
WEEKLY_MA50_SLOPE_LOOKBACK = 5      # weeks for MA50 slope


# ── Output model ───────────────────────────────────────────────────────────────

@dataclass
class ReversalOpportunity:
    symbol: str
    name: str
    asset_type: str                  # "cedear" | "argentine_stock"
    score: float                     # 0-100
    rsi_14: float
    nearest_support: float           # ARS
    nearest_support_type: str        # "MA50" | "MA200" | "swing_low"
    distance_to_support_pct: float   # positive = price above support
    catalyst: List[str]              # detected catalysts
    volume_ratio: float              # vol_5d / vol_20d
    weekly_trend: str                # "positive" | "neutral" | "negative"
    invalidation_level_ars: float
    invalidation_rationale: str
    warnings: List[str] = field(default_factory=list)


# ── RSI ────────────────────────────────────────────────────────────────────────

def _compute_rsi(closes: np.ndarray, period: int = RSI_PERIOD) -> Optional[float]:
    if len(closes) < period + 2:
        return None
    deltas = np.diff(closes.astype(float))
    gains = np.maximum(deltas, 0.0)
    losses = np.abs(np.minimum(deltas, 0.0))
    avg_gain = float(np.mean(gains[:period]))
    avg_loss = float(np.mean(losses[:period]))
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss < 1e-10:
        return 100.0
    return float(100.0 - 100.0 / (1.0 + avg_gain / avg_loss))


def _compute_rsi_series(closes: np.ndarray, period: int = RSI_PERIOD) -> np.ndarray:
    """Wilder RSI for the full series. Returns array of same length (NaN for early bars)."""
    n = len(closes)
    rsi = np.full(n, np.nan)
    if n < period + 2:
        return rsi
    deltas = np.diff(closes.astype(float))
    gains = np.maximum(deltas, 0.0)
    losses = np.abs(np.minimum(deltas, 0.0))
    avg_gain = float(np.mean(gains[:period]))
    avg_loss = float(np.mean(losses[:period]))
    if avg_loss < 1e-10:
        rsi[period] = 100.0
    else:
        rsi[period] = 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss < 1e-10:
            rsi[i + 1] = 100.0
        else:
            rsi[i + 1] = 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)
    return rsi


# ── Slope helper ───────────────────────────────────────────────────────────────

def _norm_slope(series: np.ndarray) -> float:
    if len(series) < 2:
        return 0.0
    idx = np.arange(len(series), dtype=float)
    raw_slope, _ = np.polyfit(idx, series.astype(float), 1)
    last_val = float(series[-1])
    return raw_slope / last_val if abs(last_val) > 1e-10 else 0.0


# ── Weekly trend ───────────────────────────────────────────────────────────────

def _weekly_trend(daily_df: pd.DataFrame) -> Tuple[str, float]:
    """Returns (trend_label, weekly_strength_proxy).

    trend_label: "positive" | "neutral" | "negative"
    weekly_strength_proxy: approximation comparable to DECISIONS #11 criterion.
    """
    weekly = daily_df.resample("W-FRI").agg({"close": "last"}).dropna()
    close_w = weekly["close"].astype(float).values

    if len(close_w) < 12:
        return "neutral", 0.0

    ma50w = np.mean(close_w[-50:]) if len(close_w) >= 50 else None
    last = float(close_w[-1])

    # Weekly strength proxy: count of up-weeks in last 12 weeks
    recent = close_w[-13:]
    up_weeks = sum(1 for i in range(1, len(recent)) if recent[i] > recent[i - 1])
    weekly_strength = up_weeks / (len(recent) - 1) * 20  # scale to ~0-20

    # MA50 weekly slope
    ma50_slope = 0.0
    if ma50w is not None and len(close_w) >= 55:
        ma50_series = np.array([np.mean(close_w[i - 50:i]) for i in range(50, len(close_w) + 1)])
        if len(ma50_series) >= WEEKLY_MA50_SLOPE_LOOKBACK:
            ma50_slope = _norm_slope(ma50_series[-WEEKLY_MA50_SLOPE_LOOKBACK:])

    # Clearly negative: below MA50w AND slope negative
    below_ma50 = (ma50w is not None and last < ma50w)
    clearly_negative = below_ma50 and ma50_slope < -0.001

    if clearly_negative and weekly_strength < WEEKLY_STRENGTH_NEUTRAL_MIN:
        return "negative", weekly_strength

    if weekly_strength >= WEEKLY_STRENGTH_NEUTRAL_MIN or (ma50w is not None and last > ma50w):
        return "positive", weekly_strength

    return "neutral", weekly_strength


# ── Supports ───────────────────────────────────────────────────────────────────

def _find_nearest_support(
    close: np.ndarray,
) -> Optional[Tuple[float, str, float]]:
    """Find the nearest support below (or very close to) current price.

    Returns (support_level, support_type, distance_pct) or None if none within 5%.
    distance_pct > 0 means price is above support.
    """
    n = len(close)
    last = float(close[-1])

    candidates: List[Tuple[float, str]] = []

    if n >= 50:
        ma50 = float(np.mean(close[-50:]))
        candidates.append((ma50, "MA50"))
    if n >= 200:
        ma200 = float(np.mean(close[-200:]))
        candidates.append((ma200, "MA200"))

    # Swing low: lowest close in the last SWING_LOW_LOOKBACK bars (excluding last bar)
    lookback = min(SWING_LOW_LOOKBACK, n - 1)
    if lookback > 0:
        swing_low = float(np.min(close[-(lookback + 1):-1]))
        candidates.append((swing_low, "swing_low"))

    # Filter: support must be below or equal to last price, within 5%
    valid = [
        (level, stype)
        for level, stype in candidates
        if level < last and (last - level) / last <= SUPPORT_PROXIMITY_MAX
    ]

    if not valid:
        return None

    # Pick the closest (largest level that is still below price)
    best_level, best_type = max(valid, key=lambda x: x[0])
    distance_pct = (last - best_level) / last
    return best_level, best_type, distance_pct


# ── Catalysts ─────────────────────────────────────────────────────────────────

def _detect_rsi_divergence(
    close: np.ndarray,
    rsi_series: np.ndarray,
) -> bool:
    """Bullish RSI divergence: price makes a lower low, RSI makes a higher low.

    Looks for two RSI troughs within the last DIVERGENCE_LOOKBACK bars.
    """
    n = len(close)
    if n < DIVERGENCE_LOOKBACK + 3:
        return False

    window_close = close[-DIVERGENCE_LOOKBACK:]
    window_rsi = rsi_series[-DIVERGENCE_LOOKBACK:]

    if np.any(np.isnan(window_rsi)):
        return False

    # Find RSI troughs: local minima (rsi[i] < rsi[i-1] and rsi[i] < rsi[i+1])
    troughs = [
        i for i in range(1, len(window_rsi) - 1)
        if window_rsi[i] < window_rsi[i - 1] and window_rsi[i] < window_rsi[i + 1]
    ]

    if len(troughs) < 2:
        return False

    # Compare the two most recent troughs
    t1, t2 = troughs[-2], troughs[-1]  # t1 is earlier, t2 is later
    price_lower_low = float(window_close[t2]) < float(window_close[t1])
    rsi_higher_low = float(window_rsi[t2]) > float(window_rsi[t1])

    return price_lower_low and rsi_higher_low


def _detect_reversal_candle(df: pd.DataFrame) -> bool:
    """Detect a bullish reversal candle on the last bar with above-avg volume.

    Checks:
    - Hammer: lower_shadow > 2 * body_size AND close > open
    - Bullish engulfing: close > prev_open AND open < prev_close
    Both require volume > 20-day average.
    """
    if len(df) < 21:
        return False

    o = df["open"].astype(float).values
    h = df["high"].astype(float).values
    l = df["low"].astype(float).values
    c = df["close"].astype(float).values
    v = df["volume"].astype(float).values

    avg_vol_20 = float(np.mean(v[-21:-1]))
    last_vol = float(v[-1])
    if last_vol <= avg_vol_20:
        return False

    last_o, last_h, last_l, last_c = o[-1], h[-1], l[-1], c[-1]
    body_size = abs(last_c - last_o)
    lower_shadow = min(last_o, last_c) - last_l

    # Hammer
    if body_size > 1e-10 and lower_shadow > 2 * body_size and last_c > last_o:
        return True

    # Bullish engulfing
    prev_o, prev_c = o[-2], c[-2]
    if last_c > prev_o and last_o < prev_c:
        return True

    return False


def _detect_ma200_bounce(close: np.ndarray) -> bool:
    """Price within 2% of MA200, or just crossed above it from below in last 3 bars."""
    n = len(close)
    if n < 200:
        return False
    ma200 = float(np.mean(close[-200:]))
    last = float(close[-1])

    # Within 2%
    if abs(last - ma200) / ma200 <= MA200_PROXIMITY:
        return True

    # Crossed above: was below MA200 in any of last 3 prior bars, now above
    if last > ma200:
        for i in range(2, min(4, n)):
            if float(close[-i]) < ma200:
                return True

    return False


# ── Volume ratio ──────────────────────────────────────────────────────────────

def _volume_ratio(volume: np.ndarray) -> Optional[float]:
    n = len(volume)
    if n < 20:
        return None
    avg_5 = float(np.mean(volume[-5:]))
    avg_20 = float(np.mean(volume[-20:]))
    if avg_20 < 1e-10:
        return None
    return avg_5 / avg_20


# ── Score ─────────────────────────────────────────────────────────────────────

def _compute_score(
    rsi: float,
    distance_to_support_pct: float,
    catalysts: List[str],
    vol_ratio: float,
) -> float:
    """Reversal score 0-100 per DECISIONS.md #11."""

    # RSI position (0-25)
    if rsi <= 30:
        rsi_pts = 25.0
    elif rsi <= 40:
        rsi_pts = 15.0
    else:
        rsi_pts = 8.0

    # Proximity to support (0-25)
    dist_pct = distance_to_support_pct * 100  # convert to percentage
    if dist_pct <= 1.0:
        prox_pts = 25.0
    elif dist_pct <= 3.0:
        prox_pts = 15.0
    elif dist_pct <= 5.0:
        prox_pts = 8.0
    else:
        prox_pts = 0.0

    # Catalyst quality (0-30, capped)
    cat_pts = 0.0
    for cat in catalysts:
        if "divergence" in cat.lower():
            cat_pts += 30.0
        elif "reversal candle" in cat.lower():
            cat_pts += 25.0
        elif "ma200" in cat.lower():
            cat_pts += 20.0
    cat_pts = min(cat_pts, 30.0)

    # Volume decreasing (0-20)
    if vol_ratio < 0.60:
        vol_pts = 20.0
    elif vol_ratio < 0.80:
        vol_pts = 10.0
    else:
        vol_pts = 0.0

    return min(rsi_pts + prox_pts + cat_pts + vol_pts, 100.0)


# ── Fundamentals gate ─────────────────────────────────────────────────────────

def _fundamentals_ok(bundle: TickerBundle) -> bool:
    """Return False if fundamentals are explicitly deteriorating; True otherwise."""
    if bundle.fundamentals is None:
        # Argentine stocks with no fundamentals: criterion omitted per DECISIONS #11
        if bundle.metadata.asset_type == AssetType.ARGENTINE_STOCK:
            return True
        # CEDEARs with missing fundamentals: treat as non-deteriorating (benefit of doubt)
        return True

    # Import here to avoid circular; FundamentalState is a string enum so compare by value
    state_val = None
    try:
        from analysis.filter2_deep_dive.fundamental_quality import score_fundamental_quality
        result = score_fundamental_quality(bundle)
        state_val = result.fundamental_state
    except Exception:
        return True  # if scoring fails, don't discard

    return state_val != FundamentalState.DETERIORATING


# ── Per-ticker evaluation ─────────────────────────────────────────────────────

def _evaluate_bundle(bundle: TickerBundle) -> Optional[ReversalOpportunity]:
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

    # ── Criterion 1: weekly trend not negative ─────────────────────────────────
    weekly_trend_label, _ = _weekly_trend(df)
    if weekly_trend_label == "negative":
        logger.debug("%s: skipped — weekly trend negative", symbol)
        return None

    # ── Criterion 2: RSI in 25-45 range ───────────────────────────────────────
    rsi = _compute_rsi(close)
    if rsi is None or not (RSI_LOW <= rsi <= RSI_HIGH):
        logger.debug("%s: skipped — RSI %.1f outside [%.0f, %.0f]", symbol, rsi or -1, RSI_LOW, RSI_HIGH)
        return None

    # ── Criterion 3: volume decreasing in the decline ─────────────────────────
    vol = df["volume"].values
    vol_ratio = _volume_ratio(vol)
    if vol_ratio is None or vol_ratio >= VOL_RATIO_THRESHOLD:
        logger.debug("%s: skipped — vol_ratio %.2f >= %.2f", symbol, vol_ratio or 999, VOL_RATIO_THRESHOLD)
        return None

    # ── Criterion 4: relevant support within 5% ───────────────────────────────
    support_result = _find_nearest_support(close)
    if support_result is None:
        logger.debug("%s: skipped — no support within 5%%", symbol)
        return None
    nearest_support, support_type, distance_pct = support_result

    # ── Criterion 5: at least one catalyst ────────────────────────────────────
    rsi_series = _compute_rsi_series(close)
    catalysts: List[str] = []

    if _detect_rsi_divergence(close, rsi_series):
        catalysts.append("RSI bullish divergence")

    if "volume" in df.columns and _detect_reversal_candle(df):
        catalysts.append("Reversal candle in support with volume")

    if _detect_ma200_bounce(close):
        catalysts.append("MA200 bounce/proximity")

    if not catalysts:
        logger.debug("%s: skipped — no catalyst detected", symbol)
        return None

    # ── Criterion 6: fundamentals not deteriorating ───────────────────────────
    if not _fundamentals_ok(bundle):
        logger.debug("%s: skipped — fundamentals deteriorating", symbol)
        return None

    # ── Score ─────────────────────────────────────────────────────────────────
    score = _compute_score(rsi, distance_pct, catalysts, vol_ratio)

    # ── Invalidation: support minus 1.5% buffer ───────────────────────────────
    invalidation = nearest_support * (1.0 - INVALIDATION_BUFFER)
    rationale = (
        f"{support_type} at {nearest_support:.2f} ARS"
        f" — stop {INVALIDATION_BUFFER:.1%} below ({invalidation:.2f} ARS)"
    )

    return ReversalOpportunity(
        symbol=symbol,
        name=name,
        asset_type=asset_type,
        score=round(score, 1),
        rsi_14=round(rsi, 1),
        nearest_support=round(nearest_support, 2),
        nearest_support_type=support_type,
        distance_to_support_pct=round(distance_pct, 4),
        catalyst=catalysts,
        volume_ratio=round(vol_ratio, 3),
        weekly_trend=weekly_trend_label,
        invalidation_level_ars=round(invalidation, 2),
        invalidation_rationale=rationale,
    )


# ── Main entry point ──────────────────────────────────────────────────────────

def scan_reversals(bundles: List[TickerBundle]) -> List[ReversalOpportunity]:
    """Scan all bundles for tactical reversal opportunities.

    Runs independently of Filter 1 and Filter 2 — evaluates the full universe
    with its own entry criteria. Returns opportunities sorted by score descending,
    capped at 5 (top-5 by score if more than 5 are detected).
    """
    opportunities: List[ReversalOpportunity] = []

    for bundle in bundles:
        try:
            opp = _evaluate_bundle(bundle)
            if opp is not None:
                opportunities.append(opp)
        except Exception as exc:
            logger.error("Error evaluating %s: %s", bundle.metadata.symbol_ars, exc)

    opportunities.sort(key=lambda x: x.score, reverse=True)

    if len(opportunities) > 5:
        logger.info(
            "scan_reversals: %d signals found, capping at top 5 by score",
            len(opportunities),
        )
        opportunities = opportunities[:5]

    return opportunities
