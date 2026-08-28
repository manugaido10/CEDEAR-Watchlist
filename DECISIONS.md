# Decisiones de diseño — CEDEAR Watchlist

> Registro de decisiones no triviales tomadas durante el desarrollo del sistema.
> Cada entrada incluye contexto, decisión, alternativas consideradas y estado.
> Idioma: español (documento de lógica de negocio). Ver `docs/ARCHITECTURE.md` para el diseño técnico.

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
