"""Monthly performance report — Markdown summary of realized and floating PnL."""

from __future__ import annotations

import calendar
import logging
from pathlib import Path
from typing import Optional

import pandas as pd
import yfinance as yf

from analysis.performance.pnl_calculator import (
    compute_floating_pnl,
    compute_merval_return,
    compute_realized_pnl,
)
from data.cache import Cache
from data.ccl import fetch_ccl
from data.positions_log import Position

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_month(month: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    year, mon = (int(x) for x in month.split("-"))
    start = pd.Timestamp(year=year, month=mon, day=1)
    last_day = calendar.monthrange(year, mon)[1]
    end = pd.Timestamp(year=year, month=mon, day=last_day)
    return start, end


def _ccl_at(ccl_series: pd.Series, when: pd.Timestamp) -> Optional[float]:
    """Look up CCL value at a given date in the historical series.

    The series is daily and forward-filled, so a direct lookup works for any
    in-range date. For dates after the series end we fall back to the last value.
    """
    if ccl_series is None or ccl_series.empty:
        return None
    if when in ccl_series.index:
        return float(ccl_series.loc[when])
    # Use the most recent value not after `when`
    sliced = ccl_series.loc[:when]
    if not sliced.empty:
        return float(sliced.iloc[-1])
    return float(ccl_series.iloc[0])


def _last_trading_day_close(symbol: str, year_month: str) -> Optional[tuple[float, str]]:
    """Closing price on the last trading day ≤ month-end calendar date.

    Returns (close_price, iso_date) or None when yfinance has no usable data.
    """
    try:
        start, end = _parse_month(year_month)
        # Fetch a window that comfortably covers the whole month
        df = yf.download(
            symbol,
            start=start,
            end=end + pd.Timedelta(days=1),
            progress=False,
            auto_adjust=False,
        )
        if df is None or df.empty or "Close" not in df.columns:
            return None
        closes = df["Close"].dropna()
        closes = closes[closes.index <= end]
        if closes.empty:
            return None
        last_dt = closes.index[-1]
        return float(closes.iloc[-1]), last_dt.date().isoformat()
    except Exception as exc:
        logger.warning("last trading day fetch failed for %s %s: %s", symbol, year_month, exc)
        return None


def _ticker_period_return(symbol: str, open_date: str, close_date: str) -> Optional[float]:
    try:
        start = pd.Timestamp(open_date)
        end = pd.Timestamp(close_date) + pd.Timedelta(days=1)
        df = yf.download(symbol, start=start, end=end, progress=False, auto_adjust=False)
        if df is None or df.empty or "Close" not in df.columns:
            return None
        closes = df["Close"].dropna()
        if len(closes) < 2:
            return None
        return (float(closes.iloc[-1]) / float(closes.iloc[0]) - 1.0) * 100.0
    except Exception as exc:
        logger.warning("ticker return fetch failed for %s: %s", symbol, exc)
        return None


# ── Formatters ────────────────────────────────────────────────────────────────

def _ars(v: float) -> str:
    return f"{int(round(v)):,}".replace(",", ".")


def _usd(v: float) -> str:
    return f"{v:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _pct(v: Optional[float]) -> str:
    if v is None:
        return "—"
    return f"{v:+.2f}%"


# ── Builder ───────────────────────────────────────────────────────────────────

def _filter_closed_in_month(positions: list[Position], start: pd.Timestamp, end: pd.Timestamp) -> list[Position]:
    out = []
    for p in positions:
        if p.status != "closed" or not p.close_date:
            continue
        d = pd.Timestamp(p.close_date)
        if start <= d <= end:
            out.append(p)
    return out


def _filter_open_at_month_end(positions: list[Position], end: pd.Timestamp) -> list[Position]:
    out = []
    for p in positions:
        if p.status != "open":
            # closed-in-future-of-end positions were open at month end
            if p.close_date and pd.Timestamp(p.close_date) > end and pd.Timestamp(p.open_date) <= end:
                out.append(p)
            continue
        if pd.Timestamp(p.open_date) <= end:
            out.append(p)
    return out


def _build_realized_section(closed: list[Position], ccl_series: pd.Series) -> tuple[list[str], dict]:
    lines = ["## Resultados Realizados", ""]
    if not closed:
        lines += ["_Sin posiciones cerradas en el período._", ""]
        return lines, {"momentum": [], "reversal": []}

    lines += [
        "| Symbol | Source | Apertura | Cierre | Precio apertura ARS | Precio cierre ARS | PnL ARS | PnL USD | PnL % | Merval % | Alpha % |",
        "|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]

    per_source: dict = {"momentum": [], "reversal": []}

    for p in closed:
        ccl_close = _ccl_at(ccl_series, pd.Timestamp(p.close_date)) or 0.0
        realized = compute_realized_pnl(p, ccl_close)
        merval_ret = compute_merval_return(p.open_date, p.close_date)
        alpha = (realized["pnl_pct"] - merval_ret) if merval_ret is not None else None

        lines.append(
            f"| {p.symbol} | {p.source} | {p.open_date} | {p.close_date} "
            f"| {_ars(p.open_price_ars)} | {_ars(p.close_price_ars)} "
            f"| {_ars(realized['pnl_ars'])} | {_usd(realized['pnl_usd'])} "
            f"| {_pct(realized['pnl_pct'])} | {_pct(merval_ret)} | {_pct(alpha)} |"
        )
        per_source.setdefault(p.source, []).append(realized)

    lines.append("")
    return lines, per_source


def _build_aggregates(per_source: dict) -> list[str]:
    lines = ["### Totales por source", ""]
    lines += ["| Source | Trades | Aciertos | % Aciertos | PnL ARS | PnL USD |",
              "|---|---:|---:|---:|---:|---:|"]

    grand_ars = 0.0
    grand_usd = 0.0
    grand_n = 0
    grand_wins = 0

    for source in ("momentum", "reversal"):
        results = per_source.get(source, [])
        n = len(results)
        wins = sum(1 for r in results if r["pnl_ars"] > 0)
        total_ars = sum(r["pnl_ars"] for r in results)
        total_usd = sum(r["pnl_usd"] for r in results)
        hit = (wins / n * 100.0) if n else 0.0
        lines.append(
            f"| {source} | {n} | {wins} | {hit:.1f}% | {_ars(total_ars) if n else '—'} | {_usd(total_usd) if n else '—'} |"
        )
        grand_ars += total_ars
        grand_usd += total_usd
        grand_n += n
        grand_wins += wins

    overall_hit = (grand_wins / grand_n * 100.0) if grand_n else 0.0
    lines.append(
        f"| **Total** | **{grand_n}** | **{grand_wins}** | **{overall_hit:.1f}%** "
        f"| **{_ars(grand_ars) if grand_n else '—'}** | **{_usd(grand_usd) if grand_n else '—'}** |"
    )
    lines.append("")
    return lines


def _build_floating_section(open_positions: list[Position], ccl_at_end: float, year_month: str) -> list[str]:
    lines = ["## Posiciones Abiertas — No Realizado", ""]
    if not open_positions:
        lines += ["_Sin posiciones abiertas al cierre del período._", ""]
        return lines

    lines += [
        "_Precio: cierre del último día hábil del mes exacto (vía yfinance). Resultado **no realizado**._",
        "",
        "| Symbol | Source | Apertura | Precio apertura ARS | Precio cierre mes ARS | Fecha precio | PnL ARS (flot.) | PnL USD (flot.) | PnL % (flot.) |",
        "|---|---|---|---:|---:|---|---:|---:|---:|",
    ]

    for p in open_positions:
        snap = _last_trading_day_close(p.symbol, year_month)
        if snap is None:
            lines.append(
                f"| {p.symbol} | {p.source} | {p.open_date} | {_ars(p.open_price_ars)} | — | — | — | — | — |"
            )
            continue
        last_close, last_date = snap
        floating = compute_floating_pnl(p, last_close, ccl_at_end)
        lines.append(
            f"| {p.symbol} | {p.source} | {p.open_date} | {_ars(p.open_price_ars)} "
            f"| {_ars(last_close)} | {last_date} "
            f"| {_ars(floating['pnl_ars'])} | {_usd(floating['pnl_usd'])} | {_pct(floating['pnl_pct'])} |"
        )

    lines.append("")
    return lines


def generate_performance_report(
    month: str,
    positions: list[Position],
    output_dir: Path = Path("output"),
) -> Path:
    start, end = _parse_month(month)
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / f"performance_{month}.md"

    closed = _filter_closed_in_month(positions, start, end)
    open_at_end = _filter_open_at_month_end(positions, end)

    ccl_obj = fetch_ccl(Cache())
    ccl_series = ccl_obj.data if ccl_obj else pd.Series(dtype=float)
    ccl_at_end = _ccl_at(ccl_series, end) or (ccl_obj.spot if ccl_obj else 0.0)

    lines: list[str] = [
        f"# Performance — {month}",
        "",
        f"Período: {start.date()} a {end.date()}",
        f"Posiciones cerradas en el mes: **{len(closed)}**",
        f"Posiciones abiertas al cierre del mes: **{len(open_at_end)}**",
        f"CCL al cierre del mes (referencia): {_ars(ccl_at_end)} ARS/USD" if ccl_at_end else "",
        "",
    ]

    if not closed and not open_at_end:
        lines += [
            "_Sin actividad en el período. Nada para reportar._",
            "",
        ]
        report_path.write_text("\n".join(lines), encoding="utf-8")
        return report_path

    realized_lines, per_source = _build_realized_section(closed, ccl_series)
    lines += realized_lines
    if closed:
        lines += _build_aggregates(per_source)
    lines += _build_floating_section(open_at_end, ccl_at_end, month)

    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path
