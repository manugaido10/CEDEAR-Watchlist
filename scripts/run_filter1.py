"""Run Filter 1 over the full universe and print survivor / discarded / unevaluable report.

Usage
-----
  python scripts/run_filter1.py                  # uses cached prices + fundamentals only
  python scripts/run_filter1.py --fmp-limit 60   # fetch up to 20 new tickers from FMP first
"""
from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).parent.parent


def main() -> None:
    args = _parse_args()

    import data.fundamentals as _fund
    _fund._DAILY_CALL_LIMIT = args.fmp_limit

    from data.cache import Cache
    from data.universe import load_universe
    from data.fetcher import fetch_universe_bundle
    from analysis.filter1_quick_sweep import run_filter1, FilterCategory

    cache = Cache()
    load_universe()  # warm the universe snapshot log

    logger.info("Fetching universe bundles…")
    t0 = time.monotonic()
    bundles, fetch_summary = fetch_universe_bundle(cache)
    logger.info(
        "Fetch done in %.0fs — total=%d ok=%d partial=%d stale=%d missing=%d error=%d",
        time.monotonic() - t0,
        fetch_summary.total, fetch_summary.ok, fetch_summary.partial,
        fetch_summary.stale, fetch_summary.missing, fetch_summary.error,
    )

    report = run_filter1(bundles)
    s = report.summary

    print("\n" + "=" * 70)
    print("FILTER 1 — RESULTS")
    print("=" * 70)
    print(f"  Total    : {s.total}")
    print(f"  Survivor : {s.survivors}")
    print(f"  Discarded: {s.discarded}")
    print(f"  Unevalbl : {s.unevaluable}  (fetch missing/error — not evaluated)")
    print(f"  No fundamentals (C1/C2 skipped): {s.no_fundamentals}")

    print("\n── Discards by criterion ──────────────────────────────────────────")
    for crit, count in sorted(s.discard_by_criterion.items()):
        print(f"  {crit}: {count}")

    print("\n── Discarded tickers ──────────────────────────────────────────────")
    for r in sorted(report.discarded, key=lambda x: x.symbol):
        triggers = " | ".join(f"[{t.criterion}] {t.detail}" for t in r.discard_triggers)
        print(f"  {r.symbol:14s} ({r.asset_type:16s})  {triggers}")

    print("\n── Unevaluable tickers ────────────────────────────────────────────")
    for r in sorted(report.unevaluable, key=lambda x: x.symbol):
        print(f"  {r.symbol:14s}  {r.unevaluable_reason}")

    print("\n── Survivors with priority attention (A3 flag) ────────────────────")
    priority = [r for r in report.survivors if r.priority_attention]
    if priority:
        for r in sorted(priority, key=lambda x: x.symbol):
            print(f"  {r.symbol}")
    else:
        print("  (none)")

    print()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Filter 1 over the full universe.")
    parser.add_argument(
        "--fmp-limit",
        type=int,
        default=0,
        help="Max FMP API calls for this run (3 per ticker). Default 0 (cache only).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
