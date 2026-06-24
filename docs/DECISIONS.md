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
