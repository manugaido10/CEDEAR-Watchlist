"""Earnings calendar check — shared utility for reversal and watchlist pipelines.

Fetches next earnings date from yfinance and returns a structured result
distinguishing three states:
  VERIFIED_CLEAR   — yfinance responded, no upcoming earnings within the window
  VERIFIED_WARNING — yfinance responded, earnings fall within EARNINGS_WARNING_WINDOW_DAYS
  UNVERIFIED       — date unavailable (known-unverifiable symbol, timeout, malformed
                     calendar, empty earnings_dates, unexpected type, or network error)

Only applicable to CEDEARs (symbol_underlying != None); callers must skip
Argentine stocks.
"""
from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Optional, Set

import numpy as np
import yfinance as yf

logger = logging.getLogger(__name__)

EARNINGS_WARNING_WINDOW_DAYS = 7
EARNINGS_CALENDAR_TIMEOUT_SEC = 15

_UNVERIFIED_MSG = "⚠ No se pudo verificar fecha de earnings — dato no disponible"

_EXCLUSIONS_PATH = Path(__file__).parent / "sources" / "yfinance_exclusions.json"
_excluded_underlyings_cache: Optional[Set[str]] = None


def _is_excluded_underlying(symbol: str) -> bool:
    global _excluded_underlyings_cache
    if _excluded_underlyings_cache is None:
        try:
            raw = json.loads(_EXCLUSIONS_PATH.read_text())
            _excluded_underlyings_cache = set(raw.get("excluded_underlyings", {}).keys())
        except Exception:
            _excluded_underlyings_cache = set()
    return symbol in _excluded_underlyings_cache


class EarningsCheckStatus(str, Enum):
    VERIFIED_CLEAR = "verified_clear"
    VERIFIED_WARNING = "verified_warning"
    UNVERIFIED = "unverified"


@dataclass
class EarningsCheckResult:
    status: EarningsCheckStatus
    message: Optional[str] = None  # set for VERIFIED_WARNING and UNVERIFIED


def check_earnings_warning(
    symbol_underlying: str,
    window_days: int = EARNINGS_WARNING_WINDOW_DAYS,
) -> EarningsCheckResult:
    """Check upcoming earnings for a CEDEAR underlying symbol.

    Returns EarningsCheckResult with one of three states:
      VERIFIED_CLEAR   — checked, no risk within window (message=None)
      VERIFIED_WARNING — checked, earnings imminent (message contains date + bdays)
      UNVERIFIED       — could not retrieve data (message contains explicit notice)
    Never raises.
    """
    if _is_excluded_underlying(symbol_underlying):
        logger.warning(
            "check_earnings_warning(%s): skipped — known_unverifiable (yfinance_exclusions)",
            symbol_underlying,
        )
        return EarningsCheckResult(EarningsCheckStatus.UNVERIFIED, _UNVERIFIED_MSG)

    try:
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(lambda: yf.Ticker(symbol_underlying).calendar)
        try:
            cal = future.result(timeout=EARNINGS_CALENDAR_TIMEOUT_SEC)
        except FuturesTimeoutError:
            executor.shutdown(wait=False)
            logger.warning(
                "check_earnings_warning(%s): timeout after %ss — unverified",
                symbol_underlying,
                EARNINGS_CALENDAR_TIMEOUT_SEC,
            )
            return EarningsCheckResult(EarningsCheckStatus.UNVERIFIED, _UNVERIFIED_MSG)
        executor.shutdown(wait=False)

        if not isinstance(cal, dict):
            logger.warning(
                "check_earnings_warning(%s): unexpected calendar type %s — malformed response",
                symbol_underlying,
                type(cal),
            )
            return EarningsCheckResult(EarningsCheckStatus.UNVERIFIED, _UNVERIFIED_MSG)

        earnings_dates = cal.get("Earnings Date")
        if not earnings_dates:
            logger.warning(
                "check_earnings_warning(%s): no earnings date in calendar response — empty",
                symbol_underlying,
            )
            return EarningsCheckResult(EarningsCheckStatus.UNVERIFIED, _UNVERIFIED_MSG)

        next_date = earnings_dates[0]
        if not isinstance(next_date, date):
            logger.warning(
                "check_earnings_warning(%s): unexpected date type %s — malformed date",
                symbol_underlying,
                type(next_date),
            )
            return EarningsCheckResult(EarningsCheckStatus.UNVERIFIED, _UNVERIFIED_MSG)

        today = date.today()
        if next_date < today:
            return EarningsCheckResult(EarningsCheckStatus.VERIFIED_CLEAR)

        bdays = int(np.busday_count(today.isoformat(), next_date.isoformat()))
        if bdays > window_days:
            return EarningsCheckResult(EarningsCheckStatus.VERIFIED_CLEAR)

        plural_s = "s" if bdays != 1 else ""
        plural_es = "es" if bdays != 1 else ""
        msg = (
            f"⚠ Earnings próximos: {next_date.isoformat()} "
            f"({bdays} día{plural_s} hábil{plural_es}) "
            f"— evaluar riesgo de gap antes de entrar"
        )
        return EarningsCheckResult(EarningsCheckStatus.VERIFIED_WARNING, msg)

    except Exception as exc:
        logger.warning(
            "check_earnings_warning(%s): network exception — %s",
            symbol_underlying,
            exc,
        )
        return EarningsCheckResult(EarningsCheckStatus.UNVERIFIED, _UNVERIFIED_MSG)
