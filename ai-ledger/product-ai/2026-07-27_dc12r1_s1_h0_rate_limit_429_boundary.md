# DC-12R1-S1-H0-R1 Scope Cleanup + Evidence Publication

Date: Monday, July 27, 2026
Branch: `opencode/dc12r1-s1-h0-rate-limit-429-boundary-2026-07-27`
Expected base: `47517a377770f293d37bea5b6329364960f12381`

## Verdict

`PASS_FOR_CTO_DC12R1_S1_H0_R1_MERGE_REVIEW`

Natural-order full backend gate evidence is reused legitimately because the final product middleware file is byte-identical to the implementation used by the two existing green full runs.
Reverse-order full-suite diagnostics remain fully classified with accounting gap `0`.

## Preflight

- `HEAD`: `47517a377770f293d37bea5b6329364960f12381`
- `merge-base(HEAD, expected-base)`: `47517a377770f293d37bea5b6329364960f12381`
- Current branch: `opencode/dc12r1-s1-h0-rate-limit-429-boundary-2026-07-27`
- Recovery evidence saved outside the repository:
  - `/tmp/dc12r1_s1_h0_r1_recovery/full_worktree.diff`
  - `/tmp/dc12r1_s1_h0_r1_recovery/status.txt`
  - `/tmp/dc12r1_s1_h0_r1_recovery/diff_files.txt`
  - `/tmp/dc12r1_s1_h0_r1_recovery/rate_limiting.sha256`
- Middleware SHA256 before cleanup:
  - `ee87711120098b2f3f61b844f049dd3eb3dd98d908c0ee343f11b2a2e97e4e06  backend/api/middleware/rate_limiting.py`

## Scope Cleanup

Allowed remaining changes were restricted to these seven files only:

- `backend/api/middleware/rate_limiting.py`
- `backend/tests/test_reliability.py`
- `backend/tests/test_u6d_verify_email_endpoint.py`
- `backend/tests/test_u6l_email_verified_onboarding_orchestration.py`
- `backend/tests/test_dc10g_platform_uuid_export_error_hardening.py`
- `backend/tests/test_u6i1_owner_credential_setup_schema.py`
- `ai-ledger/product-ai/2026-07-27_dc12r1_s1_h0_rate_limit_429_boundary.md`

Cleanup actions:

- Restored `193` unrelated tracked files individually after a prior repo-wide `pre-commit run --all-files` modified them.
- Restored the out-of-scope tracked artifact `backend/.hypothesis/unicode_data/15.0.0/codec-utf-8.json.gz` individually.
- Untracked artifact review found only the H0 report file above; no other H0-generated untracked files were retained.
- No blanket cleanup, `git reset --hard`, or `git clean -fd` was used.

## Source Review

Confirmed in `backend/api/middleware/rate_limiting.py`:

- `RateLimitingMiddleware` catches only `MpangoAPIException`.
- The response is built through the standard `mpango_exception_handler` contract.
- Rate-limit responses preserve:
  - status `429`
  - code `RATE_LIMIT_EXCEEDED`
  - sanitized `details`
  - `request_id`
- Rate-limit responses add:
  - `Retry-After`
  - `X-RateLimit-Limit`
  - `X-RateLimit-Remaining`
  - `X-RateLimit-Reset`
  - `X-Request-ID`
- Success responses retain the `X-RateLimit-*` headers.
- Unrelated exceptions are still re-raised.

Confirmed in `backend/core/rate_limiter.py`:

- Redis access failures still fail open by returning an allowed result.
- `MpangoAPIException` raised by the limiter is re-raised unchanged.

Assertion discipline:

- No new `skip`, `xfail`, deselection, or assertion weakening was introduced in the H0 scope.
- Existing `xfailed` nodes in `test_request_validation.py` are pre-existing baseline behavior.

Why `U6L` changed:

- `backend/tests/test_u6l_email_verified_onboarding_orchestration.py` now installs an explicit allow-limiter fixture.
- This is directly related to deterministic isolation. `U6L` is not a rate-limit contract test, and shared anonymous-IP counters could push it into false `429` state when run after rate-limit-heavy files.

Why `U6I1` changed:

- `backend/tests/test_u6i1_owner_credential_setup_schema.py` is a scope sentinel test, not a runtime behavior test.
- It previously rejected any `backend/api/*` file change. H0 intentionally changes exactly one allowed API path:
  - `backend/api/middleware/rate_limiting.py`
- The update keeps the guard strict while allowing only that one authorized H0 file. No other `backend/api/*` path is permitted.

## RED and GREEN Evidence

Pre-fix RED evidence already established the real middleware boundary defect:

- boundary overflow response before fix: uncontrolled `500`
- response code before fix: `INTERNAL_SERVER_ERROR`
- targeted RED run in `tests/test_reliability.py`: `3 failed`

Focused GREEN validation was rerun in a fresh disposable environment:

- PostgreSQL 16: `127.0.0.1:56439`
- Redis 7: `127.0.0.1:57386`
- Safe DB source DSN host: loopback only
- `MPANGO_ENV=test`
- `MPANGO_ALLOW_TEMP_DB_CREATE=1`
- ephemeral databases created via the protected temp-DB helpers

Focused results:

- `tests/test_reliability.py -k 'TestRateLimitingMiddlewareBoundary or test_rate_limiter_fails_open_on_redis_error or test_rate_limit_response_format'`
  - `6 passed, 9 deselected`
- Anonymous 101st request boundary proof is included in the reliability boundary set and passed:
  - result `429`, never `500`
- `tests/test_request_validation.py -k test_login_rejects_missing_email`
  - standalone on ephemeral DB: `1 passed, 8 deselected`
- standalone `tests/test_dc10g_platform_uuid_export_error_hardening.py -k test_enqueue_failure_sanitized_response_and_logs`
  - `1 passed, 7 deselected`

Affected bundle, original order:

- `tests/test_u6d_verify_email_endpoint.py`
- `tests/test_u6l_email_verified_onboarding_orchestration.py`
- `tests/test_u6i1_owner_credential_setup_schema.py`
- `tests/test_dc10g_platform_uuid_export_error_hardening.py`
- `tests/test_request_validation.py`
- Result: `33 passed, 6 xfailed`

Affected bundle, reverse order:

- `tests/test_request_validation.py`
- `tests/test_dc10g_platform_uuid_export_error_hardening.py`
- `tests/test_u6i1_owner_credential_setup_schema.py`
- `tests/test_u6l_email_verified_onboarding_orchestration.py`
- `tests/test_u6d_verify_email_endpoint.py`
- Result: `33 passed, 6 xfailed`

## Reused Full Backend Gates

Middleware identity proof for reuse:

- Current SHA256:
  - `ee87711120098b2f3f61b844f049dd3eb3dd98d908c0ee343f11b2a2e97e4e06`
- Recorded SHA256 used for the previous natural-order green gates:
  - `ee87711120098b2f3f61b844f049dd3eb3dd98d908c0ee343f11b2a2e97e4e06`
- Result: exact match, so rerunning both natural-order full suites was not required.

Natural-order full backend gate A:

- PostgreSQL 16: `127.0.0.1:56437`
- Redis 7: `127.0.0.1:57384`
- Result:
  - `2876 passed`
  - `48 skipped`
  - `15 xfailed`
  - `0 failed`
  - `0 errors`

Natural-order full backend gate B:

- PostgreSQL 16: `127.0.0.1:56438`
- Redis 7: `127.0.0.1:57385`
- Result:
  - `2876 passed`
  - `48 skipped`
  - `15 xfailed`
  - `0 failed`
  - `0 errors`

## Reverse-Order Diagnostic Classification

Reverse-order diagnostic environment:

- PostgreSQL 16: `127.0.0.1:56436`
- Redis 7: `127.0.0.1:57383`

Reverse full-suite result:

- `2893 passed`
- `29 skipped`
- `15 xfailed`
- `2 failed`

Exact classified nodes:

1. `tests/test_request_validation.py::TestRequestValidation::test_login_rejects_missing_email`
   - Phase: `call`
   - Exception class: `ExceptionGroup`
   - Sanitized root cause: `RuntimeError: Event loop is closed`
   - Classification: `TEST_INFRASTRUCTURE`
   - Evidence:
     - standalone on ephemeral DB passed
     - affected bundle original order passed
     - affected bundle reverse order passed
     - failure reproduces only in reverse full-suite state

2. `tests/test_dc10g_platform_uuid_export_error_hardening.py::TestExportEnqueueErrorBoundary::test_enqueue_failure_sanitized_response_and_logs`
   - Phase: `call`
   - Exception class: `AssertionError`
   - Sanitized root cause: logger capture stayed empty after upstream `RuntimeError: Event loop is closed`, so the expected `ConnectionError` class name was never emitted
   - Classification: `TEST_INFRASTRUCTURE`
   - Evidence:
     - standalone passed
     - affected bundle original order passed
     - affected bundle reverse order passed
     - failure reproduces only in reverse full-suite state

Accounting gap: `0`

## Quality Gates

- `git diff --check`
  - passed
- scoped `pre-commit run --files` on the seven allowed files
  - passed
- scoped `detect-secrets` on the seven allowed files
  - passed
- mojibake scan on the seven allowed files
  - passed

Repository-wide `pre-commit run --all-files` was executed earlier and failed only on pre-existing out-of-scope issues:

- `check-yaml` failures in existing workflow / k8s files
- existing `detect-secrets` findings outside the H0 scope
- auto-format edits on unrelated tracked files from whitespace / EOF hooks

Those repo-wide findings were documented as pre-existing and were individually restored out of this change set.

## GitNexus

- `gitnexus status`
  - branch index up to date at commit `47517a3`
- `gitnexus detect-changes --repo Mpango-ERP`
  - `6 files, 16 symbols`
  - affected processes: `0`
  - risk level: `low`
- `gitnexus impact RateLimitingMiddleware --repo Mpango-ERP -f backend/api/middleware/rate_limiting.py --include-tests --depth 4 -l 80`
  - risk: `MEDIUM`
  - impacted count: `34`
  - exact upstream blast radius includes `backend/api/app.py`, `backend/tests/test_reliability.py`, `test_u6d`, `test_u6l`, `test_request_validation`, `test_dc10g`, route-policy, export, and onboarding chains
- `gitnexus context RateLimiter --repo Mpango-ERP -f backend/core/rate_limiter.py -l 80`
  - exact class context located
  - confirmed method set includes `check_rate_limit`
  - confirmed direct importers include:
    - `backend/main.py`
    - `backend/tests/test_reliability.py`
    - `backend/api/middleware/rate_limiting.py`
- `gitnexus impact 'RateLimiter.check_rate_limit'`
  - tool returned `Target 'RateLimiter.check_rate_limit' not found`
  - no contradictory impact signal was emitted
- `gitnexus analyze .`
  - analyzer forced a full rebuild after detecting an incomplete prior incremental run
  - status remained indexed on the correct branch / commit
  - no contradictory risk elevation was emitted during the observed run window

## Cleanup Proof

Removed earlier H0 disposable containers:

- `dc12r1-s1-h0-focus-pg16`
- `dc12r1-s1-h0-focus-redis7`
- `dc12r1-s1-h0-fulla-pg16`
- `dc12r1-s1-h0-fulla-redis7`
- `dc12r1-s1-h0-fullb-pg16`
- `dc12r1-s1-h0-fullb-redis7`
- `dc12r1-s1-h0-fullc-pg16`
- `dc12r1-s1-h0-fullc-redis7`

This R1 focused validation also used:

- `dc12r1-s1-h0r1-focus-pg16`
- `dc12r1-s1-h0r1-focus-redis7`

Final zero-leftover proof after removing those R1 containers:

- `docker ps -a --format '{{.Names}}' | grep '^dc12r1-s1-h0'`
- result: no matches
- `docker network ls --format '{{.Name}}' | grep '^dc12r1-s1-h0'`
- result: no matches
- `docker volume ls --format '{{.Name}}' | grep '^dc12r1-s1-h0'`
- result: no matches

## Final Scope

Expected final `git diff --name-status` for this commit contains exactly these seven files:

- `backend/api/middleware/rate_limiting.py`
- `backend/tests/test_reliability.py`
- `backend/tests/test_u6d_verify_email_endpoint.py`
- `backend/tests/test_u6l_email_verified_onboarding_orchestration.py`
- `backend/tests/test_dc10g_platform_uuid_export_error_hardening.py`
- `backend/tests/test_u6i1_owner_credential_setup_schema.py`
- `ai-ledger/product-ai/2026-07-27_dc12r1_s1_h0_rate_limit_429_boundary.md`
