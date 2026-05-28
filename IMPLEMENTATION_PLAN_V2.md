# Batch Flip — Plan de Implementación V2

## Contexto

App autorizada para **10 sellers de prueba** en SP-API. Rate limits son **por seller por app** — cada seller conectado tiene su propio bucket de tokens. Con pipeline SP-API optimizado (batch endpoints + burst) podemos alcanzar **~15,000 ASINs/hora por seller**.

Dos modos de análisis:
- **Fast Scan** (solo SP-API): ~15,000/hr — profit, fees, restrictions, Buy Box
- **Deep Scan** (SP-API + Keepa): ~400/hr — + monthlySold, reviews, rating, velocity score

---

## Estado Actual (29 archivos Python)

```
✅ FastAPI app + PostgreSQL + Redis + Alembic
✅ Modelos: Job, JobItem, SellerConnection
✅ Schemas: 44 campos en JobItemResponse
✅ 6 engines de FlipIQ (profit, velocity, risk, competition, comp_cleaner, title_risk)
✅ KeepaProvider (batch, UPC→ASIN, multi-domain)
✅ SPAPIProvider (9 endpoints: catalog, search, restrictions, fees, 
   competitive pricing, item offers, batch offers, FBA eligibility, sellers)
✅ HybridProvider (merge Keepa + SP-API)
✅ File parser (CSV/XLSX auto-detect)
✅ Batch processor (6 fases con HybridProvider)
✅ Export CSV (39 columnas)
✅ Streamlit test UI
✅ 9 API endpoints
```

---

## Fases de Implementación

### FASE A: Auth + OAuth Amazon (10 test sellers)
**Objetivo:** Users pueden registrarse y conectar su cuenta de Amazon Seller Central.

#### A1: User Model + Auth básica
**Archivos nuevos:**
```
app/models/user.py
app/core/security.py
app/api/v1/auth.py
```

**User model:**
```python
class User:
    id: UUID
    email: str (unique, indexed)
    password_hash: str
    is_active: bool = True
    plan: str = "free"  # free, starter, pro, enterprise
    created_at: datetime
```

**Endpoints:**
```
POST /api/v1/auth/register    → email + password → user + JWT
POST /api/v1/auth/login       → email + password → JWT
GET  /api/v1/auth/me          → user profile (requiere JWT)
```

**Security:**
```python
# app/core/security.py
- hash_password(password) → bcrypt hash
- verify_password(password, hash) → bool
- create_access_token(user_id) → JWT (expires 24h)
- get_current_user(token) → User (dependency)
```

#### A2: Amazon OAuth Flow
**Archivos nuevos:**
```
app/api/v1/amazon.py
app/services/amazon_oauth.py
```

**Flujo OAuth (para 10 test sellers):**
```
1. Frontend redirige al seller a:
   https://sellercentral.amazon.com/apps/authorize/consent
     ?application_id=amzn1.sp.solution.439c6786-1782-4607-a411-317342f722cc
     &state={random_state}
     &redirect_uri=https://batchflip.com/api/v1/amazon/callback
     
2. Seller autoriza en Amazon Seller Central

3. Amazon redirige a nuestro callback con:
   ?spapi_oauth_code={auth_code}&state={state}&selling_partner_id={seller_id}

4. Nuestro backend:
   - Verifica state
   - Exchange auth_code → refresh_token (POST https://api.amazon.com/auth/o2/token)
   - Llama getMarketplaceParticipations → seller_id, store_name, marketplaces
   - Guarda SellerConnection (refresh_token, seller_id, store_name)
   - Redirige al frontend con success
```

**Endpoints:**
```
GET  /api/v1/amazon/authorize       → Genera URL de autorización + state
GET  /api/v1/amazon/callback        → Callback de Amazon OAuth
GET  /api/v1/amazon/connections     → Lista conexiones del user
DELETE /api/v1/amazon/connections/{id} → Desconectar
```

**Para desarrollo local (sin redirect URL):**
- Usar el refresh_token del .env como "seller pre-conectado"
- `POST /api/v1/amazon/connect-manual` → acepta refresh_token directo (solo dev)

#### A3: Proteger endpoints existentes con auth
**Archivos a modificar:**
```
app/api/v1/jobs.py      → require auth, vincular user_id + seller_connection
app/api/v1/analyze.py   → require auth, usar seller_connection del user
app/api/v1/deps.py      → agregar get_current_user dependency
```

**Cambios:**
- `create_job` requiere JWT, asigna `user_id`
- `create_job` acepta `seller_connection_id` del user
- Endpoints de jobs filtran por `user_id` (no puedes ver jobs de otro user)
- `analyze` usa la seller_connection del user para SP-API

---

### FASE B: Fast Scan Pipeline (SP-API optimizado, ~15K/hr)
**Objetivo:** Pipeline que usa solo SP-API con batch endpoints para máximo throughput.

#### B1: SP-API Fast Pipeline
**Archivo nuevo:** `app/services/fast_scan_processor.py`

```
Pipeline Fast Scan (20 ASINs por ciclo, todo en paralelo):

PASO 1: ID Resolution (2-4 segundos para 20 items)
  - ASINs → directo
  - UPCs → SP-API Catalog Search (2/s + burst 40)
  - Paralelo: asyncio.gather con semaphore

PASO 2: Batch Data Fetch (1 request cada uno, ~2s total)
  Todo en paralelo:
  ┌─ Batch Fees (20 ASINs)          → getMyFeesEstimates
  ├─ Competitive Pricing (20 ASINs) → getCompetitivePricing
  └─ Batch Offers (20 ASINs)        → getBatchItemOffers

PASO 3: Restrictions (4 segundos para 20 items)
  - 5 requests/segundo → 20 items en 4s
  - Paralelo con semaphore(5)

PASO 4: FBA Eligibility (solo vendibles, ~2-5s)
  - Skip si can_sell=False
  - 1/s para los vendibles (~30-50%)
  
PASO 5: Profit Calculation (instantáneo, CPU)
  - compute_profit con fees de SP-API
  - No necesita Keepa

PASO 6: Persist (batch insert)

Ciclo: ~4-6 segundos por 20 ASINs = 200-300/min = 12,000-18,000/hr
```

**Rate limit manager:**
```python
# app/services/providers/rate_limiter.py
class RateLimiter:
    """Token bucket per endpoint, lee x-amzn-RateLimit-Limit del header."""
    def __init__(self, rate: float, burst: int):
        self.rate = rate
        self.burst = burst
        self.tokens = burst
        self.last_refill = time.monotonic()
    
    async def acquire(self):
        """Espera hasta que haya un token disponible."""
        ...
    
    def update_from_header(self, header_value: str):
        """Actualiza rate dinámicamente del response header."""
        ...
```

#### B2: Batch Fees via getMyFeesEstimates
**Archivo a modificar:** `app/services/providers/spapi.py`

```python
async def get_fees_estimate_batch_v2(
    self, items: list[tuple[str, float]],  # [(asin, price), ...]
    marketplace: str, is_fba: bool = True,
) -> dict[str, FeesResult]:
    """Batch de 20 ASINs en 1 request via getMyFeesEstimates."""
    # POST /products/fees/v0/feesEstimate
    # Body: array de FeesEstimateRequest con IdType + IdValue
    # Rate: 0.5/s pero 20 ASINs por request = 10 ASINs/s
```

#### B3: Modo Fast vs Deep en Job
**Archivo a modificar:** `app/models/job.py`

```python
class Job:
    ...
    scan_mode: str = "fast"  # "fast" (SP-API only) o "deep" (SP-API + Keepa)
```

**Archivo a modificar:** `app/schemas/job.py`

```python
class CreateJobRequest:
    ...
    scan_mode: str = "fast"  # "fast" o "deep"
```

**Archivo a modificar:** `app/services/batch_processor.py`

```python
async def process_job(job_id, db):
    ...
    if job.scan_mode == "fast":
        await fast_scan_process(job, items, db)
    else:
        await deep_scan_process(job, items, db)  # pipeline actual con Keepa
```

---

### FASE C: Deep Scan Pipeline (SP-API + Keepa, ~400/hr)
**Objetivo:** Refactorizar el pipeline actual para ser el modo "Deep Scan".

#### C1: Renombrar y optimizar batch_processor actual
**Archivo:** `app/services/deep_scan_processor.py` (renombrar de batch_processor.py)

```
Pipeline Deep Scan (actual + optimizaciones):

PASO 1: ID Resolution
  - SP-API Catalog Search PRIMERO (más rápido, 0 tokens Keepa)
  - Keepa fallback solo si SP-API falla

PASO 2: Keepa MINIMAL (3 tokens/ASIN en vez de 5)
  - stats=30, buybox=1, history=0, offers=0
  - Obtiene: monthlySold, rating, reviews, BSR, fees Keepa
  - NO obtiene: seller offers individuales, historial detallado

PASO 3-6: SP-API (igual que Fast Scan)
  - Restrictions, Batch Fees, Batch Offers, FBA Eligibility

PASO 7: Analysis mejorado
  - Profit con fees SP-API (más precisos)
  - Velocity score con monthlySold de Keepa (dato real)
  - Rating/reviews de Keepa
  - Risk score (si hay datos suficientes)

PASO 8: Persist
```

**Keepa minimal vs full:**
```
Full (5 tok):  stats=30, buybox=1, history=1, days=90, offers=20
Minimal (3 tok): stats=30, buybox=1, history=0, offers=0
Ahorro: 40% menos tokens → 400/hr vs 240/hr
```

---

### FASE D: Rate Limit Manager + Per-Seller Tokens
**Objetivo:** Cada seller conectado usa SU propio bucket de rate limits.

#### D1: Per-Seller SP-API instances
**Archivo nuevo:** `app/services/providers/spapi_pool.py`

```python
class SPAPIPool:
    """Pool de SPAPIProvider instances, una por seller_connection."""
    
    _instances: dict[UUID, SPAPIProvider] = {}
    
    async def get_provider(self, seller_connection_id: UUID, db) -> SPAPIProvider:
        """Obtiene o crea un SPAPIProvider para un seller."""
        if seller_connection_id not in self._instances:
            conn = await db.get(SellerConnection, seller_connection_id)
            self._instances[seller_connection_id] = SPAPIProvider(
                refresh_token=conn.refresh_token,
                seller_id=conn.seller_id,
                marketplace=...,
            )
        return self._instances[seller_connection_id]
```

**Impacto:** Con 10 sellers, cada uno tiene su propio rate limit bucket:
- 10 sellers × 15,000/hr cada uno = **150,000 ASINs/hora** teórico
- En la práctica: limitado por CPU y network del server

#### D2: Adaptive Rate Limiter
**Archivo nuevo:** `app/services/providers/rate_limiter.py`

```python
class AdaptiveRateLimiter:
    """Lee x-amzn-RateLimit-Limit del header y ajusta dinámicamente."""
    
    def __init__(self, default_rate: float, default_burst: int):
        self.rate = default_rate
        self.burst = default_burst
    
    def update_from_response(self, response: httpx.Response):
        header = response.headers.get("x-amzn-RateLimit-Limit")
        if header:
            self.rate = float(header)
    
    async def acquire(self):
        """Token bucket con rate dinámico."""
        ...
```

Esto es importante porque Amazon puede dar rate limits MÁS ALTOS a sellers con más ventas.

---

### FASE E: Frontend Funcional
**Objetivo:** Web app donde sellers se registran, conectan Amazon, y analizan listas.

#### E1: Next.js Setup
```
frontend/
├── app/
│   ├── layout.tsx
│   ├── page.tsx                    → Landing
│   ├── login/page.tsx
│   ├── register/page.tsx
│   ├── dashboard/
│   │   ├── layout.tsx              → Sidebar + header
│   │   ├── page.tsx                → Dashboard home
│   │   ├── connect/page.tsx        → Conectar Amazon (OAuth)
│   │   ├── jobs/
│   │   │   ├── page.tsx            → Lista de jobs
│   │   │   ├── new/page.tsx        → Crear job (upload + config)
│   │   │   └── [id]/page.tsx       → Job detail (progress + results)
│   │   ├── analyze/page.tsx        → Single item analysis
│   │   └── settings/page.tsx       → Perfil, plan
├── components/
│   ├── FileUploader.tsx
│   ├── JobProgress.tsx
│   ├── ResultsTable.tsx
│   ├── StatsCards.tsx
│   ├── ScanModeSelector.tsx        → Fast vs Deep toggle
│   └── AmazonConnectButton.tsx
```

#### E2: Páginas clave

**Connect Amazon:**
```
1. Botón "Connect Amazon Seller Account"
2. Redirige a Amazon Seller Central OAuth
3. Callback → muestra "Connected: AMONCA Tecnology (US, MX, CA, BR)"
4. Guarda seller_connection en DB
```

**New Job:**
```
1. Seleccionar modo: Fast Scan ⚡ vs Deep Scan 🔍
2. Upload CSV/XLSX (drag & drop)
3. Preview: "Found 1,000 ASINs, 300 UPCs. Cost column: Wholesale Cost"
4. Config: marketplace, fulfillment type, prep cost
5. "Start Analysis" → muestra progreso en tiempo real
```

**Job Results:**
```
- Summary cards: Total, Matched, Restricted, Profitable, Avg ROI
- Tabla con color coding:
  - Verde: profitable + can_sell
  - Rojo: restricted
  - Amarillo: vendible pero no profitable
  - Gris: not found
- Filtros: ROI > X%, profit > $X, can_sell only, sort by profit/roi/velocity
- Export CSV/XLSX
```

---

### FASE F: Migración DB + Deploy Inicial
**Objetivo:** PostgreSQL real + deploy para test con 10 sellers.

#### F1: Migración Alembic
```
alembic revision --autogenerate -m "v2_users_oauth_scan_modes"
```

Tablas nuevas:
- `users` (id, email, password_hash, plan, created_at)
- `seller_connections` (ya existe, agregar FK a users)

Campos nuevos:
- `jobs.scan_mode` (fast/deep)
- `jobs.user_id` FK a users
- `job_items.fba_eligible` (bool)
- `job_items.lowest_price_new/used`
- `job_items.buy_box_eligible_offers_new/used`

#### F2: Deploy inicial
```
- Backend: Railway (FastAPI + PostgreSQL + Redis)
- Frontend: Vercel (Next.js)
- Dominio: batchflip.com
- SSL: automático
- OAuth redirect: https://batchflip.com/api/v1/amazon/callback
```

---

## Orden de Implementación

```
SEMANA 1: FASE A (Auth + OAuth)
  ├─ A1: User model + JWT auth (1-2 días)
  ├─ A2: Amazon OAuth flow (2-3 días)
  └─ A3: Proteger endpoints (1 día)
  TEST: Registrar, login, conectar Amazon, ver seller info

SEMANA 2: FASE B (Fast Scan)
  ├─ B1: Fast scan processor (2-3 días)
  ├─ B2: Batch fees v2 (1 día)
  └─ B3: Modo fast/deep en Job (1 día)
  TEST: 100 ASINs en Fast Scan, medir throughput, verificar datos

SEMANA 3: FASE C + D (Deep Scan + Rate Limiter)
  ├─ C1: Deep scan optimizado (2 días)
  ├─ D1: SPAPIPool per-seller (1 día)
  └─ D2: Adaptive rate limiter (1 día)
  TEST: Deep scan con Keepa, comparar datos Fast vs Deep

SEMANA 4: FASE E (Frontend MVP)
  ├─ E1: Next.js setup + auth pages (2 días)
  └─ E2: Dashboard, connect, jobs, results (3 días)
  TEST: Flow completo: register → connect → upload → analyze → export

SEMANA 5: FASE F (Deploy + Test con sellers)
  ├─ F1: Migración DB (1 día)
  └─ F2: Deploy Railway + Vercel (2 días)
  TEST: 10 sellers de prueba, archivos reales, feedback
```

---

## Archivos por Crear/Modificar

### Nuevos (14 archivos)
```
app/models/user.py                          → User model
app/core/security.py                        → JWT, bcrypt, get_current_user
app/api/v1/auth.py                          → register, login, me
app/api/v1/amazon.py                        → OAuth flow, connections CRUD
app/services/amazon_oauth.py                → OAuth exchange logic
app/services/fast_scan_processor.py         → Pipeline SP-API only
app/services/deep_scan_processor.py         → Pipeline SP-API + Keepa (refactor de batch_processor)
app/services/providers/spapi_pool.py        → Pool per-seller
app/services/providers/rate_limiter.py      → Adaptive token bucket
frontend/                                   → Next.js app (múltiples archivos)
```

### Modificar (8 archivos)
```
app/config.py                → oauth redirect URL, JWT secret
app/models/job.py            → scan_mode field
app/models/seller.py         → FK a user
app/schemas/job.py           → scan_mode en CreateJobRequest
app/api/v1/jobs.py           → require auth, scan mode routing
app/api/v1/analyze.py        → require auth, usar seller connection
app/api/v1/deps.py           → get_current_user dependency
app/api/v1/router.py         → incluir auth + amazon routers
app/services/providers/spapi.py → batch fees v2
alembic/env.py               → import User model
```

---

## Métricas Target

| Métrica | Fast Scan | Deep Scan |
|---------|-----------|-----------|
| Throughput/seller | 12,000-18,000/hr | 400/hr |
| 1,000 ASINs | 3-5 min | 2.5 hrs |
| 10,000 ASINs | 30-50 min | 25 hrs |
| Datos de profit | ✅ Exactos (SP-API) | ✅ Exactos (SP-API) |
| Listing restrictions | ✅ | ✅ |
| FBA eligibility | ✅ | ✅ |
| Monthly sold | ❌ | ✅ (Keepa) |
| Reviews/rating | ❌ | ✅ (Keepa) |
| Velocity score | ❌ | ✅ (Keepa) |
| Buy Box stats por seller | ❌ | ✅ (Keepa) |
| Out of stock % | ❌ | ✅ (Keepa) |

---

## Flujo del Usuario (post-implementación)

```
1. REGISTER
   → POST /auth/register {email, password}
   → JWT token

2. CONNECT AMAZON
   → GET /amazon/authorize → redirect a Seller Central
   → Amazon callback → SellerConnection guardada
   → "Connected: AMONCA Tecnology (US, MX, CA, BR)"

3. CREATE JOB
   → POST /jobs {marketplace: "us", scan_mode: "fast", fulfillment: "fba"}
   → Upload CSV: POST /jobs/{id}/upload
   → Preview: "1,000 items, 800 ASINs + 200 UPCs"

4. START
   → POST /jobs/{id}/start
   → Fast Scan: ~5 min para 1,000 items
   → Deep Scan: ~2.5 hrs para 1,000 items

5. RESULTS
   → GET /jobs/{id} → status: "processing", progress: 45%
   → GET /jobs/{id}/results → tabla paginada con filtros
   → GET /jobs/{id}/results/stats → 400 profitable, avg ROI 45%

6. EXPORT
   → GET /jobs/{id}/export → CSV con 39+ columnas
```
