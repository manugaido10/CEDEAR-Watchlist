"""Paper position log — JSON-backed tracker for the reversal scanner's paper trades.

Records every published reversal signal as a paper position. Positions are opened
automatically by signal_registry.record_signals() and closed automatically by
outcome_tracker.assess_outcomes() when a signal resolves.

No monetary sizing fields (qty, close_price_ars) — this is pure paper tracking.
The entry price is stored for scale-in detection (Part B of suppression): a new
signal at a higher price than the paper entry confirms the thesis; a lower price
would be averaging down, which is forbidden by CRITERIOS_INVERSION.md.

See DECISIONS.md #28 for the rationale behind this redesign.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

DEFAULT_PATH = Path("data/positions_log.json")

VALID_SOURCES = ("momentum", "reversal")
VALID_REASONS = ("target", "stop", "manual")
VALID_STATUSES = ("open", "closed")


@dataclass
class Position:
    symbol: str
    source: str                           # "momentum" | "reversal"
    open_date: str                        # ISO date — scan date of the published signal
    entry_price_ars: float                # close price at scan date
    score_at_entry: float
    invalidation_at_entry_ars: float
    status: str                           # "open" | "closed"
    close_date: Optional[str] = None
    close_reason: Optional[str] = None   # "target" | "stop" | "manual"


# ── I/O ───────────────────────────────────────────────────────────────────────

def load_positions(path: Path = DEFAULT_PATH) -> list[Position]:
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [Position(**entry) for entry in raw]


def save_positions(positions: list[Position], path: Path = DEFAULT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [asdict(p) for p in positions]
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# ── Mutations ─────────────────────────────────────────────────────────────────

def open_position(
    symbol: str,
    price: float,
    source: str,
    score: float,
    invalidation: float,
    date: str,
    path: Path = DEFAULT_PATH,
) -> Position:
    if source not in VALID_SOURCES:
        raise ValueError(f"invalid source {source!r}: expected one of {VALID_SOURCES}")

    positions = load_positions(path)
    if any(p.symbol == symbol and p.status == "open" for p in positions):
        raise ValueError(
            f"cannot open {symbol}: an open position already exists for this symbol "
            f"(close it first or use a different symbol)"
        )

    position = Position(
        symbol=symbol,
        source=source,
        open_date=date,
        entry_price_ars=float(price),
        score_at_entry=float(score),
        invalidation_at_entry_ars=float(invalidation),
        status="open",
    )
    positions.append(position)
    save_positions(positions, path)
    return position


def close_position(
    symbol: str,
    date: str,
    reason: str,
    path: Path = DEFAULT_PATH,
) -> Position:
    if reason not in VALID_REASONS:
        raise ValueError(f"invalid reason {reason!r}: expected one of {VALID_REASONS}")

    positions = load_positions(path)
    candidates = [
        (i, p) for i, p in enumerate(positions)
        if p.symbol == symbol and p.status == "open"
    ]
    if not candidates:
        raise ValueError(f"cannot close {symbol}: no open position found for this symbol")

    idx, position = max(candidates, key=lambda pair: pair[1].open_date)
    position.status = "closed"
    position.close_date = date
    position.close_reason = reason
    positions[idx] = position
    save_positions(positions, path)
    return position
