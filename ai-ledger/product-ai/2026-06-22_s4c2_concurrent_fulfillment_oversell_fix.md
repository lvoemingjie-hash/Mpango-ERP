# S4-C2: Concurrent Fulfillment Oversell Production Fix

| Field | Value |
|-------|-------|
| Date | 2026-06-22 |
| Branch | `opencode/s4c2-concurrent-fulfillment-oversell-fix-2026-06-22` |
| Base | `origin/opencode/s4c1-concurrent-fulfillment-oversell-audit-2026-06-22` @ `bbd15929fe5d9878b1dcd0c806d33ad9ce7c7b5b` (`test: audit concurrent fulfillment oversell invariants`) |
| Commit | Pending until branch push; final commit is reported in handoff because the commit hash cannot be embedded in the same commit that creates this ledger. |
| Status | COMPLETE - awaiting CTO review |

---

## Changed Files

- `backend/api/v1/orders.py`
- `backend/services/inventory_service.py`
- `backend/tests/business/test_s4c_concurrent_fulfillment_oversell_invariants.py`
- `ai-ledger/product-ai/2026-06-22_s4c2_concurrent_fulfillment_oversell_fix.md`

No frontend, migration, deployment, or `OrderService.transition()` files were changed.

---

## Root Cause

The S4-C1 audit showed concurrent `fulfill_order()` calls could both report success when only one fulfillment should be allowed.

The production issue was stale ORM identity-map state during the critical locked transition/deduction path:

- `fulfill_order()` performs a preflight `get_order_by_id()` before calling `OrderService.transition()`.
- `OrderService.transition()` locks the order row, but the same `AsyncSession` can reuse the preloaded order object unless that identity-map state is expired.
- `InventoryService.deduct_on_fulfillment()` locks the stock row, but the same session can also reuse a previously loaded stock object unless the locked query repopulates the instance.

Under independent concurrent sessions, that stale state allowed duplicate success or lost-update behavior around order status and final stock quantity.

---

## Implementation

- In `fulfill_order()`, save `order.id`, expire the preflight `order` instance, and then call `OrderService.transition()` with the saved UUID.
- This preserves the caller-visible ORM object as persistent in the session while forcing the locked transition query to reload current database state.
- Map `DomainInvalidStateTransitionError` and `OrderInvariantViolation` to the existing `409 CONFLICT` fail-closed response path, alongside the API-layer `InvalidStateTransitionError`.
- In `InventoryService.deduct_on_fulfillment()`, add `execution_options(populate_existing=True)` to the locked `InventoryStock` query.
- Removed the S4-C1 strict `xfail` decorators so the five concurrent fulfillment invariants are now enforced as normal passing tests.

`OrderService.transition()` was not modified, so no `STOP_AND_REPORT_CTO` escalation was required.

---

## Invariant Coverage

The S4-C2 target suite now verifies:

- Same SKU, stock only enough for one order: exactly one fulfillment succeeds and stock ends at zero.
- Same SKU, stock enough for both orders: both fulfillments succeed and stock decrements exactly twice.
- Multi-item competing order: the losing order rolls back as a whole, without partial SKU B deduction.
- Duplicate fulfillment race on the same order: only one call succeeds and only one deduction is journaled.
- Tenant isolation: concurrent tenant A fulfillment does not mutate a shadow tenant with the same SKU code.

---

## GitNexus Impact Summary

Pre-change impact analysis:

- `fulfill_order`: MEDIUM risk; direct callers are S4/S4-B/S4-C tests and fulfillment route flow.
- `InventoryService.deduct_on_fulfillment`: LOW risk; direct production caller is `fulfill_order()`.
- `OrderService.transition`: HIGH risk when analyzed as `transition`; not modified.
- `InventoryStock`: MEDIUM risk because it is the locked quantity source for fulfillment and return flows.
- `InventoryMovement`: HIGH risk because fulfillment, return, and adjustment flows share movement journaling.

Final `gitnexus_detect_changes(scope="staged")` after reindex:

- Risk: CRITICAL.
- Changed files: 4.
- Changed symbols: 49.
- Affected processes: 17, including fulfillment, return, cancel, confirm, and inventory adjustment flows.
- Manual review: the actual production diff is 8 insertions in fulfillment/stock locking paths. Return, cancel, confirm, and adjustment were reported through route/service file-level symbol attribution and were covered by regression tests where applicable.

---

## Exact Test Results

S4-C2 target suite:

```text
poetry run pytest tests/business/test_s4c_concurrent_fulfillment_oversell_invariants.py -q -rxX --tb=short
5 passed, 7 warnings
```

Required S4/S4-B/S5/Phase5 regression suite:

```text
poetry run pytest tests/business/test_s4_order_fulfillment_inventory_invariants.py tests/business/test_s4b_inventory_reversal_invariants.py tests/test_s5_order_state_machine.py tests/test_phase5_order_payment.py -q --tb=short
81 passed, 1 xfailed, 59 warnings
```

The remaining `1 xfailed` is pre-existing in `tests/test_phase5_order_payment.py` and is not introduced by S4-C2.

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

## Xfail Status

- S4-C2 target suite has no xfails.
- The five S4-C1 strict xfails are now normal passing tests.
- Regression suite still has `1 xfailed` in existing payment tests; not blocking S4-C2.

---

## Constraint Confirmations

- Deployed: no.
- Pushed `product-dev-recovered`: no.
- Frontend changed: no.
- Migration changed: no.
- `OrderService.transition()` changed: no.
- Secrets touched or printed: no.
- Sleep/retry workaround added: no.
- S4/S4-B/S5/Phase5 regression passed.
- Oversell / duplicate success / partial deduction / tenant isolation invariants are enforced by passing S4-C2 tests.
