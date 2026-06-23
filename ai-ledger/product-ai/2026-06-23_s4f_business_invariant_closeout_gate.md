# S4-F: Business Invariant Closeout Gate

| Field | Value |
|-------|-------|
| Date | 2026-06-23 |
| Branch | `opencode/s4f-business-invariant-closeout-gate-2026-06-23` |
| Base | `origin/product-dev-recovered` @ `6bcb868` (`merge: S4-E3 reservation ownership contract`) |
| Commit | Pending until branch push; final commit is reported in handoff because the commit hash cannot be embedded in the same commit that creates this ledger. |
| Verdict | PASS_FOR_CTO_REVIEW |

---

## Changed Files

- `backend/tests/business/test_s4f_business_invariant_closeout.py`
- `ai-ledger/product-ai/2026-06-23_s4f_business_invariant_closeout_gate.md`

No production, migration, frontend, or deployment files were changed.

---

## Gate Scope

S4-F is a test-only business invariant closeout gate over the merged S4-E3 reservation ownership contract.

The new suite verifies the full order/inventory/ledger lifecycle using real PostgreSQL tenant schemas and real route/service handlers:

- Confirm reserves inventory per order and rolls back cleanly on insufficient stock.
- Pay preserves inventory reservations and keeps existing Phase5 payment ledger semantics.
- Unpaid orders cannot fulfill and leave stock, movements, and ledger untouched.
- Fulfill consumes only the order-owned reservation, deducts on-hand stock, writes a deduction movement, and remains duplicate-stable.
- Return restores on-hand stock, does not re-reserve, writes restock movement and refund ledger entries, and remains duplicate-stable.
- Confirmed cancel releases reservations, while paid/fulfilled cancel attempts are rejected without side effects.
- Multi-item confirm and fulfill failures roll back all stock, reservation, movement, and ledger side effects.
- Same SKU codes in different tenant schemas remain isolated.

No mocks are used for database behavior.

---

## Implementation Notes

- The suite imports and calls the existing route handlers directly: `confirm_order`, `pay_order`, `fulfill_order`, `return_order`, and `cancel_order`.
- Assertions use `inventory_reservations` as the ownership source of truth and `inventory_stocks.quantity_reserved` as the aggregate projection.
- Ledger checks preserve existing Phase5/S4B contracts: payment entries are checked under `reference_type='order'`, and return refund entries are checked under `reference_type='refund'`.
- Cross-schema tenant setup uses schema-qualified SQL for seed rows to avoid asyncpg prepared-statement enum cache bleed between tenant schemas with identically named enum types.
- Cross-schema verification uses schema-qualified SQL for stock and reservation counts for the same reason.
- `OrderService.transition()` was not modified.

---

## Triage Notes

Initial S4-F target run found three test failures. All were test harness or assertion issues, not product defects:

- Return ledger assertion originally expected payment and refund entries under one `order` reference; existing S4B/Phase5 semantics keep refund entries under `reference_type='refund'`.
- Multi-item rollback assertion accessed expired ORM objects after an expected rollback; the test now stores UUIDs before failure paths.
- Tenant isolation setup triggered asyncpg enum/prepared statement cache issues across schemas; the test now schema-qualifies cross-tenant setup and verification SQL.

No `NEEDS_S4G_PRODUCTION_FIX` xfail was added because no new production defect was confirmed.

---

## Exact Test Results

S4-F target suite:

```text
poetry run pytest tests/business/test_s4f_business_invariant_closeout.py -q -rxX --tb=short
8 passed, 18 warnings
```

S4/S4-B/S4-C/S4-D/S4-E regression:

```text
poetry run pytest tests/business/test_s4_order_fulfillment_inventory_invariants.py tests/business/test_s4b_inventory_reversal_invariants.py tests/business/test_s4c_concurrent_fulfillment_oversell_invariants.py tests/business/test_s4d_inventory_movement_ledger_integrity.py tests/business/test_s4e_stock_reservation_lifecycle_audit.py -q --tb=short
41 passed, 59 warnings
```

S5/Phase5 regression:

```text
poetry run pytest tests/test_s5_order_state_machine.py tests/test_phase5_order_payment.py -q --tb=short
66 passed, 1 xfailed, 45 warnings
```

The remaining `1 xfailed` is pre-existing in `tests/test_phase5_order_payment.py` and is unrelated to S4-F.

Environment note:

- Final test runs used explicit local env values from running containers without printing secrets:
- `POSTGRES_HOST=127.0.0.1`
- `POSTGRES_PORT=5432`
- `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` from `mpango_postgres`
- `REPORTING_USER_PASSWORD` from `mpango_prod_backend`
- `REDIS_URL=redis://127.0.0.1:6379/0`
- `DATABASE_URL` and `TEST_DATABASE_URL` unset

---

## Business Invariant Findings

### Confirm

PASS.

- Draft-to-confirmed creates an owned reservation row and increments aggregate reserved.
- Insufficient stock raises `INSUFFICIENT_AVAILABLE_STOCK`; the order remains `draft`, no reservation row remains, and aggregate stock is unchanged.

### Pay

PASS.

- Payment does not mutate stock or reservations.
- Existing Phase5 ledger semantics remain intact for cash settlement: `CASH +75.0000`, `RECEIVABLE -75.0000` under the order reference.

### Fulfill

PASS.

- Fulfillment requires paid state.
- Fulfillment consumes the owned reservation, moves reserved to zero, deducts on-hand, and writes one `deduction` movement.
- Duplicate fulfillment is rejected without additional stock, movement, or ledger mutation.

### Return

PASS.

- Return keeps consumed reservations consumed; it does not re-reserve stock.
- Return restores on-hand stock and writes one `restock` movement after the prior deduction.
- Refund ledger entries are balanced under `reference_type='refund'`: `REVENUE +75.0000`, `CASH -75.0000`.
- Duplicate return is rejected without additional stock, movement, or ledger mutation.

### Cancel

PASS.

- Confirmed cancel releases only that order's reservation and decrements aggregate reserved.
- Paid and fulfilled cancel attempts are rejected and leave status, stock, and ledger unchanged.

### Multi-item Rollback

PASS.

- Multi-item confirm failure rolls back successful earlier item reservations from the same attempted transaction.
- Multi-item fulfill failure rolls back successful earlier item deductions from the same attempted transaction.

### Tenant Isolation

PASS.

- Two tenant schemas using the same SKU code reserve independently.
- Tenant A ends at `on_hand=10.00,reserved=3.00,available=7.00`.
- Tenant B ends at `on_hand=20.00,reserved=4.00,available=16.00`.
- Each tenant has exactly one reservation for its own order.

---

## Hygiene

```text
git diff --check
PASS
```

```text
Changed-file non-ASCII scan
PASS
```

GitNexus analyze:

```text
npx gitnexus analyze
Repository indexed successfully (16.2s)
5,646 nodes | 16,380 edges | 366 clusters | 218 flows
```

GitNexus staged change detection:

```text
gitnexus_detect_changes(scope="staged")
risk_level: low
changed_files: 2
changed_count: 36
affected_count: 0
affected_processes: []
```

Reason: S4-F is test-only plus ledger documentation; no indexed production execution flow is changed.
