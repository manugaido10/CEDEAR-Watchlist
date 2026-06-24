# Filter 1 — centralized thresholds (calibrated 2026-06-24).

# ── C1: Solvency (CRITERIOS_INVERSION.md — "Deuda impagable o deterioro acelerado de solvencia") ──
# Max net_debt / FCF ratio (years to repay); only evaluated when both net_debt > 0 and FCF > 0.
C1_MAX_ND_FCF_RATIO: float = 15.0

# Absolute net_debt floor (USD millions) that triggers C1 when FCF <= 0.
C1_MIN_NET_DEBT_ABS_NEG_FCF: float = 5_000.0

# ── C2: Earnings trend (CRITERIOS_INVERSION.md — "Earnings en caída sostenida y marcada") ──
# Minimum quarters of EPS data required to run the check.
# FMP free tier returns at most 5 quarters; 6+ always skips. At n=5 the YoY
# comparison uses arr[-5] (5 quarters ago, ~15 months) instead of arr[-4] (1
# year exact), but slope + YoY conjunction still distinguishes sustained decline
# from a single bad quarter.
C2_MIN_EPS_PERIODS: int = 5

# Normalized slope threshold (slope / mean_abs_eps per quarter); must fire only when clearly negative.
C2_EPS_SLOPE_THRESHOLD: float = -0.10

# Minimum YoY decline (eps_now vs eps_5q_ago / |eps_5q_ago|) to co-fire with slope.
# Set at -0.40 (not -0.30) to avoid false positives on cyclical companies with normal earnings swings.
C2_EPS_CHANGE_VS_4Q: float = -0.40

# ── C4: Liquidity (CRITERIOS_INVERSION.md — "Liquidez insuficiente del instrumento en Cocos") ──
# Rolling window (trading days) for median daily traded value.
C4_LOOKBACK_DAYS: int = 20

# Median daily traded value floor (ARS). Proxy via yfinance/BYMA — not Cocos-specific volume.
# 1M ARS/day is the empirical floor of operability observed across the universe.
C4_MIN_DAILY_VOLUME_ARS: float = 1_000_000.0

# ── C5: Technical trend (CRITERIOS_INVERSION.md — "Tendencia técnica de fondo claramente negativa") ──
# All three sub-conditions must fire simultaneously (conjunction, not disjunction).

# Bars of MA200 history used to measure slope.
C5_MA200_SLOPE_LOOKBACK: int = 50

# Minimum normalized MA200 slope (raw_slope / MA200_level per bar) to confirm the trend is
# "clearly negative", not just a mild drift.
C5_MA200_SLOPE_THRESHOLD: float = -0.0005

# Trading days defining the "6-month support" window.
C5_SUPPORT_LOOKBACK_BARS: int = 126  # ~6 months

# Consecutive closes that must all be below the 6m support to confirm a sustained break.
# 5 bars (~1 trading week) filters out single-day spikes while remaining sensitive.
C5_CONSECUTIVE_CLOSES_BELOW: int = 5
