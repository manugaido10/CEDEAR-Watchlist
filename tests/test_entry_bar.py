"""Fase B2: entry-bar instrumentation in outcome_tracker (additive, measurement unchanged)."""

from __future__ import annotations

import json
from datetime import date
from unittest.mock import patch

import pandas as pd
import pytest

import analysis.reversal.near_miss_tracker as nm
import analysis.reversal.outcome_tracker as ot
import analysis.reversal.regime_snapshot as rs
import analysis.reversal.signal_registry as sr

TODAY = date(2026, 11, 20)


@pytest.fixture
def tracking_paths(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    d = tmp_path / "data" / "reversal_tracking"
    d.mkdir(parents=True)
    monkeypatch.setattr(sr, "SIGNALS_PATH", d / "signals.jsonl")
    monkeypatch.setattr(nm, "NEAR_MISSES_PATH", d / "near_misses.jsonl")
    monkeypatch.setattr(ot, "OUTCOMES_PATH", d / "outcomes.jsonl")
    monkeypatch.setattr(rs, "REGIME_SNAPSHOTS_PATH", d / "regime_snapshots.jsonl")
    return d


def _history(start, opens, closes, lows=None):
    idx = pd.bdate_range(start, periods=len(closes))
    return pd.DataFrame(
        {"open": opens, "close": closes, "low": lows if lows is not None else closes},
        index=idx,
    )


def _signal(**kw):
    s = {
        "scan_date": "2026-11-11", "symbol": "TEST.BA", "entry_price_ars": 1000.0,
        "invalidation_level_ars": 950.0, "catalysts": [], "outcome_status": "pending",
    }
    s.update(kw)
    return s


# Mon 2026-11-09 … : bar 11-10 is X-1 (entry), bar 11-11 is scan_date X.
_HIST = _history(
    "2026-11-09",
    opens=[990.0, 995.0, 940.0, 1000.0],
    closes=[992.0, 1000.0, 1010.0, 1020.0],
)


class TestEntryBarFields:
    def test_data_date_reads_bar_excluded_by_scan_filter(self):
        f = ot._entry_bar_fields(_signal(data_date="2026-11-10"), _HIST)
        assert f["entry_bar_date"] == "2026-11-10"
        assert f["entry_bar_date_source"] == "data_date"
        assert f["entry_bar_close_ars"] == 1000.0
        # First bar after the entry bar is 11-11 == scan_date (outside > scan_dt).
        assert f["next_open_ars"] == 940.0
        assert f["entry_gap_pct"] == pytest.approx(-0.06)
        assert f["entry_gap_through_stop"] is True

    def test_close_match_unique(self):
        f = ot._entry_bar_fields(_signal(), _HIST)
        assert f["entry_bar_date"] == "2026-11-10"
        assert f["entry_bar_date_source"] == "close_match"

    def test_close_match_within_tolerance(self):
        entry = 1000.0 * (1 + ot.ENTRY_CLOSE_MATCH_REL_TOL * 0.9)
        f = ot._entry_bar_fields(_signal(entry_price_ars=entry), _HIST)
        assert f["entry_bar_date"] == "2026-11-10"

    def test_close_match_outside_tolerance_is_null(self):
        entry = 1000.0 * (1 + ot.ENTRY_CLOSE_MATCH_REL_TOL * 3)
        f = ot._entry_bar_fields(_signal(entry_price_ars=entry), _HIST)
        assert f["entry_bar_date"] is None and f["next_open_ars"] is None
        assert f["entry_bar_date_source"] == "unmatched"

    def test_close_match_ambiguous_is_null(self):
        h = _history("2026-11-09", [1000.0] * 4, [1000.0, 1000.0, 1010.0, 1020.0])
        f = ot._entry_bar_fields(_signal(), h)
        assert f["entry_bar_date"] is None
        assert f["entry_bar_date_source"] == "ambiguous"

    def test_close_match_ignores_bars_after_scan_date(self):
        # 1020 only appears after scan_date → must not match.
        f = ot._entry_bar_fields(_signal(entry_price_ars=1020.0), _HIST)
        assert f["entry_bar_date"] is None

    def test_next_bar_not_yet_available(self):
        h = _HIST.iloc[:2]
        f = ot._entry_bar_fields(_signal(data_date="2026-11-10"), h)
        assert f["entry_bar_date"] == "2026-11-10"
        assert f["next_open_ars"] is None and f["entry_gap_pct"] is None
        assert f["entry_gap_through_stop"] is None

    def test_no_open_column(self):
        f = ot._entry_bar_fields(_signal(data_date="2026-11-10"), _HIST.drop(columns="open"))
        assert f["entry_bar_date"] == "2026-11-10" and f["next_open_ars"] is None

    def test_no_history(self):
        f = ot._entry_bar_fields(_signal(), None)
        assert f["entry_bar_date"] is None
        assert f["entry_bar_date_source"] == "no_history"

    def test_gap_above_stop(self):
        f = ot._entry_bar_fields(_signal(data_date="2026-11-11"), _HIST)
        assert f["next_open_ars"] == 1000.0
        assert f["entry_gap_through_stop"] is False
        assert f["entry_gap_pct"] == 0.0


class TestAssessSignal:
    def test_measurement_window_unchanged(self):
        """Gap below stop on bar X (scan_date) is NOT a stop: window stays > scan_date."""
        h = _history(
            "2026-11-09",
            opens=[990.0, 995.0, 940.0, 1000.0],
            closes=[992.0, 1000.0, 1010.0, 1060.0],
            lows=[985.0, 990.0, 930.0, 1000.0],
        )
        with patch.object(ot, "_fetch_price_history", return_value=h):
            r = ot._assess_signal(_signal(data_date="2026-11-10"), TODAY)
        assert r["outcome"] == "target_5pct"
        assert r["days_to_outcome"] == 1
        assert r["entry_gap_through_stop"] is True  # recorded, not acted on

    def test_single_fetch_when_no_bars_after_scan(self):
        h = _HIST.iloc[:3]  # last bar == scan_date
        with patch("data.prices.fetch_prices", return_value=h) as fp:
            r = ot._assess_signal(_signal(data_date="2026-11-10"), date(2026, 12, 5))
        assert fp.call_count == 1  # previously 2 (has_any_data re-fetch)
        assert r["outcome"] == "unresolved_no_data"  # deadline passed, no bars after
        assert r["next_open_ars"] == 940.0

    def test_pending_within_window_still_carries_fields(self):
        h = _HIST.iloc[:3]
        with patch("data.prices.fetch_prices", return_value=h):
            r = ot._assess_signal(_signal(data_date="2026-11-10"), date(2026, 11, 12))
        assert r["outcome"] == "pending"
        assert r["entry_bar_date"] == "2026-11-10" and r["next_open_ars"] == 940.0

    def test_no_data_at_all(self):
        with patch("data.prices.fetch_prices", return_value=None):
            r = ot._assess_signal(_signal(), TODAY)
        assert r["outcome"] == "unresolved_no_data"
        assert r["entry_bar_date_source"] == "no_history"


def test_assess_outcomes_persists_fields_only_for_resolved(tracking_paths):
    resolved = _signal(data_date="2026-11-10")
    pending = _signal(symbol="PEND.BA", scan_date="2026-11-19", data_date="2026-11-18")
    sr.SIGNALS_PATH.write_text(json.dumps(resolved) + "\n" + json.dumps(pending) + "\n")

    def fake(symbol, scan_date):
        if symbol == "PEND.BA":
            return _history("2026-11-17", [1000.0] * 3, [1000.0] * 3)
        return _history(
            "2026-11-09", [990.0, 995.0, 940.0, 1000.0], [992.0, 1000.0, 1010.0, 1060.0],
        )

    with patch.object(ot, "_fetch_price_history", side_effect=fake):
        ot.assess_outcomes()
    outcomes = ot._load_outcomes()
    assert set(outcomes) == {("2026-11-11", "TEST.BA")}  # pending is not persisted
    rec = outcomes[("2026-11-11", "TEST.BA")]
    assert rec["entry_bar_date"] == "2026-11-10" and rec["next_open_ars"] == 940.0
    assert all(k in rec for k in ot.ENTRY_BAR_FIELDS)


# ── Backfill script ───────────────────────────────────────────────────────────

class TestBackfillScript:
    def _outcome(self, **kw):
        r = {"scan_date": "2026-11-11", "symbol": "TEST.BA", "entry_price_ars": 1000.0,
             "invalidation_level_ars": 950.0, "outcome": "stop_hit", "pct_change": -0.05,
             "r_multiple": -1.0}
        r.update(kw)
        return r

    def test_adds_fields_without_touching_existing(self):
        from scripts import backfill_entry_bar as bf
        before = [self._outcome()]
        with patch.object(bf, "_fetch_price_history", return_value=_HIST):
            after, st = bf.backfill(before, signals=[])
        assert st == {"computed": 1}
        assert all(after[0][k] == v for k, v in before[0].items())
        assert after[0]["entry_bar_date"] == "2026-11-10"
        assert after[0]["entry_bar_date_source"] == "close_match"

    def test_uses_signal_data_date(self):
        from scripts import backfill_entry_bar as bf
        sig = {"scan_date": "2026-11-11", "symbol": "TEST.BA", "data_date": "2026-11-09"}
        with patch.object(bf, "_fetch_price_history", return_value=_HIST):
            after, _ = bf.backfill([self._outcome()], signals=[sig])
        assert after[0]["entry_bar_date_source"] == "data_date"
        assert after[0]["next_open_ars"] == 995.0

    def test_idempotent(self):
        from scripts import backfill_entry_bar as bf
        with patch.object(bf, "_fetch_price_history", return_value=_HIST):
            once, _ = bf.backfill([self._outcome()], signals=[])
        with patch.object(bf, "_fetch_price_history", side_effect=AssertionError("no fetch")):
            twice, st = bf.backfill(once, signals=[])
        assert twice == once and st == {"already_present": 1}

    def test_one_fetch_per_ticker(self):
        from scripts import backfill_entry_bar as bf
        recs = [self._outcome(), self._outcome(scan_date="2026-11-12")]
        with patch.object(bf, "_fetch_price_history", return_value=_HIST) as fp:
            bf.backfill(recs, signals=[])
        assert fp.call_count == 1

    def test_no_history_leaves_record_untouched(self):
        from scripts import backfill_entry_bar as bf
        rec = self._outcome()
        with patch.object(bf, "_fetch_price_history", return_value=None):
            after, st = bf.backfill([rec], signals=[])
        assert after == [rec] and st == {"skipped_no_history": 1}

    def test_dry_run_does_not_write(self, tracking_paths, monkeypatch):
        from scripts import backfill_entry_bar as bf
        out = tracking_paths / "outcomes.jsonl"
        out.write_text(json.dumps(self._outcome()) + "\n")
        monkeypatch.setattr(bf, "OUTCOMES_PATH", out)
        monkeypatch.setattr(bf, "SIGNALS_PATH", tracking_paths / "signals.jsonl")
        monkeypatch.setattr("sys.argv", ["backfill_entry_bar", "--dry-run"])
        raw = out.read_text()
        with patch.object(bf, "_fetch_price_history", return_value=_HIST):
            bf.main()
        assert out.read_text() == raw
