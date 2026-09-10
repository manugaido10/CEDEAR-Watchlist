"""Tests for fail-closed post-fetch validation in data/fetcher.py.

When yfinance returns a df whose last bar is older than _last_expected_trading_day(),
_fetch_prices_with_fallback must return (None, FetchStatus.MISSING, False) and must
NOT save the stale data to cache. This prevents publishing signals on T-1 prices
when the scan runs after market close (yfinance .BA next-day lag, Decision #28).
"""

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from data.fetcher import _fetch_prices_with_fallback
from data.models import FetchStatus, TickerMetadata, AssetType

_ART = ZoneInfo("America/Argentina/Buenos_Aires")


def _make_meta(symbol: str = "COST.BA") -> TickerMetadata:
    return TickerMetadata(
        symbol_ars=symbol,
        symbol_underlying="COST",
        name="Costco",
        asset_type=AssetType.CEDEAR,
    )


def _make_df(last_date: date) -> pd.DataFrame:
    """Return a minimal df with 401 rows, last bar on last_date."""
    idx = pd.date_range(end=last_date, periods=401, freq="B")
    return pd.DataFrame(
        {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1000},
        index=idx,
    )


def _mock_art_now(dt: datetime):
    return patch("data.cache.datetime", wraps=__import__("datetime").datetime,
                 **{"now.return_value": dt})


class TestFetcherFailClosed:
    """_fetch_prices_with_fallback rejects yfinance data with last bar < expected day."""

    def _run(self, fetch_df, art_now_dt):
        """Helper: patch fetch_prices to return fetch_df, set ART time, run fetcher."""
        cache = MagicMock()
        cache.prices_are_fresh.return_value = False  # force live fetch
        warnings = []
        meta = _make_meta()

        with patch("data.fetcher.fetch_prices", return_value=fetch_df), \
             _mock_art_now(art_now_dt):
            return _fetch_prices_with_fallback(meta, cache, warnings)

    def test_stale_bar_returns_missing(self):
        """yfinance returns T-1 bar after 17:15 → MISSING, data not saved."""
        # 20:00 ART Tuesday → expects 2026-09-10 bar
        art_now = datetime(2026, 9, 10, 20, 0, tzinfo=_ART)
        stale_df = _make_df(date(2026, 9, 9))  # last bar is T-1

        history, status, from_cache = self._run(stale_df, art_now)

        assert history is None
        assert status == FetchStatus.MISSING
        assert from_cache is False

    def test_stale_bar_does_not_save_to_cache(self):
        """Stale yfinance data must NOT be persisted to cache."""
        art_now = datetime(2026, 9, 10, 20, 0, tzinfo=_ART)
        stale_df = _make_df(date(2026, 9, 9))

        cache = MagicMock()
        cache.prices_are_fresh.return_value = False
        meta = _make_meta()

        with patch("data.fetcher.fetch_prices", return_value=stale_df), \
             _mock_art_now(art_now):
            _fetch_prices_with_fallback(meta, cache, [])

        cache.save_prices.assert_not_called()

    def test_fresh_bar_returns_ok(self):
        """yfinance returns today's bar after 17:15 → OK, data saved."""
        art_now = datetime(2026, 9, 10, 20, 0, tzinfo=_ART)
        fresh_df = _make_df(date(2026, 9, 10))  # last bar is today

        cache = MagicMock()
        cache.prices_are_fresh.return_value = False
        meta = _make_meta()

        with patch("data.fetcher.fetch_prices", return_value=fresh_df), \
             _mock_art_now(art_now):
            history, status, from_cache = _fetch_prices_with_fallback(meta, cache, [])

        assert history is not None
        assert status in (FetchStatus.OK, FetchStatus.PARTIAL)
        cache.save_prices.assert_called_once()

    def test_before_gate_t_minus1_bar_ok(self):
        """Before 17:15 ART, expected day is T-1 → T-1 bar from yfinance is fresh."""
        # 09:00 ART Wednesday 2026-09-10 → _last_expected_trading_day() = 2026-09-09
        art_now = datetime(2026, 9, 10, 9, 0, tzinfo=_ART)
        df_with_prev_day = _make_df(date(2026, 9, 9))  # last bar is T-1

        history, status, from_cache = self._run(df_with_prev_day, art_now)

        assert history is not None
        assert status in (FetchStatus.OK, FetchStatus.PARTIAL)

    def test_two_day_lag_also_rejected(self):
        """A T-2 bar is also stale and must be rejected."""
        art_now = datetime(2026, 9, 10, 20, 0, tzinfo=_ART)
        old_df = _make_df(date(2026, 9, 8))  # last bar is T-2

        history, status, _ = self._run(old_df, art_now)

        assert history is None
        assert status == FetchStatus.MISSING

    def test_none_from_yfinance_still_falls_back_to_cache(self):
        """Network failure (fetch_prices returns None) still falls back to stale cache."""
        art_now = datetime(2026, 9, 10, 20, 0, tzinfo=_ART)

        cache = MagicMock()
        cache.prices_are_fresh.return_value = False
        stale_cached_df = _make_df(date(2026, 9, 9))
        cache.load_prices.return_value = stale_cached_df
        meta = _make_meta()

        with patch("data.fetcher.fetch_prices", return_value=None), \
             _mock_art_now(art_now):
            history, status, from_cache = _fetch_prices_with_fallback(meta, cache, [])

        # Network failure falls back to cache (STALE) — not MISSING
        assert status == FetchStatus.STALE
        assert from_cache is True
