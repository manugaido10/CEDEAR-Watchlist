"""Outcome tracker for published reversal signals.

For each pending signal in signals.jsonl, fetches historical prices and
determines whether the trade hit its stop (invalidation level), reached
a target, or went lateral within the evaluation window.

Outcome states:
- pending            : not yet assessed (< max_days since scan_date)
- stop_hit           : close < invalidation_level_ars before any target
- target_5pct        : close > entry * 1.05 before stop or 8% target
- target_8pct        : close > entry * 1.08 before stop
- lateral            : max_days elapsed without stop or target
- unresolved_no_data : price history unavailable for this ticker

Run independently (run_at_scan_start) or standalone:
    python -m analysis.reversal.outcome_tracker
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

OUTCOMES_PATH = Path("data/reversal_tracking/outcomes.jsonl")

_TARGET_PCTS = (0.05, 0.08)
_MAX_DAYS = 20  # calendar days; scanner runs weekly so ~4 weekly bars
_PENDING_STATUSES = {"pending"}


# ── I/O ───────────────────────────────────────────────────────────────────────

def _ensure_path() -> None:
    OUTCOMES_PATH.parent.mkdir(parents=True, exist_ok=True)


def _load_outcomes() -> Dict[Tuple[str, str], Dict]:
    """Returns {(scan_date, symbol): record}."""
    _ensure_path()
    if not OUTCOMES_PATH.exists():
        return {}
    result = {}
    for line in OUTCOMES_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                r = json.loads(line)
                result[(r["scan_date"], r["symbol"])] = r
            except (json.JSONDecodeError, KeyError):
                logger.warning("outcome_tracker: skipping malformed line")
    return result


def _save_outcomes(outcomes: Dict[Tuple[str, str], Dict]) -> None:
    _ensure_path()
    with OUTCOMES_PATH.open("w", encoding="utf-8") as f:
        for r in outcomes.values():
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


# ── Price fetch ───────────────────────────────────────────────────────────────

def _fetch_price_history(symbol: str, scan_date: str) -> Optional[pd.DataFrame]:
    """Returns a DataFrame with [close, low] columns from scan_date onwards, or None.

    close is used for target checks; low is used for stop checks.
    Returns None if no data exists or no bars after scan_date.
    """
    from data.prices import fetch_prices
    df = fetch_prices(symbol)
    if df is None or df.empty or "close" not in df.columns:
        return None
    df = df.sort_index()
    scan_dt = pd.Timestamp(scan_date)
    after = df[df.index > scan_dt]
    if after.empty:
        return None
    cols = [c for c in ["close", "low"] if c in after.columns]
    return after[cols]


# ── Single-signal assessment ──────────────────────────────────────────────────

def _assess_signal(signal: Dict, today: datetime.date) -> Dict:
    """Determine outcome for a single signal record. Returns outcome record."""
    scan_date = signal["scan_date"]
    symbol = signal["symbol"]
    entry = signal.get("entry_price_ars")
    invalidation = signal.get("invalidation_level_ars")
    catalysts = signal.get("catalysts", [])

    scan_dt = datetime.strptime(scan_date, "%Y-%m-%d").date()
    deadline = scan_dt + timedelta(days=_MAX_DAYS)
    assessed_at = str(today)

    base = {
        "scan_date": scan_date,
        "symbol": symbol,
        "assessed_at": assessed_at,
        "entry_price_ars": entry,
        "invalidation_level_ars": invalidation,
        "catalysts": catalysts,
        "outcome": "pending",
        "days_to_outcome": None,
        "exit_price_ars": None,
        "pct_change": None,
    }

    if entry is None or invalidation is None:
        base["outcome"] = "unresolved_no_data"
        return base

    price_df = _fetch_price_history(symbol, scan_date)
    if price_df is None:
        # Distinguish: no ticker data at all (permanent) vs no bars yet after
        # scan_date (transient — market not closed, wait for next run).
        from data.prices import fetch_prices as _fp
        has_any_data = _fp(symbol) is not None
        if not has_any_data or today >= deadline:
            base["outcome"] = "unresolved_no_data"
        # else: remains "pending" — will resolve on a future run
        return base

    has_low = "low" in price_df.columns

    # Evaluate day by day in chronological order.
    # Asymmetric logic: stop uses intraday low (conservative — mirrors real
    # stop-loss execution); targets use daily close (conservative — don't
    # count a target unless the price held there at end of day).
    for ts, row in price_df.iterrows():
        ts_date = ts.date() if hasattr(ts, "date") else ts
        if ts_date > deadline:
            break
        close = float(row["close"])
        low = float(row["low"]) if has_low else close
        days_elapsed = (ts_date - scan_dt).days

        # Stop first — uses intraday low
        if low < invalidation:
            base.update({
                "outcome": "stop_hit",
                "days_to_outcome": days_elapsed,
                "exit_price_ars": round(low, 2),
                "pct_change": round((low - entry) / entry, 4),
            })
            return base

        # Targets — use daily close
        if close > entry * (1 + _TARGET_PCTS[1]):
            base.update({
                "outcome": "target_8pct",
                "days_to_outcome": days_elapsed,
                "exit_price_ars": round(close, 2),
                "pct_change": round((close - entry) / entry, 4),
            })
            return base

        if close > entry * (1 + _TARGET_PCTS[0]):
            base.update({
                "outcome": "target_5pct",
                "days_to_outcome": days_elapsed,
                "exit_price_ars": round(close, 2),
                "pct_change": round((close - entry) / entry, 4),
            })
            return base

    # Deadline reached without resolution
    if today >= deadline:
        base["outcome"] = "lateral"
    # else: still within window → remains "pending"

    return base


# ── Main assessment ───────────────────────────────────────────────────────────

def assess_outcomes(
    target_pcts: tuple = _TARGET_PCTS,
    max_days: int = _MAX_DAYS,
) -> None:
    """Refresh outcome records for all pending signals.

    Loads signals.jsonl, assesses pending signals, writes outcomes.jsonl,
    and updates outcome_status in signals.jsonl via signal_registry.
    """
    from analysis.reversal.signal_registry import load_signals, update_outcome_status

    signals = load_signals()
    pending = [s for s in signals if s.get("outcome_status") in _PENDING_STATUSES]

    if not pending:
        logger.debug("outcome_tracker: no pending signals to assess")
        return

    today = datetime.today().date()
    outcomes = _load_outcomes()
    updated = 0

    for signal in pending:
        key = (signal["scan_date"], signal["symbol"])
        result = _assess_signal(signal, today)
        new_status = result["outcome"]

        if new_status == "pending":
            continue  # don't overwrite with pending — leave it as-is

        outcomes[key] = result
        update_outcome_status(signal["symbol"], signal["scan_date"], new_status)
        updated += 1
        logger.debug(
            "outcome_tracker: %s/%s → %s",
            signal["scan_date"], signal["symbol"], new_status,
        )

    _save_outcomes(outcomes)
    logger.info("outcome_tracker: assessed %d signals, %d resolved", len(pending), updated)


# ── Summarize ─────────────────────────────────────────────────────────────────

_WIN_OUTCOMES = {"target_5pct", "target_8pct"}
_LOSS_OUTCOMES = {"stop_hit"}
_EXCLUDED_FROM_RATE = {"pending", "unresolved_no_data"}

# Deduplication constants — must match signal_registry.check_recent() exactly
_DEDUP_LOOKBACK_DAYS = 7
_DEDUP_PRICE_THRESHOLD = 0.03

_OUTCOME_LABELS = {
    "stop_hit": "Stop hit (loss)",
    "target_5pct": "Target +5% (win)",
    "target_8pct": "Target +8% (win)",
    "lateral": "Lateral (sin resolución)",
    "pending": "Pending",
    "unresolved_no_data": "Sin datos",
}


def _is_exposure_duplicate(
    signal: Dict,
    all_signals: List[Dict],
    outcomes_by_key: Dict[Tuple[str, str], Dict],
) -> bool:
    """Return True if signal duplicates an already-open position in the same ticker.

    Three criteria must all hold:
    1. Same ticker appeared within _DEDUP_LOOKBACK_DAYS before this signal.
    2. Entry price moved less than _DEDUP_PRICE_THRESHOLD vs. the prior entry
       (mirrors signal_registry.check_recent — same setup, price hasn't moved).
    3. The prior signal was still pending when this signal was published.

    Criterion 3 is intentionally stricter than check_recent() (which omits it).
    check_recent() detects price-stale signals for visual warnings in reports;
    this function detects capital-exposure overlaps for win-rate accounting.
    A prior signal that already resolved (stop or target) before the new one
    was published represents a genuinely independent trade.
    """
    scan_dt = datetime.strptime(signal["scan_date"], "%Y-%m-%d").date()
    cutoff = scan_dt - timedelta(days=_DEDUP_LOOKBACK_DAYS)
    symbol = signal["symbol"]
    current_entry = signal.get("entry_price_ars")
    if current_entry is None:
        return False

    candidates = [
        s for s in all_signals
        if s["symbol"] == symbol
        and s["scan_date"] < signal["scan_date"]
        and datetime.strptime(s["scan_date"], "%Y-%m-%d").date() >= cutoff
    ]
    if not candidates:
        return False

    candidates.sort(key=lambda r: r["scan_date"], reverse=True)
    prior = candidates[0]
    prior_entry = prior.get("entry_price_ars")
    if prior_entry and abs(current_entry - prior_entry) / prior_entry >= _DEDUP_PRICE_THRESHOLD:
        return False  # price moved enough — genuinely new setup

    # Criterion 3: was the prior signal still pending when this one was published?
    prior_key = (prior["scan_date"], prior["symbol"])
    prior_outcome = outcomes_by_key.get(prior_key)
    if prior_outcome is None:
        return True  # no outcome record → still pending at publication time

    days_to = prior_outcome.get("days_to_outcome")
    if days_to is None:
        # lateral or unresolved_no_data: signal was open for the full 20-day window,
        # so it was definitely pending within any 7-day lookback.
        return True

    prior_scan_dt = datetime.strptime(prior["scan_date"], "%Y-%m-%d").date()
    return scan_dt < prior_scan_dt + timedelta(days=days_to)


def _fmt_rate(wins: int, resolvable: int) -> str:
    """Return 'X% (W/R)' or 'n/a' when no resolvable signals."""
    if resolvable == 0:
        return "n/a"
    return f"{wins / resolvable:.0%} ({wins}/{resolvable})"


def _catalyst_stats(group: List[Dict]) -> tuple:
    """Return (wins, stops, laterals, resolvable, pending) counts for a group."""
    wins      = sum(1 for r in group if r["outcome"] in _WIN_OUTCOMES)
    stops     = sum(1 for r in group if r["outcome"] == "stop_hit")
    laterals  = sum(1 for r in group if r["outcome"] == "lateral")
    pending   = sum(1 for r in group if r["outcome"] in _EXCLUDED_FROM_RATE)
    resolvable = wins + stops + laterals
    return wins, stops, laterals, resolvable, pending


def summarize() -> str:
    """Return a formatted win-rate summary: overall + breakdown by catalyst + temporal view."""
    from analysis.reversal.signal_registry import load_signals
    resolved = list(_load_outcomes().values())
    outcomes_by_key: Dict[Tuple[str, str], Dict] = {
        (r["scan_date"], r["symbol"]): r for r in resolved
    }

    # Add synthetic pending/unresolved records from signals not yet in outcomes
    resolved_keys = {(r["scan_date"], r["symbol"]) for r in resolved}
    signals = load_signals()
    for s in signals:
        key = (s["scan_date"], s["symbol"])
        if key not in resolved_keys:
            resolved.append({
                "scan_date": s["scan_date"],
                "symbol": s["symbol"],
                "outcome": s.get("outcome_status", "pending"),
                "catalysts": s.get("catalysts", []),
                "days_to_outcome": None,
            })

    outcomes = resolved
    if not outcomes:
        return "Sin señales registradas.\n"

    # Build the set of exposure duplicates (excluded from win rate, not from display)
    duplicate_keys = {
        (s["scan_date"], s["symbol"])
        for s in signals
        if _is_exposure_duplicate(s, signals, outcomes_by_key)
    }
    deduped = [r for r in outcomes if (r["scan_date"], r["symbol"]) not in duplicate_keys]

    lines: List[str] = []

    # ── Overall table ─────────────────────────────────────────────────────────
    counts: Dict[str, int] = defaultdict(int)
    days_list: List[int] = []
    for r in outcomes:
        counts[r["outcome"]] += 1
        if r.get("days_to_outcome") is not None:
            days_list.append(r["days_to_outcome"])

    total = len(outcomes)
    dup_count = len(duplicate_keys)
    wins_total, stops_total, laterals_total, resolvable, _ = _catalyst_stats(deduped)
    avg_days = sum(days_list) / len(days_list) if days_list else 0.0

    lines += [
        f"Win Rate — Reversiones (n={total} señales, {dup_count} excluidas como dup. de exposición)",
        "─" * 45,
    ]
    for status, label in _OUTCOME_LABELS.items():
        c = counts.get(status, 0)
        pct = c / total * 100 if total > 0 else 0.0
        lines.append(f"{label:<35}: {c:>3}  ({pct:.0f}%)")
    lines += [
        "─" * 45,
        f"{'Win rate real':<35}: {_fmt_rate(wins_total, resolvable)}   (excluye pending/sin datos/dup. exposición)",
        f"{'Avg días a resolución':<35}: {avg_days:.1f}d",
        "",
    ]

    # ── By-catalyst breakdown — uses deduplicated set ─────────────────────────
    catalyst_groups: Dict[str, List[Dict]] = defaultdict(list)
    for r in deduped:
        cats = r.get("catalysts") or []
        if not cats:
            catalyst_groups["(sin catalizador)"].append(r)
        else:
            for cat in cats:
                catalyst_groups[cat].append(r)

    lines += ["Desglose por catalizador:", "─" * 58]
    lines.append(f"  {'Catalizador':<40} {'n':>3}  {'wins':>4}  {'stops':>5}  {'lat':>3}  win rate")
    lines.append(f"  {'─'*40} {'─'*3}  {'─'*4}  {'─'*5}  {'─'*3}  ─────────────")
    for cat, group in sorted(catalyst_groups.items()):
        wins, stops, laterals, resolvable_g, pending = _catalyst_stats(group)
        caveat = " ⚠ n chico" if len(group) < 5 else ""
        lines.append(
            f"  {cat[:40]:<40} {len(group):>3}  {wins:>4}  {stops:>5}  {laterals:>3}  "
            f"{_fmt_rate(wins, resolvable_g)}{caveat}"
        )
    lines.append(
        "  Nota: 'stops' = pérdida de capital; 'lat' = lateral sin resolución (capital preservado)"
    )
    lines.append("")

    # ── Temporal breakdown: YYYY-MM × catalyst ────────────────────────────────
    # Reveals regime shifts that aggregate numbers hide. MA200 bounce shows
    # 4/4 wins in Jun–early Jul vs 0/10 stops in late Jul–Aug (market regime
    # effect, not a property of the catalyst). Never read aggregate win rates
    # without this view alongside.
    period_cat: Dict[tuple, List[Dict]] = defaultdict(list)
    for r in deduped:
        period = r["scan_date"][:7]  # YYYY-MM
        for cat in (r.get("catalysts") or ["(sin catalizador)"]):
            period_cat[(period, cat)].append(r)

    all_periods = sorted({k[0] for k in period_cat})
    all_cats    = sorted({k[1] for k in period_cat})

    lines += ["Desglose temporal (YYYY-MM × catalizador):", "─" * 58]
    lines.append(
        "  ⚠ Ver evolución temporal antes de leer el agregado — "
        "un régimen de mercado puede dominar el resultado total."
    )
    lines.append(f"  {'período':<9} {'catalizador':<40} {'n':>3}  {'wins':>4}  {'stops':>5}  {'lat':>3}  win rate")
    lines.append(f"  {'─'*9} {'─'*40} {'─'*3}  {'─'*4}  {'─'*5}  {'─'*3}  ─────────────")
    for period in all_periods:
        for cat in all_cats:
            group = period_cat.get((period, cat))
            if not group:
                continue
            wins, stops, laterals, resolvable_g, pending = _catalyst_stats(group)
            lines.append(
                f"  {period:<9} {cat[:40]:<40} {len(group):>3}  {wins:>4}  {stops:>5}  {laterals:>3}  "
                f"{_fmt_rate(wins, resolvable_g)}"
            )
    lines.append("")

    return "\n".join(lines)


# ── Scan-start integration ────────────────────────────────────────────────────

def run_at_scan_start() -> None:
    """Called at the beginning of each scan. Non-blocking: logs and continues on error."""
    try:
        assess_outcomes()
    except Exception as exc:
        logger.warning("outcome_tracker: failed to refresh outcomes — %s", exc)


# ── Standalone entry point ────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    assess_outcomes()
    print(summarize())
