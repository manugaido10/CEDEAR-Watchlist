"""Filter 1 diagnostic layer — raw metric extraction.

Extracts the numeric values that each Filter 1 criterion evaluates, WITHOUT
applying any threshold or producing a pass/fail verdict. The output is a flat
CSV row per ticker, intended to let the analyst see the distribution of real
values across the universe and calibrate thresholds from data.

This module is intentionally separate from filter1_quick_sweep.py so that
diagnostics can be re-run after threshold changes without re-fetching data.
"""
from __future__ import annotations

import csv
import logging
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import List, Optional

import numpy as np

from data.models import AssetType, FetchStatus, TickerBundle
from analysis.filter1_thresholds import (
    C4_LOOKBACK_DAYS,
    C5_CONSECUTIVE_CLOSES_BELOW,
    C5_MA200_SLOPE_LOOKBACK,
    C5_SUPPORT_LOOKBACK_BARS,
)

logger = logging.getLogger(__name__)


@dataclass
class DiagnosticsRow:
    # ── Identity ────────────────────────────────────────────────────────────
    symbol: str
    asset_type: str
    fetch_status: str

    # ── C1: Solvency ─────────────────────────────────────────────────────
    c1_net_debt_usd_m: Optional[float] = None
    c1_fcf_usd_m: Optional[float] = None
    # nd_fcf_ratio: computed only when net_debt>0 AND fcf>0
    c1_nd_fcf_ratio: Optional[float] = None
    # which branch the check would enter (informational, not the verdict)
    c1_branch: Optional[str] = None   # "net_cash" | "nd/fcf" | "abs_nd_neg_fcf" | "skip"
    c1_skip: Optional[str] = None

    # ── C2: EPS trend ────────────────────────────────────────────────────
    c2_eps_n_quarters: Optional[int] = None
    c2_eps_now: Optional[float] = None
    c2_eps_5q_ago: Optional[float] = None
    c2_yoy_change: Optional[float] = None   # (eps_now - eps_5q_ago) / |eps_5q_ago|
    c2_norm_slope: Optional[float] = None   # slope / mean_abs_eps
    c2_skip: Optional[str] = None

    # ── C4: Liquidity ────────────────────────────────────────────────────
    c4_median_daily_ars: Optional[float] = None
    c4_skip: Optional[str] = None

    # ── C5: Technical trend ───────────────────────────────────────────────
    c5_last_close: Optional[float] = None
    c5_ma200: Optional[float] = None
    c5_pct_vs_ma200: Optional[float] = None        # (close/ma200 - 1) * 100
    c5_ma200_norm_slope: Optional[float] = None    # per-bar, normalized by ma200 level
    c5_support_6m: Optional[float] = None
    c5_pct_vs_support: Optional[float] = None      # (close/support - 1) * 100
    c5_consec_below_support: Optional[int] = None  # consecutive closes < support_6m
    c5_skip: Optional[str] = None


def extract_diagnostics(bundle: TickerBundle) -> DiagnosticsRow:
    """Extract all raw diagnostic metrics from a single TickerBundle."""
    symbol = bundle.metadata.symbol_ars
    asset_type = bundle.metadata.asset_type.value
    status = bundle.status.value

    row = DiagnosticsRow(symbol=symbol, asset_type=asset_type, fetch_status=status)

    # C1 / C2: require fundamentals
    _fill_c1(row, bundle)
    _fill_c2(row, bundle)

    # C4 / C5: require price data; skip when PARTIAL (mirrors filter logic)
    skip_tech = bundle.status == FetchStatus.PARTIAL
    _fill_c4(row, bundle, skip_tech)
    _fill_c5(row, bundle, skip_tech)

    return row


# ── C1 ────────────────────────────────────────────────────────────────────────

def _fill_c1(row: DiagnosticsRow, bundle: TickerBundle) -> None:
    f = bundle.fundamentals
    if f is None:
        row.c1_skip = "no fundamentals"
        return
    if f.net_debt is None:
        row.c1_skip = "net_debt is None"
        return
    if f.free_cash_flow is None:
        row.c1_skip = "free_cash_flow is None"
        return

    row.c1_net_debt_usd_m = f.net_debt
    row.c1_fcf_usd_m = f.free_cash_flow
    nd, fcf = f.net_debt, f.free_cash_flow

    if nd <= 0:
        row.c1_branch = "net_cash"
    elif fcf > 0:
        row.c1_nd_fcf_ratio = nd / fcf
        row.c1_branch = "nd/fcf"
    else:
        row.c1_branch = "abs_nd_neg_fcf"


# ── C2 ────────────────────────────────────────────────────────────────────────

def _fill_c2(row: DiagnosticsRow, bundle: TickerBundle) -> None:
    f = bundle.fundamentals
    if f is None:
        row.c2_skip = "no fundamentals"
        return

    eps = f.eps_quarterly
    n = len(eps) if eps else 0
    row.c2_eps_n_quarters = n

    if not eps or n < 2:
        row.c2_skip = f"only {n} EPS quarters"
        return

    arr = np.array(eps, dtype=float)
    mean_abs = float(np.mean(np.abs(arr)))

    if mean_abs >= 1e-6:
        slope, _ = np.polyfit(np.arange(n, dtype=float), arr, 1)
        row.c2_norm_slope = float(slope / mean_abs)
    else:
        row.c2_skip = "EPS near-zero; slope not computable"

    if n >= 5:
        row.c2_eps_now = float(arr[-1])
        row.c2_eps_5q_ago = float(arr[-5])
        if abs(arr[-5]) >= 1e-6:
            row.c2_yoy_change = float((arr[-1] - arr[-5]) / abs(arr[-5]))
        else:
            # Still fill slope; only YoY is undefined
            if row.c2_skip is None:
                row.c2_skip = "eps_5q_ago near-zero"
    else:
        # We can still report slope even if not enough for YoY
        if row.c2_skip is None:
            row.c2_skip = f"only {n} quarters (need 5 for YoY)"


# ── C4 ────────────────────────────────────────────────────────────────────────

def _fill_c4(row: DiagnosticsRow, bundle: TickerBundle, skip_tech: bool) -> None:
    if skip_tech:
        row.c4_skip = "partial data"
        return
    if bundle.prices_ars is None:
        row.c4_skip = "no price data"
        return

    df = bundle.prices_ars.data
    if len(df) < C4_LOOKBACK_DAYS:
        row.c4_skip = f"only {len(df)} bars (need {C4_LOOKBACK_DAYS})"
        return

    recent = df.iloc[-C4_LOOKBACK_DAYS:]
    row.c4_median_daily_ars = float((recent["volume"] * recent["close"]).median())


# ── C5 ────────────────────────────────────────────────────────────────────────

def _fill_c5(row: DiagnosticsRow, bundle: TickerBundle, skip_tech: bool) -> None:
    if skip_tech:
        row.c5_skip = "partial data"
        return
    if bundle.prices_ars is None:
        row.c5_skip = "no price data"
        return

    df = bundle.prices_ars.data
    n = len(df)

    if n < 200:
        row.c5_skip = f"only {n} bars (need 200 for MA200)"
        return

    # Forward-fill gaps in price series before any MA/slope computation;
    # yfinance returns NaN for non-trading days on some CEDEAR tickers.
    close_series = df["close"].astype(float).ffill()
    close = close_series.values
    ma200 = np.convolve(close, np.ones(200) / 200, mode="valid")
    last_close = float(close[-1])
    last_ma200 = float(ma200[-1])

    row.c5_last_close = last_close
    row.c5_ma200 = last_ma200
    if last_ma200 > 0:
        row.c5_pct_vs_ma200 = (last_close / last_ma200 - 1.0) * 100.0

    lookback = min(C5_MA200_SLOPE_LOOKBACK, len(ma200))
    if lookback >= 2:
        ma200_slice = ma200[-lookback:]
        raw_slope, _ = np.polyfit(np.arange(lookback, dtype=float), ma200_slice, 1)
        row.c5_ma200_norm_slope = float(raw_slope / last_ma200) if last_ma200 > 0 else float(raw_slope)

    # 6m support + consecutive-below count
    required = C5_SUPPORT_LOOKBACK_BARS + C5_CONSECUTIVE_CLOSES_BELOW
    if n < required:
        # Can still report what we have above; just note support is unavailable
        row.c5_skip = f"only {n} bars for 6m support ({required} needed)"
        return

    support_window = close[-(C5_SUPPORT_LOOKBACK_BARS + C5_CONSECUTIVE_CLOSES_BELOW):-C5_CONSECUTIVE_CLOSES_BELOW]
    if len(support_window) >= 5:
        support_6m = float(np.min(support_window))
        row.c5_support_6m = support_6m
        if support_6m > 0:
            row.c5_pct_vs_support = (last_close / support_6m - 1.0) * 100.0
        recent_closes = close[-C5_CONSECUTIVE_CLOSES_BELOW:]
        row.c5_consec_below_support = int(np.sum(recent_closes < support_6m))


# ── CSV output ────────────────────────────────────────────────────────────────

_CSV_FIELDS = [f.name for f in fields(DiagnosticsRow)]


def write_csv(rows: List[DiagnosticsRow], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=_CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: v for k, v in asdict(row).items()})
    logger.info("Diagnostics CSV written: %s (%d rows)", path, len(rows))


# ── Console summary ───────────────────────────────────────────────────────────

def print_summary(rows: List[DiagnosticsRow]) -> None:
    """Print percentile stats for each criterion, split by asset_type."""
    cedears = [r for r in rows if r.asset_type == AssetType.CEDEAR.value]
    stocks  = [r for r in rows if r.asset_type == AssetType.ARGENTINE_STOCK.value]

    print("\n" + "=" * 70)
    print("FILTER 1 — DIAGNOSTIC SUMMARY (raw values, no thresholds applied)")
    print("=" * 70)

    for label, subset in [("CEDEAR", cedears), ("Argentine stock", stocks)]:
        print(f"\n── {label} (n={len(subset)}) ──────────────────────────────────────────")

        _stat_block("C1 net_debt/FCF ratio (x)",
                    [r.c1_nd_fcf_ratio for r in subset],
                    skip_count=sum(1 for r in subset if r.c1_skip))
        _stat_block("C1 net_debt (USD M)",
                    [r.c1_net_debt_usd_m for r in subset])
        _stat_block("C1 FCF (USD M)",
                    [r.c1_fcf_usd_m for r in subset])

        _stat_block("C2 norm_slope (per quarter)",
                    [r.c2_norm_slope for r in subset],
                    skip_count=sum(1 for r in subset if r.c2_skip and not r.c2_norm_slope))
        _stat_block("C2 YoY EPS change (%)",
                    [r.c2_yoy_change * 100 if r.c2_yoy_change is not None else None
                     for r in subset])

        _stat_block(f"C4 median daily ARS (over {C4_LOOKBACK_DAYS}d)",
                    [r.c4_median_daily_ars for r in subset],
                    skip_count=sum(1 for r in subset if r.c4_skip))

        _stat_block("C5 % vs MA200",
                    [r.c5_pct_vs_ma200 for r in subset],
                    skip_count=sum(1 for r in subset if r.c5_skip))
        _stat_block("C5 MA200 norm slope (per bar)",
                    [r.c5_ma200_norm_slope for r in subset])
        _stat_block("C5 % vs 6m support",
                    [r.c5_pct_vs_support for r in subset])
        _stat_block(f"C5 consec closes below 6m support (max={C5_CONSECUTIVE_CLOSES_BELOW})",
                    [r.c5_consec_below_support for r in subset])

    _print_skip_summary(rows)
    print()


def _stat_block(label: str, values: List[Optional[float]], skip_count: int = 0) -> None:
    vals = [v for v in values if v is not None]
    n_skip = skip_count or (len(values) - len(vals))
    if not vals:
        print(f"  {label}: no data (all {n_skip} skipped)")
        return
    arr = np.array(vals, dtype=float)
    print(
        f"  {label}:\n"
        f"    n={len(vals)}  skipped={n_skip}\n"
        f"    min={np.min(arr):.4g}  p10={np.percentile(arr,10):.4g}"
        f"  p25={np.percentile(arr,25):.4g}  median={np.median(arr):.4g}"
        f"  p75={np.percentile(arr,75):.4g}  p90={np.percentile(arr,90):.4g}"
        f"  max={np.max(arr):.4g}"
    )


def _print_skip_summary(rows: List[DiagnosticsRow]) -> None:
    print("\n── Skip reasons ──────────────────────────────────────────────────────")
    for crit, attr in [("C1", "c1_skip"), ("C2", "c2_skip"), ("C4", "c4_skip"), ("C5", "c5_skip")]:
        from collections import Counter
        reasons = Counter(getattr(r, attr) for r in rows if getattr(r, attr))
        if reasons:
            print(f"  {crit}: {dict(reasons)}")
