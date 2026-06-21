from __future__ import annotations

import logging
import time
from collections import Counter
from datetime import date
from typing import List, Optional, Tuple

from .cache import Cache
from .ccl import fetch_ccl
from .fundamentals import fetch_fundamentals
from .models import (
    AssetType,
    CCLSeries,
    FetchStatus,
    FetchSummary,
    PriceHistory,
    TickerBundle,
    TickerMetadata,
)
from .prices import fetch_prices
from .universe import load_universe

logger = logging.getLogger(__name__)

MIN_BARS_EXPECTED = 400
_RETRY_ATTEMPTS = 2
_RETRY_BACKOFF_BASE = 2.0  # seconds; sleeps 1s, 2s between attempts


def fetch_universe_bundle(
    cache: Optional[Cache] = None,
) -> Tuple[List[TickerBundle], FetchSummary]:
    """Fetch data for every ticker in the local universe snapshot.

    One ticker failing never aborts the cycle. Each bundle carries its own
    FetchStatus and warnings list so callers can inspect what happened.

    Returns (list[TickerBundle], FetchSummary).
    """
    if cache is None:
        cache = Cache()

    universe = load_universe()
    logger.info("Starting universe bundle fetch for %d tickers", len(universe))

    # CCL is fetched once and embedded (by reference) in every bundle
    ccl = _fetch_ccl_safe(cache)
    if ccl is None:
        logger.warning("CCL unavailable this cycle; PnL conversion will not be possible")

    bundles: List[TickerBundle] = []
    for meta in universe:
        bundle = _fetch_one(meta, ccl, cache)
        bundles.append(bundle)

    summary = _build_summary(bundles)
    logger.info(
        "Fetch complete — total=%d ok=%d partial=%d stale=%d missing=%d error=%d",
        summary.total,
        summary.ok,
        summary.partial,
        summary.stale,
        summary.missing,
        summary.error,
    )
    return bundles, summary


# ── Per-ticker orchestration ───────────────────────────────────────────────────

def _fetch_one(meta: TickerMetadata, ccl: Optional[CCLSeries], cache: Cache) -> TickerBundle:
    warnings: List[str] = []

    prices, price_status = _fetch_prices_with_fallback(meta, cache, warnings)

    fundamentals = None
    if meta.asset_type == AssetType.CEDEAR:
        if meta.symbol_underlying:
            fundamentals = _fetch_fundamentals_safe(meta.symbol_underlying, cache, warnings)
        else:
            warnings.append("CEDEAR without symbol_underlying; fundamentals skipped")

    return TickerBundle(
        metadata=meta,
        prices_ars=prices,
        ccl_series=ccl,
        fundamentals=fundamentals,
        status=price_status,
        warnings=warnings,
    )


def _fetch_prices_with_fallback(
    meta: TickerMetadata,
    cache: Cache,
    warnings: List[str],
) -> Tuple[Optional[PriceHistory], FetchStatus]:
    symbol = meta.symbol_ars

    # Skip cache for freshness check only — we always try live first
    df = None
    last_exc: Optional[Exception] = None
    for attempt in range(_RETRY_ATTEMPTS + 1):
        try:
            df = fetch_prices(symbol)
            if df is not None and not df.empty:
                break
        except Exception as exc:
            last_exc = exc
            logger.warning("Price fetch attempt %d/%d for %s: %s", attempt + 1, _RETRY_ATTEMPTS + 1, symbol, exc)
        if attempt < _RETRY_ATTEMPTS:
            time.sleep(_RETRY_BACKOFF_BASE**attempt)

    if df is not None and not df.empty:
        cache.save_prices(symbol, df)
        history = PriceHistory(symbol=symbol, data=df)
        if history.bar_count < MIN_BARS_EXPECTED:
            warnings.append(
                f"Only {history.bar_count} bars returned (expected >={MIN_BARS_EXPECTED})"
            )
            return history, FetchStatus.PARTIAL
        return history, FetchStatus.OK

    # Live failed — try cache
    cached_df = cache.load_prices(symbol)
    if cached_df is not None and not cached_df.empty:
        warnings.append(
            f"Using stale cached prices (live fetch failed: {last_exc})"
        )
        history = PriceHistory(symbol=symbol, data=cached_df)
        if history.bar_count < MIN_BARS_EXPECTED:
            warnings.append(
                f"Stale cache also has only {history.bar_count} bars (expected >={MIN_BARS_EXPECTED})"
            )
        return history, FetchStatus.STALE

    logger.error("No price data available for %s (live failed, no cache)", symbol)
    return None, FetchStatus.MISSING


def _fetch_fundamentals_safe(
    symbol_underlying: str,
    cache: Cache,
    warnings: List[str],
) -> Optional[object]:
    try:
        return fetch_fundamentals(symbol_underlying, cache)
    except Exception as exc:
        logger.error("Unexpected error fetching fundamentals for %s: %s", symbol_underlying, exc)
        warnings.append(f"Fundamentals error for {symbol_underlying}: {exc}")
        return None


def _fetch_ccl_safe(cache: Cache) -> Optional[CCLSeries]:
    try:
        return fetch_ccl(cache)
    except Exception as exc:
        logger.error("Unexpected error fetching CCL: %s", exc)
        return None


# ── Summary ────────────────────────────────────────────────────────────────────

def _build_summary(bundles: List[TickerBundle]) -> FetchSummary:
    counts = Counter(b.status for b in bundles)
    return FetchSummary(
        total=len(bundles),
        ok=counts[FetchStatus.OK],
        stale=counts[FetchStatus.STALE],
        partial=counts[FetchStatus.PARTIAL],
        missing=counts[FetchStatus.MISSING],
        error=counts[FetchStatus.ERROR],
        run_date=date.today(),
    )
