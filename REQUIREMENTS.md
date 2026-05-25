# Requisitos: API de Análisis Batch para Amazon

> **Objetivo:** Crear una API FastAPI que compita con Price Checker 2 (PC2) de Daily Source Tools, reutilizando componentes del motor de análisis de FlipIQ.

---

## 1. Funcionalidades Requeridas vs Fuente

### Leyenda
- **FlipIQ** = Se puede reutilizar del proyecto existente
- **Nuevo** = Hay que construirlo desde cero
- **Adaptar** = Existe en FlipIQ pero necesita modificaciones

| # | Feature de PC2 | Prioridad | Fuente | Detalle |
|---|----------------|-----------|--------|---------|
| 1 | Procesamiento batch (hasta 500K items) | **Crítica** | Nuevo | PC2 procesa 18K/hora. Necesitamos orquestador batch async |
| 2 | Upload de archivos (CSV, XLS, XLSX) | **Crítica** | Nuevo | Parsing de archivos con auto-detección de columnas |
| 3 | Lookup por múltiples IDs (UPC, ASIN, EAN, ISBN) | **Crítica** | Adaptar | FlipIQ tiene UPC lookup y Keepa ASIN lookup |
| 4 | Cálculo de Profit y ROI | **Crítica** | FlipIQ | `profit_engine.py` + `fees.py` son standalone |
| 5 | Fees de Amazon (FBA, MFN, referral) | **Crítica** | Adaptar | FlipIQ tiene fees básicos; PC2 tiene 99%+ precisión con SP-API |
| 6 | Multi-marketplace Amazon (US, UK, DE, FR, ES, IT, CA, MX, BR, AU) | **Alta** | Adaptar | FlipIQ solo soporta US (`domain=1`). Parametrizar Keepa |
| 7 | Detección de multipacks | **Alta** | FlipIQ | `amazon.py` ya detecta multi-packs vía regex |
| 8 | Buy Box analysis | **Alta** | Adaptar | FlipIQ extrae Buy Box de Keepa; falta "contenders" |
| 9 | Custom Filters en tiempo real | **Alta** | Nuevo | 12+ operadores sobre cualquier campo |
| 10 | Currency conversion | **Alta** | Nuevo | Tasas en vivo, conversión multi-paso |
| 11 | Cost Profiles (FBA/MFN/EFN, prep, shipping, VAT) | **Alta** | Adaptar | FlipIQ tiene Cost Profiles básicos; ampliar para VAT y EFN |
| 12 | Export a Excel/CSV | **Alta** | Nuevo | Generación de archivos con fórmulas y highlights |
| 13 | Sales Rank y estimación de ventas | **Alta** | FlipIQ | `amazon.py` ya estima ventas/día desde BSR |
| 14 | Major Brands filtering | **Media** | Nuevo | Lista editable de marcas gated |
| 15 | Historical data (promedios, % stock) | **Media** | Adaptar | FlipIQ tiene trend engine; PC2 usa datos editoriales de SP-API |
| 16 | ASIN Scoring (puntuación ponderada) | **Media** | Adaptar | FlipIQ tiene Opportunity Score; adaptar para scoring custom |
| 17 | Color Highlights en output | **Media** | Nuevo | Condicional por ROI, Buy Box, etc. |
| 18 | Keyword search | **Media** | FlipIQ | Keepa ya tiene endpoint de search |
| 19 | Seller SKU lookup | **Media** | Nuevo | Requiere SP-API directa |
| 20 | Variation discovery | **Baja** | Nuevo | Descubrir variaciones por ASIN padre |
| 21 | Amazon Browser (storefront scanning) | **Baja** | Nuevo | Scraping de storefronts/search results |
| 22 | CLI automation | **Baja** | N/A | Nuestra API reemplaza esto nativamente |
| 23 | Small & Light fees | **Baja** | Nuevo | Fees especiales para items pequeños |
| 24 | Packaging overrides por ASIN | **Baja** | Nuevo | Corrección manual de multipacks |

---

## 2. Componentes Reutilizables de FlipIQ

### Reutilizables SIN cambios (copiar directo)

| Componente | Archivo FlipIQ | Qué hace | Dependencias |
|-----------|----------------|----------|-------------|
| **Profit Engine** | `app/services/engines/profit_engine.py` | Calcula profit, ROI, margin con return reserve tiered | Solo `fees.py` |
| **Fees** | `app/core/fees.py` | Fee rates/fixed para eBay, Amazon FBA, ML, FB | Solo `decimal` (stdlib) |
| **Base Dataclasses** | `app/services/marketplace/base.py` | `CompsResult`, `MarketplaceListing`, `MarketplaceClient` | Solo stdlib |
| **Normalización de barcode** | `analysis_service.py` (funciones) | `_clean_search_keyword`, `_simplify_upc_title` | Solo `re` (stdlib) |
| **LLM Client** | `app/services/llm.py` | Gemini + OpenAI fallback | `openai` SDK |

### Reutilizables CON adaptaciones

| Componente | Archivo FlipIQ | Qué adaptar | Esfuerzo |
|-----------|----------------|-------------|----------|
| **Amazon Client (Keepa)** | `app/services/marketplace/amazon.py` | Parametrizar `domain` para multi-marketplace. Ya soporta batch nativo de ASINs | Bajo |
| **UPC Lookup** | `app/services/marketplace/ebay.py` → `lookup_upc()` | Extraer función, separar de eBay client | Bajo |
| **Title Enricher** | `app/services/engines/title_enricher.py` | Adaptar para batch masivo (actualmente 60 títulos/batch) | Medio |
| **Velocity Engine** | `app/services/engines/velocity_engine.py` | Funciona standalone. Útil como dato adicional vs PC2 | Bajo |
| **Risk Engine** | `app/services/engines/risk_engine.py` | Funciona standalone. Ventaja competitiva vs PC2 | Bajo |
| **Competition Engine** | `app/services/engines/competition_engine.py` | Adaptar para Buy Box contenders de PC2 | Medio |
| **Category Config** | `app/services/category_config.py` | Extraer `GLOBAL_DEFAULTS` y `ResolvedConfig`, desacoplar de DB | Medio |
| **Comp Cleaner** | `app/services/engines/comp_cleaner.py` | Reutilizar filtrado IQR y normalización de precios | Bajo |

### NO reutilizables (reconstruir)

| Componente | Razón |
|-----------|-------|
| `analysis_service.py` (orquestador) | Demasiadas dependencias; diseñado para single-item. Necesitamos orquestador batch |
| Modelos ORM | Schema diferente para batch processing |
| eBay scraper | PC2 no necesita eBay; nuestro diferenciador será tenerlo como extra |
| SSE Streaming | Reemplazar con job queue + polling/webhooks para batch |
| Rate Limiter | Diferente modelo de negocio y tiers |

---

## 3. Arquitectura Propuesta

```
┌─────────────────────────────────────────────────────┐
│                    API FastAPI                        │
├─────────────────────────────────────────────────────┤
│                                                       │
│  POST /api/v1/jobs              → Crear job batch     │
│  POST /api/v1/jobs/{id}/upload  → Upload archivo      │
│  GET  /api/v1/jobs/{id}         → Status del job      │
│  GET  /api/v1/jobs/{id}/results → Resultados          │
│  GET  /api/v1/jobs/{id}/export  → Download Excel/CSV  │
│  POST /api/v1/analyze           → Análisis single     │
│  POST /api/v1/analyze/asin      → Lookup ASIN directo │
│                                                       │
├─────────────────────────────────────────────────────┤
│                  Job Orchestrator                      │
│                                                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐       │
│  │  File    │  │  ID      │  │  Batch       │       │
│  │  Parser  │→ │  Resolver │→ │  Processor   │       │
│  └──────────┘  └──────────┘  └──────────────┘       │
│                                    │                  │
│                    ┌───────────────┼───────────────┐  │
│                    ▼               ▼               ▼  │
│              ┌──────────┐   ┌──────────┐   ┌────────┐│
│              │  Keepa   │   │  Profit  │   │ Filter ││
│              │  Client  │   │  Engine  │   │ Engine ││
│              │(FlipIQ)  │   │(FlipIQ)  │   │(Nuevo) ││
│              └──────────┘   └──────────┘   └────────┘│
│                                                       │
├─────────────────────────────────────────────────────┤
│  PostgreSQL  │  Redis (jobs/cache)  │  S3 (archivos) │
└─────────────────────────────────────────────────────┘
```

### Flujo de un Job Batch

```
1. Usuario crea job → POST /api/v1/jobs
   - Configura: marketplace, cost_profile, filters, currency
   - Retorna: job_id

2. Upload archivo → POST /api/v1/jobs/{id}/upload
   - Acepta: CSV, XLS, XLSX, TAB
   - Auto-detecta: columna de ID, columna de costo, tipo de ID
   - Valida y cuenta registros
   - Retorna: item_count, detected_id_type, detected_columns

3. Procesamiento async (background worker)
   a. Parse → extraer product_ids + costs del archivo
   b. Dedup → eliminar duplicados (configurable)
   c. Resolve IDs → UPC/EAN/ISBN → ASIN (vía Keepa)
   d. Batch Keepa lookup → datos de producto, offers, fees, BSR
      - Keepa acepta múltiples ASINs por request
      - Paralelizar en chunks de 20-50 ASINs
   e. Para cada item:
      - Calcular profit/ROI (profit_engine de FlipIQ)
      - Calcular velocity (velocity_engine de FlipIQ)
      - Calcular risk score (risk_engine de FlipIQ)
      - Detectar multipacks
      - Evaluar Buy Box
      - Aplicar filters del usuario
   f. Scoring → puntuar y rankear resultados
   g. Persistir resultados en DB

4. Usuario consulta status → GET /api/v1/jobs/{id}
   - Retorna: status, progress %, items_processed, items_total, eta

5. Usuario descarga → GET /api/v1/jobs/{id}/export
   - Formato: Excel con highlights o CSV
```

---

## 4. Modelos de Datos

### Job
```python
class Job:
    id: UUID
    user_id: UUID
    status: str          # pending, uploading, processing, completed, failed
    marketplace: str     # us, uk, de, fr, es, it, ca, mx, br, au
    cost_profile_id: UUID | None
    currency_input: str  # moneda del archivo de costos
    currency_output: str # moneda de salida para profits
    filters: dict        # custom filters JSON
    file_name: str
    file_path: str       # S3 path
    total_items: int
    processed_items: int
    matched_items: int   # items con ASIN encontrado
    profitable_items: int
    started_at: datetime | None
    completed_at: datetime | None
    processing_speed: float  # items/hora
    created_at: datetime
```

### JobItem (resultado por producto)
```python
class JobItem:
    id: UUID
    job_id: UUID
    input_row: int          # fila original del archivo
    input_id: str           # ID original (UPC, ASIN, etc.)
    input_id_type: str      # upc, asin, ean, isbn, keyword
    cost_price: float | None
    wholesale_pack_qty: int

    # Amazon data (de Keepa)
    asin: str | None
    title: str | None
    brand: str | None
    category: str | None
    sales_rank: int | None
    seller_count: int
    buy_box_price: float | None
    buy_box_seller: str | None
    amazon_is_seller: bool
    fba_fee: float | None
    referral_fee_pct: float | None
    multipack_qty: int
    is_hazmat: bool
    image_url: str | None
    list_price: float | None

    # Cálculos (de FlipIQ engines)
    estimated_sale_price: float | None
    profit: float | None
    roi_pct: float | None
    margin_pct: float | None
    marketplace_fees: float | None
    shipping_cost: float | None
    prep_cost: float | None
    return_reserve: float | None

    # Scores adicionales (ventaja vs PC2)
    velocity_score: float | None
    risk_score: float | None
    sales_per_day: float | None
    estimated_days_to_sell: str | None
    competition_hhi: float | None

    # Status
    status: str  # matched, not_found, filtered, error
    filter_reason: str | None
    error_message: str | None
```

### CostProfile
```python
class CostProfile:
    id: UUID
    user_id: UUID
    name: str
    fulfillment_type: str    # fba, mfn, efn
    prep_cost_per_item: float
    prep_cost_per_unit: float | None  # para multipacks
    shipping_from_supplier_pct: float | None  # % del costo
    shipping_from_supplier_per_item: float | None
    shipping_to_amazon: float | None
    vat_registered: bool
    vat_rate: float | None   # ej: 0.20 para UK 20%
    efn_source_marketplace: str | None  # para EFN
    small_light_eligible: bool
```

---

## 5. Endpoints API Detallados

### Jobs (Batch Processing)
```
POST   /api/v1/jobs                    → Crear job con config
POST   /api/v1/jobs/{id}/upload        → Upload archivo (multipart)
POST   /api/v1/jobs/{id}/start         → Iniciar procesamiento
GET    /api/v1/jobs/{id}               → Status y progreso
GET    /api/v1/jobs/{id}/results       → Resultados paginados con filtros
GET    /api/v1/jobs/{id}/results/stats → Resumen estadístico del job
GET    /api/v1/jobs/{id}/export        → Download Excel/CSV
DELETE /api/v1/jobs/{id}               → Cancelar/eliminar job
GET    /api/v1/jobs                    → Listar jobs del usuario
```

### Single Analysis (compatibilidad FlipIQ)
```
POST   /api/v1/analyze                 → Análisis single por barcode/keyword
POST   /api/v1/analyze/asin            → Análisis por ASIN directo
```

### Cost Profiles
```
POST   /api/v1/cost-profiles           → Crear perfil
GET    /api/v1/cost-profiles           → Listar perfiles
GET    /api/v1/cost-profiles/{id}      → Detalle
PUT    /api/v1/cost-profiles/{id}      → Actualizar
DELETE /api/v1/cost-profiles/{id}      → Eliminar
```

### Filters & Config
```
GET    /api/v1/filters/fields          → Campos filtrables disponibles
POST   /api/v1/filters/validate        → Validar set de filtros
GET    /api/v1/brands/major            → Lista de marcas gated
PUT    /api/v1/brands/major            → Actualizar lista
```

### Currency
```
GET    /api/v1/currencies/rates        → Tasas de cambio actuales
GET    /api/v1/currencies/supported    → Monedas soportadas
```

### Auth
```
POST   /api/v1/auth/register
POST   /api/v1/auth/login
POST   /api/v1/auth/refresh
```

---

## 6. Ventajas Competitivas vs PC2

Funcionalidades que FlipIQ nos da y PC2 **NO tiene:**

| Ventaja | Detalle | Motor FlipIQ |
|---------|---------|--------------|
| **Risk Score** | Evaluación de riesgo 0-100 por producto | `risk_engine.py` |
| **Velocity Score** | Velocidad de venta con estimación de días | `velocity_engine.py` |
| **Competition Analysis** | HHI de concentración de sellers | `competition_engine.py` |
| **Trend Analysis** | Tendencia de demanda y precio (rising/stable/declining) | `trend_engine.py` |
| **Confidence Score** | Qué tan confiable es el análisis | `confidence_engine.py` |
| **AI Explanation** | Explicación en lenguaje natural de cada producto | `ai_explanation.py` |
| **Opportunity Score** | Score combinado de todos los factores | `analysis_service.py` |
| **Recommendation** | Decisión automatizada (buy/watch/pass) | `analysis_service.py` |
| **Execution Score** | Probabilidad real de capturar la oportunidad | `execution_engine.py` |
| **eBay cross-analysis** | Comparar oportunidad Amazon vs eBay | `ebay.py` + pipeline |
| **Market Intelligence** | Contexto de mercado con LLM + web search | `market_intelligence.py` |
| **Listing Strategy** | Recomendación de formato (fixed/auction/best_offer) | `listing_strategy.py` |
| **API-first** | Integrable con cualquier frontend/app/automatización | Arquitectura nativa |

---

## 7. Stack Tecnológico

| Capa | Tecnología | Razón |
|------|-----------|-------|
| **Framework** | FastAPI | Async nativo, mismo que FlipIQ |
| **DB** | PostgreSQL + SQLAlchemy async | Mismo que FlipIQ, reutiliza patterns |
| **Cache/Queue** | Redis | Jobs queue, cache de Keepa, rate limiting |
| **Worker** | Celery o ARQ | Background processing para jobs batch |
| **Storage** | S3 / MinIO | Archivos de input y exports |
| **Data source** | Keepa API | Amazon data (FlipIQ ya lo usa) |
| **UPC lookup** | upcitemdb.com + Open Facts | Reutilizar de FlipIQ |
| **LLM** | Gemini 2.5 Flash + OpenAI fallback | Reutilizar `llm.py` de FlipIQ |
| **Excel** | openpyxl | Generación de Excel con formatos |
| **Auth** | Supabase JWT o similar | Consistente con FlipIQ |

---

## 8. Estimación de Throughput

### Cálculo basado en Keepa API

- Keepa acepta múltiples ASINs por request (batch nativo)
- Keepa rate limit: ~20-50 requests/minuto dependiendo del plan
- ~20 ASINs por request = 400-1,000 ASINs/minuto
- = **24,000 - 60,000 items/hora**

**Esto superaría los 18,000/hora de PC2** si optimizamos bien el batching.

### Bottlenecks a resolver
1. **ID Resolution:** UPC → ASIN lookup es más lento (1 por request en Keepa con `code` param)
   - Mitigación: Cache agresivo de UPC→ASIN mappings en Redis
2. **LLM enrichment:** Si usamos AI para cada item, es el bottleneck
   - Mitigación: Hacer AI enrichment opcional y en batch
3. **Excel generation:** Para 500K filas, genera archivos pesados
   - Mitigación: Streaming write con openpyxl, chunked

---

## 9. Fases de Desarrollo

### Fase 1 — MVP (Core Batch)
- [ ] Setup FastAPI + PostgreSQL + Redis
- [ ] File upload y parsing (CSV, XLSX)
- [ ] Auto-detección de columnas (ID, cost)
- [ ] ID resolution: ASIN directo + UPC→ASIN (Keepa)
- [ ] Batch Keepa lookup (producto, offers, fees, BSR)
- [ ] Profit/ROI calculation (reutilizar FlipIQ)
- [ ] Job queue con status y progreso
- [ ] Export a CSV
- [ ] Auth básica

### Fase 2 — Paridad con PC2
- [ ] Multi-marketplace Amazon (10 mercados)
- [ ] Cost Profiles (FBA/MFN/EFN, prep, shipping, VAT)
- [ ] Custom Filters (12+ operadores)
- [ ] Currency conversion con tasas en vivo
- [ ] Major Brands filtering
- [ ] Export a Excel con highlights
- [ ] Buy Box contender detection
- [ ] Historical data
- [ ] EAN/ISBN support

### Fase 3 — Superar a PC2 (ventajas FlipIQ)
- [ ] Velocity Score por producto
- [ ] Risk Score por producto
- [ ] Competition Analysis (HHI)
- [ ] Trend Analysis
- [ ] Confidence Score
- [ ] Opportunity Score combinado
- [ ] Recommendation engine (buy/watch/pass)
- [ ] AI Explanation por producto (opcional, premium)
- [ ] eBay cross-analysis
- [ ] Market Intelligence (premium)

### Fase 4 — Diferenciación
- [ ] Dashboard web con visualización de resultados
- [ ] Webhooks para notificación de job completado
- [ ] API keys para integración con herramientas de terceros
- [ ] Watchlists con price tracking (reutilizar FlipIQ)
- [ ] Price alerts
- [ ] Reportes comparativos entre jobs

---

## 10. Archivos FlipIQ a Copiar (Día 1)

```
Copiar directo:
├── app/services/engines/profit_engine.py
├── app/services/engines/velocity_engine.py
├── app/services/engines/risk_engine.py
├── app/services/engines/competition_engine.py
├── app/services/engines/trend_engine.py
├── app/services/engines/confidence_engine.py
├── app/services/engines/comp_cleaner.py
├── app/services/engines/title_risk.py
├── app/services/marketplace/base.py
├── app/core/fees.py
└── app/services/llm.py

Copiar y adaptar:
├── app/services/marketplace/amazon.py  → parametrizar domain
├── app/services/marketplace/ebay.py    → extraer lookup_upc()
├── app/services/engines/title_enricher.py → batch masivo
└── app/services/category_config.py     → extraer GLOBAL_DEFAULTS

Extraer funciones sueltas de:
└── app/services/analysis_service.py
    ├── _clean_search_keyword()
    ├── _simplify_upc_title()
    ├── _has_condition_noise()
    └── _detect_distribution_shape()
```
