# Phase 3 Execution Directive

Date: 2026-03-31

Author: CTO

## Executive Order

Mpango now enters Phase 3.

Phase 3 is not a broad feature grab. It is a focused effort to make the retailer ordering loop commercially meaningful and operationally supportable.

## CTO Reading Of Current Reality

After reviewing the current repository:

- client product browsing exists
- client order creation exists
- payment read APIs already exist
- inventory adjustment and movement log APIs already exist

However:

- client product price is currently hardcoded to `0.00`
- client order line `unit_price` is currently hardcoded to `0.00`
- retailer identity resolution remains too indirect for long-term scale
- client-visible order state is still a mapped representation rather than a domain-enforced client state model
- retailer product visibility is still global-by-activity, not account-specific catalog control

## CTO Priority Order

### P0 - Pricing System

This is the real blocker for v0.3 commercial validity.

Without pricing:

- retailer orders are not financially meaningful
- AR validation is incomplete
- the product loop is operationally fake

Therefore Phase 3 begins with pricing.

Minimum Phase 3 pricing scope:

- introduce retailer-specific sell price storage
- return real sell price from `GET /client/products`
- write real `unit_price` into `POST /client/orders`
- ensure order totals are based on resolved sell price, not client-supplied price

Recommended MVP data model:

- `retailer_prices`
  - `retailer_id`
  - `sku_id`
  - `price`
  - optional timestamps / audit metadata

CTO rule:

- do not build a complex rule engine first
- do not start with promotions or discount campaigns
- start with explicit retailer-to-SKU pricing records

### P1 - Payments Operational Visibility

The backend already exposes payment read endpoints, so this is not a greenfield backend task.

Phase 3 objective here:

- verify `GET /payments`
- verify `GET /payments/{id}`
- connect frontend usage where needed
- ensure finance workflows are not blind in practice

### P2 - Inventory Operational Maintainability

The backend already exposes inventory adjustment and movement-log endpoints.

Phase 3 objective here:

- verify `POST /inventory/adjust`
- verify `GET /inventory/logs`
- ensure UI and operational workflow actually use them

## Deferred But Tracked Risks

These are real, but not the Phase 3 entry point.

### Deferred Risk 1 - Retailer Identity Resolution Chain

Current path is too long and should later move toward direct retailer claims in JWT.

Target direction:

- JWT -> `retailer_id`

Status:

- Phase 4 optimization
- not a Phase 3 blocker unless reliability issues surface immediately

### Deferred Risk 2 - Client Order State Model

Current client status is a mapped view of internal states.

Target direction:

- stronger service-side transition enforcement
- clearer transition guards

Status:

- acceptable for now
- revisit after pricing lands

### Deferred Risk 3 - Catalog Scope

Current retailer catalog visibility is too broad for real CRM/pricing strategy.

Target direction:

- customer-specific sellability and visibility
- customer-specific price and SKU access

Status:

- Phase 3 should prepare for this, but not solve full CRM segmentation yet

## Team Instructions

### Backend AI

Primary Phase 3 owner.

Immediate tasks:

1. Add MVP retailer pricing model and migration
2. Add CRUD/service/repository support as needed
3. Update client products endpoint to resolve price
4. Update client order creation to persist resolved `unit_price`
5. Add tests proving price resolution and order total integrity

Do not do yet:

- promotions engine
- tiered discount DSL
- full catalog segmentation engine

### Frontend AI

Support the backend pricing rollout.

Immediate tasks:

1. show real product prices in retailer client views
2. show line subtotal and order total with real values
3. integrate payment and inventory operational screens only where already backed by API

Do not invent pricing logic in frontend.

### Reviewer AI

Focus review on:

- server-side price authority
- tenant safety
- no client-controlled price injection
- migration correctness
- backward compatibility

### OPS AI

Prepare validation flow, not new infra.

Immediate tasks:

1. ensure pricing migration can be applied safely
2. verify health and boot after migration
3. support end-to-end validation path for retailer order with non-zero price

## Acceptance Criteria For Phase 3

Phase 3 is complete when:

1. retailer can browse products with real price
2. retailer can place order with non-zero `unit_price`
3. stored order totals reflect server-side pricing
4. payment read flows are verified usable
5. inventory adjustment and log flows are verified usable
6. no tenant isolation or pricing authority regression is introduced

## Final CTO Constraint

This phase must preserve single-focus discipline.

Do not let Phase 3 dissolve into:

- platform work
- speculative scaling
- catalog-rule overengineering
- payment gateway integration
- broad UX polishing detached from real business validity
