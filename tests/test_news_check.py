"""Tests for analysis/reversal/news_check.py — parser and future-date guard."""

from __future__ import annotations

from datetime import date

import pytest

from analysis.reversal.news_check import (
    NewsCheckStatus,
    _has_future_date,
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
