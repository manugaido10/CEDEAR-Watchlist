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

**Calibración C1 — 2026-07-03:**
El criterio de tendencia semanal tenía tres problemas que permitían
clasificar como "positive" tickers en tendencia bajista estructural
(caso detectado en producción: SID.BA, -55% en 6 meses).

Fixes aplicados en commit 439ea38:
- clearly_negative usa OR en vez de AND — un solo indicador negativo
  fuerte es suficiente para descartar
- Agregada condición `significantly_below_ma50`: precio > 10% por
  debajo de la MA50 semanal descarta el ticker independientemente del
  slope (captura caídas rápidas donde la MA50 aún no refleja la magnitud)
- Ventana de weekly_strength extendida de 12 a 24 semanas (6 meses)
- Ventana de MA50 slope extendida de 5 a 8 semanas
- clearly_positive requiere TODAS las condiciones simultáneamente
  (AND) en vez de cualquiera (OR)

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

---

## 13 — 2026-07-23: Early Accumulation Module (Pre-Momentum)

**Context:** The current momentum module correctly detects tickers in
established uptrends, but detects them late — after the breakout has
already occurred and the move has been running for weeks or months.
Documented case: MMM.BA rose +25% between May and July 2026; the
system detected it only on 2026-07-23 when it was already at highs.
The pattern the system should have detected in May was: price rising
gradually and consistently (positive slope, R² > 0.60), neutral to
growing volume, no breakout or established MAs required.

**Decision:** Add a third independent module that detects tickers in
a silent accumulation phase, before momentum becomes obvious.
Complements (does not replace) the momentum module.

**Target pattern:** incipient uptrend with consistent slope, gradually
growing volume, price still far from historical highs. Does not require
volume breakout, oversold RSI, or established long-term MAs.

**Entry criteria (all must be met):**

C1 — Consistent price trend (last 6-8 weeks):
  Linear regression slope over the last 40 daily closing prices is
  positive AND R² > 0.60. Captures gradual, orderly rises without
  requiring breakouts.

C2 — Price below 85% of its 52-week high:
  Filters tickers that have already exploded and are at historical
  highs. A ticker at 95% of its annual high is no longer
  "early accumulation".

C3 — Neutral to growing volume:
  Average volume of the last 4 weeks > average volume of the prior
  4 weeks. Does not require spikes — just that interest is gradually
  growing.

C4 — Fundamentals not deteriorating:
  T2 status ≠ "deteriorating". If data is unavailable (Argentine
  stocks — known structural gap), criterion is skipped.

C5 — Not already in the current momentum ranking:
  If the ticker is already in the top 10 of the weekly watchlist,
  it is excluded — it has already been detected by the main system.

**Accumulation score (0-100):**
- Normalized trend slope: 0-35 pts
  (how strongly it is rising relative to price)
- R² consistency: 0-25 pts
  (R²=0.60 → 0 pts; R²=1.0 → 25 pts, linear scale)
- Volume growth: 0-20 pts
  (ratio vol_4w_recent / vol_4w_prior: 1.0x → 0 pts,
  2.0x or more → 20 pts, linear scale)
- Distance from 52W high: 0-20 pts
  (85% of high → 0 pts; 50% of high → 20 pts, linear scale)

**Universe:** same universe as the main pipeline — 391 tickers
(CEDEARs + Argentine stocks). For Argentine stocks, C4 is skipped
due to the known fundamentals data gap.

**Output:** output/acumulacion_YYYY-MM-DD.md
Format similar to reversiones report: score, slope, R², volume ratio,
distance to 52W high, suggested invalidation level (MA50 or nearest
swing low below current price).
Sizing: 8-10% of investable capital per position, maximum 5
simultaneous positions.

**Execution frequency:** weekly, same day as run_watchlist.py.

**Files to create:**
- analysis/accumulation/accumulation_scanner.py
- output/accumulation_report.py
- scripts/run_accumulation.py

**What this module does NOT do:**
- Does not require a volume breakout (momentum module handles that)
- Does not require oversold RSI (reversal module handles that)
- Does not require established long-term MAs
- Does not replace either of the two existing modules

**Alternatives considered:**
- Lower momentum module thresholds to detect earlier → rejected:
  would compromise main ranking quality with more false positives
- Use positive slope only without R² → rejected: would capture
  single-day spikes or noisy moves without consistency

**Calibration reference case:**
MMM.BA in May 2026: price rose from ARS 21,000 to ARS 22,700 over
40 days in an orderly fashion, vol_ratio mostly between 0.3-1.0
with gradual growth, no obvious volume breakout. That is the exact
pattern this module must detect.

**Calibration C6 — 2026-07-23:**
First production run detected tickers already 31-60% above their
60-day lows (ABT.BA, PYPL.BA, TRIP.BA) — moves already largely done,
not early accumulation. Added C6: price must be within 20% of its
60-day low. This ensures the module catches the buildup phase, not
the aftermath.

---

## 14 — 2026-07-27: Diagnóstico y corrección del news gate — fallos silenciosos, cache envenenado, y capital sizing de held_with_warning

**Contexto:** La corrida del 2026-07-27 devolvió "no response" para los 10/10 tickers evaluados en el light check, y el sistema defaulteó a `CLEAN` en todos los casos. El tiebreaker también devolvió "no response" en los 2 tickers donde se activó (BBV.BA, MMM.BA), resultando en `inconclusive`. Una tasa de fallo del 100% sugería que la llamada a la API no se estaba completando. Diagnóstico confirmado: el saldo de Anthropic API había llegado a $0, devolviendo `BadRequestError 400: "credit balance too low"`. La excepción era capturada silenciosamente por un `except Exception` en `_web_search`, que retornaba `[], ""` sin ningún log visible para el usuario.

Se identificaron tres problemas encadenados:

1. **Fallo silencioso**: la excepción de la API era capturada y descartada con `logger.warning` enterrado en stdout; el usuario no tenía forma de saber que el news gate no había corrido.
2. **Cache envenenado**: `_search_cached` guardaba incondicionalmente el resultado vacío `{results: [], llm_text: ""}`. Las 333 entradas generadas en esa corrida habrían invalidado el cache por 4 días, haciendo que corridas futuras (con crédito recargado) siguieran leyendo "no response" desde cache.
3. **Capital sizing insensible al status**: `_allocate_capital` usaba `final_score` directamente como peso, sin distinguir entre posiciones `ranked` y `held_with_warning`. BBV.BA (fundamentals unknown + tiebreaker inconclusive) recibió USD 918 — prácticamente igual que RTX.BA (confirmed, USD 944).

**Decisión:** Cuatro fixes aplicados en 2026-07-27.

**Fix 1 — No cachear respuestas vacías (`news_gate.py:_search_cached`):**
`cache.save_news(...)` ahora está dentro de `if results or llm_text:`. Una respuesta vacía no se persiste. Las 333 entradas del 2026-07-27 fueron purgadas manualmente del cache. El comportamiento fail-open (defaultear a `CLEAN`/`INCONCLUSIVE`) se mantiene intencional para no bloquear el ranking por fallos transitorios de API — el cambio es que el fallo ya no queda "congelado" en cache por 4 días.

**Fix 2 — Logging explícito de errores de API (`news_gate.py:_web_search`):**
Se agrega una rama específica para `anthropic.BadRequestError` antes del `except Exception` genérico. Si el error contiene "credit", el mensaje es `logger.error("ANTHROPIC API: crédito insuficiente — recargá crédito en console.anthropic.com")`. Todos los errores de API pasan a `logger.error` (antes `logger.warning`), haciendo imposible que el fallo pase desapercibido en stdout. El stacktrace se incluye en excepciones inesperadas.

**Fix 3 — Descuento escalonado de capital para held_with_warning (`filter2_runner.py`):**
Se agrega la función `_effective_score(opp)` que aplica un multiplicador al `final_score` antes de calcular el peso en `_allocate_capital`. Dos niveles de incertidumbre:
- **Nivel alto** (`fundamental_state == "unknown"` + `sentiment_gate == "inconclusive"`): factor 0.5 — el ticker tiene tanto incertidumbre fundamental como de sentimiento.
- **Nivel medio** (`fundamental_state in ("confirmed", "neutral")` + `sentiment_gate == "inconclusive"`): factor 0.7 — el fundamental está disponible pero el sentimiento no pudo resolverse.
- **Sin descuento** si `held_with_warning` se origina solo en la penalización Argentina (el ajuste ya está capturado en el `final_score`).

Los factores viven como constantes nombradas en `filter2_thresholds.py` (`HWW_CAPITAL_FACTOR_HIGH = 0.5`, `HWW_CAPITAL_FACTOR_MEDIUM = 0.7`) — ajustables sin cambiar lógica. El `capital_rationale` del output indica explícitamente cuando se aplicó el descuento y con qué factor.

**Fix 4 — Cache gate antes del fetch en vivo de yfinance (`data/fetcher.py`):**
`_fetch_prices_with_fallback` no verificaba `cache.prices_are_fresh()` antes de intentar el fetch en vivo, resultando en ~300 requests HTTP a yfinance en cada corrida aunque los datos del día anterior estuvieran en cache. Se agrega el gate: si `cache.prices_are_fresh(symbol)` devuelve `True`, se retorna el cache inmediatamente con `FetchStatus.OK` sin tocar yfinance. La lógica de retry y fallback a stale cache queda intacta. Impacto en runtime: corridas subsiguientes al mismo día pasan de 3-8 minutos de fetch a segundos.

**Costos reales de la API de Anthropic:**
Con el cache de 4 días funcionando correctamente, el costo de una corrida fresca completa es ~$0.50-0.70 (≈350 llamadas a claude-haiku-4-5 × ~$0.002/llamada incluyendo web search results). Corridas subsiguientes dentro de los 4 días cuestan ~$0 (todo desde cache). El problema del 2026-07-27 fue saldo agotado en $0, no ineficiencia de diseño.

**Alternativas consideradas:**
- Cambiar el default de fail-open (`CLEAN`) a fail-closed (`DISCARD`) cuando la API no responde → descartado: un fallo de conectividad o crédito no es evidencia de que el ticker tenga hard news; penalizar con discard sería un falso negativo sistemático. El fail-open es correcto — el problema era que el fallo era invisible y se cacheaba.
- Aplicar un multiplicador único plano para todos los `held_with_warning` (ej. ×0.6) → descartado en favor del sistema escalonado: `unknown + inconclusive` es epistemicamente peor que `confirmed + inconclusive`, y el sizing debe reflejar esa diferencia.
- Eliminar el cache de noticias completamente y fetchear siempre en vivo → descartado: con 280+ survivors por corrida, fetchear en vivo cada semana gastaría ~$0.70 innecesariamente cuando la mayoría de las noticias del martes son iguales a las del lunes.

**Estado:** Activa. Ver `analysis/filter2_deep_dive/news_gate.py`, `filter2_runner.py`, `filter2_thresholds.py`, `data/fetcher.py`.

---

## 15 — 2026-07-30: Earnings calendar warning — gap nuevo identificado en módulo de reversiones

**Contexto:** El scanner de reversiones (analysis/reversal/) nunca llamaba al news gate ni a ningún equivalente, a diferencia del pipeline principal del watchlist. En la corrida del 2026-07-27, AMZN.BA fue la única oportunidad reportada sin ninguna sección de advertencias. Amazon reportó earnings el 2026-07-30 (3 días después de la fecha del análisis) con EPS +215% — un evento binario de alta volatilidad que el scanner sugirió ignorar al calcular la invalidación táctica. Adicionalmente, se confirmó que el chequeo de fechas de earnings/balance próximos no existía en ninguna parte del proyecto (ni watchlist ni reversiones).

**Decisión:** Se implementa un chequeo de earnings calendar en AMBOS pipelines usando `yf.Ticker(symbol_underlying).calendar`:

- **Approach B (warning sin exclusión):** no se descarta el ticker ni se bloquea la señal. Se agrega una advertencia explícita en `warnings` para que el usuario evalúe el riesgo con información concreta antes de entrar.
- **Ventana:** `EARNINGS_WARNING_WINDOW_DAYS = 7` días hábiles, constante nombrada y configurable en `data/earnings.py`.
- **Tipo de retorno:** `EarningsCheckResult` con tres estados explícitos: `VERIFIED_CLEAR` (verificado, sin riesgo en ventana), `VERIFIED_WARNING` (verificado, earnings inminentes), `UNVERIFIED` (no se pudo obtener el dato). Los callers agregan `result.message` a warnings cuando no es `None` — cubre tanto `VERIFIED_WARNING` como `UNVERIFIED`. `VERIFIED_CLEAR` tiene `message=None` y no agrega nada.
- **Fallback UNVERIFIED:** warning explícito `"⚠ No se pudo verificar fecha de earnings — dato no disponible"` para los 4 casos: calendar no es dict (API cambiada), earnings_dates vacío/None (BBV y similares sin coverage en yfinance), next_date con tipo inesperado, y excepción de red. No se omite en silencio: el usuario recibe información sobre qué sabe el sistema y qué no. Mismo principio epistémico del news gate Fix 2 (Decision #14): "no sé" y "sé que está limpio" son estados distintos. Logging: `logger.warning` en los 4 casos (visible en corridas normales).
- **Solo aplica a CEDEARs** (con `symbol_underlying`). Acciones argentinas directas no tienen subyacente con calendario de earnings en yfinance.
- **Mensaje:** `"⚠ Earnings próximos: YYYY-MM-DD (N días hábiles) — evaluar riesgo de gap antes de entrar"`.

**Archivos creados/modificados:**
- `data/earnings.py` — nueva utilidad compartida `check_earnings_warning(symbol_underlying, window_days)`
- `analysis/reversal/reversal_scanner.py` — llama a `check_earnings_warning` post-construcción del `ReversalOpportunity`, popula `opp.warnings`
- `analysis/filter2_deep_dive/filter2_runner.py` — llama a `check_earnings_warning` en `_evaluate_one()` antes del ajuste Argentina, agrega a `warnings`

**Retroactividad (solo aprendizaje):**
- AMZN.BA (2026-07-27): habría generado `⚠ Earnings próximos: 2026-07-30 (3 días hábiles)` — la señal habría sido visible.
- BBV.BA (2026-07-27): no habría generado warning (coverage no disponible en yfinance para BBV).
- MMM.BA: earnings Oct 20, 2026 — bien fuera de ventana en cualquier corrida de julio.

**Alternativas consideradas:**
- Opción A (exclusión dura — no mostrar si earnings dentro de X días) → descartado: pierde oportunidades donde el mercado ya descontó el evento; además las reversiones tácticas pueden ser válidas incluso frente a un earnings (e.g., post-selloff con earnings ya incorporados). El usuario prefiere información para decidir, no exclusión automática.
- Opción A como flag `--strict` futuro → posible extensión si se identifica un patrón sistemático de falsas señales pre-earnings.

**Estado:** Activa. Ver `data/earnings.py`, `analysis/reversal/reversal_scanner.py`, `analysis/filter2_deep_dive/filter2_runner.py`.

---

## 16 — 2026-08-03: Timeout y gate de exclusiones en check_earnings_warning — corrección de hang de 1h31m

**Contexto:** La corrida del 2026-08-03 se colgó 1h31m durante el Filter 2. La última salida visible fue `WARNING check_earnings_warning(NUE): Failed to perform, curl: (28) Operation timed out after 1009897 milliseconds`. Diagnóstico: el proceso entró en sleep a mitad de una conexión TCP abierta; sin timeout explícito en la llamada `.calendar`, el socket quedó bloqueado indefinidamente. CPU del proceso: 17.75s en 1h31m de elapsed — claramente trabado en I/O, no procesando. Causa raíz confirmada: (1) `yf.Ticker(symbol).calendar` no tenía ningún timeout; (2) `check_earnings_warning` no consultaba `yfinance_exclusions.json` antes de llamar a yfinance — los 17 símbolos que dieron 404 en esa corrida (ABEV3, ADGO, BBAS3, BBDC3, BBV, BNG, BPAC11, BRFS, BRKB, CSNA3, HAPV3, ITUB3, KOFM, MBT, MGLU3, NATU3, NOKA) ya estaban todos en `excluded_underlyings`, pero el gate no existía.

**Decisión:** Dos fixes implementados en `data/earnings.py`:

**Fix A — Timeout explícito (`EARNINGS_CALENDAR_TIMEOUT_SEC = 15`):**
- Constante nombrada en `data/earnings.py` (junto a `EARNINGS_WARNING_WINDOW_DAYS` — misma convención de constantes de módulo).
- La llamada `yf.Ticker(symbol).calendar` se envuelve en un `ThreadPoolExecutor` de un worker con `future.result(timeout=EARNINGS_CALENDAR_TIMEOUT_SEC)`. Se usa `executor.shutdown(wait=False)` para no bloquear en el `__exit__` si el thread sigue colgado.
- No se usa `requests.Session(timeout=...)` porque yfinance no garantiza respetar el session timeout para `.calendar` — puede usar rutas internas que ignoran la sesión pasada. El `ThreadPoolExecutor` es un hard wall: devuelve control al caller en N segundos sin importar qué pase dentro del thread.
- En timeout: retorna `UNVERIFIED` con log `"timeout after 15s"` distinguible de las otras causas de UNVERIFIED.
- Valor 15s: el timeout de curl observado fue ~16.8 min (red cortada por sleep), lo cual confirma que yfinance no tiene ningún límite propio. 15s es suficiente para redes lentas normales y falla rápido ante cortes reales.

**Fix B — Gate de exclusiones previo a la llamada de red:**
- Mismo patrón de carga que `data/fundamentals.py` y `data/prices.py`: `_EXCLUSIONS_PATH` + `_excluded_underlyings_cache: Optional[Set[str]]` + helper privado `_is_excluded_underlying()` con lazy load y fallback a set vacío.
- `excluded_underlyings` es un `dict` en el JSON — se usa `.keys()` para construir el set.
- Gate al inicio de `check_earnings_warning()`, antes de cualquier llamada de red. Si excluido: retorna `UNVERIFIED` inmediatamente con log `"known_unverifiable (yfinance_exclusions)"` — distinguible de fallo de red.
- La carga es lazy y se cachea a nivel de proceso (no persiste entre corridas), exactamente como `fundamentals.py`. Esto satisface el requisito de re-leer el JSON fresco en cada nueva corrida: si se elimina un símbolo de `yfinance_exclusions.json`, la próxima corrida lo verá correctamente.
- `refresh_exclusions.py` sigue siendo el único proceso de mantenimiento del archivo — `earnings.py` solo lo lee.

**Logging distinguible por caso (UNVERIFIED):**
- `known_unverifiable (yfinance_exclusions)` — gate de exclusiones activado
- `timeout after 15s` — Fix A activado
- `malformed response` — `.calendar` no retornó dict
- `empty` — `Earnings Date` ausente o vacío
- `malformed date` — tipo de fecha inesperado
- `network exception` — excepción capturada en el bloque exterior

**Tests creados:** `tests/test_earnings.py` — 11 casos, todos pasan. Incluye: timeout path (verifica retorno dentro de `EARNINGS_CALENDAR_TIMEOUT_SEC + 3s`), exclusion gate (verifica que `yf.Ticker` nunca se llama para símbolos excluidos), los 4 casos UNVERIFIED pre-existentes, y happy path (VERIFIED_CLEAR, VERIFIED_WARNING).

**Archivos creados/modificados:**
- `data/earnings.py` — Fix A + Fix B implementados
- `tests/__init__.py` — nuevo (primer test file del proyecto)
- `tests/test_earnings.py` — nuevo

**Alternativas consideradas:**
- `requests.Session(timeout=15)` pasado a `yf.Ticker(symbol, session=...)` → descartado: yfinance no garantiza respetar el session timeout en `.calendar` para todas las rutas internas; el hang observado ocurrió con curl (que respeta el timeout del SO), no con requests. Un hard wrapper es más confiable.
- `signal.alarm` → descartado: solo funciona en el hilo principal; `check_earnings_warning` puede ser llamado desde threads worker (e.g., pipeline con concurrencia futura).
- Carga del JSON de exclusiones sin cache (re-lectura por llamada) → viable, pero innecesario: el cache por proceso es el patrón establecido en el proyecto y el archivo no cambia durante una corrida.

**Estado:** Activa. Ver `data/earnings.py`, `tests/test_earnings.py`.

---

## 17 — 2026-08-03: Preservación de tickers "passed but not ranked" en Filter2Report — corrección de gap de auditoría

**Contexto:** La corrida del 2026-08-03 reportó `"Filter 2 complete — ranked=10 discarded_by_sentiment=17 unevaluable=0"` y `"149 tickers below MIN_SCORE"`. El total contabilizado era 176 de 276 sobrevivientes. Los 100 restantes tenían `final_score ≥ MIN_SCORE` (completamente evaluados, con score técnico, fundamentals, sentimiento y ajuste Argentina) pero fueron descartados silenciosamente por el corte `top = passing[:MAX_POSITIONS]` en el post-processing de `run_filter2()`. No había log line, no había campo en `Filter2Report`, y sus objetos `Filter2Opportunity` eran descartados por el garbage collector. Una auditoría post-corrida no podía distinguir "superó todos los filtros pero quedó en rank 11" de "no pudo ser evaluado".

**Conexión con principio epistémico (Decision #14 y #15):** "passed but not ranked" y "failed evaluation" son estados distintos con significado diferente para el usuario. El mismo principio que distingue `VERIFIED_CLEAR` de `UNVERIFIED` en el earnings gate, y `CLEAN` de `INCONCLUSIVE` en el news gate, aplica aquí: el sistema debe exponer lo que sabe y no colapsar estados distintos en silencio.

**Decisión:** Dos cambios mínimos — sin impacto en el reporte Markdown, sin cambio en la lógica de ranking ni capital:

**1. Nuevo campo en `Filter2Report` (`filter2_models.py`):**
```python
passed_min_score_not_ranked: List[Filter2Opportunity]  # scored ≥ MIN_SCORE pero fuera del top-N
```
Mismo patrón de tipado que los campos existentes `opportunities` y `discarded_by_sentiment`. Los objetos preservados tienen `rank=0`, `proposed_capital_usd=0.0`, `capital_rationale=""` (valores ya asignados por `_evaluate_one()` antes del ranking) — no se corre `_allocate_capital` ni lógica adicional sobre ellos. La invalidación sí está computada (se calcula en `_evaluate_one()` para todos los tickers que pasan el sentiment gate).

**2. Nueva log line + captura en `run_filter2()` (`filter2_runner.py`):**
```python
not_ranked = passing[MAX_POSITIONS:]
logger.info(
    "%d tickers passed MIN_SCORE (%.0f) — top %d selected, %d passed but outside ranking",
    len(passing), MIN_SCORE, MAX_POSITIONS, len(not_ranked),
)
```
La identidad aritmética ahora es completamente trazable en los logs:
`total_input = unevaluable + discarded_by_sentiment + below_min + not_ranked + ranked`

**Impacto en output/watchlist_report.py:** nulo. El generador de Markdown accede solo a campos nombrados explícitos de `Filter2Report` (`opportunities`, `discarded_by_sentiment`, `unevaluable_symbols`, `warnings`, `run_date`, y totales). No itera sobre campos genéricamente. Verificado por inspección de código y por test `test_watchlist_report_ignores_new_field`.

**Tests creados:** `tests/test_filter2_report.py` — 4 casos:
- Construcción de `Filter2Report` con el nuevo campo
- Scores y valores cero (rank, capital) se preservan sin modificar
- Identidad aritmética en `run_filter2()` (mock end-to-end con 30 survivors controlados)
- Ausencia del nuevo campo en `watchlist_report.py` (test de no-regresión del reporte)

**Archivos modificados:**
- `analysis/filter2_deep_dive/filter2_models.py` — nuevo campo `passed_min_score_not_ranked`
- `analysis/filter2_deep_dive/filter2_runner.py` — captura `not_ranked`, log line, campo en `Filter2Report`
- `tests/test_filter2_report.py` — nuevo

**Alternativas consideradas:**
- Campo con `total_passed_min_score_not_ranked: int` (solo el conteo, sin los objetos) → descartado: pierde los scores y breakdowns, que son precisamente los datos útiles para calibración posterior de `MIN_SCORE` y `MAX_POSITIONS`.
- Log line sin preservar los objetos → descartado: un número en el log no permite inspeccionar rank 11 ni detectar si el corte en 10 está bien calibrado.
- Persistir en un archivo separado → sobrediseño para esta etapa; el campo en `Filter2Report` es suficiente para el consumidor del report (scripts de análisis, CLI, futuros callers).

**Estado:** Activa. Ver `analysis/filter2_deep_dive/filter2_models.py`, `analysis/filter2_deep_dive/filter2_runner.py`, `tests/test_filter2_report.py`.
---

## 18 — 2026-08-04: Audit layer para el scanner de reversiones — near-misses, signal registry y outcome tracking

**Contexto:** El scanner de reversiones publicaba oportunidades sin ningún mecanismo para evaluar su calidad histórica: no había registro de qué tickers pasaron el filtro, no había forma de saber si los setups se resolvieron favorablemente (target) o desfavorablemente (stop hit), y no había visibilidad de tickers que casi calificaron pero no llegaron. Esto impedía calibrar los umbrales del scanner con datos reales.

**Caso motivador concreto:** BYMA.BA apareció en 3 reportes consecutivos (23/07, 24/07, 03/08) con score y RSI casi idénticos sin resolución visible. ADGO.BA salió del reporte el 04/08 coincidiendo con downgrades de analistas que el sistema no captura. SNAP.BA del 30/06 probablemente tocó su nivel de invalidación en julio. Sin registro, ninguno de estos patrones era auditable.

**Decisión:** Implementar tres módulos de auditoría independientes del pipeline de análisis.

**Módulo 1 — `analysis/reversal/signal_registry.py`:**
Registro append-only de cada oportunidad publicada en `data/reversal_tracking/signals.jsonl`. Persiste: scan_date, symbol, score, rsi_14, entry_price_ars (close al momento del scan), invalidation_level_ars, nearest_support, support_type, catalysts, weekly_trend, outcome_status. La `entry_price_ars` se toma de `bundle.prices_ars.data.iloc[-1]["close"]` en el momento del scan y se almacena como campo explícito en `ReversalOpportunity`. El registro es idempotente: re-corridas del mismo scan_date no duplican registros. También provee deduplicación: `check_recent(symbol, scan_date, current_price_ars)` devuelve la fecha de la aparición anterior si el mismo ticker fue publicado en los últimos 7 días con movimiento de precio menor al 3%. Si se detecta, se agrega un warning al `ReversalOpportunity` ("🔁 Señal repetida"). El umbral del 3% distingue un setup genuinamente nuevo de una señal repetida sin resolución.

**Módulo 2 — `analysis/reversal/near_miss_tracker.py`:**
Captura tickers que fallaron exactamente un gate por un margen pequeño. Solo se registran fallos de un único gate (multi-gate failures son descartes genuinos). Umbrales aprobados (DECISIONS.md #18):
- RSI fuera de [25, 45] por ≤ 3 pts
- Distancia al soporte entre 5% y 7%
- Sin catalizador con todos los otros gates pasados y score hipotético ≥ 40
- Vol ratio entre 0.80 y 0.90
- Weekly trend negativa pero score hipotético ≥ 55

El gate de fundamentals deteriorating NO genera near-miss (descarte correcto por definición). Tras cada scan se loguea la distribución de near-misses por gate como `logger.info`, habilitando calibración futura (p.ej. evaluar si "weekly_trend_negative" genera ruido desproporcionado). Escribe a `data/reversal_tracking/near_misses.jsonl`.

Refactorización necesaria: `_evaluate_bundle` en `reversal_scanner.py` fue separado en `_compute_metrics()` (computa todas las métricas sin aplicar gates) + gates aplicados sobre el resultado. `_compute_metrics` es exportado para uso en `near_miss_tracker.py`. El comportamiento de `_evaluate_bundle` es idéntico al anterior.

**Módulo 3 — `analysis/reversal/outcome_tracker.py`:**
Para cada señal con outcome_status="pending", fetchea precios históricos post-scan_date y determina el outcome en orden cronológico, barra a barra:
1. Stop hit: close < invalidation_level_ars → `stop_hit`
2. Target +8%: close > entry * 1.08 → `target_8pct`
3. Target +5%: close > entry * 1.05 → `target_5pct`
4. Sin resolución tras 20 días calendario → `lateral`

Caso especial: si no hay precios disponibles post-scan_date pero el ticker existe en yfinance (señal demasiado reciente, mercado no cerrado), la señal permanece `pending`. Solo se marca `unresolved_no_data` si el ticker no tiene datos en yfinance en absoluto o si el deadline de 20 días ya pasó y aún no hay datos. Persiste en `data/reversal_tracking/outcomes.jsonl`. `summarize()` muestra tabla agregada total + desglose por catalizador con caveat "⚠ n pequeño" cuando n < 5. Se llama automáticamente al inicio de cada scan via `run_at_scan_start()` — errores son capturados con `logger.warning` sin bloquear el scan.

**Integración en `scan_reversals()`:** El parámetro `record=True` (default) activa los tres módulos en secuencia. Los fallos de cualquier módulo de tracking se logean como warning y no interrumpen el scan principal. `scan_reversals` acepta `scan_date: str` explícito (default: date.today()).

**Backfill histórico:** `scripts/backfill_reversal_signals.py` parsea los 10 reportes existentes (06-30 a 08-04) extrayendo datos desde los Markdown y precios via yfinance. Resultado inicial: 23 señales backfilled, 0 unresolved_no_data. Win rate inicial (16 resueltos): 81% (MA200 bounce 75%, RSI divergence 80%, Reversal candle 100% con n=3 pequeño). 7 pending al momento de escribir esta entrada.

**Tests:** 14 nuevos casos en `tests/test_reversal_tracking.py` cubriendo: record idempotente, deduplicación (match y no-match por precio y por antigüedad), update de outcome_status, gate distribution, stop_hit, target_5pct, lateral, summarize con pending, run_at_scan_start no-raise.

**Archivos creados:**
- `analysis/reversal/signal_registry.py`
- `analysis/reversal/near_miss_tracker.py`
- `analysis/reversal/outcome_tracker.py`
- `scripts/backfill_reversal_signals.py`
- `data/reversal_tracking/signals.jsonl` (23 registros)
- `data/reversal_tracking/outcomes.jsonl` (16 registros resueltos)
- `tests/test_reversal_tracking.py`

**Archivos modificados:**
- `analysis/reversal/reversal_scanner.py` — `ReversalOpportunity` gana `entry_price_ars`; `_evaluate_bundle` refactorizado via `_compute_metrics`; `scan_reversals` gana params `scan_date` y `record`

**Estado:** Activa. Ver `analysis/reversal/`, `data/reversal_tracking/`, `tests/test_reversal_tracking.py`.
---

## 19 — 2026-08-04: Lógica asimétrica en outcome_tracker — low intradiario para stop, close para targets

**Contexto:** El outcome_tracker original usaba únicamente el close diario para evaluar tanto stops como targets. Esto introduce un sesgo optimista: en mercados de baja liquidez como BYMA, los spreads intradiarios son amplios y los gaps frecuentes. Un stop-loss de mercado ejecuta cuando el precio toca el nivel, no cuando cierra; pero un target de largo solo se cuenta si el precio mantuvo el nivel al final del día (si cerró lejos, el trade no pudo salir ahí).

**Decisión:** Lógica asimétrica en `_assess_signal()`:
- **Stop check**: usa `low` intradiario. Si el low del día cae por debajo del nivel de invalidación, el outcome es `stop_hit` aunque el close haya recuperado. Esto refleja cómo ejecuta un stop-loss real en un mercado con liquidez imperfecta.
- **Target check**: usa `close`. Un target solo se cuenta si el precio cerró en ese nivel o por encima. Un spike intradiario que no sostiene no cuenta como win.
- **Orden**: stop se evalúa primero dentro de cada barra (antes de cheque de targets). Dado que stop < entry < targets, un mismo close no puede activar ambos, pero un low puede activar el stop mientras el close activa el target — en ese caso el stop tiene prioridad (el día comenzó siendo un día de pérdida, el cierre no borra la ejecución del stop-loss).

**Impacto en los datos:** Recálculo sobre las 16 señales resueltas del backfill (06-30 a 08-04). Un único cambio de resultado: TMUS.BA (señal del 06-30) pasó de `target_5pct` a `stop_hit`. El low del 07-01 fue 7,900 ARS, por debajo del nivel de invalidación de 8,111 ARS. Observación de calidad de señal: la invalidación de TMUS.BA (8,111) era mayor que el entry al close (7,995), lo que indica que el scanner corrió intradiario cuando el precio aún estaba sobre el soporte (high del día: 8,315), pero al close ya había perforado hacia abajo. La nueva metodología captura esto correctamente.

**Win rate corregido:** 75% (12 wins / 16 resueltos), vs. 81% con close-only. La corrección es conservadora y más fiel a la ejecución real. La distribución por catalizador no cambia cualitativamente (MA200 75%, RSI divergence 80%, Reversal candle 67% con n=3).

**Cambios de código:**
- `_fetch_price_history()`: retorna `pd.DataFrame[close, low]` en lugar de `pd.Series[close]`
- `_assess_signal()`: itera sobre `price_df.iterrows()`, usa `row['low']` para stop y `row['close']` para targets; maneja gracefully el caso de `low` ausente (fallback a close)
- Tests actualizados: mocks cambian de `pd.Series` a `pd.DataFrame({"close": ..., "low": ...})`; se agregan 2 nuevos casos: `test_stop_hit_intraday_low` (low perfora stop, close no) y `test_target_not_counted_on_intraday_high_only` (high supera target, close no)

**Archivos modificados:**
- `analysis/reversal/outcome_tracker.py`
- `tests/test_reversal_tracking.py`

**Estado:** Activa. Ver `analysis/reversal/outcome_tracker.py`, `tests/test_reversal_tracking.py`.

---

## 20 — 2026-08-04: Guardrail de señal invertida + diagnóstico de timing intradiario

**Origen:** Auditoría del signal_registry post-backfill identificó 2 señales donde `invalidation_level_ars > entry_price_ars` en los registros históricos (TMUS.BA 06-30, ADGO.BA 08-03). Esto implicaría que el stop está por encima del precio de entrada — una señal comercialmente inválida.

**Diagnóstico de causa raíz:**

El código del scanner tiene un invariante matemático que previene esta condición:
- `_find_nearest_support()` requiere `support_level < close[-1]`
- `invalidation = support_level * (1 - 0.015)`
- Por lo tanto: `invalidation < close[-1] * 0.985 < close[-1] = entry_price_ars`

El invariante se mantiene siempre en el scanner en ejecución. Las anomalías encontradas son **artefactos del backfill**, no bugs del scanner en producción. Causa específica: el backfill obtuvo `entry_price_ars` del close oficial de yfinance (al correr el backfill), mientras el scanner corrió **intradiario** con el precio en ese momento como `close[-1]`:

- TMUS.BA 06-30: scanner vio precio ~8,240 (high del día 8,315), MA50 o swing_low = 8,235 era válido. Close oficial = 7,995. El backfill registró 7,995 como entry, invirtiendo la relación.
- ADGO.BA 08-03: scanner vio precio ~15,400 (apertura 15,610, MA200 = 15,345 era válido). Close oficial = 15,010. Mismo artefacto.

**Implicación operativa separada (no corregida en esta tarea):** Si el scanner corre intradiario durante el horario de mercado, `yf.Ticker.history()` retorna el precio actual (no el close oficial) como último bar. Esto significa que:
1. `entry_price_ars` en la oportunidad publicada es el precio intradiario, no el close.
2. Un trader que ejecuta "al close" o "apertura siguiente" opera a un precio diferente del registrado.
3. Los niveles de soporte e invalidación son válidos para ese momento intradiario, pero pueden quedar estales si el precio cae significativamente antes del close (como ocurrió con ADGO.BA: abrió 15,610, el scanner vio MA200=15,345 como soporte válido, cerró 15,010 — ya debajo del soporte al momento de ejecutar).

**Decisión inmediata: guardrail en `_evaluate_bundle()`**

Aunque el invariante previene la condición en condiciones normales, se agrega un check defensivo explícito después de computar la invalidación:

```python
if invalidation >= m.entry_price_ars:
    logger.error(
        "%s: rejected — invalidation %.2f >= entry_price %.2f "
        "(support %s=%.2f above current price; possible intraday scan artifact)",
        m.symbol, invalidation, m.entry_price_ars, support_type, nearest_support,
    )
    return None
```

El guardrail usa `logger.error` (visible en producción, no silencioso), rechaza la señal antes de publicarla, y no tiene falsos positivos bajo el invariante normal. Cobertura del fix: señales con `invalidation >= entry_price` por cualquier causa (artefacto intradiario, cambio de datos, error futuro).

**Chequeo retroactivo:** 23 señales históricas en signals.jsonl, 2 con la anomalía — ambas son artefactos del backfill, no del scanner. Si el scanner corriera ahora con los closes oficiales como datos, el invariante se cumpliría para las dos.

**Tests creados:** `tests/test_reversal_scanner_guardrail.py` — 3 casos:
- Señal normal pasa sin triggear el guardrail
- Soporte por encima del entry (inverted) → rejected con logger.error
- Caso borde: invalidation == entry_price → también rejected

**Decisión de timing (resuelta en la misma sesión):** Se eligió rechazo duro (no warning en reporte), porque un warning depende de que el usuario lo lea con atención en cada corrida. Eliminar la ambigüedad de raíz es más robusto.

`scripts/run_reversals.py` agrega `_check_market_hours()` como primer paso de `main()`. Horario de bloqueo: lunes a viernes, 11:00 ART (apertura BYMA equities) hasta 17:15 ART (cierre oficial 17:00 + 15 min buffer para propagación en yfinance). Fuera de ese rango — incluyendo fines de semana — el scanner corre sin restricción.

Si el gate actúa: `logger.error` + `sys.exit(1)` con hora actual y hora recomendada. `--force` bypasea con `logger.warning` visible — solo para testing. El gate vive en el script de entrada, no en `scan_reversals()`, para que la librería permanezca testeable sin parchear el tiempo.

Validación en vivo (08-04 11:52 ART, mercado abierto): sin `--force` → exit 1 con mensaje claro; con `--force` → warning y continúa.

**Archivos modificados:**
- `analysis/reversal/reversal_scanner.py` — guardrail en `_evaluate_bundle()`
- `scripts/run_reversals.py` — `_check_market_hours()`, argumento `--force`
- `tests/test_reversal_scanner_guardrail.py` — nuevo

**Estado:** Activa. Ver `analysis/reversal/reversal_scanner.py` (`_evaluate_bundle`), `scripts/run_reversals.py` (`_check_market_hours`), `tests/test_reversal_scanner_guardrail.py`.

---

## 21 — 2026-08-04: Deduplicación de exposición en win rate — criterio pendiente como condición adicional

**Contexto:** El backfill de 23 señales reveló que `summarize()` inflaba el win rate al contar señales repetidas del mismo ticker como eventos independientes. Casos concretos: VOD.BA apareció 3 veces (7/01, 7/03, 7/05) y TTE.BA 2 veces (7/03, 7/05), todas ganando — el mismo movimiento de precio contado múltiples veces. Sin deduplicación, `n=15` resolvables con `win_rate=80%`; con deduplicación, `n=12` y `win_rate=75%`. El sesgo es sistemáticamente alcista: los duplicados aparecen cuando la jugada ya está ganando (el precio se mueve en la dirección correcta, lo que vuelve a activar el scanner). Un stop rápido elimina el ticker antes de que genere una segunda señal, por lo que los duplicados siempre sesgan hacia wins.

**Distinción central — dos criterios para dos propósitos:**

`signal_registry.check_recent()` detecta señales repetidas para el **warning visual** `"🔁 Señal repetida"` en el reporte. Su criterio: mismo ticker dentro de 7 días con precio que no movió >3%. El propósito es alertar al usuario de que el precio lleva días estancado en el mismo setup. La lógica está en `check_recent()` sin cambios.

`_is_exposure_duplicate()` (nuevo en `outcome_tracker.py`) detecta duplicados de **exposición de capital** para el cálculo interno de win rate. Comparte los mismos parámetros de ventana y precio (7 días / 3%), pero agrega una tercera condición: **la señal previa debe seguir con `outcome_status == "pending"` al momento en que se publica la nueva**. Si la señal previa ya se resolvió (target o stop) antes de que apareciera la nueva, son dos trades independientes — el capital de la primera ya se liberó, y la segunda es una entrada genuinamente nueva. Sin el filtro de pendiente, una re-entrada legítima post-stop (misma acción, precio sin moverse mucho en pocas horas) quedaría excluida incorrectamente del win rate.

**Decisión:**
- `_is_exposure_duplicate(signal, all_signals, outcomes_by_key)` — nuevo helper privado en `outcome_tracker.py`. Criterios: (1) mismo ticker dentro de 7 días, (2) movimiento de precio < 3% vs. entry de la señal previa, (3) señal previa aún pending al momento de publicación (sin registro en outcomes, o con `days_to_outcome` tal que `scan_date_nueva < scan_date_previa + days_to_outcome`). Para señales laterales o sin datos (`days_to_outcome=None`), se asume pending (estuvo abierta los 20 días completos, bien dentro de cualquier ventana de 7 días).
- `summarize()` construye `duplicate_keys = {(scan_date, symbol)}` de señales duplicadas y excluye ese subconjunto del denominador, wins y desglose por catalizador. El total de señales se muestra completo en el header; el count de excluidas se expone explícitamente: `"n=N señales, M excluidas como dup. de exposición"`.
- El warning visual `"🔁 Señal repetida"` en los reportes no cambia — sigue usando `check_recent()` tal cual.

**Resultado sobre backfill actual (2026-06-30 a 2026-08-04):**
Señales duplicadas de exposición identificadas: VOD.BA 7/03, VOD.BA 7/05, TTE.BA 7/05 (3 de 23 señales). SNAP.BA 7/01 no es duplicado (Δprecio=9.14% ≥ 3%). VRSN.BA 7/01 no es duplicado (Δprecio=3.03%, ≥ umbral de 3% por margen mínimo). Win rate ajustado: 75% (9 wins / 12 resolvables), vs. 80% sin deduplicación.

**Archivos modificados:**
- `analysis/reversal/outcome_tracker.py` — constantes `_DEDUP_LOOKBACK_DAYS / _PRICE_THRESHOLD`, helper `_is_exposure_duplicate()`, `summarize()` ajustado
- `tests/test_reversal_tracking.py` — 6 nuevos casos en `TestExposureDeduplification`

**Estado:** Activa. Ver `analysis/reversal/outcome_tracker.py` (`_is_exposure_duplicate`, `summarize`).

---

## 22 — 2026-08-06: Enrichment silencioso de revisión de estimaciones de analistas

**Contexto:** Se investigó si yfinance expone datos de revisión de estimaciones de analistas con cobertura suficiente para el universo del proyecto. El objetivo era agregar un tag informativo `analyst_revision_trend` a los registros de `signals.jsonl` y `near_misses.jsonl`, siguiendo el mismo patrón que `near_miss_tracker` (dato nuevo → se trackea primero → se decide con evidencia después). El tag NO aparece en el reporte `.md` ni afecta el score ni los filtros de entrada.

**Atributos disponibles en yfinance confirmados:** `eps_trend`, `eps_revisions`, `earnings_estimate`, `revenue_estimate`, `recommendations_summary` — todos existen como DataFrames de pandas, actualizados diariamente vía Yahoo Finance.

**Decisión — fuente: `eps_revisions` (no `eps_trend`)**

`eps_revisions` expone `upLast30days` y `downLast30days` por período (0q, +1q, 0y, +1y). Se computa `net = sum(upLast30days) - sum(downLast30days)` → tag "up" / "down" / "stable" / "no_data".

`eps_trend` (snapshot histórico del consenso EPS en current, 7d, 30d, 60d, 90d) fue descartado por un problema de calidad de datos: las columnas históricas contienen **ceros reales (no NaN)** cuando Yahoo no tenía estimación registrada en ese timestamp — observable en stocks con cobertura esporádica (ej. PAMP.BA: `30daysAgo=0.0` real, no ausencia de dato). Calcular `(current - 0) / 0` produce error de división o señal falsa. `eps_revisions` no tiene este problema.

**Nota sobre discrepancia entre fuentes:** Las dos fuentes pueden mostrar señales opuestas para el mismo ticker en el mismo momento. Ejemplo observado: GGAL.BA con `eps_trend` mostrando DOWN (-3.9% en 30d) mientras `eps_revisions` muestra UP (net +1). La razón es que miden cosas distintas: nivel del consenso vs. dirección de los movimientos individuales de analistas. Usar ambas en paralelo requeriría reconciliación explícita; se eligió una sola fuente por simplicidad del dato silencioso en esta fase.

**Umbral mínimo universal:** `numberOfAnalysts >= 3` (de `earnings_estimate`, fila "0y") antes de emitir "up"/"down". Si no llega al umbral → tag `"no_data"`, independientemente de `eps_revisions`. Aplica a todo el universo (no solo acciones argentinas) — un CEDEAR mid-cap con 1-2 analistas tiene el mismo problema de muestra chica.

**Cobertura del universo:** ~80-85% de los CEDEARs con underlying US válido (~280/349). CEDEARs sin underlying (exchanges no-US: Adidas, BASF, Samsung, etc.) y los ~54 excluidos en `yfinance_exclusions.json` → 0%. Acciones argentinas: ~70-80% con cobertura pero conteo de analistas bajo (GGAL.BA: 1-4 analistas típico). El tag ausente sale como `"no_data"` — no hay error, no hay ruido.

**Scope de ejecución:** Se corre SOLO sobre las oportunidades publicadas (0-5 por scan) y near-misses registrados (0-10), NO sobre los 391 tickers del universo. El bloque se inserta en `scan_reversals()` después del cap y deduplicación, inmediatamente antes de `record_signals` — cuando `opportunities` ya es la lista final. Total adicional de llamadas yfinance por scan: ≤15. Esto preserva el SLA de red y evita agravar la degradación observada el 2026-08-05 (131s vs. ~20s baseline, sospecha de rate limiting).

**Comportamiento ante fallos:** El bloque de enrichment tiene su propio `try/except` aislado. Fallo de red, timeout, o ticker sin datos → `{"trend": "no_data", "n_analysts": None}` para ese ticker, sin bloquear el scan ni el recording. El near-miss enrichment tiene un `try/except` adicional interno, de modo que un fallo de `fetch_revisions_for_symbols` nunca impide que `record_near_misses` se ejecute.

**Datos registrados en `signals.jsonl` y `near_misses.jsonl`:**
```json
{ "analyst_revision": {"trend": "up", "n_analysts": 28} }
```
El campo `n_analysts` se persiste para poder estratificar en la auditoría de outcomes: señales con más analistas detrás podrían tener win rate diferente del promedio — a verificar con evidencia antes de incorporarlo al scoring.

**Próximos pasos:** En unas semanas, cruzar `analyst_revision.trend` contra `outcome` en `outcomes.jsonl` para ver si hay diferencia de win rate entre "up", "down", "stable", y "no_data". Recién con esa evidencia se decide si el tag pasa a influir en el score o los filtros.

**Archivos creados/modificados:**
- `analysis/reversal/analyst_revision.py` — nuevo módulo con `_fetch_one`, `fetch_revisions`, `fetch_revisions_for_symbols`
- `analysis/reversal/signal_registry.py` — `record_signals` acepta `enrichments: Optional[Dict]` opcional
- `analysis/reversal/near_miss_tracker.py` — `_append_record` y `record_near_misses` aceptan `enrichment`/`enrichments` opcionales
- `analysis/reversal/reversal_scanner.py` — dos nuevos bloques `if record` en `scan_reversals`

**Estado:** Activa. Ver `analysis/reversal/analyst_revision.py`, `docs/DECISIONS.md #22`.

---

## 23 — 2026-08-23: Tres mejoras de legibilidad a summarize() — n explícito, stop vs lateral, y desglose temporal

**Contexto:** Un análisis ad-hoc del histórico deduplicado (scripts/adhoc_catalyst_breakdown.py) reveló que el output de `summarize()` era potencialmente engañoso en tres aspectos:
1. Los porcentajes de win rate aparecían sin el tamaño de muestra al lado — "80%" sin "(4/5)" invita a sobrestimar la confianza en n pequeños.
2. Los "no-wins" se colapsaban en una sola categoría. Un catalizador que falla lateralizando (capital preservado, sin resolución) es cualitativamente diferente de uno que genera stops (pérdida de capital). RSI bullish divergence tiene 0 stops en 5 resolvables — ese dato es más relevante que el win rate del 80%.
3. El desglose por catalizador era solo agregado. Los 14 casos de MA200 bounce/proximity acumulan 4 wins y 10 stops, pero los 4 wins están todos en el período 2026-06-30 a 2026-07-05, y los 10 stops son todos de 2026-07-23 a 2026-08-13 concentrados en 4 tickers (DECK.BA ×4, BYMA.BA ×3, ADGO.BA ×2, VIVT3.BA ×1). Un número agregado que mezcla dos regímenes de mercado distintos no describe una propiedad del catalizador — describe un accidente estadístico de la muestra disponible.

**Decisión:** Tres cambios a `summarize()` en `analysis/reversal/outcome_tracker.py`. Ninguno toca el scoring, los filtros de entrada, ni la lógica de deduplicación — son cambios de presentación exclusivamente.

**Cambio 1 — n explícito junto al win rate:**
Todas las celdas de win rate pasan a formato `"X% (W/R)"` donde W=wins, R=resolvable. Implementado en `_fmt_rate(wins, resolvable)` — función de formateo privada. El porcentaje sin el denominador al lado queda prohibido en el output.

**Cambio 2 — Distinción stops vs laterales:**
El desglose por catalizador agrega columnas `stops` y `lat` separadas. La distinción operativa: un stop implica pérdida de capital ejecutada; un lateral implica capital preservado con tiempo consumido pero sin pérdida. RSI bullish divergence: 0 stops, 1 lateral — el non-win fue tiempo perdido, no capital perdido. MA200 bounce: 10 stops, 0 laterales — el catalizador cuando falla, pierde. Esa diferencia es relevante para el sizing y la tolerancia al riesgo.

**Cambio 3 — Desglose temporal YYYY-MM × catalizador:**
Nueva sección que cruza período (año-mes de scan_date) con catalizador. Salida actual con los datos históricos disponibles:
- MA200 bounce: 100% en 2026-06, 50% en 2026-07, **0% en 2026-08** (7 stops / 7 resolvables)
- RSI divergence: 100% en 2026-06, 67% en 2026-07, 100% en 2026-08

El desglose temporal expone que el deterioro de MA200 bounce está concentrado en el último período disponible, consistente con un efecto de régimen de mercado (BYMA bajista desde fines de julio) más que con una propiedad intrínseca del catalizador. La sección incluye un aviso explícito: "⚠ Ver evolución temporal antes de leer el agregado".

**Lo que NO se cambió:**
- Scoring del scanner de reversiones — sin cambios.
- Lógica de deduplicación de exposición (`_is_exposure_duplicate`) — sin cambios.
- Lógica de assess_outcomes — sin cambios.
- Umbrales de entry/stop/target — sin cambios.
Razón: con n=5 resolvables en RSI divergence y la muestra MA200 contaminada por régimen de mercado, cualquier reponderación de scoring ahora sería sobreajuste. Estos cambios modifican cómo se LEE el output, no cómo el sistema genera señales.

**Caveat de muestra que debe recordarse al leer los números:**
El subconjunto MA200 bounce de la segunda mitad de julio–agosto 2026 no es una muestra representativa del catalizador en condiciones normales — es una cadena de stops en un régimen bajista sobre unos pocos tickers recurrentes. Si el mercado vuelve a condiciones neutras o alcistas, el win rate de MA200 bounce puede volver a niveles del 50-100% observados en el período inicial. No ajustar umbrales ni ponderaciones basándose en este número hasta tener al menos 20 resolvables en condiciones de mercado variadas.

**Verificación:**
- Nivel 1 (imports): OK — `_fmt_rate`, `_catalyst_stats`, `summarize` importan sin error.
- 22 tests en `tests/test_reversal_tracking.py`: todos pasan.
- Nivel A (smoke test): `run_reversals.py --sample 5` termina en 12s, exit 0, sin excepción.

**Archivos modificados:**
- `analysis/reversal/outcome_tracker.py` — `_fmt_rate()` nuevo helper, `_catalyst_stats()` nuevo helper, `summarize()` reemplazado

**Estado:** Activa.

---

## [2026-08-27] Degradación de fetch yfinance: causa raíz confirmada como comportamiento de caché, no problema a resolver

**Contexto:** Se observó variabilidad extrema en los tiempos de fetch yfinance: desde 13s hasta 131s, con el número de `partial` variando entre 1 y 81 en la misma semana. Se barajaron dos hipótesis: (a) hora del día (US market hours), (b) caché local.

Dos corridas el mismo día (2026-08-27) proveen evidencia concluyente:
- **08:26** → 107s, ok=245, partial=52; con líneas "CCL updated" / "MEP updated" en log.
- **19:27** → 13s, ok=296, partial=1; sin líneas "CCL updated" / "MEP updated".

**Causa raíz — caché local por trading day:**

El código en `data/fetcher.py:_fetch_prices_with_fallback` (line 123) hace `cache.prices_are_fresh(symbol)` antes de llamar a yfinance. La función `prices_are_fresh()` en `data/cache.py:65` devuelve `True` si el último bar cacheado cubre el último día hábil antes de hoy. Una vez que la primera corrida del día escribe los precios, todas las corridas posteriores los sirven de caché sin tocar yfinance.

Para CCL/MEP, el TTL es `as_of == date.today()` (`ccl_is_fresh()` / `mep_is_fresh()`): cualquier corrida después de la primera del día no hace live fetch de FX — por eso desaparecen las líneas "CCL updated" y "MEP updated" en la corrida de las 19:27.

**TTL por capa:**
| Capa | Criterio |
|---|---|
| Precios | `last_bar >= último día hábil antes de hoy` (por trading day) |
| CCL / MEP | `as_of == date.today()` (por día calendario) |
| Fundamentals | `(today - as_of).days < 90` |

**Conclusión de diseño:** "partial alto + fetch lento" es el **costo esperado y normal del primer fetch real del día**. No es un problema a resolver ni un síntoma de degradación. Las corridas lentas (~100s) con más partials (~50) son la corrida de calentamiento; las rápidas (~13s, casi 0 partials) son corridas con caché caliente. La variabilidad no es aleatoria — es determinista según si la caché está fría o caliente.

**La hipótesis de hora del día queda descartada.** Coincidía con la caché fría (primera corrida del día suele ser la matutina), pero la prueba del 2026-08-27 (primera = 08:26 lenta, segunda = 19:27 rápida) la refuta: lo que importa es si es la primera corrida del día, no la hora.

**Lo que se implementó como mejora de observabilidad:**
Se agrega campo `cache_hit: int` a `FetchSummary` (models.py) y campo `price_from_cache: bool` a `TickerBundle`. El log de fetch complete ahora expone `cache_hit=N live_fetch=M`, distinguiendo sin ambigüedad las dos situaciones. Las corridas futuras mostrarán algo como:
- Primera corrida: `cache_hit=3 live_fetch=294`
- Corridas siguientes: `cache_hit=296 live_fetch=1`

**Lo que NO se cambió:** La lógica de caché — el diseño actual es correcto. No se justifica aumentar TTL, agregar invalidación explícita, ni cambiar el comportamiento del fetcher.

**Archivos modificados:**
- `data/models.py` — `FetchSummary.cache_hit: int`, `TickerBundle.price_from_cache: bool`
- `data/fetcher.py` — `_fetch_prices_with_fallback` retorna 3-tuple con bool; `_build_summary` cuenta cache hits; log de fetch complete incluye `cache_hit` y `live_fetch`

**Verificación:** 40 tests pasan. Imports OK.

**Estado:** Activa. Tema cerrado.

**Estado:** Activa. Ver `analysis/reversal/outcome_tracker.py` (`summarize`, `_fmt_rate`, `_catalyst_stats`).

---

## [2026-09-01] outcome_tracker siempre emite una línea INFO por corrida; errores por señal son aislados

**Contexto:** La corrida del 2026-08-28 no emitió ninguna línea de `outcome_tracker`, dejando sin saber si el tracker corrió, falló, o no tuvo nada que hacer. Dos causas identificadas: (1) el path "sin señales pendientes" logueaba a DEBUG (invisible en corridas normales INFO); (2) `run_at_scan_start()` tenía un `except Exception` genérico que absorbía errores con un warning vago, sin tipo de excepción ni traceback.

**Decisión:**
- `assess_outcomes()` siempre emite exactamente una línea INFO por corrida: `"0 pending signals in evaluation window — nothing to assess"` si no hay pendientes, o `"assessed N signals, M resolved; K still pending in window"` si los hay. Nunca silencio.
- Si el assessment de una señal individual falla (por ejemplo, el fetch de precios lanza una excepción), el error se aisla a esa señal: se loguea un WARNING nombrando el ticker y el tipo de excepción, se marca como `unresolved_no_data`, y se continúa con las demás. Un ticker roto no aborta el assessment del resto.
- El guard de nivel superior en `run_at_scan_start()` ahora loguea a ERROR con `exc_info=True` (tipo de excepción + traceback completo) en lugar de un warning genérico de una línea.
- No se modificó ninguna lógica de assessment, umbrales, `_MAX_DAYS` ni estados de outcome.

**Archivos modificados:**
- `analysis/reversal/outcome_tracker.py` — `assess_outcomes()`: cambio de `logger.debug` a `logger.info` en el path vacío; try/except por señal con síntesis de `unresolved_no_data`; contador `still_pending`; línea INFO final ampliada. `run_at_scan_start()`: `logger.warning` → `logger.error(..., exc_info=True)`.
- `tests/test_reversal_tracking.py` — dos tests nuevos: `test_zero_pending_signals_logs_info_summary` (verifica la línea INFO con caplog) y `test_per_signal_price_fetch_failure_is_isolated` (verifica aislamiento de error y continuación).

**Estado:** Activa.

---

## [2026-08-31] Los archivos de tracking de reversiones se versionan en git y se auto-commitean por corrida

**Contexto:** Los archivos `data/reversal_tracking/signals.jsonl`, `outcomes.jsonl` y `near_misses.jsonl` se perdieron porque estaban sin versionar y no estaban en git. Se recuperaron 37 señales, 29 outcomes y 149 near-misses. Son la materia prima de todo el análisis de performance del scanner — perderlos implica perder la capacidad del sistema de aprender de sus propios resultados.

**Decisión:**
- Los tres archivos canónicos de tracking están ahora versionados en git (se agrega commit de recovery como baseline).
- Al final de cada corrida de `run_reversals.py`, el helper `_commit_tracking_files(scan_date)` hace `git add` de los tres archivos y crea un commit local con el mensaje `chore(tracking): update reversal tracking data YYYY-MM-DD`.
- Si los archivos no cambiaron, el commit se saltea silenciosamente (sin crear commits vacíos).
- Si la operación git falla por cualquier motivo (no es un repo, HEAD detached, git no disponible, etc.), se loguea un WARNING y la corrida continúa normalmente — el fallo de commit nunca aborta el pipeline.
- **No se hace push automático.** El commit es solo local; hacer push es decisión manual del usuario.
- Los directorios de backup (`_pre_merge_backup/`, archivos `*.bak`) permanecen en `.gitignore` — solo los tres `.jsonl` canónicos se versionan.

**Archivos modificados:**
- `scripts/run_reversals.py` — `import subprocess`, constante `_TRACKING_FILES`, helper `_commit_tracking_files()`, llamada al final de `main()`
- `.gitignore` — exclusiones explícitas para `_pre_merge_backup/` y `*.bak` en `data/reversal_tracking/`

**Estado:** Activa.

---

## [2026-09-01] Brecha entre exit registrado y nivel de invalidación en stop_hit

**Contexto:** Cuando una señal toca su stop, `outcome_tracker` registra como
`exit_price_ars` el `close` del día que gatilló el stop, no el
`invalidation_level_ars` exacto. Como el precio típicamente cierra por debajo del
nivel de invalidación el día que lo rompe, las pérdidas medidas son
sistemáticamente peores que las que se realizarían con una ejecución de stop
exactamente en el nivel.

**Cuantificación (sobre 16 señales stop_hit con datos completos):**
- Brecha promedio: **+1,69%** por debajo del nivel de invalidación.
- Brecha mediana: +1,35%.
- Rango: +0,16% (DECK 07/08, cierre casi en el nivel) a +4,48% (ADGO 03/08).
- Implicancia: un stop nominal de -5% se registra en la práctica como ~-6,7% en
  promedio. Las métricas de pérdida del sistema están sesgadas hacia peor por
  este margen.

**Observación sobre la distribución:** la brecha no es uniforme. Los papeles
menos líquidos o más volátiles (ADGO, VIVT3) rompen el nivel con más fuerza
(brechas de 2,8%-4,5%), mientras que los más líquidos cierran cerca del nivel
(DECK: 0,16%-0,20% en varias señales). No corresponde aplicar un ajuste plano.

**Decisión:** No se corrige el tracker por ahora — registrar el `close` real es
conservador (mide el peor caso realista, no un ideal optimista de ejecución
perfecta en el nivel). Se documenta la brecha para que los análisis de
expectativa y calibración la tengan en cuenta: la expectativa real del sistema es
levemente mejor que la que muestran los números crudos de stop_hit, porque asumen
ejecución en el cierre y no en el nivel.

**Implicancia para el futuro módulo de venta (Fase 4):** un stop ejecutado por
software en tiempo real (no evaluado sobre el cierre diario) capturaría precios
más cercanos al nivel de invalidación, reduciendo esta brecha. Es un argumento a
favor de la ejecución automática vs. la evaluación post-cierre, pero solo se
materializa con ejecución real, no con el tracker actual.

**Estado:** Activa (documentación; sin cambio de código).

---

## [2026-09-01] Reconciliador CSV ↔ log: principio de log limpio, adopción automática y manejo de discrepancias

**Contexto:** Con el reconciliador (cocos_csv_parser → reconciler → reconcile_positions.py) operativo, fue necesario establecer reglas explícitas sobre qué puede escribirse automáticamente al log, qué queda como manual, y cómo calibrar el mecanismo de matching de señales.

**Decisiones:**

### 1 — Principio del log limpio

`positions_log.json` es el registro de track record del sistema: solo contiene posiciones abiertas como consecuencia directa de ejecutar una señal publicada. Nunca se adopta una posición al log solo porque existe una señal histórica para ese ticker en algún momento; la adopción automática exige que la fecha de compra del CSV caiga dentro de una ventana temporal *después* de que la señal fue publicada.

Con un portfolio 100% discrecional (situación actual), el reconciliador adoptará cero posiciones de forma automática — eso es el comportamiento correcto, no un bug. El mecanismo solo empieza a adoptar una vez que el usuario opera ejecutando señales del sistema.

### 2 — Ventana de matching provisional (a calibrar)

La función `find_signal_backed_candidates()` en `data/adoption.py` usa una ventana de **5 días calendario** como placeholder para determinar si una compra del CSV pudo haber sido la ejecución de una señal. La lógica es exclusivamente hacia atrás: `scan_date ∈ [csv_first_buy_date − ventana, csv_first_buy_date]`. Una señal posterior a la compra nunca aplica.

**Este valor es provisorio y requiere calibración.** La metodología correcta es la misma que se usó para el cooldown de 15 días post-stop: medir con datos reales cuántos días tarda el usuario en ejecutar una señal después de su publicación, y ajustar la ventana a ese valor empírico. Hasta que existan datos de ejecución real, el número 5 no debe presentarse como validado en ningún output del sistema (los reportes lo etiquetan como "ventana provisoria (a calibrar)").

### 3 — Discrepancias de cantidad y costo: siempre manuales

Las entradas en `qty_mismatch` y las de `matched` con `cost_mismatch=True` **nunca se corrigen automáticamente**. El reconciliador las reporta para que el usuario las investigue y use `log_position.py` directamente. La razón es que una discrepancia de cantidad podría indicar una operación parcial, un split, o un error de CSV, y ninguna de esas situaciones es segura de resolver sin revisión humana.

### 4 — Cierres: siempre con confirmación y motivo explícito

El script `reconcile_positions.py --apply` nunca cierra posiciones automáticamente, ni siquiera cuando el CSV confirma que el ticker fue vendido. Para cada cierre el usuario debe confirmar explícitamente (`s/N`), ingresar la fecha de cierre, el precio, y el motivo (`target`/`stop`/`manual`). El motivo no se infiere porque la clasificación correcta impacta las métricas de performance del sistema.

**Archivos modificados:**
- `data/adoption.py` — nuevo módulo: `AdoptionCandidate`, `find_signal_backed_candidates()`
- `scripts/reconcile_positions.py` — nuevo CLI: `--dry-run` / `--apply` / `--verbose`
- `tests/test_adoption.py` — 11 tests cubriendo el matching window

**Estado:** Activa.

---

## 24 — 2026-09-02: News context check para el scanner de reversiones — cierre del gap estructural

**Contexto:** El scanner de reversiones nunca llamaba al news gate ni a ningún equivalente (gap identificado el 2026-08-04, ver Decision #15). A diferencia del pipeline del watchlist, que corre el news gate sobre los survivors antes del ranking, `run_reversals.py` publicaba oportunidades sin ninguna verificación de contexto de noticias. El gap era estructural: el modelo de reversión toma posiciones en tickers oversold, cuya debilidad puede tener causa fundamental que invalida el rebote. Sin un chequeo de noticias, ese riesgo era invisible en el output.

**Decisión:** Se implementa un módulo dedicado `analysis/reversal/news_check.py` con una sola etapa — sin tiebreaker condicional. El resultado es siempre informativo (warning visible en el .md), nunca un veto que descarte la oportunidad. El usuario decide con la información a la vista.

**Por qué módulo propio y no reutilizar `run_news_gate` del watchlist:**
La firma pública de `run_news_gate` requiere `TechnicalResult` y `FundamentalResult` — tipos que el scanner de reversiones no computa. Construir objetos sintéticos para satisfacer la interfaz sería engañoso y frágil. Los prompts del watchlist también están orientados a confirmar un uptrend (¿el momentum tiene soporte?), mientras que para reversión la pregunta es distinta (¿la caída tiene causa fundamental?). La infraestructura de cache y API sí es compatible — se replica el patrón de `_web_search` + `_search_cached`, con un namespace de cache distinto (`reversal_news:`) para evitar colisiones con el watchlist.

**Tres estados de salida (principio epistémico de Decision #14):**
- `VERIFIED_CLEAR` — el LLM buscó y no encontró nada relevante; `warnings = []`
- `VERIFIED_WARNING` — el LLM encontró un hallazgo relevante; `warnings` contiene ≤ 2 líneas formateadas
- `UNVERIFIED` — error de API, respuesta vacía, o el modelo respondió `UNVERIFIED`; `warnings` contiene `"⚠ NEWS [UNVERIFIED]: ..."` explícito

Nunca cachea respuesta vacía ni error (Decision #14 Fix 1): `cache.save_news()` solo se llama cuando `llm_text` es no-vacío.

**Prompt — categorías evaluadas (horizonte de 6,5 días):**
1. Cambio de recomendación de analistas o rebaja de precio objetivo (últimos 30 días)
2. Revisión de guidance, profit warning, o cambio de management
3. Litigios, investigaciones regulatorias, o eventos corporativos materiales
4. Contexto FX/macro: tendencia moneda local vs USD para CEDEARs de otro país (solo tendencia — la prima CCL la calculamos internamente con precisión, no se pide al LLM)
5. Eventos de calendario próximos: ex-dividendo, vencimiento de lock-up, decisión regulatoria

El modelo responde `CLEAR` (buscó, no encontró), `WARN: [categoría] | [hallazgo] | [fuente, fecha]` (≤ 2 líneas), o `UNVERIFIED` (no pudo buscar). Formato estricto que separa "busqué y nada" de "no pude buscar" — el fail-open a nivel prompt fue corregido aquí desde el diseño inicial, a diferencia del watchlist que lo corrigió como fix retroactivo (Decision #14).

**Truncación a 2 hallazgos:** implementada en el parser en código (`warn_lines[:NEWS_REVERSAL_MAX_WARNINGS]`), no en el prompt. Esto permite que el LLM devuelva todos los hallazgos relevantes, pero el output del report queda acotado a dos líneas máximo por oportunidad.

**TTL de cache:** 1 día de calendario (`NEWS_REVERSAL_CACHE_TTL_DAYS = 1`). Criterio: `(date.today() - cached_at).days < 1` → solo el mismo día es fresco. Un trade de 6,5 días promedio no puede tolerar contexto de más de 24h — arrastrar la búsqueda de anteayer en un trade que puede resolverse en 2-3 días es inaceptable. El costo efectivo con TTL de 1 día: ≈5 oportunidades × $0.005 × 5 corridas/semana = $0.125/semana.

**Punto de inserción:** post-cap (0-5 oportunidades finales), post-dedup, pre-analyst_revision, pre-record_signals. Simétrico con el bloque de `analyst_revision` ya existente. Nunca sobre los 391 tickers del universo.

**Cambio de firma de `scan_reversals`:** se agrega `cache: Optional[Cache] = None`. El único caller de producción (`run_reversals.py`) pasa el cache existente. Todos los callers de test usan `_evaluate_bundle` directamente — no afectados. Si `cache=None`, el bloque produce automáticamente `UNVERIFIED` para todas las oportunidades con log `WARNING` — nunca silencio.

**Formato del warning en el .md:**
```
- ⚠ NEWS [VERIFIED]: Analysts | Goldman bajó a Neutral, target USD 155 | Bloomberg, 2026-08-28
- ⚠ NEWS [VERIFIED]: FX/Macro | BRL cayó 4.2% vs USD en últimas 2 semanas | Ambito, 2026-08-30
- ⚠ NEWS [UNVERIFIED]: no se pudo verificar contexto de noticias (sin respuesta del modelo)
```

Máximo dos líneas por oportunidad. El prefijo `⚠ NEWS [VERIFIED]:` / `⚠ NEWS [UNVERIFIED]:` lo agrega el parser, no el LLM — el LLM solo devuelve el contenido después de `WARN:`.

**Alternativas consideradas:**
- Reutilizar `run_news_gate` del watchlist con objetos sintéticos → descartado: acoplamiento frágil, preguntas distintas para cada pipeline.
- Tiebreaker condicional (segunda etapa como en el watchlist) → descartado: el resultado es un warning, no un veto. La segunda etapa agregaría costo y complejidad sin cambiar ninguna decisión del usuario.
- TTL de 48h → descartado: la diferencia de costo con TTL de 24h es de ~$0.06/semana. No justifica arrastrar contexto de anteayer en un trade de 6,5 días.

**Archivos creados/modificados:**
- `analysis/reversal/news_check.py` — nuevo módulo: `NewsCheckStatus`, `NewsCheckResult`, `fetch_news_context()`
- `analysis/reversal/reversal_scanner.py` — parámetro `cache: Optional[Cache] = None`, bloque news check post-cap
- `scripts/run_reversals.py` — pasa `cache=cache` a `scan_reversals()`

**Estado:** Activa.

---

## 25 — 2026-09-03: Correcciones de primera corrida real — news check de reversiones

**Contexto:** Primera corrida real post-implementación (Decision #24) con 4 oportunidades genuinas: AMX.BA, JD.BA, NGG.BA, RIOT.BA. Se identificaron cuatro problemas no detectables con mocks: un gap de infraestructura, dos bugs de parser, y dos problemas de calidad de contenido del prompt.

---

### Fix 1 — `load_dotenv()` faltante en `run_reversals.py`

`run_reversals.py` no cargaba el `.env` del proyecto, a diferencia de `run_watchlist.py` que lo hace desde la primera línea. Sin la variable `ANTHROPIC_API_KEY`, el módulo `anthropic.Anthropic()` lanza `AuthenticationError` en producción aunque el crédito esté disponible. El error era visible (logger.ERROR), pero producía UNVERIFIED para las 4 oportunidades.

**Fix:** Se agrega `from dotenv import load_dotenv` y `load_dotenv(Path(__file__).parent.parent / ".env")` al inicio de `run_reversals.py`, igual que en `run_watchlist.py`. Mismo patrón, consistencia restaurada.

---

### Fix 2 — Parser: WARN: embebido en línea de preámbulo (Bug AMX.BA)

El LLM ocasionalmente escribe `WARN:` sin salto de línea previo, concatenado al preámbulo: `"I'll search for news.WARN: Analyst | ..."`. El parser original buscaba líneas que *empezaran* con `WARN:` — esta línea empieza con `"I'll"` y el finding quedaba descartado.

**Síntoma:** AMX.BA reportó 1 finding en vez de 2 en la primera corrida sin el fix.

**Fix:** El parser ahora también detecta `WARN:` como substring dentro de una línea. Si `"WARN:"` aparece en cualquier posición de la línea, extrae el contenido desde ese índice. Implementado en el loop de colección de `warn_lines` en `_parse_response`.

---

### Fix 3 — Parser: veredicto en línea no-primera (Bug RIOT.BA)

El LLM agrega texto de razonamiento antes del veredicto. En el caso RIOT.BA, la respuesta fue: `"I'll search... Based on my search:\n\nCLEAR"`. El parser original evaluaba solo `first_line` para detectar `CLEAR`/`UNVERIFIED`. `first_line` era el preámbulo, no `CLEAR`, y el parser caía al path de "respuesta inesperada" → UNVERIFIED.

**Síntoma:** RIOT.BA reportó UNVERIFIED en vez de VERIFIED_CLEAR en la primera corrida.

**Fix:** El parser ahora escanea *todas* las líneas para detectar `CLEAR` y `UNVERIFIED`, una vez descartada la presencia de `WARN:` lines. Prioridad: `WARN:` > `CLEAR` > `UNVERIFIED` > unparseable.

---

### Fix 4 — Prompt: alucinación de país/moneda (Bug AMX.BA con BRL)

El prompt original incluía `"For non-US based companies (e.g., Brazilian ADRs): include the local currency trend vs USD (e.g., BRL/USD)"` como instrucción genérica. El LLM, al procesar AMX (América Móvil, México), siguió el ejemplo literal del prompt y reportó contexto de BRL/USD para una empresa mexicana. La información era verificablemente incorrecta.

**Causa raíz:** `TickerMetadata` no tiene campos de país ni moneda — el universe snapshot solo tiene `market: "NYSE"` para todos los ADRs, independientemente del país de origen. El sistema no conocía el país de AMX con certeza; el prompt no lo inyectaba con certeza.

**Fix:** Se agrega `_FX_CONTEXT: dict` en `news_check.py` con el mapeo `symbol_underlying → (country, currency_code)` para todos los underlyings no-US del universo (~80 entradas, cubriendo México, Brasil, UK, Europa, China, Japón, Corea del Sur, India, Taiwan, Sudáfrica, Australia y Canadá). Para símbolos en el lookup, el prompt inyecta: `"The underlying company is based in {country}. Only report {currency}/USD macro trends. Do not reference any other country's currency."` Para símbolos no listados (US-based o no identificados), la categoría FX se omite completamente — no hay contexto antes que contexto equivocado.

**Resultado post-fix (AMX.BA):** Sin mención de BRL. El LLM reportó tres acciones de analistas reales de agosto 2026 (New Street +$35, BofA -$28, JPMorgan upgrade), que son materialmente relevantes para evaluar el trade.

---

### Fix 5 — Prompt: violación de ventana de recencia (Bug NGG.BA)

El prompt original no tenía una regla explícita de recencia para categorías 1-3. La instrucción "last 30 days" solo aparecía en la búsqueda inicial. El LLM, al no encontrar noticias recientes para NGG, reportó los eventos de litigio más recientes disponibles: Rosen Law (enero 2026) y Levi & Korsinsky/NESO fire (abril 2026) — ambos fuera de la ventana de 30 días. El mismo patrón documentado en la corrección del prompt de earnings: el modelo prefiere devolver algo desactualizado antes que admitir que no hay nada reciente.

**Fix:** Se agrega al prompt una regla dura explícita antes de las categorías: `"IMPORTANT: Only report findings with a confirmed event date within the last 30 days. If the most recent relevant event is older than 30 days, do NOT report it — reply CLEAR instead."` La restricción de 30 días también se repite inline en cada categoría (1), (2) y (3). La instrucción de `CLEAR` en el formato de respuesta también se actualiza: `"CLEAR — if you searched and found nothing relevant within the last 30 days"`.

**Resultado post-fix (NGG.BA):** Los findings de enero y abril 2026 desaparecieron. El único finding reportado fue Jefferies bajando el target de £14.10 a £13 el 3 de agosto 2026 — dentro de la ventana, verificable, materialmente relevante (price target cut = categoría 1).

---

**Archivos modificados en esta decision:**
- `analysis/reversal/news_check.py` — `_FX_CONTEXT` dict (Fix 4), `_build_prompt` con recencia dura + lookup de país/moneda (Fix 4+5), `_parse_response` escaneando todas las líneas (Fix 2+3)
- `scripts/run_reversals.py` — `load_dotenv()` (Fix 1)

**Estado:** Activa.

---

## 26 — 2026-09-02: Seguimiento de outcomes de near-misses — calibración de gates con evidencia

**Contexto:** near_misses.jsonl (183 registros) no guardaba `entry_price_ars`, `nearest_support`, `support_type` ni `invalidation_level_ars`. Sin esos campos no era posible calcular un outcome hipotético ni comparar el win rate de near-misses contra el de señales publicadas. Esta decisión cierra ese gap.

**Cambios:**

**1. Schema extension (`NearMissRecord`):** Se agregan cuatro campos opcionales con default `None`:
- `entry_price_ars` — close en scan_date
- `nearest_support` — nivel ARS absoluto del soporte más cercano
- `support_type` — tipo de soporte ("MA50" | "MA200" | "swing_low")
- `invalidation_level_ars` — support × (1 − INVALIDATION_BUFFER)

Los registros pre-#26 tienen estos campos en `null`; los nuevos scans los populan en tiempo real desde `_BundleMetrics`.

**2. Reconstrucción retroactiva (`scripts/backfill_near_miss_prices.py`):** Script de una sola corrida para los 178 registros reconstructibles. Metodología:
- `entry = yfinance close(scan_date)` — mismo método que `backfill_reversal_signals.py:107-122`
- `support = entry × (1 − support_distance_pct/100)` — aritmético, exacto
- `support_type = null` — no reconstruible sin riesgo de introducir errores silenciosos (la lógica de detección de swing_low puede haber cambiado en el período)
- `invalidation = support × 0.985` — INVALIDATION_BUFFER constante para todos los tipos de soporte

Guardrail: si `invalidation >= entry` (artefacto de corrida intradía, mirrors Decision #20), el registro se marca `reconstruction_skip_reason: invalid_reconstruction_stop_above_entry` y los campos de precio se dejan en `null`. Se loguea con `logger.warning`.

**3. Evaluador de outcomes (`analysis/reversal/near_miss_outcomes.py`):** Importa `_assess_signal` e `_is_exposure_duplicate` directamente de `outcome_tracker`. Sin copias — cualquier cambio futuro en la metodología de outcomes se propaga automáticamente. Escribe `data/reversal_tracking/near_miss_outcomes.jsonl`. Función `compare_by_gate()` produce el desglose por gate comparando con señales publicadas.

**Limitaciones documentadas:**

*Intradía:* Los entries de los 178 registros históricos son reconstruidos desde el close de scan_date. Los que provengan de corridas intradía pueden diferir del precio que vio el scanner. No es cuantificable: `near_misses.jsonl` solo guarda `scan_date` (date-only), sin timestamp de corrida. Ambos grupos (near-misses y señales publicadas) comparten el mismo tipo de ruido, por lo que la comparación relativa se sostiene aunque los valores absolutos tengan este sesgo.

*Advertencia metodológica sobre calibración de gates:* Los near-misses son una muestra condicionada — están cerca del umbral por definición, no son una muestra aleatoria de rechazados. Un gate que rechazó near-misses que "hubieran ganado" NO implica directamente que haya que aflojarlo. Mover el umbral genera una nueva población de near-misses en el borde nuevo. Esta evidencia es direccional, no una regla de decisión automática.

**Archivos modificados/creados:**
- `analysis/reversal/near_miss_tracker.py` — schema extension (4 campos), `_append_record`, `_evaluate_near_miss` (forward capture desde `_BundleMetrics`), `summarize_gate_distribution_all_time`
- `analysis/reversal/near_miss_outcomes.py` — nuevo módulo de evaluación y comparación
- `scripts/backfill_near_miss_prices.py` — script de reconstrucción retroactiva (one-shot)

**Estado:** Activa.

---

## 27 — 2026-09-02: Bug de freshness check en caché de precios — exposición histórica

**Contexto:** En la corrida nocturna del 02/09 a las 20:18 ART se detectó que los 4 signals publicados (AMX, JD, NGG, RIOT) tenían scores idénticos al decimal a la corrida matutina de las 09:05. El análisis confirmó un bug en `data/cache.py::_last_expected_trading_day()` activo desde el primer commit del módulo (21/06/2026, commit `e7810c7`).

**El bug:** La función siempre devolvía `date.today() - 1` sin considerar la hora ART. Después de las 17:15 (cierre BYMA), el pipeline debería exigir el bar del día en curso — pero la función seguía exigiendo el día anterior. Resultado: una caché con datos del 01/09 era aceptada como "fresca" a las 20:18 del 02/09.

**La condición exacta de manifestación:** El bug solo produce datos corruptos cuando se cumplen simultáneamente:
1. Corrida post-17:15 ART en un día hábil
2. Sin corrida previa ese mismo día (que ya habría cacheado el bar corriente)
3. La caché más reciente tiene barras del día anterior

Cuando hubo corridas dobles (mañana + noche), el bug estuvo enmascarado: la caché matutina ya tenía el bar del día y el check nocturno pasaba correctamente.

**Fix:** `_last_expected_trading_day()` ahora usa `datetime.now(ZoneInfo("America/Argentina/Buenos_Aires"))`. Si es día hábil y hora ≥ 17:15 ART, devuelve `today`. En otro caso, devuelve el último día hábil anterior. Mismo gate que `run_reversals.py::_MARKET_CLOSE_GATE`. 8 tests de bordes cubren todos los casos (gate exacto, un minuto antes, lunes, sábado, domingo).

**Exposición histórica (reconstruida con timestamps reales donde disponibles):**

El bug estuvo activo desde 21/06/2026. La instrumentación de `Run started at` en los logs arrancó el 24-25/08/2026; antes de esa fecha la clasificación se basa en commits de código del mismo día y no puede elevarse a `confirmed`. Timestamps reales disponibles: 25/08 20:57, 27/08 08:26 y 19:27, 28/08 19:50, 02/09 09:05 y 20:18.

| Categoría | Señal de exposición | signals | near_misses |
|---|---|---|---|
| `confirmed_stale` | Timestamp real post-17:15 sin run previo ese día; o run doble donde caché matutina obsoleta pasó como fresca | 4 | 28 |
| `likely_stale` | Sin timestamp real; solo 24/08 queda aquí por commit de código post-17:15 | 2 | 16 |
| `uncertain` | Sin timestamp y sin commits concluyentes (pre-instrumentación) | 18 | 78 |
| `safe` | Antes de 17:15 confirmado, o fin de semana (bug no aplica) | 22 | 61 |
| **Total** | | **46** | **183** |

`confirmed_stale` signals: 4 del 02/09 (AMX, JD, NGG, RIOT). `confirmed_stale` near_misses: 08-25 (8), 08-27 (8), 08-28 (12). `likely_stale` near_misses: solo 08-24 (16). Pre-instrumentación (07-23, 08-04, 08-07, 08-31): degradados a `uncertain` por ausencia de timestamp — la inferencia por commits de código no es suficiente para confirmar.

**Nota sobre el 27/08:** hubo dos corridas ese día (08:26 pre-mercado y 19:27 post-cierre). La de las 08:26 cacheó el cierre del 26/08. El bug hizo que la de las 19:27 aceptara ese cierre como si fuera el del 27/08 — mismo mecanismo que el 02/09. `confirmed_stale`.

**Análisis de dirección del sesgo (registros likely_stale con datos disponibles):**

Se chequeó el cambio D-1→D del cierre en los tickers afectados para 4 de 6 fechas likely_stale. Resultado: 2 fechas con movimiento promedio positivo (08-04: +0.93%, 08-07: +0.83%) y 2 con negativo (08-27: −0.21%, 08-31: −1.60%). Con signo alternante entre fechas, no hay evidencia de sesgo direccional consistente — el error de staleness se comporta como ruido de magnitud variable. "Ponderar por cobertura" para elegir una dirección dominante no es un criterio válido de inferencia causal en una muestra de 4 fechas. Dos fechas (08-24, 07-23) no tienen datos recuperables (caché borrada antes del análisis).

**Consecuencia:** los 122 registros en riesgo (todo salvo safe) deben tratarse como de confiabilidad reducida, no como sesgados en una dirección corregible. Los números de EV de Fase 1 (RSI EV −0.78%, no_catalyst +0.09%) calculados el 02/09 incluyen estos registros; son indicativos pero no concluyentes hasta re-auditoría con datos limpios.

**Acción tomada:**
- `price_staleness_risk` field añadido a todos los registros no-safe en `signals.jsonl` y `near_misses.jsonl` (valores: `confirmed_stale`, `likely_stale`, `uncertain`). No se eliminaron ni corrigieron registros.
- Corrida del 02/09 20:18 repetida a las 20:35 con `cache_hit=0 / live_fetch=391` — mismas 4 señales con precios validados del cierre real.
- Pendiente: re-auditoría del EV de Fase 1 filtrando exclusivamente por registros `safe` para aislar el impacto de la contaminación.

**Archivos modificados:**
- `data/cache.py` — fix + imports (`datetime`, `ZoneInfo`, `_ART`, `_MARKET_CLOSE_GATE`)
- `tests/test_cache_freshness.py` — 8 tests de bordes
- `data/reversal_tracking/signals.jsonl` — campo `price_staleness_risk` añadido y reclasificado
- `data/reversal_tracking/near_misses.jsonl` — campo `price_staleness_risk` añadido y reclasificado

**Estado:** Activa — pendiente re-auditoría de EV con corpus safe-only.

---

## 27b — 2026-09-07: Re-auditoría de EV con corpus safe-only + instrumentación de EV en `compare_by_gate()`

**Contexto:** Continuación de #26 (near-miss outcomes) y cierre del pendiente de #27 (re-auditoría del EV filtrando por registros `safe`). No amerita entrada nueva porque (a) el cambio de firma es aditivo y backward-compatible (`filter_safe_only: bool = False`), y (b) es exactamente la acción pendiente que #27 dejó explicitada.

**Cambios en `analysis/reversal/near_miss_outcomes.py`:**

1. `compare_by_gate(filter_safe_only: bool = False)`. Cuando `True`, filtra `raw_records` y `signals` antes del dedup, dejando solo registros con `price_staleness_risk in (None, "safe")` (ver nota semántica abajo). El dedup existente se aplica sin cambios sobre el corpus filtrado.
2. Nuevas columnas por gate: `avg_win` (media de `pct_change` en `_WIN_OUTCOMES`, %), `avg_loss` (media en `_LOSS_OUTCOMES`, %), y `ev = (win_rate × avg_win) + ((1 − win_rate) × avg_loss)` con `win_rate = wins / (wins+stops+laterals)`. Mismos campos calculados también para la fila de señales publicadas.
3. `__main__` acepta `--safe-only` y `--skip-assess` para correr el reporte en cualquier configuración sin re-evaluar outcomes.

**Nota semántica sobre "safe" (importante):** #27 documenta que el campo `price_staleness_risk` solo se pobló para registros no-safe; registros safe (pre-instrumentación y post-fix) no tienen el campo. `filter_safe_only=True` implementa esto como `risk in (None, "safe")` — la ausencia del campo es la marca de safe. Filtrar por `== "safe"` literal daría 0 registros en el corpus actual.

**Resultados de la re-auditoría (2026-09-07):**

| Gate | full n_resolvable | safe n_resolvable | full EV | safe EV |
|---|---|---|---|---|
| rsi_out_of_range     | 36 | 13 | −1.83% | n/a (0 wins) |
| no_catalyst          | 33 | 12 | −2.08% | −2.63% |
| weekly_trend_negative | 5 | 3  | n/a    | n/a |
| vol_ratio_high       | 3  | 1  | −1.67% | n/a  |
| señales publicadas   | 29 | 15 | +0.99% | +0.83% |

- `rsi_out_of_range` y `no_catalyst` pierden ~64% de la muestra resolvable al filtrar por safe; ambos quedan por debajo del umbral de n=15 usado como caveat (`⚠ n chico`).
- Ningún gate cambia el signo del EV entre ambos corpus. `no_catalyst` se hace más negativo (−2.08% → −2.63%). `rsi_out_of_range` pasa a incalculable por 0 wins en safe (evidencia consistente con signo negativo, no cambio de dirección).
- El EV positivo de las señales publicadas se sostiene (+0.99% → +0.83%) con la mitad de la muestra.

**Conclusión operativa:** La corrupción por el bug de #27 no invierte el signo del EV de ningún gate. Los EVs negativos de Fase 1 (rsi_out_of_range, no_catalyst) siguen siendo la lectura direccional, pero con n resolvable insuficiente para tomar decisiones de calibración en el corpus safe. Recolectar más datos post-fix antes de mover umbrales.

**Instrumentación de progreso de calibración (agregado 2026-09-07):** Nueva `log_safe_only_calibration_progress()` en el mismo módulo, invocada al final de `run_reversals.py` después de `generate_reversal_report` y antes de `_commit_tracking_files`. Corre `assess_near_miss_outcomes()` (~cache-hit tras el scan) y loguea `n_resolvable` safe-only por gate (`rsi_out_of_range`, `no_catalyst`) vs. pisos n=15 (lectura direccional) y n=40 (calibración). No loguea EV — solo conteos — para no inducir a leer un número underpowered como definitivo. Non-blocking: any failure cae a `logger.warning` sin abortar el scan (mismo patrón que `analyst_revision` y news check). Reemplaza el paso manual documentado previamente en la memoria de calibración.

**Archivos modificados:**
- `analysis/reversal/near_miss_outcomes.py` — nuevo parámetro, columnas EV, CLI flags, `log_safe_only_calibration_progress()`
- `scripts/run_reversals.py` — hook de progreso de calibración al final del scan

## 27c — 2026-09-09: Sesgo de selección del filtro safe-only — deprecación y reemplazo por corpus post-fix

**Contexto:** Al restringir el análisis de agosto–septiembre por `filter_safe_only=True`, se encontró que el filtro excluye selectivamente las tres únicas ganadoras del período (ABEV3, CAR, RIOT), dejando el corpus safe de ago-sep con 0 wins y 9 stops. La tabla 2×2 es:

| | wins | stops | lat | total | win_rate |
|---|---|---|---|---|---|
| safe | 0 | 9 | 0 | 9 | 0% |
| no-safe | 3 | 4 | 2 | 9 | 33% |
| TOTAL | 3 | 13 | 2 | 18 | 17% |

**Hallazgo:** El filtro safe resultó estar correlacionado con el outcome. No es ruido aleatorio — las tres ganadoras están concentradas en el grupo no-safe. Sin embargo, con n=9 por grupo no hay significancia estadística. La hipótesis mecanicista ("el cache quedaba stale cuando el precio se movía rápido") fue descartada: el bug dependía de la hora de la corrida, no del precio. ABEV3 y CAR son `uncertain` por falta de timestamp (18-19/08, previos a la instrumentación). Con n=3 ganadoras no-safe, **coincidencia es la explicación más simple**. La explicación mecanicista queda no confirmada.

**Comparación apples-to-apples agosto–septiembre (corpus completo, sin filtro safe):**

| Corpus | n_res | wins | stops | lat | win_rate | avg_win | avg_loss | ev |
|--------|-------|------|-------|-----|---------|---------|---------|-----|
| publicadas (completo) | 18 | 3 | 13 | 2 | 17% | +10.09% | -4.26% | -1.87% |
| rsi_out_of_range | 45 | 12 | 28 | 5 | 27% | +7.68% | -4.94% | -1.58% |
| no_catalyst | 39 | 12 | 24 | 3 | 31% | +6.28% | -4.98% | -1.51% |

**Conclusión:** En el mismo período, los tres corpus tienen EV negativo. Los near-misses tienen mayor win rate que las publicadas (27-31% vs 17%), pero los EVs convergen a −1.5%/−1.9% — diferencia indistinguible del ruido a estos n. Las publicadas compensan menor frecuencia con mayor avg_win (+10% vs +6-7%). Esto es un efecto de régimen de mercado en ago-sep, no evidencia de calidad de gates.

**Decisión — deprecación de safe-only como corpus de calibración:**
`safe-only` queda como referencia histórica hasta que `post-fix` tenga muestra suficiente. No se elimina el contador. El corpus de referencia para decisiones de calibración pasa a ser `post-fix`: todos los registros con `scan_date >= 2026-09-03`, limpios por construcción (el fix de #27 se aplicó después de la corrida de las 20:18 del 2026-09-02; RIOT en esa fecha está marcado `confirmed_stale`).

**Corpus post-fix al 2026-09-09:** n=1 publicada resolvable (JD.BA stop), n=2 resolvables para cada gate de near-miss. Insuficiente para cualquier lectura. A ritmo de ~1 publicada/semana y ~2 near-misses/semana por gate, el piso de lectura direccional (n=15) se alcanza en ~2–3 meses de escaneo continuo.

**Implementación:**
- `_CACHE_FIX_DATE = "2026-09-03"` como constante nombrada en `near_miss_outcomes.py`.
- `_compute_gate_groups(filter_safe_only, date_from=None)`: nuevo parámetro opcional que filtra `raw_records` por `scan_date >= date_from` antes del dedup. El filtro de `nm_outcomes` se unificó a `if filter_safe_only or date_from is not None`.
- `log_safe_only_calibration_progress()`: agrega segundo bloque de logging post-fix (near-miss por gate + publicadas) usando `date_from=_CACHE_FIX_DATE`. El bloque post-fix no se loguea si `n_resolvable == 0` en todos los contadores.

**Archivos modificados:**
- `analysis/reversal/near_miss_outcomes.py` — constante `_CACHE_FIX_DATE`, parámetro `date_from` en `_compute_gate_groups`, bloque post-fix en `log_safe_only_calibration_progress()`

## 27d — 2026-09-11: Filtro de fecha futura en news check — falso positivo en Calendar

**Contexto:** El filtro de fecha futura en `_parse_response` (`analysis/reversal/news_check.py`) descarta cualquier `WARN:` que contenga una fecha posterior al `scan_date`, tratándola como alucinación del modelo. El filtro es correcto para las categorías 1-4 (Analyst, Guidance, Regulatory, FX/Macro), pero produce un falso positivo estructural para la categoría 5 (Calendar): los eventos que el prompt solicita en esa categoría son futuros por definición (ex-dividend dates, lock-up expirations, regulatory decisions pendientes).

**Falso positivo concreto:** corrida del 2026-09-11 (scan_date = 2026-09-11), FDX.BA. El modelo reportó `WARN: Calendar | ex-dividend date September 14, 2026 for $1.22 dividend | FedEx/SEC, September 2026`. El filtro vio `September 14, 2026 > 2026-09-11` y descartó el finding como posible alucinación. El resultado: `UNVERIFIED` en lugar de `VERIFIED_WARNING`. El ex-dividend era real — FedEx declaró el dividendo el 9 de septiembre.

**Por qué la excepción es segura:** La alucinación original que motivó el filtro (Roth Capital, `September 26, 2026` en categoría Analyst) era una fecha inventada para una acción pasada. Exceptuar Calendar no reabre ese caso: la excepción aplica solo a la categoría 5 del prompt. Una fecha de analyst recommendation en el futuro sigue siendo una alucinación.

**Horizonte máximo (90 días):** Calendar no es ilimitado — `"September 2027"` seguiría siendo una alucinación. Se acepta hasta 90 días por delante del scan_date. Justificación: ex-dividends se anuncian 2-8 semanas antes; lock-ups relevantes están dentro de los próximos meses; decisiones regulatorias próximas raramente tienen fecha pública a más de 3 meses. 90 días cubre todos los casos operativos sin aceptar fechas claramente inventadas.

**Categorías numéricas:** El modelo a veces devuelve el índice numérico del prompt en lugar del nombre de categoría (observado: `"1"` para Analyst en la corrida del 2026-09-10). Se normaliza `_CALENDAR_CATEGORY = frozenset({"calendar", "5"})` para aceptar ambas formas. Mismo patrón defensivo para cualquier futura categoría con comportamiento especial.

**Implementación:**
- `CALENDAR_MAX_HORIZON_DAYS = 90` — constante pública (configurable sin tocar lógica).
- `_CALENDAR_CATEGORY = frozenset({"calendar", "5"})` — acepta nombre e índice.
- `_extract_warn_category(warn_line)` — extrae la categoría normalizada de cualquier `WARN:` line.
- `_is_calendar_warn(warn_line)` — predicado sobre el conjunto anterior.
- `_has_future_date_beyond_horizon(text, scan_date, horizon_days)` — variante del upper-bound check con horizonte configurable.
- `_parse_response`: Calendar lines usan `_has_future_date_beyond_horizon(wl, scan_date, 90)`; resto mantiene `_has_future_date(wl, scan_date)` (cualquier fecha futura = descarte).

**Tests añadidos (54 en total, todos green):** ex-div 3 días adelante → pasa; lock-up 60 días → pasa; Calendar a 400 días → descarta; Analyst con fecha futura → descarta (comportamiento anterior intacto); categoría `"5"` numérica → exempt; `"1"` numérico → no exempt.

**Archivos modificados:**
- `analysis/reversal/news_check.py` — constante `CALENDAR_MAX_HORIZON_DAYS`, conjunto `_CALENDAR_CATEGORY`, tres helpers, loop en `_parse_response`
- `tests/test_news_check.py` — 2 tests actualizados (comportamiento cambia con la exención), 3 clases nuevas (17 tests)

---

## 27e — 2026-09-11: Reancle del corpus post-fix — primera corrida limpia real

**Contexto:** Decision #27c estableció `_CACHE_FIX_DATE = "2026-09-03"` como ancla del corpus post-fix, con la premisa de que todos los registros a partir de esa fecha son limpios. Decision #30 invalidó esa premisa: las 13 señales publicadas con `scan_date >= 2026-09-03` usaron cierre de T-1 (yfinance publica los bars .BA el día siguiente), y todas están marcadas `price_staleness_risk: "confirmed_stale"`. El corpus que el contador reportaba como limpio es íntegramente contaminado.

**Problema adicional en near-misses:** Los 67 registros de near-miss con `scan_date` entre 2026-09-03 y 2026-09-10 no fueron auditados en Decision #30 (solo se auditaron las señales publicadas). Su campo `price_staleness_risk` es `None`, que `_is_safe()` interpreta como "safe". Un filtro de staleness puro no los excluiría, pero fueron generados por el mismo scanner con los mismos datos de T-1 — no son corpus limpio.

**Primera corrida genuinamente limpia:** 2026-09-11, pre-apertura, con el fail-closed de Decision #30 activo. A esa hora `_last_expected_trading_day()` devuelve T-1 y yfinance sí tiene el bar de T-1 disponible. Los 3 registros de señales y los 16 near-misses del 2026-09-11 son el primer corpus con semántica correcta end-to-end.

**Decisión de implementación (a+b combinados):**
- **(a) Mover `_CACHE_FIX_DATE` a `"2026-09-11"`:** resuelve el problema inmediato — excluye los 67 near-miss records no auditados que el filtro de staleness no puede ver. No requiere retroactively marcar esos registros.
- **(b) Agregar `_is_safe()` a near-misses y señales del contador post-fix:** robustez futura — si en el futuro un batch de registros se marca `confirmed_stale` retroactivamente (ya ocurrió tres veces), se excluyen automáticamente sin actualizar `_CACHE_FIX_DATE`. Los dos mecanismos son complementarios: la fecha ancla maneja el gap presente; el filtro de staleness maneja los futuros.

El argumento de (b) puro no alcanza: near-miss records no auditados tienen `risk=None` → `_is_safe()=True` → se incluirían de todos modos. La combinación (a+b) es la única que logra los dos objetivos.

**Contadores post-fix esperados al 2026-09-11:** near-0. Los 16 near-misses y 3 señales del 2026-09-11 no son resolvables aún (acaban de ocurrir; el hold promedio es 6.5 días).

**Implementación:**
- `_CACHE_FIX_DATE = "2026-09-11"` en `near_miss_outcomes.py`.
- `_compute_gate_groups(filter_safe_only=True, date_from=_CACHE_FIX_DATE)` para el bloque post-fix (was `filter_safe_only=False`).
- `signals_postfix` filtrado también por `_is_safe(s)` además de `scan_date >= _CACHE_FIX_DATE`.

**Archivos modificados:**
- `analysis/reversal/near_miss_outcomes.py` — `_CACHE_FIX_DATE`, `log_safe_only_calibration_progress()`

## 28 — 2026-09-07: Modo paper trading — eliminación de capital del pipeline de reversiones

**Contexto:** El portfolio real en Cocos Capital es discrecional y no debe mezclarse con el sistema de calibración. Las posiciones en `positions_log.json`, los campos monetarios en `Position`, y el parámetro `--capital-ars` obligatorio resolvían un problema inexistente: el sistema nunca tuvo acceso al portfolio real. Mantener esa infraestructura generaba ruido en el reporte y acoplaba la gate de liquidez a un número de capital que el usuario no querría proveer en cada corrida.

**Decisiones adoptadas:**

### 1. `--capital-ars`: optional, default None
`required=True` → `required=False, default=None`. El pipeline funciona sin capital. Solo se usa si se pasa (para diagnósticos o retrocompatibilidad con callers existentes).

### 2. Gate de liquidez: umbral ADV fijo (ADV_MIN_ARS = 15,000,000 ARS)
Reemplaza la fórmula `position_size / ADV > 10%` por un piso fijo independiente del capital. El umbral fue calibrado el 2026-09-07 como P25 de la distribución de ADV de 98 tickers del universo (run diagnose_liquidity.py):

| Percentil | ADV ARS | Tickers bajo umbral |
|-----------|---------|---------------------|
| P10       | ~3M     | —                   |
| P25       | ~15M    | 25% del universo    |
| P50       | ~40M    | —                   |
| P75       | ~120M   | —                   |

Equivalencia con el sistema anterior: P25 = 15M corresponde a correr el gate viejo con ~23M ARS de capital. Rationale para fail-closed (no fail-open): publicar señales ilíquidas contamina el corpus de calibración con outcomes no reproducibles en la práctica. `adv_ars=None` (datos de volumen ausentes) sigue siendo fail-open.

### 3. `positions_log.py`: reconversión a paper tracker sin campos monetarios
Campos eliminados: `qty: float`, `close_price_ars: Optional[float]`.  
Renombrado: `open_price_ars` → `entry_price_ars`.  
El log ahora registra señales publicadas (entry price = precio de publicación, no precio real de ejecución). No hay campos qty porque el sistema nunca manejó órdenes reales.

**Auto-open / auto-close:** `signal_registry.record_signals()` abre automáticamente una posición paper al registrar cada señal tradeable no-scale-in. `outcome_tracker.assess_outcomes()` cierra automáticamente la posición correspondiente cuando resuelve el outcome. El log es self-consistent sin intervención manual.

### 4. Reporte: .md técnico sin secciones de capital
Eliminadas: header capital (total/committed/available), sección "Capital Sugerido" por oportunidad, tabla "Distribución de Capital". Mantenidas: score, RSI, soporte, distancia, catalizadores, invalidación, advertencias. Scale-ins muestran entry date/price/score de la posición paper existente (sección "### Posición paper existente").

### 5. Supresión: eliminación de Part C (per-ticker sizing cap)
`check_sizing_cap()`, `PER_TICKER_CAP_PCT`, `per_ticker_headroom_ars()` eliminados de `suppression.py`. Parts A (cooldown 15bd post-stop) y B (open-position awareness / scale-in) intactas.

**Archivos modificados:**
- `analysis/reversal/liquidity.py` — `ADV_MIN_ARS = 15_000_000`, nuevo `check_liquidity()` sin capital
- `data/positions_log.py` — eliminados `qty`, `close_price_ars`; renombrado `open_price_ars` → `entry_price_ars`
- `analysis/reversal/suppression.py` — eliminada Part C
- `analysis/reversal/reversal_scanner.py` — campo `adv_ars` en `ReversalOpportunity`, limpieza de dependencias capital
- `analysis/reversal/signal_registry.py` — auto-open paper position + campo `adv_ars_at_scan` en signals.jsonl
- `analysis/reversal/outcome_tracker.py` — auto-close paper position al resolver outcome
- `output/reversal_report.py` — reescritura completa: sin secciones capital, paper-trading only
- `scripts/run_reversals.py` — `--capital-ars` optional
- `tests/test_suppression.py` — eliminada `TestSizingCap`; actualizados helpers `Position`
- `tests/test_liquidity.py` — reescritura para ADV-floor gate
- `tests/test_reversal_report.py` — reescritura para paper-trading report

## 29 — 2026-09-07: Umbral de tolerancia en Part B — SCALE_IN_TOLERANCE_PCT = 0.02

**Contexto:** El análisis de la sesión 2026-09-07 mostró que Part B (open-position awareness) suprimía el 31% de las señales recientes, ralentizando el ritmo hacia n=40 de ~1,5 a ~2,2 meses. El 100% de los pares bloqueados eran movimientos dentro del rango −2,66% a 0% vs. la entrada previa.

**Distribución empírica de todos los pares mismo-ticker con posición abierta (corpus completo):**

| Symbol | Diff% | Gap | check_recent cubre? |
|--------|-------|-----|---------------------|
| BYMA.BA | −2.66% | 10d | **no** (fuera de ventana 7d) |
| COST.BA | −1.56% | 4d | sí |
| JD.BA | −1.51% | 1d | sí |
| DECK.BA | −1.35% | 4d | sí |
| AMX.BA | −1.13% | 1d | sí |
| DECK.BA | −0.81% | 1d | sí |
| NGG.BA | −0.47% | 1d | sí |
| AMX.BA | −0.43% | 1d | sí |
| VOD.BA, TTE.BA, EBAY.BA, DECK.BA | 0.00% | 1-2d | sí |

Scale-ins legítimos (entrada > previa): +0.25%, +0.29%, +2.74%, +3.03%.  
**Gap observado entre el peor bloqueo y el scale-in más pequeño: −2.66% vs +0.25%.**

**Umbral adoptado: `SCALE_IN_TOLERANCE_PCT = 0.02` (2%)**

Base empírica: el máximo de diferencias negativas excluida BYMA es −1.56%. El corte en 2% deja 44 bps de buffer sin tocar el único caso genuinamente fuera de la red de check_recent().

**Lógica de tres rangos resultante:**

```
entry > open_price                        → scale-in (tesis reconfirmada)
open_price × 0.98 < entry ≤ open_price   → scale-in (ruido de día a día)
entry ≤ open_price × 0.98                → bloqueado (deterioro material)
```

El rango medio se clasifica como scale-in (no nueva posición) para evitar que `signal_registry.record_signals()` intente `open_position()` sobre un ticker con posición ya abierta — lo cual fallaría silenciosamente y dejaría el reporte inconsistente con positions_log.

**El costo del umbral — caso BYMA:**

Con el umbral de 2%, BYMA del 2026-08-03 (−2.66%, 10d gap) sigue bloqueado. Esto excluye ese outcome del corpus de calibración. El outcome fue stop_hit — un negativo real.

Esto NO es gratis. Filtrar outcomes negativos sesga el corpus exactamente igual que filtrar positivos. La decisión es aceptable por dos razones:
1. −2.66% con 10 días de gap es deterioro material, no ruido diario. Es el tipo de caso que Part B debe cubrir.
2. check_recent() no lo hubiera marcado (gap > 7d), así que el bloqueo no es redundante.

Si el umbral se subiera a 3%, BYMA también pasaría y Part B perdería toda cobertura exclusiva. Ese tradeoff se rechazó explícitamente.

**Qué cambió respecto a #28:** el umbral de 0% (bloqueo en toda entrada ≤ previa) se reemplazó por 2% (bloqueo solo en deterioro material). La igualdad de precio pasa ahora como scale-in, no como bloqueado.

**Exclusión de señales `tradeable=False` de `assess_outcomes()`:** implementada en la misma sesión. El corpus de calibración solo debe reflejar lo que el sistema efectivamente tomaría. Señales suprimidas (tradeable=False) no se tomaron; sus outcomes no miden la calidad del detector, sino la calidad del supresor — pregunta distinta.

**Archivos modificados:**
- `analysis/reversal/suppression.py` — `SCALE_IN_TOLERANCE_PCT = 0.02`, tres rangos en `check_open_position()`
- `analysis/reversal/outcome_tracker.py` — filtro `tradeable=True` en `assess_outcomes()`
- `tests/test_suppression.py` — tests de borde de tolerancia (equal, within, at-floor, below-floor)

## 30 — 2026-09-10: yfinance publicación next-day para tickers .BA — fail-closed y corrección de corpus

### Descubrimiento

Al investigar si el scan del 2026-09-10 (18:51 ART) usó el cierre correcto para VALO.BA, se confirmó que yfinance publica los bars de tickers .BA el **día hábil siguiente**, no el mismo día. A las 18:51-18:53 ART del 10-sep, los 255+ tickers .BA en cache tenían 2026-09-09 como último bar — sin excepción.

Evidencia directa: parquets COST_BA, DAL_BA, FDX_BA, PG_BA, ROST_BA, SATL_BA, VALO_BA escritos a las 18:51-18:53 del 10-sep con `last_bar = 2026-09-09`. A las 21:34 ART del 09-sep (4.5h post-cierre), el bar del 09-sep también estaba ausente. A las 09:05 ART del 02-sep (mañana), el bar del 01-sep SÍ estaba disponible.

**Ventana de publicación empírica:** entre las 21:34 ART del día D y las 09:05 ART del día D+1.

### Alcance — 13/13 señales post-fix stale

Decision #27 (2026-09-02) corrigió `prices_are_fresh()` para exigir el bar de hoy después de las 17:15 ART. El fix funcionó: el cache detectaba staleness y pedía re-fetch. Pero yfinance devolvía el bar de T-1 de todos modos. Las 13 señales publicadas con `scan_date >= 2026-09-03` y `tradeable=True` usaron cierre de T-1 sin excepción:

| Ticker | scan_date | entry_ars (T-1) | close(scan_date) real |
|--------|-----------|-----------------|----------------------|
| JD, COST, FDX | 2026-09-03 | T-1 | distinto |
| COST | 2026-09-07 | T-1 (04-sep) | distinto |
| COST, SATL | 2026-09-08 | T-1 (07-sep) | distinto |
| ROST, COST, FDX | 2026-09-09 | T-1 (08-sep) | distinto |
| COST, VALO, PG, DAL | 2026-09-10 | T-1 (09-sep) | N/A aún |

Decision #27c definió este corpus como "limpio por construcción". Esa premisa es falsa — todos los registros llevan `price_staleness_risk: "confirmed_stale"` desde esta decisión.

### Fix 1: fail-closed en `data/fetcher.py`

`_fetch_prices_with_fallback()` ahora valida el último bar de yfinance contra `_last_expected_trading_day()` antes de persistir. Si el bar no corresponde, devuelve `(None, FetchStatus.MISSING, False)` — el scanner omite el ticker con un `ERROR` explícito. No se escribe el dato stale al cache.

**Comportamiento en corrida nocturna (>17:15):** el gate exige el bar de hoy. yfinance no lo tiene. → MISSING por ticker. El scan aborta esas señales limpiamente en lugar de publicar precios de ayer.

**Comportamiento correcto:** correr el scan antes de las 17:15 ART (pre-apertura, ~08:45). A esa hora `_last_expected_trading_day()` devuelve T-1 y yfinance SÍ tiene el bar de T-1 disponible. Semántica resultante: "señal del día X basada en cierre de X-1" — consistente con cómo se ejecutaría el trade (al abrir de X).

**Fallback de red intacto:** si yfinance falla por error de red (devuelve None), el flujo sigue cayendo al cache stale como antes. El fail-closed solo aplica cuando yfinance responde con éxito pero devuelve datos desactualizados.

### Fix 2: corrección de semántica de corpus near_misses

El script `backfill_near_miss_prices.py` usaba `close(scan_date)` como `entry_price_ars` para los registros históricos (pre-2026-09-03). Esto era inconsistente: el scanner evaluó los criterios sobre T-1 data, entonces el entry hipotético del near-miss también debería ser T-1.

**Inconsistencia interna:** criterios sobre T-1, entry sobre T+0. Un near-miss con entry T+0 representa un precio que el scanner nunca observó.

**Impacto cuantificado del offset (143 registros):**

| Métrica | T+0 original | T-1 corregido | Δ |
|---------|-------------|---------------|---|
| win_rate | 25.2% | 22.8% | −2.4 pp |
| avg_win | +6.83% | +6.67% | −0.16 pp |
| avg_loss | −4.59% | −4.55% | +0.04 pp |
| **EV** | **−1.71%** | **−1.98%** | **−0.27 pp** |

El offset inflaba el EV de los near-misses (tu hipótesis era correcta): el entry T+0 más bajo producía targets más fáciles y pérdidas porcentuales mayores (denominador menor con stop fijo). La corrección empeora el EV en 0.27 pp.

### Corrección de la conclusión de Decision #27c

Decision #27c comparó near-misses (ago-sep) contra señales publicadas (jun-sep completo). El período incompleto inflaba el EV de las publicadas por las ganadoras de jun-jul.

**Comparación apples-to-apples (ago-sep, corpus post-rebackfill):**

- Señales publicadas (ago-sep): EV ≈ −1.87%
- Near-miss rsi_out_of_range: EV ≈ −2.01%
- Near-miss no_catalyst: EV ≈ −1.94%

**Conclusión corregida: empate dentro del ruido.** No hay ventaja detectable de las señales publicadas sobre los near-misses en el período comparable. Decision #27c sobreestimó la diferencia por confounding de régimen de mercado.

La implicación para calibración de gates: las decisiones deben basarse en corpus futuro post-fix (scan pre-apertura, datos T-1 limpios), no en el corpus pre-2026-09-10.

**Archivos modificados:**
- `data/fetcher.py` — fail-closed en `_fetch_prices_with_fallback()`: valida último bar post-fetch
- `data/reversal_tracking/signals.jsonl` — 13 registros `scan_date >= 2026-09-03` marcados `price_staleness_risk: "confirmed_stale"`
- `data/reversal_tracking/near_misses.jsonl` — 144 registros pre-2026-09-03 re-backfilleados con entry T-1 (34 sin parquet disponible quedan sin cambio)
- `data/reversal_tracking/near_miss_outcomes.jsonl` — regenerado con los entries corregidos
- `scripts/rebackfill_near_miss_t1.py` — script de re-backfill (idempotente)
- `tests/test_fetcher_fail_closed.py` — 6 tests del fail-closed (stale→MISSING, fresh→OK, pre-gate→OK, T-2→MISSING, red-failure→STALE)

## 31 — 2026-09-12: A1 R-múltiplo + A2 descomposición FX + A3 snapshot de régimen — Fase A del roadmap de confiabilidad

Implementación conjunta de los tres campos aditivos definidos en
`docs/ROADMAP_CONFIABILITY.md` Fase A. Ninguno modifica scoring, gates,
umbrales, definición de outcome, ni `pct_change`. Todos se **registran ahora**
para que cuando el corpus limpio post-2026-09-11 se llene, ya lleven la
información que después no se puede reconstruir sin resetear.

### El diagnóstico que motiva la fase

1. **Outcomes no comparables** — stops de 1,4% mezclados con stops de 11%. Un
   `stop_hit` registrado como igual en ambos casos costó 8× más en uno que en
   otro. Promediar `pct_change` sobre ese mix no significa nada.
2. **Contaminación FX** — el ARS de un CEDEAR mezcla el movimiento del activo
   (USD) con el del peso (CCL). Un "rebote MA200" en ARS puede ser
   principalmente devaluación.
3. **Régimen no registrado** — se sabe post-hoc que jun-jul rindió positivo y
   ago-sep no, pero sin un snapshot por corrida no se puede correlacionar
   outcomes contra el régimen que los produjo.

### A1 — Normalización por riesgo (R-múltiplo)

`R = (exit − entry) / (entry − invalidation)` — un stop tocado exacto es −1R
sin importar la distancia inicial. Un target que gana el doble del riesgo es
+2R. Registrado en `outcomes.jsonl` y `near_miss_outcomes.jsonl` como
`r_multiple`, con `r_multiple_skip_reason` explícito cuando no se puede
computar. Fuente única de la fórmula en `analysis/reversal/r_multiple.py` —
ningún consumidor la reimplementa.

**Decisión: lateral con exit al deadline (opción B)** — cuando `outcome ==
"lateral"`, se registra `exit_price_ars_at_deadline` = close del último bar
dentro de la ventana de 20 días. R se computa contra ese precio. `pct_change`
sigue null (preserva la semántica histórica). Aditivo: no cambia la
definición de `lateral`, agrega un campo nuevo. Convierte "asumimos 0" en
"esto valió".

**Decisión: skip_reason explícito para denominador inválido** — los 2
artefactos pre-fix (TMUS.BA 2026-06-30, ADGO.BA 2026-08-03) con
`invalidation >= entry` quedan con `r_multiple = null` y
`r_multiple_skip_reason = "invalid_denominator"`. Nunca un número engañoso,
nunca un null silencioso.

**Backfill retroactivo** (`scripts/backfill_r_multiple.py`, idempotente):

| Archivo | Total | R computado | Null (motivo) |
|---|---|---|---|
| `outcomes.jsonl` | 45 | 43 | 2 `invalid_denominator` |
| `near_miss_outcomes.jsonl` | 267 | 183 | 84 `no_exit_data` (pending/unresolved) |

Distribución de R sobre `outcomes.jsonl` (n=43):
```
min=-3.43  P10=-1.45  median=-1.05  P90=+3.79  max=+8.90  mean=+0.48
  lateral      n=  3  mean=+0.07R  median=+0.27R  ← antes de A1: NA
  stop_hit     n= 24  mean=-1.36R  median=-1.19R
  target_5pct  n= 10  mean=+1.77R  median=+1.33R
  target_8pct  n=  6  mean=+5.92R  median=+6.54R
```

**Lectura corregida del EV** sobre 42 outcomes resueltos (stop+target):
`mean pct_change = +0.94%` vs `mean R-múltiplo = +0.51R`. La lectura por R es
más estable — no la contamina un stop excepcionalmente ancho ni una ganancia
sobre un stop excepcionalmente angosto.

Los stops se dispersan debajo de −1R (mediana −1,19R) porque el motor mide el
stop contra el `low` intradiario (`outcome_tracker._assess_signal` línea 147):
un stop que barre el nivel puede cerrar en −1,3R. Es la asimetría documentada
del assessment (low para stop, close para target), NO un bug — se mantiene.

### A2 — Descomposición cambiaria

Para cada opportunity CEDEAR se registra al momento del scan un bloque
`fx_context` en `signals.jsonl`:

```json
"fx_context": {
  "ccl_at_scan": 1596.05,
  "underlying_symbol": "AAPL",
  "cedears_per_underlying": 20.0,
  "pct_change_ars_5d":  0.0465,   "pct_change_ars_20d":  0.1025,
  "pct_change_ccl_5d":  0.0097,   "pct_change_ccl_20d":  0.0162,
  "pct_change_usd_implied_5d":  0.0364,
  "pct_change_usd_implied_20d": 0.0849
}
```

**Decisión: solo USD implícito (opción A)** — `(1 + pct_ars) / (1 + pct_ccl)
− 1`. No se fetchea el underlying USD real. Cubre la pregunta central "cuánto
del setup fue FX vs asset" con costo cero (CCL ya está en el bundle vía
`bundle.ccl_series.data`). El spread CEDEAR/ADR queda para Fase C si se
demuestra que aporta señal.

**Decisión: ambas ventanas (5d y 20d)** — 5d porque los catalizadores que
disparan la señal se forman en días (RSI divergence, velas de reversión), 20d
por simetría con la ventana de outcome. No es una decisión que cueste elegir
mal: 2 columnas extra, sin fetch. Fase B decide después cuál importa más.

**Alineación CCL** — las lookups CCL usan **las mismas fechas calendario**
que los bars ARS (no "5 días calendario atrás"). Sin esto, fines de semana y
feriados contaminan el ratio. El helper `_ccl_pct_change_aligned` en
`analysis/reversal/fx_context.py` implementa esta alineación explícitamente.

Argentine stocks: `fx_context` ausente del record (A2 no aplica). Consumers
deben tolerar el campo faltante.

### A3 — Snapshot de régimen

Archivo nuevo `data/reversal_tracking/regime_snapshots.jsonl`, un registro
por scan_date:

```json
{"scan_date": "2026-09-12", "prev_scan_date": null,
 "n_universe_total": 391, "n_universe_ma200_eligible": 279,
 "pct_below_ma200": 0.3047, "median_rsi_14": 42.12,
 "delta_median_rsi_prev": null, "n_opportunities_published": 3}
```

Métricas cheap-to-compute sobre bundles ya en memoria post-fetch: `%
universo < MA200`, `mediana RSI(14)`, y su delta contra la corrida anterior.

**Decisión: archivo aparte, no campo embebido** — la granularidad natural es
por-scan, no por-señal. Embebido serían 5 copias del mismo número por
corrida. El archivo aparte deja el join `outcomes ⋈ regime_snapshots on
scan_date` como la representación natural para Fase B.

**Decisión: registrar en corridas de cero opportunities** — un régimen que
no produce señales es exactamente lo que la Fase C va a mirar. Sin el
registro, no se puede distinguir "no hay setups" de "el filtro está roto".

**Decisión: incluir `prev_scan_date`** — el delta contra hace 3 días
(weekend, sin corrida) no significa lo mismo que contra ayer. Registrar el
scan_date previo hace el delta interpretable.

**Decisión: respetar `record=False`** — el snapshot va dentro del
`if record:` block junto con `record_signals`. Los tests unitarios verifican
que no se escribe archivo cuando el scan corre en modo test/dry.

### Disciplina de aislamiento (transversal)

Los tres enriquecimientos van en `try/except` con `logger.warning`, siguiendo
el patrón ya establecido por `analyst_revision` y `news_check`
(`reversal_scanner.py`). Si cualquiera falla, el scan continúa y publica
igual — no bloquea la ejecución.

### Impacto en tiempo de corrida

Los tres agregados suman <1s por scan (medido). Ninguno toca el path caliente
de evaluación de bundles — todos corren post-cap, sobre los ≤5 opportunities
publicadas o (en A3) una pasada vectorizada sobre los 391 bundles.

### Reglas del roadmap respetadas

- **No se cambia la vara** — `pct_change`, `outcome`, gates, scoring, umbrales
  y criterio de publicación quedan idénticos. Todo es aditivo.
- **Registrar ahora, decidir después** — los tres campos existen antes de que
  el corpus limpio se llene. Ninguno prejuzga si su información aporta EV.
- **Backfill sin resetear** — R se computa retroactivamente sobre los 226
  outcomes ya existentes usando solo campos que ya estaban en el archivo.

### Archivos modificados

**Nuevos:**
- `analysis/reversal/r_multiple.py` — helper compartido (A1)
- `analysis/reversal/fx_context.py` — enrichment por opportunity (A2)
- `analysis/reversal/regime_snapshot.py` — snapshot + I/O idempotente (A3)
- `scripts/backfill_r_multiple.py` — one-shot backfill retroactivo
- `data/reversal_tracking/regime_snapshots.jsonl` — archivo nuevo generado
- `tests/test_r_multiple.py` — 10 casos
- `tests/test_fx_context.py` — 7 casos (CEDEAR full/partial, alineación CCL, argentine, sin CCL, sin prices)
- `tests/test_regime_snapshot.py` — 6 casos (universo mixto, sin/con prior, idempotencia, load_prior_snapshot)

**Modificados:**
- `analysis/reversal/outcome_tracker.py` — `_assess_signal` captura
  `exit_price_ars_at_deadline` para lateral y setea `r_multiple` +
  `r_multiple_skip_reason` en todos los outcomes
- `analysis/reversal/near_miss_outcomes.py` — fallback de excepción incluye
  los campos R para uniformidad de schema
- `analysis/reversal/signal_registry.py` — `record_signals` acepta nuevo
  parámetro `fx_enrichments`; merge simétrico al de `analyst_revision`
- `analysis/reversal/reversal_scanner.py` — dos bloques nuevos dentro de
  `scan_reversals`: FX enrichment (post-cap, pre-record) y regime snapshot
  (dentro del `if record:` que agrupa `record_signals`, se dispara con
  cualquier número de opportunities incluido cero)
- `data/reversal_tracking/outcomes.jsonl` — 45 registros enriquecidos con R
- `data/reversal_tracking/near_miss_outcomes.jsonl` — 267 registros enriquecidos con R

### Nota de backfill — signals 2026-09-12

Los 3 signals de `scan_date: 2026-09-12` (COST.BA, PYPL.BA, FDX.BA) son **pre-A2**:
el scanner corrió a las 13:06 y el merge de A2 ocurrió a las 13:59 del mismo día.
Sus registros en `signals.jsonl` no tenían `fx_context`.

Backfill realizado el 2026-09-12 usando exactamente `build_fx_enrichment` de
`analysis/reversal/fx_context.py` (misma función, sin reimplementación). Los datos
de precios y CCL usados son los del mismo día (barras diarias; los cierres de días
anteriores no varían). Valores resultantes: todos los campos poblados, ningún null.

Para distinguirlos de los records "live", llevan `fx_context_source: "backfill"`.
Los signals posteriores generados por el scanner en vivo no llevan este campo.

## 32 — 2026-09-13: Capa de consulta DuckDB sobre los JSONL de tracking — prerequisito Fase B

**Contexto:** La Fase B del roadmap de confiabilidad (ROADMAP-confiabilidad.md) requiere consultas analíticas sobre los .jsonl de tracking: EV por gate, comparación near-miss vs publicadas, distribución de R por catalizador, cruce con regime_snapshots. Cada consulta se resolvía con un script Python ad-hoc. La decisión es NO migrar el almacenamiento (los .jsonl siguen siendo la fuente de verdad, son diffeables en git, son append-only) y agregar una capa de consulta encima sin materializar ni duplicar datos.

**Herramienta:** DuckDB 1.4.5 (`duckdb>=1.0.0` en requirements.txt). Lee los .jsonl con `read_json_auto` sin importar nada. Compatible con pandas 2.x y pyarrow 14.x ya presentes (zero-copy vía Arrow). Sin conflictos con el stack existente.

**Archivo:** `analysis/query.py` — módulo de solo lectura. No hay archivo DuckDB persistente. Ningún consumidor puede escribir a los JSONL desde SQL.

**Decisiones de diseño tomadas:**

1. **Schema drift** (`sample_size=-1, union_by_name=true`): los .jsonl tienen campos heterogéneos entre registros tempranos y tardíos (analyst_revision, fx_context, adv_ars_at_scan solo en los tardíos). Con `sample_size=-1` DuckDB escanea todos los registros para inferir el schema, y `union_by_name` merges los conjuntos de columnas. Campos ausentes en un registro → NULL. No se truncan columnas.

2. **Columna `margins` en near_misses**: keys heterogéneas según el gate (`hypothetical_score` para no_catalyst; `rsi_value + rsi_gap` para rsi_out_of_range; `vol_ratio + vol_ratio_gap` para vol_ratio_high). Se forza a JSON VARCHAR con `REPLACE (margins::VARCHAR AS margins)` para que la vista no rompa cuando se agreguen nuevos gates con nuevas keys. Extracción: `(margins->>'rsi_gap')::DOUBLE`.

3. **Macro `is_safe(staleness_risk)`**: replica `_is_safe()` de `near_miss_outcomes.py` (Decision #27). NULL o 'safe' → confiable. Nunca reimplementar el criterio inline en las queries.

4. **Corpus post-fix**: `is_safe(price_staleness_risk) AND scan_date >= '2026-09-11'`. La fecha ancla (`CACHE_FIX_DATE = '2026-09-11'`) replica `_CACHE_FIX_DATE` de `near_miss_outcomes.py` y excluye la ventana 2026-09-03 a 2026-09-10 donde NULL no significa safe (Decision #30).

5. **Dedup no replicado en DuckDB**: la lógica `_is_exposure_duplicate()` del script Python (mismo ticker dentro de 7 días con <3% movimiento de precio) no se implementa en SQL — requeriría una self-join con ventana temporal y comparación de precio. Efecto: DuckDB n es ~9% mayor que el script Python deduped. Documentado en el módulo; el script Python sigue siendo autoritativo para métricas dedup-correctas.

6. **Dos variantes para catalizadores**: `Q_CATALYST_PERFORMANCE` (UNNEST, una fila por catalizador — "¿qué catalizador predice mejor?") y `Q_SIGNAL_PERFORMANCE` (sin UNNEST, una fila por señal — totales y win_rate agregado). Mezclarlas da números incorrectos; están nombradas y documentadas para no confundirlas.

**Queries canónicas implementadas:**
- `Q_GATE_EV` — EV y R por gate (near_miss corpus), con filtro de período y staleness. Query principal de Fase B.
- `Q_PUBLISHED_VS_NEAR_MISS` — near-miss vs publicadas restringida al mismo rango de fechas. Fix del confounding de régimen que inflaba el EV de publicadas en Decision #27c.
- `Q_CATALYST_PERFORMANCE` — distribución de R por catalizador (UNNEST).
- `Q_SIGNAL_PERFORMANCE` — win_rate y R agregados por señal (sin UNNEST).
- `Q_STOP_OVERSHOOT` / `Q_STOP_OVERSHOOT_AGG` — R en stop_hit por ticker, catalizador y distancia al stop.
- `Q_REGIME_CORRELATION` / `Q_REGIME_CORRELATION_DETAIL` — outcomes cruzados con regime_snapshot del scan_date (JOIN sobre INNER; se pobla a medida que los 3 signals del 12/09 resuelvan).
- `Q_PENDING_BIAS_CHECK` / `Q_PENDING_BIAS_BY_PERIOD` — control de sesgo: compara pending vs resueltos por catalizador, período y distancia al stop.

**Validación contra números históricos:**

| Query | Referencia | DuckDB | Match |
|---|---|---|---|
| R-múltiplo total (outcomes) | Decision #31: n=43, mean=+0.48R, median=−1.05R | n=43, mean=0.48, median=−1.05 | ✅ exacto |
| stop_hit | Decision #31: n=24, mean=−1.36R | n=24, mean=−1.36 | ✅ exacto |
| target_5pct | Decision #31: n=10, mean=+1.77R | n=10, mean=1.77 | ✅ exacto |
| target_8pct | Decision #31: n=6, mean=+5.92R | n=6, mean=5.92 | ✅ exacto |
| Gate EV (safe-only sin anchor) | Decision #27c: rsi n=13, no_cat n=12 | rsi n=36, no_cat n=34 (raw, sin dedup; corpus creció) | ✅ dirección consistente, diferencia = dedup + crecimiento del corpus |

**Hallazgo del Q6 (bias check):**
Todos los pending/unresolved son de 2026-09 — esperado (ventana de 20 días no vencida). Los pending de MA200 bounce/proximity tienen stop_dist promedio mayor (3.65% vs 2.59% resueltos), lo que sugiere que el corpus de septiembre tiene stops más anchos. No indica sesgo de selección, sí diferencia de régimen vs los resueltos de jun-ago.

**Archivos modificados:**
- `analysis/query.py` — nuevo módulo
- `requirements.txt` — `duckdb>=1.0.0` agregado

## 33 — 2026-09-15: Gap de composición en A3 — `n_rsi_eligible` y anotación del snapshot inaugural

**Contexto:** En el análisis post-corrida del 2026-09-15 se detectó que `median_rsi_14` y `n_universe_ma200_eligible` en `regime_snapshots.jsonl` se computan sobre poblaciones distintas. `n_universe_ma200_eligible` requiere ≥200 barras; `median_rsi_14` incluye cualquier bundle con `FetchStatus.OK` y suficientes barras para RSI (~15). El snapshot solo registraba el conteo de la población MA200, dejando el delta inter-corrida de RSI no interpretable: un salto puede ser movimiento de mercado o cambio de composición del denominador.

Caso concreto: entre el snapshot del 12/09 (`n_universe_ma200_eligible=279`) y el del 15/09 (`n_universe_ma200_eligible=246`) hubo una diferencia de 33 tickers en la población MA200. El `delta_median_rsi_prev=+8.39` no es atribuible exclusivamente a movimiento de mercado sin saber si la población RSI también cambió — y en qué magnitud.

**Aplica el principio de Fase A:** el conteo tiene que existir al momento del snapshot. Los snapshots anteriores no se pueden reconstruir sin los bundles originales.

### Fix — `n_rsi_eligible`

Campo nuevo en `compute_snapshot` (`regime_snapshot.py`): número de bundles que contribuyeron a `median_rsi_14`. Se registra como `len(rsi_values)` antes de computar la mediana, inmediatamente después de `median_rsi_14` en el dict de salida.

```json
{"scan_date": "2026-09-16", ..., "median_rsi_14": 48.3, "n_rsi_eligible": 296, "delta_median_rsi_prev": -2.21, ...}
```

Con ambos conteos en el snapshot, Fase B puede distinguir: si `n_rsi_eligible` cae entre dos corridas y el delta RSI sube, la causa probable es composición. Si `n_rsi_eligible` es estable, el delta refleja movimiento real.

**Decisión: `n_rsi_eligible` solo — sin hash de símbolos.**
Tres opciones evaluadas:

| Opción | Detecta cambio | Detecta magnitud | Costo por corrida |
|---|---|---|---|
| `n_rsi_eligible` | ✅ (si el conteo difiere) | ✅ | 1 entero |
| Hash del conjunto | ✅ (cualquier cambio) | ❌ | 1 string ~40 chars |
| Lista de símbolos | ✅ | ✅ | ~200-300 strings |

El hash detecta "cambió algo" pero no cuánto, y seguiría requiriendo el conteo para interpretar el delta RSI. La lista es excesiva para el uso previsto (correlación de régimen en Fase B). `n_rsi_eligible` es suficiente: con el conteo se puede estimar el impacto de composición, y los bundles por scan_date están implícitamente en `near_miss_outcomes.jsonl` si se necesita reconstruir.

### Anotación del snapshot inaugural

El snapshot del 2026-09-12 tiene `prev_scan_date: null` y fue el primero en registrarse, durante la implementación de A3. Las poblaciones de fetch de ese run no son verificables (posible estado de datos distinto al de una corrida normal). Se anota con `generated_during_implementation: true` — no se elimina, misma política de anotar en vez de reescribir.

Los snapshots del 2026-09-12 y 2026-09-15 quedan sin `n_rsi_eligible` (no se puede reconstruir retroactivamente). Los consumidores que calculen deltas RSI deben verificar que ambos snapshots del par tienen `n_rsi_eligible` presente antes de interpretar el delta.

### Archivos modificados

- `analysis/reversal/regime_snapshot.py` — `n_rsi_eligible` en `compute_snapshot`
- `data/reversal_tracking/regime_snapshots.jsonl` — `generated_during_implementation: true` en el entry del 2026-09-12
- `tests/test_regime_snapshot.py` — 2 assertions nuevas sobre `n_rsi_eligible`

---

## 34 — 2026-11-18: Refresh del universo (BYMA 2026-11-12) + override YAML de underlyings

**Contexto:** BYMA publicó un nuevo listado de CEDEARs (2026-11-12). El refresh estaba bloqueado por la deuda técnica de la entrada 2026-08-13 (`DECISIONS.md` raíz): regenerar el snapshot pisaba los 7 `symbol_underlying` corregidos a mano.

**Decisión:**
1. `data/sources/yfinance_ticker_overrides.yaml` pasa a ser la única fuente de mapeos código BYMA → ticker Yahoo cuando no coinciden. `refresh_universe.py` lo aplica después de parsear el PDF y avisa si un override apunta a un código que ya no existe en el universo. No se edita más `universe_snapshot.json` a mano.
2. `WEAT` (Teucrium Wheat Fund, commodity ETF) se agrega a `_KNOWN_ETF_CODES`: ningún marcador de nombre lo detecta.
3. Universo regenerado: 391 → 403 tickers (382 CEDEARs + 21 argentinas).
   - **Altas (14):** DELL, GEV, IBKR, KLAC, LIN, MS, NTRA, NU, PLD, SHW, SKHY, TLN, WDC, WELL. Todos verificados con precio en Yahoo (`.BA` y underlying); el CCL implícito (~1710) es consistente en todos, así que los ratios del PDF son correctos.
   - **Bajas (2):** TEFO (Telefónica) y UN. Hallazgo: `UN.BA` era el código BYMA de **NU Holdings**, no de Unilever como asumió la entrada 2026-08-13. BYMA lo renombró a `NU`. Las entradas viejas de `UN`/`UN.BA`/`TEFO`/`TEFO.BA` en `yfinance_exclusions.json` quedan huérfanas pero no hacen daño.

**Alternativas consideradas:** Volver a corregir los 7 a mano después de cada refresh: descartado, se rompe sin aviso y es justo el problema que generó la deuda.

**Estado:** Activa.

---

## 35 — 2026-11-20: Integridad de corrida del scanner de reversiones — dry-run, health gate, barra intradiaria, `run_failed` y `data_date`

**Contexto:** La auditoría del 2026-11-20 encontró que `scripts/run_reversals.py` registraba corridas que no debían contar, en un corpus post-fix chico (n≈24–44) donde cualquier corrida espuria contamina la medición:

- **Corridas fallidas registradas como "0 oportunidades".** Las del 2026-11-09 (22:03 ART) y 2026-11-18 (23:34 ART) corrieron después de las 17:15: el fetcher exige la barra de hoy, yfinance la publica recién el día hábil siguiente (#30) y todo el universo quedó MISSING. Se grabaron igual, con un snapshot de régimen vacío. `fetch_summary` se calculaba pero no se usaba para abortar.
- **El snapshot fallido contaminaba los siguientes.** `append_snapshot` es idempotente por scan_date, así que un snapshot fallido bloquea al válido de ese día. Además, `load_prior_snapshot` lo tomaba como previo: el 11-20 quedó con `delta_median_rsi_prev = null`.
- **NaN en el JSONL.** El 09-18 tiene `NaN` literal en `median_rsi_14` y en el delta, y el delta del 09-19 lo heredó. La causa es que `compute_snapshot` no aplicaba el ffill que sí aplica el scanner: un solo cierre NaN anulaba la mediana de todo el universo. Además, un MA200 NaN contaba en silencio como "arriba de MA200" (`last < NaN` da False).
- **Cobertura de commits.** `_TRACKING_FILES` no incluía `regime_snapshots.jsonl` ni `near_miss_outcomes.jsonl`, que quedaban sin versionar después de cada corrida.
- **`--sample` registraba.** Escribía signals y near-misses, abría posiciones paper y commiteaba.
- **scan_date ≠ fecha de los datos.** Desde #30, la señal del scan_date X usa el cierre de X-1. Una corrida de fin de semana y la del lunes pre-apertura leen el mismo cierre del viernes. Hay 3 duplicados históricos: DECK 08-08/08-10 y EBAY+DECK 08-23/08-24.
- **Ventana horaria mal documentada.** El docstring y el mensaje de error del script decían "correr después de las 17:15", que es justo la ventana en la que el fetch falla.

**Decisión:**

1. **`--dry-run`.** Escanea y genera el reporte en `output/reversiones_<fecha>_dryrun.md`, sin pisar el oficial. No escribe tracking, no abre posiciones paper, no actualiza near_miss_outcomes y no commitea. `--sample` implica dry-run y lo avisa con un warning.
2. **`--force` sigue registrando**, con el chequeo del punto 4. Solo saltea el gate de horario de mercado (#20) y emite un warning explícito.
3. **Health gate previo al scan.** Se calcula la proporción de tickers usables (OK+PARTIAL) sobre el universo esperado. El denominador excluye los tickers de `yfinance_exclusions`, que son MISSING por diseño, así que se mide contra un universo sano y no contra el 100%. Si la proporción queda bajo `MIN_USABLE_RATIO`, la corrida aborta con exit 2 antes de escanear: sin registros, sin snapshot y sin commit. El mensaje incluye los conteos, la causa probable y la ventana válida. En dry-run solo advierte. El umbral es una constante del script en calibración pendiente y no se documenta acá.
4. **Chequeo de barra intradiaria, en todas las corridas** (incluidas `--force` y dry-run). Si algún bundle usado (OK/PARTIAL/STALE) tiene una barra con fecha de hoy (ART), la corrida aborta fail-closed con exit 3: puede ser un snapshot intradiario y no un cierre oficial.
5. **Ventana válida documentada:** día hábil antes de las 11:00 ART (pre-apertura) o fin de semana. Se corrigieron el docstring del script, el mensaje de `_check_market_hours` y el log del fetcher.
6. **Snapshot de régimen:**
   - Un snapshot con `n_universe_ma200_eligible == 0` no se persiste.
   - `load_prior_snapshot` ignora las entradas con `run_failed: true`.
   - La salida es JSON estricto: los no finitos se graban como `null`.
   - **Cambia la definición del snapshot hacia adelante:** los cierres se ordenan y se les aplica ffill igual que en `_compute_metrics`. Un MA200 o RSI que siga sin ser finito se excluye de su agregado; nunca cuenta como "arriba de MA200". El campo nuevo `n_nonfinite_excluded` cuenta los bundles afectados, cada uno una sola vez. Los snapshots anteriores no se recalculan.
7. **Fix de datos históricos** (anotar, no reescribir; no se borra ninguna línea):
   - `run_failed: true` en las entradas 2026-11-09 y 2026-11-18.
   - `NaN` → `null` en `median_rsi_14` y `delta_median_rsi_prev` del 2026-09-18, y en `delta_median_rsi_prev` del 2026-09-19.
   - El 2026-11-20 no se recalcula: se anota con `prev_run_failed: true`.
8. **`_TRACKING_FILES`** suma `regime_snapshots.jsonl` y `near_miss_outcomes.jsonl`. `positions_log.json` queda afuera a propósito. El staging sigue siendo con paths explícitos.
9. **`data_date`.** Es la fecha de la última barra usada (moda entre los bundles OK/PARTIAL). Se graba como campo nuevo en signals, near_misses y regime_snapshots; scan_date no cambia. `record_signals` no vuelve a registrar un `(data_date, symbol)` que ya existe bajo otro scan_date: no crea registro ni abre posición paper, y loguea el skip. Los registros históricos sin `data_date` no participan del dedup. Si `data_date` difiere del último día hábil esperado (por ejemplo, un feriado BYMA), se loguea un warning.

**Alternativas consideradas:**
- *`--force` ⇒ dry-run:* descartada. La corrida forzada del 11-05 (13:24 ART) usó cierres T-1 limpios y era válida. El riesgo real de #20 es la barra intradiaria, y el punto 4 lo cubre en todas las corridas.
- *Health gate contra el 100% del universo:* descartada. Los ~90 tickers excluidos son MISSING por diseño y harían fallar toda corrida sana.
- *Reemplazar el snapshot fallido del mismo día en lugar de no escribirlo:* descartada. Rompe el append-only; no persistirlo es más simple y deja el scan_date libre.
- *Recalcular el delta del 11-20 contra el 11-06:* descartada. Reescribiría un valor calculado; se anota con `prev_run_failed`.
- *Cambiar scan_date a la fecha de los datos:* descartada. Rompe la continuidad del corpus y de las claves `(scan_date, symbol)`; se agrega `data_date` como campo aparte.
- *Serializar NaN como null sin ffill:* descartada. Ocultaría el síntoma, pero un solo hueco seguiría anulando la mediana del universo.

**No incluido (pendiente):** `outcome_tracker` evalúa barras con `> scan_date`, así que la rueda de entrada real (scan_date) no se mide. Corregirlo cambia la vara de medición; se instrumenta primero (`entry_bar_date`, `next_open_ars`) y se decide después.

**Archivos modificados:**
- `scripts/run_reversals.py` — `run(args) -> int`, `--dry-run`, health gate, chequeo intradiario, `data_date`, `_TRACKING_FILES`, docstring y mensajes
- `analysis/reversal/run_integrity.py` — nuevo: `compute_data_date`, `assess_fetch_health`, `bundles_with_bar_on_or_after`
- `analysis/reversal/regime_snapshot.py` — `run_failed`, ffill/no finitos, `n_nonfinite_excluded`, `data_date`, JSON estricto
- `analysis/reversal/signal_registry.py` — `data_date` y dedup cross-scan_date
- `analysis/reversal/near_miss_tracker.py` — `data_date`
- `analysis/reversal/reversal_scanner.py` — `scan_reversals(data_date=...)`
- `data/fetcher.py` — mensaje de ventana válida
- `data/reversal_tracking/regime_snapshots.jsonl` — fix histórico del punto 7
- `tests/test_run_reversals.py` (nuevo), `tests/test_regime_snapshot.py`

**Estado:** Activa.

---

## 36 — 2026-11-20: Instrumentación Fase B1 — campos de precio, CCL y earnings en signals y near-misses

**Contexto:** Fase B del roadmap de confiabilidad ("registrar ahora, decidir después", `docs/ROADMAP_CONFIABILITY.md`). Para calibrar después hacen falta variables que hoy no se graban: la fuerza semanal y la pendiente de MA50 que ya calcula el gate, la volatilidad del ticker en relación con el stop, la distancia a la MA200 y la descomposición ARS vs USD. #31/A2 mostró que un movimiento en ARS puede ser drift del CCL. En las 3 señales del 2026-11-20 el precio en ARS está pegado a la MA200 (−1,3% a +0,8%), pero en USD implícito está entre 9% y 11% abajo.

**Decisión:**
1. **Campos nuevos en `signals.jsonl` y `near_misses.jsonl`, siempre presentes** (`null` si no se pueden calcular; JSON estricto, sin NaN):
   - `weekly_strength` y `ma50w_slope`. La pendiente normalizada es la misma de `_weekly_trend`, sobre 8 semanas.
   - `atr_pct_14`: ATR14 de Wilder (`ATR_PERIOD`) sobre el close.
   - `stop_dist_pct` = (entry − invalidación) / entry.
   - `stop_dist_atr` = (entry − invalidación) / ATR14, en unidades de precio.
   - `ma200_dist_pct` = (close − MA200) / MA200, con signo.
   - Solo para CEDEARs con CCL: `rsi_14_usd_implied`, `weekly_strength_usd_implied` y `ma200_dist_pct_usd_implied`. Se calculan sobre la serie ARS/CCL, con el CCL alineado por fecha de barra (`asof`, la misma regla de `fx_context`). Para las acciones argentinas quedan en `null`. Las tres métricas no dependen del ratio, así que no usan `cedears_per_underlying`.
2. **Solo en `signals.jsonl`: `earnings_status`, `days_to_earnings` y `earnings_calendar_stale`.** Se reusa la llamada a earnings que ya existía en `_evaluate_bundle`, así que no agrega llamadas de red; por eso los near-misses no los llevan. `days_to_earnings` se cuenta en días hábiles (`np.busday_count`, la misma unidad que la ventana de warning). Es `null` si la fecha de yfinance ya pasó (la próxima fecha es desconocida) y si el estado es UNVERIFIED. `earnings_calendar_stale` es `true` si yfinance devolvió una fecha pasada, `false` si la fecha es hoy o posterior, y `null` si el estado es UNVERIFIED o el ticker no es CEDEAR. `earnings_status` y las advertencias no cambian: una fecha pasada sigue siendo VERIFIED_CLEAR.
3. **`_weekly_trend` se extiende sin cambiar la clasificación.** `_weekly_trend_details` expone el slope y queda como un wrapper fino. Si no se puede calcular el slope, la clasificación sigue usando 0.0 y el registro graba `null`. Con menos de 12 semanas, la clasificación sigue usando strength 0.0 y el registro graba `null`. Un test golden capturado antes del cambio (`tests/test_weekly_trend_golden.py`) fija el label y el strength.
4. **Un error de instrumentación no descarta el ticker.** Se loguea un warning y los campos se graban en `null`. Ningún gate, el score ni el ranking leen estos campos.

**Alternativas consideradas:**
- *Grabar `ma50w_slope = 0.0` cuando no se puede calcular (como usa el gate):* descartada, porque confunde "plano" con "sin dato".
- *`days_to_earnings` negativo cuando la fecha ya pasó:* descartada. Mezcla "faltan N días" con "el calendario está desactualizado"; la segunda condición queda explícita en `earnings_calendar_stale`.
- *Una llamada de earnings por near-miss:* descartada por el costo de red (~25 llamadas más por corrida).
- *Reconstruir la serie USD con `cedears_per_underlying`:* innecesario para métricas que no dependen del ratio, y sumaría un punto de falla (cambios de ratio).

**Archivos modificados:** `analysis/reversal/instrumentation.py` (nuevo), `reversal_scanner.py`, `fx_context.py` (`usd_implied_closes`), `signal_registry.py`, `near_miss_tracker.py`, `data/earnings.py`, tests (`test_instrumentation.py` y `test_weekly_trend_golden.py` nuevos, más el fixture `tests/fixtures/weekly_trend_golden.json`; los mocks de `test_liquidity.py` ahora devuelven `EarningsCheckResult` reales).

**Estado:** Activa.

---

## 37 — 2026-11-20: Instrumentación Fase B2 — barra de entrada y gap de apertura en outcomes

**Contexto:** #35 dejó pendiente que el `outcome_tracker` mide con `index > scan_date`. Desde #30, la señal del scan_date X usa el cierre de X-1, así que la rueda X, que es la primera en la que una orden real puede ejecutarse, queda fuera de la medición. Antes de decidir si se cambia la vara hay que medir cuánto pesa esa rueda, empezando por el gap de apertura. La vara de medición **no cambia**.

**Decisión:**
1. **Campos nuevos en `outcomes.jsonl`** (aditivos):
   - `entry_bar_date`, con `entry_bar_date_source` que indica de dónde sale: `data_date` / `close_match` / `unmatched` / `ambiguous` / `no_history`.
   - `entry_bar_close_ars`.
   - `next_open_ars`: open de la primera barra posterior a `entry_bar_date`.
   - `entry_gap_pct` = next_open / entry − 1.
   - `entry_gap_through_stop` = next_open ≤ invalidación.
2. **`entry_bar_date`.** Es `data_date` si la señal lo tiene. Si no, se busca por close: entre las últimas `ENTRY_CLOSE_MATCH_LOOKBACK_BARS` barras con fecha ≤ scan_date tiene que coincidir exactamente una, dentro de `ENTRY_CLOSE_MATCH_REL_TOL` (relativa). Si no coincide ninguna, o coinciden varias, queda `null` (fail-closed).
3. **Un solo fetch por señal.** `_fetch_price_history` devuelve el historial completo sin filtrar, ahora con `open`. El filtro `> scan_date` se aplica en `_assess_signal`, y los campos de entrada se leen del mismo frame. Se elimina el segundo `fetch_prices` que hacía el chequeo `has_any_data`; la semántica de pending vs `unresolved_no_data` no cambia.
4. **Pending.** `assess_outcomes` no persiste los pending (hace `continue`; nunca escribe una fila pending en `outcomes.jsonl`). Los campos se calculan en cada evaluación y aparecen cuando la señal se resuelve. `near_miss_outcomes` reevalúa y reescribe todos sus registros en cada corrida con `_assess_signal`, así que hereda los campos sin backfill, incluidos los pending.
5. **Backfill** (`scripts/backfill_entry_bar.py`). Es idempotente y tiene `--dry-run`. Hace un fetch por ticker. Si no consigue historial, no toca el registro: `fetch_prices` devuelve None tanto si no hay datos como si yfinance falla transitoriamente.

**Hallazgo (sin acción):** `fetch_prices` usa `auto_adjust=True`. Un dividendo posterior al scan reescala los close/open/low históricos, así que en el backfill el match por close falla en esos casos (5/90, todos confirmados: TMUS, CVS ×2, DAL ×2). Lo mismo afecta a la vara actual del `outcome_tracker`: compara lows y closes ajustados contra una invalidación y un entry que no lo están. Queda para la tarea de `exit_price_stop_fill`.

**Alternativas consideradas:**
- *Tolerancia más amplia (~1%) para absorber dividendos:* descartada. Las variaciones diarias de menos de 1% son comunes y harían crecer los ambiguos y los falsos matches.
- *Elegir la barra más reciente cuando hay ambigüedad:* descartada por ahora (13/90 casos, todos con closes repetidos por falta de operaciones). Queda como pregunta abierta.
- *Un segundo fetch con `auto_adjust=False` para el match:* descartada. Duplica la red y mezcla bases de precio con la vara existente.
- *Persistir los pending en `outcomes.jsonl`:* descartada. Cambia lo que leen la supresión (cooldown) y `summarize`.

**Archivos modificados:** `analysis/reversal/outcome_tracker.py`, `analysis/reversal/near_miss_outcomes.py` (path de fallo con schema uniforme), `scripts/backfill_entry_bar.py` (nuevo), `tests/test_entry_bar.py` (nuevo). El backfill de datos va en un commit aparte.

**Estado:** Activa.


## 38 — 2026-11-20: Exclusión de ROKU.BA y ORAN.BA (+ subyacente ROKU) y gate de exclusiones en `analyst_revision`

**Contexto:** La corrida de las 11:59 (`--force`) mostró dos problemas. (1) `ROKU.BA` y `TIMS3.BA` salían MISSING por barra vieja. (2) `PETR3` y `WEGE3` devolvían 404 de `quoteSummary` aunque estaban en `excluded_underlyings`: `analysis/reversal/analyst_revision._fetch_one` llamaba a `yf.Ticker` sin consultar la lista de exclusiones (`data/fundamentals.py` y `data/earnings.py` sí la respetan). `refresh_exclusions.py --new-only` propuso excluir `ROKU.BA` y `ORAN.BA`.

**Decisión:**
1. **Fix de código.** `_fetch_one` consulta `_is_excluded_underlying` (helper existente de `data/earnings.py`, sin duplicar la lectura del JSON) antes de cualquier llamada de red. Si el subyacente está excluido devuelve `{"trend": "no_data", "n_analysts": None}`, idéntico a lo que ya devolvía por la vía de excepción. No cambian gates, score, ranking ni lo que se publica.
2. **Exclusiones** (`reason: failed_verification`, `excluded_at: 2026-11-20`):
   - `excluded_ars`: `ROKU.BA`, `ORAN.BA`.
   - `excluded_underlyings`: `ROKU`. El script no lo propuso, así que se agregó con edición manual de esa única entrada.
3. **Fundamento por ticker:**
   - **ROKU.BA y subyacente ROKU:** adquisición por FOX cerrada el 2026-11-06, con delisting de Nasdaq. Última barra del CEDEAR: 2026-11-05 (15 días corridos sin operaciones al 2026-11-20).
   - **ORAN.BA:** delisting de NYSE en 2024 (ADR nivel 1 OTC). El cache tiene 0 barras con volumen > 0 en 489 días (2024-11-20 a 2026-11-19) y cierres planchados (5 valores distintos). Nunca pudo pasar el gate de ADV. Su subyacente `ORAN` ya estaba excluido desde 2026-06-29.
4. **Fuera de alcance:** `TIMS3.BA` no se excluye. El warning "No income statement" no es criterio de exclusión.

**Efecto operativo:** `ROKU.BA` y `ORAN.BA` dejan de ser evaluados y de generar errores y reintentos en cada corrida. Ninguno tiene registros en `data/reversal_tracking/` ni en `positions_log.json` (verificado), así que no hay posiciones ni outcomes afectados.

**Alternativas consideradas:**
- Dejar ambos en el universo: descartado. Generan errores y reintentos en cada corrida y no tienen posibilidad de producir señal.
- Excluir solo `.BA` y no el subyacente ROKU (como hizo la entrada 2026-08-13 con BK, por consistencia se excluyen ambos): descartado, el subyacente también está delistado.

**Archivos modificados:** `analysis/reversal/analyst_revision.py`, `tests/test_analyst_revision.py` (nuevo, 4 casos), `data/sources/yfinance_exclusions.json`.

**Estado:** Activa.


## 39 — 2026-11-25: Registro del news check de reversiones en `signals.jsonl` — evidencia, categorías y versión de prompt

**Contexto:** El news check (`analysis/reversal/news_check.py`, #24) llama a Claude Haiku 4.5 con `web_search_20250305` sobre las 0–5 oportunidades publicadas. Es informativo y nunca veta. Su resultado no se grababa en `signals.jsonl`, así que no había forma de medir si tiene valor predictivo. Además, `_web_search` armaba una lista de resultados que `_search_cached` descartaba: se perdían el `page_age` y las citations que devuelve la API. El campo `snippet` leía `content`, que en web search viene encriptado (`encrypted_content`), así que nunca tuvo texto útil. Este cambio sigue la línea "registrar ahora, decidir después" de #36.

**Decisión:**
1. **`NewsEvidence` (nuevo, solo registro).** Se extrae de la respuesta de la API con `getattr` defensivo; un campo ausente queda en `null` y nunca lanza excepción:
   - `results`: `[{url, title, page_age}]` de **todas** las búsquedas, deduplicados por URL (gana la primera aparición). Las URLs de las citations registradas entran siempre; el resto completa hasta `NEWS_EVIDENCE_MAX_RESULTS` (20), en el orden de búsqueda. Así cada citation se puede unir con su `page_age`. Un tope fijo que se llena con las primeras búsquedas lo impedía: en la prueba en vivo hubo 4 búsquedas por ticker y el tope de 8 se llenaba con las dos primeras. `page_age` es la fecha de última actualización del sitio, **no** la de publicación. Se elimina `snippet`.
   - `citations`: `[{url, title, cited_text}]` de los bloques de texto, deduplicadas por `(url, cited_text)`, como máximo 10.
   - `web_search_requests` (de `usage.server_tool_use`), `search_errors` (`error_code` de cada `web_search_tool_result_error`, que llega como objeto y no como lista) y `stop_reason`.
   - Si la extracción falla: `logger.warning` y evidence `null`. El veredicto no cambia y la señal se graba igual.
2. **Caché.** Junto a `llm_text` se guardan `evidence` y `evidence_version` (`NEWS_EVIDENCE_VERSION = 2`; la versión 1 fue el tope de 8 results y nunca se commiteó). Una entrada vieja, sin `evidence_version` o con versión 1, se sirve como antes, con evidence `null` y sin volver a buscar. Se mantienen la regla de no cachear respuestas vacías (#14) y el TTL de 1 día.
3. **`NewsCheckResult` expone lo que antes solo se logueaba:** `categories` (categorías normalizadas de los WARN que sobreviven, después del truncado a 2; el índice numérico del prompt, p. ej. `"5"`, se mapea a su nombre, `"calendar"`), `discarded_future` y `discarded_stale`. También `evidence`, `from_cache`, `model` y `prompt_version`. El veredicto (CLEAR / WARNING / UNVERIFIED) y los warnings de texto quedan idénticos.
4. **`NEWS_PROMPT_VERSION = "2026-11-v1"`** etiqueta el texto actual de `_build_prompt`, que no cambia. Cualquier cambio futuro al prompt debe subir la versión.
5. **12 keys nuevas en `signals.jsonl`, siempre presentes:** `news_status`, `news_categories`, `news_discarded_future`, `news_discarded_stale`, `news_model`, `news_prompt_version`, `news_from_cache`, `news_web_search_requests`, `news_search_errors`, `news_results`, `news_citations`, `news_stop_reason`. Si el news check no corrió (rama `cache=None` o excepción en el scanner), las 12 van en `null`. **`news_status = null` significa "no se ejecutó", que es distinto de `"unverified"`.** `near_misses.jsonl` no cambia, porque el news check no corre ahí.
   - **`news_stop_reason` y `pause_turn`:** con web search la API puede cortar el turno con `stop_reason = "pause_turn"` para que el cliente lo continúe. Todavía no se maneja: el texto parcial no trae veredicto y falla cerrado como UNVERIFIED ("respuesta inesperada del modelo"). Ahora queda registrado para medir cuánto ocurre antes de decidir si vale la pena continuar el turno.
6. **Único cambio de comportamiento: `max_uses = 5` (`NEWS_REVERSAL_MAX_SEARCHES`) en la tool de web search.** Antes no había límite y el modelo podía encadenar búsquedas sin tope por oportunidad. El valor es lo bastante alto para no limitar el caso normal (en la prueba en vivo, AAPL y TSM hicieron 4 búsquedas cada uno) y corta los casos desbocados, así que el costo y la latencia por ticker quedan acotados. Si el modelo pide más, la API devuelve `max_uses_exceeded`, que queda registrado en `news_search_errors`.

**Prueba en vivo (2026-11-25, `_web_search` directo, sin caché):**
- AAPL (CEDEAR, empresa US): WARN con **0 citations**, 4 búsquedas, `end_turn`. Es justo el caso que apunta la regla de grounding pendiente.
- TSM (ADR, Taiwán): CLEAR con 6 citations, 4 búsquedas, `end_turn`.

**Alternativas consideradas:**
- *Structured Outputs (`output_config.format`) para el veredicto:* no aplica. Es incompatible con citations, y en web search las citations están siempre activas. La documentación recomienda pedir una línea por campo y parsearla, que es lo que ya hace `_parse_response`.
- *Grabar `snippet`:* descartado. `content` / `encrypted_content` está encriptado y no se puede leer; `cited_text` (≤150 caracteres) es el texto legible que la API devuelve.
- *Re-buscar las entradas de caché viejas para tener evidencia:* descartado. Duplica el costo del mismo día a cambio de evidencia que igual sería de otra corrida.
- *Aplicar ya la regla de grounding (un WARN sin citation pasa a UNVERIFIED) y migrar a Haiku 5.5:* **pendiente** hasta tener n≥20 señales con el news check registrado. Se hará como un único cambio, con versión nueva de prompt (`NEWS_PROMPT_VERSION`), para poder comparar el antes y el después con estos mismos campos.

**Archivos modificados:** `analysis/reversal/news_check.py`, `analysis/reversal/reversal_scanner.py` (campo `news_check` en `ReversalOpportunity`), `analysis/reversal/signal_registry.py`, `tests/test_news_evidence.py` (nuevo).

**Estado:** Activa.

## 40 — 2026-11-25: Instrumentación Fase B3 (ex-dividendo) y gate de "no operable: ex-dividendo"

**Contexto:** UGP.BA entró el 2026-11-25 con ex-dividendo ese mismo día (~3,4 % de yield sobre el subyacente) y stop a 3,09 % del entry. La caída por dividendo sola alcanza para disparar el stop, de modo que un `stop_hit` en esa señal no mide una reversión fallida y contamina el corpus de calibración (`auto_adjust=True` además reescala el histórico, ver #37). El pipeline ya veía el evento, pero solo como texto en la advertencia de `news_check` (LLM): no quedaba en `data/`.

**Decisión — Parte 1 (instrumentación, implementada):**

1. `signals.jsonl` suma `ex_div_date`, `ex_div_amount`, `ex_div_yield_pct`, `ex_div_source`, `ex_div_stale`. Siempre presentes, `null` cuando no hay dato (mismo patrón que `earnings_calendar_stale`). Solo CEDEARs. `near_misses.jsonl` no cambia.
2. `ex_div_yield_pct` es una **fracción** (0,034 = 3,4 %), la misma unidad que `stop_dist_pct`, para compararlos directo.
3. No se guarda ninguna decisión de exclusión al escribir (sin `ex_div_in_window` ni `corpus_excluded`). El filtro "contaminado por dividendo" (`ex_div_yield_pct >= stop_dist_pct`, sin ex-date vencida) se calcula al analizar, con el macro `is_div_contaminated` de `analysis/query.py`. Cualquier dato faltante da "no contaminado": el filtro solo actúa con evidencia.
4. Fuente: `yfinance` (`Ticker.calendar["Ex-Dividend Date"]`). yfinance **no publica el monto del dividendo próximo**; sin entrada en el historial que matchee la fecha (±1 día) se usa `lastDividendValue` como estimación y `ex_div_source = "yfinance_last_dividend_estimate"`. Nunca se presenta como monto confirmado.
5. Backfill puntual de UGP.BA 2026-11-25 con `ex_div_source = "manual_backfill"` (fecha de NYSE, monto de la advertencia de `news_check`, cierre del subyacente de yfinance): yield 0,0342 ≥ stop 0,0309 → contaminada.

**Evidencia empírica (2026-11-25, yfinance, precios sin ajustar, CCL de `cache/ccl`):**

- **Día de la caída en el CEDEAR = ex-date de NYSE.** UGP 2025-03-10: ADR −4,55 %, UGP.BA −5,43 % en ARS (−6,10 % descontado el CCL). UGP 2026-08-26: −3,73 % / −4,19 % / −4,54 %. El día anterior no cae (ADR +1,78 % el 2025-03-07; −0,30 % el 2026-08-25). La columna `Dividends` de `UGP.BA` en Yahoo coincide con la fecha NYSE (4/4) y la de KO.BA en 6 de 7 (la excepción es el feriado argentino del 2026-06-15).
- **La fecha NYSE llega 1 día hábil después de la de B3.** En 6 ADRs de empresas B3 (UGP, VALE, PBR, BBD, ITUB, ABEV; 75 eventos pareados), fecha ADR − fecha B3: +1 día hábil en 63 (84 %), 0 en 10, +2 en 1 y +3 en 1.
- **El `calendar` de Yahoo para esos ADRs trae la fecha de B3, no la de NYSE.** Verificable en 3 de 3 (UGP, VALE, ABEV): la fecha del `calendar` es 1 día hábil anterior a la del historial del ADR. Por eso hoy Yahoo informó ex-date 2026-11-24 para UGP (ex-date real en NYSE/BYMA: 2026-11-25) y la señal habría quedado `ex_div_stale = true` sin monto.
- **Lo que no se pudo confirmar.** UGP 2025-08-25 (yield 1,97 %): dentro del ruido. UGP 2025-12-12 (yield ~4,8 %): la caída no se ve ese día (−2,3 % en ARS); el ADR cae −6,75 % el 12-16 sin explicación en los datos; B3 pagó el 12-08 (+4 días hábiles, uno de los dos desvíos de +2/+3). KO (0,7 %): por debajo del ruido diario, solo sirve para fechas.
- **Ruido de referencia:** desvío estándar diario del spread CEDEAR-ADR (CCL descontado) 1,10 % en UGP y 0,67 % en KO; del ADR de UGP, 2,56 %. En las 4 ex-dates de UGP.BA el spread fue −1,56, −0,52, −0,63 y −0,80 puntos (el CEDEAR cierra a las 17:00 ART y el ADR una hora después).

**Qué alcanza y qué no:** alcanza para una regla de **fecha** (para ADRs de empresas B3, ex-date del CEDEAR ≈ fecha del `calendar` + 1 día hábil, con ~16 % de desvíos). **No alcanza** para calibrar magnitud ni umbral de precio: hay solo 2 eventos limpios de alto yield (n = 2) y 1 contradictorio. El gate no puede apoyarse en la magnitud del efecto observado; solo en la comparación yield ≥ distancia al stop, que es aritmética y no requiere calibración.

**Decisión — Parte 2 (gate, pendiente; NO implementada):**

Gate bloqueante **solo para el caso inminente**: la señal pasa a `tradeable=False` si
- `ex_div_date` efectiva cae dentro de la **próxima sesión** desde `data_date` (la barra de entrada ya es la ex-date), y
- `ex_div_yield_pct >= stop_dist_pct`, y
- `ex_div_stale` no es `True`.

Condiciones de diseño:
- Sin score ni umbrales nuevos: el único umbral es la comparación con el stop que la señal ya tiene.
- En el reporte aparece como **"no operable: ex-dividendo"** (`suppression_reason`), en la sección de suprimidas, con fecha y yield.
- No abre posición paper (se apoya en `tradeable=False`, que ya impide la apertura en `signal_registry`).
- Queda registrada en `signals.jsonl` igual que cualquier señal suprimida; los `ex_div_*` permiten auditarla.
- Fail-open: sin fecha o sin yield, el gate no actúa.
- **Fecha efectiva.** Antes de implementar hay que normalizar la fecha para ADRs de empresas B3 (+1 día hábil sobre el `calendar`) y recalcular `ex_div_stale` con la fecha normalizada; sin eso el gate no dispara el día que más importa. Requiere decidir cómo identificar empresas B3 (la tabla país de `news_check` es una candidata).

**Preguntas abiertas:**
- Cómo marcar una ex-date de B3 sin romper el contrato de la parte 1, que guarda el valor crudo de Yahoo (¿campo aparte o normalización en el análisis?).
- Bloquear con monto estimado (`lastDividendValue`: 0,193 vs 0,1796 real en UGP, yield 3,7 % vs 3,4 %) o exigir monto confirmado.
- Con n = 2 eventos limpios, la magnitud del efecto en el CEDEAR queda sin calibrar; se acumula muestra con el filtro de análisis.

**Alternativas consideradas:**
- *Guardar `corpus_excluded` / `ex_div_in_window` al escribir:* descartada. Congela una decisión que depende de `stop_dist_pct` y de umbrales que todavía se calibran; se calcula al analizar.
- *Reusar `tradeable=False` para marcar UGP ya registrada:* descartada. `outcome_tracker` ignora las `tradeable=False`, y en la parte 1 se quiere medir, no ocultar.
- *Parsear la advertencia de `news_check` como fuente:* descartada como fuente primaria (texto de LLM, sujeto a filtros de fecha, #34); queda como candidata a respaldo.
- *Score con penalización por yield:* descartada. Agrega un umbral nuevo sin evidencia.

**Archivos modificados (parte 1):**
- `data/dividends.py` — nuevo: `ExDividendResult`, `build_ex_dividend_result` (puro), `check_ex_dividend`
- `analysis/reversal/reversal_scanner.py` — `ReversalOpportunity.ex_dividend`, llamada junto a earnings
- `analysis/reversal/signal_registry.py` — escribe los 5 campos
- `analysis/query.py` — macro `is_div_contaminated`
- `tests/test_dividends.py` (nuevo), `tests/conftest.py` (nuevo: ninguna prueba toca la red por el chequeo de ex-dividendo)
- `data/reversal_tracking/signals.jsonl` — backfill de UGP.BA 2026-11-25

**Estado:** Parte 1 implementada; parte 2 (gate) pendiente de decisión.

## 41 — 2026-11-25: Fecha efectiva de ex-dividendo para ADRs de empresas B3 y gate "no operable: ex-dividendo" (parte 2 de #40)

**Contexto:** #40 dejó el gate sin implementar porque la fecha de Yahoo no era confiable para ADRs de empresas B3. Con la fecha cruda, la señal de UGP.BA del 2026-11-25 habría quedado `ex_div_stale = true` sin monto (Yahoo: 2026-11-24; ex-date real en NYSE/BYMA: 2026-11-25) y el gate no habría actuado el día en que más importaba. Verificación adicional sobre 13 ADRs brasileños más (yfinance, historial del ADR contra el de la acción local en B3):

- **Confirman +1 día hábil:** GGB (7/7), BSBR (5/6), LND (1/1), SUZ (+1 y +2). Con los 6 ADRs de #40 (UGP, VALE, PBR, BBD, ITUB, ABEV; 63/75) la regla se sostiene.
- **En contra:** VIV da desfase 0 en 16 de 18 eventos.
- **Inconcluso:** TIMB (desfases dispersos de 0 a +5, probable mal pareo por pagos frecuentes de la acción local).
- **Sin datos de dividendos del ADR en Yahoo:** BAK, BRFS, CBRD, EBR, ELP, ERJ, SID (no se pudo verificar).

**Decisión:**

1. **Fecha efectiva.** `ex_div_date` pasa a ser la fecha efectiva del ADR/CEDEAR y se agrega `ex_div_date_raw` con la fecha tal como la informa Yahoo. Para ADRs de empresas B3, efectiva = raw + 1 día hábil. Para el resto (incluidos los subyacentes que cotizan en B3, `symbol_underlying` con dígito final: ABEV3, ITUB3, PRIO3…) efectiva = raw.
2. **Identificación de ADRs B3.** Conjunto explícito `B3_ADR_UNDERLYINGS` en `data/dividends.py` (el universo no tiene campo país y `data/` no importa de `analysis/`): ABEV, BAK, BBD, BRFS, BSBR, CBRD, EBR, ELP, ERJ, GGB, ITUB, LND, PBR, SID, SUZ, TIMB, UGP, VALE (18). Quedan fuera, con motivo documentado en `B3_ADR_NOT_SHIFTED`: VIV (evidencia en contra) y XP, PAGS, STNE (sin listado primario en B3, solo BDR). Un test cruza el conjunto contra `universe_snapshot.json` (campo `market`) y la tabla de Brasil de `news_check`, y falla si aparece un ADR brasileño sin clasificar.
3. **`ex_div_stale`** = fecha efectiva ≤ `data_date` (la barra de entrada ya incluye la caída). Cambia respecto de #40, que comparaba con la fecha de hoy. Sin `data_date`, `null`.
4. **Gate** (`check_ex_dividend_gate` en `suppression.py`, aplicado en `scan_reversals` después del cooldown y de la posición abierta): la señal pasa a `tradeable=False` si la fecha efectiva es la próxima sesión desde `data_date`, `ex_div_yield_pct >= stop_dist_pct` y `ex_div_stale` no es `True`. Sin score ni umbrales nuevos. Se permite bloquear con monto estimado; el motivo lo rotula ("…; monto estimado"). Fail-open ante cualquier dato faltante.
5. **Reuso del tratamiento existente.** `tradeable=False` + `suppression_reason` ya producen "🚫 NO OPERAR" en el reporte, `signal_registry` la registra sin abrir posición paper y `outcome_tracker` la ignora (no contamina el corpus). Un motivo de supresión anterior (cooldown, promediar a la baja) nunca se pisa.
6. **Backfill** de UGP.BA 2026-11-25: se agrega `ex_div_date_raw = 2026-11-24`; el resto no cambia. Las filas anteriores a #41 guardan la fecha cruda en `ex_div_date` y no tienen `ex_div_date_raw`.

**Límites conocidos:**
- La aritmética de días hábiles no modela feriados de NYSE ni de BYMA (p. ej. KO.BA 2026-06-12 contra KO 06-15 por feriado argentino).
- El +1 ocurre en ~84 % de los eventos verificados; el resto (+0, +2…) queda fuera de la regla. El error cae del lado conservador solo en parte: una fecha efectiva corrida un día puede dejar pasar un caso (falso negativo) o bloquear uno ya consumido (falso positivo, sin costo de pérdida).
- Con monto estimado (`lastDividendValue`) el yield puede diferir ~7 % del real (UGP: 3,7 % contra 3,4 %). La conclusión del gate es la misma en ese caso.
- Magnitud del efecto en el CEDEAR sin calibrar (n = 2 eventos limpios, ver #40); el gate no depende de ella.

**Alternativas consideradas:**
- *Aplicar +1 a todo ADR brasileño de la tabla de `news_check`:* descartada. Incluiría VIV (evidencia en contra) y XP/PAGS/STNE (sin listado B3).
- *Derivar la identificación en runtime desde `news_check._FX_CONTEXT`:* descartada. Haría depender `data/` de `analysis/`; el conjunto explícito más el test de consistencia cubre el mismo riesgo.
- *Normalizar solo al analizar (mantener la fecha cruda en `ex_div_date`):* descartada. El gate necesita la fecha efectiva en el momento del scan.
- *Exigir monto confirmado para bloquear:* descartada. yfinance no publica el monto próximo; el gate no actuaría nunca antes del hecho.
- *Bloquear más allá de la próxima sesión:* descartada. Fuera del caso inminente la señal sigue siendo evaluable y el efecto se mide con `is_div_contaminated`.

**Archivos modificados:**
- `data/dividends.py` — `ex_div_date_raw`, `B3_ADR_UNDERLYINGS`, `B3_ADR_NOT_SHIFTED`, `is_b3_adr`, fecha efectiva, `stale` contra `data_date`
- `analysis/reversal/suppression.py` — `check_ex_dividend_gate`
- `analysis/reversal/reversal_scanner.py` — `data_date` hasta `_evaluate_bundle`, `_apply_ex_dividend_gate` después de las supresiones
- `analysis/query.py` — documentación del macro `is_div_contaminated`
- `tests/test_dividends.py` (reescrito), `tests/test_ex_dividend_gate.py` (nuevo)
- `data/reversal_tracking/signals.jsonl` — `ex_div_date_raw` en UGP.BA 2026-11-25

**Estado:** Activa. Completa la parte 2 de #40.

---

## 42 — 2026-11-27: `vol_ratio_clean` (ratio de volumen sobre sesiones válidas), solo registrado (P2)

**Contexto:** `docs/HALLAZGOS_2026-11-27.md` §1.5. yfinance genera barras fantasma (OHLC planos, volumen 0) y la serie .BA trae barras en días con NYSE cerrado que no dicen nada de la demanda local de un CEDEAR con subyacente de EE.UU. Contaminan el ratio 5d/20d del gate: ADI 0.747 registrado contra 0.828 limpio; UGP 0.408 contra 0.666.

**Decisión:**
1. Se registra `vol_ratio_clean` junto a `vol_ratio` en cada señal y near-miss nuevo (`signals.jsonl` ahora también guarda `vol_ratio`). **El gate y el score siguen usando `vol_ratio`.**
2. Sesiones válidas: se excluye (a) toda barra plana con volumen 0 en un **día fantasma** (≥ 30 % de los tickers con barra ese día tienen barra plana con vol 0, calculado cruzando el universo de la corrida) y (b) toda barra de un día con **NYSE cerrado** cuando el CEDEAR tiene subyacente de EE.UU. o ADR (`symbol_underlying` informado). El resto cuenta, incluidas las barras con volumen 0 de papeles ilíquidos en días normales.
3. Ventanas de 5 y 20 sesiones válidas; con menos de 20, `vol_ratio_clean = None`.
4. Calendario NYSE: **lista fija** en `data/market_calendar.py` (2025–2027, incluye el cierre del 2025-01-09), sin `exchange_calendars`. Un test falla si el año actual supera la cobertura; fuera de cobertura el día se trata como abierto y se loguea.

**Interpretación del criterio de aceptación:** el §P2 describe la regla por ticker como "barra plana con volumen 0" en días NYSE cerrado, pero los valores de referencia (ADI 0.828, UGP 0.666) solo se reproducen excluyendo **la barra completa** del 2026-11-26 (ADI y UGP tenían volumen real pequeño, 71 y 103). Se priorizó la reproducción numérica: en días NYSE cerrado con subyacente de EE.UU. se excluye toda barra.

**Verificación:** con el cache del 2026-11-26/27, ADI 0.828 y UGP 0.666. Barrido 2025-01→2026-11 sobre los 315 .BA: solo se marcan 2026-07-06 (52 %) y 2026-11-10 (100 %); la fracción máxima en días NYSE cerrado es 19.5 % y en días normales no marcados 19.5 %.

**Límites conocidos:**
- Papeles sin `symbol_underlying` (subyacente solo listado en XETRA, LSE, OTC…) no reciben la exclusión por NYSE.
- No corrige RSI, ATR ni `vol_ratio` del gate (eso es P5 / migración del gate).

**Pendiente (plazo 2027-01-18):** migrar el gate a `vol_ratio_clean` con una entrada que compare near-misses registrado contra limpio.

**Archivos:** `data/market_calendar.py`, `analysis/reversal/volume_sessions.py` (nuevos); `analysis/reversal/reversal_scanner.py`, `near_miss_tracker.py`, `signal_registry.py`; `tests/test_volume_sessions.py`.

**Estado:** Activa (solo registro).

---

## 43 — 2026-11-27: Alineación del CCL histórico verificada en cada corrida (P1)

**Contexto:** `docs/HALLAZGOS_2026-11-27.md` §1.6. La serie histórica de argentinadatos cambió dos veces qué sesión representa cada fecha. Entre 2013 y ~mar-2020, y desde el 2026-09-08, la fecha D trae el cierre de la sesión anterior; entre ~abr-2020 y el 2026-09-07 no hay corrimiento. Con la serie cruda, `pct_change_ccl_5d` del 11-25 quedó en +8.01 % (alineado: +6.76 %) y el del 11-27 en +4.19 % (alineado: +2.56 %). Además, las series `_usd_implied` están corridas una sesión desde el 09-08. El corrimiento se cuenta en **sesiones BYMA**, no en días calendario: en 2013–2020 el sábado repetía el registro del viernes, que traía el valor del jueves, así que "+1 día" desalinea todos los viernes (con sesiones, la correlación de 2018/19 sube de 0.70/0.76 a 0.82/0.88).

**Decisión:**
1. **Tabla de regímenes versionada** en `data/sources/ccl_shift_regimes.json`: desde 2013-01-02 k=1, desde 2020-04-01 k=0 (fecha aproximada), desde 2026-09-08 k=1. Con k, la sesión Sᵢ toma el valor que la fuente publica con la fecha de Sᵢ₊ₖ. La tabla se aplica por tramos sobre el calendario de sesiones BYMA: días en que al menos 3 de GGAL, BMA, PAMP e YPFD operaron con volumen > 0, así que las barras fantasma y los feriados quedan afuera. Antes de la primera sesión del calendario (unos 2 años de cache) la serie queda cruda.
2. **Verificación en cada corrida** (`data/ccl_alignment.py`, llamada desde `run_reversals` después del health gate):
   - **Referencia:** CCL implícito con los pares GGAL/GGAL, BMA/BMA, PAMP/PAM e YPFD/YPF. Se toman los retornos logarítmicos diarios de local/ADR, que no dependen del ratio, y la mediana de al menos 3 pares, en sesiones con los dos mercados abiertos. Se descartan los días con |r| > 10 %.
   - **Candidatos:** k ∈ {−1, 0, +1}.
   - **Ventana:** 30 sesiones comunes. Para cada k se calcula la correlación con la referencia.
   - **Regla:** se **decide** solo si el margen (mejor − segundo) es ≥ 0.25 y la mejor correlación es ≥ 0.55.
3. **Qué se aplica según el resultado:**

| Estado | Condición | Qué se aplica |
|---|---|---|
| `confirmed` | detectado = régimen vigente de la tabla | la tabla |
| `regime_change` | se decidió un k distinto del vigente | la tabla, más un tramo provisorio con el k detectado en las 30 sesiones de la ventana, con WARNING. **La corrida no edita la tabla:** la actualiza una persona tras correr `scripts/backtest_ccl_alignment.py` |
| `ambiguous` | no se cumplen los umbrales | la tabla sin cambios. No se aplica ningún corrimiento estimado en la corrida (se marca, no se corrige) |
| `unavailable` | sin CCL, sin pares o sin ADR | la tabla si hay calendario; si no, la serie cruda (`applied=false`) |

4. **`ccl_at_scan` (spot) y `as_of` no se tocan.** Cada bundle recibe un `CCLSeries` nuevo con la historia alineada. `fx_context` e `instrumentation` no cambian su lógica. El CCL no entra en ningún gate ni en el score.
5. **Registro:** `regime_snapshots.jsonl` gana la clave `ccl_alignment` con `status`, `applied`, `table_shift`, `detected_shift`, `applied_shift_last_session`, `margin`, `corr_by_shift`, `n_sessions`, `window_start`, `window_end`, `pairs_used`, `tail_provisional`, `provisional_from`, `aligned_from`, `reason` y `params`. Las señales no llevan campos nuevos: se cruzan con el snapshot por `scan_date`.
6. **`tail_provisional`:** con k=+1, la última sesión depende del registro con fecha posterior. Si ese registro no existe o repite el de la sesión (como la copia del 11-27 a las 09:31), se marca y no se corrige.

**Calibración (N = 30, umbrales 0.25 / 0.55)** — backtest con ventanas móviles 2015-01 → 2026-11, 2690 ventanas dentro de regímenes conocidos:
- 0 decisiones erradas desde 2020-05. Queda 1 errada en 2016-03-08, en el régimen k=1 y fuera del rango de aceptación.
- Ambiguas: 24.7 % desde 2022, 16.8 % desde 2025 y 0 % en las ventanas posteriores al 09-08.
- Ante el cambio del 09-08: ambiguo desde el 09-17 y k=1 decidido desde el 10-08.
- 2013–14 se excluye porque los precios locales de yfinance de esos años son inutilizables (el implícito tiene un σ diario de ≈ 30 %).
- Los umbrales son calibración y pueden recalibrarse sin entrada nueva (`feedback_thresholds`); un cambio de la regla sí la requiere.

**Alternativas descartadas:**
- **Corrimiento fijo:** la fuente ya cambió dos veces.
- **Un solo k para toda la serie:** desalinea la parte anterior al cambio dentro de las ventanas de 200 barras.
- **Ubicar el punto de cambio automáticamente** (por mínimo error cuadrático): con 250 sesiones lo ubicó el 10-27 en vez del 09-08.
- **Sin el piso de correlación:** 2 decisiones erradas en abr-2021, con el CCL intervenido y un σ diario de 0.1–0.3 %.
- **N = 40:** las ventanas que cruzan el cambio siguen decidiendo 0 hasta el 09-25, lo que da errores sin marcar.
- **N = 60:** sin ventanas completas después del 09-08.
- **N = 20:** más errores con el mismo nivel de ambigüedad.
- **Error de seguimiento en vez de correlación:** entre 57 % y 77 % de ambiguas.
- **Serie cruda ante un resultado ambiguo:** reintroduce el error de 1 sesión en ≈ 17 % de las corridas.
- **Derivar el CCL de los pares** en lugar de alinear argentinadatos: pregunta abierta 9, fuera de alcance.

**Verificación:**
- `scripts/backtest_ccl_alignment.py` sale con código 0: desvío diario de la diferencia CEDEAR − ADR de UGP desde el 09-08 de 1.11 pp con la serie cruda y **0.47 pp alineado**.
- Con el cache del 11-27: `confirmed`, margen 0.67 (corr k=1: 0.89; k=0: 0.22), sesión del 11-24 = 1795.25 y `tail_provisional=true`.
- Tests sintéticos con +1, −1 y un caso ambiguo en `tests/test_ccl_alignment.py`.

**Límites conocidos:**
- Filter2 (`argentina_adjustment`) sigue usando la serie cruda, porque la alineación ocurre solo en `run_reversals`.
- Los campos históricos de `signals.jsonl` y `near_misses.jsonl` no se recalculan (pregunta abierta 3).
- Agrega 4 descargas de ADR por corrida, cacheadas en `cache/prices`.

**Archivos:**
- Nuevos: `data/ccl_alignment.py`, `data/sources/ccl_shift_regimes.json`, `scripts/backtest_ccl_alignment.py`, `tests/test_ccl_alignment.py`.
- Modificados: `scripts/run_reversals.py`, `analysis/reversal/reversal_scanner.py` (se pasa el registro al snapshot), `analysis/reversal/regime_snapshot.py`.

**Estado:** Activa.

---

## 44 — 2026-11-27: `outcomes_v2` fase 1 — ventana, entrada en la apertura y dos modelos de salida (P4)

**Contexto:** `docs/HALLAZGOS_2026-11-27.md` §1.2 y §1.9. La v1 mide con entrada al cierre de `data_date` y ventana `> scan_date`: desde #30 deja fuera la sesión del `scan_date`, la primera en que se puede ejecutar una orden (el filtro viene del primer commit, 43470a6, cuando la entrada era el cierre del propio `scan_date`; #35 y #37 lo difirieron a propósito). La vara de la v1 **no cambia**: la v2 convive con ella.

**Decisión:**
1. **Orden fijo ventana → entrada → salida.** Los Δ parciales dependen del orden (el total no); el reporte los da siempre en ese orden: v1 → (a) ventana → (b) entrada → (c) salida.
2. **Ventana:** desde la primera sesión posterior a `data_date` (inclusive), hasta `scan_date` + 20 días. `data_date`, o `entry_bar_date` de la v1, o coincidencia por cierre (fail-closed).
3. **Entrada:** `next_open_ars` registrado (base cruda de entonces); si falta, la apertura de la barra (reescalada). **Apertura ≤ stop ⇒ `no_entry_gap`**, que cuenta **0R** en el R principal; el reporte muestra siempre `n_entered` / `n_no_entry`. Targets relativos a la apertura. R en unidades del riesgo original (`entry_price_ars` − stop).
4. **Salida, dos modelos con el mismo disparo** (`low` < stop, luego +8 %, +5 % al cierre; los estados no cambian entre modelos): **S2 (principal)**: stop al nivel, o a la apertura si la barra abre por debajo (R < −1); target al cierre. **S1 (sensibilidad)**: cierre del día que gatilla. Cuidado con S1: en un `stop_hit` el cierre puede quedar por encima de la entrada y dar R positivo (5 filas: RIOT 09-02 +2.22R, ABEV +1.17R, DECK, COST), por eso no es el principal.
5. **Base de precios:** `basis_factor` = `entry_price_ars` / cierre del cache en `data_date`. Si |f − 1| > 0.001 la ventana se reescala por f (`basis_adjusted`); si |f − 1| > 0.25, `unresolved_data_error` (`basis_mismatch`; HWM ≈ 51). BNG 09-23 pasa de −1.48 a −1.27, el valor registrado. `basis_uncertain` se marca si el exit v1 registrado no coincide con la barra reescalada o si hay ex-dividendo dentro de la ventana.
6. **Dos clases de fila no medible, contadas aparte.**
   - **`unresolved_data_error`** (el dato de precio está mal; se guarda, sin R ni salida, **fuera de todas las estadísticas**): `invalid_denominator` (ADGO 08-03, TMUS 06-30), `basis_mismatch`, `price_jump`, `ratio_change`, `missing_inputs`, `no_open_price`.
   - **`not_instrumented`** (no se pudo identificar la barra de entrada; no es un error de dato; `data_error_reason` = `no_entry_bar`): 18 filas del corpus. Si la entrada registrada está a más de 25 % del nivel de precio del cache alrededor del `scan_date` (HWM, factor ≈ 51) no es falta de instrumentación sino `basis_mismatch`.
   - Los transitorios (`no_history`, `no_window_bars`) no se guardan y se reintentan; `pending` tampoco.
7. **Detectores (recomendación 1 de la auditoría).** Sobre las barras desde la entrada hasta la barra del disparo (o toda la ventana si no hubo): un salto de cierre a cierre **> 50 %** ⇒ `unresolved_data_error` (`price_jump`); si el cociente entrada/salida (cierre de la barra del disparo) coincide dentro de 3 % con un cambio de ratio (k o 1/k, k ∈ {2, 3, 4, 5, 8, 10, 15, 20, 25, 30, 40, 50, 100}) ⇒ `ratio_change`. Un salto **entre 20 % y 50 %** (`bar_jump`) y `flat_zero_trigger` (el disparo cae en una barra plana con volumen 0) **solo marcan**; no excluyen. Los umbrales (50 %, 20 %, 3 %, lista de ratios, 25 % de base) son calibración pendiente. FMCC 09-12 verificado: salto de 21.6 %, queda `stop_hit` con R −7.96 y la marca `bar_jump`, no se excluye. Se cuentan las barras planas con volumen 0 (`n_flat_zero_bars`) pero no se excluyen de la ventana; la regla por día de P2 no se aplica en v2.
8. **Ex-dividendo:** `ex_div_in_window` se marca desde `ex_div_date` de la señal; no ajusta el R ni cambia el estado. **Limitación:** las señales del corpus resuelto no tienen `ex_div_date` (se instrumentó el 11-25), así que el campo queda `null` en las 95 filas. La pregunta abierta 7 (acreditar dividendos) sigue abierta.

9. **Hook.** `refresh_outcomes_v2()` corre en `scan_reversals(record=True)` justo después de `outcome_tracker.run_at_scan_start()`. Es **fail-open**: cualquier falla es un WARNING y la corrida sigue (la función no lanza y el scanner la envuelve de nuevo). Lee las rutas de v1 de los módulos vivos y escribe solo `outcomes_v2.jsonl`, que se agrega a `_TRACKING_FILES` (auto-commit por corrida).
10. **Costos en el reporte** (`scripts/outcomes_v2_report.py`, no entran en estados ni en el registro): R neto = R − 1.11 % (0.555 % por punta) × entrada / `risk_orig`; las filas sin entrada no pagan. Agregación por fecha: filas agrupadas por `scan_date`, media por fecha y error estándar entre fechas (las filas de una misma fecha no son independientes).

**Esquema:** `data/reversal_tracking/outcomes_v2.jsonl`, clave `(scan_date, symbol)`, `schema_version` 1. Campos: identidad; entrada (`entry_price_close_ars`, `entry_open_ars`, `entry_session_date`, `stop_ars`, `risk_orig_ars`, `entry_gap_pct`, `entered`); `status_v2` (incluye `not_instrumented`), `data_error_reason`, `days_to_outcome`; `exit_s1_ars`, `exit_s2_ars`, `r_s1`, `r_s2`, `r_s2_open_risk` (secundario); `basis_*`; `ex_div_*`; `max_bar_jump`, `n_flat_zero_bars`, `data_flags`; `window_start_*`, `n_valid_sessions`; `status_v1`, `r_v1`.

**Qué sale la v1 en un `stop_hit`:** al **mínimo del día** (`outcome_tracker.py:285` dispara con `low < invalidation`; `:289` y `:292` registran `exit_price_ars` y el R con `low`). Es la convención más pesimista de las tres; en (a) y (b) se mantiene para aislar los otros efectos, y (c) la reemplaza.

**Resultado sobre el corpus** (76 filas con `next_open_ars`; 69 con R válido en todos los pasos; R medio = nivel, Δ = diferencia contra el paso anterior; en (c) contra (b)):

| Paso | 69: nivel | Δ | 76: nivel | Δ |
|---|---|---|---|---|
| v1 | −0.152 | | −0.311 | |
| (a) ventana | −0.266 | −0.114 | −0.422 | −0.111 |
| (b) entrada | −0.403 | −0.137 | −0.366 | +0.056 |
| (c) S1 | +0.029 | +0.432 | +0.026 | +0.392 |
| (c) S2 | −0.066 | +0.337 | −0.060 | +0.306 |

Los niveles son ~0.003R más altos que en HALLAZGOS §1.2 por la corrección de base de BNG. En la vista de 76 filas las 7 sin entrada cuentan 0R (y ADGO, sin R válido, también). El salto de +0.34 a +0.43 en (c) viene de dejar de salir al mínimo del día, no de una propiedad de la señal. Neto de comisiones el R medio de las 69 filas es v1 −0.518, (b) −0.770, S1 −0.338, S2 −0.433 (costo medio ≈ 0.37R por operación).

**Alternativas descartadas:** reemplazar la v1 (rompe la continuidad del corpus); excluir barras planas en la ventana (no cambia estados: una barra plana repite el cierre anterior, y mezcla la regla por ticker con la de P2); umbrales duros para `bar_jump` y `flat_zero_trigger` sin medir antes su distribución.

**Pendiente:** fase 2 (near-misses; HWM da `basis_mismatch` en sus 6 filas); medir la distribución de saltos para calibrar los umbrales.

**Archivos:** nuevos `analysis/reversal/outcomes_v2.py`, `scripts/backfill_outcomes_v2.py`, `scripts/outcomes_v2_report.py`, `tests/test_outcomes_v2.py`, `data/reversal_tracking/outcomes_v2.jsonl`. modificados `analysis/reversal/reversal_scanner.py` (hook), `scripts/run_reversals.py` (`_TRACKING_FILES`), `tests/test_run_reversals.py`. `outcomes.jsonl` y `positions_log.json` sin cambios (hash verificado).

**Addendum 2026-11-27 — barra de entrada de las `not_instrumented` del corpus limpio.** Las 9 señales con `scan_date ≥ 2026-09-11` (COST/FDX 09-11, COST/PYPL/FDX 09-12, FDX 09-15, DAL 09-18, KGC 09-24, HSBC 11-20) no tenían `data_date` y el cierre registrado no identificaba una barra única. Se resolvieron con dos reglas, en este orden, nunca por coincidencia de cierre sola:
1. **Restricción de sesión (`session_feasibility`):** la barra de entrada solo puede ser la última sesión ≤ `scan_date` (corrida post-cierre o de fin de semana, que no tiene pre-open) o la anterior (pre-open). Dentro de ese conjunto, el cierre debe calzar.
2. **Hora de corrida (`run_timestamp`)** para los empates (cierres idénticos en dos sesiones): la hora del commit que agregó la línea a `signals.jsonl`; antes de 11:00 ART = pre-open (barra anterior), después de 17:15 = post-cierre. La hora del commit es una cota superior de la hora de la corrida (el auto-commit va después). `regime_snapshots.jsonl` no sirve: no guarda `data_date` ni hora, y no existe snapshot del 09-11.
Resultado: 7 filas nuevas con R (5 `stop_hit`: COST/FDX 09-11, COST/FDX 09-12, FDX 09-15; 1 `lateral`: PYPL 09-12; 1 `target_5pct`: DAL 09-18) y 2 `no_entry_gap` (KGC 09-24, HSBC 11-20: 0R, abren por debajo del stop). El corpus limpio pasa de 27 a 36 filas medidas y de 13 a 14 fechas (suma el 09-12). DAL: la historia del cache está reescalada (factor 1.0026); los cierres crudos (cache / factor) dan 15 800 exactos solo el 09-17. **Limitación:** COST/FDX 09-12 (sábado) se resuelven por la regla de sesión, no por un dato: no se puede descartar con datos una barra de jueves vieja; la regla dice que un sábado no tiene pre-open.
**Implementación:** el mapa vive en `data/sources/entry_bar_overrides.json` (`scan_date`, `symbol`, `bar_date`, `source`, `evidence` con hora y hash del commit o la regla aplicada); `outcomes_v2._entry_bar_ts` lo lee con la precedencia `data_date` de la señal → `entry_bar_date` de v1 → override → cierre; un archivo ausente o malformado equivale a `{}` (fail-open) y una `source` distinta de `session_feasibility`/`run_timestamp` (en particular `close_match`) se rechaza. Los registros nuevos llevan `entry_bar_date` y `entry_bar_date_source` (`data_date`, `v1_entry_bar_date`, `close_match`, `session_feasibility`, `run_timestamp`); los 86 registros anteriores no se tocaron y no tienen esos campos. `build_v2` re-evalúa una fila `not_instrumented` solo si aparece un override para ella. Las otras 9 `not_instrumented` (scan_date < 09-11, backfill de junio–agosto) siguen igual: la hora de commit de un backfill no es evidencia.
**Reporte:** `scripts/outcomes_v2_report.py` muestra ahora, junto a la vista cruda y para el corpus limpio y el total, la vista deduplicada por exposición con `_is_exposure_duplicate` (mismo criterio y mismos outcomes v1 que el win rate de la auditoría). Las tablas de pasos (v1 → a → b → c) siguen crudas. Con las 9 filas nuevas, corpus limpio: cruda 36 filas / 14 fechas / R_S2 −0.27 por fila; dedup 29 filas / 13 fechas / −0.14. Total: cruda 84 / 39 / −0.115; dedup 64 / 32 / +0.113. El punto de decisión (14 / 36) sigue contando fechas crudas; sobre filas deduplicadas el 09-12 no aporta fecha (sus 3 filas son re-señales).

**Estado:** Activa (fase 1).


## 45 — 2026-11-27: Estado `suppressed` y outcome contrafactual de las señales no operables (P3)

**Contexto:** `docs/HALLAZGOS_2026-11-27.md` P3. Las señales con `tradeable=False` (cuarentena post-stop, promediar a la baja, gate de ex-dividendo) nacían `pending` y quedaban así para siempre: PCAR 09-18, PCAR 09-19 y GFI 09-24 inflaban el conteo de pending y nunca mostraban cuánto habría rendido lo que el sistema bloqueó.

**Decisión:**
1. **Estado `suppressed`.** Una señal `tradeable=False` nace con `outcome_status = "suppressed"` (`signal_registry.record_signals`) y nunca pasa por `pending`. Las tres existentes se migraron en `signals.jsonl` (solo cambió ese campo en 3 líneas; verificado con dry-run y diff antes de escribir).
2. **Outcome contrafactual con la misma lógica de v1** (`_assess_signal`, sin tocarla), marcado `counterfactual: true`. Se guarda en **archivos aparte**: `data/reversal_tracking/outcomes_suppressed.jsonl` (v1) y `outcomes_v2_suppressed.jsonl` (v2). Ambos están en `_TRACKING_FILES` y en su test. Es idempotente: un contrafactual resuelto no se recalcula; uno sin resolver (en ventana, sin datos, falla de fetch) se reintenta. Fail-open: nunca bloquea la evaluación de v1.
3. **Aislamiento por construcción, no por filtros.** Nada de lo que lee `outcomes.jsonl` ve los contrafactuales: win rate, R de las tradeables, cuarentena post-stop (`suppression.py` busca `stop_hit` ahí: un stop contrafactual no puede extender su propia cuarentena), dedup por exposición, `query.py` y `outcomes_v2`. Se verificó lector por lector que ninguno deja de considerar como exposición algo que hoy considera: una suprimida previa sigue contando como exposición abierta en `_is_exposure_duplicate` (no tiene registro en `outcomes.jsonl`, igual que antes); promediar a la baja y el rótulo ➕ SUMA salen de `positions_log`, que no se toca; `query.py` las sigue viendo como `no_outcome_record`.
4. **`outcomes_v2` SÍ evalúa las suprimidas** (preferencia del usuario), en `outcomes_v2_suppressed.jsonl`, con `counterfactual: true` y `signal_status: "suppressed"`. **Conservan el `status_v2` medido** (stop_hit, etc.) en lugar de pisarlo con "suppressed": si no, se pierde el resultado contrafactual. Su `status_v1` es el contrafactual v1. Quedan fuera de todos los agregados y del punto de decisión.
5. **`summarize()`**: `suppressed` sale de pending y de la tasa (`_EXCLUDED_FROM_RATE`) y se reporta en una sección propia ("Supresiones — contrafactual"). `scripts/adhoc_catalyst_breakdown.py` recibe el mismo cambio (era el único otro lector que habría contado las suprimidas como resueltas).
6. **`positions_log.json` no se toca**: no hay posición para estas señales, y la pasada contrafactual no llama a `close_position`.

**Resultado sobre el corpus:** PCAR 09-18 stop_hit −1.12R, PCAR 09-19 stop_hit −1.21R, GFI 09-24 stop_hit −4.82R (media −2.38R). `Win rate real` sin cambio (35 %, 25/71, 26 dup. de exposición); `n` pasa de 102 a 99 y `Pending` de 7 a 4. Con las suprimidas, las 3 pérdidas contrafactuales no entran a ningún denominador. En v2 el R S2 contrafactual es −1.04 / −0.77 / −0.55 (el modelo S2 corta en el nivel del stop o a la apertura, en lugar del mínimo del día: por eso GFI pasa de −4.82R a −0.55R). La diferencia de GFI es efecto de ventana + salida, no de un gap: en v2 el stop se gatilló el 09-24 (`days_to_outcome` 0, una sesión que v1 no evalúa) y salió en el nivel del stop; en v1 el disparo ocurrió 4 días después, al mínimo de esa sesión.

**Reporte (P4).** `scripts/outcomes_v2_report.py` recibe `--since` (default 2026-09-11, corpus limpio de la auditoría) y muestra siempre las dos vistas, limpio y total, con n de filas y de fechas. El **punto de decisión (~36 fechas) se cuenta solo sobre el corpus limpio**: fechas distintas de `scan_date ≥ since` con al menos una fila de `outcomes_v2` en stop_hit / target_* / lateral / no_entry_gap (excluye `unresolved_data_error`, `not_instrumented`, `suppressed` y `pending`). Se muestra también el conteo sobre la población de 76 hasta que converjan. Hoy: 13 / 36 fechas en ambos conteos.

**Alternativas descartadas:** marcar el contrafactual dentro de `outcomes.jsonl` (obliga a filtrar en cada lector, y un `stop_hit` contrafactual extendería la cuarentena); pisar `status_v2` con `suppressed` (pierde el resultado); evaluar las suprimidas solo en v1.

**Pendiente:** el R contrafactual v1 de GFI (−4.82R) resulta de evaluar el stop 4 días después de la sesión en que v2 ya lo había gatillado y salir al mínimo (ventana + criterio de salida, no un gap); vale una mirada en la auditoría mensual junto con el criterio de salida S2.

**Archivos:** `analysis/reversal/outcome_tracker.py` (`assess_suppressed`, `summarize`), `analysis/reversal/signal_registry.py`, `analysis/reversal/outcomes_v2.py` (`build_v2(suppressed=)`, `_refresh_suppressed`), `scripts/outcomes_v2_report.py`, `scripts/run_reversals.py`, `scripts/adhoc_catalyst_breakdown.py`, `tests/test_suppressed_outcomes.py`, `tests/test_run_reversals.py`, `data/reversal_tracking/outcomes_suppressed.jsonl`, `data/reversal_tracking/outcomes_v2_suppressed.jsonl`.

**Estado:** Activa.


## 46 — 2026-11-27: Modelo de salida S3 en `outcomes_v2` (sensibilidad; el principal sigue siendo S2)

**Contexto:** el stop de S1/S2 se dispara con `low < stop`, que en BYMA con CEDEARs de baja liquidez puede ser una mecha de una sola rueda. Se agrega un tercer modelo para medir cuánto cambia el resultado si el stop exige un **cierre** por debajo del nivel. **No cambia el modelo principal**: la decisión se toma después de ver estos números.

**Definición de S3** (`simulate(exit_model="S3")`):
1. El stop se dispara cuando el **cierre** queda debajo del nivel de invalidación (no el mínimo).
2. La salida es la **apertura de la sesión siguiente** dentro de la ventana. Si el disparo es la última sesión de la ventana (`today ≥ deadline`), sale al cierre de ese día. Si la sesión siguiente todavía no se observa (ventana abierta), la fila queda `pending` en S3.
3. Targets (+8 % / +5 % al cierre, relativos a la apertura de entrada) y `no_entry_gap` iguales a S2. La entrada es común a los tres modelos.
4. **Diferencia estructural:** a diferencia de S1/S2 (mismo disparo, estados idénticos), S3 puede cambiar el **estado** de la fila: una rueda que rompe el stop de mínima y cierra por encima ya no dispara y la operación sigue; puede terminar `lateral` o en target, o dispararse después con un gap peor que −1R. El `status_v2` almacenado sigue siendo el de S2.

**Implementación:** `assess_v2(..., with_s3=True)` agrega `status_s3`, `exit_s3_ars`, `r_s3`, `days_s3` y `exit_s3_date`. Por defecto está **apagado**: los registros de `outcomes_v2.jsonl` no cambian (ni los 95 existentes ni los nuevos) hasta que se decida el modelo principal; el reporte recalcula S3 desde el cache (sin red). Verificado: el S2 recalculado coincide con el registrado en las 84 filas medidas. Tests en `tests/test_outcomes_v2.py` (`TestExitS3`, `TestAssessWithS3`).

**Resultado** (muestra común, ninguna fila queda pendiente en S3; R_S2 = nivel principal; `neto` = R − 1.11 % × entrada / `risk_orig`; sin entrada = 0R; `R/fecha` = media de medias por `scan_date` ± EE entre fechas):

| Vista | Modelo | R/fila | neto/fila | R/fecha ± EE | neto/fecha ± EE |
|---|---|---|---|---|---|
| Limpio, cruda (36 filas, 14 fechas) | S1 | −0.356 | −0.666 | −0.197 ± 0.352 | −0.506 ± 0.359 |
| | S2 | −0.270 | −0.581 | −0.109 ± 0.321 | −0.418 ± 0.326 |
| | S3 | −0.211 | −0.522 | −0.080 ± 0.331 | −0.388 ± 0.335 |
| Limpio, dedup (29 filas, 13 fechas) | S1 | −0.338 | −0.638 | −0.079 ± 0.395 | −0.378 ± 0.402 |
| | S2 | −0.138 | −0.438 | +0.077 ± 0.354 | −0.222 ± 0.358 |
| | S3 | −0.238 | −0.538 | −0.016 ± 0.371 | −0.315 ± 0.376 |
| Total, cruda (84 filas, 39 fechas) | S1 | +0.002 | −0.327 | +0.164 ± 0.202 | −0.167 ± 0.202 |
| | S2 | −0.115 | −0.444 | +0.016 ± 0.208 | −0.315 ± 0.212 |
| | S3 | −0.024 | −0.352 | +0.067 ± 0.220 | −0.264 ± 0.226 |
| Total, dedup (64 filas, 32 fechas) | S1 | +0.127 | −0.179 | +0.359 ± 0.246 | +0.043 ± 0.245 |
| | S2 | +0.113 | −0.193 | +0.272 ± 0.236 | −0.044 ± 0.236 |
| | S3 | +0.104 | −0.203 | +0.295 ± 0.258 | −0.021 ± 0.261 |

Cambios de estado S2 → S3: 3 `stop_hit → lateral` en el limpio crudo (1 en el dedup); 9 en el total crudo (8 `stop_hit → lateral`, 1 `stop_hit → target_5pct`; 4 en el dedup: 3 y 1).

**Lectura (sin decisión):** las diferencias entre modelos son del orden de 0.1R por fila y mucho menores que el error estándar entre fechas (0.2–0.4R); con 14–39 fechas, ninguna vista distingue S2 de S3. S3 mejora en las vistas crudas (en las que 5 filas COST/FDX/PYPL cuentan varias veces) y empeora levemente en las deduplicadas del limpio; S1 queda último en el limpio y primero en el total. El orden entre modelos **no es estable** entre vistas, así que no es base para cambiar el principal.

**Pendiente:** decidir el modelo principal con más fechas (punto de decisión 14 / 36); si se elige S3, persistir los campos con un backfill aprobado sobre los registros existentes.

**Archivos:** `analysis/reversal/outcomes_v2.py` (`EXIT_S3`, `simulate`, `assess_v2(with_s3=)`), `scripts/outcomes_v2_report.py` (`collect_models`, `print_models`), `tests/test_outcomes_v2.py`.

**Estado:** Activa (sensibilidad; S2 sigue siendo el principal).
