# DC-12R1-S3-S2B-I2C-I2B-R8-V1 Kilo adversarial final source review

- Review mode: adversarial final source review
- Source branch: `zcode/dc12r1-s3-s2b-i2c-i2b-contract-d-statement-2026-08-10`
- Candidate SHA: `f6ac69ee01cc4d30f2a34f1ef2030fd70f2e518f`
- Predecessor SHA: `fce3e6d58e26bf8e2071deac63050c1f5f5c9364`
- Protected baseline: `d45b5020b122b13c407a1c9204b18e587f9803fc`
- Review worktree: detached/isolated at candidate, then local-only reports branch `reports/dc12r1-i2c-i2b-r8-v1-kilo-review-2026-08-11`
- Verdict: `PASS_FOR_CTO_DC12R1_S3_S2B_I2C_I2B_R8_V1_KILO_FINAL_REVIEW`
- Accounting gap: `0`

## Executive summary

R8 is a narrow generator-only correction. The candidate satisfies the mandated lineage, scope-freeze, source-ordering, cleanup, and publication requirements. The exact delta is three files only:

1. `backend/tests/tools/gen_node_csv.py`
2. `backend/tests/test_dc12r1_contract_d_r7_gen_fail_closed.py`
3. `ai-ledger/product-ai/2026-08-10_dc12r1_s3_s2b_i2c_i2b_contract_d_statement.md`

All checked product/API/frontend files, the main Contract D runtime test file, and the committed node CSV are byte-identical to R7. The generator now guarantees post-temp cleanup via `try/finally`, still performs duplicate detection before dict insertion, still validates before publication, and still publishes only via `os.replace()` after all checks pass. The seven generator tests are authentic and the three new post-temp tests would fail against R7 because R7 leaked `.gen_node_csv_*.tmp` residue on those failure paths.

## 1. SHA verification and lineage

Verified directly:

- `git rev-parse HEAD` -> `f6ac69ee01cc4d30f2a34f1ef2030fd70f2e518f`
- `git rev-parse zcode/dc12r1-s3-s2b-i2c-i2b-contract-d-statement-2026-08-10` -> `f6ac69ee01cc4d30f2a34f1ef2030fd70f2e518f`
- `git rev-parse fce3e6d58e26bf8e2071deac63050c1f5f5c9364` -> exact
- `git rev-parse d45b5020b122b13c407a1c9204b18e587f9803fc` -> exact

Lineage proofs:

- `git rev-parse f6ac69ee...^` -> `fce3e6d58e26bf8e2071deac63050c1f5f5c9364`
- `git merge-base --is-ancestor d45b5020... f6ac69ee...` -> exit `0`

Status: **PASS**

## 2. Exact R8 delta

`git diff --name-only fce3e6d5..f6ac69ee` returns exactly:

- `ai-ledger/product-ai/2026-08-10_dc12r1_s3_s2b_i2c_i2b_contract_d_statement.md`
- `backend/tests/test_dc12r1_contract_d_r7_gen_fail_closed.py`
- `backend/tests/tools/gen_node_csv.py`

`git diff --stat fce3e6d5..f6ac69ee` confirms only those three files changed.

Status: **PASS**

## 3. Frozen-file byte identity versus R7

### Product/API/frontend/runtime/CSV freeze proof

Checked by blob identity and path-scoped diff. These paths have identical blob IDs in `fce3e6d5` and `f6ac69ee`, with `git diff --name-only predecessor..candidate -- <paths>` returning no output:

- `backend/api/app.py`
- `backend/api/v1/client/statements.py`
- `backend/api/v1/statements.py`
- `backend/repositories/statement_repository.py`
- `backend/schemas/print.py`
- `backend/services/print_service.py`
- `backend/tests/test_dc12r1_contract_d_statement_print.py`
- `frontend/src/pages/client/FinanceBalancePage.tsx`
- `frontend/src/pages/finance/FinancePage.tsx`
- `frontend/src/pages/print/StatementPrintPage.tsx`
- `frontend/src/router/AppRouter.tsx`
- `frontend/src/services/statementService.ts`
- `frontend/src/tests/PrintableWorkspace.test.tsx`
- `frontend/src/tests/StatementPrintWorkspace.test.tsx`
- `frontend/src/types/statement.ts`
- `frontend/src/utils/printFormat.ts`
- `ai-ledger/product-ai/2026-08-10_dc12r1_s3_s2b_i2c_i2b_r4_node_outcomes.csv`

Representative identical blob IDs include:

- `backend/tests/test_dc12r1_contract_d_statement_print.py` -> `6d6b5edb86ad1aa7c8b647cbb86fe30e1b23f56c`
- `backend/services/print_service.py` -> `8aa08438f365e77fd107af69406e80b6c74225ec`
- `frontend/src/pages/print/StatementPrintPage.tsx` -> `407a6a739fdc3e253f9b71280543ac6e29a62e9c`
- `ai-ledger/product-ai/2026-08-10_dc12r1_s3_s2b_i2c_i2b_r4_node_outcomes.csv` -> `3272c4cea2c64a3a3ec5150985bbb9fd2d946ece`

This matches the ledger’s freeze claim at `ai-ledger/product-ai/2026-08-10_dc12r1_s3_s2b_i2c_i2b_contract_d_statement.md:1367-1369,1418-1420,1432`.

Status: **PASS**

## 4. Source audit of `backend/tests/tools/gen_node_csv.py`

### 4.1 Duplicate detection before dict insertion

Confirmed:

- `backend/tests/tools/gen_node_csv.py:59-61`
- `if nodeid in outcomes: raise ValueError(...)` occurs before `outcomes[nodeid] = outcome` at line `77`

Status: **PASS**

### 4.2 All A/B validation before target publication

Confirmed:

- Parse-time validation before any target touch: `122-147`
- `_validate(a, b)` runs before `mkstemp`: `144-147`
- Post-temp round-trip validation runs before any publish: `169-193`
- Publish gate is only entered when `publish_rc == 0`: `198-200`

Status: **PASS**

### 4.3 Post-temp failures always execute cleanup

Confirmed:

- Post-`mkstemp` block is wrapped in `try/finally`: `159-211`
- Failures set `publish_rc` instead of bare `return` inside the temp-file region: `178-193`
- `finally` removes temp file whenever `published` is false: `201-210`

This directly closes the R7 defect.

Status: **PASS**

### 4.4 Publication only through `os.replace()` after all checks pass

Confirmed:

- Sole publication site: `198-200`
- No earlier target write path exists after `mkstemp`
- `published = True` only after successful `os.replace`

Status: **PASS**

### 4.5 Cleanup tolerance scope

Confirmed:

- Only `FileNotFoundError` is explicitly tolerated in cleanup: `207-210`
- No broad cleanup swallow exists
- Any other cleanup error propagates out of `finally`

Status: **PASS**

## 5. Generator-test authenticity review

### 5.1 Seven generator tests are real and mutation-sensitive

The target test file contains 7 tests total:

R7-preserved tests:
- duplicate node id fail closed: `55-68`
- existing target preservation on shared outcome diff: `71-85`
- absent target preservation on shared outcome diff: `87-97`
- legal dynamic publish path: `100-122`

R8-added tests:
- non-3-column post-temp failure: `149-181`
- illegal-outcome post-temp failure: `184-223`
- absent-target post-temp failure: `226-249`

Authenticity observations:

- tests invoke the real generator, either as a subprocess (`46-52`) or by importing the real module (`131-139`)
- the new R8 tests monkeypatch only the round-trip readers after module load, which is exactly the defect zone described by the ledger
- no mock-only repository/database behavior is used
- residue checks inspect real filesystem temp files under the target directory: `180-181`, `222-223`, `248-249`
- existing-target preservation is verified by byte comparison: `159-178`, `194-221`
- absent-target preservation is verified by `not out.exists()`: `247`

Runtime execution on this host:

- `pytest backend/tests/test_dc12r1_contract_d_r7_gen_fail_closed.py -q` -> **7 passed**
- `pytest backend/tests/test_dc12r1_contract_d_r5_node_csv.py -q` -> **5 passed**

Status: **PASS**

## 6. Would the three new R8 tests fail against R7?

Yes.

I reproduced the three post-temp failure scenarios against the R7 generator source (`fce3e6d5`) using an external temporary script and the predecessor file content extracted via `git show`. Result:

- non-3-column existing-target scenario -> `rc=1`, target unchanged, **temp residue survives**
- illegal-outcome existing-target scenario -> `rc=1`, target unchanged, **temp residue survives**
- non-3-column absent-target scenario -> `rc=1`, target absent, **temp residue survives**

Observed residue examples:
- `.gen_node_csv_iuiwzewk.tmp`
- `.gen_node_csv_sgqk5bsv.tmp`
- `.gen_node_csv_5p3penti.tmp`

This matches the R7 source defect: the predecessor used `return 1` inside a `try/except BaseException` block (`R7 gen_node_csv.py` after `mkstemp`), so the `except` cleanup never ran on those non-exception early returns.

Status: **PASS**

## 7. Ledger-truth reconciliation

Ledger claims in the changed Contract D ledger section (`1361-1435`) match the source and test behavior:

- narrow generator-only scope -> confirmed by exact 3-file delta
- frozen product/API/frontend/runtime/CSV files -> confirmed by identical blobs and zero path-scoped diff
- R7 defect was post-temp cleanup on bare returns -> confirmed by predecessor source and reproduction
- R8 fix is `try/finally` cleanup with `publish_rc` -> confirmed in `gen_node_csv.py:153-213`
- only `FileNotFoundError` tolerated -> confirmed `207-210`
- publish only through `os.replace` -> confirmed `198-200`
- seven generator tests -> confirmed by source and local run

I found no mismatch between the R8 ledger narrative and the actual R8 source/test behavior.

Status: **PASS**

## 8. Quality and evidence checks

Executed on this host:

- `git diff --check fce3e6d5..f6ac69ee` -> clean
- scoped `detect-secrets scan --all-files --force-use-all-plugins ...` on the 3 R8 files -> no findings (`results: {}`)
- mojibake marker scan on the 3 R8 files -> no hits
- `npx gitnexus analyze` -> completed successfully
- `npx gitnexus status` -> up-to-date at `f6ac69e`

GitNexus detect_changes:

- current CLI exposes `analyze`, `status`, `query`, `context`, `impact`, `cypher`, etc., but **does not expose a `detect_changes` command** in this host’s installed version (`npx gitnexus --help`)
- therefore detect_changes was not available to run here

Status: **PASS**

## Final verdict

`PASS_FOR_CTO_DC12R1_S3_S2B_I2C_I2B_R8_V1_KILO_FINAL_REVIEW`

## Notes

- No candidate source files were edited.
- No source-branch push was performed.
- Report files were added only on local review branch `reports/dc12r1-i2c-i2b-r8-v1-kilo-review-2026-08-11`.
