# DC-12R1-MVP-L1 Pricing and Order Four-Stage Read-Only Discovery

## 1. Decision record

- Baseline: `24a28d76d6d9483d8101f8e0f537c148dc262859`
- Scope: `PRICING-R0`, `PRICING-R1`, `ORDER-PRICE-R1`, `REORDER-R1`
- Shared prerequisite: `ORDER-LIFECYCLE-R0`
- Verification tier: `V1_READ_ONLY_ARCHITECTURE_AND_CONTRACT_DISCOVERY`
- Claim ceiling: `CONTRACT_AND_ARCHITECTURE_RECOMMENDATION_ONLY`
- Product delta: `0`
- Runtime tests: `NOT_RUN_BY_SCOPE`

The four requested contracts are complete as read-only target contracts. They
are not all ready for implementation. The dependency gates below prevent a
team from converting an unresolved business decision into accidental product
semantics.

## 2. Current truth and target gap

| Area | Current baseline | Frozen target | Status |
| --- | --- | --- | --- |
| Base price | No base-price field | `CatalogOffer.base_price` | Missing |
| Customer price | Exact retailer+SKU row only | Retailer+offer override | Migration required |
| Price precedence | Missing special row means unavailable | Override, then base | Missing |
| Price authority | Duplicated route SQL | One server resolver | Missing |
| Order price history | Name/code/qty/price snapshots exist | Stable unit ID plus immutable submitted/final snapshots | Partial |
| Order lifecycle | Service and CRUD both mutate status | One row-locked authority | P1 debt |
| Credit | Outstanding exposure cache only | Enabled, limit, available, overdue, authorization | Decision missing |
| Credit truth | Credit can move order to PAID | Credit authorized is not cash settled | Semantic correction required |
| 24-hour expiry | In-process delayed queue | Database deadline plus durable sweep | Missing |
| Reorder | No endpoint or UI action | Preview then idempotent draft | Missing |

## 3. Accepted product behavior

### Pricing

- A sellable offer has one base price.
- A retailer override wins over the base price.
- Missing both prices means not orderable, never zero price.
- Orders always use server-resolved current prices.
- Historical orders preserve their original submitted price and currency.

### Wholesaler adjustment

- The wholesaler accepts unchanged, rejects, or publishes one adjustment.
- Every changed line shows original value, proposed value, and reason.
- The adjustment changes only this order.
- After publication, the wholesaler cannot edit it or start another round.

### Retailer decision

- The retailer accepts with cash or credit, or rejects.
- Cash acceptance is payment pending until canonical confirmation.
- Credit acceptance requires real policy checks and is not labelled cash paid.
- No decision within 24 hours causes server-authoritative expiration and
  cancellation, with owned resources released idempotently.

### Reorder

- The button pre-fills supplier, stable item, packaging, and quantity.
- The review shows old price, current price, and delta before draft creation.
- Current server price applies; historical price is not guaranteed.
- Unavailable, changed, or legacy-unmatched lines stay visible.

## 4. Four non-negotiable entry gates

### G1. Stable commercial identity

Pricing attaches to a `CatalogOffer`; fulfilment attaches to a stable
`SellableUnit`. The SKU workstream must deliver deterministic migration and
legacy handling before `PRICING-R1` or `REORDER-R1` starts.

### G2. Single lifecycle authority

`CQ-ORD-001` must close. No price-adjustment endpoint may add another direct
`order.status = ...` path.

### G3. Credit policy truth

The CTO must approve exact fields and sources for credit enablement, limit,
available amount, outstanding exposure, and overdue blocking. Unlimited or
hard-coded credit is forbidden.

### G4. Durable deadline truth

The database `expires_at` value and endpoint row-lock check are authoritative.
A restart-safe sweep is required; an in-memory sleep is not sufficient.

## 5. Stage readiness

| Stage | Read-only contract | Implementation readiness | Blocking gate |
| --- | --- | --- | --- |
| PRICING-R0 | Complete | CTO decision ready | Accept offer-layer price identity |
| PRICING-R1 | Complete | Blocked | G1 plus PRICING-R0 acceptance |
| ORDER-PRICE-R1 | Complete | Blocked | G1, G2, G3, G4, PRICING-R1 |
| REORDER-R1 | Complete | Blocked | G1, canonical resolver, snapshot contract |

## 6. Recommended delivery sequence

1. Accept the shared lifecycle and PRICING-R0 contracts.
2. Let the SKU line complete and independently prove stable identities.
3. Implement `PRICING-R1` and prove the single resolver across every consumer.
4. Close credit and deadline prerequisites, then implement
   `ORDER-PRICE-R1`.
5. Implement `REORDER-R1` on the accepted resolver and line identity.
6. Use V3 merge-critical tests for each business slice and V4 independent
   Lubuntu browser/runtime evidence before controlled merge.

## 7. Deliverable map

- Shared state contract:
  `docs/contracts/2026-08-30_order_lifecycle_r0_shared_contract.md`
- Stage contracts:
  `docs/contracts/2026-08-30_pricing_r0_contract.md`,
  `docs/contracts/2026-08-30_pricing_r1_contract.md`,
  `docs/contracts/2026-08-30_order_price_r1_contract.md`, and
  `docs/contracts/2026-08-30_reorder_r1_contract.md`
- Acceptance inventory:
  `docs/test-plans/2026-08-30_pricing_order_four_stage_node_inventory.csv`
- Audit trail:
  `ai-ledger/product-ai/2026-08-30_dc12r1_mvp_l1_pricing_order_four_stage_contract_discovery.md`

## 8. Verdict

`PASS_FOR_CTO_DC12R1_MVP_L1_PRICING_ORDER_R0_D0_READ_ONLY_CONTRACT_DISCOVERY`

This is a contract-discovery verdict only. It is not implementation approval,
merge readiness, release readiness, or deployment approval.
