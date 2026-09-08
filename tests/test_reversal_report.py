"""Tests for output/reversal_report.py — paper-trading mode (#28).

No capital allocation, no monetary sizing. Tests focus on:
- Markdown structure (headings, tables, invalidation section)
- Scale-in rendering: "Posición paper existente" block with entry price/date/score
- Suppressed signal rendering: 🚫 prefix + reason block
- No capital sections anywhere in the output
"""

from __future__ import annotations

from typing import List

import pytest

from analysis.reversal.reversal_scanner import ReversalOpportunity
from data.positions_log import Position
from output.reversal_report import generate_reversal_report


# ── Helpers ──────────────────────────────────────────────────────────────────

def _opp(
    symbol: str,
    score: float = 60.0,
    *,
    tradeable: bool = True,
    is_scale_in: bool = False,
    existing_position: Position | None = None,
    suppression_reason: str | None = None,
    warnings: list | None = None,
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
        suppression_reason=suppression_reason,
        warnings=warnings or [],
    )


def _pos(symbol: str, entry_price: float = 1000.0, status: str = "open") -> Position:
    p = Position(
        symbol=symbol,
        source="reversal",
        open_date="2026-08-01",
        entry_price_ars=entry_price,
        score_at_entry=70.0,
        invalidation_at_entry_ars=entry_price * 0.95,
        status="open",
    )
    if status != "open":
        p.status = status
    return p


# ── generate_reversal_report ─────────────────────────────────────────────────

class TestGenerateReport:
    def test_empty_opportunities_writes_file(self, tmp_path):
        path = generate_reversal_report(
            opportunities=[],
            run_date="2026-09-03",
            output_dir=tmp_path,
        )
        text = path.read_text(encoding="utf-8")
        assert "Reversiones Tácticas — 2026-09-03" in text
        assert "Sin oportunidades" in text

    def test_no_capital_sections_in_output(self, tmp_path):
        opps = [_opp("AAA.BA", score=80.0)]
        path = generate_reversal_report(
            opportunities=opps,
            run_date="2026-09-03",
            output_dir=tmp_path,
        )
        text = path.read_text(encoding="utf-8")
        assert "Capital total" not in text
        assert "Capital sugerido" not in text
        assert "Capital Sugerido" not in text
        assert "ARS disponible" not in text
        assert "Headroom" not in text

    def test_new_opportunity_shows_technical_sections(self, tmp_path):
        opps = [_opp("AAA.BA", score=80.0)]
        path = generate_reversal_report(
            opportunities=opps,
            run_date="2026-09-03",
            output_dir=tmp_path,
        )
        text = path.read_text(encoding="utf-8")
        assert "### Indicadores" in text
        assert "### Catalizadores" in text
        assert "### Invalidación" in text
        assert "RSI 14" in text
        assert "975" in text  # invalidation level
        assert "Posición paper existente" not in text

    def test_scale_in_shows_paper_position_block(self, tmp_path):
        existing = _pos("AAA.BA", entry_price=1000.0)
        opps = [
            _opp(
                "AAA.BA", score=80.0,
                is_scale_in=True, existing_position=existing,
            ),
        ]
        path = generate_reversal_report(
            opportunities=opps,
            run_date="2026-09-03",
            output_dir=tmp_path,
        )
        text = path.read_text(encoding="utf-8")
        assert "➕ SUMA:" in text
        assert "### Posición paper existente" in text
        assert "Entrada publicada:" in text
        assert "1.000 ARS" in text  # entry_price_ars formatted
        assert "2026-08-01" in text  # open_date
        assert "70.0" in text  # score_at_entry
        # Must NOT have old capital-era strings
        assert "Suma a posición existente" not in text
        assert "Costo previo" not in text
        assert "Headroom disponible" not in text

    def test_suppressed_signal_shows_no_operar(self, tmp_path):
        opps = [
            _opp(
                "DECK.BA", score=75.0,
                tradeable=False,
                suppression_reason="En cuarentena post-stop — precio 5.000 < invalidación 5.399",
            ),
        ]
        path = generate_reversal_report(
            opportunities=opps,
            run_date="2026-09-03",
            output_dir=tmp_path,
        )
        text = path.read_text(encoding="utf-8")
        assert "🚫 NO OPERAR:" in text
        assert "cuarentena" in text

    def test_warnings_section_renders(self, tmp_path):
        opps = [_opp("AAA.BA", warnings=["Volumen muy bajo", "Tendencia semanal negativa"])]
        path = generate_reversal_report(
            opportunities=opps,
            run_date="2026-09-03",
            output_dir=tmp_path,
        )
        text = path.read_text(encoding="utf-8")
        assert "### Advertencias" in text
        assert "Volumen muy bajo" in text

    def test_alertas_table_present(self, tmp_path):
        opps = [_opp("AAA.BA", score=80.0)]
        path = generate_reversal_report(
            opportunities=opps,
            run_date="2026-09-03",
            output_dir=tmp_path,
        )
        text = path.read_text(encoding="utf-8")
        assert "## Alertas — Niveles de Invalidación" in text
        assert "AAA.BA" in text
        assert "975" in text

    def test_output_file_path(self, tmp_path):
        path = generate_reversal_report(
            opportunities=[],
            run_date="2026-09-03",
            output_dir=tmp_path,
        )
        assert path.name == "reversiones_2026-09-03.md"
        assert path.exists()

    def test_accepts_unused_compat_params(self, tmp_path):
        # total_capital_ars, positions, mep_spot kept for call-site compat — must not crash.
        path = generate_reversal_report(
            opportunities=[],
            total_capital_ars=12_000_000.0,
            positions=[_pos("AAA.BA")],
            run_date="2026-09-03",
            output_dir=tmp_path,
            mep_spot=1200.0,
        )
        assert path.exists()
