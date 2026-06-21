# S4: Order Fulfillment Inventory Invariants

| Field | Value |
|-------|-------|
| Branch | `opencode/s4-business-invariant-inventory-fulfillment-2026-06-21` |
| Base | `origin/product-dev-recovered` @ `27343d179fd3b671bed8126e04085d9272a09b8c` |
| Date | 2026-06-21 |
| Status | PASS for S4 scope; one pre-existing out-of-scope U3C logging blocker remains |
| Changed production files | `backend/api/v1/orders.py`, `backend/services/inventory_service.py` |
| Changed test files | `backend/tests/business/test_s4_order_fulfillment_inventory_invariants.py` |

---

## Objective

Enforce the business invariant that fulfilling a paid order must update tenant inventory correctly and atomically. The fix was constrained to avoid changes to `OrderService.transition()`, state-machine rules, migrations, frontend, or deployment files.

---

## Implementation

- Added `InventoryService.deduct_on_fulfillment()` for fulfillment-specific stock mutation.
- Kept `InventoryService.deduct_stock()` unchanged; it still reserves stock by increasing `quantity_reserved`.
- Replaced `fulfill_order()` raw SQL stock decrement with the new inventory service method.
- Used `SELECT FOR UPDATE` on the stock row before deducting `quantity_on_hand`.
- Raised HTTP 409 with `code="INSUFFICIENT_STOCK"` if fulfillment would make stock negative.
- Wrote an `InventoryMovement` journal entry for successful fulfillment deductions.
- Rolled back the route transaction on inventory failures so the order does not remain `fulfilled`.

---

## Invariant Coverage

New real-DB tests cover:

- PAID -> FULFILLED decrements stock and writes one movement.
- Insufficient stock returns 409 and rolls back order, stock, and movement state.
- Duplicate fulfillment does not deduct twice.
- Multi-item shortage rolls back prior deductions in the same transaction.
- Tenant schema isolation for inventory mutation.
- Unpaid order cannot fulfill and leaves inventory unchanged.

The tests call the route handler directly with real SQLAlchemy async sessions and inspect committed DB state. They do not mock the inventory mutation path.

---

## Verification

Passed:

```text
poetry run pytest tests/business/test_s4_order_fulfillment_inventory_invariants.py -q -rxX --tb=short
6 passed, 4 warnings
```

```text
poetry run pytest tests/test_s5_order_state_machine.py tests/test_phase5_order_payment.py -q --tb=short
66 passed, 1 xfailed, 47 warnings
```

```text
poetry run pytest tests/test_s3c_self_contained_fresh_tenant_live_proof.py -q -rxX --tb=short
17 passed, 22 warnings
```

```text
git diff --check
PASS, with existing LF/CRLF warnings only
```

```text
Changed-diff ASCII/mojibake scan
PASS, no matches in changed diff
```

```text
gitnexus analyze
Repository indexed successfully: 5,470 nodes, 15,710 edges, 362 clusters, 228 flows
```

CTO rerun notes:

- The S4 isolated worktree does not contain ignored local env files.
- Initial pytest attempts resolved the DB host as Docker-internal `postgres`, which is not resolvable from the host OS.
- Reruns loaded DB/reporting environment variables from the main local project `.env` into the pytest process without printing values.
- `DATABASE_URL`/`TEST_DATABASE_URL` host was normalized from `@postgres:` to `@localhost:` for host-side pytest execution.
- After that environment correction, S4 invariant tests reached the intended RED business assertions, then passed after implementation.

Blocked / out of scope:

```text
poetry run pytest tests -q -k "inventory and not frontend" --tb=short
1 failed, 19 passed, 1174 deselected, 1 xfailed
```

The failure is `tests/test_u3c_live_db_apply.py::TestNoSideEffectWrites::test_apply_does_not_write_inventory`, caused by pre-existing U3C logging in `services/import_service.py` with `extra={"created": ...}`, which collides with the reserved `LogRecord.created` field. That file is outside the approved S4 edit scope, so it was not changed in the S4 branch.

---

## GitNexus

- Pre-change `fulfill_order` impact was LOW.
- Pre-change `InventoryService.deduct_stock` impact was LOW and its reserve semantics were not modified.
- `OrderService.transition()` impact was HIGH and was not modified.
- Post-change worktree analysis succeeded.
- `gitnexus_detect_changes(compare=origin/product-dev-recovered, repo=s4-business-invariant-inventory)` reported CRITICAL because file-level diff attribution marked all routes/functions in `orders.py` and `InventoryService` as modified. Manual diff review shows the actual production change is scoped to `fulfill_order()` and a new `deduct_on_fulfillment()` method.

---

## Residual Risks

- `OrderService.transition()` still emits notification side effects before inventory deduction is checked. The DB transaction rolls back correctly on inventory failure, but notification behavior is outside the allowed S4 edit scope.
- The full inventory selection gate remains blocked by the unrelated U3C logging collision noted above.
