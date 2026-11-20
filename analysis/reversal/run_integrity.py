"""Run-integrity checks for the reversal scanner (Decision #35).

Pure functions over the fetched bundles — no I/O, no network. Used by
scripts/run_reversals.py before scanning, and by scan_reversals to stamp
``data_date`` on every tracking record.

- ``compute_data_date``: date of the last bar actually used by the scan
  (mode across OK/PARTIAL bundles). Since Decision #30 the scan runs
  pre-open, so data_date is normally scan_date's previous trading day.
- ``assess_fetch_health``: fraction of the non-excluded universe that came
  back usable (OK/PARTIAL). Tickers in yfinance_exclusions are MISSING by
  design and are left out of the denominator.
- ``bundles_with_bar_on_or_after``: bundles whose last bar is dated
  on or after a given day — used to reject intraday snapshots (bar dated today ART).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date
from typing import Callable, List, Optional

from data.models import FetchStatus, TickerBundle

_USABLE_STATUSES = (FetchStatus.OK, FetchStatus.PARTIAL)
# Statuses the scanner actually reads prices from (it skips MISSING/ERROR).
_USED_STATUSES = (FetchStatus.OK, FetchStatus.PARTIAL, FetchStatus.STALE)


def _has_prices(bundle: TickerBundle) -> bool:
    return (
        bundle.prices_ars is not None
        and bundle.prices_ars.data is not None
        and not bundle.prices_ars.data.empty
    )


def _last_bar_date(bundle: TickerBundle) -> date:
    return bundle.prices_ars.data.sort_index().index[-1].date()


def compute_data_date(bundles: List[TickerBundle]) -> Optional[date]:
    """Mode of the last-bar date across OK/PARTIAL bundles; None if there are none.

    Ties resolve to the most recent date.
    """
    counts = Counter(
        _last_bar_date(b)
        for b in bundles
        if b.status in _USABLE_STATUSES and _has_prices(b)
    )
    if not counts:
        return None
    top = max(counts.values())
    return max(d for d, c in counts.items() if c == top)


def bundles_with_bar_on_or_after(bundles: List[TickerBundle], day: date) -> List[str]:
    """Symbols of used bundles (OK/PARTIAL/STALE) whose last bar is dated ``day`` or later."""
    return [
        b.metadata.symbol_ars
        for b in bundles
        if b.status in _USED_STATUSES and _has_prices(b) and _last_bar_date(b) >= day
    ]


@dataclass(frozen=True)
class FetchHealth:
    n_total: int
    n_excluded_by_design: int
    n_expected: int          # n_total - n_excluded_by_design
    n_usable: int            # OK + PARTIAL among expected
    usable_ratio: float      # n_usable / n_expected (0.0 when n_expected == 0)

    def is_healthy(self, min_ratio: float) -> bool:
        return self.n_expected > 0 and self.usable_ratio >= min_ratio


def assess_fetch_health(
    bundles: List[TickerBundle],
    is_excluded: Callable[[str], bool],
) -> FetchHealth:
    """Measure usable coverage against the universe that is expected to fetch."""
    expected = [b for b in bundles if not is_excluded(b.metadata.symbol_ars)]
    n_usable = sum(1 for b in expected if b.status in _USABLE_STATUSES)
    n_expected = len(expected)
    return FetchHealth(
        n_total=len(bundles),
        n_excluded_by_design=len(bundles) - n_expected,
        n_expected=n_expected,
        n_usable=n_usable,
        usable_ratio=(n_usable / n_expected) if n_expected else 0.0,
    )
