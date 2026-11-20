"""Golden test: _weekly_trend classification must not change (Fase B1).

The fixture was captured from the pre-change implementation. Extending
_weekly_trend to expose the MA50 slope is instrumentation only — label and
strength must stay bit-identical on every case.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from analysis.reversal.reversal_scanner import _weekly_trend

_FIXTURE = Path(__file__).parent / "fixtures" / "weekly_trend_golden.json"
_CASES = json.loads(_FIXTURE.read_text(encoding="utf-8"))["cases"]


def _df(case: dict) -> pd.DataFrame:
    return pd.DataFrame({"close": case["close"]}, index=pd.to_datetime(case["dates"]))


@pytest.mark.parametrize("case", _CASES, ids=[c["name"] for c in _CASES])
def test_weekly_trend_matches_golden(case):
    label, strength = _weekly_trend(_df(case))
    assert label == case["expected_label"]
    assert strength == case["expected_strength"]
