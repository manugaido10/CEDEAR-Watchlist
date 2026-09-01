"""Reconcile parser-derived positions against positions_log entries.

Pure comparison — no file I/O, no writes. Both inputs are injected so this
module is testable in isolation (same pattern as cocos_csv_parser and
pnl_calculator).
"""

from __future__ import annotations

from dataclasses import dataclass

from data.cocos_csv_parser import DerivedPosition, ParseResult
from data.positions_log import Position

# ---------------------------------------------------------------------------
# Symbol normalisation
# ---------------------------------------------------------------------------

# Log symbols carry exchange suffixes (e.g. 'AAPL.BA', 'DECK.BA') while
# parser tickers are bare ('AAPL', 'DECK').  Argentine equities (SEMI, MORI,
# BYMA …) may have no suffix in either place.  Stripping everything from the
# first '.' produces a single canonical key for both.
def _normalize(symbol: str) -> str:
    return symbol.split(".")[0].upper()


# ---------------------------------------------------------------------------
# Tolerance constants
# ---------------------------------------------------------------------------

_QTY_TOLERANCE = 1.0    # shares; |delta| below this → qty "matches"
_COST_TOLERANCE = 0.01  # 1 %; relative diff above this → cost mismatch


# ---------------------------------------------------------------------------
# Output dataclasses
# ---------------------------------------------------------------------------

@dataclass
class LogFields:
    """Log-only fields that cannot be derived from the CSV.

    Carried through every bucket so a downstream write step knows which
    values to retain and never loses them.
    """
    source: str
    score_at_entry: float
    invalidation_at_entry_ars: float


@dataclass
class MatchedPosition:
    """Symbol present in both sources; quantities agree within tolerance."""
    ticker: str               # normalised key
    log_symbol: str           # original log symbol (e.g. 'AAPL.BA')
    csv_qty: float
    log_qty: float
    csv_avg_cost_ars: float
    log_open_price_ars: float
    cost_mismatch: bool       # True when the two cost figures differ by > 1 %
    log_fields: LogFields


@dataclass
class QtyMismatch:
    """Symbol in both sources but net_qty differs by >= 1 share."""
    ticker: str
    log_symbol: str
    csv_qty: float
    log_qty: float
    delta: float              # csv_qty − log_qty; negative means log is higher
    csv_avg_cost_ars: float
    log_open_price_ars: float
    log_fields: LogFields


@dataclass
class InCsvNotInLog:
    """CSV shows an open position the log has no record of.

    Likely a manual buy or a trade that happened before the log was set up.
    Log-only fields (source, score, invalidation) are unknown — they require
    manual entry before this can be added to the log.
    """
    ticker: str
    csv_qty: float
    csv_avg_cost_ars: float
    csv_first_buy_date: str
    csv_last_trade_date: str
    note: str                 # always "needs manual entry criteria"


@dataclass
class InLogNotInCsv:
    """Log has an open position the CSV does not show as open.

    csv_status discriminates two sub-cases:
      "closed"  — ticker appears in parse_result.closed_positions; the
                  position was likely sold and is a candidate to be closed
                  in the log.
      "absent"  — ticker not found anywhere in the CSV; likely acquired
                  before the CSV window begins (cost basis incomplete —
                  review manually, do not assume closed).
    """
    ticker: str
    log_symbol: str
    log_qty: float
    log_open_price_ars: float
    log_fields: LogFields
    csv_status: str           # "closed" | "absent"


@dataclass
class SkippedEntry:
    """Parser warning surfaced through the reconciliation report."""
    ticker: str
    warning: str


@dataclass
class ReconciliationReport:
    matched: list[MatchedPosition]
    qty_mismatch: list[QtyMismatch]
    in_csv_not_in_log: list[InCsvNotInLog]
    in_log_not_in_csv: list[InLogNotInCsv]
    skipped: list[SkippedEntry]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def reconcile(
    parse_result: ParseResult,
    logged_positions: list[Position],
) -> ReconciliationReport:
    """Diff parser-derived positions against log positions.

    Args:
        parse_result:      Output of parse_positions() — read-only.
        logged_positions:  Output of load_positions() — full list, any status.

    Returns:
        ReconciliationReport describing every discrepancy.  No side effects.
    """
    # Build normalised lookup maps from parser output.
    csv_open: dict[str, DerivedPosition] = {
        p.ticker.upper(): p for p in parse_result.open_positions
    }
    csv_closed_keys: set[str] = {
        p.ticker.upper() for p in parse_result.closed_positions
    }

    # Only open log positions are compared against CSV open positions.
    log_open_by_key: dict[str, Position] = {
        _normalize(p.symbol): p
        for p in logged_positions
        if p.status == "open"
    }

    matched: list[MatchedPosition] = []
    qty_mismatch: list[QtyMismatch] = []
    in_csv_not_in_log: list[InCsvNotInLog] = []
    in_log_not_in_csv: list[InLogNotInCsv] = []

    # --- Walk every open CSV position ---
    for key, csv_pos in csv_open.items():
        log_pos = log_open_by_key.get(key)

        if log_pos is None:
            in_csv_not_in_log.append(InCsvNotInLog(
                ticker=key,
                csv_qty=csv_pos.net_qty,
                csv_avg_cost_ars=csv_pos.avg_cost_ars,
                csv_first_buy_date=csv_pos.first_buy_date,
                csv_last_trade_date=csv_pos.last_trade_date,
                note="needs manual entry criteria",
            ))
            continue

        log_fields = _log_fields(log_pos)
        delta = csv_pos.net_qty - log_pos.qty

        if abs(delta) >= _QTY_TOLERANCE:
            qty_mismatch.append(QtyMismatch(
                ticker=key,
                log_symbol=log_pos.symbol,
                csv_qty=csv_pos.net_qty,
                log_qty=log_pos.qty,
                delta=delta,
                csv_avg_cost_ars=csv_pos.avg_cost_ars,
                log_open_price_ars=log_pos.open_price_ars,
                log_fields=log_fields,
            ))
        else:
            matched.append(MatchedPosition(
                ticker=key,
                log_symbol=log_pos.symbol,
                csv_qty=csv_pos.net_qty,
                log_qty=log_pos.qty,
                csv_avg_cost_ars=csv_pos.avg_cost_ars,
                log_open_price_ars=log_pos.open_price_ars,
                cost_mismatch=_cost_differs(csv_pos.avg_cost_ars, log_pos.open_price_ars),
                log_fields=log_fields,
            ))

    # --- Walk log open positions not present in CSV open ---
    for key, log_pos in log_open_by_key.items():
        if key in csv_open:
            continue  # already handled above

        csv_status = "closed" if key in csv_closed_keys else "absent"
        in_log_not_in_csv.append(InLogNotInCsv(
            ticker=key,
            log_symbol=log_pos.symbol,
            log_qty=log_pos.qty,
            log_open_price_ars=log_pos.open_price_ars,
            log_fields=_log_fields(log_pos),
            csv_status=csv_status,
        ))

    return ReconciliationReport(
        matched=matched,
        qty_mismatch=qty_mismatch,
        in_csv_not_in_log=in_csv_not_in_log,
        in_log_not_in_csv=in_log_not_in_csv,
        skipped=_build_skipped(parse_result),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _log_fields(pos: Position) -> LogFields:
    return LogFields(
        source=pos.source,
        score_at_entry=pos.score_at_entry,
        invalidation_at_entry_ars=pos.invalidation_at_entry_ars,
    )


def _cost_differs(csv_avg: float, log_price: float) -> bool:
    """True when the two cost figures differ by more than _COST_TOLERANCE."""
    if log_price == 0:
        return csv_avg != 0
    return abs(csv_avg - log_price) / abs(log_price) > _COST_TOLERANCE


def _build_skipped(parse_result: ParseResult) -> list[SkippedEntry]:
    """Convert all parser warnings into SkippedEntry records."""
    entries: list[SkippedEntry] = []
    for warn in parse_result.warnings:
        # Warnings are formatted as "<TICKER>: <message>" — extract the ticker.
        ticker = warn.split(":")[0].strip() if ":" in warn else "unknown"
        entries.append(SkippedEntry(ticker=ticker, warning=warn))
    return entries
