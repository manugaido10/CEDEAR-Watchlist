"""Reconcile Cocos Capital CSV exports against positions_log and present the report.

Usage:
    python scripts/reconcile_positions.py             # dry-run (default)
    python scripts/reconcile_positions.py --dry-run   # explicit dry-run
    python scripts/reconcile_positions.py --apply     # show report, prompt to apply
    python scripts/reconcile_positions.py --verbose   # include matched position details

Dry-run (default) prints the full reconciliation report without writing anything.
--apply shows the same report and then prompts for explicit confirmation before
writing any adoption or closure to positions_log.json.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_REPO_ROOT))

_TRANSACTIONS_DIR = _REPO_ROOT / "data" / "transactions_report"
_CSV_GLOB = "report_2026*.csv"
_SEP = "─" * 70


def main() -> int:
    args = _parse_args()

    from data.cache import Cache
    from data.mep import fetch_mep
    from data.cocos_csv_parser import parse_positions
    from data.positions_log import load_positions, open_position, close_position
    from data.reconciler import reconcile, InLogNotInCsv
    from data.adoption import find_signal_backed_candidates, AdoptionCandidate
    from analysis.reversal.signal_registry import load_signals

    # --- MEP series ---
    print("Cargando tipo de cambio MEP...")
    mep_obj = fetch_mep(Cache())
    if mep_obj is None:
        print("Error: no se pudo obtener el tipo de cambio MEP. Abortando.", file=sys.stderr)
        return 1

    # --- Parse CSVs ---
    csv_paths = sorted(_TRANSACTIONS_DIR.glob(_CSV_GLOB))
    if not csv_paths:
        print(
            f"Error: no se encontraron archivos CSV en {_TRANSACTIONS_DIR} "
            f"con el patrón '{_CSV_GLOB}'.",
            file=sys.stderr,
        )
        return 1
    print(f"Procesando {len(csv_paths)} archivo(s) CSV...")
    parse_result = parse_positions(csv_paths, mep_obj.data)

    # --- Log ---
    logged = load_positions()

    # --- Reconcile ---
    report = reconcile(parse_result, logged)

    # --- Signal matching ---
    signals = load_signals()
    candidates, manual = find_signal_backed_candidates(report.in_csv_not_in_log, signals)

    # --- Print report (same for both modes) ---
    _print_report(report, candidates, manual, verbose=args.verbose)

    # --- Apply if requested ---
    if args.apply:
        return _apply(candidates, report.in_log_not_in_csv, open_position, close_position)

    return 0


# ---------------------------------------------------------------------------
# Report presentation
# ---------------------------------------------------------------------------

def _print_report(report, candidates, manual, *, verbose: bool) -> None:
    print()
    print("=" * 70)
    print("  REPORTE DE RECONCILIACIÓN")
    print("=" * 70)

    # 1. Coincidencias
    n_matched = len(report.matched)
    cost_mismatches = [m for m in report.matched if m.cost_mismatch]
    print(f"\n{_SEP}")
    print(f"  Coincidencias ({n_matched} posición/es)")
    print(_SEP)
    if verbose:
        for m in report.matched:
            flag = "  ⚠ discrepancia de costo" if m.cost_mismatch else ""
            print(
                f"  {m.ticker:<10}  CSV: {m.csv_qty:>8.2f} acc @ {m.csv_avg_cost_ars:>10.2f} ARS"
                f"  |  log: {m.log_qty:>8.2f} acc @ {m.log_open_price_ars:>10.2f} ARS{flag}"
            )
    else:
        hint = (
            f"  ({len(cost_mismatches)} con discrepancia de costo — usar --verbose para detalles)"
            if cost_mismatches else "  (usar --verbose para ver detalles)"
        )
        print(hint)

    # 2. Discrepancias de cantidad
    print(f"\n{_SEP}")
    print(f"  Discrepancias de cantidad ({len(report.qty_mismatch)} posición/es)")
    print(_SEP)
    if report.qty_mismatch:
        print("  ACCIÓN REQUERIDA — revisar y corregir manualmente con log_position.py:")
        for q in report.qty_mismatch:
            print(
                f"  {q.ticker:<10}  CSV: {q.csv_qty:>8.2f}  |  log: {q.log_qty:>8.2f}"
                f"  |  delta: {q.delta:>+.2f}"
            )
    else:
        print("  Ninguna.")

    # 3. En CSV pero no en log
    total_not_in_log = len(report.in_csv_not_in_log)
    print(f"\n{_SEP}")
    print(f"  En el CSV pero no en el log ({total_not_in_log} posición/es)")
    print(_SEP)

    print(f"\n  Candidatas a adopción automática — respaldadas por señal: {len(candidates)}")
    if candidates:
        for c in candidates:
            note_str = f"\n      [{c.note}]" if c.note else ""
            print(
                f"  {c.ticker:<10}  {c.csv_qty:.2f} acc @ {c.csv_avg_cost_ars:.2f} ARS/acc"
                f"  |  señal {c.matched_signal_scan_date}"
                f"  (score {c.matched_signal_score:.1f},"
                f" invalidación {c.matched_signal_invalidation_ars:.2f} ARS)"
                f"  [ventana provisoria (a calibrar)]{note_str}"
            )
    else:
        print("    (ninguna — el portfolio actual es totalmente discrecional)")

    print(f"\n  Manuales / sin señal — no se adoptan: {len(manual)}")
    if manual:
        for m in manual:
            print(
                f"  {m.ticker:<10}  {m.csv_qty:.2f} acc @ {m.csv_avg_cost_ars:.2f} ARS/acc"
                f"  |  primera compra: {m.csv_first_buy_date}"
            )
    else:
        print("    (ninguna)")

    # 4. En log pero no en CSV
    closed_cands = [e for e in report.in_log_not_in_csv if e.csv_status == "closed"]
    absent = [e for e in report.in_log_not_in_csv if e.csv_status == "absent"]
    print(f"\n{_SEP}")
    print(f"  En el log pero no en el CSV ({len(report.in_log_not_in_csv)} posición/es)")
    print(_SEP)

    print(f"\n  Candidatas a cerrar — el CSV las muestra como vendidas: {len(closed_cands)}")
    for e in closed_cands:
        print(
            f"  {e.ticker:<10}  ({e.log_symbol})  {e.log_qty:.2f} acc"
            f" @ {e.log_open_price_ars:.2f} ARS/acc"
        )
    if not closed_cands:
        print("    (ninguna)")

    print(f"\n  Ausentes del CSV — revisar manualmente: {len(absent)}")
    for e in absent:
        print(
            f"  {e.ticker:<10}  ({e.log_symbol})  {e.log_qty:.2f} acc"
            f" @ {e.log_open_price_ars:.2f} ARS/acc"
        )
    if not absent:
        print("    (ninguna)")

    # 5. Advertencias del parser
    print(f"\n{_SEP}")
    print(f"  Advertencias del parser ({len(report.skipped)})")
    print(_SEP)
    if report.skipped:
        for s in report.skipped:
            print(f"  {s.warning}")
    else:
        print("  Ninguna.")

    print("\n" + "=" * 70)


# ---------------------------------------------------------------------------
# Apply mode
# ---------------------------------------------------------------------------

def _apply(candidates, in_log_not_in_csv, open_position_fn, close_position_fn) -> int:
    """Prompt for confirmation before writing adoptions or closures to the log."""
    exit_code = 0

    # --- Adoptions ---
    if not candidates:
        print("\nNo hay candidatas para adopción automática. No se modificará el log.")
    else:
        print(f"\n{'─' * 70}")
        print(f"  ADOPCIÓN — {len(candidates)} posición/es a incorporar al log")
        print(f"{'─' * 70}")
        for c in candidates:
            print(
                f"  {c.ticker:<10}  {c.csv_qty:.2f} acc @ {c.csv_avg_cost_ars:.2f} ARS/acc"
                f"  fecha: {c.csv_first_buy_date}"
                f"  señal: {c.matched_signal_scan_date}"
            )
        try:
            answer = input("\n¿Confirmar adopción de todas las candidatas? [s/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nAbortado.")
            return 1

        if answer == "s":
            for c in candidates:
                try:
                    open_position_fn(
                        symbol=c.log_symbol,
                        price=c.csv_avg_cost_ars,
                        qty=c.csv_qty,
                        source="reversal",
                        score=c.matched_signal_score,
                        invalidation=c.matched_signal_invalidation_ars,
                        date=c.csv_first_buy_date,
                    )
                    print(f"  Adoptada: {c.log_symbol}")
                except ValueError as exc:
                    print(f"  Error al adoptar {c.log_symbol}: {exc}", file=sys.stderr)
                    exit_code = 1
            print("Adopción completada.")
        else:
            print("Adopción cancelada — no se realizaron cambios.")

    # --- Closures ---
    closed_cands = [e for e in in_log_not_in_csv if e.csv_status == "closed"]
    if not closed_cands:
        return exit_code

    print(f"\n{'─' * 70}")
    print(f"  CIERRES — {len(closed_cands)} posición/es que el CSV muestra como vendidas")
    print(f"{'─' * 70}")

    for e in closed_cands:
        print(f"\n  {e.log_symbol}  {e.log_qty:.2f} acc @ {e.log_open_price_ars:.2f} ARS/acc")
        try:
            answer = input(f"  ¿Cerrar {e.log_symbol} en el log? [s/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nAbortado.")
            return 1
        if answer != "s":
            print(f"  Omitiendo {e.log_symbol}.")
            continue

        try:
            close_date = input("  Fecha de cierre (YYYY-MM-DD): ").strip()
            close_price_str = input("  Precio de cierre (ARS): ").strip()
            reason = input("  Motivo de cierre (target/stop/manual): ").strip()
            close_price = float(close_price_str)
            close_position_fn(
                symbol=e.log_symbol,
                price=close_price,
                date=close_date,
                reason=reason,
            )
            print(f"  Cerrada: {e.log_symbol}")
        except (EOFError, KeyboardInterrupt):
            print("\nAbortado.")
            return 1
        except (ValueError, Exception) as exc:
            print(f"  Error al cerrar {e.log_symbol}: {exc}", file=sys.stderr)
            exit_code = 1

    return exit_code


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Reconciliar posiciones del CSV de Cocos Capital contra el log del sistema.\n"
            "Por defecto muestra el reporte sin escribir nada (dry-run)."
        )
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Solo mostrar el reporte; no escribir nada (comportamiento por defecto).",
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Mostrar el reporte y luego pedir confirmación antes de escribir.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=False,
        help="Incluir detalle de cada posición coincidente.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    sys.exit(main())
