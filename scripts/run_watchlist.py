"""Run the full Filter 1 → Filter 2 → report pipeline.

Usage:
  python scripts/run_watchlist.py
  python scripts/run_watchlist.py --no-news-gate    # skip T3 (no Claude API calls)
  python scripts/run_watchlist.py --fmp-limit 60    # pre-fetch FMP fundamentals first
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


def _patch_no_news_gate() -> None:
    """Replace run_news_gate with a no-op returning clean/none for every ticker."""
    from analysis.filter2_deep_dive import filter2_runner
    from analysis.filter2_deep_dive.filter2_models import (
        LightCheckResult,
        SentimentResult,
        SentimentVerdict,
    )

    def _noop(bundle, tech, fund, cache):  # noqa: ANN001
        return SentimentResult(
            light_check=LightCheckResult.CLEAN,
            sentiment_gate=SentimentVerdict.NONE,
            summary="News gate skipped (--no-news-gate).",
        )

    filter2_runner.run_news_gate = _noop
    logger.info("--no-news-gate: T3 news gate disabled for this run.")


def main() -> None:
    args = _parse_args()

    import data.fundamentals as _fund
    _fund._DAILY_CALL_LIMIT = args.fmp_limit

    if args.no_news_gate:
        _patch_no_news_gate()

    from data.cache import Cache
    from data.fetcher import fetch_universe_bundle
    from analysis.filter1_quick_sweep import run_filter1
    from analysis.filter2_deep_dive import run_filter2
    from output.watchlist_report import generate_report

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

    logger.info("Running Filter 1…")
    f1 = run_filter1(bundles)
    logger.info(
        "Filter 1 — survivors=%d discarded=%d unevaluable=%d",
        f1.summary.survivors,
        f1.summary.discarded,
        f1.summary.unevaluable,
    )

    logger.info("Running Filter 2 over %d survivors…", len(f1.survivors))
    f2 = run_filter2(f1.survivors, bundles, cache)

    md_path = generate_report(f2)
    logger.info("Report saved → %s", md_path)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run full watchlist pipeline: Fetch → Filter 1 → Filter 2 → Report."
    )
    parser.add_argument(
        "--no-news-gate",
        action="store_true",
        default=False,
        help="Skip T3 news gate (no Claude API calls). All tickers get clean/none.",
    )
    parser.add_argument(
        "--fmp-limit",
        type=int,
        default=0,
        help="Max FMP API calls for fundamentals pre-fetch (3 per ticker). Default 0 = cache only.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
