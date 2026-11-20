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
import math
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

# Entry-bar instrumentation (Fase B2). Legacy signals without data_date are
# matched by entry_price_ars against the history closes. Only the last
# ENTRY_CLOSE_MATCH_LOOKBACK_BARS bars on/before scan_date are candidates;
# exactly one must match within ENTRY_CLOSE_MATCH_REL_TOL (relative), else the
# entry bar is left null. Note: fetch_prices uses auto_adjust=True, so a
# dividend after the entry bar rescales historical closes and the match fails
# closed (entry_bar_close_ars exposes that basis drift when data_date is known).
ENTRY_CLOSE_MATCH_REL_TOL = 0.001
ENTRY_CLOSE_MATCH_LOOKBACK_BARS = 5

ENTRY_SOURCE_DATA_DATE = "data_date"
ENTRY_SOURCE_CLOSE_MATCH = "close_match"
ENTRY_SOURCE_UNMATCHED = "unmatched"
ENTRY_SOURCE_AMBIGUOUS = "ambiguous"
ENTRY_SOURCE_NO_HISTORY = "no_history"


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
    """Single network fetch per signal: the FULL, unfiltered price history.

    Returns a sorted DataFrame with the available [open, low, close] columns,
    or None if the ticker has no data at all. The ``index > scan_date`` filter
    that defines the measurement window is applied by _assess_signal; the
    unfiltered frame is also needed to read the entry bar and the first bar
    after it (Fase B2), which that filter excludes.

    scan_date is kept in the signature for the patch seam used by tests.
    """
    from data.prices import fetch_prices
    df = fetch_prices(symbol)
    if df is None or df.empty or "close" not in df.columns:
        return None
    df = df.sort_index()
    cols = [c for c in ["open", "close", "low"] if c in df.columns]
    return df[cols]


def _after_scan(history: pd.DataFrame, scan_date: str) -> Optional[pd.DataFrame]:
    """Bars strictly after scan_date (the existing measurement window)."""
    after = history[history.index > pd.Timestamp(scan_date)]
    return None if after.empty else after


# ── Entry-bar instrumentation (Fase B2) ───────────────────────────────────────

ENTRY_BAR_FIELDS = (
    "entry_bar_date",
    "entry_bar_date_source",
    "entry_bar_close_ars",
    "next_open_ars",
    "entry_gap_pct",
    "entry_gap_through_stop",
)


def empty_entry_bar_fields() -> Dict:
    return {k: None for k in ENTRY_BAR_FIELDS}


def _match_entry_bar(
    history: pd.DataFrame,
    scan_date: str,
    entry: float,
) -> Tuple[Optional[pd.Timestamp], str]:
    """Locate the bar whose close produced entry_price_ars (legacy signals)."""
    window = history[history.index <= pd.Timestamp(scan_date)].tail(
        ENTRY_CLOSE_MATCH_LOOKBACK_BARS
    )
    closes = window["close"].astype(float)
    hits = closes[(closes / entry - 1.0).abs() <= ENTRY_CLOSE_MATCH_REL_TOL]
    if len(hits) == 1:
        return pd.Timestamp(hits.index[0]), ENTRY_SOURCE_CLOSE_MATCH
    if len(hits) > 1:
        return None, ENTRY_SOURCE_AMBIGUOUS
    return None, ENTRY_SOURCE_UNMATCHED


def _entry_bar_fields(signal: Dict, history: Optional[pd.DataFrame]) -> Dict:
    """entry_bar_date, next_open_ars, entry_gap_pct, entry_gap_through_stop.

    - entry_bar_date: signal's data_date when present; otherwise matched by
      close (see ENTRY_CLOSE_MATCH_*); null when unmatched/ambiguous.
    - entry_bar_date_source: how entry_bar_date was obtained (or why it is null).
    - entry_bar_close_ars: close of that bar in the fetched (adjusted) history.
    - next_open_ars: open of the first bar after entry_bar_date — the first
      fill a real order could get. Null until that bar exists.
    - entry_gap_pct = next_open / entry_price_ars − 1.
    - entry_gap_through_stop = next_open <= invalidation_level_ars.
    Read from the unfiltered history: that bar is excluded by ``> scan_date``.
    """
    out = empty_entry_bar_fields()
    entry = signal.get("entry_price_ars")
    invalidation = signal.get("invalidation_level_ars")
    data_date = signal.get("data_date")

    if data_date:
        bar_ts: Optional[pd.Timestamp] = pd.Timestamp(data_date)
        source = ENTRY_SOURCE_DATA_DATE
    elif history is None:
        out["entry_bar_date_source"] = ENTRY_SOURCE_NO_HISTORY
        return out
    elif not entry:
        out["entry_bar_date_source"] = ENTRY_SOURCE_UNMATCHED
        return out
    else:
        bar_ts, source = _match_entry_bar(history, signal["scan_date"], float(entry))

    out["entry_bar_date_source"] = source
    if bar_ts is None:
        return out
    out["entry_bar_date"] = bar_ts.date().isoformat()
    if history is None:
        return out

    if bar_ts in history.index:
        bar_close = float(history.loc[bar_ts, "close"])
        if math.isfinite(bar_close):
            out["entry_bar_close_ars"] = round(bar_close, 2)

    if "open" not in history.columns:
        return out
    after = history[history.index > bar_ts]
    if after.empty:
        return out
    next_open = float(after["open"].iloc[0])
    if not math.isfinite(next_open) or next_open <= 0:
        return out
    out["next_open_ars"] = round(next_open, 2)
    if entry:
        out["entry_gap_pct"] = round(next_open / float(entry) - 1.0, 4)
    if invalidation is not None:
        out["entry_gap_through_stop"] = bool(next_open <= float(invalidation))
    return out


# ── Single-signal assessment ──────────────────────────────────────────────────

def _assess_signal(signal: Dict, today: datetime.date) -> Dict:
    """Determine outcome for a single signal record. Returns outcome record.

    R-multiple (Decision #31 / Roadmap Fase A1) is populated on any outcome
    that has an exit price — including lateral, using the close at the
    deadline (or the last bar seen inside the window). pct_change stays null
    on lateral to preserve historical semantics.
    """
    from analysis.reversal.r_multiple import compute_r_multiple

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
        "exit_price_ars_at_deadline": None,
        "r_multiple": None,
        "r_multiple_skip_reason": None,
        **empty_entry_bar_fields(),
    }

    def _annotate_r(exit_used: Optional[float]) -> None:
        r, reason = compute_r_multiple(entry, invalidation, exit_used)
        base["r_multiple"] = round(r, 4) if r is not None else None
        base["r_multiple_skip_reason"] = reason

    if entry is None or invalidation is None:
        base["outcome"] = "unresolved_no_data"
        _annotate_r(None)
        return base

    history = _fetch_price_history(symbol, scan_date)  # the only fetch
    base.update(_entry_bar_fields(signal, history))
    price_df = _after_scan(history, scan_date) if history is not None else None
    if price_df is None:
        # Distinguish: no ticker data at all (permanent) vs no bars yet after
        # scan_date (transient — market not closed, wait for next run).
        has_any_data = history is not None
        if not has_any_data or today >= deadline:
            base["outcome"] = "unresolved_no_data"
        # else: remains "pending" — will resolve on a future run
        _annotate_r(None)
        return base

    has_low = "low" in price_df.columns
    last_close_in_window: Optional[float] = None

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
        last_close_in_window = close

        # Stop first — uses intraday low
        if low < invalidation:
            base.update({
                "outcome": "stop_hit",
                "days_to_outcome": days_elapsed,
                "exit_price_ars": round(low, 2),
                "pct_change": round((low - entry) / entry, 4),
            })
            _annotate_r(low)
            return base

        # Targets — use daily close
        if close > entry * (1 + _TARGET_PCTS[1]):
            base.update({
                "outcome": "target_8pct",
                "days_to_outcome": days_elapsed,
                "exit_price_ars": round(close, 2),
                "pct_change": round((close - entry) / entry, 4),
            })
            _annotate_r(close)
            return base

        if close > entry * (1 + _TARGET_PCTS[0]):
            base.update({
                "outcome": "target_5pct",
                "days_to_outcome": days_elapsed,
                "exit_price_ars": round(close, 2),
                "pct_change": round((close - entry) / entry, 4),
            })
            _annotate_r(close)
            return base

    # Deadline reached without resolution
    if today >= deadline:
        base["outcome"] = "lateral"
        # Lateral: capture the last close in-window as deadline exit price.
        # pct_change stays null (preserves historical semantics — see Decision #31).
        if last_close_in_window is not None:
            base["exit_price_ars_at_deadline"] = round(last_close_in_window, 2)
            _annotate_r(last_close_in_window)
        else:
            _annotate_r(None)
    else:
        # Still within window → remains "pending", no R yet.
        _annotate_r(None)

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
    pending = [s for s in signals
               if s.get("outcome_status") in _PENDING_STATUSES
               and s.get("tradeable", True)]

    if not pending:
        logger.info("outcome_tracker: 0 pending signals in evaluation window — nothing to assess")
        return

    today = datetime.today().date()
    outcomes = _load_outcomes()
    updated = 0
    still_pending = 0

    for signal in pending:
        key = (signal["scan_date"], signal["symbol"])
        try:
            result = _assess_signal(signal, today)
        except Exception as exc:
            logger.warning(
                "outcome_tracker: %s/%s — assessment failed (%s: %s); marked unresolved_no_data",
                signal["scan_date"], signal["symbol"],
                type(exc).__name__, exc,
            )
            result = {
                "scan_date": signal["scan_date"],
                "symbol": signal["symbol"],
                "assessed_at": str(today),
                "entry_price_ars": signal.get("entry_price_ars"),
                "invalidation_level_ars": signal.get("invalidation_level_ars"),
                "catalysts": signal.get("catalysts", []),
                "outcome": "unresolved_no_data",
                "days_to_outcome": None,
                "exit_price_ars": None,
                "pct_change": None,
                "exit_price_ars_at_deadline": None,
                "r_multiple": None,
                "r_multiple_skip_reason": "no_exit_data",
                **empty_entry_bar_fields(),
            }
        new_status = result["outcome"]

        if new_status == "pending":
            still_pending += 1
            continue  # don't overwrite with pending — leave it as-is

        outcomes[key] = result
        update_outcome_status(signal["symbol"], signal["scan_date"], new_status)
        updated += 1
        logger.debug(
            "outcome_tracker: %s/%s → %s",
            signal["scan_date"], signal["symbol"], new_status,
        )

        # Auto-close paper position to keep positions_log self-consistent (#28).
        # Fails silently for pre-paper-tracking signals that have no open position.
        _close_reason = (
            "stop" if new_status == "stop_hit"
            else "target" if new_status.startswith("target_")
            else "manual"
        )
        try:
            from data.positions_log import close_position
            close_position(symbol=signal["symbol"], date=str(today), reason=_close_reason)
            logger.debug(
                "outcome_tracker: paper position closed for %s (%s)",
                signal["symbol"], _close_reason,
            )
        except ValueError:
            pass  # no open position — pre-paper-tracking signal
        except Exception as exc:
            logger.warning(
                "outcome_tracker: could not close paper position for %s — %s",
                signal["symbol"], exc,
            )

    _save_outcomes(outcomes)
    logger.info(
        "outcome_tracker: assessed %d signals, %d resolved; %d still pending in window",
        len(pending), updated, still_pending,
    )


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
        logger.error(
            "outcome_tracker: unexpected failure in run_at_scan_start (%s)",
            type(exc).__name__,
            exc_info=True,
        )


# ── Standalone entry point ────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    assess_outcomes()
    print(summarize())
