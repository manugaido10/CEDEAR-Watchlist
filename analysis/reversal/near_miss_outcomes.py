"""Hypothetical outcome evaluation for near-miss records (Decision #26).

Uses EXACTLY the same methodology as outcome_tracker (_assess_signal, _is_exposure_duplicate)
so near-miss win rates are directly comparable to published-signal win rates.

Writes data/reversal_tracking/near_miss_outcomes.jsonl and produces a gate-by-gate
comparison report via compare_by_gate().

Standalone:
    python -m analysis.reversal.near_miss_outcomes
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

NEAR_MISS_OUTCOMES_PATH = Path("data/reversal_tracking/near_miss_outcomes.jsonl")

_DEDUP_LOOKBACK_DAYS = 7
_DEDUP_PRICE_THRESHOLD = 0.03
_WIN_OUTCOMES = {"target_5pct", "target_8pct"}
_LOSS_OUTCOMES = {"stop_hit"}
_EXCLUDED_FROM_RATE = {"pending", "unresolved_no_data"}


# ── I/O ───────────────────────────────────────────────────────────────────────

def _load_near_miss_outcomes() -> Dict[Tuple[str, str], Dict]:
    """Returns {(scan_date, symbol): record}."""
    if not NEAR_MISS_OUTCOMES_PATH.exists():
        return {}
    result = {}
    for line in NEAR_MISS_OUTCOMES_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                r = json.loads(line)
                result[(r["scan_date"], r["symbol"])] = r
            except (json.JSONDecodeError, KeyError):
                logger.warning("near_miss_outcomes: skipping malformed line")
    return result


def _save_near_miss_outcomes(outcomes: Dict[Tuple[str, str], Dict]) -> None:
    NEAR_MISS_OUTCOMES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with NEAR_MISS_OUTCOMES_PATH.open("w", encoding="utf-8") as f:
        for r in outcomes.values():
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


# ── Dedup (adapted from outcome_tracker._is_exposure_duplicate) ───────────────

def _is_near_miss_exposure_duplicate(
    record: Dict,
    all_near_misses: List[Dict],
    outcomes_by_key: Dict[Tuple[str, str], Dict],
) -> bool:
    """Return True if record duplicates an already-open near-miss for the same ticker.

    Same criteria as outcome_tracker._is_exposure_duplicate:
    1. Same ticker within _DEDUP_LOOKBACK_DAYS.
    2. Price moved < _DEDUP_PRICE_THRESHOLD vs. prior entry.
    3. Prior record still pending (within its 20-day window) at this scan_date.

    Dedup is cross-gate: the same ticker on back-to-back days counts once
    regardless of whether the gate label changed between scans.
    """
    from analysis.reversal.outcome_tracker import _MAX_DAYS

    scan_dt = datetime.strptime(record["scan_date"], "%Y-%m-%d").date()
    cutoff = scan_dt - timedelta(days=_DEDUP_LOOKBACK_DAYS)
    symbol = record["symbol"]
    current_entry = record.get("entry_price_ars")
    if current_entry is None:
        return False

    candidates = [
        r for r in all_near_misses
        if r["symbol"] == symbol
        and r["scan_date"] < record["scan_date"]
        and datetime.strptime(r["scan_date"], "%Y-%m-%d").date() >= cutoff
        and r.get("entry_price_ars") is not None
    ]
    if not candidates:
        return False

    candidates.sort(key=lambda r: r["scan_date"], reverse=True)
    prior = candidates[0]
    prior_entry = prior.get("entry_price_ars")
    if prior_entry and abs(current_entry - prior_entry) / prior_entry >= _DEDUP_PRICE_THRESHOLD:
        return False

    prior_key = (prior["scan_date"], prior["symbol"])
    prior_outcome = outcomes_by_key.get(prior_key)
    if prior_outcome is None:
        return True

    days_to = prior_outcome.get("days_to_outcome")
    if days_to is None:
        return True

    prior_scan_dt = datetime.strptime(prior["scan_date"], "%Y-%m-%d").date()
    return scan_dt < prior_scan_dt + timedelta(days=days_to)


# ── Assessment ────────────────────────────────────────────────────────────────

def assess_near_miss_outcomes() -> None:
    """Evaluate hypothetical outcomes for all near-misses with reconstructed entry.

    Uses outcome_tracker._assess_signal directly — same logic, same constants.
    Only processes records where entry_price_ars and invalidation_level_ars are set.
    Idempotent: re-assesses all records on each run (same as outcome_tracker).
    """
    from analysis.reversal.near_miss_tracker import load_near_misses
    from analysis.reversal.outcome_tracker import _assess_signal

    records = load_near_misses()
    reconstructible = [
        r for r in records
        if r.get("entry_price_ars") is not None
        and r.get("invalidation_level_ars") is not None
    ]

    if not reconstructible:
        logger.info("near_miss_outcomes: 0 reconstructible records — nothing to assess")
        return

    today = datetime.today().date()
    outcomes: Dict[Tuple[str, str], Dict] = {}

    resolved = 0
    pending_count = 0
    for r in reconstructible:
        try:
            result = _assess_signal(r, today)
        except Exception as exc:
            logger.warning(
                "near_miss_outcomes: %s/%s assessment failed (%s) — unresolved_no_data",
                r["scan_date"], r["symbol"], exc,
            )
            result = {
                "scan_date": r["scan_date"],
                "symbol": r["symbol"],
                "assessed_at": str(today),
                "entry_price_ars": r.get("entry_price_ars"),
                "invalidation_level_ars": r.get("invalidation_level_ars"),
                "catalysts": [],
                "outcome": "unresolved_no_data",
                "days_to_outcome": None,
                "exit_price_ars": None,
                "pct_change": None,
            }

        result["failed_criteria"] = r.get("failed_criteria", [])
        key = (r["scan_date"], r["symbol"])
        outcomes[key] = result

        if result["outcome"] == "pending":
            pending_count += 1
        else:
            resolved += 1

    _save_near_miss_outcomes(outcomes)
    logger.info(
        "near_miss_outcomes: assessed %d records — %d resolved, %d still pending",
        len(reconstructible), resolved, pending_count,
    )


# ── Comparison report ─────────────────────────────────────────────────────────

def _fmt_rate(wins: int, resolvable: int) -> str:
    if resolvable == 0:
        return "n/a"
    return f"{wins / resolvable:.0%} ({wins}/{resolvable})"


def _gate_stats(
    group: List[Dict],
) -> Tuple[int, int, int, int, int]:
    """Return (wins, stops, laterals, resolvable, pending_or_unresolved)."""
    wins     = sum(1 for r in group if r["outcome"] in _WIN_OUTCOMES)
    stops    = sum(1 for r in group if r["outcome"] in _LOSS_OUTCOMES)
    laterals = sum(1 for r in group if r["outcome"] == "lateral")
    excl     = sum(1 for r in group if r["outcome"] in _EXCLUDED_FROM_RATE)
    return wins, stops, laterals, wins + stops + laterals, excl


def _pct_stats(group: List[Dict]) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """Return (avg_win_pct, avg_loss_pct, ev_pct) as percentages (0-100).

    avg_win: mean pct_change of records with outcome in _WIN_OUTCOMES.
    avg_loss: mean pct_change of records with outcome in _LOSS_OUTCOMES (negative).
    ev: (win_rate × avg_win) + ((1 − win_rate) × avg_loss), with win_rate over
        resolvable = wins+stops+laterals. Returns None for any field lacking data.
    """
    wins_pct  = [r["pct_change"] for r in group
                 if r["outcome"] in _WIN_OUTCOMES and r.get("pct_change") is not None]
    stops_pct = [r["pct_change"] for r in group
                 if r["outcome"] in _LOSS_OUTCOMES and r.get("pct_change") is not None]
    laterals  = sum(1 for r in group if r["outcome"] == "lateral")
    resolvable = len(wins_pct) + len(stops_pct) + laterals

    avg_win  = (sum(wins_pct) / len(wins_pct)) * 100 if wins_pct else None
    avg_loss = (sum(stops_pct) / len(stops_pct)) * 100 if stops_pct else None

    if resolvable == 0 or avg_win is None or avg_loss is None:
        ev = None
    else:
        wr = len(wins_pct) / resolvable
        ev = wr * avg_win + (1 - wr) * avg_loss
    return avg_win, avg_loss, ev


def _fmt_pct(v: Optional[float]) -> str:
    return f"{v:+.2f}%" if v is not None else "   n/a"


def _is_safe(record: Dict) -> bool:
    """Safe = record was not exposed to the cache-freshness bug (DECISIONS.md #27).

    Per Decision #27, only non-safe records got the price_staleness_risk field
    populated; safe records were left without it. Records written post-fix
    (2026-09-02) also lack the field. Both cases are treated as safe.
    """
    risk = record.get("price_staleness_risk")
    return risk is None or risk == "safe"


def _compute_gate_groups(
    filter_safe_only: bool,
) -> Tuple[List[Dict], Dict[str, List[Dict]], int]:
    """Single source of truth for "near-miss outcomes filtered + deduped + grouped".

    Returns (raw_records, gate_groups, n_after_dedup):
    - raw_records: near-miss records after optional safe-only filtering.
    - gate_groups: {gate_name → list of deduped outcome records}.
    - n_after_dedup: total count of deduped outcome records.

    Consumers (compare_by_gate, log_safe_only_calibration_progress) must not
    re-implement the safe filter or the dedup — any change here propagates to both.
    """
    from analysis.reversal.near_miss_tracker import load_near_misses

    raw_records = load_near_misses()
    if filter_safe_only:
        raw_records = [r for r in raw_records if _is_safe(r)]
    nm_outcomes = _load_near_miss_outcomes()
    if filter_safe_only:
        safe_keys = {(r["scan_date"], r["symbol"]) for r in raw_records}
        nm_outcomes = {k: v for k, v in nm_outcomes.items() if k in safe_keys}

    nm_outcome_list = list(nm_outcomes.values())
    all_nm_with_entry = [
        rr for rr in raw_records if rr.get("entry_price_ars") is not None
    ]
    entry_by_key = {
        (rr["scan_date"], rr["symbol"]): rr["entry_price_ars"]
        for rr in all_nm_with_entry
    }
    nm_duplicate_keys: Set[Tuple[str, str]] = set()
    for r in nm_outcome_list:
        enriched = {
            **r,
            "entry_price_ars": entry_by_key.get((r["scan_date"], r["symbol"])),
        }
        if _is_near_miss_exposure_duplicate(enriched, all_nm_with_entry, nm_outcomes):
            nm_duplicate_keys.add((r["scan_date"], r["symbol"]))

    nm_deduped = [
        r for r in nm_outcome_list
        if (r["scan_date"], r["symbol"]) not in nm_duplicate_keys
    ]

    gate_groups: Dict[str, List[Dict]] = defaultdict(list)
    for r in nm_deduped:
        for gate in r.get("failed_criteria", ["unknown"]):
            gate_groups[gate].append(r)

    return raw_records, gate_groups, len(nm_deduped)


def compare_by_gate(filter_safe_only: bool = False) -> str:
    """Return a formatted comparison: near-miss win rates by gate vs. published signals.

    When filter_safe_only=True, restricts both corpora to records that were NOT
    exposed to the cache-freshness bug (DECISIONS.md #27) before deduplication.
    """
    from analysis.reversal.outcome_tracker import (
        _load_outcomes, _is_exposure_duplicate, summarize,
    )
    from analysis.reversal.signal_registry import load_signals

    # ── Near-miss side ────────────────────────────────────────────────────────
    raw_records, gate_groups, n_after_dedup = _compute_gate_groups(filter_safe_only)
    total_raw = len(raw_records)
    reconstructible_raw = sum(
        1 for r in raw_records if r.get("entry_price_ars") is not None
    )
    excluded_no_support = sum(
        1 for r in raw_records
        if r.get("reconstruction_skip_reason") == "no_support_within_5pct"
    )
    excluded_invalid_stop = sum(
        1 for r in raw_records
        if r.get("reconstruction_skip_reason") == "invalid_reconstruction_stop_above_entry"
    )
    excluded_no_yfinance = sum(
        1 for r in raw_records
        if r.get("reconstruction_skip_reason") == "yfinance_no_data"
    )

    # ── Published-signal side ─────────────────────────────────────────────────
    pub_outcomes_by_key = _load_outcomes()
    signals = load_signals()
    if filter_safe_only:
        signals = [s for s in signals if _is_safe(s)]
        safe_sig_keys = {(s["scan_date"], s["symbol"]) for s in signals}
        pub_outcomes_by_key = {
            k: v for k, v in pub_outcomes_by_key.items() if k in safe_sig_keys
        }
    pub_outcomes_list = list(pub_outcomes_by_key.values())
    pub_duplicate_keys = {
        (s["scan_date"], s["symbol"])
        for s in signals
        if _is_exposure_duplicate(s, signals, pub_outcomes_by_key)
    }
    pub_deduped = [
        r for r in pub_outcomes_list
        if (r["scan_date"], r["symbol"]) not in pub_duplicate_keys
    ]
    pub_wins, pub_stops, pub_lat, pub_resolvable, pub_excl = _gate_stats(pub_deduped)
    pub_avg_win, pub_avg_loss, pub_ev = _pct_stats(pub_deduped)

    # ── Render ────────────────────────────────────────────────────────────────
    header_title = "Near-Miss Outcomes — comparación con señales publicadas"
    if filter_safe_only:
        header_title += "  [SAFE-ONLY: sin registros del bug de cache freshness]"
    lines: List[str] = [
        header_title,
        "═" * 60,
        f"Corpus raw: {total_raw}  |  reconstructible: {reconstructible_raw}"
        f"  |  after dedup: {n_after_dedup}",
        f"Excluidos: no_support={excluded_no_support}"
        f"  yfinance_sin_datos={excluded_no_yfinance}"
        f"  stop_sobre_entry={excluded_invalid_stop}",
        "",
        f"{'Gate':<26} {'n_raw':>5}  {'n_dedup':>7}  {'wins':>4}  {'stops':>5}  {'lat':>3}  "
        f"{'pending':>7}  {'win_rate':<15}  {'avg_win':>8}  {'avg_loss':>8}  {'ev':>8}",
        "─" * 115,
    ]

    gate_order = [
        "rsi_out_of_range",
        "no_catalyst",
        "weekly_trend_negative",
        "vol_ratio_high",
        "no_support_within_5pct",
    ]
    # Collect raw counts per gate (before dedup)
    raw_gate_counts: Dict[str, int] = defaultdict(int)
    for r in raw_records:
        for gate in r.get("failed_criteria", []):
            raw_gate_counts[gate] += 1

    for gate in gate_order:
        n_raw = raw_gate_counts.get(gate, 0)
        if gate == "no_support_within_5pct":
            lines.append(
                f"  {gate:<24} {n_raw:>5}  {'—':>7}  {'—':>4}  {'—':>5}  {'—':>3}  {'—':>7}  "
                f"{'(excluidos — sin soporte)':<15}  {'—':>8}  {'—':>8}  {'—':>8}"
            )
            continue
        group = gate_groups.get(gate, [])
        wins, stops, lat, resolvable, excl = _gate_stats(group)
        avg_win, avg_loss, ev = _pct_stats(group)
        caveat = " ⚠" if len(group) < 5 else ""
        lines.append(
            f"  {gate:<24} {n_raw:>5}  {len(group):>7}  {wins:>4}  {stops:>5}  {lat:>3}  {excl:>7}  "
            f"{_fmt_rate(wins, resolvable):<15}  {_fmt_pct(avg_win):>8}  {_fmt_pct(avg_loss):>8}  {_fmt_pct(ev):>8}"
            f"{caveat}"
        )

    lines += [
        "─" * 115,
        "",
        f"{'Señales publicadas (all gates):':<26} {'n_raw':>5}  {'n_dedup':>7}  {'wins':>4}  {'stops':>5}  {'lat':>3}  "
        f"{'pending':>7}  {'win_rate':<15}  {'avg_win':>8}  {'avg_loss':>8}  {'ev':>8}",
        "─" * 115,
        f"  {'(publicadas)':<24} {len(pub_outcomes_list):>5}  {len(pub_deduped):>7}  "
        f"{pub_wins:>4}  {pub_stops:>5}  {pub_lat:>3}  {pub_excl:>7}  "
        f"{_fmt_rate(pub_wins, pub_resolvable):<15}  "
        f"{_fmt_pct(pub_avg_win):>8}  {_fmt_pct(pub_avg_loss):>8}  {_fmt_pct(pub_ev):>8}",
        "─" * 115,
        "",
        "⚠  Advertencia metodológica (Decision #26):",
        "   Los near-misses son una muestra condicionada — están cerca del umbral por",
        "   definición. Un gate que rechazó near-misses que 'hubieran ganado' NO implica",
        "   directamente que haya que aflojarlo: mover el umbral genera una nueva población",
        "   de near-misses en el borde nuevo. Evidencia direccional, no regla automática.",
    ]

    return "\n".join(lines)


# ── Calibration progress log (Decision #27b) ──────────────────────────────────

_CALIBRATION_DIRECTIONAL_FLOOR = 15
_CALIBRATION_FLOOR = 40
_CALIBRATION_GATES = ("rsi_out_of_range", "no_catalyst")


def _floor_message(n: int) -> str:
    if n < _CALIBRATION_DIRECTIONAL_FLOOR:
        return (
            f"{n}/{_CALIBRATION_FLOOR} — por debajo de ambos pisos "
            f"(n<{_CALIBRATION_DIRECTIONAL_FLOOR} lectura direccional, "
            f"n<{_CALIBRATION_FLOOR} calibración)"
        )
    if n < _CALIBRATION_FLOOR:
        return (
            f"{n}/{_CALIBRATION_FLOOR} — supera piso de lectura direccional "
            f"(n≥{_CALIBRATION_DIRECTIONAL_FLOOR}), falta para calibración "
            f"(n≥{_CALIBRATION_FLOOR})"
        )
    return f"{n}/{_CALIBRATION_FLOOR} — supera piso de calibración (n≥{_CALIBRATION_FLOOR})"


def log_safe_only_calibration_progress() -> None:
    """Log safe-only n_resolvable per calibration gate vs. floors (Decision #27b).

    Re-assesses outcomes first so pendings that vencieron this week are counted.
    Non-blocking: any failure logs a warning and returns without crashing the
    scan (same pattern as analyst_revision and news_check integrations).
    Only logs counts, never EV — Decision #27b constraint to avoid inducing
    early reads of an underpowered number.
    """
    try:
        assess_near_miss_outcomes()
    except Exception as exc:
        logger.warning(
            "log_safe_only_calibration_progress: assess_near_miss_outcomes failed "
            "(%s: %s) — skipping calibration progress log for this run",
            type(exc).__name__, exc,
        )
        return

    try:
        _raw, gate_groups, _n = _compute_gate_groups(filter_safe_only=True)

        logger.info("Progreso de calibración safe-only (Decision #27b):")
        for gate in _CALIBRATION_GATES:
            _w, _s, _l, resolvable, _e = _gate_stats(gate_groups.get(gate, []))
            logger.info("  %s: %s", gate, _floor_message(resolvable))
    except Exception as exc:
        logger.warning(
            "log_safe_only_calibration_progress: reporting failed "
            "(%s: %s) — scan continues normally",
            type(exc).__name__, exc,
        )


# ── Standalone ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Near-miss outcome comparison.")
    parser.add_argument(
        "--safe-only",
        action="store_true",
        help="Restrict corpus to records not exposed to the cache-freshness bug (DECISIONS.md #27).",
    )
    parser.add_argument(
        "--skip-assess",
        action="store_true",
        help="Skip the re-assessment step and only print the comparison report.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    if not args.skip_assess:
        assess_near_miss_outcomes()
    print(compare_by_gate(filter_safe_only=args.safe_only))
