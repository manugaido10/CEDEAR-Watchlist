"""Tests for analysis/reversal/liquidity.py — paper-trading mode (#28).

The gate now uses a fixed ADV floor (ADV_MIN_ARS = 15M ARS) instead of a
capital-ratio formula. total_capital_ars is accepted but ignored.

Unit tests use synthetic numeric inputs. Integration test uses patched
_compute_metrics to isolate Gate 7 from other scanner criteria.
"""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from analysis.reversal.liquidity import (
    ADV_MIN_ARS,
    POSITION_PCT_MID,
    TRAILING_TRADING_DAYS,
    check_liquidity,
    compute_adv_ars,
    liquidity_ratio_pct,
)
from analysis.reversal.reversal_scanner import _BundleMetrics, scan_reversals
from data.models import AssetType, FetchStatus


# ─────────────────────────────────────────────────────────────────────────────
# compute_adv_ars — unit
# ─────────────────────────────────────────────────────────────────────────────

class TestComputeAdvArs:
    def test_none_or_empty(self):
        assert compute_adv_ars(None) is None
        assert compute_adv_ars(pd.DataFrame()) is None

    def test_missing_volume_returns_none(self):
        df = pd.DataFrame(
            {"open": [1], "close": [1]},
            index=pd.date_range("2026-01-01", periods=1, freq="B"),
        )
        assert compute_adv_ars(df) is None

    def test_uses_last_window_bars(self):
        # 40 bars, constant close=100 volume=10 → avg = 1000 ARS.
        df = pd.DataFrame(
            {"close": [100.0] * 40, "volume": [10.0] * 40},
            index=pd.date_range("2026-01-01", periods=40, freq="B"),
        )
        adv = compute_adv_ars(df)
        assert adv == pytest.approx(1000.0)

    def test_as_of_trims_window(self):
        # 40 bars; as_of before some bars → only earlier bars used.
        dates = pd.date_range("2026-01-01", periods=40, freq="B")
        df = pd.DataFrame(
            {"close": [100.0] * 20 + [200.0] * 20,
             "volume": [10.0] * 40},
            index=dates,
        )
        # as_of = 15th bar → mean of 100 × 10 = 1000 over the trailing 15 bars.
        adv = compute_adv_ars(df, as_of=dates[14])
        assert adv == pytest.approx(1000.0)


# ─────────────────────────────────────────────────────────────────────────────
# check_liquidity — unit (ADV floor gate)
# ─────────────────────────────────────────────────────────────────────────────

class TestCheckLiquidity:
    def test_adv_above_floor_passes(self):
        assert check_liquidity(20_000_000.0) is None

    def test_adv_exactly_at_floor_passes(self):
        # ADV_MIN_ARS is a strict lower bound; equality passes.
        assert check_liquidity(float(ADV_MIN_ARS)) is None

    def test_adv_below_floor_discards_with_reason(self):
        reason = check_liquidity(1_000_000.0)
        assert reason is not None
        assert "Volumen insuficiente" in reason
        assert "riesgo de iliquidez" in reason

    def test_adv_none_passes_silently(self):
        # Fail-open: missing ADV → gate cannot evaluate → no discard.
        assert check_liquidity(None) is None

    def test_adv_zero_passes_silently(self):
        assert check_liquidity(0.0) is None

    def test_capital_arg_is_ignored(self):
        # total_capital_ars kept for call-site compat — must not affect outcome.
        # ADV below floor → blocked regardless of capital.
        assert check_liquidity(1_000_000.0, total_capital_ars=None) is not None
        assert check_liquidity(1_000_000.0, total_capital_ars=0.0) is not None
        assert check_liquidity(1_000_000.0, total_capital_ars=10_000_000.0) is not None
        # ADV above floor → passes regardless of capital.
        assert check_liquidity(20_000_000.0, total_capital_ars=None) is None
        assert check_liquidity(20_000_000.0, total_capital_ars=0.0) is None

    def test_ratio_calculation_helper(self):
        # liquidity_ratio_pct kept for diagnostic script — unit sanity check.
        # 6.5% of 10M = 650K, divided by 1M → 65%.
        ratio = liquidity_ratio_pct(1_000_000.0, 10_000_000.0)
        assert ratio == pytest.approx(65.0)

    def test_constants_are_documented_values(self):
        assert ADV_MIN_ARS == 15_000_000
        assert POSITION_PCT_MID == pytest.approx(0.065)
        assert TRAILING_TRADING_DAYS == 20


# ─────────────────────────────────────────────────────────────────────────────
# scan_reversals integration — Gate 7 fires on ADV alone
# ─────────────────────────────────────────────────────────────────────────────

def _build_bundle(symbol: str, volume: float, n_bars: int = 220):
    from unittest.mock import MagicMock

    close = 100.0
    closes = [close] * n_bars
    df = pd.DataFrame(
        {
            "open": closes, "high": [c * 1.01 for c in closes],
            "low": [c * 0.99 for c in closes], "close": closes,
            "volume": [volume] * n_bars,
        },
        index=pd.date_range("2025-01-01", periods=n_bars, freq="B"),
    )

    bundle = MagicMock()
    bundle.metadata.symbol_ars = symbol
    bundle.metadata.name = symbol
    bundle.metadata.asset_type = AssetType.CEDEAR
    bundle.metadata.symbol_underlying = None
    bundle.status = FetchStatus.OK
    prices_mock = MagicMock()
    prices_mock.data = df
    bundle.prices_ars = prices_mock
    bundle.fundamentals = None
    return bundle, df


def _passing_metrics(symbol: str, df: pd.DataFrame, adv_ars):
    closes = df["close"].to_numpy()
    n = len(closes)
    return _BundleMetrics(
        symbol=symbol,
        name=symbol,
        asset_type="cedear",
        close=closes,
        df=df,
        entry_price_ars=100.0,
        weekly_trend="neutral",
        weekly_strength=12.0,
        rsi=35.0,
        rsi_series=np.full(n, 35.0),
        vol_ratio=0.5,
        support_result=(99.0, "MA50", 0.01),
        catalysts=["RSI bullish divergence"],
        fundamentals_ok=True,
        adv_ars=adv_ars,
    )


class TestGate7Integration:
    def test_adv_below_floor_discarded(self):
        # ADV=1_000 < ADV_MIN_ARS=15M → discarded regardless of capital.
        bundle, df = _build_bundle("TINY.BA", volume=10.0)
        metrics = _passing_metrics("TINY.BA", df, adv_ars=1_000.0)

        with patch(
            "analysis.reversal.reversal_scanner._compute_metrics",
            return_value=metrics,
        ):
            with patch(
                "analysis.reversal.reversal_scanner.check_earnings_warning",
                return_value=type("R", (), {"message": None})(),
            ):
                opps = scan_reversals(
                    [bundle],
                    scan_date="2026-09-03",
                    record=False,
                    total_capital_ars=10_000_000.0,
                    positions=[],
                    outcomes=[],
                )
        assert opps == []

    def test_adv_below_floor_discarded_without_capital_too(self):
        # Gate uses ADV floor, not capital ratio — total_capital_ars=None doesn't bypass it.
        bundle, df = _build_bundle("TINY.BA", volume=10.0)
        metrics = _passing_metrics("TINY.BA", df, adv_ars=1_000.0)

        with patch(
            "analysis.reversal.reversal_scanner._compute_metrics",
            return_value=metrics,
        ):
            with patch(
                "analysis.reversal.reversal_scanner.check_earnings_warning",
                return_value=type("R", (), {"message": None})(),
            ):
                opps = scan_reversals(
                    [bundle],
                    scan_date="2026-09-03",
                    record=False,
                    total_capital_ars=None,
                    positions=[],
                    outcomes=[],
                )
        assert opps == []

    def test_healthy_volume_passes_gate(self):
        # ADV=100M >> ADV_MIN_ARS → passes.
        bundle, df = _build_bundle("BIG.BA", volume=1_000_000.0)
        metrics = _passing_metrics("BIG.BA", df, adv_ars=100_000_000.0)

        with patch(
            "analysis.reversal.reversal_scanner._compute_metrics",
            return_value=metrics,
        ):
            with patch(
                "analysis.reversal.reversal_scanner.check_earnings_warning",
                return_value=type("R", (), {"message": None})(),
            ):
                opps = scan_reversals(
                    [bundle],
                    scan_date="2026-09-03",
                    record=False,
                    total_capital_ars=10_000_000.0,
                    positions=[],
                    outcomes=[],
                )
        assert len(opps) == 1
        assert opps[0].symbol == "BIG.BA"

    def test_missing_adv_passes_gate(self):
        # adv_ars=None → fail-open → opportunity emitted.
        bundle, df = _build_bundle("NOADV.BA", volume=1_000_000.0)
        metrics = _passing_metrics("NOADV.BA", df, adv_ars=None)

        with patch(
            "analysis.reversal.reversal_scanner._compute_metrics",
            return_value=metrics,
        ):
            with patch(
                "analysis.reversal.reversal_scanner.check_earnings_warning",
                return_value=type("R", (), {"message": None})(),
            ):
                opps = scan_reversals(
                    [bundle],
                    scan_date="2026-09-03",
                    record=False,
                    total_capital_ars=10_000_000.0,
                    positions=[],
                    outcomes=[],
                )
        assert len(opps) == 1
