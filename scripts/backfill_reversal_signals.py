"""One-shot backfill: populate signals.jsonl from historical reversal MD reports.

Parses output/reversiones_YYYY-MM-DD.md files, fetches the close price at
scan_date via yfinance, and writes one record per opportunity to
data/reversal_tracking/signals.jsonl.

Signals already present (same scan_date + symbol) are skipped (idempotent).
Signals where yfinance returns no data for the scan_date get outcome_status
= "unresolved_no_data" immediately.

Usage:
    python -m scripts.backfill_reversal_signals
"""

from __future__ import annotations

import json
import logging
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import yfinance as yf

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

REPORTS_DIR = Path("output")
SIGNALS_PATH = Path("data/reversal_tracking/signals.jsonl")


# ── ARS formatter reverse ─────────────────────────────────────────────────────

def _parse_ars(s: str) -> float:
    """Parse ARS string formatted with '.' as thousands separator back to float.

    E.g. "6.678" → 6678.0, "279" → 279.0, "63.539" → 63539.0
    """
    return float(s.replace(".", ""))


# ── MD parser ────────────────────────────────────────────────────────────────

_TICKER_RE = re.compile(r'^## #\d+ — (\S+\.BA)\s+Score: \*\*(\d+\.?\d*)\*\*', re.M)
_RSI_RE = re.compile(r'RSI 14 \| \*\*(\d+\.?\d*)\*\*')
_SUPPORT_RE = re.compile(r'Soporte más cercano \| ([\d.,]+) ARS \((\w+)\)')
_INVALIDATION_RE = re.compile(r'^\*\*([\d.,]+) ARS\*\*', re.M)
_TREND_RE = re.compile(r'tendencia semanal: `(\w+)`')
_CATALYST_BLOCK_RE = re.compile(r'### Catalizadores\n\n((?:- .+\n)+)')


def _parse_report(path: Path) -> List[Dict]:
    """Extract per-opportunity data from a reversal MD report."""
    text = path.read_text(encoding="utf-8")
    scan_date_m = re.search(r'(\d{4}-\d{2}-\d{2})', path.name)
    if not scan_date_m:
        return []
    scan_date = scan_date_m.group(1)

    tickers = _TICKER_RE.findall(text)
    rsis = _RSI_RE.findall(text)
    supports = _SUPPORT_RE.findall(text)
    invalidations = _INVALIDATION_RE.findall(text)
    trends = _TREND_RE.findall(text)
    catalyst_blocks = _CATALYST_BLOCK_RE.findall(text)

    records = []
    for i, (symbol, score) in enumerate(tickers):
        def _get(lst, idx, default=None):
            return lst[idx] if idx < len(lst) else default

        rsi_raw = _get(rsis, i)
        support_raw = _get(supports, i)
        inv_raw = _get(invalidations, i)
        trend = _get(trends, i, "neutral")
        cats_raw = _get(catalyst_blocks, i, "")

        rsi = float(rsi_raw) if rsi_raw else None
        invalidation = _parse_ars(inv_raw) if inv_raw else None
        nearest_support = _parse_ars(support_raw[0]) if support_raw else None
        support_type = support_raw[1] if support_raw else None
        catalysts = [
            line.lstrip("- ").strip()
            for line in cats_raw.splitlines()
            if line.strip().startswith("- ")
        ]

        records.append({
            "scan_date": scan_date,
            "symbol": symbol,
            "score": float(score),
            "rsi_14": rsi,
            "invalidation_level_ars": invalidation,
            "nearest_support": nearest_support,
            "support_type": support_type,
            "catalysts": catalysts,
            "weekly_trend": trend,
        })

    return records


# ── Price fetch ───────────────────────────────────────────────────────────────

def _fetch_entry_price(symbol: str, scan_date: str) -> Optional[float]:
    """Fetch close price for symbol on scan_date from yfinance."""
    try:
        t = yf.Ticker(symbol)
        df = t.history(start="2026-06-25", end="2026-08-06", auto_adjust=True)
        if df.empty:
            return None
        df.index = pd.to_datetime(df.index).tz_localize(None)
        scan_dt = pd.Timestamp(scan_date)
        row = df[df.index <= scan_dt].tail(1)
        if row.empty:
            return None
        return float(row["Close"].iloc[-1])
    except Exception as exc:
        logger.warning("yfinance error for %s: %s", symbol, exc)
        return None


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    SIGNALS_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Load existing to avoid duplicates
    existing_keys = set()
    if SIGNALS_PATH.exists():
        for line in SIGNALS_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    r = json.loads(line)
                    existing_keys.add((r["scan_date"], r["symbol"]))
                except Exception:
                    pass

    report_paths = sorted(REPORTS_DIR.glob("reversiones_*.md"))
    if not report_paths:
        logger.error("No reversal report files found in %s", REPORTS_DIR)
        sys.exit(1)

    total_written = 0
    total_no_data = 0

    with SIGNALS_PATH.open("a", encoding="utf-8") as out:
        for path in report_paths:
            records = _parse_report(path)
            for rec in records:
                key = (rec["scan_date"], rec["symbol"])
                if key in existing_keys:
                    logger.debug("skip existing: %s/%s", rec["scan_date"], rec["symbol"])
                    continue

                entry_price = _fetch_entry_price(rec["symbol"], rec["scan_date"])
                if entry_price is None:
                    logger.warning(
                        "%s/%s: no price data — marking unresolved_no_data",
                        rec["scan_date"], rec["symbol"],
                    )
                    outcome_status = "unresolved_no_data"
                else:
                    outcome_status = "pending"
                    total_written += 1

                if entry_price is None:
                    total_no_data += 1

                record = {
                    "scan_date": rec["scan_date"],
                    "symbol": rec["symbol"],
                    "score": rec["score"],
                    "rsi_14": rec["rsi_14"],
                    "entry_price_ars": entry_price,
                    "invalidation_level_ars": rec["invalidation_level_ars"],
                    "nearest_support": rec["nearest_support"],
                    "support_type": rec["support_type"],
                    "catalysts": rec["catalysts"],
                    "weekly_trend": rec["weekly_trend"],
                    "outcome_status": outcome_status,
                    "backfilled": True,
                }
                out.write(json.dumps(record, ensure_ascii=False) + "\n")
                existing_keys.add(key)
                logger.info(
                    "backfilled: %s/%s  entry=%.2f  status=%s",
                    rec["scan_date"], rec["symbol"],
                    entry_price or 0.0, outcome_status,
                )

    logger.info(
        "backfill complete: %d signals written, %d unresolved_no_data",
        total_written, total_no_data,
    )


if __name__ == "__main__":
    main()
