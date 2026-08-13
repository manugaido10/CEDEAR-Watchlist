# Decisiones de diseño — CEDEAR Watchlist

> Registro de decisiones no triviales tomadas durante el desarrollo del sistema.
> Cada entrada incluye contexto, decisión, alternativas consideradas y estado.
> Idioma: español (documento de lógica de negocio). Ver `docs/ARCHITECTURE.md` para el diseño técnico.

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
