"""P3 (Decision #45): `suppressed` state + counterfactual outcomes.

Invariants under test:
  - tradeable=False signals are `suppressed`, never `pending`, never in the win rate / R.
  - Their counterfactual (same logic as v1) lives in outcomes_suppressed.jsonl;
    outcomes.jsonl, outcomes_v2.jsonl and positions_log are never touched by it.
  - Anything that counted a suppressed signal as exposure still does.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

import analysis.reversal.outcome_tracker as ot
import analysis.reversal.outcomes_v2 as v2
import analysis.reversal.signal_registry as sr


def _sig(symbol, scan_date, tradeable=True, entry=1000.0, stop=950.0, **kw):
    s = {"scan_date": scan_date, "symbol": symbol, "score": 70.0, "rsi_14": 35.0,
         "entry_price_ars": entry, "invalidation_level_ars": stop, "nearest_support": 965.0,
         "support_type": "swing_low", "catalysts": ["RSI bullish divergence"],
         "weekly_trend": "neutral", "tradeable": tradeable,
         "outcome_status": "pending" if tradeable else "suppressed"}
    if not tradeable:
        s["suppression_reason"] = "En cuarentena: test"
    s.update(kw)
    return s


def _df(start, closes, lows=None):
    idx = pd.date_range(start=start, periods=len(closes), freq="B")
    return pd.DataFrame({"close": closes, "low": lows or closes}, index=idx)


STOP_DF = _df("2026-07-02", [980, 960, 940, 1020], [975, 955, 935, 1010])      # stop_hit @ low 935
WIN_DF = _df("2026-07-02", [1010, 1030, 1060, 1070])                            # target_5pct


@pytest.fixture
def env(tmp_path, monkeypatch):
    sp = tmp_path / "signals.jsonl"
    monkeypatch.setattr(sr, "SIGNALS_PATH", sp)
    monkeypatch.setattr(ot, "OUTCOMES_PATH", tmp_path / "outcomes.jsonl")
    monkeypatch.setattr(ot, "OUTCOMES_SUPPRESSED_PATH", tmp_path / "outcomes_suppressed.jsonl")

    def write(signals):
        sp.write_text("".join(json.dumps(s) + "\n" for s in signals))

    return tmp_path, write


def _run_assess(frames):
    closer = MagicMock()
    with patch.object(ot, "_fetch_price_history", side_effect=lambda sym, sd: frames[sym]), \
         patch("data.positions_log.close_position", closer):
        ot.assess_outcomes()
    return closer


def _summary(frames):
    with patch.object(ot, "_fetch_price_history", side_effect=lambda sym, sd: frames[sym]), \
         patch("data.positions_log.close_position", MagicMock()):
        ot.assess_outcomes()
    return ot.summarize()


TRADEABLE = [_sig("W.BA", "2026-07-01"), _sig("L.BA", "2026-07-01", entry=1000.0, stop=950.0)]
SUPPRESSED = _sig("S.BA", "2026-07-01", tradeable=False)
FRAMES = {"W.BA": WIN_DF, "L.BA": STOP_DF, "S.BA": STOP_DF}


class TestCounterfactual:
    def test_suppressed_gets_stop_hit_counterfactual_in_separate_file(self, env):
        tmp, write = env
        write(TRADEABLE + [SUPPRESSED])
        closer = _run_assess(FRAMES)

        cf = ot._load_suppressed()
        rec = cf[("2026-07-01", "S.BA")]
        assert rec["outcome"] == "stop_hit" and rec["counterfactual"] is True
        assert rec["exit_price_ars"] == 935.0 and rec["r_multiple"] == pytest.approx(-1.3, abs=0.01)
        # v1 file: tradeables only
        assert {k[1] for k in ot._load_outcomes()} == {"W.BA", "L.BA"}
        # no position was ever opened: never closed either
        assert all(c.kwargs.get("symbol") != "S.BA" for c in closer.call_args_list)
        statuses = {s["symbol"]: s["outcome_status"] for s in sr.load_signals()}
        assert statuses["S.BA"] == "suppressed"

    def test_legacy_pending_row_is_migrated_to_suppressed(self, env):
        _, write = env
        write([dict(SUPPRESSED, outcome_status="pending")])
        _run_assess(FRAMES)
        assert sr.load_signals()[0]["outcome_status"] == "suppressed"

    def test_idempotent_and_retries_when_unresolved(self, env):
        tmp, write = env
        write([SUPPRESSED])
        with patch.object(ot, "_fetch_price_history", side_effect=RuntimeError("net")):
            assert ot.assess_suppressed() == 0
        assert not (tmp / "outcomes_suppressed.jsonl").exists()
        assert sr.load_signals()[0]["outcome_status"] == "suppressed"
        fetch = MagicMock(return_value=STOP_DF)
        with patch.object(ot, "_fetch_price_history", fetch):
            assert ot.assess_suppressed() == 1
            h = hashlib.md5((tmp / "outcomes_suppressed.jsonl").read_bytes()).hexdigest()
            assert ot.assess_suppressed() == 0
        assert fetch.call_count == 1  # resolved counterfactual is never re-fetched
        assert hashlib.md5((tmp / "outcomes_suppressed.jsonl").read_bytes()).hexdigest() == h

    def test_v1_outcomes_does_not_contain_counterfactuals(self, env):
        """Quarantine / exposure dedup / query.py read outcomes.jsonl: they must not see these."""
        _, write = env
        write([SUPPRESSED])
        _run_assess(FRAMES)
        assert ot._load_outcomes() == {}

    def test_new_non_tradeable_signal_is_born_suppressed(self, env):
        from tests.test_reversal_tracking import _Opp
        opp = _Opp(symbol="Q.BA", score=80.0, rsi_14=33.0, entry_price_ars=100.0,
                   invalidation_level_ars=95.0, nearest_support=97.0,
                   nearest_support_type="swing_low", catalyst=["x"], weekly_trend="neutral")
        opp.tradeable = False
        opp.suppression_reason = "no operable: test"
        sr.record_signals([opp], "2026-07-01")
        r = sr.load_signals()[0]
        assert r["outcome_status"] == "suppressed" and r["tradeable"] is False


class TestTradeableStatsUnchanged:
    def test_win_rate_and_r_identical_with_and_without_suppressed(self, env):
        _, write = env
        write(TRADEABLE)
        a = _summary(FRAMES).splitlines()
        write(TRADEABLE + [SUPPRESSED])
        b = _summary(FRAMES).splitlines()
        extra = [l for l in b if l not in a]
        assert extra, "the counterfactual block must be shown"
        assert all(("suprimid" in l or "ontrafactual" in l or "Supresiones" in l) for l in extra)
        assert [l for l in a if l not in b] == []
        pending = [l for l in b if l.startswith("Pending")][0]
        assert ": " in pending and pending.split(":")[1].split()[0] == "0"

    def test_suppressed_is_excluded_from_rate_everywhere(self):
        assert "suppressed" in ot._EXCLUDED_FROM_RATE
        wins, stops, lat, resolvable, pending = ot._catalyst_stats(
            [{"outcome": "suppressed"}, {"outcome": "stop_hit"}])
        assert (wins, stops, resolvable, pending) == (0, 1, 1, 1)


class TestExposureStillCounted:
    def test_prior_suppressed_signal_still_counts_as_open_exposure(self):
        prior = _sig("S.BA", "2026-07-01", tradeable=False)
        new = _sig("S.BA", "2026-07-03", entry=1005.0)
        # suppressed prior has NO record in outcomes.jsonl (as before the change)
        assert ot._is_exposure_duplicate(new, [prior, new], {}) is True


# ── outcomes_v2 counterfactual ────────────────────────────────────────────────

def _h(start, rows):
    idx = pd.bdate_range(start, periods=len(rows))
    return pd.DataFrame([tuple(r) + (1000,) * (5 - len(r)) for r in rows], index=idx,
                        columns=["open", "high", "low", "close", "volume"])


def _flat(p):
    return (p, p, p, p, 1000)


V2_ROWS = [_flat(995.0), _flat(1000.0), (990, 995, 940, 945), _flat(1000)]


def _v2sig(symbol, tradeable=True):
    return {"scan_date": "2026-11-11", "data_date": "2026-11-10", "symbol": symbol,
            "entry_price_ars": 1000.0, "invalidation_level_ars": 950.0, "tradeable": tradeable}


class TestV2Suppressed:
    def test_build_modes_are_mirror_images(self):
        sigs = [_v2sig("T.BA"), _v2sig("S.BA", tradeable=False)]
        load = lambda s: _h("2026-11-09", V2_ROWS)
        main, _ = v2.build_v2(sigs, {}, {}, load, date(2026, 12, 31))
        sup, _ = v2.build_v2(sigs, {}, {}, load, date(2026, 12, 31), suppressed=True)
        assert [r["symbol"] for r in main] == ["T.BA"] and "counterfactual" not in main[0]
        assert [r["symbol"] for r in sup] == ["S.BA"]
        assert sup[0]["counterfactual"] is True and sup[0]["signal_status"] == "suppressed"
        assert sup[0]["status_v2"] == v2.ST_STOP  # measured state kept, not overwritten

    def test_refresh_writes_suppressed_to_its_own_file(self, tmp_path):
        sp, v1p = tmp_path / "signals.jsonl", tmp_path / "outcomes.jsonl"
        sp.write_text("".join(json.dumps(s) + "\n" for s in
                              [_v2sig("T.BA"), _v2sig("S.BA", tradeable=False)]))
        v1p.write_text("")
        (tmp_path / "outcomes_suppressed.jsonl").write_text(json.dumps(
            {"scan_date": "2026-11-11", "symbol": "S.BA", "outcome": "stop_hit", "r_multiple": -1.2}) + "\n")
        main = tmp_path / "outcomes_v2.jsonl"
        v2.refresh_outcomes_v2(sp, v1p, main, load_history=lambda s: _h("2026-11-09", V2_ROWS),
                               today=date(2026, 12, 31))
        assert [r["symbol"] for r in v2.load_v2(main).values()] == ["T.BA"]
        cf = v2.load_v2(tmp_path / "outcomes_v2_suppressed.jsonl")
        assert [r["symbol"] for r in cf.values()] == ["S.BA"]
        assert list(cf.values())[0]["status_v1"] == "stop_hit"  # counterfactual v1 linked
