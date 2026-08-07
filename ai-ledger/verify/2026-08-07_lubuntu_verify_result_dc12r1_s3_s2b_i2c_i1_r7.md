# Lubuntu Independent Verification Result -- DC-12R1-S3-S2B-I2C-I1-R7

**Date**: 2026-08-07  
**Executor**: Lubuntu host `ivy-20149` (Linux 7.0.0-28-generic x86_64, Ubuntu 24.04)  
**Verdict**: `INDEPENDENT_VERIFY_PASS`

---

## 1. Execution Environment

| Item | Value |
|------|-------|
| Host | `ivy-20149`, Linux 7.0.0-28-generic x86_64 |
| OS | Ubuntu 24.04.1 LTS |
| Python | 3.12.3 |
| Docker | 29.1.3 |
| PG image | `postgres:16-alpine` (sha256:de3a4eab8fdf...) |
| Redis image | `redis:7-alpine` (sha256:487efc061638...) |
| PG max_connections | 300 (raised from default 100 to avoid pool exhaustion) |
| Clone type | **Full clone** (NOT worktree) |
| `git rev-parse --git-dir` | `.git` (directory, not `gitdir:` pointer) |
| `.git/HEAD` content | `4c322c2ac8568d9d1afe04c8968058f8a1c6b90f` (detached) |
| Candidate HEAD | `4c322c2ac8568d9d1afe04c8968058f8a1c6b90f` |

### SHA discrepancy note

The instruction document specifies R6 baseline SHA `f5d06342ae34a3f1e7a1916306950fe41ec0d4d2`. This SHA does
NOT exist in the remote repository (`git fetch` returns "not our ref"). The actual parent of candidate
`4c322c2` is `f5d06342ae34a5f1e7a1916306950fe41ec0e4d2` (differences at positions: `3`->`5`, `d`->`e`).
The actual parent commit message is "test(i2c-i1-r6): fix final test evidence integrity -- no production code
changes", confirming it IS the R6 commit. This is a transcription error in the instruction document, not a
verification failure.

### Stack configuration

| Stack | PG port | Redis port | Database | User |
|-------|---------|------------|----------|------|
| A | 59355 | 59356 | test_mpango | test_user |
| B | 59357 | 59358 | test_mpango | test_user |

Both stacks: fresh `test_mpango` database, alembic upgrade head (037), Redis FLUSHALL before each gate.

---

## 2. Step A -- R7 Code Modifications Exist

| Check | Expected | Result |
|-------|----------|--------|
| A.1 `_extract_constraint_name(exc_info.value)` | Line present with exact equality assert | PASS -- line 1357, `constraint == "ux_payments_receipt_number"` |
| A.2 No `str(exc_info.value)` substring matching | No matches | PASS -- zero matches (R6 substring assert removed) |
| A.3 All 4 IDs initialized before `try:` | oid/pay1_id/pay2_id/did before try | PASS -- lines 1333-1336, `try:` at line 1338 |
| A.4 Order creation inside `try:` | `oid = await _seed_confirmed_order` after try | PASS -- relative line 37 (try at relative 14) |

---

## 3. Step B -- Printable-Records Suite (Two Stacks)

| Run | Stack | Order | Result |
|-----|-------|-------|--------|
| B.1 | A | Natural | **36 passed**, 0 failed, 0 errors (103.74s) |
| B.2 | A | Reverse (3 named classes + full file) | **44 passed**, 0 failed, 0 errors (131.16s) |
| B.3 | B | Natural | **36 passed**, 0 failed, 0 errors (102.83s) |

Reverse-order run total of 44 = 8 (from 3 named classes) + 36 (full file), confirming no state residue.

---

## 4. Step C -- Full Backend Suite (Non-Worktree, KEY Test)

### Results

| Metric | Stack A | Stack B |
|--------|---------|---------|
| Collected | 3279 | 3279 |
| **Passed** | **3216** | **3216** |
| Skipped | 48 | 48 |
| XFailed | 15 | 15 |
| XPassed | 0 | 0 |
| **Failed** | **0** | **0** |
| **Errors** | **0** | **0** |
| Exit code | 0 | 0 |
| Duration | 1235.76s (20:35) | 1266.56s (21:06) |

**Totals identical across both stacks. Accounting gap = 0.**

### FAILED lines

None. `grep "^FAILED"` returns zero on both logs.

### u6h2/u6h3 guard declaration

**Both guards PASSED.**

Explicit verification run (Stack A):

```
tests/test_u6h2_tenant_provisioning_wholesaler_schema.py::test_forbidden_wholesaler_api_crud_repository_and_bootstrap_files_are_untouched PASSED
tests/test_u6h3_tenant_provisioning_reconcile_cleanup.py::test_forbidden_wholesaler_api_crud_repository_and_bootstrap_files_are_untouched PASSED
2 passed in 1.03s
```

The guards run `git diff --name-only 6a8ddcf348e9b1bdcc902929011e6212cc675cf8 --` from the repo root and assert
the changed file set is disjoint from FORBIDDEN_EDIT_PATHS. On the full clone, `git diff` resolves correctly,
producing the expected empty intersection. The Zcode worktree failures are NOT reproduced.

### Comparison with Zcode host

| Metric | Zcode (worktree) | Lubuntu (full clone) | Delta |
|--------|-----------------|---------------------|-------|
| Passed | 3162 | 3216 | +54 |
| Skipped | 100 | 48 | -52 |
| XFailed | 15 | 15 | 0 |
| Failed | 2 | 0 | -2 |
| Errors | 0 | 0 | 0 |
| Total | 3279 | 3279 | 0 |

Delta explanation: 54 more passed = 52 previously-skipped tests now running + 2 previously-failed guards now passing.

---

## 5. Step D -- R7 Diff Scope

### D.1: R7 vs R6 diff (exactly 2 files)

```
ai-ledger/product-ai/2026-08-04_dc12r1_s3_s2b_i2c_i1_printable_records_backend.md | 126 ++++++++++++++++-----
backend/tests/test_dc12r1_s3_s2b_i2c_i1_printable_records.py                         |  49 +++++---
2 files changed, 132 insertions(+), 43 deletions(-)
```

### D.2: Forbidden path intersection (empty)

`git diff --name-only 6a8ddcf348e9b1bdcc902929011e6212cc675cf8 --` checked against all 6 FORBIDDEN_EDIT_PATHS.
Intersection: **empty**. Guard passes.

### D.3: Static quality

| Check | Result |
|-------|--------|
| `git diff --check` | Clean (no whitespace errors) |
| `py_compile` | OK |
| `detect-secrets scan` | 0 secrets |

---

## 6. Conclusion

`INDEPENDENT_VERIFY_PASS`

- R7 modifies exactly 2 allowed files (1 test, 1 ledger), no production code
- Printable-records suite: 36/36 on both stacks, order-independent
- Full backend suite: 3216 passed, 0 failed, 0 errors on both stacks, identical totals
- u6h2/u6h3 git-diff guards: PASSED on full clone (worktree issue NOT reproduced)
- All quality gates clean

---

## 7. Limitations

1. **Clone path**: `/opt` was not writable without sudo. Full clone performed at
   `/tmp/opencode/mpango-i2ci1-r7-verify` instead. This is still a full clone (`.git` is a directory),
   satisfying the non-worktree requirement.
2. **R6 baseline SHA**: Instruction document contains a transcription error
   (`...ae34a3f1...ec0d4d2` vs actual `...ae34a5f1...ec0e4d2`). Verified using actual parent SHA.
3. **max_connections**: Raised from default 100 to 300 to prevent `TooManyConnectionsError` pool
   exhaustion during full-suite runs. First Stack A attempt (with max_connections=100) produced 68
   setup errors; re-run with 300 produced 0 errors.
4. **Single host**: Both stacks run on the same host with different Docker port mappings. No process
   overlap between runs (sequential execution).
