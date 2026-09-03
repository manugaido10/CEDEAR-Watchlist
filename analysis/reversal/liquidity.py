"""Shared liquidity math for the reversal pipeline.

Both the pre-opportunity gate in ``reversal_scanner`` and the diagnostic
script ``scripts/diagnose_liquidity.py`` must agree on the ADV definition —
the LIQUIDITY_MAX_RATIO_PCT threshold was calibrated against the diagnostic
output on 2026-09-03, so any drift between the two would silently invalidate
that calibration.

The gate is a hard pre-opportunity discard (like the RSI/support/catalyst
gates), not a suppression: illiquid tickers never become a
``ReversalOpportunity``. See DECISIONS.md for the calibration rationale.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

# ── Constants (single source of truth) ────────────────────────────────────────

# Trailing window for the ADV calculation. Matches the diagnostic script; do
# not change independently — the calibration below assumes this window.
TRAILING_TRADING_DAYS = 20

# "Typical position size" assumption shared with the report allocator (5-8%
# band, midpoint 6.5%). Used by the diagnostic script to project position
# sizes across capital scenarios and by ``check_liquidity`` implicitly via
# the same math applied in the scanner.
POSITION_PCT_MID = 0.065

# Hard discard threshold in percent (position ARS / ADV ARS × 100).
# Calibrated 2026-09-03 from scripts/diagnose_liquidity.py: VIVT3.BA at
# 239.03% was an actual published signal held in portfolio that would need
# 2.4× a full day's volume to fill at reference capital. See DECISIONS.md.
LIQUIDITY_MAX_RATIO_PCT = 10.0


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
    """Return position_size / ADV × 100 as a percentage. Caller ensures inputs > 0."""
    return _position_size_ars(total_capital_ars) / adv_ars * 100.0


def check_liquidity(
    adv_ars: Optional[float],
    total_capital_ars: Optional[float],
) -> Optional[str]:
    """Return a Spanish discard reason if the ratio exceeds the threshold, else None.

    Returns None (never discards) when ``adv_ars`` or ``total_capital_ars`` is
    unavailable — this gate must never crash, and "we can't evaluate" is not
    the same as "gate failed". The scanner logs a single warning when capital
    is missing; missing volume rows already surface via the price-fetch
    warnings.
    """
    if adv_ars is None or adv_ars <= 0:
        return None
    if total_capital_ars is None or total_capital_ars <= 0:
        return None

    ratio_pct = liquidity_ratio_pct(adv_ars, total_capital_ars)
    if ratio_pct <= LIQUIDITY_MAX_RATIO_PCT:
        return None

    return (
        f"Volumen insuficiente: posición típica sería {ratio_pct:.0f}% "
        f"del volumen diario promedio ({adv_ars:,.0f} ARS) — riesgo de "
        f"iliquidez al salir"
    )
