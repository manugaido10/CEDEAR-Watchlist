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
- Método: entrada = `next_open_ars`; stop en el mismo nivel; targets relativos a la nueva entrada; la ventana arranca en la primera sesión posterior a `data_date` (inclusive) y termina en `scan_date` + 20 días. **El recálculo cambia dos cosas a la vez**, y se separaron en orden **ventana → entrada** (la salida no se tocó: stop al mínimo del día, target al cierre):
  - **(a) ventana:** v1 con la ventana desde la sesión posterior a `data_date` (inclusive) y entrada al cierre de `data_date` (`entry_price_ars`). Solo cambia algo donde esa sesión es la del `scan_date` (55 de 76; en 20 la ventana ya coincide y (a) no hace nada; en 1, BBAR 09-18, arranca antes del `scan_date`).
  - **(b) entrada:** sobre la misma ventana, la entrada pasa a `next_open_ars`; stop sin cambios; targets relativos a la apertura. Si apertura ≤ stop, no hay entrada.
  - R siempre en unidades del riesgo original: (salida − entrada) / (cierre de `data_date` − stop).
- Las 76 filas se reproducen desde el cache con v1 (76/76 estados). Una excepción de R: BNG 09-23 simulado −1.48 contra −1.27 registrado, mismo estado (ver §1.9).

**Separación de la diferencia de R (antes titulada "−0.25R")**

| Paso | R medio, 69 filas con entrada | Δ del paso | R medio, 76 filas (sin entrada = 0R) | Δ del paso | Cambios de estado del paso |
|---|---|---|---|---|---|
| v1 (registrado) | −0.155 | | −0.314 | | |
| (a) + ventana desde la sesión posterior a `data_date` | −0.269 | **−0.114** | −0.424 | **−0.110** | 3 |
| (b) + entrada en la apertura | −0.406 | **−0.137** | −0.369 | **+0.055** | 16 |
| Total v1 → (b) | | −0.251 | | −0.055 | 17 netos |

- Las 69 filas son las que tienen R válido en v1, (a) y (b). Las otras 7 son las 6 sin entrada (apertura ≤ stop) y ADGO 08-03 (defecto de dato: invalidación ≥ entrada, sin R en ningún paso). En la columna de 76 filas, ADGO cuenta 0R en los tres pasos; las 6 sin entrada tienen R en v1 y (a) (entre −1.2R y −5.5R) y 0R en (b). Por eso (b) **sube** el R en esa columna: las filas sin entrada evitan pérdidas. El v1 de 76 filas es −0.314 y no el −0.318 registrado (75 filas con R válido) porque ADGO entra como 0R.
- **(a) está concentrado:** 9 de 69 filas cambian de R (las demás, Δ = 0). Sin RIOT 09-02 (+6.22R → −1.01R: la barra del `scan_date` perfora el stop), el Δ de (a) es −0.009. Mínimo −7.23 (RIOT), máximo +1.51 (DECK 08-10, stop_hit en las dos medidas pero con otra salida).
- **(b) está repartido:** 66 de 69 filas cambian de R (32 negativas, 34 positivas, 3 en cero); mediana 0.00, cuartiles −0.25 y +0.13, P10 −0.95, P90 +0.63, mínimo −4.28 (HL 09-17), máximo +1.77 (GSK 08-14). Las 9 filas que cambian de estado suman −5.9R; las 60 restantes, −3.5R. Sin HL 09-17, el Δ de (b) es −0.076.
- Efecto combinado v1 → (b), por fila: mediana 0.00; cuartiles −0.31 y +0.13; P10 −1.24, P90 +0.63; media −0.25; extremos **−6.4 (RIOT 09-02)** y +1.77 (GSK 08-14). NBIS 11-05 da −1.87.
- **El orden importa en los estados, poco en la media.** En el orden inverso (entrada primero, ventana `> scan_date`), el paso de entrada solo da Δ −0.127 y 15 cambios de estado, y el paso de ventana el resto (−0.124 hasta −0.251). Los Δ parciales dependen del orden; el total no. Por eso P4 fija el orden.

**Cambios de estado por paso (n por categoría)**

| Categoría | (a) ventana | (b) entrada |
|---|---|---|
| target_8 → stop_hit | 1 (RIOT 09-02) | 0 |
| target_5 → stop_hit | 0 | 1 (HL 09-17) |
| stop_hit → sin entrada | 0 | 7 (SWKS 07-03, VIVT3 08-03 y 08-04, DECK 08-11, MU 11-20, TSM 11-20, ADGO 08-03 por defecto de dato) |
| target_5 → lateral | 0 | 2 (DECK 07-01, NVS 09-23) |
| lateral → target_5 | 0 | 1 (GSK 08-14) |
| target_8 → target_5 | 1 (TECO2 11-25) | 2 (SNAP 06-30, KEEL 09-16) |
| target_5 → target_8 | 1 (SATL 09-08) | 3 (SYY 11-06, ITUB3 11-25, TECO2 11-25) |
| **Total** | **3** | **16** |

TECO2 11-25 baja en (a) (target_8 → target_5) y vuelve a subir en (b); termina igual que en v1, y por eso el neto es 17 y no 19. ADGO 08-03 queda como defecto de dato (no como gap) en el criterio de P4; aquí se cuenta en "sin entrada" porque el recálculo no le encuentra R.

- Corrección respecto de la versión anterior de esta sección: el "−1.04R" de RIOT 09-02 y el "−1.03R" de HL 09-17 estaban medidos con el riesgo desde la apertura. En unidades del riesgo original, RIOT da −0.15R en (b) (y −1.01R en (a)) y HL da −2.40R en (b). El cambio de estado de RIOT viene de la ventana (a), no de la entrada en la apertura. El extremo −6.4 de la diferencia es RIOT 09-02, no NBIS.
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

### 1.9 BNG 09-23: R registrado −1.27 contra −1.48 simulado (diferencia de base del cache)

- Mismo estado (`stop_hit`, 8 días, barra del 10-01); cambia solo el precio de salida: registrado 34000, cache hoy 33772.
- El cache de BNG.BA hoy está en otra base que cuando se evaluó (2026-11-05): `entry_price_ars` 35380 y `entry_bar_close_ars` 35379.85 contra un cierre de 35143.50 en el cache del 09-22 (factor 1.00673); la salida registrada contra el mínimo del 10-01 en el cache da el mismo factor (34000 / 33772 = 1.00673). Es un reescalado uniforme de las barras previas de ~0.67 %, compatible con un ajuste por dividendo aplicado después del 11-05.
- El simulador usa entrada y stop **registrados** (base de entonces) contra barras del cache **de hoy** (base nueva): sale −1.48. Con el factor aplicado, 33772 × 1.00673 = 34000 y R = −1.27.
- Es la única fila de las 76 con diferencia de R > 0.001; el resto del corpus coincide con lo registrado.
- **Matiza §1.4** ("el cache .BA está de hecho sin ajustar"): en BNG el ajuste sí se aplicó, y es de un tamaño razonable para un dividendo trimestral. La ex-date no se verificó. Que §1.4 valga para el resto de los tickers .BA queda sin confirmar; BNG es un contraejemplo.
- Consecuencia para `outcomes_v2`: un backfill desde el cache mezcla bases. Ver el plan de P4 (factor de base por señal).

## 2. Correcciones respecto de lo dicho antes en la sesión

1. **Descomposición de UGP:** al principio dije que el CEDEAR en USD hizo −1.07 % el 11-25 y +3.15 % el 11-26. Con el CCL alineado fue **+0.05 % y +1.51 %**. La conclusión (ex-dividendo el 11-25, tapado por el subyacente) se mantiene y el ajuste contra el ADR mejora: diferencia −0.14 pp en lugar de −1.26 pp.
2. **Corrimiento del CCL:** dije que la fuente siempre pone en la fecha D+1 el valor de la sesión D y que "todo el historial de `_usd_implied` está corrido una sesión". **Incorrecto:** el corrimiento existe solo desde el 2026-09-08 (y entre 2013 y ~mar-2020). Entre abr-2020 y el 2026-09-07 no hay corrimiento.
3. **Ratio de volumen sin el 11-26:** primero dije que ni ADI (0.840) ni UGP (0.855) pasaban, corriendo las ventanas un día, y que en UGP el feriado no era la causa. Con sesiones válidas (sin el 11-26 y sin la barra plana del 11-10): **ADI 0.828 no pasa; UGP 0.666 pasa.**
4. **Barras fantasma:** dije que estaban el 11-10 y el 07-06. También hay en **todos los días con NYSE cerrado**, en 10–20 % del universo (en ADI y UGP: 2025-01-09 y 2025-05-26). También dije que el 2026-11-26 "tuvo volumen real": eso vale para ADI y UGP, pero 13.5 % del universo tuvo barra fantasma ese día.
5. **Barra del 11-10:** al principio la marqué como "posible fantasma". Quedó confirmada (BYMA sin operaciones, feriado bancario nacional).
6. **§1.2, separación de efectos:** el extremo de la diferencia de R era RIOT 09-02 (−6.4), no NBIS (−1.87); el −1.04R de RIOT y el −1.03R de HL estaban con el riesgo desde la apertura (en unidades del riesgo original: −0.15R y −2.40R, y el cambio de estado de RIOT viene de la ventana, no de la apertura); el titular "−0.25R" mezclaba dos efectos (−0.114R de ventana y −0.137R de entrada).

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

### P3 — Estado `suppressed` con outcome contrafactual — **implementado (ver DECISIONS #45)**

- **Qué:** las señales `tradeable=False` pasan a `outcome_status = suppressed`, en lugar de quedar `pending` para siempre. Se calcula su outcome contrafactual con la misma lógica y se guarda marcado como tal, fuera del win rate de las tradeables. El resumen muestra cuánto rinden las supresiones.
- **Archivos:** `analysis/reversal/outcome_tracker.py` (filtro en :349, `summarize`), `analysis/reversal/signal_registry.py`, el reporte o resumen que muestra pendientes, `tests/`, `docs/DECISIONS.md`.
- **Criterio de aceptación:**
  - PCAR 09-18, PCAR 09-19 y GFI 09-24 quedan `suppressed`, con contrafactual stop_hit (−1.12, −1.21 y −4.82R).
  - Dejan de contar como `pending`.
  - El win rate y el R de las tradeables no cambian.
  - `positions_log.json` no se toca para las suprimidas.

### P4 — `outcomes_v2` — **fase 1 implementada (ver DECISIONS #44)**

- **Qué (propuesta):** una segunda medición en paralelo, sin reemplazar la v1.
  - Entrada = `next_open_ars` de la sesión siguiente a `data_date`.
  - La ventana arranca en esa sesión (inclusive).
  - Si la apertura está en o debajo del stop, el estado es `no_entry_gap` (tratamiento del R a definir, ver §4).
  - R en unidades del riesgo original y R con el riesgo medido desde la apertura.
  - Marca de ex-dividendo dentro de la ventana.
  - Las barras planas con volumen 0 no cuentan como sesión.
- **Archivos:** `analysis/reversal/outcome_tracker.py`, `analysis/reversal/r_multiple.py`, `analysis/reversal/near_miss_outcomes.py`, nuevo `data/reversal_tracking/outcomes_v2.jsonl` (o campos con sufijo `_v2`), nuevo script de backfill en `scripts/`, `tests/`, `docs/DECISIONS.md`.
- **Criterio de aceptación:**
  - Sobre el corpus actual reproduce los números de 1.2: 76 filas, 17 cambios de estado netos (3 en (a), 16 en (b)), diferencia de R con mediana 0.00 y media −0.25 en unidades del riesgo original.
  - ITUB3 y TECO2 11-25 quedan target_8; MU y TSM 11-20 quedan `no_entry_gap`; ADGO 08-03 queda como defecto de dato, no como gap.
  - Se reporta el **delta incremental en orden fijo: ventana → entrada → salida**. v1 → (a) ventana desde la primera sesión posterior a `data_date` (inclusive), con entrada al cierre → (b) entrada en `next_open_ars` → (c) modelo de salida. El orden está fijado porque los Δ parciales dependen de él (el total no); sobre el corpus actual, (a) = −0.114R y (b) = −0.137R sobre 69 filas (§1.2).
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
6. **Respondida: ¿por diseño o por herencia?** Por diseño al principio, por herencia desde #30. Sigue abierta la decisión de si se cambia la vara de la v1 o solo se mide en `outcomes_v2` (propuesta: solo v2; ver P4).
   - **Origen (por diseño):** el filtro `df.index > scan_dt` está en el primer commit de `outcome_tracker.py` (43470a6, 2026-08-07). #18 (2026-08-04) define `entry_price_ars` como el close al momento del scan y mide "post-scan_date"; con el guardrail de #20 (sin corridas entre 11:00 y 17:15) la entrada era el cierre del propio `scan_date` y excluir esa barra era coherente. No hay una justificación escrita aparte de la exclusión.
   - **Herencia desde #30:** desde #30 (2026-09-10, yfinance publica al día siguiente) la señal del día X usa el cierre de X-1 y la barra X, la primera en la que se puede ejecutar una orden, quedó fuera sin que el filtro se revisara. Ninguna entrada de DECISIONS.md lo justifica con el timing nuevo. #20 ya permitía corridas antes de las 11:00 (cierre de X-1), así que el hueco es anterior; el primer caso es VIVT3 08-04.
   - **Diferido a propósito:** #35 (2026-11-20) lo dejó pendiente ("corregirlo cambia la vara de medición; se instrumenta primero y se decide después") y #37 (2026-11-20) decidió que "la vara de medición no cambia". e37922a solo movió el filtro a `_after_scan` (`outcome_tracker.py:108-111`). `tests/test_entry_bar.py:120` fija el comportamiento actual, no un criterio.
   - **Medición:** el efecto de la ventana (paso (a) de §1.2) es −0.114R sobre 69 filas, casi todo RIOT 09-02; sin ese caso, −0.009R.
7. ¿El tracker acredita dividendos en posiciones paper que los cobran? (no verificado).
8. Causa de las barras fantasma del 2026-07-06.
9. ¿Parchear argentinadatos o derivar el CCL de pares local/ADR?

---

Fuentes externas usadas: BCRA Com. A 8487 (feriado bancario del 10/11/26); prensa sobre el feriado nacional del 09/11/26 por la visita del Papa; calendario bursátil de BYMA (sin entrada específica para el 10/11 en el texto consultado).
