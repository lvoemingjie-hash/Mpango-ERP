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

## R3 Addendum: DC10G Standalone Log-Capture Contract Repair

Scope for this R3 pass was limited to:

- `backend/tests/test_dc10g_platform_uuid_export_error_hardening.py`
- this existing V2 report only

No product, migration, config, frontend, or verify-email production code was
edited in this pass.

### Preserved RED Evidence

Base tip for this R3 pass:

- `1608016db5d1e0ef25264edca74c829f8a39e8bd`

Standalone RED reproduction on fresh PostgreSQL 16 / Redis 7:

- command target:
  `tests/test_dc10g_platform_uuid_export_error_hardening.py`
- Alembic log: `/tmp/dc12r1-s1-v2-r3_dc10g_red_alembic.log`
- pytest log: `/tmp/dc12r1-s1-v2-r3_dc10g_red.log`
- result observed on this tip:
  - `1 failed, 7 passed`
- failing node:
  - `tests/test_dc10g_platform_uuid_export_error_hardening.py::TestExportEnqueueErrorBoundary::test_enqueue_failure_sanitized_response_and_logs`
- failing assertion:
  - `assert "ConnectionError" in log_text`
  - observed `log_text == ""`
- preserved RED property:
  - `caplog.text` was empty while structured JSON for
    `Failed to enqueue export job: ConnectionError` appeared on captured stdout

Note: the requested `1 failed, 6 passed` count was not reproducible on this
exact tip because the file currently collects 8 test nodes.

### Test-Contract Repair Applied

The DC10G test contract was repaired without weakening assertions:

- imported `main as main_module` at module scope so `main` initializes before
  `caplog` attaches during test execution
- kept the required `patch.object(main_module, "get_job_queue")`
- preserved all security assertions:
  - controlled HTTP `500`
  - fixed `EXPORT_ENQUEUE_FAILED` response
  - `ConnectionError` class name required in captured logs
  - sentinel URL / text absent from response and logs

### Independent And Focused GREEN Evidence

Standalone `dc10g` in fresh pytest processes:

- run 1:
  - Alembic log: `/tmp/dc12r1-s1-v2-r3_dc10g_green_run1_alembic.log`
  - pytest log: `/tmp/dc12r1-s1-v2-r3_dc10g_green_run1.log`
  - result: `8 passed`
- run 2:
  - Alembic log: `/tmp/dc12r1-s1-v2-r3_dc10g_green_run2_alembic.log`
  - pytest log: `/tmp/dc12r1-s1-v2-r3_dc10g_green_run2.log`
  - result: `8 passed`

Affected export/security bundle:

- files:
  - `tests/test_dc10g_platform_uuid_export_error_hardening.py`
  - `tests/test_dc10e_export_worker_tenant_context.py`
  - `tests/test_s6_4_async_exports.py`
  - `tests/test_route_authorization_policy.py`
  - `tests/test_rbac_enforcement.py`
  - `tests/test_security_privacy.py`
- original order:
  - Alembic log: `/tmp/dc12r1-s1-v2-r3_bundle_orig_alembic.log`
  - pytest log: `/tmp/dc12r1-s1-v2-r3_bundle_orig.log`
  - result: `129 passed`
- reverse order:
  - Alembic log: `/tmp/dc12r1-s1-v2-r3_bundle_rev_alembic.log`
  - pytest log: `/tmp/dc12r1-s1-v2-r3_bundle_rev.log`
  - result: `129 passed`

### Full Backend Gates

Natural-order full backend gate A on fresh PostgreSQL 16 / Redis 7:

- services:
  - PostgreSQL: `127.0.0.1:56436` (`dc12r1-s1-v2-r3a-pg16`)
  - Redis: `127.0.0.1:57383` (`dc12r1-s1-v2-r3a-redis7`)
- Alembic log: `/tmp/dc12r1-s1-v2-r3_full_nat_a_alembic.log`
- pytest log: `/tmp/dc12r1-s1-v2-r3_full_nat_a.log`
- result:
  - `2872 passed, 48 skipped, 15 xfailed, 0 failed, 0 errors`

Natural-order full backend gate B on separate fresh PostgreSQL 16 / Redis 7:

- services:
  - PostgreSQL: `127.0.0.1:56437` (`dc12r1-s1-v2-r3b-pg16`)
  - Redis: `127.0.0.1:57384` (`dc12r1-s1-v2-r3b-redis7`)
- Alembic log: `/tmp/dc12r1-s1-v2-r3_full_nat_b_alembic.log`
- pytest log: `/tmp/dc12r1-s1-v2-r3_full_nat_b.log`
- result:
  - `2872 passed, 48 skipped, 15 xfailed, 0 failed, 0 errors`

Required reverse-order full backend diagnostic on fresh PostgreSQL 16 / Redis 7
did not pass:

- services:
  - PostgreSQL: `127.0.0.1:56437` (`dc12r1-s1-v2-r3b-pg16`)
  - Redis: `127.0.0.1:57384` (`dc12r1-s1-v2-r3b-redis7`)
- Alembic log: `/tmp/dc12r1-s1-v2-r3_full_rev_b_alembic.log`
- pytest log: `/tmp/dc12r1-s1-v2-r3_full_rev_b.log`
- result:
  - `9 failed, 2882 passed, 29 skipped, 15 xfailed, 0 errors`

Unresolved reverse-order nodes:

- `tests/test_u6d_verify_email_endpoint.py::test_valid_token_verifies_registration_and_marks_token_used`
- `tests/test_u6d_verify_email_endpoint.py::test_invalid_token_returns_neutral_failure_and_writes_nothing`
- `tests/test_u6d_verify_email_endpoint.py::test_missing_or_query_string_token_returns_neutral_failure_and_writes_nothing`
- `tests/test_u6d_verify_email_endpoint.py::test_expired_token_returns_neutral_failure_and_writes_nothing`
- `tests/test_u6d_verify_email_endpoint.py::test_reused_token_cannot_verify_twice`
- `tests/test_u6d_verify_email_endpoint.py::test_token_for_non_pending_registration_does_not_regress_state`
- `tests/test_u6d_verify_email_endpoint.py::test_verify_email_provisions_tenant_schema_without_admin_rbac_side_effects`
  - sanitized root cause:
    signup path returned HTTP `500` instead of expected `202`
  - captured root signal:
    `Rate limit exceeded` for `rate_limit:ip:127.0.0.1` with counts `101-106`
- `tests/test_request_validation.py::TestRequestValidation::test_login_rejects_missing_email`
  - sanitized root cause:
    request path raised `RuntimeError: Event loop is closed`
- `tests/test_dc10g_platform_uuid_export_error_hardening.py::TestExportEnqueueErrorBoundary::test_enqueue_failure_sanitized_response_and_logs`
  - sanitized root cause:
    `caplog.text` was empty again in the full reverse suite, so
    `ConnectionError` was absent from captured logs

### Repo Hygiene And Tooling (R3)

- `git diff --check`
  - PASS
  - log: `/tmp/dc12r1-s1-v2-r3_git_diff_check.log`
- scoped `pre-commit run --files backend/tests/test_dc10g_platform_uuid_export_error_hardening.py ai-ledger/product-ai/2026-07-27_dc12r1_s1_v2_test_contract_reconciliation.md`
  - PASS
  - log: `/tmp/dc12r1-s1-v2-r3_precommit_scoped.log`
- scoped `pre-commit run detect-secrets --files backend/tests/test_dc10g_platform_uuid_export_error_hardening.py ai-ledger/product-ai/2026-07-27_dc12r1_s1_v2_test_contract_reconciliation.md`
  - PASS
  - log: `/tmp/dc12r1-s1-v2-r3_detect_secrets_scoped.log`
- `gitnexus analyze .`
  - PASS
  - `30,363 nodes | 50,581 edges | 735 clusters | 300 flows`
- final `gitnexus status`
  - indexed commit: `1608016`
  - current commit: `1608016`
  - status: `up-to-date`
  - log: `/tmp/dc12r1-s1-v2-r3_gitnexus_status.log`

### Cleanup Proof

- PostgreSQL temporary database audit before container removal:
  - `dc12r1-s1-v2-r3-pg16`: no `test_dc10gr3*` / `test_dc12r1r3*` leftovers
  - `dc12r1-s1-v2-r3a-pg16`: no `test_dc10gr3*` / `test_dc12r1r3*` leftovers
  - `dc12r1-s1-v2-r3b-pg16`: no `test_dc10gr3*` / `test_dc12r1r3*` leftovers
- removed containers:
  - `dc12r1-s1-v2-r3-pg16`
  - `dc12r1-s1-v2-r3-redis7`
  - `dc12r1-s1-v2-r3a-pg16`
  - `dc12r1-s1-v2-r3a-redis7`
  - `dc12r1-s1-v2-r3b-pg16`
  - `dc12r1-s1-v2-r3b-redis7`
- final zero-leftover proof:
  - `docker ps -a | grep dc12r1-s1-v2-r3` -> empty
  - `docker volume ls | grep dc12r1-s1-v2-r3` -> empty
  - `docker network ls | grep dc12r1-s1-v2-r3` -> empty

### R3 Conclusion

The requested standalone DC10G log-capture contract repair succeeded in
independent fresh-process reruns, the affected export/security bundle, and two
separate natural-order full backend gates on fresh PostgreSQL 16 / Redis 7.

This pass cannot be declared
`PASS_FOR_CTO_DC12R1_S1_V2_R3_MERGE_REVIEW` because the required reverse-order
full backend diagnostic was not green. The unresolved failures were not
confined to DC10G and included the seven `u6d` verify-email nodes and the
`test_login_rejects_missing_email` runtime failure listed above.
