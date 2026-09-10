"""Re-backfill near_misses.jsonl entries with T-1 entry prices (Decision #28).

The original backfill_near_miss_prices.py used close(scan_date) as entry_price_ars.
This is inconsistent: the scanner evaluates criteria on T-1 data (yfinance .BA
next-day lag), so the hypothetical near-miss trade would also enter at T-1 close,
not T+0.

This script corrects pre-2026-09-03 backfilled records in-place:
  - entry_price_ars  ← close(scan_date - 1 trading day)  [from parquet cache]
  - nearest_support  ← entry_t1 * (1 - support_distance_pct / 100)
  - invalidation_level_ars ← nearest_support * (1 - INVALIDATION_BUFFER)

Records already on T-1 semantics (scan_date >= 2026-09-03, live scanner) are
untouched. Records without entry_price_ars (no_support_within_5pct) are untouched.

Atomic rewrite — safe to re-run.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).parent.parent))
from data.cache import Cache

NEAR_MISSES_PATH = Path("data/reversal_tracking/near_misses.jsonl")
_INVALIDATION_BUFFER = 0.015
_LIVE_CUTOFF = "2026-09-03"  # from this date onwards, scanner was live (T-1 already)


def _get_t1_close(cache: Cache, symbol: str, scan_date: str) -> Optional[float]:
    df = cache.load_prices(symbol)
    if df is None or df.empty:
        return None
    df.index = pd.to_datetime(df.index).normalize()
    scan_ts = pd.Timestamp(scan_date)
    for delta in range(1, 8):
        prev_ts = scan_ts - pd.Timedelta(days=delta)
        if prev_ts in df.index:
            return float(df.loc[prev_ts, "close"])
    return None


def _rebackfill(record: Dict, cache: Cache) -> Dict:
    r = dict(record)

    # Only touch pre-cutoff backfilled records that already have a T+0 entry
    if r["scan_date"] >= _LIVE_CUTOFF:
        return r
    if r.get("entry_price_ars") is None:
        return r
    if r.get("support_distance_pct") is None:
        return r

    symbol = r["symbol"]
    scan_date = r["scan_date"]
    dist_pct = r["support_distance_pct"]

    t1_close = _get_t1_close(cache, symbol, scan_date)
    if t1_close is None:
        logger.warning("%s/%s: no T-1 close available in parquet — leaving as-is", symbol, scan_date)
        return r

    support = round(t1_close * (1.0 - dist_pct / 100.0), 2)
    invalidation = round(support * (1.0 - _INVALIDATION_BUFFER), 2)

    if invalidation >= t1_close:
        logger.warning(
            "%s/%s: invalidation %.2f >= T-1 entry %.2f — leaving as-is",
            symbol, scan_date, invalidation, t1_close,
        )
        return r

    old_entry = r["entry_price_ars"]
    r["entry_price_ars"] = round(t1_close, 2)
    r["nearest_support"] = support
    r["invalidation_level_ars"] = invalidation
    logger.debug(
        "%s/%s: entry %.2f → %.2f (T-1)  support %.2f  invalidation %.2f",
        symbol, scan_date, old_entry, t1_close, support, invalidation,
    )
    return r


def main() -> None:
    if not NEAR_MISSES_PATH.exists():
        logger.error("near_misses.jsonl not found: %s", NEAR_MISSES_PATH)
        sys.exit(1)

    cache = Cache()

    lines = [l.strip() for l in NEAR_MISSES_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
    records: List[Dict] = []
    for line in lines:
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            logger.warning("skipping malformed line: %.80s", line)

    logger.info("Loaded %d records", len(records))

    updated = 0
    skipped_no_t1 = 0
    unchanged = 0
    result: List[Dict] = []

    for r in records:
        if r["scan_date"] >= _LIVE_CUTOFF or r.get("entry_price_ars") is None:
            unchanged += 1
            result.append(r)
            continue

        new_r = _rebackfill(r, cache)
        if new_r["entry_price_ars"] != r["entry_price_ars"]:
            updated += 1
        elif r.get("support_distance_pct") is not None:
            # Had support_distance_pct but T-1 not available or guard triggered
            skipped_no_t1 += 1
        else:
            unchanged += 1
        result.append(new_r)

    tmp = NEAR_MISSES_PATH.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for r in result:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    tmp.replace(NEAR_MISSES_PATH)

    logger.info(
        "Done. total=%d  updated_to_t1=%d  skipped_no_t1=%d  unchanged=%d",
        len(records), updated, skipped_no_t1, unchanged,
    )


if __name__ == "__main__":
    main()
