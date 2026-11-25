"""Suite-wide guard: no test may reach the network through the ex-dividend check.

``analysis.reversal.reversal_scanner.check_ex_dividend`` calls yfinance. Tests
that exercise it on purpose (tests/test_dividends.py) inject a fetcher or patch
it themselves; everything else gets an empty, offline result.
"""
from __future__ import annotations

import pytest

from data.dividends import ExDividendResult


@pytest.fixture(autouse=True)
def _offline_ex_dividend(monkeypatch):
    monkeypatch.setattr(
        "analysis.reversal.reversal_scanner.check_ex_dividend",
        lambda symbol_underlying, *a, **k: ExDividendResult(),
    )
