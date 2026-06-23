# S4-E2: Stock Reservation Lifecycle Production Fix

| Field | Value |
|-------|-------|
| Date | 2026-06-23 |
| Branch | `opencode/s4e2-stock-reservation-lifecycle-fix-2026-06-23` |
| Base | `origin/product-dev-recovered` @ `7c660d4` (`merge: S4-D inventory movement ledger integrity gate`) |
| Commit | Pending until branch push; final commit is reported in handoff because the commit hash cannot be embedded in the same commit that creates this ledger. |
| Verdict | PASS_FOR_CTO_REVIEW |

---

## Changed Files

Production code:

- `backend/services/inventory_service.py`
- `backend/api/v1/orders.py`
- `backend/api/v1/client/orders.py`

Tests and ledger:

- `backend/tests/business/test_s4e_stock_reservation_lifecycle_audit.py`
- `ai-ledger/product-ai/2026-06-23_s4e2_stock_reservation_lifecycle_fix.md`

No migration, frontend, or deployment files were changed.

---

## Implementation Summary

- Added locked `InventoryService._locked_stock_by_sku_code()` helper using `SELECT FOR UPDATE` and `populate_existing=True`.
- Added `InventoryService.reserve_on_confirm()` to reserve available stock without writing `InventoryMovement`.
- Added `InventoryService.release_on_cancel()` to release reserved stock without writing `InventoryMovement`.
- Updated `InventoryService.deduct_on_fulfillment()` so fulfillment deducts `quantity_on_hand` and consumes aggregate reservation only when the caller explicitly passes `consume_reservation=True`.
- Wired admin `confirm_order()` to reserve stock after status transition inside the same request transaction.
- Wired admin `cancel_order()` and retailer/client `cancel_order()` to release reservation when cancelling confirmed orders.
- Wired admin `fulfill_order()` to pass `consume_reservation=True` only for route-transitioned orders with an existing `updated_by` marker. Direct seeded `paid` compatibility rows do not consume aggregate reservation.
- Added rollback handling around reservation/release route work so failed reservation/release does not leave partial order status or stock changes.
- Did not modify `OrderService.transition()`.

---

## R1 Review Finding and Fix

Reviewer finding:

- Direct-paid/no-reservation fulfillment could incorrectly consume aggregate `quantity_reserved` that belonged to another confirmed order on the same SKU.
- Example: order A reserves `3`; unrelated direct `paid` order B fulfills `3`; the first implementation decremented aggregate reserved from `3` to `0`, stealing A's reservation.

R1 fix:

- Added `consume_reservation` to `InventoryService.deduct_on_fulfillment()`, defaulting to `False`.
- Fulfillment now deducts `quantity_on_hand` for all valid paid orders.
- Fulfillment consumes aggregate `quantity_reserved` only when the admin route has an existing route-transition marker (`order.updated_by is not None`).
- Direct seeded `paid` rows, including backward-compatible/no-reservation orders, preserve unrelated aggregate reservations.
- Added regression `test_direct_paid_fulfillment_preserves_unrelated_confirmed_reservation`.

R1 residual limitation:

- `updated_by` is transition evidence, not per-order reservation ownership. The schema still cannot prove which order owns an aggregate reserved quantity.
- S4-E3 should introduce a per-order reservation ledger/table if exact ownership, partial reservations, or migration-safe historical fulfillment are required.

---

## GitNexus Impact Summary

Pre-change GitNexus checks were run before production edits.

- `InventoryService.deduct_stock` / indexed as `deduct_stock`: LOW risk, no upstream production callers detected.
- `InventoryService.deduct_on_fulfillment` / indexed as `deduct_on_fulfillment`: LOW risk, direct upstream caller is `fulfill_order`.
- `InventoryService.restock_on_return` / indexed as `restock_on_return`: LOW risk, direct upstream caller is `return_order`.
- `confirm_order`: LOW risk. Ambiguous impact resolved to CRUD `confirm_order`; direct upstream caller is API `backend/api/v1/orders.py:confirm_order`. Context confirmed API route handler.
- `cancel_order`: LOW risk. Ambiguous impact resolved to CRUD `cancel_order`; direct upstream callers include admin and client API cancel handlers. Context confirmed admin API route handler.
- `fulfill_order`: LOW risk. Ambiguous impact resolved to CRUD `fulfill_order`; context confirmed API `fulfill_order` calls `OrderService.transition()` and `InventoryService.deduct_on_fulfillment()`.
- `OrderService.transition` / indexed as `transition`: HIGH risk. Direct callers include `pay_order`, `fulfill_order`, `return_order`, seed data, and S5 tests. It was not modified.

Final `gitnexus_detect_changes(scope="staged")`:

- Risk: HIGH.
- Changed files: 4.
- Changed symbols: 73.
- Affected processes: 10.

Reason:

- Production route/service files are indexed broadly, so GitNexus attributes changes to adjacent order, client order, return, and adjustment flows.
- Manual line-level review: behavioral production changes are scoped to confirm reservation, cancel release, client cancel release, and fulfillment reservation consumption. `OrderService.transition()` and movement ledger semantics were not changed.

---

## Exact Test Results

S4-E2 target suite:

```text
poetry run pytest tests/business/test_s4e_stock_reservation_lifecycle_audit.py -q -rxX --tb=short
14 passed, 24 warnings
```

S4/S4-B/S4-C/S4-D/S4-E regression:

```text
poetry run pytest tests/business/test_s4_order_fulfillment_inventory_invariants.py tests/business/test_s4b_inventory_reversal_invariants.py tests/business/test_s4c_concurrent_fulfillment_oversell_invariants.py tests/business/test_s4d_inventory_movement_ledger_integrity.py tests/business/test_s4e_stock_reservation_lifecycle_audit.py -q --tb=short
43 passed, 55 warnings
```

S5/Phase5 regression:

```text
poetry run pytest tests/test_s5_order_state_machine.py tests/test_phase5_order_payment.py -q --tb=short
66 passed, 1 xfailed, 45 warnings
```

The remaining `1 xfailed` is pre-existing in Phase5 payment tests and is not introduced by S4-E2.

Environment note:

- Final test runs used explicit local env values from running containers without printing secrets:
  - `POSTGRES_HOST=127.0.0.1`
  - `POSTGRES_PORT=5432`
  - `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` from `mpango_postgres`
  - `REPORTING_USER_PASSWORD` from `mpango_prod_backend`
  - `REDIS_URL=redis://127.0.0.1:6379/0`
  - `DATABASE_URL` and `TEST_DATABASE_URL` unset

Hygiene:

```text
git diff --check
PASS
```

```text
Changed-file mojibake / non-ASCII scan
PASS
```

---

## Reservation Invariant Results

### 1. Confirm reserves stock and reduces available

PASS.

- Confirming quantity `3` on stock `10` keeps `quantity_on_hand=10`, sets `quantity_reserved=3`, and makes available `7`.

### 2. Confirm insufficient available fails closed

PASS.

- Confirming quantity `3` on stock `2` returns `409` with `INSUFFICIENT_AVAILABLE_STOCK`.
- The order remains `draft` and stock remains unchanged.

### 3. Concurrent confirm with limited stock

PASS.

- Two concurrent draft orders each requesting all available stock produce at most one confirmation success.
- Final stock is `on_hand=5`, `reserved=5`, `available=0`; the loser remains `draft`.

### 4. Duplicate confirm idempotency

PASS.

- Repeating confirm on an already confirmed order raises an invalid-state response and does not double reserve.

### 5. Cancel releases reservation exactly once

PASS.

- Cancelling a confirmed order releases the reservation and restores available stock without changing on-hand.

### 6. Duplicate cancel does not double release

PASS.

- Repeating cancel on a cancelled order raises an invalid-state response and leaves stock unchanged.

### 7. Fulfill consumes reservation and deducts on-hand

PASS.

- Confirm -> pay -> fulfill changes stock from `on_hand=10,reserved=3,available=7` to `on_hand=7,reserved=0,available=7`.

### 8. Direct paid/no-reservation fulfillment still works

PASS.

- A paid order without prior reservation deducts on-hand and keeps reserved at `0`, never negative.

### 9. Direct paid fulfillment preserves unrelated reservation

PASS.

- A confirmed order's reserved quantity remains intact when an unrelated direct `paid` order for the same SKU is fulfilled.
- The direct `paid` fulfillment changes stock from `on_hand=10,reserved=3,available=7` to `on_hand=7,reserved=3,available=4`.

### 10. Return restores on-hand and creates no reservation

PASS.

- Return restores `quantity_on_hand` and leaves `quantity_reserved=0`.

### 11. Reservation tenant isolation

PASS.

- Tenant A confirm reserves only tenant A stock.
- Shadow tenant stock with the same SKU id/code remains unchanged.

### 12. Reserve/release writes no InventoryMovement

PASS.

- Confirm reservation and cancel release write no physical movement entries.
- Deduction/restock/adjustment movement semantics remain covered by S4-D.

### 13. S4/S4-B/S4-C/S4-D regression

PASS.

- Existing inventory fulfillment, reversal, concurrent fulfillment, and movement ledger invariant suites remain green.

---

## Rollback Semantics

- `confirm_order()` performs status transition and stock reservation in the same request transaction. Reservation failure triggers `db.rollback()`, leaving the order in its previous state.
- `cancel_order()` performs status transition and reservation release in the same request transaction. Release failure triggers `db.rollback()`, leaving the order in its previous state.
- `fulfill_order()` keeps the S4-C2 fail-closed path: inventory shortage/SKU failures rollback the transition and any partial deductions.
- Reserve/release do not write `InventoryMovement`, so rollback cannot leave orphan physical movement rows for reservation operations.

---

## Xfail Status

- S4-E target suite has no xfails.
- The prior S4-E1 strict xfail invariants are now normal passing tests in this branch.
- Full S4/S4-B/S4-C/S4-D/S4-E regression has no xfails.
- S5/Phase5 retains one pre-existing xfail unrelated to S4-E2.

---

## Remaining Risks

- The current schema has aggregate `quantity_reserved` only; it does not have per-order reservation rows. S4-E2 therefore releases/consumes aggregate reservation quantities and cannot attribute reservations to individual orders beyond route-transition evidence.
- R1 avoids direct seeded `paid` orders stealing unrelated reservations, but `updated_by` is not a reservation ownership record. S4-E3 should add an explicit per-order reservation ledger/table before supporting precise ownership, partial fulfillment allocation, or historical migration reconciliation.
- Client order creation still validates visible physical `quantity_on_hand`; final oversell protection is enforced at confirm reservation time.

---

## Constraint Confirmations

- Product code changed: YES, listed above.
- Migration changed: NO.
- Frontend changed: NO.
- Deployment: NO.
- Pushed `product-dev-recovered`: NO.
- `OrderService.transition()` changed: NO.
- Existing S4/S4-B/S4-C/S4-D tests deleted, skipped, or relaxed: NO.
- Reservation writes to `InventoryMovement`: NO.
- Secrets printed: NO.
