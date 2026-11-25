"""Tests for news-check evidence recording (Decision #39). No real API calls."""

from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace

import pytest

import analysis.reversal.news_check as nc
import analysis.reversal.signal_registry as sr
from analysis.reversal.news_check import (
    NEWS_EVIDENCE_VERSION,
    NEWS_PROMPT_VERSION,
    NEWS_RECORD_KEYS,
    NEWS_EVIDENCE_MAX_RESULTS,
    NEWS_REVERSAL_MAX_CITATIONS,
    NEWS_REVERSAL_MAX_SEARCHES,
    NewsCheckResult,
    NewsCheckStatus,
    NewsEvidence,
    _cache_key,
    _extract_evidence,
    _parse_response,
    _search_cached,
    fetch_news_context,
)
from analysis.reversal.reversal_scanner import ReversalOpportunity
from data.cache import Cache
from data.models import AssetType, FetchStatus, TickerBundle, TickerMetadata


# ── Mock response builders ───────────────────────────────────────────────────

def _result(url, title="t", page_age="2 days ago"):
    return SimpleNamespace(
        type="web_search_result", url=url, title=title,
        page_age=page_age, encrypted_content="ENC",
    )


def _citation(url, cited_text, title="t"):
    return SimpleNamespace(
        type="web_search_result_location", url=url, title=title,
        cited_text=cited_text, encrypted_index="IDX",
    )


def _text(text, citations=None):
    return SimpleNamespace(type="text", text=text, citations=citations)


def _search_block(content):
    return SimpleNamespace(type="web_search_tool_result", tool_use_id="srv_1", content=content)


def _response(content, web_search_requests=1, stop_reason="end_turn", usage=True):
    u = None
    if usage:
        u = SimpleNamespace(
            input_tokens=10, output_tokens=5,
            server_tool_use=SimpleNamespace(web_search_requests=web_search_requests),
        )
    return SimpleNamespace(content=content, usage=u, stop_reason=stop_reason)


def _bundle(symbol="AAPL.BA", underlying="AAPL", name="Apple Inc"):
    meta = TickerMetadata(
        symbol_ars=symbol, name=name, asset_type=AssetType.CEDEAR,
        symbol_underlying=underlying,
    )
    return TickerBundle(
        metadata=meta, prices_ars=None, ccl_series=None, mep_series=None,
        fundamentals=None, status=FetchStatus.OK,
    )


# ── Extraction ───────────────────────────────────────────────────────────────

class TestExtractEvidence:
    def test_results_with_page_age_no_snippet(self):
        resp = _response([
            _search_block([_result("https://a.com", "A", "April 2, 2026"), _result("https://b.com", page_age=None)]),
            _text("CLEAR"),
        ], web_search_requests=2)
        ev = _extract_evidence(resp)
        assert ev.results == [
            {"url": "https://a.com", "title": "A", "page_age": "April 2, 2026"},
            {"url": "https://b.com", "title": "t", "page_age": None},
        ]
        assert all("snippet" not in r for r in ev.results)
        assert ev.web_search_requests == 2
        assert ev.stop_reason == "end_turn"
        assert ev.search_errors == []

    def test_results_capped(self):
        items = [_result(f"https://x{i}.com") for i in range(NEWS_EVIDENCE_MAX_RESULTS + 4)]
        ev = _extract_evidence(_response([_search_block(items)]))
        assert len(ev.results) == NEWS_EVIDENCE_MAX_RESULTS

    def test_cited_url_from_4th_search_kept_past_cap(self):
        # 3 searches × 10 = 30 distinct URLs (> 20) before search #4.
        searches = [
            _search_block([_result(f"https://s{s}-{i}.com") for i in range(10)])
            for s in range(1, 4)
        ]
        searches.append(_search_block([_result("https://s4-cited.com", page_age="3 days ago")]))
        text = _text("WARN: Analyst | x | y", [_citation("https://s4-cited.com", "cut to hold")])
        ev = _extract_evidence(_response(searches + [text], web_search_requests=4))
        urls = [r["url"] for r in ev.results]
        assert "https://s4-cited.com" in urls
        assert len(ev.results) == NEWS_EVIDENCE_MAX_RESULTS  # 1 cited + 19 uncited fill
        cited = next(r for r in ev.results if r["url"] == "https://s4-cited.com")
        assert cited["page_age"] == "3 days ago"
        assert urls[-1] == "https://s4-cited.com"  # search order preserved

    def test_results_deduplicated_by_url_across_searches(self):
        resp = _response([
            _search_block([_result("https://a.com", page_age="1 days ago"), _result("https://b.com")]),
            _search_block([_result("https://a.com", page_age="9 days ago"), _result("https://c.com")]),
        ])
        ev = _extract_evidence(resp)
        assert [r["url"] for r in ev.results] == ["https://a.com", "https://b.com", "https://c.com"]
        assert ev.results[0]["page_age"] == "1 days ago"  # first occurrence wins

    def test_citations_deduplicated_by_url_and_text(self):
        c1 = _citation("https://a.com", "downgrade to hold")
        c1_dup = _citation("https://a.com", "downgrade to hold", title="other title")
        c2 = _citation("https://a.com", "different text")
        c3 = _citation("https://b.com", "downgrade to hold")
        resp = _response([_text("WARN: Analyst | x | y", [c1, c1_dup, c2]), _text("more", [c3, c1])])
        ev = _extract_evidence(resp)
        assert [(c["url"], c["cited_text"]) for c in ev.citations] == [
            ("https://a.com", "downgrade to hold"),
            ("https://a.com", "different text"),
            ("https://b.com", "downgrade to hold"),
        ]

    def test_citations_capped(self):
        cits = [_citation(f"https://x{i}.com", "t") for i in range(NEWS_REVERSAL_MAX_CITATIONS + 5)]
        ev = _extract_evidence(_response([_text("x", cits)]))
        assert len(ev.citations) == NEWS_REVERSAL_MAX_CITATIONS

    def test_error_block_is_object_not_list(self):
        err = SimpleNamespace(type="web_search_tool_result_error", error_code="max_uses_exceeded")
        resp = _response([_search_block([_result("https://a.com")]), _search_block(err), _text("CLEAR")])
        ev = _extract_evidence(resp)
        assert ev.search_errors == ["max_uses_exceeded"]
        assert len(ev.results) == 1

    def test_usage_absent(self):
        ev = _extract_evidence(_response([_text("CLEAR")], usage=False))
        assert ev.web_search_requests is None

    def test_server_tool_use_absent(self):
        resp = SimpleNamespace(content=[_text("CLEAR")], usage=SimpleNamespace(input_tokens=1))
        ev = _extract_evidence(resp)
        assert ev.web_search_requests is None
        assert ev.stop_reason is None

    def test_bare_object_never_raises(self):
        ev = _extract_evidence(object())
        assert ev == NewsEvidence()


# ── _web_search: request kwargs and fail-closed extraction ───────────────────

class _FakeClient:
    calls: list = []

    def __init__(self, response):
        self.messages = SimpleNamespace(create=self._create)
        self._response = response

    def _create(self, **kwargs):
        _FakeClient.calls.append(kwargs)
        return self._response


def _patch_client(monkeypatch, response):
    _FakeClient.calls = []
    monkeypatch.setattr(nc.anthropic, "Anthropic", lambda *a, **k: _FakeClient(response))


class TestWebSearch:
    def test_max_uses_passed(self, monkeypatch):
        _patch_client(monkeypatch, _response([_text("CLEAR")]))
        nc._web_search("prompt")
        tools = _FakeClient.calls[0]["tools"]
        assert tools[0]["type"] == "web_search_20250305"
        assert tools[0]["max_uses"] == NEWS_REVERSAL_MAX_SEARCHES
        assert _FakeClient.calls[0]["model"] == nc._ANTHROPIC_MODEL

    def test_returns_text_and_evidence(self, monkeypatch):
        _patch_client(monkeypatch, _response([_search_block([_result("https://a.com")]), _text("CLE"), _text("AR")]))
        text, ev = nc._web_search("prompt")
        assert text == "CLEAR"
        assert ev.results[0]["url"] == "https://a.com"

    def test_extraction_failure_keeps_text(self, monkeypatch, caplog):
        _patch_client(monkeypatch, _response([_text("CLEAR")]))

        def boom(_):
            raise RuntimeError("bad shape")

        monkeypatch.setattr(nc, "_extract_evidence", boom)
        with caplog.at_level("WARNING"):
            text, ev = nc._web_search("prompt")
        assert text == "CLEAR"
        assert ev is None
        assert "evidence extraction failed" in caplog.text


# ── Cache round trip ─────────────────────────────────────────────────────────

class TestCache:
    @pytest.fixture(autouse=True)
    def _no_sleep(self, monkeypatch):
        monkeypatch.setattr(nc.time, "sleep", lambda _s: None)

    def test_round_trip_with_evidence(self, tmp_path, monkeypatch):
        cache = Cache(tmp_path)
        evidence = NewsEvidence(
            results=[{"url": "https://a.com", "title": "A", "page_age": "1 day ago"}],
            citations=[{"url": "https://a.com", "title": "A", "cited_text": "cut"}],
            web_search_requests=3, search_errors=["max_uses_exceeded"], stop_reason="end_turn",
        )
        monkeypatch.setattr(nc, "_web_search", lambda p: ("CLEAR", evidence))
        text1, ev1, fc1 = _search_cached("q", "p", cache)
        assert (text1, fc1) == ("CLEAR", False)

        stored = cache.load_news(_cache_key("q"))
        assert stored["evidence_version"] == NEWS_EVIDENCE_VERSION
        assert stored["evidence"] == evidence.to_dict()

        monkeypatch.setattr(nc, "_web_search", lambda p: pytest.fail("must not re-search"))
        text2, ev2, fc2 = _search_cached("q", "p", cache)
        assert (text2, fc2) == ("CLEAR", True)
        assert ev2 == evidence

    def test_empty_response_not_cached(self, tmp_path, monkeypatch):
        cache = Cache(tmp_path)
        monkeypatch.setattr(nc, "_web_search", lambda p: ("", NewsEvidence(search_errors=["unavailable"])))
        text, ev, fc = _search_cached("q", "p", cache)
        assert text == "" and fc is False
        assert cache.load_news(_cache_key("q")) is None

    def test_legacy_entry_gives_null_evidence_same_verdict(self, tmp_path, monkeypatch):
        cache = Cache(tmp_path)
        bundle = _bundle()
        legacy_text = "WARN: Guidance | Profit warning | Reuters"
        cache.save_news(_cache_key(nc._build_query(bundle)), {
            "query": nc._build_query(bundle),
            "stage": "reversal_news",
            "llm_text": legacy_text,
            "cached_at": date.today().isoformat(),
        })
        monkeypatch.setattr(nc, "_web_search", lambda p: pytest.fail("must not re-search"))

        result = fetch_news_context(bundle, cache)
        expected = _parse_response(legacy_text, bundle.metadata.symbol_ars, date.today())
        assert result.status == expected.status == NewsCheckStatus.VERIFIED_WARNING
        assert result.warnings == expected.warnings
        assert result.evidence is None
        assert result.from_cache is True
        assert result.model == nc._ANTHROPIC_MODEL
        assert result.prompt_version == NEWS_PROMPT_VERSION

    def test_version_1_entry_is_legacy(self, tmp_path, monkeypatch):
        assert NEWS_EVIDENCE_VERSION == 2
        cache = Cache(tmp_path)
        bundle = _bundle()
        cached_text = "WARN: Analyst | Downgrade to Hold | MarketBeat"
        cache.save_news(_cache_key(nc._build_query(bundle)), {
            "query": nc._build_query(bundle),
            "stage": "reversal_news",
            "llm_text": cached_text,
            "evidence": {"results": [{"url": "https://a.com", "title": "A", "page_age": None}],
                         "citations": [], "web_search_requests": 1,
                         "search_errors": [], "stop_reason": "end_turn"},
            "evidence_version": 1,
            "cached_at": date.today().isoformat(),
        })
        monkeypatch.setattr(nc, "_web_search", lambda p: pytest.fail("must not re-search"))

        result = fetch_news_context(bundle, cache)
        expected = _parse_response(cached_text, bundle.metadata.symbol_ars, date.today())
        assert result.status == expected.status == NewsCheckStatus.VERIFIED_WARNING
        assert result.warnings == expected.warnings
        assert result.evidence is None
        assert result.from_cache is True


# ── _parse_response recorded extras ──────────────────────────────────────────

SCAN_DATE = date(2026, 9, 9)


class TestParseExtras:
    def test_categories_after_truncation_and_numeric_normalized(self):
        llm = (
            "WARN: Analyst | a | MarketBeat, September 5, 2026\n"
            "WARN: 5 | ex-div | Reuters, September 20, 2026\n"
            "WARN: Guidance | c | Reuters, September 6, 2026"
        )
        r = _parse_response(llm, "X.BA", SCAN_DATE)
        assert r.categories == ["analyst", "calendar"]
        assert len(r.warnings) == 2

    def test_discard_counts(self):
        llm = (
            "WARN: Analyst | old | MarketBeat, August 5, 2026\n"
            "WARN: Analyst | future | MarketBeat, September 26, 2026\n"
            "WARN: Guidance | ok | Reuters, September 5, 2026"
        )
        r = _parse_response(llm, "X.BA", SCAN_DATE)
        assert r.status == NewsCheckStatus.VERIFIED_WARNING
        assert (r.discarded_future, r.discarded_stale) == (1, 1)
        assert r.categories == ["guidance"]

    def test_counts_on_unverified_and_clear_paths(self):
        r = _parse_response("WARN: Analyst | f | MarketBeat, September 26, 2026", "X.BA", SCAN_DATE)
        assert (r.status, r.discarded_future, r.categories) == (NewsCheckStatus.UNVERIFIED, 1, [])
        r = _parse_response("WARN: Analyst | s | MarketBeat, August 5, 2026", "X.BA", SCAN_DATE)
        assert (r.status, r.discarded_stale, r.categories) == (NewsCheckStatus.VERIFIED_CLEAR, 1, [])


# ── to_record / record_signals ───────────────────────────────────────────────

def _full_result():
    return NewsCheckResult(
        status=NewsCheckStatus.VERIFIED_WARNING,
        warnings=["⚠ NEWS [VERIFIED]: Analyst | x | y"],
        categories=["analyst"],
        discarded_future=0, discarded_stale=1,
        evidence=NewsEvidence(
            results=[{"url": "https://a.com", "title": "A", "page_age": None}],
            citations=[{"url": "https://a.com", "title": "A", "cited_text": "cut"}],
            web_search_requests=2, search_errors=[], stop_reason="pause_turn",
        ),
        from_cache=False, model=nc._ANTHROPIC_MODEL, prompt_version=NEWS_PROMPT_VERSION,
    )


def _opp(news_check=None):
    return ReversalOpportunity(
        symbol="AAPL.BA", name="Apple", asset_type="cedear", score=70.0, rsi_14=30.0,
        entry_price_ars=100.0, nearest_support=98.0, nearest_support_type="MA50",
        distance_to_support_pct=0.02, catalyst=["RSI bullish divergence"],
        volume_ratio=0.5, weekly_trend="neutral", invalidation_level_ars=96.53,
        invalidation_rationale="r", tradeable=False, suppression_reason="test",
        news_check=news_check,
    )


class TestRecord:
    def test_to_record_has_all_keys(self):
        rec = _full_result().to_record()
        assert len(NEWS_RECORD_KEYS) == 12
        assert tuple(rec.keys()) == NEWS_RECORD_KEYS
        assert rec["news_stop_reason"] == "pause_turn"
        assert rec["news_status"] == "verified_warning"
        assert rec["news_web_search_requests"] == 2
        assert rec["news_results"][0]["page_age"] is None
        json.dumps(rec, allow_nan=False)

    def test_to_record_without_evidence(self):
        r = NewsCheckResult(status=NewsCheckStatus.UNVERIFIED, warnings=["w"])
        rec = r.to_record()
        assert rec["news_status"] == "unverified"
        for k in ("news_web_search_requests", "news_search_errors", "news_results",
                  "news_citations", "news_stop_reason"):
            assert rec[k] is None

    @pytest.fixture
    def signals_path(self, tmp_path, monkeypatch):
        path = tmp_path / "signals.jsonl"
        monkeypatch.setattr(sr, "SIGNALS_PATH", path)
        return path

    def _records(self, path):
        return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]

    def test_record_signals_news_none_all_null(self, signals_path):
        sr.record_signals([_opp(None)], "2026-11-25", data_date="2026-11-24")
        rec = self._records(signals_path)[0]
        assert "news_stop_reason" in NEWS_RECORD_KEYS
        for k in NEWS_RECORD_KEYS:
            assert k in rec and rec[k] is None
        json.dumps(rec, allow_nan=False)

    def test_record_signals_news_populated(self, signals_path):
        sr.record_signals([_opp(_full_result())], "2026-11-25", data_date="2026-11-24")
        rec = self._records(signals_path)[0]
        assert rec["news_status"] == "verified_warning"
        assert rec["news_citations"][0]["cited_text"] == "cut"
        assert rec["news_prompt_version"] == NEWS_PROMPT_VERSION
        assert rec["news_stop_reason"] == "pause_turn"
        assert all(k in rec for k in NEWS_RECORD_KEYS)
        json.dumps(rec, allow_nan=False)

    def test_record_signals_to_record_failure_records_nulls(self, signals_path, caplog):
        class Broken:
            def to_record(self):
                raise RuntimeError("boom")

        with caplog.at_level("WARNING"):
            sr.record_signals([_opp(Broken())], "2026-11-25", data_date="2026-11-24")
        rec = self._records(signals_path)[0]
        assert all(rec[k] is None for k in NEWS_RECORD_KEYS)
        assert "to_record failed" in caplog.text
