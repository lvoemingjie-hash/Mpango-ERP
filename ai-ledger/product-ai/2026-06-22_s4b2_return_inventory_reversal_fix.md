# S4-B2: Return Inventory Reversal Production Fix

| Field | Value |
|-------|-------|
| Date | 2026-06-22 |
| Branch | `opencode/s4b2-return-inventory-reversal-fix-2026-06-22` |
| Base | `origin/product-dev-recovered` @ `951f5797dd19b0a0c84915b0c08f7060e91c0ea4` (`merge: S3B live DB env governance`) |
| Commit | Pending until branch push; final commit is reported in handoff because the commit hash cannot be embedded in the same commit that creates this ledger. |
| Status | COMPLETE - awaiting CTO review |

---

## Changed Files

- `backend/services/inventory_service.py`
- `backend/api/v1/orders.py`
- `backend/tests/business/test_s4b_inventory_reversal_invariants.py`
- `ai-ledger/product-ai/2026-06-22_s4b2_return_inventory_reversal_fix.md`

No other files were changed.

---

## Implementation

- Added `InventoryService.restock_on_return()`.
- It resolves SKU/stock in the active tenant schema via existing repository queries.
- It locks the `inventory_stocks` row with `SELECT FOR UPDATE`.
- It fail-closes if SKU is missing, stock row is missing, or return quantity is not positive.
- It restores `quantity_on_hand` by the order item quantity.
- It writes a journaled `InventoryMovement` using `movement_type='restock'`, positive `quantity`, before/after quantities, `reference_type='order'`, and `reference_id=order.id`.
- Wired `return_order()` to call `OrderService.transition(... RETURNED ...)` and then `restock_on_return()` for each order item before request commit.
- Did not modify `OrderService.transition()`.
- Did not change cancel semantics.

---

## Transaction Consistency

The return path now performs these operations on the same `AsyncSession` before the request-level commit:

- Lock and transition the order from `FULFILLED` to `RETURNED` through `OrderService.transition()`.
- Post refund ledger entries through existing `OrderService` / `LedgerService` integration.
- Refresh order items.
- Restore inventory stock through `InventoryService.restock_on_return()`.
- Write `InventoryMovement` restock journal entries.
- Flush all changes before returning the API response.

Fail-closed behavior:

- State-machine rejection happens before mutation and returns `409` without inventory changes.
- Any `HTTPException` from restock/journaling after transition triggers `db.rollback()` and re-raises.
- Any unexpected exception after transition triggers `db.rollback()` and re-raises, or returns `409` for state-machine/invariant text.
- The added rollback test soft-deletes the stock row after fulfillment and proves failed return leaves the order `FULFILLED`, writes no refund ledger entries, and does not add restock movement.

---

## GitNexus Impact Summary

Pre-change impact:

- API impact for `backend/api/v1/orders.py` / `/orders/{order_id}/return`: LOW, no detected direct consumers, existing order execution flows affected.
- `return_order` upstream impact: MEDIUM, direct callers were S4-B1 audit tests.
- `InventoryService.restock`: LOW, no direct production callers; method belongs to `InventoryService` class.
- `InventoryMovement`: HIGH because fulfillment and manual inventory adjustment also use movement journaling.
- `fulfill_order` impact was checked as precaution: MEDIUM, direct callers were S4 fulfillment tests and S4-B1 setup helper. Fulfillment code was not modified.
- `OrderService.transition()` was not modified; no STOP_AND_REPORT_CTO escalation was needed.

Final `gitnexus_detect_changes(scope="staged")`:

- Risk: CRITICAL, due production route/service files and affected order/inventory execution flows.
- Changed files: 4.
- Changed symbols: 48.
- Affected processes: 17, including return, fulfillment, cancel, confirm, and inventory adjustment flows reported by file-level symbol attribution.
- Manual review: actual production behavioral change is constrained to `return_order()` and new `InventoryService.restock_on_return()`; `fulfill_order`, cancel behavior, and manual adjustment behavior were regression-tested.

---

## Exact Test Results

S4-B2 target suite:

```text
poetry run pytest tests/business/test_s4b_inventory_reversal_invariants.py -q -rxX --tb=short
9 passed, 12 warnings
```

Regression suite:

```text
poetry run pytest tests/business/test_s4_order_fulfillment_inventory_invariants.py tests/test_s5_order_state_machine.py tests/test_phase5_order_payment.py -q --tb=short
72 passed, 1 xfailed, 48 warnings
```

The regression xfail is pre-existing in `tests/test_phase5_order_payment.py` and is not introduced by S4-B2.

Environment note:

- Initial pytest attempts failed only due local DB/reporting env resolution.
- Final runs used explicit local env values from running containers without printing secrets:
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

## Xfail Status

- S4-B2 target suite has no xfails.
- The previous S4-B1 strict xfails are now normal passing tests.
- Regression suite still has `1 xfailed` in existing payment tests; not blocking S4-B2.

---

## Constraint Confirmations

- Deployed: no.
- Pushed `product-dev-recovered`: no.
- Frontend changed: no.
- Migration changed: no.
- `OrderService.transition()` changed: no.
- Secrets touched or printed: no.
- S4 fulfillment deduction invariant regressed: no; S4 regression suite passed.
- Cancel behavior changed: no; S4-B2 tests keep confirmed cancel no inventory movement and paid/fulfilled cancel rejected.
