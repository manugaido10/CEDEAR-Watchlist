"""Run Filter 1 diagnostics over the full universe and emit a CSV of raw metric values.

The CSV goes to cache/filter1_diagnostics.csv (gitignored). Run this script
multiple times as the FMP fundamentals cache warms up — each run fetches up to
--fmp-limit new tickers from FMP; already-cached fundamentals cost 0 API calls.

With FMP free tier (250 req/day) and 3 calls per ticker, the first full cache
fill takes ~5 days. Each run shows how many tickers had fresh fundamentals.

Usage
-----
  python scripts/run_diagnostics.py                  # default budget (240 FMP calls)
  python scripts/run_diagnostics.py --fmp-limit 60   # conservative (20 new tickers)
  python scripts/run_diagnostics.py --fmp-limit 0    # prices only, no FMP calls
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).parent.parent
_CSV_OUT = _REPO_ROOT / "cache" / "filter1_diagnostics.csv"


def main() -> None:
    args = _parse_args()

    # Apply FMP call cap before importing the data layer so the limit is in
    # effect when fetch_universe_bundle runs.
    import data.fundamentals as _fund
    _fund._DAILY_CALL_LIMIT = args.fmp_limit
    logger.info("FMP call budget for this run: %d (≈ %d new tickers)", args.fmp_limit, args.fmp_limit // 3)

    from data.cache import Cache
    from data.universe import load_universe
    from data.fetcher import fetch_universe_bundle
    from analysis.diagnostics import DiagnosticsRow, extract_diagnostics, print_summary, write_csv

    cache = Cache()
    universe = load_universe()

    # Pre-run budget report: count which tickers already have fresh fundamentals.
    cedears_with_underlying = [
        t for t in universe
        if t.symbol_underlying is not None
    ]
    fresh_count = sum(
        1 for t in cedears_with_underlying
        if cache.fundamentals_are_fresh(t.symbol_underlying)
    )
    cold_count = len(cedears_with_underlying) - fresh_count
    fetchable_today = min(cold_count, args.fmp_limit // 3)

    logger.info(
        "Universe: %d tickers  |  CEDEARs with underlying: %d"
        "  |  fresh fundamentals: %d  |  cold: %d  |  fetchable today: ~%d",
        len(universe), len(cedears_with_underlying),
        fresh_count, cold_count, fetchable_today,
    )

    if cold_count > fetchable_today:
        logger.info(
            "Cache will be partial this run — %d tickers will have fundamentals=None"
            " (not enough FMP budget). Re-run to warm more.",
            cold_count - fetchable_today,
        )

    logger.info("Fetching universe bundles (prices via yfinance, fundamentals via FMP)…")
    t0 = time.monotonic()
    bundles, fetch_summary = fetch_universe_bundle(cache)
    elapsed = time.monotonic() - t0
    logger.info(
        "Fetch done in %.0fs — total=%d ok=%d partial=%d stale=%d missing=%d error=%d",
        elapsed, fetch_summary.total, fetch_summary.ok,
        fetch_summary.partial, fetch_summary.stale,
        fetch_summary.missing, fetch_summary.error,
    )

    # How many tickers ended up with actual fundamentals?
    with_fundamentals = sum(1 for b in bundles if b.fundamentals is not None)
    without_fundamentals_cedear = sum(
        1 for b in bundles
        if b.fundamentals is None
        and b.metadata.symbol_underlying is not None
    )
    logger.info(
        "Fundamentals available: %d / %d tickers  |  CEDEARs with underlying but no fundamentals: %d"
        " (FMP limit hit, data not in FMP, or fetch error)",
        with_fundamentals, len(bundles), without_fundamentals_cedear,
    )

    logger.info("Extracting diagnostic metrics…")
    rows = [extract_diagnostics(b) for b in bundles]

    write_csv(rows, _CSV_OUT)
    print_summary(rows)

    # Final tally for the caller
    logger.info("─" * 60)
    logger.info("CSV: %s", _CSV_OUT)
    logger.info(
        "Fundamentals coverage: %d / %d (%.0f%%)",
        with_fundamentals, len(bundles),
        100 * with_fundamentals / len(bundles) if bundles else 0,
    )
    fmp_calls_made = _fund._session_call_count
    logger.info("FMP calls made this run: %d  |  budget was: %d", fmp_calls_made, args.fmp_limit)
    if without_fundamentals_cedear > 0:
        logger.info(
            "%d CEDEARs with underlying still need fundamentals — re-run to fetch next batch.",
            without_fundamentals_cedear,
        )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Filter 1 diagnostics over the full universe.")
    parser.add_argument(
        "--fmp-limit",
        type=int,
        default=240,
        help="Max FMP API calls for this run (3 per ticker). Default 240 (free-tier day budget). "
             "Set to 0 to skip all FMP calls and use cached fundamentals only.",
    )
    parser.add_argument(
        "--output",
        default=str(_CSV_OUT),
        help=f"Output CSV path. Default: {_CSV_OUT}",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
