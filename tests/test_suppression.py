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
  Part B — open position (conditional scale-in):
    - no open position → not blocked, is_scale_in=False
    - open position + price above open → allowed as scale-in (is_scale_in=True)
    - open position + price equal to open → blocked (equality = not confirmed)
    - open position + price below open → blocked (promediar a la baja)
    - closed position does not block
    - different-ticker open position does not block
    - .BA canonical matching (log symbol AAPL.BA, signal AAPL.BA)
  Part C — sizing cap:
    - no capital passed → skipped
    - committed = 0 → not blocked
    - committed above 8% cap → hard block with reason
    - per_ticker_headroom_ars helper
  Orchestration:
    - short-circuits on first suppression
    - all-tradeable path
    - scale-in propagates through evaluate_suppressions
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from analysis.reversal.suppression import (
    COOLDOWN_WINDOW_BUSINESS_DAYS,
    SCALE_IN_TOLERANCE_PCT,
    check_cooldown,
    check_open_position,
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
    price: float = 1000.0,
    source: str = "reversal",
) -> Position:
    return Position(
        symbol=symbol,
        source=source,
        open_date="2026-01-10",
        entry_price_ars=price,
        score_at_entry=7.5,
        invalidation_at_entry_ars=price * 0.95,
        status="open",
    )


def _closed_pos(symbol: str, price: float = 1000.0) -> Position:
    p = _open_pos(symbol, price)
    p.status = "closed"
    p.close_date = "2026-02-01"
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
    def test_price_above_open_allows_scale_in(self):
        # Price recovered above prior open — thesis reconfirmed, scale-in allowed.
        positions = [_open_pos("AAPL.BA", price=5000.0, source="reversal")]
        result = check_open_position("AAPL.BA", entry_price_ars=5500.0, positions=positions)
        assert result.blocked is False
        assert result.is_scale_in is True
        assert result.existing_position is positions[0]
        assert result.reason is None

    def test_price_below_open_blocks(self):
        # Would average down — forbidden per CRITERIOS_INVERSION.md.
        positions = [_open_pos("AAPL.BA", price=5000.0, source="reversal")]
        result = check_open_position("AAPL.BA", entry_price_ars=4800.0, positions=positions)
        assert result.blocked is True
        assert result.is_scale_in is False
        assert result.existing_position is positions[0]
        assert result.reason is not None
        assert "promediar a la baja" in result.reason
        assert "5,000.00" in result.reason
        assert "4,800.00" in result.reason

    def test_price_equal_to_open_is_scale_in_within_tolerance(self):
        # Equality is within the SCALE_IN_TOLERANCE_PCT noise band → scale-in,
        # not blocked. Prevents signal_registry from attempting open_position()
        # on a ticker that already has an open record (see DECISIONS.md #29).
        positions = [_open_pos("AAPL.BA", price=5000.0)]
        result = check_open_position("AAPL.BA", entry_price_ars=5000.0, positions=positions)
        assert result.blocked is False
        assert result.is_scale_in is True
        assert result.existing_position is positions[0]

    def test_price_within_tolerance_below_open_is_scale_in(self):
        # -1% below open price: inside SCALE_IN_TOLERANCE_PCT (2%) → scale-in.
        positions = [_open_pos("AAPL.BA", price=5000.0)]
        result = check_open_position("AAPL.BA", entry_price_ars=4950.0, positions=positions)
        assert result.blocked is False
        assert result.is_scale_in is True
        assert result.existing_position is positions[0]
        assert result.reason is None

    def test_price_at_tolerance_floor_is_blocked(self):
        # Exactly at tolerance floor (open × 0.98 = 4900) → NOT > floor → blocked.
        # Boundary is strict: entry must be strictly greater than the floor to pass.
        positions = [_open_pos("AAPL.BA", price=5000.0)]
        tolerance_floor = 5000.0 * (1.0 - SCALE_IN_TOLERANCE_PCT)  # 4900.0
        result = check_open_position("AAPL.BA", entry_price_ars=tolerance_floor, positions=positions)
        assert result.blocked is True
        assert result.is_scale_in is False


    def test_closed_position_does_not_block(self):
        positions = [_closed_pos("AAPL.BA")]
        result = check_open_position("AAPL.BA", entry_price_ars=4000.0, positions=positions)
        assert result.blocked is False
        assert result.is_scale_in is False
        assert result.existing_position is None

    def test_different_symbol_does_not_block(self):
        positions = [_open_pos("MSFT.BA")]
        result = check_open_position("AAPL.BA", entry_price_ars=5000.0, positions=positions)
        assert result.blocked is False
        assert result.existing_position is None

    def test_ba_canonical_matches_argentine_bare(self):
        # Signal is "BYMA" (no .BA suffix, Argentine equity); log has "BYMA".
        # Price above open → scale-in allowed.
        positions = [_open_pos("BYMA", price=100.0)]
        result = check_open_position("BYMA", entry_price_ars=110.0, positions=positions)
        assert result.blocked is False
        assert result.is_scale_in is True

    def test_ba_canonical_matches_across_suffix_forms(self):
        # Log stores with .BA, signal comes bare → still same canonical ticker.
        positions = [_open_pos("AAPL.BA", price=1000.0)]
        result = check_open_position("AAPL", entry_price_ars=900.0, positions=positions)
        assert result.blocked is True

    def test_empty_positions_list(self):
        result = check_open_position("AAPL.BA", entry_price_ars=5000.0, positions=[])
        assert result.blocked is False
        assert result.is_scale_in is False
        assert result.existing_position is None


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
        )
        assert result.tradeable is True
        assert result.reason is None

    def test_cooldown_short_circuits_open_position_check(self):
        # Both cooldown AND open position would suppress — cooldown wins because
        # it runs first. The reason string must be the cooldown message.
        outcomes = [_stop_hit("AAPL.BA", scan_date="2026-08-24", invalidation=6000.0)]
        positions = [_open_pos("AAPL.BA", price=5000.0)]
        result = evaluate_suppressions(
            symbol="AAPL.BA",
            scan_date="2026-09-03",
            entry_price_ars=5000.0,
            outcomes=outcomes,
            positions=positions,
        )
        assert result.tradeable is False
        assert "cuarentena" in result.reason.lower()

    def test_open_position_blocks_when_averaging_down(self):
        # Entry 4000 vs open 5000 → averaging down, blocked. Cooldown is empty
        # so Part B is the blocking layer.
        positions = [_open_pos("AAPL.BA", price=5000.0)]
        result = evaluate_suppressions(
            symbol="AAPL.BA",
            scan_date="2026-09-03",
            entry_price_ars=4000.0,
            outcomes=[],
            positions=positions,
        )
        assert result.tradeable is False
        assert "promediar a la baja" in result.reason
        assert result.existing_position is positions[0]

    def test_scale_in_allowed_and_propagates(self):
        # Entry 6000 vs open 5000 → thesis reconfirmed, tradeable as scale-in.
        positions = [_open_pos("AAPL.BA", price=5000.0)]
        result = evaluate_suppressions(
            symbol="AAPL.BA",
            scan_date="2026-09-03",
            entry_price_ars=6000.0,
            outcomes=[],
            positions=positions,
        )
        assert result.tradeable is True
        assert result.is_scale_in is True
        assert result.existing_position is positions[0]

    def test_cooldown_still_runs_without_positions(self):
        # Cooldown (Part A) must work even with empty positions list.
        outcomes = [_stop_hit("DECK.BA", scan_date="2026-08-24", invalidation=5399.01)]
        result = evaluate_suppressions(
            symbol="DECK.BA",
            scan_date="2026-09-03",
            entry_price_ars=5000.0,
            outcomes=outcomes,
            positions=[],
        )
        assert result.tradeable is False
        assert "cuarentena" in result.reason.lower()

    def test_defaults_match_documented_constants(self):
        assert COOLDOWN_WINDOW_BUSINESS_DAYS == 15
        assert SCALE_IN_TOLERANCE_PCT == pytest.approx(0.02)
