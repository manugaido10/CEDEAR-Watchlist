"""Filter 2 — runner (orchestrator).

Receives Filter 1 survivors (TickerFilterResult list) + their TickerBundles.
Runs all four technique modules in the order defined in DISENO_FILTRO_2.md §8:
  1. technical_score
  2. fundamental_state + fundamental_penalty
  3. light check (news, always)
  4. tiebreaker activation + (if needed) full tiebreaker
  5. argentina_penalty
  6. final_score = max(0, technical - fund_pen - arg_pen)
  7. discard by sentiment gate if verdict == discard

Post-processing (§6.2, §6.3):
  - Filter by MIN_SCORE
  - Top 10 by final_score
  - Invalidation level per ticker (swing low vs. MA buffer)
  - Capital allocation with score-flattened weights + floor-based position removal

Output: Filter2Report with all opportunity details.
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from data.cache import Cache
from data.models import TickerBundle

from analysis.filter1_quick_sweep import TickerFilterResult

from .argentina_adjustment import compute_argentina_adjustment
from .filter2_models import (
    ArgentinaAdjustment,
    Filter2Opportunity,
    Filter2Report,
    FundamentalResult,
    SentimentResult,
    SentimentVerdict,
    TechnicalResult,
    TickerFilter2Status,
)
from .filter2_thresholds import (
    ARGENTINA_MAX_PENALTY,
    CASH_RESERVE_SCHEDULE,
    INVALIDATION_MA_BUFFER,
    MAX_POSITIONS,
    MIN_POSITION_USD,
    MIN_SCORE,
    SCORE_FLATTENING_ALPHA,
    SWING_LOW_LOOKBACK_BARS,
    SWING_LOW_WINDOW_N,
    TOTAL_CAPITAL_USD,
)
from .fundamental_quality import compute_fundamental_quality
from .news_gate import run_news_gate
from .technical_scoring import compute_technical_score

logger = logging.getLogger(__name__)


# ── Invalidation level ─────────────────────────────────────────────────────────

def _find_swing_low(close: np.ndarray, lookback: int, window_n: int) -> Optional[float]:
    """Find the most recent swing low within lookback bars.

    A swing low at index i = all window_n bars before and after have higher close.
    Returns the most recent (rightmost) qualifying bar's close, or None.
    """
    n = len(close)
    start = max(0, n - lookback)
    # Search from right (most recent) so the first hit is the most recent swing low
    for i in range(n - window_n - 1, start + window_n - 1, -1):
        candidate = close[i]
        left_ok = all(close[j] > candidate for j in range(i - window_n, i))
        right_ok = all(close[j] > candidate for j in range(i + 1, i + window_n + 1))
        if left_ok and right_ok:
            return float(candidate)
    return None


def _compute_invalidation(
    bundle: TickerBundle,
    tech_result: TechnicalResult,
) -> Tuple[float, float, str]:
    """Returns (invalidation_ars, invalidation_usd, rationale).

    Logic (DISENO_FILTRO_2.md §6.2):
      1. Most recent swing low in last SWING_LOW_LOOKBACK_BARS bars.
      2. Relevant MA × (1 - INVALIDATION_MA_BUFFER).
         MA50 for uptrend labels; MA200 for sideways/down.
      3. Invalidation = max(swing_low, ma_level) — the one closest to current price.
    """
    from .filter2_models import TrendLabel

    if bundle.prices_ars is None or bundle.prices_ars.data.empty:
        return 0.0, 0.0, "prices unavailable"

    close = bundle.prices_ars.data["close"].astype(float).ffill().values
    n = len(close)
    ccl_spot = bundle.ccl_series.spot if bundle.ccl_series else 0.0

    # Relevant MA
    uptrend = tech_result.trend_regime_label in (TrendLabel.STRONG_UP, TrendLabel.MILD_UP)
    if uptrend and n >= 50:
        ma_relevant = float(np.mean(close[-50:]))
        ma_name = "MA50"
    elif n >= 200:
        ma_relevant = float(np.mean(close[-200:]))
        ma_name = "MA200"
    elif n >= 50:
        ma_relevant = float(np.mean(close[-50:]))
        ma_name = "MA50"
    else:
        ma_relevant = None
        ma_name = ""

    ma_level = (ma_relevant * (1.0 - INVALIDATION_MA_BUFFER)) if ma_relevant else None

    # Swing low
    swing_low = _find_swing_low(close, SWING_LOW_LOOKBACK_BARS, SWING_LOW_WINDOW_N)

    if swing_low is not None and ma_level is not None:
        # Take the higher of the two (closest to current price)
        invalidation_ars = max(swing_low, ma_level)
        if invalidation_ars == swing_low:
            rationale = (
                f"Swing low {swing_low:.2f} ARS "
                f"(closer than {ma_name} buffer {ma_level:.2f})."
            )
        else:
            rationale = (
                f"{ma_name} {ma_relevant:.2f} ARS × (1-{INVALIDATION_MA_BUFFER:.0%}) "
                f"= {ma_level:.2f} (closer than swing low {swing_low:.2f})."
            )
    elif swing_low is not None:
        invalidation_ars = swing_low
        rationale = f"Swing low {swing_low:.2f} ARS (no MA level computable)."
    elif ma_level is not None:
        invalidation_ars = ma_level
        rationale = (
            f"{ma_name} {ma_relevant:.2f} ARS × (1-{INVALIDATION_MA_BUFFER:.0%}) "
            f"= {ma_level:.2f} (no swing low found in last {SWING_LOW_LOOKBACK_BARS} bars)."
        )
    else:
        # Fallback: 10% below current close
        invalidation_ars = float(close[-1]) * 0.90
        rationale = "Fallback 10% below current close (insufficient data for MA/swing low)."

    invalidation_usd = (invalidation_ars / ccl_spot) if ccl_spot > 0 else 0.0
    return round(invalidation_ars, 2), round(invalidation_usd, 4), rationale


# ── Capital allocation ─────────────────────────────────────────────────────────

def _cash_reserve_pct(n: int) -> float:
    for max_n in sorted(CASH_RESERVE_SCHEDULE.keys()):
        if n <= max_n:
            return CASH_RESERVE_SCHEDULE[max_n]
    return CASH_RESERVE_SCHEDULE[max(CASH_RESERVE_SCHEDULE.keys())]


def _allocate_capital(
    opportunities: List[Filter2Opportunity],
    total_capital: float,
) -> List[Tuple[Filter2Opportunity, float]]:
    """Allocate investable capital with score-flattened weights and floor removal.

    Iteratively removes positions below MIN_POSITION_USD and redistributes.
    (DISENO_FILTRO_2.md §6.3, option a)
    """
    tickers = list(opportunities)
    n = len(tickers)
    if n == 0:
        return []

    reserve_pct = _cash_reserve_pct(n)
    investable = total_capital * (1.0 - reserve_pct)

    while tickers:
        weights_raw = [o.final_score ** SCORE_FLATTENING_ALPHA for o in tickers]
        total_w = sum(weights_raw)
        if total_w < 1e-10:
            break
        capitals = [investable * w / total_w for w in weights_raw]

        below = [i for i, c in enumerate(capitals) if c < MIN_POSITION_USD]
        if not below:
            return list(zip(tickers, capitals))

        # Remove the ticker with the smallest allocation
        worst = min(below, key=lambda i: capitals[i])
        logger.debug(
            "Removing %s from ranking (allocation $%.0f < floor $%.0f)",
            tickers[worst].symbol,
            capitals[worst],
            MIN_POSITION_USD,
        )
        tickers.pop(worst)

    return []


# ── Signal summary helpers ─────────────────────────────────────────────────────

def _capital_rationale(opp: Filter2Opportunity, all_scores: List[float]) -> str:
    avg = float(np.mean(all_scores)) if all_scores else 0.0
    return (
        f"Score {opp.final_score:.0f} vs. ranking avg {avg:.0f} → "
        f"{opp.proposed_capital_pct:.1f}% of investable (${opp.proposed_capital_usd:.0f})."
    )


# ── Bundle lookup ──────────────────────────────────────────────────────────────

def _build_bundle_map(bundles: List[TickerBundle]) -> Dict[str, TickerBundle]:
    return {b.metadata.symbol_ars: b for b in bundles}


# ── Per-ticker evaluation ──────────────────────────────────────────────────────

def _evaluate_one(
    f1_result: TickerFilterResult,
    bundle: TickerBundle,
    cache: Cache,
) -> Tuple[Optional[Filter2Opportunity], str]:
    """Evaluate all four techniques for one survivor.

    Returns (Filter2Opportunity | None, unevaluable_reason).
    None + non-empty reason → unevaluable.
    """
    symbol = bundle.metadata.symbol_ars
    warnings: list[str] = []

    # Guard: prices required for technical scoring
    if bundle.prices_ars is None or bundle.prices_ars.data.empty:
        return None, f"{symbol}: prices_ars missing"

    # ── Step 1: Technical score ──
    try:
        tech: TechnicalResult = compute_technical_score(bundle, cache)
        warnings.extend(tech.warnings)
    except Exception as exc:
        logger.error("%s: technical scoring failed: %s", symbol, exc)
        return None, f"{symbol}: technical scoring exception: {exc}"

    # ── Step 2: Fundamental quality ──
    try:
        fund: FundamentalResult = compute_fundamental_quality(bundle)
    except Exception as exc:
        logger.error("%s: fundamental quality failed: %s", symbol, exc)
        return None, f"{symbol}: fundamental quality exception: {exc}"

    # ── Steps 3+4: News gate (light check + conditional tiebreaker) ──
    try:
        sentiment: SentimentResult = run_news_gate(bundle, tech, fund, cache)
        warnings.extend(sentiment.warnings)
    except Exception as exc:
        logger.error("%s: news gate failed: %s", symbol, exc)
        # Fail-open: treat as inconclusive, do not discard
        from .filter2_models import LightCheckResult
        sentiment = SentimentResult(
            light_check=LightCheckResult.CLEAN,
            sentiment_gate=SentimentVerdict.INCONCLUSIVE,
            summary=f"News gate exception (fail-open): {exc}",
            warnings=[str(exc)],
        )

    # Discard?
    if sentiment.sentiment_gate == SentimentVerdict.DISCARD:
        opp = _build_opportunity(
            symbol, bundle, f1_result, tech, fund, sentiment,
            argentina=ArgentinaAdjustment(total_penalty=0.0),
            final_score=0.0,
            status=TickerFilter2Status.DISCARDED_BY_SENTIMENT,
            rank=0,
            invalidation_ars=0.0,
            invalidation_usd=0.0,
            invalidation_rationale="Discarded by sentiment gate.",
            proposed_capital_usd=0.0,
            proposed_capital_pct=0.0,
            capital_rationale="Discarded.",
            warnings=warnings,
        )
        return opp, ""

    # ── Step 5: Argentina adjustment ──
    try:
        argentina: ArgentinaAdjustment = compute_argentina_adjustment(bundle, cache)
        warnings.extend(argentina.warnings)
    except Exception as exc:
        logger.error("%s: argentina adjustment failed: %s", symbol, exc)
        argentina = ArgentinaAdjustment(
            total_penalty=0.0,
            warnings=[f"Argentina adjustment exception: {exc}"],
        )

    # ── Step 6: Final score ──
    final_score = max(
        0.0,
        tech.technical_score - fund.fundamental_penalty - argentina.total_penalty,
    )

    # Held-with-warning flag (not used for ranking but reported)
    status = TickerFilter2Status.RANKED
    if sentiment.sentiment_gate == SentimentVerdict.INCONCLUSIVE and sentiment.tiebreaker_activated:
        warnings.append("Tiebreaker inconclusive — held with warning.")
        status = TickerFilter2Status.HELD_WITH_WARNING
    if argentina.total_penalty >= ARGENTINA_MAX_PENALTY * 0.8:
        warnings.append(f"High Argentina penalty ({argentina.total_penalty:.0f}/{ARGENTINA_MAX_PENALTY:.0f}).")
        status = TickerFilter2Status.HELD_WITH_WARNING

    # Invalidation level (filled in post-processing after ranking)
    inv_ars, inv_usd, inv_rationale = _compute_invalidation(bundle, tech)

    opp = _build_opportunity(
        symbol, bundle, f1_result, tech, fund, sentiment, argentina,
        final_score=round(final_score, 2),
        status=status,
        rank=0,  # assigned after ranking
        invalidation_ars=inv_ars,
        invalidation_usd=inv_usd,
        invalidation_rationale=inv_rationale,
        proposed_capital_usd=0.0,      # filled post-ranking
        proposed_capital_pct=0.0,
        capital_rationale="",
        warnings=warnings,
    )
    return opp, ""


def _build_opportunity(
    symbol: str,
    bundle: TickerBundle,
    f1_result: TickerFilterResult,
    tech: TechnicalResult,
    fund: FundamentalResult,
    sentiment: SentimentResult,
    argentina: ArgentinaAdjustment,
    final_score: float,
    status: TickerFilter2Status,
    rank: int,
    invalidation_ars: float,
    invalidation_usd: float,
    invalidation_rationale: str,
    proposed_capital_usd: float,
    proposed_capital_pct: float,
    capital_rationale: str,
    warnings: list,
) -> Filter2Opportunity:
    return Filter2Opportunity(
        symbol=symbol,
        asset_type=bundle.metadata.asset_type.value,
        name=bundle.metadata.name,
        technical_score=tech.technical_score,
        technical_breakdown=tech,
        technical_signal_summary=tech.signal_summary,
        fundamental_state=fund.fundamental_state.value,
        fundamental_penalty=fund.fundamental_penalty,
        fundamental_summary=fund.summary,
        sentiment_gate=sentiment.sentiment_gate.value,
        sentiment_evidence=sentiment.evidence_urls,
        sentiment_summary=sentiment.summary,
        argentina_penalty=argentina.total_penalty,
        argentina_breakdown=argentina.breakdown,
        final_score=final_score,
        rank=rank,
        status=status.value,
        invalidation_level_ars=invalidation_ars,
        invalidation_level_usd=invalidation_usd,
        invalidation_rationale=invalidation_rationale,
        proposed_capital_usd=proposed_capital_usd,
        proposed_capital_pct=proposed_capital_pct,
        capital_rationale=capital_rationale,
        warnings=warnings,
    )


# ── Main entry point ───────────────────────────────────────────────────────────

def run_filter2(
    survivors: List[TickerFilterResult],
    bundles: List[TickerBundle],
    cache: Optional[Cache] = None,
    total_capital: float = TOTAL_CAPITAL_USD,
    flags_path: Optional[Path] = None,
) -> Filter2Report:
    """Run Filter 2 over all Filter 1 survivors.

    Args:
        survivors: filter1_report.survivors (list of TickerFilterResult).
        bundles: full bundle list from fetch_universe_bundle(); matched by symbol_ars.
        cache: Cache instance (created fresh if None).
        total_capital: total investable capital in USD.
        flags_path: override for argentina_risk_flags.yaml path (testing).

    Returns Filter2Report with ranked opportunities and all metadata.
    """
    if cache is None:
        cache = Cache()

    bundle_map = _build_bundle_map(bundles)
    logger.info("Starting Filter 2 over %d survivors", len(survivors))

    ranked_opps: List[Filter2Opportunity] = []
    discarded_sentiment: List[Filter2Opportunity] = []
    unevaluable_symbols: List[str] = []
    global_warnings: List[str] = []

    for f1_result in survivors:
        symbol = f1_result.symbol
        bundle = bundle_map.get(symbol)
        if bundle is None:
            logger.warning("%s: no bundle found in bundle_map; skipping", symbol)
            unevaluable_symbols.append(symbol)
            continue

        opp, unevaluable_reason = _evaluate_one(f1_result, bundle, cache)

        if unevaluable_reason:
            logger.warning("%s", unevaluable_reason)
            unevaluable_symbols.append(symbol)
            continue

        if opp is None:
            unevaluable_symbols.append(symbol)
            continue

        if opp.status == TickerFilter2Status.DISCARDED_BY_SENTIMENT.value:
            discarded_sentiment.append(opp)
            logger.info("%s: discarded by sentiment gate", symbol)
        else:
            ranked_opps.append(opp)

    # ── Post-processing ────────────────────────────────────────────────────────

    # Filter by MIN_SCORE
    passing = [o for o in ranked_opps if o.final_score >= MIN_SCORE]
    below_min = [o for o in ranked_opps if o.final_score < MIN_SCORE]
    if below_min:
        logger.info(
            "%d tickers below MIN_SCORE (%.0f): %s",
            len(below_min),
            MIN_SCORE,
            [o.symbol for o in below_min],
        )

    # Top 10 by final_score
    passing.sort(key=lambda o: o.final_score, reverse=True)
    top = passing[:MAX_POSITIONS]

    # Capital allocation
    allocated = _allocate_capital(top, total_capital)

    # Assign ranks and capital
    final_ranked: List[Filter2Opportunity] = []
    all_scores = [o.final_score for o, _ in allocated]

    for rank, (opp, cap_usd) in enumerate(allocated, start=1):
        opp.rank = rank
        opp.proposed_capital_usd = round(cap_usd, 2)
        reserve_pct = _cash_reserve_pct(len(allocated))
        investable = total_capital * (1.0 - reserve_pct)
        opp.proposed_capital_pct = round((cap_usd / investable) * 100, 1) if investable > 0 else 0.0
        opp.capital_rationale = _capital_rationale(opp, all_scores)
        final_ranked.append(opp)

    logger.info(
        "Filter 2 complete — ranked=%d discarded_by_sentiment=%d unevaluable=%d",
        len(final_ranked),
        len(discarded_sentiment),
        len(unevaluable_symbols),
    )

    return Filter2Report(
        opportunities=final_ranked,
        discarded_by_sentiment=discarded_sentiment,
        unevaluable_symbols=unevaluable_symbols,
        total_survivors_input=len(survivors),
        total_ranked=len(final_ranked),
        total_discarded_by_sentiment=len(discarded_sentiment),
        total_unevaluable=len(unevaluable_symbols),
        run_date=date.today().isoformat(),
        warnings=global_warnings,
    )
