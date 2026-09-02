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
import time
import traceback
from dataclasses import dataclass, field
from datetime import date
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

# Cache namespace prefix — prevents collision with watchlist news gate entries
_CACHE_STAGE = "reversal_news"

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


@dataclass
class NewsCheckResult:
    status: NewsCheckStatus
    warnings: List[str] = field(default_factory=list)
    # VERIFIED_CLEAR  → warnings = []
    # VERIFIED_WARNING → warnings has formatted finding(s), ≤ NEWS_REVERSAL_MAX_WARNINGS
    # UNVERIFIED      → warnings = ["⚠ NEWS [UNVERIFIED]: ..."]


# ── Claude API search ──────────────────────────────────────────────────────────

def _web_search(prompt: str) -> Tuple[List[dict], str]:
    """Call Claude API with built-in web_search tool.

    Returns (search_results, llm_text). Returns ([], '') on any error.
    Error details are logged at ERROR level — never silenced (Decision #14 Fix 2).
    """
    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model=_ANTHROPIC_MODEL,
            max_tokens=1024,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
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
        return [], ""
    except Exception as exc:
        logger.error(
            "Claude API call failed (reversal news check) for prompt '%.60s': %s\n%s",
            prompt,
            exc,
            traceback.format_exc(),
        )
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
                if len(results) >= NEWS_REVERSAL_MAX_RESULTS:
                    break
        elif btype == "text":
            llm_text += block.text

    return results, llm_text


# ── Cache helpers ──────────────────────────────────────────────────────────────

def _cache_key(query: str) -> str:
    return hashlib.md5(f"{_CACHE_STAGE}:{query}".encode()).hexdigest()


def _search_cached(
    query: str,
    prompt: str,
    cache: Cache,
) -> Tuple[str, bool]:
    """Returns (llm_text, from_cache).

    Only persists when llm_text is non-empty (Decision #14 Fix 1).
    """
    key = _cache_key(query)
    if cache.news_is_fresh(key, NEWS_REVERSAL_CACHE_TTL_DAYS):
        cached = cache.load_news(key)
        if cached and cached.get("llm_text"):
            return cached["llm_text"], True

    _results, llm_text = _web_search(prompt)
    if llm_text:
        cache.save_news(key, {
            "query": query,
            "stage": _CACHE_STAGE,
            "llm_text": llm_text,
            "cached_at": date.today().isoformat(),
        })
    time.sleep(NEWS_REVERSAL_DELAY_SEC)
    return llm_text, False


# ── Query and prompt builders ──────────────────────────────────────────────────

def _build_query(bundle: TickerBundle) -> str:
    meta = bundle.metadata
    if meta.asset_type == AssetType.CEDEAR:
        ticker = meta.symbol_underlying or meta.symbol_ars.replace(".BA", "")
        return f'"{ticker}" OR "{meta.name}" news last 30 days'
    else:
        ticker = meta.symbol_ars.replace(".BA", "")
        return f'"{ticker}" OR "{meta.name}" noticias ultimos 30 dias'


def _build_prompt(bundle: TickerBundle) -> str:
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

    return (
        f'Search for news about "{ticker}" OR "{name}" in the last 30 days.\n\n'
        "You are evaluating a SHORT-TERM MEAN REVERSION trade (avg. 6.5-day hold). "
        "The stock is oversold. Assess whether the decline has a FUNDAMENTAL CAUSE "
        "that would invalidate a bounce, or whether it is pure price weakness.\n\n"
        "IMPORTANT: Only report findings with a confirmed event date within the last "
        "30 days. If the most recent relevant event is older than 30 days, do NOT "
        "report it — reply CLEAR instead.\n\n"
        "Report ONLY if you find concrete evidence in these categories (priority order):\n"
        "1. Analyst recommendation change or price target cut (last 30 days)\n"
        "2. Guidance revision, profit warning, or management change (last 30 days)\n"
        "3. Litigation, regulatory investigation, or material corporate event (last 30 days)\n"
        f"4. FX/macro context: {fx_note}\n"
        "5. Upcoming calendar event: ex-dividend date, lock-up expiry, regulatory decision\n\n"
        "Reply with EXACTLY this format:\n"
        "  CLEAR — if you searched and found nothing relevant within the last 30 days\n"
        "  WARN: [category] | [one sentence finding] | [source name, date if known]\n"
        "  UNVERIFIED — if you could NOT search, or the search returned no usable results\n\n"
        "One line per finding. Do not add any other text."
    )


# ── Response parser ────────────────────────────────────────────────────────────

def _parse_response(llm_text: str, symbol: str) -> NewsCheckResult:
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
        # Truncate to max 2 items — enforced here, not in the prompt (Decision #24)
        warn_lines = warn_lines[:NEWS_REVERSAL_MAX_WARNINGS]
        formatted = [
            f"⚠ NEWS [VERIFIED]: {line[5:].strip()}"  # strip "WARN:" prefix
            for line in warn_lines
        ]
        logger.debug("%s: news check VERIFIED_WARNING — %d finding(s)", symbol, len(formatted))
        return NewsCheckResult(status=NewsCheckStatus.VERIFIED_WARNING, warnings=formatted)

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
        query = _build_query(bundle)
        prompt = _build_prompt(bundle)
        llm_text, from_cache = _search_cached(query, prompt, cache)

        if not llm_text:
            logger.warning(
                "%s: news check — sin respuesta del modelo (API vacía o error de crédito)",
                symbol,
            )
            return NewsCheckResult(
                status=NewsCheckStatus.UNVERIFIED,
                warnings=["⚠ NEWS [UNVERIFIED]: no se pudo verificar contexto de noticias (sin respuesta del modelo)"],
            )

        logger.debug("%s: news check response (from_cache=%s): '%.120s'", symbol, from_cache, llm_text.strip())
        return _parse_response(llm_text, symbol)

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
        )
