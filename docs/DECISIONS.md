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