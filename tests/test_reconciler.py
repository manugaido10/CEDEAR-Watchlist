"""Tests for data/reconciler.py.

All scenarios use synthetic ParseResult + list[Position] — no CSV parsing,
no file I/O, no positions_log.json access.

Buckets exercised:
  1. matched — clean qty + cost match
  2. matched — qty match but cost mismatch (>1% diff)
  3. qty_mismatch — BYMA-style large delta
  4. in_csv_not_in_log — manual buy not in log
  5. in_log_not_in_csv (csv_status="closed") — position found in closed_positions
  6. in_log_not_in_csv (csv_status="absent") — position absent from CSV entirely
  7. skipped — parser warnings are surfaced
  8. Symbol normalisation — log 'AAPL.BA' matches CSV 'AAPL'
"""

from __future__ import annotations

import pytest

from data.cocos_csv_parser import DerivedPosition, ParseResult
from data.positions_log import Position
from data.reconciler import (
    InCsvNotInLog,
    InLogNotInCsv,
    MatchedPosition,
    QtyMismatch,
    ReconciliationReport,
    SkippedEntry,
    reconcile,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _derived(
    ticker: str,
    net_qty: float,
    avg_cost_ars: float = 1000.0,
    fully_closed: bool = False,
) -> DerivedPosition:
    return DerivedPosition(
        ticker=ticker,
        net_qty=net_qty,
        avg_cost_ars=avg_cost_ars,
        total_cost_ars=round(avg_cost_ars * net_qty, 4),
        first_buy_date="2026-01-10",
        last_trade_date="2026-06-01",
        fully_closed=fully_closed,
    )


def _logged(
    symbol: str,
    qty: float,
    open_price_ars: float = 1000.0,
    status: str = "open",
    source: str = "momentum",
    score: float = 7.5,
    invalidation: float = 950.0,
) -> Position:
    return Position(
        symbol=symbol,
        source=source,
        open_date="2026-01-10",
        open_price_ars=open_price_ars,
        qty=qty,
        score_at_entry=score,
        invalidation_at_entry_ars=invalidation,
        status=status,
    )


def _parse_result(
    open_pos: list[DerivedPosition] | None = None,
    closed_pos: list[DerivedPosition] | None = None,
    warnings: list[str] | None = None,
) -> ParseResult:
    return ParseResult(
        open_positions=open_pos or [],
        closed_positions=closed_pos or [],
        skipped_usd_no_mep=[],
        warnings=warnings or [],
    )


# ---------------------------------------------------------------------------
# Bucket 1 — clean match (qty and cost both agree)
# ---------------------------------------------------------------------------

def test_matched_clean():
    csv = _derived("AAPL", net_qty=100, avg_cost_ars=5000.0)
    log = _logged("AAPL.BA", qty=100, open_price_ars=5000.0)

    report = reconcile(_parse_result([csv]), [log])

    assert len(report.matched) == 1
    assert report.qty_mismatch == []
    assert report.in_csv_not_in_log == []
    assert report.in_log_not_in_csv == []

    m: MatchedPosition = report.matched[0]
    assert m.ticker == "AAPL"
    assert m.log_symbol == "AAPL.BA"
    assert m.csv_qty == 100
    assert m.log_qty == 100
    assert not m.cost_mismatch
    # Log-only fields must be preserved.
    assert m.log_fields.source == "momentum"
    assert m.log_fields.score_at_entry == 7.5
    assert m.log_fields.invalidation_at_entry_ars == 950.0


# ---------------------------------------------------------------------------
# Bucket 2 — qty match, cost mismatch
# ---------------------------------------------------------------------------

def test_matched_cost_mismatch():
    # avg_cost from CSV is 5100, log has 5000 → diff = 2 % > 1 % threshold.
    csv = _derived("DECK", net_qty=50, avg_cost_ars=5100.0)
    log = _logged("DECK.BA", qty=50, open_price_ars=5000.0)

    report = reconcile(_parse_result([csv]), [log])

    assert len(report.matched) == 1
    m: MatchedPosition = report.matched[0]
    assert m.cost_mismatch is True
    assert m.csv_avg_cost_ars == 5100.0
    assert m.log_open_price_ars == 5000.0


def test_matched_no_cost_mismatch_within_tolerance():
    # diff = 0.5 % < 1 % → no mismatch.
    csv = _derived("LRCX", net_qty=10, avg_cost_ars=1005.0)
    log = _logged("LRCX.BA", qty=10, open_price_ars=1000.0)

    report = reconcile(_parse_result([csv]), [log])

    assert report.matched[0].cost_mismatch is False


# ---------------------------------------------------------------------------
# Bucket 3 — qty mismatch (BYMA-style large delta)
# ---------------------------------------------------------------------------

def test_qty_mismatch_byma_style():
    csv = _derived("BYMA", net_qty=29_045, avg_cost_ars=750.0)
    log = _logged("BYMA", qty=100, open_price_ars=700.0)

    report = reconcile(_parse_result([csv]), [log])

    assert report.matched == []
    assert len(report.qty_mismatch) == 1

    q: QtyMismatch = report.qty_mismatch[0]
    assert q.ticker == "BYMA"
    assert q.csv_qty == 29_045
    assert q.log_qty == 100
    assert q.delta == pytest.approx(28_945)
    # Log-only fields preserved.
    assert q.log_fields.source == "momentum"
    assert q.log_fields.invalidation_at_entry_ars == 950.0


def test_qty_mismatch_boundary_exactly_one():
    # delta of exactly 1.0 → mismatch (not matched).
    csv = _derived("SEMI", net_qty=101, avg_cost_ars=200.0)
    log = _logged("SEMI", qty=100, open_price_ars=200.0)

    report = reconcile(_parse_result([csv]), [log])

    assert len(report.qty_mismatch) == 1
    assert report.matched == []


def test_qty_match_boundary_below_one():
    # delta of 0.5 → matched (within tolerance).
    csv = _derived("SEMI", net_qty=100.5, avg_cost_ars=200.0)
    log = _logged("SEMI", qty=100, open_price_ars=200.0)

    report = reconcile(_parse_result([csv]), [log])

    assert len(report.matched) == 1
    assert report.qty_mismatch == []


# ---------------------------------------------------------------------------
# Bucket 4 — in_csv_not_in_log (manual buy)
# ---------------------------------------------------------------------------

def test_in_csv_not_in_log():
    csv = _derived("GLOB", net_qty=200, avg_cost_ars=3000.0)

    report = reconcile(_parse_result([csv]), [])

    assert len(report.in_csv_not_in_log) == 1
    assert report.matched == []

    entry: InCsvNotInLog = report.in_csv_not_in_log[0]
    assert entry.ticker == "GLOB"
    assert entry.csv_qty == 200
    assert entry.csv_avg_cost_ars == 3000.0
    assert entry.note == "needs manual entry criteria"


# ---------------------------------------------------------------------------
# Bucket 5 — in_log_not_in_csv, csv_status="closed"
# ---------------------------------------------------------------------------

def test_in_log_not_in_csv_closed():
    # Log has MORI open; CSV shows MORI as fully closed.
    closed_csv = _derived("MORI", net_qty=0, fully_closed=True)
    log = _logged("MORI.BA", qty=50, open_price_ars=1200.0, source="reversal", score=6.0, invalidation=1100.0)

    report = reconcile(
        _parse_result(open_pos=[], closed_pos=[closed_csv]),
        [log],
    )

    assert len(report.in_log_not_in_csv) == 1
    assert report.matched == []

    entry: InLogNotInCsv = report.in_log_not_in_csv[0]
    assert entry.ticker == "MORI"
    assert entry.log_symbol == "MORI.BA"
    assert entry.csv_status == "closed"
    # Log-only fields preserved.
    assert entry.log_fields.source == "reversal"
    assert entry.log_fields.score_at_entry == 6.0
    assert entry.log_fields.invalidation_at_entry_ars == 1100.0


# ---------------------------------------------------------------------------
# Bucket 6 — in_log_not_in_csv, csv_status="absent" (pre-CSV-window)
# ---------------------------------------------------------------------------

def test_in_log_not_in_csv_absent():
    # Log has ALUA open; ticker appears nowhere in the CSV.
    log = _logged("ALUA.BA", qty=300, open_price_ars=500.0, source="momentum")

    report = reconcile(_parse_result(), [log])

    assert len(report.in_log_not_in_csv) == 1
    entry: InLogNotInCsv = report.in_log_not_in_csv[0]
    assert entry.ticker == "ALUA"
    assert entry.csv_status == "absent"


# ---------------------------------------------------------------------------
# Bucket 7 — skipped (parser warnings surfaced)
# ---------------------------------------------------------------------------

def test_skipped_warnings_surfaced():
    warn = "TXAR: sells exceed known buys (net_qty=-5.0000); cost basis incomplete — likely pre-CSV buys; skipping"
    report = reconcile(_parse_result(warnings=[warn]), [])

    assert len(report.skipped) == 1
    s: SkippedEntry = report.skipped[0]
    assert s.ticker == "TXAR"
    assert "sells exceed" in s.warning


# ---------------------------------------------------------------------------
# Bucket 8 — symbol normalisation (.BA stripped correctly)
# ---------------------------------------------------------------------------

def test_normalisation_ba_suffix():
    # CSV ticker is bare 'AAPL'; log symbol is 'AAPL.BA' → should match.
    csv = _derived("AAPL", net_qty=10, avg_cost_ars=8000.0)
    log = _logged("AAPL.BA", qty=10, open_price_ars=8000.0)

    report = reconcile(_parse_result([csv]), [log])

    assert len(report.matched) == 1
    assert report.in_csv_not_in_log == []
    assert report.in_log_not_in_csv == []


def test_normalisation_no_suffix_argentine_equity():
    # Both CSV and log use bare ticker (e.g. BYMA, SEMI) — no suffix in either.
    csv = _derived("SEMI", net_qty=500, avg_cost_ars=100.0)
    log = _logged("SEMI", qty=500, open_price_ars=100.0)

    report = reconcile(_parse_result([csv]), [log])

    assert len(report.matched) == 1


# ---------------------------------------------------------------------------
# Mixed scenario — all buckets in one call
# ---------------------------------------------------------------------------

def test_all_buckets_combined():
    open_positions = [
        _derived("AAPL", net_qty=10, avg_cost_ars=5000.0),   # matched
        _derived("BYMA", net_qty=29_045, avg_cost_ars=750.0),# qty mismatch
        _derived("GLOB", net_qty=200, avg_cost_ars=3000.0),  # in_csv_not_in_log
    ]
    closed_positions = [
        _derived("MORI", net_qty=0, fully_closed=True),       # provides "closed" signal
    ]
    parse_result = ParseResult(
        open_positions=open_positions,
        closed_positions=closed_positions,
        skipped_usd_no_mep=[],
        warnings=["TXAR: sells exceed known buys (net_qty=-5.0000); cost basis incomplete — likely pre-CSV buys; skipping"],
    )
    logged_positions = [
        _logged("AAPL.BA", qty=10, open_price_ars=5000.0),   # matched
        _logged("BYMA",    qty=100, open_price_ars=700.0),   # qty mismatch
        _logged("MORI.BA", qty=50,  open_price_ars=1200.0),  # in_log_not_in_csv → closed
        _logged("ALUA.BA", qty=300, open_price_ars=500.0),   # in_log_not_in_csv → absent
    ]

    report = reconcile(parse_result, logged_positions)

    assert len(report.matched) == 1
    assert report.matched[0].ticker == "AAPL"

    assert len(report.qty_mismatch) == 1
    assert report.qty_mismatch[0].ticker == "BYMA"

    assert len(report.in_csv_not_in_log) == 1
    assert report.in_csv_not_in_log[0].ticker == "GLOB"

    assert len(report.in_log_not_in_csv) == 2
    statuses = {e.ticker: e.csv_status for e in report.in_log_not_in_csv}
    assert statuses["MORI"] == "closed"
    assert statuses["ALUA"] == "absent"

    assert len(report.skipped) == 1
    assert "TXAR" in report.skipped[0].ticker


# ---------------------------------------------------------------------------
# Closed log positions are ignored
# ---------------------------------------------------------------------------

def test_closed_log_positions_ignored():
    # A closed log position should not appear in any diff bucket.
    closed_log = _logged("AAPL.BA", qty=10, status="closed")
    report = reconcile(_parse_result(), [closed_log])

    assert report.matched == []
    assert report.qty_mismatch == []
    assert report.in_csv_not_in_log == []
    assert report.in_log_not_in_csv == []
