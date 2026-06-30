"""CLI for the manual position tracking module.

Usage
-----
  python scripts/log_position.py open --symbol GE.BA --price 38500 --qty 10 \\
      --source momentum --score 75.0 --invalidation 60300 --date 2026-06-29
  python scripts/log_position.py close --symbol GE.BA --price 41200 \\
      --date 2026-07-15 --reason target
  python scripts/log_position.py list --status open
  python scripts/log_position.py report --month 2026-07
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from data.positions_log import (  # noqa: E402
    VALID_SOURCES,
    VALID_REASONS,
    VALID_STATUSES,
    close_position,
    load_positions,
    open_position,
)


def _fmt_ars(v: float) -> str:
    return f"{int(round(v)):,}".replace(",", ".")


def _cmd_open(args: argparse.Namespace) -> int:
    position = open_position(
        symbol=args.symbol,
        price=args.price,
        qty=args.qty,
        source=args.source,
        score=args.score,
        invalidation=args.invalidation,
        date=args.date,
    )
    print(
        f"✅ Posición abierta: {position.symbol} @ {_fmt_ars(position.open_price_ars)} ARS "
        f"x{position.qty:g} ({position.source}, score={position.score_at_entry:.1f}, "
        f"invalidación={_fmt_ars(position.invalidation_at_entry_ars)} ARS, fecha={position.open_date})"
    )
    return 0


def _cmd_close(args: argparse.Namespace) -> int:
    position = close_position(
        symbol=args.symbol,
        price=args.price,
        date=args.date,
        reason=args.reason,
    )
    pnl_pct = (position.close_price_ars / position.open_price_ars - 1.0) * 100.0
    print(
        f"✅ Posición cerrada: {position.symbol} @ {_fmt_ars(position.close_price_ars)} ARS "
        f"(razón={position.close_reason}, fecha={position.close_date}, PnL={pnl_pct:+.2f}%)"
    )
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    positions = load_positions()
    if args.status:
        positions = [p for p in positions if p.status == args.status]
    if not positions:
        print(f"(sin posiciones{' con status=' + args.status if args.status else ''})")
        return 0

    for p in positions:
        if p.status == "open":
            print(
                f"[OPEN]   {p.symbol}  {p.source:<8}  open={p.open_date}  "
                f"entry={_fmt_ars(p.open_price_ars)} ARS  qty={p.qty:g}  "
                f"score={p.score_at_entry:.1f}  inv={_fmt_ars(p.invalidation_at_entry_ars)}"
            )
        else:
            pnl_pct = (p.close_price_ars / p.open_price_ars - 1.0) * 100.0
            print(
                f"[CLOSED] {p.symbol}  {p.source:<8}  {p.open_date} → {p.close_date}  "
                f"{_fmt_ars(p.open_price_ars)} → {_fmt_ars(p.close_price_ars)}  "
                f"PnL={pnl_pct:+.2f}%  reason={p.close_reason}"
            )
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    from output.performance_report import generate_performance_report

    positions = load_positions()
    path = generate_performance_report(args.month, positions)
    print(f"✅ Reporte generado: {path}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manual position tracking CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_open = sub.add_parser("open", help="Register an opened position")
    p_open.add_argument("--symbol", required=True)
    p_open.add_argument("--price", required=True, type=float, help="Entry price in ARS")
    p_open.add_argument("--qty", required=True, type=float)
    p_open.add_argument("--source", required=True, choices=VALID_SOURCES)
    p_open.add_argument("--score", required=True, type=float, help="System score at entry")
    p_open.add_argument("--invalidation", required=True, type=float, help="Invalidation level in ARS")
    p_open.add_argument("--date", required=True, help="Open date (YYYY-MM-DD)")
    p_open.set_defaults(func=_cmd_open)

    p_close = sub.add_parser("close", help="Close an open position")
    p_close.add_argument("--symbol", required=True)
    p_close.add_argument("--price", required=True, type=float, help="Exit price in ARS")
    p_close.add_argument("--date", required=True, help="Close date (YYYY-MM-DD)")
    p_close.add_argument("--reason", required=True, choices=VALID_REASONS)
    p_close.set_defaults(func=_cmd_close)

    p_list = sub.add_parser("list", help="List positions")
    p_list.add_argument("--status", choices=VALID_STATUSES, default=None)
    p_list.set_defaults(func=_cmd_list)

    p_report = sub.add_parser("report", help="Generate monthly performance report")
    p_report.add_argument("--month", required=True, help="Report month (YYYY-MM)")
    p_report.set_defaults(func=_cmd_report)

    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    try:
        return args.func(args)
    except ValueError as exc:
        print(f"❌ Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
