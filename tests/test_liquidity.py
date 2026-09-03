"""Tests for analysis/reversal/liquidity.py + Gate 7 integration.

Unit tests use synthetic numeric inputs. Integration test constructs a
synthetic bundle whose ADV × POSITION_PCT_MID pushes the ratio over/under
threshold and calls scan_reversals directly. No file I/O, no cache access,
no network — same dependency-injection style as tests/test_suppression.py.
"""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from analysis.reversal.liquidity import (
    LIQUIDITY_MAX_RATIO_PCT,
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
# check_liquidity — unit (fail-open + threshold)
# ─────────────────────────────────────────────────────────────────────────────

class TestCheckLiquidity:
    def test_ratio_under_threshold_passes(self):
        # ADV big enough that 6.5% of 10M is tiny relative → ratio well under 10%.
        adv_ars = 100_000_000.0
        assert check_liquidity(adv_ars, total_capital_ars=10_000_000.0) is None

    def test_ratio_at_threshold_passes(self):
        # Position = 6.5% of capital. If position/ADV = 10.0% exactly → passes (<=).
        # position_ars = 650_000, so ADV_ars = 6_500_000 for ratio == 10.0%.
        assert check_liquidity(6_500_000.0, total_capital_ars=10_000_000.0) is None

    def test_ratio_over_threshold_discards_with_reason(self):
        # ADV tiny → ratio 100%. Position 650K / 650K = 100%.
        reason = check_liquidity(650_000.0, total_capital_ars=10_000_000.0)
        assert reason is not None
        assert "Volumen insuficiente" in reason
        assert "100%" in reason
        assert "riesgo de iliquidez" in reason

    def test_adv_none_passes_silently(self):
        # Fail-open: missing ADV → no discard, no crash.
        assert check_liquidity(None, total_capital_ars=10_000_000.0) is None

    def test_adv_zero_passes_silently(self):
        assert check_liquidity(0.0, total_capital_ars=10_000_000.0) is None

    def test_capital_none_passes_silently(self):
        # Fail-open: missing capital → gate cannot evaluate → not a failure.
        assert check_liquidity(1_000_000.0, total_capital_ars=None) is None

    def test_capital_zero_passes_silently(self):
        assert check_liquidity(1_000_000.0, total_capital_ars=0.0) is None

    def test_ratio_calculation_helper(self):
        # 6.5% of 10M = 650K, divided by 1M → 65%.
        ratio = liquidity_ratio_pct(1_000_000.0, 10_000_000.0)
        assert ratio == pytest.approx(65.0)

    def test_constants_are_documented_values(self):
        assert POSITION_PCT_MID == pytest.approx(0.065)
        assert LIQUIDITY_MAX_RATIO_PCT == pytest.approx(10.0)
        assert TRAILING_TRADING_DAYS == 20


# ─────────────────────────────────────────────────────────────────────────────
# scan_reversals integration — Gate 7 fires only when capital is supplied
# ─────────────────────────────────────────────────────────────────────────────

def _build_bundle(symbol: str, volume: float, n_bars: int = 220):
    """Construct a bundle that satisfies every other gate (RSI, support,
    catalyst, vol_ratio, weekly_trend, fundamentals) so the liquidity gate
    is the only remaining discriminator."""
    from unittest.mock import MagicMock

    # A steady price with a slight recent dip to trip RSI into 25-45 range,
    # and enough bars for MA200. We patch _compute_metrics anyway so the
    # actual closes only matter for _make_bundle infrastructure.
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
        support_result=(99.0, "MA50", 0.01),  # support just below → invalidation < entry
        catalysts=["RSI bullish divergence"],
        fundamentals_ok=True,
        adv_ars=adv_ars,
    )


class TestGate7Integration:
    def test_tiny_volume_discarded_when_capital_supplied(self, caplog):
        # ADV so small that 6.5% × 10M = 650K → ratio hugely over 10%.
        # ADV = 1000 → ratio = 65_000% → discard.
        bundle, df = _build_bundle("TINY.BA", volume=10.0)  # noqa: F841
        metrics = _passing_metrics("TINY.BA", df, adv_ars=1000.0)

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

    def test_tiny_volume_kept_when_capital_none(self):
        # Same bundle, but no capital → gate skipped → opportunity emitted.
        bundle, df = _build_bundle("TINY.BA", volume=10.0)
        metrics = _passing_metrics("TINY.BA", df, adv_ars=1000.0)

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
        assert len(opps) == 1
        assert opps[0].symbol == "TINY.BA"

    def test_healthy_volume_passes_gate(self):
        # ADV big enough that ratio well under 10%.
        # Position 650K / ADV 100M = 0.65% → passes.
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
        # adv_ars=None → gate cannot evaluate → passes (fail-open).
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
