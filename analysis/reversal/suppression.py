"""Tradeability suppression for reversal signals.

Runs three orthogonal checks against a candidate signal, in order:

1. Cooldown post stop_hit — 15 business days of quarantine, gated on price
   regime (the ticker must have recovered above the prior invalidation level
   before it can be re-entered).
2. Open-position awareness — a signal for a ticker already in the log's open
   set is only allowed as a scale-in when the new entry price confirms the
   thesis (price advanced above the prior open). Any other case is blocked
   to enforce the "no promediar a la baja" rule from CRITERIOS_INVERSION.md.
3. Accumulated per-ticker sizing cap — 8% of total capital per ticker across
   all committed exposure.

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
PER_TICKER_CAP_PCT = 0.08


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
    - Open position AND entry_price_ars > open_price_ars → blocked=False,
      is_scale_in=True (thesis reconfirmed — allowed per "Escalado de
      posiciones", CRITERIOS_INVERSION.md).
    - Open position AND entry_price_ars <= open_price_ars → blocked=True
      (promediar a la baja — forbidden by the same rule).
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
) -> OpenPositionCheck:
    """Evaluate a candidate signal against the log's OPEN positions.

    positions_log.open_position() forbids two simultaneous OPEN records for
    the same canonical symbol, so at most one existing position needs to be
    considered here.

    Blocks only when the new entry would average down (entry_price_ars <=
    open_price_ars). When entry_price_ars > open_price_ars the signal is
    allowed as a scale-in — same reasoning as the "Escalado de posiciones"
    rule in CRITERIOS_INVERSION.md: the thesis is reconfirmed by fresh price
    strength.
    """
    key = _canonical(symbol)
    for pos in positions:
        if getattr(pos, "status", None) != "open":
            continue
        if _canonical(getattr(pos, "symbol", "")) != key:
            continue
        open_price = float(getattr(pos, "open_price_ars", 0.0) or 0.0)
        if entry_price_ars > open_price:
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


# ── Part C — Accumulated per-ticker sizing ───────────────────────────────────

def _committed_ars(symbol: str, positions: Iterable) -> float:
    """Sum of ``qty * open_price_ars`` for OPEN positions matching ``symbol``."""
    key = _canonical(symbol)
    total = 0.0
    for pos in positions:
        if getattr(pos, "status", None) != "open":
            continue
        if _canonical(getattr(pos, "symbol", "")) != key:
            continue
        qty = float(getattr(pos, "qty", 0.0) or 0.0)
        price = float(getattr(pos, "open_price_ars", 0.0) or 0.0)
        total += qty * price
    return total


def per_ticker_headroom_ars(
    symbol: str,
    positions: Iterable,
    total_capital_ars: float,
    *,
    cap_pct: float = PER_TICKER_CAP_PCT,
) -> float:
    """Return ARS still allocatable to ``symbol`` before hitting the per-ticker cap.

    Reused by the report allocator for scale-in sizing so the cap math lives
    in a single place. Never negative (clamps at 0.0).
    """
    if total_capital_ars <= 0:
        return 0.0
    cap_ars = total_capital_ars * cap_pct
    committed = _committed_ars(symbol, positions)
    return max(0.0, cap_ars - committed)


def check_sizing_cap(
    symbol: str,
    positions: Iterable,
    total_capital_ars: float,
    *,
    cap_pct: float = PER_TICKER_CAP_PCT,
    additional_committed_ars: float = 0.0,
) -> Optional[str]:
    """Hard-block reason if committed exposure already reaches the per-ticker cap, else None.

    ``additional_committed_ars`` covers "other tradeable signals for this ticker
    already produced in the current scan cycle" (moot today because the reversal
    scanner emits at most one signal per ticker per run; kept for future-proofing).

    The rule is reduce-in-place when there is any positive headroom, hard-block
    only at zero/negative headroom. Reduction is silent (no reason string):
    the report allocator downstream honours the per-ticker cap when sizing.
    """
    if total_capital_ars <= 0:
        return None  # can't meaningfully evaluate without capital context

    committed = _committed_ars(symbol, positions) + max(0.0, additional_committed_ars)
    cap_ars = total_capital_ars * cap_pct

    if committed >= cap_ars:
        pct = committed / total_capital_ars * 100.0
        return (
            f"Límite de 8% por ticker ya alcanzado/excedido ({pct:.1f}% comprometido)"
        )
    return None


# ── Orchestrator ─────────────────────────────────────────────────────────────

def evaluate_suppressions(
    symbol: str,
    scan_date: str,
    entry_price_ars: float,
    outcomes: Iterable[Dict],
    positions: Iterable,
    total_capital_ars: Optional[float],
    *,
    cooldown_window_business_days: int = COOLDOWN_WINDOW_BUSINESS_DAYS,
    cap_pct: float = PER_TICKER_CAP_PCT,
    additional_committed_ars: float = 0.0,
) -> SuppressionResult:
    """Run cooldown → position → sizing checks, short-circuiting on first hit.

    ``total_capital_ars=None`` skips Part C entirely (used when the caller did
    not supply a capital figure — e.g. legacy code paths). This never affects
    Parts A/B.
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

    if total_capital_ars is not None:
        reason = check_sizing_cap(
            symbol, positions, total_capital_ars,
            cap_pct=cap_pct,
            additional_committed_ars=additional_committed_ars,
        )
        if reason is not None:
            return SuppressionResult(
                tradeable=False,
                reason=reason,
                is_scale_in=pos_check.is_scale_in,
                existing_position=pos_check.existing_position,
            )

    return SuppressionResult(
        tradeable=True,
        reason=None,
        is_scale_in=pos_check.is_scale_in,
        existing_position=pos_check.existing_position,
    )
