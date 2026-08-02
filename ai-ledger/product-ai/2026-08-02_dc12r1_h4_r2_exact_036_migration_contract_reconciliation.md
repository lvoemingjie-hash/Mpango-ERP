# DC-12R1-H4-R2: Exact-036 Migration Test Contract Reconciliation

**Date**: 2026-08-02
**Starting SHA**: `f031e033680b5d2fa62c3c0c5777e75d4a0639f3`
**Protected baseline**: `9528cb6de5f668ed09feb7a1eaa9aafaa537987d`
**Branch**: `codex/dc12r1-h4-r2-exact-036-contract-reconciliation-2026-08-02`

---

## Objective

Close the single remaining exact-suite RED node by reconciling the stale
migration-036-specific test contract in
`test_dc12r1_s1_r5_migration_preflight_exact_catalog.py`. Preserve the accepted
H4-R1 event-loop/pool repair without modification.

---

## Baseline Proof

| Check | Result |
|-------|--------|
| `git fetch --all --prune` | Completed |
| Starting branch tip = `f031e03` | PASS |
| `origin/product-dev-recovered` = `9528cb6` | PASS |
| Protected baseline is ancestor of H4 starting SHA | PASS |
| Clean isolated worktree created | PASS |

---

## RED Proof

**Target node**: `test_actual_alembic_035_to_036_failure_rolls_back_then_repaired_upgrade_noops`

**Phase**: Second `run_alembic_upgrade(config, "head")` at line 716 (repaired
upgrade attempt). After dropping `SETUP_TABLE`, the upgrade proceeds past 036 to
037, where 037's preflight checks registered tenant schemas for payments/orders
tables. The tenant was seeded with only auth tables (no business tables), so the
037 preflight fails.

**Exception**:
```
037_payment_declarations_schema_py.PreflightFailure:
    037 preflight (registry) failed:
    t_*.payments: payments table is missing
    t_*.orders: orders table is missing
```

**Exit code**: 1 (test failure)
**Current Alembic head**: `037_payment_declarations_schema` (sole head)

**Root cause**: The test was written when migration 036 was the sole head
revision. It used `run_alembic_upgrade(config, "head")` and asserted
`_script_heads(config) == [REV_036]`. After migration 037 was added in the
DC-12R1-S3-S2B-I1 merge, `"head"` resolves to 037, not 036.

---

## Correction Applied

In `backend/tests/test_dc12r1_s1_r5_migration_preflight_exact_catalog.py`:

### Three `"head"` calls changed to `REV_036`:

1. Line 700 (first failed attempt inside `pytest.raises`):
   `run_alembic_upgrade(config, "head")` → `run_alembic_upgrade(config, REV_036)`

2. Line 716 (repaired upgrade):
   `run_alembic_upgrade(config, "head")` → `run_alembic_upgrade(config, REV_036)`

3. Line 722 (second upgrade no-op):
   `run_alembic_upgrade(config, "head")` → `run_alembic_upgrade(config, REV_036)`

### Two stale script-head assertions removed:

1. Was line 719: `assert _script_heads(config) == [REV_036]`
2. Was line 726: `assert _script_heads(config) == [REV_036]`

### Preserved assertions (all intact):

- `_current_revision(connection) == REV_035` (before and after first failure)
- `exc.value.__class__.__name__ == "PreflightFailure"` (fail-closed)
- `after_failure_payload == before_payload` (rollback fingerprint)
- `_current_revision(connection) == REV_036` (repaired upgrade reaches 036)
- `after_noop_payload == before_noop_payload` (second upgrade no-op fingerprint)
- Catalog fingerprint computation and printing

---

## GREEN Gates

| Gate | Result | Details |
|------|--------|---------|
| 1. Target node (2x) | PASS | 1 passed each run (6.43s, 5.69s) |
| 2. Complete s1_r5 file | PASS | 41 passed in 15.80s |
| 3. H4 regression file | PASS | 7 passed in 1.87s |
| 4. R4-R1 real Alembic file | PASS | 29 passed in 172.46s |
| 5. DC11T4C reporting teardown | PASS | 4 passed in 13.62s |
| 6. I1 migration contract bundle | PASS | 79/79 passed in 210.39s |
| 7. Permission/bootstrap bundle | PASS | 43 passed, 5 xfailed in 28.72s |
| 8a. Affected files original order | PASS | 83 passed in 205.57s |
| 8b. Affected files reverse order | PASS | 83 passed in 196.65s |

---

## Exact Full Backend Gate

### Run #1 (h4r2-pg, port 56631)

```
3116 passed, 48 skipped, 15 xfailed, 2091 warnings in 1165.54s (0:19:25)
```

**Exit code: 0. Failed: 0. Errors: 0.**

### Run #2 (h4r2b-pg, port 56641)

```
3116 passed, 48 skipped, 15 xfailed, 2089 warnings in 1134.96s (0:18:54)
```

**Exit code: 0. Failed: 0. Errors: 0.**

### Totals comparison

| Metric | Run #1 | Run #2 | Identical |
|--------|--------|--------|-----------|
| Passed | 3116 | 3116 | YES |
| Failed | 0 | 0 | YES |
| Errors | 0 | 0 | YES |
| Skipped | 48 | 48 | YES |
| Xfailed | 15 | 15 | YES |

---

## Quality Gates

| Gate | Result |
|------|--------|
| py_compile | PASS |
| git diff --check | PASS |
| detect-secrets | 0 findings |
| GitNexus impact | **UNAVAILABLE**: MCP server does not respond (timed out on startup). No substitution attempted. |
| GitNexus detect_changes | **UNAVAILABLE**: Same as above. |
| GitNexus analyze/status | **UNAVAILABLE**: Same as above. |

---

## Self-Review

- [x] Exactly two allowed files changed (s1_r5 test + this ledger)
- [x] Exactly three `"head"` calls changed to `REV_036`
- [x] Exactly two stale `_script_heads` assertions removed
- [x] H4 four-call `run_coroutine` repair remains byte-for-byte unchanged (empty diff verified)
- [x] No product, migration, frontend, config, dependency or lockfile changes
- [x] No skip, xfail, timeout increase or weakened financial/catalog assertion
- [x] Report numbers and verdict agree with raw test evidence (3116 passed, 0 failed, 0 errors)
- [x] Final worktree will be clean after commit

---

## Verdict

**PASS_FOR_CTO_DC12R1_H4_R2_MERGE_REVIEW**

Both exact full-suite runs exit 0 with 3116 passed, 0 failed, 0 errors, and
identical totals. The single pre-existing RED node from H4-R1 is closed. The
H4-R1 event-loop/pool repair is preserved without modification.

**GitNexus tooling note**: The GitNexus MCP server is configured in
`opencode.json` but does not respond (timed out on startup). This tooling
failure is reported per task rule rather than silently substituting another
claim. All other quality gates pass.
