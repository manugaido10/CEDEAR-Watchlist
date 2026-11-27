"""Per-run verification of the CCL history's session alignment (P1, Decision #43).

Problem (docs/HALLAZGOS_2026-11-27.md §1.6): argentinadatos' CCL history has
changed *which session each date represents* twice. With shift k, the value of
BYMA session S_i is the one the source publishes under the date of S_{i+k}:

    2013 → ~mar-2020   k = 1  (date D carries the previous session's close)
    ~abr-2020 → 2026-09-07   k = 0
    2026-09-08 → today       k = 1

The shift is counted in BYMA *sessions*, not calendar days: in the 2013–2020
regime Saturday repeated Friday's record (which held Thursday's close), so a
"+1 calendar day" rule misaligns every Friday.

What this module does, once per run:

1. Builds an implied CCL reference from local/ADR pairs (GGAL, BMA, PAMP/PAM,
   YPFD/YPF): daily log-returns of local/ADR per pair (ratio-invariant), median
   across ≥ MIN_PAIRS pairs, on sessions where both markets traded.
2. Detects the shift over the last WINDOW_SESSIONS common sessions: Pearson
   correlation of the reference against the source re-indexed with each
   candidate k ∈ {−1, 0, +1}. A shift is *decided* only when
   margin (best − second) ≥ MIN_MARGIN and best correlation ≥ MIN_CORR;
   otherwise the result is *ambiguous*.
3. Applies the versioned regime table (data/sources/ccl_shift_regimes.json)
   piecewise over the BYMA session calendar. The detection only *verifies*
   the table's current regime:

     confirmed      detected == table           → table
     regime_change  decided  != table           → table + provisional tail
                                                   segment (last N sessions)
                                                   with the detected shift;
                                                   the table is NOT edited
     ambiguous      thresholds not met          → table, flagged
     unavailable    no CCL / pairs / ADR data   → table if possible, flagged

   Nothing is ever corrected silently: every run returns a record that the
   regime snapshot persists.

The spot (``CCLSeries.spot`` → ``ccl_at_scan``) and ``as_of`` are never
touched. Only the history is re-aligned, and only from the first session of
the calendar on (earlier dates stay raw: no consumer reads that far back).
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .models import CCLSeries, TickerBundle

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent.parent
REGIMES_PATH = _REPO_ROOT / "data" / "sources" / "ccl_shift_regimes.json"

# (local BYMA symbol, US ADR symbol)
PAIRS: Tuple[Tuple[str, str], ...] = (
    ("GGAL.BA", "GGAL"),
    ("BMA.BA", "BMA"),
    ("PAMP.BA", "PAM"),
    ("YPFD.BA", "YPF"),
)
CANDIDATE_SHIFTS: Tuple[int, ...] = (-1, 0, 1)

# Calibrated on 2015-01 → 2026-11 (2677 rolling windows inside known regimes):
# 0 wrong decisions; see Decision #43 and scripts/backtest_ccl_alignment.py.
WINDOW_SESSIONS = 30
MIN_MARGIN = 0.25
MIN_CORR = 0.55
MIN_PAIRS = 3
MAX_ABS_IMPLIED_RET = 0.10   # |daily log-return| above this is a data glitch
ADR_LOOKBACK_DAYS = 400

STATUS_CONFIRMED = "confirmed"
STATUS_REGIME_CHANGE = "regime_change"
STATUS_AMBIGUOUS = "ambiguous"
STATUS_UNAVAILABLE = "unavailable"


# ── Regime table ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ShiftSegment:
    start: pd.Timestamp   # first BYMA session the shift applies to
    shift: int


def load_regimes(path: Path = REGIMES_PATH) -> List[ShiftSegment]:
    """Load and validate the regime table (sorted, shifts in CANDIDATE_SHIFTS)."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    segments = [
        ShiftSegment(start=pd.Timestamp(s["from"]), shift=int(s["shift"]))
        for s in raw["segments"]
    ]
    if not segments:
        raise ValueError("ccl_shift_regimes: no segments")
    for seg in segments:
        if seg.shift not in CANDIDATE_SHIFTS:
            raise ValueError(f"ccl_shift_regimes: invalid shift {seg.shift}")
    starts = [s.start for s in segments]
    if starts != sorted(starts) or len(set(starts)) != len(starts):
        raise ValueError("ccl_shift_regimes: segments must be strictly increasing")
    return segments


def shift_for(day: pd.Timestamp, segments: Sequence[ShiftSegment]) -> int:
    """Shift of the segment containing ``day`` (first segment's before it)."""
    current = segments[0].shift
    for seg in segments:
        if seg.start <= day:
            current = seg.shift
        else:
            break
    return current


# ── Session calendar & reference ──────────────────────────────────────────────

def _normalized(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [str(c).lower() for c in out.columns]
    out.index = pd.to_datetime(out.index).tz_localize(None).normalize()
    return out[~out.index.duplicated(keep="last")].sort_index()


def _close(df: pd.DataFrame) -> pd.Series:
    return _normalized(df)["close"].astype(float)


def _live_mask(df: pd.DataFrame) -> pd.Series:
    """Bars with actual trading: volume > 0 when known, else close changed."""
    n = _normalized(df)
    if "volume" in n.columns:
        return n["volume"].astype(float).fillna(0) > 0
    return n["close"].astype(float).diff() != 0


def byma_sessions(local_frames: Mapping[str, pd.DataFrame], min_pairs: int = MIN_PAIRS) -> pd.DatetimeIndex:
    """Dates where at least ``min_pairs`` liquid local stocks actually traded.

    Ghost bars (flat, volume 0) and BYMA holidays drop out. Used as the session
    calendar in which the shift is counted.
    """
    masks = [
        _live_mask(df).rename(sym)
        for sym, df in local_frames.items()
        if df is not None and not df.empty
    ]
    if not masks:
        return pd.DatetimeIndex([])
    m = pd.concat(masks, axis=1).fillna(False)
    return pd.DatetimeIndex(m.index[m.sum(axis=1) >= min_pairs]).sort_values()


def implied_returns(
    local_frames: Mapping[str, pd.DataFrame],
    adr_frames: Mapping[str, pd.DataFrame],
    sessions: pd.DatetimeIndex,
    min_pairs: int = MIN_PAIRS,
) -> pd.Series:
    """Median daily log-return of local/ADR across pairs, on common sessions.

    Returns are taken between consecutive common sessions (≥ ``min_pairs`` pairs
    with both a live local bar and an ADR close). Days whose median return
    exceeds MAX_ABS_IMPLIED_RET in absolute value are dropped as data glitches.
    """
    levels = []
    for local_sym, adr_sym in PAIRS:
        ldf, adf = local_frames.get(local_sym), adr_frames.get(adr_sym)
        if ldf is None or adf is None or ldf.empty or adf.empty:
            continue
        lc = _close(ldf)[_live_mask(ldf)]
        ac = _close(adf)
        x = pd.concat([lc.rename("l"), ac.rename("a")], axis=1).dropna()
        x = x[(x["l"] > 0) & (x["a"] > 0)]
        x = x[x.index.isin(sessions)]
        levels.append(np.log(x["l"] / x["a"]).rename(local_sym))
    if not levels:
        return pd.Series(dtype=float)
    lv = pd.concat(levels, axis=1)
    lv = lv[lv.notna().sum(axis=1) >= min_pairs]
    rets = lv.diff().iloc[1:]
    counts = rets.notna().sum(axis=1)
    med = rets.median(axis=1)[counts >= min_pairs].dropna()
    return med[med.abs() <= MAX_ABS_IMPLIED_RET]


def _source_on_extended_sessions(
    ccl: pd.Series, sessions: pd.DatetimeIndex,
) -> Tuple[pd.Series, Optional[pd.Timestamp]]:
    """Source value at each session plus one trailing date (first source date after
    the last session), so shift +1 has a value for the last session."""
    ccl = ccl.sort_index()
    ext = sessions
    tail: Optional[pd.Timestamp] = None
    after = ccl.index[ccl.index > sessions[-1]]
    if len(after):
        tail = pd.Timestamp(after[0])
        ext = sessions.append(pd.DatetimeIndex([tail]))
    vals = pd.Series(ccl.asof(ext).to_numpy(dtype=float), index=ext)
    return vals, tail


def candidate_on_sessions(ccl: pd.Series, sessions: pd.DatetimeIndex, k: int) -> pd.Series:
    """Source re-indexed so that session S_i takes the value dated S_{i+k}."""
    vals, _ = _source_on_extended_sessions(ccl, sessions)
    return vals.shift(-k).reindex(sessions)


def is_tail_provisional(ccl: pd.Series, sessions: pd.DatetimeIndex) -> bool:
    """Under shift +1, is the last session's value not yet published?

    The last session S takes the first source record dated after S. When that
    record does not exist, or merely repeats the record dated S (the source
    pre-creates today's record as a copy, or data/ccl.py forward-filled it),
    the last session is still carrying the previous session's close.
    """
    vals, tail = _source_on_extended_sessions(ccl, sessions)
    if tail is None:
        return True
    return bool(vals.iloc[-1] == vals.iloc[-2])


# ── Detection ─────────────────────────────────────────────────────────────────

@dataclass
class Detection:
    status: str                         # decided | ambiguous | unavailable
    shift: Optional[int] = None
    margin: Optional[float] = None
    corr_by_shift: Optional[Dict[str, Optional[float]]] = None
    n_sessions: int = 0
    window_start: Optional[pd.Timestamp] = None
    window_end: Optional[pd.Timestamp] = None
    reason: Optional[str] = None


def candidate_returns(
    implied: pd.Series, ccl: pd.Series, sessions: pd.DatetimeIndex,
) -> pd.DataFrame:
    """Reference returns ('imp') plus the source's returns under each candidate
    shift, on common sessions; rows with any missing value are dropped."""
    common = implied.index
    frame: Dict = {"imp": implied}
    for k in CANDIDATE_SHIFTS:
        cand = candidate_on_sessions(ccl, sessions, k).reindex(common)
        frame[k] = np.log(cand / cand.shift(1))
    return pd.DataFrame(frame).replace([np.inf, -np.inf], np.nan).dropna()


def decide(
    w: pd.DataFrame, min_margin: float = MIN_MARGIN, min_corr: float = MIN_CORR,
) -> Detection:
    """Decision rule over one window of ``candidate_returns`` rows."""
    corr: Dict[int, float] = {}
    for k in CANDIDATE_SHIFTS:
        ok = w[k].std() > 0 and w["imp"].std() > 0
        corr[k] = float(w["imp"].corr(w[k])) if ok else float("nan")
    corr_rec = {str(k): (round(v, 4) if math.isfinite(v) else None) for k, v in corr.items()}
    ranked = sorted(
        CANDIDATE_SHIFTS, key=lambda k: corr[k] if math.isfinite(corr[k]) else -math.inf, reverse=True,
    )
    best, second = ranked[0], ranked[1]
    det = Detection(
        status=STATUS_AMBIGUOUS, corr_by_shift=corr_rec, n_sessions=len(w),
        window_start=w.index[0], window_end=w.index[-1],
    )
    if not math.isfinite(corr[best]):
        det.reason = "no variance in window"
        return det
    second_c = corr[second] if math.isfinite(corr[second]) else -1.0
    margin = corr[best] - second_c
    det.margin = round(margin, 4)
    if margin >= min_margin and corr[best] >= min_corr:
        det.status = "decided"
        det.shift = best
    else:
        det.reason = f"best k={best} corr={corr[best]:.2f} margin={margin:.2f} below thresholds"
    return det


def detect_shift(
    implied: pd.Series,
    ccl: pd.Series,
    sessions: pd.DatetimeIndex,
    window: int = WINDOW_SESSIONS,
    min_margin: float = MIN_MARGIN,
    min_corr: float = MIN_CORR,
) -> Detection:
    """Decide the shift over the last ``window`` common sessions."""
    if implied.empty or len(sessions) == 0:
        return Detection(status=STATUS_UNAVAILABLE, reason="no reference returns")
    df = candidate_returns(implied, ccl, sessions)
    if len(df) < window:
        return Detection(
            status=STATUS_UNAVAILABLE, n_sessions=len(df),
            reason=f"{len(df)} common sessions < window {window}",
        )
    return decide(df.iloc[-window:], min_margin, min_corr)


# ── Application ───────────────────────────────────────────────────────────────

def align_ccl_series(
    ccl: pd.Series,
    sessions: pd.DatetimeIndex,
    segments: Sequence[ShiftSegment],
    override_from: Optional[pd.Timestamp] = None,
    override_shift: Optional[int] = None,
) -> Tuple[pd.Series, int]:
    """Re-align the calendar-daily CCL series session by session.

    Each session S_i takes the source value dated S_{i+k}, with k from the
    regime table (or ``override_shift`` from ``override_from`` on). Non-session
    calendar days carry the previous session's aligned value; dates before the
    first session stay raw. Returns (aligned series, shift used at the last
    session).
    """
    ccl = ccl.sort_index().astype(float)
    if len(sessions) == 0:
        return ccl.copy(), shift_for(ccl.index[-1], segments)
    vals, _ = _source_on_extended_sessions(ccl, sessions)
    shifted = {k: vals.shift(-k).reindex(sessions) for k in CANDIDATE_SHIFTS}
    ks = []
    for s in sessions:
        k = shift_for(s, segments)
        if override_from is not None and override_shift is not None and s >= override_from:
            k = override_shift
        ks.append(k)
    raw_at_sessions = vals.reindex(sessions)
    aligned_sessions = pd.Series(
        [shifted[k].iloc[i] for i, k in enumerate(ks)], index=sessions, dtype=float,
    ).fillna(raw_at_sessions)

    out = ccl.copy()
    after = out.index >= sessions[0]
    filled = aligned_sessions.reindex(out.index[after].union(sessions)).ffill()
    out.loc[after] = filled.reindex(out.index[after]).to_numpy()
    # Sessions missing from the calendar-daily index (should not happen: the
    # source is forward-filled daily) are added so asof lookups hit them.
    missing = sessions.difference(out.index)
    if len(missing):
        out = pd.concat([out, aligned_sessions.reindex(missing)]).sort_index()
    return out, ks[-1]


# ── Orchestration ─────────────────────────────────────────────────────────────

@dataclass
class AlignmentResult:
    status: str
    applied: bool = False
    table_shift: Optional[int] = None
    detected_shift: Optional[int] = None
    applied_shift_last_session: Optional[int] = None
    margin: Optional[float] = None
    corr_by_shift: Optional[Dict[str, Optional[float]]] = None
    n_sessions: int = 0
    window_start: Optional[str] = None
    window_end: Optional[str] = None
    pairs_used: List[str] = field(default_factory=list)
    tail_provisional: bool = False
    provisional_from: Optional[str] = None
    aligned_from: Optional[str] = None
    reason: Optional[str] = None
    params: Dict[str, float] = field(default_factory=lambda: {
        "window_sessions": WINDOW_SESSIONS, "min_margin": MIN_MARGIN, "min_corr": MIN_CORR,
    })

    def to_record(self) -> Dict:
        return {
            "status": self.status,
            "applied": self.applied,
            "table_shift": self.table_shift,
            "detected_shift": self.detected_shift,
            "applied_shift_last_session": self.applied_shift_last_session,
            "margin": self.margin,
            "corr_by_shift": self.corr_by_shift,
            "n_sessions": self.n_sessions,
            "window_start": self.window_start,
            "window_end": self.window_end,
            "pairs_used": list(self.pairs_used),
            "tail_provisional": self.tail_provisional,
            "provisional_from": self.provisional_from,
            "aligned_from": self.aligned_from,
            "reason": self.reason,
            "params": dict(self.params),
        }


AdrLoader = Callable[[str], Optional[pd.DataFrame]]


def make_cached_adr_loader(cache, lookback_days: int = ADR_LOOKBACK_DAYS) -> AdrLoader:
    """ADR daily bars via the price cache; live yfinance fetch when stale."""
    from .prices import fetch_prices

    def _load(symbol: str) -> Optional[pd.DataFrame]:
        if cache is not None and cache.prices_are_fresh(symbol):
            return cache.load_prices(symbol)
        df = fetch_prices(symbol, lookback_days=lookback_days)
        if df is not None and not df.empty:
            if cache is not None:
                cache.save_prices(symbol, df)
            return df
        if cache is not None:
            stale = cache.load_prices(symbol)
            if stale is not None and not stale.empty:
                logger.warning("ccl_alignment: %s live fetch failed; using stale cache", symbol)
                return stale
        return None

    return _load


def _iso(ts: Optional[pd.Timestamp]) -> Optional[str]:
    return pd.Timestamp(ts).date().isoformat() if ts is not None else None


def align_bundles_ccl(
    bundles: List[TickerBundle],
    adr_loader: AdrLoader,
    regimes_path: Path = REGIMES_PATH,
) -> AlignmentResult:
    """Detect the shift, apply the regime table, swap the CCL on every bundle.

    Bundles are mutated in place: each one that carries a CCL series gets the
    same new ``CCLSeries`` (aligned history, unchanged spot and as_of).
    Never raises for data problems: they end as status ``unavailable``.
    """
    ccl_obj: Optional[CCLSeries] = next(
        (b.ccl_series for b in bundles if b.ccl_series is not None), None,
    )
    if ccl_obj is None or ccl_obj.data is None or ccl_obj.data.empty:
        return AlignmentResult(status=STATUS_UNAVAILABLE, reason="no CCL series")
    ccl = ccl_obj.data.sort_index().astype(float)

    try:
        segments = load_regimes(regimes_path)
    except Exception as exc:
        logger.error("ccl_alignment: regime table unreadable (%s) — CCL left raw", exc)
        return AlignmentResult(status=STATUS_UNAVAILABLE, reason=f"regime table: {exc}")

    by_symbol = {b.metadata.symbol_ars: b for b in bundles}
    local_frames: Dict[str, pd.DataFrame] = {}
    for local_sym, _ in PAIRS:
        b = by_symbol.get(local_sym)
        if b is not None and b.prices_ars is not None and b.prices_ars.data is not None \
                and not b.prices_ars.data.empty:
            local_frames[local_sym] = b.prices_ars.data
    sessions = byma_sessions(local_frames)
    if len(sessions) == 0:
        return AlignmentResult(
            status=STATUS_UNAVAILABLE, reason="no BYMA session calendar (local pairs missing)",
            table_shift=shift_for(ccl.index[-1], segments),
        )

    adr_frames: Dict[str, pd.DataFrame] = {}
    for local_sym, adr_sym in PAIRS:
        if local_sym not in local_frames:
            continue
        try:
            df = adr_loader(adr_sym)
        except Exception as exc:
            logger.warning("ccl_alignment: ADR %s load failed — %s", adr_sym, exc)
            df = None
        if df is not None and not df.empty:
            adr_frames[adr_sym] = df
    pairs_used = [l for l, a in PAIRS if l in local_frames and a in adr_frames]

    table_shift = shift_for(sessions[-1], segments)
    implied = implied_returns(local_frames, adr_frames, sessions)
    det = detect_shift(implied, ccl, sessions)

    status: str
    override_from: Optional[pd.Timestamp] = None
    override_shift: Optional[int] = None
    if det.status == "decided":
        if det.shift == table_shift:
            status = STATUS_CONFIRMED
        else:
            status = STATUS_REGIME_CHANGE
            override_from, override_shift = det.window_start, det.shift
    else:
        status = det.status  # ambiguous | unavailable

    aligned, last_shift = align_ccl_series(ccl, sessions, segments, override_from, override_shift)
    tail_provisional = last_shift == 1 and is_tail_provisional(ccl, sessions)

    new_obj = CCLSeries(data=aligned, spot=ccl_obj.spot, as_of=ccl_obj.as_of)
    for b in bundles:
        if b.ccl_series is not None:
            b.ccl_series = new_obj

    result = AlignmentResult(
        status=status,
        applied=True,
        table_shift=table_shift,
        detected_shift=det.shift if det.status == "decided" else None,
        applied_shift_last_session=last_shift,
        margin=det.margin,
        corr_by_shift=det.corr_by_shift,
        n_sessions=det.n_sessions,
        window_start=_iso(det.window_start),
        window_end=_iso(det.window_end),
        pairs_used=pairs_used,
        tail_provisional=tail_provisional,
        provisional_from=_iso(override_from),
        aligned_from=_iso(sessions[0]),
        reason=det.reason,
    )
    _log_result(result)
    return result


def _log_result(r: AlignmentResult) -> None:
    msg = (
        "CCL alignment: status=%s table=%s detected=%s applied_last=%s margin=%s "
        "corr=%s window=%s→%s pairs=%d tail_provisional=%s"
    )
    args = (
        r.status, r.table_shift, r.detected_shift, r.applied_shift_last_session, r.margin,
        r.corr_by_shift, r.window_start, r.window_end, len(r.pairs_used), r.tail_provisional,
    )
    if r.status == STATUS_CONFIRMED:
        logger.info(msg, *args)
    elif r.status == STATUS_REGIME_CHANGE:
        logger.warning(
            "⚠ " + msg + " — posible cambio de régimen del CCL: tramo provisorio desde %s; "
            "actualizar data/sources/ccl_shift_regimes.json tras verificar (scripts/backtest_ccl_alignment.py)",
            *args, r.provisional_from,
        )
    else:
        logger.warning("⚠ " + msg + " — se aplica la tabla de regímenes sin cambios (%s)", *args, r.reason)
