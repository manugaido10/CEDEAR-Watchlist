"""Tests for the ex-dividend gate (Decision #41) — offline, no scoring/threshold involved."""

from __future__ import annotations

from datetime import date

import pytest

from analysis.reversal.instrumentation import PriceInstrumentation
from analysis.reversal.reversal_scanner import ReversalOpportunity, _apply_ex_dividend_gate
from analysis.reversal.suppression import check_ex_dividend_gate
from data.dividends import (
    SOURCE_YFINANCE,
    SOURCE_YFINANCE_ESTIMATE,
    ExDividendResult,
)

DATA_DATE = date(2026, 11, 24)       # Tuesday; next session = Wed 2026-11-25
STOP = 0.0309


def _ex(ex_date=date(2026, 11, 25), yld=0.0368, stale=False, source=SOURCE_YFINANCE_ESTIMATE):
    return ExDividendResult(
        ex_div_date_raw=date(2026, 11, 24), ex_div_date=ex_date, ex_div_amount=0.193,
        ex_div_yield_pct=yld, ex_div_source=source, ex_div_stale=stale,
    )


class TestGate:
    def test_blocks_imminent_with_estimated_amount_and_labels_it(self):
        reason = check_ex_dividend_gate(_ex(), STOP, DATA_DATE)
        assert reason is not None
        assert reason.startswith("no operable: ex-dividendo 2026-11-25")
        assert "monto estimado" in reason
        assert "3.7%" in reason and "3.1%" in reason

    def test_confirmed_amount_is_not_labelled_estimated(self):
        reason = check_ex_dividend_gate(_ex(source=SOURCE_YFINANCE), STOP, DATA_DATE)
        assert reason is not None and "monto estimado" not in reason

    def test_boundary_yield_equal_to_stop_blocks(self):
        assert check_ex_dividend_gate(_ex(yld=STOP), STOP, DATA_DATE) is not None

    def test_yield_below_stop_distance_does_not_block(self):
        assert check_ex_dividend_gate(_ex(yld=0.02), STOP, DATA_DATE) is None

    def test_stale_true_does_not_block(self):
        assert check_ex_dividend_gate(_ex(stale=True), STOP, DATA_DATE) is None

    def test_stale_none_does_not_veto(self):
        assert check_ex_dividend_gate(_ex(stale=None), STOP, DATA_DATE) is not None

    @pytest.mark.parametrize("ex_date", [date(2026, 11, 24), date(2026, 11, 26), date(2026, 12, 1)])
    def test_only_the_next_session_blocks(self, ex_date):
        assert check_ex_dividend_gate(_ex(ex_date=ex_date), STOP, DATA_DATE) is None

    def test_next_session_after_friday_data_date_is_monday(self):
        friday = date(2026, 11, 27)
        assert check_ex_dividend_gate(_ex(ex_date=date(2026, 11, 30)), STOP, friday) is not None
        assert check_ex_dividend_gate(_ex(ex_date=date(2026, 11, 28)), STOP, friday) is None  # Saturday

    @pytest.mark.parametrize("ex,stop,dd", [
        (ExDividendResult(), STOP, DATA_DATE),                 # no data at all
        (_ex(yld=None), STOP, DATA_DATE),                      # no yield
        (_ex(), None, DATA_DATE),                              # no stop distance
        (_ex(), STOP, None),                                   # no data_date
    ])
    def test_fail_open_on_missing_inputs(self, ex, stop, dd):
        assert check_ex_dividend_gate(ex, stop, dd) is None


def _opp(**kw):
    base = dict(
        symbol="UGP.BA", name="Ultrapar", asset_type="cedear", score=60.0, rsi_14=38.2,
        entry_price_ars=9404.82, nearest_support=9252.74, nearest_support_type="MA200",
        distance_to_support_pct=0.0162, catalyst=["MA200 bounce/proximity"],
        volume_ratio=0.69, weekly_trend="positive", invalidation_level_ars=9113.95,
        invalidation_rationale="MA200 stop", ex_dividend=_ex(),
        instrumentation=PriceInstrumentation(stop_dist_pct=STOP),
    )
    base.update(kw)
    return ReversalOpportunity(**base)


class TestScannerApplication:
    def test_blocks_tradeable_opportunity(self):
        opp = _opp()
        _apply_ex_dividend_gate(opp, DATA_DATE)
        assert opp.tradeable is False
        assert opp.suppression_reason.startswith("no operable: ex-dividendo")

    def test_score_and_levels_are_untouched(self):
        opp = _opp()
        _apply_ex_dividend_gate(opp, DATA_DATE)
        assert (opp.score, opp.invalidation_level_ars, opp.rsi_14) == (60.0, 9113.95, 38.2)

    def test_earlier_suppression_reason_is_never_overwritten(self):
        opp = _opp(tradeable=False, suppression_reason="Bloqueado: promediar a la baja")
        _apply_ex_dividend_gate(opp, DATA_DATE)
        assert opp.suppression_reason == "Bloqueado: promediar a la baja"

    def test_no_stop_distance_leaves_it_tradeable(self):
        opp = _opp(instrumentation=PriceInstrumentation())
        _apply_ex_dividend_gate(opp, DATA_DATE)
        assert opp.tradeable is True and opp.suppression_reason is None

    def test_default_opportunity_is_never_gated(self):
        opp = _opp(ex_dividend=ExDividendResult())
        _apply_ex_dividend_gate(opp, DATA_DATE)
        assert opp.tradeable is True


class TestRecordingAndReport:
    def test_blocked_signal_is_recorded_without_opening_a_paper_position(self, tmp_path, monkeypatch):
        import analysis.reversal.signal_registry as sr
        import data.positions_log as pl
        monkeypatch.setattr(sr, "SIGNALS_PATH", tmp_path / "signals.jsonl")
        opened = []
        monkeypatch.setattr(pl, "open_position", lambda *a, **k: opened.append(a))
        opp = _opp()
        _apply_ex_dividend_gate(opp, DATA_DATE)
        sr.record_signals([opp], "2026-11-25", data_date="2026-11-24")
        rec = sr.load_signals()[0]
        assert opened == []
        assert rec["tradeable"] is False
        assert rec["suppression_reason"].startswith("no operable: ex-dividendo")
        assert rec["ex_div_date"] == "2026-11-25" and rec["ex_div_date_raw"] == "2026-11-24"

    def test_report_shows_no_operar_with_reason_and_estimate_label(self):
        from output.reversal_report import _build_markdown
        opp = _opp()
        _apply_ex_dividend_gate(opp, DATA_DATE)
        md = _build_markdown([opp], "2026-11-25")
        assert "🚫 NO OPERAR: UGP.BA" in md
        assert "no operable: ex-dividendo 2026-11-25" in md
        assert "monto estimado" in md
