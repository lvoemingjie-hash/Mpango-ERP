# DC-12R1-MVP-L1 ORDER-LIFECYCLE-R0 Shared Contract

Status: `CTO_READ_ONLY_CONTRACT_DISCOVERY`

Baseline: `24a28d76d6d9483d8101f8e0f537c148dc262859`

Verification tier: `V1_READ_ONLY_ARCHITECTURE_AND_CONTRACT_DISCOVERY`

Claim ceiling: `CONTRACT_AND_ARCHITECTURE_RECOMMENDATION_ONLY`

This document is the shared prerequisite for `PRICING-R0`, `PRICING-R1`,
`ORDER-PRICE-R1`, and `REORDER-R1`. It does not authorize product edits,
migrations, runtime execution, merge, or deployment.

## 1. Why a shared contract is mandatory

The current tree contains two incompatible order authorities:

- `backend/services/order_service.py:53` says all transitions must pass through
  `OrderService.transition`, with row locking, a state matrix, invariants, and
  ledger effects.
- `backend/crud/order.py:387`, `backend/crud/order.py:422`,
  `backend/crud/order.py:457`, `backend/crud/order.py:495`, and
  `backend/crud/order.py:530` mutate order status directly.
- `backend/core/domain/order_state.py:49` allows `DRAFT -> VOIDED`, while
  `backend/crud/order.py:495` allows a draft order to become `CANCELLED`.

Price negotiation, timeout cancellation, credit acceptance, and reorder must
not be built on this dual authority. `CQ-ORD-001` is therefore a P1 MVP
prerequisite, not optional cleanup.

The current order-line identity is also insufficient:

- Migration `003_phase_b3_orders_minimal_closed_loop.py:62` deliberately moved
  order lines to product snapshots and removed `product_id`.
- `backend/models/order.py` and order creation currently persist `sku_code`
  plus name, quantity, and unit-price snapshots.
- Inventory reservation resolves the mutable code again at
  `backend/services/inventory_service.py:96`.

New order lines must use the stable sellable-unit identity accepted by the SKU
workstream while retaining immutable snapshots. Legacy rows remain explicitly
legacy; no migration may guess identity from `sku_code`.

## 2. Canonical semantic axes

One overloaded status field cannot truthfully represent commercial review,
fulfilment, and settlement. The target contract separates three axes.

### 2.1 Operational lifecycle

`DRAFT -> CONFIRMED -> FULFILLED -> RETURNED`

Terminal pre-fulfilment outcomes use `VOIDED`; post-confirmation cancellation
uses `CANCELLED`. A reason code is mandatory for either terminal outcome.

### 2.2 Commercial decision

Allowed values:

- `ORIGINAL_PRICE_PENDING`
- `AWAITING_RETAILER_CONFIRMATION`
- `ORIGINAL_PRICE_ACCEPTED`
- `ADJUSTMENT_ACCEPTED`
- `RETAILER_REJECTED`
- `PRICE_CONFIRMATION_EXPIRED`

Only one formal wholesaler adjustment is allowed in MVP. Once published, the
wholesaler cannot edit or replace it.

### 2.3 Settlement or credit truth

Allowed semantic values:

- `UNSETTLED`
- `PAYMENT_PENDING`
- `PARTIALLY_SETTLED`
- `SETTLED`
- `CREDIT_AUTHORIZED`
- `CREDIT_BLOCKED`

`CREDIT_AUTHORIZED` is not `PAID`. The current implementation records a full
credit payment and moves the order to `PAID` while retaining receivable
exposure (`backend/services/canonical_payment_service.py:279` and
`backend/services/order_service.py:264`). That compatibility behavior must not
become the target product contract or user-facing truth.

The implementation may initially project these axes through compatibility
columns, but every stored and returned state must map without ambiguity. No UI
or API may describe credit exposure as cash received.

## 3. Business state transitions

| Actor | Action | Preconditions | Atomic result |
| --- | --- | --- | --- |
| Retailer | Submit order | All lines resolve to active offers and server prices | Operational `DRAFT`; immutable submitted snapshots |
| Wholesaler | Accept unchanged | `DRAFT`, no adjustment | Reserve stock; operational `CONFIRMED`; commercial `ORIGINAL_PRICE_ACCEPTED` |
| Wholesaler | Publish one adjustment | `DRAFT`, no prior adjustment | Persist revision, reserve proposed quantities, set deadline and `AWAITING_RETAILER_CONFIRMATION` |
| Wholesaler | Reject | `DRAFT`, no accepted decision | `VOIDED` with explicit wholesaler-rejection reason |
| Retailer | Reject adjustment | Awaiting and before deadline | `VOIDED`, commercial `RETAILER_REJECTED`, release reservation |
| Retailer | Accept with cash | Awaiting and before deadline | Materialize accepted snapshots, operational `CONFIRMED`, settlement `PAYMENT_PENDING`; no canonical payment yet |
| Retailer | Accept on credit | Awaiting, before deadline, credit checks pass | Materialize accepted snapshots, operational `CONFIRMED`, settlement `CREDIT_AUTHORIZED`, receivable exposure atomically recorded |
| Server | Expire | Awaiting and `now >= expires_at` | `VOIDED`, commercial `PRICE_CONFIRMATION_EXPIRED`, release reservation and transient intents |

For compatibility with the agreed product language, APIs may expose derived
workflow labels `CANCELLED_RETAILER_REJECTED`,
`CANCELLED_PRICE_CONFIRMATION_EXPIRED`, `PAYMENT_PENDING`, and
`CONFIRMED_ON_CREDIT`. They are projections, not a second mutable authority.

## 4. Concurrency and time authority

- Every state-changing command locks the order and current revision.
- Every command carries `expected_order_version`; stale versions return a
  structured `409 ORDER_VERSION_CONFLICT` and perform zero writes.
- The adjustment deadline is an absolute UTC database value set exactly once
  when the revision is published.
- `now >= expires_at` is expired. Retailer actions must enforce this while
  holding the row lock, even if a background worker is delayed.
- A durable sweep may materialize expiration using `FOR UPDATE SKIP LOCKED`,
  but it is never the source of deadline truth.
- `LocalJobQueue` uses in-process `asyncio.sleep` at
  `backend/core/jobs/local_queue.py:270`; it is not sufficient as the sole
  24-hour expiry authority.
- Commands are idempotent by actor, order, revision, action, and idempotency
  key. A replay returns the original result; a key reused for another request
  fails closed.

## 5. Inventory and financial boundaries

- Stock is reserved against stable sellable-unit identity, never re-resolved
  from a mutable display code.
- Adjustment publication reserves the proposed final quantity for the 24-hour
  response window. Failure to reserve blocks publication.
- Rejection, expiration, and cancellation release only reservations owned by
  that order and revision, idempotently.
- Cash acceptance may create a pending declaration or payment intent but has
  zero accounting effect until the canonical receipt/confirmation path runs.
- Credit acceptance requires a separate policy decision: enabled flag, limit,
  available amount, outstanding exposure, and overdue block. The current
  binding has only `outstanding_balance` (`backend/models/binding.py:75`), so
  the agreed credit checks cannot yet be implemented truthfully.
- A credit authorization must create receivable truth without posting cash.

## 6. RBAC boundary

- Wholesaler price decisions use `orders:update`.
- Catalog and customer price maintenance use `pricing:read` and
  `pricing:write`.
- Retailer create, reorder, accept, and reject operations use the client order
  capability family. The existing exact codes are `client:orders:read` and
  `client:orders:create` (`backend/alembic/versions/036_retailer_mvp_identity.py:57`).
- A cash declaration uses `client:payments:declare`; it must not be smuggled
  through a generic order permission.
- Retailer routes always derive retailer and wholesaler identity from the
  authenticated binding. Request bodies cannot select another retailer.

## 7. Required closure before implementation

1. Select one mutation authority and remove direct lifecycle writes outside it.
2. Accept the three-axis state semantics and the compatibility projection.
3. Freeze the credit policy fields and overdue source of truth.
4. Merge a stable sellable-unit identity contract; legacy rows remain nullable
   and marked `legacy`, with no code-based guessed backfill.
5. Approve a durable expiry sweep design whose correctness does not depend on
   an in-memory delay.

Until these are accepted, `ORDER-PRICE-R1` remains `BLOCKED_BY_SHARED_CONTRACT`.
