# DC-12R1-H4-R1: Event-Loop/AsyncPG Pool Isolation Repair

**Date**: 2026-08-02
**Base SHA**: `9528cb6de5f668ed09feb7a1eaa9aafaa537987d`
**Branch**: `codex/dc12r1-h4-event-loop-pool-isolation-2026-08-02`
**Predecessor**: DC-12R1-H4-R0 (forensics)

---

## Objective

Eliminate the proven exact-suite event-loop/pool contamination identified in H4-R0
by replacing `asyncio.run()` with `run_coroutine()` in the R4-R1 real Alembic
upgrade test file.

---

## Changes Made

### 1. `tests/test_dc12r1_s3_s2b_i1_r4_r1_real_alembic_upgrade.py`

**Import** (line 41):
- Added `run_coroutine` to the existing import from `tests.async_test_utils`.

**Site 1** — `_setup_tenant()` method (was line 310-313):
- Removed local `import asyncio`.
- Replaced `asyncio.run(_bootstrap_and_revert_to_036(schema, db_url))` with
  `run_coroutine(_bootstrap_and_revert_to_036(schema, db_url))`.

**Site 2** — `_full_proof()` method (was line 1049-1055):
- Removed local `import asyncio`.
- Replaced `asyncio.run(_bootstrap_and_revert_to_036(schema, db_url))` with
  `run_coroutine(_bootstrap_and_revert_to_036(schema, db_url))`.

**Site 3** — `test_cross_tenant_failure_neither_mutates()` (was line 1349, 1362):
- Removed local `import asyncio`.
- Replaced `asyncio.run(_bootstrap_and_revert_to_036(schema_a, db_url))` with
  `run_coroutine(_bootstrap_and_revert_to_036(schema_a, db_url))`.

**Site 4** — `test_cross_tenant_failure_neither_mutates()` (was line 1363):
- Replaced `asyncio.run(_bootstrap_and_revert_to_036(schema_b, db_url))` with
  `run_coroutine(_bootstrap_and_revert_to_036(schema_b, db_url))`.

**Note**: The forensics identified 2 proven sites (313, 1055). The file contained
4 total `asyncio.run()` call sites with the identical pattern. All 4 were
repaired to ensure complete elimination of throwaway event loop creation.

### 2. `tests/test_dc12r1_h4_event_loop_pool_isolation.py` (NEW)

7 regression tests across 3 test classes:
- `TestRunCoroutinePreservesEventLoop` (3 tests): loop identity, openness, non-None.
- `TestGlobalEngineNotContaminated` (3 tests): SELECT 1 via global engine, after
  dispose, rollback without InterfaceError.
- `TestNoLeakedConnections` (1 test): pg_stat_activity shows 0 idle Mpango ERP
  connections after local engine lifecycle via run_coroutine + global dispose.

### 3. No other files modified

- `alembic/env.py`: NOT modified (still uses `asyncio.run()` at line 211 — this
  is wrapped by `_run_alembic_preserving_loop` which restores the loop).
- `database/session.py`: NOT modified.
- `conftest.py`: NOT modified.
- Product code: NOT modified.
- Migration files: NOT modified.

---

## RED Proof (3x reproduction on base code)

Minimal contaminating sequence:
1. `test_dc11t4c_reporting_bootstrap_contract.py::test_reporting_tenant_teardown_removes_schema_and_registry_rows`
2. `test_dc12r1_s3_s2b_i1_r4_r1_real_alembic_upgrade.py::TestRealAlembicUpgradeFailClosed::test_missing_payments_table_fails`
3. `test_dc1g_retailer_registration_binding_balance.py::test_binding_repository_create_sets_zero_outstanding_balance`

| Run | Duration | Result | Error |
|-----|----------|--------|-------|
| 1 | 12.41s | 1 failed, 2 passed, 1 error | `RuntimeError: Task got Future attached to a different loop` |
| 2 | 11.84s | 1 failed, 2 passed, 1 error | Same |
| 3 | 12.27s | 1 failed, 2 passed, 1 error | Same |

---

## GREEN Proof (3x reproduction after fix)

Same 3-test sequence after correction:

| Run | Duration | Result |
|-----|----------|--------|
| 1 | 13.44s | 3 passed |
| 2 | 10.46s | 3 passed |
| 3 | 10.88s | 3 passed |

**Loop identity**: Preserved (same loop object before and after run_coroutine).
**Loop state**: Open (not closed).
**Leaked connections**: 0 (pg_stat_activity confirmed no idle Mpango ERP connections).

---

## Gate Results

| Gate | Result | Details |
|------|--------|---------|
| R4-R1 file | PASS | 29 passed in 166.79s |
| DC11T4C file | PASS | 4 passed in 13.39s |
| H4 regression file | PASS | 7 passed in 1.47s |
| I1 migration contract bundle | PASS | 79/79 passed in 193.41s |
| Permission/bootstrap bundle | PASS | 43 passed, 5 xfailed in 49.75s |
| Reverse order | PASS | 3 passed in 10.98s |
| dc1g alone | PASS | 2 passed in 2.75s |
| dc3b alone | PASS | 16 passed in 40.31s |

---

## Full Suite Runs

### Run #1 (h4r1-pg, port 56611)

```
1 failed, 3115 passed, 48 skipped, 15 xfailed in 1151.06s (0:19:11)
```

### Run #2 (h4r1b-pg, port 56621)

```
1 failed, 3115 passed, 48 skipped, 15 xfailed in 1120.84s (0:18:40)
```

**Totals identical**: 3115 passed, 1 failed, 48 skipped, 15 xfailed in both runs.

---

## Pre-Existing Failure Analysis

### Failed test

```
tests/test_dc12r1_s1_r5_migration_preflight_exact_catalog.py::
    test_actual_alembic_035_to_036_failure_rolls_back_then_repaired_upgrade_noops
```

### Error

```
037_payment_declarations_schema_py.PreflightFailure:
    037 preflight (registry) failed:
    t_*.payments: payments table is missing
    t_*.orders: orders table is missing
```

### Root cause

The test was written when migration 036 was the sole head revision. It:

1. Upgrades a temporary database to revision 035.
2. Seeds a tenant registration with `_tenant_auth_ddl` (creates users, roles,
   permissions, user_roles, role_permissions — but NOT payments/orders).
3. First `run_alembic_upgrade(config, "head")` fails at 036 preflight
   (SETUP_TABLE exists) — expected behavior, rolls back.
4. Drops SETUP_TABLE (repair).
5. Second `run_alembic_upgrade(config, "head")` now proceeds past 036 to 037,
   where 037's preflight checks registered tenant schemas for payments/orders
   tables. These tables don't exist because the tenant was never bootstrapped
   with business tables.
6. Test asserts `_current_revision == REV_036` and `_script_heads == [REV_036]`
   — both wrong now that 037 is the sole head.

### Pre-existing confirmation

- Fails on base SHA `9528cb6` WITHOUT any H4-R1 changes (verified via `git stash`).
- Not caused by event-loop contamination (fails in isolation on fresh database).
- Not fixable within allowed implementation scope (test file not in allowed list).
- Requires updating test expectations for 037 head (change `"head"` to `REV_036`
  or update assertions to expect `REV_037`).

### Classification: PRE-EXISTING — introduced by DC-12R1-S3-S2B-I1 merge

---

## Verdict

**STOP_AND_REPORT_CTO**

The event-loop/asyncPG pool contamination is fully eliminated (proven via
3x RED + 3x GREEN + 7 regression tests + all scoped gates pass). However,
the exact full-suite gate has 1 pre-existing red node
(`test_actual_alembic_035_to_036_failure_rolls_back_then_repaired_upgrade_noops`)
that exists on the base SHA and cannot be resolved within the allowed
implementation scope.

**Exact failed/error accounting**:
- Failed: 1 (`test_dc12r1_s1_r5_migration_preflight_exact_catalog.py::test_actual_alembic_035_to_036_failure_rolls_back_then_repaired_upgrade_noops`)
- Errors: 0
- Passed: 3115
- Skipped: 48
- Xfailed: 15
