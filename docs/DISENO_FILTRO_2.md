# Diseño del Filtro 2 — spec cerrada para implementación

> Diseño aprobado 2026-06-24. Spec cerrada — sin ambigüedades abiertas.
> Insumo: 297 survivors del Filtro 1 sobre universo real (391 tickers).
> Decisiones que cerraron el diseño: `DECISIONS.md` 2026-06-24 (b) y §7 de este doc.

---

## 0. Insumo real de esta sesión

297 survivors del Filtro 1 sobre universo de 391 (370 CEDEARs + 21 argentinas). Cada uno trae el `TickerBundle` completo:

- `prices_ars` (OHLCV diario, ~500 barras vía yfinance `.BA`) — siempre presente para survivors (los `MISSING/ERROR/PARTIAL` no llegan acá).
- `ccl_series` (serie histórica + spot vía dolarapi/argentinadatos).
- `fundamentals` — **puede ser `None`** y lo es de forma asimétrica:
  - Argentinas: virtualmente todas tienen `fundamentals = None` (FMP no cubre `.BA`).
  - CEDEARs: la mayoría tiene, pero algunos no (emerging markets sin cobertura FMP).
- `metadata.cedears_per_underlying`, `symbol_underlying`, `asset_type`.

Esto es importante porque la asimetría argentinas/CEDEARs en disponibilidad fundamental **interactúa con el rol del desempate** — resuelto en §7 (decisiones #2 y #3).

---

## 1. Arquitectura general del scoring

### 1.1 Forma elegida: aditiva con penalidades acotadas, y desempate como gate binario

Propongo:

```
final_score = max(0, technical_score
                     - fundamental_penalty
                     - argentina_penalty)

ranking_keep = sentiment_gate_result in {none, confirm, inconclusive}
                # discard_opportunity → fuera del ranking
```

Con escalas propuestas (rangos cualitativos, no umbrales finales — todo va a "calibración pendiente"):

| Componente | Rango | Signo | Naturaleza |
|---|---|---|---|
| `technical_score` | 0 – 100 | + | **Driver único positivo.** Producido por la técnica 1. |
| `fundamental_penalty` | 0 – 30 | – | Sólo resta. La técnica 2 nunca suma. |
| `argentina_penalty` | 0 – 25 | – | Modificador final. Distinto para CEDEAR vs. argentina. |
| `sentiment_gate` | `none / confirm / inconclusive / discard` | binario | Sólo activa cuando técnico + fundamental no coinciden. `discard` saca al ticker del ranking; el resto no toca el `final_score`. |

**Por qué esta forma y no otras dos alternativas que evalué:**

- **Pura aditiva sin techo (T + F + S + A):** descartada — convierte el "sentimiento" en un peso numérico más, contradice el criterio ("desempate, no técnica con peso propio").
- **Multiplicativa (T × (1 − f) × (1 − a)):** descartada — las penalidades stackean exponencialmente y se vuelve poco interpretable (¿una penalidad fundamental 0.3 + Argentina 0.2 deja al ticker en 0.56 del score? Cae demasiado rápido).
- **Aditiva con bounds + gate binario para sentimiento:** preserva el rol del técnico como driver (T = 0-100 sigue siendo legible como "fuerza técnica"), las penalidades acotadas no pueden dominar, y el sentimiento mantiene su rol de **árbitro condicional**, no de peso continuo.

### 1.2 Estado del ticker en cada paso

Cada ticker en el Filtro 2 termina en uno de cuatro estados:

- `ranked`: pasó todo, entra al ranking con `final_score`.
- `discarded_by_sentiment`: el desempate falló — fuera del ranking.
- `held_with_warning`: pasó pero con advertencias (alta penalidad Argentina, fundamental deteriorating + sentiment inconclusive, etc.).
- `unevaluable`: caso de borde — ej. `prices_ars` con NaNs estructurales que rompen el cómputo técnico. No descartado, "no evaluable" (alineado con la lógica epistémica de Filtro 1).

---

## 2. Técnica 1 — Técnico avanzado

Esta es la única técnica que **suma** al score. Produce `technical_score ∈ [0, 100]` y un `technical_breakdown` con los sub-scores.

### 2.1 Sub-componentes y su lógica

Cuatro sub-componentes, cada uno con su rango:

| Sub-score | Aporte | Idea |
|---|---|---|
| `trend_regime` | 0 – 50 | Combina estructura semanal + estructura diaria + alineación de MAs. Es el "núcleo" del score técnico. |
| `breakout_bonus` | 0 – 15 | Bonus binario si hay ruptura reciente confirmada por volumen. |
| `relative_strength` | −15 a +15 | Fuerza vs. índice de referencia (y eventualmente sector). |
| `momentum_rsi` | −15 a 0 | **Sólo resta.** Penaliza sobrecompra sin contexto, RSI < 30 (señal de cambio de tendencia, no de compra). |

`technical_score = clip(trend_regime + breakout_bonus + relative_strength + momentum_rsi, 0, 100)`

#### a) `trend_regime` (0–50) — estructura multi-timeframe + MAs

Resampleo semanal: tomar el `prices_ars` diario y agregarlo a barras semanales (cierre = viernes, OHLC desde diario). Necesario porque el criterio pide **explícitamente** la dimensión semanal para contexto.

Compone tres bloques en conjunción:

1. **Tendencia semanal (contexto, 0–20):**
   - Estructura HH/HL (higher highs / higher lows) sobre las últimas N semanas (~12-20).
   - Cierre semanal por encima de MA20 semanal y MA50 semanal.
   - Pendiente positiva de MA20 semanal.
   - Si la tendencia semanal es claramente bajista (cierre debajo de MAs semanales con pendiente negativa) → **cap al `trend_regime` total en 15**, sin importar lo bueno que se vea el diario. El multi-timeframe alineado no es opcional.

2. **Tendencia diaria (timing, 0–20):**
   - Cierre diario > MA20, MA50 y MA200.
   - Pendiente positiva de MA50 (la MA más relevante para horizonte semanas-meses).
   - HH/HL sobre últimos ~30-50 días.

3. **Alineación de MAs (0–10):**
   - Bonus por orden MA20 > MA50 > MA200 (alineación "perfecta").
   - Bonus extra si hubo cruce reciente MA50 sobre MA200 (cuasi-"golden cross") en las últimas ~30 barras.

**Pendiente vs. posición:** el criterio dice "cruces y pendiente, no solo posición". La pendiente entra como gate del bonus de MA semanal y MA50 diaria. Una MA200 plana o cayendo, con precio arriba, no califica como uptrend.

#### b) `breakout_bonus` (0–15) — ruptura confirmada por volumen

- **Ruptura:** cierre > máx de los cierres de las últimas N barras (N entre 20–50, calibración pendiente), dentro de las últimas K barras (K entre 3–10).
- **Volumen confirmador:** volumen del día de la ruptura > X× la mediana de las N barras previas (X entre 1.3–2.0, calibración pendiente).
- Binario: bonus completo si dispara, 0 si no.

#### c) `relative_strength` (−15 a +15) — fuerza vs. índice (y sector como gap)

- **Índice de referencia por tipo de activo:**
  - CEDEARs → SPY (S&P 500), vía yfinance (`SPY`).
  - Argentinas → Merval (`^MERV` en yfinance).
- **Ventana:** ~60-90 días hábiles (3-4 meses) — captura liderazgo reciente sin contaminarse con ruido intradía.
- **Métrica:** RS = ratio_de_precios.iloc[-1] / ratio_de_precios.iloc[-window], donde `ratio_de_precios = ticker_close / index_close`. Una RS > 1.10 = ticker lidera al índice por > 10 pp; RS < 0.90 = rezaga.
- **Mapeo a score:** lineal pero capeado:
  - RS ≥ 1.15 → +15
  - RS ≈ 1.00 → 0
  - RS ≤ 0.85 → −15
- **Detalle implementación:** SPY/Merval se descargan una vez por ciclo y se cachean (el módulo `data/prices.py` actual ya sabe pedir tickers no-`.BA`; sólo hay que orquestar). Para CEDEAR de empresa argentina dual-listada (ABEV, ITUB, VALE), revisar caso por caso si SPY sigue siendo el comparable correcto — posible gap.

> ⚠️ **GAP — fuerza relativa vs. sector:** el universo no tiene clasificación sectorial nativa. Tres opciones, ordenadas por costo:
> 1. **Omitir vs. sector** y dejarlo registrado como limitación. La fuerza vs. índice cubre la mayor parte del valor de esta señal.
> 2. **Obtener sector vía `yfinance.Ticker(...).info["sector"]`** (1 llamada extra por subyacente, cacheable 30+ días) y comparar contra ETF sectorial (XLF, XLE, XLK, XLV, XLY, XLP, XLI, XLB, XLC, XLU, XLRE). Para argentinas no hay equivalente directo.
> 3. **Construir baskets ad-hoc** desde el propio universo (clasificación manual). Costoso de mantener.
>
> Mi recomendación: arrancar con (1) y promover a (2) sólo si en la primera corrida real se ve que la fuerza vs. índice por sí sola deja casos importantes sin discriminar.

#### d) `momentum_rsi` (−15 a 0) — RSI con contexto, sólo penaliza

El criterio dice **"evitar sobrecompra extrema sin contexto"** — la frase clave es "sin contexto". Modelado:

- **No penalizar** RSI > 70/80 si hay alguna de estas condiciones simultáneamente:
  - Hubo ruptura con volumen en las últimas 5-10 barras (es decir, `breakout_bonus > 0`).
  - El precio está dentro del 5% del máximo de 52 semanas y la pendiente de MA50 diaria es claramente positiva (impulso justificado).
- **Penalizar** RSI > 80 sólo cuando:
  - No hay breakout reciente con volumen, Y
  - El precio está > 15% por encima de MA20 diaria (movimiento vertical sin base).
  - Penalidad: −10 a −15.
- **RSI 70-80 sin contexto:** penalidad chica, −5.
- **RSI < 30:** −5 a −10. Para un sistema momentum, esto no es señal de compra — generalmente confirma que la tendencia se invirtió.

El criterio dice "sin contexto" pero no define el contexto. Voy a tener que definirlo arriba en código; me parece que vincularlo a `breakout_bonus > 0` o a "precio cerca de máximos con MA50 con pendiente positiva" captura bien la idea, pero es interpretación mía. **No es ambigüedad bloqueante, sólo aviso de criterio interpretado.**

### 2.2 Output del bloque técnico

```
TechnicalResult:
  technical_score: float (0-100)
  breakdown:
    trend_regime: (weekly_strength, daily_strength, ma_alignment)
    breakout: bool + detail (date, volume_ratio)
    relative_strength: float + benchmark used
    rsi_state: ok / overbought_with_context / overbought_no_context / oversold
  trend_regime_label: strong_up / mild_up / sideways / mild_down / strong_down
```

El `trend_regime_label` (categórico) es lo que entra al test de "técnico y fundamental coinciden" en la técnica 3.

---

## 3. Técnica 2 — Fundamentals como filtro de calidad

Sólo **resta** `fundamental_penalty ∈ [0, 30]`. Nunca suma. Confirma o desmiente; no aporta convicción positiva por sí sola.

### 3.1 Métricas usadas, dado lo disponible

| Métrica del `FundamentalsSnapshot` | Disponible | Uso en Filtro 2 |
|---|---|---|
| `eps_quarterly` (5 trim) | sí | Tendencia (slope normalizado) — más granular que C2. |
| `revenue_quarterly` (5 trim) | sí | Tendencia (slope normalizado) — **clave**, complemento a EPS. |
| `net_debt` | sí | Comparado contra `revenue_ttm` para ratio de apalancamiento. |
| `free_cash_flow` (TTM) | sí | Signo del FCF (positivo / negativo). |
| `gross_margin` | **snapshot único** | Nivel absoluto vs. mediana del universo. Sin trend. |
| `operating_margin` | **snapshot único** | Idem. |

> ⚠️ **GAP — sin trend de márgenes:** el data layer hoy guarda sólo el último trimestre de gross/operating margin. El criterio pide "salud financiera (márgenes)" y "tendencia".
> Estado: aceptado como limitación (§7). Arrancar usando márgenes sólo como nivel absoluto vs. mediana del universo. Si la primera corrida sobre los 297 muestra que el trend de márgenes hubiera cambiado el `fundamental_state` en casos relevantes, extender el fetcher (bajo costo — ya tenés `income_sorted` en `data/fundamentals.py:130`; sólo agregar dos campos al snapshot).

> ⚠️ **GAP — sin posición competitiva/sectorial:** no hay datos para evaluar "por qué este movimiento de precio tiene sentido con el negocio". Lo dejo como limitación documentada; lo cubre parcialmente la fuerza relativa vs. índice del bloque técnico.

### 3.2 Cómo se traduce a `fundamental_state` y `fundamental_penalty`

Cuatro estados, con penalidad asociada:

- `confirmed` (penalty 0):
  - Revenue slope ≥ 0 (no decaimiento), Y
  - EPS slope ≥ −0.05 (estable o mejorando — más permisivo que el −0.10 del C2 porque acá no es descarte, es confirmación), Y
  - FCF > 0 (o ticker en la lista de exención bancaria — los mismos 4 de C1).

- `neutral` (penalty 5–10):
  - Cualquiera de las tres condiciones de `confirmed` falla, pero ninguna falla "feo".
  - Ejemplo: revenue flat + EPS slope ligeramente negativo + FCF positivo.

- `deteriorating` (penalty 15–30):
  - Revenue slope negativo significativo Y EPS slope negativo Y/O FCF negativo no-financiero.
  - Filtro 1 ya descartó los casos extremos (C1 + C2); acá capturamos deterioros que pasaron por debajo del umbral de descarte pero son visibles.

- `unknown` (penalty **0**, marca aparte):
  - `fundamentals = None`. No se puede confirmar ni desmentir.
  - **No aplica penalidad** — sería castigar al ticker por una falta del proveedor de datos.
  - PERO el `fundamental_state = unknown` interactúa con la técnica 3 (desempate). Reglas en §4.2: CEDEARs en `unknown` activan desempate completo **sólo si `trend_regime_label = strong_up`**; argentinas en `unknown` con cualquier tendencia alcista activan directamente.

### 3.3 Particularidades

- **Bancos / financieras** (lista `_FINANCIAL_SECTOR_SKIP_C1` del Filtro 1, hardcodeada): el FCF no aplica. Para el cálculo de `confirmed`, ignorar el chequeo de FCF y basarse sólo en revenue + EPS slopes.
  Nota: Filter 1 los marca como `unevaluable` y **no llegan al Filtro 2**. Por lo tanto este punto sólo importa si en algún momento se decide rehabilitarlos.

- **Argentinas:** virtualmente todas con `fundamentals = None`. Es la regla, no la excepción. El bloque fundamental termina siendo casi inerte para argentinas — todas caen en `unknown`. La compensación cerrada en `DECISIONS.md` 2026-06-24 (b): argentinas en `unknown` con cualquier tendencia alcista activan desempate completo directo, con búsqueda enfocada en noticias macro/regulatorias. Es coherente con la mayor exigencia para argentinas ya establecida.

---

## 4. Técnica 3 — Sentimiento/noticias (híbrido: liviano incondicional + desempate condicional)

Esta técnica **no aporta puntaje numérico**. Es un gate binario que decide si el ticker sigue en el ranking o se descarta. Es el único componente que puede **eliminar** un ticker después de que técnico y fundamental ya hablaron.

Per `DECISIONS.md` 2026-06-24 (b), corre en **dos etapas**:

1. **Chequeo liviano de hard-news** — incondicional, sobre los 297 survivors (§4.1).
2. **Desempate completo** — condicional, sólo cuando se cumplen las reglas de activación (§4.2).

### 4.1 Chequeo liviano incondicional de hard-news

Corre sobre **todos** los survivors del Filtro 1, sin excepción. Cubre el agujero C3 (profit warning) que quedó delegado al Filtro 2 desde la operacionalización del Filtro 1 (DECISIONS.md 2026-06-21).

**Alcance acotado:** sólo señales **duras**, no contexto ni matices.

- Profit warning / guidance cut anunciado en los últimos 30 días.
- Downgrade material por analyst house relevante en los últimos 30 días.
- Investigación regulatoria abierta (SEC, CNV, etc.).
- Acusación de fraude o irregularidad contable.
- Procedimiento de quiebra / Chapter 11 / concurso.

**Consulta:**

- **CEDEARs** (empresa extranjera, vía `symbol_underlying`):
  ```
  "{symbol_underlying}" OR "{company_name}"
  ("profit warning" OR "guidance cut" OR "downgraded" OR "investigation"
   OR "fraud" OR "bankruptcy" OR "Chapter 11")
  past 30 days
  ```
- **Argentinas:**
  ```
  "{ticker}" OR "{nombre_empresa}"
  ("profit warning" OR guidance OR "rebaja" OR investigación
   OR fraude OR quiebra OR concurso)
  últimos 30 días
  ```

**Resultados posibles:**

- `clean`: no se encontró ninguna señal dura → flujo normal sigue al paso §4.2 (desempate completo según condiciones).
- `hard_news_detected`: se encontró al menos una señal dura → **escalación automática al desempate completo (§4.3)** para evaluar materialidad y decidir verdict final.

**Implementación:**

- Volumen: 297 chequeos por ciclo semanal. Por ser búsqueda con términos cerrados, viable con WebSearch (más barato que el desempate completo, que requiere parseo contextual).
- Caching: resultado cacheable 3-5 días.
- Fail-open: si la búsqueda falla por error técnico, default a `clean` con `warning` adjunto al ticker (no escalar por falla del proveedor).

### 4.2 Activación del desempate completo

El desempate completo se activa cuando se cumple **al menos una** de estas tres condiciones:

**(A) El chequeo liviano de §4.1 disparó (`hard_news_detected`).** Escalación automática para evaluar materialidad.

**(B) Técnico y fundamental divergen explícitamente** — definido por el cruce `trend_regime_label` × `fundamental_state` (sólo CEDEARs con fundamentals disponibles aplican acá):

|                      | confirmed       | neutral       | deteriorating         | unknown   |
|----------------------|-----------------|---------------|-----------------------|-----------|
| **strong_up**        | coincide (omitir)| **no coincide → activar** | **no coincide → activar** | **activar** (alta convicción sin info)¹ |
| **mild_up**          | coincide (omitir)| **no coincide → activar** | **no coincide → activar** | omitir² |
| **sideways**         | omitir³         | omitir³       | omitir³               | omitir³   |
| **mild_down / strong_down** | (no debería estar acá — `trend_regime` bajo no daría score suficiente para entrar al ranking) |

¹ **CEDEAR `unknown + strong_up`:** activa desempate completo. Es el caso "alta convicción técnica + cero info fundamental" que merece control extra (DECISIONS.md 2026-06-24 b, opción A).
² **CEDEAR `unknown + mild_up`:** el chequeo liviano de §4.1 ya cubrió el riesgo de hard-news. Sin divergencia explícita ni señal de máxima convicción, no se justifica un desempate completo. Decisión cerrada — opción A, no se incluye `mild_up`.
³ **`sideways`:** el técnico no da señal de compra de momentum. Estos tickers probablemente no entran al ranking final por su `technical_score` bajo, no por desempate. No tiene sentido gastar tokens en news para algo que igual no se va a operar.

**(C) Argentina-specific: cualquier argentina en `unknown` con tendencia alcista** (`strong_up` o `mild_up`) activa desempate completo directo. Compensación por el gap estructural de fundamentals para argentinas (DECISIONS.md 2026-06-24 b).

### 4.3 Qué hace el desempate completo cuando se activa

Para cada ticker que activa desempate, una llamada de WebSearch con consulta más amplia que la del liviano:

- **CEDEARs** (empresa extranjera):
  ```
  "{symbol_underlying}" OR "{company_name}"
  (earnings warning OR guidance OR downgrade OR investigation OR fraud OR layoffs
   OR M&A OR lawsuit OR restructuring)
  past 30 days
  ```
- **Argentinas:**
  ```
  "{ticker}" OR "{nombre_empresa}"
  (regulación OR tarifa OR balance OR ganancias OR guidance OR sanción OR juicio
   OR macroeconómic* OR política OR brecha OR retenciones)
  últimos 30 días
  ```

Parseo del output a tres categorías:

- `confirm`: no hay news negativas materiales, o las que hay son rumores/no confirmadas. → ticker sigue en el ranking, sin cambio de score.
- `inconclusive`: hay señal mixta o ambigua. → ticker sigue en el ranking, con `warning` adjunto (no cambia score).
- `discard`: hay news duras (profit warning confirmado, downgrade material, evento regulatorio negativo grande). → ticker **fuera del ranking**.

### 4.4 Detalle de implementación

- **Volumen esperado:** 297 chequeos livianos + ~80-150 desempates completos por ciclo (estimación: ~40-50% de los 297 escalan, dependiendo de cuántos disparen el liviano + cuántos CEDEARs `unknown+strong_up` + todas las argentinas en `unknown+alcista`).
- **Caching:** resultado de cada nivel cacheable 3-5 días (la news cycle es rápida; refrescar suficientemente seguido para no perder eventos).
- **Estructura del agente:** un sub-agente con tool `WebSearch`, prompt que recibe `{symbol, name, asset_type, technical_summary, fundamental_summary, hard_news_hits}` (los hits del liviano alimentan al completo cuando hubo escalación), devuelve `{verdict, evidence_urls, notes}`.
- **Fail-open vs. fail-closed:** si WebSearch falla (rate-limit, error), default a `inconclusive` con `warning` — no descartar al ticker por una falla técnica, igual que la lógica de Filter 1 con missing data.

---

## 5. Técnica 4 — Ajuste por riesgo Argentina (modificador final)

Resta `argentina_penalty ∈ [0, 25]`. Nunca descarta. Composición distinta según `asset_type`.

### 5.1 Para CEDEARs (envoltorio)

Tres componentes, sumables hasta el cap de 25:

#### a) Volatilidad reciente del CCL (0–10)

- **Métrica:** desvío estándar móvil del CCL sobre últimos 30 días / media móvil 30d del CCL. Captura el régimen de volatilidad cambiaria.
- **Mapeo:**
  - Vol baja (típica) → 0
  - Vol moderada → 3-5
  - Vol alta (saltos discretos visibles) → 8-10
- **Razón:** un CCL volátil hace que el precio del CEDEAR en ARS sea ruidoso — afecta el timing técnico y el PnL real en USD entre cierre y ejecución. Es riesgo de envoltorio.
- Los umbrales concretos son calibración pendiente — depende de qué se observa como "vol baja típica" en la serie real.

#### b) Premium CEDEAR/subyacente (0–10)

- **Cómputo:**
  ```
  implied_ars = underlying_close_usd × ccl_spot / cedears_per_underlying
  actual_ars  = prices_ars.close.iloc[-1]
  premium     = actual_ars / implied_ars - 1
  ```
- **Necesita:** precio del subyacente en USD del cierre más reciente, vía yfinance del `symbol_underlying` (ej. "AAPL", "MSFT"). Una llamada extra por CEDEAR, cacheable un día.
- **Mapeo:**
  - |premium| < 2% → 0 (alineado)
  - premium > +5% → 8-10 (pagar caro vs. subyacente)
  - premium < −5% → 3-5 (CEDEAR barato; menos negativo, pero refleja poca demanda)
  - |premium| en zona intermedia → 3-5

#### c) Liquidez del envoltorio vs. subyacente (0–5)

- **Cómputo:** mediana de `volume × close` del CEDEAR en ARS últimas 20 barras, convertida a USD con CCL, dividida por (mediana de `volume × close` del subyacente en USD).
- **Razón:** ratio bajo = CEDEAR es "esquina" del libro, mayor slippage de ejecución.
- El Filtro 1 ya removió los completamente ilíquidos (C4 a 1M ARS/día); acá es matiz fino para sizing y advertencia.
- Otra llamada cacheable por subyacente.

### 5.2 Para acciones argentinas directas

- **Volatilidad del CCL:** mismo cómputo (afecta también al precio del activo en pesos vía dinámica macro). 0-8.
- **Sin componente de "premium":** no hay subyacente, no hay ratio.
- **Sin liquidez vs. exterior:** idem.
- **Bandera A3 del YAML (`argentina_risk_flags.yaml`):** si el ticker tenía `a3` (priority_attention) en el Filtro 1, agregar 5-10 puntos de penalidad acá. La bandera reaparece con un peso explícito en el Filtro 2 — no se descarta (eso lo hacen A1/A2), pero suma peso al modificador.
- **Profundización macro/regulatoria:** la sección argentinas del criterio dice "se profundiza el detalle" en Filtro 2. Esto se resuelve vía el desempate de la técnica 3 (consulta de news regulatorias/tarifarias específica), no acá. La penalidad estructural del A3 es una señal de "amerita atención"; el desempate decide si la atención lleva a descartar.

### 5.3 Sobre reutilizar el YAML del Filtro 1

- A1, A2 → ya descartaron en Filter 1, no aparecen.
- A3 → re-entra como bandera de penalidad en Filtro 2. Es la decisión consistente con el espíritu del criterio ("se profundiza acá").
- Si en el futuro algún ticker quedara en A3 que el usuario quiera tratar como riesgo mucho mayor sin descartar, ese caso es manejable subiendo manualmente la penalidad en YAML — no necesita lógica nueva.

---

## 6. Output del Filtro 2

### 6.1 Estructura por oportunidad

```
Filter2Opportunity:
  symbol: str
  asset_type: cedear | argentine_stock
  name: str

  # Driver
  technical_score: float (0-100)
  technical_breakdown: TechnicalResult (ver §2.2)
  technical_signal_summary: str   # "Breakout sobre máximos 50d con volumen 2x; MA50/200 alineadas con pendiente positiva; RS vs SPY +12%."

  # Confirmación de calidad
  fundamental_state: confirmed | neutral | deteriorating | unknown
  fundamental_penalty: float (0-30)
  fundamental_summary: str   # "Revenue slope +6%/q; EPS slope estable; FCF TTM positivo." | "Fundamentals no disponibles para argentina."

  # Desempate (sólo si se activó)
  sentiment_gate: none | confirm | inconclusive | discard
  sentiment_evidence: list[str]   # urls o "n/a — no activado"
  sentiment_summary: str

  # Modificador Argentina
  argentina_penalty: float (0-25)
  argentina_breakdown: dict   # {ccl_vol, premium, liquidity} para CEDEAR; {ccl_vol, a3_flag, a3_reason} para argentina

  # Score final + ranking
  final_score: float (0-100)
  rank: int  # 1 = mejor

  # Invalidación técnica
  invalidation_level_ars: float
  invalidation_level_usd: float   # informacional, vía CCL
  invalidation_rationale: str   # "Soporte swing 1230 ARS (más cerca que MA50 a 1198)."

  # Capital sugerido
  proposed_capital_usd: float
  proposed_capital_pct: float
  capital_rationale: str   # "Top 1 del ranking, score 78 vs. score promedio 52."

  warnings: list[str]
```

### 6.2 Nivel de invalidación técnica

Cómputo por ticker:

1. **Swing low más reciente:** mínimo local en los últimos ~30-50 días, donde "swing low" = barra con N barras anteriores y N posteriores todas con cierre superior (N ≈ 3-5 — calibración pendiente).
2. **Nivel de MA relevante:** la MA que sostiene la entrada. Si el técnico aprobó con `trend_regime` apoyándose principalmente en MA50, ese es el nivel; si fue MA200, ese.
3. **Invalidación final:** `max(swing_low, MA_relevante × 0.97)` — el nivel **más cercano al precio actual** entre los dos, con un colchón chico (~3%) abajo de la MA para filtrar ruido intradía.
   - Rationale: el nivel más cercano es el que el precio probablemente toque primero. Si la MA50 está aún arriba del swing low, la MA es el límite operativo.
   - El colchón 3% es calibración pendiente.

**Ese único nivel se reporta**, junto con la razón (qué soporte / qué MA lo definió).

### 6.3 Propuesta de distribución de capital

Algoritmo, después del ranking:

1. **Filtrado por score mínimo:** descartar oportunidades con `final_score < MIN_SCORE` (umbral calibrable, ej. 40). Esto previene rankear tickers que técnicamente pasan pero son débiles.
2. **Capar el ranking a 10 posiciones** (top 10 por `final_score`).
3. **Reserva de cash variable:**
   - N ≤ 5 → 20% reserva
   - 6 ≤ N ≤ 8 → 15%
   - 9 ≤ N ≤ 10 → 10%
4. **Capital invertible:** `total_capital × (1 − reserve_pct)`.
5. **Pesos relativos por score, con flattening:**
   - Para cada ticker i: `weight_raw_i = score_i^α`, con α ∈ [0.5, 1.0]. α < 1 aplana la distribución (que no haya un ticker con el 60% del capital y otros con 3%). Propongo α = 0.7 — calibración pendiente.
   - `weight_norm_i = weight_raw_i / sum(weight_raw_j)`.
   - `capital_i = investable × weight_norm_i`.
6. **Piso por posición:** definir `MIN_POSITION_USD` (ej. USD 500 — calibración pendiente). Si `capital_i < piso`, dos opciones:
   - **a)** Eliminar el ticker del ranking y redistribuir (preferida — evita posiciones de tamaño no significativo).
   - **b)** Bumpear a piso y reducir proporcionalmente al resto (alternativa).
   - Recomendación: **(a)**, con un único pase iterativo (si tras eliminar uno, otro queda por debajo del piso, repetir).
7. **`capital_rationale` por posición:** "score 78 vs. promedio del ranking 52 → peso relativo 24% del invertible".

**Distribución resultante** se reporta como propuesta, no como orden de ejecución (criterio: decisión final del usuario).

---

## 7. Decisiones cerradas

Las tres ambigüedades que originalmente bloqueaban la implementación quedaron cerradas el 2026-06-24. Registro canónico: `DECISIONS.md` entrada 2026-06-24 (b). Resumen acá para referencia rápida del implementador.

### Decisión #1 — Chequeo de noticias duras: híbrido en dos etapas (opción γ)

Resuelve el agujero de C3 (profit warning) que había quedado delegado al Filtro 2 desde la operacionalización del Filtro 1.

- **Etapa 1 — chequeo liviano incondicional** sobre los 297 survivors, buscando sólo señales duras (profit warning, guidance cut, downgrade material, investigación regulatoria, fraude, quiebra). Ver §4.1.
- **Etapa 2 — desempate completo condicional**, se activa por: (a) escalación automática desde el liviano, (b) divergencia técnico-fundamental, o (c) regla argentina-específica. Ver §4.2.

Descartadas: α (sólo desempate condicional — dejaba el agujero) y β (chequeo completo sobre los 297 — costo desproporcionado).

### Decisión #2 — CEDEARs con `fundamentals = None`: opción A (sólo `strong_up`)

Para CEDEARs en `fundamental_state = unknown`, el desempate completo se activa **únicamente cuando `trend_regime_label = strong_up`**. `mild_up` con `unknown` no activa — queda cubierto sólo por el chequeo liviano de la decisión #1.

- Tratamiento equivalente a "neutral acotado a strong_up": ni `confirmed` (demasiado permisivo) ni `neutral` siempre (demasiado caro).
- Ver §4.2 tabla, nota ¹ y nota ².

### Decisión #3 — Argentinas sin fundamentals: aceptar el gap, compensar con desempate

- **Gap aceptado:** no se intenta fuente alternativa de fundamentals para argentinas (CNV diferida; ya registrado en DATA_SOURCES.md). El bloque fundamental queda inerte para argentinas — todas caen en `unknown`.
- **Compensación:** cualquier argentina en `unknown` con tendencia alcista (`strong_up` o `mild_up`) activa desempate completo directo, con búsqueda enfocada en noticias macro/regulatorias argentinas. Ver §4.2 condición (C).
- Coherente con la mayor exigencia para argentinas ya establecida en `CRITERIOS_INVERSION.md`.

### Ajuste adicional — eliminado `momentum_macd_adx`

Eliminado el sub-score `momentum_macd_adx` (0–5) de la técnica 1. 5 puntos sobre 100 no mueve rankings en la práctica y agrega complejidad de implementación sin beneficio real. Ya reflejado en §2.1 (cuatro sub-componentes, no cinco).

### Gaps menores aceptados como limitaciones

- **Vs. sector sin clasificación nativa** — §2.1 c, arrancar con opción (1) (omitir vs. sector).
- **Trend de márgenes ausente** — §3.1, queda como limitación; extender el fetcher si la primera corrida lo amerita.
- **Posición competitiva/sectorial cualitativa** — sin datos, queda fuera del scope automatizable.

### Lo que ya estaba resuelto en criterio (no era pregunta abierta)

- Argentina nunca descarta — modificador acotado, ver §5.
- Stop técnico, no % fijo — ver §6.2.
- Capital ponderado por score relativo — ver §6.3.
- Análisis en ARS, PnL en USD — invalidación en ARS (operativa), USD informacional. Consistente con `DECISIONS.md` 2026-06-20 (c).

---

## 8. Resumen del flujo, end-to-end

```
Input: 297 Filter1Result(survivor) con TickerBundle

Para cada survivor:
  1. Calcular technical_score (0-100) + breakdown                       [§2]
  2. Calcular fundamental_state + fundamental_penalty                    [§3]
  3. Chequeo liviano incondicional de hard-news                          [§4.1]
     ├─ clean              → seguir a paso 4 con flujo normal
     └─ hard_news_detected → escalar (forzar activación del desempate completo en paso 4)
  4. Determinar si activar desempate completo (técnica 3)                [§4.2]
     Activa si: (A) hubo escalación del paso 3, o
                (B) divergencia técnico-fundamental (tabla §4.2 B), o
                (C) argentina en unknown con tendencia alcista (§4.2 C).
     ├─ no activa → sentiment_gate = none
     └─ activa    → WebSearch → confirm/inconclusive/discard             [§4.3, §4.4]
  5. Si sentiment_gate == discard → fuera del ranking
  6. Calcular argentina_penalty                                          [§5]
  7. final_score = max(0, technical - fund_pen - arg_pen)

Post-procesamiento:
  8. Filtrar por final_score >= MIN_SCORE
  9. Top 10 por final_score
  10. Calcular invalidation_level y propuesta de capital                 [§6.2, §6.3]

Output: ranking con 0 a 10 oportunidades, cada una con todos los campos del §6.1.
```

---

**Spec cerrada para implementación.** El siguiente paso es una sesión de implementación: estructura del módulo `analysis/filter2_deep_dive/`, mapeo de umbrales a un `filter2_thresholds.py` análogo al del Filtro 1 (todos marcados como calibración pendiente), y diagnostics paralelo para calibrar sobre los 297 reales.
