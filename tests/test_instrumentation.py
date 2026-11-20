"""Fase B1 instrumentation: ATR, price/CCL fields, earnings days, record schema."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import List
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

import analysis.reversal.near_miss_tracker as nm
import analysis.reversal.outcome_tracker as ot
import analysis.reversal.regime_snapshot as rs
import analysis.reversal.signal_registry as sr
from analysis.reversal.fx_context import usd_implied_closes
from analysis.reversal.instrumentation import (
    PriceInstrumentation,
    compute_price_instrumentation,
)
from analysis.reversal.reversal_scanner import (
    ATR_PERIOD,
    _compute_atr,
    _compute_rsi,
    _weekly_trend,
    _weekly_trend_details,
)
from data.earnings import EarningsCheckStatus, check_earnings_warning
from data.models import AssetType, CCLSeries

_FIELDS = set(PriceInstrumentation().to_record())


@pytest.fixture
def tracking_paths(tmp_path, monkeypatch):
    """Isolate every tracking path (some legacy tests reassign them globally)."""
    monkeypatch.chdir(tmp_path)
    d = tmp_path / "data" / "reversal_tracking"
    monkeypatch.setattr(sr, "SIGNALS_PATH", d / "signals.jsonl")
    monkeypatch.setattr(nm, "NEAR_MISSES_PATH", d / "near_misses.jsonl")
    monkeypatch.setattr(ot, "OUTCOMES_PATH", d / "outcomes.jsonl")
    monkeypatch.setattr(rs, "REGIME_SNAPSHOTS_PATH", d / "regime_snapshots.jsonl")
    return d


def _ohlc(closes, spread=1.0, start="2024-01-01"):
    closes = np.asarray(closes, dtype=float)
    return pd.DataFrame(
        {"open": closes, "high": closes + spread, "low": closes - spread,
         "close": closes, "volume": np.full(len(closes), 1000.0)},
        index=pd.bdate_range(start, periods=len(closes)),
    )


def _ccl(values, index) -> CCLSeries:
    s = pd.Series(values, index=index, dtype=float)
    return CCLSeries(data=s, spot=float(s.iloc[-1]), as_of=s.index[-1].date())


# ── ATR ───────────────────────────────────────────────────────────────────────

class TestATR:
    def test_constant_range_equals_range(self):
        df = _ohlc([100.0] * 40, spread=2.0)
        atr = _compute_atr(df["high"].values, df["low"].values, df["close"].values)
        assert atr == pytest.approx(4.0)

    def test_wilder_smoothing_hand_computed(self):
        # 15 bars with TR=2 seed, then one bar with TR=16 (gap up from 100 to 114).
        closes = [100.0] * 15 + [114.0]
        high = [101.0] * 15 + [116.0]
        low = [99.0] * 15 + [113.0]
        atr = _compute_atr(np.array(high), np.array(low), np.array(closes))
        # seed = mean(14 × 2) = 2; then (2 × 13 + 16) / 14 = 3.0
        assert atr == pytest.approx(3.0)

    def test_insufficient_bars(self):
        df = _ohlc([100.0] * ATR_PERIOD)
        assert _compute_atr(df["high"].values, df["low"].values, df["close"].values) is None

    def test_leading_nan_dropped_interior_ok(self):
        df = _ohlc([100.0] * 40, spread=1.0)
        df.iloc[:3, :] = np.nan
        atr = _compute_atr(df["high"].values, df["low"].values, df["close"].values)
        assert atr == pytest.approx(2.0)


# ── USD-implied alignment ─────────────────────────────────────────────────────

class TestUsdImpliedCloses:
    def test_aligned_by_bar_date_with_asof(self):
        idx = pd.bdate_range("2026-01-05", periods=5)
        closes = pd.Series([100.0, 110.0, 120.0, 130.0, 140.0], index=idx)
        # CCL known only on Mon and Wed — asof forward-fills to the bar date.
        ccl = pd.Series([10.0, 20.0], index=[idx[0], idx[2]])
        usd = usd_implied_closes(closes, ccl)
        assert usd.tolist() == pytest.approx([10.0, 11.0, 6.0, 6.5, 7.0])

    def test_leading_bars_without_ccl_dropped(self):
        idx = pd.bdate_range("2026-01-05", periods=4)
        closes = pd.Series([100.0, 100.0, 100.0, 100.0], index=idx)
        ccl = pd.Series([50.0], index=[idx[2]])
        usd = usd_implied_closes(closes, ccl)
        assert list(usd.index) == list(idx[2:])

    def test_interior_gap_fails_closed(self):
        idx = pd.bdate_range("2026-01-05", periods=4)
        closes = pd.Series([100.0, np.nan, 100.0, 100.0], index=idx)
        ccl = pd.Series([50.0] * 4, index=idx)
        assert usd_implied_closes(closes, ccl) is None

    def test_empty_ccl(self):
        idx = pd.bdate_range("2026-01-05", periods=4)
        assert usd_implied_closes(pd.Series([1.0] * 4, index=idx), pd.Series(dtype=float)) is None


# ── Weekly details ────────────────────────────────────────────────────────────

class TestWeeklyDetails:
    def test_short_history_none(self):
        d = _weekly_trend_details(_ohlc(np.linspace(100, 110, 55)))
        assert d.weekly_strength is None and d.ma50w_slope is None
        assert _weekly_trend(_ohlc(np.linspace(100, 110, 55))) == ("neutral", 0.0)

    def test_slope_none_below_58_weeks_present_above(self):
        assert _weekly_trend_details(_ohlc(np.linspace(100, 150, 260))).ma50w_slope is None
        slope = _weekly_trend_details(_ohlc(np.linspace(100, 150, 420))).ma50w_slope
        assert slope is not None and slope > 0


# ── compute_price_instrumentation ─────────────────────────────────────────────

class TestComputePriceInstrumentation:
    def _trend_df(self, n=420):
        rng = np.random.default_rng(7)
        return _ohlc(100 * np.exp(np.cumsum(rng.normal(0.001, 0.01, n))))

    def test_cedear_with_constant_ccl_matches_ars(self):
        df = self._trend_df()
        ccl = _ccl([1000.0] * len(df), df.index)
        pi = compute_price_instrumentation(df, AssetType.CEDEAR, ccl, float(df["close"].iloc[-1]), None)
        assert pi.rsi_14_usd_implied == pytest.approx(_compute_rsi(df["close"].values), abs=0.01)
        assert pi.weekly_strength_usd_implied == pi.weekly_strength
        assert pi.ma200_dist_pct_usd_implied == pi.ma200_dist_pct

    def test_argentine_stock_usd_fields_none(self):
        df = self._trend_df()
        ccl = _ccl([1000.0] * len(df), df.index)
        pi = compute_price_instrumentation(df, AssetType.ARGENTINE_STOCK, ccl, 100.0, 95.0)
        assert pi.rsi_14_usd_implied is None
        assert pi.weekly_strength_usd_implied is None
        assert pi.ma200_dist_pct_usd_implied is None
        assert pi.weekly_strength is not None

    def test_cedear_without_ccl_usd_fields_none(self):
        df = self._trend_df()
        pi = compute_price_instrumentation(df, AssetType.CEDEAR, None, 100.0, 95.0)
        assert pi.rsi_14_usd_implied is None

    def test_stop_distances(self):
        df = _ohlc([100.0] * 260, spread=1.0)  # ATR = 2
        pi = compute_price_instrumentation(df, AssetType.CEDEAR, None, 100.0, 97.0)
        assert pi.atr_pct_14 == pytest.approx(0.02)
        assert pi.stop_dist_pct == pytest.approx(0.03)
        assert pi.stop_dist_atr == pytest.approx(1.5)
        assert pi.ma200_dist_pct == 0.0

    def test_no_invalidation_no_stop_fields(self):
        df = _ohlc([100.0] * 260)
        pi = compute_price_instrumentation(df, AssetType.CEDEAR, None, 100.0, None)
        assert pi.stop_dist_pct is None and pi.stop_dist_atr is None

    def test_ma200_dist_signed(self):
        df = _ohlc([100.0] * 199 + [90.0])
        pi = compute_price_instrumentation(df, AssetType.CEDEAR, None, 90.0, None)
        assert pi.ma200_dist_pct < 0

    def test_zero_atr_is_none(self):
        df = _ohlc([100.0] * 260, spread=0.0)
        pi = compute_price_instrumentation(df, AssetType.CEDEAR, None, 100.0, 97.0)
        assert pi.atr_pct_14 is None and pi.stop_dist_atr is None
        assert pi.stop_dist_pct == pytest.approx(0.03)

    def test_short_history_all_finite_or_none(self):
        df = _ohlc(np.linspace(100, 110, 60))
        rec = compute_price_instrumentation(df, AssetType.CEDEAR, None, 110.0, 105.0).to_record()
        assert set(rec) == _FIELDS
        assert rec["ma200_dist_pct"] is None and rec["ma50w_slope"] is None
        assert all(v is None or math.isfinite(v) for v in rec.values())


# ── Earnings days ─────────────────────────────────────────────────────────────

def _calendar_mock(d):
    t = MagicMock()
    type(t).calendar = property(lambda self: {"Earnings Date": [d]})
    return t


@pytest.mark.parametrize("offset_days", [60, 4, 0])
def test_days_to_earnings_is_busday_count(offset_days):
    target = date.today() + timedelta(days=offset_days)
    with patch("data.earnings._is_excluded_underlying", return_value=False):
        with patch("data.earnings.yf.Ticker", return_value=_calendar_mock(target)):
            result = check_earnings_warning("AAPL")
    expected = int(np.busday_count(date.today().isoformat(), target.isoformat()))
    assert result.days_to_earnings == expected
    assert result.calendar_stale is False
    assert result.status != EarningsCheckStatus.UNVERIFIED


def test_past_calendar_date_is_stale_with_null_days():
    target = date.today() - timedelta(days=10)
    with patch("data.earnings._is_excluded_underlying", return_value=False):
        with patch("data.earnings.yf.Ticker", return_value=_calendar_mock(target)):
            result = check_earnings_warning("AAPL")
    assert result.days_to_earnings is None
    assert result.calendar_stale is True
    # Status and warning unchanged by the instrumentation.
    assert result.status == EarningsCheckStatus.VERIFIED_CLEAR
    assert result.message is None


def test_days_to_earnings_none_when_unverified():
    with patch("data.earnings._is_excluded_underlying", return_value=True):
        result = check_earnings_warning("XYZ")
    assert result.status == EarningsCheckStatus.UNVERIFIED
    assert result.days_to_earnings is None
    assert result.calendar_stale is None


# ── Record schema ─────────────────────────────────────────────────────────────

@dataclass
class _Opp:
    symbol: str = "AAA.BA"
    score: float = 60.0
    rsi_14: float = 35.0
    entry_price_ars: float = 100.0
    invalidation_level_ars: float = 95.0
    nearest_support: float = 96.4
    nearest_support_type: str = "MA50"
    catalyst: List[str] = field(default_factory=lambda: ["MA200 bounce/proximity"])
    weekly_trend: str = "neutral"
    tradeable: bool = False  # avoid paper-position side effects


class TestRecordSchema:
    def test_signal_carries_all_fields(self, tracking_paths):
        opp = _Opp()
        opp.instrumentation = PriceInstrumentation(weekly_strength=12.5, atr_pct_14=0.02)
        opp.earnings_status = "verified_clear"
        opp.days_to_earnings = 19
        opp.earnings_calendar_stale = False
        sr.record_signals([opp], "2026-11-20", data_date="2026-11-19")
        rec = sr.load_signals()[0]
        assert _FIELDS <= set(rec)
        assert rec["weekly_strength"] == 12.5 and rec["atr_pct_14"] == 0.02
        assert rec["rsi_14_usd_implied"] is None
        assert rec["earnings_status"] == "verified_clear" and rec["days_to_earnings"] == 19
        assert rec["earnings_calendar_stale"] is False

    def test_legacy_opp_gets_null_fields_and_strict_json(self, tracking_paths):
        sr.record_signals([_Opp()], "2026-11-20")
        raw = sr.SIGNALS_PATH.read_text(encoding="utf-8")
        assert "NaN" not in raw and "Infinity" not in raw
        rec = json.loads(raw.splitlines()[0])
        assert all(rec[k] is None for k in _FIELDS)
        assert rec["earnings_status"] is None and rec["days_to_earnings"] is None
        assert rec["earnings_calendar_stale"] is None

    def test_near_miss_carries_price_fields_not_earnings(self, tracking_paths):
        r = nm.NearMissRecord(
            scan_date="2026-11-20", symbol="BBB.BA", failed_criteria=["no_catalyst"],
            margins={}, computed_score=45.0, rsi=33.0, vol_ratio=0.7,
            support_distance_pct=2.0, weekly_trend="neutral",
            instrumentation=PriceInstrumentation(ma200_dist_pct=-0.05),
        )
        nm.record_near_misses([r], "2026-11-20", data_date="2026-11-19")
        rec = nm.load_near_misses()[0]
        assert _FIELDS <= set(rec)
        assert rec["ma200_dist_pct"] == -0.05
        assert "earnings_status" not in rec and "days_to_earnings" not in rec
        assert "earnings_calendar_stale" not in rec


# ── Scanner propagation ───────────────────────────────────────────────────────

def test_evaluate_bundle_propagates_earnings_and_instrumentation():
    from analysis.reversal.reversal_scanner import _BundleMetrics, _evaluate_bundle
    from data.earnings import EarningsCheckResult

    df = _ohlc([100.0] * 250)
    pi = PriceInstrumentation(weekly_strength=11.0)
    metrics = _BundleMetrics(
        symbol="CCC.BA", name="C", asset_type="cedear", close=df["close"].values, df=df,
        entry_price_ars=100.0, weekly_trend="neutral", weekly_strength=11.0, rsi=35.0,
        rsi_series=np.full(250, 35.0), vol_ratio=0.5, support_result=(99.0, "MA50", 0.01),
        catalysts=["RSI bullish divergence"], fundamentals_ok=True, adv_ars=1e9,
        instrumentation=pi,
    )
    bundle = MagicMock()
    bundle.metadata.symbol_underlying = "CCC"
    with patch("analysis.reversal.reversal_scanner._compute_metrics", return_value=metrics):
        with patch(
            "analysis.reversal.reversal_scanner.check_earnings_warning",
            return_value=EarningsCheckResult(
                EarningsCheckStatus.VERIFIED_CLEAR, days_to_earnings=12, calendar_stale=False,
            ),
        ):
            opp = _evaluate_bundle(bundle)
    assert opp.instrumentation is pi
    assert opp.earnings_status == "verified_clear"
    assert opp.days_to_earnings == 12
    assert opp.earnings_calendar_stale is False
