# Diseño del Filtro 2 — propuesta para revisión

> Documento de diseño (solo diseño, no implementación). Sesión 2026-06-24.
> Insumo: 297 survivors del Filtro 1 sobre universo real (391 tickers).
> Tres ambigüedades sin resolver al final (§7) — esperan decisión del usuario antes de implementar.

---

## 0. Insumo real de esta sesión

297 survivors del Filtro 1 sobre universo de 391 (370 CEDEARs + 21 argentinas). Cada uno trae el `TickerBundle` completo:

- `prices_ars` (OHLCV diario, ~500 barras vía yfinance `.BA`) — siempre presente para survivors (los `MISSING/ERROR/PARTIAL` no llegan acá).
- `ccl_series` (serie histórica + spot vía dolarapi/argentinadatos).
- `fundamentals` — **puede ser `None`** y lo es de forma asimétrica:
  - Argentinas: virtualmente todas tienen `fundamentals = None` (FMP no cubre `.BA`).
  - CEDEARs: la mayoría tiene, pero algunos no (emerging markets sin cobertura FMP).
- `metadata.cedears_per_underlying`, `symbol_underlying`, `asset_type`.

Esto es importante porque la asimetría argentinas/CEDEARs en disponibilidad fundamental **interactúa con el rol del desempate** — ver pregunta abierta en §7.

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

Propongo cinco sub-componentes, cada uno con su rango:

| Sub-score | Aporte | Idea |
|---|---|---|
| `trend_regime` | 0 – 50 | Combina estructura semanal + estructura diaria + alineación de MAs. Es el "núcleo" del score técnico. |
| `breakout_bonus` | 0 – 15 | Bonus binario si hay ruptura reciente confirmada por volumen. |
| `relative_strength` | −15 a +15 | Fuerza vs. índice de referencia (y eventualmente sector). |
| `momentum_rsi` | −15 a 0 | **Sólo resta.** Penaliza sobrecompra sin contexto, RSI < 30 (señal de cambio de tendencia, no de compra). |
| `momentum_macd_adx` | 0 – 5 | Sub-bonus chico por confirmación adicional (MACD bullish / ADX > 25). Opcional. |

`technical_score = clip(trend_regime + breakout_bonus + relative_strength + momentum_rsi + momentum_macd_adx, 0, 100)`

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

#### e) `momentum_macd_adx` (0–5) — confirmación adicional opcional

- MACD por encima de su signal y con histograma creciente → +3.
- ADX > 25 (tendencia "real", no rango) → +2.
- Opcional, calibración pendiente sobre si vale la complejidad extra para 5 puntos.

### 2.2 Output del bloque técnico

```
TechnicalResult:
  technical_score: float (0-100)
  breakdown:
    trend_regime: (weekly_strength, daily_strength, ma_alignment)
    breakout: bool + detail (date, volume_ratio)
    relative_strength: float + benchmark used
    rsi_state: ok / overbought_with_context / overbought_no_context / oversold
    macd_adx: bool flags
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

> ⚠️ **GAP — sin trend de márgenes:** el data layer hoy guarda sólo el último trimestre de gross/operating margin. El criterio pide "salud financiera (márgenes)" y "tendencia". Opciones:
> 1. **Aceptar el gap** y usar márgenes sólo como nivel absoluto vs. mediana del universo.
> 2. **Extender el fetcher** para guardar margen por trimestre (4-5 datos). Bajo costo — ya tenés `income_sorted` en `data/fundamentals.py:130`; sólo agregar dos campos al snapshot.
>
> Recomendación: (2) en una sesión corta de data layer antes de implementar Filtro 2. Pero como decisión es tuya, lo dejo como pregunta.

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
  - PERO el `fundamental_state = unknown` interactúa con la técnica 3 (desempate). Ver §7 pregunta abierta #2.

### 3.3 Particularidades

- **Bancos / financieras** (lista `_FINANCIAL_SECTOR_SKIP_C1` del Filtro 1, hardcodeada): el FCF no aplica. Para el cálculo de `confirmed`, ignorar el chequeo de FCF y basarse sólo en revenue + EPS slopes.
  Nota: Filter 1 los marca como `unevaluable` y **no llegan al Filtro 2**. Por lo tanto este punto sólo importa si en algún momento se decide rehabilitarlos.

- **Argentinas:** virtualmente todas con `fundamentals = None`. Es la regla, no la excepción. El bloque fundamental termina siendo casi inerte para argentinas — todas caen en `unknown`. Esto es **una asimetría estructural relevante** que afecta el rol del desempate. Ver §7 pregunta abierta #3.

---

## 4. Técnica 3 — Desempate por sentimiento/noticias (condicional)

Esta técnica **no aporta puntaje numérico**. Es un gate binario que decide si el ticker sigue en el ranking o se descarta. Es el único componente que puede **eliminar** un ticker después de que técnico y fundamental ya hablaron.

### 4.1 Condición de activación — "no coinciden"

Defino "coinciden" / "no coinciden" en términos del cruce entre `trend_regime_label` (técnico) y `fundamental_state`:

|                      | confirmed       | neutral       | deteriorating         | unknown   |
|----------------------|-----------------|---------------|-----------------------|-----------|
| **strong_up**        | coincide (omitir)| **no coincide → activar** | **no coincide → activar** | ❓ ambiguo (ver §7) |
| **mild_up**          | coincide        | **no coincide → activar** | **no coincide → activar** | ❓        |
| **sideways**         | omitir¹         | omitir¹       | omitir¹               | omitir¹   |
| **mild_down / strong_down** | (no debería estar acá — `trend_regime` bajo no daría score suficiente para entrar al ranking) |

¹ `sideways`: el técnico no da señal de compra de momentum. Estos tickers probablemente no entran al ranking final por su `technical_score` bajo, no por desempate. No tiene sentido gastar tokens en news para algo que igual no se va a operar.

### 4.2 Qué hace cuando se activa

Para cada ticker que activa desempate, una llamada de WebSearch con consulta estructurada:

- **CEDEARs** (empresa extranjera):
  ```
  "{symbol_underlying}" OR "{company_name}"
  (earnings warning OR guidance OR downgrade OR investigation OR fraud OR layoffs)
  past 30 days
  ```
- **Argentinas:**
  ```
  "{ticker}" OR "{nombre_empresa}"
  (regulación OR tarifa OR balance OR ganancias OR guidance OR sanción OR juicio)
  últimos 30 días
  ```

Parseo del output a tres categorías:

- `confirm`: no hay news negativas materiales, o las que hay son rumores/no confirmadas. → ticker sigue en el ranking, sin cambio de score.
- `inconclusive`: hay señal mixta o ambigua. → ticker sigue en el ranking, con `warning` adjunto (no cambia score).
- `discard`: hay news duras (profit warning confirmado, downgrade material, evento regulatorio negativo grande). → ticker **fuera del ranking**.

### 4.3 Detalle de implementación del web search

- **Volumen esperado:** de 297 survivors, asumiendo que ~40% activan desempate (estimación — depende mucho de cuántos tengan `fundamentals = unknown` y de cómo se resuelva la pregunta abierta #3), serían ~120 web searches por ciclo semanal. Costoso pero acotado.
- **Caching:** resultado de web search cacheable 3-5 días (la news cycle es rápida; refrescar suficientemente seguido para no perder eventos).
- **Estructura del agente:** un sub-agente con tool `WebSearch`, prompt que recibe `{symbol, name, asset_type, technical_summary, fundamental_summary}`, devuelve `{verdict, evidence_urls, notes}`.
- **Fail-open vs. fail-closed:** si WebSearch falla (rate-limit, error), default a `inconclusive` con `warning` — no descartar al ticker por una falla técnica, igual que la lógica de Filter 1 con missing data.

> ⚠️ **AMBIGÜEDAD CRÍTICA** — el chequeo de noticias duras (profit warning, downgrades materiales) **estaba en C3 del Filtro 1 y se delegó al Filtro 2** con la nota explícita "el chequeo de noticias duras debe ser incondicional, dado que hoy el research de noticias del Filtro 2 es solo desempate condicional" (DECISIONS.md 2026-06-21).
>
> Esto significa que con el diseño actual del Filtro 2 (desempate **condicional**), un ticker con técnico fuerte + fundamental confirmado + profit warning reciente **no recibiría chequeo de news** y entraría al ranking sin advertencia. Es la falla obvia de no haber resuelto esto en su momento.
>
> Ver §7 pregunta abierta #1 con las opciones que veo.

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

## 7. Gaps y preguntas abiertas — PAUSA antes de implementar

Hay tres ambigüedades que me niego a resolver por mi cuenta, según tu regla. Necesito tu decisión antes de pasar a implementación.

### Pregunta abierta #1 — Chequeo de noticias duras: ¿incondicional o desempate-only?

**Origen:** DECISIONS.md 2026-06-21 dejó C3 (profit warning) explícitamente diferido al Filtro 2 con la nota "el chequeo de noticias duras debe ser incondicional, dado que hoy el research de noticias del Filtro 2 es solo desempate condicional".

**Conflicto:** el Filtro 2 actual define el web research como desempate condicional únicamente. Un ticker con técnico fuerte + fundamental confirmado + profit warning reciente **pasaría sin chequeo**.

**Opciones:**

- **α — Mantener desempate condicional, ignorar el riesgo de C3:** acepta que tickers con news malas recientes pueden pasar si tech + fund coinciden. Simple, barato, pero deja un agujero conocido.
- **β — Chequeo de hard-news incondicional sobre todos los survivors:** ~297 web searches/ciclo, costo notable. Bulletproof.
- **γ — Híbrido en dos etapas:** un check liviano (consulta web acotada por términos duros: "profit warning", "guidance cut", "downgrade", "investigation") sobre **todos** los survivors. Si dispara → escalación al desempate completo (técnica 3). Si no → flujo normal.
  - Costo: ~297 chequeos livianos (potencialmente con motor de news API más barato que WebSearch full) + ~40-120 desempates completos.
  - Recomendación mía: γ. Cubre el agujero sin disparar el costo a la luna.

**Si elegís cambiar el criterio (cualquier opción salvo α), va a DECISIONS.md.**

### Pregunta abierta #2 — Fundamentals = None y "no coinciden"

**Conflicto:** el criterio dice desempate se activa cuando "técnico y fundamental no dan una señal clara en la misma dirección". Pero `fundamental_state = unknown` no es una señal **divergente**, es una **señal ausente**. ¿Cuenta como "no coinciden"?

**Opciones:**

- **a — Tratar unknown como confirmed:** asume que si no hay datos malos, no hay datos malos. Sentimiento NO se activa. Riesgo: una empresa con problemas reales sin cobertura FMP pasaría sin filtro.
- **b — Tratar unknown como neutral:** sentimiento se activa siempre que técnico sea ≥ mild_up. Más conservador, más caro.
- **c — Activar sentimiento sólo cuando unknown coincida con `trend_regime_label = strong_up`:** el caso "alta convicción técnica + cero info fundamental" merece un control. Caso intermedio.

Esto interactúa con la pregunta #1: si el chequeo de hard-news se vuelve incondicional (opción γ de #1), entonces la pregunta #2 importa menos — todos pasan por hard-news de todos modos, y el desempate sólo se activa para casos donde técnico y fundamental divergen explícitamente.

### Pregunta abierta #3 — Argentinas y el rol de fundamentals

**Hecho estructural:** casi todas las argentinas tienen `fundamentals = None` (FMP no cubre `.BA`). El bloque fundamental queda inerte para ellas. El criterio no aborda esta asimetría.

**Implicancia práctica:** según la combinatoria de #2, las argentinas o pasan sin filtro de calidad (opción a), o todas activan desempate (opción b/c). Ambas posturas son defendibles.

**Pregunta adicional implícita:** ¿el sistema debería intentar **una fuente alternativa de fundamentals para argentinas** (CNV, balance manual, alguna API criolla) — o aceptamos el gap y compensamos con desempate por noticias macro/regulatorias más profundo en argentinas?

Mi instinto: aceptar el gap por ahora (no inventar fuente sin verificar disponibilidad) y compensar con desempate mejorado para argentinas. Pero es tu llamada.

### Gaps menores (no son ambigüedad — son limitaciones a documentar)

- **Vs. sector sin clasificación nativa** — §2.1 c, opciones detalladas.
- **Trend de márgenes ausente** — §3.1, propuesta de extender el fetcher.
- **Posición competitiva/sectorial cualitativa** — sin datos, queda fuera del scope automatizable.

### Lo que NO está como pregunta abierta porque ya está resuelto en criterio

- Argentina nunca descarta — modificador acotado, ya implementado en §5.
- Stop técnico, no % fijo — ya implementado en §6.2.
- Capital ponderado por score relativo — ya implementado en §6.3.
- Análisis en ARS, PnL en USD — invalidación en ARS (operativa), USD informacional. Consistente con DECISIONS.md 2026-06-20 (c).

---

## 8. Resumen del flujo, end-to-end

```
Input: 297 Filter1Result(survivor) con TickerBundle

Para cada survivor:
  1. Calcular technical_score (0-100) + breakdown          [§2]
  2. Calcular fundamental_state + fundamental_penalty       [§3]
  3. (PREGUNTA #1) hard-news check liviano                  [§7.1, depende de decisión]
  4. Determinar si activar desempate (técnica 3)            [§4.1]
     ├─ no → sentiment_gate = none
     └─ sí → WebSearch → confirm/inconclusive/discard
  5. Si sentiment_gate == discard → fuera del ranking
  6. Calcular argentina_penalty                             [§5]
  7. final_score = max(0, technical - fund_pen - arg_pen)

Post-procesamiento:
  8. Filtrar por final_score >= MIN_SCORE
  9. Top 10 por final_score
  10. Calcular invalidation_level y propuesta de capital    [§6.2, §6.3]

Output: ranking con 0 a 10 oportunidades, cada una con todos los campos del §6.1.
```

---

**Esperando decisión sobre las tres preguntas abiertas de §7 antes de avanzar.** Cuando estén resueltas, el siguiente paso natural es una sesión de implementación: estructura del módulo `analysis/filter2_deep_dive/`, mapeo de umbrales a un `filter2_thresholds.py` análogo al del Filtro 1 (todos marcados como calibración pendiente), y diagnostics paralelo para calibrar sobre los 297 reales.
