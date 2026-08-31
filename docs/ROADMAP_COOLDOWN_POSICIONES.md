# Roadmap — Cooldown, Conciencia de Posiciones y Análisis de Resultados

> Plan de desarrollo integrado. Fusiona el trabajo del reconciliador de CSV
> (conciencia de posiciones) con el cooldown post-stop-hit y el plan de análisis
> de resultados derivado de la auditoría del sistema.
>
> **Principio rector:** primero asegurar que la medición es confiable, después
> construir la lógica que la consume. Cada fase depende de que la anterior
> produzca datos correctos. No se avanza a una fase sin validar la anterior sobre
> datos reales.
>
> Idioma: español (documento de planificación). Ver `DECISIONS.md` para las
> decisiones ya tomadas y `docs/ARCHITECTURE.md` para el diseño técnico.

---

## Orden de dependencias (resumen)

```
0.1 outcome_tracker fiable  →  0.2 doc brecha exit  →  0.3 reconciliador
                                                              ↓
                                        1.1 near-miss outcomes (arranca YA, acumula)
                                                              ↓
                                        1.2 cooldown + conciencia de posiciones
                                                              ↓
                                        2.1 sizing por riesgo (simular primero)
                                                              ↓
                                        3.1/3.2/3.3 calibración (bloqueado por muestra)
```

El razonamiento del orden: la medición confiable (0.1) es prerequisito de todo
análisis posterior. El estado de posiciones (0.3) es prerequisito de la
conciencia de posiciones del cooldown (1.2). La acumulación de near-miss outcomes
(1.1) necesita semanas, por eso arranca lo antes posible en paralelo. La
calibración (Fase 3) está bloqueada hasta tener muestra suficiente.

---

## Fase 0 — Esta semana (bajo riesgo, no toca lógica de trading)

### 0.1 — Bug silencioso de `outcome_tracker` *(ARRANQUE)*
**Prioridad máxima.** Todo el resto del plan consume los datos que produce
`outcome_tracker`; si puede fallar en silencio, cada análisis posterior se
construye sobre datos posiblemente incompletos sin que se sepa.

- **Síntoma:** la corrida del 28/08 no emitió la línea `assessed N signals`. El
  módulo corre en try/except no bloqueante, así que pudo fallar sin avisar. Es el
  mismo patrón fail-silent ya cazado tres veces (API credits a cero, MEP,
  dedup de near_misses).
- **Paso 1 — diagnóstico antes del fix:** determinar si falló o si genuinamente
  no tenía señales `pending` que evaluar. No asumir.
- **Paso 2 — fix:** que el módulo siempre loguee su resultado (incluso "0 señales
  para evaluar"), y que las excepciones se registren por tipo en vez de tragarse.
- **Skill aplicable:** `cedear-pipeline-check` antes del commit.

### 0.2 — Documentar la brecha exit vs. invalidación
Entrada en `DECISIONS.md`: el tracker registra el `close` del día que gatilló el
stop, no el nivel exacto de invalidación. Eso hace que las pérdidas medidas sean
levemente peores que las realizables. Cuantificar la brecha promedio sobre las
señales resueltas. Cero código — evita confusión en análisis futuros.

### 0.3 — Cerrar el reconciliador de CSV *(prerequisito del cooldown)*
El parser (sub-pieza 1) ya está **validado sobre datos reales** (cantidades
exactas en 7/10 posiciones; las 3 restantes son lotes pre-2026 correctamente
marcados como incompletos). Faltan:
- **Sub-pieza 2 — comparación:** derivar posiciones del CSV (reprocesando todos
  los archivos, enfoque no incremental por robustez) y compararlas contra
  `positions_log.json`. Reportar diferencias sin sobrescribir.
- **Sub-pieza 3 — presentación:** mostrar las diferencias para confirmación
  manual. Preservar siempre los campos que solo existen en el log (`score_at_entry`,
  `invalidation_level_ars`, `source`) — el CSV es verdad sobre cantidades y
  costos, el log es verdad sobre criterio de entrada.
- **Skill aplicable:** `cedear-feature-validation` antes de integrar.

---

## Fase 1 — Próximas 1-2 semanas (construir para cosechar después)

### 1.1 — Seguimiento de outcomes de near-misses *(arranca lo antes posible)*
Va primero dentro de la Fase 1 porque **necesita semanas de acumulación**: cuanto
antes empiece a registrar, antes sirve para calibrar.

- Reutiliza la maquinaria de `outcome_tracker`: mismo criterio de stop (`low`
  contra invalidación hipotética), mismos targets (5%/8%), mismo `max_days`.
- Diferencia: hay que **construir la invalidación hipotética** para el near-miss,
  porque nunca se calculó (no era señal publicada).
- Salida: `near_miss_outcomes.jsonl` + desglose por gate en `summarize()`.
- Desbloquea la mayoría de las preguntas de calibración de umbrales (Fase 3).
- **Skill aplicable:** `cedear-feature-validation`.

### 1.2 — Cooldown post-stop-hit + conciencia de posiciones
Depende de 0.3 (necesita saber qué posiciones están abiertas). Combina tres
reglas ya diseñadas:

- **Cuarentena post-stop-hit: 15 días hábiles.** Derivada del análisis histórico:
  9 de 9 re-entradas tras un stop_hit fallaron (grupo de control: re-entradas tras
  señal ganadora, 4 de 4 exitosas). El gap de tiempo por sí solo no alcanza —
  condición adicional: no reactivar el ticker si el precio sigue por debajo del
  `invalidation_level_ars` de la señal que gatilló el stop (ataca el régimen
  bajista, no solo el tiempo).
- **Supresión por posición abierta.** Una señal en un ticker ya en cartera lleva
  flag `tradeable: false`. En modo semi-manual se muestra marcada "no operar";
  en modo automático el motor la ignora. Nunca se suprime del registro (auditoría).
- **Sizing acumulado por ticker.** El límite del 8% se aplica al total por
  ticker, no por señal individual. Cuatro señales de compra del mismo ticker no
  deben poder superar el techo sumadas.
- Nota: la infraestructura de dedup ya existe (`check_recent` en
  `signal_registry`, `_is_exposure_duplicate` en `outcome_tracker`). Esta fase
  agrega **supresión dura + cooldown por outcome + conciencia de holdings** sobre
  esa base, no la reconstruye.
- **Skills aplicables:** `cedear-pipeline-check` y `cedear-feature-validation`.

---

## Fase 2 — Cuando se toque plata real (alto impacto, alto cuidado)

### 2.1 — Sizing por riesgo en vez de por score
El hallazgo de mayor impacto económico de la auditoría: BYMA arriesgaba ~4,7x más
que DECK con el mismo capital asignado, porque el sizing por score ignora la
distancia al stop.

- **Lógica:** fijar un riesgo máximo por trade (ej. 1,5% del capital invertible)
  y derivar el tamaño dividiendo por la distancia al stop, con un tope superior
  (el 8% actual) para que un stop muy cercano no concentre media cartera.
- **Requisito antes de producción:** simular sobre las 29 señales históricas —
  recalcular qué habría pasado bajo sizing por riesgo. Esa simulación se puede
  hacer ya, no necesita datos nuevos. `DECISIONS.md` establece que los cambios
  que afectan asignación de capital real exigen más evidencia.
- **Skill aplicable:** `cedear-system-audit` (análisis de expectativa y
  calibración — está diseñado justo para este tipo de estudio de fondo).

---

## Fase 3 — En 4-6 semanas (bloqueado por muestra)

Todas dependen de acumular datos vía 1.1 y de las señales en vivo. Territorio del
skill `cedear-system-audit`, corrido mensualmente.

### 3.1 — Calibración de umbrales de gates
Con los datos de near-miss outcomes (1.1). El cuello de botella observado es
`rsi_out_of_range` (RSI apenas por encima de 45), pero no se calibra hasta tener
la muestra deduplicada — recordar que los near-misses estaban inflados ~24% por
el bug de dedup ya corregido.

### 3.2 — Reponderación de catalizadores en el score
Cuando se llegue a ~20 resolvables deduplicados en regímenes de mercado variados.
Evidencia preliminar: RSI bullish divergence rinde muy por encima de MA200
bounce — el score debería reflejar esa diferencia.

### 3.3 — Evaluación de `analyst_revision`
Cuando resuelvan señales con el campo poblado, incluyendo casos `down`. EBAY es
el primer caso `down` pendiente de resolución.

---

## Skills del proyecto y cuándo se usan

| Skill | Cuándo | Fases |
|---|---|---|
| `cedear-pipeline-check` | Antes de cada commit que toca `data/`, `analysis/`, `output/`, `scripts/` | Todas |
| `cedear-feature-validation` | Antes de integrar un módulo/scanner/reporte nuevo | 0.3, 1.1, 1.2 |
| `cedear-system-audit` | Mensual — calibración, expectativa, sizing por riesgo | 2.1, 3.x |
| `cedear-weekly-review` | Cada viernes — validar win rate en vivo mientras avanzan las fases | Continuo |

---

## Regla transversal

Ninguna fase que toque asignación de capital real se activa hasta que el win rate
**en vivo** (no backfilled) confirme el edge durante 4-6 semanas. Las 6 señales en
vivo actuales no alcanzan (4 contaminadas por el bug de DECK, ya corregido). El
sistema corre en modo observación/simulación hasta tener esa validación.