"""P4 fase 1: outcomes_v2 (window -> entry -> exit), parallel to v1."""

from __future__ import annotations

import hashlib
from datetime import date

import pandas as pd
import pytest

import analysis.reversal.outcomes_v2 as v2

TODAY = date(2026, 12, 31)  # past every deadline used below


def hist(start, rows):
    """rows: (open, high, low, close[, volume]) per business day."""
    idx = pd.bdate_range(start, periods=len(rows))
    cols = ["open", "high", "low", "close", "volume"]
    data = [tuple(r) + (1000,) * (5 - len(r)) for r in rows]
    return pd.DataFrame(data, index=idx, columns=cols)


def flat(p, vol=1000):
    return (p, p, p, p, vol)


def sig(**kw):
    s = {"scan_date": "2026-11-11", "data_date": "2026-11-10", "symbol": "T.BA",
         "entry_price_ars": 1000.0, "invalidation_level_ars": 950.0}
    s.update(kw)
    return s


# 11-09 Mon, 11-10 Tue (entry bar), 11-11 Wed (scan_date), 11-12 ...
def base_rows(*after):
    return [flat(995.0), flat(1000.0), *after]


def run(rows, signal=None, v1=None):
    return v2.assess_v2(signal or sig(), hist("2026-11-09", rows), v1, TODAY)


class TestSimulate:
    def test_window_includes_scan_date_bar(self):
        # scan_date bar (11-11) breaks the stop; v1 window (> scan_date) never sees it.
        h = hist("2026-11-09", base_rows((1000, 1000, 940, 960), flat(1000)))
        sc, dl = date(2026, 11, 11), date(2026, 12, 1)
        kw = dict(entry_close=1000.0, stop=950.0, scan_dt=sc, deadline=dl, today=TODAY,
                  enter_at_open=False, exit_model=v2.EXIT_V1)
        old = v2.simulate(h[h.index > pd.Timestamp(sc)], **kw)
        new = v2.simulate(v2.window_bars(h, pd.Timestamp("2026-11-10"), dl), **kw)
        assert old["status"] == v2.ST_LATERAL
        assert new["status"] == v2.ST_STOP

    def test_no_entry_when_open_at_or_below_stop(self):
        r = run(base_rows((950, 960, 945, 955)))
        assert r["status_v2"] == v2.ST_NO_ENTRY and r["entered"] is False
        assert r["r_s2"] is None and r["exit_s2_ars"] is None

    def test_s2_stop_at_level_s1_at_close(self):
        r = run(base_rows((990, 995, 940, 945)))
        assert r["status_v2"] == v2.ST_STOP
        assert r["exit_s2_ars"] == 950.0 and r["exit_s1_ars"] == 945.0
        assert r["r_s2"] == pytest.approx((950 - 990) / 50)
        assert r["r_s1"] == pytest.approx((945 - 990) / 50)

    def test_s2_stop_fills_at_open_when_bar_opens_below_stop(self):
        r = run(base_rows((990, 995, 995, 995), (930, 940, 920, 935)))
        assert r["status_v2"] == v2.ST_STOP
        assert r["exit_s2_ars"] == 930.0       # gap: filled at the open, R < -1
        assert r["exit_s1_ars"] == 935.0
        assert r["r_s2"] < -1

    def test_targets_relative_to_open_and_at_close(self):
        # entry at open 990 -> +5 % = 1039.5, +8 % = 1069.2
        r = run(base_rows((990, 1050, 990, 1045)))
        assert r["status_v2"] == v2.ST_T5 and r["exit_s2_ars"] == 1045.0
        r = run(base_rows((990, 1100, 990, 1075)))
        assert r["status_v2"] == v2.ST_T8

    def test_stop_wins_over_target_same_day(self):
        r = run(base_rows((990, 1100, 940, 1080)))
        assert r["status_v2"] == v2.ST_STOP

    def test_exit_models_never_change_state(self):
        for bar in [(990, 995, 940, 945), (990, 1100, 990, 1075), (990, 995, 990, 992)]:
            h = hist("2026-11-09", base_rows(bar))
            kw = dict(entry_close=1000.0, stop=950.0, scan_dt=date(2026, 11, 11),
                      deadline=date(2026, 12, 1), today=TODAY, enter_at_open=True)
            w = v2.window_bars(h, pd.Timestamp("2026-11-10"), date(2026, 12, 1))
            states = {v2.simulate(w, exit_model=m, **kw)["status"] for m in (v2.EXIT_V1, v2.EXIT_S1, v2.EXIT_S2)}
            assert len(states) == 1

    def test_lateral_and_pending(self):
        rows = base_rows((990, 1000, 985, 995), flat(996))
        assert run(rows)["status_v2"] == v2.ST_LATERAL
        pend = v2.assess_v2(sig(), hist("2026-11-09", rows), None, date(2026, 11, 13))
        assert pend["status_v2"] == v2.ST_PENDING


class TestOrderAndSteps:
    def test_window_step_changes_state_entry_step_changes_r(self):
        h = hist("2026-11-09", base_rows((1000, 1000, 940, 960), flat(1000)))
        s, v1 = sig(), {"next_open_ars": 1000.0, "entry_bar_date": "2026-11-10"}
        st = v2.assess_steps(s, h, v1, TODAY)
        assert st["v1"]["status"] == v2.ST_LATERAL and st["a"]["status"] == v2.ST_STOP
        assert st["b"]["status"] == v2.ST_STOP          # same open as entry: no further change
        assert st["window_start_is_scan_date"] is True

    def test_gap_row_is_no_entry_in_b_only(self):
        h = hist("2026-11-09", base_rows((940, 945, 900, 920), flat(930)))
        st = v2.assess_steps(sig(), h, {"next_open_ars": 940.0}, TODAY)
        assert st["a"]["status"] == v2.ST_STOP and st["b"]["status"] == v2.ST_NO_ENTRY


class TestBasis:
    def test_adjusted_cache_is_rescaled_to_recorded_basis(self):
        # cache rescaled by 1/1.0067 after the signal (BNG-like); entry/stop recorded raw.
        k = 1 / 1.0067
        rows = [tuple(x * k for x in r[:4]) + (1000,) for r in
                base_rows((990, 995, 940, 945))]
        r = v2.assess_v2(sig(), hist("2026-11-09", rows), {"next_open_ars": 990.0}, TODAY)
        assert r["basis_adjusted"] is True and r["basis_factor"] == pytest.approx(1.0067, abs=1e-4)
        assert r["exit_s2_ars"] == 950.0 and r["r_s2"] == pytest.approx(-0.8)

    def test_noise_below_tolerance_is_not_rescaled(self):
        rows = base_rows((990, 995, 940, 945))
        rows[1] = flat(1000.05)
        r = v2.assess_v2(sig(), hist("2026-11-09", rows), None, TODAY)
        assert r["basis_adjusted"] is False

    def test_impossible_factor_is_data_error(self):
        rows = [tuple(x / 51 for x in r[:4]) + (1000,) for r in base_rows((990, 995, 940, 945))]
        r = v2.assess_v2(sig(), hist("2026-11-09", rows), None, TODAY)
        assert r["status_v2"] == v2.ST_ERROR and r["data_error_reason"] == v2.ERR_BASIS_MISMATCH
        assert r["r_s2"] is None

    def test_hwm_like_unmatched_entry_far_from_price_level_is_basis_error(self):
        # no data_date, entry 51x the cache level: close-match fails, but it is a data error
        rows = [tuple(x / 51 for x in r[:4]) + (1000,) for r in base_rows((990, 995, 940, 945))]
        r = v2.assess_v2(sig(data_date=None), hist("2026-11-09", rows), None, TODAY)
        assert r["status_v2"] == v2.ST_ERROR and r["data_error_reason"] == v2.ERR_BASIS_MISMATCH
        assert r["basis_factor"] == pytest.approx(51, rel=0.1)

    def test_invalid_denominator_is_data_error_not_gap(self):
        r = run(base_rows((990, 995, 940, 945)), signal=sig(invalidation_level_ars=1005.0))
        assert r["status_v2"] == v2.ST_ERROR and r["data_error_reason"] == v2.ERR_INVALID_DENOMINATOR

    def test_missing_entry_bar_is_not_instrumented(self):
        r = run(base_rows((990, 995, 940, 945)), signal=sig(data_date="2026-01-05"))
        # no instrumentation is NOT a data error: separate status, same reason code
        assert r["status_v2"] == v2.ST_NOT_INSTRUMENTED and r["data_error_reason"] == v2.ERR_NO_ENTRY_BAR


class TestFlags:
    def test_bar_jump_flag_only_state_unchanged(self):
        r = run(base_rows((990, 995, 990, 992), (1250, 1260, 1240, 1255)))
        assert "bar_jump" in r["data_flags"]
        assert r["status_v2"] == v2.ST_T8

    def test_flat_zero_trigger_flag(self):
        r = run(base_rows((990, 995, 990, 992), flat(900, vol=0)))
        assert r["status_v2"] == v2.ST_STOP and "flat_zero_trigger" in r["data_flags"]

    def test_illiquid_zero_volume_bar_without_trigger_not_flagged_as_trigger(self):
        r = run(base_rows(flat(990, vol=0), (990, 1000, 985, 995)))
        assert "flat_zero_trigger" not in r["data_flags"] and r["n_flat_zero_bars"] == 1

    def test_ex_div_in_window_flags_without_changing_state(self):
        rows = base_rows((990, 995, 985, 990), flat(990))
        a = run(rows)
        b = run(rows, signal=sig(ex_div_date="2026-11-20"))
        assert b["ex_div_in_window"] is True and b["basis_uncertain"] is True
        assert (b["status_v2"], b["r_s2"]) == (a["status_v2"], a["r_s2"])
        c = run(rows, signal=sig(ex_div_date="2027-02-01"))
        assert c["ex_div_in_window"] is False


class TestBuildAndIO:
    def _signals(self):
        return [sig(), sig(symbol="P.BA", scan_date="2026-12-30", data_date="2026-12-29"),
                sig(symbol="N.BA", tradeable=False), sig(symbol="X.BA")]

    def _loader(self, symbol):
        if symbol == "X.BA":
            return None
        if symbol == "P.BA":
            return hist("2026-12-28", [flat(1000), flat(1000), flat(1000)])
        return hist("2026-11-09", base_rows((990, 995, 940, 945)))

    def test_pending_transient_and_not_tradeable_not_stored(self):
        recs, stats = v2.build_v2(self._signals(), {}, {}, self._loader, date(2026, 12, 30))
        assert [r["symbol"] for r in recs] == ["T.BA"]
        assert stats["pending"] == 1 and stats["transient_skipped"] == 1 and stats["not_tradeable"] == 1

    def test_idempotent_and_existing_records_untouched(self, tmp_path):
        recs, _ = v2.build_v2(self._signals(), {}, {}, self._loader, TODAY)
        path = tmp_path / "o2.jsonl"
        v2.save_v2(recs, path)
        h1 = hashlib.md5(path.read_bytes()).hexdigest()
        recs2, stats = v2.build_v2(self._signals()[:1], {}, v2.load_v2(path), self._loader, TODAY)
        assert stats["kept"] == 1 and stats["new"] == 0
        v2.save_v2(recs2, path)
        assert hashlib.md5(path.read_bytes()).hexdigest() == h1

    def test_v1_outcomes_file_is_never_written(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        v1p = tmp_path / "outcomes.jsonl"
        v1p.write_text('{"scan_date": "2026-11-11", "symbol": "T.BA"}\n')
        before = hashlib.md5(v1p.read_bytes()).hexdigest()
        recs, _ = v2.build_v2(self._signals(), {}, {}, self._loader, TODAY)
        v2.save_v2(recs, tmp_path / "data" / "o2.jsonl")
        assert hashlib.md5(v1p.read_bytes()).hexdigest() == before
        assert v2.OUTCOMES_V2_PATH.name == "outcomes_v2.jsonl" and v2.OUTCOMES_V2_PATH.name != "outcomes.jsonl"


class TestDetectorsAudit:
    def test_jump_over_50pct_is_data_error_and_leaves_statistics(self):
        r = run(base_rows((990, 995, 990, 992), (1500, 1510, 1490, 1500)))
        assert r["status_v2"] == v2.ST_ERROR and r["data_error_reason"] == v2.ERR_PRICE_JUMP
        assert r["r_s2"] is None and r["r_s1"] is None and r["exit_s2_ars"] is None

    def test_jump_between_20_and_50_is_only_a_flag(self):
        r = run(base_rows((990, 995, 990, 992), (1300, 1310, 1290, 1300)))
        assert r["status_v2"] == v2.ST_T8 and "bar_jump" in r["data_flags"]
        assert r["r_s2"] is not None

    def test_jump_after_the_trigger_is_ignored(self):
        r = run(base_rows((990, 995, 940, 945), (2000, 2010, 1990, 2000)))
        assert r["status_v2"] == v2.ST_STOP

    def test_entry_exit_ratio_matching_a_split_is_data_error(self):
        # close 1000 -> 500 is exactly -50 % (not a >50 % jump) but entry/exit ~ 2
        r = run(base_rows((990, 995, 480, 500)))
        assert r["max_bar_jump"] == pytest.approx(0.5)
        assert r["status_v2"] == v2.ST_ERROR and r["data_error_reason"] == v2.ERR_RATIO_CHANGE

    def test_ratio_helper(self):
        assert v2.is_ratio_change(1000, 500) and v2.is_ratio_change(500, 1000)
        assert v2.is_ratio_change(1000, 20.2)
        assert not v2.is_ratio_change(1000, 945) and not v2.is_ratio_change(1000, 1075)

    def test_fmcc_like_21pct_jump_is_verified_not_excluded(self):
        # stale quote then a 21.6 % step: flagged, stays in the statistics
        r = run(base_rows((990, 995, 990, 992), (1000, 1000, 1000, 1000), (780, 800, 770, 784)))
        assert "bar_jump" in r["data_flags"] and r["status_v2"] == v2.ST_STOP and r["r_s2"] is not None


class TestCostAndAggregation:
    def test_cost_in_r(self):
        assert v2.cost_in_r(1000.0, 50.0) == pytest.approx(0.0111 * 1000 / 50)
        assert v2.cost_in_r(1000.0, 0.0) is None and v2.cost_in_r(None, 50.0) is None

    def test_aggregate_by_date(self):
        a = v2.aggregate_by_date([("d1", 1.0), ("d1", 3.0), ("d2", -1.0), ("d3", None)])
        assert (a["n_rows"], a["n_dates"]) == (3, 2)
        assert a["mean_per_date"] == pytest.approx(0.5)          # (2 + -1) / 2
        assert a["mean_per_row"] == pytest.approx(1.0)
        assert a["se_per_date"] == pytest.approx(1.5)            # std(2,-1)=2.1213 / sqrt(2)
        assert v2.aggregate_by_date([("d", 1.0)])["se_per_date"] != v2.aggregate_by_date([("d", 1.0)])["se_per_date"]  # nan


class TestRefreshFailOpen:
    def test_refresh_never_raises_and_warns(self, tmp_path, caplog):
        bad = tmp_path / "signals.jsonl"
        bad.write_text("{not json\n")
        with caplog.at_level("WARNING"):
            assert v2.refresh_outcomes_v2(signals_path=bad, outcomes_v1_path=tmp_path / "o.jsonl",
                                          path=tmp_path / "o2.jsonl") is None
        assert any("outcomes_v2: refresh failed" in r.getMessage() for r in caplog.records)
        assert not (tmp_path / "o2.jsonl").exists()

    def test_refresh_writes_only_v2(self, tmp_path):
        sp, v1p = tmp_path / "signals.jsonl", tmp_path / "outcomes.jsonl"
        import json
        sp.write_text(json.dumps(sig()) + "\n"); v1p.write_text("")
        before = hashlib.md5(v1p.read_bytes()).hexdigest()
        st = v2.refresh_outcomes_v2(sp, v1p, tmp_path / "outcomes_v2.jsonl",
                                    load_history=lambda s: hist("2026-11-09", base_rows((990, 995, 940, 945))),
                                    today=TODAY)
        assert st["new"] == 1 and len(v2.load_v2(tmp_path / "outcomes_v2.jsonl")) == 1
        assert hashlib.md5(v1p.read_bytes()).hexdigest() == before

    def test_scan_continues_when_v2_hook_fails(self, tmp_path, monkeypatch, caplog):
        import analysis.reversal.near_miss_tracker as nm
        import analysis.reversal.outcome_tracker as ot
        import analysis.reversal.regime_snapshot as rs
        import analysis.reversal.reversal_scanner as scanner
        import analysis.reversal.signal_registry as sr

        monkeypatch.chdir(tmp_path)
        d = tmp_path / "data" / "reversal_tracking"; d.mkdir(parents=True)
        monkeypatch.setattr(sr, "SIGNALS_PATH", d / "signals.jsonl")
        monkeypatch.setattr(nm, "NEAR_MISSES_PATH", d / "near_misses.jsonl")
        monkeypatch.setattr(ot, "OUTCOMES_PATH", d / "outcomes.jsonl")
        monkeypatch.setattr(rs, "REGIME_SNAPSHOTS_PATH", d / "regime_snapshots.jsonl")

        def boom(*a, **k):
            raise RuntimeError("v2 exploded")
        monkeypatch.setattr(v2, "refresh_outcomes_v2", boom)
        with caplog.at_level("WARNING"):
            out = scanner.scan_reversals([], scan_date="2026-11-27", record=True)
        assert out == []
        assert any("outcomes_v2: hook failed" in r.getMessage() for r in caplog.records)
