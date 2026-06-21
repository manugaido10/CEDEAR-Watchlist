# Filter 1 — centralized thresholds.
# All constants here are CALIBRACIÓN PENDIENTE: first run on the real universe
# is calibration, not a live signal. Adjust numbers here; logic changes go to DECISIONS.md.

# ── C1: Solvency (CRITERIOS_INVERSION.md — "Deuda impagable o deterioro acelerado de solvencia") ──
# Max net_debt / FCF ratio (years to repay); only evaluated when both net_debt > 0 and FCF > 0.
C1_MAX_ND_FCF_RATIO: float = 15.0  # CALIBRACIÓN PENDIENTE

# Absolute net_debt floor (USD millions) that triggers C1 when FCF <= 0.
C1_MIN_NET_DEBT_ABS_NEG_FCF: float = 5_000.0  # CALIBRACIÓN PENDIENTE

# ── C2: Earnings trend (CRITERIOS_INVERSION.md — "Earnings en caída sostenida y marcada") ──
# Minimum quarters of EPS data required to run the check.
C2_MIN_EPS_PERIODS: int = 6  # CALIBRACIÓN PENDIENTE

# Normalized slope threshold (slope / mean_abs_eps per quarter); must fire only when clearly negative.
C2_EPS_SLOPE_THRESHOLD: float = -0.10  # CALIBRACIÓN PENDIENTE

# Minimum YoY decline (eps_now vs eps_4q_ago / |eps_4q_ago|) to co-fire with slope.
C2_EPS_CHANGE_VS_4Q: float = -0.30  # CALIBRACIÓN PENDIENTE  (−30% drop)

# ── C4: Liquidity (CRITERIOS_INVERSION.md — "Liquidez insuficiente del instrumento en Cocos") ──
# Rolling window (trading days) for median daily traded value.
C4_LOOKBACK_DAYS: int = 20  # CALIBRACIÓN PENDIENTE

# Median daily traded value floor (ARS). Proxy via yfinance/BYMA — not Cocos-specific volume.
C4_MIN_DAILY_VOLUME_ARS: float = 5_000_000.0  # CALIBRACIÓN PENDIENTE

# ── C5: Technical trend (CRITERIOS_INVERSION.md — "Tendencia técnica de fondo claramente negativa") ──
# All three sub-conditions must fire simultaneously (conjunction, not disjunction).

# Bars of MA200 history used to measure slope.
C5_MA200_SLOPE_LOOKBACK: int = 50  # CALIBRACIÓN PENDIENTE

# Minimum normalized MA200 slope (raw_slope / MA200_level per bar) to confirm the trend is
# "clearly negative", not just a mild drift. Operationalizes "claramente negativa, no una
# corrección normal" from CRITERIOS_INVERSION.md. Only fires when slope is below this threshold.
C5_MA200_SLOPE_THRESHOLD: float = -0.0005  # CALIBRACIÓN PENDIENTE

# Trading days defining the "6-month support" window.
C5_SUPPORT_LOOKBACK_BARS: int = 126  # CALIBRACIÓN PENDIENTE  (~6 months)

# Consecutive closes that must all be below the 6m support to confirm a sustained break.
C5_CONSECUTIVE_CLOSES_BELOW: int = 10  # CALIBRACIÓN PENDIENTE
