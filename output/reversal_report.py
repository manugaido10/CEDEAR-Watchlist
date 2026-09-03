"""Reversal report — Markdown file from a list of ReversalOpportunity.

Capital is treated ARS-native (project convention): the report allocates
against the caller-supplied ``total_capital_ars`` and displays USD via MEP
as a convenience only. There is no cash-tracking module — free capital is
approximated as ``total_capital_ars - Σ open positions (qty × open_price)``.

Scale-ins are allocated up to the per-ticker headroom under the 8% cap
(reusing :func:`analysis.reversal.suppression.per_ticker_headroom_ars` so
the math lives in a single place). New positions keep the historical
score-weighted [5%, 8%] band. When proposed allocations exceed the free
capital estimate, every allocation scales down proportionally.
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Iterable, List, Optional

from analysis.reversal.reversal_scanner import ReversalOpportunity
from analysis.reversal.suppression import (
    PER_TICKER_CAP_PCT,
    per_ticker_headroom_ars,
)
from data.positions_log import Position

logger = logging.getLogger(__name__)

_MIN_POSITION_PCT = 0.05
_MAX_POSITION_PCT = PER_TICKER_CAP_PCT  # 0.08 — single source of truth


# ── MEP conversion (best-effort) ──────────────────────────────────────────────

def _fetch_mep_spot() -> Optional[float]:
    """Return the current MEP spot, or None when unavailable.

    Failure is silent by design: the report is still useful without USD
    equivalents, and the caller (run_reversals) should never crash because
    a currency lookup missed.
    """
    try:
        from data.cache import Cache
        from data.mep import fetch_mep
        mep = fetch_mep(Cache())
        return float(mep.spot) if mep is not None else None
    except Exception as exc:
        logger.warning("reversal_report: MEP fetch failed — %s", exc)
        return None


# ── Capital math ──────────────────────────────────────────────────────────────

def _total_committed_ars(positions: Iterable[Position]) -> float:
    """Sum qty × open_price_ars over ALL open positions in the log."""
    total = 0.0
    for pos in positions:
        if getattr(pos, "status", None) != "open":
            continue
        qty = float(getattr(pos, "qty", 0.0) or 0.0)
        price = float(getattr(pos, "open_price_ars", 0.0) or 0.0)
        total += qty * price
    return total


def _allocate_capital(
    opportunities: List[ReversalOpportunity],
    total_capital_ars: float,
    capital_disponible_ars: float,
    positions: List[Position],
) -> List[float]:
    """Return an allocation in ARS for each opportunity (same order).

    Rules:
      - Non-tradeable → 0.
      - New (tradeable, not scale-in): score-weighted portion of
        ``total_capital_ars``, clipped to [5%, 8%].
      - Scale-in: base amount = score-weighted portion in the same band,
        then clipped down to the ticker's remaining 8% headroom.
      - If Σ proposed > capital_disponible_ars, scale ALL proposed values
        down proportionally.
      - If capital_disponible_ars <= 0, every allocation is 0.
    """
    n = len(opportunities)
    if n == 0:
        return []
    if capital_disponible_ars <= 0 or total_capital_ars <= 0:
        return [0.0] * n

    min_ars = total_capital_ars * _MIN_POSITION_PCT
    max_ars = total_capital_ars * _MAX_POSITION_PCT

    tradeable_idx = [i for i, o in enumerate(opportunities) if getattr(o, "tradeable", True)]
    total_score = sum(opportunities[i].score for i in tradeable_idx)

    proposed: List[float] = [0.0] * n
    for i in tradeable_idx:
        opp = opportunities[i]
        if total_score < 1e-10:
            weight = 1.0 / len(tradeable_idx)
        else:
            weight = opp.score / total_score
        base = max(min_ars, min(max_ars, weight * total_capital_ars))

        if bool(getattr(opp, "is_scale_in", False)):
            headroom = per_ticker_headroom_ars(
                opp.symbol, positions, total_capital_ars,
            )
            base = min(base, headroom)
        proposed[i] = base

    total_proposed = sum(proposed)
    if total_proposed > capital_disponible_ars and total_proposed > 0:
        scale = capital_disponible_ars / total_proposed
        proposed = [v * scale for v in proposed]

    return proposed


# ── Formatters ────────────────────────────────────────────────────────────────

def _ars(v: float) -> str:
    return f"{int(round(v)):,}".replace(",", ".")


def _pct(v: float) -> str:
    return f"{v:.1f}%"


def _usd_equiv(ars: float, mep_spot: Optional[float]) -> str:
    if mep_spot is None or mep_spot <= 0:
        return ""
    usd = ars / mep_spot
    return f" (~USD {usd:,.0f})".replace(",", ".")


# ── Markdown builder ──────────────────────────────────────────────────────────

def _build_markdown(
    opportunities: List[ReversalOpportunity],
    positions: List[Position],
    total_capital_ars: float,
    run_date: str,
    mep_spot: Optional[float],
) -> str:
    n = len(opportunities)
    committed_total_ars = _total_committed_ars(positions)
    capital_disponible_ars = total_capital_ars - committed_total_ars
    allocations = _allocate_capital(
        opportunities, total_capital_ars, capital_disponible_ars, positions,
    )

    mep_line = (
        # Argentine locale: '.' thousands, ',' decimals — swap via a placeholder.
        f"MEP referencia: {mep_spot:,.2f} ARS/USD"
        .replace(",", "X").replace(".", ",").replace("X", ".")
        if mep_spot else "MEP referencia: no disponible"
    )
    header_capital = (
        f"Capital total: ARS {_ars(total_capital_ars)}"
        f"{_usd_equiv(total_capital_ars, mep_spot)}"
    )
    header_committed = (
        f"Capital comprometido (posiciones abiertas): ARS {_ars(committed_total_ars)}"
        f"{_usd_equiv(committed_total_ars, mep_spot)}"
    )
    disp_display_ars = max(0.0, capital_disponible_ars)
    header_disponible = (
        f"Capital disponible aproximado: ARS {_ars(disp_display_ars)}"
        f"{_usd_equiv(disp_display_ars, mep_spot)}"
    )

    lines: List[str] = [
        f"# Reversiones Tácticas — {run_date}",
        "",
        f"Análisis: {run_date}  |  Oportunidades: {n}",
        "",
        header_capital,
        "",
        header_committed,
        "",
        header_disponible,
        "",
        mep_line,
        "",
    ]

    if capital_disponible_ars <= 0:
        lines += [
            "> ⚠ **Sin capital disponible — cartera ya comprometida al 100% o más.** "
            "Todas las asignaciones sugeridas quedan en 0. Cerrar posiciones o "
            "actualizar `--capital-ars` para operar nuevas señales.",
            "",
        ]

    lines += ["---", ""]

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
            alloc_ars = allocations[i]
            alloc_pct = (
                alloc_ars / total_capital_ars * 100.0
                if total_capital_ars > 0 else 0.0
            )

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
                open_price = float(getattr(existing_position, "open_price_ars", 0.0) or 0.0)
                qty = float(getattr(existing_position, "qty", 0.0) or 0.0)
                headroom_ars = per_ticker_headroom_ars(
                    opp.symbol, positions, total_capital_ars,
                )
                lines += [
                    "### Suma a posición existente",
                    "",
                    f"- Costo previo: **{_ars(open_price)} ARS** "
                    f"(qty {qty:g}, "
                    f"comprometido {_ars(qty * open_price)} ARS)",
                    f"- Headroom disponible (cap 8% por ticker): "
                    f"**{_ars(headroom_ars)} ARS**{_usd_equiv(headroom_ars, mep_spot)}",
                    f"- Suma sugerida: **{_ars(alloc_ars)} ARS**"
                    f"{_usd_equiv(alloc_ars, mep_spot)} "
                    f"({_pct(alloc_pct)} del capital total)",
                    "",
                ]
            else:
                lines += [
                    "### Capital Sugerido",
                    "",
                    f"**{_ars(alloc_ars)} ARS**{_usd_equiv(alloc_ars, mep_spot)} "
                    f"({_pct(alloc_pct)} del capital total)",
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
        f"| Capital total | ARS {_ars(total_capital_ars)} |",
        f"| Capital comprometido | ARS {_ars(committed_total_ars)} |",
        f"| Capital disponible | ARS {_ars(disp_display_ars)} |",
        f"| Sizing por posición nueva | 5-8% (ponderado por score) |",
        f"| Sizing por suma | hasta headroom del 8% por ticker |",
        f"| Máximo posiciones | 5 |",
        "",
    ]

    if opportunities:
        lines += [
            "| Rank | Ticker | Tipo | ARS | % capital total |",
            "|------|--------|------|-----|-----------------|",
        ]
        for i, opp in enumerate(opportunities):
            alloc_ars = allocations[i]
            alloc_pct = (
                alloc_ars / total_capital_ars * 100.0
                if total_capital_ars > 0 else 0.0
            )
            if not getattr(opp, "tradeable", True):
                tipo, ticker_label = "🚫 no operar", f"🚫 {opp.symbol}"
            elif bool(getattr(opp, "is_scale_in", False)):
                tipo, ticker_label = "➕ suma", f"➕ {opp.symbol}"
            else:
                tipo, ticker_label = "nueva", opp.symbol
            lines.append(
                f"| #{i + 1} | {ticker_label} | {tipo} | "
                f"{_ars(alloc_ars)} | {_pct(alloc_pct)} |"
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
    total_capital_ars: float,
    positions: List[Position],
    run_date: str = "",
    output_dir: Path = Path("output"),
    mep_spot: Optional[float] = None,
) -> Path:
    """Generate reversal report and save to output/reversiones_YYYY-MM-DD.md.

    ``total_capital_ars`` and ``positions`` are required — capital allocation
    is ARS-native and positions-aware. ``mep_spot`` is fetched via
    :func:`data.mep.fetch_mep` when not supplied; failure is silent (USD
    columns become blank).

    Returns the path of the saved file.
    """
    if not run_date:
        run_date = str(date.today())

    if mep_spot is None:
        mep_spot = _fetch_mep_spot()

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    md_path = output_dir / f"reversiones_{run_date}.md"
    content = _build_markdown(
        opportunities, positions, total_capital_ars, run_date, mep_spot,
    )
    md_path.write_text(content, encoding="utf-8")
    return md_path
