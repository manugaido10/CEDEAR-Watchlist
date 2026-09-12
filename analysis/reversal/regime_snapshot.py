"""Per-scan regime snapshot (Decision #31, Roadmap Fase A3).

Records three cheap universe-wide metrics that let Phase B correlate outcomes
against the market regime that produced them:

    pct_below_ma200         — fraction of eligible bundles trading below MA200
    median_rsi_14           — median RSI(14) across eligible bundles
    delta_median_rsi_prev   — median_rsi_14 minus the previous snapshot's value
                              (null when no previous snapshot exists)

`prev_scan_date` accompanies the delta so a consumer can tell whether the
comparison is against yesterday or against a run three days ago (weekend, gap).

Snapshot is written on every scan with ``record=True`` — including runs that
produce zero opportunities. A regime that produces no signals is itself a data
point, and Phase C's potential regime gate needs to see it.

Reuses ``analysis.reversal.reversal_scanner._compute_rsi`` — single source of
truth for the RSI(14) computation.
"""

from __future__ import annotations

import json
import logging
import statistics
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from data.models import FetchStatus, TickerBundle

logger = logging.getLogger(__name__)

REGIME_SNAPSHOTS_PATH = Path("data/reversal_tracking/regime_snapshots.jsonl")

_RSI_PERIOD = 14
_MA_WINDOW = 200


# ── I/O ───────────────────────────────────────────────────────────────────────

def _ensure_path() -> None:
    REGIME_SNAPSHOTS_PATH.parent.mkdir(parents=True, exist_ok=True)


def load_prior_snapshot() -> Optional[Dict]:
    """Return the last-recorded snapshot (by file order), or None if empty."""
    _ensure_path()
    if not REGIME_SNAPSHOTS_PATH.exists():
        return None
    lines = [
        ln for ln in REGIME_SNAPSHOTS_PATH.read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    if not lines:
        return None
    try:
        return json.loads(lines[-1])
    except json.JSONDecodeError:
        logger.warning("regime_snapshot: last line of %s is malformed", REGIME_SNAPSHOTS_PATH)
        return None


def _load_all_scan_dates() -> set:
    _ensure_path()
    if not REGIME_SNAPSHOTS_PATH.exists():
        return set()
    dates: set = set()
    for ln in REGIME_SNAPSHOTS_PATH.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            dates.add(json.loads(ln)["scan_date"])
        except (json.JSONDecodeError, KeyError):
            continue
    return dates


def append_snapshot(snapshot: Dict) -> None:
    """Append a snapshot line. Idempotent: no-op if this scan_date is already present."""
    existing = _load_all_scan_dates()
    if snapshot["scan_date"] in existing:
        logger.debug(
            "regime_snapshot: %s already recorded — skipping append",
            snapshot["scan_date"],
        )
        return
    _ensure_path()
    with REGIME_SNAPSHOTS_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(snapshot, ensure_ascii=False) + "\n")


# ── Compute ───────────────────────────────────────────────────────────────────

def compute_snapshot(
    bundles: List[TickerBundle],
    scan_date: str,
    n_opportunities_published: int,
) -> Dict:
    """Compute the snapshot for one scan.

    Only bundles with FetchStatus.OK are considered eligible. The MA200 metric
    additionally requires >= 200 bars per bundle. The two n counts document
    how much of the universe backed each aggregate.
    """
    from analysis.reversal.reversal_scanner import _compute_rsi

    n_universe_total = len(bundles)
    ma200_eligible: List[bool] = []  # True = eligible AND below MA200
    rsi_values: List[float] = []

    for b in bundles:
        if b.status != FetchStatus.OK:
            continue
        if b.prices_ars is None or b.prices_ars.data is None or b.prices_ars.data.empty:
            continue
        df = b.prices_ars.data
        close_col = "close" if "close" in df.columns else ("Close" if "Close" in df.columns else None)
        if close_col is None:
            continue
        closes = df[close_col].astype(float).values

        if len(closes) >= _MA_WINDOW:
            ma200 = float(np.mean(closes[-_MA_WINDOW:]))
            last = float(closes[-1])
            ma200_eligible.append(last < ma200)

        rsi = _compute_rsi(closes, _RSI_PERIOD)
        if rsi is not None:
            rsi_values.append(rsi)

    n_ma200_eligible = len(ma200_eligible)
    pct_below_ma200 = (
        round(sum(ma200_eligible) / n_ma200_eligible, 4)
        if n_ma200_eligible > 0
        else None
    )
    median_rsi_14 = round(statistics.median(rsi_values), 2) if rsi_values else None

    prior = load_prior_snapshot()
    prev_scan_date: Optional[str] = None
    delta_median_rsi_prev: Optional[float] = None
    if prior is not None:
        prev_scan_date = prior.get("scan_date")
        prior_median = prior.get("median_rsi_14")
        if median_rsi_14 is not None and prior_median is not None:
            delta_median_rsi_prev = round(median_rsi_14 - float(prior_median), 2)

    return {
        "scan_date": scan_date,
        "prev_scan_date": prev_scan_date,
        "n_universe_total": n_universe_total,
        "n_universe_ma200_eligible": n_ma200_eligible,
        "pct_below_ma200": pct_below_ma200,
        "median_rsi_14": median_rsi_14,
        "delta_median_rsi_prev": delta_median_rsi_prev,
        "n_opportunities_published": int(n_opportunities_published),
    }
