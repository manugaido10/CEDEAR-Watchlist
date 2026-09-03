"""Tests for analysis/reversal/suppression.py.

All scenarios use synthetic outcomes lists + Position objects — no file I/O,
no positions_log.json access, no outcomes.jsonl access. Same dependency-
injection style as tests/test_reconciler.py and tests/test_pnl_calculator.py.

Coverage:
  Part A — cooldown:
    - in-cooldown window + price still below invalidation → not tradeable
    - in-cooldown window + price recovered above invalidation → tradeable
    - stop_hit outside window (16 business days) → tradeable
    - no prior stop_hit → tradeable
    - non-stop-hit outcome (target_5pct) → tradeable
    - .BA canonical matching across signal / outcome symbols
  Part B — open position:
    - open position blocks the signal
    - closed position does not block
    - different-ticker open position does not block
    - .BA canonical matching (log symbol AAPL.BA, signal AAPL.BA)
  Part C — sizing cap:
    - no capital passed → skipped
    - committed = 0 → not blocked
    - committed above 8% cap → hard block with reason
  Orchestration:
    - short-circuits on first suppression
    - all-tradeable path
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from analysis.reversal.suppression import (
    COOLDOWN_WINDOW_BUSINESS_DAYS,
    PER_TICKER_CAP_PCT,
    check_cooldown,
    check_open_position,
    check_sizing_cap,
    evaluate_suppressions,
)
from data.positions_log import Position


# ── Helpers ──────────────────────────────────────────────────────────────────

def _stop_hit(
    symbol: str,
    scan_date: str,
    invalidation: float,
    days_to_outcome: int = 3,
    entry: float = 100.0,
) -> dict:
    return {
        "scan_date": scan_date,
        "symbol": symbol,
        "outcome": "stop_hit",
        "invalidation_level_ars": invalidation,
        "entry_price_ars": entry,
        "days_to_outcome": days_to_outcome,
    }


def _target(symbol: str, scan_date: str, invalidation: float = 90.0) -> dict:
    return {
        "scan_date": scan_date,
        "symbol": symbol,
        "outcome": "target_5pct",
        "invalidation_level_ars": invalidation,
        "entry_price_ars": 100.0,
        "days_to_outcome": 5,
    }


def _open_pos(
    symbol: str,
    qty: float = 10,
    price: float = 1000.0,
    source: str = "reversal",
) -> Position:
    return Position(
        symbol=symbol,
        source=source,
        open_date="2026-01-10",
        open_price_ars=price,
        qty=qty,
        score_at_entry=7.5,
        invalidation_at_entry_ars=price * 0.95,
        status="open",
    )


def _closed_pos(symbol: str, qty: float = 10, price: float = 1000.0) -> Position:
    p = _open_pos(symbol, qty, price)
    p.status = "closed"
    p.close_date = "2026-02-01"
    p.close_price_ars = price * 1.05
    p.close_reason = "target"
    return p


# ─────────────────────────────────────────────────────────────────────────────
# Part A — cooldown
# ─────────────────────────────────────────────────────────────────────────────

class TestCooldown:
    def test_in_window_price_below_invalidation_blocks(self):
        # stop_hit signal from 2026-08-24, exit 3 calendar days later (Aug 27).
        # Scan on Sept 3 → 5 business days later → within 15bd window.
        outcomes = [_stop_hit("DECK.BA", scan_date="2026-08-24", invalidation=5399.01)]
        reason = check_cooldown("DECK.BA", "2026-09-03", entry_price_ars=5200.0, outcomes=outcomes)
        assert reason is not None
        assert "cuarentena" in reason.lower()
        assert "5,399.01" in reason
        assert "2026-08-27" in reason  # exit_date == scan_date + days_to_outcome

    def test_in_window_price_recovered_above_invalidation_allowed(self):
        outcomes = [_stop_hit("DECK.BA", scan_date="2026-08-24", invalidation=5000.0)]
        reason = check_cooldown("DECK.BA", "2026-09-03", entry_price_ars=5500.0, outcomes=outcomes)
        assert reason is None

    def test_outside_window_allowed(self):
        # Exit on 2026-08-01, scan on 2026-09-03 → ~23 business days later, outside 15bd.
        outcomes = [
            _stop_hit("BYMA", scan_date="2026-07-29", invalidation=500.0, days_to_outcome=3)
        ]
        reason = check_cooldown("BYMA", "2026-09-03", entry_price_ars=450.0, outcomes=outcomes)
        assert reason is None

    def test_no_prior_stop_hit_allowed(self):
        reason = check_cooldown("AAPL.BA", "2026-09-03", entry_price_ars=100.0, outcomes=[])
        assert reason is None

    def test_non_stop_outcome_ignored(self):
        # Only target_5pct → cooldown does not apply even if invalidation not reclaimed.
        outcomes = [_target("ADGO.BA", scan_date="2026-08-24")]
        reason = check_cooldown("ADGO.BA", "2026-09-03", entry_price_ars=50.0, outcomes=outcomes)
        assert reason is None

    def test_ba_canonical_matching(self):
        # Outcome recorded as "DECK", signal as "DECK.BA" → still same ticker.
        outcomes = [_stop_hit("DECK", scan_date="2026-08-24", invalidation=5399.01)]
        reason = check_cooldown("DECK.BA", "2026-09-03", entry_price_ars=5000.0, outcomes=outcomes)
        assert reason is not None

    def test_most_recent_stop_hit_wins(self):
        # Two stop_hits — the newer one governs the cooldown decision.
        outcomes = [
            _stop_hit("DECK.BA", scan_date="2026-07-20", invalidation=5500.0, days_to_outcome=2),
            _stop_hit("DECK.BA", scan_date="2026-08-24", invalidation=5000.0, days_to_outcome=3),
        ]
        # Price is above the newer invalidation (5000) but below the older one (5500).
        # Newer one governs → tradeable.
        reason = check_cooldown("DECK.BA", "2026-09-03", entry_price_ars=5200.0, outcomes=outcomes)
        assert reason is None

    def test_window_boundary_exactly_15bd_still_in_cooldown(self):
        # Exit exactly 15 business days before scan → boundary is inclusive (<= 15).
        today = date(2026, 9, 3)  # Thursday
        # Rewind 15 business days:
        import numpy as np
        exit_dt = date(2026, 8, 13)  # Aug 13 → 15 bd before Sept 3
        assert int(np.busday_count(np.datetime64(exit_dt, "D"), np.datetime64(today, "D"))) == 15

        # Build outcome: scan_date such that scan_date + days_to_outcome = exit_dt.
        outcomes = [{
            "scan_date": (exit_dt - timedelta(days=2)).isoformat(),
            "symbol": "TEST.BA",
            "outcome": "stop_hit",
            "invalidation_level_ars": 100.0,
            "days_to_outcome": 2,
        }]
        reason = check_cooldown("TEST.BA", today.isoformat(), entry_price_ars=90.0, outcomes=outcomes)
        assert reason is not None, "exactly-15-bd window should still be in cooldown"

    def test_future_stop_hit_ignored(self):
        # Defensive: outcomes with exit_dt >= scan_date must not trigger cooldown.
        outcomes = [_stop_hit("X.BA", scan_date="2026-09-10", invalidation=100.0, days_to_outcome=0)]
        reason = check_cooldown("X.BA", "2026-09-03", entry_price_ars=50.0, outcomes=outcomes)
        assert reason is None


# ─────────────────────────────────────────────────────────────────────────────
# Part B — open-position awareness
# ─────────────────────────────────────────────────────────────────────────────

class TestOpenPosition:
    def test_open_position_blocks(self):
        positions = [_open_pos("AAPL.BA", qty=10, price=5000.0, source="reversal")]
        reason = check_open_position("AAPL.BA", positions)
        assert reason is not None
        assert "AAPL.BA" in reason
        assert "source=reversal" in reason

    def test_closed_position_does_not_block(self):
        positions = [_closed_pos("AAPL.BA")]
        reason = check_open_position("AAPL.BA", positions)
        assert reason is None

    def test_different_symbol_does_not_block(self):
        positions = [_open_pos("MSFT.BA")]
        reason = check_open_position("AAPL.BA", positions)
        assert reason is None

    def test_ba_canonical_matches_argentine_bare(self):
        # Signal is "BYMA" (no .BA suffix, Argentine equity); log has "BYMA".
        positions = [_open_pos("BYMA", qty=29045)]
        reason = check_open_position("BYMA", positions)
        assert reason is not None

    def test_ba_canonical_matches_across_suffix_forms(self):
        # Log stores with .BA, signal comes bare → still same canonical ticker.
        positions = [_open_pos("AAPL.BA")]
        reason = check_open_position("AAPL", positions)
        assert reason is not None

    def test_empty_positions_list(self):
        assert check_open_position("AAPL.BA", []) is None


# ─────────────────────────────────────────────────────────────────────────────
# Part C — sizing cap
# ─────────────────────────────────────────────────────────────────────────────

class TestSizingCap:
    def test_no_capital_skips_check(self):
        # A None or zero total_capital_ars must not error and must not block.
        positions = [_open_pos("AAPL.BA", qty=10, price=1000.0)]
        assert check_sizing_cap("AAPL.BA", positions, total_capital_ars=0.0) is None

    def test_no_exposure_no_block(self):
        assert (
            check_sizing_cap("AAPL.BA", [], total_capital_ars=10_000_000.0)
            is None
        )

    def test_below_cap_no_block(self):
        # 5% committed vs 8% cap → headroom left, no block.
        positions = [_open_pos("AAPL.BA", qty=500, price=1000.0)]  # 500K
        assert check_sizing_cap(
            "AAPL.BA", positions, total_capital_ars=10_000_000.0
        ) is None

    def test_at_or_above_cap_blocks(self):
        # 8.5% committed → over cap → block.
        positions = [_open_pos("AAPL.BA", qty=850, price=1000.0)]  # 850K = 8.5%
        reason = check_sizing_cap(
            "AAPL.BA", positions, total_capital_ars=10_000_000.0
        )
        assert reason is not None
        assert "8%" in reason
        assert "8.5%" in reason

    def test_exactly_at_cap_blocks(self):
        # committed == cap → block (>= condition).
        positions = [_open_pos("AAPL.BA", qty=800, price=1000.0)]  # 800K = 8%
        reason = check_sizing_cap(
            "AAPL.BA", positions, total_capital_ars=10_000_000.0
        )
        assert reason is not None

    def test_additional_committed_stacks(self):
        # committed=5%, additional=4% → 9% total → block.
        positions = [_open_pos("AAPL.BA", qty=500, price=1000.0)]
        reason = check_sizing_cap(
            "AAPL.BA", positions,
            total_capital_ars=10_000_000.0,
            additional_committed_ars=400_000.0,
        )
        assert reason is not None


# ─────────────────────────────────────────────────────────────────────────────
# Orchestration
# ─────────────────────────────────────────────────────────────────────────────

class TestEvaluateSuppressions:
    def test_all_pass_returns_tradeable(self):
        result = evaluate_suppressions(
            symbol="AAPL.BA",
            scan_date="2026-09-03",
            entry_price_ars=5000.0,
            outcomes=[],
            positions=[],
            total_capital_ars=10_000_000.0,
        )
        assert result.tradeable is True
        assert result.reason is None

    def test_cooldown_short_circuits_open_position_check(self):
        # Both cooldown AND open position would suppress — cooldown wins because
        # it runs first. The reason string must be the cooldown message.
        outcomes = [_stop_hit("AAPL.BA", scan_date="2026-08-24", invalidation=6000.0)]
        positions = [_open_pos("AAPL.BA", qty=10, price=5000.0)]
        result = evaluate_suppressions(
            symbol="AAPL.BA",
            scan_date="2026-09-03",
            entry_price_ars=5000.0,
            outcomes=outcomes,
            positions=positions,
            total_capital_ars=10_000_000.0,
        )
        assert result.tradeable is False
        assert "cuarentena" in result.reason.lower()

    def test_open_position_short_circuits_sizing(self):
        # Sizing would also block (huge position), but Part B fires first.
        positions = [_open_pos("AAPL.BA", qty=100_000, price=1000.0)]
        result = evaluate_suppressions(
            symbol="AAPL.BA",
            scan_date="2026-09-03",
            entry_price_ars=5000.0,
            outcomes=[],
            positions=positions,
            total_capital_ars=10_000_000.0,
        )
        assert result.tradeable is False
        assert "posición abierta" in result.reason

    def test_no_capital_still_runs_cooldown_and_position(self):
        # total_capital_ars=None must not disable Parts A/B.
        outcomes = [_stop_hit("DECK.BA", scan_date="2026-08-24", invalidation=5399.01)]
        result = evaluate_suppressions(
            symbol="DECK.BA",
            scan_date="2026-09-03",
            entry_price_ars=5000.0,
            outcomes=outcomes,
            positions=[],
            total_capital_ars=None,
        )
        assert result.tradeable is False
        assert "cuarentena" in result.reason.lower()

    def test_defaults_match_documented_constants(self):
        assert COOLDOWN_WINDOW_BUSINESS_DAYS == 15
        assert PER_TICKER_CAP_PCT == pytest.approx(0.08)
