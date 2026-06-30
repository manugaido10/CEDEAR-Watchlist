# Decisions Log — CEDEAR Watchlist (Cocos Capital)

> Cada vez que se toma o se cambia una decisión importante del proyecto (criterio, arquitectura, alcance), se agrega una entrada acá. No se borran entradas viejas aunque queden obsoletas — se marca como superada y se referencia la nueva. Esto es lo que evita perder de vista cómo y por qué cambiaron las cosas a lo largo del proyecto.

## Formato de cada entrada

```
### [Fecha] — [Título corto de la decisión]
**Contexto:** por qué surgió esta decisión / qué problema resuelve
**Decisión:** qué se decidió, concretamente
**Alternativas consideradas:** (si aplica)
**Estado:** Activa / Superada por [link a entrada nueva]
```

---
### 2026-06-19 — Definición inicial de criterios de inversión
**Contexto:** Arranque del proyecto. Necesitábamos definir el perfil de análisis antes de construir cualquier cosa.
**Decisión:** Sistema técnico/momentum-driven, fundamentals como filtro de calidad (no como señal), horizonte mediano plazo táctico, riesgo Argentina como ajuste secundario no bloqueante, stop técnico (no % fijo) como criterio de invalidación, cadencia semanal + alertas puntuales por ruptura de nivel.
**Alternativas consideradas:** Enfoque fundamentals-first (descartado, no es el estilo del usuario); enfoque equilibrado 33/33/33 (descartado, se prefirió un driver claro en vez de promediar señales).
**Estado:** Activa — ver `CRITERIOS_INVERSION.md` para el detalle completo.

---
### 2026-06-20 — Estructura de dos filtros + distinción CEDEAR exterior vs. acción argentina
**Contexto:** El primer borrador de criterios trataba "fundamental → técnico" como única secuencia y no distinguía entre CEDEARs (empresas del exterior) y acciones argentinas directas. El usuario aclaró que va a operar ambos tipos de activos, que el riesgo Argentina no aplica igual a los dos, y que quiere un proceso de dos pasos: un barrido rápido sobre todo el universo para descartar lo claramente malo, y un análisis profundo (múltiples técnicas) solo sobre los sobrevivientes.
**Decisión:**
- Se reemplaza la secuencia original por **Filtro 1 (rápido, todo el universo) → Filtro 2 (profundo, solo sobrevivientes)**.
- Filtro 1: calibración moderada (descarta solo lo claramente malo). Para acciones argentinas directas, el filtro rápido suma criterios adicionales de riesgo macro/regulatorio, dado que ahí el riesgo país afecta el negocio en sí, no solo el envoltorio.
- Filtro 2: combina técnico avanzado + fundamentals (filtro de calidad) + sentimiento/noticias (rol de **desempate**, no señal con peso propio) + ajuste de riesgo Argentina (modificador final, distinto para CEDEAR vs. acción argentina).
- Se mantiene: riesgo Argentina nunca es descarte automático, solo ajuste de score. Stop técnico (no % fijo) como criterio de invalidación.
**Alternativas consideradas:** Mismo filtro rápido para CEDEARs y argentinas sin diferenciar (descartado, el usuario pidió explícitamente mayor exigencia para argentinas dado el riesgo país adicional); sentimiento/noticias con peso propio en el score (descartado, el usuario lo definió como desempate, no como técnica de igual jerarquía).
**Estado:** Activa — supera la versión inicial del 2026-06-19. Ver `CRITERIOS_INVERSION.md`.

---
### 2026-06-20 (b) — Gestión de capital, sizing por score, y desempate condicional
**Contexto:** Faltaba definir cuánto invertir por posición y cómo se distribuye el capital disponible (USD 10.000). También se ajustó el rol del research de sentimiento/noticias para optimizar tokens y tiempo.
**Decisión:**
- **Sizing:** sin tope rígido por posición. El peso de capital se pondera por el score relativo del Filtro 2 — mayor convicción analítica, mayor capital sugerido, pero siempre trazable al análisis, no a una corazonada sin respaldo. El sistema debe proponer una distribución de capital justificada, la decisión final es del usuario.
- **Cantidad de posiciones objetivo:** 5 a 10 simultáneas.
- **Reserva de cash:** variable según cantidad de posiciones activas (mayor reserva si hay ~5 posiciones, menor si hay ~10).
- **Escalado:** permitido sumar a posiciones ganadoras si la señal técnica se reconfirma (similar al esquema de tramos del portfolio cripto). Prohibido promediar a la baja — si se rompe el nivel de invalidación, la posición se cierra, no se refuerza.
- **Desempate por sentimiento/noticias (Filtro 2, técnica 3):** se simplifica para que **solo se ejecute cuando técnico y fundamental no coinciden**. Si ya coinciden, se omite el research web en ese paso — ahorro intencional de tokens/tiempo, ya no es chequeo obligatorio en todos los casos.
**Alternativas consideradas:** Tope máximo fijo por posición, ej. 25-30% (descartado, el usuario prefirió ponderación libre por convicción, aunque se la ató al score para que no sea arbitraria); research de sentimiento siempre obligatorio como chequeo de riesgo aunque no hubiera desempate (descartado por costo de tokens/tiempo innecesario).
**Estado:** Activa. Ver `CRITERIOS_INVERSION.md`, secciones "Gestión de capital y tamaño de posición" y Filtro 2 técnica 3.

---
### 2026-06-20 (c) — Moneda de análisis técnico vs. moneda de medición de performance
**Contexto:** Durante la investigación de fuentes de datos (TASK_001) surgió la duda de si el
análisis técnico y el registro de posiciones deberían correr sobre el segmento en pesos (ej.
`GGAL.BA`) o sobre el segmento de liquidación en dólar MEP (ej. `GGALD.BA`), dado que el
usuario prefiere medir ganancias/pérdidas en dólares para evitar la distorsión de la inflación
en pesos.
**Decisión:**
- El **análisis técnico** (Filtro 1 y Filtro 2: estructura de tendencia, rupturas, medias
  móviles, RSI, fuerza relativa, niveles de invalidación) corre siempre sobre el **segmento en
  pesos**, que es el de mayor liquidez confirmada en Cocos Capital. El segmento dólar MEP (`D`)
  tiene menor liquidez, lo que lo vuelve menos confiable para generar señales técnicas.
- La **medición de performance/PnL de las posiciones** se hace en dólares, convirtiendo el
  precio en pesos a USD con el tipo de cambio CCL del día (fuente: `dolarapi.com`), tanto en
  la entrada como en el estado actual de cada posición.
- El **nivel de invalidación técnica** de cada posición se define y reporta en pesos (es donde
  existe el nivel real de soporte/resistencia), con el equivalente en USD mostrado solo como
  referencia informativa.
- Ambos segmentos (pesos y `D`) representan el mismo activo con el mismo precio económico —el
  segmento `D` no ofrece protección cambiaria adicional, dado que el precio en pesos ya
  incorpora el tipo de cambio implícito (cercano al MEP). Por eso no hay ganancia de
  "dolarización" eligiendo operar en `D`, solo el costo de menor liquidez.
**Alternativas consideradas:** Analizar y operar directamente sobre el segmento dólar MEP
(`D.BA`) (descartado — menor liquidez confirmada por el usuario, y el ruido cambiario de saltos
discretos en el CCL puede generar señales técnicas falsas que no reflejan movimiento real del
activo).
**Estado:** Activa. Ver `DATA_SOURCES.md` para el detalle de fuentes (precios en ARS vía
yfinance/BYMA Open Data, CCL vía dolarapi.com).

---
### 2026-06-21 — Operacionalización del Filtro 1 (traducción de criterios a código)
**Contexto:** Al diseñar el módulo `analysis/filter1_quick_sweep` surgió que varios criterios de descarte de `CRITERIOS_INVERSION.md` (Filtro 1) no se pueden evaluar con los datos que hoy entrega la capa de datos, y que otros no tienen umbrales cuantificados. Había que decidir cómo bajar cada criterio a lógica concreta sin apartarse del espíritu del documento, especialmente la calibración moderada ("ante la duda, pasa") y la mayor exigencia para acciones argentinas.
**Decisión:**
- **C3 (profit warning / guidance negativo):** no se evalúa en el Filtro 1 — requiere noticias, y correr research sobre todo el universo semanalmente contradice el propósito "rápido y barato" del Filtro 1. Se delega al Filtro 2. (Pendiente para el diseño del Filtro 2: definir si el chequeo de noticias duras debe ser incondicional, dado que hoy el research de noticias del Filtro 2 es solo desempate condicional.)
- **A1 / A2 (riesgo regulatorio/tarifario y dependencia macro de argentinas):** se resuelven con una lista manual versionada (`analysis/argentina_risk_flags.yaml`), no con automatización ni con proxy técnico. Son características estructurales y estables de un universo argentino acotado; el mantenimiento manual es bajo y ataca el criterio directamente.
- **Mayor exigencia para argentinas (camino B):** la exigencia adicional proviene de los gates extra A1/A2, NO de umbrales técnicos más estrictos. El motor técnico se mantiene simétrico entre CEDEARs y argentinas, preservando un driver técnico consistente y comparable entre tipos de activo.
- **Calibración moderada en código:** cada chequeo es de descarte explícito (un ticker pasa si no dispara ningún descarte, no si "aprueba" tests). Dato faltante = no dispara descarte. Chequeos compuestos en conjunción (no disyunción) para minimizar falsos descartes. Umbrales tirados hacia el extremo "claramente malo".
- **Umbrales C1/C2/C4/C5:** no se fijan a ciegas. Viven como constantes nombradas y centralizadas, traceables al criterio, marcadas como calibración pendiente. La primera corrida sobre el universo real se trata como calibración, no como señal operativa. Ajustar un umbral luego es táctico y no requiere nueva entrada acá; sí la requiere un cambio de la lógica del chequeo.
- **C5 (tendencia de fondo negativa):** definición operativa = precio < MA200 + pendiente de MA200 negativa + ruptura sostenida de soporte mayor (6m), las tres en conjunción. La ruptura debe ser sostenida (no un solo día), para capturar el "de forma sostenida, no una corrección normal" del criterio.
- **Tres categorías de output:** `survivor`, `discarded`, `unevaluable`. Un ticker sin datos suficientes (status missing/error, o datos insuficientes para los chequeos) es `unevaluable`, no `discarded` — son epistémicamente distintos ("no se pudo evaluar" ≠ "se evaluó y falló"). El Filtro 2 no recibe los `unevaluable`; el reporte los muestra aparte.
- **Proxy de liquidez (C4):** se usa el volumen de yfinance/BYMA como proxy de la liquidez "en Cocos" que pide el criterio. Limitación conocida: captura el volumen total de BYMA, no la magnitud específica en Cocos (la pertenencia a Cocos ya está garantizada por el universo). Aceptable para un filtro de descarte moderado.
**Alternativas consideradas:** Sumar una fuente de noticias/clasificación al fetcher para cubrir C3/A1/A2 (descartado — encarece el Filtro 1 y rompe la lógica de dos filtros); endurecer umbrales técnicos solo para argentinas (camino A, descartado — inventa un mecanismo que el documento no describe y ensucia el motor técnico con asimetría por tipo de activo); contar missing/error como `discarded` (descartado — afirma falsamente que un ticker fue evaluado y rechazado, y podría descartar silenciosamente buenos tickers por fallas transitorias de fetch); fijar umbrales numéricos de entrada sin ver el universo real (descartado — riesgo de descartar de más o de menos sin base empírica).
**Estado:** Activa. Ver `CRITERIOS_INVERSION.md` sección "FILTRO 1" y el módulo `analysis/filter1_quick_sweep`.

---
### 2026-06-21 (b) — Fuente del universo de CEDEARs: BYMA PDF en vez de CVSA Excel; pyCocos diferido
**Contexto:** Al construir el universo real para calibrar el Filtro 1, se descubrió que el Excel de CVSA descargado (`Tablas_CVSA_2026-06-01.xlsx`) es solo el lote de actualizaciones del mes (~59 entradas), no el universo completo de CEDEARs — contradiciendo el supuesto original de DATA_SOURCES.md de usarlo como fuente principal. El listado oficial completo (~424 filas brutas, 370 CEDEARs netos tras excluir ETFs) está en el PDF de BYMA "CEDEARs Negociables en BYMA con Ratios de Conversión". Además, se evaluó si valía la pena habilitar pyCocos (requiere re-enrolar 2FA, ya que la semilla TOTP original no fue guardada al configurar Google Authenticator).
**Decisión:**
- **Fuente del universo de CEDEARs: el PDF de BYMA**, no el Excel de CVSA. El Excel de CVSA se mantiene como oráculo de validación cruzada para el subset que cubre (ratios, ISIN, ticker de mercado de origen), no como fuente primaria.
- **pyCocos queda diferido**, no descartado. El PDF de BYMA es la fuente oficial de CEDEARs operables en el mercado argentino en general; la diferencia entre eso y lo que Cocos específicamente habilita se considera inmaterial para calibrar umbrales del Filtro 1. Re-evaluar si en producción hace falta el universo exacto de Cocos.
- **Se excluyen los CEDEARs de ETF del universo** (no son operables en Cocos según el usuario), usando como proxy: flag de CVSA Tabla N°1 + heurística de nombre + una lista override chica para casos sin marcador claro (ej. USO). Este proxy queda documentado en el código como aproximación, no como lista verificada de Cocos — no hay fuente confirmada de qué excluye Cocos específicamente.
- **Universo final: 391 tickers — 370 CEDEARs + 21 acciones argentinas** (lista curada a mano en `data/sources/argentine_stocks.yaml`, editable).
- Se preserva la dirección del ratio (`cedears_per_underlying`) y los listados duales (ABEV/ABEV3, ITUB/ITUB3, VALE/VALE3, etc.) como entradas separadas.
**Alternativas consideradas:** Re-enrolar el 2FA de Cocos para usar pyCocos desde el arranque (descartado por ahora — fricción alta para un beneficio marginal en la etapa de calibración; no descarta usarlo más adelante); incluir todos los CEDEARs del PDF sin excluir ETFs (descartado — el usuario confirmó que Cocos no los ofrece, aunque no hay lista verificada que lo confirme dato a dato).
**Estado:** Activa. Ver `data/sources/`, `scripts/refresh_universe.py` y `DATA_SOURCES.md` (actualizar).

*(Las próximas entradas se agregan acá, más recientes abajo.)*

---
### 2026-06-24 — Calibración del Filtro 1: umbrales definitivos y tratamiento de sectores especiales

**Contexto:** Primera corrida del Filtro 1 sobre el universo real (391 tickers). Se calibraron los umbrales que habían quedado marcados como "CALIBRACIÓN PENDIENTE" y surgieron dos casos de borde que requerían decisión de criterio: empresas financieras evaluadas con FCF (métrica inaplicable a su modelo de negocio) y empresas cíclicas con caída de EPS por ciclo de commodities.

**Decisión:**
- **C4 liquidez:** umbral fijado en 1.000.000 ARS de volumen mediano diario (últimos 20 días). Representa el piso real de operabilidad para el tamaño de capital del sistema (~USD 10.000). 29 tickers descartados.
- **C5 consecutivos bajo soporte:** umbral bajado de 10 a 5 cierres consecutivos. La distribución real mostró p90=1 para CEDEARs, por lo que 10 era demasiado permisivo. Corregido además un bug: se agrega condición de que el *último* cierre esté bajo soporte antes de contar consecutivos (evita falso positivo en tickers que están saliendo de una ruptura). 6 tickers descartados.
- **C2 YoY EPS:** umbral subido de -30% a -40% para mayor robustez ante empresas cíclicas con swings anuales normales de earnings. 3 tickers descartados (BIDU, UBER, XOM).
- **C1 rama B (FCF ≤ 0 y ND > 0):** umbral mantenido en 5.000M USD sin ajuste para casos específicos.
- **Empresas financieras y C1:** bancos y empresas financieras con FCF negativo estructural (C, WFC, JPM, GS) se marcan como `unevaluable` con advertencia "C1 not applicable: banking/financial business model (FCF metric invalid for this sector)", no como `discarded`. Fundamento: C1 no tiene los datos adecuados para evaluarlos (el FCF no refleja solvencia en el modelo bancario), y "no se puede evaluar correctamente" es epistémicamente distinto de "está claramente mal". Lista inicial hardcodeada: C.BA, WFC.BA, JPM.BA, GS.BA. No es una excepción por nombre o sector — es reconocer que la métrica del criterio no aplica.
- **Empresas cíclicas y C2:** no se crean excepciones de sector. XOM descartado por C2 aunque la caída de EPS sea por ciclo de commodities — el Filtro 2 puede recuperarlo si el técnico lo justifica. Se registra como mejora futura evaluar agregar una condición de "caída en al menos N de los 5 trimestres" para hacer C2 más robusto a ciclos, pero eso requiere cambio de lógica (sesión de diseño aparte).

**Resultado del Filtro 1 calibrado sobre universo real:**
- 391 tickers totales (370 CEDEARs + 21 acciones argentinas)
- 297 survivors → pasan al Filtro 2
- 39 discarded → descartados con criterio registrado
- 55 unevaluable → sin datos suficientes o métrica inaplicable (incluye 51 delisted/sin datos en yfinance + 4 financieros)

**Alternativas consideradas:** Crear excepción de sector para financieros en C1 (descartado — genera ambigüedad sobre qué entra en "financiero" y puede ser incorrecta en otro contexto de mercado); subir umbral abs_nd de C1 a 50.000M para no descartar AMZN (descartado — ajuste ad-hoc para un ticker específico, contradice el criterio de robustez); crear excepción de sector para empresas cíclicas en C2 (descartado — misma razón).

**Estado:** Activa. Ver `analysis/filter1_thresholds.py` y `analysis/filter1_quick_sweep.py`.

---
### 2026-06-24 (b) — Chequeo de noticias duras en Filtro 2: híbrido incondicional + desempate condicional
**Contexto:** Al diseñar el Filtro 2, se detectó un agujero en el criterio existente: C3 (profit warning) había sido delegado al Filtro 2 con la nota "el chequeo de noticias duras debe ser incondicional" (DECISIONS.md 2026-06-21), pero el Filtro 2 define el web research como desempate condicional únicamente. Esto significa que un ticker con técnico fuerte + fundamental confirmado + profit warning reciente pasaría al ranking sin ningún chequeo de noticias.
**Decisión:**
- **Opción elegida: híbrido en dos etapas (γ).** Un chequeo liviano de hard-news corre sobre TODOS los survivors del Filtro 1 (297 tickers), buscando únicamente señales duras: profit warning, guidance cut, downgrade material, investigación regulatoria, fraude, quiebra. Si el chequeo liviano no dispara nada → flujo normal (desempate condicional solo si técnico y fundamental divergen). Si dispara → escalación al desempate completo (técnica 3).
- **Argentinas con fundamentals = None:** van a desempate completo directo (no solo chequeo liviano), con búsqueda enfocada en noticias macro/regulatorias. Es coherente con la mayor exigencia para argentinas ya establecida.
- **Activación del desempate completo (técnica 3):** se activa cuando (a) el chequeo liviano dispara algo, (b) técnico y fundamental divergen explícitamente, o (c) fundamental = unknown + trend_regime = strong_up (o cualquier tendencia alcista para argentinas).
- **Fundamentals = None (CEDEARs sin cobertura FMP):** tratar como neutral en la activación del desempate — solo activa desempate completo si technical = strong_up. No se equipara a confirmed (demasiado permisivo) ni a neutral siempre (demasiado caro).
- **Gap de fundamentals para argentinas:** se acepta. CNV como fuente de balances queda diferida (ya registrado en DATA_SOURCES.md). La compensación es el desempate completo automático para argentinas.
- **Sub-score momentum_macd_adx:** eliminado del diseño. 5 puntos sobre 100 es ruido estadístico que no mueve rankings en la práctica, y agrega complejidad de implementación sin beneficio real.
**Alternativas consideradas:** Chequeo de noticias duras solo como desempate condicional (descartado — deja agujero conocido para tickers con técnico fuerte + profit warning); chequeo incondicional completo sobre los 297 (descartado — ~297 web searches/ciclo, costo desproporcionado); tratar fundamentals=None como confirmed (descartado — demasiado permisivo para tickers con alta convicción técnica y cero info fundamental).
**Estado:** Activa. Ver `analysis/filter2_deep_dive/` y `docs/CRITERIOS_INVERSION.md` sección "FILTRO 2".

---
### 2026-06-24 (c) — Eliminación de liquidity_penalty del ajuste Argentina (Filtro 2)
**Contexto:** La primera corrida de diagnóstico del Filtro 2 sobre los 297 survivors mostró que el componente `liquidity_penalty` del ajuste Argentina aplicaba penalidad máxima (5 pts) al 82% de los CEDEARs con subyacente fetcheable. La causa es estructural: la métrica compara el volumen del CEDEAR en BYMA (ARS) contra el volumen del subyacente en NYSE/NASDAQ (USD) — mercados incomparables en escala. AAPL.BA, el CEDEAR más líquido del mercado argentino con ~USD 1.1M de volumen mediano diario, tiene un ratio de 0.00074% respecto al volumen de AAPL en NYSE, 140x por debajo del umbral mínimo de 0.1%. Para los 37 CEDEARs cuyo subyacente no se puede fetchear en yfinance (brazileras, exóticos), el fallback era 0 — tampoco correcto.
**Decisión:** Eliminar `liquidity_penalty` del cálculo del ajuste Argentina en el Filtro 2. El Filtro 1 (C4, umbral 1M ARS/día de volumen mediano) ya descartó los CEDEARs genuinamente ilíquidos para el tamaño de capital del sistema. La penalidad de liquidez en Filtro 2 no agregaba información útil — solo ruido sistemático que penalizaba a todos los CEDEARs operables en Cocos por igual. La función `_liquidity_penalty` queda en el código comentada para uso futuro si se dispone de una fuente de datos de liquidez específica de Cocos (ej. pyCocos con profundidad de libro real).
**Alternativas consideradas:** Recalibrar los umbrales de liquidez para comparar contra la liquidez típica del mercado argentino en vez de contra el subyacente global (descartado — requeriría una fuente de datos de "mercado argentino típico" que no existe en la arquitectura actual); mantener la métrica solo para CEDEARs muy líquidos del exterior (descartado — la asimetría de escala es inherente a cualquier comparación BYMA vs. NYSE/NASDAQ).
**Estado:** Activa. Ver `analysis/filter2_deep_dive/argentina_adjustment.py` y `filter2_thresholds.py`.

### 2026-06-28 — Migración de fundamentals: FMP → yfinance (CEDEARs) y aceptación de gap para argentinas

**Contexto:** El free tier de FMP resultó incompatible con el universo real del proyecto. De los 332 CEDEARs elegibles para fundamentals, solo ~35 tienen cobertura en el plan gratuito — el resto devuelve HTTP 402 "Special Endpoint / plan restriction". El plan pago de FMP (~USD 49/mes) no se justifica en la etapa actual. Se investigaron fuentes alternativas para ambos tipos de activo.

**Decisión:**
- **CEDEARs — migrar a yfinance:** `fetch_fundamentals` se reimplementa usando `yfinance` (`ticker.quarterly_income_stmt`, `ticker.quarterly_cashflow`, `ticker.quarterly_balance_sheet`). Cobertura amplia para NYSE/NASDAQ sin API key ni límites de plan. Retorna máximo 5 trimestres — consistente con C2_MIN_EPS_PERIODS = 5 ya ajustado. TTL de caché de 90 días se mantiene. Los tres endpoints FMP (`/stable/income-statement`, `/stable/cash-flow-statement`, `/stable/balance-sheet-statement`) quedan eliminados.
- **Acciones argentinas — gap aceptado definitivamente:** No existe fuente gratuita con API programática para estados financieros de empresas BYMA. IOL tiene API documentada pero solo cubre cotizaciones y operaciones, no balances. BYMADATA tiene balances en su portal pero sin API. La CNV tiene los datos como XBRL/PDF sin API — complejidad alta, diferida en `DATA_SOURCES.md` desde el inicio. Se acepta `fundamental_state = unknown` para argentinas como limitación estructural, no como deuda técnica temporal. La compensación ya implementada (news gate completo automático para argentinas con unknown + tendencia alcista) cubre el riesgo.
- **FMP queda eliminado del pipeline activo.** Las constantes de FMP en `data/fundamentals.py` y los thresholds relacionados quedan comentados o removidos. La API key `FMP_API_KEY` del `.env` puede eliminarse.
- **`DATA_SOURCES.md`:** actualizar la sección de fundamentals para reflejar yfinance como fuente primaria y el gap argentino como definitivo.

**Alternativas consideradas:** Plan pago FMP (descartado — costo desproporcionado en etapa de desarrollo); EODHD fundamentals feed (descartado — USD 59.99/mes, mismo problema de costo); IOL para fundamentals argentinas (descartado — su API no expone estados financieros, solo cotizaciones); CNV XBRL parsing (diferido desde el inicio, no ha cambiado la evaluación de complejidad alta vs. beneficio marginal para 21 tickers).

**Estado:** Activa. Ver `data/fundamentals.py` y `DATA_SOURCES.md`.

---

## 11 — 2026-06-29: Módulo de Reversión Táctica

**Contexto:** El pipeline de momentum (Filtro 1 + Filtro 2) produce
correctamente tickers en tendencia alcista establecida. Se identificó
la necesidad de una segunda funcionalidad complementaria para capturar
oportunidades de reversión: acciones "baratas" (sobrevendidas o con
cambio de tendencia emergente) con horizonte de 2-3 semanas.

**Decisión:** Agregar un módulo de reversión táctica que corre
independiente del pipeline principal. No reemplaza ni modifica el
sistema de momentum — agrega una segunda salida paralela.

**Criterios de entrada (todos deben cumplirse):**
1. Tendencia semanal positiva o neutral (weekly_strength ≥ 8, o MA50
   semanal con slope no claramente negativo). Protege de atrapar
   cuchillos en tendencias bajistas sostenidas.
2. Corrección en diario: RSI 14 entre 25-45 Y precio cerca de soporte
   relevante (MA50 diaria, MA200 diaria, o swing low previo de los
   últimos 40 barras).
3. Volumen decreciente en la caída: volumen promedio de los últimos 5
   días < 80% del volumen promedio de los últimos 20 días.
4. Catalizador de entrada — al menos uno de:
   a. Divergencia alcista en RSI diario (precio hace mínimo más bajo,
      RSI hace mínimo más alto, en los últimos 10 barras)
   b. Vela de reversión en soporte (martillo o engulfing alcista) con
      volumen > promedio 20 días
   c. Precio dentro del 2% de MA200 diaria o rebotando desde ella
5. Fundamentals no deteriorados: el ticker no tiene estado
   `deteriorating` en T2 (fundamental_quality). Si no hay datos de
   fundamentals (acciones argentinas), este criterio se omite.

**Invalidación:** quiebre del soporte que justificó la entrada con
volumen > promedio. Stop técnico, no porcentual fijo.

**Universo:** mismo universo que el pipeline principal (391 tickers:
CEDEARs + acciones argentinas). No requiere pasar Filtro 1 primero —
corre sobre el universo completo con sus propios criterios.

**Output:** reporte separado `output/reversiones_YYYY-MM-DD.md`.
Sizing: 5-8% del capital invertible por posición (vs. ~10% del
pipeline de momentum). Máximo 3-5 posiciones simultáneas — si el
módulo detecta más de 5 señales válidas en un ciclo, aplicar ranking
por score de reversión y tomar las 5 mejores.

**Score de reversión (0-100):**
- RSI position (qué tan sobrevendido): 0-25 pts
  - RSI ≤ 30: 25 pts
  - RSI 30-40: 15 pts
  - RSI 40-45: 8 pts
- Proximidad al soporte: 0-25 pts
  - Precio dentro del 1% del soporte: 25 pts
  - Precio dentro del 3%: 15 pts
  - Precio dentro del 5%: 8 pts
- Calidad del catalizador: 0-30 pts
  - Divergencia RSI: 30 pts
  - Vela de reversión en soporte con volumen: 25 pts
  - Rebote desde MA200: 20 pts
  - (se puede sumar si hay más de uno, cap 30)
- Volumen decreciente en caída: 0-20 pts
  - Vol 5d < 60% del Vol 20d: 20 pts
  - Vol 5d 60-80%: 10 pts

**Alternativas consideradas:**
- Incorporar reversión dentro del pipeline existente → descartado
  porque los criterios son opuestos al momentum y mezclarlos
  distorsionaría ambos rankings.
- Usar solo RSI < 30 como señal → descartado porque genera muchas
  falsas señales sin contexto de soporte ni catalizador.

**Archivos a crear:**
- `analysis/reversal/reversal_scanner.py` — lógica principal
- `output/reversal_report.py` — generador del reporte
- `scripts/run_reversals.py` — script de ejecución

---

## 12 — 2026-06-30: Módulo de Tracking de Posiciones

**Contexto:** El objetivo del proyecto se amplía: además de generar señales, se necesita un historial auditable de operaciones reales para documentar resultados públicamente (canal de contenido sobre trading). Sin tracking de resultados reales, no hay forma de validar si el sistema funciona antes de mostrarlo en público.

**Decisión:** Módulo enteramente manual — no hay automatismos de apertura ni cierre de posiciones. El sistema solo registra lo que el usuario confirma explícitamente.

**Almacenamiento:** `data/positions_log.json`, versionado en git.

**Comandos CLI (`scripts/log_position.py`):**
- `open --symbol --price --qty --source [momentum|reversal] --date`
- `close --symbol --price --date --reason [target|stop|manual]`
- `list --status [open|closed]`
- `report --month YYYY-MM`

**Campos por posición:**
- symbol, fecha apertura, precio entrada, cantidad
- source: momentum o reversal (track records separados)
- score del sistema al momento de la entrada (trazabilidad)
- invalidation_level_ars al momento de la entrada
- status: open | closed
- si closed: fecha cierre, precio salida, reason, resultado en ARS y USD (vía CCL del día de cierre), resultado en %

**Reporte mensual (`output/performance_YYYY-MM.md`):**
- Posiciones cerradas en el mes: resultado realizado, en ARS y USD, agregado y separado por source (momentum vs. reversal)
- Posiciones abiertas al cierre del mes: resultado flotante usando el precio de cierre del último día hábil del mes exacto (vía yfinance), marcado explícitamente como "no realizado", en ARS y USD
- % de aciertos (trades con resultado positivo / total cerrados) por source
- Comparación contra Merval en el mismo período de cada posición cerrada (rendimiento del ticker vs. rendimiento del Merval entre fecha apertura y fecha cierre)

**Benchmark:** Merval, no S&P 500. Razón: el capital base está en pesos argentinos y la pregunta relevante para el usuario y la audiencia es si el sistema le ganó a quedarse en el mercado local, no a un índice extranjero. Puede agregarse S&P 500 como referencia secundaria en una fase posterior si se desea.

**Lo que NO hace este módulo:**
- No ejecuta órdenes ni se conecta a Cocos/PyCocos
- No infiere aperturas automáticas a partir del ranking semanal
- No cierra posiciones automáticamente, ni siquiera por invalidación técnica detectada — el cierre siempre requiere confirmación manual

**Alternativas consideradas:**
- Apertura/cierre automático basado en el ranking semanal y la invalidación técnica → descartado: el usuario quiere control total sobre qué operaciones reales se registran, dado que no todas las señales del ranking se ejecutan en la práctica.
- Resultado flotante con precio "más reciente al correr el comando" → descartado en favor de precio de cierre del último día hábil del mes exacto, para que el corte mensual sea reproducible y no dependa de cuándo se corre el reporte.
- S&P 500 como benchmark principal → descartado en favor de Merval por coherencia con la moneda base del capital.

**Estado:** Activa.