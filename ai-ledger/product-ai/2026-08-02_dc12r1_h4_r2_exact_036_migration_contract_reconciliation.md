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

## Self-Review (H4-R2, Lubuntu execution)

- [x] Exactly two allowed files changed (s1_r5 test + this ledger)
- [x] Exactly three `"head"` calls changed to `REV_036`
- [x] Exactly two stale `_script_heads` assertions removed
- [x] H4 four-call `run_coroutine` repair remains byte-for-byte unchanged (empty diff verified)
- [x] No product, migration, frontend, config, dependency or lockfile changes
- [x] No skip, xfail, timeout increase or weakened financial/catalog assertion
- [x] Report numbers and verdict agree with raw test evidence (3116 passed, 0 failed, 0 errors)
- [x] Final worktree clean after commit

---

## Original H4-R2 Verdict (Corrected/Superseded by R2-R1)

> **PASS_FOR_CTO_DC12R1_H4_R2_MERGE_REVIEW** (original wording)
>
> Both exact full-suite runs exit 0 with 3116 passed, 0 failed, 0 errors, and
> identical totals. The single pre-existing RED node from H4-R1 is closed. The
> H4-R1 event-loop/pool repair is preserved without modification.

The original H4-R2 verdict and all runtime evidence above remain valid and are
preserved as historical evidence. The trailing statement "All other quality
gates pass" was inaccurate: it did not distinguish between (a) Lubuntu runtime
gates that passed, (b) the GitNexus tooling limitation in the Lubuntu
environment, and (c) complementary quality evidence that was not yet recorded.
This R2-R1 revision corrects that evidence-contract contradiction.

---

## Independent CTO Complementary Quality Evidence

The following evidence was executed independently by the **CTO review
environment** against source SHA `a4176a5`. It was not executed by Lubuntu and
is attributed solely to the CTO environment. It closes the GitNexus
quality-evidence gap that could not be satisfied in the Lubuntu execution
environment.

### GitNexus analyze

- Repository indexed successfully
- 14,269 nodes
- 44,213 edges
- 922 clusters
- 300 flows

### GitNexus status

- Indexed commit: `a4176a5`
- Current commit: `a4176a5`
- Status: up-to-date

### GitNexus detect_changes

- Comparison base: `f031e033`
- Changed files: 2
- Changed count: 21
- Affected count: 0
- Affected processes: 0
- Risk level: low

### GitNexus impact

- Target: `test_actual_alembic_035_to_036_failure_rolls_back_then_repaired_upgrade_noops`
- Risk: LOW
- Direct callers: 0
- Affected processes: 0
- Affected modules: 0

### Independent CTO hygiene

- py_compile: PASS
- Scoped pre-commit: PASS
- Scoped detect-secrets: 0 findings
- git diff remained clean after checks

---

## No Full-Suite Rerun Required

This R2-R1 revision changes only this ledger Markdown file. Source SHA
`a4176a5` and its runtime evidence remain unchanged: no code, test, migration,
or configuration file is modified. The two exact full-suite runs (3116 passed,
0 failed, 0 errors, identical totals) executed by Lubuntu against `a4176a5`
remain valid and authoritative.

---

## Corrected Quality-Evidence Summary

| Evidence category | Source | Status |
|-------------------|--------|--------|
| Runtime tests (RED/GREEN/exact suite) | Lubuntu | PASS (all gates, 3116/0/0) |
| py_compile, git diff --check, detect-secrets | Lubuntu | PASS |
| GitNexus impact/detect_changes/analyze/status | CTO environment | PASS (low risk, 0 affected) |
| Scoped pre-commit, detect-secrets | CTO environment | PASS |
| GitNexus availability in Lubuntu | Lubuntu | UNAVAILABLE (tooling limitation, honestly reported) |

---

## Verdict

**PASS_FOR_CTO_DC12R1_H4_R2_R1_MERGE_REVIEW**

The H4-R2 source correction is confirmed by complete Lubuntu runtime evidence
(3116 passed, 0 failed, 0 errors across two independent full-suite runs with
identical totals) and by independent CTO complementary quality evidence
(GitNexus analyze/status/detect_changes/impact all clean, risk LOW). The
GitNexus tooling limitation in the Lubuntu environment is acknowledged and
closed by the CTO-side evidence. No exact full-suite rerun is required because
R2-R1 modifies only this ledger.
