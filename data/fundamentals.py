from __future__ import annotations

import logging
import os
import time
from datetime import date
from typing import List, Optional

import requests

from .cache import Cache
from .models import FundamentalsSnapshot

logger = logging.getLogger(__name__)

_FMP_BASE = "https://financialmodelingprep.com/stable"
_REQUEST_TIMEOUT = 15
_DAILY_CALL_LIMIT = 240  # conservative buffer below the 250/day free-tier cap

_session_call_count = 0
_INTER_CALL_DELAY = 4.0   # seconds between FMP requests (~15 req/min, safe for free tier)
_RATE_LIMIT_BACKOFF = 65  # seconds to wait on 429 before retrying (full 60s window + buffer)


def fetch_fundamentals(symbol_underlying: str, cache: Cache) -> Optional[FundamentalsSnapshot]:
    """Fetch fundamentals for a CEDEAR's underlying stock via FMP.

    Call budget: 3 FMP requests per ticker (income statement, cash flow, balance sheet).
    With 90-day cache TTL, most weekly runs spend 0 calls on already-cached tickers.
    Uses the /stable/ endpoint family; free-tier cap is 5 records per request.

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

    sym = {"symbol": symbol_underlying}
    # Free-tier hard limit is 5 records per request; requesting more returns 402.
    income = _fmp_get("income-statement", {**sym, "period": "quarter", "limit": 5})
    cash_flow = _fmp_get("cash-flow-statement", {**sym, "period": "quarter", "limit": 4})
    balance = _fmp_get("balance-sheet-statement", {**sym, "period": "quarter", "limit": 1})

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

    url = f"{_FMP_BASE}/{endpoint}"  # stable: symbol goes in params, not path
    params = {**params, "apikey": _api_key()}

    for attempt in range(2):
        try:
            resp = requests.get(url, params=params, timeout=_REQUEST_TIMEOUT)
            if resp.status_code == 402:
                logger.error(
                    "FMP plan limit reached for %s (HTTP 402) — request limit exceeded "
                    "for this endpoint or record count; reduce limit or upgrade plan",
                    endpoint,
                )
                return None
            if resp.status_code == 429:
                if attempt == 0:
                    logger.warning(
                        "FMP per-minute rate limit hit for %s (HTTP 429); "
                        "backing off %ds before retry",
                        endpoint, _RATE_LIMIT_BACKOFF,
                    )
                    time.sleep(_RATE_LIMIT_BACKOFF)
                    continue
                else:
                    logger.error(
                        "FMP per-minute rate limit still hit for %s after backoff; "
                        "skipping this call",
                        endpoint,
                    )
                    return None
            resp.raise_for_status()
            _session_call_count += 1
            time.sleep(_INTER_CALL_DELAY)  # throttle to stay under per-minute cap
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

        # stable endpoint dropped pre-computed ratio fields; calculate from components.
        latest = income_sorted[-1] if income_sorted else {}
        revenue_latest = float(latest.get("revenue") or 0)
        gross_margin: Optional[float] = (
            float(latest.get("grossProfit") or 0) / revenue_latest
            if revenue_latest else None
        )
        operating_margin: Optional[float] = (
            float(latest.get("operatingIncome") or 0) / revenue_latest
            if revenue_latest else None
        )

        free_cash_flow: Optional[float] = None
        if cash_flow:
            fcf_values = [float(q.get("freeCashFlow") or 0) for q in cash_flow]
            free_cash_flow = sum(fcf_values) / 1_000_000  # TTM sum in USD millions

        net_debt: Optional[float] = None
        if balance:
            b = balance[0]
            # stable endpoint provides netDebt directly; fall back to manual calc.
            if b.get("netDebt") is not None:
                net_debt = float(b["netDebt"]) / 1_000_000
            else:
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
