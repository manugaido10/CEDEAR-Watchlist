from __future__ import annotations

import logging
import os
from datetime import date
from typing import List, Optional

import requests

from .cache import Cache
from .models import FundamentalsSnapshot

logger = logging.getLogger(__name__)

_FMP_BASE = "https://financialmodelingprep.com/api/v3"
_REQUEST_TIMEOUT = 15
_DAILY_CALL_LIMIT = 240  # conservative buffer below the 250/day free-tier cap

_session_call_count = 0


def fetch_fundamentals(symbol_underlying: str, cache: Cache) -> Optional[FundamentalsSnapshot]:
    """Fetch fundamentals for a CEDEAR's underlying stock via FMP.

    Call budget: 3 FMP requests per ticker (income statement, cash flow, balance sheet).
    With 90-day cache TTL, most weekly runs spend 0 calls on already-cached tickers.

    Returns None if:
    - FMP_API_KEY is not set
    - symbol is unavailable in FMP (e.g. some emerging-market stocks)
    - live fetch fails and no cache exists
    """
    if not _api_key():
        logger.debug("FMP_API_KEY not set; skipping fundamentals for %s", symbol_underlying)
        return None

    if cache.fundamentals_are_fresh(symbol_underlying):
        cached = cache.load_fundamentals(symbol_underlying)
        if cached:
            logger.debug("Fundamentals for %s loaded from fresh cache", symbol_underlying)
            return _dict_to_snapshot(cached)

    income = _fmp_get(f"income-statement/{symbol_underlying}", {"period": "quarter", "limit": 8})
    cash_flow = _fmp_get(f"cash-flow-statement/{symbol_underlying}", {"period": "quarter", "limit": 4})
    balance = _fmp_get(f"balance-sheet-statement/{symbol_underlying}", {"period": "quarter", "limit": 1})

    if not income:
        logger.warning("No income statement from FMP for %s; trying stale cache", symbol_underlying)
        cached = cache.load_fundamentals(symbol_underlying)
        if cached:
            logger.warning("Using stale fundamentals cache for %s", symbol_underlying)
            return _dict_to_snapshot(cached)
        return None

    snapshot = _parse_fmp_response(symbol_underlying, income, cash_flow, balance)
    if snapshot:
        cache.save_fundamentals(symbol_underlying, _snapshot_to_dict(snapshot))
    return snapshot


def _api_key() -> Optional[str]:
    return os.environ.get("FMP_API_KEY")


def _fmp_get(endpoint: str, params: dict) -> Optional[list]:
    global _session_call_count
    if _session_call_count >= _DAILY_CALL_LIMIT:
        logger.error("Daily FMP call limit (%d) reached; skipping %s", _DAILY_CALL_LIMIT, endpoint)
        return None

    url = f"{_FMP_BASE}/{endpoint}"
    params = {**params, "apikey": _api_key()}

    try:
        resp = requests.get(url, params=params, timeout=_REQUEST_TIMEOUT)
        resp.raise_for_status()
        _session_call_count += 1
        data = resp.json()
        if isinstance(data, dict) and "Error Message" in data:
            logger.error("FMP error for %s: %s", endpoint, data["Error Message"])
            return None
        if not isinstance(data, list):
            logger.warning("Unexpected FMP response type for %s: %s", endpoint, type(data))
            return None
        return data
    except requests.RequestException as exc:
        logger.error("FMP request failed for %s: %s", endpoint, exc)
        return None


def _parse_fmp_response(
    symbol: str,
    income: list,
    cash_flow: Optional[list],
    balance: Optional[list],
) -> Optional[FundamentalsSnapshot]:
    try:
        income_sorted: List[dict] = sorted(income, key=lambda x: x.get("date", ""))

        eps_quarterly = [float(q.get("eps") or 0) for q in income_sorted]
        revenue_quarterly = [float(q.get("revenue") or 0) / 1_000_000 for q in income_sorted]

        latest = income_sorted[-1] if income_sorted else {}
        gross_margin = latest.get("grossProfitRatio")
        operating_margin = latest.get("operatingIncomeRatio")

        free_cash_flow: Optional[float] = None
        if cash_flow:
            fcf_values = [float(q.get("freeCashFlow") or 0) for q in cash_flow]
            free_cash_flow = sum(fcf_values) / 1_000_000  # TTM sum in USD millions

        net_debt: Optional[float] = None
        if balance:
            b = balance[0]
            total_debt = float(b.get("totalDebt") or 0)
            cash = float(b.get("cashAndCashEquivalents") or 0)
            net_debt = (total_debt - cash) / 1_000_000  # USD millions

        return FundamentalsSnapshot(
            symbol_underlying=symbol,
            as_of=date.today(),
            eps_quarterly=eps_quarterly,
            revenue_quarterly=revenue_quarterly,
            net_debt=net_debt,
            gross_margin=float(gross_margin) if gross_margin is not None else None,
            operating_margin=float(operating_margin) if operating_margin is not None else None,
            free_cash_flow=free_cash_flow,
        )
    except Exception as exc:
        logger.error("Error parsing FMP data for %s: %s", symbol, exc)
        return None


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
        data_source=d.get("data_source", "fmp"),
    )
