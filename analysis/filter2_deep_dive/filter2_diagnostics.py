"""Filter 2 — diagnostic mode for calibration.

Runs T1 (technical), T2 (fundamentals), T4 (Argentina) over Filter 1 survivors.
News gate (T3) is intentionally skipped: treats every ticker as light_check=clean
so calibration runs are fast and cost-free.

Output:
  - cache/filter2_diagnostics.csv  (gitignored)
  - Console summary: min/p10/p25/median/p75/p90/max per numeric metric,
    split by asset_type (cedear vs. argentine_stock)

Usage:
  python -m analysis.filter2_deep_dive.filter2_diagnostics
  python -m analysis.filter2_deep_dive.filter2_diagnostics --fmp-batch-size 80

--fmp-batch-size N: pre-fetch FMP fundamentals for up to N tickers that lack
  fresh cache, then run the full diagnostic using only cache (no live FMP calls
  during the diagnostic pass). Run on consecutive days to populate the full
  universe within the free-tier 250 req/day cap (~80 tickers × 3 endpoints).
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from data.cache import Cache
from data.models import TickerBundle

from analysis.filter1_quick_sweep import TickerFilterResult

from .argentina_adjustment import compute_argentina_adjustment
from .filter2_models import ArgentinaAdjustment, FundamentalResult, TechnicalResult
from .filter2_runner import _compute_invalidation
from .fundamental_quality import compute_fundamental_quality
from .technical_scoring import compute_technical_score

logger = logging.getLogger(__name__)

_OUTPUT_PATH = Path(__file__).parents[2] / "cache" / "filter2_diagnostics.csv"

_NUMERIC_COLS = [
    "technical_score",
    "trend_regime",
    "breakout_bonus",
    "relative_strength_score",
    "rsi_penalty",
    "weekly_strength",
    "daily_strength",
    "ma_alignment",
    "rsi_value",
    "fundamental_penalty",
    "revenue_slope",
    "eps_slope",
    "argentina_penalty",
    "ccl_vol_penalty",
    "premium_penalty",
    "final_score",
    "invalidation_level_ars",
]

_PERCENTILES = [0, 10, 25, 50, 75, 90, 100]
_PCT_LABELS = ["min", "p10", "p25", "median", "p75", "p90", "max"]


def _evaluate_one_diag(
    f1_result: TickerFilterResult,
    bundle: TickerBundle,
    cache: Cache,
) -> Optional[Dict]:
    symbol = bundle.metadata.symbol_ars
    asset_type = bundle.metadata.asset_type.value

    row: Dict = {
        "symbol": symbol,
        "asset_type": asset_type,
        "fetch_status": "ok",
        # T1
        "technical_score": None,
        "trend_regime": None,
        "breakout_bonus": None,
        "relative_strength_score": None,
        "rsi_penalty": None,
        "trend_regime_label": None,
        "weekly_strength": None,
        "daily_strength": None,
        "ma_alignment": None,
        "weekly_cap_applied": None,
        "rsi_value": None,
        "rsi_state": None,
        "benchmark_used": None,
        # T2
        "fundamental_state": None,
        "fundamental_penalty": None,
        "revenue_slope": None,
        "eps_slope": None,
        "fcf_positive": None,
        # T4
        "argentina_penalty": None,
        "ccl_vol_penalty": None,
        "premium_penalty": None,
        "a3_flag": None,
        "premium_pct": None,
        # Final score (no news gate)
        "final_score": None,
        "news_gate_note": "news gate skipped for calibration run",
        # Invalidation
        "invalidation_level_ars": None,
        "invalidation_rationale": None,
    }

    if bundle.prices_ars is None or bundle.prices_ars.data.empty:
        row["fetch_status"] = "missing_prices"
        return row

    # T1 — technical score
    try:
        tech: TechnicalResult = compute_technical_score(bundle, cache)
        row["technical_score"] = tech.technical_score
        row["trend_regime"] = tech.trend_regime
        row["breakout_bonus"] = tech.breakout_bonus
        row["relative_strength_score"] = tech.relative_strength_score
        row["rsi_penalty"] = tech.rsi_penalty
        row["trend_regime_label"] = tech.trend_regime_label.value
        row["weekly_strength"] = tech.trend_breakdown.weekly_strength
        row["daily_strength"] = tech.trend_breakdown.daily_strength
        row["ma_alignment"] = tech.trend_breakdown.ma_alignment
        row["weekly_cap_applied"] = tech.trend_breakdown.weekly_cap_applied
        row["rsi_value"] = tech.rsi_value if not np.isnan(tech.rsi_value) else None
        row["rsi_state"] = tech.rsi_state.value
        row["benchmark_used"] = tech.benchmark_used
    except Exception as exc:
        logger.error("%s: technical scoring failed: %s", symbol, exc)
        row["fetch_status"] = f"t1_error: {exc}"
        return row

    # T2 — fundamental quality
    try:
        fund: FundamentalResult = compute_fundamental_quality(bundle)
        row["fundamental_state"] = fund.fundamental_state.value
        row["fundamental_penalty"] = fund.fundamental_penalty
        row["revenue_slope"] = fund.revenue_slope
        row["eps_slope"] = fund.eps_slope
        row["fcf_positive"] = fund.fcf_positive
    except Exception as exc:
        logger.error("%s: fundamental quality failed: %s", symbol, exc)
        row["fetch_status"] = f"t2_error: {exc}"
        return row

    # T4 — Argentina adjustment (T3 skipped)
    try:
        argentina: ArgentinaAdjustment = compute_argentina_adjustment(bundle, cache)
        row["argentina_penalty"] = argentina.total_penalty
        row["ccl_vol_penalty"] = argentina.ccl_vol_penalty
        row["premium_penalty"] = argentina.premium_penalty
        row["a3_flag"] = argentina.a3_flag
        row["premium_pct"] = argentina.premium_pct
    except Exception as exc:
        logger.error("%s: argentina adjustment failed: %s", symbol, exc)
        row["fetch_status"] = f"t4_error: {exc}"
        return row

    # Final score (no news gate deduction)
    fund_pen = fund.fundamental_penalty or 0.0
    arg_pen = argentina.total_penalty or 0.0
    tech_score = tech.technical_score or 0.0
    row["final_score"] = round(max(0.0, tech_score - fund_pen - arg_pen), 2)

    # Invalidation level
    inv_ars, _inv_usd, inv_rationale = _compute_invalidation(bundle, tech)
    row["invalidation_level_ars"] = inv_ars
    row["invalidation_rationale"] = inv_rationale

    return row


def run_diagnostics(
    survivors: List[TickerFilterResult],
    bundles: List[TickerBundle],
    cache: Optional[Cache] = None,
    output_path: Optional[Path] = None,
) -> List[Dict]:
    """Run Filter 2 diagnostic pass over all Filter 1 survivors.

    News gate is skipped. Returns the list of row dicts (also written to CSV).
    """
    if cache is None:
        cache = Cache()
    if output_path is None:
        output_path = _OUTPUT_PATH

    bundle_map = {b.metadata.symbol_ars: b for b in bundles}
    logger.info("Diagnostic run starting — %d survivors, news gate skipped", len(survivors))

    rows: List[Dict] = []
    for i, f1_result in enumerate(survivors, start=1):
        symbol = f1_result.symbol
        bundle = bundle_map.get(symbol)
        if bundle is None:
            logger.warning("%s: no bundle — skipping", symbol)
            rows.append({"symbol": symbol, "asset_type": "unknown", "fetch_status": "no_bundle"})
            continue

        if i % 50 == 0 or i == 1:
            logger.info("  %d/%d — %s", i, len(survivors), symbol)

        row = _evaluate_one_diag(f1_result, bundle, cache)
        if row is not None:
            rows.append(row)

    # Write CSV
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if rows:
        fieldnames = list(rows[0].keys())
        with output_path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        logger.info("CSV written → %s (%d rows)", output_path, len(rows))

    return rows


def print_summary(rows: List[Dict]) -> None:
    """Print min/p10/p25/median/p75/p90/max for each numeric column, split by asset_type."""
    asset_types = sorted({r.get("asset_type", "unknown") for r in rows if r.get("asset_type")})

    for atype in asset_types:
        subset = [r for r in rows if r.get("asset_type") == atype and r.get("fetch_status") == "ok"]
        print(f"\n{'=' * 72}")
        print(f"  asset_type={atype}   n={len(subset)}")
        print(f"{'=' * 72}")
        print(f"  {'metric':<32}  {'min':>7}  {'p10':>7}  {'p25':>7}  {'med':>7}  {'p75':>7}  {'p90':>7}  {'max':>7}")
        print(f"  {'-' * 32}  {'-' * 7}  {'-' * 7}  {'-' * 7}  {'-' * 7}  {'-' * 7}  {'-' * 7}  {'-' * 7}")

        for col in _NUMERIC_COLS:
            vals = [r[col] for r in subset if r.get(col) is not None]
            if not vals:
                print(f"  {col:<32}  {'—':>7}  (no data)")
                continue
            arr = np.array(vals, dtype=float)
            arr = arr[~np.isnan(arr)]
            if len(arr) == 0:
                print(f"  {col:<32}  {'—':>7}  (all NaN)")
                continue
            pcts = np.percentile(arr, _PERCENTILES)
            vals_str = "  ".join(f"{v:7.2f}" for v in pcts)
            n_str = f"n={len(arr)}"
            print(f"  {col:<32}  {vals_str}  ({n_str})")

    # Overall fetch status breakdown
    print(f"\n{'=' * 72}")
    print("  fetch_status breakdown (all tickers)")
    print(f"{'=' * 72}")
    statuses: Dict[str, int] = {}
    for r in rows:
        s = r.get("fetch_status", "unknown")
        statuses[s] = statuses.get(s, 0) + 1
    for s, count in sorted(statuses.items(), key=lambda x: -x[1]):
        print(f"  {s:<40}  {count}")


# ── FMP batch pre-fetch ────────────────────────────────────────────────────────

def _prefetch_fmp_batch(cache: Cache, batch_size: int) -> int:
    """Pre-fetch FMP fundamentals for up to batch_size tickers without fresh cache.

    Identifies CEDEAR underlyings that lack fresh fundamentals cache and fetches
    them one by one up to batch_size. Returns the number of tickers fetched.
    Callers should then run fetch_universe_bundle with FMP_API_KEY unset so that
    only the pre-fetched (now cached) data is used in the diagnostic pass.
    """
    from data.universe import load_universe
    from data.fundamentals import fetch_fundamentals, is_quota_exhausted
    from data.models import AssetType

    tickers = load_universe()
    # Map underlying → ars symbol so we can check the price cache
    cedear_pairs = [
        (m.symbol_underlying, m.symbol_ars)
        for m in tickers
        if m.asset_type == AssetType.CEDEAR and m.symbol_underlying
    ]
    cedear_underlyings = [sym for sym, _ in cedear_pairs]
    underlying_to_ars = {sym: ars for sym, ars in cedear_pairs}

    # Determine which ones lack fresh cache (same check as fetch_fundamentals)
    stale = [s for s in cedear_underlyings if not cache.fundamentals_are_fresh(s)]

    # Skip tickers whose yfinance price data is missing — no point fetching
    # fundamentals for a CEDEAR that has no price in the Argentine market
    no_price: list[str] = []
    eligible: list[str] = []
    for sym in stale:
        ars = underlying_to_ars[sym]
        if cache.load_prices(ars) is None:
            no_price.append(sym)
        else:
            eligible.append(sym)

    if no_price:
        logger.info(
            "FMP batch: skipping %d tickers with no price data in yfinance: %s",
            len(no_price), ", ".join(no_price),
        )

    to_fetch = eligible[:batch_size]

    if not to_fetch:
        logger.info("FMP batch: all CEDEAR underlyings already have fresh cache; nothing to fetch")
        return 0

    logger.info(
        "FMP batch: %d stale / %d total — %d skipped (no price) — fetching up to %d",
        len(stale), len(cedear_underlyings), len(no_price), batch_size,
    )

    fetched = 0
    for i, sym in enumerate(to_fetch, start=1):
        logger.info("  FMP [%d/%d] %s", i, len(to_fetch), sym)
        result = fetch_fundamentals(sym, cache)
        if result is not None:
            fetched += 1
            if i < len(to_fetch):
                time.sleep(15)  # 3 endpoints/ticker at ~4s each = ~12s; 15s total keeps us under the per-minute cap
        elif is_quota_exhausted():
            remaining = len(stale) - fetched
            logger.warning(
                "FMP batch: quota exhausted after %d ticker(s) — %d remaining stale "
                "(run again tomorrow or increase plan limit)",
                fetched, remaining,
            )
            break
        else:
            logger.warning("  FMP [%d/%d] %s → no data (symbol not covered or not available on free tier)", i, len(to_fetch), sym)

    logger.info(
        "FMP batch complete — %d fetched, %d skipped (no price), %d remaining stale",
        fetched, len(no_price), len(stale) - fetched,
    )
    return fetched


# ── CLI entry point ────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Filter 2 diagnostic calibration run")
    parser.add_argument(
        "--fmp-batch-size",
        type=int,
        default=0,
        metavar="N",
        help=(
            "Pre-fetch FMP fundamentals for up to N tickers without fresh cache, "
            "then run diagnostics using only cache. Default 0 = use whatever is "
            "already cached, no new FMP calls."
        ),
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s  %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )

    cache = Cache()

    # Optional FMP pre-fetch phase
    if args.fmp_batch_size > 0:
        if not os.environ.get("FMP_API_KEY"):
            print("ERROR: --fmp-batch-size requires FMP_API_KEY to be set")
            sys.exit(1)
        print(f"FMP pre-fetch: up to {args.fmp_batch_size} tickers...")
        fetched = _prefetch_fmp_batch(cache, args.fmp_batch_size)
        print(f"FMP pre-fetch complete — {fetched} tickers fetched into cache")
        # Disable FMP for the diagnostic pass so fetch_universe_bundle uses only cache
        fmp_key = os.environ.pop("FMP_API_KEY", None)
    else:
        fmp_key = None

    print("Loading universe and running Filter 1...")
    from data.fetcher import fetch_universe_bundle
    from analysis.filter1_quick_sweep import run_filter1

    bundles, _ = fetch_universe_bundle(cache)
    f1_report = run_filter1(bundles)
    survivors = f1_report.survivors
    print(f"Filter 1 survivors: {len(survivors)}")

    # Restore FMP key after fetch_universe_bundle (not needed here, but clean)
    if fmp_key is not None:
        os.environ["FMP_API_KEY"] = fmp_key

    print("\nRunning Filter 2 diagnostics (news gate skipped)...")
    rows = run_diagnostics(survivors, bundles, cache)

    print(f"\nDiagnostic complete — {len(rows)} rows written to {_OUTPUT_PATH}")
    print_summary(rows)


if __name__ == "__main__":
    main()
