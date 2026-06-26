# Filter 2 — centralized thresholds.
# All numeric values are CALIBRACIÓN PENDIENTE unless noted otherwise.
# First run over 297 real survivors is calibration, not live signal.
# Changing a number → no DECISIONS.md entry.
# Changing the logic (what is evaluated, how) → DECISIONS.md entry required.

# ── Técnica 1: Technical scoring ───────────────────────────────────────────────

# trend_regime (0-50): weekly strength sub-component (0-20)
# Points awarded per weekly condition (CRITERIOS_INVERSION.md "estructura semanal para contexto")
WEEKLY_ABOVE_MA50_PTS: float = 5.0    # close > MA50 weekly
WEEKLY_ABOVE_MA20_PTS: float = 4.0    # close > MA20 weekly
WEEKLY_MA20_SLOPE_POS_PTS: float = 4.0  # MA20w slope positive
WEEKLY_HH_HL_MAX_PTS: float = 7.0    # HH/HL structure score (proportion × max)
WEEKLY_LOOKBACK_BARS: int = 16        # weeks of weekly bars to inspect for HH/HL
WEEKLY_MA20_SLOPE_LOOKBACK: int = 8   # weeks of MA20w used to estimate slope

# Weekly bearish cap: if weekly trend is clearly bearish, cap trend_regime here
# (DISENO_FILTRO_2.md §2.1a: "si tendencia semanal claramente bajista → cap a 15")
WEEKLY_BEARISH_CAP: float = 15.0
# "Clearly bearish" = close < MA20w AND close < MA50w AND MA20w slope negative
WEEKLY_MA20_SLOPE_BEARISH_THRESHOLD: float = -0.001  # norm slope per week

# trend_regime: daily strength sub-component (0-20)
# (CRITERIOS_INVERSION.md "diario para timing")
DAILY_ABOVE_MA200_PTS: float = 4.0
DAILY_ABOVE_MA50_PTS: float = 5.0
DAILY_ABOVE_MA20_PTS: float = 3.0
DAILY_MA50_SLOPE_POS_PTS: float = 4.0   # MA50d slope positive
DAILY_HH_HL_MAX_PTS: float = 4.0       # HH/HL daily structure score
DAILY_HH_HL_LOOKBACK: int = 40         # trading days to look for HH/HL pattern
DAILY_MA50_SLOPE_LOOKBACK: int = 20    # bars used to estimate MA50d slope

# trend_regime: MA alignment sub-component (0-10)
# (CRITERIOS_INVERSION.md "cruces y pendiente, no solo posición")
MA_PERFECT_ALIGNMENT_PTS: float = 7.0   # MA20 > MA50 > MA200
MA_PARTIAL_ALIGNMENT_PTS: float = 4.0   # MA20 > MA50 but not > MA200
MA_WEAK_ALIGNMENT_PTS: float = 2.0      # MA50 > MA200 only
MA_GOLDEN_CROSS_BONUS_PTS: float = 3.0  # MA50 crossed above MA200 recently
MA_GOLDEN_CROSS_LOOKBACK: int = 30      # bars to look back for golden cross

# trend_regime label thresholds (based on 0-50 score)
TREND_LABEL_STRONG_UP_MIN: float = 37.0
TREND_LABEL_MILD_UP_MIN: float = 24.0
TREND_LABEL_SIDEWAYS_MIN: float = 13.0
TREND_LABEL_MILD_DOWN_MIN: float = 6.0
# below MILD_DOWN_MIN → strong_down

# breakout_bonus (0-15) — (CRITERIOS_INVERSION.md "rupturas de rango confirmadas por volumen")
BREAKOUT_SCORE: float = 15.0           # binary: full bonus or 0
BREAKOUT_LOOKBACK_N: int = 50          # bars defining the prior range maximum
BREAKOUT_RECENT_K: int = 5             # bars ago within which the breakout must fall
BREAKOUT_VOLUME_MULTIPLIER: float = 1.5  # volume on breakout bar vs. median of prior N

# relative_strength (-15 to +15) — (CRITERIOS_INVERSION.md "fuerza relativa vs. índice de referencia")
RS_WINDOW_DAYS: int = 63               # ~3 months of trading days
RS_HIGH_THRESHOLD: float = 1.15        # RS >= this → +15 pts
RS_LOW_THRESHOLD: float = 0.85         # RS <= this → -15 pts
# Linear interpolation between 0.85 and 1.15 (0.0 at RS = 1.00)
RS_MAX_SCORE: float = 15.0
RS_MIN_SCORE: float = -15.0

# RS "near 52-week high" context for RSI penalty exemption
RS_HIGH_CONTEXT_PCT: float = 0.05     # price within 5% of 52w high → context applies

# momentum_rsi (-15 to 0) — (CRITERIOS_INVERSION.md "RSI/momentum, evitando sobrecompra extrema sin contexto")
RSI_PERIOD: int = 14
RSI_OVERSOLD_THRESHOLD: float = 30.0
RSI_OVERBOUGHT_MILD: float = 70.0
RSI_OVERBOUGHT_STRONG: float = 80.0
# Penalty when RSI > 80 AND no context (no breakout, no near-high+MA50-positive)
RSI_OVERBOUGHT_STRONG_PENALTY: float = -12.0   # -10 to -15 range
# Additional: triggered when price is also > RSI_VERTICAL_MA_MULT × MA20d (vertical move)
RSI_VERTICAL_MA_MULT: float = 1.15    # 15% above MA20d
RSI_OVERBOUGHT_STRONG_VERTICAL_PENALTY: float = -15.0
# Penalty when RSI 70-80 without context
RSI_OVERBOUGHT_MILD_PENALTY: float = -5.0
# Penalty when RSI < 30 (momentum reversal signal, not a buy signal for this system)
RSI_OVERSOLD_PENALTY: float = -7.0

# Minimum daily bars needed to compute technical score reliably
TECHNICAL_MIN_BARS: int = 250         # covers MA200 + some weekly context

# ── Técnica 2: Fundamental quality ────────────────────────────────────────────

# Minimum quarterly periods for slope computation
FUNDAMENTAL_MIN_PERIODS: int = 3

# Confirmed state thresholds (DISENO_FILTRO_2.md §3.2)
CONFIRMED_REVENUE_SLOPE_MIN: float = 0.0       # revenue slope >= 0 (not decaying)
CONFIRMED_EPS_SLOPE_MIN: float = -0.05         # eps slope >= -0.05 (stable or improving)
# FCF must be > 0 for confirmed (or ticker in financial exemption list)

# Deteriorating thresholds: revenue AND eps clearly negative AND/OR FCF negative
DETERIORATING_REVENUE_SLOPE_MAX: float = -0.05  # revenue slope clearly negative
DETERIORATING_EPS_SLOPE_MAX: float = -0.08      # eps slope clearly negative

# Fundamental penalties (DISENO_FILTRO_2.md §3.2)
FUNDAMENTAL_PENALTY_CONFIRMED: float = 0.0
FUNDAMENTAL_PENALTY_NEUTRAL_BASE: float = 5.0   # base penalty for neutral
FUNDAMENTAL_PENALTY_NEUTRAL_MAX: float = 10.0   # ceiling for neutral
FUNDAMENTAL_PENALTY_DETERIORATING_BASE: float = 15.0
FUNDAMENTAL_PENALTY_DETERIORATING_MAX: float = 30.0
FUNDAMENTAL_PENALTY_UNKNOWN: float = 0.0        # unknown → no penalty (epistemic, not failure)

# ── Técnica 3: News gate ───────────────────────────────────────────────────────

# Cache TTL for news results (DISENO_FILTRO_2.md §4.4: "3-5 días")
NEWS_CACHE_TTL_DAYS: int = 4

# Max results to fetch per search query
NEWS_SEARCH_MAX_RESULTS: int = 8

# Delay between search requests to avoid rate-limiting (seconds)
NEWS_SEARCH_DELAY_SEC: float = 1.0

# Request timeout for search queries (seconds)
NEWS_SEARCH_TIMEOUT_SEC: int = 12

# ── Técnica 4: Argentina adjustment ───────────────────────────────────────────

# CCL volatility component — (DISENO_FILTRO_2.md §5.1a and §5.2)
# Metric: std_dev(CCL_30d) / mean(CCL_30d)
CCL_VOL_LOOKBACK_DAYS: int = 30
CCL_VOL_CEDEAR_MAX_PTS: float = 10.0    # cap for CEDEARs
CCL_VOL_ARGENTINA_MAX_PTS: float = 8.0  # cap for Argentine stocks (different role)
CCL_VOL_LOW_THRESHOLD: float = 0.01     # below → 0 pts
CCL_VOL_HIGH_THRESHOLD: float = 0.04    # above → max pts

# Premium CEDEAR/subyacente component — (DISENO_FILTRO_2.md §5.1b)
# premium = actual_ars / implied_ars - 1
# implied_ars = underlying_usd × ccl_spot / cedears_per_underlying
PREMIUM_ALIGNED_THRESHOLD: float = 0.02    # |premium| < 2% → 0 pts
PREMIUM_EXPENSIVE_THRESHOLD: float = 0.05  # premium > +5% → max pts (paying expensive)
PREMIUM_CHEAP_THRESHOLD: float = -0.05     # premium < -5% → partial pts (low demand)
PREMIUM_MAX_PTS: float = 10.0
PREMIUM_CHEAP_PTS: float = 4.0    # discount CEDEAR is less worrying than premium

# Liquidity component — REMOVED FROM ACTIVE USE (DISENO_FILTRO_2.md §5.1c)
# Reason: BYMA vs NYSE/NASDAQ volume comparison is meaningless in scale.
# AAPL.BA (~USD 1.1M/day) hits max penalty despite being the most liquid CEDEAR.
# Filter 1 C4 already discards genuinely illiquid tickers.
# Re-enable if a Cocos-native liquidity source becomes available.
# LIQUIDITY_LOOKBACK_DAYS: int = 20
# LIQUIDITY_LOW_THRESHOLD: float = 0.001
# LIQUIDITY_HIGH_THRESHOLD: float = 0.01
# LIQUIDITY_MAX_PTS: float = 5.0

# Underlying price cache lookback (days fetched for premium/liquidity computation)
UNDERLYING_LOOKBACK_DAYS: int = 30

# A3 flag penalty for Argentine stocks — (DISENO_FILTRO_2.md §5.2)
A3_PENALTY_BASE: float = 5.0    # base penalty if a3 flag is present
A3_PENALTY_MAX: float = 10.0   # user can escalate via YAML (future)

# Total cap for argentina_penalty
ARGENTINA_MAX_PENALTY: float = 25.0

# ── Runner: post-processing ────────────────────────────────────────────────────

# Minimum final_score to appear in the ranking (DISENO_FILTRO_2.md §6.3)
MIN_SCORE: float = 35.0

# Maximum positions in ranking (DISENO_FILTRO_2.md §6.3)
MAX_POSITIONS: int = 10

# Score-to-weight flattening exponent α (DISENO_FILTRO_2.md §6.3)
# α < 1 → flatter distribution; α = 1 → proportional to score
SCORE_FLATTENING_ALPHA: float = 0.7

# Minimum position size in USD (positions below this are removed and redistributed)
MIN_POSITION_USD: float = 500.0

# Total capital to allocate (CRITERIOS_INVERSION.md)
TOTAL_CAPITAL_USD: float = 10_000.0

# Cash reserve schedule: {max_n → reserve_pct} (DISENO_FILTRO_2.md §6.3)
# Read as: if n <= key → reserve = value
CASH_RESERVE_SCHEDULE: dict = {
    5: 0.20,   # up to 5 positions → 20% cash
    8: 0.15,   # 6-8 positions → 15% cash
    10: 0.10,  # 9-10 positions → 10% cash
}

# ── Runner: invalidation level ─────────────────────────────────────────────────

# Swing low detection window (DISENO_FILTRO_2.md §6.2)
SWING_LOW_LOOKBACK_BARS: int = 40     # bars to search for swing lows
SWING_LOW_WINDOW_N: int = 4           # bars on each side must be higher

# Buffer below the relevant MA (DISENO_FILTRO_2.md §6.2: "colchón ~3%")
INVALIDATION_MA_BUFFER: float = 0.03  # 3% below MA → invalidation level
