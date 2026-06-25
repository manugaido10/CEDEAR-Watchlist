"""Filter 2 — Técnica 3: News gate (hybrid two-stage).

PROVISIONAL IMPLEMENTATION — to be replaced with Claude API + web search tool.
  Current: keyword-matching over DuckDuckGo Lite HTML (requests + BeautifulSoup).
  Target:  anthropic SDK + claude-haiku-4-5-20251001 with built-in WebSearch tool.
  Replace: _web_search(), _parse_light_verdict(), _parse_tiebreaker_verdict().
  Keep:    two-stage structure, caching, fail-open behavior, activation logic.
  Blocked on: ANTHROPIC_API_KEY in .env + anthropic>=0.40.0 installed.

Stage 1 — Light check (unconditional, all 297 survivors):
  Searches for hard signals only: profit warning, guidance cut, analyst downgrade,
  regulatory investigation, fraud, bankruptcy. Returns clean or hard_news_detected.
  Fail-open: any error → clean with warning.

Stage 2 — Full tiebreaker (conditional):
  Activated when (A) light check escalated, (B) technical/fundamental diverge per
  §4.2 table, or (C) Argentine stock in unknown with any uptrend.
  Returns confirm / inconclusive / discard.
  Fail-open: any error → inconclusive with warning.

Caching:
  Each (symbol, stage) query result is cached by MD5 hash of the query string
  in cache/news/. TTL: NEWS_CACHE_TTL_DAYS (4 days).
"""

from __future__ import annotations

import hashlib
import logging
import time
from datetime import date
from typing import List, Optional, Tuple

from bs4 import BeautifulSoup
import requests

from data.cache import Cache
from data.models import AssetType, TickerBundle

from .filter2_models import (
    FundamentalResult,
    FundamentalState,
    LightCheckResult,
    SentimentResult,
    SentimentVerdict,
    TechnicalResult,
    TrendLabel,
)
from .filter2_thresholds import (
    NEWS_CACHE_TTL_DAYS,
    NEWS_SEARCH_DELAY_SEC,
    NEWS_SEARCH_MAX_RESULTS,
    NEWS_SEARCH_TIMEOUT_SEC,
)

logger = logging.getLogger(__name__)

# ── Hard-news keyword sets ─────────────────────────────────────────────────────

# Stage 1: only these hard signals trigger escalation
_HARD_NEWS_KEYWORDS = {
    "profit warning", "warns on profit", "profit alert",
    "guidance cut", "cuts guidance", "lowered guidance", "reduced guidance",
    "downgraded", "rating cut", "target cut", "sell rating",
    "sec investigation", "sec charges", "regulatory probe", "under investigation",
    "fraud", "accounting fraud", "accounting irregularity", "misstatement",
    "bankruptcy", "chapter 11", "chapter 7", "files for bankruptcy",
    "concurso", "quiebra", "investigación", "fraude", "rebaja",
}

# Stage 2: discard signals (hard confirmed bad news)
_DISCARD_KEYWORDS = {
    "confirmed profit warning", "profit warning confirmed", "guidance slashed",
    "sec charges filed", "formal investigation", "indicted", "criminal charges",
    "files for bankruptcy", "chapter 11 filing", "bankruptcy protection",
    "accounting fraud confirmed", "restated earnings", "material weakness",
    "concurso preventivo", "pedido de quiebra",
    # Also the hard-news set as strong signals
    "profit warning", "guidance cut", "cuts guidance",
    "downgraded", "fraud",
}

# Stage 2: confirm signals (positive / clean)
_CONFIRM_KEYWORDS = {
    "beats earnings", "earnings beat", "raised guidance", "guidance raised",
    "upgrade", "upgraded", "strong results", "record revenue",
    "buyback", "share repurchase", "dividend increase",
    "ganancias récord", "sube utilidades", "resultados positivos",
}

# ── DuckDuckGo search ─────────────────────────────────────────────────────────

def _web_search(query: str) -> List[dict]:
    """Fetch search results from DuckDuckGo Lite HTML endpoint.

    Returns list of {title, url, snippet}. Returns [] on any error (fail-open).
    DuckDuckGo Lite is used because requests + BeautifulSoup are already
    in the project dependencies. This is an unofficial interface — if it breaks,
    replace with another provider; the rest of the module is unaffected.
    """
    try:
        resp = requests.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query},
            headers={"User-Agent": "Mozilla/5.0 (compatible; watchlist-bot/1.0)"},
            timeout=NEWS_SEARCH_TIMEOUT_SEC,
        )
        resp.raise_for_status()
    except Exception as exc:
        logger.warning("Web search request failed for query '%s': %s", query[:60], exc)
        return []

    try:
        soup = BeautifulSoup(resp.text, "html.parser")
        results: List[dict] = []
        for r in soup.select(".result"):
            title_el = r.select_one(".result__title")
            url_el = r.select_one(".result__url")
            snippet_el = r.select_one(".result__snippet")
            if not title_el:
                continue
            results.append({
                "title": title_el.get_text(strip=True),
                "url": url_el.get_text(strip=True) if url_el else "",
                "snippet": snippet_el.get_text(strip=True) if snippet_el else "",
            })
            if len(results) >= NEWS_SEARCH_MAX_RESULTS:
                break
    except Exception as exc:
        logger.warning("Failed to parse search results: %s", exc)
        return []

    return results


def _cache_key(query: str, stage: str) -> str:
    return hashlib.md5(f"{stage}:{query}".encode()).hexdigest()


def _search_cached(
    query: str,
    stage: str,
    cache: Cache,
) -> Tuple[List[dict], bool]:
    """Returns (results, from_cache). Caches results for NEWS_CACHE_TTL_DAYS."""
    key = _cache_key(query, stage)
    if cache.news_is_fresh(key, NEWS_CACHE_TTL_DAYS):
        cached = cache.load_news(key)
        if cached and "results" in cached:
            return cached["results"], True

    results = _web_search(query)
    cache.save_news(key, {
        "query": query,
        "stage": stage,
        "results": results,
        "cached_at": date.today().isoformat(),
    })
    time.sleep(NEWS_SEARCH_DELAY_SEC)
    return results, False


# ── Query builders ─────────────────────────────────────────────────────────────

def _light_query(bundle: TickerBundle) -> str:
    meta = bundle.metadata
    if meta.asset_type == AssetType.CEDEAR:
        ticker = meta.symbol_underlying or meta.symbol_ars
        name = meta.name
        signals = "profit warning OR guidance cut OR downgraded OR investigation OR fraud OR bankruptcy OR Chapter 11"
        return f'"{ticker}" OR "{name}" ({signals}) past 30 days'
    else:
        ticker = meta.symbol_ars.replace(".BA", "")
        name = meta.name
        signals = "profit warning OR guidance OR rebaja OR investigacion OR fraude OR quiebra OR concurso"
        return f'"{ticker}" OR "{name}" ({signals}) ultimos 30 dias'


def _tiebreaker_query(bundle: TickerBundle) -> str:
    meta = bundle.metadata
    if meta.asset_type == AssetType.CEDEAR:
        ticker = meta.symbol_underlying or meta.symbol_ars
        name = meta.name
        signals = "earnings warning OR guidance OR downgrade OR investigation OR fraud OR layoffs OR MA OR lawsuit OR restructuring"
        return f'"{ticker}" OR "{name}" ({signals}) past 30 days'
    else:
        ticker = meta.symbol_ars.replace(".BA", "")
        name = meta.name
        signals = "regulacion OR tarifa OR balance OR ganancias OR guidance OR sancion OR juicio OR macroeconomico OR politica OR brecha OR retenciones"
        return f'"{ticker}" OR "{name}" ({signals}) ultimos 30 dias'


# ── Verdict parsers ────────────────────────────────────────────────────────────

def _text_hits(results: List[dict], keywords: set) -> List[str]:
    """Return keyword matches found across titles + snippets."""
    hits = []
    for r in results:
        combined = (r.get("title", "") + " " + r.get("snippet", "")).lower()
        for kw in keywords:
            if kw in combined:
                hits.append(kw)
    return list(set(hits))


def _parse_light_verdict(results: List[dict]) -> Tuple[LightCheckResult, List[str]]:
    """Return (LightCheckResult, matching_snippets)."""
    hits = _text_hits(results, _HARD_NEWS_KEYWORDS)
    if hits:
        snippets = [
            r["title"] + ": " + r.get("snippet", "")[:120]
            for r in results
            if any(kw in (r.get("title", "") + r.get("snippet", "")).lower() for kw in _HARD_NEWS_KEYWORDS)
        ]
        return LightCheckResult.HARD_NEWS_DETECTED, snippets[:3]
    return LightCheckResult.CLEAN, []


def _parse_tiebreaker_verdict(
    results: List[dict],
    light_snippets: List[str],
) -> Tuple[SentimentVerdict, List[str]]:
    """Keyword-based verdict for the full tiebreaker.

    Scoring:
      Each discard keyword hit adds -1 weight.
      Each confirm keyword hit adds +1 weight.
      Weight < -1 → DISCARD; weight > 0 → CONFIRM; else INCONCLUSIVE.
    """
    discard_hits = _text_hits(results, _DISCARD_KEYWORDS)
    confirm_hits = _text_hits(results, _CONFIRM_KEYWORDS)
    evidence_urls = [r.get("url", "") for r in results if r.get("url")]

    weight = len(confirm_hits) - len(discard_hits)

    if len(results) == 0:
        return SentimentVerdict.INCONCLUSIVE, evidence_urls

    if discard_hits and weight < -1:
        return SentimentVerdict.DISCARD, evidence_urls
    if confirm_hits and weight > 0 and not discard_hits:
        return SentimentVerdict.CONFIRM, evidence_urls
    return SentimentVerdict.INCONCLUSIVE, evidence_urls


# ── Tiebreaker activation logic ────────────────────────────────────────────────

def _should_activate_tiebreaker(
    light_check: LightCheckResult,
    asset_type: AssetType,
    trend_label: TrendLabel,
    fundamental_state: FundamentalState,
) -> Tuple[bool, str]:
    """Returns (activate, reason_string) per §4.2."""
    # (A) Hard news detected in light check
    if light_check == LightCheckResult.HARD_NEWS_DETECTED:
        return True, "light_check_escalation"

    # (C) Argentine stock in unknown with any uptrend
    if asset_type == AssetType.ARGENTINE_STOCK:
        if fundamental_state == FundamentalState.UNKNOWN and trend_label in (
            TrendLabel.STRONG_UP, TrendLabel.MILD_UP
        ):
            return True, "argentina_unknown_uptrend"

    # (B) Divergence table (CEDEARs with fundamentals available)
    if asset_type == AssetType.CEDEAR:
        # strong_up + unknown → activate (DECISIONS.md 2026-06-24 b, Decision #2)
        if trend_label == TrendLabel.STRONG_UP and fundamental_state == FundamentalState.UNKNOWN:
            return True, "cedear_unknown_strong_up"

        # strong_up + neutral or deteriorating → divergence
        if trend_label == TrendLabel.STRONG_UP and fundamental_state in (
            FundamentalState.NEUTRAL, FundamentalState.DETERIORATING
        ):
            return True, "divergence_strong_up_not_confirmed"

        # mild_up + neutral or deteriorating → divergence
        if trend_label == TrendLabel.MILD_UP and fundamental_state in (
            FundamentalState.NEUTRAL, FundamentalState.DETERIORATING
        ):
            return True, "divergence_mild_up_not_confirmed"

    return False, ""


# ── Stage runners ──────────────────────────────────────────────────────────────

def _run_light_check(bundle: TickerBundle, cache: Cache) -> Tuple[LightCheckResult, List[str], List[str]]:
    """Run Stage 1. Returns (result, light_snippets, warnings)."""
    warnings: List[str] = []
    try:
        query = _light_query(bundle)
        results, from_cache = _search_cached(query, "light", cache)
        verdict, snippets = _parse_light_verdict(results)
        if not results:
            warnings.append(f"light check: no search results for {bundle.metadata.symbol_ars}; defaulting clean")
        logger.debug(
            "%s: light check %s (from_cache=%s)",
            bundle.metadata.symbol_ars,
            verdict.value,
            from_cache,
        )
        return verdict, snippets, warnings
    except Exception as exc:
        logger.warning(
            "%s: light check exception — defaulting clean: %s",
            bundle.metadata.symbol_ars,
            exc,
        )
        return (
            LightCheckResult.CLEAN,
            [],
            [f"light check error (fail-open): {exc}"],
        )


def _run_full_tiebreaker(
    bundle: TickerBundle,
    light_snippets: List[str],
    tiebreaker_reason: str,
    cache: Cache,
) -> Tuple[SentimentVerdict, List[str], List[str]]:
    """Run Stage 2. Returns (verdict, evidence_urls, warnings)."""
    warnings: List[str] = []
    try:
        query = _tiebreaker_query(bundle)
        results, from_cache = _search_cached(query, "tiebreaker", cache)
        verdict, evidence_urls = _parse_tiebreaker_verdict(results, light_snippets)
        if not results:
            warnings.append(f"tiebreaker: no results for {bundle.metadata.symbol_ars}; inconclusive")
        logger.debug(
            "%s: tiebreaker %s (reason=%s, from_cache=%s)",
            bundle.metadata.symbol_ars,
            verdict.value,
            tiebreaker_reason,
            from_cache,
        )
        return verdict, evidence_urls, warnings
    except Exception as exc:
        logger.warning(
            "%s: tiebreaker exception — defaulting inconclusive: %s",
            bundle.metadata.symbol_ars,
            exc,
        )
        return (
            SentimentVerdict.INCONCLUSIVE,
            [],
            [f"tiebreaker error (fail-open): {exc}"],
        )


# ── Main entry point ───────────────────────────────────────────────────────────

def run_news_gate(
    bundle: TickerBundle,
    tech_result: TechnicalResult,
    fund_result: FundamentalResult,
    cache: Cache,
) -> SentimentResult:
    """Run the two-stage news gate for a survivor.

    Stage 1 runs unconditionally. Stage 2 activates per §4.2 rules.
    Both stages are fail-open: errors produce clean/inconclusive, not discard.
    """
    symbol = bundle.metadata.symbol_ars
    warnings: List[str] = []

    # Stage 1 — light check (always)
    light_check, light_snippets, w1 = _run_light_check(bundle, cache)
    warnings.extend(w1)

    # Determine if tiebreaker activates
    activate, tb_reason = _should_activate_tiebreaker(
        light_check,
        bundle.metadata.asset_type,
        tech_result.trend_regime_label,
        fund_result.fundamental_state,
    )

    if not activate:
        summary = f"Light check {light_check.value}; tiebreaker not activated."
        return SentimentResult(
            light_check=light_check,
            sentiment_gate=SentimentVerdict.NONE,
            tiebreaker_activated=False,
            tiebreaker_reason="",
            evidence_urls=[],
            light_snippets=light_snippets,
            summary=summary,
            warnings=warnings,
        )

    # Stage 2 — full tiebreaker
    verdict, evidence_urls, w2 = _run_full_tiebreaker(bundle, light_snippets, tb_reason, cache)
    warnings.extend(w2)

    summary_parts = [
        f"Light check: {light_check.value}.",
        f"Tiebreaker activated ({tb_reason}): {verdict.value}.",
    ]
    if warnings:
        summary_parts.append(f"Warnings: {len(warnings)}.")
    summary = " ".join(summary_parts)

    return SentimentResult(
        light_check=light_check,
        sentiment_gate=verdict,
        tiebreaker_activated=True,
        tiebreaker_reason=tb_reason,
        evidence_urls=evidence_urls,
        light_snippets=light_snippets,
        summary=summary,
        warnings=warnings,
    )
