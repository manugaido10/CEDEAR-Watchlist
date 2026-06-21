"""Refresh the local universe snapshot (data/universe_snapshot.json).

Builds the tradeable universe from two local sources:

  1. data/sources/Listado-CEDEAR.pdf — BYMA official CEDEAR list (master).
     Provides: name, BYMA code, market, ratio (N CEDEARs : M underlying).
  2. data/sources/argentine_stocks.yaml — hand-maintained list of direct
     Argentine stocks tradeable in Cocos.

The CVSA Excel (Tablas_CVSA_*.xlsx) is consumed only as a validation oracle:
it covers a small subset of CEDEARs but provides the underlying ticker on
non-US markets (B3, FRANKFURT, LSE, OTC) and the underlying ISIN, plus a
clean ratio that we cross-check against the PDF parse.

pyCocos / live Cocos integration is intentionally deferred.

Usage
-----
  python scripts/refresh_universe.py
  python scripts/refresh_universe.py --pdf <path> --cvsa-excel <path> --stocks-yaml <path>

Run this manually whenever BYMA publishes a new CEDEAR list (splits, new
listings, delistings) or you want to edit the Argentine stocks file.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).parent.parent
_SOURCES = _REPO_ROOT / "data" / "sources"
_DEFAULT_PDF = _SOURCES / "Listado-CEDEAR.pdf"
_DEFAULT_CVSA = _SOURCES / "Tablas_CVSA_2026-06-01.xlsx"
_DEFAULT_STOCKS_YAML = _SOURCES / "argentine_stocks.yaml"
_DEFAULT_SNAPSHOT = _REPO_ROOT / "data" / "universe_snapshot.json"

# Date stamped inside the PDF header — kept in sync manually when a new PDF lands.
_PDF_SNAPSHOT_DATE = date(2026, 6, 12)

# Markets recognized at the trailing position of a PDF line.
# Longest variants first so e.g. "NASDAQ GS" wins over "NASDAQ".
_MARKETS_ORDERED = (
    "LONDON STOCK EXCHANGE",
    "NASDAQ Arca",
    "NASDAQ ARCA",
    "NYSE Arca",
    "NYSE ARCA",
    "NASDAQ GS",
    "NASDAQ GM",
    "OTC US",
    "New York",
    "NASDAQ",
    "BOVESPA",
    "FRANKFURT",
    "XETRA",
    "CBOE",
    "NYSE",
    "OTC",
    "B3",
    "-",
)

# Markets where the BYMA code equals the underlying ticker abroad.
# Anything outside this set defers to the CVSA oracle for the underlying ticker.
_US_MARKETS = {
    "NYSE", "NYSE Arca", "NYSE ARCA",
    "NASDAQ", "NASDAQ GS", "NASDAQ GM", "NASDAQ Arca", "NASDAQ ARCA",
    "CBOE", "New York", "-",
}

# What this filter actually means: a row is excluded from the CEDEAR universe
# if (a) CVSA's "Tabla N°1: CEDEAR de ETF" lists its BYMA code, or (b) its name
# matches one of the substring markers below, or (c) its code is in
# _KNOWN_ETF_CODES. CVSA is authoritative for the codes it covers (~25 ETFs),
# but BYMA lists many more, so the heuristic catches the long tail.
#
# IMPORTANT: this is NOT "what Cocos actually offers to trade". We do not have
# a verified Cocos universe and pyCocos is deferred. The exclusion is the best
# proxy we have for "this is an ETF, defer to a separate ETF-screening flow"
# — treat it as an assumption, not a fact. If Cocos turns out to gate ETFs
# differently (or to not offer some non-ETF CEDEAR here), revisit this.
#
# Markers are matched as case-insensitive substrings, so they must be
# specific enough not to collide with real company names. Notable trap:
# "iPath" cannot be a bare substring because "UIPATH" (a real stock, PATH)
# contains it — use "ipath series" instead.
_ETF_NAME_MARKERS = (
    " etf",
    "ishares",
    "spdr",
    "van eck",
    "vanguard",
    "invesco",
    "ark innovation",
    "proshares",
    "first trust",
    "direxion",
    "global x",
    "select sector",
    "ipath series",
    "bitcoin trust",
    "ethereum tr",
    "silver trust",
    "gold trust",
    "uranium etf",
    "vix",
)

# Long-tail ETFs that no marker catches and CVSA doesn't cover. Keep this list
# minimal and only add codes after manually confirming they're ETFs/ETNs.
_KNOWN_ETF_CODES = frozenset({
    "USO",  # United States Oil Fund
})


def main() -> None:
    args = _parse_args()

    logger.info("Parsing BYMA PDF: %s", args.pdf)
    pdf_entries, pdf_warnings = _parse_byma_pdf(Path(args.pdf))
    logger.info("PDF yielded %d CEDEAR entries (%d warnings)", len(pdf_entries), len(pdf_warnings))
    for w in pdf_warnings:
        logger.warning("PDF: %s", w)

    cvsa_by_code: Dict[str, Dict[str, Any]] = {}
    if args.cvsa_excel and Path(args.cvsa_excel).exists():
        logger.info("Loading CVSA oracle: %s", args.cvsa_excel)
        cvsa_by_code = _load_cvsa_oracle(Path(args.cvsa_excel))
        logger.info("CVSA oracle covers %d BYMA codes", len(cvsa_by_code))
    else:
        logger.warning("CVSA Excel not found; underlying tickers for non-US markets will be None")

    cedear_records, no_underlying, ratio_discrepancies, etf_dropped = _enrich_with_oracle(
        pdf_entries, cvsa_by_code
    )

    logger.info("Loading Argentine stocks YAML: %s", args.stocks_yaml)
    stock_records = _load_argentine_stocks(Path(args.stocks_yaml))
    logger.info("Argentine stocks list has %d entries", len(stock_records))

    snapshot = {
        "snapshot_date": _PDF_SNAPSHOT_DATE.isoformat(),
        "source": "byma_pdf+argentine_stocks_yaml",
        "tickers": cedear_records + stock_records,
    }

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False))

    _print_summary(
        out_path=out_path,
        cedear_count=len(cedear_records),
        stock_count=len(stock_records),
        no_underlying=no_underlying,
        ratio_discrepancies=ratio_discrepancies,
        etf_dropped=etf_dropped,
    )


# ── BYMA PDF parsing ───────────────────────────────────────────────────────────


def _parse_byma_pdf(path: Path) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Extract one record per CEDEAR row from the BYMA PDF.

    Returns (records, warnings). Records are dicts with keys: name, byma_code,
    market, cedear_ratio_str, cedears_per_underlying, raw_ratio_from_pdf.
    """
    try:
        import pdfplumber  # type: ignore[import]
    except ImportError:
        logger.error("pdfplumber is required: pip install pdfplumber")
        sys.exit(1)

    warnings: List[str] = []
    records: List[Dict[str, Any]] = []

    with pdfplumber.open(path) as pdf:
        all_lines: List[str] = []
        for page in pdf.pages:
            text = page.extract_text() or ""
            all_lines.extend(text.splitlines())

    # LSE rows in the PDF wrap across three lines:
    #   "LONDON STOCK"     <- previous line
    #   "<Name> <CODE> <RATIO>"   <- data line WITHOUT market token
    #   "EXCHANGE"         <- next line
    # We detect this with a one-line lookahead flag.
    expect_lse_data = False
    skip_next_exchange = False

    for raw_line in all_lines:
        line = raw_line.strip()
        if not line:
            continue
        if _is_header_or_footer(line):
            continue
        if line == "LONDON STOCK":
            expect_lse_data = True
            continue
        if line == "EXCHANGE":
            # Closing token of an LSE wrap; nothing to parse here.
            skip_next_exchange = False
            continue

        parsed = _parse_data_line(line, expect_lse=expect_lse_data)
        # Reset the LSE flag whether or not the parse succeeded — it only spans
        # one data row.
        expect_lse_data = False

        if parsed is None:
            continue

        name, code, market, num, den, raw_ratio = parsed
        cedears_per_underlying = float(num) / float(den)
        normalized_str = f"{num}:{den}"
        if normalized_str != raw_ratio:
            # OCR-style artifacts (e.g. "10:01" → "10:1"). Not an error.
            logger.debug("Normalized ratio %s → %s for %s", raw_ratio, normalized_str, code)

        records.append({
            "name": name,
            "byma_code": code,
            "market": market,
            "cedear_ratio_str": normalized_str,
            "cedears_per_underlying": cedears_per_underlying,
            "raw_ratio_from_pdf": raw_ratio,
        })

    return records, warnings


def _is_header_or_footer(line: str) -> bool:
    if line.startswith("CEDEARs Negociables en BYMA"):
        return True
    if line.startswith("Bolsas y Mercados Argentinos"):
        return True
    if line.startswith("Mercado registrado bajo"):
        return True
    if line.startswith("Código Mercado donde"):
        return True
    if line.startswith("Nombre de la Compañía"):
        return True
    if line.startswith("BYMA Cotiza"):
        return True
    return False


_RATIO_TAIL_RE = re.compile(r"\s+(\d+):(\d+)\s*$")


def _parse_data_line(
    line: str, expect_lse: bool
) -> Optional[Tuple[str, str, str, int, int, str]]:
    """Return (name, byma_code, market, num, den, raw_ratio_str) or None.

    Strategy: anchor the ratio at the end, then identify the market by
    matching one of the known market keywords at the trailing position of
    the remaining substring. What's left splits as "<name> <code>" on the
    last whitespace.
    """
    m = _RATIO_TAIL_RE.search(line)
    if not m:
        return None
    raw_ratio = f"{m.group(1)}:{m.group(2)}"
    num = int(m.group(1))
    den = int(m.group(2))
    if den == 0:
        return None
    head = line[:m.start()].rstrip()

    market: Optional[str] = None
    head_no_market = head
    for candidate in _MARKETS_ORDERED:
        if head.endswith(" " + candidate) or head == candidate:
            market = candidate
            head_no_market = head[: -len(candidate)].rstrip()
            break

    if market is None:
        if expect_lse:
            market = "LONDON STOCK EXCHANGE"
            head_no_market = head
        else:
            return None

    # head_no_market should now be "<company name> <byma_code>".
    parts = head_no_market.rsplit(None, 1)
    if len(parts) != 2:
        return None
    name, code = parts
    name = name.strip()
    code = code.strip()
    if not name or not code:
        return None
    # BYMA codes are uppercase alphanumerics plus optional dot (e.g. AKO.B).
    if not re.fullmatch(r"[A-Z][A-Z0-9.]*", code):
        return None
    return name, code, market, num, den, raw_ratio


# ── CVSA oracle ───────────────────────────────────────────────────────────────


def _load_cvsa_oracle(path: Path) -> Dict[str, Dict[str, Any]]:
    """Index the CVSA Excel by BYMA code.

    The Excel has two tables (ETFs and Acciones) stacked in one sheet, each
    introduced by a "Tabla N°x:" row followed by a header row. We scan rows
    and pick up the header row whenever encountered, then read records below.
    """
    try:
        import pandas as pd  # type: ignore[import]
    except ImportError:
        logger.error("pandas is required: pip install pandas openpyxl")
        sys.exit(1)

    df = pd.read_excel(path, sheet_name=0, dtype=str, header=None)
    oracle: Dict[str, Dict[str, Any]] = {}
    header_idx: Dict[str, int] = {}
    current_table_kind: Optional[str] = None  # "etf" or "stock"

    for _, row in df.iterrows():
        cells = [c if isinstance(c, str) else None for c in row.tolist()]
        if any(cell == "Símbolo BYMA" for cell in cells if cell):
            header_idx = {}
            for i, cell in enumerate(cells):
                if not cell:
                    continue
                key = cell.strip()
                if key == "Símbolo BYMA":
                    header_idx["byma"] = i
                elif key == "Ticker en Mercado de Origen":
                    header_idx["underlying"] = i
                elif key == "Mercado de Origen":
                    header_idx["market"] = i
                elif key.startswith("Ratio"):
                    header_idx["ratio"] = i
                elif key in ("ISIN Acción", "ISIN ETF"):
                    header_idx["isin"] = i
                # The "section label" cell sits in column 0 of the header row
                # ("CEDEAR de ETF" or "CEDEAR de Acciones") — use it to tag the
                # following records.
                if key.lower().startswith("cedear de etf"):
                    current_table_kind = "etf"
                elif key.lower().startswith("cedear de acciones"):
                    current_table_kind = "stock"
            continue

        if "byma" not in header_idx:
            continue
        code = cells[header_idx["byma"]]
        if not code or not isinstance(code, str):
            continue
        code = code.strip()
        if not code or code == "Símbolo BYMA":
            continue

        oracle[code] = {
            "underlying": _cell(cells, header_idx.get("underlying")),
            "market": _cell(cells, header_idx.get("market")),
            "ratio": _cell(cells, header_idx.get("ratio")),
            "isin": _cell(cells, header_idx.get("isin")),
            "kind": current_table_kind,
        }
    return oracle


def _cell(cells: List[Optional[str]], idx: Optional[int]) -> Optional[str]:
    if idx is None or idx >= len(cells):
        return None
    val = cells[idx]
    if not val or not isinstance(val, str):
        return None
    s = val.strip()
    return s or None


# ── Enrichment & cross-validation ─────────────────────────────────────────────


def _enrich_with_oracle(
    pdf_entries: List[Dict[str, Any]],
    cvsa_by_code: Dict[str, Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[str], List[str], List[str]]:
    """Filter ETFs, dedupe, resolve underlying, cross-check ratios.

    Dedup policy: when the PDF has multiple rows for the same BYMA code
    (BYMA published at least one such typo: XLU appears twice), prefer the
    row whose ratio matches CVSA. If CVSA doesn't cover the code, keep the
    first occurrence.

    Returns (cedear_records, codes_without_underlying, ratio_discrepancies,
    etf_dropped_codes).
    """
    etf_dropped: List[str] = []
    survivors: Dict[str, Dict[str, Any]] = {}

    for entry in pdf_entries:
        code = entry["byma_code"]
        cvsa_entry = cvsa_by_code.get(code)
        if _is_etf(code, entry["name"], cvsa_entry):
            etf_dropped.append(code)
            continue

        if code not in survivors:
            survivors[code] = entry
            continue

        # Duplicate code: prefer the row whose ratio matches CVSA, if known.
        oracle_ratio = (cvsa_entry or {}).get("ratio")
        if oracle_ratio:
            oracle_ratio = oracle_ratio.strip()
            incoming_matches = entry["cedear_ratio_str"] == oracle_ratio
            existing_matches = survivors[code]["cedear_ratio_str"] == oracle_ratio
            if incoming_matches and not existing_matches:
                survivors[code] = entry

    cedear_records: List[Dict[str, Any]] = []
    no_underlying: List[str] = []
    ratio_discrepancies: List[str] = []

    for code in sorted(survivors):
        entry = survivors[code]
        market = entry["market"]
        oracle = cvsa_by_code.get(code)

        if market in _US_MARKETS:
            symbol_underlying: Optional[str] = code
        elif oracle and oracle.get("underlying"):
            symbol_underlying = oracle["underlying"]
        else:
            symbol_underlying = None
            no_underlying.append(f"{code} ({market})")

        isin = oracle.get("isin") if oracle else None

        if oracle and oracle.get("ratio"):
            oracle_ratio = oracle["ratio"].strip()
            if oracle_ratio != entry["cedear_ratio_str"]:
                ratio_discrepancies.append(
                    f"{code}: PDF={entry['cedear_ratio_str']} CVSA={oracle_ratio}"
                )

        cedear_records.append({
            "symbol_ars": f"{code}.BA",
            "name": entry["name"],
            "asset_type": "cedear",
            "symbol_underlying": symbol_underlying,
            "cedear_ratio_str": entry["cedear_ratio_str"],
            "cedears_per_underlying": round(entry["cedears_per_underlying"], 6),
            "isin": isin,
            "market": market,
        })

    return cedear_records, no_underlying, ratio_discrepancies, etf_dropped


def _is_etf(code: str, name: str, cvsa_entry: Optional[Dict[str, Any]]) -> bool:
    """Decide whether a PDF row represents an ETF, to be excluded from the
    CEDEAR universe.

    Precedence:
      1. CVSA Tabla N°1 — authoritative for codes it covers ("etf"/"stock").
      2. Explicit override list — long-tail ETFs CVSA doesn't list (e.g. USO).
      3. Name substring heuristic — catches the bulk of ETFs (iShares, SPDR,
         Vanguard, Select Sector, ProShares, DIREXION, Global X, Van Eck,
         First Trust, ARK, etc.).

    This is a best-effort proxy. We have no verified list of what Cocos
    actually offers — see the comment on _ETF_NAME_MARKERS.
    """
    if cvsa_entry and cvsa_entry.get("kind") == "etf":
        return True
    if cvsa_entry and cvsa_entry.get("kind") == "stock":
        return False
    if code in _KNOWN_ETF_CODES:
        return True
    lower = name.lower()
    return any(marker in lower for marker in _ETF_NAME_MARKERS)


# ── Argentine stocks YAML ─────────────────────────────────────────────────────


def _load_argentine_stocks(path: Path) -> List[Dict[str, Any]]:
    try:
        import yaml  # type: ignore[import]
    except ImportError:
        logger.error("pyyaml is required: pip install pyyaml")
        sys.exit(1)

    if not path.exists():
        logger.warning("Argentine stocks YAML not found at %s; skipping", path)
        return []

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    stocks = raw.get("stocks") or {}
    records: List[Dict[str, Any]] = []
    for ticker, name in stocks.items():
        ticker = str(ticker).strip().upper()
        records.append({
            "symbol_ars": f"{ticker}.BA",
            "name": str(name).strip() if name else ticker,
            "asset_type": "argentine_stock",
            "symbol_underlying": None,
            "cedear_ratio_str": None,
            "cedears_per_underlying": None,
            "isin": None,
            "market": "BYMA",
        })
    return records


# ── Output summary ────────────────────────────────────────────────────────────


def _print_summary(
    out_path: Path,
    cedear_count: int,
    stock_count: int,
    no_underlying: List[str],
    ratio_discrepancies: List[str],
    etf_dropped: List[str],
) -> None:
    total = cedear_count + stock_count
    logger.info("─" * 60)
    logger.info("Snapshot written: %s", out_path)
    logger.info("Total tickers: %d (CEDEARs=%d, Argentinas=%d)", total, cedear_count, stock_count)
    logger.info("ETF rows filtered out of CEDEAR universe: %d", len(etf_dropped))
    logger.info("CEDEARs without resolved symbol_underlying: %d", len(no_underlying))
    if no_underlying:
        logger.info("  %s", ", ".join(no_underlying))
    logger.info("Ratio discrepancies vs CVSA: %d", len(ratio_discrepancies))
    for line in ratio_discrepancies:
        logger.warning("  RATIO MISMATCH: %s", line)


# ── CLI ───────────────────────────────────────────────────────────────────────


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the BYMA-based universe snapshot.")
    parser.add_argument("--pdf", default=str(_DEFAULT_PDF), help="Path to BYMA Listado-CEDEAR PDF.")
    parser.add_argument(
        "--cvsa-excel",
        default=str(_DEFAULT_CVSA),
        help="Path to CVSA updates Excel (validation oracle).",
    )
    parser.add_argument(
        "--stocks-yaml",
        default=str(_DEFAULT_STOCKS_YAML),
        help="Path to argentine_stocks.yaml.",
    )
    parser.add_argument(
        "--output",
        default=str(_DEFAULT_SNAPSHOT),
        help=f"Output snapshot path. Default: {_DEFAULT_SNAPSHOT}",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
