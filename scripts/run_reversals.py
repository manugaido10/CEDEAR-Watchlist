"""Run the tactical reversal scanner over the full universe.

Usage:
  python scripts/run_reversals.py --capital-ars 12000000
  python scripts/run_reversals.py --capital-ars 12000000 --sample N    # first N tickers only
  python scripts/run_reversals.py --capital-ars 12000000 --force       # bypass market-hours gate (testing only)

The scanner rejects execution during BYMA market hours (Mon-Fri 11:00-17:15 ART).
This prevents publishing signals based on intraday price snapshots instead of
official closes. See DECISIONS.md #20 for the full rationale.
"""
from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import time
from datetime import datetime, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv(Path(__file__).parent.parent / ".env")

_TRACKING_FILES = [
    "data/reversal_tracking/signals.jsonl",
    "data/reversal_tracking/outcomes.jsonl",
    "data/reversal_tracking/near_misses.jsonl",
]

# BYMA equities continuous session: 11:00-17:00 ART.
# Gate uses 17:15 (15-min buffer) to allow official closes to propagate in yfinance.
_ART = ZoneInfo("America/Argentina/Buenos_Aires")
_MARKET_OPEN = dtime(11, 0)
_MARKET_CLOSE_GATE = dtime(17, 15)


def _commit_tracking_files(scan_date: str) -> None:
    """Git-commit the three canonical reversal-tracking files after each run.

    These files (signals, outcomes, near_misses) were lost once while unversioned.
    This step locks in each run's state locally so the history is never at risk.

    Only the three explicit paths are staged — never a broad 'git add .'.
    If the files are unchanged the commit is skipped silently.
    Any git failure is logged as a WARNING and swallowed; a commit failure must
    never abort or crash the pipeline run. The scan results are what matter.
    Never auto-pushes — pushing remains a manual decision.
    """
    repo_root = str(Path(__file__).parent.parent)
    commit_msg = f"chore(tracking): update reversal tracking data {scan_date}"

    try:
        # Skip early if none of the tracking files have changed.
        status = subprocess.run(
            ["git", "status", "--porcelain", "--"] + _TRACKING_FILES,
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        )
        if not status.stdout.strip():
            logger.debug("_commit_tracking_files: no changes detected, skipping.")
            return

        # Stage only the three canonical files — never anything broader.
        subprocess.run(
            ["git", "add", "--"] + _TRACKING_FILES,
            cwd=repo_root,
            check=True,
            capture_output=True,
        )

        # Guard against edge cases where status showed a change but add staged nothing.
        diff = subprocess.run(
            ["git", "diff", "--cached", "--quiet", "--"] + _TRACKING_FILES,
            cwd=repo_root,
        )
        if diff.returncode == 0:
            logger.debug("_commit_tracking_files: nothing staged after add, skipping.")
            return

        subprocess.run(
            ["git", "commit", "-m", commit_msg],
            cwd=repo_root,
            check=True,
            capture_output=True,
        )
        logger.info("Tracking data committed — %s", commit_msg)

    except subprocess.CalledProcessError as exc:
        logger.warning(
            "_commit_tracking_files: git operation failed (exit %d) — tracking data "
            "NOT committed. Run continues normally. stderr: %s",
            exc.returncode,
            (exc.stderr or b"").decode(errors="replace").strip() if isinstance(exc.stderr, bytes)
            else (exc.stderr or "").strip(),
        )
    except Exception as exc:
        logger.warning(
            "_commit_tracking_files: unexpected error — tracking data NOT committed. "
            "Run continues normally. Error: %s",
            exc,
        )


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
    now_art = datetime.now(_ART)
    scan_date = str(now_art.date())
    logger.info("Run started at %s", now_art.isoformat(timespec="seconds"))

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

    from data.positions_log import load_positions
    positions = load_positions()

    logger.info(
        "Scanning for reversal opportunities over %d tickers… (capital=%s ARS, posiciones=%d)",
        len(bundles), f"{int(args.capital_ars):,}", len(positions),
    )
    opportunities = scan_reversals(
        bundles,
        cache=cache,
        total_capital_ars=args.capital_ars,
        positions=positions,
    )

    md_path = generate_reversal_report(
        opportunities,
        total_capital_ars=args.capital_ars,
        positions=positions,
    )
    logger.info("Report saved → %s", md_path)

    _commit_tracking_files(scan_date)

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
    parser.add_argument(
        "--capital-ars",
        type=float,
        required=True,
        metavar="ARS",
        help=(
            "Capital total en ARS para el cap del 8%% por ticker (Fase 1.2 del roadmap). "
            "Requerido — sin default silencioso, dado que no hay módulo de cash-tracking."
        ),
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
