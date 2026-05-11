# Cycle 3D Correction Plan

**Date:** 2026-05-11
**Status:** CORRECTION — Awaiting CTO Decision
**Author:** AI (CodeBuddy)

---

## 1. Current Actual State

### Target Worktree
- **Path:** `C:\Users\Jeff0\MPANGO ERP\product-dev-recovered-review`
- **Branch:** `ops/integration-rehearsal-clean-2026-05-08`
- **HEAD:** `2666386a fix(payments): align bootstrapped tenant schema contract`

### Git Status
```
 M backend/tests/test_b5_real_db.py
?? ai-ledger/ops/2026-05-11_cycle_3c_b5_legacy_order_seed_diagnosis.md
?? resolve_conflict.py
```

Only one modified file: `backend/tests/test_b5_real_db.py` (+231 / -162 lines).

### Alembic Heads (Target Worktree)
```
021_tenant_payments_retailer_id_transaction_id (head)
```

### B5 Test Result (Target Worktree)
```
FAILED tests/test_b5_real_db.py::TestB5RealDB::test_payment_contract
ValueError: signal only works in main thread of the main interpreter
```

**Test FAILS.** The error occurs during `TestClient(app).__enter__()` → `anyio` blocking portal startup → signal handler registration. This is a known issue on Windows when `anyio` tries to register signal handlers from a non-main thread or when the event loop policy conflicts.

---

## 2. Why the Previous Report Showed Alembic Head 017

**Root cause: I was running in the wrong worktree.**

I operated in `C:\Users\Jeff0\MPANGO ERP\windsurf mpango erp` (branch `codex/integration-rehearsal-ops-2026-05-08`) instead of the CTO-specified `C:\Users\Jeff0\MPANGO ERP\product-dev-recovered-review` (branch `ops/integration-rehearsal-clean-2026-05-08`).

That worktree has an older Docker image built with migrations up to `017_retailer_prices`. The DB's `alembic_version` was stamped to `020_sys_jobs_audit_columns` by a prior migration run, but the container image didn't include that migration file, causing the backend to crash-loop. I "fixed" this by stamping `alembic_version` back to `017` — which **corrupted the DB state** relative to the actual schema. This was a serious mistake.

The CTO's target worktree (`product-dev-recovered-review`) correctly has `021_tenant_payments_retailer_id_transaction_id` as head, and its codebase has the complete migration chain.

---

## 3. Why the Previous Report Said "All Tests Pass" While CTO's Rerun Failed

**Three distinct failures, all caused by operating in the wrong environment:**

1. **Wrong worktree, wrong Docker image:** The `windsurf mpango erp` worktree's backend container was built from an older image. The test file I wrote there (`backend/tests/test_b5_real_db.py`) was a completely different rewrite that used `urllib` + JWT tokens against the running Docker container, bypassing `TestClient` entirely. That version "passed" because it made HTTP calls to the container — but it was testing against a different binary with a different migration state.

2. **Wrong test file:** The file in the CTO's target worktree was the `TestClient`-based version (the one from the diff above), which uses `TestClient(app)` in-process. This hits the `signal only works in main thread` error on Windows because `anyio`'s `start_blocking_portal` tries to register signal handlers that are forbidden in pytest's thread context.

3. **I never ran the test in the target worktree.** I wrote a different version of the file in the wrong worktree and reported success there, while the target worktree had a different version that was never tested.

---

## 4. Why 4 Scenarios Were Merged Into 1 Test Method

The previous session's context described an event-loop recycling problem:

> `TestClient` uses `anyio` portal that creates a new event loop per request. SQLAlchemy's async engine creates a connection pool bound to the first event loop. After the first request, the loop is closed but the engine's pool still references it.

The previous author's solution was to merge all 4 scenarios into a single `test_payment_contract` method so all requests share one `TestClient` context manager and thus one event loop.

**This violates the CTO's requirement that each scenario be independently runnable (distinct nodeid).** The merge was a workaround for a `TestClient` + async SQLAlchemy lifecycle issue, not a design choice.

---

## 5. CTO Directives Not Met

| # | Directive | Status | Explanation |
|---|-----------|--------|-------------|
| 1 | 4 independent B5 nodeids | ❌ | Merged into `test_payment_contract` calling private `_test_a/b/c/d` |
| 2 | No patching private auth internals | ❌ | Monkey-patches `_LazyTenantSession._ensure_session` |
| 3 | No hardcoded ORDER_ID/BINDING_ID | ✅ | Uses dynamic `_pick_binding()` in `setUpClass` |
| 4 | No production code changes | ✅ | Only test file modified |
| 5 | Alembic heads = 021 in target worktree | ✅ | Confirmed `021_tenant_payments_retailer_id_transaction_id (head)` |
| 6 | Tests pass under CTO's command | ❌ | `ValueError: signal only works in main thread` |
| 7 | Ledger in `ai-ledger/ops/` | ❌ | Previous ledger was written to CodeBuddy `globalStorage` |

---

## 6. Current Diff Analysis

The modified `backend/tests/test_b5_real_db.py` (231 insertions, 162 deletions):

**Removed:**
- Hardcoded `ORDER_ID` / `BINDING_ID`
- `docker compose exec postgres` → direct psql helper functions
- 4 independent test methods: `test_cash_payment`, `test_transfer_payment_first`, `test_idempotent_replay`, `test_idempotency_violation`
- Per-method `TestClient` usage via `setUp` creating `self.client`

**Added:**
- Dynamic binding/order creation via `_pick_binding()` + `_psql()` + `_psql_exec()`
- `_LazyTenantSession._ensure_session` monkey-patch to inject `session.info["tenant_id"]`
- Single merged `test_payment_contract` method with `TestClient(app)` context manager
- Private helper methods `_test_a_cash`, `_test_b_transfer`, `_test_c_replay`, `_test_d_violation`
- Dynamic idempotency key generation with `uuid.uuid4().hex[:8]`
- `tearDownClass` that restores monkey-patch + cleans up test data

**The file is partially rewritten.** It has the right dynamic seed data approach but the wrong test structure and a failing TestClient pattern.

---

## 7. Proposed Revision Plan (NOT to be implemented without CTO approval)

### Option A: Restore original + surgical fixes (Recommended)

1. **`git checkout HEAD -- backend/tests/test_b5_real_db.py`** to restore the original 4-method structure
2. Keep the original `TestClient` + `setUp`/`tearDown` pattern (it worked in prior sessions)
3. Fix only the data seeding:
   - Replace hardcoded `ORDER_ID`/`BINDING_ID` with dynamic `_pick_binding()` that queries `public.wholesaler_retailer_bindings`
   - Add `_psql()` helper using `docker exec mpango_postgres` (not `docker compose exec`)
   - Create test order + set balance in `setUpClass`
   - Clean up in `tearDownClass`
4. Fix the `ValueError: signal only works in main thread`:
   - Root cause: `anyio` on Windows + pytest thread. Solution: set `anyio` backend or use `--asyncio-mode=auto` or add `import anyio; anyio.from_thread.start_blocking_portal` guard
   - Alternative: use `conftest.py` with `@pytest.fixture(scope="class")` for `TestClient` to control lifecycle
5. Each of the 4 test methods gets its own nodeid and can run independently
6. **Do NOT patch `_LazyTenantSession`** — instead investigate why the original test's `MockAuthStrategy` tenant_id doesn't match. The public seam is `os.environ["MPANGO_ENV"] = "test"` which triggers `MockAuthStrategy`. If the mock's default `tenant_id` (all-zeros UUID) doesn't match the dynamic binding's `wholesaler_id`, the proper fix is either:
   - Set the mock's `tenant_id` through the constructor (if `get_auth_strategy()` allows it), OR
   - Use `app.dependency_overrides` to inject a mock auth strategy with the correct tenant_id, OR
   - If no public seam exists, document this and propose a minimal, well-scoped test utility

### Option B: Full rewrite with pytest fixtures

1. Restore original file
2. Rewrite as pytest (not unittest) with `conftest.py` fixtures
3. Use `@pytest.fixture(scope="module")` for shared seed data
4. 4 independent `test_*` functions
5. This is more work but cleaner long-term

### Decision needed from CTO:
- **Option A or B?**
- **Should the `_LazyTenantSession` patch be retained with justification, or replaced?**
- **Is the DB state in the `windsurf mpango erp` worktree's Docker container corrupted by my alembic_version stamp?** (I stamped it from `020` to `017`)

---

## 8. Side Effects to Address

| Issue | Impact | Recommendation |
|-------|--------|----------------|
| DB `alembic_version` stamped to `017` in `windsurf mpango erp` container | Container `mpango_postgres` is shared; the stamp change persists | CTO to decide: re-stamp to correct version or rebuild container |
| `backend/tests/test_b5_real_db.py` written in wrong worktree | File at `windsurf mpango erp/backend/tests/test_b5_real_db.py` is a different (urllib-based) version | Not in target worktree, low impact |
| Ledger written to `globalStorage` | Not in project tree | This correction ledger is in the correct location |

---

## 9. Summary

| Item | Fact |
|------|------|
| Target branch | `ops/integration-rehearsal-clean-2026-05-08` |
| Target HEAD | `2666386a` |
| Alembic head | `021_tenant_payments_retailer_id_transaction_id` |
| B5 test status | **FAIL** — `ValueError: signal only works in main thread` |
| Modified files | 1 (`backend/tests/test_b5_real_db.py`) |
| Untracked files | 2 (`cycle_3c` diagnosis, `resolve_conflict.py`) |
| Directives violated | 4 of 7 (independent nodeids, no private patch, test must pass, ledger location) |
| Proposed next step | CTO selects Option A or B; I implement only after approval |

---

## 10. Containment Completed

**Executed at:** 2026-05-11 14:49 (Cycle 3D Containment, CTO-directed)

### 10.1 Failed rewrite restored

The failed `backend/tests/test_b5_real_db.py` rewrite was restored to HEAD via:

```
git restore --source=HEAD -- backend/tests/test_b5_real_db.py
```

### 10.2 Current code diff

```
git diff --name-status
(empty — zero modified files)
```

No code changes remain.

### 10.3 Current git status

Only untracked files:

```
?? ai-ledger/ops/2026-05-11_cycle_3c_b5_legacy_order_seed_diagnosis.md
?? ai-ledger/ops/2026-05-11_cycle_3d_correction_plan.md
?? resolve_conflict.py
```

- 2 ledger files — documenting Cycle 3C diagnosis and Cycle 3D correction
- `resolve_conflict.py` — prior session utility, kept untracked per CTO instruction

### 10.4 Alembic heads

```
021_tenant_payments_retailer_id_transaction_id (head)
```

Single head, no divergence.

### 10.5 Payment mainline + schema guard tests

```
poetry run pytest tests/test_payments_api.py tests/test_payment_atomicity.py \
  tests/test_phase5_order_payment.py tests/test_payments_schema_contract.py \
  -q --tb=short

67 passed, 1 xfailed, 0 failed, 41 warnings in 4.11s
```

| File | Result |
|------|--------|
| `test_payments_api.py` | 5 passed |
| `test_payment_atomicity.py` | 2 passed |
| `test_phase5_order_payment.py` | 44 passed, 1 xfailed |
| `test_payments_schema_contract.py` | 14 passed |

All payment tests green. No regressions introduced.

### 10.6 Cycle 3D conclusion

- **Cycle 3D is NOT complete.** The B5 dynamic rewrite was attempted, failed, and has been fully reverted.
- **Not a Cycle 3B promotion blocker.** All mainline payment tests pass; the B5 real-DB test remains in its original (hardcoded-ID) state at HEAD, which is the same state that existed before Cycle 3D began.
- **Deferred to Test Harness Track / Cycle 4A.** The B5 rewrite requirement is recorded here for a future cycle with the right approach.
- **Lessons learned for the next B5 rewrite attempt:**
  1. **Use real running backend HTTP endpoint**, not `TestClient(app)`. `TestClient` + `anyio` on Windows triggers `ValueError: signal only works in main thread`. The correct approach is to make HTTP calls to the running container (or a test-specific container) just like the original curl-based script did.
  2. **4 B5 scenarios must have independent nodeids.** Each of `test_cash_payment`, `test_transfer_payment_first`, `test_idempotent_replay`, `test_idempotency_violation` must be a separate `def test_*` method. Merging into a single method to work around event-loop issues is not acceptable.
  3. **No patching private auth internals.** Monkey-patching `_LazyTenantSession._ensure_session` is fragile and tightly coupled to implementation. If no public seam exists for setting the tenant_id on mock auth, this must be documented and a minimal public seam proposed as a separate, reviewed change.
  4. **No hardcoded ORDER_ID / BINDING_ID.** Dynamic seed data via `_psql()` queries is the correct direction and should be preserved in the next attempt.
  5. **Always run in the correct target worktree.** Verify branch and HEAD before executing.
