# FBA/MFN Compare Mode

Date: 2026-05-28  
Status: partial implementation in single-item, not complete in batch

## Executive Summary

The codebase now has a usable `v1` of comparative fulfillment analysis for single-item analysis:

- `/api/v1/analyze` supports comparing `FBA` and `MFN` in one request.
- The response can return a scenario breakdown for both fulfillment modes.
- Streamlit exposes a compare mode with scenario-specific costs.

The implementation is **not complete end-to-end yet**.

What is still missing:

- batch persistence for two scenarios
- scenario-aware exports and stats
- job schemas and migrations for scenario cost profiles
- consistent storage of `fba_eligible`
- tests for fulfillment comparison behavior
- a finalized business definition of ROI and pricing assumptions

The main conclusion is:

- `single-item compare` is a valid `v1`
- `batch compare` needs a data model redesign before implementation

## Product Goal

Support three valid operating modes:

1. `FBA only`
2. `MFN only`
3. `Compare both`

The compare mode should answer:

- Can I sell this ASIN at all?
- Am I eligible for FBA specifically?
- What is the estimated profit in `FBA`?
- What is the estimated profit in `MFN`?
- Which scenario looks better, under the current assumptions?

## What Exists Today

## Single-Item API

Current implementation lives in:

- `app/schemas/analyze.py`
- `app/api/v1/analyze.py`

Current capabilities:

- request supports `compare_fulfillment`
- request supports separate scenario costs:
  - `fba_prep_cost`
  - `shipping_to_amazon`
  - `mfn_prep_cost`
  - `shipping_to_customer`
  - `mfn_packaging_cost`
- response supports:
  - `selected_fulfillment_type`
  - top-level selected-scenario metrics for backward compatibility
  - `profit_scenarios.fba`
  - `profit_scenarios.mfn`
  - `fba_eligible`

Behavior today:

- if `compare_fulfillment=false`, top-level fields behave like legacy single analysis
- if `compare_fulfillment=true`, the endpoint computes both scenarios
- top-level fields still reflect the selected `fulfillment_type`
- exact SP-API fees are fetched separately per scenario when SP-API is available
- compare mode forces seller-specific checks because `fba_eligible` and exact fees matter

## Streamlit Dev UI

Current implementation lives in:

- `streamlit_app.py`

Current capabilities:

- checkbox to compare `FBA` and `MFN`
- separate scenario cost inputs
- side-by-side display of:
  - eligibility
  - fees
  - profit
  - ROI
  - margin

Important caveat:

- Streamlit is a dev/test UI
- it calls providers directly
- it uses environment credentials from `.env`
- it does **not** use the authenticated user flow of the API

That means the API is the correct product path. Streamlit is only a development harness.

## Providers and Data Sources

Relevant files:

- `app/services/providers/base.py`
- `app/services/providers/hybrid.py`
- `app/services/providers/spapi.py`
- `app/services/providers/keepa.py`

### Shared Product Data

`ProductData` already contains the key fields needed for compare mode:

- `can_sell`
- `restriction_reason`
- `restriction_message`
- `fba_eligible`
- `referral_fee_pct`
- `fba_fulfillment_fee`
- `sp_api_total_fees`
- `sp_api_referral_fee`
- `sp_api_fba_fee`
- pricing, velocity, competition, dimensions, reviews

### SP-API Capabilities Already Available

The provider already supports:

- listing restrictions
- FBA inbound eligibility
- fees estimate with `is_fba=True/False`
- competitive pricing
- item offers
- catalog lookup

This is important because compare mode does **not** require a new external integration. The required raw data is already available in the codebase.

### Hybrid Provider Behavior

`HybridProvider` currently enriches data by combining:

- Keepa for historical/velocity/rich product signals
- SP-API for restrictions, fees, pricing, and FBA eligibility

Important detail:

- the existing hybrid fee fetch path is FBA-oriented by default
- for compare mode, exact fees must be fetched per scenario, not reused blindly

The single-item compare implementation already does that correctly in `app/api/v1/analyze.py`.

## Profit Engine: Current Assumptions

Relevant file:

- `app/services/engines/profit_engine.py`

The current engine already supports:

- `shipping_cost`
- `packaging_cost`
- `prep_cost`
- fee rate override
- fixed fee override

This is good enough for compare mode.

The current formula is effectively:

```text
marketplace_fees = sale_price * fee_rate + fee_fixed
gross_proceeds = sale_price - marketplace_fees - shipping_cost - packaging_cost - promo_cost
risk_adjusted_net = gross_proceeds - return_reserve
profit = risk_adjusted_net - cost_price - prep_cost
roi = profit / (cost_price + prep_cost)
margin = profit / sale_price
```

### Current Formula Caveat

The ROI denominator currently excludes:

- shipping
- packaging
- promo

This is a product decision that matters more in `MFN`, because customer shipping is often a major cost component.

Before rolling compare mode through batch, the team should explicitly choose one of these paths:

1. keep the current ROI definition for continuity
2. change ROI to include all direct operational costs in the invested base

If this is not decided explicitly, users may compare `FBA` and `MFN` on a misleading ROI basis.

## Key Business Assumptions

## Assumption 1: Shared Sale Price

Current compare mode uses the same `sale_price` for both scenarios.

That makes the current system a:

- `same market price, different cost structure` comparison

This is acceptable for `v1`, but it must be documented clearly because it is not the same as:

- `expected FBA price vs expected MFN price`

Real-world behavior often differs:

- FBA may sustain a higher winning price
- MFN may need a lower price to compete
- Buy Box share can differ by fulfillment method

Recommended product framing for `v1`:

> Compare mode estimates FBA and MFN profitability using the same current market sale price and different cost/fee assumptions.

## Assumption 2: Eligibility Layers

There are two different questions:

1. `Can I sell this listing at all?`
2. `Can I use FBA for this listing?`

These map to different fields:

- `can_sell`
- `fba_eligible`

This distinction is essential.

Possible states:

- `can_sell=false`, `fba_eligible=null`
  - product is blocked entirely
- `can_sell=true`, `fba_eligible=true`
  - both scenarios are operationally possible
- `can_sell=true`, `fba_eligible=false`
  - MFN may be viable while FBA is not
- `can_sell=null`, `fba_eligible=null`
  - seller-specific checks were not completed

## Gaps Still Open

## 1. Batch Data Model Is Single-Scenario

Relevant files:

- `app/models/job.py`
- `app/models/job_item.py`
- `app/schemas/job.py`

Current batch model only supports one fulfillment profile:

- `fulfillment_type`
- `prep_cost_per_item`
- `shipping_to_amazon`

That is FBA-biased and insufficient for compare mode.

Current `JobItem` only stores one set of profitability outputs:

- `profit`
- `roi_pct`
- `margin_pct`
- `marketplace_fees`

That is the main structural blocker for `batch compare`.

## 2. `fba_eligible` Is Not Persisted in `JobItem`

Relevant files:

- `app/services/providers/base.py`
- `app/services/providers/hybrid.py`
- `app/services/fast_scan_processor.py`
- `app/models/job_item.py`

`fba_eligible` already exists in provider-layer product data.

However:

- `JobItem` does not define an `fba_eligible` column
- `fast_scan_processor` assigns `item.fba_eligible = fba_elig`

This is a correctness issue.

Even before compare mode reaches batch, `fba_eligible` should be added to persistent batch item storage.

## 3. Batch Stats and Export Are Single-Scenario

Relevant files:

- `app/services/export_service.py`
- `app/api/v1/jobs.py`
- `app/schemas/job.py`

Current exports and stats assume one scenario:

- one `profit`
- one `ROI`
- one `marketplace_fees`

Compare mode needs scenario-aware outputs such as:

- `fba_profit`
- `mfn_profit`
- `fba_roi_pct`
- `mfn_roi_pct`
- `fba_eligible`
- `mfn_eligible`
- `best_scenario`

## 4. Batch Pipelines Only Calculate One Scenario

Relevant files:

- `app/services/batch_processor.py`
- `app/services/fast_scan_processor.py`

Both batch pipelines currently decide one marketplace:

- `amazon_fba`
- or `amazon_mfn`

Neither pipeline is designed to:

- compute both scenarios
- persist both scenarios
- return both scenarios

## 5. Fast Scan Throughput Will Change

`fast_scan` is currently optimized around a single profitability path.

Compare mode would add:

- two fee estimates per ASIN instead of one
- reliance on `fba_eligible`
- larger result payloads

This does not make the feature impossible, but it changes throughput expectations and should be treated explicitly in planning.

## Recommended Target Architecture

## Single-Item

The current architecture is good enough.

Keep:

- top-level selected scenario fields for backward compatibility
- nested `profit_scenarios` for compare mode

Add:

- stronger validation
- clearer degraded-mode behavior when seller-specific checks are unavailable
- API tests

## Batch

Do **not** add duplicated columns like:

- `profit_fba`
- `profit_mfn`
- `roi_fba`
- `roi_mfn`

directly to `job_items` unless you want a short-lived patch.

Recommended design:

### `job_items`

Keep only:

- shared product-level data
- status
- seller-independent metrics
- seller restriction summary fields
- `fba_eligible`

### New table: `job_item_scenarios`

Recommended columns:

```text
id
job_item_id
fulfillment_type              # fba | mfn
eligible_to_sell
eligibility_reason
uses_exact_fees
estimated_sale_price
shipping_cost
prep_cost
packaging_cost
return_reserve
marketplace_fees
referral_fee_pct
sp_api_total_fees
sp_api_referral_fee
sp_api_fba_fee
profit
roi_pct
margin_pct
created_at
```

Optional additions:

- `assumed_sale_price_source`
- `is_selected_default`
- `is_best_scenario`

This model scales much better and keeps the code sane.

## Recommended API Contract

## Single-Item Request

Current shape is acceptable for `v1`:

```json
{
  "product_id": "B0F48J2JSP",
  "cost_price": 100,
  "marketplace": "us",
  "fulfillment_type": "fba",
  "compare_fulfillment": true,
  "fba_prep_cost": 0.5,
  "shipping_to_amazon": 0.8,
  "mfn_prep_cost": 0.25,
  "shipping_to_customer": 4.2,
  "mfn_packaging_cost": 0.5,
  "check_restrictions": true
}
```

## Single-Item Response

Current shape is also acceptable for `v1`:

- top-level fields = selected scenario
- nested `profit_scenarios` = comparative detail

## Batch Job Request

Recommended future request shape:

```json
{
  "scan_mode": "deep",
  "marketplace": "us",
  "analysis_mode": "compare",
  "selected_fulfillment_type": "fba",
  "fba_prep_cost": 0.5,
  "shipping_to_amazon": 0.8,
  "mfn_prep_cost": 0.25,
  "shipping_to_customer": 4.2,
  "mfn_packaging_cost": 0.5,
  "seller_connection_id": "...",
  "check_restrictions": true
}
```

Backward compatibility path:

- map legacy jobs to `analysis_mode=single`
- derive their selected scenario from `fulfillment_type`

## Required Implementation Plan

## Phase 1: Harden Single-Item Compare

Goal:

- make current single compare reliable and explicitly defined

Tasks:

1. Validate `fulfillment_type` strictly to `fba|mfn`
2. Decide and document ROI semantics
3. Decide compare behavior when no seller connection exists
4. Add API tests for:
   - FBA profitable, MFN unprofitable
   - MFN profitable, FBA ineligible
   - no restrictions checked
   - no Buy Box price
   - no SP-API available
5. Add explicit docs for the shared-price assumption

Deliverable:

- stable single-item compare mode with test coverage

## Phase 2: Fix Batch Eligibility Storage

Goal:

- remove the current `fba_eligible` inconsistency

Tasks:

1. Add `fba_eligible` to `app/models/job_item.py`
2. Add Alembic migration
3. Populate it in:
   - `batch_processor`
   - `fast_scan_processor`
4. Expose it in:
   - `JobItemResponse`
   - job results
   - export

Deliverable:

- batch items correctly retain FBA eligibility state

## Phase 3: Add Scenario Persistence Model

Goal:

- make batch compare structurally possible

Tasks:

1. Create `job_item_scenarios` model
2. Add Alembic migration
3. Add ORM relationships
4. Add scenario response schemas
5. Decide whether `job_items` should keep a selected scenario summary for convenience

Deliverable:

- normalized scenario persistence layer

## Phase 4: Redesign Job Cost Profile

Goal:

- remove the FBA-biased batch request model

Tasks:

1. Replace `fulfillment_type + shipping_to_amazon` as the only cost profile
2. Add:
   - `analysis_mode`
   - `selected_fulfillment_type`
   - separate FBA and MFN cost fields
3. Migrate legacy records safely
4. Update create-job schema and API validation

Deliverable:

- batch jobs can carry compare-mode cost assumptions

## Phase 5: Implement Compare Mode in Deep Scan

Goal:

- support compare mode in the rich data pipeline first

Tasks:

1. For compare-mode jobs, compute both scenarios per item
2. Fetch exact fees twice:
   - FBA
   - MFN
3. Reuse shared product data
4. Persist scenario rows
5. Keep item-level status independent from scenario profitability

Recommended reason to do deep scan first:

- it already has the richest product context
- compare mode is easier to validate there

Deliverable:

- compare mode working in deep scan jobs

## Phase 6: Implement Compare Mode in Fast Scan

Goal:

- extend compare mode to high-throughput batch jobs

Tasks:

1. Add scenario fee fetches
2. Persist two scenarios
3. Ensure `fba_eligible` remains available
4. Measure throughput impact
5. Decide if compare mode should be limited by plan or scan mode

Deliverable:

- compare mode supported in fast scan with explicit performance expectations

## Phase 7: Results, Stats, and Export

Goal:

- make compare-mode output usable

Tasks:

1. Extend results endpoint to include scenario blocks
2. Update CSV export with prefixed columns:
   - `fba_profit`
   - `fba_roi_pct`
   - `mfn_profit`
   - `mfn_roi_pct`
   - `fba_eligible`
   - `mfn_eligible`
   - `best_scenario`
3. Extend job stats with:
   - profitable count by scenario
   - best-scenario counts
   - avg profit by scenario

Deliverable:

- batch compare results become analytically useful

## Phase 8: Final UI and Productization

Goal:

- make the feature coherent in the user-facing product

Tasks:

1. Bring compare mode into the real frontend, not only Streamlit
2. Explain scenario assumptions in the UI
3. Show FBA-ineligible vs sellable-in-MFN states clearly
4. Add sorting/filtering by scenario
5. Add “best scenario” recommendation

Deliverable:

- complete user-facing compare feature

## Testing Plan

## Unit Tests

Targets:

- scenario cost resolution
- eligibility resolution
- profit calculations for FBA and MFN
- behavior when exact SP-API fees are missing

## Integration Tests

Targets:

- `/api/v1/analyze` with `compare_fulfillment=true`
- seller restrictions on/off
- exact fees per scenario
- `fba_eligible=false` case

## Batch Tests

Targets:

- deep compare job end-to-end
- fast compare job end-to-end
- CSV export with both scenarios
- stats with both scenarios

## Regression Tests

Targets:

- legacy single-fulfillment requests still work
- old batch jobs still render correctly
- old exports remain stable for legacy jobs

## Operational Considerations

## Cost and Rate Limits

Compare mode adds work.

Most important effects:

- two fee estimates instead of one
- FBA eligibility becomes non-optional for a reliable compare
- larger response payloads

Expected impact:

- single-item latency increases modestly
- batch compare is more expensive than batch single-scenario
- fast scan throughput will drop relative to pure single-fulfillment mode

## Recommended Policy

- allow compare mode in single-item by default
- enable compare mode in deep scan first
- roll out compare mode in fast scan only after throughput is measured

## Risks

1. Users may interpret `compare mode` as “expected actual FBA price vs actual MFN price” when it is currently the same-price assumption.
2. ROI semantics may bias MFN comparisons if shipping remains excluded from invested capital.
3. Batch implementation can become messy if scenario data is bolted onto `job_items` instead of normalized.
4. Performance expectations for `fast scan compare` may be unrealistic without explicit communication.

## Recommended Execution Order

1. Harden single-item compare and formalize business rules
2. Add `fba_eligible` persistence to batch items
3. Introduce `job_item_scenarios`
4. Redesign job cost profiles
5. Implement deep scan compare
6. Implement fast scan compare
7. Extend results/export/stats
8. Finish frontend productization

## Final Recommendation

The project should treat `compare FBA vs MFN` as a **scenario-comparison feature**, not as a third fulfillment enum.

That means:

- shared product data
- scenario-specific fee and profit computation
- scenario-specific persistence in batch
- explicit handling of seller eligibility and FBA eligibility

The current single-item implementation is the correct direction.

The next meaningful engineering step is:

- **Phase 2 + Phase 3**

That is:

- persist `fba_eligible`
- add a scenario persistence model for batch

Without those two pieces, the rest of the batch implementation will either be fragile or need to be rewritten later.
