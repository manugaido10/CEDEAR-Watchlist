"""Tests for analysis/reversal/fx_context.py.

All scenarios use synthetic TickerBundles — no yfinance, no cache, no I/O.
Coverage:
  - CEDEAR with enough bars for both windows → full enrichment
  - CEDEAR with only 6 bars → 5d populated, 20d null
  - CEDEAR with <6 bars → both windows null (metadata still present)
  - Argentine stock → returns None (A2 does not apply)
  - Bundle without CCL series → returns None
  - CCL alignment: verify CCL lookup uses the same calendar dates as the ARS bars
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from analysis.reversal.fx_context import build_fx_enrichment
from data.models import (
    AssetType,
    CCLSeries,
    FetchStatus,
    PriceHistory,
    TickerBundle,
    TickerMetadata,
)


def _make_price_df(closes: list, start_date: str = "2026-01-05") -> pd.DataFrame:
    idx = pd.date_range(start=start_date, periods=len(closes), freq="B")
    return pd.DataFrame(
        {
            "open": closes,
            "high": [c * 1.01 for c in closes],
            "low": [c * 0.99 for c in closes],
            "close": closes,
            "volume": [1_000_000] * len(closes),
        },
        index=idx,
    )


def _make_ccl(dates: pd.DatetimeIndex, values: list, spot: float | None = None) -> CCLSeries:
    ser = pd.Series(values, index=dates)
    return CCLSeries(data=ser, spot=spot if spot is not None else float(ser.iloc[-1]), as_of=dates[-1].date())


def _make_bundle(
    asset_type: AssetType,
    price_df: pd.DataFrame | None,
    ccl: CCLSeries | None,
    symbol: str = "TEST.BA",
    underlying: str | None = "TEST",
    ratio: float | None = 1.0,
) -> TickerBundle:
    return TickerBundle(
        metadata=TickerMetadata(
            symbol_ars=symbol,
            name="Test",
            asset_type=asset_type,
            symbol_underlying=underlying,
            cedears_per_underlying=ratio,
        ),
        prices_ars=PriceHistory(symbol=symbol, data=price_df) if price_df is not None else None,
        ccl_series=ccl,
        mep_series=None,
        fundamentals=None,
        status=FetchStatus.OK,
    )


# ── CEDEAR with enough bars ──────────────────────────────────────────────────

def test_cedear_full_enrichment_populates_all_fields():
    # 25 bars → both 5d and 20d windows have enough data.
    closes = [100.0 + i for i in range(25)]  # rising linearly
    df = _make_price_df(closes)
    # CCL constant at 1000 → pct_change_ccl_*d should be 0.0, and pct_usd_implied == pct_ars.
    ccl = _make_ccl(df.index, [1000.0] * 25, spot=1000.0)
    bundle = _make_bundle(AssetType.CEDEAR, df, ccl)

    enrichment = build_fx_enrichment(bundle)

    assert enrichment is not None
    assert enrichment["ccl_at_scan"] == 1000.0
    assert enrichment["underlying_symbol"] == "TEST"
    assert enrichment["cedears_per_underlying"] == 1.0

    # ARS 5d: close[-1]=124, close[-6]=119, → (124/119)−1 ≈ 0.042
    assert enrichment["pct_change_ars_5d"] == pytest.approx(124 / 119 - 1, abs=1e-4)
    assert enrichment["pct_change_ars_20d"] == pytest.approx(124 / 104 - 1, abs=1e-4)
    # CCL constant → 0.0 both windows
    assert enrichment["pct_change_ccl_5d"] == 0.0
    assert enrichment["pct_change_ccl_20d"] == 0.0
    # Implied USD equals ARS change when CCL is flat
    assert enrichment["pct_change_usd_implied_5d"] == pytest.approx(enrichment["pct_change_ars_5d"], abs=1e-4)
    assert enrichment["pct_change_usd_implied_20d"] == pytest.approx(enrichment["pct_change_ars_20d"], abs=1e-4)


def test_cedear_ccl_alignment_uses_same_calendar_dates():
    # 25 bars. Make CCL jump only on the LAST bar's calendar date. If alignment
    # uses that same date, the ccl pct_change spans the jump; otherwise it doesn't.
    closes = [100.0] * 25  # constant ARS
    df = _make_price_df(closes)
    ccl_vals = [1000.0] * 24 + [1100.0]  # 10% jump on last day
    ccl = _make_ccl(df.index, ccl_vals)
    bundle = _make_bundle(AssetType.CEDEAR, df, ccl)

    enrichment = build_fx_enrichment(bundle)

    # ARS flat → 0.0
    assert enrichment["pct_change_ars_5d"] == 0.0
    # CCL 5d = ccl[-1]/ccl[-6] − 1 = 1100/1000 − 1 = 0.10 (aligned to bar dates)
    assert enrichment["pct_change_ccl_5d"] == pytest.approx(0.10, abs=1e-4)
    # Implied USD: (1+0)/(1+0.10) − 1 ≈ −0.0909 — asset lost purchasing power vs USD
    assert enrichment["pct_change_usd_implied_5d"] == pytest.approx(-0.0909, abs=1e-4)


# ── CEDEAR with partial-window data ──────────────────────────────────────────

def test_cedear_only_5d_when_bars_insufficient_for_20d():
    closes = [100.0 + i for i in range(7)]  # 7 bars: enough for 5d, not 20d
    df = _make_price_df(closes)
    ccl = _make_ccl(df.index, [1000.0] * 7)
    bundle = _make_bundle(AssetType.CEDEAR, df, ccl)

    enrichment = build_fx_enrichment(bundle)

    assert enrichment["pct_change_ars_5d"] is not None
    assert enrichment["pct_change_ars_20d"] is None
    assert enrichment["pct_change_ccl_20d"] is None
    assert enrichment["pct_change_usd_implied_20d"] is None
    # Metadata is still populated even without windows
    assert enrichment["ccl_at_scan"] is not None
    assert enrichment["underlying_symbol"] == "TEST"


def test_cedear_both_windows_null_when_too_few_bars():
    closes = [100.0, 101.0, 102.0]  # 3 bars — neither window can compute
    df = _make_price_df(closes)
    ccl = _make_ccl(df.index, [1000.0] * 3)
    bundle = _make_bundle(AssetType.CEDEAR, df, ccl)

    enrichment = build_fx_enrichment(bundle)

    assert enrichment is not None
    assert enrichment["pct_change_ars_5d"] is None
    assert enrichment["pct_change_ars_20d"] is None


# ── Not-applicable cases return None ─────────────────────────────────────────

def test_argentine_stock_returns_none():
    closes = [100.0 + i for i in range(25)]
    df = _make_price_df(closes)
    ccl = _make_ccl(df.index, [1000.0] * 25)
    bundle = _make_bundle(
        AssetType.ARGENTINE_STOCK, df, ccl,
        symbol="YPFD.BA", underlying=None, ratio=None,
    )
    assert build_fx_enrichment(bundle) is None


def test_cedear_without_ccl_returns_none():
    closes = [100.0 + i for i in range(25)]
    df = _make_price_df(closes)
    bundle = _make_bundle(AssetType.CEDEAR, df, ccl=None)
    assert build_fx_enrichment(bundle) is None


def test_cedear_without_prices_returns_none():
    ccl_dates = pd.date_range("2026-01-05", periods=25, freq="B")
    ccl = _make_ccl(ccl_dates, [1000.0] * 25)
    bundle = _make_bundle(AssetType.CEDEAR, price_df=None, ccl=ccl)
    assert build_fx_enrichment(bundle) is None
