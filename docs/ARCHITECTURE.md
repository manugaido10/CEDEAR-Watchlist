# Architecture — CEDEAR Watchlist (Cocos Capital)

> Technical reference for how the system is structured. Updated only when structure changes, not on every session. Written in English (code-facing document) — see `CRITERIOS_INVERSION.md` and `DECISIONS.md` for business logic and reasoning, which stay in Spanish.

## Status
🟡 Data layer implemented — analysis modules not yet started.

## Goal

A weekly-refreshed watchlist system that:
1. Pulls the universe of tradeable assets on Cocos Capital — CEDEARs (foreign companies) and direct Argentine stocks
2. Runs a fast quality sweep (Filter 1) across the entire universe to discard clearly bad candidates
3. Runs a deep multi-technique analysis (Filter 2) only on Filter 1 survivors: advanced technical, fundamental quality check, sentiment/news as tie-breaker, Argentina-risk adjustment
4. Outputs a ranked list with entry signal, fundamental confirmation, and a defined technical invalidation level per ticker
5. Sends alerts when a watchlist ticker breaks a key technical level outside the weekly cycle

Asset type matters: CEDEARs carry Argentina-risk only in the "wrapper" (FX gap, CEDEAR/underlying ratio, local liquidity), while direct Argentine stocks carry country risk in the business itself. Filter 1 is stricter for Argentine stocks accordingly. See `CRITERIOS_INVERSION.md` for full rationale.

## High-level data flow

```
[Cocos Capital universe: CEDEARs + Argentine stocks]
        ↓
[FILTER 1 — fast sweep, moderate strictness, whole universe]
  - common discard criteria (solvency, earnings trend, liquidity, broken technical trend)
  - extra criteria for Argentine stocks (regulatory/macro exposure)
        ↓ (survivors only)
[FILTER 2 — deep analysis, multi-technique]
  ├─ Advanced technical scoring (multi-timeframe, breakouts, MAs, RSI, relative strength)
  ├─ Fundamental quality check (confirms, doesn't drive score)
  ├─ Sentiment/news via live web research → TIE-BREAKER only when technical + fundamental disagree
  └─ Argentina-risk adjustment (wrapper-only for CEDEARs, business-level for Argentine stocks) → score modifier, never a hard discard
        ↓
[Ranked output + invalidation levels per ticker]
        ↓
[Alert monitor — between weekly cycles, on key level breaks]
```

## Modules

| Module | Responsibility | Status |
|---|---|---|
| `data/universe.py` | Read tradeable universe from local snapshot (never calls external APIs) | Done |
| `data/prices.py` | Fetch OHLCV in ARS for `.BA` tickers via yfinance (pesos segment only, never `D`) | Done |
| `data/ccl.py` | Fetch CCL spot + historical series (dolarapi.com + argentinadatos.com) | Done |
| `data/fundamentals.py` | Fetch underlying fundamentals via FMP (CEDEARs only; rate-limited, 90-day cache) | Done |
| `data/cache.py` | Filesystem cache abstraction (parquet for time series, JSON for metadata) | Done |
| `data/fetcher.py` | Orchestrator: `fetch_universe_bundle()` → list of `TickerBundle` + `FetchSummary` | Done |
| `data/models.py` | Dataclasses: `TickerMetadata`, `PriceHistory`, `CCLSeries`, `FundamentalsSnapshot`, `TickerBundle`, `FetchStatus`, `FetchSummary` | Done |
| `scripts/refresh_universe.py` | Manual tool: cross-reference pyCocos + CVSA Excel → `data/universe_snapshot.json` | Done |
| `analysis/filter1_quick_sweep` | Fast pass/fail gate per `CRITERIOS_INVERSION.md` Filtro 1 | Not started |
| `analysis/technical_scoring` | Advanced multi-timeframe technical scoring per Filtro 2.1 | Not started |
| `analysis/fundamental_quality` | Fundamental quality confirmation per Filtro 2.2 | Not started |
| `research/web_validator` | Live web search for news/sentiment, tie-breaker per Filtro 2.3 | Not started |
| `analysis/argentina_adjustment` | Score modifier per Filtro 2.4 — branches by asset type | Not started |
| `output/watchlist_report` | Final ranked output + invalidation levels | Not started |
| `alerts/level_monitor` | Detects breaks of key technical levels between weekly cycles | Not started |

## Data layer design decisions

- **Universe source:** `data/universe_snapshot.json` is versioned in git. Updated manually
  (monthly or on splits/new listings) by `scripts/refresh_universe.py`. pyCocos is only used
  in the refresh script, never in the weekly cycle — isolates pyCocos fragility from production.

- **Technical analysis:** always on the ARS pesos segment (`.BA`). The MEP segment (`D.BA`) is
  never fetched. `prices.py` raises if a `D.BA` ticker is passed. See `DECISIONS.md` 2026-06-20 (c).

- **CCL separation:** `CCLSeries` travels in every `TickerBundle` but is kept separate from
  `PriceHistory`. PnL conversion (ARS → USD) happens downstream, never inside the data layer.

- **FMP call budget:** 3 calls/ticker × ~70 CEDEARs = ~210 first-run calls. 90-day cache TTL
  means subsequent weekly runs typically spend <20 calls. Conservative cap at 240/session.

- **Cache TTLs:**
  - Prices: fresh if last bar ≤ 3 calendar days old (covers weekends + 1 holiday)
  - CCL: fresh if spot recorded today
  - Fundamentals: fresh for 90 days (quarterly earnings cadence)
  - Universe: no automatic TTL — refresh manually

- **Failure isolation:** every ticker fetch is individually wrapped. A single ticker error
  sets `status = MISSING` on that bundle and is recorded in `warnings`; the cycle continues.
  The `FetchSummary` returned by `fetch_universe_bundle()` shows aggregate counts per status.

## Tech stack
- **Language: Python 3.9**
- **Data sources:** yfinance (prices, dev), dolarapi.com (CCL), argentinadatos.com (CCL history),
  FMP free tier (fundamentals), pyCocos (universe snapshot only, manual), CVSA Excel (ratios)
- **Storage:** Filesystem cache (`cache/`, gitignored) — parquet for time series, JSON for metadata
- **Scheduling:** TBD (weekly cycle — cron, GitHub Actions, or manual trigger)

## Conventions
- All code, comments, and commit messages: English
- Business logic and reasoning docs: Spanish
- Every fundamental/technical threshold used in code should trace back to a line in `CRITERIOS_INVERSION.md` — no magic numbers without documented rationale

---
*Last updated: 2026-06-21 — data layer implemented; analysis modules pending.*
