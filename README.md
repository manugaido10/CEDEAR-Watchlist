# CEDEAR Watchlist — Cocos Capital

Sistema de análisis semanal de oportunidades de inversión en CEDEARs y acciones argentinas disponibles en Cocos Capital. Produce un ranking accionable con señal técnica, confirmación fundamental, ajuste de riesgo Argentina, nivel de invalidación y propuesta de distribución de capital.

---

## Cómo funciona

El sistema aplica dos filtros en cascada sobre el universo completo de ~391 instrumentos:

```
[Universo: 370 CEDEARs + 21 acciones argentinas]
        ↓
[Filtro 1 — barrido rápido sobre todo el universo]
  Descarta lo claramente malo: solvencia, earnings en caída,
  liquidez insuficiente, tendencia técnica rota.
  Criterios adicionales para acciones argentinas (riesgo país en el negocio).
        ↓ (~280 survivors)
[Filtro 2 — análisis profundo solo sobre survivors]
  T1: Técnico avanzado (multi-timeframe, breakouts, MAs, RSI, RS)
  T2: Fundamentals como filtro de calidad (confirmed/neutral/deteriorating)
  T3: News gate via Claude API — chequeo liviano incondicional + desempate condicional
  T4: Ajuste de riesgo Argentina (CCL vol + premium CEDEAR/subyacente)
        ↓
[Ranking final + invalidación + propuesta de capital]
```

**Capital base:** USD 10.000 | **Posiciones objetivo:** 5–10 | **Cadencia:** semanal

---

## Setup inicial

```bash
# 1. Clonar y activar entorno
git clone <repo>
cd CEDEAR-Watchlist
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Configurar variables de entorno
cp .env.example .env
# Editar .env con:
#   ANTHROPIC_API_KEY=sk-ant-...   (para el news gate — Claude API)
```

> **No se requiere FMP_API_KEY** — los fundamentals de CEDEARs se obtienen vía yfinance (gratuito).

---

## Comandos principales

### Ciclo semanal completo

```bash
# Corrida completa con news gate activo (recomendado para uso en producción)
python scripts/run_watchlist.py

# Corrida sin news gate (más rápida, para testing o cuando no se necesita T3)
python scripts/run_watchlist.py --no-news-gate

# Corrida de prueba con N survivors (para verificar el pipeline antes del universo completo)
python scripts/run_watchlist.py --sample 5
python scripts/run_watchlist.py --sample 5 --no-news-gate
```

**Output generado:**
- Resumen en consola con el ranking completo
- `output/watchlist_YYYY-MM-DD.md` — reporte detallado con técnico, fundamentals, Argentina, invalidación y capital por posición

---

### Mantenimiento del universo

```bash
# Reconstruir el snapshot del universo desde el PDF de BYMA + Excel de CVSA
# Correr cuando BYMA lista nuevos CEDEARs o cambian ratios de conversión
python scripts/refresh_universe.py \
  --byma-pdf data/sources/Listado-CEDEAR.pdf \
  --cvsa-excel data/sources/Tablas_CVSA.xlsx
```

> El universo resultante se guarda en `data/universe_snapshot.json` (versionado en git).
> Las acciones argentinas se configuran manualmente en `data/sources/argentine_stocks.yaml`.

---

### Mantenimiento de exclusiones de yfinance

```bash
# Verificar lista completa: detecta tickers recuperados y nuevos fallos
python scripts/refresh_exclusions.py

# Solo buscar tickers que antes fallaban y ahora tienen datos
python scripts/refresh_exclusions.py --recover-only

# Solo verificar tickers nuevos del universo que aún no están en la lista
python scripts/refresh_exclusions.py --new-only
```

> Correr después de cada `refresh_universe.py` para mantener la lista de exclusiones actualizada.
> La lista vive en `data/sources/yfinance_exclusions.json` (versionado en git).

---

### Diagnóstico y calibración

```bash
# Diagnóstico del Filtro 2 sin news gate (para calibrar umbrales T1/T2/T4)
# Genera cache/filter2_diagnostics.csv con valores crudos por ticker
python -m analysis.filter2_deep_dive.filter2_diagnostics

# Diagnóstico del Filtro 1 (para calibrar umbrales C1/C2/C4/C5)
# Ver analysis/filter1_quick_sweep.py para el modo diagnóstico
```

---

## Estructura del proyecto

```
CEDEAR-Watchlist/
├── data/
│   ├── models.py              # Dataclasses: TickerBundle, TickerMetadata, etc.
│   ├── universe.py            # Lector del snapshot estático del universo
│   ├── prices.py              # Precios ARS vía yfinance (.BA) — segmento pesos
│   ├── ccl.py                 # Tipo de cambio CCL vía dolarapi.com + argentinadatos.com
│   ├── fundamentals.py        # Fundamentals de subyacentes vía yfinance
│   ├── cache.py               # Caché en filesystem (parquet + JSON)
│   ├── fetcher.py             # Orquestador: fetch_universe_bundle()
│   └── sources/
│       ├── universe_snapshot.json     # Universo de 391 tickers (versionado)
│       ├── argentine_stocks.yaml      # Lista curada de acciones argentinas
│       ├── yfinance_exclusions.json   # Tickers sin cobertura en yfinance
│       ├── Listado-CEDEAR.pdf         # PDF oficial BYMA (fuente del universo)
│       └── Tablas_CVSA.xlsx           # Excel CVSA (oráculo de validación)
│
├── analysis/
│   ├── filter1_quick_sweep.py         # Filtro 1: barrido rápido, todo el universo
│   ├── filter1_thresholds.py          # Umbrales del Filtro 1 (calibrados)
│   ├── argentina_risk_flags.yaml      # Flags manuales A1/A2/A3 para acciones argentinas
│   └── filter2_deep_dive/
│       ├── filter2_runner.py          # Orquestador del Filtro 2
│       ├── technical_scoring.py       # T1: scoring técnico avanzado
│       ├── fundamental_quality.py     # T2: calidad fundamental
│       ├── news_gate.py               # T3: news gate via Claude API
│       ├── argentina_adjustment.py    # T4: ajuste de riesgo Argentina
│       ├── filter2_thresholds.py      # Umbrales del Filtro 2 (calibrados)
│       ├── filter2_models.py          # Dataclasses del Filtro 2
│       └── filter2_diagnostics.py     # Modo diagnóstico para calibración
│
├── output/
│   └── watchlist_report.py    # Generador de reporte (consola + Markdown)
│
├── scripts/
│   ├── run_watchlist.py       # Pipeline end-to-end
│   ├── refresh_universe.py    # Reconstruye el universo desde PDF BYMA
│   └── refresh_exclusions.py  # Mantiene la lista de exclusiones de yfinance
│
├── docs/
│   ├── CRITERIOS_INVERSION.md # Marco de decisión de inversión (fuente de verdad)
│   ├── DECISIONS.md           # Log de decisiones del proyecto
│   ├── ARCHITECTURE.md        # Arquitectura técnica
│   ├── DATA_SOURCES.md        # Fuentes de datos y sus limitaciones
│   └── DISENO_FILTRO_2.md     # Spec detallada del Filtro 2
│
├── cache/                     # Caché local (gitignoreado)
│   ├── prices/                # Parquet por ticker .BA
│   ├── fundamentals/          # JSON por subyacente (TTL 90 días)
│   ├── news/                  # JSON por query (TTL 4 días)
│   └── filter2_diagnostics.csv
│
└── output/                    # Reportes generados (gitignoreado)
    └── watchlist_YYYY-MM-DD.md
```

---

## Fuentes de datos

| Dato | Fuente | Costo |
|---|---|---|
| Universo de CEDEARs | PDF oficial BYMA (descarga manual periódica) | Gratuito |
| Acciones argentinas | Lista curada manual (`argentine_stocks.yaml`) | — |
| Precios ARS (.BA) | yfinance — segmento pesos únicamente | Gratuito |
| Tipo de cambio CCL | dolarapi.com + argentinadatos.com | Gratuito |
| Fundamentals CEDEARs | yfinance (subyacente US/internacional) | Gratuito |
| Fundamentals argentinas | No disponible (gap estructural del mercado) | — |
| News gate (T3) | Claude API — claude-haiku-4-5 + web search | ~USD 0.50/ciclo |

---

## Notas operativas

**Análisis técnico:** siempre sobre el segmento en pesos (`.BA`), que tiene mayor liquidez que el segmento dólar MEP (`.D.BA`). El PnL se mide en USD convirtiendo via CCL.

**Stop técnico:** cada oportunidad tiene un nivel de invalidación explícito (swing low o MA relevante con buffer del 3%). No se usa stop por porcentaje fijo.

**News gate:** usa caché de 4 días para no repetir búsquedas en corridas sucesivas. El chequeo liviano corre sobre todos los survivors; el desempate completo solo se activa cuando hay divergencia técnico/fundamental o noticias duras detectadas.

**Acciones argentinas:** no tienen cobertura de fundamentals en yfinance. El sistema las compensa activando el desempate completo del news gate automáticamente cuando tienen tendencia alcista, con búsqueda enfocada en contexto macro/regulatorio argentino.

**Caché:** los precios tienen TTL hasta el próximo cierre EOD, los fundamentals 90 días, las noticias 4 días. El caché se almacena en `cache/` (gitignoreado).