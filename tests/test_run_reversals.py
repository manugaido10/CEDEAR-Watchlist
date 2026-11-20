"""Tests for scripts/run_reversals.py run-integrity behaviour (Decision #35).

No network: the fetch, cache, market-hours gate, git commit and calibration
log are monkeypatched. Every test runs in tmp_path (monkeypatch.chdir) so the
relative tracking paths (data/reversal_tracking/*, data/positions_log.json,
output/) resolve inside the sandbox.

Coverage:
  - --dry-run writes no tracking file, no paper position, no commit; report
    goes to a *_dryrun.md file (control: the same run without --dry-run writes)
  - --sample implies dry-run
  - health gate aborts (exit != 0) on a stale-data universe, before scanning,
    with no records and no commit; in dry-run it only warns
  - intraday-bar check aborts every run, --force included
  - failed regime snapshot is not persisted and does not become the prior
  - re-run with the same data_date under another scan_date does not duplicate
    signals or paper positions
  - _TRACKING_FILES lists the five tracking files and never positions_log
"""

from __future__ import annotations

import importlib.util
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Optional

import pandas as pd
import pytest

from data.models import AssetType, FetchStatus, PriceHistory, TickerBundle, TickerMetadata

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "run_reversals.py"
_spec = importlib.util.spec_from_file_location("run_reversals_under_test", _SCRIPT)
rr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rr)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _bundle(
    symbol: str,
    last_day: Optional[date],
    status: FetchStatus = FetchStatus.OK,
    n_bars: int = 260,
) -> TickerBundle:
    prices = None
    if last_day is not None:
        idx = pd.bdate_range(end=pd.Timestamp(last_day), periods=n_bars)
        closes = [100.0 + (i % 7) for i in range(n_bars)]
        df = pd.DataFrame(
            {"open": closes, "high": closes, "low": closes, "close": closes,
             "volume": [1_000_000] * n_bars},
            index=idx,
        )
        prices = PriceHistory(symbol=symbol, data=df)
    return TickerBundle(
        metadata=TickerMetadata(symbol_ars=symbol, name=symbol, asset_type=AssetType.CEDEAR),
        prices_ars=prices,
        ccl_series=None,
        mep_series=None,
        fundamentals=None,
        status=status,
    )


def _prev_weekday(d: date) -> date:
    d -= timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def _healthy_universe(n: int = 10) -> List[TickerBundle]:
    last = _prev_weekday(datetime.now(rr._ART).date())
    return [_bundle(f"T{i}.BA", last) for i in range(n)]


class _CommitSpy:
    def __init__(self):
        self.calls: List[str] = []

    def __call__(self, scan_date: str) -> None:
        self.calls.append(scan_date)


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """Isolate cwd and stub every external side effect of run()."""
    monkeypatch.chdir(tmp_path)

    # Pin every tracking path explicitly: some older tests reassign these
    # module globals without monkeypatch, so the defaults cannot be trusted.
    import analysis.reversal.signal_registry as sr
    import analysis.reversal.near_miss_tracker as nmt
    import analysis.reversal.regime_snapshot as rs
    import analysis.reversal.outcome_tracker as ot
    _trk = Path("data/reversal_tracking")
    monkeypatch.setattr(sr, "SIGNALS_PATH", _trk / "signals.jsonl")
    monkeypatch.setattr(nmt, "NEAR_MISSES_PATH", _trk / "near_misses.jsonl")
    monkeypatch.setattr(rs, "REGIME_SNAPSHOTS_PATH", _trk / "regime_snapshots.jsonl")
    monkeypatch.setattr(ot, "OUTCOMES_PATH", _trk / "outcomes.jsonl")

    import data.cache
    import data.fetcher
    import data.prices
    import analysis.reversal.near_miss_outcomes as nmo
    import analysis.reversal.analyst_revision as ar

    class _DummyCache:
        pass

    state = {"bundles": _healthy_universe()}

    def _fake_fetch(cache=None):
        bundles = state["bundles"]
        return bundles, data.fetcher._build_summary(bundles)

    monkeypatch.setattr(data.cache, "Cache", _DummyCache)
    monkeypatch.setattr(data.fetcher, "fetch_universe_bundle", _fake_fetch)
    monkeypatch.setattr(data.prices, "_is_excluded_ars", lambda s: s.startswith("EXCL"))
    monkeypatch.setattr(nmo, "log_safe_only_calibration_progress", lambda: None)
    import analysis.reversal.news_check as nc
    monkeypatch.setattr(ar, "fetch_revisions_for_symbols", lambda pairs: {})
    monkeypatch.setattr(ar, "fetch_revisions", lambda opps, bundles: {})
    monkeypatch.setattr(nc, "fetch_news_context", lambda bundle, cache: None)
    monkeypatch.setattr(rr, "_check_market_hours", lambda force: None)
    spy = _CommitSpy()
    monkeypatch.setattr(rr, "_commit_tracking_files", spy)

    state["commit"] = spy
    state["root"] = tmp_path
    return state


def _tracking_files(root: Path) -> List[Path]:
    d = root / "data" / "reversal_tracking"
    return sorted(p for p in d.glob("*.jsonl") if p.stat().st_size > 0) if d.exists() else []


def _args(*argv: str):
    return rr._parse_args(list(argv))


# ── A1: dry-run ───────────────────────────────────────────────────────────────

def test_dry_run_writes_nothing_and_does_not_commit(sandbox):
    rc = rr.run(_args("--dry-run"))

    assert rc == rr.EXIT_OK
    assert _tracking_files(sandbox["root"]) == []
    assert not (sandbox["root"] / "data" / "positions_log.json").exists()
    assert sandbox["commit"].calls == []
    reports = list((sandbox["root"] / "output").glob("reversiones_*.md"))
    assert len(reports) == 1 and reports[0].name.endswith("_dryrun.md")


def test_control_record_run_writes_and_commits(sandbox):
    """Control for the dry-run test: same universe, record mode does write."""
    rc = rr.run(_args())

    assert rc == rr.EXIT_OK
    written = {p.name for p in _tracking_files(sandbox["root"])}
    assert "regime_snapshots.jsonl" in written
    assert len(sandbox["commit"].calls) == 1
    snap = json.loads((sandbox["root"] / "data/reversal_tracking/regime_snapshots.jsonl")
                      .read_text().splitlines()[0])
    assert snap["data_date"] == _prev_weekday(datetime.now(rr._ART).date()).isoformat()


def test_sample_implies_dry_run(sandbox):
    rc = rr.run(_args("--sample", "3"))

    assert rc == rr.EXIT_OK
    assert _tracking_files(sandbox["root"]) == []
    assert sandbox["commit"].calls == []


# ── A2: health gate ───────────────────────────────────────────────────────────

def _stale_universe() -> List[TickerBundle]:
    # 10 expected tickers came back MISSING (stale bars rejected by the fetcher)
    # plus 5 excluded-by-design tickers that are MISSING regardless.
    return (
        [_bundle(f"T{i}.BA", None, FetchStatus.MISSING) for i in range(10)]
        + [_bundle(f"EXCL{i}.BA", None, FetchStatus.MISSING) for i in range(5)]
    )


def test_health_gate_aborts_on_stale_universe(sandbox, monkeypatch, caplog):
    sandbox["bundles"] = _stale_universe()
    import analysis.reversal.reversal_scanner as scanner

    def _must_not_scan(*a, **k):
        raise AssertionError("scan_reversals must not run when the health gate fails")

    monkeypatch.setattr(scanner, "scan_reversals", _must_not_scan)

    rc = rr.run(_args())

    assert rc == rr.EXIT_UNHEALTHY_FETCH != 0
    assert _tracking_files(sandbox["root"]) == []
    assert sandbox["commit"].calls == []
    msg = " ".join(r.getMessage() for r in caplog.records if r.levelname == "ERROR")
    assert "0/10" in msg and "5 excluidos" in msg and "11:00" in msg


def test_health_gate_ignores_excluded_by_design(sandbox):
    # All expected tickers OK; many excluded tickers MISSING → still healthy.
    sandbox["bundles"] = _healthy_universe(10) + [
        _bundle(f"EXCL{i}.BA", None, FetchStatus.MISSING) for i in range(30)
    ]
    assert rr.run(_args("--dry-run")) == rr.EXIT_OK


def test_health_gate_only_warns_in_dry_run(sandbox):
    sandbox["bundles"] = _stale_universe()
    assert rr.run(_args("--dry-run")) == rr.EXIT_OK
    assert _tracking_files(sandbox["root"]) == []


# ── Intraday-bar check (replaces --force ⇒ dry-run) ───────────────────────────

@pytest.mark.parametrize("argv", [(), ("--force",), ("--dry-run",)])
def test_bar_dated_today_aborts_every_run(sandbox, argv):
    today = datetime.now(rr._ART).date()
    sandbox["bundles"] = _healthy_universe(10) + [_bundle("INTRA.BA", today)]

    rc = rr.run(_args(*argv))

    assert rc == rr.EXIT_INTRADAY_BAR
    assert _tracking_files(sandbox["root"]) == []
    assert sandbox["commit"].calls == []


def test_force_still_records_when_data_is_clean(sandbox):
    assert rr.run(_args("--force")) == rr.EXIT_OK
    assert len(sandbox["commit"].calls) == 1
    assert _tracking_files(sandbox["root"]) != []


# ── A3: failed snapshot ───────────────────────────────────────────────────────

def test_failed_snapshot_not_persisted_and_not_used_as_prior(sandbox):
    from analysis.reversal import regime_snapshot as rs

    good = rs.compute_snapshot(_healthy_universe(), "2026-11-06", 1)
    assert rs.append_snapshot(good) is True

    failed = rs.compute_snapshot(_stale_universe(), "2026-11-09", 0)
    assert failed["n_universe_ma200_eligible"] == 0
    assert rs.append_snapshot(failed) is False

    # A historical failed line (annotated) must be skipped as prior too.
    with rs.REGIME_SNAPSHOTS_PATH.open("a") as f:
        f.write(json.dumps({"scan_date": "2026-11-18", "n_universe_ma200_eligible": 0,
                            "median_rsi_14": None, "run_failed": True}) + "\n")

    nxt = rs.compute_snapshot(_healthy_universe(), "2026-11-09", 1)
    assert nxt["prev_scan_date"] == "2026-11-06"
    assert nxt["delta_median_rsi_prev"] is not None
    # Same scan_date as the failed run: the valid snapshot is not blocked.
    assert rs.append_snapshot(nxt) is True


# ── A5: data_date dedup ───────────────────────────────────────────────────────

def _opp(symbol: str):
    from analysis.reversal.reversal_scanner import ReversalOpportunity
    return ReversalOpportunity(
        symbol=symbol, name=symbol, asset_type="cedear", score=70.0, rsi_14=30.0,
        entry_price_ars=100.0, nearest_support=98.0, nearest_support_type="MA50",
        distance_to_support_pct=0.02, catalyst=["MA200 bounce/proximity"],
        volume_ratio=0.5, weekly_trend="neutral", invalidation_level_ars=96.53,
        invalidation_rationale="test",
    )


def test_same_data_date_rerun_does_not_duplicate(sandbox):
    from analysis.reversal.signal_registry import load_signals, record_signals
    from data.positions_log import load_positions

    # Saturday run and Monday pre-open run both read Friday's close.
    record_signals([_opp("AAA.BA")], "2026-11-21", data_date="2026-11-20")
    record_signals([_opp("AAA.BA"), _opp("BBB.BA")], "2026-11-23", data_date="2026-11-20")

    sigs = load_signals()
    assert [(s["scan_date"], s["symbol"]) for s in sigs] == [
        ("2026-11-21", "AAA.BA"), ("2026-11-23", "BBB.BA"),
    ]
    assert all(s["data_date"] == "2026-11-20" for s in sigs)
    assert sorted(p.symbol for p in load_positions()) == ["AAA.BA", "BBB.BA"]


def test_historical_records_without_data_date_do_not_block(sandbox):
    import analysis.reversal.signal_registry as sr
    from analysis.reversal.signal_registry import load_signals, record_signals

    sr.SIGNALS_PATH.parent.mkdir(parents=True, exist_ok=True)
    sr.SIGNALS_PATH.write_text(json.dumps({"scan_date": "2026-09-19", "symbol": "AAA.BA"}) + "\n")
    record_signals([_opp("AAA.BA")], "2026-09-22", data_date="2026-09-19")
    assert len(load_signals()) == 2


# ── A4 ────────────────────────────────────────────────────────────────────────

def test_tracking_files_list():
    assert set(rr._TRACKING_FILES) == {
        "data/reversal_tracking/signals.jsonl",
        "data/reversal_tracking/outcomes.jsonl",
        "data/reversal_tracking/near_misses.jsonl",
        "data/reversal_tracking/regime_snapshots.jsonl",
        "data/reversal_tracking/near_miss_outcomes.jsonl",
    }
    assert not any("positions_log" in p for p in rr._TRACKING_FILES)
