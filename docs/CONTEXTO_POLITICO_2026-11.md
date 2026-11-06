# Contexto Político USA — Noviembre 2026 → Febrero 2027

> Documento de contexto para las revisiones semanales del scanner y para priorizar la watchlist manual.
> **No modifica ningún gate ni umbral del sistema.** Los criterios siguen siendo los de `CRITERIOS_INVERSION.md`.
> Si en algún momento esta lista pasa a influir en el código (ej. un `focus_list.yaml` que ajuste score), eso es cambio de criterio y requiere entrada en `DECISIONS.md`.
>
> Creado: 2026-11-06 · Vigencia: hasta 2027-02-28 · Próxima revisión: mensual (primer viernes de cada mes)

---

## 1. Qué pasó

- **3/11 — Midterms:** los demócratas ganaron mayoría en ambas cámaras del Congreso y gobernaciones clave, incluida Texas (Gina Hinojosa, que hizo campaña con una moratoria a data centers). Trump mantiene el veto por los próximos dos años → gobierno dividido.
- **4/11 — Rally de alivio:** Dow +3% (+1.569 pts), S&P +1,6%, Nasdaq +1,4%. Debajo de la superficie, chips y data centers ya caían. Ganadores del día: hospitales (HCA +10,6%), solar (FSLR +9,4%), consumo de descuento (DLTR +8,9%), hyperscalers (MSFT +6%, AMZN +8%). Perdedores: defensa, neoclouds, nombres ligados a Trump/Musk.
- **5/11 — Rout de chips:** Nasdaq −5,52% a 24.315 (en corrección, >10% bajo el máximo de octubre). SOX −12%, peor día de chips desde marzo 2020. NVDA −9,3% (USD 181,60), AMD −17,3%, MU ~−17%, AVGO −10%, Intel −10,4%. Neoclouds (CRWV, NBIS, IREN) entre −10% y −16%. Agravantes ajenos a la elección: outlook débil de Qualcomm y Arm.
- **6/11 — Premarket:** rebote parcial (MU +9%, NVDA +3%) antes del reporte de empleo de octubre.

## 2. El tamaño real de la amenaza

| Nivel | Riesgo | Por qué |
|---|---|---|
| Federal | **Bajo** | Trump veta. El riesgo concreto son audiencias e investigaciones, no leyes. |
| Estatal (Texas) | **Alto, con freno** | Texas ≈ 27% de la capacidad de data centers planificada en USA (Wells Fargo). Pero el Senado estatal seguiría republicano, la moratoria es una promesa (no está vigente) y podría enfrentar obstáculos legales. |
| Otros estados | **Medio** | BMI: ~53% del crecimiento del pipeline de hyperscalers está en estados que dieron vuelta la gobernación (TX, GA, OH, PA). Pausa en Texas podría extenderse hasta fines de 2027. |
| Pipeline efectivo | **Atenuante** | Bernstein: solo ~35% del pipeline anunciado es creíble por cuellos de botella de red, transformadores y refrigeración. Parte de lo "perdido" no se iba a construir a tiempo igual. |
| Timing | **Atenuante** | Una moratoria frena aprobaciones nuevas → arranques de proyectos 2028. Entregas de chips 2026–2027 ya están en backlog. |

**Lectura de trabajo (juicio propio, no dato):** el golpe es de *timing y relocalización* (proyectos que se mueven de estado o se demoran 12–18 meses), no de demanda perdida. Los chips líderes ya descuentan un escenario de demanda *perdida*. Los operadores de data centers con deuda y exposición directa a Texas, en cambio, tienen daño real.

## 3. Mapa de impacto por grupo

| Grupo | Mecanismo | Exposición | Prob. | Ya en precio | Veredicto |
|---|---|---|---|---|---|
| Neoclouds (CRWV, NBIS, IREN) | Moratoria TX + apalancamiento (CDS de CoreWeave subiendo) | Directa | Media-alta | −10% a −16% el 5/11, ~−40% en el mes | Daño justificado |
| Energía atada a DC (VST, CEG) | Menos demanda eléctrica de DC | Directa | Media | VST −14,7% el 4/11 | Daño probablemente justificado |
| Chips líderes (NVDA, AMD, AVGO, TSM) | Demanda de DC 2028 | Indirecta, global | Media (timing) | −9% a −17% el 5/11 | **Sobre-reacción probable** |
| MU | Ídem + ciclo de memoria | Indirecta | Media | ~−17% | Mayor beta (venía +272% en el año) |
| QCOM | Outlook propio | Baja por elección | — | −9% | No es tesis electoral |
| Hyperscalers (MSFT, AMZN, GOOGL, META) | Capex más lento → mejor ROIC; escrutinio antimonopolio | Mixta | Baja (veto) | Subieron el 4/11 | Ganadores relativos; riesgo de audiencias **no descontado** |
| Defensa (LMT, RTX) | Presupuesto USD 1,5 bn; suplementos por Irán | Directa | Media | −3% a −5% | Recorte de expectativas, no de base (BNY no espera recorte del gasto base) |
| Pharma (LLY, PFE, MRK, ABBV, JNJ) | Precios de medicamentos | Directa | Baja-media (veto) | Poco | Riesgo latente **sub-descontado** |
| Clean energy (FSLR, NEE) | Se mantiene apoyo federal | Directa | Media | FSLR +9,4% | Ganador ya repriceado |
| Consumo básico (SYY, WMT, COST, PG, KO) | Agenda de costo de vida / ayuda alimentaria | Indirecta | Media | Parcial | Viento a favor leve |
| Oro y mineras (NEM, AEM, GFI, HMY) | Dólar débil, tasas en baja | Macro | — | Suba fuerte el 4/11 | Viento a favor macro |

## 4. Lista de foco Nov 2026 → Feb 2027

**Regla de uso:** esta lista prioriza qué revisar a mano en cada ciclo semanal. **No es una lista de compra.** Ningún ticker se opera sin señal del scanner con su nivel de invalidación técnica en ARS (Filtro 2). Cada ticker tiene además una **invalidación de tesis**: si se cumple, sale de la lista aunque el técnico se vea bien.

Todos los tickers verificados contra `data/universe_snapshot.json` (snapshot 2026-06-12). Quedaron afuera por no estar en el universo: HCA, CNC, MOH, ENPH, NOC, GD, DLTR.

### A. Reversión post-shock — chips líderes (prioridad 1)

| Ticker | Ratio | Tesis | Catalizador en ventana | Invalidación de tesis |
|---|---|---|---|---|
| NVDA.BA | 24:1 | Backlog asegurado; impacto es de timing 2028 | Earnings **17/11** (confirmado) | Guidance de data center Q4 por debajo de lo esperado, o hyperscalers recortan capex 2027 |
| AMD.BA | 10:1 | Trimestre récord; Su proyecta >80% de crecimiento 2027 | Earnings ~principios de feb (estimado) | Revisión a la baja del outlook 2027 |
| AVGO.BA | 39:1 | ASIC custom para hyperscalers, menos dependiente de dónde se construye | Earnings ~mediados de dic (estimado) | Guidance de AI revenue por debajo del consenso |
| TSM.BA | 9:1 | Proveedor global; demanda de USA se relocaliza, no desaparece | Ventas mensuales + earnings ~mediados de ene (estimado) | Recorte de capex o de guidance de AI |
| MU.BA | 5:1 | Ídem, con más beta | Earnings ~mediados/fines de dic (estimado) | Caída de precios contractuales de DRAM/HBM |

**Condición de entrada:** RSI(14) en [25, 45] + vela de reversión al cierre + invalidación < precio. Si el RSI está < 25, se espera (no se fuerza el gate).

### B. Defensivos con viento político (prioridad 2)

| Ticker | Ratio | Tesis | Catalizador | Invalidación de tesis |
|---|---|---|---|---|
| SYY.BA | 8:1 | **Señal activa 6/11** (score 53, RSI 41,3, MA200 a 1,3%). Caída por balance, no por política; mantuvo guidance de EPS (+9% a +11%) | Earnings ~fines de ene (estimado) | Segunda baja de guidance o deflación persistente de alimentos |
| WMT.BA | 18:1 | Agenda de costo de vida | Earnings ~mediados de nov (estimado) | Recorte de guidance por consumo débil |
| COST.BA | 48:1 | Ídem; consumo resiliente | Ventas mensuales | Desaceleración de ventas comparables 2 meses seguidos |
| PG.BA | 15:1 | Defensivo puro | Earnings ~fines de ene (estimado) | Guidance de volumen orgánico negativo |

### C. Macro: oro (prioridad 2)

| Ticker | Ratio | Tesis | Invalidación de tesis |
|---|---|---|---|
| NEM.BA | 3:1 | Dólar más débil, tasas en baja tras la elección | Rebote sostenido del dólar (DXY) o suba de tasas reales |
| AEM.BA | 6:1 | Ídem, minera de menor costo | Ídem |
| GFI.BA / HMY.BA | 1:1 | Ídem, mayor beta | Ídem. **Ojo:** en el run del 6/11 usaron fallback a cache de fundamentals |

### D. Ganadores relativos a monitorear en pullbacks (prioridad 3)

| Ticker | Ratio | Tesis | Invalidación de tesis |
|---|---|---|---|
| MSFT.BA | 30:1 | Capex más lento mejora ROIC | Audiencias antimonopolio con propuestas concretas |
| AMZN.BA | 144:1 | Ídem | Ídem |
| FSLR.BA | 18:1 | Apoyo federal a solar se mantiene | Liquidez en BYMA insuficiente (volumen promedio bajo, verificar antes de operar) |

### Fuera de foco (sesgo negativo)

No se monitorean de forma proactiva. Si el scanner los da como señal, exigir revisión manual extra de noticias antes de operar (consistente con riesgo como ajuste, no como descarte automático):

- **CRWV, NBIS, IREN** — exposición directa a moratorias + deterioro de crédito (posible disparo del criterio C1 de solvencia).
- **VST, CEG** — demanda eléctrica de data centers en Texas.
- **LMT, RTX** — recorte de expectativas presupuestarias.
- **TSLA** — escrutinio sobre el merge SpaceX–Tesla.
- **COIN, MSTR** — más escrutinio regulatorio sobre cripto.

## 5. Calendario de catalizadores

| Fecha | Evento | Relevancia |
|---|---|---|
| 09/11/2026 | Se abre el pre-filing de proyectos de ley en Texas | Primeros proyectos sobre data centers |
| 17/11/2026 | Earnings NVDA (confirmado) | Test de la tesis A |
| 08–09/12/2026 | FOMC (con dot plot) | Tasas → oro y growth |
| ~mediados dic | Earnings AVGO, MU (estimado) | Test de la tesis A |
| 03/01/2027 | Asume el nuevo Congreso | Arrancan comisiones e investigaciones |
| 12/01/2027 | Abre la sesión legislativa de Texas | Proyectos de moratoria en juego |
| ~19/01/2027 | Asunción de Hinojosa (tercer martes de enero) | A partir de acá, posible moratoria ejecutiva |
| 26–27/01/2027 | FOMC | — |
| fines ene – principios feb | Earnings hyperscalers con **guidance de capex 2027** | **Catalizador más importante de la ventana** para chips |
| ~principios feb | Earnings AMD (estimado) | Test de la tesis A |
| ~fines feb | Earnings NVDA Q4 (estimado) | Cierre de la ventana |

Riesgo sin fecha: posible pelea por el techo de deuda y pedido de juicio político (mencionados por Natixis). No cuantificado.

## 6. Checks de revisión mensual

| # | Check | Pasa si |
|---|---|---|
| 1 | La moratoria de Texas sigue siendo promesa o ya está vigente | Se registra el estado actual y su alcance (aprobaciones nuevas vs. obras en curso) |
| 2 | Otros estados copiaron la moratoria | Lista de estados actualizada |
| 3 | Algún hyperscaler cambió su guidance de capex | Se registra la dirección del cambio |
| 4 | Cada ticker de la lista conserva su tesis | Ninguna invalidación de tesis disparada |
| 5 | Universo vigente | Tickers siguen en `universe_snapshot.json` con liquidez |

## 7. Contexto histórico (n chico)

En las tres midterms con Congreso demócrata y presidente republicano (1986, 1990, 2006), el S&P 500 promedió −0,5% el día de la reacción, +3,4% al mes y +10,9% al año (CNBC). **n=3: es contexto, no señal.**

---

## Fuentes

- [CNBC — Nasdaq en corrección (5/11)](https://www.cnbc.com/2026/11/04/stock-market-today-live-updates.html)
- [CNBC — Rebote en premarket (6/11)](https://www.cnbc.com/2026/11/05/stock-market-today-live-updates.html)
- [Investing.com — Cierre del 5/11](https://www.investing.com/news/stock-market-news/us-stock-index-futures-steady-after-midterms-rally-5001919)
- [CBS News — AMD, NVDA, CoreWeave](https://www.cbsnews.com/news/stocks-midterm-elections-tech-companies-ai-data-centers/)
- [IBTimes — Ganadores y perdedores del 4/11](https://www.ibtimes.com/us-stocks-rally-democrats-win-congress-2026-midterms-3809436)
- [Investing.com — Sectores ganadores y perdedores](https://www.investing.com/news/stock-market-news/which-sectors-will-benefit-most-and-face-pressure-after-democratic-sweep-93CH-4999088)
- [DCD — BMI: 53% del pipeline expuesto](https://www.datacenterdynamics.com/en/news/more-than-half-of-us-hyperscale-data-center-projects-face-regulatory-friction-after-2026-midterm-elections-report/)
- [24/7 Wall St — Texas 27% de la capacidad planificada](https://247wallst.com/investing/2026/11/04/texas-blue-wave-could-threaten-27-of-planned-u-s-data-center-power-heres-what-it-means-for-coreweave-iren-nebius-and-other-neocloud-stocks/)
- [Luminix — Bernstein: ~35% del pipeline creíble](https://www.useluminix.com/reports/industry-analysis/data-center-moratoriums-after-the-midterms)
- [Yahoo Finance — Texas: Senado estatal y moratoria](https://finance.yahoo.com/economy/article/democrats-victories-in-texas-laid-bare-voter-unease-over-data-centers--and-signal-new-hurdles-for-the-industry-142918051.html)
- [Multibagg — BNY sobre defensa](https://www.multibagg.ai/market-pulse/articles/us-midterm-sector-winners-losers-cmw1o73c5000zew2rmay9l24y)
- [Yahoo/Reuters — Reacción de analistas (Natixis)](https://finance.yahoo.com/markets/stocks/articles/analysts-react-us-midterm-election-025738421.html)
- [TradingKey — Sysco −9,8% el 3/11](https://www.tradingkey.com/news/market-movers/262268181-market-movers-syy-20261103)
- [Benzinga — Sysco reafirma guidance FY27](https://www.benzinga.com/markets/earnings/26/11/62822182/sysco-q1-earnings-sales-miss-estimates-full-year-eps-outlook-unchanged)
- [CM Elite — Fecha de earnings de NVDA](https://www.cmelitegroup.com/knowledge-hub/nvidia-earnings-date-fiscal-q3-2027-report-time-guidance-and-expected-move/)
- [TXLA — Calendario de la 90ª Legislatura de Texas](https://txla.org/advocacy/texas-legislative-process-2/)
- [Federal Reserve — Calendario de diciembre 2026](https://www.federalreserve.gov/newsevents/2026-december.htm)
- [FinanceCalendar — FOMC 2027](https://www.financecalendar.com/fomc-meetings/)
- [CNBC — Historia del S&P 500 post-midterms](https://www.cnbc.com/2026/11/02/stock-market-after-midterm-elections-sp-500-history.html)

*Las fechas marcadas "estimado" surgen del patrón histórico de reporte de cada empresa y deben confirmarse a medida que se anuncien.*
