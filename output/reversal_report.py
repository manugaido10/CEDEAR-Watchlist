"""Reversal report — Markdown file from a list of ReversalOpportunity.

Paper-trading mode (#28): no capital allocation, no monetary sizing.
The report shows technical analysis only: entry, invalidation, support
distance, RSI, catalysts, and warnings. Scale-in signals show the
existing paper position's entry date and price for reference.
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import List, Optional

from analysis.reversal.reversal_scanner import ReversalOpportunity
from data.positions_log import Position

logger = logging.getLogger(__name__)


# ── Formatters ────────────────────────────────────────────────────────────────

def _ars(v: float) -> str:
    return f"{int(round(v)):,}".replace(",", ".")


# ── Markdown builder ──────────────────────────────────────────────────────────

def _build_markdown(
    opportunities: List[ReversalOpportunity],
    run_date: str,
) -> str:
    n = len(opportunities)

    lines: List[str] = [
        f"# Reversiones Tácticas — {run_date}",
        "",
        f"Análisis: {run_date}  |  Oportunidades: {n}",
        "",
        "---",
        "",
    ]

    if not opportunities:
        lines += [
            "*Sin oportunidades de reversión en este ciclo.*",
            "",
            "No se detectaron tickers que cumplan simultáneamente todos los criterios:",
            "tendencia semanal no negativa, RSI 25-45, volumen decreciente en la caída,",
            "soporte relevante dentro del 5%, y al menos un catalizador de entrada.",
            "",
        ]
    else:
        lines += [f"# Oportunidades ({n})", ""]
        for i, opp in enumerate(opportunities):
            tradeable = getattr(opp, "tradeable", True)
            is_scale_in = bool(getattr(opp, "is_scale_in", False))
            suppression_reason = getattr(opp, "suppression_reason", None)
            existing_position = getattr(opp, "existing_position", None)

            if not tradeable:
                heading_prefix = "🚫 NO OPERAR: "
            elif is_scale_in:
                heading_prefix = "➕ SUMA: "
            else:
                heading_prefix = ""

            lines += [
                f"## #{i + 1} — {heading_prefix}{opp.symbol}  Score: **{opp.score:.1f}**",
                "",
                f"**{opp.name}** | tipo: {opp.asset_type} | tendencia semanal: `{opp.weekly_trend}`",
                "",
            ]
            if not tradeable and suppression_reason:
                lines += [f"> 🚫 **NO OPERAR** — {suppression_reason}", ""]

            lines += [
                "### Indicadores",
                "",
                f"| Métrica | Valor |",
                f"|---------|-------|",
                f"| RSI 14 | **{opp.rsi_14:.1f}** |",
                f"| Soporte más cercano | {_ars(opp.nearest_support)} ARS ({opp.nearest_support_type}) |",
                f"| Distancia al soporte | {opp.distance_to_support_pct * 100:.2f}% |",
                f"| Ratio volumen (5d/20d) | {opp.volume_ratio:.3f} ({opp.volume_ratio * 100:.1f}% del vol 20d) |",
                "",
                "### Catalizadores",
                "",
            ]
            for cat in opp.catalyst:
                lines.append(f"- {cat}")
            lines += [
                "",
                "### Invalidación",
                "",
                f"**{_ars(opp.invalidation_level_ars)} ARS**",
                "",
                opp.invalidation_rationale,
                "",
            ]

            if is_scale_in and existing_position is not None:
                ep = float(getattr(existing_position, "entry_price_ars", 0.0) or 0.0)
                od = getattr(existing_position, "open_date", "—")
                score_prev = float(getattr(existing_position, "score_at_entry", 0.0) or 0.0)
                lines += [
                    "### Posición paper existente",
                    "",
                    f"- Entrada publicada: **{_ars(ep)} ARS** el {od}",
                    f"- Score al ingreso: {score_prev:.1f}",
                    "",
                ]

            if opp.warnings:
                lines += ["### Advertencias", ""]
                for w in opp.warnings:
                    lines.append(f"- {w}")
                lines.append("")
            lines += ["---", ""]

    lines += [
        "## Alertas — Niveles de Invalidación",
        "",
        "| Ticker | Nivel ARS | Rationale |",
        "|--------|-----------|-----------|",
    ]
    for opp in opportunities:
        short = opp.invalidation_rationale[:80].replace("|", "/")
        lines.append(f"| {opp.symbol} | {_ars(opp.invalidation_level_ars)} ARS | {short} |")

    lines.append("")
    return "\n".join(lines)


# ── Main entry point ──────────────────────────────────────────────────────────

def generate_reversal_report(
    opportunities: List[ReversalOpportunity],
    total_capital_ars: Optional[float] = None,   # unused — kept for call-site compat
    positions: Optional[List[Position]] = None,   # unused — kept for call-site compat
    run_date: str = "",
    output_dir: Path = Path("output"),
    mep_spot: Optional[float] = None,            # unused — kept for call-site compat
) -> Path:
    """Generate reversal report and save to output/reversiones_YYYY-MM-DD.md.

    Paper-trading mode: capital, positions, and mep_spot parameters are accepted
    but ignored. Returns the path of the saved file.
    """
    if not run_date:
        run_date = str(date.today())

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    md_path = output_dir / f"reversiones_{run_date}.md"
    content = _build_markdown(opportunities, run_date)
    md_path.write_text(content, encoding="utf-8")
    return md_path
