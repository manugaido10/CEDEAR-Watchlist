"""Tests for analysis/reversal/regime_snapshot.py.

Coverage:
  - compute_snapshot on a mixed universe: some below MA200, some above
  - Bundles with <200 bars are excluded from the MA200 metric but count in the total
  - median_rsi_14 computed over eligible bundles
  - prev_scan_date + delta_median_rsi_prev populated from the prior snapshot line
  - No prior snapshot → prev_scan_date and delta are null
  - n_opportunities_published=0 records normally (regime snapshots on empty scans)
  - append_snapshot idempotency: appending the same scan_date twice is a no-op
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from analysis.reversal import regime_snapshot as rs
from data.models import FetchStatus, PriceHistory, TickerBundle, TickerMetadata, AssetType


def _bundle(symbol: str, closes: list, status: FetchStatus = FetchStatus.OK) -> TickerBundle:
    df = pd.DataFrame(
        {"open": closes, "high": closes, "low": closes, "close": closes, "volume": [1] * len(closes)},
        index=pd.date_range("2025-01-01", periods=len(closes), freq="B"),
    )
    return TickerBundle(
        metadata=TickerMetadata(symbol_ars=symbol, name=symbol, asset_type=AssetType.CEDEAR),
        prices_ars=PriceHistory(symbol=symbol, data=df),
        ccl_series=None,
        mep_series=None,
        fundamentals=None,
        status=status,
    )


@pytest.fixture(autouse=True)
def _isolated_snapshot_file(tmp_path, monkeypatch):
    """Redirect REGIME_SNAPSHOTS_PATH to a tmp file for every test."""
    tmp_file = tmp_path / "regime_snapshots.jsonl"
    monkeypatch.setattr(rs, "REGIME_SNAPSHOTS_PATH", tmp_file)
    return tmp_file


# ── compute_snapshot ─────────────────────────────────────────────────────────

def test_compute_snapshot_mixed_universe():
    # A: 250 bars, last below MA200 → counts as below.
    # Build such that mean(closes[-200:]) > close[-1].
    closes_below = list(range(1, 200)) + [50.0] * 51  # last 51 bars flat at 50, MA200 dragged up
    bundle_a = _bundle("A.BA", closes_below)
    # B: 250 bars flat at 100 → close == MA200 → not below.
    bundle_b = _bundle("B.BA", [100.0] * 250)
    # C: 100 bars → excluded from MA200 metric, still counted in total + RSI.
    bundle_c = _bundle("C.BA", [100.0 + i * 0.5 for i in range(100)])
    # D: fetch error → excluded entirely.
    bundle_d = _bundle("D.BA", [100.0] * 250, status=FetchStatus.ERROR)

    snap = rs.compute_snapshot([bundle_a, bundle_b, bundle_c, bundle_d], "2026-09-12", n_opportunities_published=2)

    assert snap["scan_date"] == "2026-09-12"
    assert snap["n_universe_total"] == 4
    # MA200 eligible: A and B (both have ≥200 bars and OK). C too short; D errored.
    assert snap["n_universe_ma200_eligible"] == 2
    # A is below MA200 (last=50, MA200 dragged up by the rising series). B is not.
    assert snap["pct_below_ma200"] == pytest.approx(0.5, abs=1e-4)
    # median_rsi_14 exists over the 3 OK bundles with enough bars
    assert snap["median_rsi_14"] is not None
    assert snap["n_opportunities_published"] == 2


def test_compute_snapshot_zero_opportunities_still_records_regime():
    bundle = _bundle("A.BA", [100.0 + i for i in range(250)])
    snap = rs.compute_snapshot([bundle], "2026-09-12", n_opportunities_published=0)
    assert snap["n_opportunities_published"] == 0
    assert snap["median_rsi_14"] is not None


def test_compute_snapshot_without_prior_returns_null_delta():
    bundle = _bundle("A.BA", [100.0] * 250)
    snap = rs.compute_snapshot([bundle], "2026-09-12", n_opportunities_published=1)
    assert snap["prev_scan_date"] is None
    assert snap["delta_median_rsi_prev"] is None


def test_compute_snapshot_computes_delta_against_prior(_isolated_snapshot_file: Path):
    # Seed a prior snapshot with median_rsi_14=50 dated 2026-09-11.
    prior = {
        "scan_date": "2026-09-11",
        "prev_scan_date": None,
        "n_universe_total": 1,
        "n_universe_ma200_eligible": 1,
        "pct_below_ma200": 0.0,
        "median_rsi_14": 50.0,
        "delta_median_rsi_prev": None,
        "n_opportunities_published": 0,
    }
    _isolated_snapshot_file.write_text(json.dumps(prior) + "\n")

    bundle = _bundle("A.BA", [100.0 + i for i in range(250)])
    snap = rs.compute_snapshot([bundle], "2026-09-12", n_opportunities_published=1)

    assert snap["prev_scan_date"] == "2026-09-11"
    assert snap["delta_median_rsi_prev"] is not None
    # delta = new_median − 50
    assert snap["delta_median_rsi_prev"] == pytest.approx(round(snap["median_rsi_14"] - 50.0, 2), abs=1e-4)


# ── append_snapshot ──────────────────────────────────────────────────────────

def test_append_snapshot_idempotent(_isolated_snapshot_file: Path):
    snap = {
        "scan_date": "2026-09-12",
        "prev_scan_date": None,
        "n_universe_total": 1,
        "n_universe_ma200_eligible": 1,
        "pct_below_ma200": 0.5,
        "median_rsi_14": 47.0,
        "delta_median_rsi_prev": None,
        "n_opportunities_published": 3,
    }
    rs.append_snapshot(snap)
    rs.append_snapshot(snap)  # second call must be a no-op

    lines = _isolated_snapshot_file.read_text().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["scan_date"] == "2026-09-12"


def test_load_prior_snapshot_returns_last_line(_isolated_snapshot_file: Path):
    _isolated_snapshot_file.write_text(
        json.dumps({"scan_date": "2026-09-10", "median_rsi_14": 45.0}) + "\n"
        + json.dumps({"scan_date": "2026-09-11", "median_rsi_14": 48.0}) + "\n"
    )
    prior = rs.load_prior_snapshot()
    assert prior["scan_date"] == "2026-09-11"
    assert prior["median_rsi_14"] == 48.0
