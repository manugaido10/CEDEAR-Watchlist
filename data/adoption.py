"""Signal-backed adoption candidates derived from the reconciliation report.

Splits in_csv_not_in_log entries into those traceable to a published reversal
signal (candidates for clean adoption) and those with no signal match (manual).

Pure computation — no file I/O, no side effects. Inputs are injected so this
module is testable in isolation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from data.reconciler import InCsvNotInLog


@dataclass
class AdoptionCandidate:
    ticker: str                            # normalized (no .BA suffix)
    log_symbol: str                        # from matched signal (e.g. "AAPL.BA")
    csv_qty: float
    csv_avg_cost_ars: float
    csv_first_buy_date: str               # ISO YYYY-MM-DD
    matched_signal_scan_date: str         # ISO YYYY-MM-DD
    matched_signal_score: float
    matched_signal_invalidation_ars: float
    note: str                             # empty unless multiple signals matched


# ---------------------------------------------------------------------------
# IMPORTANT — provisional matching window
# ---------------------------------------------------------------------------
# matching_window_days=5 is a PROVISIONAL placeholder.
# The real value must be calibrated once live execution data exists: measure
# how many calendar days typically elapse between a signal being published
# (scan_date) and the user actually executing the trade (csv_first_buy_date).
# This is the same calibration approach used for the 15-day post-stop cooldown
# — measure, don't guess.
#
# Do NOT present this number as validated anywhere in printed output. Always
# label it "ventana provisoria (a calibrar)" in user-facing report sections.
# ---------------------------------------------------------------------------

def find_signal_backed_candidates(
    in_csv_not_in_log: list[InCsvNotInLog],
    signals: list[dict],
    matching_window_days: int = 5,
) -> tuple[list[AdoptionCandidate], list[InCsvNotInLog]]:
    """Split in_csv_not_in_log into signal-backed candidates and manual remainder.

    A position is a candidate when a published reversal signal for the same
    ticker has a scan_date within matching_window_days calendar days BEFORE
    csv_first_buy_date (inclusive of both endpoints). Signals dated after the
    buy date are never matched — a signal cannot be executed before it exists.

    If multiple signals fall within the window, the one with the scan_date
    closest to (most recent before) csv_first_buy_date is chosen as the most
    plausible execution, and a note is added to the candidate.

    Returns:
        (candidates, remaining_manual) — disjoint, together covering every
        entry from in_csv_not_in_log.
    """
    candidates: list[AdoptionCandidate] = []
    manual: list[InCsvNotInLog] = []

    # Index signals by normalized ticker (strip .BA and anything after first dot).
    signals_by_ticker: dict[str, list[dict]] = {}
    for sig in signals:
        raw_symbol = sig.get("symbol", "")
        key = raw_symbol.split(".")[0].upper()
        if key:
            signals_by_ticker.setdefault(key, []).append(sig)

    for entry in in_csv_not_in_log:
        ticker_key = entry.ticker.upper()
        buy_date = _parse_date(entry.csv_first_buy_date)
        if buy_date is None:
            manual.append(entry)
            continue

        # Backward-only window: [buy_date - window, buy_date].
        cutoff = buy_date - timedelta(days=matching_window_days)

        matching = [
            sig for sig in signals_by_ticker.get(ticker_key, [])
            if _in_window(_parse_date(sig.get("scan_date", "")), cutoff, buy_date)
        ]

        if not matching:
            manual.append(entry)
            continue

        # Sort descending by scan_date so index 0 is closest to buy_date.
        matching.sort(key=lambda s: s.get("scan_date", ""), reverse=True)
        best = matching[0]

        note = ""
        if len(matching) > 1:
            note = (
                f"múltiples señales coincidentes ({len(matching)}); "
                f"se usó la más cercana ({best.get('scan_date', '?')})"
            )

        candidates.append(AdoptionCandidate(
            ticker=ticker_key,
            log_symbol=best.get("symbol", ticker_key),
            csv_qty=entry.csv_qty,
            csv_avg_cost_ars=entry.csv_avg_cost_ars,
            csv_first_buy_date=entry.csv_first_buy_date,
            matched_signal_scan_date=best.get("scan_date", ""),
            matched_signal_score=float(best.get("score", 0.0)),
            matched_signal_invalidation_ars=float(best.get("invalidation_level_ars", 0.0)),
            note=note,
        ))

    return candidates, manual


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_date(date_str: str) -> date | None:
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return None


def _in_window(d: date | None, cutoff: date, buy_date: date) -> bool:
    """True when d falls in [cutoff, buy_date] (both inclusive)."""
    if d is None:
        return False
    return cutoff <= d <= buy_date
