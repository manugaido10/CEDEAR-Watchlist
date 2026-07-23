"""Accumulation report — Markdown file from a list of AccumulationOpportunity."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import List

from analysis.accumulation.accumulation_scanner import AccumulationOpportunity

_TOTAL_CAPITAL_USD = 9_000.0
_MIN_POSITION_PCT = 0.08
_MAX_POSITION_PCT = 0.10


# ── Capital allocation ────────────────────────────────────────────────────────

def _allocate_capital(
    opportunities: List[AccumulationOpportunity],
    investable: float,
) -> List[float]:
    """Weight by score, then clip to [8%, 10%] of investable capital."""
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
    opportunities: List[AccumulationOpportunity],
    run_date: str,
    investable: float,
) -> str:
    n = len(opportunities)
    allocations = _allocate_capital(opportunities, investable)

    lines: List[str] = [
        f"# Acumulación Temprana — {run_date}",
        "",
        f"Análisis: {run_date}  |  Oportunidades: {n}  |  Capital invertible: USD {int(investable):,}",
        "",
        "---",
        "",
    ]

    if not opportunities:
        lines += [
            "*Sin oportunidades de acumulación temprana en este ciclo.*",
            "",
            "No se detectaron tickers que cumplan simultáneamente todos los criterios:",
            "tendencia consistente (slope positivo y R² > 0.60), precio por debajo",
            "del 85% del máximo de 52 semanas, volumen creciente, y fundamentos no deteriorados.",
            "",
        ]
    else:
        lines += [f"# Oportunidades ({n})", ""]
        for i, opp in enumerate(opportunities):
            alloc_usd = allocations[i]
            alloc_pct = (alloc_usd / investable * 100) if investable > 0 else 0.0
            slope_daily_pct = opp.slope_normalized * 100

            lines += [
                f"## #{i + 1} — {opp.symbol}  Score: **{opp.score:.1f}**",
                "",
                f"**{opp.name}** | tipo: {opp.asset_type}",
                "",
                "### Indicadores",
                "",
                "| Métrica | Valor |",
                "|---------|-------|",
                f"| Slope diario (normalizado) | **{slope_daily_pct:.4f}%** |",
                f"| R² (consistencia de tendencia) | **{opp.r_squared:.3f}** |",
                f"| Ratio volumen (4w reciente / 4w anterior) | {opp.volume_ratio:.3f}x |",
                f"| Precio vs máximo 52 semanas | {opp.pct_of_52w_high * 100:.1f}% del máximo |",
                f"| Distancia desde mínimo 60d | {opp.pct_above_60d_low * 100:.1f}% |",
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
        "| | |",
        "|---|---|",
        f"| Capital invertible | USD {int(investable):,} |",
        "| Sizing por posición | 8-10% (ponderado por score) |",
        "| Máximo posiciones simultáneas | 5 |",
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

def generate_accumulation_report(
    opportunities: List[AccumulationOpportunity],
    run_date: str = "",
    output_dir: Path = Path("output"),
    total_capital: float = _TOTAL_CAPITAL_USD,
) -> Path:
    """Generate accumulation report and save to output/acumulacion_YYYY-MM-DD.md.

    Returns the path of the saved file.
    """
    if not run_date:
        run_date = str(date.today())

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    md_path = output_dir / f"acumulacion_{run_date}.md"
    content = _build_markdown(opportunities, run_date, total_capital)
    md_path.write_text(content, encoding="utf-8")

    return md_path
