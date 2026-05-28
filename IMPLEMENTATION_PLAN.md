# Batch Flip — Plan de Implementación Detallado

## Estado Actual (lo que ya existe)

### Infraestructura ✅
- FastAPI app con lifespan, CORS, health check
- PostgreSQL + Redis (docker-compose)
- SQLAlchemy async + Alembic migrations
- Config con Pydantic Settings (.env)

### Modelos ✅
- `Job` — status, marketplace, file info, counts, cost profile inline
- `JobItem` — input data, Amazon data, profit, scores, status

### API Endpoints ✅
- `POST /api/v1/jobs` — Crear job
- `POST /api/v1/jobs/{id}/upload` — Upload CSV/XLSX
- `POST /api/v1/jobs/{id}/start` — Iniciar procesamiento
- `GET /api/v1/jobs/{id}` — Status
- `GET /api/v1/jobs/{id}/results` — Resultados paginados
- `GET /api/v1/jobs/{id}/results/stats` — Resumen
- `GET /api/v1/jobs/{id}/export` — CSV
- `DELETE /api/v1/jobs/{id}` — Eliminar
- `POST /api/v1/analyze` — Single-item

### Engines (de FlipIQ) ✅
- profit_engine, velocity_engine, risk_engine
- competition_engine, comp_cleaner, title_risk
- marketplace/base.py (dataclasses), core/fees.py

### Providers ✅
- `KeepaProvider` — batch ASINs, resolve UPC→ASIN, multi-domain
- `SPAPIProvider` — stub (por implementar)
- `DataProvider` ABC con `ProductData` dataclass

### File Parser ✅
- CSV/XLSX/TSV parsing
- Auto-detección de columnas (ID, cost)
- Auto-detección de tipo de ID (ASIN, UPC, EAN, ISBN)

### Credenciales Verificadas ✅
- **Keepa API** — funcionando (monthlySold, fees, BSR, Buy Box stats)
- **SP-API** — funcionando:
  - ✅ Marketplace Participations (US, MX, CA, BR)
  - ✅ Catalog Items (título, marca, dimensiones, UPC/EAN)
  - ✅ Fees Estimate (referral + FBA exactos)
  - ✅ Competitive Pricing (offers, trade-in, BSR)
  - ✅ Listing Restrictions (gating, brand approval)
  - ❌ FBA Eligibility (requiere rol Amazon Fulfillment aprobado)
- **Seller**: AMONCA Tecnology (A2TSJV48FRRFVQ)

---

## Fases de Implementación

---

### FASE 1: SP-API Provider Real
**Objetivo:** Implementar SPAPIProvider con los 5 endpoints que ya funcionan.
**Prioridad:** CRÍTICA — es el diferenciador principal.

#### 1.1 SP-API Auth Client
**Archivo:** `app/services/providers/spapi_auth.py`

```
- Clase SPAPIAuth que maneja OAuth token lifecycle
- get_access_token() → cachea token en memoria (expira en 3600s)
- Auto-refresh cuando expira
- Para MVP: usa refresh_token del .env (tu cuenta)
- Para SaaS: cada seller tendrá su propio refresh_token en DB
```

**Campos config.py a usar:**
- `sp_api_client_id`
- `sp_api_client_secret`
- `sp_api_refresh_token`

#### 1.2 SP-API Provider
**Archivo:** `app/services/providers/spapi.py` (reemplazar stub)

**Métodos a implementar:**

```python
class SPAPIProvider(DataProvider):
    # Heredados de DataProvider ABC
    async def get_products_batch(asins, domain) -> dict[str, ProductData]
    async def resolve_code_to_asin(code, domain) -> str | None
    async def search_by_keyword(keyword, domain, limit) -> list[str]
    
    # Específicos de SP-API
    async def check_listing_restrictions(asin, seller_id, marketplace_id, condition) -> RestrictionResult
    async def check_listing_restrictions_batch(asins, seller_id, marketplace_id) -> dict[str, RestrictionResult]
    async def get_fees_estimate(asin, price, marketplace_id, is_fba) -> FeesResult
    async def get_fees_estimate_batch(items: list[FeeRequest]) -> dict[str, FeesResult]
    async def get_competitive_pricing(asins, marketplace_id) -> dict[str, PricingResult]
    async def get_catalog_item(asin, marketplace_id) -> CatalogItem
```

**Rate limits SP-API a respetar:**
- Catalog Items: 2 requests/sec
- Fees Estimate: 1 request/sec  
- Listing Restrictions: 5 requests/sec
- Competitive Pricing: 2 requests/sec (10 ASINs por request)

**Dataclasses nuevas en `providers/base.py`:**
```python
@dataclass
class RestrictionResult:
    can_sell: bool
    reason_code: str | None  # NOT_ELIGIBLE, APPROVAL_REQUIRED, None
    message: str | None
    
@dataclass  
class FeesResult:
    total_fees: float
    referral_fee: float
    fba_fee: float
    variable_closing_fee: float
    per_item_fee: float

@dataclass
class PricingResult:
    buy_box_price: float | None
    number_of_offers: dict[str, int]  # {"New": 2, "Used": 1}
    trade_in_value: float | None
    sales_rank: int | None
```

#### 1.3 Hybrid Provider (Keepa + SP-API combinados)
**Archivo:** `app/services/providers/hybrid.py`

```
Combina lo mejor de ambos:
- Keepa: monthlySold, salesRankDrops, historial Buy Box, Buy Box stats por seller, 
         outOfStock%, rating, reviews, historial de precios completo
- SP-API: listing restrictions (can_sell), fees EXACTOS, competitive pricing en tiempo real,
          catalog data oficial, FBA eligibility (cuando se apruebe)

Flujo:
1. Keepa batch (datos históricos + velocity + Buy Box stats)
2. SP-API listing restrictions batch (can_sell per seller)
3. SP-API fees estimate (fees exactos para items que sí se pueden vender)
4. Merge: ProductData con todos los campos de ambas fuentes
```

**Lógica de merge:**
```python
# Datos de Keepa (primario para históricos)
product.monthly_sold = keepa.monthly_sold
product.sales_rank_drops_30 = keepa.sales_rank_drops_30
product.buy_box_stats = keepa.buy_box_stats
product.rating = keepa.rating
product.review_count = keepa.review_count
product.out_of_stock_pct_90 = keepa.out_of_stock_pct_90

# Datos de SP-API (primario para datos en tiempo real)
product.can_sell = spapi.restriction.can_sell
product.restriction_reason = spapi.restriction.message
product.referral_fee_pct = spapi.fees.referral_fee / price  # más preciso
product.fba_fulfillment_fee = spapi.fees.fba_fee  # más preciso
product.buy_box_price = spapi.pricing.buy_box_price  # más actual

# Fallback: si SP-API falla, usar Keepa
product.referral_fee_pct = spapi.fees?.referral ?? keepa.referral_fee_pct
product.fba_fulfillment_fee = spapi.fees?.fba_fee ?? keepa.fba_fulfillment_fee
```

---

### FASE 2: Modelos y Schema Expandidos
**Objetivo:** Agregar campos para SP-API data, listing restrictions, y seller connections.

#### 2.1 Modelo SellerConnection
**Archivo:** `app/models/seller.py`

```python
class SellerConnection:
    id: UUID
    user_id: UUID                    # nuestro usuario
    seller_id: str                   # Amazon seller ID (ej: A2TSJV48FRRFVQ)
    store_name: str                  # AMONCA Tecnology
    marketplace_ids: list[str]       # ["ATVPDKIKX0DER", "A1AM78C64UM0Y8"]
    refresh_token_encrypted: str     # Token encriptado con Fernet
    is_active: bool
    connected_at: datetime
    last_used_at: datetime | None
```

**Para MVP:** Usar el refresh_token del .env (una sola cuenta).
**Para SaaS:** OAuth flow donde cada seller conecta su cuenta.

#### 2.2 Campos nuevos en JobItem
**Archivo:** `app/models/job_item.py` — agregar:

```python
# Listing Restrictions (SP-API)
can_sell: bool | None              # ¿Este seller puede vender este ASIN?
restriction_reason: str | None     # "NOT_ELIGIBLE", "APPROVAL_REQUIRED", etc.
restriction_message: str | None    # Mensaje completo de Amazon

# Fees exactos (SP-API)
sp_api_total_fees: float | None    # Fees totales de SP-API
sp_api_referral_fee: float | None  # Referral fee exacto
sp_api_fba_fee: float | None       # FBA fee exacto

# Datos adicionales
monthly_sold: int | None           # Dato real "X+ bought in past month"
sales_rank_drops_30: int | None    # Drops de rank en 30 días
rating: float | None               # 1.0 - 5.0
review_count: int | None           # Número de reviews
buy_box_is_amazon: bool            # ¿Amazon tiene el Buy Box?
out_of_stock_pct_90: int | None    # % tiempo OOS (Amazon)
trade_in_value: float | None       # Valor de trade-in
offer_count_new: int               # Ofertas New
offer_count_used: int              # Ofertas Used
```

#### 2.3 Campos nuevos en Job
**Archivo:** `app/models/job.py` — agregar:

```python
seller_connection_id: UUID | None  # FK a SellerConnection
check_restrictions: bool           # ¿Verificar si puede vender? (requiere SP-API)
```

#### 2.4 Migración Alembic
- Generar migración con los nuevos campos
- `alembic revision --autogenerate -m "add_spapi_fields_and_seller_connection"`

---

### FASE 3: Batch Processor Mejorado
**Objetivo:** Pipeline de 6 fases que combina Keepa + SP-API.

**Archivo:** `app/services/batch_processor.py` — refactorizar

```
Pipeline de 6 Fases:

FASE 1: ID Resolution (existente)
  - ASIN → directo
  - UPC/EAN → Keepa code lookup (con cache Redis 24h)
  - ISBN/Keyword → Keepa search

FASE 2: Keepa Batch Lookup (existente, mejorado)
  - Chunks de 20 ASINs
  - Extraer: monthlySold, BSR, Buy Box stats, rating, reviews, OOS%
  - Extraer: fees de Keepa como fallback
  - Cache Redis 6h por ASIN

FASE 3: SP-API Listing Restrictions (NUEVO)
  - Solo si job.check_restrictions = True y hay seller_connection
  - Batch: 5 requests/sec, 1 ASIN por request
  - Para cada ASIN: check_listing_restrictions()
  - Resultado: can_sell (bool), reason_code, message
  - Items con can_sell=False → status="restricted", skip profit calc
  - Cache Redis 24h por (seller_id, asin, marketplace)

FASE 4: SP-API Fees Estimate (NUEVO)
  - Solo para items que can_sell=True (o sin SP-API)
  - 1 request/sec, 1 ASIN por request
  - Fees exactos: referral + FBA + variable closing
  - Override fees de Keepa con fees de SP-API (más precisos)
  - Cache Redis 12h por (asin, marketplace, price_bucket)

FASE 5: Analysis (existente, mejorado)
  - Profit calculation con fees de SP-API (o Keepa fallback)
  - Velocity: monthlySold → salesRankDrops30 → BSR estimate
  - Risk score (si hay suficientes datos de ofertas)
  - Competition: seller count, Amazon is seller, Buy Box stats

FASE 6: Persist (existente)
  - Bulk update JobItems
  - Actualizar Job counts (matched, profitable, restricted, errors)
  - Calcular processing_speed
```

**Nuevo status para JobItem:**
```
pending → matched (datos encontrados, análisis completo)
        → restricted (can_sell=False, no se puede vender)
        → not_found (ASIN no encontrado en Keepa ni SP-API)
        → error (error en el procesamiento)
```

**Nuevo campo en Job:**
```
restricted_items: int  # Items que no se pueden vender
```

**Progress phases:**
```
resolving_ids → fetching_keepa → checking_restrictions → 
fetching_fees → analyzing → persisting
```

---

### FASE 4: Auth y Multi-Tenant
**Objetivo:** Usuarios pueden registrarse y conectar sus cuentas de Amazon.

#### 4.1 Auth System
**Archivo:** `app/api/v1/auth.py`

```
POST /api/v1/auth/register     → email + password → JWT
POST /api/v1/auth/login        → email + password → JWT
POST /api/v1/auth/refresh      → refresh token → new JWT
GET  /api/v1/auth/me           → user profile
```

**Modelo User:**
```python
class User:
    id: UUID
    email: str (unique)
    password_hash: str
    plan: str  # free, starter, pro, enterprise
    scans_used_today: int
    created_at: datetime
```

#### 4.2 Amazon OAuth Flow
**Archivos:** `app/api/v1/amazon_connect.py`, `app/services/amazon_oauth.py`

```
Flujo:
1. GET /api/v1/amazon/connect
   → Redirect a Amazon Seller Central OAuth
   → URL: https://sellercentral.amazon.com/apps/authorize/consent?application_id={app_id}&state={state}

2. GET /api/v1/amazon/callback?code={auth_code}&state={state}
   → Exchange auth_code por refresh_token (POST https://api.amazon.com/auth/o2/token)
   → Guardar refresh_token encriptado en SellerConnection
   → Llamar getMarketplaceParticipations para obtener seller_id y marketplaces
   → Retornar al frontend

3. GET /api/v1/amazon/connections
   → Listar conexiones del usuario

4. DELETE /api/v1/amazon/connections/{id}
   → Desconectar cuenta de Amazon
```

#### 4.3 Rate Limiting por Plan
**Archivo:** `app/api/v1/deps.py` — middleware

```
| Plan       | Jobs/día | Items/job | Items/mes |
|------------|----------|-----------|-----------|
| free       | 1        | 500       | 500       |
| starter    | 10       | 10,000    | 50,000    |
| pro        | 50       | 50,000    | 200,000   |
| enterprise | unlimited| unlimited | unlimited |
```

---

### FASE 5: Schemas y Export Mejorados
**Objetivo:** Output completo comparable a PC2.

#### 5.1 JobItem Response expandido
```python
class JobItemResponse:
    # Input
    input_id, input_id_type, cost_price
    
    # Amazon básico
    asin, title, brand, category, image_url
    parent_asin, product_type, color, size
    
    # ¿Puedo venderlo?
    can_sell: bool | None
    restriction_reason: str | None
    
    # Pricing
    buy_box_price, list_price, estimated_sale_price
    
    # Fees (SP-API exactos o Keepa fallback)
    referral_fee, fba_fee, total_fees
    
    # Profit
    profit, roi_pct, margin_pct
    return_reserve, shipping_cost, prep_cost
    
    # Velocity
    velocity_score, estimated_days_to_sell
    monthly_sold, sales_rank_drops_30, sales_per_day
    
    # Competencia
    sales_rank, seller_count, offer_count_new, offer_count_used
    amazon_is_seller, buy_box_is_amazon
    
    # Reviews
    rating, review_count
    
    # Flags
    is_hazmat, is_multipack, multipack_qty
    out_of_stock_pct_90
    trade_in_value
    
    # Links
    amazon_url, keepa_url, camel_url
    
    # Status
    status  # matched, restricted, not_found, error
```

#### 5.2 Export Excel con Highlights
**Archivo:** `app/services/export_service.py` — mejorar

```
- Formato XLSX con openpyxl
- Header azul para columnas calculadas
- Header amarillo para columnas clave
- Filas verdes: profitable (ROI > 0%)
- Filas rojas: restricted (can_sell = False)
- Filas amarillas: ROI negativo pero vendible
- Fórmulas en celdas de profit/ROI (no solo valores)
- Sheet "Summary" con stats del job
- Sheet "Profitable" solo con items rentables
- Sheet "All Results" con todo
```

#### 5.3 Custom Filters
**Archivo:** `app/services/filter_engine.py`

```python
# Estructura de filtro
{
    "field": "roi_pct",
    "operator": "greater_than",
    "value": 30
}

# Operadores soportados
OPERATORS = {
    "equal", "not_equal",
    "greater_than", "greater_or_equal",
    "lower_than", "lower_or_equal",
    "contains", "not_contains",
    "is_true", "is_false",
    "is_blank", "is_not_blank",
}

# Aplicar en GET /results como query params o JSON body
# Aplicar durante export para filtrar output
```

---

### FASE 6: Engines Avanzados (de FlipIQ)
**Objetivo:** Agregar los engines que nos diferencian de PC2.

#### 6.1 Copiar engines adicionales de FlipIQ
```
FlipIQ/app/services/engines/trend_engine.py      → Trend analysis
FlipIQ/app/services/engines/confidence_engine.py  → Confidence score
FlipIQ/app/services/engines/seller_premium.py     → Seller premium detection
FlipIQ/app/services/engines/listing_strategy.py   → Listing strategy
FlipIQ/app/services/engines/execution_engine.py   → Execution feasibility
FlipIQ/app/services/engines/ai_explanation.py     → AI explanation (Gemini/GPT)
FlipIQ/app/core/llm.py                           → LLM client
```

#### 6.2 Opportunity Score
**Archivo:** `app/services/engines/opportunity_engine.py`

```python
# Fórmula de FlipIQ adaptada para batch:
opportunity = (
    0.30 * profit_score +      # 100 si ROI>=50%, 80 si >=30%, 60 si >=15%
    0.25 * velocity_score +    # 0-100 del velocity engine
    0.20 * risk_score +        # 0-100 del risk engine
    0.15 * confidence_score +  # 0-100 basado en datos disponibles
    0.10 * market_health       # competition + trend
)
```

#### 6.3 Recommendation Engine
```python
# Decisión automatizada:
if opportunity >= 60 and profit > 0 and can_sell:
    recommendation = "buy"
elif opportunity >= 45 and profit > 0 and roi > 20:
    recommendation = "buy_small"
elif opportunity >= 35 or roi > 10:
    recommendation = "watch"
else:
    recommendation = "pass"

# Si can_sell = False:
recommendation = "restricted"
```

#### 6.4 Nuevos campos en JobItem
```python
opportunity_score: int | None      # 0-100
confidence_score: int | None       # 0-100
recommendation: str | None         # buy, buy_small, watch, pass, restricted
ai_explanation: str | None         # Texto de AI (premium)
```

---

### FASE 7: Frontend Web
**Objetivo:** Dashboard web donde el seller interactúa con Batch Flip.

#### 7.1 Stack
```
Next.js 14+ (App Router)
Tailwind CSS + shadcn/ui
React Query para data fetching
Vercel para deploy
```

#### 7.2 Páginas

```
/                          → Landing page
/login                     → Login
/register                  → Registro
/dashboard                 → Dashboard principal
/dashboard/connect         → Conectar cuenta Amazon (OAuth)
/dashboard/jobs            → Lista de jobs
/dashboard/jobs/new        → Crear nuevo job (upload + config)
/dashboard/jobs/[id]       → Detalle del job (progress, results)
/dashboard/jobs/[id]/results → Tabla de resultados con filtros
/dashboard/analyze         → Single-item analysis
/dashboard/settings        → Perfil, plan, billing
```

#### 7.3 Componentes clave
```
- FileUploader: drag & drop CSV/XLSX con preview
- JobProgress: barra de progreso con fases
- ResultsTable: tabla con sort, filter, pagination
  - Columnas toggleables
  - Color coding (verde/rojo/amarillo)
  - Inline links a Amazon, Keepa, CamelCamelCamel
- StatsCards: summary cards (profitable, restricted, avg ROI)
- ProductCard: detalle de un producto con todos los datos
- FilterBuilder: UI para construir custom filters
- ExportButton: download CSV/XLSX
```

---

### FASE 8: Billing y Planes
**Objetivo:** Monetización con Stripe.

```
POST /api/v1/billing/checkout    → Crear Stripe checkout session
POST /api/v1/billing/webhook     → Stripe webhook (payment confirmed)
GET  /api/v1/billing/portal      → Stripe customer portal (manage plan)
GET  /api/v1/billing/usage       → Items usados este mes
```

**Planes:**
```
Free:       $0/mes   — 500 items, 1 job, sin SP-API restrictions check
Starter:    $49/mes  — 50K items, 10 jobs, SP-API restrictions
Pro:        $99/mes  — 200K items, 50 jobs, SP-API + AI explanations
Enterprise: $199/mes — Unlimited, API keys, priority support
```

---

### FASE 9: Deploy y DevOps
**Objetivo:** Producción con CI/CD.

```
Backend:  Railway o Fly.io (FastAPI + PostgreSQL + Redis)
Frontend: Vercel (Next.js)
Storage:  S3 para archivos de upload/export
CI/CD:    GitHub Actions
Monitoring: Sentry + basic logging
```

---

## Orden de Implementación

```
SEMANA 1-2: Fase 1 (SP-API Provider) + Fase 2 (Schema expandido)
  → SP-API funcional, listing restrictions, fees exactos
  → Batch processor con 6 fases (Keepa + SP-API)

SEMANA 3: Fase 3 (Batch Processor mejorado)
  → Pipeline híbrido completo
  → Probar con lista real de 100-1000 productos

SEMANA 4: Fase 5 (Export mejorado + Custom Filters)
  → Excel con highlights
  → Filtros en resultados

SEMANA 5-6: Fase 4 (Auth + Multi-tenant)
  → Registro/login
  → OAuth flow para conectar Amazon
  → Rate limiting por plan

SEMANA 7-8: Fase 6 (Engines avanzados)
  → Opportunity score, recommendation, confidence
  → AI explanations (premium)

SEMANA 9-12: Fase 7 (Frontend)
  → Next.js dashboard
  → Upload, progress, results, export

SEMANA 13: Fase 8 (Billing)
  → Stripe integration
  → Plans enforcement

SEMANA 14: Fase 9 (Deploy)
  → Producción
  → Beta launch
```

---

## Archivos por Crear/Modificar por Fase

### Fase 1
```
CREAR:
  app/services/providers/spapi_auth.py    — OAuth token management
  app/services/providers/spapi.py         — SP-API Provider (reemplazar stub)
  app/services/providers/hybrid.py        — Combina Keepa + SP-API

MODIFICAR:
  app/services/providers/base.py          — Agregar RestrictionResult, FeesResult, PricingResult
  app/config.py                           — Ya tiene sp_api_* fields ✅
```

### Fase 2
```
CREAR:
  app/models/seller.py                    — SellerConnection model
  alembic/versions/xxx_add_spapi_fields.py — Migración

MODIFICAR:
  app/models/job_item.py                  — Campos SP-API
  app/models/job.py                       — seller_connection_id, check_restrictions
  app/models/__init__.py                  — Importar SellerConnection
  app/schemas/job.py                      — Expandir responses
```

### Fase 3
```
MODIFICAR:
  app/services/batch_processor.py         — 6 fases con SP-API
```

### Fase 4
```
CREAR:
  app/models/user.py                      — User model
  app/api/v1/auth.py                      — Register, login, refresh
  app/api/v1/amazon_connect.py            — OAuth flow Amazon
  app/services/amazon_oauth.py            — OAuth logic
  app/core/security.py                    — JWT, password hashing, encryption

MODIFICAR:
  app/api/v1/deps.py                      — get_current_user, rate_limit
  app/api/v1/router.py                    — Incluir nuevos routers
  app/api/v1/jobs.py                      — Require auth, link seller_connection
```

### Fase 5
```
CREAR:
  app/services/filter_engine.py           — Custom filters

MODIFICAR:
  app/services/export_service.py          — Excel con highlights
  app/schemas/job.py                      — Expandir JobItemResponse
  app/api/v1/jobs.py                      — Filtros en GET results
```

### Fase 6
```
COPIAR de FlipIQ:
  app/services/engines/trend_engine.py
  app/services/engines/confidence_engine.py
  app/services/engines/execution_engine.py
  app/services/engines/ai_explanation.py
  app/services/engines/listing_strategy.py
  app/services/engines/seller_premium.py

CREAR:
  app/services/engines/opportunity_engine.py
  app/services/engines/recommendation_engine.py

COPIAR + ADAPTAR:
  app/core/llm.py                         — Gemini + OpenAI client
```

---

## Métricas de Throughput Estimadas

### Con Keepa solo (actual)
```
ID Resolution: ~10 UPCs/sec (semaphore 10)
Product Lookup: 20 ASINs/request × 4 req/min = 80 ASINs/min = 4,800/hora
Analysis: instantáneo (CPU)
TOTAL: ~4,800 items/hora (limitado por Keepa tokens)
```

### Con Keepa + SP-API (Fase 3)
```
Keepa Lookup: 4,800 ASINs/hora (en paralelo con SP-API)
SP-API Restrictions: 5 req/sec = 18,000/hora
SP-API Fees: 1 req/sec = 3,600/hora (solo items vendibles)
SP-API Pricing: 2 req/sec × 10 ASINs = 72,000/hora

Bottleneck: Keepa (4,800/hora) o SP-API Fees (3,600/hora)
Optimización: SP-API fees solo para items can_sell=True (~30-50% del total)
ESTIMADO: ~3,000-5,000 items/hora procesamiento completo
```

### PC2 comparación
```
PC2: 18,000 items/hora (SP-API directa, sin Keepa overhead)
Nosotros: 3,000-5,000 items/hora (más datos por item)
Ventaja: monthlySold, Buy Box stats, velocity, risk, recommendation
```

---

## Resumen de Features por Fase

| Feature | Fase | PC2 tiene? | Nosotros? |
|---------|------|-----------|-----------|
| Batch processing | ✅ Ya existe | ✅ | ✅ |
| File upload CSV/XLSX | ✅ Ya existe | ✅ | ✅ |
| Auto-detect columns | ✅ Ya existe | ✅ | ✅ |
| UPC/EAN/ASIN lookup | ✅ Ya existe | ✅ | ✅ |
| Profit/ROI calculation | ✅ Ya existe | ✅ | ✅ |
| Keepa fees (fallback) | ✅ Ya existe | ❌ | ✅ |
| Velocity score | ✅ Ya existe | ❌ | ✅ |
| **SP-API listing restrictions** | Fase 1 | ✅ | ⏳ |
| **SP-API exact fees** | Fase 1 | ✅ | ⏳ |
| **SP-API competitive pricing** | Fase 1 | ✅ | ⏳ |
| **Hybrid Keepa+SP-API** | Fase 1 | ❌ | ⏳ |
| **Monthly sold (real Amazon data)** | Fase 1 | ❌ | ⏳ |
| **Buy Box stats por seller** | Fase 1 | ❌ | ⏳ |
| **6-phase batch pipeline** | Fase 3 | ❌ | ⏳ |
| Excel export con highlights | Fase 5 | ✅ | ⏳ |
| Custom filters | Fase 5 | ✅ | ⏳ |
| Auth + multi-tenant | Fase 4 | ✅ | ⏳ |
| Amazon OAuth (connect account) | Fase 4 | ✅ | ⏳ |
| Risk score | Fase 6 | ❌ | ⏳ |
| Competition analysis | Fase 6 | ❌ | ⏳ |
| Opportunity score | Fase 6 | ❌ | ⏳ |
| AI recommendation (buy/pass) | Fase 6 | ❌ | ⏳ |
| AI explanation (Gemini/GPT) | Fase 6 | ❌ | ⏳ |
| Web dashboard | Fase 7 | ✅ (desktop) | ⏳ |
| Stripe billing | Fase 8 | ✅ | ⏳ |
| Multi-marketplace (10 markets) | Fase 1 | ✅ | ⏳ |
| Currency conversion | Fase 5 | ✅ | ⏳ |
| Major brands filtering | Fase 5 | ✅ | ⏳ |
| Historical data (30/90/180d) | Fase 1 | ✅ | ⏳ |
