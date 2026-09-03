"""Tests for output/reversal_report.py capital allocation.

Focuses on _allocate_capital pure math + report structure signals — the
Markdown builder is exercised via generate_reversal_report over a tmp_path.

Dependency-injection style, mirroring test_suppression / test_pnl_calculator.
"""

from __future__ import annotations

from typing import List

import pytest

from analysis.reversal.reversal_scanner import ReversalOpportunity
from data.positions_log import Position
from output.reversal_report import (
    _MAX_POSITION_PCT,
    _MIN_POSITION_PCT,
    _allocate_capital,
    _total_committed_ars,
    generate_reversal_report,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _opp(
    symbol: str,
    score: float = 60.0,
    *,
    tradeable: bool = True,
    is_scale_in: bool = False,
    existing_position: Position | None = None,
) -> ReversalOpportunity:
    return ReversalOpportunity(
        symbol=symbol,
        name=symbol,
        asset_type="cedear",
        score=score,
        rsi_14=30.0,
        entry_price_ars=1000.0,
        nearest_support=990.0,
        nearest_support_type="MA50",
        distance_to_support_pct=0.01,
        catalyst=["RSI bullish divergence"],
        volume_ratio=0.5,
        weekly_trend="neutral",
        invalidation_level_ars=975.0,
        invalidation_rationale="MA50 support",
        tradeable=tradeable,
        is_scale_in=is_scale_in,
        existing_position=existing_position,
    )


def _pos(symbol: str, qty: float, open_price: float, status: str = "open") -> Position:
    p = Position(
        symbol=symbol,
        source="reversal",
        open_date="2026-08-01",
        open_price_ars=open_price,
        qty=qty,
        score_at_entry=70.0,
        invalidation_at_entry_ars=open_price * 0.95,
        status="open",
    )
    if status != "open":
        p.status = status
    return p


# ── _total_committed_ars ─────────────────────────────────────────────────────

class TestCommittedTotal:
    def test_sums_open_only(self):
        positions = [
            _pos("AAPL.BA", qty=10, open_price=1000.0),
            _pos("MSFT.BA", qty=5, open_price=2000.0),
            _pos("GOOG.BA", qty=100, open_price=500.0, status="closed"),
        ]
        # closed excluded
        assert _total_committed_ars(positions) == pytest.approx(10_000 + 10_000)

    def test_empty(self):
        assert _total_committed_ars([]) == 0.0


# ── _allocate_capital ────────────────────────────────────────────────────────

class TestAllocateNewPositions:
    def test_score_weighted_within_band(self):
        # Two tradeable, no scale-in, plenty of capital disponible.
        # Score weights: 80/(80+40) = 2/3, 40/120 = 1/3 → raw 2/3 * 10M = 6.67M,
        # 1/3 * 10M = 3.33M. Both clipped to max 8% = 800K.
        opps = [_opp("AAA.BA", score=80.0), _opp("BBB.BA", score=40.0)]
        alloc = _allocate_capital(
            opps, total_capital_ars=10_000_000.0,
            capital_disponible_ars=10_000_000.0, positions=[],
        )
        # Both hit the 8% ceiling because raw weights exceed the max.
        assert alloc[0] == pytest.approx(10_000_000.0 * _MAX_POSITION_PCT)
        assert alloc[1] == pytest.approx(10_000_000.0 * _MAX_POSITION_PCT)

    def test_low_weight_lifted_to_floor(self):
        # 5 opportunities equal score → weight 20% each → but clipped to max 8%.
        opps = [_opp(f"T{i}.BA", score=50.0) for i in range(5)]
        alloc = _allocate_capital(
            opps, total_capital_ars=10_000_000.0,
            capital_disponible_ars=10_000_000.0, positions=[],
        )
        for v in alloc:
            assert 10_000_000.0 * _MIN_POSITION_PCT <= v <= 10_000_000.0 * _MAX_POSITION_PCT

    def test_non_tradeable_zero(self):
        opps = [
            _opp("AAA.BA", score=80.0, tradeable=False),
            _opp("BBB.BA", score=40.0),
        ]
        alloc = _allocate_capital(
            opps, total_capital_ars=10_000_000.0,
            capital_disponible_ars=10_000_000.0, positions=[],
        )
        assert alloc[0] == 0.0
        assert alloc[1] > 0.0


class TestAllocateScaleIn:
    def test_scale_in_capped_by_headroom(self):
        # Ticker already committed 700K on 10M capital → cap 800K → headroom 100K.
        # Score-weighted base would be 8% (800K); scale-in clip → 100K.
        existing = _pos("AAA.BA", qty=700, open_price=1000.0)  # 700K committed
        opps = [
            _opp("AAA.BA", score=80.0, is_scale_in=True, existing_position=existing),
        ]
        alloc = _allocate_capital(
            opps, total_capital_ars=10_000_000.0,
            capital_disponible_ars=9_300_000.0,  # 10M - 700K
            positions=[existing],
        )
        assert alloc[0] == pytest.approx(100_000.0)

    def test_scale_in_zero_headroom_zero_allocation(self):
        # Ticker fully committed at cap → headroom 0 → alloc 0 (even though tradeable).
        existing = _pos("AAA.BA", qty=800, open_price=1000.0)  # 800K = 8% cap
        opps = [
            _opp("AAA.BA", score=80.0, is_scale_in=True, existing_position=existing),
        ]
        alloc = _allocate_capital(
            opps, total_capital_ars=10_000_000.0,
            capital_disponible_ars=9_200_000.0,
            positions=[existing],
        )
        assert alloc[0] == 0.0


class TestAllocateScaleDown:
    def test_proportional_scale_down_when_capital_short(self):
        # 5 new-position opportunities, all clipped to 800K each = 4M total,
        # but capital_disponible only 2M → scale factor 0.5 → each 400K.
        opps = [_opp(f"T{i}.BA", score=50.0) for i in range(5)]
        alloc = _allocate_capital(
            opps, total_capital_ars=10_000_000.0,
            capital_disponible_ars=2_000_000.0, positions=[],
        )
        assert sum(alloc) == pytest.approx(2_000_000.0)
        for v in alloc:
            assert v == pytest.approx(400_000.0)

    def test_no_scale_down_when_capital_sufficient(self):
        opps = [_opp("AAA.BA", score=80.0)]
        alloc = _allocate_capital(
            opps, total_capital_ars=10_000_000.0,
            capital_disponible_ars=10_000_000.0, positions=[],
        )
        # 8% = 800K, disponible 10M >> 800K → no scaling.
        assert alloc[0] == pytest.approx(10_000_000.0 * _MAX_POSITION_PCT)


class TestAllocateZeroCapital:
    def test_zero_disponible_all_zero(self):
        opps = [_opp("AAA.BA"), _opp("BBB.BA")]
        alloc = _allocate_capital(
            opps, total_capital_ars=10_000_000.0,
            capital_disponible_ars=0.0, positions=[],
        )
        assert alloc == [0.0, 0.0]

    def test_negative_disponible_all_zero(self):
        opps = [_opp("AAA.BA")]
        alloc = _allocate_capital(
            opps, total_capital_ars=10_000_000.0,
            capital_disponible_ars=-1_000_000.0, positions=[],
        )
        assert alloc == [0.0]


# ── generate_reversal_report — smoke + key rendering signals ────────────────

class TestGenerateReport:
    def test_empty_opportunities_writes_file(self, tmp_path):
        path = generate_reversal_report(
            opportunities=[],
            total_capital_ars=10_000_000.0,
            positions=[],
            run_date="2026-09-03",
            output_dir=tmp_path,
            mep_spot=1200.0,
        )
        text = path.read_text(encoding="utf-8")
        assert "Reversiones Tácticas — 2026-09-03" in text
        assert "Capital total: ARS 10.000.000" in text
        assert "Sin oportunidades" in text

    def test_zero_disponible_shows_warning(self, tmp_path):
        # Positions consume 100% of capital.
        positions = [_pos("XXX.BA", qty=10_000, open_price=1000.0)]  # 10M committed
        opps = [_opp("AAA.BA", score=80.0)]
        path = generate_reversal_report(
            opportunities=opps,
            total_capital_ars=10_000_000.0,
            positions=positions,
            run_date="2026-09-03",
            output_dir=tmp_path,
            mep_spot=1200.0,
        )
        text = path.read_text(encoding="utf-8")
        assert "Sin capital disponible" in text
        # Allocation row shows 0.
        assert "| 0 | 0.0% |" in text

    def test_scale_in_label_present(self, tmp_path):
        existing = _pos("AAA.BA", qty=100, open_price=1000.0)  # 100K committed
        opps = [
            _opp(
                "AAA.BA", score=80.0,
                is_scale_in=True, existing_position=existing,
            ),
        ]
        path = generate_reversal_report(
            opportunities=opps,
            total_capital_ars=10_000_000.0,
            positions=[existing],
            run_date="2026-09-03",
            output_dir=tmp_path,
            mep_spot=1200.0,
        )
        text = path.read_text(encoding="utf-8")
        assert "Suma a posición existente" in text
        assert "Costo previo" in text
        assert "Headroom disponible" in text
        # Rank table marks it as suma.
        assert "➕" in text

    def test_new_position_label(self, tmp_path):
        opps = [_opp("AAA.BA", score=80.0)]
        path = generate_reversal_report(
            opportunities=opps,
            total_capital_ars=10_000_000.0,
            positions=[],
            run_date="2026-09-03",
            output_dir=tmp_path,
            mep_spot=1200.0,
        )
        text = path.read_text(encoding="utf-8")
        assert "### Capital Sugerido" in text
        # Should not use the scale-in header.
        assert "Suma a posición existente" not in text
