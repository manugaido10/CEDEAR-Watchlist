"""Tradeability suppression for reversal signals.

Runs two orthogonal checks against a candidate signal, in order:

1. Cooldown post stop_hit — 15 business days of quarantine, gated on price
   regime (the ticker must have recovered above the prior invalidation level
   before it can be re-entered).
2. Open-position awareness — a signal for a ticker already in the paper log's
   open set is evaluated in three ranges (see DECISIONS.md #29):
     a. entry > prior entry → scale-in (thesis reconfirmed by price strength)
     b. prior * (1 - SCALE_IN_TOLERANCE_PCT) < entry ≤ prior → scale-in
        (day-to-day noise, same setup; avoids positions_log inconsistency
        if classified as a new tradeable position when one is already open)
     c. entry ≤ prior * (1 - SCALE_IN_TOLERANCE_PCT) → blocked (material
        deterioration — promediar a la baja)

Part C (per-ticker sizing cap) was removed in DECISIONS.md #28: in paper-trading
mode there is no capital figure, so a monetary cap per ticker is meaningless.

Suppressed signals are never dropped from the audit trail; they carry
``tradeable=False`` and a Spanish ``suppression_reason`` so the report can
mark them "no operar" while retaining the record.

Pure functions, dependency-injected — no file I/O in this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Dict, Iterable, List, Optional, Tuple

import numpy as np

if TYPE_CHECKING:
    from data.positions_log import Position

COOLDOWN_WINDOW_BUSINESS_DAYS = 15

# Tolerance for Part B: entries within this fraction below the prior open price
# are classified as scale-in (day-to-day noise) rather than blocked.
# Empirically derived from the corpus: max observed noise diff = -1.56%;
# -2.66% (BYMA, 10d gap) is the boundary of genuine deterioration that Part B
# exclusively covers. See DECISIONS.md #29 for the full distribution and trade-off.
SCALE_IN_TOLERANCE_PCT = 0.02


# ── Symbol normalisation (mirrors data.reconciler._normalize) ────────────────

def _canonical(symbol: str) -> str:
    return symbol.split(".")[0].upper()


# ── Date helpers ─────────────────────────────────────────────────────────────

def _to_date(value) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    return datetime.strptime(str(value), "%Y-%m-%d").date()


def _business_days_between(start: date, end: date) -> int:
    """Business days elapsed from ``start`` to ``end`` (end exclusive).

    Uses numpy.busday_count which matches BYMA/NYSE weekday convention.
    Returns 0 when ``end <= start``.
    """
    if end <= start:
        return 0
    return int(np.busday_count(np.datetime64(start, "D"), np.datetime64(end, "D")))


# ── Result containers ────────────────────────────────────────────────────────

@dataclass
class SuppressionResult:
    tradeable: bool
    reason: Optional[str] = None
    is_scale_in: bool = False
    existing_position: Optional["Position"] = None


@dataclass
class OpenPositionCheck:
    """Outcome of the open-position check.

    - No open position → blocked=False, is_scale_in=False.
    - Open AND entry > existing → is_scale_in=True (thesis reconfirmed).
    - Open AND existing × (1 - TOL) < entry ≤ existing → is_scale_in=True
      (within SCALE_IN_TOLERANCE_PCT noise band — see DECISIONS.md #29).
    - Open AND entry ≤ existing × (1 - TOL) → blocked=True (material
      deterioration — promediar a la baja, forbidden by CRITERIOS_INVERSION.md).
    """
    blocked: bool
    reason: Optional[str] = None
    is_scale_in: bool = False
    existing_position: Optional["Position"] = None


# ── Part A — Cooldown ────────────────────────────────────────────────────────

def check_cooldown(
    symbol: str,
    scan_date: str,
    entry_price_ars: float,
    outcomes: Iterable[Dict],
    *,
    window_business_days: int = COOLDOWN_WINDOW_BUSINESS_DAYS,
) -> Optional[str]:
    """Return a Spanish reason string if the symbol is in a losing-regime cooldown, else None.

    Cooldown is active when BOTH:
      1. There is a ``stop_hit`` outcome for ``symbol`` whose exit event lies
         within the last ``window_business_days`` business days of ``scan_date``.
      2. ``entry_price_ars`` is at or below the ``invalidation_level_ars`` of
         that stop_hit signal (the regime that broke the prior thesis has not
         yet been reclaimed).

    Exit event date = outcome.scan_date + days_to_outcome (calendar). Falls back
    to outcome.scan_date when days_to_outcome is missing.
    """
    key = _canonical(symbol)
    scan_dt = _to_date(scan_date)

    most_recent: Optional[Tuple[date, float]] = None

    for outcome in outcomes:
        if outcome.get("outcome") != "stop_hit":
            continue
        if _canonical(outcome.get("symbol", "")) != key:
            continue

        outcome_scan_dt = _to_date(outcome["scan_date"])
        days_to = outcome.get("days_to_outcome")
        exit_dt = outcome_scan_dt + timedelta(days=int(days_to)) if days_to is not None else outcome_scan_dt

        if exit_dt >= scan_dt:
            continue  # stop_hit is in the future relative to this scan — ignore
        if _business_days_between(exit_dt, scan_dt) > window_business_days:
            continue

        invalidation = outcome.get("invalidation_level_ars")
        if invalidation is None:
            continue

        if most_recent is None or exit_dt > most_recent[0]:
            most_recent = (exit_dt, float(invalidation))

    if most_recent is None:
        return None

    exit_dt, invalidation = most_recent
    if entry_price_ars > invalidation:
        return None  # regime reclaimed — cooldown does not apply

    return (
        f"En cuarentena: stop_hit el {exit_dt.isoformat()}, "
        f"precio aún bajo el nivel de invalidación ({invalidation:,.2f})"
    )


# ── Part B — Open-position awareness (conditional scale-in) ──────────────────

def _format_ars(value: float) -> str:
    return f"{value:,.2f}"


def check_open_position(
    symbol: str,
    entry_price_ars: float,
    positions: Iterable,
    *,
    tolerance_pct: float = SCALE_IN_TOLERANCE_PCT,
) -> OpenPositionCheck:
    """Evaluate a candidate signal against the paper log's OPEN positions.

    positions_log.open_position() forbids two simultaneous OPEN records for
    the same canonical symbol, so at most one existing position needs to be
    considered here.

    Three-range logic (see DECISIONS.md #29):
      entry > open_price                            → scale-in (thesis confirmed)
      open_price * (1 - tolerance_pct) < entry      → scale-in (noise band)
        ≤ open_price
      entry ≤ open_price * (1 - tolerance_pct)      → blocked (material
                                                        deterioration)

    The noise-band range is classified as scale-in (not new tradeable) to
    prevent signal_registry from attempting open_position() on a ticker that
    already has an open record — which would silently fail and leave the report
    inconsistent with positions_log.
    """
    key = _canonical(symbol)
    for pos in positions:
        if getattr(pos, "status", None) != "open":
            continue
        if _canonical(getattr(pos, "symbol", "")) != key:
            continue
        open_price = float(getattr(pos, "entry_price_ars", 0.0) or 0.0)
        tolerance_floor = open_price * (1.0 - tolerance_pct)
        if entry_price_ars > tolerance_floor:
            return OpenPositionCheck(
                blocked=False,
                is_scale_in=True,
                existing_position=pos,
            )
        reason = (
            f"Bloqueado: sumar ahora sería promediar a la baja "
            f"(costo previo {_format_ars(open_price)}, "
            f"precio actual {_format_ars(entry_price_ars)})"
        )
        return OpenPositionCheck(
            blocked=True,
            reason=reason,
            existing_position=pos,
        )
    return OpenPositionCheck(blocked=False)


# ── Orchestrator ─────────────────────────────────────────────────────────────

def evaluate_suppressions(
    symbol: str,
    scan_date: str,
    entry_price_ars: float,
    outcomes: Iterable[Dict],
    positions: Iterable,
    *,
    cooldown_window_business_days: int = COOLDOWN_WINDOW_BUSINESS_DAYS,
) -> SuppressionResult:
    """Run cooldown → position checks, short-circuiting on first hit.

    Part C (per-ticker sizing cap) was removed in #28: paper-trading mode
    has no capital figure. Parts A and B are unchanged.
    """
    reason = check_cooldown(
        symbol, scan_date, entry_price_ars, outcomes,
        window_business_days=cooldown_window_business_days,
    )
    if reason is not None:
        return SuppressionResult(tradeable=False, reason=reason)

    pos_check = check_open_position(symbol, entry_price_ars, positions)
    if pos_check.blocked:
        return SuppressionResult(
            tradeable=False,
            reason=pos_check.reason,
            existing_position=pos_check.existing_position,
        )

    return SuppressionResult(
        tradeable=True,
        reason=None,
        is_scale_in=pos_check.is_scale_in,
        existing_position=pos_check.existing_position,
    )
