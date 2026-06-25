"""Filter 2 — deep dive analysis on Filter 1 survivors.

Public API:
  run_filter2(survivors, bundles, cache, ...) → Filter2Report

See filter2_runner.py for orchestration logic and DISENO_FILTRO_2.md for spec.
"""

from .filter2_runner import run_filter2
from .filter2_models import Filter2Report, Filter2Opportunity
from .technical_scoring import clear_benchmark_cache

__all__ = [
    "run_filter2",
    "Filter2Report",
    "Filter2Opportunity",
    "clear_benchmark_cache",
]
