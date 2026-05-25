# FlipIQ - Price Checker 2: Features Completas

Sistema SaaS API-first construido con FastAPI para evaluar productos antes de comprarlos para revender, calculando margen neto, riesgo, velocidad de venta y canales recomendados.

## Stack Tecnológico

- **Backend:** FastAPI (Python 3.11, 100% async)
- **Base de datos:** PostgreSQL + SQLAlchemy async + Alembic migrations
- **Cache:** Redis
- **Auth:** Supabase JWT
- **LLM:** Gemini 2.5 Flash (preferido) → fallback OpenAI GPT-4o-mini → fallback regex
- **Marketplaces:** eBay (scraper propio + Browse API) + Amazon (Keepa API)
- **Notificaciones:** OneSignal (push) + Customer.io (email)
- **Billing:** Stripe + Apple IAP

---

## Pipeline de Análisis (13 Motores)

Orquesta 13 motores especializados en paralelo para eBay y Amazon.

### Motor A - Comp Cleaner
**Archivo:** `app/services/engines/comp_cleaner.py`

- Normaliza precios (price + shipping), dividiendo por lot_size en bundles
- Filtra por ventana temporal adaptativa (30 días, expande a 90 si hay menos de 5 comps)
- Filtra outliers con IQR Tukey (1.5x)
- Filtra por product_type (detecta accesorios vs producto principal)
- Filtra "danger patterns" (box_only, empty_box, for_parts, etc.)
- Filtra por condición (new/used/open_box/refurbished)
- Auto-filtra condiciones: si 50%+ son "new", excluye "used"
- Filtra por relevancia (si hay datos enriquecidos por LLM)
- Recalcula estadísticas: mediana, media, p25, p75, IQR, CV, std_dev

### Motor B - Pricing Engine
**Archivo:** `app/services/engines/pricing_engine.py`

Calcula 3 precios recomendados:
- **quick_list:** salida rápida → `max(p25, mediana - spread)`
- **market_list:** precio de mercado → `mediana`
- **stretch_list:** precio premium → si CV < 0.45, `min(p75, mediana + spread)`

### Motor C - Profit Engine
**Archivo:** `app/services/engines/profit_engine.py`

Calcula rentabilidad neta real con todos los costos:
- Marketplace fees (eBay 13.6% + $0.40, Amazon FBA 15% + $3.50)
- Shipping, packaging, prep, promo costs
- Return reserve escalonada por precio (5% hasta $50, 3% hasta $200, 2% hasta $500, 1% arriba)
- Output: profit, ROI, margin, gross_proceeds, risk_adjusted_net

### Motor D - Max Buy Price
**Archivo:** `app/services/engines/max_buy_price.py`

- **breakeven:** máximo sin perder dinero
- **max_by_roi:** máximo para lograr 35% ROI target
- **recommended_max:** el menor de breakeven y max_by_roi
- **max_by_profit:** basado en target_profit (informativo)

### Motor E - Velocity Engine
**Archivo:** `app/services/engines/velocity_engine.py`

- Fórmula logarítmica: `score = min(100, 25 * ln(1 + 30 * sales_per_day))`
- Categorías: very_fast (>=1/día), healthy (>=0.5), moderate (>=0.1), slow
- Estima días para vender con rangos de incertidumbre

### Motor F - Risk Engine
**Archivo:** `app/services/engines/risk_engine.py`

- Score 0-100 (100 = bajo riesgo)
- Fórmula: `100 - 35*CV_penalty - 30*dispersion_penalty - 20*outlier_share - 15*sample_penalty`
- Categorías: low (>=70), medium (>=40), high (<40)

### Motor G - Confidence Engine
**Archivo:** `app/services/engines/confidence_engine.py`

- Score 0-100 basado en:
  - 30% sample size, 25% consistency, 20% attribute quality, 15% timeline coverage, 10% enrichment quality
- Penalizaciones por: expansión temporal, title risk, burstiness alta
- 4 niveles: high (>=85), medium_high (>=70), medium (>=50), low (<50)

### Motor H - Seller Premium
**Archivo:** `app/services/engines/seller_premium.py`

- Compara precios de sellers top (>=99.5% feedback) vs el resto
- Detecta premium de precio por reputación

### Motor I - Competition Engine
**Archivo:** `app/services/engines/competition_engine.py`

- Calcula HHI (Herfindahl-Hirschman Index) de concentración de sellers
- Categorías: healthy (<0.15), moderate (0.15-0.25), concentrated (>0.25)
- Informa dominant_seller_share y unique_sellers

### Motor J - Trend Engine
**Archivo:** `app/services/engines/trend_engine.py`

- Compara últimos 7 días vs 7 días previos
- Calcula demand_trend (% cambio en volumen) y price_trend (% cambio en precio medio)
- Mide burstiness (concentración de ventas en pocos días)
- Categorías: rising (>15% delta), stable, declining

### Motor K - Listing Strategy
**Archivo:** `app/services/engines/listing_strategy.py`

- Recomienda formato: fixed_price, auction, best_offer
- Basado en velocidad, riesgo, CV, presencia de bids
- Genera reasoning en lenguaje natural

### Motor L - AI Explanation
**Archivo:** `app/services/engines/ai_explanation.py`

- Genera explicación en lenguaje natural con GPT-4o-mini/Gemini
- Formato fijo 4 líneas: Decision, Why, Risk, Action
- Alineación forzada: la Decision del AI debe coincidir con la del motor determinista

### Motor M - Market Intelligence (Premium)
**Archivo:** `app/services/engines/market_intelligence.py`

- Usa Brave Search + LLM para contexto de mercado
- Analiza: ciclo de vida, riesgo de depreciación, factor estacional, eventos de mercado
- Output: timing_recommendation (buy_now/wait/sell_fast/hold)

---

## Motores Auxiliares

### Title Enricher
**Archivo:** `app/services/engines/title_enricher.py`

- Enriquece listings con LLM: extrae condition, brand, model, is_bundle, lot_size de títulos
- Fallback a regex cuando LLM no está disponible
- Deduplica títulos antes de enviar al LLM para ahorrar costos
- Logea samples para ML training

### Comp Relevance Filter
**Archivo:** `app/services/engines/comp_relevance.py`

- Usa LLM para clasificar cada comp como match (1) o no-match (0) vs keyword
- Resuelve variantes semánticas (GS vs Mens, accesorios vs producto)
- Safety nets: no filtra si quedan <2 comps, logea para ML training

### Title Risk Detector
**Archivo:** `app/services/engines/title_risk.py`

- Detecta 30+ danger patterns en títulos: box_only, empty_box, broken, locked, icloud_locked, etc.
- Cada patrón tiene un peso de riesgo (0-1)
- Suprime flags cuando el keyword contiene la misma palabra

### Product Categorizer
**Archivo:** `app/services/engines/product_categorizer.py`

- Strategy: eBay Taxonomy API (gratis, rápida) con fallback a LLM
- Extrae product_type y ebay_category_id del keyword
- Mapea a 40+ categorías curadas de eBay

### Execution Engine
**Archivo:** `app/services/engines/execution_engine.py`

- Estima si el reseller puede CAPTURAR la oportunidad (no solo si existe)
- Penalizaciones por: low_confidence, small_sample, seller_dominance, generic_fba_fees, bimodal_pricing, high_price_volatility, demand_declining, mixed_conditions, high_ticket_execution
- Score determina max_recommendation y quantity_guidance
- Amazon: penaliza fuertemente Buy Box inaccesible

---

## Sistema de Decisión

### Opportunity Score (0-100)
```
30% profit_score + 25% velocity + 20% risk + 15% confidence + 10% market_health
```

### Final Score
```
65% market_opportunity + 35% execution_score
```

### Decisiones
| Decisión | Criterio |
|----------|----------|
| **buy** | opportunity >= 60, profit > 0, risk >= 40, confidence >= 30 |
| **buy_small** | opportunity >= 45, profit > 0, ROI > 20%, risk >= 30 |
| **watch** | opportunity >= 35 o ROI > 10% |
| **pass** | todo lo demás |

### Validador `_validate_buy`
Degrada recomendaciones por:
- Costo > breakeven o > max_by_roi
- Confianza baja (<50 o <60)
- Condition mismatch
- Title risk alto
- Pocos comps (<5 o <3)
- Distribución bimodal o dispersa
- Profit negativo
- CV alto (>0.50)

---

## Endpoints API

### Analysis (`/api/v1/analysis/`)
| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | `/` | Análisis completo por barcode/keyword |
| POST | `/asin` | Análisis Amazon por ASIN directo |
| POST | `/stream` | Análisis progresivo vía SSE |
| GET | `/history` | Historial de análisis del usuario |
| GET | `/not-found` | Lista de análisis sin comps |
| GET | `/flagged` | Análisis marcados como incorrectos |
| POST | `/{id}/feedback` | Reportar análisis incorrecto |
| POST | `/{id}/share` | Generar link compartible |
| GET | `/share/{token}` | Ver análisis compartido (público) |
| PATCH | `/manual-reviews/{id}/details` | Agregar detalles para revisión manual |
| GET | `/{id}` | Detalle completo de un análisis |

### Auth (`/api/v1/auth/`)
### Products (`/api/v1/products/`)

### Watchlists (`/api/v1/watchlists/`)
- CRUD de watchlists con items
- Target buy price y notas por item
- Precio history con snapshot diario

### Search (`/api/v1/search/`)
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/suggest` | Autocomplete híbrido (DB local + eBay Browse API fallback) |
| POST | `/suggest/{id}/select` | Registra selección para ranking de popularidad |

### Billing (`/api/v1/billing/`)
### Admin (`/api/v1/admin/`)
### Notifications (`/api/v1/notifications/`)
### Cron (`/api/v1/cron/`)
### Waitlist (`/api/v1/waitlist/`)

---

## Modelos de Datos

**Archivo:** `app/models/analysis.py`

- **Analysis:** resultado completo con inputs, scores, recommendation, engines_data (JSON blob), ai_explanation, share_token
- **AnalysisFeedback:** feedback del usuario (incorrect_price, incorrect_recommendation, outdated, missing_data, other)
- **Product:** título, barcode, brand, image, ebay_avg_sold_price, search_count
- **User:** auth con Supabase
- **Watchlist/WatchlistItem:** listas con target_buy_price
- **ProductPriceHistory:** historial diario eBay+Amazon
- **ManualReviewRequest:** revisiones manuales
- **MLTrainingSample:** datos para entrenar modelos ML propios

---

## Servicios de Marketplace

### eBay
**Archivo:** `app/services/marketplace/ebay.py`

- Scraper propio con curl_cffi + BeautifulSoup
- Pool de RPi proxies residenciales
- eBay Browse API para autocompletado
- eBay Taxonomy API para categorización
- UPC lookup vía upcitemdb.com

### Amazon
**Archivo:** `app/services/marketplace/amazon.py`

- Keepa API para datos reales: Buy Box, historial de precios, sales rank
- Estimación de ventas/día desde BSR
- Detección de multi-packs
- Fees reales de FBA por producto

---

## Servicios Complementarios

### Price Tracker
**Archivo:** `app/services/price_tracker.py`

- Actualización diaria de precios para productos en watchlists
- Obtiene mediana eBay sold y Buy Box Amazon
- Almacena en product_price_history

### Price Alerts
**Archivo:** `app/services/price_alerts.py`

- Monitorea target_buy_price de items en watchlists
- Notifica vía OneSignal push + Customer.io cuando el precio baja al target

### Category Config
**Archivo:** `app/services/category_config.py`

- Sistema de configuración de 3 niveles: GLOBAL_DEFAULTS → category.engine_defaults → category_channels.engine_overrides
- 43+ constantes de motores configurables por categoría y marketplace
- Fees por brackets de precio (eBay cobra diferente según rango)

---

## Fees por Marketplace

**Archivo:** `app/core/fees.py`

| Marketplace | Fee |
|-------------|-----|
| **eBay** | 13.6% final value + $0.30/$0.40 per-order fee |
| **Amazon FBA** | 15% referral + $3.50 fulfillment (override por Keepa con fees reales) |
| **MercadoLibre** | 16% comisión |
| **Facebook Marketplace** | 5% selling fee |

---

## Sistema de Streaming Progresivo (SSE)

El endpoint `/stream` envía eventos SSE con progreso:

1. **start** (3%) - Inicio del scan
2. **identify** (8-12%) - Lookup de barcode
3. **category** (14-18%) - Clasificación de producto
4. **fetch** (25-46%) - Obtención de datos eBay + Amazon en paralelo
5. **matching** (52-68%) - Enriquecimiento + filtro de relevancia
6. **scoring** (72-88%) - Pipeline de motores A-K
7. **analysis** (evento) - Resultado completo sin AI
8. **ai_complete** (evento) - AI explanation + market intelligence

---

## Seguridad y Rate Limiting

- Rate limiting por tier: free, starter, pro
- Semáforo global de 8 análisis concurrentes
- JWT validation con Supabase
- CORS configurado para localhost y getflipiq.com
- Headers X-RateLimit-Remaining y X-RateLimit-Tier

---

## ML y Entrenamiento

- Los LLM calls logean samples para futuro ML training (`MLTrainingSample`)
- Flags de configuración: `ml_comp_relevance_enabled`, `ml_condition_enabled`, `ml_shadow_mode`
- Scripts de training: `train_comp_relevance.py`, `train_condition_classifier.py`
- Directorio de modelos: `models/`
