# Contexto Político USA — Noviembre 2026 → Febrero 2027

> Documento de contexto para las revisiones semanales del scanner y para priorizar la watchlist manual.
> **No modifica ningún gate ni umbral del sistema.** Los criterios siguen siendo los de `CRITERIOS_INVERSION.md`.
> Si en algún momento esta lista pasa a influir en el código (ej. un `focus_list.yaml` que ajuste score), eso es cambio de criterio y requiere entrada en `DECISIONS.md`.
>
> Creado: 2026-11-06 · Última actualización: 2026-11-06 (primer bloque de puntajes) · Vigencia: hasta 2027-02-28 · Próxima revisión: mensual (primer viernes de cada mes)

---

## 1. Qué pasó

- **3/11 — Midterms:** los demócratas ganaron mayoría en ambas cámaras del Congreso y gobernaciones clave, incluida Texas (Gina Hinojosa, que hizo campaña con una moratoria a data centers). Trump mantiene el veto por los próximos dos años → gobierno dividido.
- **4/11 — Rally de alivio:** Dow +3% (+1.569 pts), S&P +1,6%, Nasdaq +1,4%. Debajo de la superficie, chips y data centers ya caían. Ganadores del día: hospitales (HCA +10,6%), solar (FSLR +9,4%), consumo de descuento (DLTR +8,9%), hyperscalers (MSFT +6%, AMZN +8%). Perdedores: defensa, neoclouds, nombres ligados a Trump/Musk.
- **5/11 — Rout de chips:** Nasdaq −5,52% a 24.315 (en corrección, >10% bajo el máximo de octubre). SOX −12%, peor día de chips desde marzo 2020. NVDA −9,3% (USD 181,60), AMD −17,3%, MU ~−17%, AVGO −10%, Intel −10,4%. Neoclouds (CRWV, NBIS, IREN) entre −10% y −16%. Agravantes ajenos a la elección: outlook débil de Qualcomm y Arm.
- **5/11 — Cierre amplio:** S&P 500 −4,36% a 7.353,73; SOX −12,25%. NVDA perdió ~USD 450.000 M de capitalización (peor día desde DeepSeek).
- **6/11 — Premarket:** rebote parcial (MU +9%, TSM +7,4%, NVDA +3–4%) antes del reporte de empleo de octubre (consenso: +65K, desempleo 4,2%). **Dato real del reporte: sin dato** al momento de la actualización.
- **Fed:** el mercado descuenta una **suba** de 25 pb en diciembre (FedWatch ~69% al 5–6/11, bajando desde ~85% tras el FOMC del 28/10). Tasa actual 3,75–4%; votación 10-2 con dos disidencias a favor de subir. **Corrige la premisa de "tasas en baja"** de versiones previas de este doc: lo que bajó tras la elección fueron los rendimientos de los bonos, no la expectativa de la Fed.
- **Dólar y commodities:** DXY a mínimo de un mes (~101,35) tras la elección; oro recuperó USD 4.000 y llegó a ~USD 4.124 el 6/11 (máximo desde el 20/10); petróleo en fuerte baja el 4/11.
- **Capex de hyperscalers (temporada Q3):** ningún recorte de 2027. MSFT bajó su capex 2026 a ~USD 170.000 M (desde 175.000 M) por demoras de proveedores de GPU — capacidad que se corre a 1S27, no se cancela; Azure +48%. AMZN mantiene ~USD 220.000 M en 2026 y gastará "significativamente más" en 2027. GOOGL: capex "sube significativamente" en 2027. META: presupuesto 2027 en armado, "inversión agresiva".
- **Congreso:** la agenda demócrata conocida se centra en costo de vida (revertir aranceles, crédito por hijo, subsidios de salud) e investigaciones. **Sin novedades** concretas sobre precios de medicamentos, IA, cripto, presupuesto de defensa o techo de deuda.

## 2. El tamaño real de la amenaza

| Nivel | Riesgo | Por qué |
|---|---|---|
| Federal | **Bajo** | Trump veta. El riesgo concreto son audiencias e investigaciones, no leyes. |
| Estatal (Texas) | **Alto, con freno** | Texas ≈ 27% de la capacidad de data centers planificada en USA (Wells Fargo). **Ya hay una pausa vigente:** Abbott frenó desde el 3/8 la conexión de nuevos DC a la red hasta que ERCOT/PUCT terminen una auditoría de energía y agua (ERCOT postergó el estudio "Batch Zero"), y desde el 21/9 la extendió a permisos ambientales (TCEQ). Se esperaba que la auditoría terminara en diciembre y que los permisos se reanudaran. **Lo que promete Hinojosa es extender** esa pausa hasta que la Legislatura (abre el 12/01) apruebe reglas. Frenos: Senado estatal republicano, permisos con derechos adquiridos (*grandfathered*), posibles obstáculos legales. Ninguna moratoria por ley. |
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
| Oro y mineras (NEM, AEM, GFI, HMY) | Dólar débil, rendimientos de bonos en baja | Macro | — | Suba fuerte el 4/11; +10% en ARS en 5 ruedas | Viento a favor macro, con riesgo de suba de la Fed en diciembre (~69%) |

## 4. Lista de foco Nov 2026 → Feb 2027

**Regla de uso:** esta lista prioriza qué revisar a mano en cada ciclo semanal. **No es una lista de compra.** Ningún ticker se opera sin señal del scanner con su nivel de invalidación técnica en ARS (Filtro 2). Cada ticker tiene además una **invalidación de tesis**: si se cumple, sale de la lista aunque el técnico se vea bien.

Todos los tickers verificados contra `data/universe_snapshot.json` (snapshot 2026-06-12). Quedaron afuera por no estar en el universo: HCA, CNC, MOH, ENPH, NOC, GD, DLTR.

### A. Reversión post-shock — chips líderes (prioridad 1)

| Ticker | Ratio | Tesis | Catalizador en ventana | Invalidación de tesis |
|---|---|---|---|---|
| NVDA.BA | 24:1 | Backlog asegurado; impacto es de timing 2028 | Earnings **17/11** después del cierre (Earnings Whispers/CM Elite: confirmado; TipRanks: estimado). Consenso ~USD 109.000 M de ingresos, EPS ~2,48 | Guidance de data center Q4 por debajo de lo esperado, o hyperscalers recortan capex 2027 |
| AMD.BA | 10:1 | Q3 récord (reportado 3/11): ingresos +45%, data center +97%; guidance Q4 ~USD 17.000 M sobre consenso; data center >80% de los ingresos en 2027 (antes 70%) | Earnings ~principios de feb (estimado) | Revisión a la baja del outlook 2027 |
| AVGO.BA | 39:1 | ASIC custom para hyperscalers, menos dependiente de dónde se construye. Guidance Q4: AI revenue USD 21.700 M; "visibilidad" de USD 115.000 M en FY27 | Earnings **9/12** después del cierre (anunciado por la empresa en el call de Q3) | Guidance de AI revenue por debajo del consenso |
| TSM.BA | 9:1 | Proveedor global; demanda de USA se relocaliza, no desaparece | Ventas mensuales + earnings ~mediados de ene (estimado) | Recorte de capex o de guidance de AI |
| MU.BA | 5:1 | Ídem, con más beta | Earnings ~mediados/fines de dic (estimado) | Caída de precios contractuales de DRAM/HBM |

**Condición de entrada:** RSI(14) en [25, 45] + vela de reversión al cierre + invalidación < precio. Si el RSI está < 25, se espera (no se fuerza el gate).

**⚠ AVGO.BA no es operable con el sistema actual:** está en `data/sources/yfinance_exclusions.json` (`failed_verification`, desde 2026-06-29). El scanner nunca puede darle señal ni invalidación técnica. Hasta resolver la exclusión (o definir otra fuente de precios), queda en la lista solo como referencia sectorial.

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
| NEM.BA | 3:1 | Dólar más débil y rendimientos en baja tras la elección. Q3: guidance de producción mantenido (5,3 M oz), AISC mejorado a USD 1.520/oz | Rebote sostenido del dólar (DXY) o suba de tasas reales |
| AEM.BA | 6:1 | Ídem, minera de menor costo | Ídem |
| GFI.BA / HMY.BA | 1:1 | Ídem, mayor beta | Ídem. **Ojo:** en el run del 6/11 usaron fallback a cache de fundamentals |

### D. Ganadores relativos a monitorear en pullbacks (prioridad 3)

| Ticker | Ratio | Tesis | Invalidación de tesis |
|---|---|---|---|
| MSFT.BA | 30:1 | Capex más lento mejora ROIC | Audiencias antimonopolio con propuestas concretas |
| AMZN.BA | 144:1 | Ídem. **Ojo:** la premisa de "capex más lento" no aplica a AMZN — en Q3 dijo que gastará significativamente más en 2027 y el FCF de 12 meses es negativo. La tesis que queda es AWS (+39%, guidance >40% en 2027–2028) | Ídem |
| FSLR.BA | 18:1 | Apoyo federal a solar se mantiene. **Ojo:** recortó guidance el 29/10 (volumen 16–17 GW, ventas USD 4.600–4.900 M) | Liquidez en BYMA insuficiente (volumen promedio bajo, verificar antes de operar). *Pendiente: definir una invalidación de tesis de negocio; la liquidez es un gate, no una tesis* |

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
| 17/11/2026 | Earnings NVDA (después del cierre; fuentes discrepan sobre si está confirmado) | Test de la tesis A |
| 19/11/2026 | Earnings WMT (antes de la apertura; fuentes discrepan sobre si está confirmado) | Test de la tesis B |
| diciembre 2026 | Cierre esperado de la auditoría ERCOT/PUCT de la pausa de Abbott | Si se reanudan los permisos antes de que asuma Hinojosa → atenuante para el bloque A |
| ~principios dic | Ventas mensuales de COST (noviembre) | Test de la tesis B |
| 08–09/12/2026 | FOMC (con dot plot). Mercado descuenta ~69% de **suba** | Tasas → oro y growth |
| 09/12/2026 | Earnings AVGO (anunciado por la empresa en el call de Q3) | Test de la tesis A |
| ~mediados/fines dic | Earnings MU (estimado) | Test de la tesis A |
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

## Historial de puntajes

> Puntaje de momento (1–10) = T + F + P + M + A, con topes G0–G4. **No es señal de compra ni gate.** Prioriza qué revisar. Este historial existe para auditar más adelante si los puntajes altos anticiparon mejores resultados; con n chico no se saca ninguna conclusión.
> T de los tickers sin señal ni near-miss: derivado de `data/prices.py` (yfinance, segmento pesos), MA200 y RSI(14) de Wilder sobre el cierre del 2026-11-05. Validado contra la salida del scanner para SYY (precio, RSI y MA200 coinciden exactamente). El scanner no persiste MA200 para tickers sin señal.

### 2026-11-06

| fecha | ticker | T | F | P | M | A | gate | final | banda |
|---|---|---|---|---|---|---|---|---|---|
| 2026-11-06 | AMD.BA | 2 | 2 | 1 | 0 | 1 | G4 | 6 | Vigilar |
| 2026-11-06 | NEM.BA | 2 | 2 | 1 | 1 | 0 | G4 | 6 | Vigilar |
| 2026-11-06 | SYY.BA | 4 | 0 | 1 | 0 | 0 | ninguno | 5 | Neutral |
| 2026-11-06 | MSFT.BA | 2 | 2 | 1 | 0 | 0 | G4 | 5 | Neutral |
| 2026-11-06 | AEM.BA | 2 | 1 | 1 | 1 | 0 | G4 | 5 | Neutral |
| 2026-11-06 | HMY.BA | 2 | 1 | 1 | 1 | 0 | G4 | 5 | Neutral |
| 2026-11-06 | NVDA.BA | 1 | 1 | 1 | 0 | 1 | G4 | 4 | Neutral |
| 2026-11-06 | TSM.BA | 1 | 1 | 1 | 0 | 1 | G4 | 4 | Neutral |
| 2026-11-06 | WMT.BA | 2 | 1 | 1 | 0 | 0 | G4 | 4 | Neutral |
| 2026-11-06 | COST.BA | 2 | 1 | 1 | 0 | 0 | G4 | 4 | Neutral |
| 2026-11-06 | PG.BA | 2 | 1 | 1 | 0 | 0 | G4 | 4 | Neutral |
| 2026-11-06 | AMZN.BA | 2 | 1 | 1 | 0 | 0 | G4 | 4 | Neutral |
| 2026-11-06 | MU.BA | 1 | 1 | 1 | 0 | 0 | G4 | 3 | Evitar |
| 2026-11-06 | GFI.BA | 1 | 0 (sin dato) | 1 | 1 | 0 | G4 | 3 | Evitar |
| 2026-11-06 | AVGO.BA | 0 (sin dato) | 1 | 1 | 0 | 0 (sin dato) | G1, G4 | 2 | Evitar |
| 2026-11-06 | FSLR.BA | 1 | 0 | 1 | 0 | 0 | G4 | 2 | Evitar |

Estado de la corrida: **INCOMPLETA** — AVGO.BA sin dato técnico (excluido de yfinance). G1 y G4 no cambian ningún puntaje final (ninguno superaba su tope). G2: todos superan `ADV_MIN_ARS` (15 M ARS); SYY al límite (17 M). G3: sin earnings en ≤3 días hábiles.

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

**Actualización 2026-11-06 (puntajes):**

- [Texas Tribune — Con Hinojosa, la pausa podría seguir (4/11)](https://www.texastribune.org/2026/11/04/data-center-texas-pause-gina-hinojosa-governor-policies/)
- [Houston Public Media — Abbott pausa nuevos DC hasta auditoría ERCOT/PUCT (3/8)](https://www.houstonpublicmedia.org/articles/news/energy-environment/2026/08/03/558529/gov-greg-abbott-pauses-new-data-centers-until-ercot-puct-audit-energy-water-usage/)
- [Texas Tribune — Pausa de permisos ambientales (21/9)](https://www.texastribune.org/2026/09/21/texas-data-center-moratorium-water-energy/)
- [E&E News — La pausa reordena planes de red](https://www.eenews.net/articles/texas-data-center-approval-halt-scrambles-grid-plans/)
- [CNN — Consecuencias económicas de la ola anti-DC (5/11)](https://www.cnn.com/2026/11/05/economy/data-center-texas-election)
- [TipRanks — Mercado 6/11, futuros](https://www.tipranks.com/news/stock-market-today-nov-6-futures-mixed-as-nasdaq-futures-rebound-after-tech-selloff)
- [CoinCentral — USD 2,3 billones borrados antes del reporte de empleo](https://coincentral.com/stock-market-today-data-center-worries-erase-2-3-trillion-from-us-stocks-before-jobs-report)
- [TechFlow — FedWatch: 68,7% de suba en diciembre](https://www.techflowpost.com/en-US/newsletter/143261)
- [Norada — Probabilidad de suba en dic. 85% tras el FOMC de octubre](https://www.noradarealestate.com/blog/interest-rates-hike-odds-december-2026-jump-85-after-feds-recent-decision/)
- [FXStreet — Oro recupera USD 4.000, el dólar cae tras la elección](https://www.fxstreet.com/news/gold-reclaims-4-000-as-us-midterm-sweep-sinks-usd-oil-plunges-202611041803)
- [Vantage — Oro y payrolls, semana 2–6/11](https://www.vantagemarkets.com/market-analysis/why-gold-slipped-wall-street-slid-payrolls-xauusd-november-2-6-2026/)
- [HL — Capex de hyperscalers 2026/2027](https://www.hl.co.uk/news/ai-hyperscalers-are-expected-to-finish-the-year-spending-a-whopping-828-billion-on-capex)
- [investingLive — MSFT capex ~USD 170.000 M](https://investinglive.com/stocks/microsoft-sees-170bn-capex-in-fiscal-2027-but-says-it-will-stay-cash-flow-positive/)
- [Convexity — MSFT Q1 FY27: Azure y capex](https://convexityos.com/blog/microsoft-q1-fy2027-azure-capex)
- [Data Studios — AMZN Q3 2026](https://www.datastudios.org/post/amazon-q3-2026-results-aws-39-percent-growth-46-billion-220-billion-capex)
- [Vested Finance — AMZN −7% post Q3](https://vestedfinance.com/blog/us-stocks/amazon-falls-7-after-q3-2026-earnings-aws-surges-39-as-operating-margin-hits-record-high/)
- [Bloomberg Gov — Agenda demócrata de costo de vida 2027](https://news.bgov.com/bloomberg-government-news/democrats-plot-2027-affordability-agenda-in-quest-to-flip-house)
- [NOTUS — Agenda demócrata en definición](https://www.notus.org/congress/democrats-midterms-donald-trump-house-control)
- [Benzinga — NVDA −24% antes de earnings, valuación](https://www.benzinga.com/markets/prediction-markets/26/11/62956559/nvidia-stock-selloff)
- [TipRanks — Fecha de earnings NVDA](https://www.tipranks.com/stocks/nvda/earnings)
- [24/7 Wall St — NVDA peor día desde DeepSeek](https://247wallst.com/investing/2026/11/06/nvidia-just-had-its-worst-day-since-deepseek-losing-about-450-billion/)
- [Benzinga — AMD Q3 2026 y guidance Q4](https://www.benzinga.com/markets/earnings/26/11/62845344/amd-posts-q3-double-beat-as-data-center-segment-shines-growth-expected-to-accelerate-in-q4)
- [Chartmill — AMD guidance sobre consenso](https://www.chartmill.com/news/AMD/Chartmill-57632-Advanced-Micro-Devices-NASDAQAMD-Q3-2026-Earnings-Data-Center-Nearly-Doubles-and-Guidance-Tops-Consensus)
- [Investing.com — AVGO call Q3 FY26 (fecha 9/12, guidance AI)](https://www.investing.com/news/transcripts/earnings-call-transcript-broadcom-tops-q3-2026-estimates-as-ai-sales-surge-93CH-4886849)
- [Yahoo Finance — TSM: Bernstein sube target a 600 (4/11)](https://finance.yahoo.com/quote/TSM/)
- [Forbes — MU: HBM vendido, riesgo de sobreoferta](https://www.forbes.com/sites/petercohan/2026/05/27/microns-unstoppable-march-past-1-trillion/)
- [SoftwareSeni — Precios contractuales de DRAM 2026 (TrendForce)](https://www.softwareseni.com/dram-prices-in-2026-have-doubled-and-the-numbers-are-getting-worse/)
- [Yahoo Finance — WMT: mejor mes desde 1999, guidance Q3](https://finance.yahoo.com/markets/stocks/articles/walmart-having-best-month-since-134058825.html)
- [Earnings Whispers — WMT 19/11](https://www.earningswhispers.com/stocks/WMT)
- [Costco IR — Ventas de octubre 2026](https://investor.costco.com/news/news-details/2026/Costco-Wholesale-Corporation-Reports-October-Sales-Results/default.aspx)
- [SEC — P&G 8-K Q1 FY27](https://www.sec.gov/Archives/edgar/data/0000080424/000008042426000250/fy2627q1jas8-kexhibit991.htm)
- [Newmont — Resultados Q3 2026](https://www.newmont.com/investors/news-release/news-details/2026/Newmont-Reports-Third-Quarter-2026-Results-with-Record-Third-Quarter-Adjusted-Net-Income-Positioned-to-Achieve-Full-Year-Guidance-Provides-Update-on-Red-Chris-Block-Cave-Project/default.aspx)
- [TradingView/PRNewswire — AEM Q3 2026](https://www.tradingview.com/news/prnewswire:02974183216d9:0-agnico-eagle-reports-third-quarter-2026-results-strong-free-cash-flow-generation-driven-by-solid-operational-performance-on-track-to-achieve-2026-production-and-cost-guidance/)
- [Investing.com — AEM supera estimaciones, la acción cae](https://www.investing.com/news/transcripts/earnings-call-transcript-agnico-eagle-beats-q3-2026-estimates-shares-fall-93CH-4989461)
- [SEC — Harmony 6-K resultados FY26](https://www.sec.gov/Archives/edgar/data/0001023514/000162828026059198/harmony-shortformxresultsf.htm)
- [Chartmill — FSLR Q3: guidance de ventas más débil](https://www.chartmill.com/news/FSLR/Chartmill-57288-First-Solar-NASDAQFSLR-Posts-Mixed-Q3-With-EPS-Beat-Revenue-Miss-and-Soft-Sales-Guidance)
- Scanner: `output/reversiones_2026-11-06.md` (SYY: noticias JPMorgan 4/11 y guidance de Sysco 3/11 marcadas [VERIFIED])

*Las fechas marcadas "estimado" surgen del patrón histórico de reporte de cada empresa y deben confirmarse a medida que se anuncien.*
