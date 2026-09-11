"""Tests for analysis/reversal/news_check.py — parser and date-bound guards."""

from __future__ import annotations

from datetime import date

import pytest

from analysis.reversal.news_check import (
    CALENDAR_MAX_HORIZON_DAYS,
    NewsCheckStatus,
    _extract_dates,
    _extract_warn_category,
    _has_future_date,
    _has_future_date_beyond_horizon,
    _has_only_stale_dates,
    _is_calendar_warn,
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

    def test_mixed_future_and_past_warns_keeps_both_when_calendar_within_horizon(self):
        # Calendar finding 17 days ahead is within the 90-day horizon → valid.
        # Both the Analyst (past) and Calendar (upcoming) findings should survive.
        llm = (
            "WARN: Analyst | Downgrade issued | MarketBeat, September 5, 2026\n"
            "WARN: Calendar | Earnings call | Benzinga, September 26, 2026"
        )
        result = _parse_response(llm, "COST.BA", SCAN_DATE)
        assert result.status == NewsCheckStatus.VERIFIED_WARNING
        assert len(result.warnings) == 2

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

    def test_stale_analyst_plus_upcoming_calendar_returns_verified_warning(self):
        # Stale Analyst finding is discarded; Calendar 17 days ahead (within 90d) is valid.
        llm = (
            "WARN: Analyst | Old downgrade | MarketBeat, August 5, 2026\n"
            "WARN: Calendar | Earnings call | Benzinga, September 26, 2026"
        )
        result = _parse_response(llm, "XYZ.BA", SCAN_DATE)
        assert result.status == NewsCheckStatus.VERIFIED_WARNING
        assert len(result.warnings) == 1
        assert "Earnings call" in result.warnings[0]


# ── Calendar category exemption (Decision #27e) ───────────────────────────────

class TestCalendarCategoryExemption:
    """Calendar WARN lines accept future dates up to CALENDAR_MAX_HORIZON_DAYS.

    The original false-positive: FDX ex-dividend Sep 14, 2026 (3 days ahead of
    Sep 11 scan) was discarded as a hallucination — this class verifies the fix.
    """

    # SCAN_DATE = 2026-09-09

    def test_ex_dividend_3_days_ahead_passes(self):
        # Sep 12 is 3 days after SCAN_DATE (2026-09-09) — well within 90 days.
        llm = "WARN: Calendar | ex-dividend date | FedEx IR, September 12, 2026"
        result = _parse_response(llm, "FDX.BA", SCAN_DATE)
        assert result.status == NewsCheckStatus.VERIFIED_WARNING
        assert len(result.warnings) == 1

    def test_lockup_expiry_60_days_ahead_passes(self):
        # Nov 8 is 60 days after SCAN_DATE — within 90-day horizon.
        llm = "WARN: Calendar | lock-up expiry | Bloomberg, November 8, 2026"
        result = _parse_response(llm, "XYZ.BA", SCAN_DATE)
        assert result.status == NewsCheckStatus.VERIFIED_WARNING

    def test_calendar_event_beyond_horizon_is_discarded(self):
        # 2027-12-01 is far beyond 90 days → treated as hallucination → UNVERIFIED.
        llm = "WARN: Calendar | regulatory decision | Reuters, December 1, 2027"
        result = _parse_response(llm, "XYZ.BA", SCAN_DATE)
        assert result.status == NewsCheckStatus.UNVERIFIED
        assert "alucinación" in result.warnings[0]

    def test_calendar_numeric_category_5_also_exempt(self):
        # Model sometimes returns the numeric index from the prompt ("5") instead of "Calendar".
        llm = "WARN: 5 | ex-dividend date | Reuters, September 20, 2026"
        result = _parse_response(llm, "FDX.BA", SCAN_DATE)
        assert result.status == NewsCheckStatus.VERIFIED_WARNING

    def test_analyst_future_date_still_discarded(self):
        # Non-Calendar category with future date → UNVERIFIED (existing behavior unchanged).
        llm = "WARN: Analyst | Price target cut | MarketBeat, September 26, 2026"
        result = _parse_response(llm, "COST.BA", SCAN_DATE)
        assert result.status == NewsCheckStatus.UNVERIFIED
        assert "alucinación" in result.warnings[0]

    def test_analyst_numeric_category_1_future_date_still_discarded(self):
        # Numeric "1" (Analyst) with future date → UNVERIFIED.
        llm = "WARN: 1 | Price target cut | MarketBeat, September 26, 2026"
        result = _parse_response(llm, "COST.BA", SCAN_DATE)
        assert result.status == NewsCheckStatus.UNVERIFIED


# ── _is_calendar_warn / _extract_warn_category ───────────────────────────────

class TestCalendarWarnHelpers:
    def test_named_calendar(self):
        assert _is_calendar_warn("WARN: Calendar | ex-dividend | Reuters, Sep 20, 2026")

    def test_numeric_5(self):
        assert _is_calendar_warn("WARN: 5 | lock-up expiry | Bloomberg, Oct 1, 2026")

    def test_analyst_not_calendar(self):
        assert not _is_calendar_warn("WARN: Analyst | downgrade | MarketBeat, Sep 5, 2026")

    def test_numeric_1_not_calendar(self):
        assert not _is_calendar_warn("WARN: 1 | downgrade | MarketBeat, Sep 5, 2026")

    def test_category_case_insensitive(self):
        assert _is_calendar_warn("WARN: CALENDAR | ex-div | Reuters, Sep 20, 2026")

    def test_extract_category_named(self):
        assert _extract_warn_category("WARN: Analyst | downgrade | source") == "analyst"

    def test_extract_category_numeric(self):
        assert _extract_warn_category("WARN: 5 | event | source") == "5"


# ── _has_future_date_beyond_horizon ──────────────────────────────────────────

class TestHasFutureDateBeyondHorizon:
    def test_date_within_horizon_not_flagged(self):
        # 30 days ahead, horizon = 90 → not beyond
        assert not _has_future_date_beyond_horizon("October 9, 2026", SCAN_DATE, 90)

    def test_date_exactly_at_horizon_not_flagged(self):
        # 90 days after 2026-09-09 = 2026-12-08
        assert not _has_future_date_beyond_horizon("December 8, 2026", SCAN_DATE, 90)

    def test_date_one_day_beyond_horizon_flagged(self):
        # 91 days after → beyond
        assert _has_future_date_beyond_horizon("December 9, 2026", SCAN_DATE, 90)

    def test_past_date_not_flagged(self):
        assert not _has_future_date_beyond_horizon("August 1, 2026", SCAN_DATE, 90)

    def test_no_date_not_flagged(self):
        assert not _has_future_date_beyond_horizon("no date here", SCAN_DATE, 90)
