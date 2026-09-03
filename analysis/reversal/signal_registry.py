"""Registry of published reversal signals — append-only JSONL log.

Responsibilities:
- Record every ReversalOpportunity that appears in a published report.
- Detect repeated signals: same ticker published recently with no significant price movement.
- Provide a stable read interface used by outcome_tracker.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

SIGNALS_PATH = Path("data/reversal_tracking/signals.jsonl")
_DEFAULT_LOOKBACK_DAYS = 7
_DEFAULT_PRICE_THRESHOLD = 0.03  # 3% movement = genuinely new setup


# ── I/O helpers ───────────────────────────────────────────────────────────────

def _ensure_path() -> None:
    SIGNALS_PATH.parent.mkdir(parents=True, exist_ok=True)


def load_signals() -> List[Dict]:
    """Load all records from signals.jsonl. Returns [] if file missing."""
    _ensure_path()
    if not SIGNALS_PATH.exists():
        return []
    records = []
    for line in SIGNALS_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                logger.warning("signal_registry: skipping malformed line: %s", line[:80])
    return records


def _append_record(record: Dict) -> None:
    _ensure_path()
    with SIGNALS_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ── Record ────────────────────────────────────────────────────────────────────

def record_signals(
    opportunities: list,  # List[ReversalOpportunity] — avoid circular import
    scan_date: str,
    enrichments: Optional[Dict] = None,
) -> None:
    """Append one record per opportunity to signals.jsonl.

    Skips symbols already recorded for this exact scan_date (idempotent on re-runs).
    enrichments: optional {symbol_ars: {"trend": str, "n_analysts": int|None}} from
    analyst_revision.fetch_revisions — merged silently, absent if enrichments is empty.
    """
    existing_keys = {
        (r["scan_date"], r["symbol"])
        for r in load_signals()
    }
    for opp in opportunities:
        key = (scan_date, opp.symbol)
        if key in existing_keys:
            logger.debug("signal_registry: %s/%s already recorded, skipping", scan_date, opp.symbol)
            continue
        record = {
            "scan_date": scan_date,
            "symbol": opp.symbol,
            "score": opp.score,
            "rsi_14": opp.rsi_14,
            "entry_price_ars": opp.entry_price_ars,
            "invalidation_level_ars": opp.invalidation_level_ars,
            "nearest_support": opp.nearest_support,
            "support_type": opp.nearest_support_type,
            "catalysts": opp.catalyst,
            "weekly_trend": opp.weekly_trend,
            "outcome_status": "pending",
            "tradeable": bool(getattr(opp, "tradeable", True)),
        }
        suppression_reason = getattr(opp, "suppression_reason", None)
        if suppression_reason is not None:
            record["suppression_reason"] = suppression_reason
        if bool(getattr(opp, "is_scale_in", False)):
            record["is_scale_in"] = True
        if enrichments and opp.symbol in enrichments:
            record["analyst_revision"] = enrichments[opp.symbol]
        _append_record(record)
        logger.debug("signal_registry: recorded %s for %s", opp.symbol, scan_date)


# ── Deduplication ─────────────────────────────────────────────────────────────

def check_recent(
    symbol: str,
    scan_date: str,
    current_price_ars: float,
    lookback_days: int = _DEFAULT_LOOKBACK_DAYS,
    price_threshold: float = _DEFAULT_PRICE_THRESHOLD,
) -> Optional[str]:
    """Return the last scan_date this symbol appeared if it's a repeated signal, else None.

    A repeated signal is: same ticker published within lookback_days, AND the
    price has not moved more than price_threshold since the prior entry.
    If price moved significantly, the setup is genuinely new.
    """
    scan_dt = datetime.strptime(scan_date, "%Y-%m-%d").date()
    cutoff = scan_dt - timedelta(days=lookback_days)

    signals = load_signals()
    candidates = [
        r for r in signals
        if r["symbol"] == symbol
        and r["scan_date"] != scan_date
        and datetime.strptime(r["scan_date"], "%Y-%m-%d").date() >= cutoff
    ]
    if not candidates:
        return None

    # Most recent prior appearance
    candidates.sort(key=lambda r: r["scan_date"], reverse=True)
    prior = candidates[0]
    prior_entry = prior.get("entry_price_ars")
    if prior_entry and abs(current_price_ars - prior_entry) / prior_entry >= price_threshold:
        return None  # price moved enough — treat as new setup

    return prior["scan_date"]


# ── Outcome status update (called by outcome_tracker) ────────────────────────

def update_outcome_status(symbol: str, scan_date: str, new_status: str) -> None:
    """Rewrite the JSONL updating outcome_status for the given signal.

    Linear rewrite — acceptable given small file size.
    """
    records = load_signals()
    updated = False
    for r in records:
        if r["symbol"] == symbol and r["scan_date"] == scan_date:
            r["outcome_status"] = new_status
            updated = True
    if not updated:
        logger.warning("signal_registry: no record found for %s/%s", scan_date, symbol)
        return
    _ensure_path()
    with SIGNALS_PATH.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
