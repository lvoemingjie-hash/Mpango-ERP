# DC-12R1-S1-V2-R2 Standalone Seeder Entry-Point Repair Evidence

## Verdict

**STOP_AND_REPORT_CTO**

Unresolved exact full-backend gate node:

- `tests/test_u6l_email_verified_onboarding_orchestration.py::test_reused_verification_token_remains_neutral_and_does_not_duplicate_orchestration`

## Scope

- Date: Monday, July 27, 2026
- Branch: `reports/dc12r1-s1-v2-test-contract-reconciliation-2026-07-27`
- Branch tip at start of this R2 pass: `f9d2d9fdb8a02069789da06f66ab9ad422cbc521`
- Disposable worktree: `/home/ivy/MPANGO/dc12r1-s1-v2-r1-disposable`
- Allowed edits used in this pass:
  - `backend/scripts/seed_demo_data.py`
  - `backend/tests/test_s6e_rbac_permission_registry_drift_gate.py`
  - this report

No skip, xfail, deselection, exclusion, assertion weakening, migration edits,
or S2 work were introduced in this pass.

## Test-Safe Environment

- PostgreSQL 16 container: `dc12r1-s1-v2-r2-pg16`
- Redis 7 container: `dc12r1-s1-v2-r2-redis7`
- PostgreSQL loopback endpoint: `127.0.0.1:56433`
- Redis loopback URL: `redis://127.0.0.1:57380/0`
- Environment:
  - `MPANGO_ENV=test`
  - `MPANGO_ALLOW_TEMP_DB_CREATE=1`
  - `MPANGO_TEMP_DB_ALLOWED_HOSTS=127.0.0.1,localhost`
  - `MPANGO_TEMP_DB_ALLOWED_PORTS=56433`
  - `REPORTING_USER_PASSWORD` set to a disposable test-only value
  - all `TEST_DATABASE_URL` / `DATABASE_URL` values used disposable non-production
    database names, loopback hosts, and test credentials only
  - all reporting DSNs used explicit test reporting credentials only

## CLI RED -> GREEN Proof

Required standalone command:

- `env -u PYTHONPATH python3 scripts/seed_demo_data.py --help`
- working directory: `backend/`

RED before the repair:

- exit: `1`
- root cause: `ModuleNotFoundError: No module named 'core'`
- direct observed traceback showed `seed_demo_data.py` imported
  `core.permission_registry` before adding `backend/` to `sys.path`
- artifacts:
  - `/tmp/dc12r1-s1-v2-r2_seed_demo_cli_red.out`
  - `/tmp/dc12r1-s1-v2-r2_seed_demo_cli_red.err`
  - `/tmp/dc12r1-s1-v2-r2_seed_demo_cli_red.rc`

GREEN after the repair:

- exit: `0`
- no import traceback
- artifacts:
  - `/tmp/dc12r1-s1-v2-r2_seed_demo_cli_green.out`
  - `/tmp/dc12r1-s1-v2-r2_seed_demo_cli_green.err`
  - `/tmp/dc12r1-s1-v2-r2_seed_demo_cli_green.rc`

## Corrections Applied

- Moved `_add_backend_to_path()` above `from core.permission_registry import ADMIN_PERMISSIONS`
  in `backend/scripts/seed_demo_data.py`
- executed `_add_backend_to_path()` before importing `core.permission_registry`
- preserved `PERMISSION_CODES = ADMIN_PERMISSIONS`
- added subprocess regression
  `test_seed_demo_data_cli_help_runs_without_pythonpath()`
  that:
  - removes `PYTHONPATH`
  - runs `python scripts/seed_demo_data.py --help` from `backend/`
  - requires exit `0`
  - requires no traceback text
- preserved the exact four-script canonical permission gate

## Focused Regression Results

- standalone CLI regression is covered by
  `tests/test_s6e_rbac_permission_registry_drift_gate.py`
- targeted S6-E + permission/RBAC bundle:
  - `tests/test_s6e_rbac_permission_registry_drift_gate.py`
  - `tests/test_u3b1_contract_foundation.py`
  - `tests/test_u1_bootstrap_permission_completeness.py`
  - `tests/test_u1r1_bootstrap_completeness.py`
  - `tests/test_dc12r1_s1_r5a_permission_registry_parity.py`
  - `tests/test_route_authorization_policy.py`
  - `tests/test_rbac_enforcement.py`
  - result: `124 passed, 5 xfailed`
  - log: `/tmp/dc12r1-s1-v2-r2_targeted.log`

## Exact Full Backend Gate

Exact-tip full backend suite on fresh PostgreSQL 16 / Redis 7 test services:

- database: `test_backend_v2_r2_full1`
- Alembic log: `/tmp/dc12r1-s1-v2-r2_full_alembic.log`
- pytest log: `/tmp/dc12r1-s1-v2-r2_backend_full1.log`
- JUnit: `/tmp/dc12r1-s1-v2-r2_backend_full1.xml`
- result:
  - `1 failed, 2871 passed, 48 skipped, 15 xfailed, 0 errors in 643.16s`

Unresolved node:

- nodeid:
  `tests/test_u6l_email_verified_onboarding_orchestration.py::test_reused_verification_token_remains_neutral_and_does_not_duplicate_orchestration`
- phase: call
- observed exception: `AssertionError`
- sanitized root cause:
  - expected reused verification token response: HTTP `400`
  - observed exact full-suite response: HTTP `500 Internal Server Error`
  - failing assertion: `assert reused.status_code == 400`

Because the required exact full backend gate on a fresh database was not green,
this pass cannot be declared `PASS_FOR_CTO_DC12R1_S1_V2_R2_MERGE_REVIEW`.

## Independent Recheck Of The Unresolved Node

The failing node was rechecked independently in fresh pytest processes on fresh
PostgreSQL 16 databases:

- single failing node only
  - result: `1 passed`
  - log: `/tmp/dc12r1-s1-v2-r2_u6lsolo.log`
- whole file `tests/test_u6l_email_verified_onboarding_orchestration.py`
  - result: `7 passed`
  - log: `/tmp/dc12r1-s1-v2-r2_u6lfile.log`
- neighboring order probe
  - command order:
    `tests/test_u6k_production_smtp_email_delivery.py tests/test_u6l_email_verified_onboarding_orchestration.py`
  - result: `12 passed`
  - log: `/tmp/dc12r1-s1-v2-r2_u6ku6l.log`

This establishes that the exact full-suite failure was real but did not
reproduce independently in the minimal rechecks performed during this pass.
The suite-level instability remains unresolved, so the merge gate remains
stopped.

## Repo Hygiene And Tooling

- `git diff --check`
  - PASS
  - log: `/tmp/dc12r1-s1-v2-r2_git_diff_check.log`
- `pre-commit run --all-files`
  - FAIL on pre-existing repo-wide issues unrelated to this R2 scope
  - hooks auto-touched unrelated files; all incidental hook edits were reverted
  - unrelated failures included existing `check-yaml` errors and broad
    trailing-whitespace / EOF rewrites outside this task scope
- scoped `pre-commit run --files backend/scripts/seed_demo_data.py backend/tests/test_s6e_rbac_permission_registry_drift_gate.py`
  - PASS
  - log: `/tmp/dc12r1-s1-v2-r2_precommit_scoped.log`
- scoped `pre-commit run detect-secrets --files backend/scripts/seed_demo_data.py backend/tests/test_s6e_rbac_permission_registry_drift_gate.py`
  - PASS
  - log: `/tmp/dc12r1-s1-v2-r2_detect_secrets_scoped.log`

## GitNexus

Code commit analyzed for this R2 pass:

- `78ebc3c` `fix seeder standalone entrypoint`

GitNexus execution:

- initial `gitnexus status`
  - indexed commit: `7237438`
  - current commit: `78ebc3c`
  - status: stale
  - log: `/tmp/dc12r1-s1-v2-r2_gitnexus_status.log`
- first incremental `gitnexus analyze .`
  - FAIL
  - root cause: local GitNexus FTS index inconsistency
    `file_fts ... missing during delete`
  - log: `/tmp/dc12r1-s1-v2-r2_gitnexus_analyze.log`
- repair:
  - `gitnexus clean --force`
  - PASS
  - log: `/tmp/dc12r1-s1-v2-r2_gitnexus_clean.log`
- rebuilt `gitnexus analyze .`
  - PASS
  - `30,364 nodes | 50,581 edges | 735 clusters | 300 flows`
  - log: `/tmp/dc12r1-s1-v2-r2_gitnexus_analyze2.log`
- final `gitnexus status`
  - indexed commit: `78ebc3c`
  - current commit: `78ebc3c`
  - status: `up-to-date`

The report commit that follows this analyzed code commit is documentation only.

## Final Statement

The standalone seeder entry-point defect is repaired and the required CLI
subprocess regression is in place. Focused permission/RBAC regressions are
green, scoped hygiene/security checks are green, and GitNexus was repaired and
brought up to date at code commit `78ebc3c`.

The required exact-tip full backend suite on a fresh PostgreSQL 16 / Redis 7
environment was not green because of the unresolved `u6l` suite-level failure
listed above. This pass therefore stops for CTO review instead of claiming the
requested PASS verdict.
