# Hallazgos — sesión 2026-11-27 (resumen de traspaso)

Alcance: análisis de solo lectura sobre la corrida 2026-11-27 (`data_date` 2026-11-26). No se cambiaron gates, score ni datos. Los scripts de análisis quedaron en el scratchpad de la sesión (temporales, no forman parte del repo).

---

## 1. Hallazgos confirmados

### 1.1 Ex-dividendo de UGP (2026-11-25)

- Ex-date del ADR: 2026-11-25, $0.18 por acción (3.43 % sobre el cierre de 5.25). En B3 fue el 2026-11-24 (R$ 1.00). Confirma el +1 día hábil de #40.
- CEDEAR: abrió el 11-25 en 9300 contra un cierre de 9405 el 11-24 (−1.1 %); el ADR abrió −1.9 %.
- Con el CCL alineado, el CEDEAR en USD hizo **+0.05 %** el 11-25 y el ADR +0.19 % (solo precio): diferencia −0.14 pp. **La caída por dividendo apareció completa el 11-25**, tapada por la suba del subyacente (UGPA3 convertido a USD +2.47 %).
- 11-26 (NYSE cerrado): CEDEAR en USD +1.51 % contra +8.25 % del subyacente sintético (UGPA3 convertido a USD). Quedó ~6.7 pp atrás con 103 nominales operados.
- Posición paper UGP 11-25 (entrada 9404.82, stop 9113.95): mínimos de 9205 (11-25) y 9200 (11-26). **No tocó el stop.** La distancia al stop al entrar (3.09 %) era menor que el dividendo (3.43 %).

Desfase BYMA de UGP con el CCL alineado según el régimen de cada fecha (ver 1.6):

| Ex-date | Corrimiento CCL | Dividendo ADR (rendimiento) | ADR | UGP.BA ARS | CCL | CEDEAR USD | Diferencia CEDEAR − ADR |
|---|---|---|---|---|---|---|---|
| 2025-03-10 | ninguno | $0.078 (2.73 %) | −4.55 % | −5.43 % | +0.72 % | −6.10 % | −1.56 pp |
| 2025-08-25 | ninguno | sin dato en yf | −0.89 % | +1.12 % | +2.57 % | −1.41 % | −0.52 pp |
| 2025-12-12 | ninguno | sin dato en yf | −2.00 % | −2.30 % | +0.35 % | −2.63 % | −0.63 pp |
| 2026-08-26 | ninguno | $0.193 (2.88 %) | −3.73 % | −4.19 % | +0.37 % | −4.54 % | −0.80 pp |
| 2026-11-25 | 1 sesión | $0.18 (3.43 %) | +0.19 % | −1.54 % | −1.59 % | +0.05 % | −0.14 pp |

Desvío diario de la diferencia CEDEAR − ADR desde el 2026-09-08: **1.08 pp con el CCL sin alinear y 0.47 pp alineado**. En 2025-01 a 2026-11 completo baja de 1.03 a 0.98 pp.

### 1.2 Entrada en la apertura siguiente a `data_date`

- Hay 95 outcomes resueltos; 76 tienen `next_open_ars` y la fecha de la barra de entrada. Desde el cache se reproducen los 76 outcomes registrados.
- En 55 de los 76, la sesión siguiente a `data_date` es la barra del `scan_date`, que **el tracker actual no evalúa** (ventana `index > scan_date`, `analysis/reversal/outcome_tracker.py:108-111`).
- Método: entrada = `next_open_ars`; stop en el mismo nivel; targets relativos a la nueva entrada; la ventana arranca en esa sesión (inclusive) y termina en `scan_date` + 20 días. **El recálculo cambia dos cosas a la vez:** el precio de entrada y la inclusión de la sesión del `scan_date` en la ventana. Las cifras de abajo mezclan los dos efectos; no se separaron.
- **Cambian de estado 17 de 76:**

| Cambio | n | Casos |
|---|---|---|
| stop_hit → no hay entrada (apertura ≤ stop) | 6 | SWKS 07-03, VIVT3 08-03 y 08-04, DECK 08-11, MU 11-20, TSM 11-20 |
| stop_hit → sin R válido (defecto de dato: invalidación ≥ entrada) | 1 | ADGO 08-03 |
| target → stop_hit | 2 | RIOT 09-02 (+6.2R → −1.04R), HL 09-17 (+1.6R → −1.03R) |
| target_5 → lateral | 2 | DECK 07-01, NVS 09-23 |
| lateral → target_5 | 1 | GSK 08-14 |
| cambio entre target_5 y target_8 | 5 | SNAP, KEEL (8→5); SATL, SYY, ITUB3 (5→8) |

- Diferencia de R, en unidades del riesgo original, (salida − apertura) / (entrada − stop), con n=69: mediana 0.00; cuartiles −0.31 y +0.13; percentiles 10 y 90 en −1.24 y +0.63; media −0.25; extremos −6.4 (NBIS) y +1.77.
- R medio en esas filas: registrado −0.15, con entrada en apertura −0.41. La diferencia de −0.25R mezcla la entrada en apertura con la inclusión de la sesión del `scan_date`.
- Si los 7 casos sin R (6 sin entrada y ADGO) cuentan como 0R: −0.37 sobre 76 filas, contra −0.32 registrado (75 filas con R válido). **Diferencia: −0.05R.**
- Si el riesgo se recalcula desde la apertura, el R se dispara cuando la apertura cae cerca del stop. De las 69 filas con entrada, en 7 el riesgo medido desde la apertura es menor que la mitad del original: NBIS −28.1R, NVO −7.95R, ITUB3 +7.42R, GSK +5.98R, ABEV −5.09R, NGG −1.91R y RIOT −1.04R. Por eso se miden las diferencias en unidades del riesgo original.
- Gap nocturno: mediana −0.02 %; 38 negativos y 32 positivos. Sin sesgo, pero con colas gruesas.
- ITUB3 y TECO2 del 11-25: el tramo del cierre del 24 a la apertura del 25 fue negativo y toda la ganancia vino después.

| | Cierre 24 → apertura 25 | Sesión del 11-25 | 11-26 | Total registrado | Desde la apertura |
|---|---|---|---|---|---|
| ITUB3 | −3.25 % | +3.99 % | +6.32 % | +6.96 % | +10.6 % (target_8) |
| TECO2 | −2.85 % | +8.14 % | +3.05 % | +8.26 % | +8.14 % el mismo 11-25 (target_8) |

### 1.3 `stop_dist_atr` retroactivo (102 señales)

ATR de Wilder de 14 al cierre de la barra de entrada. Coincide con el `stop_dist_atr` registrado en las 6 señales que lo tienen (diferencia máxima 0.005).

| Tramo | n | stop | target | expirada | pendiente | R medio | R mediano | % de targets |
|---|---|---|---|---|---|---|---|---|
| <0.5 | 9 | 5 | 3 | 0 | 1 | +0.74 | +0.66 | 37.5 % |
| 0.5–1 | 35 | 20 | 10 | 0 | 5 | −0.01 | −1.12 | 33 % |
| >1 | 58 | 36 | 15 | 6 | 1 | −0.45 | −1.11 | 26 % |

Sin las señales que repiten una posición ya abierta (n=76): <0.5 igual; 0.5–1 con n=26 (R −0.43, 35 % de targets); >1 con n=41 (R −0.19, 35 %).
**Sin evidencia con estos n.** En <0.5 el R sale inflado por construcción (denominador chico). Después de deduplicar, el % de targets no cambia entre tramos.

### 1.4 yfinance en .BA: el ajuste por dividendos en la práctica no se aplica

- Se revisaron 28 ex-dates de 21 CEDEARs (KO, PEP, JNJ, XOM, CVX, ABBV, PG, MO, VZ, T, PFE, MRK, JPM, WMT, MCD, HD, AAPL, MSFT, UGP, ABEV, BBD) y todos muestran el mismo patrón.
- El factor de ajuste del día previo es ≈ 0.99999. Implica un dividendo igual al **monto en USD por CEDEAR restado a un precio en ARS**: KO da 0.106 = 0.53/5, MO 0.277 = 1.11/4, UGP 0.18. Es ~1/1600 del ajuste correcto.
- La columna `Dividends` sí viene en ARS, pero convertida a un tipo de cambio fijo de ≈1600, no al CCL. JNJ (11-24) y CVX (11-18) repiten el monto de agosto (143.02 y 178.11 ARS); con el CCL esperado serían 161.14 y 188.65.
- Ejemplos: KO 09-15 con factor 0.999996 (esperado 0.9941); MO 09-15 con 0.999990 (esperado 0.9843); VZ 10-09 con 0.999991 (esperado 0.9847).
- **Consecuencia:** el cache .BA está de hecho sin ajustar. Las caídas por ex-dividendo entran como movimiento de precio en RSI, MA, soportes y ATR. Del lado bueno, entradas y stops quedan en la misma base que el precio en vivo. En los ADR (por ejemplo UGP) el ajuste sí se aplica bien.
- El docstring de `analysis/reversal/outcome_tracker.py:42-44` supone que `auto_adjust` reescala el histórico tras un dividendo. Para .BA no pasa en la práctica.

### 1.5 Barras fantasma e inconsistencia con feriados de EE.UU.

- Los feriados de BYMA de 2026 están limpios: 14 días hábiles sin ninguna barra (incluidos el 11-09, feriado nacional por la visita del Papa, y el 11-23).
- **2026-11-10:** feriado bancario nacional (BCRA, Com. A 8487) y feriado en CABA. No hubo volumen en ninguno de los 311 tickers. yfinance generó barras planas, con volumen 0, para **201 tickers (180 CEDEARs y 21 acciones locales)**; en 199 el precio es igual al cierre anterior. Los otros 110 no tienen barra ese día. No hay confirmación directa del calendario de BYMA.
- **2026-07-06** (lunes, no feriado): **155 CEDEARs** con barra plana y volumen 0, mientras las acciones locales operaron normal (GGAL movió 2.6M). Causa desconocida.
- **Días con NYSE cerrado:** entre 10 % y 20 % de los tickers .BA tienen barra plana con volumen 0. Por ejemplo: 2025-01-09 (duelo por Carter) 19.5 %, 2025-05-26 (Memorial Day) 19.5 %, 2025-11-27 12.7 %, 2026-01-19 13.8 %, 2026-06-19 12.8 %, 2026-07-03 13.1 % y 2026-11-26 13.5 %. En ADI y UGP aparecen el 2025-01-09 y el 2025-05-26. Los días sin feriado quedan por debajo de 10 %.
- **Inconsistencia:** el 2026-11-26 (Thanksgiving) generó barras fantasma en 13.5 % de los tickers, pero no en ADI ni en UGP, que tuvieron volumen real mínimo (71 y 103). yfinance no trata los feriados de EE.UU. de forma consistente entre tickers.
- Las barras salen de yfinance mismo: al volver a descargar se reproducen. No las genera el cache.
- Impacto: **9 señales y 32 near-misses** tienen una barra fantasma en su ventana de 20 barras. Las señales son AMZN 07-27, ADGO 07-30 y 08-03, HSBC y TSM 11-20, UGP y TECO2 11-25, y ADI y UGP 11-27. Bajan el promedio de volumen de 20d (sube el ratio de volumen), bajan el ATR (sube `stop_dist_atr`) y suman un día sin cambio al RSI.
- Ratio de volumen 5d/20d del 2026-11-27:

| | Registrado | Sesiones válidas (sin 11-26 ni barras planas con vol 0) | Con medianas (sesiones válidas) | ¿Gate <0.8 con el limpio? |
|---|---|---|---|---|
| ADI | 0.747 | **0.828** | 0.999 | ❌ |
| UGP | 0.408 | **0.666** | 1.110 | ✅, pero frágil: la ventana de 20d incluye 17016 (10-26) y 23402 (10-27) |

### 1.6 Regímenes del CCL (argentinadatos) y punto de cambio 2026-09-08

- El cache es idéntico a la fuente: 0 diferencias en 5078 días (2013-01-02 → 2026-11-27). El relleno hacia adelante de `data/ccl.py` no altera valores; la fuente ya publica todos los días calendario.
- Lo que cambia es **qué sesión representa cada fecha**. Se contrastó con un CCL implícito (local × ratio / ADR, mediana de GGAL, BMA, PAM y YPF) usando la correlación de cambios diarios:

| Período | Corrimiento | Evidencia |
|---|---|---|
| 2013 → ~mar-2020 | la fecha D tiene el valor de la sesión D-1 | gana el corrimiento todos los años (2018: 0.70 contra 0.08; 2019: 0.76 contra 0.12) |
| ~abr-2020 → 2026-09-07 | sin corrimiento | 2022: 0.77 contra 0.44; 2025: 0.88 contra 0.45; abr–ago 2026 sin corrimiento todos los meses |
| **2026-09-08 → hoy** | la fecha D tiene el valor de la sesión D-1 | sep: 0.60 contra 0.10; oct: 0.86 contra −0.23; nov: 0.88 contra 0.26 |

- **Punto de cambio:** la fuente no actualizó el martes 2026-09-08 (repitió 1582.60). Desde entonces va una sesión atrasada: el valor con fecha 09-09 (1591.30) coincide con el implícito de la sesión del 09-08 (1591.0), y el del 09-12, un sábado (1596.05), con el del viernes 09-11 (1596.0).
- **Prueba de fin de semana:** desde 2013 hasta agosto de 2026, el sábado repite el valor del viernes y el lunes trae uno nuevo. Desde el 09-12 hay 11 sábados: en 10 el sábado trae un valor nuevo y el lunes repite el del domingo; el otro (11-07) no tiene cambio ni el sábado ni el lunes. Ninguno muestra el patrón anterior.
- El 1803.80 de 11-21 a 11-24 es el cierre del viernes 11-20, repetido por la fuente en sábado, domingo, el lunes 11-23 (feriado) y el martes 11-24, cuya fecha corresponde a la sesión del lunes feriado. El CCL real de la sesión del 11-24 es ≈ 1795.25.
- Campos afectados:
  - `pct_change_ccl_5d`: 11-25 registrado +8.01 % (alineado ≈ +6.77 %); 11-27 registrado +4.19 % (alineado ≈ +2.56 %).
  - `_usd_implied` (RSI, fuerza semanal, MA200): las barras desde el 2026-09-08 están corridas una sesión. Las ventanas de 200 barras de las señales recientes mezclan los dos regímenes.
  - `ccl_at_scan` (spot de dolarapi) está bien.
- La referencia de ruido de #40 (desvío de 1.10 % en UGP) incluye el período contaminado.

### 1.7 Señales suprimidas que quedan `pending` para siempre

- PCAR 09-18, PCAR 09-19 y GFI 09-24 tienen `tradeable=False`, y `assess_outcomes` solo evalúa las tradeables (`analysis/reversal/outcome_tracker.py:349`). Nunca salen de `pending` y cuentan como pendientes en los resúmenes.
- Motivos: PCAR, cuarentena por stop_hit del 09-17; GFI, bloqueada por promediar a la baja.
- Outcome contrafactual (misma lógica): las tres darían **stop_hit**: PCAR −1.12R y −1.21R, GFI −4.82R. Las supresiones evitaron pérdidas (n=3, sin valor estadístico).
- Son las únicas 3 con `tradeable=False`; las otras 46 señales no tienen el campo y se toman como tradeables.
- Near-misses: ninguno quedó `pending` con el plazo vencido. Hay 27 sin outcome por diseño: sin invalidación (22) o sin entrada ni invalidación (5).

### 1.8 Menores

- PETR3 está en `yfinance_exclusions`, así que los chequeos de ex-dividendo y earnings no corren. El news check encontró una remuneración extraordinaria sobre ordinarias pagadera el 23-12.
- ADI: la ex-date estimada (12-06, `yfinance_last_dividend_estimate`) cae domingo.
- ADI con `stop_dist_atr` de 0.25: stop muy ajustado.

---

## 2. Correcciones respecto de lo dicho antes en la sesión

1. **Descomposición de UGP:** al principio dije que el CEDEAR en USD hizo −1.07 % el 11-25 y +3.15 % el 11-26. Con el CCL alineado fue **+0.05 % y +1.51 %**. La conclusión (ex-dividendo el 11-25, tapado por el subyacente) se mantiene y el ajuste contra el ADR mejora: diferencia −0.14 pp en lugar de −1.26 pp.
2. **Corrimiento del CCL:** dije que la fuente siempre pone en la fecha D+1 el valor de la sesión D y que "todo el historial de `_usd_implied` está corrido una sesión". **Incorrecto:** el corrimiento existe solo desde el 2026-09-08 (y entre 2013 y ~mar-2020). Entre abr-2020 y el 2026-09-07 no hay corrimiento.
3. **Ratio de volumen sin el 11-26:** primero dije que ni ADI (0.840) ni UGP (0.855) pasaban, corriendo las ventanas un día, y que en UGP el feriado no era la causa. Con sesiones válidas (sin el 11-26 y sin la barra plana del 11-10): **ADI 0.828 no pasa; UGP 0.666 pasa.**
4. **Barras fantasma:** dije que estaban el 11-10 y el 07-06. También hay en **todos los días con NYSE cerrado**, en 10–20 % del universo (en ADI y UGP: 2025-01-09 y 2025-05-26). También dije que el 2026-11-26 "tuvo volumen real": eso vale para ADI y UGP, pero 13.5 % del universo tuvo barra fantasma ese día.
5. **Barra del 11-10:** al principio la marqué como "posible fantasma". Quedó confirmada (BYMA sin operaciones, feriado bancario nacional).

---

## 3. Pendientes priorizados

### P1 — CCL: verificar la alineación en cada corrida

- **Qué:** no aplicar un corrimiento fijo (la fuente ya cambió de régimen dos veces). En cada corrida, estimar el corrimiento (0 o 1) en las últimas N sesiones comparando con un CCL implícito (pares local/ADR: GGAL, BMA, PAM, YPF; o CEDEARs líquidos), aplicarlo a la serie y registrar el resultado. Si el resultado es ambiguo, marcarlo; nunca corregir en silencio.
- **Archivos:** `data/ccl.py`, `analysis/reversal/fx_context.py`, `analysis/reversal/instrumentation.py`, `analysis/reversal/regime_snapshot.py` (registrar el corrimiento por corrida), `tests/` (nuevo), `docs/DECISIONS.md`.
- **Criterio de aceptación:**
  - Sobre el historial guardado reproduce los regímenes: corrimiento 0 entre abr-2020 y el 2026-09-07, y 1 desde el 2026-09-08.
  - El desvío diario de la diferencia CEDEAR − ADR de UGP desde el 09-08 queda ≤ 0.5 pp.
  - Tests con un corrimiento sintético de +1 y −1 sesión, y con un caso ambiguo que se marca.
  - `ccl_at_scan` no cambia.
  - Cada corrida registra el corrimiento detectado y su margen.
  - `cedear-pipeline-check` pasa.

### P2 — Ratio de volumen con sesiones válidas

- **Qué:** registrar los dos ratios: `vol_ratio` (el actual, que sigue siendo el del gate) y `vol_ratio_clean`, en 5 y 20 sesiones válidas. Las sesiones válidas excluyen las barras fantasma y los días con NYSE cerrado cuando el subyacente cotiza en EE.UU. o es un ADR. **Pasar el gate al ratio limpio antes del 2027-01-18.**
- **Detección de barras fantasma, en dos niveles:**
  - **Por día, cruzando tickers:** un día se marca como fantasma si **≥ 30 %** de los tickers con barra ese día tienen barra plana (open = high = low = close) y volumen 0. Referencia del umbral (2025-01 a 2026-11): los días sin feriado quedan por debajo de 10 %; los días con NYSE cerrado, entre 10 % y 20 %; el 2026-07-06 dio 52 % y el 2026-11-10, 100 %. Los días con NYSE cerrado no llegan al umbral y los cubre la regla por ticker. En un día marcado se excluyen todas las barras planas con volumen 0.
  - **Por ticker:** una barra plana con volumen 0 en un día no marcado se excluye solo si NYSE estuvo cerrado y el subyacente cotiza en EE.UU. o es un ADR (casos 2025-01-09 y 2025-05-26). Si no, cuenta como sesión real con volumen 0 (papel ilíquido).
- **Archivos:** `analysis/reversal/reversal_scanner.py` (`_volume_ratio`, gate en ~629), `analysis/reversal/near_miss_tracker.py`, `analysis/reversal/signal_registry.py`, calendario NYSE (lista fija en `data/sources/` o la dependencia `exchange_calendars`, hoy no instalada), `tests/`, `docs/DECISIONS.md`.
- **Criterio de aceptación:**
  - Reproduce ADI 0.828 y UGP 0.666 para el 2026-11-27.
  - Los dos campos aparecen en cada señal y near-miss nuevo.
  - Tests de exclusión de barras planas y de días con NYSE cerrado.
  - Con el umbral de 30 %, en 2025–2026 se marcan solo el 2026-07-06 y el 2026-11-10; ningún día con NYSE cerrado ni ningún día normal.
  - En los días con NYSE cerrado, las barras planas con volumen 0 de subyacentes de EE.UU. o ADR se excluyen por la regla por ticker.
  - Test con un papel ilíquido con volumen 0 real en un día normal: la barra queda en la ventana con volumen 0 y no se excluye.
  - Las ventanas siempre tienen 5 y 20 sesiones válidas.
  - Antes del 2027-01-18, entrada en DECISIONS.md con la comparación de near-misses entre el ratio registrado y el limpio, y el gate migrado.

### P3 — Estado `suppressed` con outcome contrafactual

- **Qué:** las señales `tradeable=False` pasan a `outcome_status = suppressed`, en lugar de quedar `pending` para siempre. Se calcula su outcome contrafactual con la misma lógica y se guarda marcado como tal, fuera del win rate de las tradeables. El resumen muestra cuánto rinden las supresiones.
- **Archivos:** `analysis/reversal/outcome_tracker.py` (filtro en :349, `summarize`), `analysis/reversal/signal_registry.py`, el reporte o resumen que muestra pendientes, `tests/`, `docs/DECISIONS.md`.
- **Criterio de aceptación:**
  - PCAR 09-18, PCAR 09-19 y GFI 09-24 quedan `suppressed`, con contrafactual stop_hit (−1.12, −1.21 y −4.82R).
  - Dejan de contar como `pending`.
  - El win rate y el R de las tradeables no cambian.
  - `positions_log.json` no se toca para las suprimidas.

### P4 — `outcomes_v2`

- **Qué (propuesta):** una segunda medición en paralelo, sin reemplazar la v1.
  - Entrada = `next_open_ars` de la sesión siguiente a `data_date`.
  - La ventana arranca en esa sesión (inclusive).
  - Si la apertura está en o debajo del stop, el estado es `no_entry_gap` (tratamiento del R a definir, ver §4).
  - R en unidades del riesgo original y R con el riesgo medido desde la apertura.
  - Marca de ex-dividendo dentro de la ventana.
  - Las barras planas con volumen 0 no cuentan como sesión.
- **Archivos:** `analysis/reversal/outcome_tracker.py`, `analysis/reversal/r_multiple.py`, `analysis/reversal/near_miss_outcomes.py`, nuevo `data/reversal_tracking/outcomes_v2.jsonl` (o campos con sufijo `_v2`), nuevo script de backfill en `scripts/`, `tests/`, `docs/DECISIONS.md`.
- **Criterio de aceptación:**
  - Sobre el corpus actual reproduce los números de 1.2: 76 filas, 17 cambios de estado, diferencia de R con mediana 0.00 y media −0.25 en unidades del riesgo original.
  - ITUB3 y TECO2 11-25 quedan target_8; MU y TSM 11-20 quedan `no_entry_gap`; ADGO 08-03 queda como defecto de dato, no como gap.
  - Se reportan **por separado** los dos efectos: (a) solo la entrada en la apertura, con la ventana actual (`> scan_date`), y (b) solo la inclusión de la sesión del `scan_date`, con la entrada al cierre. Además, el efecto combinado.
  - `outcomes.jsonl` (v1) no cambia ni un byte.
  - `cedear-feature-validation` pasa.

### Prioridad baja

- **P5:** filtrar las barras fantasma en `data/prices.py` (afectan ATR, RSI y volumen). Coordinar con P2.
- **P6:** ex-dividendo y earnings para acciones B3 directas (PETR3) vía `PETR3.SA`.
- **P7:** recalcular la referencia de ruido de #40 cuando P1 esté listo.
- **P8:** averiguar la causa de las barras fantasma del 2026-07-06.
- **P9 — `earnings_calendar_stale` en UGP (fail-open).** Si la fecha del calendario de Yahoo ya pasó, `data/earnings.py:130-133` devuelve `VERIFIED_CLEAR` con `calendar_stale=True`. UGP 11-27 quedó `verified_clear` con `days_to_earnings = null`. Criterio: un calendario vencido no da `verified_clear` (queda `unverified` o un estado explícito), con test.
- **P10 — Regla de ejecución "no entrar si la apertura está bajo el stop"** (tarjeta de Fase C en `docs/ROADMAP_CONFIABILITY.md`). Evidencia: 6 de 76 outcomes con la apertura bajo el stop (§1.2). Criterio: tarjeta escrita con la evidencia y el efecto medido en `outcomes_v2` (P4); no se implementa antes de P4.
- **P11 — Una corrida repetida con el mismo `data_date` rotula "➕ SUMA".** Archivos: `output/reversal_report.py:65` (`heading_prefix`), `analysis/reversal/suppression.py`, `analysis/reversal/signal_registry.py` (dedup por `(data_date, symbol)` de #35). Criterio: al repetir la corrida con el mismo `data_date` no aparece el rótulo SUMA contra la posición que abrió la primera corrida, con test. *(Reportado por vos; no lo reproduje en esta sesión.)*
- **P12 — Revisar el diff del gate de ex-dividendo (2b98842).** Archivos: `data/dividends.py`, `analysis/reversal/suppression.py:228-258`. Criterio: revisión hecha (por ejemplo con `/code-review`) y hallazgos registrados o descartados.
- **P13 — `ex_div_date_raw` 2026-11-24 en la fila UGP 11-25** de `data/reversal_tracking/signals.jsonl` (backfill de #41). Criterio: la fila es consistente con `ex_div_date` 2026-11-25 y su `ex_div_source`, y el backfill está documentado. *(No revisado en esta sesión.)*
- **P14 — ROKU en las exclusiones de subyacentes** (`data/sources/yfinance_exclusions.json:599`, #38). Criterio: confirmar si la exclusión del subyacente sigue haciendo falta o se puede levantar, con la decisión anotada. *(No revisado en esta sesión.)*
- **P15 — ERROR → WARNING para barras atrasadas por feriado de EE.UU.** `data/fetcher.py:151` loguea ERROR y aborta el ticker cuando la última barra es anterior al día hábil esperado; en un día con NYSE cerrado eso es esperable. Criterio: en un feriado de NYSE no hay ERROR para subyacentes de EE.UU. (queda WARNING) y el comportamiento fail-closed no cambia, con test.

---

## 4. Decisiones tomadas y preguntas abiertas

### Decisiones tomadas

- La sesión fue de solo lectura: sin cambios de gates, score ni datos.
- CCL: verificar la alineación en cada corrida, no aplicar un corrimiento fijo.
- Ratio de volumen: registrar los dos ratios y migrar el gate al limpio antes del 2027-01-18.
- Las señales suprimidas pasan a un estado propio con outcome contrafactual.
- `outcomes_v2` convive con la v1, no la reemplaza.
- Cualquier cambio de criterio (lógica o umbral) va a `docs/DECISIONS.md`.

### Preguntas abiertas

1. `outcomes_v2`: con la apertura en o debajo del stop, ¿no hay entrada (sin R), se cuenta 0R o se sale en la apertura (R < −1)?
2. ¿Cuándo pasa la v2 a ser la métrica de calibración principal?
3. Después de P1, ¿se recalculan los campos de FX y `_usd_implied` históricos en `signals.jsonl` y `near_misses.jsonl`, o se dejan y se marcan?
4. Calendario NYSE: ¿lista fija en `data/sources/` o la dependencia `exchange_calendars`?
5. Ratio de volumen: ¿media o mediana/media recortada? (el caso UGP muestra fragilidad ante operaciones grandes aisladas). Es para la auditoría mensual.
6. ¿Se cambia la vara de la v1 para incluir la barra del `scan_date`, o solo se mide en `outcomes_v2`? Historia:
   - **Origen:** el filtro `df.index > scan_dt` está desde el primer commit de `outcome_tracker.py` (43470a6, 2026-08-07). En ese momento la señal usaba el cierre del propio `scan_date` (en las señales de junio y julio, `entry_bar_date == scan_date`), así que excluir esa barra era correcto.
   - **Por qué dejó de serlo:** según #37, desde #30 (2026-09-10, publicación de yfinance al día siguiente) la señal del día X usa el cierre de X-1, y la barra X, la primera en que se puede ejecutar una orden, quedó fuera de la medición. En los datos, el primer caso con `entry_bar_date` anterior al `scan_date` es VIVT3 del 2026-08-04.
   - **Estado actual:** #35 (2026-11-20) lo dejó como pendiente. #37 (2026-11-20) instrumentó `entry_bar_date` y `next_open_ars` y decidió explícitamente que "la vara de medición no cambia". e37922a (2026-11-20) solo movió el filtro a `_after_scan` (`outcome_tracker.py:108-111`).
7. ¿El tracker acredita dividendos en posiciones paper que los cobran? (no verificado).
8. Causa de las barras fantasma del 2026-07-06.
9. ¿Parchear argentinadatos o derivar el CCL de pares local/ADR?

---

Fuentes externas usadas: BCRA Com. A 8487 (feriado bancario del 10/11/26); prensa sobre el feriado nacional del 09/11/26 por la visita del Papa; calendario bursátil de BYMA (sin entrada específica para el 10/11 en el texto consultado).
