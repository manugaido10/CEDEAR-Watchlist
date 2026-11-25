"""Reversal-specific news context check — single-stage, post-cap enrichment.

Called on 0-5 published reversal opportunities only — never on the full universe.

Three explicit output states (Decision #14 epistemic principle, Decision #24):
  VERIFIED_CLEAR   — LLM searched and found nothing relevant
  VERIFIED_WARNING — LLM found relevant signal; max 2 items surfaced
  UNVERIFIED       — API error, no usable results, or LLM replied UNVERIFIED

Never caches empty or error responses (Decision #14 Fix 1).
TTL: 1 calendar day — "same day is fresh, next day re-fetches" (Decision #24).
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
import traceback
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum
from typing import List, Optional, Tuple

import anthropic

from data.cache import Cache
from data.models import AssetType, TickerBundle

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

_ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"
NEWS_REVERSAL_CACHE_TTL_DAYS: int = 1   # same-day freshness; re-fetches next calendar day
NEWS_REVERSAL_DELAY_SEC: float = 1.0
NEWS_REVERSAL_MAX_RESULTS: int = 8
NEWS_REVERSAL_MAX_WARNINGS: int = 2     # truncated in code, not in prompt (Decision #24)
CALENDAR_MAX_HORIZON_DAYS: int = 90    # Calendar WARN: accept future dates up to N days ahead
NEWS_REVERSAL_MAX_SEARCHES: int = 5     # web_search max_uses per call (Decision #39)
NEWS_REVERSAL_MAX_CITATIONS: int = 10   # recorded citations cap, after dedup (Decision #39)
NEWS_PROMPT_VERSION: str = "2026-11-v1"  # label for the current _build_prompt text; bump on any change
NEWS_EVIDENCE_VERSION: int = 2          # schema version of the cached/recorded NewsEvidence
NEWS_EVIDENCE_MAX_RESULTS: int = 20     # recorded results cap (cited URLs always kept on top)

# Numeric category index (prompt order) → normalized category name.
_CATEGORY_BY_INDEX: dict = {
    "1": "analyst", "2": "guidance", "3": "regulatory", "4": "fx/macro", "5": "calendar",
}

# Keys written to signals.jsonl by record_signals — always present, null when the
# news check did not run (Decision #39).
NEWS_RECORD_KEYS: Tuple[str, ...] = (
    "news_status",
    "news_categories",
    "news_discarded_future",
    "news_discarded_stale",
    "news_model",
    "news_prompt_version",
    "news_from_cache",
    "news_web_search_requests",
    "news_search_errors",
    "news_results",
    "news_citations",
    "news_stop_reason",
)

# Cache namespace prefix — prevents collision with watchlist news gate entries
_CACHE_STAGE = "reversal_news"

# Category 5 ("Calendar") exemption: upcoming events are future by definition.
# Both named form ("calendar") and indexed form ("5") are accepted — the LLM
# sometimes returns the prompt's numeric index instead of the category name.
_CALENDAR_CATEGORY: frozenset = frozenset({"calendar", "5"})

# ── Country / currency lookup ──────────────────────────────────────────────────
# Keyed by symbol_underlying. Only non-US companies are listed.
# For unknowns (US-based or unlisted): FX category is omitted from the prompt
# entirely — no context is better than wrong context (Decision #25).
_FX_CONTEXT: dict = {
    # Mexico (MXN)
    "AMX": ("Mexico", "MXN"), "ASR": ("Mexico", "MXN"), "CX": ("Mexico", "MXN"),
    "FMX": ("Mexico", "MXN"), "KOFM": ("Mexico", "MXN"), "PAC": ("Mexico", "MXN"),
    "TV": ("Mexico", "MXN"), "VIST": ("Mexico", "MXN"),
    # Brazil (BRL)
    "ABEV": ("Brazil", "BRL"), "ABEV3": ("Brazil", "BRL"),
    "BBAS3": ("Brazil", "BRL"), "BBD": ("Brazil", "BRL"), "BBDC3": ("Brazil", "BRL"),
    "BAK": ("Brazil", "BRL"), "BPAC11": ("Brazil", "BRL"),
    "BRFS": ("Brazil", "BRL"), "BSBR": ("Brazil", "BRL"), "CBRD": ("Brazil", "BRL"),
    "CSNA3": ("Brazil", "BRL"), "EBR": ("Brazil", "BRL"), "ELP": ("Brazil", "BRL"),
    "ERJ": ("Brazil", "BRL"), "GGB": ("Brazil", "BRL"), "HAPV3": ("Brazil", "BRL"),
    "ITUB": ("Brazil", "BRL"), "ITUB3": ("Brazil", "BRL"),
    "LND": ("Brazil", "BRL"), "LREN3": ("Brazil", "BRL"),
    "MGLU3": ("Brazil", "BRL"), "NATU3": ("Brazil", "BRL"),
    "PAGS": ("Brazil", "BRL"), "PBR": ("Brazil", "BRL"), "PETR3": ("Brazil", "BRL"),
    "PRIO3": ("Brazil", "BRL"), "RENT3": ("Brazil", "BRL"),
    "SBSP3": ("Brazil", "BRL"), "SID": ("Brazil", "BRL"), "STNE": ("Brazil", "BRL"),
    "SUZ": ("Brazil", "BRL"), "SUZB3": ("Brazil", "BRL"),
    "TIMB": ("Brazil", "BRL"), "TIMS3": ("Brazil", "BRL"),
    "UGP": ("Brazil", "BRL"), "VALE": ("Brazil", "BRL"), "VALE3": ("Brazil", "BRL"),
    "VIV": ("Brazil", "BRL"), "VIVT3": ("Brazil", "BRL"),
    "WEGE3": ("Brazil", "BRL"), "XP": ("Brazil", "BRL"),
    "UN": ("Brazil", "BRL"),   # NU Holdings — Cayman incorporated, Brazil-focused
    # UK (GBP)
    "ARM": ("UK", "GBP"), "AZN": ("UK", "GBP"), "BCS": ("UK", "GBP"),
    "BP": ("UK", "GBP"), "DEO": ("UK", "GBP"), "GSK": ("UK", "GBP"),
    "HSBC": ("UK", "GBP"), "LYG": ("UK", "GBP"), "NGG": ("UK", "GBP"),
    "PSO": ("UK", "GBP"), "RIO": ("UK", "GBP"), "UL": ("UK", "GBP"),
    "VOD": ("UK", "GBP"),
    # Europe — EUR
    "AEG": ("Netherlands", "EUR"), "ASML": ("Netherlands", "EUR"),
    "ING": ("Netherlands", "EUR"), "PHG": ("Netherlands", "EUR"),
    "NBIS": ("Netherlands", "EUR"),
    "SAP": ("Germany", "EUR"), "JMIA": ("Germany", "EUR"),
    "ORAN": ("France", "EUR"), "TTE": ("France", "EUR"),
    "BBV": ("Spain", "EUR"), "SAN": ("Spain", "EUR"), "TEFO": ("Spain", "EUR"),
    "RACE": ("Italy", "EUR"), "E": ("Italy", "EUR"), "TIIAY": ("Italy", "EUR"),
    # Europe — other
    "NVO": ("Denmark", "DKK"),
    "EQNR": ("Norway", "NOK"),
    "ERIC": ("Sweden", "SEK"),
    "NVS": ("Switzerland", "CHF"),
    "NOK": ("Finland", "EUR"),  # Nokia (underlying for NOKA.BA)
    # China / HK (CNY)
    "AOCA": ("China", "CNY"), "BABA": ("China", "CNY"), "BIDU": ("China", "CNY"),
    "JD": ("China", "CNY"), "JOYY": ("China", "CNY"), "LFC": ("China", "CNY"),
    "NIO": ("China", "CNY"), "NTES": ("China", "CNY"), "PDD": ("China", "CNY"),
    "PTR": ("China", "CNY"), "SNP": ("China", "CNY"), "TCOM": ("China", "CNY"),
    "WBO": ("China", "CNY"), "XPEV": ("China", "CNY"), "HNPIY": ("China", "CNY"),
    # Japan (JPY)
    "CAJ": ("Japan", "JPY"), "HMC": ("Japan", "JPY"), "MFG": ("Japan", "JPY"),
    "MUFG": ("Japan", "JPY"), "NMR": ("Japan", "JPY"),
    "SONY": ("Japan", "JPY"), "TM": ("Japan", "JPY"),
    # South Korea (KRW)
    "KB": ("South Korea", "KRW"), "KEP": ("South Korea", "KRW"),
    "PKX": ("South Korea", "KRW"),
    # India (INR)
    "HDB": ("India", "INR"), "IBN": ("India", "INR"),
    "INFY": ("India", "INR"), "TTM": ("India", "INR"),
    # Taiwan (TWD)
    "TSM": ("Taiwan", "TWD"),
    # South Africa (ZAR)
    "GFI": ("South Africa", "ZAR"), "HMY": ("South Africa", "ZAR"),
    # Australia (AUD)
    "BHP": ("Australia", "AUD"),
    # Canada (CAD)
    "AEM": ("Canada", "CAD"), "AUY": ("Canada", "CAD"), "B": ("Canada", "CAD"),
    "BB": ("Canada", "CAD"), "CCJ": ("Canada", "CAD"), "CLS": ("Canada", "CAD"),
    "KEEL": ("Canada", "CAD"), "KGC": ("Canada", "CAD"), "LAC": ("Canada", "CAD"),
    "MUX": ("Canada", "CAD"), "NXE": ("Canada", "CAD"),
    "PAAS": ("Canada", "CAD"), "SHOP": ("Canada", "CAD"),
}


# ── Output types ──────────────────────────────────────────────────────────────

class NewsCheckStatus(str, Enum):
    VERIFIED_CLEAR = "verified_clear"
    VERIFIED_WARNING = "verified_warning"
    UNVERIFIED = "unverified"


def _opt_str(value: object) -> Optional[str]:
    """None stays None; anything else is coerced to str (strict-JSON safe)."""
    return None if value is None else str(value)


@dataclass
class NewsEvidence:
    """What the web search actually returned — recorded only, never read by the verdict.

    results:   [{url, title, page_age}] across ALL searches, deduplicated by URL —
               page_age is the site's last-update string, NOT the publication date.
               Cited URLs always included; the rest fill up to NEWS_EVIDENCE_MAX_RESULTS.
    citations: [{url, title, cited_text}] from text blocks, deduplicated by
               (url, cited_text). ≤ NEWS_REVERSAL_MAX_CITATIONS.
    web_search_requests: usage.server_tool_use.web_search_requests (None if absent).
    search_errors: error_code of each web_search_tool_result_error block.
    stop_reason: response.stop_reason (None if absent).
    """
    results: List[dict] = field(default_factory=list)
    citations: List[dict] = field(default_factory=list)
    web_search_requests: Optional[int] = None
    search_errors: List[str] = field(default_factory=list)
    stop_reason: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "results": [dict(r) for r in self.results],
            "citations": [dict(c) for c in self.citations],
            "web_search_requests": self.web_search_requests,
            "search_errors": list(self.search_errors),
            "stop_reason": self.stop_reason,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "NewsEvidence":
        wsr = data.get("web_search_requests")
        return cls(
            results=list(data.get("results") or []),
            citations=list(data.get("citations") or []),
            web_search_requests=wsr if isinstance(wsr, int) and not isinstance(wsr, bool) else None,
            search_errors=[str(e) for e in (data.get("search_errors") or [])],
            stop_reason=_opt_str(data.get("stop_reason")),
        )


@dataclass
class NewsCheckResult:
    status: NewsCheckStatus
    warnings: List[str] = field(default_factory=list)
    # VERIFIED_CLEAR  → warnings = []
    # VERIFIED_WARNING → warnings has formatted finding(s), ≤ NEWS_REVERSAL_MAX_WARNINGS
    # UNVERIFIED      → warnings = ["⚠ NEWS [UNVERIFIED]: ..."]
    # ── Recorded only (Decision #39) — never read by the verdict ──
    categories: List[str] = field(default_factory=list)  # surviving WARN categories, post-truncation
    discarded_future: int = 0     # WARN lines dropped by the future-date guard
    discarded_stale: int = 0      # WARN lines dropped by the 30-day window guard
    evidence: Optional[NewsEvidence] = None
    from_cache: Optional[bool] = None
    model: Optional[str] = None
    prompt_version: Optional[str] = None

    def to_record(self) -> dict:
        """Flat dict with exactly NEWS_RECORD_KEYS, strict-JSON serializable."""
        ev = self.evidence
        return {
            "news_status": self.status.value,
            "news_categories": list(self.categories),
            "news_discarded_future": int(self.discarded_future),
            "news_discarded_stale": int(self.discarded_stale),
            "news_model": self.model,
            "news_prompt_version": self.prompt_version,
            "news_from_cache": self.from_cache,
            "news_web_search_requests": ev.web_search_requests if ev else None,
            "news_search_errors": list(ev.search_errors) if ev else None,
            "news_results": [dict(r) for r in ev.results] if ev else None,
            "news_citations": [dict(c) for c in ev.citations] if ev else None,
            "news_stop_reason": ev.stop_reason if ev else None,
        }


def empty_news_record() -> dict:
    """All NEWS_RECORD_KEYS set to None — the news check did not run."""
    return {k: None for k in NEWS_RECORD_KEYS}


# ── Evidence extraction ────────────────────────────────────────────────────────

def _extract_evidence(response: object) -> NewsEvidence:
    """Read results, citations, usage and errors from a Messages API response.

    Every attribute is read with getattr; a missing field yields None / empty.
    """
    citations: List[dict] = []
    seen_citations: set = set()
    search_errors: List[str] = []
    all_results: List[dict] = []   # every search, in order, deduplicated by URL
    seen_urls: set = set()

    for block in getattr(response, "content", None) or []:
        btype = getattr(block, "type", None)
        if btype == "web_search_tool_result":
            content = getattr(block, "content", None)
            if isinstance(content, (list, tuple)):
                for item in content:
                    if getattr(item, "type", "web_search_result") != "web_search_result":
                        continue
                    url = _opt_str(getattr(item, "url", None))
                    if url in seen_urls:
                        continue
                    seen_urls.add(url)
                    all_results.append({
                        "url": url,
                        "title": _opt_str(getattr(item, "title", None)),
                        "page_age": _opt_str(getattr(item, "page_age", None)),
                    })
            elif content is not None:
                # Error shape: a single web_search_tool_result_error object, not a list.
                code = getattr(content, "error_code", None)
                if code is None and isinstance(content, dict):
                    code = content.get("error_code")
                search_errors.append(str(code) if code is not None else "unknown")
        elif btype == "text":
            for cit in getattr(block, "citations", None) or []:
                if getattr(cit, "type", "web_search_result_location") != "web_search_result_location":
                    continue
                url = _opt_str(getattr(cit, "url", None))
                cited_text = _opt_str(getattr(cit, "cited_text", None))
                key = (url, cited_text)
                if key in seen_citations or len(citations) >= NEWS_REVERSAL_MAX_CITATIONS:
                    continue
                seen_citations.add(key)
                citations.append({
                    "url": url,
                    "title": _opt_str(getattr(cit, "title", None)),
                    "cited_text": cited_text,
                })

    # Results: URLs of recorded citations always kept (so citation → page_age can be
    # joined later); the rest fill up to NEWS_EVIDENCE_MAX_RESULTS. Search order kept.
    cited_urls = {c["url"] for c in citations}
    n_cited = sum(1 for r in all_results if r["url"] in cited_urls)
    room = max(NEWS_EVIDENCE_MAX_RESULTS - n_cited, 0)
    results: List[dict] = []
    for r in all_results:
        if r["url"] in cited_urls:
            results.append(r)
        elif room > 0:
            results.append(r)
            room -= 1

    server_tool_use = getattr(getattr(response, "usage", None), "server_tool_use", None)
    wsr = getattr(server_tool_use, "web_search_requests", None)
    web_search_requests = wsr if isinstance(wsr, int) and not isinstance(wsr, bool) else None

    return NewsEvidence(
        results=results,
        citations=citations,
        web_search_requests=web_search_requests,
        search_errors=search_errors,
        stop_reason=_opt_str(getattr(response, "stop_reason", None)),
    )


# ── Claude API search ──────────────────────────────────────────────────────────

def _web_search(prompt: str) -> Tuple[str, Optional[NewsEvidence]]:
    """Call Claude API with built-in web_search tool.

    Returns (llm_text, evidence). Returns ('', None) on any API error.
    Evidence extraction failures yield evidence=None and never touch llm_text.
    Error details are logged at ERROR level — never silenced (Decision #14 Fix 2).
    """
    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model=_ANTHROPIC_MODEL,
            max_tokens=1024,
            tools=[{
                "type": "web_search_20250305",
                "name": "web_search",
                "max_uses": NEWS_REVERSAL_MAX_SEARCHES,
            }],
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.BadRequestError as exc:
        if "credit" in str(exc).lower():
            logger.error(
                "ANTHROPIC API: crédito insuficiente — news check de reversión no evaluado. "
                "Recargá crédito en console.anthropic.com. Prompt: '%.60s'",
                prompt,
            )
        else:
            logger.error(
                "Claude API BadRequestError (reversal news check) for prompt '%.60s': %s",
                prompt,
                exc,
            )
        return "", None
    except Exception as exc:
        logger.error(
            "Claude API call failed (reversal news check) for prompt '%.60s': %s\n%s",
            prompt,
            exc,
            traceback.format_exc(),
        )
        return "", None

    llm_text = ""
    for block in response.content:
        if getattr(block, "type", None) == "text":
            llm_text += block.text

    evidence: Optional[NewsEvidence]
    try:
        evidence = _extract_evidence(response)
    except Exception as exc:
        logger.warning(
            "reversal news check: evidence extraction failed for prompt '%.60s' — %s; "
            "evidence recorded as null, verdict unaffected",
            prompt,
            exc,
        )
        evidence = None

    return llm_text, evidence


# ── Cache helpers ──────────────────────────────────────────────────────────────

def _cache_key(query: str) -> str:
    return hashlib.md5(f"{_CACHE_STAGE}:{query}".encode()).hexdigest()


def _search_cached(
    query: str,
    prompt: str,
    cache: Cache,
) -> Tuple[str, Optional[NewsEvidence], bool]:
    """Returns (llm_text, evidence, from_cache).

    Only persists when llm_text is non-empty (Decision #14 Fix 1).
    Entries written before Decision #39 (no evidence_version) or with an older
    evidence_version are still served from cache with evidence=None — no re-search.
    """
    key = _cache_key(query)
    if cache.news_is_fresh(key, NEWS_REVERSAL_CACHE_TTL_DAYS):
        cached = cache.load_news(key)
        if cached and cached.get("llm_text"):
            return cached["llm_text"], _evidence_from_cache(cached, query), True

    llm_text, evidence = _web_search(prompt)
    if llm_text:
        cache.save_news(key, {
            "query": query,
            "stage": _CACHE_STAGE,
            "llm_text": llm_text,
            "evidence": evidence.to_dict() if evidence is not None else None,
            "evidence_version": NEWS_EVIDENCE_VERSION,
            "cached_at": date.today().isoformat(),
        })
    time.sleep(NEWS_REVERSAL_DELAY_SEC)
    return llm_text, evidence, False


def _evidence_from_cache(cached: dict, query: str) -> Optional[NewsEvidence]:
    if cached.get("evidence_version") != NEWS_EVIDENCE_VERSION:
        return None  # legacy entry (pre-#39, or evidence_version 1) or other schema version
    raw = cached.get("evidence")
    if not isinstance(raw, dict):
        return None
    try:
        return NewsEvidence.from_dict(raw)
    except Exception as exc:
        logger.warning(
            "reversal news check: cached evidence unreadable for query '%.60s' — %s; "
            "evidence recorded as null",
            query,
            exc,
        )
        return None


# ── Query and prompt builders ──────────────────────────────────────────────────

def _build_query(bundle: TickerBundle) -> str:
    meta = bundle.metadata
    if meta.asset_type == AssetType.CEDEAR:
        ticker = meta.symbol_underlying or meta.symbol_ars.replace(".BA", "")
        return f'"{ticker}" OR "{meta.name}" news last 30 days'
    else:
        ticker = meta.symbol_ars.replace(".BA", "")
        return f'"{ticker}" OR "{meta.name}" noticias ultimos 30 dias'


def _build_prompt(bundle: TickerBundle, scan_date: date | None = None) -> str:
    meta = bundle.metadata

    if meta.asset_type == AssetType.CEDEAR:
        ticker = meta.symbol_underlying or meta.symbol_ars.replace(".BA", "")
        name = meta.name
        country_currency = _FX_CONTEXT.get(ticker)
        if country_currency:
            country, currency = country_currency
            fx_note = (
                f"The underlying company is based in {country}. "
                f"Only report {currency}/USD macro trends if relevant. "
                f"Do not reference any other country's currency."
            )
        else:
            # Unknown country → omit FX context entirely (no context > wrong context)
            fx_note = "Category 4 not applicable — primary country unknown; skip FX context."
    else:
        ticker = meta.symbol_ars.replace(".BA", "")
        name = meta.name
        fx_note = (
            "Incluir contexto macro argentino si es relevante "
            "(tipo de cambio, regulaciones sectoriales)."
        )

    today = scan_date or date.today()
    return (
        f'Search for news about "{ticker}" OR "{name}" in the last 30 days.\n\n'
        "You are evaluating a SHORT-TERM MEAN REVERSION trade (avg. 6.5-day hold). "
        "The stock is oversold. Assess whether the decline has a FUNDAMENTAL CAUSE "
        "that would invalidate a bounce, or whether it is pure price weakness.\n\n"
        f"Today's date is {today.isoformat()}. "
        "IMPORTANT: Only report findings with a confirmed event date within the last "
        "30 days and NOT after today. A date in the future means the event has not "
        "happened yet — do NOT report it. If you cannot find a real past event, reply CLEAR.\n\n"
        "Report ONLY if you find concrete evidence in these categories (priority order):\n"
        "1. Analyst recommendation change or price target cut (last 30 days)\n"
        "2. Guidance revision, profit warning, or management change (last 30 days)\n"
        "3. Litigation, regulatory investigation, or material corporate event (last 30 days)\n"
        f"4. FX/macro context: {fx_note}\n"
        "5. Upcoming calendar event: ex-dividend date, lock-up expiry, regulatory decision\n\n"
        "Reply with EXACTLY this format:\n"
        "  CLEAR — if you searched and found nothing relevant within the last 30 days\n"
        "  WARN: [Analyst|Guidance|Regulatory|FX/Macro|Calendar] | [one sentence finding] | [source name, date if known]\n"
        "  UNVERIFIED — if you could NOT search, or the search returned no usable results\n\n"
        "Use the category name from the brackets above (e.g. Analyst, Guidance). "
        "One line per finding. Do not add any other text."
    )


# ── Response parser ────────────────────────────────────────────────────────────

_MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7,
    "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

# Matches "September 26, 2026", "Sep 26 2026", "26 September 2026"
_DATE_PATTERN = re.compile(
    r'\b(?:'
    r'(january|february|march|april|may|june|july|august|september|october|november|december'
    r'|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)\w*'
    r'\s+(\d{1,2}),?\s+(20\d{2})'   # Month DD YYYY
    r'|(\d{1,2})\s+'
    r'(january|february|march|april|may|june|july|august|september|october|november|december'
    r'|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)\w*'
    r'\s+(20\d{2})'                  # DD Month YYYY
    r'|(20\d{2})-(0[1-9]|1[0-2])-([0-2]\d|3[01])'  # YYYY-MM-DD
    r')\b',
    re.IGNORECASE,
)


def _extract_dates(text: str) -> List[date]:
    """Extract all parseable dates from *text*. Unparseable matches are silently skipped."""
    results: List[date] = []
    for m in _DATE_PATTERN.finditer(text):
        try:
            if m.group(1):  # Month DD YYYY
                mon = _MONTH_MAP.get(m.group(1).lower()[:3])
                if mon:
                    results.append(date(int(m.group(3)), mon, int(m.group(2))))
            elif m.group(4):  # DD Month YYYY
                mon = _MONTH_MAP.get(m.group(5).lower()[:3])
                if mon:
                    results.append(date(int(m.group(6)), mon, int(m.group(4))))
            elif m.group(7):  # YYYY-MM-DD
                results.append(date(int(m.group(7)), int(m.group(8)), int(m.group(9))))
        except ValueError:
            pass
    return results


def _has_future_date(text: str, scan_date: date) -> bool:
    """Return True if *text* contains any date strictly after scan_date."""
    return any(d > scan_date for d in _extract_dates(text))


def _has_only_stale_dates(text: str, scan_date: date) -> bool:
    """Return True if *text* contains at least one date and ALL dates are outside the 30-day window.

    A finding is stale when every date in it predates scan_date − 30 days.
    A finding without any recognizable date is NOT stale — it passes through.
    """
    dates = _extract_dates(text)
    if not dates:
        return False
    cutoff = scan_date - timedelta(days=30)
    return all(d < cutoff for d in dates)


def _extract_warn_category(warn_line: str) -> str:
    """Extract normalized category token from a WARN: line.

    Accepts both named ("Calendar") and indexed ("5") forms; returns lowercase.
    Returns "" if the line cannot be parsed.
    """
    body = warn_line[5:].strip() if warn_line.upper().startswith("WARN:") else warn_line
    parts = body.split("|")
    return parts[0].strip().lower() if parts else ""


def _normalized_category(warn_line: str) -> str:
    """Category for recording: lowercase name; numeric prompt index mapped to its name."""
    cat = _extract_warn_category(warn_line)
    return _CATEGORY_BY_INDEX.get(cat, cat)


def _is_calendar_warn(warn_line: str) -> bool:
    """Return True when the WARN line belongs to the Calendar category (name or index)."""
    return _extract_warn_category(warn_line) in _CALENDAR_CATEGORY


def _has_future_date_beyond_horizon(text: str, scan_date: date, horizon_days: int) -> bool:
    """Return True if *text* contains a date strictly more than horizon_days after scan_date."""
    return any(d > scan_date + timedelta(days=horizon_days) for d in _extract_dates(text))


def _parse_response(llm_text: str, symbol: str, scan_date: date | None = None) -> NewsCheckResult:
    """Parse LLM response into NewsCheckResult.

    WARN: lines take priority over CLEAR / UNVERIFIED.
    Scans ALL lines, not just the first — the LLM often adds preamble text
    before the actual verdict, or embeds WARN: in the same line as the preamble.
    """
    lines = llm_text.strip().split("\n")

    # Collect WARN: findings across all lines.
    # Handles two LLM output patterns:
    #   (a) line starts with WARN: (expected format)
    #   (b) WARN: is embedded after preamble on the same line without a newline
    #       e.g. "I'll search for news.WARN: Analyst | ..."
    _scan_date = scan_date or date.today()

    warn_lines: List[str] = []
    for line in lines:
        stripped = line.strip()
        upper = stripped.upper()
        if upper.startswith("WARN:"):
            warn_lines.append(stripped)
        elif "WARN:" in upper:
            idx = upper.index("WARN:")
            warn_lines.append(stripped[idx:])

    if warn_lines:
        # Two-sided date guard:
        #   Upper bound: future date → hallucination → UNVERIFIED
        #     Exception: Calendar category (ex-div, lock-up, regulatory dates are inherently
        #     future). Accept up to CALENDAR_MAX_HORIZON_DAYS; reject beyond that.
        #   Lower bound: all dates older than 30 days → model found real but stale news
        #                → treat as CLEAR (no relevant recent news within window)
        valid_warn: List[str] = []
        future_count = 0
        stale_count = 0
        for wl in warn_lines:
            is_calendar = _is_calendar_warn(wl)
            if is_calendar:
                is_future_hallu = _has_future_date_beyond_horizon(wl, _scan_date, CALENDAR_MAX_HORIZON_DAYS)
            else:
                is_future_hallu = _has_future_date(wl, _scan_date)

            if is_future_hallu:
                future_count += 1
                logger.warning(
                    "%s: news check — descartando WARN con fecha futura%s (posible alucinación): '%.120s'",
                    symbol,
                    f" > {CALENDAR_MAX_HORIZON_DAYS}d" if is_calendar else "",
                    wl,
                )
            elif _has_only_stale_dates(wl, _scan_date):
                stale_count += 1
                logger.warning(
                    "%s: news check — descartando WARN fuera de ventana 30 días: '%.120s'",
                    symbol,
                    wl,
                )
            else:
                valid_warn.append(wl)

        if future_count > 0 and not valid_warn:
            return NewsCheckResult(
                status=NewsCheckStatus.UNVERIFIED,
                warnings=["⚠ NEWS [UNVERIFIED]: hallazgo descartado — fecha futura detectada (posible alucinación del modelo)"],
                discarded_future=future_count,
                discarded_stale=stale_count,
            )

        # All findings were stale (real dates, but outside the 30-day window).
        # The model did search and found something; it's just not recent. → CLEAR.
        if stale_count > 0 and not valid_warn and future_count == 0:
            logger.debug("%s: news check VERIFIED_CLEAR — %d hallazgo(s) fuera de ventana descartados", symbol, stale_count)
            return NewsCheckResult(
                status=NewsCheckStatus.VERIFIED_CLEAR,
                discarded_future=future_count,
                discarded_stale=stale_count,
            )

        if valid_warn:
            # Truncate to max 2 items — enforced here, not in the prompt (Decision #24)
            valid_warn = valid_warn[:NEWS_REVERSAL_MAX_WARNINGS]
            formatted = [
                f"⚠ NEWS [VERIFIED]: {line[5:].strip()}"  # strip "WARN:" prefix
                for line in valid_warn
            ]
            logger.debug("%s: news check VERIFIED_WARNING — %d finding(s)", symbol, len(formatted))
            return NewsCheckResult(
                status=NewsCheckStatus.VERIFIED_WARNING,
                warnings=formatted,
                categories=[_normalized_category(line) for line in valid_warn],
                discarded_future=future_count,
                discarded_stale=stale_count,
            )

    # Scan all lines for CLEAR or UNVERIFIED — the verdict may appear after preamble text
    for line in lines:
        stripped = line.strip().upper()
        if stripped == "CLEAR":
            logger.debug("%s: news check VERIFIED_CLEAR", symbol)
            return NewsCheckResult(status=NewsCheckStatus.VERIFIED_CLEAR)
        if stripped == "UNVERIFIED":
            logger.warning("%s: news check — model replied UNVERIFIED (búsqueda no disponible)", symbol)
            return NewsCheckResult(
                status=NewsCheckStatus.UNVERIFIED,
                warnings=["⚠ NEWS [UNVERIFIED]: no se pudo verificar contexto de noticias (búsqueda no disponible)"],
            )

    # No recognizable verdict found in any line
    logger.warning(
        "%s: news check — formato de respuesta inesperado (primeras 80 chars: '%.80s')",
        symbol,
        llm_text.strip(),
    )
    return NewsCheckResult(
        status=NewsCheckStatus.UNVERIFIED,
        warnings=["⚠ NEWS [UNVERIFIED]: no se pudo verificar contexto de noticias (respuesta inesperada del modelo)"],
    )


# ── Public entry point ─────────────────────────────────────────────────────────

def fetch_news_context(bundle: TickerBundle, cache: Cache) -> NewsCheckResult:
    """Run single-stage news context check for one reversal opportunity.

    Always runs (no conditional tiebreaker). Result is informational — never
    a veto. Failure path returns UNVERIFIED with an explicit warning string.

    Args:
        bundle: The TickerBundle for the opportunity being evaluated.
        cache:  Shared cache instance. Results cached for NEWS_REVERSAL_CACHE_TTL_DAYS.

    Returns:
        NewsCheckResult with status and warnings list (empty if VERIFIED_CLEAR).
    """
    symbol = bundle.metadata.symbol_ars
    try:
        scan_date = date.today()
        query = _build_query(bundle)
        prompt = _build_prompt(bundle, scan_date)
        llm_text, evidence, from_cache = _search_cached(query, prompt, cache)

        if not llm_text:
            logger.warning(
                "%s: news check — sin respuesta del modelo (API vacía o error de crédito)",
                symbol,
            )
            result = NewsCheckResult(
                status=NewsCheckStatus.UNVERIFIED,
                warnings=["⚠ NEWS [UNVERIFIED]: no se pudo verificar contexto de noticias (sin respuesta del modelo)"],
            )
        else:
            logger.debug("%s: news check response (from_cache=%s): '%.120s'", symbol, from_cache, llm_text.strip())
            result = _parse_response(llm_text, symbol, scan_date)

        # Recorded-only metadata (Decision #39) — set after the verdict is final.
        result.evidence = evidence
        result.from_cache = from_cache
        result.model = _ANTHROPIC_MODEL
        result.prompt_version = NEWS_PROMPT_VERSION
        return result

    except Exception as exc:
        logger.error(
            "%s: news check — excepción inesperada: %s\n%s",
            symbol,
            exc,
            traceback.format_exc(),
        )
        return NewsCheckResult(
            status=NewsCheckStatus.UNVERIFIED,
            warnings=["⚠ NEWS [UNVERIFIED]: no se pudo verificar contexto de noticias (error inesperado)"],
            model=_ANTHROPIC_MODEL,
            prompt_version=NEWS_PROMPT_VERSION,
        )
