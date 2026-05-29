# Cambios Backend — Guía para Frontend

**Fecha:** 2026-05-28
**Backend URL:** https://batch-flip.onrender.com
**OpenAPI docs:** https://batch-flip.onrender.com/docs

---

## 1. Filtros Server-Side en Resultados

### Endpoint: `GET /api/v1/jobs/{job_id}/results`

Ahora acepta **22 query params** para filtrar, ordenar y buscar. Todos opcionales — si no se envían, retorna todo sin filtros.

### Ejemplo completo

```
GET /api/v1/jobs/{id}/results
  ?page=1
  &page_size=50
  &sort_by=fba_profit
  &sort_order=desc
  &min_profit=5
  &min_roi=20
  &can_sell=true
  &fba_eligible=true
  &hide_amazon_seller=true
  &max_bsr=100000
  &search=Apple
```

### Parámetros disponibles

#### Paginación y orden
| Param | Tipo | Default | Descripción |
|-------|------|---------|-------------|
| `page` | int | 1 | Página actual |
| `page_size` | int | 50 | Items por página |
| `sort_by` | string | "profit" | Columna para ordenar (ver lista abajo) |
| `sort_order` | string | "desc" | "asc" o "desc" |

#### Columnas ordenables (`sort_by`)
```
profit, fba_profit, mfn_profit, roi, fba_roi, mfn_roi,
rank, velocity, monthly_sold, sellers, rating, reviews,
buy_box, cost, row
```

#### Filtros numéricos (rango)
| Param | Tipo | Descripción |
|-------|------|-------------|
| `min_profit` | float | Profit mínimo (selected scenario) |
| `max_profit` | float | Profit máximo |
| `min_roi` | float | ROI % mínimo |
| `min_fba_profit` | float | Profit FBA mínimo |
| `min_mfn_profit` | float | Profit MFN mínimo |
| `max_bsr` | int | BSR máximo (ej: 100000) |
| `max_sellers` | int | Máximo de sellers |
| `min_velocity` | int | Velocity score mínimo (0-100) |
| `min_rating` | float | Rating mínimo (ej: 4.0) |
| `min_monthly_sold` | int | Ventas mensuales mínimas |

#### Filtros booleanos
| Param | Tipo | Default | Descripción |
|-------|------|---------|-------------|
| `can_sell` | bool | null | `true` = solo vendibles, `false` = solo no vendibles |
| `fba_eligible` | bool | null | `true` = solo FBA eligible |
| `hide_amazon_seller` | bool | false | Ocultar items donde Amazon vende |
| `hide_restricted` | bool | false | Ocultar items restringidos |

#### Filtros de texto
| Param | Tipo | Descripción |
|-------|------|-------------|
| `status` | string | Filtrar por status: `matched`, `restricted`, `not_found`, `error` |
| `best_scenario` | string | Filtrar por mejor escenario: `fba`, `mfn`, `neither` |
| `search` | string | Busca en title, brand y ASIN (case insensitive) |

### Response (sin cambios)

```json
{
  "items": [...],    // Array de JobItemResponse (59 campos por item)
  "total": 234,      // Total de items que pasan los filtros
  "page": 1,
  "page_size": 50,
  "total_pages": 5
}
```

### CAMBIO IMPORTANTE

Antes: el endpoint **solo mostraba items con status="matched"**.
Ahora: muestra **todos los statuses** por default. Usar `?status=matched` o `?hide_restricted=true` para filtrar.

---

## 2. Export Filtrado

### Endpoint: `GET /api/v1/jobs/{job_id}/export`

Ahora acepta los **mismos filtros** que `/results`. El CSV solo incluye los items que pasan los filtros.

### Ejemplo

```
GET /api/v1/jobs/{id}/export
  ?min_profit=5
  &can_sell=true
  &fba_eligible=true
  &best_scenario=fba
  &hide_amazon_seller=true
```

Esto exporta solo los items que:
- Tienen profit > $5
- Se pueden vender
- Son FBA eligible
- FBA es el mejor escenario
- Amazon no vende

### UI sugerida

Botón "Export CSV" que envía los mismos filtros activos en la tabla:

```tsx
<Button onClick={() => {
  const params = new URLSearchParams(activeFilters);
  window.open(`/api/v1/jobs/${jobId}/export?${params}`);
}}>
  Export Filtered CSV
</Button>
```

---

## 3. Cost Profiles — NUEVO

### Endpoints

| Método | URL | Auth | Descripción |
|--------|-----|------|-------------|
| `POST` | `/api/v1/cost-profiles` | ✅ JWT | Crear perfil |
| `GET` | `/api/v1/cost-profiles` | ✅ JWT | Listar perfiles del user |
| `GET` | `/api/v1/cost-profiles/{id}` | ✅ JWT | Detalle |
| `PUT` | `/api/v1/cost-profiles/{id}` | ✅ JWT | Actualizar |
| `DELETE` | `/api/v1/cost-profiles/{id}` | ✅ JWT | Eliminar |

### Crear perfil

```
POST /api/v1/cost-profiles
Authorization: Bearer {token}

{
  "name": "Mi FBA US",
  "marketplace": "us",
  "fulfillment_type": "both",
  "fba_prep_cost": 1.50,
  "fba_shipping_to_amazon": 0.80,
  "mfn_prep_cost": 0.50,
  "mfn_shipping_to_customer": 5.00,
  "mfn_packaging_cost": 1.00,
  "is_default": true
}
```

#### Campos del request

| Campo | Tipo | Default | Descripción |
|-------|------|---------|-------------|
| `name` | string | **required** | Nombre del perfil (ej: "Mi FBA US") |
| `marketplace` | string | "us" | Marketplace: us, uk, de, fr, es, it, ca, mx, br, au |
| `fulfillment_type` | string | "both" | "fba", "mfn", o "both" |
| `fba_prep_cost` | float | 0.0 | Costo de prep por item para FBA ($) |
| `fba_shipping_to_amazon` | float | 0.0 | Shipping al warehouse FBA por item ($) |
| `mfn_prep_cost` | float | 0.0 | Costo de prep por item para MFN ($) |
| `mfn_shipping_to_customer` | float | 0.0 | Shipping al cliente por item ($) |
| `mfn_packaging_cost` | float | 0.0 | Empaque por item para MFN ($) |
| `is_default` | bool | false | Si es el perfil default del user |

**Nota:** Si `is_default=true`, los otros perfiles del user se ponen `is_default=false` automáticamente.

### Response

```json
{
  "id": "uuid",
  "user_id": "uuid",
  "name": "Mi FBA US",
  "marketplace": "us",
  "fulfillment_type": "both",
  "fba_prep_cost": 1.50,
  "fba_shipping_to_amazon": 0.80,
  "mfn_prep_cost": 0.50,
  "mfn_shipping_to_customer": 5.00,
  "mfn_packaging_cost": 1.00,
  "is_default": true,
  "created_at": "2026-05-28T...",
  "updated_at": "2026-05-28T..."
}
```

### Usar perfil al crear Job

```
POST /api/v1/jobs
Authorization: Bearer {token}

{
  "scan_mode": "fast",
  "marketplace": "us",
  "fulfillment_type": "fba",
  "cost_profile_id": "uuid-del-perfil",
  "seller_connection_id": "uuid-seller",
  "check_restrictions": true
}
```

Si `cost_profile_id` se envía, los costos del perfil sobrescriben los campos inline. El frontend puede mostrar un dropdown con los perfiles guardados.

### UI sugerida para Cost Profiles

**En Settings o como modal:**
```
Mis Perfiles de Costo
┌────────────────────────────────────────────┐
│ ★ Mi FBA US (default)          [Edit] [Del]│
│   FBA: prep $1.50, ship $0.80              │
│   MFN: prep $0.50, ship $5.00, pkg $1.00  │
├────────────────────────────────────────────┤
│   MFN con DHL                  [Edit] [Del]│
│   MFN: prep $0.25, ship $8.50, pkg $0.50  │
├────────────────────────────────────────────┤
│   [+ Nuevo perfil]                         │
└────────────────────────────────────────────┘
```

**Al crear Job:**
```
Perfil de costo: [Mi FBA US (default) ▼]
                  Mi FBA US (default)
                  MFN con DHL
                  Custom (escribir costos)
```

---

## 4. Resumen de Todos los Endpoints (27 total)

### Auth (4)
```
POST   /api/v1/auth/register
POST   /api/v1/auth/login
POST   /api/v1/auth/refresh
GET    /api/v1/auth/me
```

### Amazon OAuth (5)
```
GET    /api/v1/amazon/authorize
GET    /api/v1/amazon/callback
POST   /api/v1/amazon/connect-manual
GET    /api/v1/amazon/connections
DELETE /api/v1/amazon/connections/{id}
```

### Jobs (8)
```
POST   /api/v1/jobs                    → Crear (con cost_profile_id opcional)
GET    /api/v1/jobs                    → Listar mis jobs
POST   /api/v1/jobs/{id}/upload        → Upload CSV/XLSX
POST   /api/v1/jobs/{id}/start         → Iniciar análisis
GET    /api/v1/jobs/{id}               → Status/progreso
GET    /api/v1/jobs/{id}/results       → Resultados con filtros (22 params)
GET    /api/v1/jobs/{id}/results/stats → Resumen estadístico
GET    /api/v1/jobs/{id}/export        → CSV filtrado (18 params)
DELETE /api/v1/jobs/{id}               → Eliminar
```

### Analyze (1)
```
POST   /api/v1/analyze                 → Single item (dual FBA/MFN)
```

### Cost Profiles (5) — NUEVO
```
POST   /api/v1/cost-profiles           → Crear
GET    /api/v1/cost-profiles           → Listar
GET    /api/v1/cost-profiles/{id}      → Detalle
PUT    /api/v1/cost-profiles/{id}      → Actualizar
DELETE /api/v1/cost-profiles/{id}      → Eliminar
```

### Admin (2)
```
POST   /api/v1/admin/rotate-encryption-key
GET    /api/v1/admin/generate-key
```

### Health (1)
```
GET    /health
```

---

## 5. Campos por Producto (JobItemResponse — 59 campos)

Los campos que el frontend puede mostrar/filtrar por cada producto:

### Datos de input
`input_row`, `input_id`, `input_id_type`, `cost_price`

### Producto
`asin`, `title`, `brand`, `category`, `sales_rank`, `buy_box_price`, `list_price`, `image_url`, `multipack_qty`, `is_hazmat`, `item_weight_grams`, `package_weight_grams`, `item_height`, `item_length`, `item_width`

### Elegibilidad
`can_sell`, `fba_eligible`, `restriction_reason`, `restriction_message`

### Profit — Selected
`estimated_sale_price`, `profit`, `roi_pct`, `margin_pct`, `marketplace_fees`

### Profit — FBA scenario
`fba_profit`, `fba_roi_pct`, `fba_margin_pct`, `fba_total_fees`

### Profit — MFN scenario
`mfn_profit`, `mfn_roi_pct`, `mfn_margin_pct`, `mfn_total_fees`

### Best scenario
`best_scenario` (fba / mfn / neither)

### Velocity
`velocity_score`, `sales_per_day`, `estimated_days_to_sell`, `monthly_sold`, `sales_rank_drops_30`

### Competencia
`seller_count`, `amazon_is_seller`, `buy_box_is_amazon`, `offer_count_new`, `offer_count_used`, `out_of_stock_pct_90`

### Reviews
`rating`, `review_count`, `trade_in_value`

### Fees
`fba_fee`, `referral_fee_pct`, `sp_api_total_fees`, `sp_api_referral_fee`, `sp_api_fba_fee`

### Scores
`risk_score`

### Status
`status` (matched / restricted / not_found / error)
