"""R-multiple normalization for reversal outcomes (Decision #31, Roadmap Fase A1).

R = (exit − entry) / (entry − invalidation)

A stop touched exactly is −1R regardless of whether the stop was 1.5% or 7%
below entry. A target that gains twice the initial risk is +2R. Normalizing
outcomes by their own initial risk makes trades of different stop distances
directly comparable — a prerequisite for meaningful EV aggregation.

Single source of truth: outcome_tracker, near_miss_outcomes and the backfill
script all call compute_r_multiple. Skip reasons are explicit — never a silent
null, never a misleading number.
"""

from __future__ import annotations

from typing import Optional, Tuple

# Skip-reason vocabulary (persisted verbatim to jsonl)
SKIP_MISSING_INPUTS = "missing_inputs"
SKIP_INVALID_DENOMINATOR = "invalid_denominator"
SKIP_NO_EXIT_DATA = "no_exit_data"
SKIP_LATERAL_NO_DEADLINE_PRICE = "lateral_no_deadline_price"


def compute_r_multiple(
    entry_price_ars: Optional[float],
    invalidation_level_ars: Optional[float],
    exit_price_ars: Optional[float],
) -> Tuple[Optional[float], Optional[str]]:
    """Return (r_multiple, skip_reason).

    - (float, None)              when computable.
    - (None, "missing_inputs")   entry or invalidation missing.
    - (None, "invalid_denominator") invalidation >= entry (denominator ≤ 0).
      Pre-fix artifacts (Decision #20) surface here — never coerced to a number.
    - (None, "no_exit_data")     exit price unknown (pending / unresolved).

    lateral_no_deadline_price is set by callers (the backfill script) when the
    price feed cannot deliver a close for scan_date + 20d; this function does
    not distinguish it from no_exit_data on its own.
    """
    if entry_price_ars is None or invalidation_level_ars is None:
        return None, SKIP_MISSING_INPUTS
    denom = float(entry_price_ars) - float(invalidation_level_ars)
    if denom <= 0:
        return None, SKIP_INVALID_DENOMINATOR
    if exit_price_ars is None:
        return None, SKIP_NO_EXIT_DATA
    r = (float(exit_price_ars) - float(entry_price_ars)) / denom
    return r, None
