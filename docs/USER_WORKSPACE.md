# Batch Flip — Espacio de Trabajo del Usuario

> Documento de referencia: todos los datos, features y campos disponibles en el workspace de un usuario.

---

## 1. Perfil del Usuario

**Endpoint:** `GET /api/v1/auth/me`

| Campo | Tipo | Descripción |
|-------|------|-------------|
| id | UUID | ID único (= Supabase Auth ID) |
| email | string | Email del usuario |
| plan | string | `free` / `starter` / `pro` / `enterprise` |
| is_admin | bool | Acceso a endpoints admin |
| scans_used_month | int | Items analizados este mes |
| scans_limit_month | int | Límite mensual según plan |

### Planes y Límites

| Plan | Límite/mes | Precio | Features |
|------|-----------|--------|----------|
| free | 500 items | $0 | Fast Scan, Keepa básico |
| starter | 50,000 | $49/mes | + SP-API restrictions |
| pro | 200,000 | $99/mes | + Deep Scan, AI (futuro) |
| enterprise | Ilimitado | $199/mes | + API keys, priority |

---

## 2. Conexiones Amazon (Seller Accounts)

**Endpoints:**
- `GET /api/v1/amazon/authorize` — Iniciar OAuth
- `GET /api/v1/amazon/callback` — Callback OAuth
- `POST /api/v1/amazon/connect-manual` — Conectar con refresh token (dev)
- `GET /api/v1/amazon/connections` — Listar conexiones
- `DELETE /api/v1/amazon/connections/{id}` — Desconectar

| Campo | Tipo | Descripción |
|-------|------|-------------|
| id | UUID | ID de la conexión |
| seller_id | string | Amazon Seller ID (ej: A2TSJV48FRRFVQ) |
| store_name | string | Nombre de la tienda (ej: AMONCA Tecnology) |
| marketplace_ids | string[] | Marketplaces activos (US, MX, CA, BR) |
| is_active | bool | Si la conexión está activa |
| connected_at | datetime | Fecha de conexión |

**Seguridad:** El refresh_token se almacena encriptado (Fernet AES-128-CBC). Cada seller tiene su propio bucket de rate limits en SP-API.

---

## 3. Jobs (Análisis Batch)

### Crear Job

**Endpoint:** `POST /api/v1/jobs`

| Campo | Tipo | Default | Descripción |
|-------|------|---------|-------------|
| scan_mode | string | "fast" | `fast` (SP-API only, ~31K/hr) o `deep` (SP-API + Keepa, ~400/hr) |
| marketplace | string | "us" | `us`, `uk`, `de`, `fr`, `es`, `it`, `ca`, `mx`, `br`, `au` |
| fulfillment_type | string | "fba" | `fba` o `mfn` |
| prep_cost_per_item | float | 0.0 | Costo de preparación por item ($) |
| shipping_to_amazon | float | 0.0 | Costo de envío al warehouse ($) |
| seller_connection_id | UUID | null | Conexión Amazon a usar (para SP-API) |
| check_restrictions | bool | true | Verificar listing restrictions |

### Upload Archivo

**Endpoint:** `POST /api/v1/jobs/{id}/upload`

**Formatos:** CSV, XLSX, XLS, TSV (máx 50MB)

**Auto-detección:**
- Columna de ID: busca `asin`, `upc`, `barcode`, `ean`, `isbn`, `code`, `id`
- Columna de costo: busca `cost`, `price`, `wholesale`, `unit cost`
- Tipo de ID: ASIN (B0XXXXXXXX), UPC (12 dígitos), EAN (13 dígitos), ISBN

**Response:**

| Campo | Tipo | Descripción |
|-------|------|-------------|
| total_items | int | Productos encontrados |
| detected_id_type | string | Tipo mayoritario (asin/upc/ean) |
| detected_id_column | string | Columna detectada como ID |
| detected_cost_column | string | Columna detectada como costo |
| warnings | string[] | Advertencias del parsing |

### Job Status

**Endpoint:** `GET /api/v1/jobs/{id}`

| Campo | Tipo | Descripción |
|-------|------|-------------|
| id | UUID | |
| status | string | `pending` → `uploading` → `processing` → `completed` / `completed_with_errors` / `failed` |
| progress_phase | string | `resolving_ids` → `fetching_keepa` / `fetching_data` → `checking_restrictions` → `fetching_fees` → `analyzing` → `persisting` |
| scan_mode | string | `fast` o `deep` |
| marketplace | string | |
| fulfillment_type | string | |
| check_restrictions | bool | |
| file_name | string | Nombre del archivo subido |
| total_items | int | Total de items en el archivo |
| processed_items | int | Items procesados hasta ahora |
| matched_items | int | Items con datos encontrados |
| profitable_items | int | Items con profit > 0 |
| restricted_items | int | Items que no se pueden vender |
| error_items | int | Items con error o no encontrados |
| processing_speed | float | Items/hora |
| started_at | datetime | |
| completed_at | datetime | |
| created_at | datetime | |

### Job Stats (Resumen)

**Endpoint:** `GET /api/v1/jobs/{id}/results/stats`

| Campo | Tipo | Descripción |
|-------|------|-------------|
| total_items | int | Total |
| matched_items | int | Con datos |
| restricted_items | int | No vendibles |
| not_found_items | int | ASIN no encontrado |
| profitable_items | int | Profit > 0 |
| error_items | int | Errores |
| avg_roi | float | ROI promedio (%) |
| avg_profit | float | Profit promedio ($) |
| total_profit | float | Profit total ($) |
| best_roi_asin | string | ASIN con mejor ROI |
| best_profit_asin | string | ASIN con mejor profit |

---

## 4. Resultados por Producto (Job Item)

**Endpoint:** `GET /api/v1/jobs/{id}/results?page=1&page_size=50&sort_by=profit&profitable_only=false`

### 49 campos por producto:

#### Input (del archivo del proveedor)
| Campo | Tipo | Fuente |
|-------|------|--------|
| input_row | int | Fila original del archivo |
| input_id | string | ID como vino en el archivo |
| input_id_type | string | asin/upc/ean/isbn |
| cost_price | float | Costo wholesale ($) |

#### Producto (datos de Amazon)
| Campo | Tipo | Fuente | Descripción |
|-------|------|--------|-------------|
| asin | string | Keepa/SP-API | ASIN resuelto |
| title | string | Keepa | Título del producto |
| brand | string | Keepa | Marca |
| category | string | Keepa | Categoría (ej: "Digital Scales") |
| image_url | string | Keepa | URL de imagen |
| list_price | float | Keepa/SP-API | MSRP ($) |
| multipack_qty | int | Keepa | Cantidad en el paquete |
| is_hazmat | bool | Keepa | Material peligroso |
| item_weight_grams | int | Keepa/SP-API | Peso del item (gramos) |
| package_weight_grams | int | Keepa/SP-API | Peso del paquete (gramos) |
| item_height | int | Keepa/SP-API | Altura (1/100 pulgada) |
| item_length | int | Keepa/SP-API | Largo (1/100 pulgada) |
| item_width | int | Keepa/SP-API | Ancho (1/100 pulgada) |

#### Elegibilidad (¿puedo venderlo?)
| Campo | Tipo | Fuente | Descripción |
|-------|------|--------|-------------|
| can_sell | bool/null | SP-API | true/false/null (no verificado) |
| restriction_reason | string | SP-API | `APPROVAL_REQUIRED`, `NOT_ELIGIBLE`, null |
| restriction_message | string | SP-API | Mensaje completo de Amazon |

#### Pricing y Fees
| Campo | Tipo | Fuente | Descripción |
|-------|------|--------|-------------|
| buy_box_price | float | SP-API/Keepa | Precio actual del Buy Box ($) |
| estimated_sale_price | float | Calculado | = buy_box_price |
| fba_fee | float | Keepa | Fee FBA de Keepa (fallback) |
| referral_fee_pct | float | SP-API/Keepa | Referral fee % (SP-API override si disponible) |
| sp_api_total_fees | float | SP-API | Fees totales exactos ($) |
| sp_api_referral_fee | float | SP-API | Referral fee exacto ($) |
| sp_api_fba_fee | float | SP-API | FBA fee exacto ($) |

#### Profit (calculado)
| Campo | Tipo | Descripción |
|-------|------|-------------|
| profit | float | Ganancia neta ($) |
| roi_pct | float | Return on Investment (%) |
| margin_pct | float | Margen sobre venta (%) |
| marketplace_fees | float | Total fees Amazon ($) |

#### Velocity (¿qué tan rápido se vende?)
| Campo | Tipo | Fuente | Descripción |
|-------|------|--------|-------------|
| velocity_score | int | FlipIQ engine | 0-100 (100 = muy rápido) |
| sales_per_day | float | Keepa | Ventas por día |
| estimated_days_to_sell | string | FlipIQ engine | "~1d", "~7-14d", etc. |
| monthly_sold | int | Keepa | "X+ bought in past month" (dato real Amazon) |
| sales_rank_drops_30 | int | Keepa | Drops de rank en 30 días ≈ ventas |
| sales_rank | int | SP-API/Keepa | Best Seller Rank |

#### Competencia
| Campo | Tipo | Fuente | Descripción |
|-------|------|--------|-------------|
| seller_count | int | Keepa/SP-API | Total de sellers |
| amazon_is_seller | bool | Keepa | ¿Amazon vende este producto? |
| buy_box_is_amazon | bool | Keepa | ¿Amazon tiene el Buy Box? |
| offer_count_new | int | SP-API | Ofertas New activas |
| offer_count_used | int | SP-API | Ofertas Used activas |
| out_of_stock_pct_90 | int | Keepa | % tiempo fuera de stock en 90 días |

#### Reviews
| Campo | Tipo | Fuente | Descripción |
|-------|------|--------|-------------|
| rating | float | Keepa | Rating 1.0-5.0 |
| review_count | int | Keepa | Número de reviews |
| trade_in_value | float | SP-API | Valor de trade-in ($) |

#### Scores y Status
| Campo | Tipo | Descripción |
|-------|------|-------------|
| risk_score | int | 0-100 (100 = bajo riesgo) |
| status | string | `matched` / `restricted` / `not_found` / `error` |

---

## 5. Análisis Single Item

**Endpoint:** `POST /api/v1/analyze`

### Request (13 campos)

| Campo | Tipo | Default | Descripción |
|-------|------|---------|-------------|
| product_id | string | required | ASIN, UPC, EAN o ISBN |
| cost_price | float | required | Costo del producto ($) |
| marketplace | string | "us" | Marketplace Amazon |
| fulfillment_type | string | "fba" | `fba` o `mfn` |
| prep_cost | float | 0.0 | Costo de preparación |
| shipping_cost | float | 0.0 | Costo de envío |
| compare_fulfillment | bool | false | Comparar FBA vs MFN |
| fba_prep_cost | float | null | Prep cost específico FBA |
| shipping_to_amazon | float | null | Shipping específico FBA |
| mfn_prep_cost | float | null | Prep cost específico MFN |
| shipping_to_customer | float | null | Shipping específico MFN |
| mfn_packaging_cost | float | 0.0 | Packaging MFN |
| check_restrictions | bool | true | Verificar elegibilidad |

### Response (43 campos + profit_scenarios)

Los mismos campos que Job Item, más:
- `selected_fulfillment_type` — FBA o MFN seleccionado
- `fba_eligible` — Elegibilidad FBA específica
- `profit_scenarios` — Comparación FBA vs MFN (si compare_fulfillment=true)

#### Profit Scenarios (17 campos por escenario)

| Campo | Tipo | Descripción |
|-------|------|-------------|
| fulfillment_type | string | "fba" o "mfn" |
| eligible_to_sell | bool/null | Elegibilidad para este fulfillment |
| eligibility_reason | string | Razón si no elegible |
| uses_exact_fees | bool | Si usa fees de SP-API (vs Keepa) |
| estimated_sale_price | float | Precio de venta estimado |
| shipping_cost | float | Costo de envío para este escenario |
| prep_cost | float | Costo de prep |
| packaging_cost | float | Costo de empaque (solo MFN) |
| return_reserve | float | Reserva de devoluciones |
| marketplace_fees | float | Fees totales |
| referral_fee_pct | float | Referral % |
| sp_api_total_fees | float | Fees SP-API exactos |
| sp_api_referral_fee | float | Referral SP-API |
| sp_api_fba_fee | float | FBA fee SP-API |
| profit | float | Ganancia neta |
| roi_pct | float | ROI % |
| margin_pct | float | Margen % |

---

## 6. Export

**Endpoint:** `GET /api/v1/jobs/{id}/export`

**Formato:** CSV con 39+ columnas

Incluye todos los campos de Job Item en formato tabular con headers legibles.

---

## 7. Fuentes de Datos por Campo

### Solo de Keepa (datos exclusivos)
- monthly_sold (dato real de Amazon "X+ bought")
- sales_rank_drops_30/90 (cada drop ≈ 1 venta)
- buy_box_stats por seller (% del tiempo con Buy Box)
- rating y review_count
- out_of_stock_pct_90 (% OOS en 90 días)
- Historial de precios completo
- Detección de multipacks

### Solo de SP-API (datos por seller)
- can_sell / restriction_reason (listing restrictions por seller)
- fba_eligible (elegibilidad FBA)
- sp_api_total/referral/fba_fee (fees exactos al centavo)
- offer_count_new/used (conteo en tiempo real)
- trade_in_value
- lowest_price_new/used
- buy_box_eligible_offers

### De ambos (SP-API override, Keepa fallback)
- buy_box_price (SP-API más actual)
- sales_rank (SP-API más actual)
- referral_fee_pct (SP-API más preciso)
- fba_fulfillment_fee (SP-API más preciso)
- title, brand, category, dimensions

### Calculados (nuestros engines)
- profit, roi_pct, margin_pct (profit_engine de FlipIQ)
- velocity_score, estimated_days_to_sell (velocity_engine)
- risk_score (risk_engine)
- marketplace_fees, return_reserve

---

## 8. Modos de Scan

| | Fast Scan | Deep Scan |
|---|-----------|-----------|
| **Fuente** | Solo SP-API | SP-API + Keepa |
| **Throughput** | ~31,000 ASINs/hr | ~400 ASINs/hr |
| **Profit/ROI** | ✅ (SP-API fees exactos) | ✅ (SP-API fees exactos) |
| **Restrictions** | ✅ can_sell | ✅ can_sell |
| **FBA Eligibility** | ✅ | ✅ |
| **Buy Box price** | ✅ (real-time) | ✅ (real-time + historial) |
| **Monthly Sold** | ❌ | ✅ (dato real Keepa) |
| **Reviews/Rating** | ❌ | ✅ (Keepa) |
| **Velocity Score** | ❌ | ✅ (FlipIQ engine) |
| **Buy Box Stats** | ❌ | ✅ (% por seller) |
| **OOS Tracking** | ❌ | ✅ (% tiempo OOS) |
| **Risk Score** | ❌ | ✅ (FlipIQ engine) |

---

## 9. Seguridad y Compliance

| Requisito | Status |
|-----------|--------|
| Tokens encriptados (AES-128-CBC Fernet) | ✅ |
| Key rotation (dual-key + admin endpoint) | ✅ |
| Audit logging (12 meses) | ✅ |
| Password policy (12+ chars, mixed) | ✅ |
| Security headers (HSTS, X-Frame, etc.) | ✅ |
| CORS whitelist (no wildcard) | ✅ |
| Auth + ownership en todos los endpoints | ✅ |
| Admin restricted to is_admin role | ✅ |
| Upload validation (50MB, extensión whitelist) | ✅ |
| OAuth state con TTL (10 min) | ✅ |
| Rate limiting por plan | ✅ |
| Incident Response Plan | ✅ |
| Data Classification Document | ✅ |

---

## 10. Base de Datos

| Tabla | Columnas | Propósito |
|-------|----------|-----------|
| users | 11 | Plan, admin, rate limits, billing |
| products | 27 | Cache compartida de productos (ASIN key) |
| jobs | 29 | Batch jobs con config y progreso |
| job_items | 53 | Resultados per-product per-job |
| seller_connections | 9 | Cuentas Amazon conectadas (token encriptado) |
| audit_logs | 9 | Eventos de seguridad |
| alembic_version | 1 | Control de migraciones |

**Total: 7 tablas, ~139 columnas**

---

## 11. Features Pendientes

| Feature | Prioridad | Descripción |
|---------|-----------|-------------|
| Frontend Next.js | Alta | Dashboard web completo |
| Stripe billing | Alta | Pagos y planes |
| Watchlists + alerts | Media | Monitorear precios (de FlipIQ) |
| Product price history | Media | Historial diario por ASIN |
| Opportunity Score | Media | Score combinado 0-100 |
| Recommendation engine | Media | buy/buy_small/watch/pass |
| AI Explanation | Baja | Gemini/GPT explicación |
| eBay cross-analysis | Baja | Comparar Amazon vs eBay |
| Currency conversion | Baja | Multi-moneda |
| Custom Filters | Baja | Filtros avanzados |
