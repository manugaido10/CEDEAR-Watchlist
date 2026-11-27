"""P4 report: --since (clean corpus) and the decision-point date count."""

from __future__ import annotations

from scripts import outcomes_v2_report as rep


class TestReport:
    RECS = [
        {"scan_date": "2026-09-10", "status_v2": "stop_hit"},          # before --since
        {"scan_date": "2026-09-11", "status_v2": "stop_hit"},
        {"scan_date": "2026-09-11", "status_v2": "target_5pct"},       # same date: counted once
        {"scan_date": "2026-09-12", "status_v2": "no_entry_gap"},
        {"scan_date": "2026-09-13", "status_v2": "lateral"},
        {"scan_date": "2026-09-14", "status_v2": "unresolved_data_error"},
        {"scan_date": "2026-09-15", "status_v2": "not_instrumented"},
        {"scan_date": "2026-09-16", "status_v2": "pending"},
        {"scan_date": "2026-09-17", "status_v2": "stop_hit", "counterfactual": True},
    ]

    def test_decision_point_counts_only_measured_clean_dates(self):
        assert rep.decision_point_dates(self.RECS, "2026-09-11") == ["2026-09-11", "2026-09-12", "2026-09-13"]

    def test_default_since_is_audit_clean_corpus(self):
        assert rep.CLEAN_SINCE == "2026-09-11" and rep.DECISION_POINT_DATES == 36

    def test_since_changes_the_corpus(self):
        assert len(rep.decision_point_dates(self.RECS, "2026-09-01")) == 4
