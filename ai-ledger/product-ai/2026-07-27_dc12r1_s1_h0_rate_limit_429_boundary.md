# DC-12R1-S1-H0-R2 Narrow Exception Boundary

Date: Monday, July 27, 2026
Branch: `opencode/dc12r1-s1-h0-rate-limit-429-boundary-2026-07-27`
Started from tip: `9e2296ae19e25531f0cd0ad03143db15ede529fd`
Expected base: `47517a377770f293d37bea5b6329364960f12381`

## Verdict

`PASS_FOR_CTO_DC12R1_S1_H0_R2_MERGE_REVIEW`

The middleware exception boundary is now narrowed to `rate_limiter.check_rate_limit(request)` only.
Only `MpangoAPIException` with `error_code == RATE_LIMIT_EXCEEDED` and `status_code == 429` is converted into the standard rate-limit response.
All other limiter-raised `MpangoAPIException` values and every exception from `call_next()` now re-raise unchanged.

## Product Change

Changed file:

- `backend/api/middleware/rate_limiting.py`

Behavior now enforced:

- `try/except MpangoAPIException` wraps only `await rate_limiter.check_rate_limit(request)`
- handled path requires both:
  - `exc.error_code == ErrorCode.RATE_LIMIT_EXCEEDED`
  - `exc.status_code == 429`
- handled `429` path still uses `mpango_exception_handler`
- handled `429` path still returns:
  - status `429`
  - code `RATE_LIMIT_EXCEEDED`
  - sanitized details
  - `request_id`
  - `Retry-After`
  - `X-RateLimit-Limit`
  - `X-RateLimit-Remaining`
  - `X-RateLimit-Reset`
  - `X-Request-ID`
- successful requests still retain `X-RateLimit-*` and `X-Request-ID`
- non-rate-limit `MpangoAPIException` from the limiter re-raises unchanged
- every `call_next()` exception, including `MpangoAPIException`, re-raises unchanged
- Redis failure fail-open behavior remains in `backend/core/rate_limiter.py` unchanged

## Test Changes

Changed file:

- `backend/tests/test_reliability.py`

Added coverage for the narrowed contract:

- success path still emits `X-RateLimit-*` headers
- limiter `MpangoAPIException(ErrorCode.VALIDATION_ERROR, 429)` re-raises unchanged
- limiter `MpangoAPIException(ErrorCode.RATE_LIMIT_EXCEEDED, 503)` re-raises unchanged
- `call_next()` raising `MpangoAPIException` re-raises unchanged
- `call_next()` raising `RuntimeError` re-raises unchanged

No skip, xfail, deselection, or assertion weakening was introduced.

## RED Evidence

Pre-fix targeted RED command:

```bash
cd backend
pytest tests/test_reliability.py -k 'outside_429_contract or call_next_mpango_exception or call_next_runtime_error or successful_response_retains_rate_limit_headers'
```

Pre-fix result:

- `3 failed, 2 passed, 15 deselected`

Exact RED nodes:

1. `tests/test_reliability.py::TestRateLimitingMiddlewareBoundary::test_limiter_mpango_exception_outside_429_contract_is_reraised_unchanged[VALIDATION_ERROR-429]`
   - phase: `call`
   - exception: `Failed`
   - sanitized root cause: middleware swallowed a non-rate-limit `MpangoAPIException` instead of re-raising it
2. `tests/test_reliability.py::TestRateLimitingMiddlewareBoundary::test_limiter_mpango_exception_outside_429_contract_is_reraised_unchanged[RATE_LIMIT_EXCEEDED-503]`
   - phase: `call`
   - exception: `Failed`
   - sanitized root cause: middleware swallowed a non-429 limiter `MpangoAPIException` instead of re-raising it
3. `tests/test_reliability.py::TestRateLimitingMiddlewareBoundary::test_call_next_mpango_exception_is_reraised_unchanged`
   - phase: `call`
   - exception: `Failed`
   - sanitized root cause: middleware caught `MpangoAPIException` raised downstream by `call_next()`

## GREEN Evidence

Post-fix rerun of the same targeted command:

- `5 passed, 15 deselected`

This proves:

- the allowed `429 RATE_LIMIT_EXCEEDED` path still works
- limiter exceptions outside that exact contract now bubble unchanged
- downstream `call_next()` exceptions are no longer intercepted by the middleware

## Focused Reliability Gate

Fresh disposable focus environment:

- PostgreSQL 16 container: `dc12r1-s1-h0r2-focus-pg16`
- PostgreSQL host: `127.0.0.1:56440`
- Redis 7 container: `dc12r1-s1-h0r2-focus-redis7`
- Redis host: `127.0.0.1:57387`
- `MPANGO_ENV=test`
- `MPANGO_ALLOW_TEMP_DB_CREATE=1`
- `MPANGO_TEMP_DB_ALLOWED_HOSTS=127.0.0.1,localhost`
- `MPANGO_TEMP_DB_ALLOWED_PORTS=56440`
- loopback-only `TEST_DATABASE_URL`

Focused reliability command:

```bash
cd backend
pytest tests/test_reliability.py -k 'TestRateLimitingMiddlewareBoundary or test_rate_limiter_fails_open_on_redis_error or test_rate_limit_response_format'
```

Focused result:

- `11 passed, 9 deselected, 1 warning`

Validated here:

- anonymous exceed path returns controlled `429`
- authenticated exceed path returns controlled `429`
- anonymous request `101` returns controlled `429`, never `500`
- success responses retain `X-RateLimit-*`
- Redis outage remains fail-open
- non-contract limiter exceptions re-raise unchanged
- `call_next()` exceptions re-raise unchanged

## Affected Bundle Validation

Invalid evidence discarded:

- an earlier attempt ran original and reverse bundle orders in parallel against one shared disposable environment
- that evidence was rejected because it was not isolated and introduced cross-process interference

Valid original-order bundle used fresh environment `bundlea`:

- PostgreSQL 16: `127.0.0.1:56443`
- Redis 7: `127.0.0.1:57390`

Command:

```bash
cd backend
pytest \
  tests/test_u6d_verify_email_endpoint.py \
  tests/test_u6l_email_verified_onboarding_orchestration.py \
  tests/test_u6i1_owner_credential_setup_schema.py \
  tests/test_dc10g_platform_uuid_export_error_hardening.py \
  tests/test_request_validation.py
```

Result:

- `33 passed, 6 xfailed, 366 warnings`

Valid reverse-order bundle used separate fresh environment `bundleb`:

- PostgreSQL 16: `127.0.0.1:56444`
- Redis 7: `127.0.0.1:57391`

Command:

```bash
cd backend
pytest \
  tests/test_request_validation.py \
  tests/test_dc10g_platform_uuid_export_error_hardening.py \
  tests/test_u6i1_owner_credential_setup_schema.py \
  tests/test_u6l_email_verified_onboarding_orchestration.py \
  tests/test_u6d_verify_email_endpoint.py
```

Result:

- `33 passed, 6 xfailed, 486 warnings`

## Full Backend Gates

Because product middleware code changed, two natural-order full backend gates were rerun on separate fresh PostgreSQL 16 / Redis 7 environments.
Each source database was migrated to head before the suite run with a protected loopback-only test DSN and `REPORTING_USER_PASSWORD` set.

Abandoned invalid full-run attempts:

- earlier `fulla` and `fullb` suite attempts were invalid because their source databases were not pre-migrated
- standalone reproduction on that state showed:
  - `tests/business/test_s4e_reservation_schema_contract.py::test_fresh_tenant_bootstrap_creates_inventory_reservations_contract`
  - sanitized root cause: `reporting_role` missing because migration `011_s6_p_reporting_role` had not run
- this was an environment setup issue, not a current product defect
- those runs were excluded from final gate evidence

Valid full gate A:

- PostgreSQL 16 container: `dc12r1-s1-h0r2-fulld-pg16`
- PostgreSQL host: `127.0.0.1:56448`
- Redis 7 container: `dc12r1-s1-h0r2-fulld-redis7`
- Redis host: `127.0.0.1:57395`

Result:

- `2881 passed, 48 skipped, 15 xfailed, 1750 warnings`
- `0 failed`
- `0 errors`

Valid full gate B:

- PostgreSQL 16 container: `dc12r1-s1-h0r2-fulle-pg16`
- PostgreSQL host: `127.0.0.1:56449`
- Redis 7 container: `dc12r1-s1-h0r2-fulle-redis7`
- Redis host: `127.0.0.1:57396`

Result:

- `2881 passed, 48 skipped, 15 xfailed, 1738 warnings`
- `0 failed`
- `0 errors`

## Retained Reverse-Full Diagnostic Classification

Reverse-full rerun was not required for R2.
The existing classified diagnostic evidence from the prior H0 run remains the retained reverse-order record.

Exact classified nodes:

1. `tests/test_request_validation.py::TestRequestValidation::test_login_rejects_missing_email`
   - phase: `call`
   - exception class: `ExceptionGroup`
   - sanitized root cause: `RuntimeError: Event loop is closed`
   - classification: `TEST_INFRASTRUCTURE`
2. `tests/test_dc10g_platform_uuid_export_error_hardening.py::TestExportEnqueueErrorBoundary::test_enqueue_failure_sanitized_response_and_logs`
   - phase: `call`
   - exception class: `AssertionError`
   - sanitized root cause: logger capture stayed empty after upstream `RuntimeError: Event loop is closed`
   - classification: `TEST_INFRASTRUCTURE`

Accounting gap: `0`

## Final Scope

Allowed changed files at R2 completion:

- `backend/api/middleware/rate_limiting.py`
- `backend/tests/test_reliability.py`
- `ai-ledger/product-ai/2026-07-27_dc12r1_s1_h0_rate_limit_429_boundary.md`

No unrelated file modifications are retained.
