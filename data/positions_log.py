"""Position log — JSON-backed storage for manually tracked trades.

The log is the source of truth for the user's real trading history. All
opens and closes are explicit user actions; nothing here is automated.
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
    source: str                      # "momentum" | "reversal"
    open_date: str                   # ISO date (YYYY-MM-DD)
    open_price_ars: float
    qty: float
    score_at_entry: float
    invalidation_at_entry_ars: float
    status: str                      # "open" | "closed"
    close_date: Optional[str] = None
    close_price_ars: Optional[float] = None
    close_reason: Optional[str] = None  # "target" | "stop" | "manual"


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
    qty: float,
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
        open_price_ars=float(price),
        qty=float(qty),
        score_at_entry=float(score),
        invalidation_at_entry_ars=float(invalidation),
        status="open",
    )
    positions.append(position)
    save_positions(positions, path)
    return position


def close_position(
    symbol: str,
    price: float,
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

    # If multiple opens existed (shouldn't, but defensive), close the most recent by open_date.
    idx, position = max(candidates, key=lambda pair: pair[1].open_date)
    position.status = "closed"
    position.close_date = date
    position.close_price_ars = float(price)
    position.close_reason = reason
    positions[idx] = position
    save_positions(positions, path)
    return position
