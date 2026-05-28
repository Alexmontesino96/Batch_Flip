# PM Decision: FBA/MFN Compare — Qué Implementar y Qué No

**Date:** 2026-05-28
**Decision by:** Product Manager analysis based on 3 specialist reviews

---

## Contexto

Tenemos un plan de 8 fases para implementar comparación FBA vs MFN. Somos pre-revenue, sin frontend, sin paying customers, con 10 test sellers. PC2 ($148/mo) NO tiene esta feature — es nuestro diferenciador.

**Pregunta clave:** ¿Qué necesitamos ANTES del primer cliente que paga?

---

## Decisión por Fase

### ✅ IMPLEMENTAR AHORA

| Fase | Qué | Esfuerzo | Por qué |
|------|-----|----------|---------|
| **1 (parcial)** | Definir ROI formula + validación fulfillment_type + comportamiento sin seller connection | 1 día | Cimientos. Si el ROI está mal, todo lo que construimos encima es basura. Decisión de producto, no de ingeniería. |
| **2** | Agregar `fba_eligible` a job_items + migración + expose en response/export | 2 días | Ya lo computamos y lo tiramos. Es dato que el seller necesita para decidir. Sin esto el export está incompleto. |
| **7 (parcial)** | CSV export con columnas: `fba_eligible`, `best_scenario` + assumption text | 1 día | El seller vive en el spreadsheet. Si el CSV no dice "can sell via FBA: yes/no", el tool es inútil. |

**Total: ~4 días de trabajo**

### ⏳ IMPLEMENTAR DESPUÉS DE VALIDAR CON TEST SELLERS

| Fase | Qué | Condición para hacerlo |
|------|-----|----------------------|
| **3 (simplificado)** | Columna JSONB `scenarios` en job_items (NO tabla separada) | Cuando 3+ test sellers digan "quiero ver FBA vs MFN profit side-by-side en batch" |
| **4** | Campos de costo separados FBA/MFN en Job | Junto con Phase 3 en una sola migración |
| **5** | Compare mode en Deep Scan | Cuando Phase 3+4 estén listos. Deep Scan no tiene bottleneck de fees (Keepa es el bottleneck) |

### ❌ DIFERIR / NO IMPLEMENTAR

| Fase | Qué | Por qué NO |
|------|-----|-----------|
| **6** | Compare mode en Fast Scan | Reduce throughput 30-50% (de 31K a ~15K/hr). El valor de Fast Scan ES la velocidad. Compare mode pertenece a Deep Scan donde los datos son más ricos. |
| **8** | Frontend Next.js para compare | No hay frontend. Streamlit es suficiente para validar. Construir UI bonita para un feature no validado es desperdicio. |
| **Stats por escenario** | Avg profit by scenario, profitable count by scenario | Analytics de portfolio. Solo importa después de que el seller haya corrido 10+ batches. |

---

## Decisiones de Producto (requeridas ANTES de código)

### 1. Fórmula de ROI

**Decisión:** Incluir shipping y packaging en el denominador de ROI.

```
ROI = profit / (cost + prep + shipping + packaging)
```

**Razón:** Si excluimos shipping del "capital invertido" en MFN, el ROI de MFN se infla artificialmente vs FBA. El seller toma decisiones de compra basadas en ROI — tiene que reflejar TODO lo que gasta.

**Impacto:** Cambiar la fórmula en `profit_engine.py`. Los ROI de MFN bajarán respecto al cálculo actual.

### 2. Assumption de precio compartido

**Decisión:** Documentar explícitamente que FBA y MFN usan el MISMO Buy Box price.

**Texto visible en resultados:**
> "Both scenarios use the current Buy Box price ($X.XX). Actual MFN prices may be lower to compete without Prime."

**Razón:** Si el seller no sabe esto, creerá que MFN es más profitable de lo que realmente es (porque en la práctica MFN necesita precio más bajo para competir sin Prime).

### 3. Comportamiento sin seller connection

**Decisión:** Si no hay seller connection:
- `can_sell` = null (no verificado)
- `fba_eligible` = null (no verificado)
- Fees = Keepa fallback (no SP-API exactos)
- Mostrar warning: "Connect your Amazon account for eligibility and exact fee data"

---

## Secuencia de Implementación

```
SEMANA 1 (4 días):
  Día 1: Decisión ROI + actualizar profit_engine + validación
  Día 2: fba_eligible en job_items + migración
  Día 3: Export CSV con fba_eligible + best_scenario
  Día 4: Assumption text + tests
  
  → Entregar a test sellers para feedback

DESPUÉS DE FEEDBACK (si validan):
  Semana 2-3: JSONB scenarios + cost profile + Deep Scan compare
  
  → CSV con fba_profit, mfn_profit, best_scenario side-by-side
```

---

## Lo que el Seller Recibe HOY (después de Semana 1)

CSV con estas columnas NUEVAS:

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `fba_eligible` | Yes/No/? | ¿Puede enviarse a FBA? |
| `best_scenario` | FBA/MFN/? | ¿Qué fulfillment es mejor? (basado en profit) |

Columnas EXISTENTES que ya tienen:
- `can_sell` — ¿Puede venderlo?
- `profit`, `roi_pct` — Para el fulfillment seleccionado
- `restriction_reason` — Por qué no puede vender

**Esto ya es más de lo que PC2 ofrece.** PC2 no tiene `fba_eligible` como columna exportable, no tiene `best_scenario`, y no compara FBA vs MFN.

---

## Lo que el Seller Recibiría DESPUÉS (si lo validamos)

CSV con columnas adicionales:

| Columna | Descripción |
|---------|-------------|
| `fba_profit` | Profit si vende via FBA |
| `fba_roi_pct` | ROI via FBA |
| `fba_fees` | Fees totales FBA |
| `mfn_profit` | Profit si vende via MFN |
| `mfn_roi_pct` | ROI via MFN |
| `mfn_fees` | Fees totales MFN |
| `best_scenario` | FBA/MFN/Neither |
| `profit_difference` | Diferencia de profit entre escenarios |

---

## Riesgos Aceptados

| Riesgo | Mitigación | Status |
|--------|-----------|--------|
| ROI bias MFN si shipping excluido | Incluir shipping en ROI denominator | ✅ Decidido |
| Users asumen precio diferente por canal | Texto explícito de assumption | ✅ Decidido |
| Schema debt si bolteamos columnas a job_items | JSONB column como bridge, normalizar después | ✅ Aceptado |
| Fast Scan compare reduce throughput 50% | No implementar en Fast Scan | ✅ Decidido |
| No hay frontend real | Streamlit para validar, Next.js después | ✅ Aceptado |

---

## Métricas de Validación

Antes de invertir en Phases 3-5, necesitamos respuestas de test sellers:

1. "¿Usas MFN para algún producto?" (si 0 de 10 dice sí → no construir compare)
2. "¿Ves fba_eligible en el export?" (si no lo ven → fix UX)
3. "¿Quieres ver profit FBA vs MFN lado a lado?" (si <3 de 10 → diferir)
4. "¿Cambiaría tu decisión de compra?" (si no → no vale la pena)

---

## Resumen Ejecutivo

| | Implementar | Diferir | No Hacer |
|---|------------|---------|----------|
| ROI formula fix | ✅ | | |
| fba_eligible en batch | ✅ | | |
| CSV con best_scenario | ✅ | | |
| Assumption text | ✅ | | |
| JSONB scenarios | | ⏳ validar primero | |
| Deep Scan compare | | ⏳ validar primero | |
| Job cost profile redesign | | ⏳ con scenarios | |
| Fast Scan compare | | | ❌ |
| Stats por escenario | | | ❌ por ahora |
| Next.js compare UI | | | ❌ por ahora |

**Bottom line:** 4 días de trabajo nos dan `fba_eligible` + `best_scenario` en el export — ya superamos a PC2. El resto lo validamos con sellers reales antes de construirlo.
