# Decisiones de diseño — CEDEAR Watchlist

> Registro de decisiones no triviales tomadas durante el desarrollo del sistema.
> Cada entrada incluye contexto, decisión, alternativas consideradas y estado.
> Idioma: español (documento de lógica de negocio). Ver `docs/ARCHITECTURE.md` para el diseño técnico.

---

## 2026-09-03 — Gate de liquidez (Criterio 7): descarte por posición/ADV sobre 10%

**Contexto:**
`docs/CRITERIOS_INVERSION.md` (Filtro 1) exige descartar activos con "liquidez insuficiente del instrumento específicamente en Cocos Capital". Hasta hoy el pipeline de reversiones no medía esto — el proxy `vol_ratio` (5d/20d) mide *cambio* en volumen, no *nivel* absoluto. Consecuencia observada: señales publicadas en tickers cuya salida a la orden sugerida podría demandar múltiples días de volumen diario.

`scripts/diagnose_liquidity.py` corrió sobre los 90 símbolos únicos de `signals.jsonl` + `near_misses.jsonl` (misma metodología que se usó para calibrar el cooldown de 15 hábiles — medir primero, decidir después):

- **VIVT3.BA:** ratio 239.03% al escenario de capital 40M ARS, freq=2 en signals. Es el caso concreto que motivó el gate — señal publicada, mantenida en cartera, cuya posición al 6.5% (2.6M ARS) requeriría ~2.4× un día completo de volumen para llenar. Este es el hallazgo material: no un fenómeno teórico sino una posición existente con problema de ejecución latente.
- **BYMA.BA:** ratio 0.31% al mismo escenario, freq=3. El flag manual previo ("known-thin") **no se sostiene con los datos** — BYMA tiene ADV ~832M ARS, liquidez cómoda. Se remueve del set `KNOWN_THIN_TICKERS` de `diagnose_liquidity.py`. Se deja MORI.BA y SEMI.BA como sospechas a validar cuando aparezcan (no aparecen en la data histórica actual).
- **DECK.BA:** ratio 4.00% al escenario 40M, freq=8 — el ticker con más apariciones en signals. Confirma que el problema histórico de DECK.BA (documentado en la calibración del cooldown) **nunca fue de liquidez**; fue de régimen bajista con precio bajo la invalidación. El gate correcto sigue siendo cooldown, no liquidez.

**Decisión:**

1. **Umbral: `LIQUIDITY_MAX_RATIO_PCT = 10.0%`.** Un `position_ars / adv_ars > 10%` descarta. Elección basada en la distribución observada en la diagnóstica del 2026-09-03: hay un salto natural entre tickers en el rango 0-10% (líquidos, la mayoría del universo señalado) y los que están por encima; el 10% ya implica que salir sin mover el mercado exige dividir la orden en ~2-3 días si la liquidez del día promedio se sostiene. Estimación: **~30 de 90 símbolos históricos** habrían sido gateados al escenario de capital 40M (ratio > 10% al reference). Los 30 concentran los casos donde la fricción de ejecución dominaría el retorno técnico esperado.

2. **Hard discard (Criterio 7 en `_evaluate_bundle`), no supresión.** Consistente con RSI/soporte/catalizador/volumen/tendencia: un ticker que falla liquidez nunca entra a `signals.jsonl` ni al reporte — no queda como `tradeable=False`. La supresión (`suppression.py`) es para bloqueos que dependen de cartera y stops previos; el gate de liquidez depende del ticker y del capital total nada más — arquitectónicamente pertenece pre-oportunidad.

3. **Fail-open por dato ausente.** `check_liquidity(adv_ars, total_capital_ars)` devuelve `None` (no descarta) cuando cualquiera es `None` o `<= 0`. Racional: mismo patrón que `check_sizing_cap` con `total_capital_ars=None` — "no puedo evaluar" no es lo mismo que "el gate falló". El scanner emite **una** WARNING por corrida cuando `total_capital_ars` no fue provisto (afecta tanto Criterio 7 como Parte C de supresión); esta consolidación reemplaza la advertencia previa que era específica de Parte C.

4. **Matemática compartida:** nuevo módulo `analysis/reversal/liquidity.py` con las constantes `POSITION_PCT_MID = 0.065`, `TRAILING_TRADING_DAYS = 20`, `LIQUIDITY_MAX_RATIO_PCT = 10.0` y las funciones `compute_adv_ars(df, as_of=None)` + `check_liquidity(adv_ars, total_capital_ars)`. **`diagnose_liquidity.py` importa desde acá** — antes tenía su propia copia local; el drift entre ambos silenciaría la calibración. La refactorización es prerrequisito de esta decisión, no accesoria.

5. **Cálculo dentro de `_compute_metrics`:** `adv_ars = compute_adv_ars(df)` sobre el DataFrame que la función ya construye (columnas lowercased, ffilled). Cero I/O adicional — la data ya está en memoria. El bundle no gana un campo nuevo (se computa localmente en el scanner) porque la métrica es específica del scanner de reversiones.

6. **Capital-dependencia intencional.** Un mismo ticker puede pasar en una corrida (capital 20M ARS → posición 1.3M) y fallar en otra (capital 80M ARS → posición 5.2M). No es bug: refleja que la fricción de ejecución escala con el tamaño de la posición, no solo con la liquidez del ticker. Auditar corridas históricas requiere considerar el `--capital-ars` de cada una.

**Alternativas consideradas:**
- **Threshold 5%:** más conservador, gatearía ~45/90 símbolos. Descartado por ahora — sin evidencia de fricción de ejecución a ratios 5-10%; se puede endurecer cuando aparezca evidencia (fill quality en órdenes reales).
- **Gate como near-miss "casi líquido":** deferido — la lógica de `near_miss_tracker.py` está centrada en criterios técnicos (RSI, soporte, catalizador), no en liquidez. Extenderla a "quedó fuera solo por liquidez" es útil para calibrar el umbral con el tiempo, pero suma scope y contamina la clasificación de near-miss actual. Se retoma cuando haya ≥ 20 tickers gateados por liquidez en corridas reales.
- **Gate por `ADV` absoluto (piso fijo en ARS):** descartado — la métrica correcta no es ADV crudo sino ADV vs. posición proyectada. Un ticker con ADV 10M ARS puede ser líquido para 500K y ilíquido para 2M.
- **Gate como parte de supresión:** descartado (ver punto 2). Rompe la separación conceptual "descarte técnico previo a la oportunidad" vs. "bloqueo por estado de cartera".

**Tests:**
- `tests/test_liquidity.py`: 20 casos — `compute_adv_ars` (df vacío, sin volumen, ventana, as_of), `check_liquidity` (bajo threshold, en threshold, sobre threshold, adv=None, capital=None, cero), integración con `scan_reversals` (mismo bundle: descarta con capital, deja pasar sin capital, deja pasar cuando ADV=None). Estilo de inyección de dependencias, sin file I/O.
- `tests/test_reversal_scanner_guardrail.py`: agregado `adv_ars=None` a las fixtures de `_BundleMetrics` que faltaba después de extender la dataclass.

**Estado:** implementado. Umbral queda registrado en `analysis/reversal/liquidity.py::LIQUIDITY_MAX_RATIO_PCT` para futura recalibración (patrón: cambiar el número no requiere entrada nueva en DECISIONS; cambiar la fórmula/estructura sí).

---

## 2026-09-03 — Scale-in condicional + sizing real en ARS con MEP como conversión

**Contexto:**
Dos huecos identificados en la implementación de Fase 1.2 (supresión) y en el reporte de reversiones:

1. **`check_open_position` bloqueaba TODA señal cuando ya había posición abierta.** El criterio en `docs/CRITERIOS_INVERSION.md` sección "Gestión de capital y tamaño de posición" es explícito en dos reglas relacionadas: (i) *"Permitido escalar posiciones si la señal se reconfirma"* y (ii) *"No se permite promediar a la baja"*. Bloqueo incondicional colapsa ambas en una sola: nunca se puede sumar, aunque la tesis se refuerce. El scanner emitía señales legítimas de suma que quedaban archivadas como "no operables".
2. **`output/reversal_report.py` usaba `_TOTAL_CAPITAL_USD = 9_000.0` hardcodeado.** La convención adoptada en 2026-08-27 (ver entrada "PnL neto de comisiones + conversión FX vía MEP") es ARS-nativa; el reporte seguía viviendo en USD como si fuera el instrumento primario. Además el capital era una constante desconectada del `--capital-ars` que el scanner ya consumía para el cap del 8%.

**Decisión:**

1. **Scale-in condicional por precio.** `check_open_position(symbol, entry_price_ars, positions)` devuelve un `OpenPositionCheck` con `blocked`, `is_scale_in`, `existing_position`. La regla:
   - `entry_price_ars > open_price_ars` → `blocked=False`, `is_scale_in=True` — el precio reconfirmó la tesis, se permite sumar (regla "Escalado de posiciones").
   - `entry_price_ars <= open_price_ars` → `blocked=True`, `reason="Bloqueado: sumar ahora sería promediar a la baja (costo previo X, precio actual Y)"` — regla "No promediar a la baja". La igualdad se trata como *no reconfirmada*: el precio tiene que subir por encima del costo previo, no solo empatar.
   - Sin posición abierta → `blocked=False`, `is_scale_in=False`.
   `positions_log.open_position()` ya garantiza un máximo de una posición abierta por ticker, así que no hay que resolver el caso de múltiples.

2. **`SuppressionResult` propaga `is_scale_in` y `existing_position`** para que el reporte no tenga que re-consultar el log. Cuando la sizing cap hard-bloquea a un scale-in con 0 headroom, el resultado sigue llevando `is_scale_in=True` — es información útil para el operador aunque la señal quede como `tradeable=False`.

3. **Capital ARS-nativo con MEP para conversión display.** `generate_reversal_report(opportunities, total_capital_ars, positions, ...)` — ambos parámetros son requeridos, sin defaults silenciosos. Se eliminó `_TOTAL_CAPITAL_USD`. El equivalente USD se muestra entre paréntesis usando `fetch_mep().spot` (mismo patrón que `performance_report.py`). Si el MEP falla, el reporte sigue funcional en ARS y omite la columna USD. Nunca CCL: MEP es la tasa efectiva del inversor para CEDEARs comprados en pesos.

4. **`capital_disponible_ars = total_capital_ars - Σ (qty × open_price_ars) sobre TODAS las posiciones abiertas`** (proxy manual — decisión previa: no hay módulo de cash-tracking). El reporte lo publica junto con `capital_comprometido` para que quede visible al operador.

5. **Asignación diferenciada por tipo de oportunidad:**
   - **Nuevas** (`tradeable=True`, `is_scale_in=False`): ponderación por score entre nuevas, luego clip a [5%, 8%] de `total_capital_ars`. Comportamiento equivalente al histórico.
   - **Sumas** (`is_scale_in=True`): mismo cálculo base, luego se recorta al headroom del 8% por ticker vía `per_ticker_headroom_ars(symbol, positions, total_capital_ars)` — nuevo helper público en `analysis/reversal/suppression.py` que expone la matemática que ya usaba `check_sizing_cap` internamente. Se factorizó ahí para evitar duplicar la regla; `check_sizing_cap` queda con su lógica de bloqueo intacta.
   - **Suprimidas**: 0.

6. **Scale-down proporcional cuando `Σ propuesto > capital_disponible_ars`.** Se aplica el mismo factor a todas las asignaciones no nulas. Motivación: nunca sugerir más capital del que hay disponible según la contabilidad manual. Alternativa (recortar solo a las de menor score) descartada — hace opaco cuánto pesa cada posición cuando el operador compara con `total_capital_ars`.

7. **Caso borde `capital_disponible_ars <= 0`:** todas las asignaciones = 0 y el header del reporte muestra: *"⚠ Sin capital disponible — cartera ya comprometida al 100% o más"*. No se filtra la publicación de la señal (auditoría) ni se aborta el reporte — la decisión de operar o no siempre es manual.

8. **Etiqueta visual del scale-in en el reporte.** Prefijo `➕ SUMA:` en el heading, sección "Suma a posición existente" con costo previo, headroom disponible y suma sugerida — en lugar de la sección "Capital Sugerido" que se usa para nuevas. La tabla de rank agrega columna "Tipo" con `nueva` / `➕ suma` / `🚫 no operar`.

**Audit trail:** `signal_registry.record_signals` agrega `is_scale_in: true` al JSON cuando corresponde. Se preserva el rastro requerido por `CRITERIOS_INVERSION.md`: *"Cada suma a una posición existente debe quedar registrada igual que una entrada nueva"*.

**Alternativas consideradas:**
- Permitir scale-in con `entry_price_ars == open_price_ars` (empate): rechazado — la regla habla de "reconfirmación por señal técnica"; un empate en precio no es reconfirmación. Se puede relajar en el futuro si aparece evidencia.
- Ponderar el scale-in por score independiente del headroom (dar suma tope 8% ARS sin considerar committed): rechazado — rompe el cap del 8% por ticker que la Fase 1.2 ya estableció.
- Recortar solo las señales de menor score cuando el capital falta (en vez de scale-down uniforme): rechazado — hace opaco el trade-off para el operador.
- Mantener `total_capital` como parámetro USD y convertir internamente: rechazado — introduce una conversión de ida-y-vuelta con la MEP en el path principal del sizing, aparte de contradecir la decisión ARS-nativa del 2026-08-27.

**Tests:** `tests/test_suppression.py` (33 casos, +7 nuevos cubren scale-in permitido, bloqueo por promediar a la baja, igualdad de precio, propagación de `is_scale_in` por `evaluate_suppressions`, headroom helper) y `tests/test_reversal_report.py` (15 casos nuevos: score-weighted en nuevas, scale-in recortado al headroom, scale-down proporcional, capital disponible 0/negativo, rendering de labels).

**Estado:** implementado. Referencia: reglas "Escalado de posiciones" y "No promediar a la baja" en `docs/CRITERIOS_INVERSION.md`. Roadmap: próxima fase 2.1 (sizing por riesgo).

---

## 2026-09-03 — Supresión de señales: cooldown post-stop-hit, conciencia de posición y cap acumulado del 8% por ticker

**Contexto:**
Fase 1.2 del `docs/ROADMAP_COOLDOWN_POSICIONES.md`. Tres reglas ortogonales que un chequeo por señal no cubría:

1. **Cooldown.** Análisis histórico sobre reversiones resueltas: **7 de 8 re-entradas resolubles a DECK.BA tras un stop_hit fallaron** (la 8va corresponde a la señal del 2026-08-24, cuya `entry_price_ars` cae dentro del período `price_staleness_risk` — ver memoria `project_near_miss_calibration` — y por eso no se cuenta como confirmatoria del patrón). BYMA y ADGO exhiben el mismo patrón cualitativo con muestras chicas. La quiebra no es solo temporal: el régimen bajista (`close < invalidation_level_ars` de la señal previa) es la condición material.
2. **Conciencia de posición.** Una señal en un ticker ya en cartera no debe re-ingresarse por ruido de scanner — el dedup existente (`check_recent`, `_is_exposure_duplicate`) opera a nivel señal, no a nivel exposición real.
3. **Cap del 8% acumulado por ticker.** Convención ya adoptada (ver entradas anteriores). Antes se validaba por señal individual — cuatro señales del mismo ticker podían superar el techo sumadas.

**Decisión:**

1. **Cooldown = 15 días hábiles + condición de régimen.** Nuevo módulo `analysis/reversal/suppression.py`, función `check_cooldown`. Se activa si existe un `stop_hit` para el ticker con `exit_date` (= `scan_date + days_to_outcome` calendar) dentro de los 15 días hábiles previos al nuevo `scan_date`, **Y** `entry_price_ars <= invalidation_level_ars` del stop previo. Si el precio recuperó por encima del nivel de invalidación, la señal es operable — el tiempo por sí solo no bloquea. Uso de días hábiles (`numpy.busday_count`) para no penalizar feriados/fines de semana. Cuando hay múltiples `stop_hit` recientes gobierna el más reciente (representa el régimen actual).

2. **Supresión por posición abierta.** `check_open_position` compara símbolos por forma canónica (`_normalize` de `data/reconciler.py`: strip everything from first '.'). Cualquier `Position` con `status == "open"` bloquea. Cerradas no bloquean — la memoria del stop la maneja Parte A.

3. **Cap del 8% acumulado por ticker.** `check_sizing_cap`. `committed_ars = Σ (qty × open_price_ars)` sobre posiciones abiertas del ticker. Un parámetro `additional_committed_ars` cubre otras señales `tradeable=true` del mismo scan (hoy es 0 — el scanner emite a lo sumo una señal por ticker por corrida, verificado en `scan_reversals`). Comportamiento: **reducir si hay headroom > 0, bloquear duro solo si headroom ≤ 0.** La reducción es silenciosa (no emite `suppression_reason`) porque el allocator downstream (`output/reversal_report._allocate_capital`) ya respeta la banda 5-8%. El bloqueo duro sí emite reason. **Redundancia con Parte B:** hoy Parte B ya bloquea el caso realista (posición abierta → cualquier `committed_ars` > 0 activa B antes de C). Se mantiene C como red defensiva para futuros cambios de arquitectura (salidas parciales, relajar B, etc.) y para el caso hipotético en que múltiples señales por ticker por scan sean permitidas.

4. **Nunca borrar señales suprimidas.** Se persisten en `signals.jsonl` con dos campos nuevos: `tradeable: bool` (default `true`) y `suppression_reason: Optional[str]`. Auditoría intacta. El reporte las marca con `🚫 NO OPERAR:` — nunca las oculta. Un futuro modo de ejecución automática filtraría por `tradeable=true`; hoy es semi-manual.

5. **Orden de evaluación:** cooldown → posición → sizing. Corta al primer bloqueo. La razón es prioridad semántica: si el ticker está en régimen roto, ni siquiera importa el estado de la cartera; si ya está en cartera, ni siquiera importa cuánto capital resta.

6. **`--capital-ars` sin default silencioso.** `scripts/run_reversals.py` requiere `--capital-ars` (argparse `required=True`). No existe módulo de cash-tracking automático (decisión previa: se mantiene manual). Un default silencioso rompería la validez del cap de la Parte C sin aviso — patrón fail-silent ya cazado tres veces (API credits, MEP, dedup near_misses). El script aborta si no se pasa.

**Wiring:**
- `analysis/reversal/reversal_scanner.py::scan_reversals` acepta `total_capital_ars`, `positions`, `outcomes` inyectables (dependency-injected para tests, con carga por defecto vía `positions_log.load_positions` y `outcome_tracker._load_outcomes` cuando no se inyectan).
- `analysis/reversal/signal_registry.py::record_signals` escribe `tradeable` y `suppression_reason` en cada registro. Usa `getattr(..., default)` para retro-compatibilidad con stubs de tests que no traen los campos.
- `output/reversal_report.py` prefija `🚫 NO OPERAR: ` en el heading de la oportunidad, agrega una línea de aviso con el motivo, y marca la fila de la tabla de asignación con `🚫`.

**Alternativas consideradas:**
- Filtrar señales suprimidas del `signals.jsonl`: rechazado — se perdería el rastro de auditoría necesario para calibrar cooldown en el futuro y para responder "¿por qué esa señal no apareció?".
- Cooldown en días calendario: rechazado — 15 calendario ≈ 11 hábiles, y la evidencia se levantó en días hábiles (velas diarias de BYMA).
- Cap del 8% como reducción hard en sizing (no bloqueo): rechazado — cuando headroom = 0, un tamaño 0 es equivalente a un bloqueo, y bloquear explícitamente comunica mejor la razón al operador.
- Persistir el `adjusted_allocation_ars` en el registro: rechazado por ahora — el allocator downstream ya respeta el cap, y agregar un campo derivado que puede quedar desincronizado con el capital cambiante no aporta.

**Tests:** `tests/test_suppression.py` — 26 casos, cubre para cada Parte (A/B/C) todos los caminos: bloqueo válido, cases en que no debe bloquear, matching canónico `.BA`, boundary del window de 15 hábiles, cortocircuito del orquestrador, `total_capital_ars=None` sin desactivar A/B. Estilo de inyección de dependencias — sin file I/O.

**Estado:** implementado. Fase 1.2 completa; próximo paso del roadmap es 2.1 (sizing por riesgo, alto cuidado — requiere simulación previa).

---

## 2026-08-27 — PnL neto de comisiones + conversión FX vía MEP

**Contexto:**
El reporte de performance calculaba el PnL bruto (sin descontar comisiones de Cocos Capital) y usaba el tipo de cambio CCL para convertir a USD. Ambos puntos eran incorrectos para reflejar el resultado real del inversor: las comisiones tienen impacto material (~0.555% por punta) y el instrumento utilizado para la conversión es MEP (no CCL).

**Decisión:**

1. **Comisiones integradas al PnL.** `compute_realized_pnl` descuenta ambas puntas (compra + venta) a la tasa constante `COMMISSION_RATE = 0.00555`. `compute_floating_pnl` descuenta solo la punta de venta prospectiva — la compra es un costo hundido ya pagado al abrir la posición. El `pnl_pct` reportado es siempre neto de comisiones (número real). El `pnl_ars` bruto se expone como `gross_pnl_ars` en el dict de retorno para que nunca desaparezca del contexto; el reporte agrega la columna "Comisiones ARS" para visibilidad explícita.

2. **CCL → MEP para conversión a USD en el reporte de performance.** `performance_report.py` usa `fetch_mep` en lugar de `fetch_ccl`. La tasa MEP es la que efectivamente usa el inversor para medir retornos en dólares en el contexto de CEDEARs comprados en pesos. El cálculo del premium de CEDEAR (diferencia precio local vs ADR ajustado por FX) sigue usando CCL donde corresponda — el reporte de performance no toca ese cálculo.

**Alternativas consideradas:**
- Almacenar comisiones absolutas en el `Position` datalog: descartado por complejidad innecesaria — la tasa es constante para Cocos y puede recalcularse.
- Mostrar PnL bruto como columna principal: descartado — el número visible debe ser el real.
- Usar MEP spot siempre (sin serie histórica): descartado — para posiciones cerradas en fechas pasadas se necesita el MEP de esa fecha.

**Estado:** Implementado. Tasa de comisión: 0.555% por punta (validada contra ejemplo real AMD: 50 acc., open 75.288, close 77.725 → bruto +121.850 ARS, comisión ~42.461 ARS, neto ~79.389 ARS).

---

## 2026-08-13 — Auditoría de exclusiones: 31 desincronizados, 7 mapeos corregidos

**Contexto:**
Al investigar `UN.BA` generando "possibly delisted" en el scanner se descubrió un patrón más amplio: 31 tickers con `symbol_underlying` en `excluded_underlyings` cuyo `.BA` correspondiente NO estaba en `excluded_ars`. La sospecha inicial era un bug estructural en `refresh_exclusions.py` (propagación unilateral de exclusiones). Se realizó un dry-run de probe sobre los 31 para verificar antes de excluir.

**Hallazgo principal: el script NO tenía el bug sospechado.**

`excluded_ars` y `excluded_underlyings` son listas INTENCIONALMENTE independientes:
- `excluded_ars`: el ticker `.BA` no retorna datos de precio en Yahoo Finance.
- `excluded_underlyings`: el underlying no tiene `fast_info.last_price` en Yahoo Finance (falla el fetch de fundamentals).

Un ticker puede tener precios `.BA` usables en BYMA pero underlying sin `fast_info` (todos los B3, muchos OTC). El probe de los 31 confirmó que 30 de ellos tienen 2-3 barras de precio en Yahoo Finance → correctamente NO excluidos de precio. El único genuinamente roto era `UN.BA` (0 barras).

**Clasificación de los 31:**

- **15 B3** (ABEV3, BBAS3, BBDC3, BPA11, CSNA3, HAPV3, ITUB3, LREN3, MGLU3, PETR3, PRIO3, TIMS3, VALE3, VIVT3, WEGE3): precios `.BA` operables en Yahoo Finance. Underlying excluido porque Yahoo requiere sufijo `.SA` para B3, no el código desnudo. El pipeline los evalúa correctamente para precios, sin fundamentals. **Sin cambios.**

- **7 NYSE/NASDAQ con ticker mal mapeado** (BNG→BG, BRKB→BRK-B, NOKA→NOK, PKS→PKX, TRVV→TRV, TXR→TX, XROX→XRX): el PDF de BYMA usa códigos distintos a los tickers de Yahoo Finance. El underlying del código correcto sí tiene `fast_info`. **Acciones:** se corrigió `symbol_underlying` en `universe_snapshot.json` y se removieron los códigos incorrectos de `excluded_underlyings`.

- **8 "dead candidates"** (ADGO, AOCA, BBV, DISN, HNPIY, KOFM, ORAN, WBO): BYMA los sigue cotizando como CEDEARs con precio local (3 barras en Yahoo). El ADR original puede estar cerrado pero el CEDEAR sigue siendo un instrumento válido en el mercado local. **Sin cambios.**

- **1 genuinamente roto** (UN.BA — Unilever Dutch entity, delisted NYSE 2022): 0 barras. **Acción:** agregado a `excluded_ars` con reason `delisted_adr`.

**Deuda técnica pendiente:**
`refresh_universe.py` regenera `universe_snapshot.json` desde el PDF de BYMA, que usa los códigos BYMA como `symbol_underlying` para mercados US. Al regenerar, los 7 mapeos corregidos se revierten sin aviso. Se agregó un warning explícito en el docstring de `refresh_universe.py`. La fix permanente es un override YAML (`data/sources/yfinance_ticker_overrides.yaml`) que se aplique post-generación en `refresh_universe.py`. Implementar antes del próximo refresh del universo.

**Estado:** 1 ticker excluido (UN.BA), 7 mapeos corregidos en snapshot, warning en script, deuda técnica documentada.

---

## 2026-08-13 — Exclusión de 7 tickers ARS con fallas recurrentes + 1 underlying

**Contexto:**
Tres patrones acumulados durante semanas de monitoreo justificaron pasar de logging pasivo a exclusión activa:

1. **BK.BA, MBT.BA, SNP.BA, TTM.BA** aparecían como "possibly delisted" en cada corrida — 3 reintentos live por ticker por semana sin cache válida. Sus underlyings `MBT`, `SNP`, `TTM` ya estaban en `excluded_underlyings` desde 2026-06-29, pero los tickers `.BA` no estaban en `excluded_ars` → el fetcher de precios los seguía intentando.

2. **RENT3.BA, SBSP3.BA, SUZB3.BA** generaban un 404 rotativo (un ticker distinto cada semana) de B3. El patrón "rotativo" era cache aging: el ticker cuyo cache había vencido esa semana generaba el 404 live; los otros dos eran servidos desde cache. Sus underlyings ya estaban correctamente excluidos de fundamentals.

3. **BK** (BNY Mellon) no estaba en `excluded_underlyings` — era el único CEDEAR de los afectados con ambos fetches (ARS y underlying) activos.

**Decisión:**
Se agregan a `excluded_ars`: `BK.BA`, `MBT.BA`, `SNP.BA`, `TTM.BA`, `RENT3.BA`, `SBSP3.BA`, `SUZB3.BA`.
Se agrega a `excluded_underlyings`: `BK`.

Las razones se diferencian en el JSON para preservar trazabilidad futura:
- `delisted_adr`: MBT (NYSE: mayo 2022, sanciones), SNP (NYSE: octubre 2023, retiro voluntario ADR). No recuperables desde esta fuente.
- `no_ba_yfinance`: BK, TTM. Underlyings vigentes en NYSE; Yahoo Finance no sirve su ticker `.BA` de BYMA. Reevaluar si cambia fuente de precios.
- `b3_cedear_intermittent`: RENT3, SBSP3, SUZB3. Stocks B3 vivos; el ticker `.BA` en Yahoo es intermitente y genera 404 al expirar cache. Underlying correctamente excluido de fundamentals desde 2026-06-29.

**Efecto operativo:** pool activo pasa de ~391 a ~384 tickers. Estos 7 no serán evaluados por filter1 ni el scanner de reversiones.

**Alternativas consideradas:**
- Mantener en el pool y aceptar el ruido en logs: rechazado — 3 reintentos por ticker por corrida sin beneficio informacional.
- Excluir solo del logging sin excluir del fetch: no existe ese mecanismo; `excluded_ars` es el único punto de corte limpio.

**Estado:** implementado. Tests: 40/40 passed.

---

## 2026-08-13 — Agregar MEP como serie de FX paralela a CCL

**Contexto:**
Se detectó que las verificaciones de precio del día a día y la conversión de PnL requieren MEP
(dólar bolsa), no CCL (contado con liqui). Son tipos de cambio distintos con una brecha real y
usos económicos diferentes: se observó una diferencia de ~4% el 2026-08-11 (MEP ~1.523, CCL ~1.580).

- **CCL** es el tipo de cambio del mecanismo real de arbitraje entre CEDEARs y sus subyacentes
  en el exterior: se compra el subyacente afuera y se trae a través del CEDEAR local. El cálculo
  de premium/descuento de CEDEARs debe usar CCL.
- **MEP** es el tipo de cambio operativo para compra/venta de acciones y bonos en el mercado
  local sin restricciones. Es el tipo que se usa en la operatoria diaria de Cocos Capital y el
  relevante para verificar precios y convertir PnL de ARS a USD.

**Decisión:**
Se agrega `MepSeries` como serie paralela en el pipeline, sin modificar el uso existente de CCL
en `argentina_adjustment.py` (cálculo de premium/descuento de CEDEARs). Ambas series viajan
en cada `TickerBundle` — misma arquitectura, mismo patrón de cache, mismo comportamiento de
fallback. El cálculo de premium/descuento sigue usando CCL exclusivamente.

**Alternativas consideradas:**
- Reemplazar CCL por MEP en todos lados: rechazado — rompería la lógica de premium/descuento,
  que es estructuralmente un arbitraje de contado con liqui.
- Usar un único spot promedio entre ambos: rechazado — pierde precisión en los dos usos y mezcla
  tipos de cambio con significados económicos distintos.
- Solo exponer el spot de MEP sin serie histórica: rechazado — la consistencia con CCL (serie
  completa + spot + cache) tiene costo marginal bajo y facilita análisis futuros.

**Estado:** implementado.
