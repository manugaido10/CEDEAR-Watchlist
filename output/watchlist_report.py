"""Watchlist report — console summary + Markdown file from a Filter2Report."""

from __future__ import annotations

from pathlib import Path
from typing import List

from analysis.filter2_deep_dive.filter2_models import Filter2Opportunity, Filter2Report
from analysis.filter2_deep_dive.filter2_thresholds import CASH_RESERVE_SCHEDULE, TOTAL_CAPITAL_USD

_W = "═" * 58
_T = "─" * 58


# ── Number formatters ──────────────────────────────────────────────────────────

def _ars(v: float) -> str:
    """Format ARS price with Argentine thousands separator (dot)."""
    return f"{int(round(v)):,}".replace(",", ".")


def _usd_k(v: float) -> str:
    """Format USD integer amount with Argentine thousands separator."""
    return f"{int(round(v)):,}".replace(",", ".")


def _pct(v: float) -> str:
    return f"{v:.1f}%"


# ── Capital helpers ────────────────────────────────────────────────────────────

def _reserve_pct(n: int) -> float:
    for max_n in sorted(CASH_RESERVE_SCHEDULE.keys()):
        if n <= max_n:
            return CASH_RESERVE_SCHEDULE[max_n]
    return CASH_RESERVE_SCHEDULE[max(CASH_RESERVE_SCHEDULE.keys())]


# ── Argentina formatters ───────────────────────────────────────────────────────

def _argentina_oneliner(opp: Filter2Opportunity) -> str:
    bd = opp.argentina_breakdown
    parts: List[str] = []

    ccl_info = bd.get("ccl_vol") or {}
    ccl_ratio = ccl_info.get("ccl_vol_ratio")
    if ccl_ratio is not None:
        if ccl_ratio < 0.015:
            parts.append("CCL estable")
        elif ccl_ratio < 0.03:
            parts.append(f"CCL vol moderada ({ccl_ratio:.2%})")
        else:
            parts.append(f"CCL vol alta ({ccl_ratio:.2%})")
    else:
        note = ccl_info.get("note", "")
        if note:
            parts.append(f"CCL: {note}")

    prem_info = bd.get("premium") or {}
    prem_pct = prem_info.get("premium_pct")
    if prem_pct is not None:
        parts.append(f"premium {prem_pct:+.1f}%")

    if bd.get("a3_flag"):
        parts.append(f"A3: {bd.get('a3_reason', 'flag activo')}")

    if opp.argentina_penalty > 0:
        parts.append(f"-{opp.argentina_penalty:.0f}pts")
    elif not parts:
        parts.append("sin ajuste")

    return ", ".join(parts)


def _argentina_detail_md(opp: Filter2Opportunity) -> str:
    bd = opp.argentina_breakdown
    asset_type = bd.get("asset_type", "cedear")
    lines = [f"Penalización total: **{opp.argentina_penalty:.1f}pts**"]

    ccl_info = bd.get("ccl_vol") or {}
    ccl_ratio = ccl_info.get("ccl_vol_ratio")
    ccl_note = ccl_info.get("note", "")
    if ccl_ratio is not None:
        lines.append(
            f"- CCL vol 30d: {ccl_ratio:.2%}"
            f" (media {ccl_info.get('ccl_mean', '?')} ARS, σ {ccl_info.get('ccl_std', '?')} ARS)"
        )
    elif ccl_note:
        lines.append(f"- CCL vol: {ccl_note}")

    if asset_type == "cedear":
        prem_info = bd.get("premium") or {}
        prem_pct = prem_info.get("premium_pct")
        prem_note = prem_info.get("note", "")
        if prem_pct is not None:
            lines.append(
                f"- Premium CEDEAR/subyacente: **{prem_pct:+.1f}%**"
                f" (ARS {prem_info.get('actual_ars', '?')}"
                f" vs implícito {prem_info.get('implied_ars', '?')}"
                f" @ CCL {prem_info.get('ccl_spot', '?')})"
            )
        elif prem_note:
            lines.append(f"- Premium: {prem_note}")
    else:
        if bd.get("a3_flag"):
            lines.append(f"- **A3 flag activo:** {bd.get('a3_reason', '')}")
        else:
            lines.append("- Sin flag A3")

    return "\n".join(lines)


# ── Console format ─────────────────────────────────────────────────────────────

def _opp_console_block(opp: Filter2Opportunity) -> str:
    tb = opp.technical_breakdown
    label = tb.trend_regime_label.value if tb else "?"

    lines = [
        f"#{opp.rank}  {opp.symbol}  [{label}]  Score: {opp.final_score:.1f}",
        f"   Técnico:     {opp.technical_signal_summary}",
        f"   Fundamental: {opp.fundamental_state} — {opp.fundamental_summary}",
    ]

    if opp.sentiment_gate not in ("none", ""):
        lines.append(f"   Sentimiento: {opp.sentiment_summary or opp.sentiment_gate}")

    lines.append(f"   Argentina:   {_argentina_oneliner(opp)}")
    lines.append(
        f"   Invalidación: {_ars(opp.invalidation_level_ars)} ARS"
        f"  (~{opp.invalidation_level_usd:.2f} USD)"
    )
    lines.append(
        f"   Capital sugerido: USD {_usd_k(opp.proposed_capital_usd)}"
        f" ({_pct(opp.proposed_capital_pct)} del capital invertible)"
    )

    if opp.status == "held_with_warning":
        lines.append("   ⚠  held_with_warning")
    for w in opp.warnings:
        lines.append(f"   ⚠  {w}")

    return "\n".join(lines)


def _build_console_report(report: Filter2Report, total_capital: float) -> str:
    n = len(report.opportunities)
    reserve_pct = _reserve_pct(n)
    reserve_usd = total_capital * reserve_pct
    investable_usd = total_capital * (1.0 - reserve_pct)

    lines: List[str] = [
        "",
        f"CEDEAR WATCHLIST — {report.run_date}",
        "",
        _W,
        "",
        f"RANKING DE OPORTUNIDADES ({n} posiciones)",
        "",
        _T,
    ]

    if report.opportunities:
        for opp in report.opportunities:
            lines.append("")
            lines.append(_opp_console_block(opp))
    else:
        lines += ["", "   Sin oportunidades en este ciclo."]

    lines += ["", _T]

    if report.discarded_by_sentiment:
        syms = ", ".join(o.symbol for o in report.discarded_by_sentiment)
        lines += ["", f"DESCARTADOS POR SENTIMIENTO: {syms}"]

    if report.unevaluable_symbols:
        syms = ", ".join(report.unevaluable_symbols)
        lines += [
            "",
            f"UNEVALUABLES: {report.total_unevaluable} tickers sin datos suficientes",
            f"   ({syms})",
        ]

    lines += [
        "",
        _T,
        "",
        "DISTRIBUCIÓN DE CAPITAL",
        "",
        f"   Capital total:        USD {_usd_k(total_capital)}",
        f"   Reserva de cash:      USD {_usd_k(reserve_usd)} ({reserve_pct:.0%})",
        f"   Capital invertible:   USD {_usd_k(investable_usd)}",
        f"   Posiciones:           {n}",
        "",
    ]

    for opp in report.opportunities:
        lines.append(
            f"   #{opp.rank}  {opp.symbol:<14}"
            f"USD {_usd_k(opp.proposed_capital_usd):>8}"
            f"  {_pct(opp.proposed_capital_pct)}"
        )

    lines += ["", _W, ""]
    return "\n".join(lines)


# ── Markdown format ────────────────────────────────────────────────────────────

def _opp_md_section(opp: Filter2Opportunity) -> str:
    tb = opp.technical_breakdown
    label = tb.trend_regime_label.value if tb else "?"

    lines = [
        f"## #{opp.rank} — {opp.symbol}  `[{label}]`  Score: **{opp.final_score:.1f}**",
        "",
        f"**{opp.name}** | tipo: {opp.asset_type} | estado: `{opp.status}`",
        "",
        "### Técnico",
        "",
        opp.technical_signal_summary,
        "",
    ]

    if tb:
        breakout_detail = (
            f" (bar {tb.breakout_detail.bar_date}, vol ×{tb.breakout_detail.volume_ratio:.1f})"
            if tb.breakout_detail.triggered
            else " (no detectado)"
        )
        weekly_cap = " ⚠ cap semanal aplicado" if tb.trend_breakdown.weekly_cap_applied else ""
        lines += [
            f"| Componente | Valor |",
            f"|---|---|",
            f"| Score técnico | {tb.technical_score:.1f} / 100 |",
            f"| Trend regime | {tb.trend_regime:.1f} / 50 ({label}) |",
            f"| → semanal | {tb.trend_breakdown.weekly_strength:.1f} / 20{weekly_cap} |",
            f"| → diario | {tb.trend_breakdown.daily_strength:.1f} / 20 |",
            f"| → alineación MAs | {tb.trend_breakdown.ma_alignment:.1f} / 10 |",
            f"| Breakout bonus | {tb.breakout_bonus:.1f} / 15{breakout_detail} |",
            f"| Fuerza relativa | {tb.relative_strength_score:.1f} (RS {tb.rs_value:.3f} vs {tb.benchmark_used}) |",
            f"| RSI ({tb.rsi_value:.0f}) | {tb.rsi_state.value} → penalización {tb.rsi_penalty:.1f} |",
        ]
        if tb.warnings:
            lines.append("")
            for w in tb.warnings:
                lines.append(f"- ⚠ {w}")

    lines += [
        "",
        "### Fundamentals",
        "",
        f"**Estado:** `{opp.fundamental_state}`  |  Penalización: {opp.fundamental_penalty:.1f}pts",
        "",
        opp.fundamental_summary,
    ]

    if opp.sentiment_gate not in ("none", ""):
        lines += [
            "",
            "### Sentimiento (tiebreaker activado)",
            "",
            f"**Veredicto:** `{opp.sentiment_gate}`",
        ]
        if opp.sentiment_summary:
            lines += ["", opp.sentiment_summary]
        if opp.sentiment_evidence:
            lines.append("")
            for url in opp.sentiment_evidence:
                lines.append(f"- {url}")

    lines += [
        "",
        "### Ajuste Argentina",
        "",
        _argentina_detail_md(opp),
        "",
        "### Nivel de Invalidación",
        "",
        f"**{_ars(opp.invalidation_level_ars)} ARS**  (~{opp.invalidation_level_usd:.2f} USD)",
        "",
        opp.invalidation_rationale,
        "",
        "### Capital Sugerido",
        "",
        f"**USD {_usd_k(opp.proposed_capital_usd)}** ({_pct(opp.proposed_capital_pct)} del capital invertible)",
        "",
        opp.capital_rationale,
    ]

    if opp.warnings:
        lines += ["", "### Advertencias", ""]
        for w in opp.warnings:
            lines.append(f"- ⚠ {w}")

    lines += ["", "---", ""]
    return "\n".join(lines)


def _build_markdown_report(report: Filter2Report, total_capital: float) -> str:
    n = len(report.opportunities)
    reserve_pct = _reserve_pct(n)
    reserve_usd = total_capital * reserve_pct
    investable_usd = total_capital * (1.0 - reserve_pct)

    lines: List[str] = [
        f"# CEDEAR WATCHLIST — {report.run_date}",
        "",
        (
            f"Análisis: {report.run_date}  |  "
            f"Posiciones: {n}  |  "
            f"Sobrevivientes F1 evaluados: {report.total_survivors_input}"
        ),
        "",
        "---",
        "",
    ]

    if report.opportunities:
        lines += [f"# Ranking de Oportunidades ({n} posiciones)", ""]
        for opp in report.opportunities:
            lines.append(_opp_md_section(opp))
    else:
        lines += ["*Sin oportunidades en este ciclo.*", ""]

    if report.discarded_by_sentiment:
        lines += ["## Descartados por Sentimiento", ""]
        for opp in report.discarded_by_sentiment:
            lines.append(
                f"- **{opp.symbol}** ({opp.name}) — "
                f"Score técnico: {opp.technical_score:.1f}  |  {opp.sentiment_summary}"
            )
        lines.append("")

    if report.unevaluable_symbols:
        lines += [
            "## Unevaluables",
            "",
            f"{report.total_unevaluable} tickers sin datos suficientes:",
            "",
        ]
        for sym in report.unevaluable_symbols:
            lines.append(f"- {sym}")
        lines.append("")

    lines += [
        "---",
        "",
        "## Distribución de Capital",
        "",
        "| | |",
        "|---|---|",
        f"| Capital total | USD {_usd_k(total_capital)} |",
        f"| Reserva de cash | USD {_usd_k(reserve_usd)} ({reserve_pct:.0%}) |",
        f"| Capital invertible | USD {_usd_k(investable_usd)} |",
        f"| Posiciones | {n} |",
        "",
        "| Rank | Ticker | USD | % invertible |",
        "|------|--------|-----|-------------|",
    ]
    for opp in report.opportunities:
        lines.append(
            f"| #{opp.rank} | {opp.symbol} | {_usd_k(opp.proposed_capital_usd)} | {_pct(opp.proposed_capital_pct)} |"
        )

    lines += [
        "",
        "---",
        "",
        "## Alertas — Niveles de Invalidación",
        "",
        "Referencia rápida para monitoreo intraweek.",
        "",
        "| Ticker | Nivel ARS | Nivel USD | Rationale |",
        "|--------|-----------|-----------|-----------|",
    ]
    for opp in report.opportunities:
        short_rationale = opp.invalidation_rationale[:80].replace("|", "/")
        lines.append(
            f"| {opp.symbol}"
            f" | {_ars(opp.invalidation_level_ars)} ARS"
            f" | ~{opp.invalidation_level_usd:.2f} USD"
            f" | {short_rationale} |"
        )

    if report.warnings:
        lines += ["", "---", "", "## Avisos Globales", ""]
        for w in report.warnings:
            lines.append(f"- {w}")

    lines.append("")
    return "\n".join(lines)


# ── Main entry point ───────────────────────────────────────────────────────────

def generate_report(
    report: Filter2Report,
    output_dir: Path = Path("output"),
    print_to_console: bool = True,
    save_markdown: bool = True,
    total_capital: float = TOTAL_CAPITAL_USD,
) -> Path:
    """Generate watchlist report from a Filter2Report.

    Prints a console summary and saves a detailed Markdown file.
    Returns the path of the .md file (regardless of save_markdown).
    """
    output_dir = Path(output_dir)
    md_path = output_dir / f"watchlist_{report.run_date}.md"

    console_text = _build_console_report(report, total_capital)
    if print_to_console:
        print(console_text)

    if save_markdown:
        output_dir.mkdir(parents=True, exist_ok=True)
        md_path.write_text(_build_markdown_report(report, total_capital), encoding="utf-8")

    return md_path
