"""Tests for data/adoption.py — signal-matching window logic.

Focused on find_signal_backed_candidates() since that's where the real risk is.
All inputs are synthetic — no file I/O, no CSV parsing, no signal_registry calls.
"""

from __future__ import annotations

import pytest

from data.adoption import AdoptionCandidate, find_signal_backed_candidates
from data.reconciler import InCsvNotInLog


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _entry(
    ticker: str = "AAPL",
    csv_qty: float = 100.0,
    csv_avg_cost_ars: float = 5000.0,
    csv_first_buy_date: str = "2026-01-10",
) -> InCsvNotInLog:
    return InCsvNotInLog(
        ticker=ticker,
        csv_qty=csv_qty,
        csv_avg_cost_ars=csv_avg_cost_ars,
        csv_first_buy_date=csv_first_buy_date,
        csv_last_trade_date=csv_first_buy_date,
        note="needs manual entry criteria",
    )


def _signal(
    symbol: str = "AAPL.BA",
    scan_date: str = "2026-01-05",
    score: float = 7.5,
    invalidation_level_ars: float = 4800.0,
) -> dict:
    return {
        "symbol": symbol,
        "scan_date": scan_date,
        "score": score,
        "invalidation_level_ars": invalidation_level_ars,
        "entry_price_ars": 5000.0,
    }


# ---------------------------------------------------------------------------
# Case 1 — signal on same day as buy → adopts
# ---------------------------------------------------------------------------

def test_signal_same_day_as_buy_adopts():
    entry = _entry(ticker="AAPL", csv_first_buy_date="2026-01-10")
    sig = _signal(symbol="AAPL.BA", scan_date="2026-01-10")

    candidates, manual = find_signal_backed_candidates([entry], [sig], matching_window_days=5)

    assert len(candidates) == 1
    assert manual == []
    c: AdoptionCandidate = candidates[0]
    assert c.ticker == "AAPL"
    assert c.log_symbol == "AAPL.BA"
    assert c.matched_signal_scan_date == "2026-01-10"
    assert c.matched_signal_score == 7.5
    assert c.matched_signal_invalidation_ars == 4800.0
    assert c.csv_qty == 100.0
    assert c.csv_avg_cost_ars == 5000.0
    assert c.note == ""


# ---------------------------------------------------------------------------
# Case 2 — signal 3 days before buy, within a 5-day window → adopts
# ---------------------------------------------------------------------------

def test_signal_three_days_before_buy_within_window_adopts():
    entry = _entry(ticker="DECK", csv_first_buy_date="2026-01-10")
    sig = _signal(symbol="DECK.BA", scan_date="2026-01-07")  # 3 days before

    candidates, manual = find_signal_backed_candidates([entry], [sig], matching_window_days=5)

    assert len(candidates) == 1
    assert manual == []
    assert candidates[0].matched_signal_scan_date == "2026-01-07"


# ---------------------------------------------------------------------------
# Case 3 — signal 10 days before buy, outside 5-day window → stays manual
# ---------------------------------------------------------------------------

def test_signal_ten_days_before_buy_outside_window_stays_manual():
    entry = _entry(ticker="GLOB", csv_first_buy_date="2026-01-10")
    sig = _signal(symbol="GLOB.BA", scan_date="2025-12-31")  # 10 days before

    candidates, manual = find_signal_backed_candidates([entry], [sig], matching_window_days=5)

    assert candidates == []
    assert len(manual) == 1
    assert manual[0].ticker == "GLOB"


# ---------------------------------------------------------------------------
# Case 4 — signal AFTER buy date → never adopts (even if only 1 day after)
# ---------------------------------------------------------------------------

def test_signal_after_buy_date_never_adopts():
    entry = _entry(ticker="LRCX", csv_first_buy_date="2026-01-10")
    sig = _signal(symbol="LRCX.BA", scan_date="2026-01-11")  # 1 day after

    candidates, manual = find_signal_backed_candidates([entry], [sig], matching_window_days=5)

    assert candidates == []
    assert len(manual) == 1


# ---------------------------------------------------------------------------
# Case 5 — multiple signals in window → picks closest (most recent scan_date)
# ---------------------------------------------------------------------------

def test_multiple_signals_picks_closest():
    entry = _entry(ticker="SEMI", csv_first_buy_date="2026-01-10")
    sig_far = _signal(symbol="SEMI", scan_date="2026-01-05", score=6.0, invalidation_level_ars=95.0)
    sig_close = _signal(symbol="SEMI", scan_date="2026-01-08", score=8.0, invalidation_level_ars=90.0)

    candidates, manual = find_signal_backed_candidates(
        [entry], [sig_far, sig_close], matching_window_days=5
    )

    assert len(candidates) == 1
    assert manual == []
    c: AdoptionCandidate = candidates[0]
    # 2026-01-08 is closer to 2026-01-10 than 2026-01-05
    assert c.matched_signal_scan_date == "2026-01-08"
    assert c.matched_signal_score == 8.0
    assert "múltiples señales" in c.note
    assert "2026-01-08" in c.note


# ---------------------------------------------------------------------------
# Case 6 — no signals at all → everything stays manual
# ---------------------------------------------------------------------------

def test_no_signals_all_manual():
    entries = [
        _entry(ticker="AAPL", csv_first_buy_date="2026-01-10"),
        _entry(ticker="DECK", csv_first_buy_date="2026-01-15"),
    ]

    candidates, manual = find_signal_backed_candidates(entries, [], matching_window_days=5)

    assert candidates == []
    assert len(manual) == 2


# ---------------------------------------------------------------------------
# Case 7 — ticker mismatch (signal is for a different ticker) → stays manual
# ---------------------------------------------------------------------------

def test_ticker_mismatch_stays_manual():
    entry = _entry(ticker="AAPL", csv_first_buy_date="2026-01-10")
    sig = _signal(symbol="DECK.BA", scan_date="2026-01-08")  # different ticker

    candidates, manual = find_signal_backed_candidates([entry], [sig], matching_window_days=5)

    assert candidates == []
    assert len(manual) == 1


# ---------------------------------------------------------------------------
# Case 8 — .BA suffix on signal symbol normalises correctly
# ---------------------------------------------------------------------------

def test_ba_suffix_normalised_for_matching():
    # CSV ticker is bare "AAPL"; signal symbol is "AAPL.BA" — should match.
    entry = _entry(ticker="AAPL", csv_first_buy_date="2026-01-10")
    sig = _signal(symbol="AAPL.BA", scan_date="2026-01-09")

    candidates, manual = find_signal_backed_candidates([entry], [sig], matching_window_days=5)

    assert len(candidates) == 1
    assert candidates[0].log_symbol == "AAPL.BA"


# ---------------------------------------------------------------------------
# Case 9 — mixed: one entry matches, one doesn't
# ---------------------------------------------------------------------------

def test_mixed_some_match_some_manual():
    entries = [
        _entry(ticker="AAPL", csv_first_buy_date="2026-01-10"),
        _entry(ticker="GLOB", csv_first_buy_date="2026-01-10"),
    ]
    # Only AAPL has a signal in window; GLOB has none.
    signals = [_signal(symbol="AAPL.BA", scan_date="2026-01-08")]

    candidates, manual = find_signal_backed_candidates(entries, signals, matching_window_days=5)

    assert len(candidates) == 1
    assert candidates[0].ticker == "AAPL"
    assert len(manual) == 1
    assert manual[0].ticker == "GLOB"


# ---------------------------------------------------------------------------
# Case 10 — entry with empty csv_first_buy_date → stays manual, no crash
# ---------------------------------------------------------------------------

def test_empty_buy_date_stays_manual():
    entry = _entry(ticker="TXAR", csv_first_buy_date="")
    sig = _signal(symbol="TXAR.BA", scan_date="2026-01-08")

    candidates, manual = find_signal_backed_candidates([entry], [sig], matching_window_days=5)

    assert candidates == []
    assert len(manual) == 1


# ---------------------------------------------------------------------------
# Case 11 — window of 0 days: only same-day signals match
# ---------------------------------------------------------------------------

def test_window_zero_only_same_day_matches():
    entry = _entry(ticker="BYMA", csv_first_buy_date="2026-01-10")
    sig_same = _signal(symbol="BYMA", scan_date="2026-01-10")
    sig_day_before = _signal(symbol="BYMA", scan_date="2026-01-09")

    candidates_same, _ = find_signal_backed_candidates([entry], [sig_same], matching_window_days=0)
    candidates_prev, manual_prev = find_signal_backed_candidates(
        [entry], [sig_day_before], matching_window_days=0
    )

    assert len(candidates_same) == 1
    assert candidates_prev == []
    assert len(manual_prev) == 1
