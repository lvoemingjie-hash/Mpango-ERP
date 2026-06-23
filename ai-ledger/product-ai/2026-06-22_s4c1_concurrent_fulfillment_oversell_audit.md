# S4-C1: Concurrent Fulfillment Oversell Invariant Audit

| Field | Value |
|-------|-------|
| Date | 2026-06-22 |
| Branch | `opencode/s4c1-concurrent-fulfillment-oversell-audit-2026-06-22` |
| Base | `origin/product-dev-recovered` @ `bc1114f447c2c3da33490a21183fc168a63ec389` (`merge: S4-B2 return inventory reversal invariants`) |
| Commit | Pending until branch push; final commit is reported in handoff because the commit hash cannot be embedded in the same commit that creates this ledger. |
| Verdict | NEEDS_S4C2_PRODUCTION_FIX |

---

## Changed Files

- `backend/tests/business/test_s4c_concurrent_fulfillment_oversell_invariants.py`
- `ai-ledger/product-ai/2026-06-22_s4c1_concurrent_fulfillment_oversell_audit.md`

No production, migration, frontend, or deployment files were changed.

---

## Audit Method

The S4-C1 tests use real database sessions and the real `fulfill_order()` route handler.

Concurrency method:

- Test setup uses the existing `async_session` fixture for tenant schema/bootstrap and data creation.
- Each concurrent fulfillment task uses its own independent `AsyncSessionLocal()` session.
- Each independent session sets `session.info["tenant_schema"]`, `session.info["tenant_id"]`, and `SET LOCAL search_path TO "<tenant>", public` before calling `fulfill_order()`.
- Each task commits on route success and returns the route status.
- Each task catches `HTTPException` and returns the failure details; the session context closes independently.
- Post-concurrency assertions read committed database state through SQL snapshots using saved UUIDs, not shared ORM objects.

This is a real DB concurrency audit, not a mock or single-session simulation.

---

## GitNexus Impact Summary

Pre-test impact analysis:

- `fulfill_order`: MEDIUM risk. Direct upstream callers are S4/S4-B tests; no affected processes reported by GitNexus for direct route callers.
- `InventoryService.deduct_on_fulfillment`: LOW risk. Direct upstream caller is `backend/api/v1/orders.py:fulfill_order`; affected process is fulfillment.
- `InventoryStock`: MEDIUM risk. Shared stock model used by repository/service/tests and API import graph.
- `InventoryMovement`: HIGH risk. Shared journal model used by fulfillment deduction, return restock, and manual inventory adjustment flows.

Detect changes:

- `gitnexus_detect_changes(scope="unstaged")` returned no changes because the only changed file at that point was untracked.
- Final `gitnexus_detect_changes(scope="staged")`: LOW risk, 2 changed files, 0 changed symbols, 0 affected processes.

---

## Exact Test Results

S4-C1 target audit:

```text
poetry run pytest tests/business/test_s4c_concurrent_fulfillment_oversell_invariants.py -q -rxX --tb=short
5 xfailed, 11 warnings
```

S4/S4-B regression:

```text
poetry run pytest tests/business/test_s4_order_fulfillment_inventory_invariants.py tests/business/test_s4b_inventory_reversal_invariants.py -q --tb=short
15 passed, 15 warnings
```

S5/Phase5 regression:

```text
poetry run pytest tests/test_s5_order_state_machine.py tests/test_phase5_order_payment.py -q --tb=short
66 passed, 1 xfailed, 45 warnings
```

Environment note:

- Final test runs used explicit local env values from running containers without printing secrets:
  - `POSTGRES_HOST=127.0.0.1`
  - `POSTGRES_PORT=5432`
  - `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` from `mpango_postgres`
  - `REPORTING_USER_PASSWORD` from `mpango_prod_backend`
  - `REDIS_URL=redis://127.0.0.1:6379/0`
  - `DATABASE_URL` and `TEST_DATABASE_URL` unset

---

## Findings

### Oversell / duplicate success

Observed.

- With one SKU at stock 5 and two paid orders for quantity 5, both concurrent calls returned success with status `fulfilled` during the raw failing run.
- Expected invariant is exactly one success and one fail-closed paid order.
- This is a product concurrency gap, not a test environment issue.

### Negative stock

Not observed in the raw failing evidence.

- The current failure mode appears to be a lost-update / stale identity map issue that can under-deduct stock while allowing too many fulfillments, rather than driving stock below zero.
- S4-C2 should still preserve the non-negative stock invariant explicitly.

### Duplicate or inconsistent movement

Observed risk.

- Duplicate fulfillment race on the same order returned two successes during the raw failing run.
- Stock-enough-for-both scenario returned two successes but final stock assertion observed `5.00` instead of expected `0.00`, indicating successful order/movement paths can diverge from final stock state under concurrency.
- This requires production investigation in S4-C2.

### Partial commit

Observed risk.

- Multi-item order competing with a single-item order returned two successes despite SKU A only being sufficient for one order.
- The target invariant is that one order fails as a whole, with no SKU B deduction if the multi-item order loses the SKU A race.
- Current behavior does not reliably enforce that invariant under concurrency.

### Tenant leakage

Not observed as direct cross-tenant mutation evidence.

- The tenant-isolation test includes a shadow tenant with the same `sku_code` and independent stock/movement tables.
- The test is marked xfail because the tenant A concurrent oversell invariant fails first; S4-C2 should rerun it after fixing concurrency to confirm no tenant leakage.

---

## Final Verdict

NEEDS_S4C2_PRODUCTION_FIX

Reason:

- `fulfill_order()` + `InventoryService.deduct_on_fulfillment()` is not concurrency-safe enough under independent sessions.
- Tests indicate concurrent callers can both report fulfillment success when business stock/order invariants require at most one success or exactly-once fulfillment.
- The likely production fix should refresh/lock rows in a way that defeats stale identity-map state, preserve atomic rollback, and re-run these strict xfail tests as passing tests.

---

## Constraint Confirmations

- Production code changes: 0.
- Migration changes: 0.
- Frontend changes: 0.
- Deployment: no.
- Pushed `product-dev-recovered`: no.
- Secrets printed: no.
- Tests were not relaxed to manufacture pass; concurrency gaps are encoded as strict xfails with explicit S4-C2 reason.
