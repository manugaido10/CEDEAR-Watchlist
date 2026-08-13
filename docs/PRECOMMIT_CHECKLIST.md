# CEDEAR Pipeline — Protocolo de Verificación Pre-Commit

Este skill define los checks que deben pasar antes de commitear cualquier
cambio al pipeline de CEDEAR Watchlist. El objetivo es detectar problemas
de integración antes de que lleguen a producción.

## Cuándo aplicar este skill

Aplicar después de implementar cualquier cambio en:
- `data/` — fetcher, precios, fundamentals, caché, universo
- `analysis/` — Filtro 1, Filtro 2, scoring, news gate, Argentina adjustment
- `output/` — watchlist report
- `scripts/` — run_watchlist, refresh_universe, refresh_exclusions

No aplicar para cambios en `docs/`, `README.md`, o archivos de configuración
que no tocan el pipeline (`.gitignore`, `.env.example`).

---

## Checklist de verificación

### Nivel 1 — Imports y estructura (siempre)

python -c "
from data.fetcher import fetch_universe_bundle
from data.cache import Cache
from analysis.filter1_quick_sweep import run_filter1
from analysis.filter2_deep_dive import run_filter2
from output.watchlist_report import generate_report
print('imports OK')
"

**Pasa si:** imprime `imports OK` sin traceback.
**Falla si:** cualquier ImportError, ModuleNotFoundError, o SyntaxError.

---

### Nivel 2 — Pipeline end-to-end sin news gate (siempre)

python scripts/run_watchlist.py --sample 3 --no-news-gate 2>&1

**Pasa si:**
- Los logs NO muestran errores de yfinance para tickers conocidos (los que están
  en `data/yfinance_exclusions.json` deben ser silenciados)
- Aparece `Filter 1 complete — survivors=N` con N > 0
- Aparece `Filter 2 complete — ranked=3`
- Aparece `Report saved → output/watchlist_YYYY-MM-DD.md`
- El reporte generado tiene 3 posiciones con score, invalidación y capital

**Falla si:**
- Hay errores de yfinance para tickers que deberían estar excluidos
- El pipeline termina con excepción
- El reporte no se genera o está vacío
- Alguna posición tiene `score=0` o `invalidation_level_ars=0` (indica bug en cálculo)

---

### Nivel 3 — News gate (solo cuando se modifica news_gate.py o filter2_runner.py)

export ANTHROPIC_API_KEY=$(grep ANTHROPIC_API_KEY .env | cut -d'=' -f2) && \
python scripts/run_watchlist.py --sample 1 2>&1 | grep -E "(light check|tiebreaker|HARD_NEWS|CLEAN|CONFIRM|INCONCLUSIVE|DISCARD|no response)"

**Pasa si:**
- Aparece `light check clean` o `light check hard_news_detected` (no `no response`)
- Si el tiebreaker se activa: aparece `CONFIRM`, `INCONCLUSIVE`, o `DISCARD`
- No hay `⚠ light check: no response` ni `⚠ tiebreaker: no response`

**Falla si:**
- Todos los tickers muestran `no response` (indica que ANTHROPIC_API_KEY no está
  disponible o el cliente de Anthropic falla)
- Hay un traceback en el log del news gate

**Nota:** Si el nivel 3 falla por API key no disponible, verificar:
python -c "from dotenv import load_dotenv; import os; load_dotenv(); print(bool(os.getenv('ANTHROPIC_API_KEY')))"

---

### Nivel 4 — Integridad del caché (cuando se modifica data/cache.py o data/fetcher.py)

python -c "
from data.cache import Cache
from data.universe import load_universe
from data.models import AssetType
c = Cache()
tickers = [m.symbol_underlying for m in load_universe()
           if m.asset_type == AssetType.CEDEAR and m.symbol_underlying]
fresh = [s for s in tickers if c.fundamentals_are_fresh(s)]
print(f'Fundamentals cache: {len(fresh)}/{len(tickers)} frescos')
assert len(fresh) > 100, f'Muy pocos tickers con caché fresco: {len(fresh)}'
print('cache OK')
"

**Pasa si:** imprime `cache OK` con al menos 100 tickers frescos.
**Falla si:** AssertionError o menos de 100 tickers (indica que el caché se limpió
por error o hay un bug en la lógica de frescura).

---

## Cómo reportar los resultados

Después de correr los checks, presentar una tabla con el resultado de cada nivel:

| Check | Comando | Resultado | Nota |
|---|---|---|---|
| Imports | `python -c "from data..."` | ✅ PASA / ❌ FALLA | |
| Pipeline (--sample 3) | `run_watchlist.py --sample 3 --no-news-gate` | ✅ PASA / ❌ FALLA | |
| News gate | `run_watchlist.py --sample 1` | ✅ PASA / ⏭ NO APLICA / ❌ FALLA | Solo si se modificó T3 |
| Caché | `cache.fundamentals_are_fresh` | ✅ PASA / ⏭ NO APLICA / ❌ FALLA | Solo si se modificó cache.py |

**Veredicto:**
- Todos los checks aplicables pasan → **LISTO PARA COMMITEAR**
- Cualquier check falla → **BLOQUEADO** — listar qué falló y por qué

---

## Errores comunes y su diagnóstico

| Error en log | Causa probable | Acción |
|---|---|---|
| `yfinance returned empty data for AABA.BA` | Ticker no está en exclusions JSON | Correr `python scripts/refresh_exclusions.py --new-only` |
| `light check: no response` | ANTHROPIC_API_KEY no disponible | Verificar `.env` y que `load_dotenv()` se llama en el script |
| `No income statement from yfinance for X` | Underlying no está en exclusions | Correr `python scripts/refresh_exclusions.py --new-only` |
| `invalidation_level_ars = 0.01` | Bug en cálculo de swing low o MA | Revisar `_compute_invalidation` en filter2_runner.py |
| `Filter 1 complete — survivors=0` | Umbrales demasiado estrictos o bug en el fetcher | Revisar filter1_thresholds.py y el output de fetch_universe_bundle |

---

## Frecuencia recomendada

- **Antes de cada commit** que toca el pipeline: Nivel 1 + Nivel 2 (obligatorio)
- **Cuando se modifica el news gate**: agregar Nivel 3
- **Cuando se modifica la lógica de caché**: agregar Nivel 4
- **Semanalmente en producción**: correr el pipeline completo sin --sample y
  revisar que el ranking tiene sentido con el mercado actual

## Adaptación para el módulo de reversiones (run_reversals.py)

`FEATURE_VALIDATION.md` ya está calibrado para reversiones (Niveles A/B/C con comandos de `run_reversals.py`).
Para cambios a código existente del scanner usar: **Nivel 1** de este checklist + **Nivel A** de `FEATURE_VALIDATION.md` como smoke test de regresión.