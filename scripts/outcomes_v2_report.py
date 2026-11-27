"""Read-only step decomposition v1 -> (a) window -> (b) entry -> (c) exit (P4).

Population: signals whose v1 outcome is resolved and carries next_open_ars
(the 76 rows of HALLAZGOS §1.2). R is in original-risk units
((exit - entry) / (entry_price_ars - stop)). Prices from the local cache.
Writes nothing.

Steps: v1 (stop exit at the DAY'S LOW, window > scan_date) ->
(a) window from the first session after data_date, entry at the close ->
(b) entry at next_open_ars, same exit rule as v1 (low) ->
(c) exit model S1 (close of the triggering day) / S2 (stop level or open if
    it gaps below; primary). S1 and S2 are alternatives, both against (b).

Net R subtracts the round-trip commission (1.11 % = 0.555 % per side) of the
traded notional, converted to R per row with the original risk. No-entry rows
cost nothing. Aggregation by date groups rows by scan_date.

Two views are always printed: the CLEAN corpus (scan_date >= --since, default
2026-09-11, the corpus left by the audit) and the TOTAL. Each shows n rows and
n dates. The decision point (~36 dates) counts only the clean corpus, over dates
with at least one outcomes_v2 row in stop_hit / target_* / lateral / no_entry_gap
(never unresolved_data_error, not_instrumented, suppressed or pending); the same
count over the 76-row population is shown until the two converge.

Usage:
    python -m scripts.outcomes_v2_report [--since YYYY-MM-DD]
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import date
from pathlib import Path

import numpy as np

from analysis.reversal.outcomes_v2 import (
    RESOLVED_STATES, ST_ERROR, ST_NO_ENTRY, ST_NOT_INSTRUMENTED, ROUND_TRIP_COST,
    aggregate_by_date, assess_steps, assess_v2, cache_history_loader, cost_in_r,
)

RESOLVED = {"stop_hit", "target_5pct", "target_8pct", "lateral"}
CLEAN_SINCE = "2026-09-11"          # clean corpus left by the audit
DECISION_POINT_DATES = 36           # ~36 dates, counted on the clean corpus only
MEASURED_STATES = RESOLVED_STATES | {ST_NO_ENTRY}
STEPS = ["v1", "a", "b", "s1", "s2"]
LABEL = {"v1": "v1 (stop at the low)", "a": "(a) window", "b": "(b) entry at open",
         "s1": "(c) exit S1 (close)", "s2": "(c) exit S2 (stop lvl/open)"}
PREV = {"a": "v1", "b": "a", "s1": "b", "s2": "b"}


def _load(p):
    return [json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


def collect(signals, v1, today):
    rows, skipped, hist = [], [], {}
    sig = {(s["scan_date"], s["symbol"]): s for s in signals}
    for k, o in v1.items():
        if o["outcome"] not in RESOLVED or o.get("next_open_ars") is None or o.get("entry_bar_date") is None:
            continue
        s = sig.get(k)
        if s is None:
            continue
        if o["symbol"] not in hist:
            hist[o["symbol"]] = cache_history_loader(o["symbol"])
        h = hist[o["symbol"]]
        st = assess_steps(s, h, o, today) if h is not None else None
        if st is None:
            skipped.append(k)
            continue
        risk0 = s["entry_price_ars"] - s["invalidation_level_ars"]
        rec = assess_v2(s, h, o, today)
        rows.append({"key": k, "date": k[0], "st": st, "risk0": risk0, "v2": rec["status_v2"],
                     "v2_reason": rec["data_error_reason"]})
    return rows, skipped


def _r(row, step, net):
    """(R, counted) for a row at a step. No-entry rows count as 0R; None if R undefined."""
    res = row["st"][step]
    if res["status"] == ST_NO_ENTRY:
        return 0.0
    if res["r"] is None:
        return None
    if not net:
        return res["r"]
    c = cost_in_r(res["entry"], row["risk0"])
    return None if c is None else res["r"] - c


def _fmt(x, w=8, d=3, sign=False):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return " " * (w - 1) + "—"
    return f"{x:+{w}.{d}f}" if sign else f"{x:{w}.{d}f}"


def print_population(name, rows, zero_fill):
    """zero_fill: rows without a valid R count as 0R (76-row view)."""
    def val(row, step, net):
        v = _r(row, step, net)
        return (0.0 if v is None else v) if zero_fill else v

    if zero_fill:
        use = rows
    else:
        use = [r for r in rows if all(_r(r, s, False) is not None and r["st"][s]["status"] != ST_NO_ENTRY
                                      for s in STEPS)]
        use = [r for r in use if all(_r(r, s, True) is not None for s in STEPS)]
    n_dates = len({r["date"] for r in use})
    print(f"\n══ {name}: n={len(use)} filas, {n_dates} fechas ══")
    if not use:
        return use
    print(f"{'paso':<30}{'R medio':>9}{'Δ vs paso':>10}{'Δ acum v1':>10}  {'R neto':>8}{'Δ vs paso':>10}{'Δ acum v1':>10}  {'cambios estado':>14}")
    m, mn = {}, {}
    for s in STEPS:
        m[s] = float(np.mean([val(r, s, False) for r in use]))
        mn[s] = float(np.mean([val(r, s, True) for r in use]))
    for s in STEPS:
        p = PREV.get(s)
        ch = "" if p is None else sum(r["st"][s]["status"] != r["st"][p]["status"] for r in use)
        print(f"{LABEL[s]:<30}{_fmt(m[s])}{_fmt(m[s]-m[p], 10, 3, True) if p else ' '*10}"
              f"{_fmt(m[s]-m['v1'], 10, 3, True) if p else ' '*10}  {_fmt(mn[s])}"
              f"{_fmt(mn[s]-mn[p], 10, 3, True) if p else ' '*10}{_fmt(mn[s]-mn['v1'], 10, 3, True) if p else ' '*10}  {str(ch):>14}")
    print("  (S1 y S2 son modelos alternativos: su Δ vs paso es contra (b), no acumulativo.)")

    print(f"\n  Por fecha (scan_date) — {name}")
    print(f"  {'paso':<30}{'n filas':>8}{'n fechas':>9}{'R/fila':>9}{'R/fecha':>9}{'EE':>8}   {'neto R/fecha':>13}{'EE':>8}")
    for s in STEPS:
        g = aggregate_by_date((r["date"], val(r, s, False)) for r in use)
        n = aggregate_by_date((r["date"], val(r, s, True)) for r in use)
        print(f"  {LABEL[s]:<30}{g['n_rows']:>8}{g['n_dates']:>9}{_fmt(g['mean_per_row'],9)}"
              f"{_fmt(g['mean_per_date'],9)}{_fmt(g['se_per_date'],8)}   {_fmt(n['mean_per_date'],13)}{_fmt(n['se_per_date'],8)}")
    return use


def decision_point_dates(records, since):
    """Distinct scan_dates >= since with >=1 outcomes_v2 row in a measured state
    (stop_hit/target_*/lateral/no_entry_gap). Data errors, not_instrumented and
    pending never count; suppressed rows live in another file."""
    return sorted({r["scan_date"] for r in records
                   if r["scan_date"] >= since and r["status_v2"] in MEASURED_STATES
                   and not r.get("counterfactual")})


def print_transitions(rows):
    def cats(a, b):
        return Counter((r["st"][a]["status"], r["st"][b]["status"]) for r in rows
                       if r["st"][a]["status"] != r["st"][b]["status"])
    for name, (x, y) in {"(a) ventana": ("v1", "a"), "(b) entrada": ("a", "b")}.items():
        print(f"\nCambios de estado {name}: {sum(cats(x, y).values())}")
        for (f, t), n in sorted(cats(x, y).items()):
            print(f"   {f:>12} -> {t:<13} {n}")
    ne = sum(r["st"]["b"]["status"] == ST_NO_ENTRY for r in rows)
    print(f"\nv1 -> (b): {sum(cats('v1', 'b').values())} cambios netos | n_entered={len(rows) - ne} n_no_entry={ne}")


def print_file_view(label, recs):
    print(f"\n  [{label}] outcomes_v2.jsonl: {len(recs)} registros, {len({r['scan_date'] for r in recs})} fechas")
    print("    por estado:", dict(Counter(r["status_v2"] for r in recs)))
    print("    errores de DATO (fuera de estadísticas):",
          dict(Counter(r["data_error_reason"] for r in recs if r["status_v2"] == ST_ERROR)))
    print("    SIN INSTRUMENTACIÓN (no es error de dato):",
          sum(r["status_v2"] == ST_NOT_INSTRUMENTED for r in recs))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--since", default=CLEAN_SINCE,
                    help=f"first scan_date of the clean corpus (default {CLEAN_SINCE})")
    since = ap.parse_args(argv).since
    date.fromisoformat(since)  # fail fast on a malformed date

    signals = _load("data/reversal_tracking/signals.jsonl")
    v1 = {(o["scan_date"], o["symbol"]): o for o in _load("data/reversal_tracking/outcomes.jsonl")}
    rows, skipped = collect(signals, v1, date.today())
    clean = [r for r in rows if r["date"] >= since]
    print(f"filas={len(rows)} omitidas={skipped}")
    print(f"costo ida y vuelta = {ROUND_TRIP_COST:.4f} del nocional ({ROUND_TRIP_COST/2:.5f} por punta); en R = costo × entrada / risk_orig")
    print(f"corpus limpio: scan_date >= {since} ({len(clean)} filas, {len({r['date'] for r in clean})} fechas) | "
          f"total: {len(rows)} filas, {len({r['date'] for r in rows})} fechas")

    p = Path("data/reversal_tracking/outcomes_v2.jsonl")
    recs = _load(p) if p.exists() else []
    views = [(f"CORPUS LIMPIO (scan_date >= {since})", clean, [r for r in recs if r["scan_date"] >= since]),
             ("TOTAL", rows, recs)]
    for label, rws, vrecs in views:
        print(f"\n{'█' * 3} {label}: {len(rws)} filas, {len({r['date'] for r in rws})} fechas")
        c = Counter(r["v2"] for r in rws)
        print("estado v2 de la población:", dict(c),
              "| errores de dato:", [(r["key"], r["v2_reason"]) for r in rws if r["v2"] == ST_ERROR],
              "| sin instrumentación:", c.get(ST_NOT_INSTRUMENTED, 0))
        print_population(f"{label} — filas con R válido en todos los pasos", rws, zero_fill=False)
        print_population(f"{label} — zero-fill (sin entrada = 0R; R indefinido = 0R)", rws, zero_fill=True)
        if rws:
            print_transitions(rws)
        if p.exists():
            print_file_view(label, vrecs)

    dp = decision_point_dates(recs, since)
    pop = len({r["date"] for r in clean})
    print(f"\n══ PUNTO DE DECISIÓN: {len(dp)} / {DECISION_POINT_DATES} fechas (corpus limpio, "
          f"outcomes_v2 en stop/target/lateral/no_entry_gap) ══")
    print(f"   sobre la población de 76 (scan_date >= {since}): {pop} fechas"
          + ("" if pop == len(dp) else f"  — difieren en {abs(pop - len(dp))}: aún no convergen"))
    sp = Path("data/reversal_tracking/outcomes_v2_suppressed.jsonl")
    if sp.exists():
        srecs = _load(sp)
        print(f"   (suprimidas contrafactuales: {len(srecs)} filas en outcomes_v2_suppressed.jsonl, "
              f"fuera de todo lo anterior)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
