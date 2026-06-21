"""Refresh the local universe snapshot (data/universe_snapshot.json).

Usage
-----
  # With CVSA Excel only (no pyCocos required):
  python scripts/refresh_universe.py --cvsa-excel ~/Downloads/cedears_cvsa.xlsx

  # With a pre-exported Cocos ticker list (JSON array of ticker strings, e.g. ["AAPL","MSFT"]):
  python scripts/refresh_universe.py --cvsa-excel ~/Downloads/cedears_cvsa.xlsx \
      --cocos-tickers ~/Downloads/cocos_tickers.json

  # Pull Cocos tickers live via pyCocos (requires pyCocos installed + TOTP configured):
  python scripts/refresh_universe.py --cvsa-excel ~/Downloads/cedears_cvsa.xlsx \
      --use-pycocos

Run this script manually once a month, or whenever Cocos adds/removes instruments
or a CEDEAR undergoes a split/reverse-split that changes the ratio.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).parent.parent
_SNAPSHOT_PATH = _REPO_ROOT / "data" / "universe_snapshot.json"

# Known column name variants in CVSA Excel (case-insensitive match)
_CVSA_COL_TICKER = ("especie", "ticker", "simbolo", "código", "cedear")
_CVSA_COL_NAME = ("denominacion", "nombre", "name", "denominación", "descripcion")
_CVSA_COL_RATIO = ("ratio", "relacion", "relación", "cantidad", "cedears por accion")
_CVSA_COL_ISIN = ("isin",)
_CVSA_COL_MARKET = ("mercado", "bolsa", "exchange", "mercado de origen")

# Mapping from CVSA ticker (without .BA) to the primary US underlying ticker.
# Populated here for the most common CEDEARs; extend as needed.
# If a CEDEAR's underlying is not listed here it will be set to null in the snapshot
# and should be filled manually.
_UNDERLYING_MAP: Dict[str, str] = {
    "AAPL": "AAPL", "MSFT": "MSFT", "GOOGL": "GOOGL", "AMZN": "AMZN",
    "NVDA": "NVDA", "META": "META", "TSLA": "TSLA", "BRKB": "BRK-B",
    "JPM": "JPM", "JNJ": "JNJ", "V": "V", "WMT": "WMT",
    "XOM": "XOM", "UNH": "UNH", "PG": "PG", "HD": "HD",
    "MA": "MA", "CVX": "CVX", "ABBV": "ABBV", "MRK": "MRK",
    "AVGO": "AVGO", "COST": "COST", "PEP": "PEP", "KO": "KO",
    "LLY": "LLY", "BAC": "BAC", "NFLX": "NFLX", "DIS": "DIS",
    "ADBE": "ADBE", "CRM": "CRM", "AMD": "AMD", "INTC": "INTC",
    "QCOM": "QCOM", "TXN": "TXN", "PYPL": "PYPL", "SBUX": "SBUX",
    "BA": "BA", "CAT": "CAT", "GS": "GS", "MS": "MS",
    "UBER": "UBER", "ABNB": "ABNB", "SNAP": "SNAP", "TWTR": "TWTR",
    # Argentine stocks with US ADR listings
    "GGAL": "GGAL", "BMA": "BMA", "YPF": "YPF", "PAM": "PAM",
    "SUPV": "SUPV", "CEPU": "CEPU", "LOMA": "LOMA", "EDN": "EDN",
    "TGS": "TGS", "CGPA": "CGPA",
}


def main() -> None:
    args = _parse_args()

    logger.info("Loading CVSA Excel: %s", args.cvsa_excel)
    cvsa_tickers = _load_cvsa_excel(Path(args.cvsa_excel))
    logger.info("Found %d CEDEARs in CVSA Excel", len(cvsa_tickers))

    cocos_set: Optional[set] = None
    if args.use_pycocos:
        cocos_set = _get_cocos_tickers_via_pycocos()
    elif args.cocos_tickers:
        cocos_set = _load_cocos_tickers_from_file(Path(args.cocos_tickers))

    output = _build_snapshot(cvsa_tickers, cocos_set)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    logger.info("Snapshot written to %s (%d tickers)", out_path, len(output["tickers"]))


# ── CVSA Excel parsing ─────────────────────────────────────────────────────────

def _load_cvsa_excel(path: Path) -> List[Dict[str, Any]]:
    try:
        import pandas as pd
    except ImportError:
        logger.error("pandas is required: pip install pandas openpyxl")
        sys.exit(1)

    try:
        df = pd.read_excel(path, dtype=str)
    except Exception as exc:
        logger.error("Failed to read CVSA Excel %s: %s", path, exc)
        sys.exit(1)

    col_map = _detect_columns(df.columns.tolist())
    if "ticker" not in col_map:
        logger.error(
            "Could not detect ticker column in CVSA Excel. "
            "Columns found: %s. Expected one of: %s",
            df.columns.tolist(),
            _CVSA_COL_TICKER,
        )
        sys.exit(1)

    records = []
    for _, row in df.iterrows():
        ticker = _clean(row.get(col_map["ticker"]))
        if not ticker:
            continue
        records.append(
            {
                "ticker": ticker.upper(),
                "name": _clean(row.get(col_map.get("name", ""), "")),
                "ratio": _parse_float(row.get(col_map.get("ratio", ""))),
                "isin": _clean(row.get(col_map.get("isin", ""), "")),
                "market": _clean(row.get(col_map.get("market", ""), "")),
            }
        )
    return records


def _detect_columns(columns: List[str]) -> Dict[str, str]:
    """Map semantic column names to actual Excel column names (case-insensitive)."""
    lower_cols = {c.lower().strip(): c for c in columns}
    mapping: Dict[str, str] = {}
    for key, variants in [
        ("ticker", _CVSA_COL_TICKER),
        ("name", _CVSA_COL_NAME),
        ("ratio", _CVSA_COL_RATIO),
        ("isin", _CVSA_COL_ISIN),
        ("market", _CVSA_COL_MARKET),
    ]:
        for variant in variants:
            if variant in lower_cols:
                mapping[key] = lower_cols[variant]
                break
    return mapping


# ── Cocos ticker sources ───────────────────────────────────────────────────────

def _get_cocos_tickers_via_pycocos() -> Optional[set]:
    try:
        from pyCocos import Cocos  # type: ignore[import]
    except ImportError:
        logger.error(
            "pyCocos is not installed. Install via: pip install pyCocos\n"
            "Note: pyCocos requires a Cocos account and TOTP secret key."
        )
        return None

    try:
        import os
        email = os.environ.get("COCOS_EMAIL") or input("Cocos email: ")
        password = os.environ.get("COCOS_PASSWORD") or input("Cocos password: ")
        totp_secret = os.environ.get("COCOS_TOTP_SECRET") or input("TOTP secret key: ")

        client = Cocos(email=email, password=password, totp_secret=totp_secret)
        client.login()
        tickers_resp = client.get_tickers()

        symbols = set()
        for item in tickers_resp:
            sym = item.get("symbol") or item.get("ticker")
            if sym:
                symbols.add(sym.upper().replace(".BA", ""))
        logger.info("pyCocos returned %d tradeable symbols", len(symbols))
        return symbols
    except Exception as exc:
        logger.error("pyCocos fetch failed: %s", exc)
        return None


def _load_cocos_tickers_from_file(path: Path) -> Optional[set]:
    try:
        data = json.loads(path.read_text())
        if isinstance(data, list):
            return {str(t).upper().replace(".BA", "") for t in data}
        logger.error("Cocos tickers file must be a JSON array of strings")
        return None
    except Exception as exc:
        logger.error("Failed to read Cocos tickers file %s: %s", path, exc)
        return None


# ── Snapshot assembly ──────────────────────────────────────────────────────────

def _build_snapshot(cvsa_tickers: List[Dict], cocos_set: Optional[set]) -> dict:
    cedear_symbols = {r["ticker"] for r in cvsa_tickers}
    cvsa_by_ticker = {r["ticker"]: r for r in cvsa_tickers}

    all_symbols = set(cedear_symbols)
    if cocos_set:
        all_symbols |= cocos_set

    all_symbols = _filter_mep_tickers(all_symbols)

    tickers_out = []
    for sym in sorted(all_symbols):
        if sym in cedear_symbols:
            cvsa = cvsa_by_ticker[sym]
            tickers_out.append(
                {
                    "symbol_ars": f"{sym}.BA",
                    "name": cvsa["name"] or sym,
                    "asset_type": "cedear",
                    "symbol_underlying": _UNDERLYING_MAP.get(sym),
                    "cedear_ratio": cvsa["ratio"],
                    "isin": cvsa["isin"] or None,
                }
            )
        else:
            tickers_out.append(
                {
                    "symbol_ars": f"{sym}.BA",
                    "name": sym,
                    "asset_type": "argentine_stock",
                    "symbol_underlying": _UNDERLYING_MAP.get(sym),
                    "cedear_ratio": None,
                    "isin": None,
                }
            )

    return {
        "snapshot_date": date.today().isoformat(),
        "source": "refresh_universe_script",
        "tickers": tickers_out,
    }


# ── MEP filter ────────────────────────────────────────────────────────────────

def _filter_mep_tickers(symbols: set) -> set:
    """Remove MEP-segment duplicates from the universe.

    BYMA MEP segment tickers follow the pattern {BASE}D (e.g. GGALD for GGAL).
    If both BASE and BASED exist in the universe, BASED is the MEP variant and
    is dropped. If only BASED exists (e.g. YPFD with no YPF), it is kept — it
    is a legitimate pesos-segment ticker, not a MEP duplicate.
    """
    return {sym for sym in symbols if not (sym.endswith("D") and sym[:-1] in symbols)}


# ── Utilities ──────────────────────────────────────────────────────────────────

def _clean(value: Any, default: str = "") -> str:
    if value is None:
        return default
    s = str(value).strip()
    return default if s.lower() in ("nan", "none", "") else s


def _parse_float(value: Any) -> Optional[float]:
    try:
        return float(str(value).replace(",", "."))
    except (ValueError, TypeError):
        return None


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Refresh the Cocos universe snapshot.")
    parser.add_argument(
        "--cvsa-excel",
        required=True,
        help="Path to the CVSA Excel file with CEDEAR list and ratios.",
    )
    parser.add_argument(
        "--cocos-tickers",
        help="Path to a JSON file with a list of Cocos ticker symbols (alternative to --use-pycocos).",
    )
    parser.add_argument(
        "--use-pycocos",
        action="store_true",
        help="Fetch Cocos universe live via pyCocos (requires account + TOTP).",
    )
    parser.add_argument(
        "--output",
        default=str(_SNAPSHOT_PATH),
        help=f"Output path for the snapshot JSON. Default: {_SNAPSHOT_PATH}",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
