"""Diagnóstico de liquidez para el scanner de reversiones (Item 2 — diagnóstico).

Objetivo: medir, con datos históricos REALES, qué fracción del volumen medio
diario negociado representaría una posición típica del scanner en cada uno de
los tickers que han aparecido como señal o near_miss. NO cambia lógica de
gating: solo emite un reporte que informa una decisión futura sobre dónde
poner un umbral de liquidez (misma metodología que se usó para calibrar el
cooldown de 15 días hábiles — medir primero, decidir después).

Uso:
    python scripts/diagnose_liquidity.py

Fuentes:
    - data/reversal_tracking/signals.jsonl (frecuencia y scan_dates)
    - data/reversal_tracking/near_misses.jsonl (scan_dates adicionales)
    - cache/prices/*.parquet (Volume + Close por ticker, ya presente)

Salida: tabla en stdout ordenada por ratio position_size / ADV descendente
(peor liquidez primero). No modifica archivos.
"""

from __future__ import annotations

import json
import logging
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from data.cache import Cache  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SIGNALS_PATH = Path("data/reversal_tracking/signals.jsonl")
NEAR_MISSES_PATH = Path("data/reversal_tracking/near_misses.jsonl")

# ── Fase 1.2: 5-8% por posición, 6.5% midpoint (ver output/reversal_report.py) ─
POSITION_PCT_MID = 0.065

# ── Escenarios de capital total en ARS (números redondos, portafolio real) ─────
CAPITAL_SCENARIOS_ARS = [20_000_000, 40_000_000, 80_000_000]
REFERENCE_CAPITAL_ARS = 40_000_000  # columna "posición al escenario medio"

# ── Tickers marcados manualmente en sesiones previas como sospechosos ─────────
KNOWN_THIN_TICKERS = {"SEMI.BA", "MORI.BA", "BYMA.BA"}

TRAILING_TRADING_DAYS = 20


# ── Carga de tracking ─────────────────────────────────────────────────────────

def _iter_jsonl(path: Path):
    if not path.exists():
        logger.warning("Missing tracking file: %s", path)
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            logger.warning("Skipping malformed JSONL line in %s", path)


def _collect_symbol_scandates() -> Tuple[Dict[str, str], Counter]:
    """Return ({symbol: max_scan_date}, Counter(frequency_in_signals)).

    Scan_dates come from BOTH signals and near_misses (union). Frequency counts
    only signals.jsonl — the count that matters for "shows up often as a real
    signal".
    """
    latest: Dict[str, str] = {}
    freq: Counter = Counter()

    for record in _iter_jsonl(SIGNALS_PATH):
        symbol = record.get("symbol")
        scan_date = record.get("scan_date")
        if not symbol or not scan_date:
            continue
        freq[symbol] += 1
        if symbol not in latest or scan_date > latest[symbol]:
            latest[symbol] = scan_date

    for record in _iter_jsonl(NEAR_MISSES_PATH):
        symbol = record.get("symbol")
        scan_date = record.get("scan_date")
        if not symbol or not scan_date:
            continue
        if symbol not in latest or scan_date > latest[symbol]:
            latest[symbol] = scan_date

    return latest, freq


# ── ADV cálculo ───────────────────────────────────────────────────────────────

def _compute_adv_ars(cache: Cache, symbol: str, as_of: str) -> Optional[float]:
    """Return avg(close × volume) over the trailing TRAILING_TRADING_DAYS bars.

    - Uses the cached parquet (no network).
    - "as of" = last bar with index <= as_of. If the ticker has no bar on/before
      as_of we return None (skipping the row rather than lying).
    - Requires the "volume" column present (yfinance provides it by default);
      returns None otherwise.
    """
    df = cache.load_prices(symbol)
    if df is None or df.empty:
        return None
    df.columns = [c.lower() for c in df.columns]
    if "close" not in df.columns or "volume" not in df.columns:
        return None

    df = df.sort_index()
    try:
        cutoff = pd.Timestamp(as_of)
    except Exception:
        return None
    window = df[df.index <= cutoff].tail(TRAILING_TRADING_DAYS)
    if window.empty:
        return None

    close = pd.to_numeric(window["close"], errors="coerce")
    volume = pd.to_numeric(window["volume"], errors="coerce")
    daily_traded_ars = (close * volume).dropna()
    if daily_traded_ars.empty:
        return None
    return float(daily_traded_ars.mean())


# ── Formateo ──────────────────────────────────────────────────────────────────

def _fmt_ars(v: Optional[float]) -> str:
    if v is None:
        return "—"
    return f"{int(round(v)):>15,}".replace(",", ".")


def _fmt_pct(v: Optional[float]) -> str:
    if v is None:
        return "—"
    return f"{v:>7.2f}%"


def _fmt_ratio(pos_ars: float, adv_ars: Optional[float]) -> Optional[float]:
    if adv_ars is None or adv_ars <= 0:
        return None
    return pos_ars / adv_ars * 100.0


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    cache = Cache()
    latest, freq = _collect_symbol_scandates()

    if not latest:
        logger.error("Sin símbolos en signals.jsonl ni near_misses.jsonl — nada que analizar.")
        sys.exit(1)

    logger.info(
        "Analizando %d símbolos únicos (signals=%d filas, near_misses fusionados por scan_date).",
        len(latest), sum(freq.values()),
    )

    rows: List[Dict] = []
    skipped: List[Tuple[str, str]] = []

    for symbol, as_of in sorted(latest.items()):
        adv_ars = _compute_adv_ars(cache, symbol, as_of)
        if adv_ars is None:
            skipped.append((symbol, "sin datos de volumen en cache"))
            continue

        pos_sizes_ars = {
            cap: cap * POSITION_PCT_MID for cap in CAPITAL_SCENARIOS_ARS
        }
        ratios = {
            cap: _fmt_ratio(pos_sizes_ars[cap], adv_ars)
            for cap in CAPITAL_SCENARIOS_ARS
        }

        rows.append({
            "symbol": symbol,
            "as_of": as_of,
            "adv_ars": adv_ars,
            "pos_size_ref_ars": pos_sizes_ars[REFERENCE_CAPITAL_ARS],
            "ratio_ref_pct": ratios[REFERENCE_CAPITAL_ARS],
            "ratios_pct": ratios,
            "frequency": freq.get(symbol, 0),
            "known_thin": symbol in KNOWN_THIN_TICKERS,
        })

    # Worst liquidity first (highest ratio at the reference capital).
    rows.sort(
        key=lambda r: r["ratio_ref_pct"] if r["ratio_ref_pct"] is not None else -1,
        reverse=True,
    )

    print()
    print(f"Diagnóstico de liquidez — {datetime.now().date().isoformat()}")
    print(f"  Position size = capital × {POSITION_PCT_MID:.1%} (midpoint 5-8%)")
    print(f"  ADV = avg(close × volume) sobre últimos {TRAILING_TRADING_DAYS} bars ≤ scan_date")
    print(f"  Escenarios de capital ARS: {', '.join(f'{c:,}' for c in CAPITAL_SCENARIOS_ARS)}")
    print(f"  Columnas de ratio: pos_size / ADV × 100 en cada escenario")
    print()

    header = (
        f"{'symbol':<12} {'as_of':<11} {'ADV_ars':>15} "
        f"{'pos@40M ARS':>15} "
        + " ".join(f"ratio@{c//1_000_000:>2}M" for c in CAPITAL_SCENARIOS_ARS)
        + f"  {'freq':>4}  flags"
    )
    print(header)
    print("-" * len(header))

    for row in rows:
        ratios = row["ratios_pct"]
        ratio_cols = "  ".join(_fmt_pct(ratios[c]) for c in CAPITAL_SCENARIOS_ARS)
        flag = "⚠known-thin" if row["known_thin"] else ""
        print(
            f"{row['symbol']:<12} {row['as_of']:<11} "
            f"{_fmt_ars(row['adv_ars'])} "
            f"{_fmt_ars(row['pos_size_ref_ars'])} "
            f"{ratio_cols}  "
            f"{row['frequency']:>4}  {flag}"
        )

    if skipped:
        print()
        print(f"Saltados ({len(skipped)}) — sin datos de volumen en cache:")
        for symbol, reason in skipped:
            print(f"  {symbol}: {reason}")

    # Sanity report on the manually-flagged trio.
    print()
    print("Chequeo cualitativo — tickers ya identificados como thin en sesiones previas:")
    for sym in sorted(KNOWN_THIN_TICKERS):
        matches = [r for r in rows if r["symbol"] == sym]
        if not matches:
            print(f"  {sym}: sin datos (skipped o nunca apareció en signals/near_misses)")
            continue
        r = matches[0]
        print(
            f"  {sym}: ratio@40M={_fmt_pct(r['ratio_ref_pct']).strip()}  "
            f"ADV={_fmt_ars(r['adv_ars']).strip()} ARS  "
            f"freq={r['frequency']}"
        )
    print()


if __name__ == "__main__":
    main()
