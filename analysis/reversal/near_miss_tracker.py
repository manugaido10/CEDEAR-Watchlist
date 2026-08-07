"""Near-miss tracker for the reversal scanner.

Records tickers that almost qualified but failed one gate by a small margin.
Writes append-only to data/reversal_tracking/near_misses.jsonl and logs a
per-gate distribution summary after each scan, enabling calibration over time.

Near-miss thresholds (see DECISIONS.md #18):
- RSI outside [25, 45] by <= 3 pts
- Support distance in (5%, 7%]
- No catalyst detected but all other gates passed (hypothetical score >= 40)
- Vol ratio in [0.80, 0.90)
- Weekly trend negative but hypothetical score >= 55 (setup otherwise strong)

Only single-gate failures are recorded. Multi-gate failures are genuine discards.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

NEAR_MISSES_PATH = Path("data/reversal_tracking/near_misses.jsonl")

# Near-miss margins (mirror of DECISIONS.md #18)
_RSI_NEAR_MARGIN = 3.0
_SUPPORT_NEAR_MAX_DIST = 0.07   # 7% upper bound
_VOL_RATIO_NEAR_MAX = 0.90
_MIN_SCORE_NO_CATALYST = 40.0
_MIN_SCORE_WEEKLY_NEGATIVE = 55.0


@dataclass
class NearMissRecord:
    scan_date: str
    symbol: str
    failed_criteria: List[str]
    margins: Dict[str, float]        # e.g. {"rsi_gap": 2.2, "rsi_value": 47.2}
    computed_score: Optional[float]  # hypothetical score if gates had passed
    rsi: Optional[float]
    vol_ratio: Optional[float]
    support_distance_pct: Optional[float]
    weekly_trend: str


# ── I/O helpers ───────────────────────────────────────────────────────────────

def _ensure_path() -> None:
    NEAR_MISSES_PATH.parent.mkdir(parents=True, exist_ok=True)


def _append_record(r: NearMissRecord, enrichment: Optional[Dict] = None) -> None:
    _ensure_path()
    payload: Dict = {
        "scan_date": r.scan_date,
        "symbol": r.symbol,
        "failed_criteria": r.failed_criteria,
        "margins": r.margins,
        "computed_score": r.computed_score,
        "rsi": r.rsi,
        "vol_ratio": r.vol_ratio,
        "support_distance_pct": r.support_distance_pct,
        "weekly_trend": r.weekly_trend,
    }
    if enrichment is not None:
        payload["analyst_revision"] = enrichment
    with NEAR_MISSES_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


# ── Hypothetical score ────────────────────────────────────────────────────────

def _hypothetical_score(
    rsi: Optional[float],
    support_distance_pct: Optional[float],
    catalysts: List[str],
    vol_ratio: Optional[float],
) -> Optional[float]:
    """Score assuming ALL gates passed (used for near-miss threshold checks)."""
    if rsi is None or support_distance_pct is None or vol_ratio is None:
        return None

    from analysis.reversal.reversal_scanner import _compute_score
    return _compute_score(rsi, support_distance_pct, catalysts, vol_ratio)


# ── Near-miss evaluation ──────────────────────────────────────────────────────

def _evaluate_near_miss(metrics) -> Optional[NearMissRecord]:
    """Evaluate pre-computed metrics for near-miss status.

    metrics: _BundleMetrics from reversal_scanner.
    Returns NearMissRecord if exactly one gate failed by a small margin, else None.
    """
    from analysis.reversal.reversal_scanner import (
        RSI_LOW, RSI_HIGH, VOL_RATIO_THRESHOLD, SUPPORT_PROXIMITY_MAX,
    )

    failures: List[str] = []
    margins: Dict[str, float] = {}

    # ── Gate 1: weekly trend ─────────────────────────────────────────────────
    if metrics.weekly_trend == "negative":
        hyp = _hypothetical_score(
            metrics.rsi,
            metrics.support_result[2] if metrics.support_result else None,
            metrics.catalysts,
            metrics.vol_ratio,
        )
        if hyp is not None and hyp >= _MIN_SCORE_WEEKLY_NEGATIVE:
            failures.append("weekly_trend_negative")
            margins["hypothetical_score"] = round(hyp, 1)
        else:
            return None  # true discard: weak setup on top of negative trend

    # ── Gate 2: RSI ───────────────────────────────────────────────────────────
    if metrics.rsi is not None:
        rsi = metrics.rsi
        if not (RSI_LOW <= rsi <= RSI_HIGH):
            if rsi < RSI_LOW:
                gap = RSI_LOW - rsi
            else:
                gap = rsi - RSI_HIGH
            if gap <= _RSI_NEAR_MARGIN:
                failures.append("rsi_out_of_range")
                margins["rsi_value"] = round(rsi, 1)
                margins["rsi_gap"] = round(gap, 1)
            else:
                return None  # too far from RSI range

    # ── Gate 3: volume ratio ─────────────────────────────────────────────────
    if metrics.vol_ratio is not None:
        if metrics.vol_ratio >= VOL_RATIO_THRESHOLD:
            if metrics.vol_ratio < _VOL_RATIO_NEAR_MAX:
                failures.append("vol_ratio_high")
                margins["vol_ratio"] = round(metrics.vol_ratio, 3)
                margins["vol_ratio_gap"] = round(metrics.vol_ratio - VOL_RATIO_THRESHOLD, 3)
            else:
                return None  # clearly too high

    # ── Gate 4: support distance ─────────────────────────────────────────────
    if metrics.support_result is None:
        # Check if a support existed but slightly farther — not computable without
        # re-running the support search with extended range. Skip for now.
        failures.append("no_support_within_5pct")
        # We can't compute margins without re-running with wider window
    else:
        dist = metrics.support_result[2]
        if dist > SUPPORT_PROXIMITY_MAX:
            if dist <= _SUPPORT_NEAR_MAX_DIST:
                failures.append("support_too_far")
                margins["support_distance_pct"] = round(dist * 100, 2)
                margins["support_gap_pct"] = round((dist - SUPPORT_PROXIMITY_MAX) * 100, 2)
            else:
                return None

    # ── Gate 5: catalyst ─────────────────────────────────────────────────────
    if not metrics.catalysts and "rsi_out_of_range" not in failures:
        # Only a near-miss if everything else was fine
        hyp = _hypothetical_score(
            metrics.rsi,
            metrics.support_result[2] if metrics.support_result else None,
            [],
            metrics.vol_ratio,
        )
        if hyp is not None and hyp >= _MIN_SCORE_NO_CATALYST:
            failures.append("no_catalyst")
            margins["hypothetical_score"] = round(hyp, 1)
        else:
            return None

    # Require exactly one failed gate for near-miss classification
    if len(failures) != 1:
        return None

    hyp_score = _hypothetical_score(
        metrics.rsi,
        metrics.support_result[2] if metrics.support_result else None,
        metrics.catalysts,
        metrics.vol_ratio,
    )

    return NearMissRecord(
        scan_date="",  # filled by caller
        symbol=metrics.symbol,
        failed_criteria=failures,
        margins=margins,
        computed_score=round(hyp_score, 1) if hyp_score is not None else None,
        rsi=round(metrics.rsi, 1) if metrics.rsi is not None else None,
        vol_ratio=round(metrics.vol_ratio, 3) if metrics.vol_ratio is not None else None,
        support_distance_pct=(
            round(metrics.support_result[2] * 100, 2) if metrics.support_result else None
        ),
        weekly_trend=metrics.weekly_trend,
    )


# ── Public API ────────────────────────────────────────────────────────────────

def collect_near_misses(bundles: list, scan_date: str) -> List[NearMissRecord]:
    """Evaluate all bundles for near-miss status. Returns list of records."""
    from analysis.reversal.reversal_scanner import _compute_metrics, _evaluate_bundle

    records: List[NearMissRecord] = []
    passed_symbols = set()

    # First pass: collect passing symbols so we exclude them from near-miss
    for bundle in bundles:
        try:
            opp = _evaluate_bundle(bundle)
            if opp is not None:
                passed_symbols.add(bundle.metadata.symbol_ars)
        except Exception:
            pass

    # Second pass: near-miss evaluation for non-passing tickers
    for bundle in bundles:
        symbol = bundle.metadata.symbol_ars
        if symbol in passed_symbols:
            continue
        try:
            m = _compute_metrics(bundle)
            if m is None:
                continue
            rec = _evaluate_near_miss(m)
            if rec is not None:
                rec.scan_date = scan_date
                records.append(rec)
        except Exception as exc:
            logger.debug("near_miss_tracker: error evaluating %s: %s", symbol, exc)

    return records


def record_near_misses(
    records: List[NearMissRecord],
    scan_date: str,
    enrichments: Optional[Dict] = None,
) -> None:
    """Append records to near_misses.jsonl and log gate distribution summary.

    enrichments: optional {symbol_ars: {"trend": str, "n_analysts": int|None}} —
    merged silently into each record's payload when present.
    """
    for r in records:
        _append_record(r, enrichment=enrichments.get(r.symbol) if enrichments else None)

    dist = _gate_distribution(records)
    if dist:
        logger.info(
            "near_miss_tracker [%s]: %d near-misses — gate distribution: %s",
            scan_date,
            len(records),
            ", ".join(f"{gate}={count}" for gate, count in sorted(dist.items())),
        )
    else:
        logger.info("near_miss_tracker [%s]: 0 near-misses detected", scan_date)


def _gate_distribution(records: List[NearMissRecord]) -> Dict[str, int]:
    dist: Dict[str, int] = {}
    for r in records:
        for gate in r.failed_criteria:
            dist[gate] = dist.get(gate, 0) + 1
    return dist


def load_near_misses() -> List[Dict]:
    """Load all near-miss records from JSONL. Returns [] if file missing."""
    _ensure_path()
    if not NEAR_MISSES_PATH.exists():
        return []
    records = []
    for line in NEAR_MISSES_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                logger.warning("near_miss_tracker: skipping malformed line")
    return records


def summarize_gate_distribution_all_time() -> Dict[str, int]:
    """Aggregate gate distribution across all recorded near-misses."""
    return _gate_distribution([
        NearMissRecord(
            scan_date=r.get("scan_date", ""),
            symbol=r.get("symbol", ""),
            failed_criteria=r.get("failed_criteria", []),
            margins=r.get("margins", {}),
            computed_score=r.get("computed_score"),
            rsi=r.get("rsi"),
            vol_ratio=r.get("vol_ratio"),
            support_distance_pct=r.get("support_distance_pct"),
            weekly_trend=r.get("weekly_trend", ""),
        )
        for r in load_near_misses()
    ])
