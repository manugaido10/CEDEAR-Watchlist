"""outcomes_v2: second outcome measurement, parallel to outcome_tracker (v1).

Does NOT replace or modify v1 (outcomes.jsonl is never written here). Three
axes, applied in this fixed order (window -> entry -> exit), because the
incremental deltas depend on the order (HALLAZGOS_2026-11-27 §1.2, P4):

  window : bars strictly after data_date (= first session after the entry
           close, inclusive of the scan_date session), up to scan_date + 20d.
  entry  : the OPEN of that first session (next_open_ars). If open <= stop the
           trade is `no_entry_gap`: it counts as 0R in the headline R and is
           reported via n_entered / n_no_entry.
  exit   : two models. The stop TRIGGER is the same in both (low < stop, as
           v1), so states never differ between models, only R:
             S1: exit at the CLOSE of the triggering day (stop and targets).
             S2: stop fills at the stop level, or at the open if the bar opens
                 below it; targets fill at the close. S2 is the primary model.

R is in units of the original risk: (exit - entry) / (entry_price_ars - stop),
with entry_price_ars the signal's close-based entry.

Price basis: the price cache is rescaled retroactively by dividend adjustments,
while entry/stop are recorded raw. basis_factor = entry_price_ars / cache close
at data_date; when it differs from 1 by more than BASIS_ADJUSTED_TOL the window
bars are rescaled by it (BNG 09-23: R -1.48 -> -1.27, the recorded value). A
factor outside BASIS_ERROR_TOL is a data error (HWM near-misses: factor ~51).

Data-quality flags other than basis are FLAG-ONLY for now (bar_jump,
flat_zero_trigger): their thresholds are pending calibration. Phantom bars are
counted per ticker (flat OHLC, volume 0) but not excluded; the cross-ticker
phantom-day rule of P2 is not applied here.

Pure functions + one IO layer (load/save/backfill). Prices are read from the
local cache only (no network), so results are reproducible.
"""

from __future__ import annotations

import json
import logging
import math
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

OUTCOMES_V2_PATH = Path("data/reversal_tracking/outcomes_v2.jsonl")
SCHEMA_VERSION = 1

TARGET_PCTS = (0.05, 0.08)
MAX_DAYS = 20

# Provisional thresholds (calibration pending; see DECISIONS.md entry for P4).
BASIS_ADJUSTED_TOL = 0.001   # |factor-1| above this: rescale the window bars
BASIS_ERROR_TOL = 0.25       # |factor-1| above this: unresolved_data_error
BAR_JUMP_FLAG = 0.20         # close-to-close move: flag only (20-50 %)
BAR_JUMP_ERROR = 0.50        # close-to-close move above this: unresolved_data_error
                             # (audit rec. 1: "salta mas de 50 %")
RATIO_CHANGE_TOL = 0.03      # entry/exit within this of a split-like ratio: data error
RATIO_CHANGE_FACTORS = (2, 3, 4, 5, 8, 10, 15, 20, 25, 30, 40, 50, 100)
ROUND_TRIP_COST = 0.0111     # 0.555 % per side (report only; never used in states)

ST_STOP = "stop_hit"
ST_T5 = "target_5pct"
ST_T8 = "target_8pct"
ST_LATERAL = "lateral"
ST_PENDING = "pending"
ST_NO_ENTRY = "no_entry_gap"
ST_ERROR = "unresolved_data_error"          # the price DATA is wrong: excluded from statistics
ST_NOT_INSTRUMENTED = "not_instrumented"    # no entry bar could be identified (no instrumentation)

RESOLVED_STATES = {ST_STOP, ST_T5, ST_T8, ST_LATERAL}
EXIT_V1, EXIT_S1, EXIT_S2 = "V1", "S1", "S2"   # V1 = stop at the low (report steps only)

# Error reasons that are stored (deterministic). Transient ones are not stored.
ERR_MISSING_INPUTS = "missing_inputs"
ERR_INVALID_DENOMINATOR = "invalid_denominator"
ERR_NO_ENTRY_BAR = "no_entry_bar"       # status not_instrumented, not a data error
ERR_BASIS_MISMATCH = "basis_mismatch"
ERR_NO_OPEN = "no_open_price"
ERR_PRICE_JUMP = "price_jump"           # a bar moved more than BAR_JUMP_ERROR
ERR_RATIO_CHANGE = "ratio_change"       # entry/exit matches a split-like ratio
ERR_NO_HISTORY = "no_history"           # transient: not stored
ERR_NO_WINDOW_BARS = "no_window_bars"   # transient: not stored
_TRANSIENT = {ERR_NO_HISTORY, ERR_NO_WINDOW_BARS}


# ── Pure helpers ──────────────────────────────────────────────────────────────

def _finite(x) -> Optional[float]:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def window_bars(history: pd.DataFrame, after_ts: pd.Timestamp, deadline: date) -> pd.DataFrame:
    """Bars strictly after `after_ts` and on/before `deadline`."""
    w = history[history.index > after_ts]
    return w[[d.date() <= deadline for d in w.index]]


def basis_factor(history: pd.DataFrame, entry_bar_ts: pd.Timestamp, entry: float) -> Optional[float]:
    if entry_bar_ts not in history.index:
        return None
    c = _finite(history.loc[entry_bar_ts, "close"])
    return entry / c if c and c > 0 else None


def rescale(history: pd.DataFrame, factor: float) -> pd.DataFrame:
    out = history.copy()
    for col in ("open", "high", "low", "close"):
        if col in out.columns:
            out[col] = out[col] * factor
    return out


def is_ratio_change(entry: float, exit_price: float) -> bool:
    """entry/exit within RATIO_CHANGE_TOL of k or 1/k for a split-like k."""
    if not entry or not exit_price or entry <= 0 or exit_price <= 0:
        return False
    q = entry / exit_price
    return any(abs(q / k - 1) <= RATIO_CHANGE_TOL or abs(q * k - 1) <= RATIO_CHANGE_TOL
               for k in RATIO_CHANGE_FACTORS)


def cost_in_r(entry_price: Optional[float], risk0: Optional[float],
              round_trip: float = ROUND_TRIP_COST) -> Optional[float]:
    """Round-trip commission expressed in R: cost% * entry / original risk."""
    if not entry_price or not risk0 or risk0 <= 0:
        return None
    return round_trip * entry_price / risk0


def aggregate_by_date(pairs: Iterable[Tuple[str, Optional[float]]]) -> Dict:
    """pairs: (date, R). Rows with R None are dropped. Per-date means, then the
    mean and standard error ACROSS dates (rows of one date are not independent)."""
    by: Dict[str, List[float]] = {}
    n_rows = 0
    for d, r in pairs:
        if r is None:
            continue
        by.setdefault(d, []).append(r)
        n_rows += 1
    means = [sum(v) / len(v) for v in by.values()]
    n = len(means)
    if n == 0:
        return {"n_rows": 0, "n_dates": 0, "mean_per_row": float("nan"),
                "mean_per_date": float("nan"), "se_per_date": float("nan")}
    mu = sum(means) / n
    se = (sum((m - mu) ** 2 for m in means) / (n - 1)) ** 0.5 / n ** 0.5 if n > 1 else float("nan")
    return {"n_rows": n_rows, "n_dates": n,
            "mean_per_row": sum(x for v in by.values() for x in v) / n_rows,
            "mean_per_date": mu, "se_per_date": se}


def _flat_zero(row: pd.Series) -> bool:
    try:
        return bool(
            row["volume"] == 0 and row["open"] == row["high"]
            == row["low"] == row["close"]
        )
    except KeyError:
        return False


def simulate(
    bars: pd.DataFrame,
    *,
    entry_close: float,
    stop: float,
    scan_dt: date,
    deadline: date,
    today: date,
    enter_at_open: bool,
    exit_model: str,
    open_override: Optional[float] = None,
) -> Dict:
    """Walk `bars` (already windowed). Returns a result dict.

    enter_at_open False: entry = entry_close, no gap check (v1/(a) semantics).
    enter_at_open True : entry = first bar's open (or open_override); open <=
                         stop -> no_entry_gap.
    Trigger order per bar: stop (low < stop), then +8 %, then +5 % on the close,
    targets relative to the actual entry. R = (exit - entry) / (entry_close - stop).
    """
    risk0 = entry_close - stop
    res = {"status": ST_PENDING, "entry": None, "exit": None, "r": None,
           "days": None, "trigger_ts": None, "n_bars": len(bars)}
    if bars.empty:
        return res

    entry = entry_close
    if enter_at_open:
        entry = _finite(open_override) if open_override is not None else _finite(bars["open"].iloc[0])
        if entry is None or entry <= 0:
            res["status"] = ST_ERROR
            res["error"] = ERR_NO_OPEN
            return res
        if entry <= stop:
            res.update(status=ST_NO_ENTRY, entry=entry)
            return res
    res["entry"] = entry

    last_close = None
    for ts, row in bars.iterrows():
        d = ts.date()
        if d > deadline:
            break
        close = float(row["close"])
        low = float(row["low"]) if "low" in row and _finite(row["low"]) is not None else close
        opn = _finite(row["open"]) if "open" in row else None
        last_close = close
        days = (d - scan_dt).days

        if low < stop:
            if exit_model == EXIT_V1:
                ex = low
            elif exit_model == EXIT_S1:
                ex = close
            else:  # S2
                ex = opn if (opn is not None and opn < stop) else stop
            res.update(status=ST_STOP, exit=ex, days=days, trigger_ts=ts)
            break
        if close > entry * (1 + TARGET_PCTS[1]):
            res.update(status=ST_T8, exit=close, days=days, trigger_ts=ts)
            break
        if close > entry * (1 + TARGET_PCTS[0]):
            res.update(status=ST_T5, exit=close, days=days, trigger_ts=ts)
            break

    if res["status"] == ST_PENDING and today >= deadline and last_close is not None:
        res.update(status=ST_LATERAL, exit=last_close)
    if res["exit"] is not None and risk0 > 0:
        res["r"] = (res["exit"] - entry) / risk0
    return res


def data_flags(history: pd.DataFrame, entry_bar_ts: pd.Timestamp, bars: pd.DataFrame,
               trigger_ts: Optional[pd.Timestamp]) -> Dict:
    """Data-quality indicators over the evaluated bars. Here only the 20-50 % jump
    and the flat-zero trigger are FLAGS (no state change); the > 50 % jump is
    turned into unresolved_data_error by assess_v2."""
    closes = pd.concat([history.loc[[entry_bar_ts], ["close"]], bars[["close"]]])["close"]
    jump = _finite(closes.pct_change().abs().max()) or 0.0
    flat_bars = sum(_flat_zero(r) for _, r in bars.iterrows()) if "volume" in bars.columns else 0
    trig_flat = bool(trigger_ts is not None and "volume" in bars.columns
                     and _flat_zero(bars.loc[trigger_ts]))
    flags = []
    if BAR_JUMP_FLAG < jump <= BAR_JUMP_ERROR:
        flags.append("bar_jump")
    if trig_flat:
        flags.append("flat_zero_trigger")
    return {"max_bar_jump": round(jump, 4), "n_flat_zero_bars": int(flat_bars),
            "data_flags": flags}


# ── Single-signal assessment ──────────────────────────────────────────────────

def _error_record(base: Dict, reason: str) -> Dict:
    """Data error: the row stays out of every statistic (no R, no exit)."""
    status = ST_NOT_INSTRUMENTED if reason == ERR_NO_ENTRY_BAR else ST_ERROR
    base.update(status_v2=status, data_error_reason=reason, days_to_outcome=None,
                exit_s1_ars=None, exit_s2_ars=None, r_s1=None, r_s2=None, r_s2_open_risk=None)
    return base


def _entry_bar_ts(signal: Dict, v1: Optional[Dict], history: pd.DataFrame) -> Optional[pd.Timestamp]:
    from analysis.reversal.outcome_tracker import _match_entry_bar

    dd = signal.get("data_date") or (v1 or {}).get("entry_bar_date")
    if dd:
        return pd.Timestamp(dd)
    ts, _src = _match_entry_bar(history, signal["scan_date"], float(signal["entry_price_ars"]))
    return ts


def assess_v2(signal: Dict, history: Optional[pd.DataFrame], v1: Optional[Dict],
              today: date) -> Dict:
    """Build the outcomes_v2 record for one signal (status may be `pending`)."""
    scan_date = signal["scan_date"]
    scan_dt = datetime.strptime(scan_date, "%Y-%m-%d").date()
    deadline = scan_dt + timedelta(days=MAX_DAYS)
    entry = _finite(signal.get("entry_price_ars"))
    stop = _finite(signal.get("invalidation_level_ars"))

    base: Dict = {
        "scan_date": scan_date, "symbol": signal["symbol"],
        "data_date": signal.get("data_date"), "schema_version": SCHEMA_VERSION,
        "assessed_at": str(today),
        "status_v2": ST_PENDING, "data_error_reason": None,
        "entry_price_close_ars": entry, "stop_ars": stop, "risk_orig_ars": None,
        "entry_open_ars": None, "entry_session_date": None, "entry_gap_pct": None,
        "entered": None, "days_to_outcome": None,
        "exit_s1_ars": None, "exit_s2_ars": None,
        "r_s1": None, "r_s2": None, "r_s2_open_risk": None,
        "basis_factor": None, "basis_adjusted": False, "basis_uncertain": False,
        "ex_div_in_window": None, "ex_div_date_in_window": None,
        "max_bar_jump": None, "n_flat_zero_bars": None, "data_flags": [],
        "window_start_date": None, "window_start_is_scan_date": None, "n_valid_sessions": None,
        "status_v1": (v1 or {}).get("outcome") or signal.get("outcome_status"),
        "r_v1": (v1 or {}).get("r_multiple"),
    }
    if entry is None or stop is None:
        return _error_record(base, ERR_MISSING_INPUTS)
    risk0 = entry - stop
    base["risk_orig_ars"] = round(risk0, 4)
    if risk0 <= 0:
        return _error_record(base, ERR_INVALID_DENOMINATOR)
    if history is None or history.empty:
        return _error_record(base, ERR_NO_HISTORY)

    history = history.sort_index()
    ebt = _entry_bar_ts(signal, v1, history)
    f = basis_factor(history, ebt, entry) if ebt is not None else None
    if ebt is None or f is None:
        # No entry bar could be matched. If the recorded entry is wildly off the
        # price level around scan_date (HWM: ~51x), that is a basis/ratio DATA
        # error, not a missing instrumentation.
        near = history[history.index <= pd.Timestamp(scan_date)]
        c = _finite(near["close"].iloc[-1]) if not near.empty else None
        if c and c > 0:
            base["basis_factor"] = round(entry / c, 6)
            if abs(entry / c - 1.0) > BASIS_ERROR_TOL:
                return _error_record(base, ERR_BASIS_MISMATCH)
        return _error_record(base, ERR_NO_ENTRY_BAR)
    base["basis_factor"] = round(f, 6)
    if abs(f - 1.0) > BASIS_ERROR_TOL:
        return _error_record(base, ERR_BASIS_MISMATCH)
    if abs(f - 1.0) > BASIS_ADJUSTED_TOL:
        history = rescale(history, f)
        base["basis_adjusted"] = True

    bars = window_bars(history, ebt, deadline)
    if bars.empty:
        return _error_record(base, ERR_NO_WINDOW_BARS)
    first = bars.index[0]
    base["window_start_date"] = str(first.date())
    base["window_start_is_scan_date"] = first.date() == scan_dt

    rec_open = _finite((v1 or {}).get("next_open_ars"))
    kwargs = dict(entry_close=entry, stop=stop, scan_dt=scan_dt, deadline=deadline,
                  today=today, enter_at_open=True, open_override=rec_open)
    s2 = simulate(bars, exit_model=EXIT_S2, **kwargs)
    s1 = simulate(bars, exit_model=EXIT_S1, **kwargs)
    if s2["status"] == ST_ERROR:
        return _error_record(base, s2.get("error", ERR_NO_OPEN))

    op = s2["entry"]
    base.update(entry_open_ars=round(op, 2), entry_session_date=str(first.date()),
                entry_gap_pct=round(op / entry - 1.0, 4),
                entered=s2["status"] != ST_NO_ENTRY)
    eval_bars = bars.loc[:s2["trigger_ts"]] if s2["trigger_ts"] is not None else bars
    base.update(data_flags(history, ebt, eval_bars, s2["trigger_ts"]))
    base["n_valid_sessions"] = len(bars) - base["n_flat_zero_bars"]
    bar_open = _finite(bars["open"].iloc[0])
    if rec_open is not None and bar_open and abs(rec_open / bar_open - 1) > 0.005:
        base["data_flags"] = base["data_flags"] + ["next_open_mismatch"]

    exd = signal.get("ex_div_date")
    if exd:
        base["ex_div_in_window"] = bool(first.date() <= date.fromisoformat(exd) <= deadline)
        base["ex_div_date_in_window"] = exd if base["ex_div_in_window"] else None
    if base["ex_div_in_window"]:
        base["basis_uncertain"] = True

    if base["max_bar_jump"] > BAR_JUMP_ERROR:
        return _error_record(base, ERR_PRICE_JUMP)
    if s2["status"] in RESOLVED_STATES and is_ratio_change(op, s1["exit"]):
        return _error_record(base, ERR_RATIO_CHANGE)

    base["status_v2"] = s2["status"]
    base["days_to_outcome"] = s2["days"]
    if s2["status"] in RESOLVED_STATES:
        base.update(exit_s1_ars=round(s1["exit"], 2), exit_s2_ars=round(s2["exit"], 2),
                    r_s1=round(s1["r"], 4), r_s2=round(s2["r"], 4))
        if op - stop > 0:
            base["r_s2_open_risk"] = round((s2["exit"] - op) / (op - stop), 4)
        # Basis consistency check against the v1-recorded exit (same bar).
        v1x, v1d, v1s = (v1 or {}).get("exit_price_ars"), (v1 or {}).get("days_to_outcome"), (v1 or {}).get("outcome")
        if v1x and v1d is not None and v1s in (ST_STOP, ST_T5, ST_T8):
            ts = pd.Timestamp(scan_dt + timedelta(days=int(v1d)))
            if ts in history.index:
                px = float(history.loc[ts, "low" if v1s == ST_STOP else "close"])
                if abs(v1x / px - 1.0) > BASIS_ADJUSTED_TOL:
                    base["basis_uncertain"] = True
    return base


# ── IO ────────────────────────────────────────────────────────────────────────

def load_v2(path: Optional[Path] = None) -> Dict[Tuple[str, str], Dict]:
    path = path or OUTCOMES_V2_PATH
    if not path.exists():
        return {}
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            out[(r["scan_date"], r["symbol"])] = r
    return out


def save_v2(records: Iterable[Dict], path: Optional[Path] = None) -> None:
    path = path or OUTCOMES_V2_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def cache_history_loader(symbol: str) -> Optional[pd.DataFrame]:
    """Local price cache only (no network): reproducible backfills."""
    from data.cache import Cache

    return Cache().load_prices(symbol)


def build_v2(
    signals: List[Dict],
    v1_outcomes: Dict[Tuple[str, str], Dict],
    existing: Dict[Tuple[str, str], Dict],
    load_history: Callable[[str], Optional[pd.DataFrame]],
    today: date,
) -> Tuple[List[Dict], Dict[str, int]]:
    """Idempotent. Resolved/error records already present are kept untouched;
    pending signals are re-assessed; transient failures are not stored.
    Returns (records in signal order, counters)."""
    hist_cache: Dict[str, Optional[pd.DataFrame]] = {}
    out: List[Dict] = []
    stats = {"kept": 0, "new": 0, "pending": 0, "transient_skipped": 0, "not_tradeable": 0}
    for s in signals:
        key = (s["scan_date"], s["symbol"])
        if s.get("tradeable", True) is False:
            stats["not_tradeable"] += 1
            continue
        if key in existing:
            out.append(existing[key])
            stats["kept"] += 1
            continue
        if s["symbol"] not in hist_cache:
            hist_cache[s["symbol"]] = load_history(s["symbol"])
        rec = assess_v2(s, hist_cache[s["symbol"]], v1_outcomes.get(key), today)
        if rec["status_v2"] == ST_PENDING:
            stats["pending"] += 1
        elif rec["status_v2"] == ST_ERROR and rec["data_error_reason"] in _TRANSIENT:
            stats["transient_skipped"] += 1
        else:
            out.append(rec)
            stats["new"] += 1
    return out, stats


def refresh_outcomes_v2(
    signals_path: Optional[Path] = None,
    outcomes_v1_path: Optional[Path] = None,
    path: Optional[Path] = None,
    load_history: Callable[[str], Optional[pd.DataFrame]] = cache_history_loader,
    today: Optional[date] = None,
) -> Optional[Dict[str, int]]:
    """Run after outcome_tracker on every scan. FAIL-OPEN: any failure is a
    WARNING and returns None; it never raises and never touches v1 files."""
    try:
        # Resolve at call time from the live modules so that anything that
        # redirects v1 tracking (tests, sandboxes) redirects v2 with it.
        import analysis.reversal.outcome_tracker as _ot
        import analysis.reversal.signal_registry as _sr

        signals_path = signals_path or _sr.SIGNALS_PATH
        outcomes_v1_path = outcomes_v1_path or _ot.OUTCOMES_PATH
        path = path or Path(outcomes_v1_path).with_name("outcomes_v2.jsonl")

        def _jsonl(p: Path) -> List[Dict]:
            if not p.exists():
                return []
            return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]

        signals = _jsonl(signals_path)
        v1 = {(o["scan_date"], o["symbol"]): o for o in _jsonl(outcomes_v1_path)}
        existing = load_v2(path)
        records, stats = build_v2(signals, v1, existing, load_history, today or date.today())
        if stats["new"] or len(records) != len(existing):
            save_v2(records, path)
        logger.info("outcomes_v2: %s", stats)
        return stats
    except Exception as exc:
        logger.warning("outcomes_v2: refresh failed (%s: %s) — v1 tracking unaffected",
                       type(exc).__name__, exc)
        return None


# ── Step decomposition (report) ───────────────────────────────────────────────

def assess_steps(signal: Dict, history: pd.DataFrame, v1: Dict, today: date) -> Optional[Dict]:
    """v1 -> (a) window -> (b) entry -> (c) exit, on one signal.

    Returns None when the row cannot be decomposed (no entry bar / no recorded
    next_open / basis error). Same basis handling as assess_v2.
    """
    scan_dt = datetime.strptime(signal["scan_date"], "%Y-%m-%d").date()
    deadline = scan_dt + timedelta(days=MAX_DAYS)
    entry, stop = _finite(signal.get("entry_price_ars")), _finite(signal.get("invalidation_level_ars"))
    if entry is None or stop is None:
        return None
    history = history.sort_index()
    ebt = _entry_bar_ts(signal, v1, history)
    f = basis_factor(history, ebt, entry) if ebt is not None else None
    if f is None or abs(f - 1.0) > BASIS_ERROR_TOL:
        return None
    if abs(f - 1.0) > BASIS_ADJUSTED_TOL:
        history = rescale(history, f)
    common = dict(entry_close=entry, stop=stop, scan_dt=scan_dt, deadline=deadline, today=today)
    w_v1 = history[history.index > pd.Timestamp(scan_dt)]
    w_v1 = w_v1[[d.date() <= deadline for d in w_v1.index]]
    w_new = window_bars(history, ebt, deadline)
    op = _finite((v1 or {}).get("next_open_ars"))
    return {
        "v1": simulate(w_v1, enter_at_open=False, exit_model=EXIT_V1, **common),
        "a": simulate(w_new, enter_at_open=False, exit_model=EXIT_V1, **common),
        "b": simulate(w_new, enter_at_open=True, exit_model=EXIT_V1, open_override=op, **common),
        "s1": simulate(w_new, enter_at_open=True, exit_model=EXIT_S1, open_override=op, **common),
        "s2": simulate(w_new, enter_at_open=True, exit_model=EXIT_S2, open_override=op, **common),
        "window_start_is_scan_date": bool(len(w_new) and w_new.index[0].date() == scan_dt),
    }
