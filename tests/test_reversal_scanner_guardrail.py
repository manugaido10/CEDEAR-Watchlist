"""Tests for the invalidation >= entry_price guardrail in _evaluate_bundle."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from unittest.mock import patch, MagicMock

from data.models import AssetType, FetchStatus


def _make_bundle(symbol: str, closes: list, asset_type=AssetType.CEDEAR) -> MagicMock:
    """Minimal TickerBundle mock with a price series."""
    bundle = MagicMock()
    bundle.metadata.symbol_ars = symbol
    bundle.metadata.name = f"Test {symbol}"
    bundle.metadata.asset_type = asset_type
    bundle.metadata.symbol_underlying = None
    bundle.status = FetchStatus.OK

    df = pd.DataFrame(
        {
            "open": closes,
            "high": [c * 1.01 for c in closes],
            "low": [c * 0.99 for c in closes],
            "close": closes,
            "volume": [1_000_000] * len(closes),
        },
        index=pd.date_range("2025-01-01", periods=len(closes), freq="B"),
    )
    prices_mock = MagicMock()
    prices_mock.data = df
    bundle.prices_ars = prices_mock
    bundle.fundamentals = None
    return bundle


class TestInvalidationGuardrail:
    def test_normal_signal_passes_guardrail(self):
        """A valid signal where invalidation < entry_price should not be rejected."""
        from analysis.reversal.reversal_scanner import _evaluate_bundle

        # 250 bars rising then flat — entry well above any rolling support
        closes = [100.0 + i * 0.1 for i in range(200)] + [105.0] * 50
        bundle = _make_bundle("NORMAL.BA", closes)

        with patch("analysis.reversal.reversal_scanner._fundamentals_ok", return_value=True):
            with patch("analysis.reversal.reversal_scanner.check_earnings_warning") as mock_earn:
                mock_earn.return_value = MagicMock(message=None)
                # Just verify no exception and no forced rejection on a reasonable bundle
                result = _evaluate_bundle(bundle)
                # Result may be None (doesn't meet RSI/catalyst criteria) but must not error
                # The guardrail is not triggered here

    def test_guardrail_rejects_inverted_signal(self, caplog):
        """If by any means invalidation >= entry_price, the signal is rejected with logger.error."""
        import logging
        from analysis.reversal.reversal_scanner import _evaluate_bundle, _BundleMetrics

        # Construct a _BundleMetrics where support > entry_price to trigger the guardrail.
        # We patch _compute_metrics to return this pathological state.
        n = 250
        closes = np.array([150.0] * n)
        df = pd.DataFrame(
            {"open": closes, "high": closes * 1.01, "low": closes * 0.99,
             "close": closes, "volume": [1_000_000] * n},
            index=pd.date_range("2025-01-01", periods=n, freq="B"),
        )

        bad_metrics = _BundleMetrics(
            symbol="BAD.BA",
            name="Bad Corp",
            asset_type="cedear",
            close=closes,
            df=df,
            entry_price_ars=100.0,       # entry is LOW
            weekly_trend="neutral",
            weekly_strength=12.0,
            rsi=35.0,                    # RSI passes
            rsi_series=np.full(n, 35.0),
            vol_ratio=0.5,               # vol passes
            support_result=(102.0, "MA200", 0.02),  # support ABOVE entry → inverted
            catalysts=["MA200 bounce/proximity"],
            fundamentals_ok=True,
        )

        bundle = _make_bundle("BAD.BA", list(closes))

        with patch("analysis.reversal.reversal_scanner._compute_metrics", return_value=bad_metrics):
            with caplog.at_level(logging.ERROR, logger="analysis.reversal.reversal_scanner"):
                result = _evaluate_bundle(bundle)

        assert result is None, "Guardrail must return None for inverted invalidation"
        assert any("rejected" in r.message and "BAD.BA" in r.message for r in caplog.records), \
            "Guardrail must log logger.error with ticker and values"

    def test_guardrail_rejects_equal_invalidation(self, caplog):
        """Edge case: invalidation == entry_price is also rejected (>= condition)."""
        import logging
        from analysis.reversal.reversal_scanner import _evaluate_bundle, _BundleMetrics, INVALIDATION_BUFFER

        n = 250
        # If entry=100 and we want invalidation == entry:
        # invalidation = support * (1 - 0.015) = 100 → support = 100/0.985 ≈ 101.52
        entry = 100.0
        support = entry / (1.0 - INVALIDATION_BUFFER)  # makes invalidation == entry exactly

        closes = np.array([entry] * n)
        df = pd.DataFrame(
            {"open": closes, "high": closes * 1.01, "low": closes * 0.99,
             "close": closes, "volume": [1_000_000] * n},
            index=pd.date_range("2025-01-01", periods=n, freq="B"),
        )

        edge_metrics = _BundleMetrics(
            symbol="EDGE.BA",
            name="Edge Corp",
            asset_type="cedear",
            close=closes,
            df=df,
            entry_price_ars=entry,
            weekly_trend="neutral",
            weekly_strength=12.0,
            rsi=35.0,
            rsi_series=np.full(n, 35.0),
            vol_ratio=0.5,
            support_result=(support, "swing_low", 0.015),
            catalysts=["RSI bullish divergence"],
            fundamentals_ok=True,
        )

        bundle = _make_bundle("EDGE.BA", list(closes))

        with patch("analysis.reversal.reversal_scanner._compute_metrics", return_value=edge_metrics):
            with caplog.at_level(logging.ERROR, logger="analysis.reversal.reversal_scanner"):
                result = _evaluate_bundle(bundle)

        assert result is None
        assert any("rejected" in r.message for r in caplog.records)
