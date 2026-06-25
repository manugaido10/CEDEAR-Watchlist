"""Filter 2 — Técnica 1: Technical scoring.

Produces technical_score ∈ [0, 100] and TechnicalResult for a survivor.

Sub-components (DISENO_FILTRO_2.md §2.1):
  trend_regime      (0-50): weekly structure + daily structure + MA alignment
  breakout_bonus    (0-15): binary breakout confirmed by volume
  relative_strength (-15 to +15): performance vs. SPY (CEDEARs) or ^MERV (argentinas)
  momentum_rsi      (-15 to 0): penalizes overbought without context; penalizes oversold

technical_score = clip(trend_regime + breakout_bonus + relative_strength + rsi_penalty, 0, 100)

Design decisions:
  - Weekly bearish cap: if weekly trend is clearly bearish, trend_regime is capped at 15
    regardless of daily or MA alignment score (multi-timeframe alignment is mandatory).
  - RSI context: no penalty if breakout active OR price near 52-week high with MA50 positive.
  - Benchmark (SPY / ^MERV) downloaded once per cycle via existing Cache; same price
    mechanism as ticker prices (data/prices.py fetch_prices handles non-.BA tickers).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple

import numpy as np
import pandas as pd

from data.cache import Cache
from data.models import AssetType, TickerBundle
from data.prices import fetch_prices

from .filter2_models import (
    BreakoutDetail,
    RSIState,
    TechnicalResult,
    TrendBreakdown,
    TrendLabel,
)
from .filter2_thresholds import (
    BREAKOUT_LOOKBACK_N,
    BREAKOUT_RECENT_K,
    BREAKOUT_SCORE,
    BREAKOUT_VOLUME_MULTIPLIER,
    DAILY_ABOVE_MA200_PTS,
    DAILY_ABOVE_MA20_PTS,
    DAILY_ABOVE_MA50_PTS,
    DAILY_HH_HL_LOOKBACK,
    DAILY_HH_HL_MAX_PTS,
    DAILY_MA50_SLOPE_LOOKBACK,
    DAILY_MA50_SLOPE_POS_PTS,
    MA_GOLDEN_CROSS_BONUS_PTS,
    MA_GOLDEN_CROSS_LOOKBACK,
    MA_PARTIAL_ALIGNMENT_PTS,
    MA_PERFECT_ALIGNMENT_PTS,
    MA_WEAK_ALIGNMENT_PTS,
    RS_HIGH_CONTEXT_PCT,
    RS_HIGH_THRESHOLD,
    RS_LOW_THRESHOLD,
    RS_MAX_SCORE,
    RS_MIN_SCORE,
    RS_WINDOW_DAYS,
    RSI_OVERBOUGHT_MILD,
    RSI_OVERBOUGHT_MILD_PENALTY,
    RSI_OVERBOUGHT_STRONG,
    RSI_OVERBOUGHT_STRONG_PENALTY,
    RSI_OVERBOUGHT_STRONG_VERTICAL_PENALTY,
    RSI_OVERSOLD_PENALTY,
    RSI_OVERSOLD_THRESHOLD,
    RSI_PERIOD,
    RSI_VERTICAL_MA_MULT,
    TECHNICAL_MIN_BARS,
    TREND_LABEL_MILD_DOWN_MIN,
    TREND_LABEL_MILD_UP_MIN,
    TREND_LABEL_SIDEWAYS_MIN,
    TREND_LABEL_STRONG_UP_MIN,
    WEEKLY_ABOVE_MA20_PTS,
    WEEKLY_ABOVE_MA50_PTS,
    WEEKLY_BEARISH_CAP,
    WEEKLY_HH_HL_MAX_PTS,
    WEEKLY_LOOKBACK_BARS,
    WEEKLY_MA20_SLOPE_BEARISH_THRESHOLD,
    WEEKLY_MA20_SLOPE_LOOKBACK,
    WEEKLY_MA20_SLOPE_POS_PTS,
)

logger = logging.getLogger(__name__)

_BENCHMARK_SPY = "SPY"
_BENCHMARK_MERV = "^MERV"
_BENCHMARK_LOOKBACK_DAYS = 200  # covers RS_WINDOW_DAYS with comfortable margin


# ── Benchmark cache (module-level, one download per process/cycle) ─────────────

_benchmark_cache: dict[str, Optional[pd.DataFrame]] = {}


def _get_benchmark(symbol: str, cache: Optional[Cache]) -> Optional[pd.DataFrame]:
    """Download benchmark prices once and memoize for the cycle."""
    if symbol in _benchmark_cache:
        return _benchmark_cache[symbol]

    df: Optional[pd.DataFrame] = None
    if cache is not None:
        df = cache.load_prices(symbol)
        if df is not None and not df.empty:
            last_bar = pd.Timestamp(df.index[-1]).date()
            from datetime import date
            if last_bar >= (date.today() - timedelta(days=3)):
                _benchmark_cache[symbol] = df
                return df

    df = fetch_prices(symbol, lookback_days=_BENCHMARK_LOOKBACK_DAYS)
    if df is not None and cache is not None:
        cache.save_prices(symbol, df)

    _benchmark_cache[symbol] = df
    return df


def clear_benchmark_cache() -> None:
    """Call at the start of each weekly cycle to force fresh benchmark downloads."""
    _benchmark_cache.clear()


# ── RSI ────────────────────────────────────────────────────────────────────────

def _compute_rsi(closes: np.ndarray, period: int = RSI_PERIOD) -> Optional[float]:
    """Wilder-smoothed RSI. Returns None if insufficient data."""
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
    rs = avg_gain / avg_loss
    return float(100.0 - 100.0 / (1.0 + rs))


# ── Slope helper ───────────────────────────────────────────────────────────────

def _norm_slope(series: np.ndarray) -> float:
    """Normalized linear slope: raw_slope / last_value. Zero if last_value ≈ 0."""
    if len(series) < 2:
        return 0.0
    idx = np.arange(len(series), dtype=float)
    raw_slope, _ = np.polyfit(idx, series, 1)
    last_val = float(series[-1])
    return raw_slope / last_val if abs(last_val) > 1e-10 else 0.0


# ── Weekly resampling ──────────────────────────────────────────────────────────

def _resample_weekly(daily_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate daily OHLCV to weekly bars (week ending Friday)."""
    agg = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }
    available = {k: v for k, v in agg.items() if k in daily_df.columns}
    weekly = daily_df.resample("W-FRI").agg(available).dropna(subset=["close"])
    return weekly


# ── Weekly strength (0-20) ─────────────────────────────────────────────────────

def _score_weekly_strength(
    weekly: pd.DataFrame,
) -> Tuple[float, bool]:
    """Returns (weekly_strength_score, weekly_is_clearly_bearish)."""
    close_w = weekly["close"].astype(float).ffill()
    if len(close_w) < 22:  # need enough bars for MA20w
        return 0.0, False

    ma20w = close_w.rolling(20).mean()
    ma50w = close_w.rolling(50).mean() if len(close_w) >= 52 else None

    last_close = float(close_w.iloc[-1])
    last_ma20 = float(ma20w.dropna().iloc[-1]) if ma20w.dropna().shape[0] > 0 else None
    last_ma50 = float(ma50w.dropna().iloc[-1]) if (ma50w is not None and ma50w.dropna().shape[0] > 0) else None

    score = 0.0

    if last_ma50 is not None and last_close > last_ma50:
        score += WEEKLY_ABOVE_MA50_PTS
    if last_ma20 is not None and last_close > last_ma20:
        score += WEEKLY_ABOVE_MA20_PTS

    # MA20w slope
    ma20w_valid = ma20w.dropna().values
    slope_lookback = min(WEEKLY_MA20_SLOPE_LOOKBACK, len(ma20w_valid))
    ma20w_slope = 0.0
    if slope_lookback >= 2:
        ma20w_slope = _norm_slope(ma20w_valid[-slope_lookback:])
        if ma20w_slope > 0:
            score += WEEKLY_MA20_SLOPE_POS_PTS

    # HH/HL score: proportion of recent weeks with higher-close than prior week
    lookback = min(WEEKLY_LOOKBACK_BARS, len(close_w) - 1)
    if lookback >= 4:
        recent = close_w.iloc[-lookback - 1:].values
        hh_count = sum(1 for i in range(1, len(recent)) if recent[i] > recent[i - 1])
        prop = hh_count / (len(recent) - 1)
        score += WEEKLY_HH_HL_MAX_PTS * prop

    # Clearly bearish: close below both MAs AND MA20w slope negative
    clearly_bearish = (
        last_ma20 is not None
        and last_close < last_ma20
        and (last_ma50 is None or last_close < last_ma50)
        and ma20w_slope < WEEKLY_MA20_SLOPE_BEARISH_THRESHOLD
    )

    return min(score, 20.0), clearly_bearish


# ── Daily strength (0-20) ──────────────────────────────────────────────────────

def _score_daily_strength(close: np.ndarray) -> Tuple[float, float, float]:
    """Returns (daily_strength_score, ma50d_last, ma20d_last)."""
    n = len(close)
    score = 0.0

    ma20 = float(np.mean(close[-20:])) if n >= 20 else None
    ma50 = float(np.mean(close[-50:])) if n >= 50 else None
    ma200 = float(np.mean(close[-200:])) if n >= 200 else None
    last = float(close[-1])

    if ma200 is not None and last > ma200:
        score += DAILY_ABOVE_MA200_PTS
    if ma50 is not None and last > ma50:
        score += DAILY_ABOVE_MA50_PTS
    if ma20 is not None and last > ma20:
        score += DAILY_ABOVE_MA20_PTS

    # MA50d slope
    if n >= 50 + DAILY_MA50_SLOPE_LOOKBACK:
        ma50_series = np.convolve(close, np.ones(50) / 50, mode="valid")
        slope_lookback = min(DAILY_MA50_SLOPE_LOOKBACK, len(ma50_series))
        if slope_lookback >= 2:
            if _norm_slope(ma50_series[-slope_lookback:]) > 0:
                score += DAILY_MA50_SLOPE_POS_PTS

    # HH/HL daily: proportion of recent days with higher close
    lookback = min(DAILY_HH_HL_LOOKBACK, n - 1)
    if lookback >= 4:
        recent = close[-lookback - 1:]
        hh_count = sum(1 for i in range(1, len(recent)) if recent[i] > recent[i - 1])
        prop = hh_count / (len(recent) - 1)
        score += DAILY_HH_HL_MAX_PTS * prop

    return min(score, 20.0), ma50 or 0.0, ma20 or 0.0


# ── MA alignment (0-10) ───────────────────────────────────────────────────────

def _score_ma_alignment(close: np.ndarray) -> float:
    n = len(close)
    ma20 = float(np.mean(close[-20:])) if n >= 20 else None
    ma50 = float(np.mean(close[-50:])) if n >= 50 else None
    ma200 = float(np.mean(close[-200:])) if n >= 200 else None

    score = 0.0
    if ma20 is not None and ma50 is not None and ma200 is not None:
        if ma20 > ma50 > ma200:
            score = MA_PERFECT_ALIGNMENT_PTS
            # Golden cross: MA50 crossed above MA200 within last N bars
            lookback = min(MA_GOLDEN_CROSS_LOOKBACK, n - 50)
            if lookback > 0:
                ma50_series = np.convolve(close, np.ones(50) / 50, mode="valid")
                ma200_series = np.convolve(close, np.ones(200) / 200, mode="valid")
                min_len = min(len(ma50_series), len(ma200_series))
                if min_len > lookback:
                    ma50_tail = ma50_series[-lookback:]
                    ma200_tail = ma200_series[-lookback:]
                    diffs = ma50_tail - ma200_tail
                    # Cross: any sign change from negative to positive
                    for i in range(1, len(diffs)):
                        if diffs[i - 1] < 0 and diffs[i] > 0:
                            score += MA_GOLDEN_CROSS_BONUS_PTS
                            break
        elif ma20 is not None and ma50 is not None and ma20 > ma50:
            score = MA_PARTIAL_ALIGNMENT_PTS
        elif ma50 is not None and ma200 is not None and ma50 > ma200:
            score = MA_WEAK_ALIGNMENT_PTS
    elif ma20 is not None and ma50 is not None:
        if ma20 > ma50:
            score = MA_PARTIAL_ALIGNMENT_PTS

    return min(score, 10.0)


# ── Breakout bonus (0-15) ─────────────────────────────────────────────────────

def _score_breakout(df: pd.DataFrame) -> BreakoutDetail:
    """Check for a recent volume-confirmed breakout over N-bar highs."""
    n = len(df)
    if n < BREAKOUT_LOOKBACK_N + BREAKOUT_RECENT_K + 1:
        return BreakoutDetail(triggered=False)

    close = df["close"].astype(float).ffill().values
    volume = df["volume"].astype(float).ffill().values

    # Prior range: bars from -(LOOKBACK_N + RECENT_K) to -RECENT_K (exclusive)
    prior_slice = close[-(BREAKOUT_LOOKBACK_N + BREAKOUT_RECENT_K):-BREAKOUT_RECENT_K]
    prior_max = float(np.max(prior_slice))

    # Median volume of the prior range (for the volume multiplier check)
    vol_prior = volume[-(BREAKOUT_LOOKBACK_N + BREAKOUT_RECENT_K):-BREAKOUT_RECENT_K]
    median_vol = float(np.median(vol_prior)) if len(vol_prior) > 0 else 0.0

    # Look for a breakout bar in the last RECENT_K bars
    recent_close = close[-BREAKOUT_RECENT_K:]
    recent_vol = volume[-BREAKOUT_RECENT_K:]
    recent_dates = df.index[-BREAKOUT_RECENT_K:]

    for i in range(len(recent_close)):
        if recent_close[i] > prior_max:
            vol_ratio = (recent_vol[i] / median_vol) if median_vol > 1e-10 else 0.0
            if vol_ratio >= BREAKOUT_VOLUME_MULTIPLIER:
                bar_date = str(recent_dates[i].date())
                return BreakoutDetail(
                    triggered=True,
                    bar_date=bar_date,
                    volume_ratio=round(vol_ratio, 2),
                )

    return BreakoutDetail(triggered=False)


# ── Relative strength (-15 to +15) ────────────────────────────────────────────

def _score_relative_strength(
    close: np.ndarray,
    dates: pd.DatetimeIndex,
    benchmark_df: Optional[pd.DataFrame],
    benchmark_symbol: str,
) -> Tuple[float, float]:
    """Returns (rs_score, rs_value). rs_value = ratio of returns over RS_WINDOW_DAYS."""
    if benchmark_df is None or benchmark_df.empty:
        return 0.0, 1.0

    bench_close = benchmark_df["close"].astype(float).ffill()
    ticker_series = pd.Series(close, index=dates).ffill()

    # Align on common dates
    common = ticker_series.index.intersection(bench_close.index)
    if len(common) < RS_WINDOW_DAYS + 5:
        return 0.0, 1.0

    t = ticker_series.loc[common]
    b = bench_close.loc[common]

    window = min(RS_WINDOW_DAYS, len(common) - 1)
    t_return = float(t.iloc[-1]) / float(t.iloc[-window - 1])
    b_return = float(b.iloc[-1]) / float(b.iloc[-window - 1])

    if abs(b_return) < 1e-10:
        return 0.0, 1.0

    rs_value = t_return / b_return

    # Linear map: RS ∈ [0.85, 1.15] → score ∈ [-15, +15]
    score = (rs_value - 1.0) / (RS_HIGH_THRESHOLD - 1.0) * RS_MAX_SCORE
    score = float(np.clip(score, RS_MIN_SCORE, RS_MAX_SCORE))

    return score, rs_value


# ── RSI penalty (-15 to 0) ────────────────────────────────────────────────────

def _score_rsi(
    close: np.ndarray,
    breakout_triggered: bool,
    ma50d: float,
    ma20d: float,
) -> Tuple[float, float, RSIState]:
    """Returns (rsi_penalty, rsi_value, rsi_state)."""
    rsi = _compute_rsi(close)
    if rsi is None:
        return 0.0, float("nan"), RSIState.OK

    # Context: near 52-week high + MA50 slope positive
    high_52w = float(np.max(close[-252:])) if len(close) >= 252 else float(np.max(close))
    near_high = float(close[-1]) >= high_52w * (1 - RS_HIGH_CONTEXT_PCT)
    ma50_positive = ma50d > 0 and float(close[-1]) > ma50d  # crude proxy for positive slope

    has_context = breakout_triggered or (near_high and ma50_positive)

    if rsi < RSI_OVERSOLD_THRESHOLD:
        return RSI_OVERSOLD_PENALTY, rsi, RSIState.OVERSOLD

    if rsi >= RSI_OVERBOUGHT_STRONG:
        if has_context:
            return 0.0, rsi, RSIState.OVERBOUGHT_WITH_CONTEXT
        # Extra penalty when price is also stretched above MA20d (vertical move)
        vertical = ma20d > 0 and float(close[-1]) > ma20d * RSI_VERTICAL_MA_MULT
        penalty = RSI_OVERBOUGHT_STRONG_VERTICAL_PENALTY if vertical else RSI_OVERBOUGHT_STRONG_PENALTY
        return penalty, rsi, RSIState.OVERBOUGHT_NO_CONTEXT

    if rsi >= RSI_OVERBOUGHT_MILD:
        if has_context:
            return 0.0, rsi, RSIState.OVERBOUGHT_WITH_CONTEXT
        return RSI_OVERBOUGHT_MILD_PENALTY, rsi, RSIState.OVERBOUGHT_NO_CONTEXT

    return 0.0, rsi, RSIState.OK


# ── Trend label ────────────────────────────────────────────────────────────────

def _assign_trend_label(trend_regime: float) -> TrendLabel:
    if trend_regime >= TREND_LABEL_STRONG_UP_MIN:
        return TrendLabel.STRONG_UP
    if trend_regime >= TREND_LABEL_MILD_UP_MIN:
        return TrendLabel.MILD_UP
    if trend_regime >= TREND_LABEL_SIDEWAYS_MIN:
        return TrendLabel.SIDEWAYS
    if trend_regime >= TREND_LABEL_MILD_DOWN_MIN:
        return TrendLabel.MILD_DOWN
    return TrendLabel.STRONG_DOWN


# ── Signal summary ─────────────────────────────────────────────────────────────

def _build_signal_summary(
    trend_regime: float,
    trend_label: TrendLabel,
    breakout_detail: BreakoutDetail,
    rs_score: float,
    rs_value: float,
    benchmark: str,
    rsi_value: float,
    rsi_state: RSIState,
    weekly_cap_applied: bool,
) -> str:
    parts = []
    parts.append(f"Trend {trend_label.value} (regime={trend_regime:.0f}/50)")
    if weekly_cap_applied:
        parts.append("weekly cap applied")
    if breakout_detail.triggered:
        vol_str = f"{breakout_detail.volume_ratio:.1f}x" if breakout_detail.volume_ratio else "?"
        parts.append(f"breakout {breakout_detail.bar_date} vol {vol_str}")
    rs_pct = (rs_value - 1.0) * 100
    parts.append(f"RS vs {benchmark} {rs_pct:+.1f}% (score {rs_score:+.0f})")
    if not (rsi_state == RSIState.OK):
        parts.append(f"RSI {rsi_value:.0f} ({rsi_state.value})")
    return "; ".join(parts) + "."


# ── Main entry point ───────────────────────────────────────────────────────────

def compute_technical_score(
    bundle: TickerBundle,
    cache: Optional[Cache] = None,
) -> TechnicalResult:
    """Compute technical score for a Filter 1 survivor.

    Fail-safe: if prices_ars is missing or too short, returns a zero-score
    TechnicalResult with warnings explaining why.
    """
    warnings: list[str] = []
    symbol = bundle.metadata.symbol_ars

    if bundle.prices_ars is None or bundle.prices_ars.data.empty:
        warnings.append("prices_ars missing — zero technical score")
        return _zero_result(warnings)

    df = bundle.prices_ars.data.copy()
    df.columns = [c.lower() for c in df.columns]
    df = df.sort_index()

    # Forward-fill gaps (yfinance returns NaN for some CEDEAR bars)
    for col in ["open", "high", "low", "close", "volume"]:
        if col in df.columns:
            df[col] = df[col].astype(float).ffill()

    close = df["close"].values
    n = len(close)

    if n < TECHNICAL_MIN_BARS:
        warnings.append(f"only {n} bars (need {TECHNICAL_MIN_BARS}); reduced score reliability")

    # Weekly resampling
    weekly = _resample_weekly(df)
    weekly_strength, weekly_bearish = _score_weekly_strength(weekly)

    # Daily strength
    daily_strength, ma50d, ma20d = _score_daily_strength(close)

    # MA alignment
    ma_alignment = _score_ma_alignment(close)

    # trend_regime (with possible weekly bearish cap)
    trend_regime_raw = weekly_strength + daily_strength + ma_alignment
    weekly_cap_applied = False
    if weekly_bearish and trend_regime_raw > WEEKLY_BEARISH_CAP:
        trend_regime_raw = WEEKLY_BEARISH_CAP
        weekly_cap_applied = True

    trend_regime = min(trend_regime_raw, 50.0)

    # Breakout bonus
    breakout_detail = _score_breakout(df)
    breakout_bonus = BREAKOUT_SCORE if breakout_detail.triggered else 0.0

    # Benchmark download
    if bundle.metadata.asset_type == AssetType.ARGENTINE_STOCK:
        benchmark_symbol = _BENCHMARK_MERV
    else:
        benchmark_symbol = _BENCHMARK_SPY

    benchmark_df = _get_benchmark(benchmark_symbol, cache)
    if benchmark_df is None:
        warnings.append(f"benchmark {benchmark_symbol} unavailable; RS set to 0")

    rs_score, rs_value = _score_relative_strength(
        close, df.index, benchmark_df, benchmark_symbol
    )

    # RSI penalty
    rsi_penalty, rsi_value, rsi_state = _score_rsi(
        close,
        breakout_triggered=breakout_detail.triggered,
        ma50d=ma50d,
        ma20d=ma20d,
    )

    # Final score
    raw_score = trend_regime + breakout_bonus + rs_score + rsi_penalty
    technical_score = float(np.clip(raw_score, 0.0, 100.0))

    trend_label = _assign_trend_label(trend_regime)

    trend_breakdown = TrendBreakdown(
        weekly_strength=round(weekly_strength, 2),
        daily_strength=round(daily_strength, 2),
        ma_alignment=round(ma_alignment, 2),
        weekly_cap_applied=weekly_cap_applied,
    )

    summary = _build_signal_summary(
        trend_regime, trend_label, breakout_detail,
        rs_score, rs_value, benchmark_symbol,
        rsi_value, rsi_state, weekly_cap_applied,
    )

    return TechnicalResult(
        technical_score=round(technical_score, 2),
        trend_regime=round(trend_regime, 2),
        breakout_bonus=breakout_bonus,
        relative_strength_score=round(rs_score, 2),
        rsi_penalty=round(rsi_penalty, 2),
        trend_breakdown=trend_breakdown,
        breakout_detail=breakout_detail,
        rs_value=round(rs_value, 4),
        benchmark_used=benchmark_symbol,
        rsi_value=round(rsi_value, 1) if not np.isnan(rsi_value) else float("nan"),
        rsi_state=rsi_state,
        trend_regime_label=trend_label,
        signal_summary=summary,
        warnings=warnings,
    )


def _zero_result(warnings: list[str]) -> TechnicalResult:
    return TechnicalResult(
        technical_score=0.0,
        trend_regime=0.0,
        breakout_bonus=0.0,
        relative_strength_score=0.0,
        rsi_penalty=0.0,
        trend_breakdown=TrendBreakdown(0.0, 0.0, 0.0),
        breakout_detail=BreakoutDetail(triggered=False),
        rs_value=1.0,
        benchmark_used="",
        rsi_value=float("nan"),
        rsi_state=RSIState.OK,
        trend_regime_label=TrendLabel.STRONG_DOWN,
        signal_summary="Unevaluable — insufficient price data.",
        warnings=warnings,
    )
