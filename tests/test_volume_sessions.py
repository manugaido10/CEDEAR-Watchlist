"""P2: vol_ratio_clean over valid sessions (phantom bars, NYSE-closed days)."""
from datetime import date

import numpy as np
import pandas as pd

from analysis.reversal.volume_sessions import (
    compute_phantom_days,
    has_us_underlying,
    valid_session_mask,
    volume_ratio_clean,
)
from data.market_calendar import (
    LAST_COVERED_YEAR,
    NYSE_CLOSED_DATES,
    nyse_closed,
)
from data.models import AssetType, FetchStatus, PriceHistory, TickerBundle, TickerMetadata


def _df(days, vols, flat_idx=()):
    idx = pd.DatetimeIndex(days)
    n = len(idx)
    px = 100.0 + np.arange(n, dtype=float)
    df = pd.DataFrame(
        {"open": px, "high": px + 1, "low": px - 1, "close": px + 0.5, "volume": vols}, index=idx
    )
    for i in flat_idx:
        df.iloc[i, df.columns.get_indexer(["open", "high", "low", "close"])] = px[i]
    return df


def _bundle(df, sym="X.BA", underlying="X", asset=AssetType.CEDEAR):
    return TickerBundle(
        metadata=TickerMetadata(symbol_ars=sym, name=sym, asset_type=asset,
                                symbol_underlying=underlying),
        prices_ars=PriceHistory(symbol=sym, data=df), ccl_series=None, mep_series=None,
        fundamentals=None, status=FetchStatus.OK,
    )


def _bdays(n, end="2026-11-20"):
    return pd.bdate_range(end=end, periods=n)


# ── calendar ──────────────────────────────────────────────────────────────────

def test_nyse_closed_known_days():
    assert nyse_closed(date(2026, 11, 26))      # Thanksgiving
    assert nyse_closed(date(2025, 1, 9))        # Carter
    assert nyse_closed(date(2026, 11, 28))      # Saturday
    assert not nyse_closed(date(2026, 11, 10))  # BYMA holiday, NYSE open
    assert not nyse_closed(date(2026, 11, 27))


def test_calendar_not_stale():
    assert date.today().year <= LAST_COVERED_YEAR, "extend data/market_calendar.py"
    assert all(d.weekday() < 5 for d in NYSE_CLOSED_DATES)


# ── phantom days ──────────────────────────────────────────────────────────────

def _universe(day_flat_fraction, day, n=40):
    days = list(_bdays(30))
    bundles = []
    k = int(round(n * day_flat_fraction))
    for i in range(n):
        df = _df(days, [100] * 30)
        if i < k:
            j = days.index(pd.Timestamp(day))
            df.iloc[j, df.columns.get_indexer(["open", "high", "low", "close"])] = 100.0
            df.iloc[j, df.columns.get_loc("volume")] = 0
        bundles.append(_bundle(df, sym=f"T{i}.BA"))
    return bundles


def test_phantom_day_flagged_at_threshold():
    ph = compute_phantom_days(_universe(0.30, "2026-11-10"))
    assert ph == frozenset({date(2026, 11, 10)})


def test_day_below_threshold_not_flagged():
    assert compute_phantom_days(_universe(0.20, "2026-11-10")) == frozenset()


def test_small_universe_never_flags():
    assert compute_phantom_days(_universe(1.0, "2026-11-10", n=5)) == frozenset()


# ── exclusion ─────────────────────────────────────────────────────────────────

def test_phantom_day_excludes_flat_zero_bars_only():
    days = _bdays(30)
    d = date(2026, 11, 10)
    i = list(days).index(pd.Timestamp(d))
    df = _df(days, [100] * 30, flat_idx=[i])
    df.iloc[i, df.columns.get_loc("volume")] = 0
    keep = valid_session_mask(df, frozenset({d}), us_underlying=False)
    assert not keep[i] and keep.sum() == 29
    # a real (non-flat) bar on the phantom day stays
    df2 = _df(days, [100] * 30)
    assert valid_session_mask(df2, frozenset({d}), False).all()


def test_nyse_closed_excludes_bar_for_us_underlying_only():
    days = _bdays(30, end="2026-11-27")
    i = list(days).index(pd.Timestamp("2026-11-26"))
    df = _df(days, [100] * 30)
    assert not valid_session_mask(df, frozenset(), True)[i]
    assert valid_session_mask(df, frozenset(), False)[i]


def test_illiquid_zero_volume_on_normal_day_stays_in_window():
    days = _bdays(30)
    i = 10
    df = _df(days, [100] * 30, flat_idx=[i])
    df.iloc[i, df.columns.get_loc("volume")] = 0
    keep = valid_session_mask(df, frozenset(), us_underlying=True)
    assert keep.all()
    vols = df["volume"].values[keep]
    assert 0 in vols


def test_windows_always_have_20_valid_sessions():
    days = _bdays(30, end="2026-11-27")
    df = _df(days, list(range(1, 31)))
    r = volume_ratio_clean(df, frozenset(), True)
    keep = valid_session_mask(df, frozenset(), True)
    v = df["volume"].values[keep]
    assert r == np.mean(v[-5:]) / np.mean(v[-20:])
    # too few valid sessions -> None
    # 20 bars with 1 NYSE-closed day -> 19 valid sessions -> no ratio
    assert volume_ratio_clean(df.iloc[-20:], frozenset(), True) is None


def test_ratio_matches_plain_when_nothing_excluded():
    days = _bdays(25)
    vols = list(range(10, 35))
    df = _df(days, vols)
    plain = np.mean(vols[-5:]) / np.mean(vols[-20:])
    assert abs(volume_ratio_clean(df, frozenset(), True) - plain) < 1e-12


def test_has_us_underlying():
    df = _df(_bdays(5), [1] * 5)
    assert has_us_underlying(_bundle(df))
    assert not has_us_underlying(_bundle(df, underlying=None))
    assert not has_us_underlying(_bundle(df, asset=AssetType.ARGENTINE_STOCK, underlying=None))


# ── recording ─────────────────────────────────────────────────────────────────

def test_signal_and_near_miss_records_carry_both_ratios(tmp_path, monkeypatch):
    import json
    from analysis.reversal import near_miss_tracker as nm, signal_registry as sr
    from analysis.reversal.near_miss_tracker import NearMissRecord
    from analysis.reversal.reversal_scanner import ReversalOpportunity

    monkeypatch.setattr(sr, "SIGNALS_PATH", tmp_path / "signals.jsonl", raising=False)
    monkeypatch.setattr(nm, "NEAR_MISSES_PATH", tmp_path / "nm.jsonl")
    opp = ReversalOpportunity(
        symbol="ADI.BA", name="ADI", asset_type="cedear", score=70.0, rsi_14=35.0,
        entry_price_ars=100.0, nearest_support=98.0, nearest_support_type="MA50",
        distance_to_support_pct=0.02, catalyst=[], volume_ratio=0.747,
        weekly_trend="neutral", invalidation_level_ars=96.5, invalidation_rationale="x",
        volume_ratio_clean=0.828,
    )
    captured = []
    monkeypatch.setattr(sr, "_append_record", captured.append)
    monkeypatch.setattr(sr, "load_signals", lambda: [])
    sr.record_signals([opp], "2026-11-27")
    assert captured[0]["vol_ratio"] == 0.747 and captured[0]["vol_ratio_clean"] == 0.828

    rec = NearMissRecord(
        scan_date="2026-11-27", symbol="ADI.BA", failed_criteria=["vol_ratio_high"], margins={},
        computed_score=50.0, rsi=40.0, vol_ratio=0.85, support_distance_pct=2.0,
        weekly_trend="neutral", vol_ratio_clean=0.7,
    )
    nm._append_record(rec)
    line = json.loads((tmp_path / "nm.jsonl").read_text().splitlines()[0])
    assert line["vol_ratio"] == 0.85 and line["vol_ratio_clean"] == 0.7
