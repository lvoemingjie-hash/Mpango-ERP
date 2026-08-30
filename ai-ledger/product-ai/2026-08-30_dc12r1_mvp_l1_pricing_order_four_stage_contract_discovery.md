# DC-12R1-MVP-L1 Pricing and Order Four-Stage Contract Discovery

## 1. Metadata

- Task: `DC-12R1-MVP-L1-PRICING-ORDER-R0-D0`
- Executor: Windows Codex CTO
- Baseline: `24a28d76d6d9483d8101f8e0f537c148dc262859`
- Branch: `codex/dc12r1-mvp-l1-pricing-order-four-stage-contract-discovery-2026-08-30`
- Verification tier: `V1_READ_ONLY_ARCHITECTURE_AND_CONTRACT_DISCOVERY`
- Claim ceiling: `CONTRACT_AND_ARCHITECTURE_RECOMMENDATION_ONLY`
- Product delta: `0`
- Runtime execution: `NOT_RUN_BY_SCOPE`

## 2. Requested stages

This round covers the next four planned stages:

1. `PRICING-R0`
2. `PRICING-R1`
3. `ORDER-PRICE-R1`
4. `REORDER-R1`

`ORDER-LIFECYCLE-R0` is treated as their shared contract prerequisite rather
than a fifth implementation stage.

## 3. Source facts established

### Pricing

- Existing pricing is special-price-only: tenant-local retailer plus SKU.
- No base-price field or fallback exists.
- Missing special price makes the item non-orderable.
- Client and wholesaler order routes duplicate price-resolution logic.
- Current pricing UI exposes only customer prices and hard-codes KES.

### Order identity and history

- Migration 003 intentionally removed `product_id` and retained snapshots.
- Current line identity for downstream stock work is still `sku_code`.
- New work needs stable sellable-unit identity plus immutable snapshots.
- Legacy rows cannot be truthfully backfilled from mutable codes.

### Lifecycle and finance

- `OrderService` claims sole lifecycle authority, but CRUD and routes still
  write status directly.
- Domain and CRUD disagree on draft cancellation (`VOIDED` vs `CANCELLED`).
- Credit currently marks an order `PAID` while retaining receivable exposure.
- Binding data contains outstanding exposure but no limit or overdue policy.
- Payment declarations are intentionally non-accounting until confirmed.

### Time and background jobs

- The local queue persists records but delayed execution uses in-process
  `asyncio.sleep`.
- A database deadline and endpoint-side expiry check are therefore required;
  a delayed worker cannot be the 24-hour authority.

## 4. CTO architecture decisions recorded

1. Price attaches to `CatalogOffer`, with `RETAILER_OVERRIDE > BASE_PRICE`.
2. All price consumers use one server resolver; clients never submit price.
3. New order lines keep stable sellable-unit identity and immutable historical
   snapshots; legacy identity remains nullable and explicit.
4. Commercial decision, operational lifecycle, and settlement/credit are
   separate semantic axes.
5. Credit authorization is not cash payment and must not be presented as paid.
6. One wholesaler adjustment only; retailer accepts or rejects; no multi-round
   bargaining.
7. Adjustment expiry is exactly 24 hours from server publication and remains
   enforceable even when a worker is late or restarts.
8. Reorder copies identity, packaging, and quantity into a review flow, but
   resolves current server prices and never guarantees historical price.
9. Order adjustment never silently changes catalog or customer pricing.

## 5. Blocking decisions and debt

- `CQ-ORD-001`: dual order lifecycle authority must close before
  `ORDER-PRICE-R1`.
- Stable catalog/sellable-unit/offer identity must be accepted before
  `PRICING-R1` or `REORDER-R1` implementation.
- Credit policy must define enabled state, limit, available calculation,
  overdue authority, and atomic exposure mutation.
- Durable expiration sweep must be designed; `LocalJobQueue` delay alone is
  insufficient.
- Legacy pricing migration must fail closed on ambiguous SKU-to-offer mapping.

## 6. Deliverables

- `docs/planning/2026-08-30_pricing_order_four_stage_contract_discovery.md`
- `docs/contracts/2026-08-30_order_lifecycle_r0_shared_contract.md`
- `docs/contracts/2026-08-30_pricing_r0_contract.md`
- `docs/contracts/2026-08-30_pricing_r1_contract.md`
- `docs/contracts/2026-08-30_order_price_r1_contract.md`
- `docs/contracts/2026-08-30_reorder_r1_contract.md`
- `docs/test-plans/2026-08-30_pricing_order_four_stage_node_inventory.csv`
- this ledger

The node inventory contains only future acceptance obligations. Every node is
`NOT_RUN_CONTRACT_ONLY`; this round makes no runtime PASS claim.

## 7. Recommended execution sequence

1. CTO accepts `ORDER-LIFECYCLE-R0` and `PRICING-R0` decisions.
2. Merge independently reviewed SKU stable-identity work.
3. Implement and independently verify `PRICING-R1`.
4. Close lifecycle, credit-policy, and durable-expiry prerequisites, then
   implement `ORDER-PRICE-R1`.
5. Implement `REORDER-R1` against the accepted identity and resolver.
6. Run risk-tiered backend, frontend, browser, and independent Lubuntu gates
   before each controlled merge.

## 8. Verdict

`PASS_FOR_CTO_DC12R1_MVP_L1_PRICING_ORDER_R0_D0_READ_ONLY_CONTRACT_DISCOVERY`

This verdict approves only the completeness of the read-only discovery output.
It does not approve implementation, migration, merge, release, or deployment.
