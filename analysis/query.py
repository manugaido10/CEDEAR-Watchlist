"""Read-only DuckDB query layer over the five reversal tracking JSONL files.

Usage:
    from analysis.query import get_connection
    conn = get_connection()
    df = conn.execute(Q_GATE_EV, {"from_date": "2026-06-01", "to_date": "2026-09-30"}).df()

Views registered (all read-only; source files are never modified):
    signals              — published reversal signals        (signals.jsonl)
    near_misses          — near-miss records                  (near_misses.jsonl)
    outcomes             — resolved outcomes / published sigs  (outcomes.jsonl)
    near_miss_outcomes   — hypothetical outcomes / near-misses (near_miss_outcomes.jsonl)
    regime_snapshots     — per-scan universe metrics           (regime_snapshots.jsonl)

Dedup views (Decision #21 / #27 criteria):
    sig_dup_keys   — (scan_date, symbol) pairs to exclude from signal analysis
    nm_dup_keys    — (scan_date, symbol) pairs to exclude from near-miss analysis

    Criteria (identical to _is_exposure_duplicate and _is_near_miss_exposure_duplicate
    in outcome_tracker.py and near_miss_outcomes.py):
      1. Same ticker appeared within 7 days before this record.
      2. Entry price moved < 3% vs. the most recent prior entry.
      3. The prior record was still pending at this scan_date.

    All canonical queries below apply the dedup automatically via NOT EXISTS.
    Use the _RAW suffix variant (see Q_GATE_EV note) to bypass if needed.

────────────────────────────────────────────────────────────────────────────────
STALENESS FILTER — is_safe(staleness_risk)
────────────────────────────────────────────────────────────────────────────────
Replicates _is_safe() from near_miss_outcomes.py (Decision #27).
NULL = safe by construction for pre-instrumentation and post-fix records.
'confirmed_stale' and 'uncertain' are explicitly unsafe.

    is_safe(price_staleness_risk)          -- historical safe-only corpus
    is_safe(price_staleness_risk)
        AND scan_date >= CACHE_FIX_DATE    -- post-fix corpus (Decision #27e)

CACHE_FIX_DATE = '2026-09-11'. The gap 2026-09-03 to 2026-09-10 is
confirmed_stale for signals (Decision #30) and un-audited for near-misses.
NULL in that window does NOT mean safe — the date anchor excludes the gap.

All canonical queries use both guards (is_safe + date anchor).

────────────────────────────────────────────────────────────────────────────────
ARRAY COLUMNS
────────────────────────────────────────────────────────────────────────────────
catalysts (signals):             VARCHAR[]
failed_criteria (near_misses,
                 near_miss_outcomes): VARCHAR[]

Two query variants for catalysts — they answer different questions:

  Q_CATALYST_PERFORMANCE  — UNNEST, one row per catalyst.
    Answers: "Which catalyst type predicts best?"
    Does NOT answer: total win rate or n (over-counts multi-catalyst signals).

  Q_SIGNAL_PERFORMANCE    — one row per (scan_date, symbol).
    Answers: "What is the aggregate win rate / total n?"
    Does NOT answer: per-catalyst breakdown.

────────────────────────────────────────────────────────────────────────────────
NESTED STRUCT COLUMNS
────────────────────────────────────────────────────────────────────────────────
analyst_revision (signals):
    STRUCT(trend VARCHAR, n_analysts BIGINT)
    Access: analyst_revision.trend, analyst_revision.n_analysts

fx_context (signals):
    STRUCT(ccl_at_scan, underlying_symbol, cedears_per_underlying,
           pct_change_ars_5d/20d, pct_change_ccl_5d/20d,
           pct_change_usd_implied_5d/20d, fx_context_source)
    Access: fx_context.pct_change_usd_implied_5d

────────────────────────────────────────────────────────────────────────────────
MARGINS COLUMN (near_misses) — JSON VARCHAR
────────────────────────────────────────────────────────────────────────────────
Gate-specific keys; forced to JSON VARCHAR for resilience to future gates.
Extraction patterns:

    rsi_gap (rsi_out_of_range):
        (margins->>'rsi_gap')::DOUBLE

    vol_ratio_gap (vol_ratio_high):
        (margins->>'vol_ratio_gap')::DOUBLE

    hypothetical_score (no_catalyst):
        (margins->>'hypothetical_score')::DOUBLE

    vol_ratio actual (vol_ratio_high):
        (margins->>'vol_ratio')::DOUBLE
"""

from __future__ import annotations

from pathlib import Path

import duckdb

from analysis.reversal.near_miss_outcomes import CACHE_FIX_DATE

# ── Constants ─────────────────────────────────────────────────────────────────

_TRACKING_DIR = Path(__file__).parent.parent / "data" / "reversal_tracking"

_VIEWS: dict[str, Path] = {
    "signals":            _TRACKING_DIR / "signals.jsonl",
    "near_misses":        _TRACKING_DIR / "near_misses.jsonl",
    "outcomes":           _TRACKING_DIR / "outcomes.jsonl",
    "near_miss_outcomes": _TRACKING_DIR / "near_miss_outcomes.jsonl",
    "regime_snapshots":   _TRACKING_DIR / "regime_snapshots.jsonl",
}

# sample_size=-1: scan ALL rows for schema inference — safe when files exceed
# the 20480-row default and heterogeneous fields appear only in late records.
# union_by_name: merges column sets across rows with different keys.
_READ_OPTS = (
    "format='newline_delimited', "
    "sample_size=-1, "
    "union_by_name=true, "
    "ignore_errors=true"
)

# Dedup constants — mirror Python constants in outcome_tracker.py / near_miss_outcomes.py.
_DEDUP_DAYS = 7
_DEDUP_PRICE_THRESHOLD = 0.03


# ── Connection factory ────────────────────────────────────────────────────────

def get_connection() -> duckdb.DuckDBPyConnection:
    """Return an in-memory DuckDB connection with all views and dedup views registered.

    The connection is read-only by intent: no DuckDB file is created, and
    no SQL in this module or the canonical queries writes to any JSONL file.
    Call .df() on results to get pandas DataFrames (zero-copy via Arrow).
    """
    conn = duckdb.connect(database=":memory:")

    # ── Data views ────────────────────────────────────────────────────────────
    for view_name, path in _VIEWS.items():
        if view_name == "near_misses":
            # margins has gate-specific keys — cast auto-inferred STRUCT to
            # JSON VARCHAR for resilience to future gates with new key names.
            conn.execute(f"""
                CREATE VIEW near_misses AS
                SELECT * REPLACE (margins::VARCHAR AS margins)
                FROM read_json_auto('{path}', {_READ_OPTS})
            """)
        else:
            conn.execute(
                f"CREATE VIEW {view_name} AS "
                f"SELECT * FROM read_json_auto('{path}', {_READ_OPTS})"
            )

    # ── Staleness macro ───────────────────────────────────────────────────────
    # Replicates _is_safe() from near_miss_outcomes.py (Decision #27).
    # NULL = safe by construction; only explicitly non-safe records fail.
    conn.execute(
        "CREATE MACRO is_safe(staleness_risk) AS "
        "(staleness_risk IS NULL OR staleness_risk = 'safe')"
    )

    # ── Dedup view: published signals ─────────────────────────────────────────
    # Returns (scan_date, symbol) pairs that are exposure duplicates, replicating
    # _is_exposure_duplicate() from outcome_tracker.py (Decision #21).
    # Criteria:
    #   1. Same ticker within 7 days of a prior signal.
    #   2. Entry price moved < 3% vs. most recent prior entry.
    #   3. Prior signal still pending when this signal was published.
    #
    # Both current and prior signals are restricted to safe records so that an
    # unsafe prior (e.g. confirmed_stale from Decision #30) cannot suppress a
    # valid safe entry — mirroring Python's filter-before-dedup order.
    conn.execute(f"""
        CREATE VIEW sig_dup_keys AS
        WITH ranked_priors AS (
            SELECT
                s_c.scan_date           AS curr_date,
                s_c.symbol,
                s_c.entry_price_ars     AS curr_entry,
                s_p.scan_date           AS prior_date,
                s_p.entry_price_ars     AS prior_entry,
                ROW_NUMBER() OVER (
                    PARTITION BY s_c.scan_date, s_c.symbol
                    ORDER BY s_p.scan_date DESC
                ) AS rn
            FROM signals s_c
            JOIN signals s_p ON
                s_p.symbol    = s_c.symbol
                AND s_p.scan_date < s_c.scan_date
                AND s_p.scan_date >= s_c.scan_date - INTERVAL {_DEDUP_DAYS} DAYS
                AND is_safe(s_p.price_staleness_risk)
            WHERE s_c.entry_price_ars IS NOT NULL
              AND is_safe(s_c.price_staleness_risk)
        ),
        most_recent_prior AS (
            SELECT curr_date, symbol, curr_entry, prior_date, prior_entry
            FROM ranked_priors
            WHERE rn = 1
        )
        SELECT mrp.curr_date AS scan_date, mrp.symbol
        FROM most_recent_prior mrp
        LEFT JOIN outcomes o ON o.scan_date = mrp.prior_date AND o.symbol = mrp.symbol
        WHERE
            -- Criterion 2: price moved < 3% (NULL prior_entry skips check)
            (mrp.prior_entry IS NULL
             OR ABS(mrp.curr_entry - mrp.prior_entry) / mrp.prior_entry < {_DEDUP_PRICE_THRESHOLD})
            -- Criterion 3: prior still pending at curr_date
            AND (
                o.outcome IS NULL
                OR o.days_to_outcome IS NULL
                OR DATEDIFF('day', mrp.prior_date, mrp.curr_date) < o.days_to_outcome
            )
    """)

    # ── Dedup view: near-miss records ─────────────────────────────────────────
    # Replicates _is_near_miss_exposure_duplicate() from near_miss_outcomes.py.
    # Same 3-criterion logic; cross-gate (gate label is irrelevant for dedup).
    # Differences from signals: prior side also requires entry_price_ars IS NOT NULL.
    #
    # Both sides filtered by is_safe() so unsafe priors from the 2026-09-03–10
    # gap (Decision #30) cannot suppress valid safe entries. Matches Python's
    # filter-before-dedup order in _compute_gate_groups(filter_safe_only=True).
    conn.execute(f"""
        CREATE VIEW nm_dup_keys AS
        WITH ranked_priors AS (
            SELECT
                nm_c.scan_date          AS curr_date,
                nm_c.symbol,
                nm_c.entry_price_ars    AS curr_entry,
                nm_p.scan_date          AS prior_date,
                nm_p.entry_price_ars    AS prior_entry,
                ROW_NUMBER() OVER (
                    PARTITION BY nm_c.scan_date, nm_c.symbol
                    ORDER BY nm_p.scan_date DESC
                ) AS rn
            FROM near_misses nm_c
            JOIN near_misses nm_p ON
                nm_p.symbol    = nm_c.symbol
                AND nm_p.scan_date < nm_c.scan_date
                AND nm_p.scan_date >= nm_c.scan_date - INTERVAL {_DEDUP_DAYS} DAYS
                AND nm_p.entry_price_ars IS NOT NULL
                AND is_safe(nm_p.price_staleness_risk)
            WHERE nm_c.entry_price_ars IS NOT NULL
              AND is_safe(nm_c.price_staleness_risk)
        ),
        most_recent_prior AS (
            SELECT curr_date, symbol, curr_entry, prior_date, prior_entry
            FROM ranked_priors
            WHERE rn = 1
        )
        SELECT mrp.curr_date AS scan_date, mrp.symbol
        FROM most_recent_prior mrp
        LEFT JOIN near_miss_outcomes nmo
            ON nmo.scan_date = mrp.prior_date AND nmo.symbol = mrp.symbol
        WHERE
            (mrp.prior_entry IS NULL
             OR ABS(mrp.curr_entry - mrp.prior_entry) / mrp.prior_entry < {_DEDUP_PRICE_THRESHOLD})
            AND (
                nmo.outcome IS NULL
                OR nmo.days_to_outcome IS NULL
                OR DATEDIFF('day', mrp.prior_date, mrp.curr_date) < nmo.days_to_outcome
            )
    """)

    return conn


# ── Canonical queries ─────────────────────────────────────────────────────────
# All queries apply is_safe() + date anchor + dedup (NOT EXISTS nm/sig_dup_keys).
# Parameters: pass as conn.execute(QUERY, {"from_date": "...", "to_date": "..."})
#
# Default reliable corpus: is_safe(...) AND scan_date >= CACHE_FIX_DATE.
# To use the full historical safe corpus: pass from_date="2026-01-01" (covers all).


# Q1 — Gate calibration: win_rate and avg_R per failed_gate (near_miss corpus).
# Primary Fase B query. Dedup-correct: same n as Python _compute_gate_groups().
Q_GATE_EV = """
WITH base AS (
    SELECT
        UNNEST(nm.failed_criteria)  AS failed_gate,
        nmo.outcome,
        nmo.r_multiple
    FROM near_misses nm
    JOIN near_miss_outcomes nmo USING (scan_date, symbol)
    WHERE nmo.outcome NOT IN ('unresolved_no_data', 'pending')
      AND nmo.r_multiple_skip_reason IS NULL
      AND is_safe(nm.price_staleness_risk)
      AND nm.scan_date >= $from_date
      AND nm.scan_date <= $to_date
      AND NOT EXISTS (
          SELECT 1 FROM nm_dup_keys d
          WHERE d.scan_date = nm.scan_date AND d.symbol = nm.symbol
      )
)
SELECT
    failed_gate,
    COUNT(*)                                                              AS n,
    ROUND(AVG(r_multiple), 3)                                            AS avg_r,
    ROUND(STDDEV(r_multiple), 3)                                         AS std_r,
    ROUND(AVG((outcome IN ('target_5pct','target_8pct'))::INT)::DOUBLE, 3) AS win_rate,
    COUNT(*) FILTER (WHERE outcome IN ('target_5pct','target_8pct'))     AS wins,
    COUNT(*) FILTER (WHERE outcome = 'stop_hit')                         AS stops,
    COUNT(*) FILTER (WHERE outcome = 'lateral')                          AS laterals
FROM base
GROUP BY failed_gate
HAVING COUNT(*) >= 5
ORDER BY avg_r DESC
"""


# Q2 — Near-miss vs published: regime-controlled comparison.
# Restricts BOTH corpora to the same $from_date / $to_date range.
# Fix for confounding that inflated published-signal EV in Decision #27c.
Q_PUBLISHED_VS_NEAR_MISS = """
WITH published AS (
    SELECT s.scan_date, o.outcome, o.r_multiple, 'published' AS source
    FROM signals s
    JOIN outcomes o USING (scan_date, symbol)
    WHERE o.outcome NOT IN ('unresolved_no_data', 'pending')
      AND o.r_multiple_skip_reason IS NULL
      AND is_safe(s.price_staleness_risk)
      AND s.scan_date >= $from_date
      AND s.scan_date <= $to_date
      AND NOT EXISTS (
          SELECT 1 FROM sig_dup_keys d
          WHERE d.scan_date = s.scan_date AND d.symbol = s.symbol
      )
),
near AS (
    SELECT nm.scan_date, nmo.outcome, nmo.r_multiple, 'near_miss' AS source
    FROM near_misses nm
    JOIN near_miss_outcomes nmo USING (scan_date, symbol)
    WHERE nmo.outcome NOT IN ('unresolved_no_data', 'pending')
      AND nmo.r_multiple_skip_reason IS NULL
      AND is_safe(nm.price_staleness_risk)
      AND nm.scan_date >= $from_date
      AND nm.scan_date <= $to_date
      AND NOT EXISTS (
          SELECT 1 FROM nm_dup_keys d
          WHERE d.scan_date = nm.scan_date AND d.symbol = nm.symbol
      )
)
SELECT
    source,
    COUNT(*)                                                              AS n,
    ROUND(AVG(r_multiple), 3)                                            AS avg_r,
    ROUND(STDDEV(r_multiple), 3)                                         AS std_r,
    ROUND(AVG((outcome IN ('target_5pct','target_8pct'))::INT)::DOUBLE, 3) AS win_rate,
    COUNT(*) FILTER (WHERE outcome IN ('target_5pct','target_8pct'))     AS wins,
    COUNT(*) FILTER (WHERE outcome = 'stop_hit')                         AS stops,
    COUNT(*) FILTER (WHERE outcome = 'lateral')                          AS laterals
FROM (SELECT * FROM published UNION ALL SELECT * FROM near)
GROUP BY source
ORDER BY source
"""


# Q3a — Catalyst performance: UNNEST, one row per catalyst.
# Answers: "Which catalyst type predicts best?"
# Does NOT answer: total win rate (double-counts multi-catalyst signals).
Q_CATALYST_PERFORMANCE = """
SELECT
    cat.catalyst,
    o.outcome,
    COUNT(*)                                           AS n,
    ROUND(AVG(o.r_multiple), 3)                       AS avg_r,
    ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP
          (ORDER BY o.r_multiple), 3)                 AS p25_r,
    ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP
          (ORDER BY o.r_multiple), 3)                 AS median_r,
    ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP
          (ORDER BY o.r_multiple), 3)                 AS p75_r
FROM signals s
JOIN outcomes o USING (scan_date, symbol)
JOIN LATERAL UNNEST(s.catalysts) AS cat(catalyst) ON TRUE
WHERE o.outcome NOT IN ('unresolved_no_data', 'pending')
  AND o.r_multiple_skip_reason IS NULL
  AND is_safe(s.price_staleness_risk)
  AND s.scan_date >= $from_date
  AND s.scan_date <= $to_date
  AND NOT EXISTS (
      SELECT 1 FROM sig_dup_keys d
      WHERE d.scan_date = s.scan_date AND d.symbol = s.symbol
  )
GROUP BY cat.catalyst, o.outcome
ORDER BY cat.catalyst, avg_r DESC
"""


# Q3b — Signal performance: one row per (scan_date, symbol).
# Answers: "What is the aggregate win rate and total n?"
# Does NOT answer: per-catalyst breakdown.
Q_SIGNAL_PERFORMANCE = """
SELECT
    o.outcome,
    COUNT(*)                                                              AS n,
    ROUND(AVG(o.r_multiple), 3)                                          AS avg_r,
    ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP
          (ORDER BY o.r_multiple), 3)                                    AS median_r
FROM signals s
JOIN outcomes o USING (scan_date, symbol)
WHERE o.outcome NOT IN ('unresolved_no_data', 'pending')
  AND o.r_multiple_skip_reason IS NULL
  AND is_safe(s.price_staleness_risk)
  AND s.scan_date >= $from_date
  AND s.scan_date <= $to_date
  AND NOT EXISTS (
      SELECT 1 FROM sig_dup_keys d
      WHERE d.scan_date = s.scan_date AND d.symbol = s.symbol
  )
GROUP BY o.outcome
ORDER BY avg_r DESC
"""


# Q4 — Stop overshoot: R of stop_hit by ticker, catalyst, entry→invalidation distance.
# Identifies systematically tight stops per ticker or catalyst.
Q_STOP_OVERSHOOT = """
SELECT
    s.symbol,
    cat.catalyst,
    ROUND(
        (s.entry_price_ars - s.invalidation_level_ars) / s.entry_price_ars * 100,
        2
    )                          AS stop_dist_pct,
    o.r_multiple,
    o.exit_price_ars,
    o.days_to_outcome,
    s.scan_date
FROM signals s
JOIN outcomes o USING (scan_date, symbol)
JOIN LATERAL UNNEST(s.catalysts) AS cat(catalyst) ON TRUE
WHERE o.outcome = 'stop_hit'
  AND o.r_multiple_skip_reason IS NULL
  AND is_safe(s.price_staleness_risk)
  AND s.scan_date >= $from_date
  AND s.scan_date <= $to_date
  AND NOT EXISTS (
      SELECT 1 FROM sig_dup_keys d
      WHERE d.scan_date = s.scan_date AND d.symbol = s.symbol
  )
ORDER BY o.r_multiple ASC
"""

Q_STOP_OVERSHOOT_AGG = """
SELECT
    s.symbol,
    cat.catalyst,
    COUNT(*)                                                              AS n_stops,
    ROUND(AVG(
        (s.entry_price_ars - s.invalidation_level_ars) / s.entry_price_ars * 100
    ), 2)                                                                 AS avg_stop_dist_pct,
    ROUND(AVG(o.r_multiple), 3)                                          AS avg_r_at_stop,
    ROUND(MIN(o.r_multiple), 3)                                          AS worst_r
FROM signals s
JOIN outcomes o USING (scan_date, symbol)
JOIN LATERAL UNNEST(s.catalysts) AS cat(catalyst) ON TRUE
WHERE o.outcome = 'stop_hit'
  AND o.r_multiple_skip_reason IS NULL
  AND is_safe(s.price_staleness_risk)
  AND s.scan_date >= $from_date
  AND s.scan_date <= $to_date
  AND NOT EXISTS (
      SELECT 1 FROM sig_dup_keys d
      WHERE d.scan_date = s.scan_date AND d.symbol = s.symbol
  )
GROUP BY s.symbol, cat.catalyst
HAVING COUNT(*) >= 2
ORDER BY avg_r_at_stop ASC
"""


# Q5 — Regime correlation: outcomes joined to the regime_snapshot of their scan_date.
# Requires INNER JOIN on regime_snapshots — only scan_dates with a snapshot appear.
# Will populate automatically as the 2026-09-12 signals resolve (~20 days).
Q_REGIME_CORRELATION = """
SELECT
    CASE
        WHEN rs.pct_below_ma200 >= 0.55 THEN 'bearish (>55%)'
        WHEN rs.pct_below_ma200 >= 0.40 THEN 'neutral (40-55%)'
        ELSE                                  'bullish (<40%)'
    END                                                                      AS regime,
    COUNT(*)                                                                 AS n,
    ROUND(AVG(o.r_multiple), 3)                                             AS avg_r,
    ROUND(AVG((o.outcome IN ('target_5pct','target_8pct'))::INT)::DOUBLE, 3) AS win_rate,
    ROUND(AVG(rs.pct_below_ma200), 3)                                       AS avg_pct_below_ma200,
    ROUND(AVG(rs.median_rsi_14), 2)                                         AS avg_median_rsi
FROM signals s
JOIN outcomes o      USING (scan_date, symbol)
JOIN regime_snapshots rs ON rs.scan_date = s.scan_date
WHERE o.outcome NOT IN ('unresolved_no_data', 'pending')
  AND o.r_multiple_skip_reason IS NULL
  AND is_safe(s.price_staleness_risk)
  AND NOT EXISTS (
      SELECT 1 FROM sig_dup_keys d
      WHERE d.scan_date = s.scan_date AND d.symbol = s.symbol
  )
GROUP BY regime
ORDER BY avg_r DESC
"""

Q_REGIME_CORRELATION_DETAIL = """
SELECT
    rs.scan_date,
    rs.pct_below_ma200,
    rs.median_rsi_14,
    rs.delta_median_rsi_prev,
    o.outcome,
    o.r_multiple,
    s.symbol,
    s.catalysts
FROM signals s
JOIN outcomes o      USING (scan_date, symbol)
JOIN regime_snapshots rs ON rs.scan_date = s.scan_date
WHERE o.outcome NOT IN ('unresolved_no_data', 'pending')
  AND o.r_multiple_skip_reason IS NULL
  AND is_safe(s.price_staleness_risk)
  AND NOT EXISTS (
      SELECT 1 FROM sig_dup_keys d
      WHERE d.scan_date = s.scan_date AND d.symbol = s.symbol
  )
ORDER BY rs.scan_date, o.r_multiple
"""


# Q6 — Pending bias check: compare pending vs resolved by catalyst, period, stop distance.
# Detects selection bias in the resolved corpus (e.g., safe filter excluding winners
# as in Decision #27c; regime confounding). No date parameters — full corpus.
Q_PENDING_BIAS_CHECK = """
WITH base AS (
    SELECT
        strftime('%Y-%m', s.scan_date)  AS period,
        cat.catalyst,
        ROUND(
            (s.entry_price_ars - s.invalidation_level_ars) / s.entry_price_ars * 100,
            1
        )                               AS stop_dist_pct,
        COALESCE(o.outcome, 'no_outcome_record') AS outcome_status
    FROM signals s
    LEFT JOIN outcomes o USING (scan_date, symbol)
    JOIN LATERAL UNNEST(s.catalysts) AS cat(catalyst) ON TRUE
    WHERE is_safe(s.price_staleness_risk)
      AND NOT EXISTS (
          SELECT 1 FROM sig_dup_keys d
          WHERE d.scan_date = s.scan_date AND d.symbol = s.symbol
      )
)
SELECT
    CASE
        WHEN outcome_status IN ('pending', 'unresolved_no_data', 'no_outcome_record')
             THEN 'pending / unresolved'
        ELSE 'resolved'
    END                           AS resolution_group,
    catalyst,
    COUNT(*)                      AS n,
    ROUND(AVG(stop_dist_pct), 2)  AS avg_stop_dist_pct,
    MIN(period)                   AS earliest_scan,
    MAX(period)                   AS latest_scan
FROM base
GROUP BY resolution_group, catalyst
ORDER BY catalyst, resolution_group
"""

Q_PENDING_BIAS_BY_PERIOD = """
WITH base AS (
    SELECT
        strftime('%Y-%m', s.scan_date)  AS period,
        cat.catalyst,
        COALESCE(o.outcome, 'no_outcome_record') AS outcome_status
    FROM signals s
    LEFT JOIN outcomes o USING (scan_date, symbol)
    JOIN LATERAL UNNEST(s.catalysts) AS cat(catalyst) ON TRUE
    WHERE is_safe(s.price_staleness_risk)
      AND NOT EXISTS (
          SELECT 1 FROM sig_dup_keys d
          WHERE d.scan_date = s.scan_date AND d.symbol = s.symbol
      )
)
SELECT
    period,
    catalyst,
    COUNT(*) FILTER (WHERE outcome_status NOT IN
        ('pending','unresolved_no_data','no_outcome_record')) AS resolved,
    COUNT(*) FILTER (WHERE outcome_status IN
        ('pending','unresolved_no_data','no_outcome_record')) AS unresolved,
    COUNT(*)                                                  AS total
FROM base
GROUP BY period, catalyst
ORDER BY period, catalyst
"""
