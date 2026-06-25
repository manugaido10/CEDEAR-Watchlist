"""Filter 2 — Técnica 3: News gate (hybrid two-stage).

Implementation: Claude API (claude-haiku-4-5-20251001) + built-in web_search_20250305 tool.
  The LLM searches the web and returns a structured verdict; no keyword matching.

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
from typing import List, Tuple

import anthropic

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
)

logger = logging.getLogger(__name__)

# ── Claude API search ─────────────────────────────────────────────────────────

_ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"


def _web_search(prompt: str) -> Tuple[List[dict], str]:
    """Call Claude API with built-in web_search tool.

    Sends `prompt` to the model, which searches the web and returns a verdict.
    Returns (search_results, llm_verdict_text). Returns ([], '') on any error (fail-open).
    """
    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model=_ANTHROPIC_MODEL,
            max_tokens=1024,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as exc:
        logger.warning("Claude API call failed for prompt '%.60s': %s", prompt, exc)
        return [], ""

    results: List[dict] = []
    llm_text = ""

    for block in response.content:
        btype = getattr(block, "type", None)
        if btype == "web_search_tool_result":
            for item in getattr(block, "content", []):
                results.append({
                    "title": getattr(item, "title", ""),
                    "url": getattr(item, "url", ""),
                    "snippet": (getattr(item, "content", "") or "")[:300],
                })
                if len(results) >= NEWS_SEARCH_MAX_RESULTS:
                    break
        elif btype == "text":
            llm_text = block.text

    return results, llm_text


def _cache_key(query: str, stage: str) -> str:
    return hashlib.md5(f"{stage}:{query}".encode()).hexdigest()


def _search_cached(
    query: str,
    prompt: str,
    stage: str,
    cache: Cache,
) -> Tuple[List[dict], str, bool]:
    """Returns (results, llm_text, from_cache). Caches for NEWS_CACHE_TTL_DAYS."""
    key = _cache_key(query, stage)
    if cache.news_is_fresh(key, NEWS_CACHE_TTL_DAYS):
        cached = cache.load_news(key)
        if cached and "results" in cached:
            return cached["results"], cached.get("llm_text", ""), True

    results, llm_text = _web_search(prompt)
    cache.save_news(key, {
        "query": query,
        "stage": stage,
        "results": results,
        "llm_text": llm_text,
        "cached_at": date.today().isoformat(),
    })
    time.sleep(NEWS_SEARCH_DELAY_SEC)
    return results, llm_text, False


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


# ── Prompt builders ────────────────────────────────────────────────────────────

def _light_prompt(bundle: TickerBundle) -> str:
    query = _light_query(bundle)
    return (
        f"Search for recent news (last 30 days) about: {query}\n\n"
        "Look ONLY for hard signals: profit warning, guidance cut, material analyst downgrade, "
        "regulatory investigation, accounting fraud, or bankruptcy filing.\n\n"
        "Reply with EXACTLY one line — no other text:\n"
        "CLEAN — if no hard signals found\n"
        "HARD_NEWS_DETECTED: [one-sentence reason] — if any hard signal found"
    )


def _tiebreaker_prompt(bundle: TickerBundle, light_snippets: List[str]) -> str:
    query = _tiebreaker_query(bundle)
    context = ""
    if light_snippets:
        context = f"\nLight check flagged: {'; '.join(light_snippets[:2])}"
    return (
        f"Search for recent news (last 30 days) about: {query}{context}\n\n"
        "Evaluate the overall news context: earnings, guidance, analyst coverage, "
        "legal/regulatory issues, and business developments.\n\n"
        "Reply with EXACTLY one line — no other text:\n"
        "CONFIRM: [one-sentence reason] — no material negative news, thesis intact\n"
        "INCONCLUSIVE: [one-sentence reason] — mixed or ambiguous signals\n"
        "DISCARD: [one-sentence reason] — hard negative news confirmed, invalidates thesis"
    )


# ── Verdict parsers ────────────────────────────────────────────────────────────

def _parse_light_verdict(llm_text: str) -> Tuple[LightCheckResult, List[str]]:
    """Parse LLM verdict text into (LightCheckResult, snippets)."""
    first_line = llm_text.strip().split("\n")[0].strip()
    if first_line.upper().startswith("HARD_NEWS_DETECTED"):
        colon = first_line.find(":")
        reason = first_line[colon + 1:].strip() if colon != -1 else first_line
        return LightCheckResult.HARD_NEWS_DETECTED, [reason] if reason else [first_line]
    return LightCheckResult.CLEAN, []


def _parse_tiebreaker_verdict(
    llm_text: str,
    results: List[dict],
) -> Tuple[SentimentVerdict, List[str]]:
    """Parse LLM verdict text into (SentimentVerdict, evidence_urls)."""
    evidence_urls = [r.get("url", "") for r in results if r.get("url")]
    first_line = llm_text.strip().split("\n")[0].strip().upper()
    if first_line.startswith("DISCARD"):
        return SentimentVerdict.DISCARD, evidence_urls
    if first_line.startswith("CONFIRM"):
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
        prompt = _light_prompt(bundle)
        results, llm_text, from_cache = _search_cached(query, prompt, "light", cache)
        verdict, snippets = _parse_light_verdict(llm_text)
        if not results and not llm_text:
            warnings.append(f"light check: no response for {bundle.metadata.symbol_ars}; defaulting clean")
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
        prompt = _tiebreaker_prompt(bundle, light_snippets)
        results, llm_text, from_cache = _search_cached(query, prompt, "tiebreaker", cache)
        verdict, evidence_urls = _parse_tiebreaker_verdict(llm_text, results)
        if not results and not llm_text:
            warnings.append(f"tiebreaker: no response for {bundle.metadata.symbol_ars}; inconclusive")
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
