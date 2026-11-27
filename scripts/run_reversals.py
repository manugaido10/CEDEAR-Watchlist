"""Run the tactical reversal scanner over the full universe.

Usage:
  python scripts/run_reversals.py                          # paper-trading mode (#28)
  python scripts/run_reversals.py --dry-run                # scan + report, no tracking writes, no commit
  python scripts/run_reversals.py --sample N               # first N tickers only (implies --dry-run)
  python scripts/run_reversals.py --force                  # bypass market-hours gate (still records)
  python scripts/run_reversals.py --capital-ars 12000000   # optional: override ADV gate with capital-ratio gate

Valid run window: weekday before 11:00 ART (pre-open), or weekend. The signal
for scan_date X is built on the close of X's previous trading day (#30):
yfinance publishes .BA bars on the next business day, so after 17:15 ART the
fetcher demands today's bar, does not get it and marks the universe MISSING.
The market-hours gate rejects 11:00-17:15 ART on weekdays (#20).

Run-integrity checks (Decision #35), before scanning:
  - Health gate: abort (exit 2) if the usable share of the non-excluded
    universe is below MIN_USABLE_RATIO. Dry-run only warns.
  - Intraday-bar check: abort (exit 3) in every run, --force included, if any
    used bundle has a bar dated today (ART).
  - data_date (mode of the last bar used) is stamped on every tracking record.

Paper-trading mode (default since #28): --capital-ars is optional. Without it,
the liquidity gate uses a fixed ADV floor (ADV_MIN_ARS = 15M ARS). The report
contains technical analysis only — no capital allocation sections.
"""
from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import time
from datetime import datetime, time as dtime
from pathlib import Path
from typing import List, Optional
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv(Path(__file__).parent.parent / ".env")

_TRACKING_FILES = [
    "data/reversal_tracking/signals.jsonl",
    "data/reversal_tracking/outcomes.jsonl",
    "data/reversal_tracking/outcomes_v2.jsonl",
    "data/reversal_tracking/near_misses.jsonl",
    "data/reversal_tracking/regime_snapshots.jsonl",
    "data/reversal_tracking/near_miss_outcomes.jsonl",
]

# Health gate (Decision #35). CALIBRATION PENDING — not a decided value.
# Share of the non-excluded universe that must come back OK/PARTIAL.
# Reference: healthy pre-open run 2026-11-20 = 309/311; failed after-close
# runs (2026-11-09, 2026-11-18) = 0 usable.
MIN_USABLE_RATIO = 0.80

EXIT_OK = 0
EXIT_MARKET_OPEN = 1
EXIT_UNHEALTHY_FETCH = 2
EXIT_INTRADAY_BAR = 3

_VALID_WINDOW_MSG = "día hábil antes de las 11:00 ART (pre-apertura) o fin de semana"

# BYMA equities continuous session: 11:00-17:00 ART.
# Gate uses 17:15 (15-min buffer) to allow official closes to propagate in yfinance.
_ART = ZoneInfo("America/Argentina/Buenos_Aires")
_MARKET_OPEN = dtime(11, 0)
_MARKET_CLOSE_GATE = dtime(17, 15)


def _commit_tracking_files(scan_date: str) -> None:
    """Git-commit the canonical reversal-tracking files after each run.

    These files (signals, outcomes, near_misses, regime_snapshots,
    near_miss_outcomes) must never be lost while unversioned. This step locks
    in each run's state locally so the history is never at risk.

    Only the explicit _TRACKING_FILES paths are staged — never a broad 'git add .'.
    positions_log.json is deliberately excluded.
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

        # Stage only the canonical tracking files — never anything broader.
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
    """Exit with code 1 if BYMA is open (weekday 11:00-17:15 ART), unless --force.

    Passing this gate is not enough: after 17:15 the fetch fails (see module
    docstring). Valid window: weekday before 11:00 ART, or weekend.
    """
    now = datetime.now(_ART)
    is_weekday = now.weekday() < 5
    t = now.time().replace(tzinfo=None)
    market_open = is_weekday and _MARKET_OPEN <= t < _MARKET_CLOSE_GATE

    if not market_open:
        return

    if force:
        logger.warning(
            "⚠ Scan corriendo durante horario de mercado BYMA (%s ART, %s). "
            "--force activado: se registra igual, pero el chequeo de barra intradiaria "
            "aborta si algún ticker trae una barra con fecha de hoy.",
            now.strftime("%H:%M"),
            now.strftime("%A"),
        )
        return

    logger.error(
        "Scan abortado: mercado BYMA abierto (%s ART, %s). "
        "Ventana válida: %s. "
        "Usar --force para omitir esta validación.",
        now.strftime("%H:%M"),
        now.strftime("%A"),
        _VALID_WINDOW_MSG,
    )
    sys.exit(EXIT_MARKET_OPEN)


def main() -> int:
    args = _parse_args()
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format="%(levelname)s %(message)s")
    return run(args)


def _resolve_dry_run(args: argparse.Namespace) -> bool:
    if args.sample is not None and not args.dry_run:
        logger.warning(
            "⚠ --sample implica --dry-run: no se registra tracking, no se abren "
            "posiciones paper y no se commitea."
        )
        return True
    return bool(args.dry_run)


def run(args: argparse.Namespace) -> int:
    """Fetch → integrity checks → scan → report → (record + commit). Returns exit code."""
    now_art = datetime.now(_ART)
    scan_date = str(now_art.date())
    logger.info("Run started at %s", now_art.isoformat(timespec="seconds"))

    dry_run = _resolve_dry_run(args)
    if dry_run:
        logger.warning("⚠ DRY-RUN: sin escritura de tracking, sin posiciones paper, sin commit.")

    _check_market_hours(args.force)

    from data.cache import Cache, _last_expected_trading_day
    from data.fetcher import fetch_universe_bundle
    from data.prices import _is_excluded_ars
    from analysis.reversal.reversal_scanner import scan_reversals
    from analysis.reversal.run_integrity import (
        assess_fetch_health,
        bundles_with_bar_on_or_after,
        compute_data_date,
    )
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

    # ── Health gate (Decision #35) ────────────────────────────────────────────
    health = assess_fetch_health(bundles, _is_excluded_ars)
    if not health.is_healthy(MIN_USABLE_RATIO):
        detail = (
            f"{health.n_usable}/{health.n_expected} tickers usables "
            f"({health.usable_ratio:.0%}, mínimo {MIN_USABLE_RATIO:.0%}; "
            f"{health.n_excluded_by_design} excluidos por diseño) — "
            f"ok={fetch_summary.ok} partial={fetch_summary.partial} "
            f"stale={fetch_summary.stale} missing={fetch_summary.missing} "
            f"error={fetch_summary.error}. Causa probable: barras desactualizadas "
            f"(yfinance publica el cierre .BA el día hábil siguiente; después de las "
            f"17:15 ART se exige la barra de hoy). Ventana válida: {_VALID_WINDOW_MSG}."
        )
        if dry_run:
            logger.warning("⚠ Fetch no saludable (dry-run, se continúa): %s", detail)
        else:
            logger.error(
                "Scan abortado — fetch no saludable: %s "
                "Sin registros, sin snapshot, sin commit.", detail,
            )
            return EXIT_UNHEALTHY_FETCH

    # ── Intraday-bar check (Decision #35) — every run, --force included ───────
    today_art = now_art.date()
    intraday = bundles_with_bar_on_or_after(bundles, today_art)
    if intraday:
        logger.error(
            "Scan abortado — %d tickers traen una barra con fecha de hoy (%s ART): "
            "posible snapshot intradiario, no cierre oficial (#20). Ejemplos: %s. "
            "Ventana válida: %s. Sin registros, sin snapshot, sin commit.",
            len(intraday), today_art, ", ".join(intraday[:5]), _VALID_WINDOW_MSG,
        )
        return EXIT_INTRADAY_BAR

    # ── data_date (Decision #35) ──────────────────────────────────────────────
    data_dt = compute_data_date(bundles)
    data_date = data_dt.isoformat() if data_dt is not None else None
    expected_day = _last_expected_trading_day()
    if data_dt != expected_day:
        logger.warning(
            "⚠ data_date=%s difiere del último día hábil esperado (%s) — "
            "feriado BYMA o datos desactualizados.",
            data_date, expected_day,
        )
    else:
        logger.info("data_date=%s (scan_date=%s)", data_date, scan_date)

    # ── CCL alignment (Decision #43) — before --sample, which could drop the pairs ──
    # Re-aligns the CCL history session by session (regime table, verified per
    # run against an implied CCL from local/ADR pairs). Spot untouched.
    ccl_alignment_record = None
    try:
        from data.ccl_alignment import align_bundles_ccl, make_cached_adr_loader
        ccl_alignment_record = align_bundles_ccl(bundles, make_cached_adr_loader(cache)).to_record()
    except Exception as exc:
        logger.warning("⚠ CCL alignment failed — CCL history left raw: %s", exc)
        ccl_alignment_record = {"status": "unavailable", "applied": False, "reason": str(exc)}

    if args.sample:
        bundles = bundles[: args.sample]
        logger.info("--sample %d: limiting scan to first %d bundles.", args.sample, len(bundles))

    from data.positions_log import load_positions
    positions = load_positions()

    logger.info(
        "Scanning for reversal opportunities over %d tickers… (capital=%s ARS, posiciones=%d)",
        len(bundles), f"{int(args.capital_ars):,}" if args.capital_ars is not None else "—", len(positions),
    )
    opportunities = scan_reversals(
        bundles,
        scan_date=scan_date,
        record=not dry_run,
        cache=cache,
        total_capital_ars=args.capital_ars,
        positions=positions,
        data_date=data_date,
        ccl_alignment=ccl_alignment_record,
    )

    md_path = generate_reversal_report(
        opportunities,
        total_capital_ars=args.capital_ars,
        positions=positions,
        run_date=f"{scan_date}_dryrun" if dry_run else scan_date,
    )
    logger.info("Report saved → %s", md_path)

    if dry_run:
        logger.warning("⚠ DRY-RUN: tracking y calibración no actualizados, sin commit.")
    else:
        from analysis.reversal.near_miss_outcomes import log_safe_only_calibration_progress
        log_safe_only_calibration_progress()
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
    return EXIT_OK


def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run tactical reversal scanner: Fetch → Scan → Report."
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=None,
        metavar="N",
        help="Limit to first N tickers (for testing). Implies --dry-run.",
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
        help=(
            "Bypass market-hours gate. Still records; the run aborts if any "
            "ticker has a bar dated today (intraday snapshot)."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help=(
            "Scan and write report (output/reversiones_<date>_dryrun.md) without "
            "writing tracking files, opening paper positions or committing."
        ),
    )
    parser.add_argument(
        "--capital-ars",
        type=float,
        required=False,
        default=None,
        metavar="ARS",
        help=(
            "Capital total en ARS (paper-trading mode: opcional desde #28). "
            "Si se omite, la gate de liquidez usa ADV_MIN_ARS fijo y el reporte "
            "no muestra secciones de capital."
        ),
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main())
