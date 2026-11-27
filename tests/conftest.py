"""Suite-wide guard: no test may reach the network through the ex-dividend check.

``analysis.reversal.reversal_scanner.check_ex_dividend`` calls yfinance. Tests
that exercise it on purpose (tests/test_dividends.py) inject a fetcher or patch
it themselves; everything else gets an empty, offline result.
"""
from __future__ import annotations

import pytest

from data.dividends import ExDividendResult


@pytest.fixture(autouse=True)
def _offline_ex_dividend(monkeypatch):
    monkeypatch.setattr(
        "analysis.reversal.reversal_scanner.check_ex_dividend",
        lambda symbol_underlying, *a, **k: ExDividendResult(),
    )


# ── Tracking-data isolation ──────────────────────────────────────────────────
# The tracking modules default to relative paths under data/reversal_tracking/.
# Without redirection, any test that calls them without its own sandbox writes
# into the real corpus. Every path is pointed at tmp_path, and a session-level
# guard fails the run if the real directory changes anyway.

import hashlib
from pathlib import Path

_REAL_TRACKING_DIR = Path(__file__).resolve().parent.parent / "data" / "reversal_tracking"

# (module, attribute, file name)
_TRACKING_PATHS = [
    ("analysis.reversal.outcome_tracker", "OUTCOMES_PATH", "outcomes.jsonl"),
    ("analysis.reversal.outcome_tracker", "OUTCOMES_SUPPRESSED_PATH", "outcomes_suppressed.jsonl"),
    ("analysis.reversal.outcomes_v2", "OUTCOMES_V2_PATH", "outcomes_v2.jsonl"),
    ("analysis.reversal.outcomes_v2", "OUTCOMES_V2_SUPPRESSED_PATH", "outcomes_v2_suppressed.jsonl"),
    ("analysis.reversal.signal_registry", "SIGNALS_PATH", "signals.jsonl"),
    ("analysis.reversal.near_miss_tracker", "NEAR_MISSES_PATH", "near_misses.jsonl"),
    ("analysis.reversal.near_miss_outcomes", "NEAR_MISS_OUTCOMES_PATH", "near_miss_outcomes.jsonl"),
    ("analysis.reversal.regime_snapshot", "REGIME_SNAPSHOTS_PATH", "regime_snapshots.jsonl"),
]


def _fingerprint(root: Path) -> dict[str, str]:
    if not root.exists():
        return {}
    return {
        str(p.relative_to(root)): hashlib.md5(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*")) if p.is_file()
    }


@pytest.fixture(autouse=True)
def _isolate_tracking_paths(request, monkeypatch, tmp_path):
    """Redirect every reversal-tracking file to tmp_path (restored per test).

    Read-only tests that must see the real corpus (e.g. SQL-vs-Python parity in
    test_query.py) opt out with ``pytestmark = pytest.mark.real_tracking_readonly``;
    the session guard still fails the run if they write.
    """
    import importlib

    if request.node.get_closest_marker("real_tracking_readonly"):
        return

    base = tmp_path / "_tracking_default"
    for mod_name, attr, fname in _TRACKING_PATHS:
        mod = importlib.import_module(mod_name)
        monkeypatch.setattr(mod, attr, base / fname)


@pytest.fixture(autouse=True, scope="session")
def _guard_real_tracking_dir():
    """Fail the session if any test modified data/reversal_tracking/."""
    before = _fingerprint(_REAL_TRACKING_DIR)
    yield
    after = _fingerprint(_REAL_TRACKING_DIR)
    if before != after:
        changed = sorted(k for k in before.keys() | after.keys() if before.get(k) != after.get(k))
        pytest.fail(
            "Test suite modified the real data/reversal_tracking/: " + ", ".join(changed),
            pytrace=False,
        )


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "real_tracking_readonly: reads the real data/reversal_tracking/ (never writes)",
    )
