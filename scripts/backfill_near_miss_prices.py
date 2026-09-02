"""Retroactive price reconstruction for near_misses.jsonl (Decision #26).

Populates entry_price_ars, nearest_support, support_type, invalidation_level_ars
for the 178 records written before those fields were added to NearMissRecord.

Skips records that already have entry_price_ars (idempotent).
Skips records with support_distance_pct=null (no_support_within_5pct gate).
Marks records where invalidation >= entry as invalid_reconstruction_stop_above_entry
and leaves their price fields as null (mirrors Decision #20 guardrail).

Rewrites near_misses.jsonl in-place. Run once after deploying the schema change.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import yfinance as yf
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

NEAR_MISSES_PATH = Path("data/reversal_tracking/near_misses.jsonl")
_INVALIDATION_BUFFER = 0.015  # must match reversal_scanner.INVALIDATION_BUFFER


def _fetch_close(symbol: str, scan_date: str) -> Optional[float]:
    """Return close on or before scan_date via yfinance. Same logic as backfill_reversal_signals."""
    try:
        scan_dt = pd.Timestamp(scan_date)
        start = (scan_dt - pd.Timedelta(days=7)).strftime("%Y-%m-%d")
        end = (scan_dt + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        df = yf.Ticker(symbol).history(start=start, end=end, auto_adjust=True)
        if df.empty:
            return None
        df.index = pd.to_datetime(df.index).tz_localize(None)
        row = df[df.index <= scan_dt].tail(1)
        if row.empty:
            return None
        return float(row["Close"].iloc[-1])
    except Exception as exc:
        logger.warning("yfinance error %s/%s: %s", symbol, scan_date, exc)
        return None


def _reconstruct(record: Dict) -> Dict:
    """Return record with price fields populated, or with reconstruction_skip_reason set."""
    r = dict(record)

    if r.get("entry_price_ars") is not None:
        return r  # already reconstructed

    dist_pct = r.get("support_distance_pct")
    if dist_pct is None:
        r["reconstruction_skip_reason"] = "no_support_within_5pct"
        return r

    symbol = r["symbol"]
    scan_date = r["scan_date"]

    entry = _fetch_close(symbol, scan_date)
    if entry is None:
        r["reconstruction_skip_reason"] = "yfinance_no_data"
        return r

    support = round(entry * (1.0 - dist_pct / 100.0), 2)
    invalidation = round(support * (1.0 - _INVALIDATION_BUFFER), 2)

    if invalidation >= entry:
        logger.warning(
            "%s/%s: invalidation %.2f >= entry %.2f — skipping reconstruction",
            symbol, scan_date, invalidation, entry,
        )
        r["reconstruction_skip_reason"] = "invalid_reconstruction_stop_above_entry"
        return r

    r["entry_price_ars"] = round(entry, 2)
    r["nearest_support"] = support
    r["support_type"] = None  # cannot reconstruct safely; see Decision #26
    r["invalidation_level_ars"] = invalidation
    return r


def main() -> None:
    if not NEAR_MISSES_PATH.exists():
        logger.error("near_misses.jsonl not found: %s", NEAR_MISSES_PATH)
        sys.exit(1)

    raw_lines = [
        line.strip()
        for line in NEAR_MISSES_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    records: List[Dict] = []
    for line in raw_lines:
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            logger.warning("skipping malformed line: %s", line[:80])

    total = len(records)
    logger.info("Loaded %d records from near_misses.jsonl", total)

    already_done = 0
    reconstructed = 0
    no_support = 0
    no_yfinance = 0
    invalid_stop = 0

    result: List[Dict] = []
    for r in records:
        if r.get("entry_price_ars") is not None:
            already_done += 1
            result.append(r)
            continue

        updated = _reconstruct(r)
        reason = updated.get("reconstruction_skip_reason")
        if reason == "no_support_within_5pct":
            no_support += 1
        elif reason == "yfinance_no_data":
            no_yfinance += 1
        elif reason == "invalid_reconstruction_stop_above_entry":
            invalid_stop += 1
        else:
            reconstructed += 1

        result.append(updated)

    # Atomic rewrite
    tmp = NEAR_MISSES_PATH.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for r in result:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    tmp.replace(NEAR_MISSES_PATH)

    unreconstructible = no_support + no_yfinance + invalid_stop
    logger.info(
        "Done. total=%d  already_done=%d  reconstructed=%d  "
        "unreconstructible=%d (no_support=%d, no_yfinance=%d, invalid_stop_above_entry=%d)",
        total, already_done, reconstructed,
        unreconstructible, no_support, no_yfinance, invalid_stop,
    )


if __name__ == "__main__":
    main()
