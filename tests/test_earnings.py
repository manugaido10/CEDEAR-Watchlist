"""Tests for data/earnings.py — check_earnings_warning()."""
from __future__ import annotations

import time
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest

import data.earnings as earnings_mod
from data.earnings import (
    EARNINGS_CALENDAR_TIMEOUT_SEC,
    EarningsCheckResult,
    EarningsCheckStatus,
    check_earnings_warning,
)


@pytest.fixture(autouse=True)
def reset_exclusions_cache():
    """Reset module-level exclusions cache between tests."""
    earnings_mod._excluded_underlyings_cache = None
    yield
    earnings_mod._excluded_underlyings_cache = None


# ── FIX A: Timeout ──────────────────────────────────────────────────────────


def test_timeout_returns_unverified_within_deadline():
    """A hanging .calendar call must not block beyond EARNINGS_CALENDAR_TIMEOUT_SEC."""

    def slow_calendar():
        time.sleep(EARNINGS_CALENDAR_TIMEOUT_SEC + 30)
        return {}

    mock_ticker = MagicMock()
    type(mock_ticker).calendar = property(lambda self: slow_calendar())

    with patch("data.earnings.yf.Ticker", return_value=mock_ticker):
        with patch.object(earnings_mod, "_is_excluded_underlying", return_value=False):
            start = time.monotonic()
            result = check_earnings_warning("SLOW")
            elapsed = time.monotonic() - start

    assert result.status == EarningsCheckStatus.UNVERIFIED
    assert result.message == earnings_mod._UNVERIFIED_MSG
    assert elapsed < EARNINGS_CALENDAR_TIMEOUT_SEC + 3, (
        f"Took {elapsed:.1f}s — expected to return within timeout + 3s margin"
    )


# ── FIX B: Exclusions gate ───────────────────────────────────────────────────


def test_excluded_symbol_skips_network_call():
    """A symbol in yfinance_exclusions.json must never trigger a yf.Ticker call."""
    excluded_data = {"excluded_underlyings": {"BBV": {"reason": "no coverage"}}}

    def raise_if_called(*args, **kwargs):
        raise AssertionError("yf.Ticker must not be called for excluded symbols")

    with patch("data.earnings.json.loads", return_value=excluded_data):
        with patch("data.earnings.yf.Ticker", side_effect=raise_if_called):
            result = check_earnings_warning("BBV")

    assert result.status == EarningsCheckStatus.UNVERIFIED
    assert result.message == earnings_mod._UNVERIFIED_MSG


def test_non_excluded_symbol_proceeds_to_network():
    """A symbol NOT in exclusions must reach the yf.Ticker call."""
    excluded_data = {"excluded_underlyings": {}}
    future_date = date.today() + timedelta(days=60)
    mock_cal = {"Earnings Date": [future_date]}
    mock_ticker = MagicMock()
    type(mock_ticker).calendar = property(lambda self: mock_cal)

    with patch("data.earnings.json.loads", return_value=excluded_data):
        with patch("data.earnings.yf.Ticker", return_value=mock_ticker) as mock_yf:
            result = check_earnings_warning("AAPL")

    mock_yf.assert_called_once_with("AAPL")
    assert result.status == EarningsCheckStatus.VERIFIED_CLEAR


# ── Existing UNVERIFIED cases (must be unchanged) ───────────────────────────


@pytest.fixture
def no_exclusions():
    """Patch exclusions to return empty set so the gate never fires."""
    with patch.object(earnings_mod, "_is_excluded_underlying", return_value=False):
        yield


def test_malformed_calendar_not_dict(no_exclusions):
    mock_ticker = MagicMock()
    type(mock_ticker).calendar = property(lambda self: "not-a-dict")

    with patch("data.earnings.yf.Ticker", return_value=mock_ticker):
        result = check_earnings_warning("XYZ")

    assert result.status == EarningsCheckStatus.UNVERIFIED
    assert result.message == earnings_mod._UNVERIFIED_MSG


def test_empty_earnings_dates(no_exclusions):
    mock_ticker = MagicMock()
    type(mock_ticker).calendar = property(lambda self: {"Earnings Date": []})

    with patch("data.earnings.yf.Ticker", return_value=mock_ticker):
        result = check_earnings_warning("XYZ")

    assert result.status == EarningsCheckStatus.UNVERIFIED
    assert result.message == earnings_mod._UNVERIFIED_MSG


def test_none_earnings_dates(no_exclusions):
    mock_ticker = MagicMock()
    type(mock_ticker).calendar = property(lambda self: {"Earnings Date": None})

    with patch("data.earnings.yf.Ticker", return_value=mock_ticker):
        result = check_earnings_warning("XYZ")

    assert result.status == EarningsCheckStatus.UNVERIFIED
    assert result.message == earnings_mod._UNVERIFIED_MSG


def test_unexpected_date_type(no_exclusions):
    mock_ticker = MagicMock()
    type(mock_ticker).calendar = property(lambda self: {"Earnings Date": ["2026-12-01"]})

    with patch("data.earnings.yf.Ticker", return_value=mock_ticker):
        result = check_earnings_warning("XYZ")

    assert result.status == EarningsCheckStatus.UNVERIFIED
    assert result.message == earnings_mod._UNVERIFIED_MSG


def test_network_exception(no_exclusions):
    mock_ticker = MagicMock()
    type(mock_ticker).calendar = property(
        lambda self: (_ for _ in ()).throw(ConnectionError("simulated network error"))
    )

    with patch("data.earnings.yf.Ticker", return_value=mock_ticker):
        result = check_earnings_warning("XYZ")

    assert result.status == EarningsCheckStatus.UNVERIFIED
    assert result.message == earnings_mod._UNVERIFIED_MSG


# ── Happy path ───────────────────────────────────────────────────────────────


def test_verified_clear_far_future(no_exclusions):
    future_date = date.today() + timedelta(days=60)
    mock_ticker = MagicMock()
    type(mock_ticker).calendar = property(
        lambda self: {"Earnings Date": [future_date]}
    )

    with patch("data.earnings.yf.Ticker", return_value=mock_ticker):
        result = check_earnings_warning("AAPL")

    assert result.status == EarningsCheckStatus.VERIFIED_CLEAR
    assert result.message is None


def test_verified_clear_past_date(no_exclusions):
    past_date = date.today() - timedelta(days=10)
    mock_ticker = MagicMock()
    type(mock_ticker).calendar = property(
        lambda self: {"Earnings Date": [past_date]}
    )

    with patch("data.earnings.yf.Ticker", return_value=mock_ticker):
        result = check_earnings_warning("AAPL")

    assert result.status == EarningsCheckStatus.VERIFIED_CLEAR
    assert result.message is None


def test_verified_warning_imminent(no_exclusions):
    # 3 business days out: use next Monday if today is Friday, else just add 3
    today = date.today()
    # find a date ~3 business days out
    candidate = today + timedelta(days=4)

    mock_ticker = MagicMock()
    type(mock_ticker).calendar = property(
        lambda self: {"Earnings Date": [candidate]}
    )

    with patch("data.earnings.yf.Ticker", return_value=mock_ticker):
        result = check_earnings_warning("AAPL", window_days=30)

    assert result.status == EarningsCheckStatus.VERIFIED_WARNING
    assert result.message is not None
    assert "⚠ Earnings próximos" in result.message
    assert candidate.isoformat() in result.message
