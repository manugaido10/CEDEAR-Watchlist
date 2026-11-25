"""Tests for data/dividends.py (Fase B3) — offline: no yfinance call is made."""

from __future__ import annotations

import json
from datetime import date, datetime
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from data.dividends import (
    SOURCE_YFINANCE,
    SOURCE_YFINANCE_ESTIMATE,
    ExDividendResult,
    RawExDividend,
    build_ex_dividend_result,
    check_ex_dividend,
)

TODAY = date(2026, 11, 25)


class TestBuild:
    def test_no_calendar_date_is_all_none(self):
        res = build_ex_dividend_result(RawExDividend(), TODAY)
        assert res.to_record() == {
            "ex_div_date": None, "ex_div_amount": None, "ex_div_yield_pct": None,
            "ex_div_source": None, "ex_div_stale": None,
        }

    def test_upcoming_with_confirmed_amount(self):
        raw = RawExDividend(
            calendar_ex_date=date(2026, 11, 25),
            dividends={date(2026, 11, 25): 0.1796},
            last_close=5.25,
            last_dividend_value=0.193,
        )
        res = build_ex_dividend_result(raw, TODAY)
        assert res.ex_div_date == date(2026, 11, 25)
        assert res.ex_div_amount == 0.1796
        assert res.ex_div_yield_pct == round(0.1796 / 5.25, 4)
        assert res.ex_div_source == SOURCE_YFINANCE
        assert res.ex_div_stale is False  # ex-date today is not stale

    def test_amount_match_tolerates_one_day_offset(self):
        raw = RawExDividend(
            calendar_ex_date=date(2026, 11, 24),
            dividends={date(2026, 11, 25): 0.18},
            last_close=5.0,
        )
        res = build_ex_dividend_result(raw, date(2026, 11, 24))
        assert res.ex_div_amount == 0.18
        assert res.ex_div_source == SOURCE_YFINANCE

    def test_no_matching_entry_falls_back_to_labelled_estimate(self):
        raw = RawExDividend(
            calendar_ex_date=date(2026, 11, 26),
            dividends={date(2026, 8, 26): 0.193},  # months away: must not match
            last_close=5.25,
            last_dividend_value=0.193,
        )
        res = build_ex_dividend_result(raw, TODAY)
        assert res.ex_div_amount == 0.193
        assert res.ex_div_source == SOURCE_YFINANCE_ESTIMATE

    def test_no_amount_anywhere_keeps_date_only(self):
        raw = RawExDividend(calendar_ex_date=date(2026, 11, 26), last_close=5.25)
        res = build_ex_dividend_result(raw, TODAY)
        assert res.ex_div_date == date(2026, 11, 26)
        assert res.ex_div_amount is None and res.ex_div_yield_pct is None
        assert res.ex_div_stale is False

    def test_missing_close_gives_no_yield(self):
        raw = RawExDividend(calendar_ex_date=date(2026, 11, 26), last_dividend_value=0.2)
        res = build_ex_dividend_result(raw, TODAY)
        assert res.ex_div_amount == 0.2
        assert res.ex_div_yield_pct is None

    def test_past_date_is_stale_without_amount_or_yield(self):
        raw = RawExDividend(
            calendar_ex_date=date(2026, 11, 20),
            dividends={date(2026, 11, 20): 0.2}, last_close=5.0, last_dividend_value=0.2,
        )
        res = build_ex_dividend_result(raw, TODAY)
        assert res.ex_div_date == date(2026, 11, 20)
        assert res.ex_div_stale is True
        assert res.ex_div_amount is None and res.ex_div_yield_pct is None

    @pytest.mark.parametrize("bad", [0, -0.1, float("nan"), None, "x"])
    def test_non_positive_or_non_finite_amount_is_ignored(self, bad):
        raw = RawExDividend(
            calendar_ex_date=date(2026, 11, 26), last_close=5.0, last_dividend_value=bad,
        )
        res = build_ex_dividend_result(raw, TODAY)
        assert res.ex_div_amount is None and res.ex_div_yield_pct is None

    def test_timestamp_calendar_date_is_normalised(self):
        raw = RawExDividend(calendar_ex_date=pd.Timestamp("2026-11-26"))
        assert build_ex_dividend_result(raw, TODAY).ex_div_date == date(2026, 11, 26)
        raw = RawExDividend(calendar_ex_date=datetime(2026, 11, 26, 0, 0))
        assert build_ex_dividend_result(raw, TODAY).ex_div_date == date(2026, 11, 26)

    def test_record_is_json_serialisable(self):
        raw = RawExDividend(
            calendar_ex_date=date(2026, 11, 26), last_close=5.0, last_dividend_value=0.2,
        )
        json.dumps(build_ex_dividend_result(raw, TODAY).to_record(), allow_nan=False)


class TestCheck:
    def test_uses_injected_fetcher(self):
        raw = RawExDividend(calendar_ex_date=date(2026, 11, 26), last_close=5.0,
                            last_dividend_value=0.25)
        res = check_ex_dividend("UGP", today=TODAY, fetcher=lambda s: raw)
        assert res.ex_div_yield_pct == 0.05

    def test_fetcher_exception_returns_empty(self):
        def boom(_s):
            raise RuntimeError("network down")
        assert check_ex_dividend("UGP", today=TODAY, fetcher=boom) == ExDividendResult()

    def test_timeout_returns_empty(self):
        import data.dividends as dv
        with patch.object(dv, "EX_DIV_FETCH_TIMEOUT_SEC", 0.05):
            import time
            res = check_ex_dividend("UGP", today=TODAY, fetcher=lambda s: time.sleep(0.5))
        assert res == ExDividendResult()

    def test_excluded_underlying_skips_fetch(self):
        fetcher = MagicMock()
        with patch("data.dividends._is_excluded_underlying", return_value=True):
            res = check_ex_dividend("ROKU", today=TODAY, fetcher=fetcher)
        assert res == ExDividendResult()
        fetcher.assert_not_called()


class TestFetchRawOffline:
    """_fetch_raw with a fake yf.Ticker — proves parsing without network."""

    def _ticker(self, calendar, hist, info):
        t = MagicMock()
        t.calendar = calendar
        t.history.return_value = hist
        t.info = info
        return t

    def test_parses_calendar_history_and_info(self):
        import data.dividends as dv
        idx = pd.to_datetime(["2026-11-23", "2026-11-24"]).tz_localize("America/New_York")
        hist = pd.DataFrame({"Close": [5.26, 5.25], "Dividends": [0.0, 0.0]}, index=idx)
        t = self._ticker({"Ex-Dividend Date": date(2026, 11, 24)}, hist,
                         {"lastDividendValue": 0.193})
        with patch.object(dv.yf, "Ticker", return_value=t):
            raw = dv._fetch_raw("UGP")
        assert raw.calendar_ex_date == date(2026, 11, 24)
        assert raw.last_close == 5.25
        assert raw.dividends == {}
        assert raw.last_dividend_value == 0.193

    def test_no_ex_date_skips_history_and_info(self):
        import data.dividends as dv
        t = self._ticker({}, None, {})
        with patch.object(dv.yf, "Ticker", return_value=t):
            raw = dv._fetch_raw("XYZ")
        assert raw.calendar_ex_date is None
        t.history.assert_not_called()

    def test_non_dict_calendar_is_tolerated(self):
        import data.dividends as dv
        t = self._ticker(None, None, {})
        with patch.object(dv.yf, "Ticker", return_value=t):
            assert dv._fetch_raw("XYZ").calendar_ex_date is None


# ── Registry: keys always present ─────────────────────────────────────────────

_EX_KEYS = {"ex_div_date", "ex_div_amount", "ex_div_yield_pct", "ex_div_source", "ex_div_stale"}


class TestRegistryRecord:
    def _opp(self, **extra):
        from tests.test_reversal_tracking import _Opp
        opp = _Opp(
            symbol="UGP.BA", score=60.0, rsi_14=38.2, entry_price_ars=9404.82,
            invalidation_level_ars=9113.95, nearest_support=9252.74,
            nearest_support_type="MA200", catalyst=["MA200 bounce/proximity"],
            weekly_trend="positive",
        )
        for k, v in extra.items():
            setattr(opp, k, v)
        return opp

    def _registry(self, tmp_path, monkeypatch):
        import analysis.reversal.signal_registry as sr
        monkeypatch.setattr(sr, "SIGNALS_PATH", tmp_path / "signals.jsonl")
        # No paper position in these tests.
        monkeypatch.setattr("data.positions_log.open_position", lambda *a, **k: None, raising=False)
        return sr

    def test_keys_present_and_null_without_data(self, tmp_path, monkeypatch):
        sr = self._registry(tmp_path, monkeypatch)
        sr.record_signals([self._opp(tradeable=False)], "2026-11-25")
        rec = sr.load_signals()[0]
        assert _EX_KEYS <= set(rec)
        assert all(rec[k] is None for k in _EX_KEYS)

    def test_values_written_without_any_exclusion_decision(self, tmp_path, monkeypatch):
        sr = self._registry(tmp_path, monkeypatch)
        ex = ExDividendResult(
            ex_div_date=date(2026, 11, 25), ex_div_amount=0.1796, ex_div_yield_pct=0.0343,
            ex_div_source=SOURCE_YFINANCE, ex_div_stale=False,
        )
        sr.record_signals([self._opp(ex_dividend=ex, tradeable=False)], "2026-11-25")
        rec = sr.load_signals()[0]
        assert rec["ex_div_date"] == "2026-11-25"
        assert rec["ex_div_amount"] == 0.1796
        assert rec["ex_div_yield_pct"] == 0.0343
        assert rec["ex_div_source"] == "yfinance"
        assert rec["ex_div_stale"] is False
        assert "ex_div_in_window" not in rec and "corpus_excluded" not in rec


# ── Scanner propagation ───────────────────────────────────────────────────────

def test_evaluate_bundle_propagates_ex_dividend(monkeypatch):
    import numpy as np
    from analysis.reversal.instrumentation import PriceInstrumentation
    from analysis.reversal.reversal_scanner import _BundleMetrics, _evaluate_bundle
    from data.earnings import EarningsCheckResult, EarningsCheckStatus

    n = 250
    df = pd.DataFrame({"open": [100.0] * n, "high": [101.0] * n, "low": [99.0] * n,
                       "close": [100.0] * n, "volume": [1e6] * n})
    metrics = _BundleMetrics(
        symbol="CCC.BA", name="C", asset_type="cedear", close=df["close"].values, df=df,
        entry_price_ars=100.0, weekly_trend="neutral", weekly_strength=11.0, rsi=35.0,
        rsi_series=np.full(n, 35.0), vol_ratio=0.5, support_result=(99.0, "MA50", 0.01),
        catalysts=["RSI bullish divergence"], fundamentals_ok=True, adv_ars=1e9,
        instrumentation=PriceInstrumentation(),
    )
    ex = ExDividendResult(ex_div_date=date(2026, 11, 26), ex_div_source=SOURCE_YFINANCE,
                          ex_div_stale=False)
    seen = {}
    monkeypatch.setattr(
        "analysis.reversal.reversal_scanner.check_ex_dividend",
        lambda sym, *a, **k: seen.setdefault("sym", sym) and ex,
    )
    bundle = MagicMock()
    bundle.metadata.symbol_underlying = "CCC"
    with patch("analysis.reversal.reversal_scanner._compute_metrics", return_value=metrics), \
         patch("analysis.reversal.reversal_scanner.check_earnings_warning",
               return_value=EarningsCheckResult(EarningsCheckStatus.VERIFIED_CLEAR)):
        opp = _evaluate_bundle(bundle)
    assert seen["sym"] == "CCC"  # the underlying, not the .BA symbol
    assert opp.ex_dividend is ex


def test_evaluate_bundle_argentine_stock_has_empty_ex_dividend(monkeypatch):
    """No symbol_underlying → check_ex_dividend is not called; fields stay None."""
    import numpy as np
    from analysis.reversal.instrumentation import PriceInstrumentation
    from analysis.reversal.reversal_scanner import _BundleMetrics, _evaluate_bundle

    n = 250
    df = pd.DataFrame({"open": [100.0] * n, "high": [101.0] * n, "low": [99.0] * n,
                       "close": [100.0] * n, "volume": [1e6] * n})
    metrics = _BundleMetrics(
        symbol="TECO2.BA", name="T", asset_type="stock", close=df["close"].values, df=df,
        entry_price_ars=100.0, weekly_trend="neutral", weekly_strength=11.0, rsi=35.0,
        rsi_series=np.full(n, 35.0), vol_ratio=0.5, support_result=(99.0, "MA50", 0.01),
        catalysts=["RSI bullish divergence"], fundamentals_ok=True, adv_ars=1e9,
        instrumentation=PriceInstrumentation(),
    )
    called = MagicMock()
    monkeypatch.setattr("analysis.reversal.reversal_scanner.check_ex_dividend", called)
    bundle = MagicMock()
    bundle.metadata.symbol_underlying = None
    with patch("analysis.reversal.reversal_scanner._compute_metrics", return_value=metrics):
        opp = _evaluate_bundle(bundle)
    called.assert_not_called()
    assert opp.ex_dividend == ExDividendResult()


# ── query.py: is_div_contaminated ─────────────────────────────────────────────

@pytest.mark.parametrize("yld,stop,stale,expected", [
    (0.0343, 0.0309, False, True),    # UGP 2026-11-25: drop alone trips the stop
    (0.0309, 0.0309, False, True),    # boundary is inclusive (>=)
    (0.0200, 0.0309, False, False),   # dividend smaller than the stop distance
    (None,   0.0309, False, False),   # no yield → no evidence
    (0.0343, None,   False, False),   # no stop distance → no evidence
    (0.0343, 0.0309, True,  False),   # ex-date already past
    (0.0343, 0.0309, None,  True),    # stale unknown → does not veto
])
def test_is_div_contaminated_macro(yld, stop, stale, expected):
    from analysis.query import get_connection
    conn = get_connection()
    got = conn.execute(
        "SELECT is_div_contaminated(?::DOUBLE, ?::DOUBLE, ?::BOOLEAN)", [yld, stop, stale]
    ).fetchone()[0]
    assert got is expected
