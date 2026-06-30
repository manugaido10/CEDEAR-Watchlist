"""Reversal report — Markdown file from a list of ReversalOpportunity."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import List

from analysis.reversal.reversal_scanner import ReversalOpportunity

_TOTAL_CAPITAL_USD = 9_000.0
_MIN_POSITION_PCT = 0.05
_MAX_POSITION_PCT = 0.08


# ── Capital allocation ────────────────────────────────────────────────────────

def _allocate_capital(
    opportunities: List[ReversalOpportunity],
    investable: float,
) -> List[float]:
    """Weight by score, then clip to [5%, 8%] of investable capital."""
    if not opportunities:
        return []
    total_score = sum(o.score for o in opportunities)
    if total_score < 1e-10:
        weights = [1.0 / len(opportunities)] * len(opportunities)
    else:
        weights = [o.score / total_score for o in opportunities]

    raw = [w * investable for w in weights]
    min_usd = investable * _MIN_POSITION_PCT
    max_usd = investable * _MAX_POSITION_PCT
    return [max(min_usd, min(max_usd, v)) for v in raw]


# ── Formatters ────────────────────────────────────────────────────────────────

def _ars(v: float) -> str:
    return f"{int(round(v)):,}".replace(",", ".")


def _pct(v: float) -> str:
    return f"{v:.1f}%"


# ── Markdown builder ──────────────────────────────────────────────────────────

def _build_markdown(
    opportunities: List[ReversalOpportunity],
    run_date: str,
    investable: float,
) -> str:
    n = len(opportunities)
    allocations = _allocate_capital(opportunities, investable)

    lines: List[str] = [
        f"# Reversiones Tácticas — {run_date}",
        "",
        f"Análisis: {run_date}  |  Oportunidades: {n}  |  Capital invertible: USD {int(investable):,}",
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
            alloc_usd = allocations[i]
            alloc_pct = (alloc_usd / investable * 100) if investable > 0 else 0.0

            lines += [
                f"## #{i + 1} — {opp.symbol}  Score: **{opp.score:.1f}**",
                "",
                f"**{opp.name}** | tipo: {opp.asset_type} | tendencia semanal: `{opp.weekly_trend}`",
                "",
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
                "### Capital Sugerido",
                "",
                f"**USD {int(round(alloc_usd)):,}** ({_pct(alloc_pct)} del capital invertible)",
                "",
            ]
            if opp.warnings:
                lines += ["### Advertencias", ""]
                for w in opp.warnings:
                    lines.append(f"- {w}")
                lines.append("")
            lines += ["---", ""]

    lines += [
        "## Distribución de Capital",
        "",
        f"| | |",
        f"|---|---|",
        f"| Capital invertible | USD {int(investable):,} |",
        f"| Sizing por posición | 5-8% (ponderado por score) |",
        f"| Máximo posiciones | 5 |",
        "",
    ]

    if opportunities:
        lines += [
            "| Rank | Ticker | USD | % invertible |",
            "|------|--------|-----|-------------|",
        ]
        for i, opp in enumerate(opportunities):
            alloc_usd = allocations[i]
            alloc_pct = alloc_usd / investable * 100 if investable > 0 else 0.0
            lines.append(
                f"| #{i + 1} | {opp.symbol} | {int(round(alloc_usd)):,} | {_pct(alloc_pct)} |"
            )
        lines.append("")

    lines += [
        "---",
        "",
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
    run_date: str = "",
    output_dir: Path = Path("output"),
    total_capital: float = _TOTAL_CAPITAL_USD,
) -> Path:
    """Generate reversal report and save to output/reversiones_YYYY-MM-DD.md.

    Returns the path of the saved file.
    """
    if not run_date:
        run_date = str(date.today())

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    investable = total_capital  # no cash reserve rule for the reversal module
    md_path = output_dir / f"reversiones_{run_date}.md"
    content = _build_markdown(opportunities, run_date, investable)
    md_path.write_text(content, encoding="utf-8")

    return md_path
