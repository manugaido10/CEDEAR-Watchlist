"""Ad-hoc: win-rate breakdown por catalizador y tipo de soporte.

Usa la misma lógica de deduplicación que outcome_tracker._is_exposure_duplicate().
support_type viene de signals.jsonl (no está en outcomes.jsonl).

Run: python scripts/adhoc_catalyst_breakdown.py
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple

OUTCOMES_PATH = Path("data/reversal_tracking/outcomes.jsonl")
SIGNALS_PATH  = Path("data/reversal_tracking/signals.jsonl")

WIN_OUTCOMES  = {"target_5pct", "target_8pct"}
LOSS_OUTCOMES = {"stop_hit"}
EXCLUDED      = {"pending", "unresolved_no_data"}

DEDUP_LOOKBACK = 7
DEDUP_PRICE_TH = 0.03


def load_jsonl(path: Path) -> List[Dict]:
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def is_exposure_duplicate(signal, all_signals, outcomes_by_key) -> bool:
    scan_dt = datetime.strptime(signal["scan_date"], "%Y-%m-%d").date()
    cutoff  = scan_dt - timedelta(days=DEDUP_LOOKBACK)
    symbol  = signal["symbol"]
    entry   = signal.get("entry_price_ars")
    if entry is None:
        return False

    candidates = [
        s for s in all_signals
        if s["symbol"] == symbol
        and s["scan_date"] < signal["scan_date"]
        and datetime.strptime(s["scan_date"], "%Y-%m-%d").date() >= cutoff
    ]
    if not candidates:
        return False

    prior = sorted(candidates, key=lambda r: r["scan_date"], reverse=True)[0]
    prior_entry = prior.get("entry_price_ars")
    if prior_entry and abs(entry - prior_entry) / prior_entry >= DEDUP_PRICE_TH:
        return False

    prior_key     = (prior["scan_date"], prior["symbol"])
    prior_outcome = outcomes_by_key.get(prior_key)
    if prior_outcome is None:
        return True

    days_to = prior_outcome.get("days_to_outcome")
    if days_to is None:
        return True

    prior_scan_dt = datetime.strptime(prior["scan_date"], "%Y-%m-%d").date()
    return scan_dt < prior_scan_dt + timedelta(days=days_to)


def rate_str(wins: int, resolvable: int) -> str:
    if resolvable == 0:
        return "n/a"
    return f"{wins}/{resolvable} = {wins/resolvable:.0%}"


def group_stats(records: List[Dict]) -> Tuple[int, int, int]:
    """Returns (wins, losses, resolvable)."""
    wins       = sum(1 for r in records if r["outcome"] in WIN_OUTCOMES)
    losses     = sum(1 for r in records if r["outcome"] in LOSS_OUTCOMES)
    resolvable = sum(1 for r in records if r["outcome"] not in EXCLUDED)
    return wins, losses, resolvable


def main() -> None:
    signals  = load_jsonl(SIGNALS_PATH)
    outcomes = load_jsonl(OUTCOMES_PATH)

    outcomes_by_key: Dict[Tuple[str, str], Dict] = {
        (r["scan_date"], r["symbol"]): r for r in outcomes
    }

    # Build enriched records: outcome fields + support_type from signals
    signal_meta: Dict[Tuple[str, str], Dict] = {
        (s["scan_date"], s["symbol"]): s for s in signals
    }

    # Merge all signal keys → outcome record (use pending if not in outcomes yet)
    all_records: List[Dict] = []
    for s in signals:
        key = (s["scan_date"], s["symbol"])
        if key in outcomes_by_key:
            r = dict(outcomes_by_key[key])
        else:
            r = {
                "scan_date": s["scan_date"],
                "symbol": s["symbol"],
                "outcome": s.get("outcome_status", "pending"),
                "catalysts": s.get("catalysts", []),
                "days_to_outcome": None,
                "pct_change": None,
                "entry_price_ars": s.get("entry_price_ars"),
            }
        r["support_type"] = s.get("support_type", "unknown")
        all_records.append(r)

    # Build signals list with entry_price_ars (needed for dedup)
    signals_with_entry = []
    for s in signals:
        key = (s["scan_date"], s["symbol"])
        entry = s.get("entry_price_ars") or outcomes_by_key.get(key, {}).get("entry_price_ars")
        sc = dict(s)
        sc["entry_price_ars"] = entry
        signals_with_entry.append(sc)

    # Identify duplicates
    dup_keys = {
        (s["scan_date"], s["symbol"])
        for s in signals_with_entry
        if is_exposure_duplicate(s, signals_with_entry, outcomes_by_key)
    }

    deduped = [r for r in all_records if (r["scan_date"], r["symbol"]) not in dup_keys]

    print(f"\n{'='*55}")
    print(f"Análisis por catalizador y soporte  —  {len(all_records)} señales totales")
    print(f"{len(dup_keys)} excluidas como duplicado de exposición → {len(deduped)} señales deduplicadas")
    print(f"{'='*55}\n")

    # ── 1. Por catalizador ────────────────────────────────────────────────────
    cat_groups: Dict[str, List[Dict]] = defaultdict(list)
    for r in deduped:
        for cat in (r.get("catalysts") or ["(sin catalizador)"]):
            cat_groups[cat].append(r)

    print("1. Win rate por catalizador")
    print("-" * 45)
    for cat, group in sorted(cat_groups.items()):
        wins, losses, resolvable = group_stats(group)
        pending = sum(1 for r in group if r["outcome"] in EXCLUDED)
        print(f"  {cat}")
        print(f"    n={len(group)}  resolvable={resolvable}  win={rate_str(wins, resolvable)}  loss={losses}  pending/sin datos={pending}")
    print()

    # ── 2. Por tipo de soporte ────────────────────────────────────────────────
    sup_groups: Dict[str, List[Dict]] = defaultdict(list)
    for r in deduped:
        sup_groups[r["support_type"]].append(r)

    print("2. Win rate por tipo de soporte")
    print("-" * 45)
    for sup, group in sorted(sup_groups.items()):
        wins, losses, resolvable = group_stats(group)
        pending = sum(1 for r in group if r["outcome"] in EXCLUDED)
        print(f"  {sup}")
        print(f"    n={len(group)}  resolvable={resolvable}  win={rate_str(wins, resolvable)}  loss={losses}  pending/sin datos={pending}")
    print()

    # ── 3. Combo: RSI divergence ∩ swing_low ─────────────────────────────────
    RSI_CAT    = "RSI bullish divergence"
    MA200_CAT  = "MA200 bounce/proximity"
    SWING_SUP  = "swing_low"
    MA200_SUP  = "MA200"

    def has_cat(r: Dict, cat: str) -> bool:
        return cat in (r.get("catalysts") or [])

    combo_rsi_swing   = [r for r in deduped if has_cat(r, RSI_CAT)   and r["support_type"] == SWING_SUP]
    combo_ma200_ma200 = [r for r in deduped if has_cat(r, MA200_CAT) and r["support_type"] == MA200_SUP]
    only_rsi          = [r for r in deduped if has_cat(r, RSI_CAT)   and r["support_type"] != SWING_SUP]
    only_swing        = [r for r in deduped if not has_cat(r, RSI_CAT) and r["support_type"] == SWING_SUP]

    print("3. Cruce catalizador × soporte")
    print("-" * 45)
    for label, group in [
        (f"RSI divergence + swing_low (combo)", combo_rsi_swing),
        (f"MA200 bounce  + MA200 support",       combo_ma200_ma200),
        (f"RSI divergence + otro soporte",        only_rsi),
        (f"swing_low sin RSI divergence",         only_swing),
    ]:
        wins, losses, resolvable = group_stats(group)
        pending = sum(1 for r in group if r["outcome"] in EXCLUDED)
        rate = rate_str(wins, resolvable)
        print(f"  {label}")
        print(f"    n={len(group)}  resolvable={resolvable}  win={rate}  loss={losses}  pending={pending}")
        if group:
            for r in group:
                oc = r["outcome"]
                pct = f"{r['pct_change']:+.1%}" if r.get("pct_change") is not None else "—"
                print(f"    · {r['scan_date']} {r['symbol']:<12} {oc:<15} {pct}")
    print()

    # ── 4. Detalle full table ─────────────────────────────────────────────────
    print("4. Tabla completa (deduplicada)")
    print("-" * 75)
    print(f"  {'fecha':<12} {'ticker':<12} {'outcome':<16} {'cats':<35} {'soporte'}")
    print(f"  {'-'*12} {'-'*12} {'-'*16} {'-'*35} {'-'*10}")
    for r in sorted(deduped, key=lambda x: x["scan_date"]):
        cats = ", ".join(r.get("catalysts") or []) or "(ninguno)"
        pct  = f"{r['pct_change']:+.1%}" if r.get("pct_change") is not None else "—  "
        print(f"  {r['scan_date']:<12} {r['symbol']:<12} {r['outcome']:<16} {cats[:35]:<35} {r['support_type']:<12} {pct}")
    print()


if __name__ == "__main__":
    main()
