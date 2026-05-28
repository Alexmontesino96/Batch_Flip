# Price Checker 2 vs Batch Flip — Comparación Detallada

## Planes y Precios

### PC2
| Plan | Precio | Límites |
|------|--------|---------|
| Free Demo | $0 | 1 ejecución, hasta 20K items |
| Monthly | $108-148/mes | Ilimitado |

- **Un solo plan de pago** — sin tiers
- Software de escritorio (Windows/Mac)
- No tiene API — solo UI de desktop

### Batch Flip (propuesto)
| Plan | Precio | Límites | Diferenciador |
|------|--------|---------|---------------|
| Free | $0 | 500 items, 1 job | Prueba |
| Starter | $49/mes | 50K items/mes, 10 jobs | SP-API restrictions |
| Pro | $99/mes | 200K items/mes, 50 jobs | + AI explanations |
| Enterprise | $199/mes | Ilimitado + API keys | Priority support |

- **4 tiers** con progresión de features
- Cloud-based (API + Web app)
- API-first — integrable con cualquier herramienta

---

## Datos de Análisis por Producto

### Datos que AMBOS tienen

| Dato | PC2 (fuente) | Batch Flip (fuente) |
|------|-------------|-------------------|
| ASIN | SP-API | Keepa + SP-API |
| Title | SP-API | Keepa |
| Brand | SP-API | Keepa |
| Manufacturer | SP-API | Keepa |
| Model | SP-API | Keepa |
| Color, Size | SP-API | Keepa |
| Product Group/Type | SP-API | Keepa |
| Parent ASIN | SP-API | Keepa |
| UPC/EAN | SP-API | Keepa |
| Image | SP-API | Keepa |
| List Price (MSRP) | SP-API | Keepa |
| BSR (Sales Rank) | SP-API | SP-API (real-time) + Keepa (historial) |
| Buy Box Price | SP-API | **SP-API Item Offers** (real-time) |
| # of Sellers | SP-API | Keepa + SP-API |
| Hazmat | SP-API | Keepa (detallado) + SP-API Catalog |
| Shipment Restrictions | SP-API | SP-API (parcial, pendiente rol FBA) |
| Trade-in Eligible | SP-API | SP-API Catalog |
| Multi ASIN? | SP-API | Keepa (upcList) |
| Multipack Qty | SP-API | Keepa + SP-API |
| Inactive/Redirects | SP-API | Keepa (isRedirectASIN) |
| Dimensions/Weight | SP-API | Keepa + SP-API |
| $ Net Profit | Calculado | Calculado (profit_engine de FlipIQ) |
| % ROI | Calculado | Calculado |
| FBA Fees | SP-API | **SP-API Fees Estimate** (exacto al centavo) |
| Referral Fee | SP-API | **SP-API Fees Estimate** |
| Total Amazon Fees | SP-API | **SP-API Fees Estimate** |
| Listing Restrictions | SP-API | **SP-API Listing Restrictions** |
| Brand Gating | SP-API | **SP-API Listing Restrictions** |
| # of Variations | SP-API | Keepa (variations[]) |
| Is Amazon a Seller? | SP-API (historical) | Keepa (buy_box_stats) + SP-API |
| Links (Keepa, CamelCC, Alibaba, Google) | Construidos | Construidos |

### Datos que SOLO PC2 tiene (SP-API exclusivos)

| Dato | PC2 | Batch Flip | Nota |
|------|-----|-----------|------|
| Trade-in Price ($) | ✅ SP-API | ❌ | Keepa no tiene el valor en $ |
| Seller SKU lookup | ✅ SP-API | ❌ | Requiere SP-API autenticada |
| FBA Inbound Eligibility | ✅ SP-API | ⏳ Pendiente rol | Necesitamos rol Amazon Fulfillment |
| 50+ atributos extra | ✅ SP-API Catalog | ✅ SP-API Catalog attributes | Actor, Director, Genre, etc. |
| MFN BuyBox Premium | ✅ Setting configurable | ❌ | Ajuste para MFN vs FBA pricing |
| Reference Offer Selection | ✅ Configurable | ❌ | Qué precio alimenta el profit calc |
| In-Stock Filter | ✅ Setting | ❌ | Ignorar ofertas no disponibles |

### Datos que SOLO Batch Flip tiene (Keepa + nuestros engines)

| Dato | Batch Flip | PC2 | Ventaja |
|------|-----------|-----|---------|
| **Monthly Sold** | ✅ 40,000/mes | ❌ | Dato REAL de Amazon "X+ bought in past month" |
| **Sales Rank Drops 30/90d** | ✅ 5/16 drops | ❌ | Cada drop ≈ 1 venta, más preciso que BSR estimation |
| **Est. Sales/Month** | ✅ (de monthlySold) | ✅ (estimado de BSR) | **Nuestro dato es real, PC2 estima** |
| **Buy Box Stats por Seller** | ✅ {Amazon: 83%, SellerX: 17%} | ❌ | % exacto de quién tiene el Buy Box |
| **Buy Box Price historial** | ✅ 30/90/180 días | ❌ (solo actual) | Tendencia de precios |
| **Avg Price 30/90/180d** | ✅ Keepa stats | ✅ (historical data) | Ambos lo tienen |
| **Out of Stock % 90d** | ✅ Keepa | ❌ | Oportunidad cuando Amazon no tiene stock |
| **Amazon OOS Days 30d** | ✅ Keepa | ❌ | Días que Amazon estuvo sin stock |
| **Rating** | ✅ 4.6/5.0 (Keepa) | ❌ | SP-API no expone rating |
| **Review Count** | ✅ 147,552 (Keepa) | ❌ | SP-API no expone reviews |
| **Lowest Price New** | ✅ SP-API Item Offers | ❌ | Precio mínimo por condición |
| **Lowest Price Used** | ✅ SP-API Item Offers | ❌ | |
| **BB Eligible Offers (New/Used)** | ✅ SP-API Item Offers | ❌ | Cuántos compiten por Buy Box |
| **Offer Count FBA vs FBM** | ✅ SP-API Item Offers | ❌ (solo total) | Separado por fulfillment channel |
| **Velocity Score** | ✅ 0-100 (FlipIQ engine) | ❌ | Score normalizado de velocidad |
| **Estimated Days to Sell** | ✅ "~1d", "~7-14d" | ❌ | Estimación legible |
| **Risk Score** | ✅ 0-100 (FlipIQ engine) | ❌ | Volatilidad y dispersión de precios |
| **Competition HHI** | ✅ (FlipIQ engine) | ❌ | Índice de concentración de sellers |
| **Opportunity Score** | ✅ 0-100 (futuro) | ❌ | Score combinado multi-factor |
| **Recommendation** | ✅ buy/watch/pass (futuro) | ❌ | Decisión automatizada |
| **AI Explanation** | ✅ Gemini/GPT (futuro) | ❌ | Explicación en lenguaje natural |

---

## Tipos de Análisis

### PC2
| Tipo | Descripción |
|------|-------------|
| **File Analysis** | Procesar CSV/XLSX del proveedor |
| **Amazon Browser** | Escanear storefronts, brand stores, search results |
| **Quick Lookup** | Un solo producto |
| **CLI Automation** | Batch via línea de comandos |

### Batch Flip
| Tipo | Descripción | Estado |
|------|-------------|--------|
| **Batch Job** | Procesar CSV/XLSX del proveedor (POST /jobs) | ✅ Implementado |
| **Single Analysis** | Un solo producto (POST /analyze) | ✅ Implementado |
| **API Access** | Integrar con cualquier herramienta | ✅ Nativo |
| **Storefront Scan** | Escanear storefronts | ⏳ Futuro |
| **Watchlist + Alerts** | Monitorear precios y alertar | ⏳ Futuro (de FlipIQ) |

---

## Pipeline de Procesamiento

### PC2 (4 pasos)
```
1. Parse archivo → detectar IDs y costos
2. SP-API lookup → datos de producto + fees + restrictions
3. Calcular profit/ROI
4. Exportar Excel
```

### Batch Flip (6 fases)
```
1. Resolve IDs       → UPC/EAN → ASIN (Keepa)
2. Keepa Batch       → monthlySold, BSR, Buy Box stats, rating, reviews, fees, OOS%
3. SP-API Restrict.  → can_sell per seller (5 req/sec)
4. SP-API Fees       → Fees exactos al centavo (solo vendibles)
5. SP-API Offers     → Buy Box real-time, lowest prices, BB eligible offers
6. Analysis          → Profit, velocity score, risk score, competition
```

**Diferencia clave:** Batch Flip tiene 2 fuentes de datos combinadas (Keepa históricos + SP-API real-time) vs PC2 que solo usa SP-API.

---

## Configuración del Análisis

### PC2 ofrece
| Setting | Descripción | Batch Flip? |
|---------|-------------|-------------|
| Cost Profile (FBA/MFN/EFN) | Costos de fulfillment | ✅ FBA/MFN (inline) |
| Prep costs | Costo de preparación | ✅ |
| Shipping to Amazon | Costo de envío | ✅ |
| VAT treatment | Impuestos (EU) | ⏳ Futuro |
| Currency conversion | Conversión de monedas | ⏳ Futuro |
| Custom Filters | Filtros por cualquier campo | ⏳ Futuro |
| Major Brands | Lista de marcas gated | ⏳ Futuro |
| ASIN Scoring | Puntuación ponderada custom | ⏳ Futuro (Opportunity Score) |
| Reference Offer | Qué precio usa para profit | ❌ |
| MFN Premium | Premium para MFN vs FBA | ❌ |
| In-Stock Filter | Solo ofertas disponibles | ❌ |
| Historical Data toggle | Activar/desactivar datos históricos | ❌ (siempre activo via Keepa) |
| Color Highlights | Colores en Excel | ⏳ Futuro |
| Cache Control | Controlar cache de datos | ❌ (automático) |

---

## Resumen Ejecutivo

| Aspecto | PC2 | Batch Flip | Ganador |
|---------|-----|-----------|---------|
| **Datos de producto** | SP-API | Keepa + SP-API | **Batch Flip** (más datos) |
| **Velocidad de venta** | Estimado de BSR | monthlySold REAL + rankDrops | **Batch Flip** (dato real) |
| **Buy Box analysis** | Básico (sí/no Amazon) | % por seller + historial + BB eligible | **Batch Flip** |
| **Listing restrictions** | ✅ Completo | ✅ Completo | Empate |
| **Fees exactos** | ✅ SP-API | ✅ SP-API + Keepa fallback | **Batch Flip** (doble fuente) |
| **Reviews/Rating** | ❌ No tiene | ✅ Keepa | **Batch Flip** |
| **Stock tracking** | ❌ | ✅ OOS%, Amazon OOS days | **Batch Flip** |
| **Scoring inteligente** | ASIN Scoring (manual) | Velocity + Risk + Opportunity (automático) | **Batch Flip** |
| **Throughput** | 18K/hora | ~5K/hora (dual source) | **PC2** (solo SP-API) |
| **Plataforma** | Desktop (Win/Mac) | Cloud (API + Web) | **Batch Flip** |
| **Precio** | $148/mes (1 plan) | $49-199/mes (4 tiers) | **Batch Flip** (más flexible) |
| **Configurabilidad** | Muy alta (15+ settings) | Media (creciendo) | **PC2** (más maduro) |
| **Integraciones** | CLI | API REST | **Batch Flip** |
| **Amazon Browser** | ✅ Storefront scanning | ❌ | **PC2** |
