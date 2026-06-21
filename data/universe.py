from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path
from typing import List

from .models import AssetType, TickerMetadata

logger = logging.getLogger(__name__)

SNAPSHOT_PATH = Path(__file__).parent / "universe_snapshot.json"


def load_universe(snapshot_path: Path = SNAPSHOT_PATH) -> List[TickerMetadata]:
    """Load the tradeable universe from the local snapshot file.

    The snapshot is maintained by scripts/refresh_universe.py and versioned in git.
    This function never calls external APIs.
    """
    if not snapshot_path.exists():
        raise FileNotFoundError(
            f"Universe snapshot not found at {snapshot_path}. "
            "Run `python scripts/refresh_universe.py` to generate it."
        )

    with snapshot_path.open(encoding="utf-8") as f:
        raw = json.load(f)

    snapshot_date: date | None = None
    if "snapshot_date" in raw:
        try:
            snapshot_date = date.fromisoformat(raw["snapshot_date"])
        except ValueError:
            logger.warning("Invalid snapshot_date in universe snapshot; ignoring")

    tickers: List[TickerMetadata] = []
    for item in raw.get("tickers", []):
        try:
            tickers.append(
                TickerMetadata(
                    symbol_ars=item["symbol_ars"],
                    name=item["name"],
                    asset_type=AssetType(item["asset_type"]),
                    symbol_underlying=item.get("symbol_underlying"),
                    cedear_ratio_str=item.get("cedear_ratio_str"),
                    cedears_per_underlying=item.get("cedears_per_underlying"),
                    isin=item.get("isin"),
                    source_snapshot_date=snapshot_date,
                )
            )
        except (KeyError, ValueError) as exc:
            logger.warning("Skipping malformed universe entry %s: %s", item, exc)

    logger.info("Loaded %d tickers from universe snapshot (%s)", len(tickers), snapshot_path)
    return tickers
