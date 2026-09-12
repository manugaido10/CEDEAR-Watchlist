"""One-shot backfill: populate r_multiple / r_multiple_skip_reason /
exit_price_ars_at_deadline on outcomes.jsonl and near_miss_outcomes.jsonl.

Decision #31 / Roadmap Fase A1: enriches the existing corpus retroactively.
Never modifies pct_change, outcome, exit_price_ars, or catalysts. For lateral
records without exit_price_ars_at_deadline, fetches the close at
scan_date + 20 days via data.prices.fetch_prices (cache-first through the
yfinance layer). If yfinance has no bar in-window, marks
r_multiple_skip_reason = "lateral_no_deadline_price".

Idempotent: re-running is a no-op on records that already carry r_multiple or
a skip_reason.

Usage:
    python -m scripts.backfill_r_multiple [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import logging
import statistics
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from analysis.reversal.r_multiple import (
    SKIP_LATERAL_NO_DEADLINE_PRICE,
    SKIP_NO_EXIT_DATA,
    compute_r_multiple,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

OUTCOMES_PATH = Path("data/reversal_tracking/outcomes.jsonl")
NEAR_MISS_OUTCOMES_PATH = Path("data/reversal_tracking/near_miss_outcomes.jsonl")

_MAX_DAYS = 20  # must match outcome_tracker._MAX_DAYS


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


# ── Deadline close fetch (lateral) ───────────────────────────────────────────

def _fetch_deadline_close(symbol: str, scan_date: str) -> Optional[float]:
    """Return the close of the last trading bar within scan_date + _MAX_DAYS.

    Uses data.prices.fetch_prices — cache-first through yfinance. Returns None
    if the symbol has no data or the window contains no bars.
    """
    from data.prices import fetch_prices
    df = fetch_prices(symbol)
    if df is None or df.empty or "close" not in df.columns:
        return None
    df = df.sort_index()
    scan_dt = pd.Timestamp(scan_date)
    deadline = pd.Timestamp(scan_date) + pd.Timedelta(days=_MAX_DAYS)
    window = df[(df.index > scan_dt) & (df.index <= deadline)]
    if window.empty:
        return None
    return float(window["close"].iloc[-1])


# ── Backfill one record ──────────────────────────────────────────────────────

def _backfill_record(record: Dict) -> Tuple[Dict, str]:
    """Enrich a single outcome record in-place. Returns (record, status_key).

    status_key ∈ {"already_present", "computed", "skip_<reason>"}.
    """
    # Idempotency: skip if already annotated.
    if "r_multiple" in record and (
        record["r_multiple"] is not None
        or record.get("r_multiple_skip_reason") is not None
    ):
        return record, "already_present"

    entry = record.get("entry_price_ars")
    invalidation = record.get("invalidation_level_ars")
    outcome = record.get("outcome")

    # Pick exit and fetch deadline close if lateral without one.
    exit_used: Optional[float] = record.get("exit_price_ars")
    if outcome == "lateral":
        deadline_price = record.get("exit_price_ars_at_deadline")
        if deadline_price is None:
            fetched = _fetch_deadline_close(record["symbol"], record["scan_date"])
            if fetched is not None:
                record["exit_price_ars_at_deadline"] = round(fetched, 2)
                deadline_price = record["exit_price_ars_at_deadline"]
        exit_used = deadline_price
    elif outcome in ("pending", "unresolved_no_data"):
        exit_used = None

    r, reason = compute_r_multiple(entry, invalidation, exit_used)

    # For laterals whose deadline price couldn't be fetched, override the
    # generic no_exit_data reason with the more specific lateral marker.
    if outcome == "lateral" and reason == SKIP_NO_EXIT_DATA:
        reason = SKIP_LATERAL_NO_DEADLINE_PRICE

    record["r_multiple"] = round(r, 4) if r is not None else None
    record["r_multiple_skip_reason"] = reason
    # Ensure the deadline field exists (as null) for schema uniformity.
    record.setdefault("exit_price_ars_at_deadline", None)

    if r is not None:
        return record, "computed"
    return record, f"skip_{reason}"


# ── Report ───────────────────────────────────────────────────────────────────

def _report(name: str, records: List[Dict]) -> None:
    counts: Dict[str, int] = defaultdict(int)
    rs: List[float] = []
    for r in records:
        if r.get("r_multiple") is not None:
            counts["computed"] += 1
            rs.append(r["r_multiple"])
        else:
            counts[f"null: {r.get('r_multiple_skip_reason') or 'unknown'}"] += 1

    print(f"\n── {name} ({len(records)} records) ──")
    for k in sorted(counts):
        print(f"  {k:<40} {counts[k]:>4}")

    if rs:
        rs.sort()
        n = len(rs)
        print(
            f"  R distribution (n={n}): "
            f"min={rs[0]:.2f}  P10={rs[max(0, n // 10 - 1)]:.2f}  "
            f"median={statistics.median(rs):.2f}  "
            f"P90={rs[min(n - 1, 9 * n // 10)]:.2f}  "
            f"max={rs[-1]:.2f}  mean={statistics.mean(rs):.2f}"
        )
        # Bucket by outcome to check the −1R plateau on stops and target multiples.
        by_outcome: Dict[str, List[float]] = defaultdict(list)
        for rec in records:
            if rec.get("r_multiple") is not None:
                by_outcome[rec.get("outcome", "?")].append(rec["r_multiple"])
        for outcome in sorted(by_outcome):
            vals = by_outcome[outcome]
            print(
                f"    {outcome:<20} n={len(vals):>3}  "
                f"mean={statistics.mean(vals):+.2f}R  "
                f"median={statistics.median(vals):+.2f}R"
            )


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Compute and report without writing back to the jsonl files.",
    )
    args = parser.parse_args()

    for path in (OUTCOMES_PATH, NEAR_MISS_OUTCOMES_PATH):
        if not path.exists():
            logger.warning("%s does not exist — skipping", path)
            continue
        records = _load(path)
        updates: Dict[str, int] = defaultdict(int)
        for i, rec in enumerate(records):
            records[i], status = _backfill_record(rec)
            updates[status] += 1

        logger.info(
            "%s — %d records processed: %s",
            path.name, len(records), dict(updates),
        )
        if not args.dry_run:
            _save(path, records)
            logger.info("%s written back.", path)

        _report(path.name, records)


if __name__ == "__main__":
    main()
