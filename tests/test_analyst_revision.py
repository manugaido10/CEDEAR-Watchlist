"""analyst_revision._fetch_one must not hit the network for excluded underlyings."""
from __future__ import annotations

from unittest.mock import patch

import analysis.reversal.analyst_revision as ar

_NO_DATA = {"trend": "no_data", "n_analysts": None}


def test_excluded_underlying_skips_network_and_returns_no_data():
    with patch("yfinance.Ticker") as mock_ticker, \
            patch.object(ar, "_is_excluded_underlying", return_value=True):
        result = ar._fetch_one("PETR3")
    mock_ticker.assert_not_called()
    assert result == _NO_DATA


def test_excluded_result_identical_to_exception_path():
    with patch("yfinance.Ticker", side_effect=RuntimeError("404")), \
            patch.object(ar, "_is_excluded_underlying", return_value=False):
        exception_result = ar._fetch_one("FOO")
    with patch("yfinance.Ticker") as mock_ticker, \
            patch.object(ar, "_is_excluded_underlying", return_value=True):
        excluded_result = ar._fetch_one("FOO")
    mock_ticker.assert_not_called()
    assert excluded_result == exception_result == _NO_DATA


def test_real_exclusions_file_covers_petr3_and_wege3():
    with patch("yfinance.Ticker") as mock_ticker:
        assert ar._fetch_one("PETR3") == _NO_DATA
        assert ar._fetch_one("WEGE3") == _NO_DATA
    mock_ticker.assert_not_called()


def test_non_excluded_underlying_still_calls_yfinance():
    with patch("yfinance.Ticker", side_effect=RuntimeError("boom")) as mock_ticker, \
            patch.object(ar, "_is_excluded_underlying", return_value=False):
        assert ar._fetch_one("AAPL") == _NO_DATA
    mock_ticker.assert_called_once_with("AAPL")
