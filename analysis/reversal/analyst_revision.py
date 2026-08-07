"""Best-effort analyst estimate revision enrichment for reversal scanner candidates.

Called ONLY on post-filter candidates (0-5 opportunities + 0-10 near-misses).
Never invoked during the full-universe evaluation loop.
See docs/DECISIONS.md #22 for source selection rationale (eps_revisions over eps_trend).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

MIN_ANALYSTS = 3  # universal threshold — applies to all tickers, not just Argentine stocks


def _fetch_one(symbol_underlying: Optional[str]) -> Dict[str, Any]:
    """Fetch analyst revision signal for one underlying symbol.

    Returns {"trend": str, "n_analysts": int|None}. Never raises.
    trend values: "up" | "down" | "stable" | "no_data"
    """
    if not symbol_underlying:
        return {"trend": "no_data", "n_analysts": None}

    try:
        import yfinance as yf

        tk = yf.Ticker(symbol_underlying)

        # Step 1: numberOfAnalysts from earnings_estimate annual row ("0y")
        n_analysts: Optional[int] = None
        try:
            ee = tk.earnings_estimate
            if ee is not None and not ee.empty and "0y" in ee.index:
                raw = ee.loc["0y"].get("numberOfAnalysts")
                if raw is not None and not pd.isna(raw):
                    n_analysts = int(raw)
        except Exception:
            pass

        # Universal threshold: below MIN_ANALYSTS → no_data, regardless of revision counts
        if n_analysts is None or n_analysts < MIN_ANALYSTS:
            return {"trend": "no_data", "n_analysts": n_analysts}

        # Step 2: net revision from eps_revisions (sum across all periods)
        rev = tk.eps_revisions
        if rev is None or not isinstance(rev, pd.DataFrame) or rev.empty:
            return {"trend": "no_data", "n_analysts": n_analysts}

        if "upLast30days" not in rev.columns or "downLast30days" not in rev.columns:
            return {"trend": "no_data", "n_analysts": n_analysts}

        up30 = int(rev["upLast30days"].sum())
        down30 = int(rev["downLast30days"].sum())
        net = up30 - down30

        if net > 0:
            trend = "up"
        elif net < 0:
            trend = "down"
        else:
            trend = "stable"

        return {"trend": trend, "n_analysts": n_analysts}

    except Exception as exc:
        logger.debug(
            "analyst_revision: %s → no_data (%s: %s)",
            symbol_underlying, type(exc).__name__, exc,
        )
        return {"trend": "no_data", "n_analysts": None}


def fetch_revisions(
    opportunities: list,  # List[ReversalOpportunity] — avoid circular import
    bundles: list,        # List[TickerBundle] — to resolve underlying symbols
) -> Dict[str, Dict]:
    """Fetch analyst revisions for published opportunities.

    Returns {symbol_ars: {"trend": ..., "n_analysts": ...}}.
    Every symbol in opportunities is guaranteed to appear in the result.
    """
    underlying_map: Dict[str, Optional[str]] = {
        b.metadata.symbol_ars: b.metadata.symbol_underlying
        for b in bundles
    }
    result: Dict[str, Dict] = {}
    for opp in opportunities:
        # .get() returns None cleanly for missing keys (Argentine stocks, non-US CEDEARs)
        underlying = underlying_map.get(opp.symbol)
        result[opp.symbol] = _fetch_one(underlying)
        logger.debug(
            "analyst_revision: %s (underlying=%s) → %s",
            opp.symbol, underlying, result[opp.symbol],
        )
    return result


def fetch_revisions_for_symbols(
    symbol_pairs: List[Tuple[str, Optional[str]]],
) -> Dict[str, Dict]:
    """Fetch analyst revisions for near-miss symbols.

    Args:
        symbol_pairs: list of (symbol_ars, symbol_underlying) — symbol_underlying may be None.

    Returns {symbol_ars: {"trend": ..., "n_analysts": ...}}.
    """
    result: Dict[str, Dict] = {}
    for sym_ars, sym_underlying in symbol_pairs:
        result[sym_ars] = _fetch_one(sym_underlying)
        logger.debug(
            "analyst_revision [near-miss]: %s (underlying=%s) → %s",
            sym_ars, sym_underlying, result[sym_ars],
        )
    return result
