"""Filter 2 — Técnica 2: Fundamental quality filter.

Produces FundamentalResult with fundamental_state and fundamental_penalty ∈ [0, 30].
This block only subtracts from the score — it never adds.

States (DISENO_FILTRO_2.md §3.2):
  confirmed    (penalty 0):   revenue_slope >= 0, eps_slope >= -0.05, FCF > 0
  neutral      (penalty 5-10): one condition fails but not clearly bad
  deteriorating(penalty 15-30): revenue clearly declining AND eps/FCF clearly bad
  unknown      (penalty 0):   fundamentals = None — epistemic, not a failure

Financial sector exemption (DISENO_FILTRO_2.md §3.3):
  Bancos/financieras are structurally FCF-negative by design. FCF gate is
  skipped for those tickers. Per the design, Filter 1 already marks them
  unevaluable so they don't reach Filter 2; exemption kept for robustness.
"""

from __future__ import annotations

import logging
from typing import Optional, Tuple

import numpy as np

from data.models import AssetType, FundamentalsSnapshot, TickerBundle

from .filter2_models import FundamentalResult, FundamentalState
from .filter2_thresholds import (
    CONFIRMED_EPS_SLOPE_MIN,
    CONFIRMED_REVENUE_SLOPE_MIN,
    DETERIORATING_EPS_SLOPE_MAX,
    DETERIORATING_REVENUE_SLOPE_MAX,
    FUNDAMENTAL_MIN_PERIODS,
    FUNDAMENTAL_PENALTY_CONFIRMED,
    FUNDAMENTAL_PENALTY_DETERIORATING_BASE,
    FUNDAMENTAL_PENALTY_DETERIORATING_MAX,
    FUNDAMENTAL_PENALTY_NEUTRAL_BASE,
    FUNDAMENTAL_PENALTY_NEUTRAL_MAX,
    FUNDAMENTAL_PENALTY_UNKNOWN,
)

logger = logging.getLogger(__name__)

# Same set as filter1_quick_sweep._FINANCIAL_SECTOR_SKIP_C1 — kept in sync manually.
# These tickers are structurally FCF-negative; the FCF gate does not apply to them.
_FINANCIAL_SECTOR_TICKERS: frozenset = frozenset({
    "C.BA",    # Citigroup
    "WFC.BA",  # Wells Fargo
    "JPM.BA",  # JPMorgan Chase
    "GS.BA",   # Goldman Sachs
})


def _normalized_slope(series: list[float]) -> Optional[float]:
    """Linear regression slope normalized by mean absolute value of the series.

    Returns None if fewer than FUNDAMENTAL_MIN_PERIODS points or near-zero scale.
    """
    if not series or len(series) < FUNDAMENTAL_MIN_PERIODS:
        return None
    arr = np.array(series, dtype=float)
    mean_abs = float(np.mean(np.abs(arr)))
    if mean_abs < 1e-6:
        return None
    idx = np.arange(len(arr), dtype=float)
    slope, _ = np.polyfit(idx, arr, 1)
    return float(slope / mean_abs)


def _compute_neutral_penalty(
    revenue_slope: Optional[float],
    eps_slope: Optional[float],
    fcf_positive: Optional[bool],
) -> float:
    """Compute penalty within the neutral band based on how many conditions fail."""
    penalty = FUNDAMENTAL_PENALTY_NEUTRAL_BASE
    # Each failing condition beyond the first adds weight
    if revenue_slope is not None and revenue_slope < CONFIRMED_REVENUE_SLOPE_MIN:
        # Revenue declining but not clearly deteriorating
        severity = min(abs(revenue_slope) / abs(DETERIORATING_REVENUE_SLOPE_MAX), 1.0)
        penalty += 2.0 * severity
    if eps_slope is not None and eps_slope < CONFIRMED_EPS_SLOPE_MIN:
        severity = min(abs(eps_slope - CONFIRMED_EPS_SLOPE_MIN) / abs(DETERIORATING_EPS_SLOPE_MAX - CONFIRMED_EPS_SLOPE_MIN), 1.0)
        penalty += 2.0 * severity
    if fcf_positive is not None and not fcf_positive:
        penalty += 2.0
    return min(penalty, FUNDAMENTAL_PENALTY_NEUTRAL_MAX)


def _compute_deteriorating_penalty(
    revenue_slope: Optional[float],
    eps_slope: Optional[float],
    fcf_positive: Optional[bool],
) -> float:
    """Compute penalty within the deteriorating band based on severity."""
    penalty = FUNDAMENTAL_PENALTY_DETERIORATING_BASE
    if revenue_slope is not None and revenue_slope < DETERIORATING_REVENUE_SLOPE_MAX:
        # More negative → higher penalty
        severity = min(abs(revenue_slope) / (abs(DETERIORATING_REVENUE_SLOPE_MAX) * 3), 1.0)
        penalty += 7.0 * severity
    if eps_slope is not None and eps_slope < DETERIORATING_EPS_SLOPE_MAX:
        severity = min(abs(eps_slope) / (abs(DETERIORATING_EPS_SLOPE_MAX) * 3), 1.0)
        penalty += 5.0 * severity
    if fcf_positive is not None and not fcf_positive:
        penalty += 3.0
    return min(penalty, FUNDAMENTAL_PENALTY_DETERIORATING_MAX)


def _determine_state_and_penalty(
    revenue_slope: Optional[float],
    eps_slope: Optional[float],
    fcf_positive: Optional[bool],
) -> Tuple[FundamentalState, float]:
    """Map slope/FCF data to a (FundamentalState, penalty) pair."""
    # Unknown: all three data points missing
    if revenue_slope is None and eps_slope is None and fcf_positive is None:
        return FundamentalState.UNKNOWN, FUNDAMENTAL_PENALTY_UNKNOWN

    # Confirmed: all available conditions pass (missing data → not a failure for that condition)
    rev_ok = revenue_slope is None or revenue_slope >= CONFIRMED_REVENUE_SLOPE_MIN
    eps_ok = eps_slope is None or eps_slope >= CONFIRMED_EPS_SLOPE_MIN
    fcf_ok = fcf_positive is None or fcf_positive

    if rev_ok and eps_ok and fcf_ok:
        return FundamentalState.CONFIRMED, FUNDAMENTAL_PENALTY_CONFIRMED

    # Deteriorating: revenue clearly declining AND (eps clearly negative OR FCF negative)
    rev_bad = revenue_slope is not None and revenue_slope < DETERIORATING_REVENUE_SLOPE_MAX
    eps_bad = eps_slope is not None and eps_slope < DETERIORATING_EPS_SLOPE_MAX
    fcf_bad = fcf_positive is not None and not fcf_positive

    if rev_bad and (eps_bad or fcf_bad):
        penalty = _compute_deteriorating_penalty(revenue_slope, eps_slope, fcf_positive)
        return FundamentalState.DETERIORATING, penalty

    # Neutral: at least one condition fails but not clearly deteriorating
    penalty = _compute_neutral_penalty(revenue_slope, eps_slope, fcf_positive)
    return FundamentalState.NEUTRAL, penalty


def _build_summary(
    f: FundamentalsSnapshot,
    state: FundamentalState,
    revenue_slope: Optional[float],
    eps_slope: Optional[float],
    fcf_positive: Optional[bool],
    fcf_exempt: bool,
) -> str:
    parts = []
    if revenue_slope is not None:
        parts.append(f"revenue slope {revenue_slope:+.3f}/q")
    else:
        parts.append("revenue slope unavailable")
    if eps_slope is not None:
        parts.append(f"EPS slope {eps_slope:+.3f}/q")
    else:
        parts.append("EPS slope unavailable")
    if fcf_exempt:
        parts.append("FCF exempt (financial sector)")
    elif fcf_positive is not None:
        parts.append(f"FCF {'positive' if fcf_positive else 'negative'}")
    else:
        parts.append("FCF unavailable")
    parts.append(f"→ {state.value}")
    return "; ".join(parts) + "."


def compute_fundamental_quality(bundle: TickerBundle) -> FundamentalResult:
    """Evaluate fundamental quality for a Filter 1 survivor.

    Returns FundamentalResult with state, penalty, and human-readable summary.
    """
    f = bundle.fundamentals

    if f is None:
        summary = (
            "Fundamentals unavailable for Argentine stock — expected gap."
            if bundle.metadata.asset_type == AssetType.ARGENTINE_STOCK
            else "Fundamentals unavailable (FMP no coverage)."
        )
        return FundamentalResult(
            fundamental_state=FundamentalState.UNKNOWN,
            fundamental_penalty=FUNDAMENTAL_PENALTY_UNKNOWN,
            summary=summary,
        )

    symbol = bundle.metadata.symbol_ars
    fcf_exempt = symbol in _FINANCIAL_SECTOR_TICKERS

    # Revenue slope
    revenue_slope = _normalized_slope(f.revenue_quarterly) if f.revenue_quarterly else None

    # EPS slope
    eps_slope = _normalized_slope(f.eps_quarterly) if f.eps_quarterly else None

    # FCF positivity
    if fcf_exempt:
        fcf_positive = None  # not evaluated for financial sector
    elif f.free_cash_flow is not None:
        fcf_positive = f.free_cash_flow > 0
    else:
        fcf_positive = None

    if revenue_slope is None:
        logger.debug("%s: revenue slope unavailable (insufficient quarterly data)", symbol)
    if eps_slope is None:
        logger.debug("%s: EPS slope unavailable (insufficient quarterly data)", symbol)

    state, penalty = _determine_state_and_penalty(revenue_slope, eps_slope, fcf_positive)
    summary = _build_summary(f, state, revenue_slope, eps_slope, fcf_positive, fcf_exempt)

    return FundamentalResult(
        fundamental_state=state,
        fundamental_penalty=round(penalty, 2),
        revenue_slope=round(revenue_slope, 4) if revenue_slope is not None else None,
        eps_slope=round(eps_slope, 4) if eps_slope is not None else None,
        fcf_positive=fcf_positive,
        summary=summary,
    )
