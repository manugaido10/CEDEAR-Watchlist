"""NYSE holiday calendar (fixed list) — used to discount sessions with no US trading.

Fixed list instead of ``exchange_calendars`` (decision P2, 2026-11-27): ~10 dates a
year do not justify a heavy dependency, and a literal list is auditable. The list
must be extended every year; ``LAST_COVERED_YEAR`` + a test make a stale list loud.
Dates outside the covered range are treated as open (and logged once).
"""
from __future__ import annotations

import logging
from datetime import date

logger = logging.getLogger(__name__)

FIRST_COVERED_YEAR = 2025
LAST_COVERED_YEAR = 2027

NYSE_CLOSED_DATES = frozenset(
    date.fromisoformat(s)
    for s in (
        # 2025 (01-09: national day of mourning, President Carter)
        "2025-01-01", "2025-01-09", "2025-01-20", "2025-02-17", "2025-04-18",
        "2025-05-26", "2025-06-19", "2025-07-04", "2025-09-01", "2025-11-27",
        "2025-12-25",
        # 2026 (07-03: Independence Day observed)
        "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25",
        "2026-06-19", "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25",
        # 2027 (06-18 and 07-05 and 12-24: observed holidays)
        "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31",
        "2027-06-18", "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24",
    )
)

_warned_uncovered = False


def nyse_closed(d: date) -> bool:
    """True when NYSE had no session on ``d`` (weekend or listed holiday)."""
    global _warned_uncovered
    if d.weekday() >= 5:
        return True
    if not (FIRST_COVERED_YEAR <= d.year <= LAST_COVERED_YEAR):
        if not _warned_uncovered:
            logger.warning(
                "market_calendar: %s outside covered years %d-%d; treated as open — extend the list",
                d, FIRST_COVERED_YEAR, LAST_COVERED_YEAR,
            )
            _warned_uncovered = True
        return False
    return d in NYSE_CLOSED_DATES
