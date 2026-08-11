# Lubuntu Independent Final Runtime Verification -- DC-12R1-S3-S2B-I2C-I2B-R8-V2

**Date**: 2026-08-11
**Executor**: Lubuntu host `ivy-20149` (Linux 7.0.0-28-generic x86_64, Ubuntu 24.04)
**Candidate**: `f6ac69ee01cc4d30f2a34f1ef2030fd70f2e518f`
**Predecessor**: `fce3e6d58e26bf8e2071deac63050c1f5f5c9364`
**Protected baseline**: `d45b5020b122b13c407a1c9204b18e587f9803fc`
**Source branch**: `zcode/dc12r1-s3-s2b-i2c-i2b-contract-d-statement-2026-08-10`
**Kilo report branch**: `reports/dc12r1-i2c-i2b-r8-v1-kilo-review-2026-08-11` (SHA `300ebae5`)
**Verdict**: **`PASS_DC12R1_S3_S2B_I2C_I2B_R8_V2_INDEPENDENT_FINAL`**

---

## P1. Evidence preflight

| Check | Result |
|-------|--------|
| Candidate SHA exact | `f6ac69ee01cc4d30f2a34f1ef2030fd70f2e518f` -- PASS |
| Predecessor SHA exact | `fce3e6d58e26bf8e2071deac63050c1f5f5c9364` -- PASS |
| Protected baseline SHA exact | `d45b5020b122b13c407a1c9204b18e587f9803fc` -- PASS |
| Predecessor = candidate direct parent | `git rev-parse HEAD~1` = `fce3e6d5` -- PASS |
| Baseline ancestry | `git merge-base --is-ancestor baseline candidate` exit 0 -- PASS |
| Kilo branch exists remotely | SHA `300ebae513f67e724ff447fdf375d2bc79f10f24` -- PASS |
| Kilo deliverables read | `2026-08-11_dc12r1_i2c_i2b_r8_v1_kilo_review.md` + `_kilo_findings.csv` (9 findings, all PASS) -- PASS |

### R8 delta (predecessor..candidate) = exactly 3 files

| File | Role |
|------|------|
| `backend/tests/tools/gen_node_csv.py` | generator (the fix) |
| `backend/tests/test_dc12r1_contract_d_r7_gen_fail_closed.py` | generator tests (+3 R8 tests) |
| `ai-ledger/product-ai/2026-08-10_dc12r1_s3_s2b_i2c_i2b_contract_d_statement.md` | ledger |

### Aggregate baseline..candidate scope = 23 files (reconciled)

The aggregate `d45b5020..f6ac69ee` spans 11 commits (the full Contract D feature R1-R8) and touches 23 files. These decompose as:
- **19 approved feature-scope files** (6 backend product + 7 frontend product + 4 Contract D feature tests + 1 read-only-finance test + 1 catalog-hardening test)
- **4 node-outcomes evidence-pipeline files** (generator tool + 2 generator/CSV-validity tests + committed node-outcomes CSV), each individually approved in the R4-R7 Kilo reviews.

Reconciliation: 23 = 19 + 4. Zero unexplained files.

**Forbidden file types in scope**: NONE. No migration, alembic version, permission, config, dependency, lockfile (`pyproject.toml`/`poetry.lock`/`package.json`/`pnpm-lock.yaml`), deployment, Dockerfile, or `.env` changes. Alembic versions dir untouched; single head `037_payment_declarations_schema`.

---

## P2. R8 causal gate

### 7 generator tests + 5 CSV-validity tests (candidate)

```
tests/test_dc12r1_contract_d_r7_gen_fail_closed.py .......  (7)
tests/test_dc12r1_contract_d_r5_node_csv.py .....          (5)
============================== 12 passed in 1.12s ==============================
```

### Predecessor causal reproduction (the R8 defect)

The predecessor (`fce3e6d5`) cleaned the temp file in an `except BaseException` block, but the round-trip validation failures `return 1` from *inside* the `try` -- a `return` does not trigger `except`, so the temp file leaked. Reproduced by loading each generator version and injecting the 3 R8 post-temp failures:

| Scenario | Version | rc | target preserved | leftover temp |
|----------|---------|----|------------------|---------------|
| non3col, existing target | predecessor | 1 | YES | **`.gen_node_csv_iey1khud.tmp`** (LEAK) |
| non3col, existing target | candidate | 1 | YES | `[]` (clean) |
| illegal-outcome, existing target | predecessor | 1 | YES | **`.gen_node_csv_kp5p6lv8.tmp`** (LEAK) |
| illegal-outcome, existing target | candidate | 1 | YES | `[]` (clean) |
| non3col, absent target | predecessor | 1 | YES (absent) | **`.gen_node_csv_frk4rxon.tmp`** (LEAK) |
| non3col, absent target | candidate | 1 | YES (absent) | `[]` (clean) |

The candidate's `finally` block cleans up on BOTH `return` and exception -- the fix is **causal** (3/3 leak on predecessor, 0/3 leak on candidate).

### Duplicate XML fails before dict overwrite

`test_duplicate_node_id_fails_and_produces_no_output`: two identical testcases -> exit 1, NO output file. The `_parse()` check fires before dict insertion. PASS.

### Legal dynamic A-only/B-only publishes atomically

`test_legal_dynamic_a_only_b_only_publishes_exit0`: exit 0, output published, round-trips as 3-column, correct `absent` markers. PASS.

---

## P3. Contract D focused gate (69)

Files: `test_dc12r1_contract_d_statement_print.py` (57) + `test_dc12r1_contract_d_r5_node_csv.py` (5) + `test_dc12r1_contract_d_r7_gen_fail_closed.py` (7) = **69 collected**.

| Run | Result |
|-----|--------|
| Natural order | **69 passed**, 0 failed, 0 errors (298.20s) |
| Reverse node order | **69 passed**, 0 failed, 0 errors (310.75s) |

No new skip, xfail, or deselection in either order.

---

## P4. Contract D regression bundle (192 nodes, two stacks)

CTO-approved 8-file composition (Option 1), confirmed `--collect-only` = 192 on candidate:

| Run | Stack | Result |
|-----|-------|--------|
| Bundle A | A (PG 59701 + Redis 59702) | **192 passed**, 0 failed, 0 errors (258.06s) |
| Bundle B | B (PG 59703 + Redis 59704) | **192 passed**, 0 failed, 0 errors (271.50s) |

---

## P5. Two exact full backend gates

Command (both stacks, identical): `poetry run pytest tests/ -q -rs --junitxml=<stack-specific-file>`.
No `--ignore`, `-k`, deselection, rerun, split, or timeout increase. Each stack: fresh disposable `test_mpango` DB (DROP/CREATE), `alembic upgrade head` = 037, Redis FLUSHALL, `MPANGO_ALLOW_TEMP_DB_CREATE=1`, `MPANGO_TEMP_DB_ALLOWED_PORTS` set.

| Run | Stack | Result |
|-----|-------|--------|
| #1 | A (PG 59701 + Redis 59702) | **3285 passed, 48 skipped, 15 xfailed -- 0 failed, 0 errors** (exit 0, 1716.46s) |
| #2 | B (PG 59703 + Redis 59704) | **3285 passed, 48 skipped, 15 xfailed -- 0 failed, 0 errors** (exit 0, 1714.15s) |

Identical pass/skip/xfail totals across both independent runs.

### JUnit comparison via fail-closed generator (exit 0)

```
nodes A=3348 B=3348 union=3352
outcomes A: {'passed': 3285, 'skipped': 48, 'xfailed': 15}
outcomes B: {'passed': 3285, 'skipped': 48, 'xfailed': 15}
shared-node outcome diffs: 0
accounting gap (A-B): {'passed': 0, 'xfailed': 0, 'skipped': 0}
OK: all checks passed    EXIT=0
```

### Disclosed dynamic node IDs (4 A-only + 4 B-only, NOT normalized)

The 8 absent-row differences are all dynamic parametrize IDs that change between runs:
- `test_u4d_intake_parser_preview.py::test_parser_rejects_csv_and_xlsx_cell_length[cell_too_large.xlsx-<binary>]` -- binary xlsx bytes in the ID
- `test_u4d_intake_parser_preview.py::test_parser_rejects_csv_and_xlsx_column_limit[too_many_columns.xlsx-<binary>]`
- `test_u4d_intake_parser_preview.py::test_parser_rejects_csv_and_xlsx_header_length[header_too_large.xlsx-<binary>]`
- `test_u6i3_owner_credential_setup_consume.py::test_invalid_or_missing_raw_token_fails_neutrally[u6i3-missing-<hex>]` -- random hex token

Red-node accounting gap = 0.

---

## P6. Frontend

| Gate | Result |
|------|--------|
| `pnpm vitest run` | **269 passed, 1 failed** (of 270); 20 test files |
| `pnpm build` | **exit 0**, built in 11.78s |
| String-only money rendering | `renders exact large + high-precision amounts without rounding` -- PASS |
| Statement route ownership | `I2C-I2B -- actual AppRouter guard matrix across all 8 print routes` (retailer ALLOW + wholesaler DENY) -- PASS |

### The 1 vitest failure (disclosed, not a candidate regression)

`StatementPrintWorkspace.test.tsx > R1 rule 6 -- EAT calendar dates > frozen time: the UTC calendar date differs from EAT` asserts `utcDate == '2026-08-10'` while `eatToday() == '2026-08-11'`. This only holds during the 21:00-00:00 UTC window where EAT (UTC+3) has crossed midnight but UTC has not. At verification time (07:06 UTC) both dates are `2026-08-11`, so the UTC assertion fails. **Frontend files are byte-identical to the predecessor** (R8 delta is 3 backend files only, confirmed by Kilo finding R8-03), so this is a time-of-day artifact, not a candidate regression.

---

## P7. Quality and cleanup

| Check | Result |
|-------|--------|
| `py_compile` (3 R8 files) | clean |
| `git diff --check` (predecessor..candidate) | clean |
| scoped `pre-commit run` (3 R8 files) | trim-trailing-whitespace / end-of-file / large-file / detect-secrets -- all Passed |
| scoped `detect-secrets scan` (3 R8 files) | `results: {}` (no findings) |
| mojibake / UTF-8 scan (3 R8 files) | clean |
| GitNexus `analyze` | 32,852 nodes / 53,671 edges / 681 clusters / 300 flows -- OK |
| GitNexus `status` | indexed commit = current commit = `f6ac69e`; status: up-to-date |
| GitNexus `detect_changes` | not available in this CLI build (same as Kilo R8-09) |
| Candidate ref unchanged | `f6ac69ee01cc4d30f2a34f1ef2030fd70f2e518f` |
| Source branch tip unchanged | `f6ac69ee01cc4d30f2a34f1ef2030fd70f2e518f` |
| Protected baseline ancestry | still ancestor of candidate |

Task-owned containers, volumes, networks, clone and logs removed after delivery (see teardown log).

---

## Verdict

**`PASS_DC12R1_S3_S2B_I2C_I2B_R8_V2_INDEPENDENT_FINAL`**

All seven phases pass. The frozen R8 candidate `f6ac69ee` satisfies every mandated gate: lineage exact, R8 delta = 3 files, aggregate scope reconciled (23 = 19 + 4, zero forbidden file types), the generator cleanup fix is causal (3/3 predecessor leak vs 0/3 candidate leak), 69 focused (natural + reverse), 192 regression bundle x2, 3285/48/15 full backend x2 (identical, 0 failed/errors), JUnit generator comparison exit 0 with 8 disclosed dynamic IDs and gap=0, frontend build exit 0 with named gates green, and all quality checks clean.
