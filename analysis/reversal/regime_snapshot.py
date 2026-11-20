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

Failed runs (Decision #35): a snapshot with ``n_universe_ma200_eligible == 0``
means the fetch returned no usable universe; it is NOT persisted, so it can
neither block a later valid run on the same scan_date nor become the "prior"
of the next delta. Historical failed entries carry ``run_failed: true`` and are
skipped by ``load_prior_snapshot``.

Non-finite data (Decision #35): closes are forward-filled exactly as in
``reversal_scanner._compute_metrics``; any MA200/RSI value that is still
non-finite is excluded from its aggregate, and the number of bundles affected
is recorded in ``n_nonfinite_excluded``. Output is strict JSON (no NaN).

Reuses ``analysis.reversal.reversal_scanner._compute_rsi`` — single source of
truth for the RSI(14) computation.
"""

from __future__ import annotations

import json
import logging
import math
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
    """Return the last-recorded valid snapshot (by file order), or None.

    Entries marked ``run_failed: true`` are skipped (Decision #35). A malformed
    line ends the search with None, as before.
    """
    _ensure_path()
    if not REGIME_SNAPSHOTS_PATH.exists():
        return None
    lines = [
        ln for ln in REGIME_SNAPSHOTS_PATH.read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    for ln in reversed(lines):
        try:
            snap = json.loads(ln)
        except json.JSONDecodeError:
            logger.warning("regime_snapshot: malformed line in %s", REGIME_SNAPSHOTS_PATH)
            return None
        if snap.get("run_failed") is True:
            continue
        return snap
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


def is_failed_snapshot(snapshot: Dict) -> bool:
    """A snapshot with no MA200-eligible bundle comes from a failed fetch."""
    return snapshot.get("n_universe_ma200_eligible") == 0


def _strict_json_value(v):
    """Map non-finite floats to None (recursively) so json.dumps never emits NaN."""
    if isinstance(v, float) and not math.isfinite(v):
        return None
    if isinstance(v, dict):
        return {k: _strict_json_value(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_strict_json_value(x) for x in v]
    return v


def append_snapshot(snapshot: Dict) -> bool:
    """Append a snapshot line. Returns True if a line was written.

    No-op when this scan_date is already present (idempotent) or when the
    snapshot comes from a failed run (Decision #35).
    """
    if is_failed_snapshot(snapshot):
        logger.warning(
            "regime_snapshot: %s has n_universe_ma200_eligible=0 (failed fetch) — not persisted",
            snapshot["scan_date"],
        )
        return False
    existing = _load_all_scan_dates()
    if snapshot["scan_date"] in existing:
        logger.debug(
            "regime_snapshot: %s already recorded — skipping append",
            snapshot["scan_date"],
        )
        return False
    _ensure_path()
    line = json.dumps(_strict_json_value(snapshot), ensure_ascii=False, allow_nan=False)
    with REGIME_SNAPSHOTS_PATH.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    return True


# ── Compute ───────────────────────────────────────────────────────────────────

def compute_snapshot(
    bundles: List[TickerBundle],
    scan_date: str,
    n_opportunities_published: int,
    data_date: Optional[str] = None,
) -> Dict:
    """Compute the snapshot for one scan.

    Only bundles with FetchStatus.OK are considered eligible. The MA200 metric
    additionally requires >= 200 bars per bundle. The two n counts document
    how much of the universe backed each aggregate. Bundles with a non-finite
    MA200 or RSI (after ffill) are excluded from that aggregate and counted
    once in n_nonfinite_excluded.
    """
    from analysis.reversal.reversal_scanner import _compute_rsi

    n_universe_total = len(bundles)
    ma200_eligible: List[bool] = []  # True = eligible AND below MA200
    rsi_values: List[float] = []
    n_nonfinite_excluded = 0

    for b in bundles:
        if b.status != FetchStatus.OK:
            continue
        if b.prices_ars is None or b.prices_ars.data is None or b.prices_ars.data.empty:
            continue
        df = b.prices_ars.data
        close_col = "close" if "close" in df.columns else ("Close" if "Close" in df.columns else None)
        if close_col is None:
            continue
        # Same preprocessing as reversal_scanner._compute_metrics.
        closes = df[close_col].sort_index().astype(float).ffill().values
        nonfinite = False

        if len(closes) >= _MA_WINDOW:
            ma200 = float(np.mean(closes[-_MA_WINDOW:]))
            last = float(closes[-1])
            if math.isfinite(ma200) and math.isfinite(last):
                ma200_eligible.append(last < ma200)
            else:
                nonfinite = True

        rsi = _compute_rsi(closes, _RSI_PERIOD)
        if rsi is not None:
            if math.isfinite(rsi):
                rsi_values.append(rsi)
            else:
                nonfinite = True

        if nonfinite:
            n_nonfinite_excluded += 1

    n_ma200_eligible = len(ma200_eligible)
    pct_below_ma200 = (
        round(sum(ma200_eligible) / n_ma200_eligible, 4)
        if n_ma200_eligible > 0
        else None
    )
    n_rsi_eligible = len(rsi_values)
    median_rsi_14 = round(statistics.median(rsi_values), 2) if rsi_values else None

    prior = load_prior_snapshot()
    prev_scan_date: Optional[str] = None
    delta_median_rsi_prev: Optional[float] = None
    if prior is not None:
        prev_scan_date = prior.get("scan_date")
        prior_median = prior.get("median_rsi_14")
        if (
            median_rsi_14 is not None
            and prior_median is not None
            and math.isfinite(float(prior_median))
        ):
            delta_median_rsi_prev = round(median_rsi_14 - float(prior_median), 2)

    return {
        "scan_date": scan_date,
        "data_date": data_date,
        "prev_scan_date": prev_scan_date,
        "n_universe_total": n_universe_total,
        "n_universe_ma200_eligible": n_ma200_eligible,
        "pct_below_ma200": pct_below_ma200,
        "median_rsi_14": median_rsi_14,
        "n_rsi_eligible": n_rsi_eligible,
        "n_nonfinite_excluded": n_nonfinite_excluded,
        "delta_median_rsi_prev": delta_median_rsi_prev,
        "n_opportunities_published": int(n_opportunities_published),
    }
