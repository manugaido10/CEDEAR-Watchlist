"""Parse Cocos Capital movimientos_cuenta CSV exports into derived positions.

Pure derivation — no I/O against positions_log.json or any external service.
MEP series is injected so this module remains testable in isolation.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

_TICKER_RE = re.compile(r'\(([^()]+)\)\s*$')

_BUY_TYPES = {"Compra", "Compra Dolar Mep", "Compra Trading"}
_SELL_TYPES = {"Venta", "Venta Dolar Mep", "Venta Trading"}
_POSITION_TYPES = _BUY_TYPES | _SELL_TYPES

_NUMERIC_COLS = ["cantidad", "precio", "montoBruto", "comision", "iva", "otros", "total"]


@dataclass
class DerivedPosition:
    ticker: str
    net_qty: float
    avg_cost_ars: float       # weighted-average cost per share, commissions included
    total_cost_ars: float     # avg_cost_ars * net_qty
    first_buy_date: str       # ISO; earliest buy still contributing to this position
    last_trade_date: str      # ISO; most recent trade for this ticker
    fully_closed: bool        # True when net_qty rounds to zero


@dataclass
class ParseResult:
    open_positions: list[DerivedPosition]
    closed_positions: list[DerivedPosition]
    skipped_usd_no_mep: list[str]   # tickers dropped because MEP was unavailable
    warnings: list[str]


def parse_positions(csv_paths: list[Path], mep_series: pd.Series) -> ParseResult:
    """Derive current positions from one or more Cocos movimientos_cuenta CSVs.

    Args:
        csv_paths:  Paths to Cocos semicolon-separated exports (Argentine locale).
        mep_series: Daily ARS/USD MEP series (DatetimeIndex, forward-filled).
                    Pass MepSeries.data from fetch_mep().

    Returns:
        ParseResult with open/closed positions, skipped tickers, and warnings.
    """
    frames = [
        pd.read_csv(p, sep=";", dtype=str, keep_default_na=False)
        for p in csv_paths
    ]
    df = pd.concat(frames, ignore_index=True)

    # Cocos sometimes overlaps rows across monthly exports.
    df = df.drop_duplicates(subset=["nroTicket", "nroComprobante"])

    # Filter to position-affecting trades BEFORE numeric conversion.
    # Non-trade rows (dividends, credit notes, FCI) routinely have blank numeric
    # cells — converting those first would raise ValueError.
    df["ticker"] = df["instrumento"].apply(_extract_ticker)
    trades = df[
        df["tipoOperacion"].isin(_POSITION_TYPES) & df["ticker"].notna()
    ].copy()

    trades["fechaEjecucion"] = pd.to_datetime(
        trades["fechaEjecucion"], format="%d-%m-%Y"
    )

    # Parse numbers on trade rows only. errors='coerce' turns any unparseable
    # cell into NaN so a single malformed row doesn't abort the whole parse.
    for col in _NUMERIC_COLS:
        trades[col] = pd.to_numeric(
            trades[col]
            .str.replace(".", "", regex=False)
            .str.replace(",", ".", regex=False),
            errors="coerce",
        )

    warnings: list[str] = []
    skipped_usd_no_mep: list[str] = []
    open_positions: list[DerivedPosition] = []
    closed_positions: list[DerivedPosition] = []

    # Drop rows where the columns the math depends on could not be parsed.
    bad_mask = trades[["cantidad", "total"]].isna().any(axis=1)
    for _, bad_row in trades[bad_mask].iterrows():
        warnings.append(
            f"{bad_row['ticker']}: row nroTicket={bad_row['nroTicket']} "
            f"has unparseable numeric data — row dropped"
        )
    trades = trades[~bad_mask].copy()

    for ticker, group in trades.groupby("ticker"):
        group = group.sort_values("fechaEjecucion")

        total_qty = 0.0
        total_cost_ars = 0.0
        last_avg = 0.0
        first_buy_date: Optional[str] = None
        last_trade_date = group["fechaEjecucion"].iloc[-1].strftime("%Y-%m-%d")
        skipped_usd = False

        for _, row in group.iterrows():
            op = row["tipoOperacion"]
            qty = abs(float(row["cantidad"]))
            trade_date: pd.Timestamp = row["fechaEjecucion"]
            trade_date_str = trade_date.strftime("%Y-%m-%d")
            moneda = str(row["moneda"]).strip().upper()
            # abs(total) is the cash actually moved; already bundles commission+IVA+otros.
            cash_moved = abs(float(row["total"]))

            if moneda == "USD":
                rate = _lookup_mep(mep_series, trade_date)
                if rate is None:
                    msg = (
                        f"{ticker}: MEP unavailable for {trade_date_str}; "
                        f"USD cost basis cannot be computed — ticker skipped"
                    )
                    logger.warning(msg)
                    warnings.append(msg)
                    skipped_usd = True
                    skipped_usd_no_mep.append(str(ticker))
                    break
                cash_moved_ars = cash_moved * rate
            else:
                cash_moved_ars = cash_moved

            if op in _BUY_TYPES:
                if qty <= 0:
                    warnings.append(
                        f"{ticker}: buy row nroTicket={row['nroTicket']} "
                        f"has zero/negative quantity — row skipped"
                    )
                    continue
                if first_buy_date is None:
                    first_buy_date = trade_date_str
                total_cost_ars += cash_moved_ars
                total_qty += qty
                if total_qty > 1e-9:
                    last_avg = total_cost_ars / total_qty
            else:  # sell
                if total_qty > 1e-9:
                    last_avg = total_cost_ars / total_qty
                    # Debit only as many shares as we currently hold (rest handled below).
                    shares_to_debit = min(qty, total_qty)
                    total_cost_ars -= last_avg * shares_to_debit
                    total_cost_ars = max(0.0, total_cost_ars)  # guard float drift
                total_qty -= qty

        if skipped_usd:
            continue

        # Net negative means buys predate the CSV window — cost basis is incomplete.
        if total_qty < -1e-9:
            warnings.append(
                f"{ticker}: sells exceed known buys "
                f"(net_qty={total_qty:.4f}); cost basis incomplete — "
                f"likely pre-CSV buys; skipping"
            )
            continue

        fully_closed = abs(total_qty) < 1e-9
        avg_cost = last_avg if fully_closed else (
            total_cost_ars / total_qty if total_qty > 1e-9 else 0.0
        )

        pos = DerivedPosition(
            ticker=str(ticker),
            net_qty=round(total_qty, 6),
            avg_cost_ars=round(avg_cost, 4),
            total_cost_ars=round(avg_cost * max(total_qty, 0.0), 4),
            first_buy_date=first_buy_date or "",
            last_trade_date=last_trade_date,
            fully_closed=fully_closed,
        )

        if fully_closed:
            closed_positions.append(pos)
        else:
            open_positions.append(pos)

    return ParseResult(
        open_positions=open_positions,
        closed_positions=closed_positions,
        skipped_usd_no_mep=sorted(set(skipped_usd_no_mep)),
        warnings=warnings,
    )


def _extract_ticker(instrumento: str) -> Optional[str]:
    m = _TICKER_RE.search(str(instrumento))
    return m.group(1) if m else None


def _lookup_mep(mep_series: pd.Series, trade_date: pd.Timestamp) -> Optional[float]:
    """Return the most recent MEP rate on or before trade_date, or None if unavailable."""
    ts = pd.Timestamp(trade_date)
    try:
        loc = mep_series.index.searchsorted(ts, side="right") - 1
        if loc >= 0:
            return float(mep_series.iloc[loc])
        return None
    except Exception:
        return None
