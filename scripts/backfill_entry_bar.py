"""One-shot backfill: populate entry-bar fields on outcomes.jsonl (Fase B2).

Adds entry_bar_date, entry_bar_date_source, entry_bar_close_ars,
next_open_ars, entry_gap_pct and entry_gap_through_stop to each outcome
record, using exactly the live logic (outcome_tracker._entry_bar_fields).
The signal's data_date is used when signals.jsonl has it; otherwise the entry
bar is matched by close (ENTRY_CLOSE_MATCH_* constants in outcome_tracker).

Never modifies existing fields (outcome, pct_change, r_multiple, ...).
One price fetch per ticker (cache-first via data.prices.fetch_prices).

Idempotent: records that already carry entry_bar_date are skipped. Records
whose ticker history cannot be fetched are left untouched (no null written),
so a later run can retry — fetch_prices returns None both for "no data" and
for transient yfinance errors.

near_miss_outcomes.jsonl needs no backfill: assess_near_miss_outcomes
re-assesses and rewrites every record on each run.

Usage:
    python -m scripts.backfill_entry_bar [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import logging
import statistics
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from analysis.reversal.outcome_tracker import _entry_bar_fields, _fetch_price_history

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

OUTCOMES_PATH = Path("data/reversal_tracking/outcomes.jsonl")
SIGNALS_PATH = Path("data/reversal_tracking/signals.jsonl")

STATUS_ALREADY_PRESENT = "already_present"
STATUS_COMPUTED = "computed"
STATUS_NO_HISTORY = "skipped_no_history"


# ── I/O ───────────────────────────────────────────────────────────────────────

def _load(path: Path) -> List[Dict]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _save(path: Path, records: List[Dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


# ── Backfill ──────────────────────────────────────────────────────────────────

def _backfill_record(
    record: Dict,
    signal: Optional[Dict],
    history_cache: Dict[str, Optional[pd.DataFrame]],
) -> Tuple[Dict, str]:
    """Enrich one outcome record in place. Returns (record, status)."""
    if "entry_bar_date" in record:
        return record, STATUS_ALREADY_PRESENT

    symbol = record["symbol"]
    if symbol not in history_cache:
        history_cache[symbol] = _fetch_price_history(symbol, record["scan_date"])
    history = history_cache[symbol]
    if history is None:
        return record, STATUS_NO_HISTORY

    source = {
        "scan_date": record["scan_date"],
        "entry_price_ars": record.get("entry_price_ars"),
        "invalidation_level_ars": record.get("invalidation_level_ars"),
        "data_date": (signal or {}).get("data_date"),
    }
    record.update(_entry_bar_fields(source, history))
    return record, STATUS_COMPUTED


def backfill(
    outcomes: List[Dict],
    signals: List[Dict],
) -> Tuple[List[Dict], Counter]:
    by_key = {(s["scan_date"], s["symbol"]): s for s in signals}
    cache: Dict[str, Optional[pd.DataFrame]] = {}
    statuses: Counter = Counter()
    out: List[Dict] = []
    for rec in outcomes:
        new = dict(rec)
        new, status = _backfill_record(new, by_key.get((rec["scan_date"], rec["symbol"])), cache)
        statuses[status] += 1
        out.append(new)
    return out, statuses


# ── Report ────────────────────────────────────────────────────────────────────

def _report(before: List[Dict], after: List[Dict], statuses: Counter) -> None:
    print(f"\n── outcomes.jsonl ({len(after)} records) ──")
    for k in sorted(statuses):
        print(f"  {k:<28} {statuses[k]:>4}")

    changed = [(b, a) for b, a in zip(before, after) if b != a]
    print(f"\n  records changed: {len(changed)} (only new keys added: "
          f"{all(all(b[k] == a[k] for k in b) for b, a in changed)})")
    print(f"  entry_bar_date_source: {dict(Counter(a.get('entry_bar_date_source') for _, a in changed))}")

    gaps = [a["entry_gap_pct"] for _, a in changed if a.get("entry_gap_pct") is not None]
    if gaps:
        print(f"  entry_gap_pct (n={len(gaps)}): min={min(gaps):+.4f} "
              f"median={statistics.median(gaps):+.4f} max={max(gaps):+.4f}")
    thru = [a for _, a in changed if a.get("entry_gap_through_stop")]
    print(f"  entry_gap_through_stop=True: {len(thru)}")

    print("\n  scan_date   symbol      outcome      entry_bar   src          bar_close/entry  next_open   gap      thru")
    for _, a in changed:
        e = a.get("entry_price_ars")
        bc = a.get("entry_bar_close_ars")
        ratio = f"{bc / e - 1:+.4f}" if bc is not None and e else "   —   "
        gap = f"{a['entry_gap_pct']:+.4f}" if a.get("entry_gap_pct") is not None else "   —  "
        print(f"  {a['scan_date']}  {a['symbol']:<10}  {a.get('outcome', ''):<11}  "
              f"{a.get('entry_bar_date') or '—':<10}  {a.get('entry_bar_date_source') or '—':<11}  "
              f"{ratio:>15}  {a.get('next_open_ars') or '—':>10}  {gap}  "
              f"{a.get('entry_gap_through_stop')}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Compute and report without writing back to outcomes.jsonl.",
    )
    args = parser.parse_args()

    if not OUTCOMES_PATH.exists():
        logger.warning("%s does not exist — nothing to backfill", OUTCOMES_PATH)
        return

    before = _load(OUTCOMES_PATH)
    after, statuses = backfill(before, _load(SIGNALS_PATH))
    logger.info("%s — %d records processed: %s", OUTCOMES_PATH.name, len(after), dict(statuses))
    _report(before, after, statuses)

    if args.dry_run:
        logger.info("--dry-run: nothing written.")
        return
    _save(OUTCOMES_PATH, after)
    logger.info("%s written back.", OUTCOMES_PATH)


if __name__ == "__main__":
    main()
