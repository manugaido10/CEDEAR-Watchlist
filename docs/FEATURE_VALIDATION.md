# CEDEAR Feature Validation — Protocolo de Validación de Nuevas Funcionalidades

Este skill define los checks que debe pasar cualquier nueva funcionalidad
antes de integrarse al pipeline de CEDEAR Watchlist. Aplica a nuevos
módulos de análisis, scanners, reportes, o scripts de ejecución.

## Cuándo aplicar este skill

Aplicar cuando se implementa:
- Un nuevo módulo de análisis (ej: `analysis/reversal/`)
- Un nuevo script de ejecución (ej: `scripts/run_reversals.py`)
- Un nuevo generador de reportes (ej: `output/reversal_report.py`)
- Cualquier funcionalidad que no modifica código existente sino que agrega nueva

Para cambios a módulos existentes usar `cedear-pipeline-check` en su lugar.

---

## Nivel A — Smoke test (siempre)

Verifica que la funcionalidad arranca y corre sin excepción sobre datos reales.

python scripts/run_reversals.py --sample 5 2>&1 | tail -20

**Pasa si:**
- Termina con exit code 0
- No hay traceback ni excepción no manejada
- Imprime algún output de progreso o resultado (no cuelga en silencio)
- El tiempo de ejecución es razonable (< 3 minutos para --sample 5)

**Falla si:**
- ImportError, ModuleNotFoundError, AttributeError, TypeError
- Excepción no capturada durante la ejecución
- El proceso cuelga sin output

---

## Nivel B — Validación de lógica de criterios (siempre para módulos de análisis)

Verifica que cada criterio del diseño (en DECISIONS.md) está implementado
correctamente. Se hace con casos de prueba manuales sobre datos sintéticos
o inspeccionando el comportamiento del módulo con datos reales conocidos.

### Patrón general

Para cada criterio de descarte o scoring, construir un caso que debería
fallar y verificar que el módulo lo descarta:

python -c "
from analysis.reversal.reversal_scanner import scan_reversals
from data.fetcher import fetch_universe_bundle

bundles = fetch_universe_bundle(['AAPL.BA'])
results = scan_reversals(bundles)
print(f'Resultados: {len(results)}')
for r in results:
    print(f'  {r.symbol}: score={r.score}, RSI={r.rsi_14:.1f}')
"

### Checks específicos para el módulo de reversión táctica

Correr cada uno y verificar el resultado esperado:

**B1 — RSI fuera de rango es descartado:**
python scripts/run_reversals.py --sample 20 2>&1 | grep -E "(RSI|rsi)" | head -10
Pasa si: ningún ticker en el output tiene RSI > 45 o RSI < 25.

**B2 — Score dentro del rango válido:**
python scripts/run_reversals.py --sample 20 2>&1 | grep "Score:"
Pasa si: todos los scores están entre 0 y 100.

**B3 — Invalidación por debajo del precio actual:**
python scripts/run_reversals.py --sample 20 2>&1 | grep -E "(Invalidación|invalidation)"
Pasa si: todos los niveles de invalidación en ARS son menores al precio
actual del ticker. Si hay un nivel mayor al precio, es un bug crítico.

**B4 — Capital sugerido dentro del rango definido:**
python scripts/run_reversals.py 2>&1 | grep "Capital sugerido"
Pasa si: todos los valores están entre 5% y 8% del capital invertible
(USD 450 - USD 720 sobre USD 9.000 base).

**B5 — Reporte generado con estructura válida:**
ls -la output/reversiones_*.md 2>/dev/null && \
cat output/reversiones_$(date +%Y-%m-%d).md | head -30
Pasa si: el archivo existe, tiene más de 10 líneas, y el header contiene
la fecha correcta.

---

## Nivel C — Sanity check de output (siempre)

Verifica que el output tiene sentido económico y no contiene valores
absurdos que indicarían bugs silenciosos.

python scripts/run_reversals.py 2>&1 | grep -E "(oportunidades|Score|RSI|Invalidación)"

**Pasa si:**
- La cantidad de oportunidades encontradas es razonable (0-10 es normal;
  >15 simultáneas sugiere que los criterios son demasiado laxos)
- Si hay 0 oportunidades, el log explica por qué (no es un error silencioso)
- Los niveles de invalidación tienen sentido en el contexto del precio actual
- Los catalizadores listados son específicos (no genéricos o vacíos)

**Falla si:**
- Más de 15 oportunidades en un ciclo normal (criterios demasiado permisivos)
- Niveles de invalidación iguales a 0 o negativos (bug en cálculo)
- Scores todos iguales (bug en scoring)
- Capital sugerido que suma más del capital total disponible

---

## Cómo reportar los resultados

Después de correr los checks, presentar una tabla:

| Check | Descripción | Resultado | Nota |
|---|---|---|---|
| A — Smoke test | `run_reversals.py --sample 5` | ✅ PASA / ❌ FALLA | |
| B1 — RSI range | Todos los RSI en output ∈ [25,45] | ✅ PASA / ❌ FALLA | |
| B2 — Score range | Todos los scores ∈ [0,100] | ✅ PASA / ❌ FALLA | |
| B3 — Invalidación < precio | Nivel stop < precio actual | ✅ PASA / ❌ FALLA | |
| B4 — Capital range | Capital por posición ∈ [5%,8%] | ✅ PASA / ❌ FALLA | |
| B5 — Reporte válido | Archivo .md generado y legible | ✅ PASA / ❌ FALLA | |
| C — Sanity check | Cantidad y valores razonables | ✅ PASA / ❌ FALLA | |

**Veredicto:**
- Todos los checks pasan → **LISTO PARA INTEGRAR** → commitear
- Cualquier check falla → **BLOQUEADO** — listar qué falló y el fix requerido

---

## Errores comunes y diagnóstico

| Síntoma | Causa probable | Acción |
|---|---|---|
| `AttributeError: TickerBundle has no attribute X` | El dataclass cambió o el campo tiene otro nombre | Revisar `data/models.py` |
| Smoke test pasa pero 0 oportunidades siempre | Criterios demasiado estrictos o bug en un filtro | Loguear cuántos tickers pasan cada criterio por separado |
| Scores todos iguales (ej: todos 0 o todos 100) | Bug en la función de scoring | Agregar logging intermedio al cálculo del score |
| Invalidación > precio actual | Bug en la lógica de soporte (tomó resistencia en vez de soporte) | Verificar que el soporte se busca por debajo del precio actual |
| Capital sugerido > 8% | Bug en la distribución de capital | Verificar el cap máximo en `generate_reversal_report` |
| Más de 15 oportunidades | Criterio de catalizador demasiado permisivo | Revisar la detección de divergencias y velas de reversión |

---

## Adaptación para otros módulos futuros

Este skill está pensado para módulos de análisis del pipeline CEDEAR.
Para adaptar a un nuevo módulo:

1. Reemplazar el comando de Nivel A con el script correspondiente
2. En Nivel B, reemplazar los checks B1-B5 con los criterios del diseño
   del nuevo módulo (leer DECISIONS.md para la entrada correspondiente)
3. En Nivel C, ajustar los rangos de sanity según lo que tenga sentido
   para el nuevo output (cantidad esperada, rangos de valores, etc.)

Los niveles A y C son siempre aplicables sin modificación.