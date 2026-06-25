"""Filter 2 — data models (output types for all four technique modules)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


# ── Technical scoring (Técnica 1) ─────────────────────────────────────────────

class TrendLabel(str, Enum):
    STRONG_UP = "strong_up"
    MILD_UP = "mild_up"
    SIDEWAYS = "sideways"
    MILD_DOWN = "mild_down"
    STRONG_DOWN = "strong_down"


class RSIState(str, Enum):
    OK = "ok"
    OVERBOUGHT_WITH_CONTEXT = "overbought_with_context"
    OVERBOUGHT_NO_CONTEXT = "overbought_no_context"
    OVERSOLD = "oversold"


@dataclass
class TrendBreakdown:
    weekly_strength: float   # 0-20
    daily_strength: float    # 0-20
    ma_alignment: float      # 0-10
    weekly_cap_applied: bool = False


@dataclass
class BreakoutDetail:
    triggered: bool
    bar_date: Optional[str] = None    # ISO date of the breakout bar
    volume_ratio: Optional[float] = None  # volume / median_volume_prior_n


@dataclass
class TechnicalResult:
    technical_score: float          # 0-100 (clipped)
    trend_regime: float             # 0-50 (with possible weekly cap)
    breakout_bonus: float           # 0-15
    relative_strength_score: float  # -15 to +15
    rsi_penalty: float              # -15 to 0
    trend_breakdown: TrendBreakdown
    breakout_detail: BreakoutDetail
    rs_value: float                 # raw RS ratio (ticker / index ratio change)
    benchmark_used: str             # "SPY" or "^MERV"
    rsi_value: float                # last RSI14 value
    rsi_state: RSIState
    trend_regime_label: TrendLabel
    signal_summary: str = ""        # human-readable one-liner
    warnings: List[str] = field(default_factory=list)


# ── Fundamental quality (Técnica 2) ───────────────────────────────────────────

class FundamentalState(str, Enum):
    CONFIRMED = "confirmed"
    NEUTRAL = "neutral"
    DETERIORATING = "deteriorating"
    UNKNOWN = "unknown"


@dataclass
class FundamentalResult:
    fundamental_state: FundamentalState
    fundamental_penalty: float        # 0-30
    revenue_slope: Optional[float] = None   # normalized slope per quarter
    eps_slope: Optional[float] = None       # normalized slope per quarter
    fcf_positive: Optional[bool] = None     # None if unknown or exempt
    summary: str = ""


# ── News gate (Técnica 3) ──────────────────────────────────────────────────────

class LightCheckResult(str, Enum):
    CLEAN = "clean"
    HARD_NEWS_DETECTED = "hard_news_detected"


class SentimentVerdict(str, Enum):
    NONE = "none"           # tiebreaker not activated
    CONFIRM = "confirm"
    INCONCLUSIVE = "inconclusive"
    DISCARD = "discard"


@dataclass
class SentimentResult:
    light_check: LightCheckResult
    sentiment_gate: SentimentVerdict
    tiebreaker_activated: bool = False
    tiebreaker_reason: str = ""
    evidence_urls: List[str] = field(default_factory=list)
    light_snippets: List[str] = field(default_factory=list)
    summary: str = ""
    warnings: List[str] = field(default_factory=list)


# ── Argentina adjustment (Técnica 4) ──────────────────────────────────────────

@dataclass
class ArgentinaAdjustment:
    # Shared
    ccl_vol_penalty: float = 0.0
    # CEDEAR-specific
    premium_penalty: float = 0.0
    liquidity_penalty: float = 0.0
    premium_pct: Optional[float] = None   # actual_ars/implied_ars - 1
    liquidity_ratio: Optional[float] = None
    # Argentine stock-specific
    a3_flag: bool = False
    a3_penalty: float = 0.0
    a3_reason: str = ""
    # Total (capped at ARGENTINA_MAX_PENALTY)
    total_penalty: float = 0.0
    breakdown: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)


# ── Runner output ──────────────────────────────────────────────────────────────

class TickerFilter2Status(str, Enum):
    RANKED = "ranked"
    DISCARDED_BY_SENTIMENT = "discarded_by_sentiment"
    HELD_WITH_WARNING = "held_with_warning"
    UNEVALUABLE = "unevaluable"


@dataclass
class Filter2Opportunity:
    symbol: str
    asset_type: str   # "cedear" | "argentine_stock"
    name: str

    # Driver
    technical_score: float
    technical_breakdown: TechnicalResult
    technical_signal_summary: str

    # Quality confirmation
    fundamental_state: str    # FundamentalState.value
    fundamental_penalty: float
    fundamental_summary: str

    # Tiebreaker
    sentiment_gate: str       # SentimentVerdict.value
    sentiment_evidence: List[str]
    sentiment_summary: str

    # Argentina modifier
    argentina_penalty: float
    argentina_breakdown: Dict[str, Any]

    # Final score + ranking
    final_score: float
    rank: int
    status: str               # TickerFilter2Status.value

    # Technical invalidation
    invalidation_level_ars: float
    invalidation_level_usd: float
    invalidation_rationale: str

    # Capital proposal
    proposed_capital_usd: float
    proposed_capital_pct: float
    capital_rationale: str

    warnings: List[str] = field(default_factory=list)


@dataclass
class Filter2Report:
    opportunities: List[Filter2Opportunity]          # ranked, status=RANKED or HELD_WITH_WARNING
    discarded_by_sentiment: List[Filter2Opportunity]
    unevaluable_symbols: List[str]
    total_survivors_input: int
    total_ranked: int
    total_discarded_by_sentiment: int
    total_unevaluable: int
    run_date: str   # ISO date string
    warnings: List[str] = field(default_factory=list)
