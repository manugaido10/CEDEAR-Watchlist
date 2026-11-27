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

from analysis.reversal.instrumentation import PriceInstrumentation
from analysis.reversal.news_check import NEWS_RECORD_KEYS, empty_news_record
from data.dividends import ExDividendResult

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

def _news_fields(opp: Any) -> Dict[str, Any]:
    """The NEWS_RECORD_KEYS for one opportunity. Never raises (fail-closed to nulls)."""
    fields = empty_news_record()
    news_check = getattr(opp, "news_check", None)
    if news_check is None:
        return fields
    try:
        rec = news_check.to_record()
        fields.update({k: rec.get(k) for k in NEWS_RECORD_KEYS})
    except Exception as exc:
        logger.warning(
            "signal_registry: news_check.to_record failed for %s — %s; news fields recorded as null",
            getattr(opp, "symbol", "?"), exc,
        )
        return empty_news_record()
    return fields


def record_signals(
    opportunities: list,  # List[ReversalOpportunity] — avoid circular import
    scan_date: str,
    enrichments: Optional[Dict] = None,
    fx_enrichments: Optional[Dict] = None,
    data_date: Optional[str] = None,
) -> None:
    """Append one record per opportunity to signals.jsonl.

    Skips symbols already recorded for this exact scan_date (idempotent on re-runs).
    data_date (Decision #35): date of the last price bar the scan used. When
    given, it is stored on the record, and a symbol already recorded with the
    same data_date under a different scan_date is skipped — no record, no paper
    position (e.g. a Saturday run and the following Monday pre-open run both
    read Friday's close). Historical records without data_date never match.
    enrichments: optional {symbol_ars: {"trend": str, "n_analysts": int|None}} from
    analyst_revision.fetch_revisions — merged silently, absent if enrichments is empty.
    fx_enrichments: optional {symbol_ars: {...FX context fields...}} from
    fx_context.build_fx_enrichments (Decision #31 / Roadmap Fase A2). Only present
    for CEDEARs — argentine stocks and bundles without CCL are absent from the map.
    """
    existing = load_signals()
    existing_keys = {(r["scan_date"], r["symbol"]) for r in existing}
    data_date_owner = {
        (r["data_date"], r["symbol"]): r["scan_date"]
        for r in existing
        if r.get("data_date") is not None
    }
    for opp in opportunities:
        key = (scan_date, opp.symbol)
        if key in existing_keys:
            logger.debug("signal_registry: %s/%s already recorded, skipping", scan_date, opp.symbol)
            continue
        if data_date is not None and (data_date, opp.symbol) in data_date_owner:
            logger.warning(
                "signal_registry: %s skipped for scan_date %s — same data_date %s already "
                "recorded under scan_date %s (no record, no paper position)",
                opp.symbol, scan_date, data_date, data_date_owner[(data_date, opp.symbol)],
            )
            continue
        record = {
            "scan_date": scan_date,
            "data_date": data_date,
            "symbol": opp.symbol,
            "score": opp.score,
            "rsi_14": opp.rsi_14,
            "entry_price_ars": opp.entry_price_ars,
            "invalidation_level_ars": opp.invalidation_level_ars,
            "nearest_support": opp.nearest_support,
            "support_type": opp.nearest_support_type,
            "catalysts": opp.catalyst,
            "weekly_trend": opp.weekly_trend,
            "vol_ratio": getattr(opp, "volume_ratio", None),
            "vol_ratio_clean": getattr(opp, "volume_ratio_clean", None),
            "outcome_status": "pending",
            "tradeable": bool(getattr(opp, "tradeable", True)),
        }
        adv_ars = getattr(opp, "adv_ars", None)
        if adv_ars is not None:
            record["adv_ars_at_scan"] = int(round(adv_ars))
        suppression_reason = getattr(opp, "suppression_reason", None)
        if suppression_reason is not None:
            record["suppression_reason"] = suppression_reason
        if bool(getattr(opp, "is_scale_in", False)):
            record["is_scale_in"] = True
        if enrichments and opp.symbol in enrichments:
            record["analyst_revision"] = enrichments[opp.symbol]
        if fx_enrichments and opp.symbol in fx_enrichments:
            record["fx_context"] = fx_enrichments[opp.symbol]
        # Fase B1 instrumentation: always-present keys, None when not computable.
        instrumentation = getattr(opp, "instrumentation", None) or PriceInstrumentation()
        record.update(instrumentation.to_record())
        record["earnings_status"] = getattr(opp, "earnings_status", None)
        record["days_to_earnings"] = getattr(opp, "days_to_earnings", None)
        record["earnings_calendar_stale"] = getattr(opp, "earnings_calendar_stale", None)
        # Fase B3: ex_div_* keys always present, None when no data. No exclusion
        # decision is stored; "contaminated" is computed in analysis/query.py.
        ex_dividend = getattr(opp, "ex_dividend", None) or ExDividendResult()
        record.update(ex_dividend.to_record())
        # Decision #39: news check fields, always present; all null = did not run.
        record.update(_news_fields(opp))
        _append_record(record)
        logger.debug("signal_registry: recorded %s for %s", opp.symbol, scan_date)

        # Auto-open paper position for new tradeable signals (#28).
        # Scale-ins already have an open position; non-tradeable signals are suppressed.
        if bool(getattr(opp, "tradeable", True)) and not bool(getattr(opp, "is_scale_in", False)):
            from data.positions_log import open_position
            try:
                open_position(
                    symbol=opp.symbol,
                    price=opp.entry_price_ars,
                    source="reversal",
                    score=float(opp.score),
                    invalidation=opp.invalidation_level_ars,
                    date=scan_date,
                )
                logger.debug("signal_registry: paper position opened for %s", opp.symbol)
            except ValueError as exc:
                logger.warning(
                    "signal_registry: could not open paper position for %s — %s", opp.symbol, exc
                )
            except Exception as exc:
                logger.warning(
                    "signal_registry: unexpected error opening paper position for %s — %s",
                    opp.symbol, exc,
                )


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
