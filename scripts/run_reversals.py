"""Run the tactical reversal scanner over the full universe.

Usage:
  python scripts/run_reversals.py
  python scripts/run_reversals.py --sample N    # first N tickers only
  python scripts/run_reversals.py --force       # bypass market-hours gate (testing only)

The scanner rejects execution during BYMA market hours (Mon-Fri 11:00-17:15 ART).
This prevents publishing signals based on intraday price snapshots instead of
official closes. See DECISIONS.md #20 for the full rationale.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).parent.parent))

# BYMA equities continuous session: 11:00-17:00 ART.
# Gate uses 17:15 (15-min buffer) to allow official closes to propagate in yfinance.
_ART = ZoneInfo("America/Argentina/Buenos_Aires")
_MARKET_OPEN = dtime(11, 0)
_MARKET_CLOSE_GATE = dtime(17, 15)


def _check_market_hours(force: bool) -> None:
    """Exit with code 1 if BYMA is open, unless --force is passed."""
    now = datetime.now(_ART)
    is_weekday = now.weekday() < 5
    t = now.time().replace(tzinfo=None)
    market_open = is_weekday and _MARKET_OPEN <= t < _MARKET_CLOSE_GATE

    if not market_open:
        return

    if force:
        logger.warning(
            "⚠ Scan corriendo durante horario de mercado BYMA (%s ART, %s). "
            "Precios pueden ser snapshots intradiarios, no closes oficiales. "
            "--force activado, continuando igual.",
            now.strftime("%H:%M"),
            now.strftime("%A"),
        )
        return

    logger.error(
        "Scan abortado: mercado BYMA abierto (%s ART, %s). "
        "Correr después de las 17:15 ART para garantizar closes oficiales. "
        "Usar --force para omitir esta validación (solo testing).",
        now.strftime("%H:%M"),
        now.strftime("%A"),
    )
    sys.exit(1)


def main() -> None:
    args = _parse_args()
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format="%(levelname)s %(message)s")

    _check_market_hours(args.force)

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
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=False,
        help="Enable DEBUG logging (shows per-ticker rejection reasons).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Bypass market-hours gate. Use only for testing — signals may be intraday.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
