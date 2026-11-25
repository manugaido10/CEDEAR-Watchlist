"""Ex-dividend instrumentation (Fase B3) — recorded only, never gates anything.

Captures the next ex-dividend date of a CEDEAR's underlying so a later analysis
can flag signals whose price path is contaminated by the dividend drop (the
ex-date gap can trip the stop with no reversal failure). No decision is stored
at write time: the "contaminated" filter is computed in analysis/query.py.

Fields (all None when there is no data — same pattern as calendar_stale):
  ex_div_date       ISO date of the ex-dividend date reported by the source.
  ex_div_amount     USD per underlying share.
  ex_div_yield_pct  amount / last underlying close, as a FRACTION (0.034 = 3.4%),
                    the same unit as stop_dist_pct so both compare directly.
  ex_div_source     provenance of date/amount (see SOURCE_* below).
  ex_div_stale      True when the source date is already in the past; False when
                    it is today or later; None when there is no date.

yfinance only exposes the upcoming ex-date (``Ticker.calendar``); the upcoming
*amount* is not published until after the ex-date. When no dividend entry
matches the ex-date, ``lastDividendValue`` is used as an estimate and the source
says so — it is never presented as the confirmed amount.

Only applicable to CEDEARs (symbol_underlying != None). Never raises.
"""
from __future__ import annotations

import logging
import math
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Callable, Dict, Optional

import yfinance as yf

from data.earnings import _is_excluded_underlying

logger = logging.getLogger(__name__)

EX_DIV_FETCH_TIMEOUT_SEC = 20
# Calendar vs dividend-history dates can differ by a day (US ex-date vs the
# date Yahoo stamps the cash dividend); prior dividends are months away.
AMOUNT_MATCH_TOLERANCE_DAYS = 1
_ROUND_AMOUNT = 4
_ROUND_YIELD = 4

SOURCE_YFINANCE = "yfinance"  # date from calendar; amount confirmed in history, or absent
SOURCE_YFINANCE_ESTIMATE = "yfinance_last_dividend_estimate"  # amount = last paid dividend


@dataclass
class ExDividendResult:
    ex_div_date: Optional[date] = None
    ex_div_amount: Optional[float] = None
    ex_div_yield_pct: Optional[float] = None
    ex_div_source: Optional[str] = None
    ex_div_stale: Optional[bool] = None

    def to_record(self) -> Dict[str, Any]:
        """Always-present keys for signals.jsonl; None when not computable."""
        return {
            "ex_div_date": self.ex_div_date.isoformat() if self.ex_div_date else None,
            "ex_div_amount": self.ex_div_amount,
            "ex_div_yield_pct": self.ex_div_yield_pct,
            "ex_div_source": self.ex_div_source,
            "ex_div_stale": self.ex_div_stale,
        }


@dataclass
class RawExDividend:
    """Network output, kept separate so the builder is pure and testable offline."""

    calendar_ex_date: Any = None
    dividends: Dict[date, float] = field(default_factory=dict)  # recent history
    last_close: Optional[float] = None
    last_dividend_value: Optional[float] = None


def _as_date(value: Any) -> Optional[date]:
    if isinstance(value, datetime):  # includes pandas.Timestamp
        return value.date()
    if isinstance(value, date):
        return value
    return None


def _positive_finite(value: Any) -> Optional[float]:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) and v > 0 else None


def build_ex_dividend_result(raw: RawExDividend, today: date) -> ExDividendResult:
    """Pure: RawExDividend -> ExDividendResult. No date, no record."""
    ex_date = _as_date(raw.calendar_ex_date)
    if ex_date is None:
        return ExDividendResult()

    if ex_date < today:
        # Past date: kept for audit, but amount/yield describe a payment that
        # is no longer upcoming, so they are not derived.
        return ExDividendResult(
            ex_div_date=ex_date, ex_div_source=SOURCE_YFINANCE, ex_div_stale=True,
        )

    amount: Optional[float] = None
    source = SOURCE_YFINANCE
    for d, value in raw.dividends.items():
        if abs((d - ex_date).days) <= AMOUNT_MATCH_TOLERANCE_DAYS:
            amount = _positive_finite(value)
            break
    if amount is None:
        amount = _positive_finite(raw.last_dividend_value)
        if amount is not None:
            source = SOURCE_YFINANCE_ESTIMATE

    close = _positive_finite(raw.last_close)
    yield_frac = round(amount / close, _ROUND_YIELD) if amount and close else None
    return ExDividendResult(
        ex_div_date=ex_date,
        ex_div_amount=round(amount, _ROUND_AMOUNT) if amount else None,
        ex_div_yield_pct=yield_frac,
        ex_div_source=source,
        ex_div_stale=False,
    )


def _fetch_raw(symbol_underlying: str) -> RawExDividend:
    """Network: calendar (+ history and info only when an ex-date exists)."""
    ticker = yf.Ticker(symbol_underlying)
    cal = ticker.calendar
    ex_date = cal.get("Ex-Dividend Date") if isinstance(cal, dict) else None
    raw = RawExDividend(calendar_ex_date=ex_date)
    if _as_date(ex_date) is None:
        return raw

    hist = ticker.history(period="1mo", auto_adjust=False)
    if hist is not None and not hist.empty:
        raw.last_close = float(hist["Close"].iloc[-1])
        if "Dividends" in hist.columns:
            paid = hist["Dividends"][hist["Dividends"] > 0]
            raw.dividends = {idx.date(): float(v) for idx, v in paid.items()}
    info = ticker.info
    if isinstance(info, dict):
        raw.last_dividend_value = info.get("lastDividendValue")
    return raw


def check_ex_dividend(
    symbol_underlying: str,
    today: Optional[date] = None,
    fetcher: Callable[[str], RawExDividend] = _fetch_raw,
) -> ExDividendResult:
    """Ex-dividend instrumentation for a CEDEAR underlying. Never raises."""
    if _is_excluded_underlying(symbol_underlying):
        logger.debug("check_ex_dividend(%s): skipped (yfinance_exclusions)", symbol_underlying)
        return ExDividendResult()

    today = today or date.today()
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(fetcher, symbol_underlying)
        try:
            raw = future.result(timeout=EX_DIV_FETCH_TIMEOUT_SEC)
        except FuturesTimeoutError:
            logger.warning(
                "check_ex_dividend(%s): timeout after %ss — no data",
                symbol_underlying, EX_DIV_FETCH_TIMEOUT_SEC,
            )
            return ExDividendResult()
        return build_ex_dividend_result(raw, today)
    except Exception as exc:
        logger.warning("check_ex_dividend(%s): %s — no data", symbol_underlying, exc)
        return ExDividendResult()
    finally:
        executor.shutdown(wait=False)
