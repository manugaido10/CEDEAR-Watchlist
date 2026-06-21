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

*(Las próximas entradas se agregan acá, más recientes abajo.)*
