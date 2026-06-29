"""Maintenance script for data/yfinance_exclusions.json.

Verifies excluded tickers for recovery, and optionally scans the full universe
for new failures. Run manually — not part of the weekly automated cycle.

Usage:
  python scripts/refresh_exclusions.py              # verify all
  python scripts/refresh_exclusions.py --recover-only  # only check excluded → recovered
  python scripts/refresh_exclusions.py --new-only      # only check universe for new failures
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import date
from pathlib import Path
from typing import Dict, List, Tuple

import yfinance as yf

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_REPO_ROOT))

EXCLUSIONS_PATH = _REPO_ROOT / "data" / "sources" / "yfinance_exclusions.json"
SNAPSHOT_PATH = _REPO_ROOT / "data" / "universe_snapshot.json"

_PRICE_LOOKBACK = 5   # days — lightweight probe for recovery / new-failure checks
_REQUEST_DELAY = 0.4  # seconds between yfinance calls to avoid rate-limiting


# ── File I/O ──────────────────────────────────────────────────────────────────

def _load_exclusions() -> dict:
    if not EXCLUSIONS_PATH.exists():
        logger.info("No exclusions file found at %s; starting fresh.", EXCLUSIONS_PATH)
        return {"last_verified": None, "excluded_ars": {}, "excluded_underlyings": {}}
    try:
        return json.loads(EXCLUSIONS_PATH.read_text())
    except Exception as exc:
        logger.error("Failed to read exclusions file: %s — starting fresh.", exc)
        return {"last_verified": None, "excluded_ars": {}, "excluded_underlyings": {}}


def _save_exclusions(data: dict) -> None:
    data["last_verified"] = date.today().isoformat()
    EXCLUSIONS_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    logger.info("Exclusions saved → %s", EXCLUSIONS_PATH)


def _load_universe_tickers() -> Tuple[List[str], List[str]]:
    """Return (symbol_ars_list, symbol_underlying_list) from the local snapshot."""
    raw = json.loads(SNAPSHOT_PATH.read_text())
    ars: List[str] = []
    underlyings: List[str] = []
    seen_underlyings: set = set()
    for item in raw.get("tickers", []):
        if sym := item.get("symbol_ars"):
            ars.append(sym)
        if und := item.get("symbol_underlying"):
            if und not in seen_underlyings:
                underlyings.append(und)
                seen_underlyings.add(und)
    return ars, underlyings


# ── Probe functions ───────────────────────────────────────────────────────────

def _probe_ars(symbol_ars: str) -> bool:
    """True if yfinance returns any price data for this BYMA ticker."""
    from data.prices import fetch_prices
    try:
        df = fetch_prices(symbol_ars, lookback_days=_PRICE_LOOKBACK)
        return df is not None and not df.empty
    except Exception:
        return False


def _probe_underlying(symbol: str) -> bool:
    """True if yfinance has a last price for this underlying (fast, no income stmt)."""
    try:
        last_price = yf.Ticker(symbol).fast_info.last_price
        return last_price is not None
    except Exception:
        return False


# ── Mode 1: check excluded tickers for recovery ───────────────────────────────

def verify_excluded(exclusions: dict) -> Tuple[List[str], List[str]]:
    """Probe each excluded ticker; return (recovered_ars, recovered_underlyings)."""
    recovered_ars: List[str] = []
    recovered_underlyings: List[str] = []

    excluded_ars: Dict[str, dict] = exclusions.get("excluded_ars", {})
    if excluded_ars:
        logger.info("Checking %d excluded ARS tickers…", len(excluded_ars))
    for ticker in list(excluded_ars):
        if _probe_ars(ticker):
            logger.info("  recovered: %s", ticker)
            recovered_ars.append(ticker)
        else:
            logger.debug("  still excluded: %s", ticker)
        time.sleep(_REQUEST_DELAY)

    excluded_underlyings: Dict[str, dict] = exclusions.get("excluded_underlyings", {})
    if excluded_underlyings:
        logger.info("Checking %d excluded underlyings…", len(excluded_underlyings))
    for ticker in list(excluded_underlyings):
        if _probe_underlying(ticker):
            logger.info("  recovered: %s", ticker)
            recovered_underlyings.append(ticker)
        else:
            logger.debug("  still excluded: %s", ticker)
        time.sleep(_REQUEST_DELAY)

    return recovered_ars, recovered_underlyings


# ── Mode 2: check universe for new failures ───────────────────────────────────

def verify_new(
    exclusions: dict,
    ars_tickers: List[str],
    underlying_tickers: List[str],
) -> Tuple[List[str], List[str]]:
    """Probe tickers NOT in the exclusion list; return (newly_failed_ars, newly_failed_underlyings)."""
    excluded_ars = set(exclusions.get("excluded_ars", {}))
    excluded_underlyings = set(exclusions.get("excluded_underlyings", {}))

    to_check_ars = [t for t in ars_tickers if t not in excluded_ars]
    to_check_underlyings = [t for t in underlying_tickers if t not in excluded_underlyings]

    newly_failed_ars: List[str] = []
    newly_failed_underlyings: List[str] = []

    logger.info("Checking %d ARS tickers from universe…", len(to_check_ars))
    for ticker in to_check_ars:
        if not _probe_ars(ticker):
            logger.warning("  failed → will exclude: %s", ticker)
            newly_failed_ars.append(ticker)
        else:
            logger.debug("  ok: %s", ticker)
        time.sleep(_REQUEST_DELAY)

    logger.info("Checking %d underlyings from universe…", len(to_check_underlyings))
    for ticker in to_check_underlyings:
        if not _probe_underlying(ticker):
            logger.warning("  failed → will exclude: %s", ticker)
            newly_failed_underlyings.append(ticker)
        else:
            logger.debug("  ok: %s", ticker)
        time.sleep(_REQUEST_DELAY)

    return newly_failed_ars, newly_failed_underlyings


# ── Mutations ─────────────────────────────────────────────────────────────────

def _apply_recoveries(exclusions: dict, recovered_ars: List[str], recovered_underlyings: List[str]) -> None:
    for ticker in recovered_ars:
        exclusions["excluded_ars"].pop(ticker, None)
    for ticker in recovered_underlyings:
        exclusions["excluded_underlyings"].pop(ticker, None)


def _apply_new_failures(exclusions: dict, failed_ars: List[str], failed_underlyings: List[str]) -> None:
    today = date.today().isoformat()
    for ticker in failed_ars:
        if ticker not in exclusions["excluded_ars"]:
            exclusions["excluded_ars"][ticker] = {"reason": "failed_verification", "excluded_at": today}
    for ticker in failed_underlyings:
        if ticker not in exclusions["excluded_underlyings"]:
            exclusions["excluded_underlyings"][ticker] = {"reason": "failed_verification", "excluded_at": today}


# ── Summary ───────────────────────────────────────────────────────────────────

def _print_summary(
    recovered_ars: List[str],
    recovered_underlyings: List[str],
    failed_ars: List[str],
    failed_underlyings: List[str],
    exclusions: dict,
) -> None:
    total_recovered = len(recovered_ars) + len(recovered_underlyings)
    total_failed = len(failed_ars) + len(failed_underlyings)
    total_excluded = len(exclusions.get("excluded_ars", {})) + len(exclusions.get("excluded_underlyings", {}))

    sep = "─" * 44
    print(f"\n{sep}")
    print(f"  recovered:        {total_recovered:3d}  (ARS: {len(recovered_ars)}, underlyings: {len(recovered_underlyings)})")
    print(f"  newly excluded:   {total_failed:3d}  (ARS: {len(failed_ars)}, underlyings: {len(failed_underlyings)})")
    print(f"  unchanged:        {total_excluded - total_failed:3d}  (total excluded after update: {total_excluded})")

    if recovered_ars:
        print(f"\n  Recovered ARS ({len(recovered_ars)}): {', '.join(recovered_ars)}")
    if recovered_underlyings:
        print(f"  Recovered underlyings ({len(recovered_underlyings)}): {', '.join(recovered_underlyings)}")
    if failed_ars:
        print(f"\n  Newly excluded ARS ({len(failed_ars)}): {', '.join(failed_ars)}")
    if failed_underlyings:
        print(f"  Newly excluded underlyings ({len(failed_underlyings)}): {', '.join(failed_underlyings)}")

    print(f"{sep}\n")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    args = _parse_args()

    exclusions = _load_exclusions()
    ars_tickers, underlying_tickers = _load_universe_tickers()

    recovered_ars: List[str] = []
    recovered_underlyings: List[str] = []
    failed_ars: List[str] = []
    failed_underlyings: List[str] = []

    if not args.new_only:
        logger.info("=== Mode 1: checking currently excluded tickers for recovery ===")
        recovered_ars, recovered_underlyings = verify_excluded(exclusions)
        _apply_recoveries(exclusions, recovered_ars, recovered_underlyings)

    if not args.recover_only:
        logger.info("=== Mode 2: checking universe for new failures ===")
        failed_ars, failed_underlyings = verify_new(exclusions, ars_tickers, underlying_tickers)
        _apply_new_failures(exclusions, failed_ars, failed_underlyings)

    _save_exclusions(exclusions)
    _print_summary(recovered_ars, recovered_underlyings, failed_ars, failed_underlyings, exclusions)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify and update yfinance_exclusions.json.",
        epilog="Run manually when universe_snapshot.json changes or after ~30 days.",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--recover-only",
        action="store_true",
        help="Only check excluded tickers for recovery (skip universe scan).",
    )
    group.add_argument(
        "--new-only",
        action="store_true",
        help="Only scan universe for new failures (skip recovery check).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
