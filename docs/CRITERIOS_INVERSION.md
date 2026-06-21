# Criterios de Inversión — Watchlist (Cocos Capital)

> Este documento define el marco de decisión para todo análisis de activos en este proyecto: CEDEARs (empresas del exterior) y acciones argentinas directas. Cualquier research, scoring o recomendación debe ser consistente con estos criterios. Si en algún momento un análisis se aparta de esto, debe registrarse el motivo en `DECISIONS.md`.

## Perfil del inversor

- **Estilo:** Técnico/momentum como driver principal. Fundamentals como filtro de calidad, no como señal de entrada.
- **Horizonte:** Mediano plazo táctico (semanas a pocos meses). No es day-trading, no es buy-and-hold de años.
- **Riesgo:** Moderado. Busca oportunidades tácticas, no apuestas binarias de alto riesgo.
- **Universo:** Dos tipos de activos, tratados distinto en el riesgo país (ver más abajo):
  - **CEDEARs de empresas del exterior**: el riesgo Argentina afecta solo el "envoltorio" (brecha cambiaria, ratio CEDEAR/subyacente, liquidez en Cocos), no el negocio subyacente.
  - **Acciones argentinas directas**: el riesgo país es parte del negocio mismo — afecta ingresos, regulación, costo de capital, no solo el envoltorio.

## Proceso de evaluación: dos filtros en cascada

La lógica es **rápido y amplio primero, profundo y caro después**. El Filtro 1 corre sobre todo el universo disponible en Cocos Capital. El Filtro 2 corre solo sobre los sobrevivientes — esto ahorra tiempo y recursos de análisis, concentrando el esfuerzo pesado donde ya hay una señal mínima de que vale la pena.

---

### FILTRO 1 — Barrido rápido (sobre todo el universo)

**Objetivo:** descartar rápido lo que está claramente mal, sin profundizar. Es un termómetro de salud, no un análisis completo.

**Calibración: moderada.** Descarta solo lo claramente malo. No se busca ser exhaustivo acá — el objetivo es eliminar ruido obvio, no tomar la decisión final. Ante la duda, el ticker pasa al Filtro 2 (mejor revisar de más en el filtro profundo que descartar algo bueno por error acá).

**Criterios de descarte rápido — comunes a todos los activos:**
- Deuda impagable o deterioro acelerado de solvencia (señal evidente, no sutil)
- Earnings en caída sostenida y marcada (tendencia clara, no un trimestre puntual)
- Profit warning o guidance negativo reciente sin explicación convincente
- Liquidez insuficiente del instrumento específicamente en Cocos Capital (sin volumen no hay forma de operar)
- Tendencia técnica de fondo claramente negativa (rompiendo soportes mayores de forma sostenida, no una corrección normal)

**Criterio adicional — exclusivo para acciones argentinas directas:**
El filtro rápido es **más exigente** para acciones argentinas que para CEDEARs del exterior, dado que el riesgo país impacta el negocio directamente, no solo el envoltorio. Se suman estos chequeos rápidos:
- Exposición relevante a riesgo regulatorio/tarifario de conocimiento público reciente y negativo
- Dependencia fuerte de variables macro inestables (tipo de cambio oficial, brecha, acceso a dólares) cuando eso compromete la operación del negocio, no solo su cotización
- Si hay duda razonable sobre el impacto de un evento macro/político reciente sobre el negocio puntual, no se descarta automáticamente, pero se marca para atención prioritaria en el Filtro 2

**Output del Filtro 1:** lista corta de tickers (CEDEARs + argentinas) que pasaron el barrido, con motivo breve de por qué cada uno avanza.

---

### FILTRO 2 — Análisis profundo (solo sobre los sobrevivientes del Filtro 1)

**Objetivo:** ser la prueba suficiente para justificar invertir dinero real. Acá se combinan varias técnicas, no una sola señal.

**Técnicas a aplicar (todas, no opcionales, sobre cada sobreviviente):**

1. **Técnico avanzado**
   - Estructura de tendencia en múltiples temporalidades (ej: semanal para contexto, diario para timing)
   - Rupturas de rango confirmadas por volumen
   - Medias móviles relevantes (cruces y pendiente, no solo posición de precio)
   - RSI / momentum, evitando entrar en sobrecompra extrema sin contexto
   - Fuerza relativa vs. sector y vs. índice de referencia — ¿lidera el movimiento o va a la rastra?

2. **Fundamentals como filtro de calidad** (no como señal de entrada, confirma que el negocio aguanta la apuesta técnica)
   - Salud financiera: deuda, márgenes, flujo de caja
   - Tendencia de earnings reciente (no solo el último trimestre, la serie)
   - Posición competitiva/sectorial — ¿por qué este movimiento de precio tiene sentido con el negocio?

3. **Sentimiento y noticias — rol de desempate (research bajo demanda, no siempre)**
   - No es una técnica con peso propio en el score: **solo se ejecuta** cuando técnico y fundamental **no dan una señal clara en la misma dirección**.
   - Si técnico y fundamental ya coinciden con claridad, este paso **se omite** — no se gasta research web innecesario. El ahorro de tiempo/tokens es intencional: el desempate es la excepción, no la regla.
   - Cuando sí se activa el desempate, el research de noticias/sentimiento (siempre con web search activo, información de mercado actual) decide si la oportunidad se confirma o se descarta.

4. **Ajuste por riesgo Argentina** (modificador final, no filtro)
   - **Para CEDEARs:** brecha cambiaria, ratio CEDEAR/subyacente, liquidez relativa en pesos vs. el activo en el exterior.
   - **Para acciones argentinas directas:** además de lo anterior, impacto de contexto macro/regulatorio sobre el negocio en sí (esto ya se filtró parcialmente en el Filtro 1, acá se profundiza el detalle).
   - En ambos casos, esto ajusta el score y se documenta como advertencia — no descarta una oportunidad ya confirmada por técnico + fundamental.

**Output del Filtro 2:** ranking final de oportunidades, cada una con:
- Señal técnica que la sostiene
- Confirmación fundamental (pasa el filtro de calidad)
- Resultado del desempate por sentimiento/noticias (solo si se activó — ver técnica 3)
- Ajuste de riesgo Argentina (si aplica al tipo de activo)
- **Nivel de invalidación técnica explícito** (ver sección siguiente — sin esto, la oportunidad no está completa)
- **Propuesta de distribución de capital**, ponderada por score relativo dentro del ranking (ver sección "Gestión de capital y tamaño de posición")

---

## Gestión de capital y tamaño de posición

**Capital disponible:** USD 10.000.
**Cantidad de posiciones objetivo:** entre 5 y 10 simultáneas, según cuántas oportunidades sobrevivan el Filtro 2 en cada ciclo.

**Criterio de sizing — sin tope rígido por posición, ponderado por convicción:**
- No hay un porcentaje máximo fijo por posición. El peso de capital en cada oportunidad es proporcional al **score resultante del Filtro 2** (fuerza de la señal técnica + confirmación fundamental + resultado del desempate si aplicó + ajuste de riesgo Argentina).
- Esto significa: a mayor score relativo dentro del ranking, mayor proporción de capital sugerida. La convicción no es arbitraria — tiene que ser trazable al análisis, no a una corazonada sin respaldo.
- Cada vez que se arma el ranking final, el sistema debe proponer una distribución sugerida de capital entre las posiciones seleccionadas, justificada por el score relativo de cada una. La decisión final de cuánto poner es siempre del usuario, pero la propuesta debe partir del análisis, no estar en blanco.

**Reserva de cash (USDT/pesos sin invertir):**
- Variable según cantidad de posiciones activas: si entran ~5 oportunidades, mantener una reserva mayor (ej. 15-20%) por si aparecen mejores señales en el próximo ciclo semanal. Si entran ~10 oportunidades, la reserva puede ser menor, dado que el capital ya está más distribuido entre más ideas.
- La reserva no es un número fijo — se ajusta cada ciclo semanal según cuántas posiciones de calidad pasaron el Filtro 2 ese período.

**Escalado de posiciones (sumar a ganadoras):**
- Permitido. Si una posición ya abierta reconfirma su señal técnica (ej: rompe un nuevo nivel de resistencia con volumen, la tendencia se fortalece), se puede sumar capital adicional a esa posición — de forma similar al esquema de entradas en tramos que ya usás en el portfolio cripto.
- Cada suma a una posición existente debe quedar registrada igual que una entrada nueva: con el motivo técnico que la justificó y, si corresponde, un nivel de invalidación actualizado para la posición ampliada.
- No se permite "promediar a la baja" (sumar capital a una posición que se está moviendo en contra de la tesis) — eso contradice el criterio de stop técnico. Si el nivel de invalidación se rompe, la posición se cierra, no se refuerza.



**Regla por defecto: stop técnico**, no stop fijo por porcentaje.
- La tesis se invalida cuando se rompe un soporte clave o una media móvil relevante que sostenía la entrada — no a un % de pérdida arbitrario.
- Cada oportunidad del Filtro 2 debe tener su nivel de invalidación técnica definido y registrado junto con la recomendación (igual que el BTC $58K en el portfolio cripto). Sin nivel de invalidación, la oportunidad no se considera completa ni se reporta como lista para operar.

## Cadencia de revisión

- **Revisión programada: semanal.** El Filtro 1 corre sobre todo el universo de Cocos Capital una vez por semana; el Filtro 2 corre sobre lo que sobrevivió.
- **Alertas puntuales:** si un ticker ya en watchlist (resultado de Filtro 2) rompe su nivel técnico clave —entrada o invalidación— entre revisiones semanales, se reporta de inmediato, sin esperar al ciclo semanal.

## Qué NO hace este sistema

- No reemplaza el análisis de juicio final — entrega un ranking de oportunidades con su justificación; la decisión de ejecutar la compra es siempre manual.
- No hace timing intradiario ni señales de day-trading.
- No trata el riesgo Argentina como bloqueante en ningún caso (ni CEDEARs ni acciones argentinas) — es siempre ajuste de score, nunca descarte automático por sí solo. Si esto cambia en el futuro, debe actualizarse este documento y registrarse en `DECISIONS.md`.

---
*Última actualización: 2026-06-20 — agregada estructura de dos filtros (rápido/profundo) y distinción CEDEAR exterior vs. acción argentina directa.*
