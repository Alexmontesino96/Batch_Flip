# Batch Flip — Visión del Producto

## ¿Qué es Batch Flip?

Batch Flip es una **plataforma SaaS API-first** que permite a vendedores de Amazon analizar listas de productos wholesale en masa para identificar cuáles son rentables para revender. El vendedor sube un archivo con miles de productos de su proveedor, y en minutos recibe un análisis completo de cada producto: si se puede vender, cuánto ganará, qué tan rápido se vende, y qué tan riesgoso es.

Es el equivalente moderno y cloud-based de **Price Checker 2** (PC2) de Daily Source Tools — un software de escritorio de $148/mes que domina este mercado desde 2015 — pero con ventajas significativas: más inteligente (AI + scoring avanzado), más rápido (cloud, no desktop), y más accesible (API + web app, no solo Windows/Mac).

---

## ¿Para quién es?

**Resellers de Amazon** que compran productos al por mayor (wholesale) para revender en Amazon. Su flujo de trabajo típico:

1. Un proveedor les envía una **lista de precios** con miles de productos (CSV/Excel con UPC y costos)
2. Necesitan analizar **cada producto** para saber: ¿puedo venderlo? ¿a qué precio se vende? ¿cuánto ganaré después de fees?
3. De 10,000 productos, quizás solo 200-500 son rentables
4. Compran esos 200-500 productos, los envían a Amazon FBA, y los venden

Este proceso se repite **semanalmente** con múltiples proveedores. Analizar manualmente es imposible — necesitan herramientas como PC2 o Batch Flip.

---

## ¿Qué problema resuelve?

### Sin Batch Flip:
- El seller recibe una lista de 50,000 productos
- Tiene que buscar **cada uno manualmente** en Amazon
- Calcular fees, profit, verificar si puede venderlo
- Esto toma **días o semanas** por lista
- Muchos sellers simplemente no analizan todo y pierden oportunidades

### Con Batch Flip:
- Sube el archivo → análisis completo en **minutos**
- Cada producto tiene: profit, ROI, velocidad de venta, riesgo, recomendación
- Filtros para mostrar solo los rentables
- Exporta los ganadores a CSV para hacer la orden al proveedor

---

## ¿Cómo funciona?

### Flujo del usuario:

```
1. CONECTAR
   El seller conecta su cuenta de Amazon Seller Central
   via OAuth (SP-API). Esto nos permite verificar si puede
   vender cada producto específico (gating, restricciones).

2. SUBIR
   Sube el archivo del proveedor (CSV, XLSX, XLS).
   El sistema auto-detecta las columnas de ID y costo.
   Soporta: ASIN, UPC, EAN, ISBN, keywords.

3. CONFIGURAR
   Selecciona: marketplace (US, UK, DE...), tipo de
   fulfillment (FBA/MFN), costos de prep y shipping.

4. ANALIZAR
   El sistema procesa en batch:
   ┌─────────────────────────────────────────┐
   │ Fase 1: Resolver IDs                     │
   │   UPC/EAN → ASIN via Keepa              │
   │                                           │
   │ Fase 2: Obtener datos de Amazon           │
   │   Precios, Buy Box, fees, BSR, sellers   │
   │   via Keepa API (batch de 20 ASINs)      │
   │                                           │
   │ Fase 3: Verificar elegibilidad            │
   │   ¿Puedo venderlo? ¿FBA eligible?        │
   │   via SP-API (con cuenta del seller)      │
   │                                           │
   │ Fase 4: Analizar cada producto            │
   │   Profit, ROI, velocity, risk, score     │
   │   via motores de análisis (de FlipIQ)     │
   └─────────────────────────────────────────┘

5. REVISAR
   Dashboard con resultados filtrados y ordenados.
   Cada producto muestra:
   - ✅/❌ ¿Puedo venderlo?
   - 💰 Profit y ROI esperados
   - 📊 Velocidad de venta y riesgo
   - 🏷️ Datos del producto (título, marca, BSR, reviews)
   - 📦 Buy Box: quién lo tiene, % Amazon

6. EXPORTAR
   Descarga CSV/Excel con los productos seleccionados
   para hacer la orden al proveedor.
```

---

## Fuentes de datos

### Keepa API (disponible ahora)
Keepa es un servicio que recopila datos históricos de Amazon. Nos proporciona:

| Dato | Ejemplo | Para qué sirve |
|------|---------|----------------|
| **Precio Buy Box** | $258.37 | Estimar a qué precio venderemos |
| **Fees reales** | Referral 10.71%, FBA $4.47 | Calcular profit exacto |
| **Monthly Sold** | "300+ bought in past month" | Saber qué tan rápido se vende |
| **Sales Rank (BSR)** | #353 en Electronics | Ranking de ventas |
| **Historial de precios** | 30/90/180 días | Tendencias y estabilidad |
| **Buy Box Stats** | Amazon 12.3%, Seller X 16.5% | Quién controla el Buy Box |
| **Sellers** | 6 sellers (0 FBA, 1 FBM) | Competencia |
| **Rating/Reviews** | 4.6★ (46,746 reviews) | Calidad del listing |
| **Dimensiones/Peso** | 45g, 0.31"×0.24"×0.22" | Estimar fees de envío |
| **Hazmat** | Lithium Ion Battery info | Restricciones de envío |
| **UPC/EAN** | 195949704529 | Resolver códigos a ASIN |
| **Out of Stock %** | Amazon OOS 30 de 30 días | Oportunidad cuando Amazon no compite |

### Amazon SP-API (cuando se apruebe la developer app)
Datos privados **por cuenta de seller**:

| Dato | Para qué sirve |
|------|----------------|
| **Listing Restrictions** | ¿PUEDO vender este ASIN? (gating, marca, categoría) |
| **FBA Eligibility** | ¿Puedo enviarlo a FBA? |
| **Shipment Restrictions** | Restricciones específicas de envío |
| **Seller SKU Lookup** | Buscar por SKU propio |

---

## Motores de análisis (heredados de FlipIQ)

El corazón del sistema viene de FlipIQ, una app de análisis para resellers que ya opera en producción. Estos motores procesan los datos crudos y producen inteligencia accionable:

### Profit Engine
Calcula ganancia neta real considerando todos los costos:
```
Profit = Precio venta
       - Fees Amazon (referral % + FBA fee)
       - Shipping al warehouse
       - Prep cost
       - Promo cost
       - Return reserve (5% hasta $50, 3% hasta $200, 2% hasta $500, 1% arriba)
       - Costo del producto
```
Retorna: **profit, ROI, margin, marketplace fees, return reserve**

### Velocity Engine
Estima qué tan rápido se vende con fórmula logarítmica:
- Usa `monthlySold` de Keepa (dato real de Amazon) como fuente primaria
- Fallback a `salesRankDrops30` (cada drop ≈ 1 venta)
- Categoriza: very_fast (≥1/día), healthy (≥0.5), moderate (≥0.1), slow (<0.1)
- Estima días para vender: "~2d", "~7-14d", etc.

### Risk Engine
Score de riesgo 0-100 (100 = bajo riesgo) basado en:
- Volatilidad de precios (CV)
- Dispersión de precios (IQR/mediana)
- Proporción de outliers
- Tamaño de la muestra

### Competition Engine
Analiza concentración del mercado con índice HHI:
- healthy (HHI ≤ 0.15): muchos sellers, mercado sano
- moderate (0.15-0.25): algo concentrado
- concentrated (> 0.25): dominado por pocos sellers

### Comp Cleaner
Limpia y normaliza datos de comparables (comps):
- Filtra outliers con IQR Tukey
- Filtra por condición (new/used/open box)
- Normaliza precios (price + shipping ÷ lot_size)
- Filtra danger patterns (box_only, for_parts, etc.)

### Title Risk Detector
Detecta 33 danger patterns en títulos:
- box_only, empty_box, for_parts, broken, icloud_locked...
- Cada uno con peso de riesgo (0.15 - 1.0)

---

## Ventajas competitivas vs Price Checker 2

### Lo que PC2 hace y nosotros también:
- ✅ Batch processing de listas wholesale
- ✅ Cálculo de profit/ROI con fees reales
- ✅ Multi-marketplace Amazon (10 mercados)
- ✅ Detección de multipacks
- ✅ Buy Box analysis
- ✅ Sales rank y estimación de ventas
- ✅ Historial de precios (30/90/180 días)
- ✅ Soporte CSV/XLSX
- ✅ Custom filters
- ✅ Export a CSV/Excel

### Lo que nosotros tenemos y PC2 NO:

| Ventaja | Descripción |
|---------|-------------|
| **Velocity Score** | Score 0-100 de velocidad de venta con estimación de días |
| **Risk Score** | Evaluación de riesgo de mercado 0-100 |
| **Competition Analysis** | Índice HHI de concentración + seller dominance |
| **Monthly Sold real** | Dato directo de Amazon "X+ bought in past month" (Keepa) — PC2 solo estima |
| **Buy Box Stats por seller** | % exacto del Buy Box por seller, no solo si Amazon lo tiene |
| **Out of Stock tracking** | % de tiempo que Amazon estuvo OOS (oportunidad) |
| **API-first** | Integrable con cualquier frontend, app móvil, o automatización |
| **Cloud-based** | No requiere instalar software desktop |
| **Recommendation engine** | Decisión automatizada: buy / buy_small / watch / pass |
| **AI Explanation** | Explicación en lenguaje natural de por qué comprar o no (futuro) |
| **eBay cross-analysis** | Comparar oportunidad Amazon vs eBay (futuro, de FlipIQ) |

### Lo que PC2 tiene y nosotros tendremos con SP-API:
- ⏳ Listing restrictions (gating check por seller)
- ⏳ FBA eligibility check
- ⏳ Shipment restrictions
- ⏳ Amazon Browser (storefront scanning)

---

## Modelo de negocio

### Pricing (propuesto)

| Plan | Precio | Límite | Target |
|------|--------|--------|--------|
| **Free** | $0 | 1 análisis de 500 items | Prueba |
| **Starter** | $49/mes | 50,000 items/mes | Sellers pequeños |
| **Pro** | $99/mes | 200,000 items/mes | Sellers medianos |
| **Enterprise** | $199/mes | Ilimitado + API access | Sellers grandes |

**Referencia:** PC2 cobra **$148/mes** por acceso ilimitado. Nuestro plan Pro a $99 es más barato y ofrece más funcionalidades (scores, AI, cloud).

### Revenue adicional (futuro):
- **API access** para integrar con herramientas del seller
- **Watchlists** con price alerts (de FlipIQ)
- **Market Intelligence** con AI (de FlipIQ, premium)

---

## Stack técnico

| Capa | Tecnología |
|------|-----------|
| **Backend** | FastAPI (Python 3.11, 100% async) |
| **Base de datos** | PostgreSQL + SQLAlchemy async |
| **Cache/Queue** | Redis |
| **Background jobs** | ARQ (async-native) |
| **Data: Amazon** | Keepa API + Amazon SP-API (futuro) |
| **Data: UPC** | upcitemdb.com + Open Facts APIs |
| **Engines** | 6 motores de FlipIQ (profit, velocity, risk, competition, comp_cleaner, title_risk) |
| **Auth** | OAuth (SP-API) + JWT (usuarios) |
| **Frontend** | Por definir (web app) |
| **Deploy** | Por definir (AWS/Railway/Fly.io) |

---

## Roadmap

### Fase 1 — MVP (ahora) ✅
- [x] FastAPI + PostgreSQL + Redis
- [x] Upload y parsing de CSV/XLSX con auto-detección
- [x] Keepa API integration (batch de ASINs, multi-marketplace)
- [x] Profit/ROI calculation con fees reales de Keepa
- [x] Velocity scoring (monthlySold + salesRankDrops)
- [x] Job queue con status y progreso
- [x] Export a CSV
- [x] Single-item analysis endpoint
- [x] Data provider abstraction (Keepa → SP-API swap)

### Fase 2 — Paridad con PC2
- [ ] SP-API integration (OAuth multi-tenant, listing restrictions)
- [ ] Custom Filters (12+ operadores sobre cualquier campo)
- [ ] Currency conversion con tasas en vivo
- [ ] Cost Profiles avanzados (FBA/MFN/EFN, VAT, prep, shipping)
- [ ] Export a Excel con highlights y fórmulas
- [ ] Major Brands filtering
- [ ] Historical data (promedios 30/90/180 días)
- [ ] Web dashboard

### Fase 3 — Superar a PC2
- [ ] Risk Score por producto
- [ ] Competition Analysis (HHI, seller dominance)
- [ ] Trend Analysis (demanda rising/stable/declining)
- [ ] Confidence Score
- [ ] Opportunity Score combinado
- [ ] Recommendation engine (buy/buy_small/watch/pass)
- [ ] AI Explanation por producto (Gemini/GPT)

### Fase 4 — Diferenciación
- [ ] Watchlists con price tracking y alerts
- [ ] Market Intelligence con búsqueda web + LLM
- [ ] eBay cross-analysis
- [ ] Mobile app
- [ ] Webhooks para notificaciones
- [ ] API keys para integraciones de terceros
- [ ] Amazon Browser (storefront scanning)

---

## Métricas de éxito

| Métrica | Target |
|---------|--------|
| Throughput | ≥ 5,000 items/hora (PC2: 18K/hora con SP-API directa) |
| Precisión de fees | ≥ 99% (usando fees reales de Keepa) |
| Latencia single-item | < 3 segundos |
| Uptime | 99.9% |
| Primer usuario pagado | 30 días post-launch |
