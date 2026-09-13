"""Parity tests for analysis/query.py.

Coverage:
  - is_safe() SQL macro matches _is_safe() Python function for all known
    staleness values (NULL, 'safe', 'uncertain', 'confirmed_stale', 'likely_stale').
  - nm_dup_keys view marks the same (scan_date, symbol) pairs as
    _is_near_miss_exposure_duplicate() — verified per-gate and in total.
"""

from __future__ import annotations

import pytest

from analysis.query import get_connection


@pytest.fixture(scope="module")
def conn():
    return get_connection()


# ── is_safe() parity ──────────────────────────────────────────────────────────

_IS_SAFE_CASES = [
    (None,               True,  "absent field (pre-instrumentation) → safe by construction"),
    ("safe",             True,  "explicitly safe"),
    ("uncertain",        False, "problematic — see Decision #27"),
    ("confirmed_stale",  False, "explicitly stale — see Decision #30"),
    ("likely_stale",     False, "hypothetical future value must also fail"),
]


@pytest.mark.parametrize("value,expected,label", _IS_SAFE_CASES)
def test_is_safe_sql_matches_python(conn, value, expected, label):
    """SQL macro is_safe() must return the same boolean as Python _is_safe()."""
    from analysis.reversal.near_miss_outcomes import _is_safe

    py_result = _is_safe({"price_staleness_risk": value})
    assert py_result == expected, f"Python baseline broken for {value!r}: {label}"

    sql_literal = "NULL" if value is None else f"'{value}'"
    sql_result = conn.execute(f"SELECT is_safe({sql_literal})").fetchone()[0]

    assert sql_result == expected, (
        f"SQL is_safe({value!r}) = {sql_result}, expected {expected}: {label}"
    )
    assert py_result == sql_result, (
        f"Parity drift for {value!r}: Python={py_result}, SQL={sql_result}"
    )


def test_is_safe_absent_key_equals_null_value(conn):
    """Dict without the key and dict with key=None must give the same result."""
    from analysis.reversal.near_miss_outcomes import _is_safe

    result_absent = _is_safe({})
    result_null   = _is_safe({"price_staleness_risk": None})
    assert result_absent == result_null == True


# ── nm_dup_keys parity ────────────────────────────────────────────────────────

def test_nm_dup_total_resolvable_matches_python(conn):
    """Total deduped resolvable count from nm_dup_keys must match Python.

    Python reference: _compute_gate_groups(filter_safe_only=True).
    nm_dup_keys is built with is_safe() on both sides to mirror Python's
    filter-before-dedup order (unsafe priors must not suppress safe entries).
    """
    from analysis.reversal.near_miss_outcomes import _compute_gate_groups, _gate_stats

    _, gate_groups, _ = _compute_gate_groups(filter_safe_only=True)
    py_total = sum(
        _gate_stats(grp)[3]  # index 3 = n_resolvable
        for grp in gate_groups.values()
    )

    sql_total = conn.execute("""
        SELECT COUNT(*)
        FROM near_miss_outcomes nmo
        JOIN near_misses nm USING (scan_date, symbol)
        WHERE nmo.outcome NOT IN ('unresolved_no_data', 'pending')
          AND nmo.r_multiple_skip_reason IS NULL
          AND is_safe(nm.price_staleness_risk)
          AND NOT EXISTS (
              SELECT 1 FROM nm_dup_keys d
              WHERE d.scan_date = nmo.scan_date AND d.symbol = nmo.symbol
          )
    """).fetchone()[0]

    assert sql_total == py_total, (
        f"Total deduped resolvable: SQL={sql_total}, Python={py_total}"
    )


@pytest.mark.parametrize("gate", ["rsi_out_of_range", "no_catalyst"])
def test_nm_dup_per_gate_resolvable_matches_python(conn, gate):
    """Per-gate deduped n_resolvable must match Python for calibration gates.

    Python reference: _compute_gate_groups(filter_safe_only=True) for the
    safe corpus — the primary Fase B analysis corpus.
    """
    from analysis.reversal.near_miss_outcomes import _compute_gate_groups, _gate_stats

    _, gate_groups, _ = _compute_gate_groups(filter_safe_only=True)
    _, _, _, py_resolvable, _ = _gate_stats(gate_groups.get(gate, []))

    sql_resolvable = conn.execute("""
        SELECT COUNT(*)
        FROM near_miss_outcomes nmo
        JOIN near_misses nm USING (scan_date, symbol)
        WHERE nmo.outcome NOT IN ('unresolved_no_data', 'pending')
          AND nmo.r_multiple_skip_reason IS NULL
          AND is_safe(nm.price_staleness_risk)
          AND list_contains(nm.failed_criteria, $gate)
          AND NOT EXISTS (
              SELECT 1 FROM nm_dup_keys d
              WHERE d.scan_date = nm.scan_date AND d.symbol = nm.symbol
          )
    """, {"gate": gate}).fetchone()[0]

    assert sql_resolvable == py_resolvable, (
        f"Gate '{gate}': SQL deduped n={sql_resolvable}, Python n={py_resolvable}"
    )
