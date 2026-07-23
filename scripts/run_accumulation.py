"""Run the early accumulation scanner over the full universe.

Usage:
  python scripts/run_accumulation.py
  python scripts/run_accumulation.py --sample N
  python scripts/run_accumulation.py --momentum-file output/watchlist_YYYY-MM-DD.md
"""
from __future__ import annotations

import argparse
import logging
import re
import sys
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).parent.parent))


def _parse_momentum_symbols(filepath: str) -> set:
    """Extract ticker symbols from the top-10 ranked entries in a watchlist Markdown report."""
    path = Path(filepath)
    if not path.exists():
        logger.warning("--momentum-file not found: %s", filepath)
        return set()

    content = path.read_text(encoding="utf-8")
    # Watchlist headers: ## #N — TICKER.BA  `[label]`  Score: X.X
    symbols = set(re.findall(r"##\s+#\d+\s+—\s+([A-Z0-9.]+)\s", content))
    logger.info("Loaded %d momentum symbols from %s", len(symbols), filepath)
    return symbols


def main() -> None:
    args = _parse_args()

    from data.cache import Cache
    from data.fetcher import fetch_universe_bundle
    from analysis.accumulation.accumulation_scanner import scan_accumulation
    from output.accumulation_report import generate_accumulation_report

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

    momentum_symbols: set = set()
    if args.momentum_file:
        momentum_symbols = _parse_momentum_symbols(args.momentum_file)

    logger.info("Scanning for accumulation opportunities over %d tickers…", len(bundles))
    opportunities = scan_accumulation(bundles, momentum_symbols)

    md_path = generate_accumulation_report(opportunities)
    logger.info("Report saved → %s", md_path)

    print(f"\n{len(opportunities)} oportunidades de acumulación temprana encontradas")
    if opportunities:
        print()
        for i, opp in enumerate(opportunities):
            print(
                f"  #{i + 1}  {opp.symbol:<14}"
                f"  Score: {opp.score:>5.1f}"
                f"  Slope: {opp.slope_normalized * 100:.4f}%/día"
                f"  R²: {opp.r_squared:.3f}"
                f"  VolRatio: {opp.volume_ratio:.2f}x"
                f"  vs52W: {opp.pct_of_52w_high * 100:.1f}%"
            )
    print()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run early accumulation scanner: Fetch → Scan → Report."
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=None,
        metavar="N",
        help="Limit to first N tickers (for testing).",
    )
    parser.add_argument(
        "--momentum-file",
        type=str,
        default=None,
        metavar="PATH",
        help="Path to watchlist report Markdown; top-10 symbols excluded via C5.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
