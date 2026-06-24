# Fuentes de Datos — CEDEAR Watchlist (Cocos Capital)

> Diagnóstico de acceso a datos para el proyecto. Documento en español (decisión de negocio).
> Última actualización: 2026-06-20 — investigación inicial, pre-implementación.
> ACTUALIZACIÓN 2026-06-21: la sección "2.1 Universo de instrumentos" de este
> documento describía el Excel de CVSA como fuente del universo completo. En
> la práctica, ese Excel es solo un lote mensual de actualizaciones, no el
> listado completo. La fuente real usada es el PDF de BYMA "CEDEARs Negociables
> en BYMA con Ratios de Conversión" (listado completo, ~370 CEDEARs netos tras
> excluir ETFs). CVSA se mantiene como oráculo de validación cruzada parcial.
> pyCocos queda diferido (no descartado) — ver DECISIONS.md "2026-06-21 (b)"
> para el detalle completo y el razonamiento.

---

## Conclusión ejecutiva

No existe API pública oficial de Cocos Capital. La web tiene protección Cloudflare activa que bloquea scraping HTML directo. La vía más viable para acceder a datos de Cocos es una librería no oficial que llama endpoints internos de la app —con todos los riesgos que eso implica.

Para los datos de mercado en sí (precios, fundamentals, universe), la arquitectura más robusta es **desacoplar la fuente de datos del broker**: usar BYMA (fuente oficial del mercado argentino) para precios de CEDEARs y acciones argentinas, la Caja de Valores para el universo + ratios de conversión, y yfinance/FMP para datos del subyacente exterior.

---

## 1. Acceso a Cocos Capital

### ¿Existe API pública?

**No.** Cocos Capital no publica documentación de desarrolladores ni endpoints oficiales.

### Alternativa: librería no oficial `pyCocos`

Existe una librería Python creada por reverse-engineering de la app móvil/web de Cocos:
- Repositorio: https://github.com/nacho-herrera/pyCocos
- Base URL interna: `https://api.cocos.capital/api`
- Última versión: 0.2.12 (junio 2024), 58 commits

**Qué expone:**
- Lista de instrumentos operables (`v1/markets/tickers`)
- Snapshots de precios por tipo de instrumento
- Portfolio y saldo de cuenta
- Datos de la cotización del dólar MEP
- Enrutamiento de órdenes (compra/venta/cancelación)

**Limitaciones críticas de `pyCocos`:**
- **Librería no oficial.** Puede romperse sin aviso ante cualquier cambio de Cocos Capital en su app.
- **2FA obligatorio desde abril 2024.** Cocos exige autenticación de dos factores en todos los accesos. El único flujo automatizable es TOTP (requiere extraer el `totp_secret_key` del QR durante la configuración inicial). SMS/email no son automatizables.
- **Sin soporte.** No hay documentación oficial ni garantía de estabilidad.
- **Riesgo de suspensión de cuenta.** Uso automatizado de endpoints internos no autorizados puede considerarse violación de los T&C.

### ¿Se puede scrapear la web de Cocos?

**No de forma confiable.** La capa web de Cocos Capital tiene **Cloudflare activo**, confirmado por la comunidad (un desarrollador tuvo que migrar su scraper a la API interna precisamente por esto). El scraping HTML directo es inviable para producción.

**Conclusión sobre Cocos Capital:**
- `pyCocos` es viable para obtener el **universo de instrumentos disponibles en Cocos** (qué tickers están habilitados, con qué liquidez mínima operable) como fuente inicial.
- **No recomendado como fuente primaria de precios** —demasiado frágil para depender de él semanalmente.
- Como dato de mercado, la fuente primaria debe ser **BYMA**, no Cocos.

---

## 2. Fuentes recomendadas por tipo de dato

### 2.1 Universo de instrumentos: ¿qué hay disponible en Cocos?

| Fuente | Detalle | Costo | Viabilidad |
|---|---|---|---|
| `pyCocos` (`v1/markets/tickers`) | Lista exacta de tickers disponibles en Cocos | Gratis (cuenta Cocos + TOTP) | Alta fragilidad, riesgo T&C |
| BYMA Instruments API | Lista oficial de todos los CEDEARs y acciones listadas en BYMA | Gratuito con contrato | Fuente oficial; no garantiza qué está habilitado específicamente en Cocos |
| Caja de Valores (CVSA) | Excel descargable con todos los CEDEARs: ticker, ISIN, ratio, mercado de origen | Gratuito | Fuente oficial para CEDEARs; descarga manual, no hay API |

**Enfoque recomendado:** Usar `pyCocos` **una sola vez o manualmente** para obtener el snapshot inicial del universo de Cocos, validarlo contra el Excel de Caja de Valores, y mantenerse actualizado con BYMA Instruments para cambios. El universo de CEDEARs no cambia con frecuencia semanal —una actualización mensual o ante eventos puntuales (splits, nuevos listados) es suficiente.

---

### 2.2 Precios y volumen de CEDEARs en ARS

| Fuente | Tipo de dato | Costo | Calidad |
|---|---|---|---|
| **BYMA Open Data** (`open.bymadata.com.ar`) | EOD y delay (20 min) | Gratuito (requiere credenciales) | Oficial; wrappers Python disponibles (PyOBD, bymadata-api-wrapper) |
| **BYMA Market Data API (retail)** | Snapshot en tiempo real, EOD | USD 30–120/mes | Formal, contrato firmado con BYMA |
| **EODHD** (exchange `BA`) | EOD + intraday para tickers `.BA` | USD 19.99/mes (EOD All World) | Cubre CEDEARs en BA; confirmado |
| **yfinance** (`TICKER.BA`) | EOD; sin clave API | Gratuito | Tickers `.BA` confirmados; inestable para uso continuo |

**Enfoque recomendado para desarrollo inicial:** yfinance + BYMA Open Data.
- yfinance para prototipar rápido (cero fricción, sin cuenta).
- BYMA Open Data como fuente más robusta para el ciclo semanal en producción (requiere registrar credenciales en el portal open.bymadata.com.ar).
- Si el presupuesto lo justifica, EODHD a USD 19.99/mes consolida precios BA + datos internacionales en un solo proveedor.

**Serie histórica:** yfinance provee años de datos diarios para `.BA` sin restricción de ventana. BYMA EOD API incluye histórico. EODHD: 30+ años en plan pagado.

---

### 2.3 Precios y fundamentals del subyacente exterior (acciones internacionales)

Los CEDEARs representan acciones de empresas del exterior (NYSE, NASDAQ, B3, Frankfurt, etc.). Para el análisis técnico y fundamental del subyacente:

| Fuente | Precios | Fundamentals | Costo | Recomendación |
|---|---|---|---|---|
| **yfinance** (tickers US estándar) | Sí, confiable para EOD | Poco confiable post-2024 (DataFrames vacíos frecuentes) | Gratuito | Precios OK; no usarlo para fundamentals |
| **Financial Modeling Prep (FMP)** | Sí | Excelente (EDGAR, 10+ años, trimestral) | Gratuito: 250 llamadas/día; Pago: desde USD variable/mes | **Mejor opción para fundamentals** |
| **Alpha Vantage** | Sí (US) | Bueno (income statement, balance sheet, cash flow, EPS) | Gratuito: 25 llamadas/día (restrictivo); Pago: USD 49.99/mes para 75 llamadas/min | Alternativa a FMP; tier gratuito muy limitado |
| **EODHD** | Sí | Disponible; ~10 años para no-US | USD 59.99/mes (Fundamentals Data Feed) o USD 99.99/mes (All-In-One) | Conveniente si ya se usa para precios BA, pero más caro para fundamentals |
| **Polygon.io** | No aplicable | No aplicable | — | **Descartado.** Solo cubre mercado US; no aplica para CEDEAR ni acciones argentinas. |

**Enfoque recomendado:**
- **Precios subyacente:** yfinance (confiable para US, gratuito, sin configuración).
- **Fundamentals subyacente:** FMP capa gratuita (250 llamadas/día) para el ciclo semanal. El Filtro 1 y Filtro 2 necesitan: tendencia de earnings, deuda, márgenes y cash flow — FMP cubre todo esto con su tier gratuito si se diseña bien el número de llamadas.

**Ratio de conversión CEDEAR:**
- **Fuente oficial:** BYMA publica un PDF actualizado en su página de CEDEARs. Caja de Valores publica el Excel con ratios (última versión disponible: 1-06-2026).
- **No hay API.** Es una descarga manual (Excel o PDF). Los ratios cambian ante splits/reverse splits del subyacente o ajustes de la CNV —no diariamente, pero hay que monitorear.
- **Impacto en el análisis:** El ratio CEDEAR/subyacente es necesario para calcular la brecha real entre el precio en ARS del CEDEAR (ajustado por CCL) y el precio del subyacente en USD. Sin el ratio correcto, la comparación es errónea.

---

### 2.4 Precios de acciones argentinas directas (MERVAL/BYMA)

Mismas fuentes que para CEDEARs en ARS:
- yfinance con sufijo `.BA` (ej: `GGAL.BA`, `BMA.BA`, `CEPU.BA`, `TGS.BA`)
- BYMA Open Data o BYMA Market Data API
- EODHD exchange `BA`

**Fundamentals de empresas argentinas:**
- Cobertura escasa en FMP y Alpha Vantage (datos incompletos o inexistentes para empresas BYMA).
- **Fuente alternativa:** Yahoo Finance directamente (vía yfinance), aunque poco confiable. Para empresas con ADR listado en NYSE (GGAL, BMA, PAM, etc.), FMP cubre el subyacente bien.
- **Fuente específica para Argentina:** Los balances de empresas BYMA están disponibles en la CNV (Comisión Nacional de Valores, https://www.cnv.gov.ar/) como archivos XBRL/PDF. No hay API; requiere parsing manual o automatizado de presentaciones regulatorias. Complejidad alta —considerar para fase 2 del proyecto.

---

### 2.5 IOL (Invertir Online) — ¿es útil?

IOL tiene una **API pública documentada** (`https://www.invertironline.com/api`) con JSON, cobertura de CEDEARs y acciones argentinas, y datos históricos.

**Limitación para este proyecto:** el acceso a la API IOL requiere cuenta activa en IOL, no en Cocos Capital. Es una fuente válida de precios de mercado argentino, pero no integra el portfolio de Cocos. Para precios e histórico de mercado (sin necesidad de operar desde IOL), podría funcionar como fuente de precios alternativa a BYMA Open Data.

**Conclusión:** IOL API es una opción secundaria viable si BYMA Open Data presenta fricción de acceso. No es prioritaria en la arquitectura inicial.

---

## 3. Arquitectura de datos recomendada

```
[Universo Cocos]
  → pyCocos (una vez / mensual): snapshot inicial de tickers disponibles
  → CVSA Excel: validación y ratios de conversión (descarga periódica manual)

[Precios CEDEARs y acciones argentinas en ARS]
  → Desarrollo: yfinance (.BA tickers, EOD diario)
  → Producción: BYMA Open Data (credenciales open.bymadata.com.ar)

[Precios subyacente exterior (USD)]
  → yfinance (tickers US estándar, confiable, gratis)

[Fundamentals subyacente exterior]
  → Financial Modeling Prep, tier gratuito (250 llamadas/día)
  → Cubre: earnings trend, deuda, márgenes, cash flow

[Fundamentals empresas argentinas]
  → Best-effort: yfinance para las que tienen ADR
  → CNV como fuente primaria: complejidad alta, diferir a fase 2

[Ratio CEDEAR/subyacente]
  → CVSA Excel o BYMA PDF (actualización periódica manual)

[Tipo de cambio CCL / brecha]
  → dolarapi.com (fuente usada por agregadores de la comunidad, gratuita)
```

---

## 4. Limitaciones relevantes para el diseño del sistema

| Limitación | Impacto | Mitigación |
|---|---|---|
| `pyCocos` puede romperse sin aviso | Si se usa para el universo, el sistema se rompe | Usar solo para snapshot inicial; validar contra BYMA Instruments |
| yfinance inestable para uso continuo intensivo | Rate limiting en uso frecuente; datos no garantizados | Cachear localmente las respuestas; BYMA Open Data como respaldo |
| FMP gratuito: 250 llamadas/día | Para un universo de 100+ activos, el Filtro 1 requiere manejo cuidadoso de llamadas | Diseñar el Filtro 1 para minimizar llamadas a FMP; cachear fundamentals (cambian trimestralmente) |
| Ratios CEDEAR sin API | Actualización manual ante splits o ajustes CNV | Archivo local versionado con los ratios; proceso de actualización documentado |
| Fundamentals de empresas argentinas (BYMA puras) | Cobertura escasa en FMP/Alpha Vantage | Diferir a fase 2; el Filtro 1 para acciones argentinas puede basarse más en técnico que en fundamentals |
| BYMA Open Data requiere registro | Pequeña fricción de setup | Documentar el proceso de obtención de credenciales |
| BYMA Market Data API formal (Snapshot real-time) | Costo USD 30–120/mes; requiere contrato firmado | Para el ciclo semanal, EOD es suficiente — no necesitamos real-time |

---

## 5. Riesgos y bloqueantes

### Bloqueante potencial
- **pyCocos como única fuente del universo:** Si se depende exclusivamente de `pyCocos` para saber qué hay disponible en Cocos, cualquier cambio de autenticación o endpoint de Cocos Capital rompe el sistema. **Mitigación:** usar pyCocos solo como punto de partida; el universo de CEDEARs es estable y puede mantenerse como lista local validada contra BYMA.

### Riesgos de baja prioridad
- **Bloqueo de cuenta de Cocos por uso automatizado:** Si se automatiza el acceso vía pyCocos para el ciclo semanal, hay riesgo de que Cocos detecte el acceso automatizado y suspenda la cuenta. Uso esporádico (mensual para validar universo) es mucho menos riesgoso que acceso semanal continuo.
- **Cambio en la estructura del CVSA Excel:** El Excel de Caja de Valores puede cambiar su formato entre versiones. Requiere parsing defensivo.
- **Yahoo Finance cambia sus endpoints sin aviso:** Ha ocurrido varias veces; quebrando yfinance por períodos. En producción, BYMA Open Data debe ser el fallback.

### No bloqueante (pero a monitorear)
- **Terms of Service de Cocos Capital para uso de API interna:** No fue posible acceder al texto completo de los T&C (retornó HTTP 403). El uso de endpoints internos no documentados es un área gris —no hay prohibición explícita encontrada, pero tampoco autorización. Si se escala el uso de pyCocos, revisar con la cuenta activa los T&C desde la interfaz web de Cocos.

---

## 6. Decisión pendiente (para el usuario)

Antes de implementar `data/cocos_fetcher`, hay una decisión arquitectural abierta:

**¿Cuál es la fuente primaria de precios en ARS para el ciclo semanal?**

- **Opción A — BYMA Open Data (gratuita, requiere registro):** Más robusta y oficial. Requiere gestionar credenciales.
- **Opción B — yfinance `.BA` (cero fricción, gratis):** Más simple de implementar. Riesgo de inestabilidad en producción; aceptable para uso semanal con caché.
- **Opción C — EODHD (USD 19.99/mes):** Simplifica la arquitectura (un solo proveedor para BA + internacional), pero tiene costo.

La decisión afecta el módulo `data/cocos_fetcher` y cómo se maneja el caché local.

---

*Investigación realizada: 2026-06-20. Próximo paso: revisión del usuario y decisión sobre fuente de precios antes de iniciar implementación.*
