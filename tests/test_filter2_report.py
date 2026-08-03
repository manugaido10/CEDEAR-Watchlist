"""Tests for filter2_models.py Filter2Report new field + run_filter2 arithmetic identity."""
from __future__ import annotations

from typing import Optional, Tuple
from unittest.mock import MagicMock, patch

import pytest

from analysis.filter2_deep_dive.filter2_models import (
    ArgentinaAdjustment,
    BreakoutDetail,
    Filter2Opportunity,
    Filter2Report,
    FundamentalResult,
    FundamentalState,
    LightCheckResult,
    RSIState,
    SentimentResult,
    SentimentVerdict,
    TechnicalResult,
    TickerFilter2Status,
    TrendBreakdown,
    TrendLabel,
)
from analysis.filter2_deep_dive.filter2_thresholds import MAX_POSITIONS, MIN_SCORE
from analysis.filter1_quick_sweep import FilterCategory, TickerFilterResult


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_opp(symbol: str, score: float, status: TickerFilter2Status = TickerFilter2Status.RANKED) -> Filter2Opportunity:
    tech = TechnicalResult(
        technical_score=score,
        trend_regime=20.0,
        breakout_bonus=0.0,
        relative_strength_score=0.0,
        rsi_penalty=0.0,
        trend_breakdown=TrendBreakdown(weekly_strength=10.0, daily_strength=10.0, ma_alignment=5.0),
        breakout_detail=BreakoutDetail(triggered=False),
        rs_value=1.0,
        benchmark_used="SPY",
        rsi_value=50.0,
        rsi_state=RSIState.OK,
        trend_regime_label=TrendLabel.MILD_UP,
    )
    fund = FundamentalResult(
        fundamental_state=FundamentalState.NEUTRAL,
        fundamental_penalty=0.0,
    )
    sentiment = SentimentResult(
        light_check=LightCheckResult.CLEAN,
        sentiment_gate=(
            SentimentVerdict.DISCARD
            if status == TickerFilter2Status.DISCARDED_BY_SENTIMENT
            else SentimentVerdict.NONE
        ),
    )
    return Filter2Opportunity(
        symbol=symbol,
        asset_type="cedear",
        name=symbol,
        technical_score=score,
        technical_breakdown=tech,
        technical_signal_summary="ok",
        fundamental_state=fund.fundamental_state.value,
        fundamental_penalty=fund.fundamental_penalty,
        fundamental_summary="ok",
        sentiment_gate=sentiment.sentiment_gate.value,
        sentiment_evidence=[],
        sentiment_summary="",
        argentina_penalty=0.0,
        argentina_breakdown={},
        final_score=score,
        rank=0,
        status=status.value,
        invalidation_level_ars=0.0,
        invalidation_level_usd=0.0,
        invalidation_rationale="",
        proposed_capital_usd=0.0,
        proposed_capital_pct=0.0,
        capital_rationale="",
    )


# ── Filter2Report field tests ─────────────────────────────────────────────────


def test_filter2_report_has_new_field():
    """Filter2Report can be constructed with passed_min_score_not_ranked."""
    opp_a = _make_opp("AAA", 80.0)
    opp_b = _make_opp("BBB", 60.0)
    report = Filter2Report(
        opportunities=[opp_a],
        discarded_by_sentiment=[],
        passed_min_score_not_ranked=[opp_b],
        unevaluable_symbols=[],
        total_survivors_input=2,
        total_ranked=1,
        total_discarded_by_sentiment=0,
        total_unevaluable=0,
        run_date="2026-08-03",
    )
    assert len(report.passed_min_score_not_ranked) == 1
    assert report.passed_min_score_not_ranked[0].symbol == "BBB"


def test_passed_not_ranked_preserves_scores():
    """Opportunities in passed_min_score_not_ranked retain their computed scores."""
    opp = _make_opp("XYZ", 72.5)
    report = Filter2Report(
        opportunities=[],
        discarded_by_sentiment=[],
        passed_min_score_not_ranked=[opp],
        unevaluable_symbols=[],
        total_survivors_input=1,
        total_ranked=0,
        total_discarded_by_sentiment=0,
        total_unevaluable=0,
        run_date="2026-08-03",
    )
    assert report.passed_min_score_not_ranked[0].final_score == 72.5
    assert report.passed_min_score_not_ranked[0].rank == 0
    assert report.passed_min_score_not_ranked[0].proposed_capital_usd == 0.0
    assert report.passed_min_score_not_ranked[0].capital_rationale == ""


# ── run_filter2 arithmetic identity ──────────────────────────────────────────


def _make_f1_result(symbol: str) -> TickerFilterResult:
    return TickerFilterResult(
        symbol=symbol,
        asset_type="cedear",
        category=FilterCategory.SURVIVOR,
    )


def _make_evaluate_one_side_effect(score_map: dict, discard_set: set, unevaluable_set: set):
    """Return a side_effect function for patching _evaluate_one."""
    def _side_effect(f1_result, bundle, cache) -> Tuple[Optional[Filter2Opportunity], str]:
        sym = f1_result.symbol
        if sym in unevaluable_set:
            return None, f"{sym}: prices_ars missing"
        if sym in discard_set:
            opp = _make_opp(sym, 0.0, TickerFilter2Status.DISCARDED_BY_SENTIMENT)
            return opp, ""
        score = score_map.get(sym, 40.0)
        opp = _make_opp(sym, score)
        return opp, ""
    return _side_effect


def test_run_filter2_arithmetic_identity():
    """Verify: unevaluable + discarded_sentiment + below_min + not_ranked + ranked == input."""
    from analysis.filter2_deep_dive.filter2_runner import run_filter2

    # Design: 30 survivors total
    # - 2 unevaluable (prices missing)
    # - 3 discarded by sentiment
    # - 5 below MIN_SCORE  (score = MIN_SCORE - 5)
    # - 20 above MIN_SCORE (score = MIN_SCORE + varied amount to spread across ranks)
    #   → top MAX_POSITIONS ranked; 20 - MAX_POSITIONS = not_ranked

    total_input = 30
    n_unevaluable = 2
    n_discard = 3
    n_below = 5
    n_above = total_input - n_unevaluable - n_discard - n_below  # = 20
    n_not_ranked = n_above - MAX_POSITIONS  # = 20 - 10 = 10

    symbols = [f"SYM{i:03d}" for i in range(total_input)]
    unevaluable_set = set(symbols[:n_unevaluable])
    discard_set = set(symbols[n_unevaluable: n_unevaluable + n_discard])
    below_symbols = symbols[n_unevaluable + n_discard: n_unevaluable + n_discard + n_below]
    above_symbols = symbols[n_unevaluable + n_discard + n_below:]

    score_map = {}
    for sym in below_symbols:
        score_map[sym] = MIN_SCORE - 5.0
    for i, sym in enumerate(above_symbols):
        score_map[sym] = MIN_SCORE + 10.0 + i  # ensure distinct, all ≥ MIN_SCORE

    survivors = [_make_f1_result(s) for s in symbols]

    # Mock bundle_map: every symbol gets a dummy bundle stub
    mock_bundle = MagicMock()
    mock_bundle.metadata.symbol_ars = "dummy"

    fake_bundle_map = {s: MagicMock() for s in symbols}
    for s in symbols:
        fake_bundle_map[s].metadata.symbol_ars = s

    with patch(
        "analysis.filter2_deep_dive.filter2_runner._evaluate_one",
        side_effect=_make_evaluate_one_side_effect(score_map, discard_set, unevaluable_set),
    ), patch(
        "analysis.filter2_deep_dive.filter2_runner._build_bundle_map",
        return_value=fake_bundle_map,
    ), patch(
        "analysis.filter2_deep_dive.filter2_runner._allocate_capital",
        side_effect=lambda opps, total: [(o, 1000.0) for o in opps],
    ), patch(
        "analysis.filter2_deep_dive.filter2_runner._compute_invalidation",
        return_value=(0.0, 0.0, "mocked"),
    ):
        report = run_filter2(survivors, bundles=[], cache=MagicMock())

    ranked = len(report.opportunities)
    discarded = len(report.discarded_by_sentiment)
    not_ranked = len(report.passed_min_score_not_ranked)
    unevaluable = len(report.unevaluable_symbols)
    # below_min is implicit: total - ranked - discarded - not_ranked - unevaluable
    implicit_below = total_input - ranked - discarded - not_ranked - unevaluable

    assert unevaluable == n_unevaluable, f"expected {n_unevaluable} unevaluable, got {unevaluable}"
    assert discarded == n_discard, f"expected {n_discard} discarded, got {discarded}"
    assert not_ranked == n_not_ranked, f"expected {n_not_ranked} not_ranked, got {not_ranked}"
    assert ranked == MAX_POSITIONS, f"expected {MAX_POSITIONS} ranked, got {ranked}"
    assert implicit_below == n_below, (
        f"arithmetic mismatch: {total_input} input ≠ "
        f"{ranked}+{discarded}+{not_ranked}+{unevaluable}+{implicit_below}"
    )
    # Golden identity
    assert ranked + discarded + not_ranked + unevaluable + implicit_below == total_input


def test_watchlist_report_ignores_new_field():
    """watchlist_report.generate_report() must not reference passed_min_score_not_ranked."""
    import inspect
    from output import watchlist_report
    src = inspect.getsource(watchlist_report)
    assert "passed_min_score_not_ranked" not in src, (
        "watchlist_report.py references the new field — audit output may change"
    )
