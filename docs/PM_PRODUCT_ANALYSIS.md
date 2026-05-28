# PM Product Analysis — Batch Flip

**Date:** 2026-05-28
**Status:** Pre-launch, backend complete, frontend complete (separate repo)

---

## 1. Qué tenemos construido

### Números duros
| Métrica | Valor |
|---------|-------|
| Archivos Python | 42 |
| Endpoints API | 22 |
| Tablas DB | 6 (+ alembic) |
| Columnas totales | 158 |
| Campos por producto | 59 (en JobItemResponse) |
| Campos en export CSV | 54 |
| Engines de análisis | 6 (de FlipIQ) |
| Data providers | 5 (Keepa, SP-API, Hybrid, base, auth) |
| SP-API endpoints | 9 funcionando |
| Documentos | 5 (incident response, data classification, user workspace, PM decisions) |

### Features funcionales
```
✅ Auth: Supabase register/login/JWT + User ORM con plan/admin/rate limits
✅ Amazon OAuth: conectar cuenta de seller (10 test sellers autorizados)
✅ Upload: CSV/XLSX con auto-detección de columnas (50MB max, extension whitelist)
✅ Fast Scan: ~31K ASINs/hr (solo SP-API, batch endpoints)
✅ Deep Scan: ~400 ASINs/hr (SP-API + Keepa, datos completos)
✅ Dual FBA/MFN: ambos escenarios en 1 corrida, 1 CSV
✅ Listing Restrictions: can_sell per seller (SP-API)
✅ FBA Eligibility: fba_eligible per ASIN (SP-API)
✅ Fees exactos: SP-API getMyFeesEstimates batch (20/req)
✅ Buy Box real-time: SP-API Item Offers batch
✅ Monthly Sold: dato real de Keepa ("X+ bought in past month")
✅ Velocity Score: FlipIQ engine (0-100)
✅ Risk Score: FlipIQ engine
✅ Product Cache: tabla products compartida, cache 6h
✅ Rate Limiting: por plan (free 500, starter 50K, pro 200K/mes)
✅ Security: encryption at rest, audit logs, CORS whitelist, headers, password policy
✅ Export CSV: 54 columnas con FBA + MFN profit side-by-side
✅ Streamlit dev UI: single analysis + batch test
```

---

## 2. Posición Competitiva vs PC2

### Lo que PC2 hace y nosotros también
| Feature | PC2 | Batch Flip | Nota |
|---------|-----|-----------|------|
| Batch processing | 18K/hr | 31K/hr (fast) | **Somos más rápido** |
| Profit/ROI | ✅ | ✅ | Misma precisión (SP-API fees) |
| Listing restrictions | ✅ (cacheado) | ✅ (per seller) | |
| FBA eligibility | ✅ | ✅ | |
| Multi-marketplace | 10 mercados | 10 mercados | |
| CSV/XLSX upload | ✅ | ✅ | |
| UPC/EAN/ASIN/ISBN | ✅ | ✅ | |
| Multipack detection | ✅ | ✅ | |
| Export Excel/CSV | ✅ | ✅ (CSV, XLSX futuro) | |
| Historical data | ✅ (SP-API) | ✅ (Keepa 30/90/180d) | |

### Lo que nosotros tenemos y PC2 NO
| Feature | Ventaja | Impacto |
|---------|---------|---------|
| **Dual FBA/MFN en 1 corrida** | PC2 necesita 2 corridas + Excel manual | **ALTO** — ahorra 50% del tiempo |
| **best_scenario automático** | PC2 no lo calcula | **ALTO** — decisión inmediata |
| **monthly_sold real** | PC2 solo estima de BSR | **ALTO** — dato real vs estimación |
| **Buy Box stats por seller** | PC2 solo dice sí/no Amazon | **MEDIO** — quién domina el Buy Box |
| **Velocity Score 0-100** | PC2 no tiene scoring | **MEDIO** — priorización rápida |
| **Rating/Reviews** | PC2 no expone | **MEDIO** — calidad del listing |
| **Out of Stock %** | PC2 no trackea | **MEDIO** — oportunidad |
| **Risk Score** | PC2 no tiene | **BAJO** — analytics avanzado |
| **API-first** | PC2 es desktop | **ALTO** — integrable con cualquier tool |
| **Cloud-based** | PC2 requiere instalar | **ALTO** — acceso desde anywhere |
| **pricing_assumption transparency** | PC2 no explica | **MEDIO** — confianza |

### Lo que PC2 tiene y nosotros NO (todavía)
| Feature | Impacto | Prioridad |
|---------|---------|-----------|
| Custom filters (12+ operadores) | Medio | Post-launch |
| ASIN Scoring configurable | Bajo | Post-launch |
| Currency conversion | Medio (EU sellers) | Post-launch |
| Amazon Browser (storefront scan) | Bajo | Post-launch |
| Color highlights en Excel | Bajo | Post-launch |
| MFN BuyBox Premium adjust | Bajo | Post-launch |
| Reference Offer Selection | Bajo | Post-launch |

---

## 3. Readiness Assessment

### ✅ Listo para producción
| Componente | Status |
|-----------|--------|
| Backend API | ✅ 22 endpoints, auth, rate limiting |
| Database | ✅ 6 tablas en Supabase PostgreSQL |
| Auth | ✅ Supabase + User ORM + plans |
| Amazon OAuth | ✅ 10 test sellers |
| Data pipeline | ✅ Fast + Deep scan, dual FBA/MFN |
| Security | ✅ Encryption, audit, headers, CORS, password policy |
| Export | ✅ 54 columnas CSV |
| Frontend | ✅ (repo separado, completo) |

### ❌ Falta para lanzar
| Componente | Esfuerzo | Blocker? |
|-----------|----------|----------|
| **Deploy backend** | 1 día | **SÍ** — nada es accesible sin esto |
| **Stripe billing** | 2-3 días | **SÍ** — no podemos cobrar |
| **Dominio + SSL** | 1 hora | **SÍ** — necesario para OAuth callback |
| **OAuth redirect URL real** | 30 min | **SÍ** — Amazon necesita URL real |
| Onboarding email | 1 día | No — puede ser manual |
| Monitoring (Sentry) | 2 horas | No — nice to have |

---

## 4. Unit Economics

### Costos por seller
| Servicio | Costo/mes | Nota |
|----------|-----------|------|
| Keepa API (individual) | $20-50 | 20 tok/min, ~400 ASINs/hr Deep Scan |
| Supabase (free) | $0 | Hasta 50K MAU, 500MB DB |
| SP-API | $0 | Gratis (rate limits por seller) |
| Railway (deploy) | $5-20 | Depende de uso |
| **Total infra** | **~$25-70/mes** | |

### Revenue por seller
| Plan | Precio | Margen | Break-even |
|------|--------|--------|-----------|
| Starter ($49) | $49/mes | ~$30-45/mes | **1 seller paga la infra** |
| Pro ($99) | $99/mes | ~$70-95/mes | |
| Enterprise ($199) | $199/mes | ~$170-195/mes | |

### Keepa Economics
| Escenario | Costo Keepa | Revenue | Viable? |
|-----------|-------------|---------|---------|
| 1 seller Pro (Deep Scan) | $50/mes | $99/mes | ✅ ~50% margen |
| 5 sellers Starter (Fast only) | $0 extra (SP-API) | $245/mes | ✅ 90%+ margen |
| 10 sellers mix | ~$100/mes (upgrade Keepa) | ~$700/mes | ✅ 85% margen |

**Insight clave:** Fast Scan no usa Keepa → $0 costo marginal per seller. Deep Scan sí → necesita upgrade Keepa con más sellers.

### Escalar Keepa
| Plan Keepa | Tokens/min | Deep Scan/hr | Costo | Sellers soportados |
|-----------|-----------|-------------|-------|-------------------|
| Individual | 20 | 400 | $20-50/mes | 1-2 |
| Business | 100-500 | 2,000-10,000 | Negociable | 10-50 |

---

## 5. Go-to-Market

### Target customer
**Wholesale Amazon sellers** que:
- Reciben listas de proveedores (CSV/Excel) semanalmente
- Necesitan analizar 1,000-50,000 productos por lista
- Usan FBA como fulfillment primario
- Hoy usan PC2 ($148/mo) o hacen el análisis manualmente

### Pricing strategy
- **Undercut PC2:** Nuestro Pro ($99) tiene más features que PC2 ($148)
- **Fast Scan gratis:** 500 items/mes gratis → conversion funnel
- **Value prop:** "Lo que PC2 hace en 2 corridas, nosotros en 1. Con datos que PC2 no tiene."

### Differentiation messaging
```
"Upload your wholesale list. Get FBA AND MFN profit for every product 
in one scan. Know instantly: Can I sell it? How fast does it sell? 
Which fulfillment mode wins? Export and buy."
```

### Launch plan (10 test sellers)
```
Week 1: Deploy + domain + Stripe
Week 2: Invite 10 test sellers (free Pro for 30 days)
Week 3: Collect feedback, fix issues
Week 4: Open waitlist, $49/$99 pricing
```

---

## 6. Riesgos

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|-------------|---------|------------|
| Keepa rate limits insuficientes para Deep Scan con muchos sellers | Alta | Alto | Fast Scan es $0 marginal; upgrade Keepa plan cuando revenue lo justifique |
| Amazon revoca SP-API access | Baja | Crítico | Cumplimos Data Protection Policy; audit logs; incident response plan |
| PC2 copia nuestras features | Media | Medio | Ellos son desktop, nosotros cloud + API — ventaja estructural |
| Sellers no usan MFN comparison | Media | Bajo | Ya verificamos: si no la usan, el rest del producto sigue siendo valioso |
| Supabase free tier no alcanza | Baja | Bajo | Upgrade a $25/mes cuando necesitemos |

---

## 7. Decisión Final PM

### Lo que está HECHO y es BUENO
El backend es **feature-complete para launch**. 22 endpoints, dual FBA/MFN, 54 columnas en export, security compliance, rate limiting por plan. Supera a PC2 en datos y velocidad.

### Lo que FALTA y es BLOCKER
1. **Deploy** (1 día)
2. **Stripe** (2-3 días)
3. **Dominio** (1 hora)

### Lo que NO falta para launch
- Custom filters → post-launch
- Currency conversion → post-launch
- Excel highlights → post-launch
- Más engines (AI, opportunity score) → post-launch

### Recomendación
**Ship it.** El producto tiene más features que PC2 a menor precio. El backend está listo. El frontend está listo. Los únicos blockers son infra (deploy + billing). Eso son 3-4 días de trabajo.

**No seguir agregando features al backend.** Cada día sin deploy es un día sin feedback de sellers reales. El feedback es más valioso que cualquier feature que podamos imaginar.

```
PRIORIDAD 1: Deploy backend (Railway)
PRIORIDAD 2: Stripe checkout ($49/$99)  
PRIORIDAD 3: Invitar 10 test sellers
PRIORIDAD 4: Iterar basado en feedback
```
