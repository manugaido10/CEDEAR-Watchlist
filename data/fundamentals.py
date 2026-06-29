from __future__ import annotations

import logging
from datetime import date
from typing import List, Optional

import pandas as pd
import yfinance as yf

from .cache import Cache
from .models import FundamentalsSnapshot

logger = logging.getLogger(__name__)


def fetch_fundamentals(symbol_underlying: str, cache: Cache) -> Optional[FundamentalsSnapshot]:
    """Fetch fundamentals for a CEDEAR's underlying stock via yfinance.

    Uses 90-day cache TTL; most weekly runs return cached data.
    Returns None if yfinance returns no income statement data.
    """
    if cache.fundamentals_are_fresh(symbol_underlying):
        cached = cache.load_fundamentals(symbol_underlying)
        if cached:
            logger.debug("Fundamentals for %s loaded from fresh cache", symbol_underlying)
            return _dict_to_snapshot(cached)

    try:
        ticker = yf.Ticker(symbol_underlying)
        income = ticker.quarterly_income_stmt
        cashflow = ticker.quarterly_cashflow
        balance = ticker.quarterly_balance_sheet
    except Exception as exc:
        logger.warning("yfinance fetch failed for %s: %s; trying stale cache", symbol_underlying, exc)
        cached = cache.load_fundamentals(symbol_underlying)
        if cached:
            logger.warning("Using stale fundamentals cache for %s", symbol_underlying)
            return _dict_to_snapshot(cached)
        return None

    if income is None or income.empty:
        logger.warning("No income statement from yfinance for %s; trying stale cache", symbol_underlying)
        cached = cache.load_fundamentals(symbol_underlying)
        if cached:
            logger.warning("Using stale fundamentals cache for %s", symbol_underlying)
            return _dict_to_snapshot(cached)
        return None

    snapshot = _parse_yf_response(symbol_underlying, income, cashflow, balance)
    if snapshot:
        cache.save_fundamentals(symbol_underlying, _snapshot_to_dict(snapshot))
    return snapshot


def _parse_yf_response(
    symbol: str,
    income: pd.DataFrame,
    cashflow: Optional[pd.DataFrame],
    balance: Optional[pd.DataFrame],
) -> Optional[FundamentalsSnapshot]:
    try:
        # yfinance columns are dates descending; reverse to ascending chronological order
        income_sorted = income[sorted(income.columns)]

        eps_quarterly = _extract_series(income_sorted, ["Diluted EPS", "Basic EPS"], scale=1.0, max_vals=5)
        revenue_quarterly = _extract_series(income_sorted, ["Total Revenue"], scale=1 / 1_000_000, max_vals=5)

        latest_col = income_sorted.columns[-1] if not income_sorted.empty else None

        gross_margin: Optional[float] = None
        operating_margin: Optional[float] = None
        if latest_col is not None:
            revenue_latest = _get_scalar(income_sorted, ["Total Revenue"], latest_col)
            if revenue_latest:
                gp = _get_scalar(income_sorted, ["Gross Profit"], latest_col)
                if gp is not None:
                    gross_margin = gp / revenue_latest
                oi = _get_scalar(income_sorted, ["Operating Income"], latest_col)
                if oi is not None:
                    operating_margin = oi / revenue_latest

        free_cash_flow: Optional[float] = None
        if cashflow is not None and not cashflow.empty:
            fcf_cols = sorted(cashflow.columns)
            fcf_row = _find_row(cashflow, ["Free Cash Flow"])
            if fcf_row is not None:
                vals = [cashflow.loc[fcf_row, c] for c in fcf_cols[-4:]]
                valid = [float(v) for v in vals if pd.notna(v)]
                if valid:
                    free_cash_flow = sum(valid) / 1_000_000

        net_debt: Optional[float] = None
        if balance is not None and not balance.empty:
            bal_col = sorted(balance.columns)[-1]
            nd = _get_scalar(balance, ["Net Debt"], bal_col)
            if nd is not None:
                net_debt = nd / 1_000_000
            else:
                total_debt = _get_scalar(balance, ["Total Debt"], bal_col) or 0.0
                cash = _get_scalar(balance, ["Cash And Cash Equivalents"], bal_col) or 0.0
                net_debt = (total_debt - cash) / 1_000_000

        return FundamentalsSnapshot(
            symbol_underlying=symbol,
            as_of=date.today(),
            eps_quarterly=eps_quarterly,
            revenue_quarterly=revenue_quarterly,
            net_debt=net_debt,
            gross_margin=float(gross_margin) if gross_margin is not None else None,
            operating_margin=float(operating_margin) if operating_margin is not None else None,
            free_cash_flow=free_cash_flow,
            data_source="yfinance",
        )
    except Exception as exc:
        logger.error("Error parsing yfinance data for %s: %s", symbol, exc)
        return None


def _find_row(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    for name in candidates:
        if name in df.index:
            return name
    return None


def _get_scalar(df: pd.DataFrame, candidates: List[str], col) -> Optional[float]:
    row = _find_row(df, candidates)
    if row is None:
        return None
    val = df.loc[row, col]
    if pd.isna(val):
        return None
    return float(val)


def _extract_series(
    df: pd.DataFrame,
    candidates: List[str],
    scale: float,
    max_vals: int,
) -> List[float]:
    row = _find_row(df, candidates)
    if row is None:
        return []
    series = df.loc[row]
    vals = [float(v) * scale for v in series[-max_vals:] if pd.notna(v)]
    return vals


def _snapshot_to_dict(s: FundamentalsSnapshot) -> dict:
    return {
        "symbol_underlying": s.symbol_underlying,
        "as_of": s.as_of.isoformat(),
        "eps_quarterly": s.eps_quarterly,
        "revenue_quarterly": s.revenue_quarterly,
        "net_debt": s.net_debt,
        "gross_margin": s.gross_margin,
        "operating_margin": s.operating_margin,
        "free_cash_flow": s.free_cash_flow,
        "data_source": s.data_source,
    }


def _dict_to_snapshot(d: dict) -> FundamentalsSnapshot:
    return FundamentalsSnapshot(
        symbol_underlying=d["symbol_underlying"],
        as_of=date.fromisoformat(d["as_of"]),
        eps_quarterly=d.get("eps_quarterly", []),
        revenue_quarterly=d.get("revenue_quarterly", []),
        net_debt=d.get("net_debt"),
        gross_margin=d.get("gross_margin"),
        operating_margin=d.get("operating_margin"),
        free_cash_flow=d.get("free_cash_flow"),
        data_source=d.get("data_source", "yfinance"),
    )
