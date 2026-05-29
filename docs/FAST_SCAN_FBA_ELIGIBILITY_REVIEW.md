# Fast Scan FBA Eligibility Optimization Review

Fecha: 2026-05-29

## Scope

Este documento revisa la solucion descrita en `docs/FBA_ELIGIBILITY_OPTIMIZATION.md` y la implementacion actual en:

- `app/services/fast_scan_processor.py`
- `app/services/providers/spapi.py`
- `app/models/product.py`

El foco es `fast scan`, no `deep scan`.

## Executive Summary

La optimizacion actual es valida como mejora tactica, pero no resuelve por si sola el problema de throughput del `fast scan`.

Lo que si hace bien:

- elimina llamadas repetidas de `FBA eligibility` para ASINs ya vistos
- reduce coste de chunks vendibles cuando hay recurrencia de catalogo
- no rompe el pipeline actual ni el calculo de `best_scenario`

Lo que no resuelve:

- jobs muy restringidos siguen lentos aunque `eligibility` no se dispare
- el progreso sigue siendo confuso cuando hay duplicados
- el cache esta modelado con una clave demasiado amplia (`asin` solamente)
- el control de rate limit sigue siendo semaforos de concurrencia, no pacing real

Conclusion: la medida sirve, pero su impacto real es menor que el que proyecta el documento original. El siguiente cuello no es pequeno: `catalog` y `restrictions` siguen siendo el lastre estructural del `fast scan`.

## What Was Validated

Revise:

- `docs/FBA_ELIGIBILITY_OPTIMIZATION.md`
- `app/services/fast_scan_processor.py`
- `app/services/providers/spapi.py`
- `app/models/product.py`
- `app/services/dual_profit.py`
- `app/models/job.py`
- `app/models/seller.py`

Pruebas y verificaciones locales realizadas:

1. `python -m compileall app`
   Resultado: OK

2. Inspeccion de jobs fast reales en la base local
   Evidencia observada:
   - ultimo job fast activo:
     - `total_items=1000`
     - `processed_items=20`
     - `unique_asins=445`
     - `restricted_rows=38`
     - `restricted_unique_asins=20`
   - ultimo job fast completado:
     - `48` ASINs unicos
     - duracion aproximada: `3325s`
     - throughput aproximado: `0.87 rows/min`
     - throughput aproximado: `0.87 unique_asins/min`

3. Validacion del flujo actual del chunk
   Confirmado por codigo:
   - `FBA eligibility` solo corre para ASINs vendibles
   - chunks restringidos pueden ser lentos aunque `eligibility` no corra
   - `processed_items` sigue contando ASINs unicos, no filas

## Current Implementation Summary

### 1. Cache en `Product`

Se agregaron estas columnas en `app/models/product.py`:

- `fba_eligible`
- `fba_eligible_updated_at`

La implementacion actual trata `fba_eligible` como un cache persistente por `asin`.

### 2. Semaforo FBA

En `app/services/providers/spapi.py` el semaforo `fba` paso de `1` a `3`.

### 3. Cache lookup en fast scan

En `app/services/fast_scan_processor.py`:

- se calculan los ASINs vendibles
- se consulta `Product` antes de pegarle a SP-API
- se llama a `check_fba_eligibility_batch()` solo para misses
- el resultado se persiste en `Product`

### 4. Fix parcial de progreso

`processed_items` ahora usa:

```python
min((chunk_idx + 1) * CHUNK_SIZE, len(unique_asins))
```

Esto corrige el sobreconteo del ultimo chunk, pero no corrige la inconsistencia principal entre ASINs unicos y filas.

## Reassessment of the Bottleneck

El documento original asume que `FBA eligibility` era el cuello numero uno en casi todos los casos. Esa conclusion no aguanta bien frente al flujo real del codigo y a los jobs observados.

### Como funciona de verdad el chunk

Por chunk de `20` ASINs unicos, el pipeline hace:

1. `offers` batch: `1` request
2. `competitive pricing` batch: `1` request
3. `catalog`: hasta `20` requests individuales
4. `restrictions`: hasta `20` requests individuales
5. `fees`: hasta `2` requests batch
6. `fba eligibility`: hasta `20` requests individuales

### Caso A: chunk mayoritariamente restringido

Si `restrictions` devuelve `can_sell=False`, el pipeline no llama a `FBA eligibility` para esos ASINs:

- ver `app/services/fast_scan_processor.py`, bloque `sellable`

Entonces el tiempo del chunk lo siguen dominando:

- `catalog` 1x1
- `restrictions` 1x1
- la latencia real y los reintentos de SP-API

Esto es importante porque el ultimo job real observado tenia:

- `20` ASINs unicos ya cerrados
- `38` filas restringidas
- por tanto, el primer chunk era restringido-heavy

Ese chunk no podia estar gastando la mayor parte del tiempo en `FBA eligibility`, porque la propia logica del pipeline lo salta para ASINs no vendibles.

### Caso B: chunk mayoritariamente vendible

Aqui si la optimizacion ayuda bastante:

- `eligibility` corre para cada ASIN vendible
- el semaforo `fba=3` reduce el tiempo en frio
- el cache reduce llamadas repetidas en caliente

Este es el escenario donde la medida tiene mejor retorno.

### Conclusion del cuello real

`FBA eligibility` es un cuello relevante solo en chunks vendibles. No explica por si solo el bajo throughput global del `fast scan`.

Los cuellos estructurales que siguen presentes son:

- `catalog` 1 por 1
- `restrictions` 1 por 1
- falta de rate limiting real
- commits solo al final del chunk
- progreso medido sobre ASINs unicos en vez de filas

## Detailed Review of Each Measure

### Measure 1: Persistir `fba_eligible` en `Product`

Veredicto: buena idea, modelo incompleto.

Pros:

- persistente entre jobs
- bajo coste de implementacion
- no cambia la API externa
- mejora acumulativa cuando hay catalogos repetidos

Problemas:

1. La clave del cache es demasiado amplia.
   - hoy es solo `asin`
   - el pipeline corre con contexto de `marketplace`
   - tambien corre con contexto de seller cuando hay `seller_connection_id`
   - por tanto, la implementacion actual asume implicitamente que `fba_eligible` es global por ASIN

2. Esa asuncion no esta documentada ni validada.
   - si `eligibility` cambia por marketplace, el cache actual puede contaminar datos entre `US`, `CA`, `MX`, etc.
   - si cambia por seller, el riesgo es aun mayor

3. No hay metadatos de origen.
   - falta guardar al menos `marketplace`
   - idealmente tambien `seller_id` o una capa que deje explicito que el cache es global y aceptado como tradeoff

4. `None` no se cachea como estado util.
   - si SP-API falla temporalmente y devuelve `None`, el sistema seguira pagando ese miss en cada run
   - eso evita falsos positivos, pero empeora estabilidad y coste

Mejora recomendada:

- mover el cache a una tabla especifica, por ejemplo:
  - `product_capabilities`
  - o `seller_product_capabilities`
- columnas minimas:
  - `asin`
  - `marketplace`
  - `seller_id` opcional
  - `fba_eligible`
  - `checked_at`
  - `source`
  - `error_state` opcional

### Measure 2: Migracion Alembic

Veredicto: correcta pero minima.

Pros:

- es segura
- agrega columnas nullable
- no rompe datos existentes

Limites:

- el modelo elegido condiciona el problema de scope del cache
- deja metido un dato potencialmente marketplace/seller-aware dentro de una tabla global de producto

No es una migracion mala. El problema no es tecnico; es de modelado.

### Measure 3: Subir `fba` de `1` a `3`

Veredicto: mejora razonable, control incompleto.

Pros:

- reduce el peor caso en frio para chunks vendibles
- es un cambio pequeno y reversible

Problemas:

1. No hay rate limiting real.
   - `app/services/providers/spapi.py` usa `asyncio.Semaphore`
   - eso limita concurrencia, no requests por segundo

2. El retry de `429` es tosco.
   - sleep fijo de `1s`
   - reintento recursivo
   - sin jitter
   - sin backoff exponencial
   - sin lectura de headers de quota si SP-API los expone

3. La mejora puede degradarse sola.
   - si subir a `3` provoca mas `429`, el throughput real puede quedar lejos de la mejora teorica

Mejora recomendada:

- mantener `fba=3` si los logs no muestran una explosion de `429`
- sustituir el modelo de semaforo por pacing real por endpoint
- anadir metricas:
  - `requests`
  - `429_count`
  - `retry_count`
  - `effective_latency_ms`

### Measure 4: Cache lookup dentro del chunk

Veredicto: correcto en idea, ineficiente en DB access pattern.

Pros:

- hace el filtro justo donde se necesita
- mantiene intacta la interfaz del provider

Problemas:

1. Patron N+1 en DB.
   - se hace `db.get(Product, asin)` por cada ASIN vendible
   - despues se hace otro `db.get(Product, asin)` por cada ASIN del chunk al persistir

2. Aunque el `identity map` ayuda, la primera ronda de lecturas sigue costando.

3. No hay preload bulk.
   - deberia hacerse una sola query:
   - `select(Product).where(Product.asin.in_(chunk_asins))`

4. Se mezcla cache lookup con upsert en el mismo bloque operativo sin instrumentacion por fase.

Mejora recomendada:

- precargar `Product` para todo el chunk en una sola query
- construir un `dict[asin, Product]`
- reutilizarlo para:
  - cache lookup
  - upsert
  - persist de resultados

### Measure 5: Fix de progreso

Veredicto: fix parcial; el problema principal sigue.

Lo que si arregla:

- el ultimo chunk ya no sobreconteara si tiene menos de `20` ASINs unicos

Lo que no arregla:

- `processed_items` sigue siendo conteo de ASINs unicos
- `total_items`, `restricted_items`, `matched_items` siguen siendo conteos de filas

Ejemplo real observado:

- `processed_items = 20`
- `restricted_items = 38`

Eso sigue siendo correcto para la maquina, pero malo para la UX. El usuario lee "solo 20 procesados" aunque 38 filas ya tengan estado final.

Mejora recomendada:

- separar metricas:
  - `processed_unique_asins`
  - `processed_rows`
- o redefinir `processed_items` para contar filas realmente cerradas

## Risks and Hidden Assumptions

### 1. Warm-cache economics depend on repeated catalogs

El documento proyecta mucha mejora en segundo run. Eso es cierto solo si:

- los sellers procesan listas con mucho solapamiento de ASINs
- o el mismo seller reprocesa catalogos similares

Si las listas son mas one-off, el hit rate sera bajo y la mejora sera modesta.

### 2. Same TTL for positive and negative eligibility

`True` y `False` usan el mismo TTL de 7 dias.

Eso puede ser aceptable, pero es una decision de negocio, no una verdad tecnica. Si quereis ser mas prudentes:

- `True`: TTL mas largo
- `False`: TTL mas corto

### 3. No proof yet that `fba_eligible` is safely global by ASIN

La implementacion actual lo da por hecho. Si esa suposicion es falsa, el cache compartido ensucia resultados.

### 4. The optimization helps the wrong side of the funnel first

En `fast scan`, primero necesitas decidir si el item es vendible. Muchos catalogos caen antes por `restrictions`. En ese caso, acelerar `eligibility` ayuda poco.

## Additional Measures Needed

Estas son las medidas que realmente completarian la optimizacion del `fast scan`.

### Priority 1: Instrumentacion por fase

Agregar timing por chunk para:

- `offers`
- `catalog`
- `pricing`
- `restrictions`
- `fees`
- `fba_eligibility`
- `db_persist`

Sin esto, cualquier decision posterior sigue siendo parcialmente ciega.

### Priority 2: Bulk preload de `Product`

Reemplazar `db.get()` repetidos por una sola query por chunk.

Impacto esperado:

- menos roundtrips a DB
- menos overhead en el event loop
- codigo mas claro

### Priority 3: Corregir el scope del cache

Opciones:

1. Minimo viable:
   - guardar `fba_eligible_marketplace`
   - o duplicar cache por marketplace

2. Opcion correcta:
   - tabla nueva por `asin + marketplace + seller_id?`

### Priority 4: Rate limiter real

Reemplazar semaforos por un limiter por endpoint con pacing real.

Minimo:

- token bucket o leaky bucket
- backoff exponencial con jitter en `429`

### Priority 5: Cache o degradacion de `restrictions`

`restrictions` sigue siendo una llamada 1x1 muy cara.

Opciones:

- cache corto por seller + marketplace + asin
- modo fast mas agresivo que posponga `restrictions`
- o pipeline de dos fases:
  - fase 1: marketability basica
  - fase 2: seller checks solo para candidatos

### Priority 6: No bloquear el chunk por `catalog`

`catalog` no siempre es critico para decidir si el item vale la pena.

Opciones:

- usar cache fuerte para titulo, brand y dimensiones
- completar `catalog` solo para `matched`
- o hacer enriquecimiento posterior

### Priority 7: Progreso por filas

La UX no mejorara del todo hasta que `processed_items` refleje filas cerradas.

## Suggested Test Plan

### Tests to keep

1. Compilacion:
   - `python -m compileall app`

2. Smoke test de fast scan con duplicados:
   - verificar que `processed_items` y `restricted_items` no se contradicen en UI

### Tests to add

1. Unit test: cache hit
   - `fba_eligible` reciente
   - no debe llamar a SP-API

2. Unit test: cache miss
   - `fba_eligible_updated_at` expirado
   - debe llamar a SP-API

3. Unit test: restricted-only chunk
   - si `can_sell=False`, `check_fba_eligibility_batch()` no debe llamarse

4. Unit test: progress with duplicates
   - `20` ASINs unicos que representan `38` filas
   - validar que la metrica elegida refleje el comportamiento deseado

5. Integration test: cache scope
   - mismo ASIN en dos marketplaces distintos
   - asegurar que no se recicla el dato sin aislamiento

6. Integration test: seller-specific path
   - mismo ASIN con dos sellers distintos
   - al menos validar el comportamiento esperado del modelo elegido

7. Load test de chunk synthetic
   - medir tiempos por fase con:
     - chunk mostly restricted
     - chunk mostly sellable
     - warm cache
     - cold cache

## Recommended Plan

### Phase 1: Medir y corregir lo obvio

- agregar instrumentacion por fase
- bulk preload de `Product`
- arreglar `processed_items` para filas o agregar metrica separada

### Phase 2: Endurecer el cache

- mover `fba_eligible` a un modelo con scope correcto
- documentar TTL y supuestos
- agregar test de aislamiento por marketplace

### Phase 3: Control de quota

- reemplazar semaforos por pacing real
- mejorar manejo de `429`

### Phase 4: Atacar el cuello restante

- cache o defer de `restrictions`
- cache o defer de `catalog`

## Bottom Line

La solucion actual es util, pero hay que leerla como una optimizacion tactica del caso vendible y repetido, no como la solucion del throughput del `fast scan`.

Mi evaluacion final es:

- `cache de fba_eligible`: si
- `semaforo 1 -> 3`: si, con metricas
- `fix de progreso`: insuficiente
- `diagnostico original`: exagera el peso de `eligibility`
- `siguiente prioridad real`: `catalog`, `restrictions`, progreso por filas y pacing real

Si el objetivo es bajar de horas a algo cercano a una experiencia competitiva, esta medida debe quedarse, pero no puede ser la ultima.
