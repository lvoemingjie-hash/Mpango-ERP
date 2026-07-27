# DC-12R1-S1-V2-R2A-L Runtime Suite-State Forensics

## Verdict

**PASS_RUNTIME_ROOT_CAUSE_IDENTIFIED**

## Scope

- Date: Monday, July 27, 2026
- Base commit: `1608016db5d1e0ef25264edca74c829f8a39e8bd`
- Branch: `reports/dc12r1-s1-v2-r2a-lubuntu-runtime-forensics-2026-07-27`
- Worktree: `/home/ivy/MPANGO/dc12r1-s1-v2-r2a-runtime-forensics`
- Code policy for this pass:
  - no product fixes
  - no committed test edits
  - temporary diagnostics were reverted
  - final commit contains report only

## Fresh Runtime Environment

- PostgreSQL 16 container: `dc12r1-s1-v2-r2a-pg16`
- Redis 7 container: `dc12r1-s1-v2-r2a-redis7`
- PostgreSQL loopback endpoint: `127.0.0.1:56434`
- Redis loopback endpoint: `127.0.0.1:57381`
- Test-safe env:
  - `MPANGO_ENV=test`
  - `MPANGO_ALLOW_TEMP_DB_CREATE=1`
  - `MPANGO_TEMP_DB_ALLOWED_HOSTS=127.0.0.1,localhost`
  - `MPANGO_TEMP_DB_ALLOWED_PORTS=56434`
  - disposable `TEST_DATABASE_URL` / `DATABASE_URL`
  - disposable reporting password / reporting DSN

## Original-Order Full Suite

Fresh full backend suite on PostgreSQL 16 / Redis 7:

- database: `test_backend_v2_r2a_full1`
- Alembic log: `/tmp/dc12r1-s1-v2-r2a_full1_alembic.log`
- pytest log: `/tmp/dc12r1-s1-v2-r2a_full1.log`
- result:
  - `2872 passed, 48 skipped, 15 xfailed, 0 failed, 0 errors`
  - runtime `761.78s`

U6-L status in original order:

- `tests/test_u6l_email_verified_onboarding_orchestration.py .......`
- the previously reported node
  `tests/test_u6l_email_verified_onboarding_orchestration.py::test_reused_verification_token_remains_neutral_and_does_not_duplicate_orchestration`
  passed on the fresh runtime

## Reverse-Order Full Suite

Reverse file-order full backend suite on a second fresh database:

- database: `test_backend_v2_r2a_full_rev1`
- file order source: `find tests -type f -name 'test*.py' | sort -r`
- Alembic log: `/tmp/dc12r1-s1-v2-r2a_full_rev1_alembic.log`
- pytest log: `/tmp/dc12r1-s1-v2-r2a_full_rev1.log`
- result:
  - `1 failed, 2890 passed, 29 skipped, 15 xfailed`
  - runtime `677.93s`

Important observations:

- `tests/test_u6l_email_verified_onboarding_orchestration.py` ran first in the
  reverse suite and all seven tests passed
- the reverse-order failure was a different node:
  - `tests/test_dc10g_platform_uuid_export_error_hardening.py::TestExportEnqueueErrorBoundary::test_enqueue_failure_sanitized_response_and_logs`

## U6-L Raise-App-Exceptions Diagnostic

Temporary diagnostic:

- changed `ASGITransport(app=app, raise_app_exceptions=False)` to `True`
  in `tests/test_u6l_email_verified_onboarding_orchestration.py`
- reran only:
  - `tests/test_u6l_email_verified_onboarding_orchestration.py::test_reused_verification_token_remains_neutral_and_does_not_duplicate_orchestration`
- database: `test_backend_v2_r2a_u6l_diag`
- log: `/tmp/dc12r1-s1-v2-r2a_u6l_diag.log`
- result:
  - `1 passed`
  - no exception bubbled out of FastAPI
  - no source exception class / line existed to capture on the fresh runtime

The temporary change was reverted immediately after the run and is not present
in the worktree.

## Same-Process Bisection Outcome

Required same-process bisection was attempted against the reverse-order failure
set, starting with the control case:

- control run:
  - `tests/test_dc10g_platform_uuid_export_error_hardening.py`
  - log: `/tmp/dc12r1-s1-v2-r2a_dc10g_target_alone.log`
  - result:
    - `1 failed, 6 passed`

This immediately collapsed the predecessor-file contamination hypothesis for the
reverse-order failure: no predecessor files were required. The node fails in an
isolated fresh pytest process by itself.

Because the fresh original-order full suite was green, there was no failing
fresh-runtime superset available to bisect for the earlier U6-L 500 report.

## Root Cause Identified

### Node 1

- nodeid:
  `tests/test_u6l_email_verified_onboarding_orchestration.py::test_reused_verification_token_remains_neutral_and_does_not_duplicate_orchestration`
- current fresh-runtime classification: `ENVIRONMENT_GATED`
- evidence:
  - original-order fresh full suite passed
  - reverse-order fresh full suite passed the entire U6-L file
  - direct `raise_app_exceptions=True` rerun passed
- sanitized conclusion:
  - the earlier HTTP 500 reported on the older long-lived runtime pair
    (`127.0.0.1:56433` / `redis://127.0.0.1:57380/0`) does not reproduce on a
    fresh PostgreSQL 16 / Redis 7 runtime with the same code base
  - no current-product exception was observable on the fresh runtime

### Node 2

- nodeid:
  `tests/test_dc10g_platform_uuid_export_error_hardening.py::TestExportEnqueueErrorBoundary::test_enqueue_failure_sanitized_response_and_logs`
- phase: call
- classification: `STALE_TEST_CONTRACT`
- direct failure symptom:
  - assertion expected `"ConnectionError"` in `caplog.text`
  - actual `caplog.text == ""`
  - response was still the expected sanitized HTTP 500
- direct isolated reproduction:
  - `/tmp/dc12r1-s1-v2-r2a_dc10g_target_alone.log`
  - `Captured stdout` shows the error log was emitted as structured JSON:
    `"Failed to enqueue export job: ConnectionError"`
- runtime root cause proof:
  - `api/v1/exports.py:168` lazily imports `from main import get_job_queue`
    during the request path
  - `main.py:42` executes `setup_structured_logging(...)` at module import time
  - `core/structured_logging.py:156-168` clears existing root handlers and
    replaces them with a `StreamHandler`
  - forensic script log: `/tmp/dc12r1-s1-v2-r2a_dc10g_logging_forensics.log`
  - exact observed proof from that script:
    - before call: `before_has_marker True`
    - after call: `after_has_marker False`
    - after call handlers: only `['StreamHandler']`

Sanitized conclusion:

- the `dc10g` test contract assumes `caplog` remains attached after the export
  error path runs
- that assumption is stale because the lazy `main` import reinitializes
  structured logging during the tested call and removes pre-existing root
  handlers, including the capture handler
- the product behavior under test still returns the intended sanitized 500 and
  logs the exception class name; only the test’s capture mechanism assumption is
  invalid

## Classification Summary

- `tests/test_u6l_email_verified_onboarding_orchestration.py::test_reused_verification_token_remains_neutral_and_does_not_duplicate_orchestration`
  - `ENVIRONMENT_GATED`
- `tests/test_dc10g_platform_uuid_export_error_hardening.py::TestExportEnqueueErrorBoundary::test_enqueue_failure_sanitized_response_and_logs`
  - `STALE_TEST_CONTRACT`

No fresh-runtime evidence in this pass supported `CURRENT_PRODUCT_DEFECT` or
`TEST_INFRASTRUCTURE` for the original U6-L report.

## Final Statement

The requested runtime forensics were completed on a fresh PostgreSQL 16 /
Redis 7 environment.

- The earlier U6-L 500 did not reproduce on fresh original order, fresh reverse
  order, or targeted `raise_app_exceptions=True` rerun, so it is classified as
  `ENVIRONMENT_GATED`.
- The reproducible suite-state issue discovered during reverse-order validation
  was independently root-caused to a stale log-capture contract in `dc10g`:
  the export enqueue path lazily imports `main`, which reinitializes structured
  logging and removes existing root handlers mid-test.

Only this report should be committed from this pass.
