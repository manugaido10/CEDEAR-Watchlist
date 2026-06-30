"""Run the tactical reversal scanner over the full universe.

Usage:
  python scripts/run_reversals.py
  python scripts/run_reversals.py --sample N    # first N tickers only
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).parent.parent))


def main() -> None:
    args = _parse_args()

    from data.cache import Cache
    from data.fetcher import fetch_universe_bundle
    from analysis.reversal.reversal_scanner import scan_reversals
    from output.reversal_report import generate_reversal_report

    cache = Cache()

    logger.info("Fetching universe bundles…")
    t0 = time.monotonic()
    bundles, fetch_summary = fetch_universe_bundle(cache)
    logger.info(
        "Fetch done in %.0fs — total=%d ok=%d partial=%d stale=%d missing=%d error=%d",
        time.monotonic() - t0,
        fetch_summary.total,
        fetch_summary.ok,
        fetch_summary.partial,
        fetch_summary.stale,
        fetch_summary.missing,
        fetch_summary.error,
    )

    if args.sample:
        bundles = bundles[: args.sample]
        logger.info("--sample %d: limiting scan to first %d bundles.", args.sample, len(bundles))

    logger.info("Scanning for reversal opportunities over %d tickers…", len(bundles))
    opportunities = scan_reversals(bundles)

    md_path = generate_reversal_report(opportunities)
    logger.info("Report saved → %s", md_path)

    print(f"\n{len(opportunities)} oportunidades encontradas")
    if opportunities:
        print()
        for i, opp in enumerate(opportunities):
            cats = ", ".join(opp.catalyst)
            print(
                f"  #{i + 1}  {opp.symbol:<14}"
                f"  Score: {opp.score:>5.1f}"
                f"  RSI: {opp.rsi_14:>5.1f}"
                f"  Soporte: {opp.nearest_support_type} ({opp.distance_to_support_pct * 100:.1f}% dist)"
                f"  Catalizadores: {cats}"
            )
    print()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run tactical reversal scanner: Fetch → Scan → Report."
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=None,
        metavar="N",
        help="Limit to first N tickers (for testing).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
