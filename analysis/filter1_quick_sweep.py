"""Filter 1 — quick sweep over the full universe.

Receives a list of TickerBundle (from the data layer) and returns a Filter1Report
classifying every ticker as survivor / discarded / unevaluable.

Design rules (DECISIONS.md 2026-06-21):
- A ticker passes if it fires NO discard check, not because it "approves" checks.
- Missing data → check does not run → does not vote for discard.
- Compound checks (C5) use conjunction, not disjunction.
- Thresholds are tilted toward "clearly bad" — calibration happens after the first run.
- C3 (profit warning) is not implemented here; delegated to Filter 2.
- Argentine stock extra gates (A1/A2) come from argentina_risk_flags.yaml only;
  technical thresholds (C4/C5) are symmetric between CEDEARs and Argentine stocks.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import yaml

from data.models import AssetType, FetchStatus, TickerBundle
from analysis.filter1_thresholds import (
    C1_MAX_ND_FCF_RATIO,
    C1_MIN_NET_DEBT_ABS_NEG_FCF,
    C2_EPS_CHANGE_VS_4Q,
    C2_EPS_SLOPE_THRESHOLD,
    C2_MIN_EPS_PERIODS,
    C4_LOOKBACK_DAYS,
    C4_MIN_DAILY_VOLUME_ARS,
    C5_CONSECUTIVE_CLOSES_BELOW,
    C5_MA200_SLOPE_LOOKBACK,
    C5_MA200_SLOPE_THRESHOLD,
    C5_SUPPORT_LOOKBACK_BARS,
)

logger = logging.getLogger(__name__)

_DEFAULT_FLAGS_FILE = Path(__file__).parent / "argentina_risk_flags.yaml"


# ── Output models ──────────────────────────────────────────────────────────────

class FilterCategory(str, Enum):
    SURVIVOR = "survivor"
    DISCARDED = "discarded"
    UNEVALUABLE = "unevaluable"


@dataclass
class DiscardTrigger:
    criterion: str  # "C1" | "C2" | "C4" | "C5" | "A1" | "A2"
    detail: str     # the value / condition that fired the check


@dataclass
class TickerFilterResult:
    symbol: str
    asset_type: str
    category: FilterCategory
    checks_run: List[str] = field(default_factory=list)
    checks_skipped: List[str] = field(default_factory=list)
    discard_triggers: List[DiscardTrigger] = field(default_factory=list)
    survival_reason: str = ""      # non-empty for survivors; built from checks_run
    unevaluable_reason: str = ""   # non-empty for unevaluable
    priority_attention: bool = False  # set by A3 flag; meaningful for survivors


@dataclass
class Filter1Summary:
    run_date: date
    total: int
    survivors: int
    discarded: int
    unevaluable: int
    no_fundamentals: int                          # tickers where fundamentals is None
    discard_by_criterion: Dict[str, int] = field(default_factory=dict)


@dataclass
class Filter1Report:
    survivors: List[TickerFilterResult]
    discarded: List[TickerFilterResult]
    unevaluable: List[TickerFilterResult]
    summary: Filter1Summary


# ── YAML loader ────────────────────────────────────────────────────────────────

def _load_risk_flags(path: Path) -> Dict[str, Dict[str, str]]:
    """Load Argentina risk flags YAML. Returns empty dict if file is missing or has no tickers."""
    if not path.exists():
        logger.warning("Argentina risk flags file not found at %s; proceeding with no flags", path)
        return {}
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data.get("tickers") or {}


# ── Individual checks ──────────────────────────────────────────────────────────
# Each check returns (DiscardTrigger | None, skip_reason: str).
# - skip_reason non-empty → check did not run (data missing); no discard vote.
# - trigger non-None → check ran and fired.
# - trigger None + skip_reason empty → check ran and did not fire.

def _check_c1_solvency(bundle: TickerBundle) -> Tuple[Optional[DiscardTrigger], str]:
    """C1: Impayable debt or accelerated solvency deterioration (clearly bad, not subtle).

    Fires when:
      - net_debt > 0 AND fcf > 0 AND net_debt/fcf > C1_MAX_ND_FCF_RATIO, OR
      - net_debt > 0 AND fcf <= 0 AND net_debt > C1_MIN_NET_DEBT_ABS_NEG_FCF.
    Both net_debt and fcf must be present; missing either → skip (no discard).
    """
    f = bundle.fundamentals
    if f is None:
        return None, "no fundamentals"
    if f.net_debt is None:
        return None, "net_debt is None"
    if f.free_cash_flow is None:
        return None, "free_cash_flow is None"

    nd = f.net_debt
    fcf = f.free_cash_flow

    if nd <= 0:
        # Net cash position — clearly solvent on this check.
        return None, ""

    if fcf > 0:
        ratio = nd / fcf
        if ratio > C1_MAX_ND_FCF_RATIO:
            return (
                DiscardTrigger(
                    "C1",
                    f"net_debt/fcf={ratio:.1f}x > {C1_MAX_ND_FCF_RATIO}x "
                    f"(net_debt=${nd:.0f}M, fcf=${fcf:.0f}M USD)",
                ),
                "",
            )
    else:
        # fcf <= 0: cannot service debt from operations at all.
        if nd > C1_MIN_NET_DEBT_ABS_NEG_FCF:
            return (
                DiscardTrigger(
                    "C1",
                    f"net_debt=${nd:.0f}M USD with non-positive fcf=${fcf:.0f}M USD",
                ),
                "",
            )

    return None, ""


def _check_c2_eps_trend(bundle: TickerBundle) -> Tuple[Optional[DiscardTrigger], str]:
    """C2: Sustained and marked earnings decline.

    Fires only when BOTH conditions are true (conjunction):
      (a) normalized EPS slope < C2_EPS_SLOPE_THRESHOLD (sustained negative trend), AND
      (b) eps_now < eps_4q_ago by more than C2_EPS_CHANGE_VS_4Q (marked YoY decline).

    Requires C2_MIN_EPS_PERIODS quarters; missing data → skip.
    """
    f = bundle.fundamentals
    if f is None:
        return None, "no fundamentals"

    eps = f.eps_quarterly
    if not eps or len(eps) < C2_MIN_EPS_PERIODS:
        return None, f"only {len(eps) if eps else 0} EPS quarters (need {C2_MIN_EPS_PERIODS})"

    arr = np.array(eps, dtype=float)
    n = len(arr)

    # Normalize slope by mean absolute EPS so the threshold is scale-invariant.
    mean_abs = float(np.mean(np.abs(arr)))
    if mean_abs < 1e-6:
        return None, "EPS values near-zero; slope normalization not possible"

    indices = np.arange(n, dtype=float)
    slope, _ = np.polyfit(indices, arr, 1)
    norm_slope = slope / mean_abs

    # YoY comparison: current quarter vs same quarter one year ago (4 periods back).
    if n < 5:
        return None, f"only {n} EPS quarters; need 5 for YoY comparison"

    eps_now = arr[-1]
    eps_4q_ago = arr[-5]
    if abs(eps_4q_ago) < 1e-6:
        return None, "eps_4q_ago near-zero; YoY change cannot be computed"

    change_vs_4q = (eps_now - eps_4q_ago) / abs(eps_4q_ago)

    slope_fires = norm_slope < C2_EPS_SLOPE_THRESHOLD
    change_fires = change_vs_4q < C2_EPS_CHANGE_VS_4Q

    if slope_fires and change_fires:
        return (
            DiscardTrigger(
                "C2",
                f"norm_slope={norm_slope:.3f} < {C2_EPS_SLOPE_THRESHOLD} "
                f"AND yoy_change={change_vs_4q:.1%} < {C2_EPS_CHANGE_VS_4Q:.0%}",
            ),
            "",
        )

    return None, ""


def _check_c4_liquidity(
    bundle: TickerBundle,
    skip_for_partial: bool,
) -> Tuple[Optional[DiscardTrigger], str]:
    """C4: Insufficient liquidity — median daily traded value (ARS) over lookback window.

    Proxy: yfinance/BYMA volume × close, not Cocos-specific (known limitation per DECISIONS.md).
    Skipped for PARTIAL status (insufficient bars for MA200, per design spec).
    """
    if skip_for_partial:
        return None, "skipped (partial data — insufficient bars for MA200)"
    if bundle.prices_ars is None:
        return None, "no price data"

    df = bundle.prices_ars.data
    if len(df) < C4_LOOKBACK_DAYS:
        return None, f"only {len(df)} bars (need {C4_LOOKBACK_DAYS})"

    recent = df.iloc[-C4_LOOKBACK_DAYS:]
    daily_value = recent["volume"] * recent["close"]
    median_val = float(daily_value.median())

    if median_val < C4_MIN_DAILY_VOLUME_ARS:
        return (
            DiscardTrigger(
                "C4",
                f"median daily ARS value={median_val:,.0f} < {C4_MIN_DAILY_VOLUME_ARS:,.0f} "
                f"(over {C4_LOOKBACK_DAYS}d)",
            ),
            "",
        )

    return None, ""


def _check_c5_technical_trend(
    bundle: TickerBundle,
    skip_for_partial: bool,
) -> Tuple[Optional[DiscardTrigger], str]:
    """C5: Clearly negative background trend — all three sub-conditions in conjunction:
      1. Last close < MA200.
      2. MA200 slope is negative (over C5_MA200_SLOPE_LOOKBACK bars).
      3. Sustained break below 6m support: last C5_CONSECUTIVE_CLOSES_BELOW closes
         are ALL strictly below the 6m support level.

    If any sub-condition is false, the check does not fire (no discard).
    Skipped for PARTIAL status.
    """
    if skip_for_partial:
        return None, "skipped (partial data — insufficient bars for MA200)"
    if bundle.prices_ars is None:
        return None, "no price data"

    df = bundle.prices_ars.data
    n = len(df)

    if n < 200:
        return None, f"only {n} bars; need 200 for MA200"

    close = df["close"].values.astype(float)

    # MA200 via simple moving average (numpy convolution).
    # ma200[i] = average of close[i : i+200]; last element aligns with last close.
    ma200 = np.convolve(close, np.ones(200) / 200, mode="valid")
    last_close = close[-1]
    last_ma200 = ma200[-1]

    # Sub-condition 1: price below MA200.
    if last_close >= last_ma200:
        return None, ""

    # Sub-condition 2: MA200 slope is negative.
    lookback = min(C5_MA200_SLOPE_LOOKBACK, len(ma200))
    if lookback < 2:
        return None, "not enough MA200 points to measure slope"

    ma200_slice = ma200[-lookback:]
    idx = np.arange(lookback, dtype=float)
    raw_slope, _ = np.polyfit(idx, ma200_slice, 1)
    # Normalize by current MA200 level for a scale-invariant threshold.
    norm_slope = raw_slope / last_ma200 if last_ma200 > 0 else raw_slope

    if norm_slope >= C5_MA200_SLOPE_THRESHOLD:
        return None, ""

    # Sub-condition 3: sustained break below 6-month support.
    # Support = min of closes over the prior 6 months, excluding the last N bars
    # (the ones being tested for the break) to avoid circular definition.
    required = C5_SUPPORT_LOOKBACK_BARS + C5_CONSECUTIVE_CLOSES_BELOW
    if n < required:
        return None, f"only {n} bars; need {required} for 6m support + consecutive check"

    support_window = close[-(C5_SUPPORT_LOOKBACK_BARS + C5_CONSECUTIVE_CLOSES_BELOW): -C5_CONSECUTIVE_CLOSES_BELOW]
    if len(support_window) < 5:
        return None, "support window degenerate (< 5 bars)"

    support_6m = float(np.min(support_window))
    recent_closes = close[-C5_CONSECUTIVE_CLOSES_BELOW:]

    if not np.all(recent_closes < support_6m):
        return None, ""

    return (
        DiscardTrigger(
            "C5",
            f"close={last_close:.2f} < MA200={last_ma200:.2f} "
            f"(MA200 norm_slope={norm_slope:.5f}/bar); "
            f"all {C5_CONSECUTIVE_CLOSES_BELOW} recent closes below 6m support={support_6m:.2f}",
        ),
        "",
    )


def _check_argentina_flags(
    bundle: TickerBundle,
    risk_flags: Dict[str, Dict[str, str]],
) -> Tuple[List[DiscardTrigger], bool, str]:
    """Check A1/A2 (discard) and A3 (priority attention) for Argentine stocks.

    Returns (discard_triggers, priority_attention, skip_reason).
    Tickers not listed in the YAML have no flags — not an error.
    """
    if bundle.metadata.asset_type != AssetType.ARGENTINE_STOCK:
        return [], False, "not an Argentine stock"

    symbol = bundle.metadata.symbol_ars
    flags = risk_flags.get(symbol, {})

    triggers: List[DiscardTrigger] = []
    if "a1" in flags:
        triggers.append(DiscardTrigger("A1", str(flags["a1"])))
    if "a2" in flags:
        triggers.append(DiscardTrigger("A2", str(flags["a2"])))

    priority_attention = "a3" in flags
    return triggers, priority_attention, ""


# ── Bundle evaluation ──────────────────────────────────────────────────────────

def _evaluate_bundle(
    bundle: TickerBundle,
    risk_flags: Dict[str, Dict[str, str]],
) -> TickerFilterResult:
    symbol = bundle.metadata.symbol_ars
    asset_type = bundle.metadata.asset_type.value

    if bundle.status in (FetchStatus.MISSING, FetchStatus.ERROR):
        return TickerFilterResult(
            symbol=symbol,
            asset_type=asset_type,
            category=FilterCategory.UNEVALUABLE,
            unevaluable_reason=f"fetch status={bundle.status.value}",
        )

    # STALE: treat as OK (data is old but exists).
    # PARTIAL: technical checks C4/C5 are skipped (insufficient bars for MA200).
    skip_technical = bundle.status == FetchStatus.PARTIAL
    if skip_technical:
        logger.debug("%s has PARTIAL status; C4 and C5 will be skipped", symbol)

    checks_run: List[str] = []
    checks_skipped: List[str] = []
    discard_triggers: List[DiscardTrigger] = []

    # C1 — Solvency
    trigger, skip_reason = _check_c1_solvency(bundle)
    if skip_reason:
        checks_skipped.append(f"C1 ({skip_reason})")
    else:
        checks_run.append("C1")
        if trigger:
            discard_triggers.append(trigger)

    # C2 — EPS trend
    trigger, skip_reason = _check_c2_eps_trend(bundle)
    if skip_reason:
        checks_skipped.append(f"C2 ({skip_reason})")
    else:
        checks_run.append("C2")
        if trigger:
            discard_triggers.append(trigger)

    # C4 — Liquidity
    trigger, skip_reason = _check_c4_liquidity(bundle, skip_for_partial=skip_technical)
    if skip_reason:
        checks_skipped.append(f"C4 ({skip_reason})")
    else:
        checks_run.append("C4")
        if trigger:
            discard_triggers.append(trigger)

    # C5 — Technical trend
    trigger, skip_reason = _check_c5_technical_trend(bundle, skip_for_partial=skip_technical)
    if skip_reason:
        checks_skipped.append(f"C5 ({skip_reason})")
    else:
        checks_run.append("C5")
        if trigger:
            discard_triggers.append(trigger)

    # A1/A2/A3 — Argentina risk flags (Argentine stocks only)
    arg_triggers, priority_attention, skip_reason = _check_argentina_flags(bundle, risk_flags)
    if skip_reason:
        checks_skipped.append(f"A1/A2 ({skip_reason})")
    else:
        if arg_triggers:
            for t in arg_triggers:
                checks_run.append(t.criterion)
                discard_triggers.append(t)
        else:
            checks_run.append("A1/A2")  # ran, no active flags

    if discard_triggers:
        return TickerFilterResult(
            symbol=symbol,
            asset_type=asset_type,
            category=FilterCategory.DISCARDED,
            checks_run=checks_run,
            checks_skipped=checks_skipped,
            discard_triggers=discard_triggers,
        )

    # Build survival reason from checks that ran (not free text, assembled from checks).
    label_map = {
        "C1": "solvency ok",
        "C2": "earnings trend ok",
        "C4": "liquidity ok",
        "C5": "technical trend ok",
        "A1/A2": "no Argentina risk flags",
        "A1": "no A1 flag",
        "A2": "no A2 flag",
    }
    parts = [label_map[c] for c in checks_run if c in label_map]
    survival_reason = "; ".join(parts) if parts else "passed all available checks"

    return TickerFilterResult(
        symbol=symbol,
        asset_type=asset_type,
        category=FilterCategory.SURVIVOR,
        checks_run=checks_run,
        checks_skipped=checks_skipped,
        survival_reason=survival_reason,
        priority_attention=priority_attention,
    )


# ── Main entry point ───────────────────────────────────────────────────────────

def run_filter1(
    bundles: List[TickerBundle],
    flags_path: Optional[Path] = None,
) -> Filter1Report:
    """Run Filter 1 over the full universe.

    Args:
        bundles: output of fetch_universe_bundle() from the data layer.
        flags_path: override path to argentina_risk_flags.yaml (for testing).

    Returns a Filter1Report with survivors, discarded, unevaluable, and summary.
    """
    risk_flags = _load_risk_flags(flags_path or _DEFAULT_FLAGS_FILE)
    logger.info("Running Filter 1 over %d tickers", len(bundles))

    survivors: List[TickerFilterResult] = []
    discarded: List[TickerFilterResult] = []
    unevaluable: List[TickerFilterResult] = []

    for bundle in bundles:
        result = _evaluate_bundle(bundle, risk_flags)
        if result.category == FilterCategory.SURVIVOR:
            survivors.append(result)
        elif result.category == FilterCategory.DISCARDED:
            discarded.append(result)
        else:
            unevaluable.append(result)

    summary = _build_summary(bundles, survivors, discarded, unevaluable)
    logger.info(
        "Filter 1 complete — survivors=%d discarded=%d unevaluable=%d",
        summary.survivors,
        summary.discarded,
        summary.unevaluable,
    )
    return Filter1Report(
        survivors=survivors,
        discarded=discarded,
        unevaluable=unevaluable,
        summary=summary,
    )


def _build_summary(
    bundles: List[TickerBundle],
    survivors: List[TickerFilterResult],
    discarded: List[TickerFilterResult],
    unevaluable: List[TickerFilterResult],
) -> Filter1Summary:
    no_fundamentals = sum(1 for b in bundles if b.fundamentals is None)

    discard_by_criterion: Dict[str, int] = {}
    for r in discarded:
        for t in r.discard_triggers:
            discard_by_criterion[t.criterion] = discard_by_criterion.get(t.criterion, 0) + 1

    return Filter1Summary(
        run_date=date.today(),
        total=len(bundles),
        survivors=len(survivors),
        discarded=len(discarded),
        unevaluable=len(unevaluable),
        no_fundamentals=no_fundamentals,
        discard_by_criterion=discard_by_criterion,
    )
