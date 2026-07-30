# DC-12R1-S3-S1-R3-R2: Deterministic Evidence Correction

**Date:** 2026-07-30
**Branch:** `zcode/dc12r1-s3-s1-catalog-order-hardening-2026-07-29`
**Turn type:** Evidence-only correction. No product code or tests were modified in this R3-R2 turn.
**Verdict:** `PASS_FOR_CTO_DC12R1_S3_S1_R3_R2_MERGE_REVIEW`

## 1. Branch And Ancestry

| Check | Evidence | Result |
|---|---|---|
| Fetch | `git fetch --all --prune` | Completed |
| S3-S1 remote tip | `git rev-parse origin/zcode/dc12r1-s3-s1-catalog-order-hardening-2026-07-29` -> `280c2b027c2fae7373d9168d4fc3d07e7f4806b1` | PASS |
| Protected baseline remote | `git rev-parse origin/product-dev-recovered` -> `abdf3e454f420cc825faeddb264d010eae9c6d72` | PASS |
| Ancestry | `git merge-base --is-ancestor abdf3e454f420cc825faeddb264d010eae9c6d72 280c2b027c2fae7373d9168d4fc3d07e7f4806b1` | PASS |
| Validation worktree | New detached worktree `_dc12r1_s3_s1_r3_r2_validation` created from exact remote tip | PASS |

## 2. Validated Source SHA

Validated source tree:
`280c2b027c2fae7373d9168d4fc3d07e7f4806b1`

This SHA is the only source tree used for backend Run A, backend Run B, frontend Vitest, and frontend build. The later report-publication commit is documentation-only and is supplied in the final handoff; it is not presented as the tested source tree.

Source-state proof before testing:

| Item | Evidence | Result |
|---|---|---|
| `HEAD` | `git rev-parse HEAD` -> `280c2b027c2fae7373d9168d4fc3d07e7f4806b1` | PASS |
| Worktree status | `git status --short` -> empty | PASS |
| `requirements.txt` vs R2 | `git diff --exit-code 67b92867 -- backend/requirements.txt` | PASS, identical |
| `pyproject.toml` and `poetry.lock` vs R2 | `git diff --exit-code 67b92867 -- backend/pyproject.toml backend/poetry.lock` | PASS, identical |
| Alembic heads | `poetry run alembic heads` -> `036_retailer_mvp_identity (head)` | PASS, one head |
| Python | `Python 3.12.10` | Recorded |
| Poetry | `Poetry 2.2.1` | Recorded |
| Docker | `Docker version 29.1.3, build f52814d` | Recorded |
| PostgreSQL image | `postgres:16`, image id `sha256:fe03a7605299a34ddf5e4f285dff78c3d7190a576b3c6b46f2fcff69f4bffd54` | Recorded |
| Redis image | `redis:7`, image id `sha256:b2b95679e3b46fb51864949ed25ea976fc3a6bcc00a40a1bc00d568cb2822e50` | Recorded |

## 3. Implementation SHA

Validated implementation commit:
`0707c52fd392e6e9b058fcddbbf8877cc1a552bc`

Remote tip at validation time:
`280c2b027c2fae7373d9168d4fc3d07e7f4806b1`

The remote tip includes prior report-publication commits after the validated implementation commit. R3-R2 tested the exact remote tip to remove the earlier stale final-SHA contradiction.

## 4. Protected Baseline SHA

Protected baseline:
`abdf3e454f420cc825faeddb264d010eae9c6d72`

Protected baseline ancestry into the tested branch tip was verified with `git merge-base --is-ancestor` and passed.

## 5. Exact Final Effective Changed Files Versus R2

Command:
`git diff --name-status 67b92867..HEAD`

Effective branch delta at validated source SHA `280c2b02`:

```text
M       ai-ledger/product-ai/2026-07-29_dc12r1_s3_s1_catalog_order_hardening.md
M       backend/crud/order.py
M       backend/scripts/create_wholesaler.py
M       backend/scripts/onboard_tenant.py
M       backend/scripts/seed_demo_data.py
M       backend/scripts/seed_test_tenant.py
M       backend/tests/test_dc12r1_s3_s1_catalog_order_hardening.py
M       backend/tests/test_s6e_rbac_permission_registry_drift_gate.py
M       backend/tests/test_u1r1_bootstrap_completeness.py
```

R3-R2 turn delta after validation: report-only. Final allowed changed file for this correction is:
`ai-ledger/product-ai/2026-07-29_dc12r1_s3_s1_catalog_order_hardening.md`

Forbidden path audit for this R3-R2 turn: no backend product code, tests, migrations, dependency files, frontend files, config, Docker/deployment files, or `.secrets.baseline` were edited.

## 6. Requirements And Poetry Equality Proof

| File | Check | Result |
|---|---|---|
| `backend/requirements.txt` | `git diff --exit-code 67b92867 -- backend/requirements.txt` | Identical to R2 checkpoint |
| `backend/pyproject.toml` | `git diff --exit-code 67b92867 -- backend/pyproject.toml` | Identical to R2 checkpoint |
| `backend/poetry.lock` | `git diff --exit-code 67b92867 -- backend/poetry.lock` | Identical to R2 checkpoint |

Backend dependencies were installed from the existing lockfile with `poetry install --sync` into a new Poetry virtualenv. No lockfile or dependency manifest changed.

## 7. Focused S3-S1/RBAC/Payment Results Already Validated

The following focused evidence was already validated before this evidence-only R3-R2 correction and remains part of the validated branch history:

| Scope | Command | Result |
|---|---|---|
| S3-S1 focused suite | `pytest tests/test_dc12r1_s3_s1_catalog_order_hardening.py -x -v` | 43 passed |
| S3-S1 stability run | `pytest tests/test_dc12r1_s3_s1_catalog_order_hardening.py -q` | 43 passed |
| RBAC/bootstrap regressions | `pytest tests/test_s6e_rbac_permission_registry_drift_gate.py tests/test_u1r1_bootstrap_completeness.py -q` | 26 passed, 5 xfailed |
| S2 + S3-S1 + H2 + payment regressions | `pytest tests/test_dc12r1_s2_supplier_scoped_retailer_login.py tests/test_dc12r1_s3_s1_catalog_order_hardening.py tests/test_dc12r1_h2_structured_http_error_contract.py tests/test_dc10f_payment_method_integrity.py -q` | 141 passed |

R3-R2 does not alter those implementation/test results. It replaces only the contradictory full-suite evidence.

## 8. Full Backend Run A

| Field | Value |
|---|---|
| Source SHA | `280c2b027c2fae7373d9168d4fc3d07e7f4806b1` |
| Working directory | `backend/` |
| Exact command | `poetry run pytest tests/ -q --tb=short` |
| Pytest process | Separate process from Run B |
| Start UTC | `2026-07-30T10:42:15.0596748Z` |
| End UTC | `2026-07-30T10:52:18.5960725Z` |
| Exit code | 0 |
| PostgreSQL container | `dc12r1_r3r2_pg_a`, id `4934b4305fcd39b1afa42761e9700dd4443ec8c8d501dae82e58d4d93da97dc9` |
| PostgreSQL port/database/user | `127.0.0.1:55432`, `test_dc12r1_r3r2_a`, `mpango_test` |
| PostgreSQL version | `16.14 (Debian 16.14-1.pgdg13+1)` |
| Test DB role authorization | `rolsuper=t`, `rolcreatedb=t` |
| Redis container | `dc12r1_r3r2_redis_a`, id `772e8fb7c5fee3f81949b7c229f841d50c5e1fbabe1568a8c18cadbb66985ee6` |
| Redis port | `127.0.0.1:56379` |
| Redis version | `Redis server v=7.4.9` |
| Database state | Empty PostgreSQL 16 database, Alembic upgraded to `036_retailer_mvp_identity (head)` before pytest |
| Pytest cache | Task-owned `.pytest_cache` cleared before run |
| Environment contract | `MPANGO_ENV=test`, `DATABASE_URL/TEST_DATABASE_URL` pointed to Run A DB, `REDIS_URL` pointed to Run A Redis, `MPANGO_ALLOW_TEMP_DB_CREATE=1`, allowed temp DB host `127.0.0.1`, allowed temp DB port `55432`, `PYTHONUTF8=1`, `PYTHONIOENCODING=utf-8` |

Run A totals:

| Metric | Value |
|---|---:|
| Collected | 3086 |
| Passed | 3023 |
| Failed | 0 |
| Errors | 0 |
| Skipped | 48 |
| Xfailed | 15 |
| Xpassed | 0 |
| Deselected | 0 |
| Accounting gap | 0 |

Summary line:
`3023 passed, 48 skipped, 15 xfailed, 1881 warnings in 592.95s (0:09:52)`

## 9. Full Backend Run B

| Field | Value |
|---|---|
| Source SHA | `280c2b027c2fae7373d9168d4fc3d07e7f4806b1` |
| Working directory | `backend/` |
| Exact command | `poetry run pytest tests/ -q --tb=short` |
| Pytest process | Separate process from Run A |
| Start UTC | `2026-07-30T10:53:44.9189830Z` |
| End UTC | `2026-07-30T11:03:08.5777376Z` |
| Exit code | 0 |
| PostgreSQL container | `dc12r1_r3r2_pg_b`, id `da898d7113137893173647fb7a3b99e2cf671ac4c407779fd86c98df6ea30847` |
| PostgreSQL port/database/user | `127.0.0.1:55433`, `test_dc12r1_r3r2_b`, `mpango_test` |
| PostgreSQL version | `16.14 (Debian 16.14-1.pgdg13+1)` |
| Test DB role authorization | `rolsuper=t`, `rolcreatedb=t` |
| Redis container | `dc12r1_r3r2_redis_b`, id `1a3ad4112cf3fc425cfa5dd8814a030f966818ccd9728ae201ef5fad878cf950` |
| Redis port | `127.0.0.1:56380` |
| Redis version | `Redis server v=7.4.9` |
| Database state | Empty PostgreSQL 16 database, Alembic upgraded to `036_retailer_mvp_identity (head)` before pytest |
| Pytest cache | Task-owned `.pytest_cache` cleared before run |
| Environment contract | `MPANGO_ENV=test`, `DATABASE_URL/TEST_DATABASE_URL` pointed to Run B DB, `REDIS_URL` pointed to Run B Redis, `MPANGO_ALLOW_TEMP_DB_CREATE=1`, allowed temp DB host `127.0.0.1`, allowed temp DB port `55433`, `PYTHONUTF8=1`, `PYTHONIOENCODING=utf-8` |

Run B totals:

| Metric | Value |
|---|---:|
| Collected | 3086 |
| Passed | 3023 |
| Failed | 0 |
| Errors | 0 |
| Skipped | 48 |
| Xfailed | 15 |
| Xpassed | 0 |
| Deselected | 0 |
| Accounting gap | 0 |

Summary line:
`3023 passed, 48 skipped, 15 xfailed, 1876 warnings in 558.04s (0:09:18)`

## 10. Exact A/B Equality Comparison

| Metric | Run A | Run B | Match |
|---|---:|---:|---|
| Source SHA | `280c2b02` | `280c2b02` | PASS |
| Command | `poetry run pytest tests/ -q --tb=short` | `poetry run pytest tests/ -q --tb=short` | PASS |
| Collected | 3086 | 3086 | PASS |
| Passed | 3023 | 3023 | PASS |
| Failed | 0 | 0 | PASS |
| Errors | 0 | 0 | PASS |
| Skipped | 48 | 48 | PASS |
| Xfailed | 15 | 15 | PASS |
| Xpassed | 0 | 0 | PASS |
| Deselected | 0 | 0 | PASS |
| Failed node set | Empty | Empty | PASS |
| Error node set | Empty | Empty | PASS |
| Accounting gap | 0 | 0 | PASS |

Acceptance result: PASS. There are no differing totals and no differing node sets. No environment-difference waiver was used.

## 11. Failed/Error Node Ledger

No failed nodes and no error nodes were present in Run A or Run B.

| Category | Run A | Run B |
|---|---:|---:|
| Failed node IDs | 0 | 0 |
| Error node IDs | 0 | 0 |

No red-node classification is required because both full backend runs were green.

## 12. Baseline Reproduction And Fingerprints

Not applicable. There were no failed or error nodes on the validated source tree. No `BASELINE_PRODUCT_DEFECT` claim is made, no product defect is waived, and no baseline reproduction is needed for green full-suite evidence.

## 13. Frontend Vitest And Build

Frontend working directory: `frontend/`

| Command | Result |
|---|---|
| `pnpm install --frozen-lockfile` | Exit 0; lockfile up to date; 434 packages installed/reused |
| `pnpm vitest run` | Exit 0; 15 test files passed; 142 tests passed; 0 failed |
| `pnpm build` | Exit 0; `tsc -p tsconfig.app.json && vite build`; build completed in 4.93s |

Vitest files: 15 passed.
Vitest tests: 142 passed, 0 failed.

Recorded frontend warnings:

| Gate | Warning |
|---|---|
| `pnpm vitest run` | Duplicate `jsdom` key in `package.json`; React Router v7 future-flag warnings; React `act(...)` warnings |
| `pnpm build` | Duplicate `jsdom` key in `package.json`; Vite chunk larger than 500 kB warning for `assets/index-BKeUer45.js` |

The frontend build was mandatory and was run successfully.

## 14. GitNexus

GitNexus CLI availability check:
`npx gitnexus --help` lists `setup`, `analyze`, `index`, `serve`, `mcp`, `list`, `status`, `clean`, `wiki`, `augment`, `query`, `context`, `impact`, `cypher`, and `eval-server`. It does not expose a `detect_changes` subcommand in this environment.

Available equivalent scope/risk evidence before report commit:

| Check | Evidence | Result |
|---|---|---|
| Branch delta versus R2 | `git diff --name-status 67b92867..HEAD` | 9 effective files: 1 ledger report, 5 backend implementation/script files, 3 backend test files |
| Scope stat versus R2 | `git diff --stat 67b92867..HEAD` | Effective branch scope matches prior S3-S1/RBAC correction plus ledger report |
| R3-R2 working-tree scope | `git status --short` after editing is checked before commit | Must contain only this report |

`npx gitnexus analyze` and `npx gitnexus status` are run after the report-publication commit so the index status is tied to that documentation-only commit. The resulting publication commit SHA and GitNexus status are supplied in the final handoff.

## 15. Hygiene

Required pre-commit hygiene for this R3-R2 evidence-only turn:

| Check | Result |
|---|---|
| `git diff --check` | PASS; no whitespace errors |
| Scoped pre-commit on report | PASS; trailing whitespace, EOF fixer, large-file check, and detect-secrets passed |
| Scoped detect-secrets on report | PASS; pre-commit detect-secrets hook passed and non-mutating `detect-secrets scan <report>` returned `results: {}` |
| Email/credential/token/DB URL/raw exception scan | PASS; no matches |
| Mojibake scan | PASS; no matches |
| Working-tree status | PASS; only the report is modified |
| Forbidden generated file restoration | PASS; `.secrets.baseline` was rewritten by a direct baseline scan and restored individually because `.secrets.baseline` is forbidden in R3-R2 |

No code/test changes were made in this R3-R2 turn. If any non-report change appears, it is individually restored before commit and recorded.

## 16. Cleanup

Task-owned resources for cleanup after publication:

| Resource | Identifier |
|---|---|
| Run A PostgreSQL | `dc12r1_r3r2_pg_a` |
| Run A Redis | `dc12r1_r3r2_redis_a` |
| Run B PostgreSQL | `dc12r1_r3r2_pg_b` |
| Run B Redis | `dc12r1_r3r2_redis_b` |
| Validation worktree | `_dc12r1_s3_s1_r3_r2_validation` |
| Evidence logs | `C:\Users\Jeff0\AppData\Local\Temp\kilo\dc12r1_r3r2_evidence` |
| Pytest cache | Task-owned `.pytest_cache` artifacts only |

Cleanup is performed after report commit, push, remote equality proof, protected-ref proof, and GitNexus status. No unrelated worktrees or user files are removed.

## 17. Final Self-Review

| # | Item | Result |
|---:|---|---|
| 1 | Both runs tested SHA `280c2b02` | PASS |
| 2 | Both used identical commands | PASS |
| 3 | Both used equivalent fresh infrastructure | PASS |
| 4 | All totals match exactly | PASS |
| 5 | Failed/error node sets match exactly | PASS, both empty |
| 6 | Arithmetic accounting gap is 0 | PASS |
| 7 | No deselected tests | PASS |
| 8 | No hidden reruns or exclusions | PASS |
| 9 | Every red node has exact classification and fingerprint | PASS, no red nodes |
| 10 | No product defect is being waived | PASS |
| 11 | `pnpm build` actually ran | PASS |
| 12 | Report contains no pending item | PASS |
| 13 | Report verdict and final sentence agree | PASS |
| 14 | Only the report is modified by R3-R2 | PASS |
| 15 | Protected branches and tags are unchanged before publication | PASS |

## 18. Final Verdict

```text
PASS_FOR_CTO_DC12R1_S3_S1_R3_R2_MERGE_REVIEW
```

R3-R2 provides deterministic, internally consistent, green full-gate evidence for source tree `280c2b027c2fae7373d9168d4fc3d07e7f4806b1`; the branch is ready for CTO merge review, and S3-S2/S3-S3 are not started.
