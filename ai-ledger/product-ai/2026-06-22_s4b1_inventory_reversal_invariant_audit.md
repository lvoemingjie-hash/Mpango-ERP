# S4-B1: Inventory Reversal Invariant Audit

| Field | Value |
|-------|-------|
| Date | 2026-06-22 |
| Branch | `opencode/s4b1-inventory-reversal-invariant-audit-2026-06-22` |
| Base | `origin/product-dev-recovered` @ `951f579` (`merge: S3B live DB env governance`) |
| Commit | Pending until branch push; final commit is reported in handoff because the commit hash cannot be embedded in the same commit that creates this ledger. |
| Status | READ-ONLY AUDIT COMPLETE - S4-B2 production fix required |

---

## Scope

This was a read-only audit and test task for inventory reversal behavior after S4 fulfillment inventory deduction.

Allowed changes:

- Add tests.
- Add ledger report.

Forbidden changes were respected:

- Production code changed: no.
- Migration changed: no.
- Frontend changed: no.
- Deployment changed: no.
- Product branch pushed: no.

Changed files:

- `backend/tests/business/test_s4b_inventory_reversal_invariants.py`
- `ai-ledger/product-ai/2026-06-22_s4b1_inventory_reversal_invariant_audit.md`

---

## Read-Only Audit Findings

### Return flow

- `backend/api/v1/orders.py:return_order()` transitions `FULFILLED -> RETURNED` through `OrderService.transition()`.
- The route comment explicitly states: `Restocking is manual in MVP - inventory is NOT auto-adjusted`.
- `OrderService.transition(... RETURNED ...)` posts refund ledger entries via `LedgerService.post_order_return()`.
- No production call path invokes `InventoryService.restock()` during return.
- No return/restock `InventoryMovement` is written during return.

### Cancel flow

- `backend/api/v1/orders.py:cancel_order()` delegates to `crud.order.cancel_order()`.
- CRUD cancel only allows `DRAFT` or `CONFIRMED` orders.
- Core domain state machine allows `PAID -> CANCELLED`, but the API route does not currently use `OrderService.transition()` for cancellation.
- Cancel does not touch inventory or write inventory movements.
- Fulfilled cancellation is rejected and leaves the S4 fulfillment deduction intact.

### Inventory service

- `InventoryService.deduct_on_fulfillment()` is used by `fulfill_order()` and writes deduction movement.
- `InventoryService.restock()` exists but only increases `quantity_on_hand`; it does not write `InventoryMovement`, does not reduce reserved stock despite the docstring, and has no callers in the return path.

### Ledger interaction

- Return posts two refund ledger entries with `reference_type='refund'`.
- Those refund entries are balanced and use `REVENUE` and `CASH` accounts.
- Return ledger and inventory state currently diverge: financial refund is posted but stock remains deducted.
- Confirmed cancellation posts no refund ledger and writes no inventory movement.
- Paid cancellation is rejected by the API route, despite the core state graph mentioning paid cancel with refund logic.

---

## Invariant Status

Already satisfied:

- Fulfilled cancellation is rejected and does not restore or further deduct inventory.
- Confirmed cancellation does not mutate inventory and does not write inventory movement.
- Unfulfilled return is rejected and does not mutate inventory.
- Duplicate return is rejected by terminal-state protection after the first return.
- Return posts refund ledger entries.

Missing / expected failures:

- Return after fulfillment does not restore stock.
- Return after fulfillment does not write a restock/reversal `InventoryMovement`.
- Duplicate return cannot prove "restored exactly once" because the first return restores zero stock.
- Tenant-isolated return restock cannot be proven because return restock does not exist.
- `InventoryService.restock()` is not a complete journaled reversal primitive for S4-B2.

---

## Test Results

S4-B1 audit tests:

```text
poetry run pytest tests/business/test_s4b_inventory_reversal_invariants.py -q -rxX --tb=short
5 passed, 3 xfailed, 11 warnings
```

Expected xfails:

- `test_return_after_fulfillment_restores_stock_and_writes_restock_movement`
- `test_duplicate_return_restores_inventory_exactly_once`
- `test_return_restock_is_tenant_schema_isolated`

Existing S4 regression:

```text
poetry run pytest tests/business/test_s4_order_fulfillment_inventory_invariants.py -q --tb=short
6 passed, 4 warnings
```

State machine / payment regression:

```text
poetry run pytest tests/test_s5_order_state_machine.py tests/test_phase5_order_payment.py -q --tb=short
66 passed, 1 xfailed, 47 warnings
```

Hygiene:

```text
git diff --check
PASS
```

```text
Changed-file mojibake / non-ASCII scan
PASS
```

GitNexus:

```text
gitnexus analyze
Repository indexed successfully: 5,499 nodes, 15,826 edges, 364 clusters, 228 flows
```

```text
gitnexus_detect_changes(scope="staged")
LOW risk: 2 changed files, 19 changed test symbols, 0 affected processes.
```

Note: An initial attempt to run two DB-heavy pytest commands in parallel caused a PostgreSQL deadlock in the shared `t_test` fixture setup. The required regression commands were then rerun sequentially and passed as shown above.

---

## Risk Classification

P0:

- Return after fulfillment leaves inventory permanently deducted while the order is returned and refund ledger entries are posted. This can corrupt stock availability after real customer returns.

P1:

- Missing return/restock `InventoryMovement` journal prevents auditability of stock reversal.
- Financial ledger refund and inventory state are inconsistent after return.
- API cancellation behavior rejects paid cancellation even though the core state matrix documents `PAID -> CANCELLED` with refund implications.

P2:

- `InventoryService.restock()` docstring mentions reserved-stock behavior, but implementation only increments `quantity_on_hand`.
- Return route message says refund ledger entries posted, but does not mention manual inventory restock limitation.

---

## S4-B2 Recommended Production Fix Scope

Keep S4-B2 constrained and production-focused:

- Add a fulfillment-return reversal method to `InventoryService`, separate from reserve-oriented `deduct_stock()`.
- Use `SELECT FOR UPDATE` on stock rows.
- Restore `quantity_on_hand` by returned item quantity.
- Write `InventoryMovement` with `movement_type='restock'`, positive quantity, before/after quantities, `reference_type='order'`, and `reference_id=order.id`.
- Make return reversal atomic with `OrderService.transition(... RETURNED ...)` so order, ledger, stock, and movement commit or rollback together.
- Prevent duplicate return from restoring twice; terminal `RETURNED` state already helps, but tests should prove stock remains restored exactly once.
- Preserve tenant schema isolation.
- Decide whether paid cancellation is intentionally unsupported at API level or should move to `OrderService.transition(... CANCELLED ...)` with refund semantics.

STOP condition for S4-B2:

- If changing `OrderService.transition()` is required, run impact analysis first and ask CTO before expanding scope.
