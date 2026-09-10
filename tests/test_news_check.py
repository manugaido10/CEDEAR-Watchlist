"""Tests for analysis/reversal/news_check.py — parser and date-bound guards."""

from __future__ import annotations

from datetime import date

import pytest

from analysis.reversal.news_check import (
    NewsCheckStatus,
    _extract_dates,
    _has_future_date,
    _has_only_stale_dates,
    _parse_response,
)

SCAN_DATE = date(2026, 9, 9)


# ── _has_future_date ──────────────────────────────────────────────────────────

class TestHasFutureDate:
    def test_past_date_not_flagged(self):
        assert not _has_future_date("MarketBeat, September 5, 2026", SCAN_DATE)

    def test_same_day_not_flagged(self):
        assert not _has_future_date("MarketBeat, September 9, 2026", SCAN_DATE)

    def test_future_month_day_year_flagged(self):
        assert _has_future_date("MarketBeat, September 26, 2026", SCAN_DATE)

    def test_future_abbreviated_month_flagged(self):
        assert _has_future_date("Sep 26, 2026", SCAN_DATE)

    def test_future_dd_month_year_flagged(self):
        assert _has_future_date("26 September 2026", SCAN_DATE)

    def test_future_iso_date_flagged(self):
        assert _has_future_date("2026-09-26", SCAN_DATE)

    def test_past_iso_date_not_flagged(self):
        assert not _has_future_date("2026-08-15", SCAN_DATE)

    def test_no_date_in_text(self):
        assert not _has_future_date("Analyst downgraded the stock without a date", SCAN_DATE)

    def test_different_year_future(self):
        assert _has_future_date("January 1, 2027", SCAN_DATE)

    def test_different_year_past(self):
        assert not _has_future_date("January 1, 2025", SCAN_DATE)


# ── _parse_response future-date guard ─────────────────────────────────────────

class TestParseResponseFutureDateGuard:
    def test_future_date_warn_returns_unverified(self):
        llm = "WARN: Analyst | Price target cut | MarketBeat, September 26, 2026"
        result = _parse_response(llm, "COST.BA", SCAN_DATE)
        assert result.status == NewsCheckStatus.UNVERIFIED
        assert "alucinación" in result.warnings[0]

    def test_future_date_iso_warn_returns_unverified(self):
        llm = "WARN: Guidance | Profit warning issued | Reuters, 2026-09-15"
        result = _parse_response(llm, "TEST.BA", SCAN_DATE)
        assert result.status == NewsCheckStatus.UNVERIFIED

    def test_past_date_warn_returns_verified_warning(self):
        llm = "WARN: Analyst | Downgrade to Hold | MarketBeat, September 5, 2026"
        result = _parse_response(llm, "COST.BA", SCAN_DATE)
        assert result.status == NewsCheckStatus.VERIFIED_WARNING
        assert len(result.warnings) == 1

    def test_mixed_future_and_past_warns_keeps_past_only(self):
        llm = (
            "WARN: Analyst | Downgrade issued | MarketBeat, September 5, 2026\n"
            "WARN: Calendar | Earnings call | Benzinga, September 26, 2026"
        )
        result = _parse_response(llm, "COST.BA", SCAN_DATE)
        assert result.status == NewsCheckStatus.VERIFIED_WARNING
        assert len(result.warnings) == 1
        assert "September 5" in result.warnings[0]

    def test_warn_without_date_passes_through(self):
        llm = "WARN: Litigation | SEC investigation announced | Reuters"
        result = _parse_response(llm, "XYZ.BA", SCAN_DATE)
        assert result.status == NewsCheckStatus.VERIFIED_WARNING

    def test_clear_still_works(self):
        result = _parse_response("CLEAR", "XYZ.BA", SCAN_DATE)
        assert result.status == NewsCheckStatus.VERIFIED_CLEAR
        assert result.warnings == []

    def test_unverified_still_works(self):
        result = _parse_response("UNVERIFIED", "XYZ.BA", SCAN_DATE)
        assert result.status == NewsCheckStatus.UNVERIFIED


# ── _extract_dates ────────────────────────────────────────────────────────────

class TestExtractDates:
    def test_iso_date(self):
        assert date(2026, 8, 5) in _extract_dates("Reuters, 2026-08-05")

    def test_month_dd_yyyy(self):
        assert date(2026, 8, 5) in _extract_dates("August 5, 2026")

    def test_dd_month_yyyy(self):
        assert date(2026, 8, 5) in _extract_dates("5 August 2026")

    def test_multiple_dates(self):
        dates = _extract_dates("August 5, 2026 and 2026-09-01")
        assert date(2026, 8, 5) in dates
        assert date(2026, 9, 1) in dates

    def test_no_date(self):
        assert _extract_dates("SEC investigation announced") == []

    def test_invalid_date_skipped(self):
        # February 30 is invalid — should not raise, just skip
        assert _extract_dates("February 30, 2026") == []


# ── _has_only_stale_dates ─────────────────────────────────────────────────────

class TestHasOnlyStaleDates:
    # SCAN_DATE = 2026-09-09; cutoff = 2026-08-10

    def test_date_exactly_at_cutoff_is_not_stale(self):
        # 2026-08-10 == cutoff — not strictly before, so not stale
        assert not _has_only_stale_dates("MarketBeat, August 10, 2026", SCAN_DATE)

    def test_date_one_day_before_cutoff_is_stale(self):
        # 2026-08-09 < cutoff → stale
        assert _has_only_stale_dates("MarketBeat, August 9, 2026", SCAN_DATE)

    def test_date_33_days_ago_is_stale(self):
        # Matches real SATL.BA case: 2026-08-05 is 35 days before 2026-09-09
        assert _has_only_stale_dates("MarketBeat, August 5, 2026", SCAN_DATE)

    def test_date_34_days_ago_iso_is_stale(self):
        assert _has_only_stale_dates("Reuters, 2026-08-06", SCAN_DATE)

    def test_recent_date_not_stale(self):
        assert not _has_only_stale_dates("MarketBeat, September 5, 2026", SCAN_DATE)

    def test_no_date_is_not_stale(self):
        # No date → passes through (not stale)
        assert not _has_only_stale_dates("SEC investigation announced", SCAN_DATE)

    def test_mixed_stale_and_recent_dates_not_stale(self):
        # One date in window → not stale overall
        text = "August 5, 2026 and September 5, 2026"
        assert not _has_only_stale_dates(text, SCAN_DATE)


# ── _parse_response lower-bound (stale date) guard ───────────────────────────

class TestParseResponseStaleDateGuard:
    def test_stale_warn_returns_clear(self):
        # 2026-08-05 is 35 days before 2026-09-09 → outside 30-day window → CLEAR
        llm = "WARN: Analyst | Downgrade issued | MarketBeat, August 5, 2026"
        result = _parse_response(llm, "SATL.BA", SCAN_DATE)
        assert result.status == NewsCheckStatus.VERIFIED_CLEAR
        assert result.warnings == []

    def test_stale_iso_warn_returns_clear(self):
        # Matches real PG.BA case: 2026-08-07 is 33 days before 2026-09-09
        llm = "WARN: Analyst | Argus downgraded to Hold | Reuters, 2026-08-07"
        result = _parse_response(llm, "PG.BA", SCAN_DATE)
        assert result.status == NewsCheckStatus.VERIFIED_CLEAR

    def test_recent_warn_still_passes(self):
        llm = "WARN: Analyst | Downgrade | MarketBeat, September 5, 2026"
        result = _parse_response(llm, "COST.BA", SCAN_DATE)
        assert result.status == NewsCheckStatus.VERIFIED_WARNING

    def test_mixed_stale_and_valid_keeps_valid_only(self):
        llm = (
            "WARN: Analyst | Old downgrade | MarketBeat, August 5, 2026\n"
            "WARN: Guidance | Profit warning | Reuters, September 5, 2026"
        )
        result = _parse_response(llm, "XYZ.BA", SCAN_DATE)
        assert result.status == NewsCheckStatus.VERIFIED_WARNING
        assert len(result.warnings) == 1
        assert "Profit warning" in result.warnings[0]

    def test_no_date_warn_passes_through(self):
        # Finding without any date is not filtered by either bound guard
        llm = "WARN: Regulatory | SEC investigation announced | Reuters"
        result = _parse_response(llm, "XYZ.BA", SCAN_DATE)
        assert result.status == NewsCheckStatus.VERIFIED_WARNING

    def test_stale_and_future_mix_returns_unverified(self):
        # Future date takes priority over stale: no valid_warn, but future_count > 0
        llm = (
            "WARN: Analyst | Old downgrade | MarketBeat, August 5, 2026\n"
            "WARN: Calendar | Earnings call | Benzinga, September 26, 2026"
        )
        result = _parse_response(llm, "XYZ.BA", SCAN_DATE)
        assert result.status == NewsCheckStatus.UNVERIFIED
