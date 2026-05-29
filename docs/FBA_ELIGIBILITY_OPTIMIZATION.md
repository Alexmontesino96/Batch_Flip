# FBA Eligibility Optimization — Análisis PM y Cambios

> **Fecha:** 2026-05-29
> **Contexto:** Fast Scan pipeline tarda ~7 horas para 445 ASINs (63 items/hr). PC2 hace 18,000 items/hr.
> **Resultado:** FBA eligibility era el cuello de botella #1. Se implementó cache + semáforo calibrado.

---

## 1. Diagnóstico del problema

### Desglose de requests SP-API por chunk de 20 ASINs

| Endpoint | Tipo real | Requests | Semáforo | Tiempo estimado |
|---|---|---|---|---|
| Offers Batch | Batch real (1 POST) | 1 | `offers=2` | ~2s |
| Competitive Pricing | Batch real (1 GET) | 1 | `pricing=2` | ~2s |
| Catalog Items | **Falso batch** (20 GET individuales) | 20 | `catalog=2` | ~20s |
| Restrictions | **Falso batch** (20 GET individuales) | 20 | `restrictions=5` | ~8s |
| Fees FBA | Batch real (1 POST) | 1 | `fees=1` | ~2s |
| Fees MFN | Batch real (1 POST) | 1 | `fees=1` | ~2s |
| **FBA Eligibility** | **Falso batch (20 GET individuales)** | **20** | **`fba=1`** | **~300s** |
| **TOTAL** | | **~64** | | **~336s (~5.6 min)** |

### El cuello de botella: FBA Eligibility

Con semáforo `fba=1`, las 20 llamadas de `check_fba_eligibility` se ejecutan **de forma serial** — aunque `asyncio.gather` las lance en paralelo, solo 1 pasa el semáforo a la vez.

**Archivos involucrados:**
- `app/services/providers/spapi.py:54` — `"fba": 1` (semáforo)
- `app/services/providers/spapi.py:697-712` — `check_fba_eligibility_batch` (gather de calls individuales)
- `app/services/fast_scan_processor.py:234-239` — invocación en el pipeline

**Impacto medido:**
- FBA eligibility representa **~89% del tiempo por chunk** (300s de 336s)
- Job de 48 ASINs completado: 55 min 26s = **69s por ASIN**
- Proyección para 445 ASINs: **~7.1 horas**

### Bug de progreso (corregido junto con este cambio)

`fast_scan_processor.py:149` reportaba:
```python
job.processed_items = (chunk_idx + 1) * CHUNK_SIZE
```

Esto sobre-reportaba en el último chunk (si tiene 5 ASINs, reportaba 20).

---

## 2. Referencia: cómo lo resuelve PC2

Price Checker 2 (nuestra referencia competitiva, $148/mes, 18K items/hr) maneja FBA eligibility así:

| Aspecto | PC2 | Nosotros (antes) |
|---|---|---|
| Llamada por ASIN | Sí (SP-API no tiene batch) | Sí |
| Cache | **Sí, con retención configurable** | No |
| Datos cacheados | "Inbound Eligibility/Hazmat" | N/A |
| Fresh en cada scan | **No** — solo product codes y offers | Sí (todo) |

**Lección clave:** PC2 demuestra que cachear eligibility es aceptable para sellers. FBA eligibility cambia raramente (es por ASIN, no por seller ni por momento). Los sellers lo aceptan porque la frecuencia de cambio es baja.

Fuente: `PRICE_CHECKER_2_ANALYSIS.md` líneas 374-390.

---

## 3. Opciones evaluadas

### Opción A: Eliminar FBA Eligibility del Fast Scan

| | |
|---|---|
| **Velocidad** | Máxima mejora (~89% del tiempo eliminado) |
| **Riesgo** | **ALTO** — `best_scenario` en `dual_profit.py:95` depende de `fba_eligible`. Sin él, recomendamos FBA a items que no califican. El seller compra, envía a Amazon, Amazon rechaza. Pérdida de confianza. |
| **Veredicto** | **Descartada** |

### Opción B: Cachear en tabla Product con TTL

| | |
|---|---|
| **Velocidad** | Mejora proporcional a cache hits. Segundo scan de mismos ASINs = 0 calls |
| **Riesgo** | Bajo. FBA eligibility cambia raramente |
| **Problema** | Primer scan de ASINs nuevos sigue siendo lento |
| **Veredicto** | Buena pero incompleta sola |

### Opción C: Subir semáforo fba=1 a fba=5

| | |
|---|---|
| **Velocidad** | ~5x en eligibility (300s → 60s por chunk) |
| **Riesgo** | SP-API FBA Inbound rate limit real es ~30 req/min. Con fba=5 a ~1s/req = 300 req/min, 10x sobre el límite. Provocaría cascada de 429s |
| **Veredicto** | Necesita calibración conservadora |

### Opción D: Cache + Semáforo calibrado (ELEGIDA)

| | |
|---|---|
| **Velocidad** | Primer run: ~3x más rápido en eligibility. Runs posteriores: 0 calls para ASINs conocidos |
| **Riesgo** | Bajo. Cache con TTL 7 días (validado por modelo PC2). Semáforo fba=3 es conservador |
| **Esfuerzo** | 4 archivos modificados, 1 migración |
| **Veredicto** | **Mejor relación impacto/riesgo** |

### Opción E: Post-procesamiento async

| | |
|---|---|
| **Velocidad** | Job "termina" sin eligibility, se enriquece en background |
| **Riesgo** | **ALTO para UX** — seller exporta antes de que termine, tiene `best_scenario` incorrecto. Necesita websockets, estado parcial |
| **Veredicto** | Over-engineering para el problema actual |

---

## 4. Decisión: Opción D

### Por qué

1. **PC2 validó el modelo**: Cachear eligibility con TTL es lo que hace el líder del mercado
2. **No rompe `best_scenario`**: El dato sigue disponible en el momento del cálculo de `dual_profit`
3. **Mejora compuesta**: Cada job enriquece el cache. Con 10 sellers procesando listas con ASINs compartidos (wholesale = mismos proveedores), el cache hit rate sube rápidamente
4. **Esfuerzo contenido**: 4 archivos, 1 migración, sin cambios de API ni UX

### Consumidores de `fba_eligible` (no afectados)

| Archivo | Línea | Uso | Impacto |
|---|---|---|---|
| `dual_profit.py` | 95 | `if item.fba_eligible is False → best_scenario="mfn"` | Ninguno — el dato llega igual, solo cambia la fuente |
| `streamlit_app.py` | 72-74, 371, 468 | Etiquetas visuales | Ninguno |
| `export_service.py` | 27 | Columna "FBA Eligible?" en CSV | Ninguno |
| `api/v1/jobs.py` | 85-86 | Filtro por fba_eligible en query | Ninguno |
| `api/v1/analyze.py` | 57-59 | Single analysis display | Ninguno (no pasa por fast scan) |

---

## 5. Cambios implementados

### 5.1 Modelo Product — cache de FBA eligibility

**Archivo:** `app/models/product.py`

Agregadas 2 columnas:
```python
fba_eligible: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
fba_eligible_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

`fba_eligible_updated_at` permite implementar TTL sin necesidad de un campo `expires_at`. La lógica `(now - updated_at).days < 7` es clara y auditable.

### 5.2 Migración Alembic

**Archivo:** `alembic/versions/227ab05d874c_add_fba_eligible_cache_to_products.py`

Agrega las 2 columnas a la tabla `products`. Operación non-blocking (columnas nullable, sin índice).

### 5.3 Semáforo FBA: 1 → 3

**Archivo:** `app/services/providers/spapi.py:54`

```python
# Antes
"fba": 1,

# Después
"fba": 3,
```

**Justificación:** El rate limit real de SP-API para FBA Inbound Eligibility es ~30 requests/minuto. Con `fba=3` y requests de ~1-2s, estamos en ~1.5-3 req/s = 90-180 req/min. Puede generar algunos 429s, pero el retry con 1s de espera los absorbe sin cascada. Es 3x más rápido que `fba=1` sin ser agresivo.

### 5.4 Cache lookup en fast_scan_processor

**Archivo:** `app/services/fast_scan_processor.py`

**Lógica del cache (reemplaza líneas 234-258 originales):**

1. Para cada ASIN vendible, consultar `Product` en DB
2. Si `fba_eligible` existe y `fba_eligible_updated_at` tiene menos de 7 días → usar cache
3. Si no existe o está vencido → agregar a lista `asins_need_api`
4. Solo llamar `check_fba_eligibility_batch` para `asins_need_api`
5. En el upsert de Product, guardar el resultado nuevo en `fba_eligible` + `fba_eligible_updated_at`
6. Log: `"FBA eligibility: X cached, Y from API"` para monitoreo

**Nota sobre doble `db.get(Product, asin)`:** SQLAlchemy AsyncSession mantiene un identity map por sesión. El segundo `db.get` para el mismo ASIN es un hit al mapa en memoria, no otra query SQL.

### 5.5 Fix de progreso (bonus)

**Archivo:** `app/services/fast_scan_processor.py:149`

```python
# Antes (sobre-reportaba en último chunk)
job.processed_items = (chunk_idx + 1) * CHUNK_SIZE

# Después
job.processed_items = min((chunk_idx + 1) * CHUNK_SIZE, len(unique_asins))
```

---

## 6. Impacto proyectado

### Por chunk de 20 ASINs

| Cuello de botella | Antes | Después (cold cache) | Después (warm cache) |
|---|---|---|---|
| FBA Eligibility | ~300s (fba=1, 20 serial) | ~100s (fba=3, ~7 rondas) | **0s** |
| Catalog 1-por-1 | ~20s | ~20s | ~20s |
| Restrictions | ~8s | ~8s | ~8s |
| Otros (offers, pricing, fees) | ~8s | ~8s | ~8s |
| **Total por chunk** | **~336s (5.6 min)** | **~136s (2.3 min)** | **~36s** |

### Job de 445 ASINs (23 chunks)

| Escenario | Tiempo estimado | vs. antes |
|---|---|---|
| **Antes** | ~7.1 horas | — |
| **Primer run (cold cache)** | ~2.5-3 horas | **-58% a -65%** |
| **Segundo run (warm cache)** | ~30-45 min | **-89% a -93%** |
| **PC2 (referencia)** | ~1.5 min | Aún 20-120x más lento |

### Gap restante con PC2

Seguimos lejos de PC2 (18K/hr). Los próximos cuellos a atacar serían:

1. **Catalog 1-por-1** — SP-API no tiene batch. Opciones: usar Keepa para catalog data en fast scan, o cachear en Product con TTL
2. **Restrictions 1-por-1** — Mismo patrón: cache en Product (per-seller, más complejo)
3. **Progress reporting** — Reportar por fila, no por chunk, para UX responsiva

Estos son cambios más grandes que requieren decisiones de producto separadas.

---

## 7. Cómo verificar que funciona

### Logs esperados

Primer run de un catálogo nuevo:
```
FBA eligibility: 0 cached, 18 from API
```

Segundo run del mismo catálogo:
```
FBA eligibility: 18 cached, 0 from API
```

Run mixto (algunos ASINs nuevos):
```
FBA eligibility: 12 cached, 6 from API
```

### Métricas a monitorear

- **Tiempo total de job**: Debe bajar de ~7h a ~2.5-3h en primer run
- **Cache hit rate de FBA eligibility**: Debería crecer con el tiempo
- **429s en logs de SP-API**: No deberían aumentar significativamente con fba=3
- **`best_scenario` accuracy**: Verificar que items con `fba_eligible=False` (cacheado) siguen siendo `best_scenario="mfn"`

---

## 8. Archivos modificados (implementación original)

| Archivo | Cambio |
|---|---|
| `app/models/product.py` | +2 columnas: `fba_eligible`, `fba_eligible_updated_at` |
| `alembic/versions/227ab05d874c_...py` | Migración para las nuevas columnas |
| `app/services/providers/spapi.py:54` | Semáforo `fba`: 1 → 3 |
| `app/services/fast_scan_processor.py:234-288` | Cache lookup + persist en Product |
| `app/services/fast_scan_processor.py:149` | Fix progreso: `min(...)` en vez de CHUNK_SIZE fijo |

---

## 9. Correcciones post-review (2026-05-29)

Tres revisiones independientes (infraestructura, optimización, SP-API) identificaron 4 problemas en la implementación original. Todos corregidos.

### 9.1 Bug: scope del cache sin marketplace

**Problema:** El cache usaba clave solo `asin`. El endpoint `/fba/inbound/v1/eligibility/itemPreview` requiere `marketplaceIds` y el resultado varía por marketplace (US vs CA vs MX tienen redes de fulfillment distintas). El cache podía contaminar datos entre marketplaces.

**Fix:** Agregada columna `fba_eligible_marketplace` a `Product`. El cache hit ahora requiere `cached.fba_eligible_marketplace == job.marketplace`. El persist guarda `job.marketplace` junto con el resultado.

**Migración:** `3f8a1c29d4e7_add_fba_eligible_marketplace_scope.py`

**Nota:** FBA eligibility es per-ASIN + marketplace, NO per-seller. La restricción per-seller la cubre `check_listing_restrictions`. `(asin, marketplace)` es clave suficiente.

### 9.2 Bug: retry recursivo sin límite

**Problema:** `spapi.py:_request` hacía retry recursivo en 429 con sleep fijo de 1s. El semáforo no se liberaba durante retry (dentro de `async with`), bloqueando todos los slots indefinidamente bajo throttling sostenido.

**Fix:** Reescrito como loop con:
- Max 5 retries
- Backoff exponencial con jitter: `min(2^attempt + random(0,1), 30)`
- Semáforo adquirido/liberado POR intento (sleep fuera del `async with`)
- Log: `"SP-API 429 on %s, retry %d/%d in %.1fs"`

### 9.3 Bug: race condition en upsert Product

**Problema:** 2 jobs procesando el mismo ASIN hacían `db.get()→None→db.add()` simultáneamente, causando `IntegrityError` por PK duplicada en el commit.

**Fix:** El `db.add()` ahora está dentro de `db.begin_nested()` (SAVEPOINT). Si otro job insertó primero, se captura `IntegrityError`, se re-fetch el Product, y se actualiza.

### 9.4 Optimización: bulk preload elimina N+1

**Problema:** Hasta 40 `db.get(Product, asin)` individuales por chunk (cache lookup + upsert).

**Fix:** Un solo `SELECT ... WHERE asin IN (...)` al inicio del chunk. Resultado en dict `existing_products`. Todos los lookups posteriores usan el dict.

### 9.5 Calibración de semáforos SP-API

| Semáforo | Antes | Después | Rate limit real SP-API |
|---|---|---|---|
| `pricing` | 2 | **5** | 10/s burst 20 (estaba al 20%) |
| `offers` | 2 | **1** | 0.5/s burst 1 (estaba SOBRE el límite) |
| `fba` | 3 | **5** | 2/s burst 30 (conservador con burst) |
| `catalog` | 2 | 2 | 2/s burst 2 (correcto) |
| `restrictions` | 5 | 5 | 5/s burst 5 (correcto) |
| `fees` | 1 | 1 | 0.5/s burst 1 (correcto) |

### 9.6 Archivos modificados (correcciones)

| Archivo | Cambio |
|---|---|
| `app/models/product.py` | +1 columna: `fba_eligible_marketplace` |
| `alembic/versions/3f8a1c29d4e7_...py` | Migración marketplace scope |
| `app/services/providers/spapi.py` | Retry con backoff + import random + semáforos recalibrados |
| `app/services/fast_scan_processor.py` | Bulk preload + marketplace en cache + savepoint en upsert + import IntegrityError |
