"""Tests for the reversal audit layer: signal_registry, near_miss_tracker, outcome_tracker."""

from __future__ import annotations

import json
import logging
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# ── Minimal ReversalOpportunity stub ─────────────────────────────────────────

@dataclass
class _Opp:
    symbol: str
    score: float
    rsi_14: float
    entry_price_ars: float
    invalidation_level_ars: float
    nearest_support: float
    nearest_support_type: str
    catalyst: List[str]
    weekly_trend: str
    warnings: List[str] = field(default_factory=list)


# ── signal_registry ───────────────────────────────────────────────────────────

class TestSignalRegistry:
    def _make_registry(self, tmp_path):
        import analysis.reversal.signal_registry as sr
        sr.SIGNALS_PATH = tmp_path / "signals.jsonl"
        return sr

    def test_record_and_load(self, tmp_path):
        sr = self._make_registry(tmp_path)
        opp = _Opp(
            symbol="SNAP.BA", score=80.0, rsi_14=33.1, entry_price_ars=6895.0,
            invalidation_level_ars=6678.0, nearest_support=6780.0,
            nearest_support_type="swing_low", catalyst=["RSI bullish divergence"],
            weekly_trend="positive",
        )
        sr.record_signals([opp], "2026-06-30")
        records = sr.load_signals()
        assert len(records) == 1
        assert records[0]["symbol"] == "SNAP.BA"
        assert records[0]["entry_price_ars"] == 6895.0
        assert records[0]["outcome_status"] == "pending"

    def test_record_is_idempotent(self, tmp_path):
        sr = self._make_registry(tmp_path)
        opp = _Opp(
            symbol="SNAP.BA", score=80.0, rsi_14=33.1, entry_price_ars=6895.0,
            invalidation_level_ars=6678.0, nearest_support=6780.0,
            nearest_support_type="swing_low", catalyst=["RSI bullish divergence"],
            weekly_trend="positive",
        )
        sr.record_signals([opp], "2026-06-30")
        sr.record_signals([opp], "2026-06-30")  # second call — same scan_date
        assert len(sr.load_signals()) == 1

    def test_check_recent_finds_repeated_signal(self, tmp_path):
        sr = self._make_registry(tmp_path)
        opp = _Opp(
            symbol="BYMA.BA", score=46.0, rsi_14=43.0, entry_price_ars=292.5,
            invalidation_level_ars=279.0, nearest_support=283.0,
            nearest_support_type="swing_low", catalyst=["MA200 bounce/proximity"],
            weekly_trend="neutral",
        )
        sr.record_signals([opp], "2026-07-23")
        # Same ticker 1 day later, price barely moved
        result = sr.check_recent("BYMA.BA", "2026-07-24", current_price_ars=293.0)
        assert result == "2026-07-23"

    def test_check_recent_ignores_significant_price_move(self, tmp_path):
        sr = self._make_registry(tmp_path)
        opp = _Opp(
            symbol="SNAP.BA", score=80.0, rsi_14=33.1, entry_price_ars=6895.0,
            invalidation_level_ars=6678.0, nearest_support=6780.0,
            nearest_support_type="swing_low", catalyst=["RSI bullish divergence"],
            weekly_trend="positive",
        )
        sr.record_signals([opp], "2026-06-30")
        # Price moved >3% — new setup
        result = sr.check_recent("SNAP.BA", "2026-07-01", current_price_ars=7300.0)
        assert result is None

    def test_check_recent_ignores_old_signals(self, tmp_path):
        sr = self._make_registry(tmp_path)
        opp = _Opp(
            symbol="NEM.BA", score=51.0, rsi_14=41.1, entry_price_ars=48640.0,
            invalidation_level_ars=45921.0, nearest_support=46500.0,
            nearest_support_type="MA200", catalyst=["MA200 bounce/proximity"],
            weekly_trend="neutral",
        )
        sr.record_signals([opp], "2026-06-30")
        # 10 days later — beyond default lookback_days=7
        result = sr.check_recent("NEM.BA", "2026-07-10", current_price_ars=48700.0)
        assert result is None

    def test_update_outcome_status(self, tmp_path):
        sr = self._make_registry(tmp_path)
        opp = _Opp(
            symbol="VOD.BA", score=80.0, rsi_14=35.0, entry_price_ars=20480.0,
            invalidation_level_ars=20000.0, nearest_support=20200.0,
            nearest_support_type="MA50", catalyst=["RSI bullish divergence"],
            weekly_trend="positive",
        )
        sr.record_signals([opp], "2026-07-01")
        sr.update_outcome_status("VOD.BA", "2026-07-01", "target_5pct")
        records = sr.load_signals()
        assert records[0]["outcome_status"] == "target_5pct"


# ── near_miss_tracker ─────────────────────────────────────────────────────────

class TestNearMissTracker:
    def test_gate_distribution_counts(self):
        from analysis.reversal.near_miss_tracker import NearMissRecord, _gate_distribution

        records = [
            NearMissRecord("2026-08-01", "A.BA", ["rsi_out_of_range"], {}, 35.0, 47.2, 0.5, 2.0, "neutral"),
            NearMissRecord("2026-08-01", "B.BA", ["rsi_out_of_range"], {}, 30.0, 46.0, 0.5, 1.5, "neutral"),
            NearMissRecord("2026-08-01", "C.BA", ["weekly_trend_negative"], {}, 55.0, 38.0, 0.4, 3.0, "negative"),
            NearMissRecord("2026-08-01", "D.BA", ["no_catalyst"], {}, 42.0, 35.0, 0.5, 2.5, "neutral"),
        ]
        dist = _gate_distribution(records)
        assert dist["rsi_out_of_range"] == 2
        assert dist["weekly_trend_negative"] == 1
        assert dist["no_catalyst"] == 1

    def test_record_near_misses_writes_jsonl(self, tmp_path):
        import analysis.reversal.near_miss_tracker as nm
        nm.NEAR_MISSES_PATH = tmp_path / "near_misses.jsonl"

        from analysis.reversal.near_miss_tracker import NearMissRecord
        records = [
            NearMissRecord(
                scan_date="2026-08-04",
                symbol="FAKE.BA",
                failed_criteria=["rsi_out_of_range"],
                margins={"rsi_value": 47.2, "rsi_gap": 2.2},
                computed_score=None,
                rsi=47.2,
                vol_ratio=0.5,
                support_distance_pct=2.0,
                weekly_trend="neutral",
            )
        ]
        nm.record_near_misses(records, "2026-08-04")
        lines = (tmp_path / "near_misses.jsonl").read_text().splitlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["symbol"] == "FAKE.BA"
        assert data["failed_criteria"] == ["rsi_out_of_range"]

    def test_record_near_misses_is_idempotent(self, tmp_path):
        import analysis.reversal.near_miss_tracker as nm
        nm.NEAR_MISSES_PATH = tmp_path / "near_misses.jsonl"

        from analysis.reversal.near_miss_tracker import NearMissRecord
        record = NearMissRecord(
            scan_date="2026-08-13",
            symbol="AIG.BA",
            failed_criteria=["rsi_out_of_range"],
            margins={"rsi_value": 47.5, "rsi_gap": 2.5},
            computed_score=None,
            rsi=47.5,
            vol_ratio=0.5,
            support_distance_pct=2.0,
            weekly_trend="neutral",
        )
        nm.record_near_misses([record], "2026-08-13")
        nm.record_near_misses([record], "2026-08-13")  # second call — same scan_date
        lines = (tmp_path / "near_misses.jsonl").read_text().splitlines()
        assert len(lines) == 1

    def test_summarize_gate_distribution_all_time(self, tmp_path):
        import analysis.reversal.near_miss_tracker as nm
        nm.NEAR_MISSES_PATH = tmp_path / "near_misses.jsonl"

        from analysis.reversal.near_miss_tracker import NearMissRecord
        records = [
            NearMissRecord("2026-08-01", "A.BA", ["weekly_trend_negative"], {}, 60.0, 35.0, 0.4, 2.0, "negative"),
            NearMissRecord("2026-08-01", "B.BA", ["weekly_trend_negative"], {}, 58.0, 33.0, 0.5, 1.5, "negative"),
            NearMissRecord("2026-08-01", "C.BA", ["no_catalyst"], {}, 40.0, 38.0, 0.6, 3.0, "neutral"),
        ]
        nm.record_near_misses(records, "2026-08-01")
        dist = nm.summarize_gate_distribution_all_time()
        assert dist["weekly_trend_negative"] == 2
        assert dist["no_catalyst"] == 1


# ── outcome_tracker ───────────────────────────────────────────────────────────

class TestOutcomeTracker:
    def _setup_signals_file(self, tmp_path, signals):
        path = tmp_path / "signals.jsonl"
        with path.open("w") as f:
            for s in signals:
                f.write(json.dumps(s) + "\n")
        return path

    def _patch_paths(self, tmp_path, monkeypatch):
        import analysis.reversal.signal_registry as sr
        import analysis.reversal.outcome_tracker as ot
        signals_path = tmp_path / "signals.jsonl"
        outcomes_path = tmp_path / "outcomes.jsonl"
        monkeypatch.setattr(sr, "SIGNALS_PATH", signals_path)
        monkeypatch.setattr(ot, "OUTCOMES_PATH", outcomes_path)
        return signals_path, outcomes_path

    def _make_price_df(self, start_date: str, closes: list, lows: list = None) -> pd.DataFrame:
        idx = pd.date_range(start=start_date, periods=len(closes), freq="B")
        if lows is None:
            lows = closes  # fallback: low == close (no intraday dip)
        return pd.DataFrame({"close": closes, "low": lows}, index=idx)

    def test_stop_hit_outcome(self, tmp_path, monkeypatch):
        signals_path, outcomes_path = self._patch_paths(tmp_path, monkeypatch)

        signals_path.write_text(json.dumps({
            "scan_date": "2026-07-01",
            "symbol": "TEST.BA",
            "score": 70.0,
            "rsi_14": 35.0,
            "entry_price_ars": 1000.0,
            "invalidation_level_ars": 950.0,
            "nearest_support": 965.0,
            "support_type": "swing_low",
            "catalysts": ["RSI bullish divergence"],
            "weekly_trend": "neutral",
            "outcome_status": "pending",
        }) + "\n")

        # close and low both below stop on day 3 → stop_hit, exit at low
        mock_df = self._make_price_df(
            "2026-07-02",
            closes=[980, 960, 940, 1020],
            lows=[975, 955, 935, 1010],
        )

        import analysis.reversal.outcome_tracker as ot
        with patch.object(ot, "_fetch_price_history", return_value=mock_df):
            with patch("data.prices.fetch_prices", return_value=pd.DataFrame({"close": [1000]})):
                ot.assess_outcomes()

        outcomes = list(ot._load_outcomes().values())
        assert len(outcomes) == 1
        assert outcomes[0]["outcome"] == "stop_hit"
        assert outcomes[0]["exit_price_ars"] == 935.0  # low, not close

    def test_stop_hit_intraday_low(self, tmp_path, monkeypatch):
        """Low pierces stop but close stays above — should still be stop_hit."""
        signals_path, outcomes_path = self._patch_paths(tmp_path, monkeypatch)

        signals_path.write_text(json.dumps({
            "scan_date": "2026-07-01",
            "symbol": "INTRA.BA",
            "score": 65.0,
            "rsi_14": 38.0,
            "entry_price_ars": 1000.0,
            "invalidation_level_ars": 950.0,
            "nearest_support": 965.0,
            "support_type": "MA50",
            "catalysts": ["MA200 bounce/proximity"],
            "weekly_trend": "neutral",
            "outcome_status": "pending",
        }) + "\n")

        # Day 2: close=975 (above stop), but low=940 (below stop) — intraday breach
        mock_df = self._make_price_df(
            "2026-07-02",
            closes=[990, 975, 1020],  # close never below 950
            lows=[985, 940, 1010],    # low[1]=940 pierces stop
        )

        import analysis.reversal.outcome_tracker as ot
        with patch.object(ot, "_fetch_price_history", return_value=mock_df):
            with patch("data.prices.fetch_prices", return_value=pd.DataFrame({"close": [1000]})):
                ot.assess_outcomes()

        outcomes = list(ot._load_outcomes().values())
        assert outcomes[0]["outcome"] == "stop_hit"
        assert outcomes[0]["exit_price_ars"] == 940.0  # the low that breached

    def test_target_5pct_outcome(self, tmp_path, monkeypatch):
        signals_path, outcomes_path = self._patch_paths(tmp_path, monkeypatch)

        signals_path.write_text(json.dumps({
            "scan_date": "2026-07-01",
            "symbol": "WIN.BA",
            "score": 80.0,
            "rsi_14": 30.0,
            "entry_price_ars": 1000.0,
            "invalidation_level_ars": 950.0,
            "nearest_support": 965.0,
            "support_type": "MA50",
            "catalysts": ["MA200 bounce/proximity"],
            "weekly_trend": "positive",
            "outcome_status": "pending",
        }) + "\n")

        # close reaches +5% on day 5; lows are all safe above stop
        mock_df = self._make_price_df(
            "2026-07-02",
            closes=[1010, 1020, 1030, 1045, 1060],
            lows=[1005, 1015, 1025, 1040, 1055],
        )

        import analysis.reversal.outcome_tracker as ot
        with patch.object(ot, "_fetch_price_history", return_value=mock_df):
            with patch("data.prices.fetch_prices", return_value=pd.DataFrame({"close": [1000]})):
                ot.assess_outcomes()

        outcomes = list(ot._load_outcomes().values())
        assert outcomes[0]["outcome"] == "target_5pct"

    def test_target_not_counted_on_intraday_high_only(self, tmp_path, monkeypatch):
        """High spikes above target but close stays below — should NOT count as target."""
        signals_path, outcomes_path = self._patch_paths(tmp_path, monkeypatch)

        signals_path.write_text(json.dumps({
            "scan_date": "2026-06-01",
            "symbol": "SPIKE.BA",
            "score": 55.0,
            "rsi_14": 36.0,
            "entry_price_ars": 1000.0,
            "invalidation_level_ars": 950.0,
            "nearest_support": 965.0,
            "support_type": "swing_low",
            "catalysts": ["RSI bullish divergence"],
            "weekly_trend": "neutral",
            "outcome_status": "pending",
        }) + "\n")

        # close never reaches +5% (max close=1049); lows safe — should be lateral
        mock_df = self._make_price_df(
            "2026-06-02",
            closes=[1010, 1020, 1035, 1049] + [1030] * 26,  # 30 days total
            lows=[1005, 1015, 1030, 1040] + [1025] * 26,
        )

        import analysis.reversal.outcome_tracker as ot
        with patch.object(ot, "_fetch_price_history", return_value=mock_df):
            with patch("data.prices.fetch_prices", return_value=pd.DataFrame({"close": [1000]})):
                ot.assess_outcomes()

        outcomes = list(ot._load_outcomes().values())
        assert outcomes[0]["outcome"] == "lateral"

    def test_lateral_after_max_days(self, tmp_path, monkeypatch):
        signals_path, outcomes_path = self._patch_paths(tmp_path, monkeypatch)

        signals_path.write_text(json.dumps({
            "scan_date": "2026-06-01",  # far in the past → deadline passed
            "symbol": "FLAT.BA",
            "score": 50.0,
            "rsi_14": 40.0,
            "entry_price_ars": 1000.0,
            "invalidation_level_ars": 950.0,
            "nearest_support": 965.0,
            "support_type": "swing_low",
            "catalysts": ["RSI bullish divergence"],
            "weekly_trend": "neutral",
            "outcome_status": "pending",
        }) + "\n")

        # Prices always within range — no stop or target triggered
        mock_df = self._make_price_df(
            "2026-06-02",
            closes=[1005] * 30,
            lows=[1002] * 30,
        )

        import analysis.reversal.outcome_tracker as ot
        with patch.object(ot, "_fetch_price_history", return_value=mock_df):
            with patch("data.prices.fetch_prices", return_value=pd.DataFrame({"close": [1000]})):
                ot.assess_outcomes()

        outcomes = list(ot._load_outcomes().values())
        assert outcomes[0]["outcome"] == "lateral"

    def test_summarize_includes_pending(self, tmp_path, monkeypatch):
        signals_path, outcomes_path = self._patch_paths(tmp_path, monkeypatch)
        import analysis.reversal.signal_registry as sr

        signals_path.write_text(
            json.dumps({"scan_date": "2026-08-03", "symbol": "PEND.BA", "score": 60.0,
                        "rsi_14": 38.0, "entry_price_ars": 500.0, "invalidation_level_ars": 480.0,
                        "nearest_support": 490.0, "support_type": "MA50",
                        "catalysts": ["MA200 bounce/proximity"], "weekly_trend": "neutral",
                        "outcome_status": "pending"}) + "\n"
        )
        # outcomes.jsonl is empty — all pending
        outcomes_path.write_text("")

        import analysis.reversal.outcome_tracker as ot
        result = ot.summarize()
        assert "Pending" in result
        assert "n=1" in result

    def test_run_at_scan_start_does_not_raise(self, tmp_path, monkeypatch):
        import analysis.reversal.outcome_tracker as ot
        monkeypatch.setattr(ot, "OUTCOMES_PATH", tmp_path / "outcomes.jsonl")
        import analysis.reversal.signal_registry as sr
        monkeypatch.setattr(sr, "SIGNALS_PATH", tmp_path / "signals.jsonl")
        (tmp_path / "signals.jsonl").write_text("")
        # Should not raise even on empty files
        ot.run_at_scan_start()

    def test_zero_pending_signals_logs_info_summary(self, tmp_path, monkeypatch, caplog):
        signals_path, outcomes_path = self._patch_paths(tmp_path, monkeypatch)
        signals_path.write_text("")  # no signals → no pending

        import analysis.reversal.outcome_tracker as ot
        with caplog.at_level(logging.INFO, logger="analysis.reversal.outcome_tracker"):
            ot.assess_outcomes()

        info_messages = [r.message for r in caplog.records if r.levelno == logging.INFO]
        assert any("0 pending signals" in m for m in info_messages), (
            f"Expected INFO summary for empty run, got: {info_messages}"
        )

    def test_per_signal_price_fetch_failure_is_isolated(self, tmp_path, monkeypatch, caplog):
        """A fetch failure for one ticker marks it unresolved_no_data without aborting others."""
        signals_path, outcomes_path = self._patch_paths(tmp_path, monkeypatch)

        # Both signals have a scan_date far in the past so GOOD.BA resolves as lateral
        signals_path.write_text(
            json.dumps({
                "scan_date": "2026-06-01", "symbol": "FAIL.BA",
                "score": 60.0, "rsi_14": 35.0, "entry_price_ars": 1000.0,
                "invalidation_level_ars": 950.0, "nearest_support": 960.0,
                "support_type": "swing_low", "catalysts": [], "weekly_trend": "neutral",
                "outcome_status": "pending",
            }) + "\n" +
            json.dumps({
                "scan_date": "2026-06-01", "symbol": "GOOD.BA",
                "score": 65.0, "rsi_14": 37.0, "entry_price_ars": 1000.0,
                "invalidation_level_ars": 950.0, "nearest_support": 960.0,
                "support_type": "swing_low", "catalysts": [], "weekly_trend": "neutral",
                "outcome_status": "pending",
            }) + "\n"
        )

        good_df = self._make_price_df("2026-06-02", closes=[1005] * 30, lows=[1002] * 30)

        import analysis.reversal.outcome_tracker as ot

        def fake_fetch(symbol, scan_date):
            if symbol == "FAIL.BA":
                raise ConnectionError("simulated fetch failure")
            return good_df

        with patch.object(ot, "_fetch_price_history", side_effect=fake_fetch):
            with caplog.at_level(logging.WARNING, logger="analysis.reversal.outcome_tracker"):
                ot.assess_outcomes()

        outcomes = ot._load_outcomes()
        assert outcomes[("2026-06-01", "FAIL.BA")]["outcome"] == "unresolved_no_data"
        assert outcomes[("2026-06-01", "GOOD.BA")]["outcome"] == "lateral"
        assert any(
            "FAIL.BA" in r.message and r.levelno == logging.WARNING
            for r in caplog.records
        ), "Expected a WARNING naming FAIL.BA"


# ── exposure deduplication ────────────────────────────────────────────────────

class TestExposureDeduplification:
    """Unit tests for _is_exposure_duplicate and its effect on summarize()."""

    def test_duplicate_when_prior_pending(self):
        """Signal is a duplicate when prior is still open (no outcome yet)."""
        from analysis.reversal.outcome_tracker import _is_exposure_duplicate
        signals = [
            {"scan_date": "2026-07-01", "symbol": "VOD.BA", "entry_price_ars": 20480.0},
            {"scan_date": "2026-07-03", "symbol": "VOD.BA", "entry_price_ars": 20540.0},
        ]
        assert _is_exposure_duplicate(signals[1], signals, {}) is True

    def test_not_duplicate_when_prior_resolved_before_publication(self):
        """Signal is NOT a duplicate when prior resolved before it was published."""
        from analysis.reversal.outcome_tracker import _is_exposure_duplicate
        signals = [
            {"scan_date": "2026-07-01", "symbol": "VOD.BA", "entry_price_ars": 20480.0},
            {"scan_date": "2026-07-03", "symbol": "VOD.BA", "entry_price_ars": 20540.0},
        ]
        # Prior hit stop on day 1 → resolved 2026-07-02, before 2026-07-03
        outcomes_by_key = {
            ("2026-07-01", "VOD.BA"): {
                "outcome": "stop_hit", "days_to_outcome": 1,
            }
        }
        assert _is_exposure_duplicate(signals[1], signals, outcomes_by_key) is False

    def test_not_duplicate_when_price_moved_above_threshold(self):
        """Signal is NOT a duplicate when entry price moved ≥3% (new setup)."""
        from analysis.reversal.outcome_tracker import _is_exposure_duplicate
        # SNAP 6/30 → 7/01: 9.14% move — classic re-entry after exit
        signals = [
            {"scan_date": "2026-06-30", "symbol": "SNAP.BA", "entry_price_ars": 6895.0},
            {"scan_date": "2026-07-01", "symbol": "SNAP.BA", "entry_price_ars": 7525.0},
        ]
        assert _is_exposure_duplicate(signals[1], signals, {}) is False

    def test_not_duplicate_outside_lookback_window(self):
        """Signal is NOT a duplicate when prior is older than 7 days."""
        from analysis.reversal.outcome_tracker import _is_exposure_duplicate
        # DECK 7/01 → 8/03: 33 days apart, outside the 7-day window
        signals = [
            {"scan_date": "2026-07-01", "symbol": "DECK.BA", "entry_price_ars": 6350.0},
            {"scan_date": "2026-08-03", "symbol": "DECK.BA", "entry_price_ars": 6285.0},
        ]
        assert _is_exposure_duplicate(signals[1], signals, {}) is False

    def test_duplicate_when_prior_is_lateral(self):
        """Signal is a duplicate when prior resolved as lateral (days_to_outcome=None)."""
        from analysis.reversal.outcome_tracker import _is_exposure_duplicate
        signals = [
            {"scan_date": "2026-07-01", "symbol": "TST.BA", "entry_price_ars": 1000.0},
            {"scan_date": "2026-07-05", "symbol": "TST.BA", "entry_price_ars": 1010.0},
        ]
        outcomes_by_key = {
            ("2026-07-01", "TST.BA"): {
                "outcome": "lateral", "days_to_outcome": None,
            }
        }
        # Lateral = pending for 20 days → was open on day 4 when new signal arrived
        assert _is_exposure_duplicate(signals[1], signals, outcomes_by_key) is True

    def test_summarize_excludes_duplicates_from_win_rate(self, tmp_path, monkeypatch):
        """summarize() reports 100% win rate when the only duplicate is also a win."""
        import analysis.reversal.signal_registry as sr
        import analysis.reversal.outcome_tracker as ot

        signals_path = tmp_path / "signals.jsonl"
        outcomes_path = tmp_path / "outcomes.jsonl"
        monkeypatch.setattr(sr, "SIGNALS_PATH", signals_path)
        monkeypatch.setattr(ot, "OUTCOMES_PATH", outcomes_path)

        # Original signal (7/01) + duplicate 2 days later, price < 3% move
        # Original resolves on day 9 (after duplicate was published on day 2)
        signals_path.write_text(
            json.dumps({
                "scan_date": "2026-07-01", "symbol": "TST.BA",
                "entry_price_ars": 1000.0, "invalidation_level_ars": 950.0,
                "nearest_support": 960.0, "support_type": "MA200",
                "catalysts": ["MA200 bounce/proximity"], "weekly_trend": "positive",
                "score": 75.0, "rsi_14": 35.0, "outcome_status": "target_5pct",
            }) + "\n" +
            json.dumps({
                "scan_date": "2026-07-03", "symbol": "TST.BA",
                "entry_price_ars": 1010.0, "invalidation_level_ars": 960.0,
                "nearest_support": 970.0, "support_type": "MA200",
                "catalysts": ["MA200 bounce/proximity"], "weekly_trend": "positive",
                "score": 73.0, "rsi_14": 36.0, "outcome_status": "target_5pct",
            }) + "\n"
        )
        outcomes_path.write_text(
            json.dumps({
                "scan_date": "2026-07-01", "symbol": "TST.BA",
                "assessed_at": "2026-08-04", "entry_price_ars": 1000.0,
                "invalidation_level_ars": 950.0,
                "catalysts": ["MA200 bounce/proximity"],
                "outcome": "target_5pct", "days_to_outcome": 9,
                "exit_price_ars": 1055.0, "pct_change": 0.055,
            }) + "\n" +
            json.dumps({
                "scan_date": "2026-07-03", "symbol": "TST.BA",
                "assessed_at": "2026-08-04", "entry_price_ars": 1010.0,
                "invalidation_level_ars": 960.0,
                "catalysts": ["MA200 bounce/proximity"],
                "outcome": "target_5pct", "days_to_outcome": 7,
                "exit_price_ars": 1061.0, "pct_change": 0.051,
            }) + "\n"
        )

        result = ot.summarize()
        assert "n=2" in result          # total shown
        assert "1 excluidas" in result  # duplicate count
        assert "100%" in result         # win rate on deduped set (1 win / 1 resolvable)
