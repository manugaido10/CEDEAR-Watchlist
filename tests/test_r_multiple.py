"""Tests for analysis/reversal/r_multiple.py.

Coverage:
  - stop tocado exacto = −1R
  - target 2× riesgo = +2R
  - lateral con exit_at_deadline = fracción de R
  - invalidation == entry → invalid_denominator
  - invalidation > entry → invalid_denominator
  - entry o invalidation faltantes → missing_inputs
  - exit_price faltante → no_exit_data
"""

from __future__ import annotations

import pytest

from analysis.reversal.r_multiple import (
    SKIP_INVALID_DENOMINATOR,
    SKIP_MISSING_INPUTS,
    SKIP_NO_EXIT_DATA,
    compute_r_multiple,
)


def test_stop_hit_exactly_one_r_negative():
    r, reason = compute_r_multiple(entry_price_ars=100.0, invalidation_level_ars=95.0, exit_price_ars=95.0)
    assert r == pytest.approx(-1.0)
    assert reason is None


def test_target_two_r_positive():
    # entry=100, inv=95 → risk=5. exit=110 → gain=10 → R=+2.0
    r, reason = compute_r_multiple(entry_price_ars=100.0, invalidation_level_ars=95.0, exit_price_ars=110.0)
    assert r == pytest.approx(2.0)
    assert reason is None


def test_deep_stop_below_invalidation():
    # exit 93 with inv 95 and entry 100 → (93 − 100) / (100 − 95) = −1.4R
    r, reason = compute_r_multiple(entry_price_ars=100.0, invalidation_level_ars=95.0, exit_price_ars=93.0)
    assert r == pytest.approx(-1.4)
    assert reason is None


def test_lateral_partial_r_from_deadline_price():
    # A lateral outcome whose deadline close is 101: R = (101 − 100)/(100 − 95) = +0.2
    r, reason = compute_r_multiple(entry_price_ars=100.0, invalidation_level_ars=95.0, exit_price_ars=101.0)
    assert r == pytest.approx(0.2)
    assert reason is None


def test_invalidation_equal_to_entry_is_invalid_denominator():
    r, reason = compute_r_multiple(entry_price_ars=100.0, invalidation_level_ars=100.0, exit_price_ars=105.0)
    assert r is None
    assert reason == SKIP_INVALID_DENOMINATOR


def test_invalidation_above_entry_is_invalid_denominator():
    # Pre-fix Decision #20 artifact: TMUS/ADGO in outcomes.jsonl.
    r, reason = compute_r_multiple(entry_price_ars=100.0, invalidation_level_ars=105.0, exit_price_ars=98.0)
    assert r is None
    assert reason == SKIP_INVALID_DENOMINATOR


def test_missing_entry_is_missing_inputs():
    r, reason = compute_r_multiple(entry_price_ars=None, invalidation_level_ars=95.0, exit_price_ars=100.0)
    assert r is None
    assert reason == SKIP_MISSING_INPUTS


def test_missing_invalidation_is_missing_inputs():
    r, reason = compute_r_multiple(entry_price_ars=100.0, invalidation_level_ars=None, exit_price_ars=100.0)
    assert r is None
    assert reason == SKIP_MISSING_INPUTS


def test_missing_exit_is_no_exit_data():
    # A pending signal — entry and invalidation known, no exit yet.
    r, reason = compute_r_multiple(entry_price_ars=100.0, invalidation_level_ars=95.0, exit_price_ars=None)
    assert r is None
    assert reason == SKIP_NO_EXIT_DATA


def test_missing_all_prefers_missing_inputs_over_no_exit():
    # When everything is missing, the earlier check (missing_inputs) wins.
    r, reason = compute_r_multiple(entry_price_ars=None, invalidation_level_ars=None, exit_price_ars=None)
    assert r is None
    assert reason == SKIP_MISSING_INPUTS
