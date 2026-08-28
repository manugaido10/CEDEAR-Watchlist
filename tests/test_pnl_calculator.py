"""Tests for analysis/performance/pnl_calculator.py."""

from __future__ import annotations

import math
import pytest

from analysis.performance.pnl_calculator import (
    COMMISSION_RATE,
    compute_floating_pnl,
    compute_realized_pnl,
)
from data.positions_log import Position


def _make_position(**kwargs) -> Position:
    defaults = dict(
        symbol="TEST",
        source="momentum",
        open_date="2026-01-01",
        open_price_ars=100.0,
        qty=10.0,
        score_at_entry=0.8,
        invalidation_at_entry_ars=90.0,
        status="open",
        close_date=None,
        close_price_ars=None,
        close_reason=None,
    )
    defaults.update(kwargs)
    return Position(**defaults)


class TestComputeRealizedPnl:
    def test_amd_example_gross_net_commission(self):
        # AMD: 50 sh, open 75288, close 77725
        # gross +121,850 ARS, commission ~42,461 ARS, net ~+79,389 ARS
        pos = _make_position(
            symbol="AMD",
            open_price_ars=75_288.0,
            qty=50.0,
            status="closed",
            close_date="2026-02-01",
            close_price_ars=77_725.0,
            close_reason="target",
        )
        result = compute_realized_pnl(pos, mep_at_close=1300.0)

        assert result["realized"] is True
        assert result["gross_pnl_ars"] == pytest.approx(121_850.0, abs=1)
        assert result["commission_ars"] == pytest.approx(42_461.0, abs=5)
        assert result["pnl_ars"] == pytest.approx(79_389.0, abs=5)

    def test_net_pnl_pct_uses_invested_capital(self):
        pos = _make_position(
            status="closed",
            close_date="2026-02-01",
            close_price_ars=110.0,
            close_reason="target",
        )
        result = compute_realized_pnl(pos, mep_at_close=1000.0)
        invested = 100.0 * 10.0
        expected_pct = result["pnl_ars"] / invested * 100.0
        assert result["pnl_pct"] == pytest.approx(expected_pct, rel=1e-6)

    def test_pnl_usd_conversion(self):
        pos = _make_position(
            status="closed",
            close_date="2026-02-01",
            close_price_ars=110.0,
            close_reason="target",
        )
        mep = 1200.0
        result = compute_realized_pnl(pos, mep_at_close=mep)
        assert result["pnl_usd"] == pytest.approx(result["pnl_ars"] / mep, rel=1e-6)

    def test_zero_mep_returns_nan_usd(self):
        pos = _make_position(
            status="closed",
            close_date="2026-02-01",
            close_price_ars=110.0,
            close_reason="target",
        )
        result = compute_realized_pnl(pos, mep_at_close=0.0)
        assert math.isnan(result["pnl_usd"])

    def test_raises_on_open_position(self):
        pos = _make_position(status="open")
        with pytest.raises(ValueError):
            compute_realized_pnl(pos, mep_at_close=1000.0)

    def test_commission_is_both_legs(self):
        pos = _make_position(
            status="closed",
            close_date="2026-02-01",
            close_price_ars=100.0,
            close_reason="manual",
        )
        result = compute_realized_pnl(pos, mep_at_close=1000.0)
        buy_comm = COMMISSION_RATE * 100.0 * 10.0
        sell_comm = COMMISSION_RATE * 100.0 * 10.0
        assert result["commission_ars"] == pytest.approx(buy_comm + sell_comm, rel=1e-6)


class TestComputeFloatingPnl:
    def test_only_sell_commission_deducted(self):
        pos = _make_position(open_price_ars=100.0, qty=10.0)
        current = 110.0
        result = compute_floating_pnl(pos, current_price_ars=current, mep_now=1000.0)

        gross = (110.0 - 100.0) * 10.0
        sell_comm = COMMISSION_RATE * 110.0 * 10.0
        assert result["gross_pnl_ars"] == pytest.approx(gross, rel=1e-6)
        assert result["sell_commission_ars"] == pytest.approx(sell_comm, rel=1e-6)
        assert result["pnl_ars"] == pytest.approx(gross - sell_comm, rel=1e-6)

    def test_realized_flag_is_false(self):
        pos = _make_position()
        result = compute_floating_pnl(pos, current_price_ars=100.0, mep_now=1000.0)
        assert result["realized"] is False

    def test_pnl_pct_is_net_of_sell_commission(self):
        pos = _make_position(open_price_ars=100.0, qty=10.0)
        result = compute_floating_pnl(pos, current_price_ars=110.0, mep_now=1000.0)
        invested = 100.0 * 10.0
        expected_pct = result["pnl_ars"] / invested * 100.0
        assert result["pnl_pct"] == pytest.approx(expected_pct, rel=1e-6)

    def test_floating_does_not_include_buy_commission(self):
        # Realized should be lower than floating by exactly the buy commission
        pos = _make_position(
            open_price_ars=100.0,
            qty=10.0,
            status="closed",
            close_date="2026-02-01",
            close_price_ars=110.0,
            close_reason="target",
        )
        mep = 1000.0
        realized = compute_realized_pnl(pos, mep_at_close=mep)
        floating = compute_floating_pnl(
            _make_position(open_price_ars=100.0, qty=10.0),
            current_price_ars=110.0,
            mep_now=mep,
        )
        buy_comm = COMMISSION_RATE * 100.0 * 10.0
        assert realized["pnl_ars"] == pytest.approx(floating["pnl_ars"] - buy_comm, rel=1e-6)
