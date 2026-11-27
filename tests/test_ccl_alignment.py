"""Tests for data/ccl_alignment.py (P1, Decision #43).

Synthetic world: a "true" CCL per BYMA session, four local/ADR pairs whose
local/ADR ratio tracks it (plus small noise), and a source series published with
a known session shift k (session S_i's value dated S_{i+k}), forward-filled per
calendar day like data/ccl.py does.

Coverage:
  - shift +1 and −1 detected and applied (aligned == true CCL at every session)
  - ambiguous reference → flagged, table applied, never "corrected" to the estimate
  - no-variance window → ambiguous
  - decided ≠ table → regime_change, provisional tail segment, table file untouched
  - piecewise table (0 → 1 change with a repeated record, like 2026-09-08)
  - spot / as_of (ccl_at_scan) unchanged; one shared CCLSeries across bundles
  - ADR missing / no CCL / no local pairs → unavailable
  - tail_provisional when the record after the last session is not published yet
  - regime table validation and the repo's seeded table
  - ghost bars excluded from the session calendar
  - regime snapshot stores the record; fx_context reads the aligned history
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd
import pytest

from analysis.reversal import regime_snapshot as rs
from analysis.reversal.fx_context import build_fx_enrichment
from data import ccl_alignment as ca
from data.models import (
    AssetType,
    CCLSeries,
    FetchStatus,
    PriceHistory,
    TickerBundle,
    TickerMetadata,
)

N_SESSIONS = 120
SPOT = 1766.75
AS_OF = date(2026, 11, 27)


# ── Synthetic world ───────────────────────────────────────────────────────────

def _sessions(n: int = N_SESSIONS) -> pd.DatetimeIndex:
    days = pd.bdate_range("2026-03-02", periods=n + 2)
    return days.delete([10, 50])  # two weekday holidays


def _walk(rng: np.random.Generator, n: int, sigma: float, start: float) -> np.ndarray:
    return start * np.exp(np.cumsum(rng.normal(0.0, sigma, n)))


def _true_ccl(sessions: pd.DatetimeIndex, seed: int = 1) -> pd.Series:
    rng = np.random.default_rng(seed)
    return pd.Series(_walk(rng, len(sessions), 0.01, 1500.0), index=sessions)


def _source(true: pd.Series, ks: Sequence[int], tail: bool = True) -> pd.Series:
    """Session S_i's true value published under the date of S_{i+k_i}; calendar ffill."""
    s = true.index
    rec: Dict[pd.Timestamp, float] = {}
    for i, k in enumerate(ks):
        j = i + k
        if 0 <= j < len(s):
            rec[s[j]] = float(true.iloc[i])
        elif j == len(s) and tail:
            rec[s[-1] + pd.Timedelta(days=1)] = float(true.iloc[i])
    ser = pd.Series(rec).sort_index()
    full = pd.date_range(min(ser.index[0], s[0]), max(ser.index[-1], s[-1]), freq="D")
    out = ser.reindex(full).ffill()
    return out.bfill()  # first dates before any record (shift −1 at the start)


def _frame(close: np.ndarray, index: pd.DatetimeIndex, volume: Optional[np.ndarray] = None) -> pd.DataFrame:
    vol = np.full(len(close), 1000.0) if volume is None else volume
    return pd.DataFrame(
        {"open": close, "high": close, "low": close, "close": close, "volume": vol}, index=index,
    )


def _pairs(true: pd.Series, seed: int = 7, linked: bool = True):
    """Local frames (in bundles) and ADR frames (loader). linked=False → reference unrelated to CCL."""
    rng = np.random.default_rng(seed)
    n = len(true)
    driver = true.to_numpy() if linked else _walk(rng, n, 0.01, 1500.0)
    local, adr = {}, {}
    for (lsym, asym), ratio in zip(ca.PAIRS, (10, 10, 25, 1)):
        a = _walk(rng, n, 0.02, 20.0)
        noise = np.exp(rng.normal(0.0, 0.002, n))
        adr[asym] = _frame(a, true.index)
        local[lsym] = _frame(a * driver / ratio * noise, true.index)
    return local, adr


def _bundle(symbol: str, df: Optional[pd.DataFrame], ccl: Optional[CCLSeries],
            asset_type: AssetType = AssetType.ARGENTINE_STOCK) -> TickerBundle:
    return TickerBundle(
        metadata=TickerMetadata(
            symbol_ars=symbol, name=symbol, asset_type=asset_type,
            symbol_underlying="XYZ" if asset_type == AssetType.CEDEAR else None,
            cedears_per_underlying=1.0 if asset_type == AssetType.CEDEAR else None,
        ),
        prices_ars=PriceHistory(symbol=symbol, data=df) if df is not None else None,
        ccl_series=ccl,
        mep_series=None,
        fundamentals=None,
        status=FetchStatus.OK,
    )


def _world(ks: Sequence[int], linked: bool = True, tail: bool = True, seed: int = 1):
    sessions = _sessions()
    true = _true_ccl(sessions, seed)
    source = _source(true, ks, tail=tail)
    ccl = CCLSeries(data=source, spot=SPOT, as_of=AS_OF)
    local, adr = _pairs(true, linked=linked)
    bundles = [_bundle(s, df, ccl) for s, df in local.items()]
    cedear_df = _frame(_walk(np.random.default_rng(3), len(sessions), 0.01, 10000.0), sessions)
    bundles.append(_bundle("XYZ.BA", cedear_df, ccl, AssetType.CEDEAR))
    return dict(sessions=sessions, true=true, source=source, ccl=ccl, bundles=bundles,
                loader=lambda sym: adr.get(sym))


def _regimes(tmp_path: Path, segments: List[Dict]) -> Path:
    p = tmp_path / "regimes.json"
    p.write_text(json.dumps({"segments": segments}), encoding="utf-8")
    return p


def _aligned_at_sessions(bundles: List[TickerBundle], sessions: pd.DatetimeIndex) -> pd.Series:
    return pd.Series(bundles[0].ccl_series.data.asof(sessions).to_numpy(), index=sessions)


# ── Detection + application ──────────────────────────────────────────────────

def test_synthetic_shift_plus_one_detected_and_applied(tmp_path):
    w = _world([1] * N_SESSIONS)
    path = _regimes(tmp_path, [{"from": "2020-01-01", "shift": 1}])

    r = ca.align_bundles_ccl(w["bundles"], w["loader"], path)

    assert r.status == ca.STATUS_CONFIRMED
    assert r.detected_shift == 1 and r.table_shift == 1 and r.applied
    assert r.margin >= ca.MIN_MARGIN and r.corr_by_shift["1"] >= ca.MIN_CORR
    assert r.n_sessions == ca.WINDOW_SESSIONS
    assert len(r.pairs_used) == 4
    np.testing.assert_allclose(_aligned_at_sessions(w["bundles"], w["sessions"]), w["true"])
    # Sanity: the raw source is one session behind the truth.
    raw = pd.Series(w["source"].asof(w["sessions"]).to_numpy(), index=w["sessions"])
    assert not np.allclose(raw, w["true"])


def test_synthetic_shift_minus_one_detected_and_applied(tmp_path):
    w = _world([-1] * N_SESSIONS)
    path = _regimes(tmp_path, [{"from": "2020-01-01", "shift": -1}])

    r = ca.align_bundles_ccl(w["bundles"], w["loader"], path)

    assert r.status == ca.STATUS_CONFIRMED
    assert r.detected_shift == -1
    # First session has no earlier record: it stays raw. Every other session is exact.
    s = w["sessions"]
    np.testing.assert_allclose(_aligned_at_sessions(w["bundles"], s)[1:], w["true"][1:])
    assert r.tail_provisional is False  # only shift +1 depends on a later record


def test_detect_shift_ranks_all_candidates():
    w = _world([1] * N_SESSIONS)
    local = {b.metadata.symbol_ars: b.prices_ars.data for b in w["bundles"][:4]}
    adr = {a: w["loader"](a) for _, a in ca.PAIRS}
    sessions = ca.byma_sessions(local)
    det = ca.detect_shift(ca.implied_returns(local, adr, sessions), w["source"], sessions)
    assert det.status == "decided" and det.shift == 1
    assert set(det.corr_by_shift) == {"-1", "0", "1"}
    assert det.corr_by_shift["1"] > det.corr_by_shift["0"] > -1


def test_ambiguous_reference_is_flagged_and_not_corrected(tmp_path):
    # Source truly shifted +1, table says 0, but the reference is unrelated
    # noise: the run must NOT apply its own estimate — table (raw, k=0) stays.
    w = _world([1] * N_SESSIONS, linked=False)
    path = _regimes(tmp_path, [{"from": "2020-01-01", "shift": 0}])

    r = ca.align_bundles_ccl(w["bundles"], w["loader"], path)

    assert r.status == ca.STATUS_AMBIGUOUS
    assert r.detected_shift is None and r.provisional_from is None
    assert r.applied_shift_last_session == 0
    assert r.reason and "below thresholds" in r.reason
    raw = w["source"].asof(w["sessions"]).to_numpy()
    np.testing.assert_allclose(_aligned_at_sessions(w["bundles"], w["sessions"]), raw)


def test_no_variance_window_is_ambiguous():
    w = _world([0] * N_SESSIONS)
    flat = pd.Series(1500.0, index=w["source"].index)
    local = {b.metadata.symbol_ars: b.prices_ars.data for b in w["bundles"][:4]}
    adr = {a: w["loader"](a) for _, a in ca.PAIRS}
    sessions = ca.byma_sessions(local)
    df = ca.candidate_returns(ca.implied_returns(local, adr, sessions), flat, sessions)
    det = ca.decide(df.iloc[-ca.WINDOW_SESSIONS:])
    assert det.status == ca.STATUS_AMBIGUOUS and det.shift is None
    assert det.reason == "no variance in window"


def test_decided_mismatch_is_regime_change_with_provisional_tail(tmp_path):
    w = _world([1] * N_SESSIONS)
    path = _regimes(tmp_path, [{"from": "2020-01-01", "shift": 0}])
    before = path.read_text()

    r = ca.align_bundles_ccl(w["bundles"], w["loader"], path)

    assert r.status == ca.STATUS_REGIME_CHANGE
    assert r.table_shift == 0 and r.detected_shift == 1
    assert r.provisional_from == r.window_start
    assert r.applied_shift_last_session == 1
    assert path.read_text() == before  # the table is never edited by a run
    s = w["sessions"]
    tail = s[s >= pd.Timestamp(r.provisional_from)]
    head = s[s < pd.Timestamp(r.provisional_from)]
    aligned = _aligned_at_sessions(w["bundles"], s)
    np.testing.assert_allclose(aligned[tail], w["true"][tail])
    np.testing.assert_allclose(aligned[head], w["source"].asof(head).to_numpy())


def test_piecewise_table_reproduces_a_0_to_1_change(tmp_path):
    # Like 2026-09-08: k=0 up to a session, k=1 from it on (the source repeats
    # the previous record on the change date).
    cut = 70
    ks = [0] * cut + [1] * (N_SESSIONS - cut)
    w = _world(ks)
    change = w["sessions"][cut]
    assert w["source"][change] == w["source"][w["sessions"][cut - 1]]  # repeated record
    path = _regimes(tmp_path, [
        {"from": "2020-01-01", "shift": 0},
        {"from": change.date().isoformat(), "shift": 1},
    ])

    r = ca.align_bundles_ccl(w["bundles"], w["loader"], path)

    assert r.status == ca.STATUS_CONFIRMED and r.detected_shift == 1
    np.testing.assert_allclose(_aligned_at_sessions(w["bundles"], w["sessions"]), w["true"])


def test_spot_as_of_unchanged_and_series_shared(tmp_path):
    w = _world([1] * N_SESSIONS)
    path = _regimes(tmp_path, [{"from": "2020-01-01", "shift": 1}])
    original = w["ccl"]
    raw_copy = original.data.copy()

    ca.align_bundles_ccl(w["bundles"], w["loader"], path)

    objs = {id(b.ccl_series) for b in w["bundles"]}
    assert len(objs) == 1
    new = w["bundles"][0].ccl_series
    assert new is not original
    assert new.spot == SPOT and new.as_of == AS_OF
    pd.testing.assert_series_equal(original.data, raw_copy)  # input not mutated


def test_fx_context_uses_aligned_history_and_keeps_ccl_at_scan(tmp_path):
    w = _world([1] * N_SESSIONS)
    cedear = w["bundles"][-1]
    before = build_fx_enrichment(cedear)
    path = _regimes(tmp_path, [{"from": "2020-01-01", "shift": 1}])

    ca.align_bundles_ccl(w["bundles"], w["loader"], path)
    after = build_fx_enrichment(cedear)

    assert after["ccl_at_scan"] == before["ccl_at_scan"] == round(SPOT, 2)
    true = w["true"]
    expected_5d = round(float(true.iloc[-1] / true.iloc[-6] - 1.0), 4)
    assert after["pct_change_ccl_5d"] == expected_5d
    assert before["pct_change_ccl_5d"] != expected_5d


# ── Degraded inputs ───────────────────────────────────────────────────────────

def test_adr_missing_is_unavailable_but_table_applied(tmp_path):
    w = _world([1] * N_SESSIONS)
    path = _regimes(tmp_path, [{"from": "2020-01-01", "shift": 1}])

    r = ca.align_bundles_ccl(w["bundles"], lambda sym: None, path)

    assert r.status == ca.STATUS_UNAVAILABLE and r.applied
    assert r.pairs_used == [] and r.detected_shift is None
    np.testing.assert_allclose(_aligned_at_sessions(w["bundles"], w["sessions"]), w["true"])


def test_adr_loader_exception_is_contained(tmp_path):
    w = _world([1] * N_SESSIONS)
    path = _regimes(tmp_path, [{"from": "2020-01-01", "shift": 1}])

    def boom(sym):
        raise RuntimeError("yfinance down")

    r = ca.align_bundles_ccl(w["bundles"], boom, path)
    assert r.status == ca.STATUS_UNAVAILABLE


def test_no_ccl_leaves_bundles_untouched(tmp_path):
    b = _bundle("GGAL.BA", None, None)
    r = ca.align_bundles_ccl([b], lambda s: None, _regimes(tmp_path, [{"from": "2020-01-01", "shift": 1}]))
    assert r.status == ca.STATUS_UNAVAILABLE and not r.applied
    assert b.ccl_series is None


def test_no_local_pairs_leaves_ccl_raw(tmp_path):
    w = _world([1] * N_SESSIONS)
    cedear = w["bundles"][-1]
    original = cedear.ccl_series
    r = ca.align_bundles_ccl([cedear], w["loader"], _regimes(tmp_path, [{"from": "2020-01-01", "shift": 1}]))
    assert r.status == ca.STATUS_UNAVAILABLE and not r.applied
    assert cedear.ccl_series is original


def test_unreadable_table_leaves_ccl_raw(tmp_path):
    w = _world([1] * N_SESSIONS)
    original = w["ccl"]
    r = ca.align_bundles_ccl(w["bundles"], w["loader"], tmp_path / "missing.json")
    assert r.status == ca.STATUS_UNAVAILABLE and not r.applied
    assert all(b.ccl_series is original for b in w["bundles"])


# ── Tail ──────────────────────────────────────────────────────────────────────

def test_tail_provisional_when_next_record_missing_or_repeated(tmp_path):
    path = _regimes(tmp_path, [{"from": "2020-01-01", "shift": 1}])

    published = _world([1] * N_SESSIONS, tail=True)
    assert ca.align_bundles_ccl(published["bundles"], published["loader"], path).tail_provisional is False

    missing = _world([1] * N_SESSIONS, tail=False)
    assert ca.align_bundles_ccl(missing["bundles"], missing["loader"], path).tail_provisional is True

    # Record after the last session exists but repeats the previous one
    # (placeholder copy / ffill), as seen on 2026-11-27 at 09:31.
    w = _world([1] * N_SESSIONS, tail=False)
    src = w["ccl"].data
    extra = pd.Series([src.iloc[-1]], index=[src.index[-1] + pd.Timedelta(days=1)])
    w["ccl"].data = pd.concat([src, extra])
    assert ca.align_bundles_ccl(w["bundles"], w["loader"], path).tail_provisional is True


# ── Regime table ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("segments", [
    [],
    [{"from": "2020-01-01", "shift": 2}],
    [{"from": "2021-01-01", "shift": 0}, {"from": "2020-01-01", "shift": 1}],
    [{"from": "2020-01-01", "shift": 0}, {"from": "2020-01-01", "shift": 1}],
])
def test_load_regimes_rejects_invalid_tables(tmp_path, segments):
    with pytest.raises(ValueError):
        ca.load_regimes(_regimes(tmp_path, segments))


def test_repo_regime_table_matches_findings():
    segs = ca.load_regimes()
    assert ca.shift_for(pd.Timestamp("2018-06-01"), segs) == 1
    assert ca.shift_for(pd.Timestamp("2026-09-07"), segs) == 0
    assert ca.shift_for(pd.Timestamp("2026-09-08"), segs) == 1
    assert ca.shift_for(pd.Timestamp("2026-11-26"), segs) == 1


# ── Session calendar ─────────────────────────────────────────────────────────

def test_ghost_bars_are_not_sessions():
    idx = pd.bdate_range("2026-11-02", periods=8)
    ghost = idx[3]
    frames = {}
    for sym, _ in ca.PAIRS:
        vol = np.full(len(idx), 500.0)
        vol[3] = 0.0
        frames[sym] = _frame(np.linspace(100, 110, len(idx)), idx, vol)
    sessions = ca.byma_sessions(frames)
    assert ghost not in sessions and len(sessions) == len(idx) - 1


# ── Regime snapshot ───────────────────────────────────────────────────────────

def test_snapshot_records_alignment(tmp_path, monkeypatch):
    monkeypatch.setattr(rs, "REGIME_SNAPSHOTS_PATH", tmp_path / "regime_snapshots.jsonl")
    w = _world([1] * N_SESSIONS)
    record = ca.align_bundles_ccl(
        w["bundles"], w["loader"], _regimes(tmp_path, [{"from": "2020-01-01", "shift": 1}]),
    ).to_record()

    snap = rs.compute_snapshot(w["bundles"], "2026-11-27", 0, data_date="2026-11-26",
                               ccl_alignment=record)
    # The synthetic world has < 200 bars (a "failed run" for append_snapshot,
    # Decision #35), so check the exact line append_snapshot would write.
    line = json.dumps(rs._strict_json_value(snap), ensure_ascii=False, allow_nan=False)
    stored = json.loads(line)
    al = stored["ccl_alignment"]
    assert al["status"] == "confirmed" and al["detected_shift"] == 1
    assert al["margin"] is not None and set(al["corr_by_shift"]) == {"-1", "0", "1"}
    assert al["params"] == {"window_sessions": 30, "min_margin": 0.25, "min_corr": 0.55}


def test_snapshot_without_alignment_is_null(tmp_path, monkeypatch):
    monkeypatch.setattr(rs, "REGIME_SNAPSHOTS_PATH", tmp_path / "regime_snapshots.jsonl")
    snap = rs.compute_snapshot([], "2026-11-27", 0)
    assert snap["ccl_alignment"] is None
