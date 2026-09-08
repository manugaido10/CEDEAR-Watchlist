"""Shared liquidity math for the reversal pipeline.

Both the pre-opportunity gate in ``reversal_scanner`` and the diagnostic
script ``scripts/diagnose_liquidity.py`` must agree on the ADV definition —
ADV_MIN_ARS was calibrated from the diagnostic output on 2026-09-07 at the
P25 of the universe ADV distribution. See DECISIONS.md #28 for rationale.

The gate is a hard pre-opportunity discard (like the RSI/support/catalyst
gates), not a suppression: illiquid tickers never become a
``ReversalOpportunity``.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

# ── Constants (single source of truth) ────────────────────────────────────────

# Trailing window for the ADV calculation. Matches the diagnostic script; do
# not change independently — the calibration below assumes this window.
TRAILING_TRADING_DAYS = 20

# "Typical position size" assumption used by the diagnostic script to project
# position sizes across capital scenarios (not used by the gate any more).
POSITION_PCT_MID = 0.065

# Fixed ADV floor — P25 of the universe distribution (98 tickers, 2026-09-07).
# Equivalent to running check_liquidity at ~23M ARS capital with the old
# 10%-ratio gate. Replaces the capital-dependent formula so the gate can
# operate in paper-trading mode without a capital figure. See DECISIONS.md #28.
ADV_MIN_ARS = 15_000_000


# ── ADV — average daily traded value in ARS ──────────────────────────────────

def compute_adv_ars(
    df: Optional[pd.DataFrame],
    *,
    as_of=None,
    window: int = TRAILING_TRADING_DAYS,
) -> Optional[float]:
    """Return avg(close × volume) over the trailing ``window`` bars, or None.

    Requirements:
      - ``df`` non-empty with lowercase ``close`` and ``volume`` columns.
      - When ``as_of`` is supplied, only bars with index ≤ ``as_of`` are used
        (the diagnostic path). When None, uses the last ``window`` bars in
        the frame (the scanner path — bundle already trimmed to the scan
        cutoff via freshness rules).

    Returns None on any missing precondition — this function is used inside
    fail-open gates, so silence-then-skip is the correct failure mode.
    """
    if df is None or df.empty:
        return None
    lowered = [c.lower() for c in df.columns]
    if "close" not in lowered or "volume" not in lowered:
        return None
    if list(df.columns) != lowered:
        df = df.copy()
        df.columns = lowered

    df = df.sort_index()
    if as_of is not None:
        try:
            cutoff = pd.Timestamp(as_of)
        except Exception:
            return None
        df = df[df.index <= cutoff]

    window_df = df.tail(window)
    if window_df.empty:
        return None

    close = pd.to_numeric(window_df["close"], errors="coerce")
    volume = pd.to_numeric(window_df["volume"], errors="coerce")
    daily_traded_ars = (close * volume).dropna()
    if daily_traded_ars.empty:
        return None
    return float(daily_traded_ars.mean())


# ── Gate ─────────────────────────────────────────────────────────────────────

def _position_size_ars(total_capital_ars: float) -> float:
    return total_capital_ars * POSITION_PCT_MID


def liquidity_ratio_pct(adv_ars: float, total_capital_ars: float) -> float:
    """Return position_size / ADV × 100 as a percentage. Caller ensures inputs > 0.

    Used by scripts/diagnose_liquidity.py for scenario analysis; not used by
    the gate itself any more (gate uses ADV_MIN_ARS directly since #28).
    """
    return _position_size_ars(total_capital_ars) / adv_ars * 100.0


def check_liquidity(
    adv_ars: Optional[float],
    total_capital_ars: Optional[float] = None,  # ignored since #28; kept for call-site compat
) -> Optional[str]:
    """Return a Spanish discard reason if ADV is below the fixed floor, else None.

    Returns None when ``adv_ars`` is unavailable (fail-open: "can't evaluate"
    is not the same as "gate failed"). ``total_capital_ars`` is accepted but
    ignored — the gate now uses ADV_MIN_ARS so it can operate without a capital
    figure (paper-trading mode). See DECISIONS.md #28.
    """
    if adv_ars is None or adv_ars <= 0:
        return None
    if adv_ars < ADV_MIN_ARS:
        return (
            f"Volumen insuficiente: ADV {adv_ars:,.0f} ARS < mínimo "
            f"{ADV_MIN_ARS:,.0f} ARS — riesgo de iliquidez al salir"
        )
    return None
