from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import List, Optional

import pandas as pd


class AssetType(str, Enum):
    CEDEAR = "cedear"
    ARGENTINE_STOCK = "argentine_stock"


class FetchStatus(str, Enum):
    OK = "ok"
    STALE = "stale"       # fell back to cached data because live fetch failed
    PARTIAL = "partial"   # fewer bars than MIN_BARS_EXPECTED
    MISSING = "missing"   # no data at all (live failed, no cache)
    ERROR = "error"       # unexpected error outside the normal fetch path


@dataclass
class TickerMetadata:
    symbol_ars: str                          # e.g. "GGAL.BA"
    name: str
    asset_type: AssetType
    symbol_underlying: Optional[str] = None  # e.g. "GGAL" (ADR/NYSE) for CEDEARs
    cedear_ratio: Optional[float] = None     # N CEDEARs = 1 underlying share
    isin: Optional[str] = None
    source_snapshot_date: Optional[date] = None


@dataclass
class PriceHistory:
    symbol: str
    data: pd.DataFrame  # OHLCV; DatetimeIndex, columns: open high low close volume

    @property
    def bar_count(self) -> int:
        return len(self.data)


@dataclass
class CCLSeries:
    data: pd.Series  # DatetimeIndex → float (ARS per USD); forward-filled for non-business days
    spot: float      # most recent value
    as_of: date


@dataclass
class FundamentalsSnapshot:
    symbol_underlying: str
    as_of: date
    eps_quarterly: List[float]      # last 8 quarters, ascending chronological order
    revenue_quarterly: List[float]  # USD millions, same cadence
    net_debt: Optional[float] = None          # USD millions; negative = net cash position
    gross_margin: Optional[float] = None      # 0.0–1.0
    operating_margin: Optional[float] = None  # 0.0–1.0
    free_cash_flow: Optional[float] = None    # USD millions, TTM
    data_source: str = "fmp"


@dataclass
class TickerBundle:
    metadata: TickerMetadata
    prices_ars: Optional[PriceHistory]
    ccl_series: Optional[CCLSeries]     # shared across all bundles in a cycle; not per-ticker data
    fundamentals: Optional[FundamentalsSnapshot]
    status: FetchStatus
    warnings: List[str] = field(default_factory=list)


@dataclass
class FetchSummary:
    total: int
    ok: int
    stale: int
    partial: int
    missing: int
    error: int
    run_date: date
