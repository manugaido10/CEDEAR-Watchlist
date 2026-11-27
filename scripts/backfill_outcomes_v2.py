"""Backfill / refresh data/reversal_tracking/outcomes_v2.jsonl (P4 fase 1).

Reads signals.jsonl and outcomes.jsonl (v1) READ-ONLY and writes only
outcomes_v2.jsonl. Prices come from the local cache (no network).
Idempotent: records already present are kept byte for byte; only signals
without a v2 record are assessed (pending and transient failures are not
stored and are retried on the next run).

Usage:
    python -m scripts.backfill_outcomes_v2 [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import logging
from collections import Counter
from datetime import date
from pathlib import Path

from analysis.reversal.outcomes_v2 import (
    OUTCOMES_V2_PATH, build_v2, cache_history_loader, load_v2, save_v2,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

SIGNALS_PATH = Path("data/reversal_tracking/signals.jsonl")
OUTCOMES_V1_PATH = Path("data/reversal_tracking/outcomes.jsonl")


def _load_jsonl(path: Path):
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    signals = _load_jsonl(SIGNALS_PATH)
    v1 = {(o["scan_date"], o["symbol"]): o for o in _load_jsonl(OUTCOMES_V1_PATH)}
    existing = load_v2()
    records, stats = build_v2(signals, v1, existing, cache_history_loader, date.today())

    print(f"signals={len(signals)} existing_v2={len(existing)} -> records={len(records)}  {stats}")
    print("status_v2:", dict(Counter(r["status_v2"] for r in records)))
    print("data errors (excluded from statistics):",
          dict(Counter(r["data_error_reason"] for r in records if r["status_v2"] == "unresolved_data_error")))
    print("not instrumented (no entry bar; NOT a data error):",
          sum(r["status_v2"] == "not_instrumented" for r in records))
    print("basis_adjusted:", sum(r["basis_adjusted"] for r in records),
          "basis_uncertain:", sum(r["basis_uncertain"] for r in records),
          "flags:", dict(Counter(f for r in records for f in r["data_flags"])))
    if args.dry_run:
        print("dry-run: nothing written")
        return 0
    save_v2(records, OUTCOMES_V2_PATH)
    print(f"wrote {OUTCOMES_V2_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
