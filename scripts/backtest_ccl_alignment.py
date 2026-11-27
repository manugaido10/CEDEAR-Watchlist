"""Backtest of the per-run CCL alignment check (Decision #43, P1).

Reproduces, on the cached CCL history, the evidence behind the detector's
window and thresholds, using the SAME functions run_reversals uses
(data/ccl_alignment.py):

Exit code 0 when the acceptance holds (no wrong decision from 2020-05 on and
UGP ≤ 0.5 pp), 2 otherwise.

1. Rolling windows of WINDOW_SESSIONS common sessions from --start on. Each
   window lying entirely inside one segment of data/sources/ccl_shift_regimes.json
   is scored against that segment's shift: decided-correct / decided-wrong /
   ambiguous. Windows touching the approximate 2020 boundary are skipped.
2. UGP: daily standard deviation of (CEDEAR in USD − ADR) returns since
   2026-09-08, with the raw and with the aligned CCL (acceptance: ≤ 0.5 pp aligned).
3. Last 30 sessions' decision trail around the 2026-09-08 change.

Downloads full daily history for the four local/ADR pairs and UGP from
yfinance (unadjusted closes). Read-only: writes nothing to the repo or cache.

Usage:
    python scripts/backtest_ccl_alignment.py [--start 2015-01-01]

--start defaults to 2015-01-01: before mid-2014 yfinance's local closes are
unusable (implied CCL daily σ ≈ 30 %).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data import ccl_alignment as ca  # noqa: E402
from data.cache import Cache  # noqa: E402

_UNCERTAIN = (pd.Timestamp("2020-03-01"), pd.Timestamp("2020-05-01"))


def _history(symbol: str) -> pd.DataFrame:
    import yfinance as yf

    df = yf.Ticker(symbol).history(start="2012-12-01", auto_adjust=False)
    df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
    df.columns = [c.lower() for c in df.columns]
    return df[["close", "volume"]]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2015-01-01")
    args = ap.parse_args()
    start = pd.Timestamp(args.start)

    ccl = Cache().load_ccl()
    if ccl is None:
        print("No cached CCL history.")
        return 1
    segments = ca.load_regimes()
    local = {l: _history(l) for l, _ in ca.PAIRS}
    adr = {a: _history(a) for _, a in ca.PAIRS}
    sessions = ca.byma_sessions(local)
    implied = ca.implied_returns(local, adr, sessions)
    df = ca.candidate_returns(implied, ccl, sessions)
    df = df[df.index >= start]
    n = ca.WINDOW_SESSIONS
    print(f"CCL {ccl.index[0].date()} → {ccl.index[-1].date()} ({len(ccl)} days); "
          f"{len(df)} common sessions from {start.date()}; window {n}, "
          f"margin ≥ {ca.MIN_MARGIN}, corr ≥ {ca.MIN_CORR}")

    rows = []
    for i in range(n, len(df) + 1):
        w = df.iloc[i - n:i]
        a, b = w.index[0], w.index[-1]
        if a < _UNCERTAIN[1] and b >= _UNCERTAIN[0]:
            continue
        exp = ca.shift_for(a, segments)
        if ca.shift_for(b, segments) != exp:
            continue  # window straddles a regime boundary
        d = ca.decide(w)
        rows.append((b, exp, d.status, d.shift))
    r = pd.DataFrame(rows, columns=["end", "expected", "status", "shift"])
    decided = r.status == "decided"
    wrong = decided & (r["shift"] != r.expected)
    print(f"\nWindows inside known regimes: {len(r)}")
    print(f"  decided correct: {(decided & ~wrong).sum()}   decided WRONG: {wrong.sum()}   "
          f"ambiguous: {(~decided).sum()} ({(~decided).mean():.1%})")
    for since in ("2022-01-01", "2025-01-01", "2026-09-08"):
        m = r.end >= pd.Timestamp(since)
        if m.any():
            print(f"  since {since}: windows {m.sum()}, ambiguous {(~decided[m]).mean():.1%}, "
                  f"wrong {wrong[m].sum()}")
    print(pd.DataFrame({"windows": r.groupby("expected").size(),
                        "wrong": wrong.groupby(r.expected).sum()}).to_string())
    if wrong.any():
        print("  wrong windows:", ", ".join(d.date().isoformat() for d in r.end[wrong]))

    # Decision trail around the latest change
    print("\nDecision trail (window end → status/shift/margin):")
    for i in range(max(n, len(df) - 75), len(df) + 1, 5):
        d = ca.decide(df.iloc[i - n:i])
        print(f"  {d.window_end.date()}  {d.status:<9} {d.shift!s:>4}  margin={d.margin}")

    # UGP acceptance
    aligned, _ = ca.align_ccl_series(ccl, sessions, segments)
    ugp_ba, ugp = _history("UGP.BA"), _history("UGP")
    live = ugp_ba[ugp_ba.volume > 0].close
    x = pd.concat([live.rename("ba"), ugp.close.rename("adr")], axis=1).dropna()
    x = x[x.index >= pd.Timestamp("2026-08-01")]
    out = {}
    for name, series in (("raw", ccl), ("aligned", aligned)):
        usd = x.ba / series.sort_index().asof(x.index).to_numpy()
        diff = (np.log(usd).diff() - np.log(x.adr).diff()) * 100
        out[name] = diff[diff.index >= pd.Timestamp("2026-09-08")].std()
    print(f"\nUGP daily σ of (CEDEAR USD − ADR) since 2026-09-08: raw {out['raw']:.2f} pp, "
          f"aligned {out['aligned']:.2f} pp (acceptance ≤ 0.50)")
    # Acceptance (HALLAZGOS P1): no wrong decision from abr-2020 on, UGP ≤ 0.5 pp.
    wrong_accept = int(wrong[r.end >= _UNCERTAIN[1]].sum())
    print(f"Acceptance: wrong decisions since {_UNCERTAIN[1].date()} = {wrong_accept}")
    return 0 if wrong_accept == 0 and out["aligned"] <= 0.5 else 2


if __name__ == "__main__":
    sys.exit(main())
