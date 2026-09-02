"""Tests for _last_expected_trading_day() time-aware logic.

Bug fixed 2026-09-02: the function previously always returned yesterday,
ignoring the current time — so a nightly run after 17:15 ART incorrectly
accepted a prior-day cache as fresh.
"""

from __future__ import annotations

from datetime import date, datetime, time as dtime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from data.cache import _last_expected_trading_day

_ART = ZoneInfo("America/Argentina/Buenos_Aires")


def _mock_now(dt: datetime):
    """Patch datetime.now(_ART) to return a fixed ART datetime."""
    return patch("data.cache.datetime", wraps=__import__("datetime").datetime,
                 **{"now.return_value": dt})


# ── After close gate (≥17:15 ART) on a weekday → must require today ──────────

def test_weekday_after_gate_requires_today():
    """20:18 ART Tuesday 02-Sep-2026 → must require 02-Sep (today closed)."""
    now = datetime(2026, 9, 2, 20, 18, 0, tzinfo=_ART)
    with _mock_now(now):
        result = _last_expected_trading_day()
    assert result == date(2026, 9, 2)


def test_exactly_at_gate_requires_today():
    """17:15:00 ART exactly → gate is inclusive, must require today."""
    now = datetime(2026, 9, 2, 17, 15, 0, tzinfo=_ART)
    with _mock_now(now):
        result = _last_expected_trading_day()
    assert result == date(2026, 9, 2)


# ── Before close gate (<17:15 ART) on a weekday → must require yesterday ─────

def test_weekday_before_gate_requires_yesterday():
    """09:05 ART Tuesday 02-Sep-2026 → market not closed, require 01-Sep."""
    now = datetime(2026, 9, 2, 9, 5, 0, tzinfo=_ART)
    with _mock_now(now):
        result = _last_expected_trading_day()
    assert result == date(2026, 9, 1)


def test_one_minute_before_gate_requires_yesterday():
    """17:14 ART → one minute before gate, require yesterday."""
    now = datetime(2026, 9, 2, 17, 14, 59, tzinfo=_ART)
    with _mock_now(now):
        result = _last_expected_trading_day()
    assert result == date(2026, 9, 1)


# ── Weekend → step back to Friday ─────────────────────────────────────────────

def test_saturday_any_hour_requires_friday():
    """Saturday 23:00 ART → most recent weekday is Friday."""
    now = datetime(2026, 9, 5, 23, 0, 0, tzinfo=_ART)  # Saturday
    with _mock_now(now):
        result = _last_expected_trading_day()
    assert result == date(2026, 9, 4)  # Friday


def test_sunday_any_hour_requires_friday():
    """Sunday 10:00 ART → most recent weekday is Friday."""
    now = datetime(2026, 9, 6, 10, 0, 0, tzinfo=_ART)  # Sunday
    with _mock_now(now):
        result = _last_expected_trading_day()
    assert result == date(2026, 9, 4)  # Friday


# ── Monday before gate → step back to Friday (not Sunday) ─────────────────────

def test_monday_before_gate_requires_friday():
    """Monday 08:00 ART → market not open yet, require prior Friday."""
    now = datetime(2026, 9, 7, 8, 0, 0, tzinfo=_ART)  # Monday
    with _mock_now(now):
        result = _last_expected_trading_day()
    assert result == date(2026, 9, 4)  # Friday


def test_monday_after_gate_requires_monday():
    """Monday 18:00 ART → Monday close propagated, require Monday."""
    now = datetime(2026, 9, 7, 18, 0, 0, tzinfo=_ART)  # Monday
    with _mock_now(now):
        result = _last_expected_trading_day()
    assert result == date(2026, 9, 7)
