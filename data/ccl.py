from __future__ import annotations

import logging
from datetime import date
from typing import Optional, Tuple

import pandas as pd
import requests

from .cache import Cache
from .models import CCLSeries

logger = logging.getLogger(__name__)

_DOLAR_API_SPOT_URL = "https://dolarapi.com/v1/dolares/contadoconliqui"
_ARGENTINA_DATOS_HISTORICAL_URL = "https://api.argentinadatos.com/v1/cotizaciones/dolares/contadoconliqui"
_REQUEST_TIMEOUT = 10


def fetch_ccl(cache: Cache) -> Optional[CCLSeries]:
    """Fetch CCL spot + full historical series.

    Priority:
      1. Cache hit (as_of == today) → return immediately.
      2. Live fetch: spot from dolarapi.com, history from argentinadatos.com.
         New history is merged with existing cache to extend the series.
      3. Fallback: stale cache if both live sources fail.

    Returns None only if every source fails and no cache exists.
    """
    if cache.ccl_is_fresh():
        series = cache.load_ccl()
        cached_spot = cache.load_ccl_spot()
        if series is not None and cached_spot is not None:
            spot, as_of = cached_spot
            logger.debug("CCL loaded from fresh cache (as_of %s, spot %.2f)", as_of, spot)
            return CCLSeries(data=series, spot=spot, as_of=as_of)

    spot, spot_date = _fetch_spot()
    historical = _fetch_historical()

    if spot is None and historical is None:
        return _fallback_to_stale_cache(cache)

    if spot is None and historical is not None:
        spot = float(historical.iloc[-1])
        spot_date = historical.index[-1].date()

    if historical is None and spot is not None:
        historical = _single_point_series(spot, spot_date or date.today())

    # Merge with existing cached series to extend history without re-fetching
    cached_series = cache.load_ccl()
    if cached_series is not None and not cached_series.empty:
        combined = pd.concat([cached_series, historical])
        combined = combined[~combined.index.duplicated(keep="last")]
        historical = combined.sort_index()

    # Forward-fill weekends and holidays so callers always get a value for any date
    today_ts = pd.Timestamp(date.today())
    if historical.index[-1] < today_ts:
        full_range = pd.date_range(start=historical.index[0], end=today_ts, freq="D")
        historical = historical.reindex(full_range).ffill()

    effective_spot = spot if spot is not None else float(historical.iloc[-1])
    effective_date = spot_date or date.today()

    cache.save_ccl(historical, effective_spot, effective_date)
    logger.info("CCL updated: spot=%.2f as_of=%s, %d days of history", effective_spot, effective_date, len(historical))
    return CCLSeries(data=historical, spot=effective_spot, as_of=effective_date)


def _fetch_spot() -> Tuple[Optional[float], Optional[date]]:
    try:
        resp = requests.get(_DOLAR_API_SPOT_URL, timeout=_REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        compra = data.get("compra")
        venta = data.get("venta")
        if compra and venta:
            return (float(compra) + float(venta)) / 2, date.today()
        if venta:
            return float(venta), date.today()
        logger.warning("dolarapi response missing compra/venta fields: %s", data)
        return None, None
    except Exception as exc:
        logger.warning("Failed to fetch CCL spot from dolarapi: %s", exc)
        return None, None


def _fetch_historical() -> Optional[pd.Series]:
    try:
        resp = requests.get(_ARGENTINA_DATOS_HISTORICAL_URL, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list) or not data:
            return None

        records: dict[str, float] = {}
        for entry in data:
            fecha = entry.get("fecha")
            if not fecha:
                continue
            compra = entry.get("compra")
            venta = entry.get("venta")
            if compra and venta:
                records[fecha] = (float(compra) + float(venta)) / 2
            elif venta:
                records[fecha] = float(venta)

        if not records:
            return None

        series = pd.Series(records)
        series.index = pd.to_datetime(series.index)
        return series.sort_index()
    except Exception as exc:
        logger.warning("Failed to fetch CCL history from argentinadatos: %s", exc)
        return None


def _fallback_to_stale_cache(cache: Cache) -> Optional[CCLSeries]:
    series = cache.load_ccl()
    cached_spot = cache.load_ccl_spot()
    if series is not None and cached_spot is not None:
        spot, as_of = cached_spot
        logger.warning("CCL live fetch failed; using stale cache (as_of %s)", as_of)
        return CCLSeries(data=series, spot=spot, as_of=as_of)
    logger.error("CCL fetch failed and no cache available")
    return None


def _single_point_series(spot: float, as_of: date) -> pd.Series:
    return pd.Series([spot], index=[pd.Timestamp(as_of)])
