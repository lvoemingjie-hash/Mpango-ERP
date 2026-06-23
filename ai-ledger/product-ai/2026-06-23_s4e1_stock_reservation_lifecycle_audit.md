# S4-E1: Stock Reservation Lifecycle Audit Gate

| Field | Value |
|-------|-------|
| Date | 2026-06-23 |
| Branch | `opencode/s4e1-stock-reservation-lifecycle-audit-2026-06-23` |
| Base | `origin/product-dev-recovered` @ `7c660d4` (`merge: S4-D inventory movement ledger integrity gate`) |
| Commit | Pending until branch push; final commit is reported in handoff because the commit hash cannot be embedded in the same commit that creates this ledger. |
| Verdict | NEEDS_S4E2_PRODUCTION_FIX |

---

## Changed Files

- `backend/tests/business/test_s4e_stock_reservation_lifecycle_audit.py`
- `ai-ledger/product-ai/2026-06-23_s4e1_stock_reservation_lifecycle_audit.md`

No production, migration, frontend, or deployment files were changed.

---

## Audit Scope

S4-E1 audits the lifecycle of:

- `InventoryStock.quantity_on_hand`
- `InventoryStock.quantity_reserved`
- `available = quantity_on_hand - quantity_reserved`

The audit uses real tenant DB sessions and real order route handlers for confirm, cancel, fulfill, and return flows. No mocks are used.

Strict xfails in this file are intentional audit findings. They expose missing reservation lifecycle behavior and should become normal passing tests in S4-E2 after production implementation.

---

## GitNexus Impact And Context Summary

Pre-audit GitNexus checks were run after indexing the clean S4-E1 worktree.

- `InventoryService.deduct_stock`: LOW risk, no upstream production callers detected. Context confirms this method increments `quantity_reserved`, but current order flows do not call it.
- `InventoryService.deduct_on_fulfillment`: LOW risk, direct upstream caller is `fulfill_order`.
- `InventoryService.restock_on_return`: LOW risk, direct upstream caller is `return_order`; affected process is return.
- `fulfill_order`: LOW risk, no upstream callers detected with tests excluded. Context shows it calls `OrderService.transition` and `InventoryService.deduct_on_fulfillment`.
- `cancel_order`: LOW risk, no upstream callers detected with tests excluded.
- `OrderService.transition` / indexed as `transition`: HIGH risk. Direct callers include `pay_order`, `fulfill_order`, `return_order`, seed data, and multiple S5/S5 ledger tests. This is recorded only; S4-E1 does not modify production code.

Final `gitnexus_detect_changes(scope="staged")`:

- Risk: LOW.
- Changed files: 2.
- Changed symbols: 0.
- Affected processes: 0.

Reason: S4-E1 is test-only plus ledger documentation; no indexed production symbol changed.

---

## Exact Test Results

S4-E1 target audit:

```text
poetry run pytest tests/business/test_s4e_stock_reservation_lifecycle_audit.py -q -rxX --tb=short
4 passed, 7 xfailed, 15 warnings
```

S4 full invariant regression:

```text
poetry run pytest tests/business/test_s4_order_fulfillment_inventory_invariants.py tests/business/test_s4b_inventory_reversal_invariants.py tests/business/test_s4c_concurrent_fulfillment_oversell_invariants.py tests/business/test_s4d_inventory_movement_ledger_integrity.py -q --tb=short
29 passed, 32 warnings
```

S5/Phase5 regression:

```text
poetry run pytest tests/test_s5_order_state_machine.py tests/test_phase5_order_payment.py -q --tb=short
66 passed, 1 xfailed, 45 warnings
```

The remaining S5/Phase5 `1 xfailed` is pre-existing and not introduced by S4-E1.

Environment note:

- Final test runs used explicit local env values from running containers without printing secrets:
  - `POSTGRES_HOST=127.0.0.1`
  - `POSTGRES_PORT=5432`
  - `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` from `mpango_postgres`
  - `REPORTING_USER_PASSWORD` from `mpango_prod_backend`
  - `REDIS_URL=redis://127.0.0.1:6379/0`
  - `DATABASE_URL` and `TEST_DATABASE_URL` unset

Hygiene before ledger:

```text
git diff --check
PASS
```

```text
Changed-file mojibake / non-ASCII scan
PASS
```

---

## Audit Invariants

### A. Confirm reservation semantics

Status: XFAIL.

Expected invariant:

- Confirming a draft order for quantity `3` on stock `10` should keep `on_hand=10`, set `reserved=3`, and make `available=7`.

Observed current behavior:

- `confirm_order()` only changes order status through `crud.confirm_order()`.
- `quantity_reserved` remains `0`.
- `InventoryService.deduct_stock()` contains reservation-like behavior, but no order confirm flow calls it.

Finding: confirmed order does not reserve stock. Needs S4-E2 production fix.

### B. Cancel releases reservation

Status: XFAIL.

Expected invariant:

- Cancelling a confirmed, unfulfilled order with reserved quantity should release the reservation and restore available stock.

Observed current behavior:

- `cancel_order()` only changes order status through `crud.cancel_order()`.
- A pre-existing reservation is not released.

Finding: cancel does not release reserved stock. Needs S4-E2 production fix.

### C. Fulfillment consumes reservation correctly

Status: XFAIL.

Expected invariant:

- If an order already reserved quantity `3`, fulfillment should reduce `on_hand` by `3`, reduce `reserved` by `3`, and leave `available` equal to the new on-hand stock.

Observed current behavior:

- `deduct_on_fulfillment()` deducts `quantity_on_hand` but does not reduce `quantity_reserved`.
- A pre-existing reservation remains after fulfillment, causing available stock to be understated.

Finding: fulfillment does not consume existing reservations. Needs S4-E2 production fix.

### D. Available never negative under concurrent reservation pressure

Status: XFAIL.

Expected invariant:

- With stock `5` and two concurrent draft orders for quantity `5`, at most one confirmation should reserve stock.
- Final reserved should be `5`, available should be `0`, and excess demand should remain unconfirmed or fail closed.

Observed current behavior:

- Concurrent confirm calls can both succeed because confirm does not reserve or lock stock.
- Available does not go negative only because no reservation is recorded at all.

Finding: reservation oversell protection is missing. Needs S4-E2 production fix.

### E. Duplicate confirm/cancel idempotency

Status: XFAIL for reservation semantics; PASS for illegal repeat cancel no-op with current zero reservation.

Expected invariant:

- Repeating confirm must not double-increase reserved quantity.
- Repeating cancel must not double-release reserved quantity.
- Illegal repeat operations must leave stock and reserved unchanged.

Observed current behavior:

- Duplicate confirm cannot double reserve because the first confirm does not reserve at all.
- Duplicate cancel cannot demonstrate release idempotency because cancel does not release reservation.
- Illegal repeat cancel with current zero reservation leaves stock unchanged; this narrower no-op check passes.

Finding: duplicate operation tests are blocked by missing reservation/release implementation and are encoded as strict xfails where reservation semantics are required.

### F. Return semantics

Status: PASS.

Expected invariant:

- Returned orders restore physical stock through S4-B.
- Return should not create reserved stock.
- After return, `available = restored_on_hand - reserved`.

Observed current behavior:

- Fulfill reduces on-hand from `10` to `7`.
- Return restores on-hand to `10`.
- Reserved remains `0` and available is `10`.

Finding: return does not create reserved stock and remains consistent with current no-reservation behavior.

### G. Tenant isolation

Status: XFAIL for confirm reservation isolation; PASS for fulfillment physical stock isolation.

Expected invariant:

- Same SKU code in tenant A and tenant B must not cross-mutate `quantity_reserved` or `quantity_on_hand`.

Observed current behavior:

- Tenant A confirmation does not reserve in tenant A, so reservation isolation cannot pass the expected reservation invariant.
- Tenant A fulfillment does not mutate tenant B `on_hand` or `reserved`.

Finding: physical fulfillment isolation passes; reservation isolation awaits S4-E2 reservation implementation.

### H. Movement ledger boundary

Status: PASS.

Expected invariant:

- InventoryMovement is a physical stock movement ledger.
- Reserve/release should not be mixed into `deduction`, `restock`, or `adjustment` movement types.
- If reservation audit is needed later, use a separate reservation ledger rather than overloading physical movement journal semantics.

Observed current behavior:

- Confirm/cancel write no `InventoryMovement` rows.

Finding: movement ledger boundary is currently clean.

---

## Xfail Status

- S4-E1 target suite has `7 xfailed` strict audit tests.
- These xfails are not relaxed tests; they are explicit evidence of missing stock reservation lifecycle behavior.
- Existing S4/S4-B/S4-C/S4-D tests were not modified, skipped, deleted, or relaxed.

---

## Final Verdict

NEEDS_S4E2_PRODUCTION_FIX

Reason:

- Confirm does not reserve stock.
- Cancel does not release stock reservations.
- Fulfillment does not consume existing reservations.
- Concurrent confirm does not protect available stock from reservation oversell.
- Reservation-specific tenant isolation cannot pass until reservation behavior exists.

---

## Constraint Confirmations

- Product code changed: NO.
- Migration changed: NO.
- Frontend changed: NO.
- Deployment: NO.
- Pushed `product-dev-recovered`: NO.
- `OrderService.transition()` changed: NO.
- Existing S4/S4-B/S4-C/S4-D tests relaxed or removed: NO.
- Secrets printed: NO.
