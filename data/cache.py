from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).parent.parent
CACHE_DIR = _REPO_ROOT / "cache"


def _last_expected_trading_day() -> date:
    """Return the most recent weekday before today (Mon–Fri).

    Used as the minimum bar date for a 'fresh' price cache.
    Does not account for BYMA holidays — see prices_are_fresh() docstring.
    """
    yesterday = date.today() - timedelta(days=1)
    wd = yesterday.weekday()  # Mon=0 … Sun=6
    if wd == 5:   # yesterday was Saturday → step back to Friday
        return yesterday - timedelta(days=1)
    if wd == 6:   # yesterday was Sunday → step back to Friday
        return yesterday - timedelta(days=2)
    return yesterday


class Cache:
    def __init__(self, cache_dir: Path = CACHE_DIR):
        self.cache_dir = cache_dir
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        for sub in ("prices", "ccl", "fundamentals"):
            (self.cache_dir / sub).mkdir(parents=True, exist_ok=True)

    # ── Prices ────────────────────────────────────────────────────────────────

    def _prices_path(self, symbol: str) -> Path:
        safe = symbol.replace("/", "_").replace(".", "_")
        return self.cache_dir / "prices" / f"{safe}.parquet"

    def load_prices(self, symbol: str) -> Optional[pd.DataFrame]:
        path = self._prices_path(symbol)
        if not path.exists():
            return None
        try:
            df = pd.read_parquet(path)
            df.index = pd.to_datetime(df.index).tz_localize(None)
            return df
        except Exception:
            logger.warning("Corrupted price cache for %s; ignoring", symbol)
            return None

    def save_prices(self, symbol: str, df: pd.DataFrame) -> None:
        try:
            df.to_parquet(self._prices_path(symbol))
        except Exception as e:
            logger.warning("Failed to write price cache for %s: %s", symbol, e)

    def prices_are_fresh(self, symbol: str) -> bool:
        """Fresh if the cached data covers up to the last expected trading day.

        Uses a weekday-only heuristic: last expected trading day = most recent
        weekday before today. Does NOT account for Argentine market holidays (BYMA).
        When the heuristic errs, it errs toward refreshing more than needed —
        never toward missing a new bar.
        """
        df = self.load_prices(symbol)
        if df is None or df.empty:
            return False
        last_bar = pd.Timestamp(df.index[-1]).date()
        return last_bar >= _last_expected_trading_day()

    # ── CCL ───────────────────────────────────────────────────────────────────

    @property
    def _ccl_history_path(self) -> Path:
        return self.cache_dir / "ccl" / "ccl_history.parquet"

    @property
    def _ccl_meta_path(self) -> Path:
        return self.cache_dir / "ccl" / "ccl_meta.json"

    def load_ccl(self) -> Optional[pd.Series]:
        if not self._ccl_history_path.exists():
            return None
        try:
            df = pd.read_parquet(self._ccl_history_path)
            series = df.squeeze()
            series.index = pd.to_datetime(series.index).tz_localize(None)
            return series
        except Exception:
            logger.warning("Corrupted CCL history cache; ignoring")
            return None

    def save_ccl(self, series: pd.Series, spot: float, as_of: date) -> None:
        try:
            series.to_frame(name="ccl").to_parquet(self._ccl_history_path)
            self._ccl_meta_path.write_text(
                json.dumps({"spot": spot, "as_of": as_of.isoformat()})
            )
        except Exception as e:
            logger.warning("Failed to write CCL cache: %s", e)

    def ccl_is_fresh(self) -> bool:
        """Fresh if the spot was recorded today."""
        if not self._ccl_meta_path.exists():
            return False
        try:
            meta = json.loads(self._ccl_meta_path.read_text())
            as_of = date.fromisoformat(meta["as_of"])
            return as_of == date.today()
        except Exception:
            return False

    def load_ccl_spot(self) -> Optional[Tuple[float, date]]:
        if not self._ccl_meta_path.exists():
            return None
        try:
            meta = json.loads(self._ccl_meta_path.read_text())
            return meta["spot"], date.fromisoformat(meta["as_of"])
        except Exception:
            return None

    # ── Fundamentals ──────────────────────────────────────────────────────────

    def _fundamentals_path(self, symbol_underlying: str) -> Path:
        safe = symbol_underlying.replace("/", "_")
        return self.cache_dir / "fundamentals" / f"{safe}.json"

    def load_fundamentals(self, symbol_underlying: str) -> Optional[dict]:
        path = self._fundamentals_path(symbol_underlying)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text())
        except Exception:
            logger.warning("Corrupted fundamentals cache for %s; ignoring", symbol_underlying)
            return None

    def save_fundamentals(self, symbol_underlying: str, data: dict) -> None:
        try:
            self._fundamentals_path(symbol_underlying).write_text(json.dumps(data))
        except Exception as e:
            logger.warning("Failed to write fundamentals cache for %s: %s", symbol_underlying, e)

    def fundamentals_are_fresh(self, symbol_underlying: str) -> bool:
        """Fresh if cached within the last 90 days (quarterly earnings cadence)."""
        raw = self.load_fundamentals(symbol_underlying)
        if not raw:
            return False
        try:
            as_of = date.fromisoformat(raw.get("as_of", "1970-01-01"))
            return (date.today() - as_of).days < 90
        except Exception:
            return False
