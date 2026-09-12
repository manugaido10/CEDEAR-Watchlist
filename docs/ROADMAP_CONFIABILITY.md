# Roadmap de confiabilidad — CEDEAR Reversals

**Fecha:** 2026-09-12
**Objetivo:** pasar de un sistema que produce señales a uno que puede
demostrar si esas señales valen algo.

---

## El problema, dicho sin vueltas

Hoy el sistema no puede responder la pregunta central: **¿alguna de sus
señales es mejor que elegir al azar?**

No es por falta de datos ni de fuentes. Es por tres razones concretas:

1. **Las señales no son comparables entre sí.** COST tiene el stop a 0,46%
   del soporte y FDX a 3,57% — casi 8x de diferencia. Un stop tocado en
   cada una se registra igual (`stop_hit`) pero costó ocho veces más en
   una que en la otra. Promediar eso no significa nada.

2. **Las señales técnicas en ARS están contaminadas por el tipo de cambio.**
   COST cayó 3,6% en pesos y 9,1% en dólares en el mismo período: la
   diferencia es devaluación. Un "rebote en MA200" calculado sobre precios
   en ARS puede estar midiendo el peso, no la acción.

3. **Ninguna de las cinco fuentes de señal está validada.** Indicadores
   técnicos, `analyst_revision`, news gate, calendario de earnings y
   contexto FX: ninguna demostró todavía tener valor predictivo. Se
   agregaron porque parecían razonables.

Y por encima de todo: el corpus limpio arranca en **n=0** (2026-09-11).

---

## El principio que ordena todo el plan

> **Registrar ahora, decidir después.**

Cada vez que cambiamos cómo se mide un resultado, el corpus acumulado deja
de ser comparable y hay que empezar de nuevo. Ya pasó tres veces en dos
semanas.

De eso se desprende la regla operativa:

- Lo que tiene que existir **como campo registrado al momento de la señal**
  va ahora, antes de que el corpus se llene.
- Lo que es **análisis sobre datos ya registrados** puede esperar.
- Lo que **cambia qué señales se publican** espera a tener evidencia.

---

## Fase A — Instrumentación (ahora, antes de que el corpus se llene)

Tres campos nuevos. Ninguno cambia qué señales se publican ni cómo se
calcula el score. Todos se computan con datos que el sistema **ya tiene**.

### A1 — Normalización por riesgo (R-múltiplo)

El resultado de cada señal expresado en unidades de su propio riesgo
inicial, además del porcentaje:

```
R = (exit − entry) / (entry − invalidation)
```

Un stop tocado exacto es −1R siempre, sin importar si el stop estaba a
1,5% o a 7%. Un target que gana el doble de lo que arriesgaba es +2R.

**Por qué es lo más importante del plan:** sin esto, el EV que venimos
calculando mezcla trades de riesgo muy distinto y el número no significa
nada. Con esto, las señales se vuelven comparables por primera vez.

**Ventaja clave:** es computable retroactivamente desde `entry`,
`invalidation` y `exit`, que ya están guardados. No resetea el corpus —
lo enriquece.

*Resuelve el hallazgo que veníamos llamando "Fase 2".*

### A2 — Descomposición cambiaria

Para cada señal sobre un CEDEAR, registrar al momento del scan:
- Precio del subyacente en USD
- CCL del día
- Variación del subyacente en USD vs. variación del CEDEAR en ARS sobre
  la misma ventana

Con eso se puede responder: **¿cuánto del movimiento que el scanner leyó
como señal técnica fue realmente el activo, y cuánto fue el peso?**

No es un gate todavía — es un campo. Cuando haya muestra, se podrá medir
si las señales con alta divergencia FX rinden distinto.

*Aplica a todos los CEDEARs, no solo a los brasileños.*

### A3 — Snapshot de régimen

En cada corrida, registrar tres métricas del universo completo:
- % de tickers por debajo de su MA200
- Mediana de RSI del universo
- Variación de la mediana respecto a la corrida anterior

Son baratas de computar: los datos ya están en memoria después del fetch.

**Por qué importa:** es el hallazgo más fuerte de toda la investigación.
En junio-julio el sistema rindió fuertemente positivo; desde fines de
julio, EV negativo para *todo* — señales publicadas y rechazadas por
igual (−1,5% a −1,9%). La variable dominante no es qué filtro se aplica,
es en qué régimen se opera.

Sin el snapshot registrado por corrida, nunca vamos a poder correlacionar
resultados con régimen.

---

## Fase B — Validación (a medida que el corpus se llena)

Análisis sobre los campos que la Fase A deja registrados. No requiere
código nuevo más allá de queries.

### B1 — ¿Qué fuente predice algo?

Una por una, con el corpus limpio:
- `analyst_revision`: ¿las señales con `up` rinden distinto que las `down`
  o `no_data`?
- News gate: ¿las señales con warnings de analistas rinden peor?
- Tipo de catalizador: RSI divergence vs MA200 bounce vs reversal candle,
  ahora en R-múltiplos en vez de porcentajes.
- Divergencia FX: ¿las señales con alta divergencia rinden peor?

**Cualquier fuente que no muestre diferencia debería sacarse del reporte.**
Mostrar información que no predice nada agrega ruido a la decisión.

### B2 — Calibración de gates

Lo que ya está en curso: `rsi_out_of_range` y `no_catalyst` contra el piso
de n=40. Ahora con R-múltiplos, que es la métrica correcta.

### B3 — Correlación con régimen

¿El EV cambia con el snapshot de régimen? Si la respuesta es sí y es
fuerte, eso define la Fase C.

---

## Fase C — Acción (solo con evidencia de Fase B)

Nada de esto se toca antes de tener los números.

- **Gate de régimen:** si B3 confirma que el régimen predice el EV, no
  publicar señales en régimen adverso. Un sistema que sabe cuándo no
  operar probablemente valga más que uno con más fuentes de análisis.
- **Reponderación del score** según qué catalizadores rinden en
  R-múltiplos.
- **Ajuste de umbrales** de los gates que B2 demuestre mal calibrados.
- **Sizing por riesgo** cuando el sistema pase a operar con plata real
  (hoy no aplica: modo paper sin montos).

---

## Lo que NO vamos a hacer, y por qué

| Idea | Por qué no |
|---|---|
| Analista de gráficos con LLM | El sistema ya calcula RSI, MA200, swing lows y volumen desde los datos crudos — más preciso que un LLM mirando una imagen. Agregaría narrativa subjetiva y difícil de falsar. |
| Más fuentes de datos (SEC, FRED, Finnhub) | El cuello de botella es la medición, no los datos. Sumar una sexta fuente no validada a cinco no validadas empeora la atribución. |
| Machine learning | Con n=0 en el corpus limpio, cualquier modelo memoriza ruido. Revisar recién con 100+ resolvables. |
| Ajustar umbrales ahora | Piso acordado: n=40 por gate. Ya nos pasó sacar conclusiones con muestra chica y verlas caerse. |

---

## Reglas permanentes

1. **No cambiar la vara mientras se acumula.** Cualquier cambio a cómo se
   mide un outcome resetea el corpus. Si hace falta, se hace de una vez y
   se documenta el corte.
2. **Todo número va con su n.** Sin excepción.
3. **Antes de comparar dos grupos, verificar que cubran el mismo período.**
   El confounding de régimen ya invalidó dos conclusiones.
4. **Un filtro que corrige contaminación puede introducir sesgo peor.** El
   filtro `safe` excluyó las tres ganadoras del período. Verificar siempre
   si la exclusión correlaciona con el resultado.
5. **Fail-closed por defecto.** Si un dato no se puede verificar, se dice
   — no se asume limpio.

---

## Estado y próximo paso

| Fase | Estado |
|---|---|
| A1 — R-múltiplos | Pendiente — **prioridad 1** |
| A2 — Descomposición FX | Pendiente |
| A3 — Snapshot de régimen | Pendiente |
| B — Validación | Bloqueada hasta tener muestra |
| C — Acción | Bloqueada hasta Fase B |

**Próximo paso concreto:** implementar A1, A2 y A3 en una sola tanda esta
semana, antes de que el corpus post-fix empiece a llenarse. Las tres son
aditivas, no cambian comportamiento, y sin ellas la muestra que se acumule
no va a servir para las preguntas que importan.