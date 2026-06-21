# Architecture — CEDEAR Watchlist (Cocos Capital)

> Technical reference for how the system is structured. Updated only when structure changes, not on every session. Written in English (code-facing document) — see `CRITERIOS_INVERSION.md` and `DECISIONS.md` for business logic and reasoning, which stay in Spanish.

## Status
🟡 Stack confirmed (Python) — implementation not yet started. This is the skeleton to be filled in during the first Claude Code sessions.

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

## Modules (planned — to be defined with Claude Code)

| Module | Responsibility | Status |
|---|---|---|
| `data/cocos_fetcher` | Get full tradeable universe (CEDEARs + Argentine stocks) + prices from Cocos Capital | Not started |
| `analysis/filter1_quick_sweep` | Fast pass/fail gate per `CRITERIOS_INVERSION.md` Filtro 1 (moderate strictness, stricter sub-rules for Argentine stocks) | Not started |
| `analysis/technical_scoring` | Advanced multi-timeframe technical scoring per Filtro 2.1 | Not started |
| `analysis/fundamental_quality` | Fundamental quality confirmation per Filtro 2.2 | Not started |
| `research/web_validator` | Live web search for news/sentiment, used as tie-breaker per Filtro 2.3 — must always fetch current data | Not started |
| `analysis/argentina_adjustment` | Score modifier per Filtro 2.4 — branches by asset type (CEDEAR vs. Argentine stock) | Not started |
| `output/watchlist_report` | Final ranked output + invalidation levels | Not started |
| `alerts/level_monitor` | Detects breaks of key technical levels between weekly cycles | Not started |

## Tech stack
- **Language: Python** (confirmed)
- Data storage: TBD (likely flat JSON/CSV initially, revisit if scale requires DB)
- Scheduling: TBD (weekly cycle — cron, GitHub Actions, or manual trigger)

## Conventions
- All code, comments, and commit messages: English
- Business logic and reasoning docs: Spanish
- Every fundamental/technical threshold used in code should trace back to a line in `CRITERIOS_INVERSION.md` — no magic numbers without documented rationale

---
*Last updated: 2026-06-19 — initial skeleton, pre-implementation.*
