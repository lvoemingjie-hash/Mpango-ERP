# 2026-07-13 DC-6B Export Malformed Job ID Fail-Closed Fix

## Scope

- Branch: `opencode/dc6b-export-malformed-job-id-fail-closed-2026-07-13`
- Base: `origin/product-dev-recovered` at `bde03da4dd322b4e68ca064c96121dec329524fa`
- Area: export status/download API fail-closed handling for malformed `job_id`
- Out of scope: migrations, frontend, deployment, package/lockfile changes, auth/permission redesign

## Red-Team Finding

Malformed export IDs such as `not-a-uuid` reached `uuid.UUID(job_id)` inside broad exception handlers. That produced HTTP 500 responses and exposed UUID parse exception text in public error messages.

## Behavior Choice

- Malformed UUID now returns HTTP 400 with code `INVALID_EXPORT_ID`.
- Rationale: malformed `job_id` is syntactically invalid client input, not a missing export. Existing tenant ownership hiding remains unchanged for well-formed IDs that do not belong to the caller.

## Fix

- Added `_parse_export_job_id()` and `_invalid_export_id_response()` in `backend/api/v1/exports.py`.
- `GET /api/v1/exports/{job_id}` validates `job_id` before DB lookup.
- `GET /api/v1/exports/{job_id}/download` validates `job_id` before DB lookup.
- Both routes keep `RequirePermission("exports:create")`.
- Tenant ownership checks are unchanged.
- Unexpected status/download handler failures now return generic public messages while detailed exception text remains in server logs.

## Regression Tests

Updated `backend/tests/test_s6_4_async_exports.py` with handler-level checks proving:

- Authenticated request with `exports:create` plus malformed status `job_id` returns controlled 400/404 and not 500.
- Authenticated request with `exports:create` plus malformed download `job_id` returns controlled 400/404 and not 500.
- Response bodies do not include Python UUID parse exception text or `ValueError`.
- No-auth `RequirePermission("exports:create")` remains 401.
- Wrong-tenant well-formed `job_id` remains hidden as `EXPORT_NOT_FOUND` 404.
- Pending job download remains `EXPORT_NOT_READY` 409.

## Validation

- Red check before fix: `poetry run pytest tests/test_s6_4_async_exports.py -q` failed two malformed-ID tests with HTTP 500.
- `poetry run pytest tests/test_s6_4_async_exports.py -q`: 38 passed.
- `poetry run pytest tests/test_route_authorization_policy.py -q`: 35 passed.
- `poetry run python -m py_compile api/v1/exports.py`: passed.
- `git diff --check`: clean except LF-to-CRLF warnings.
- ASCII/mojibake scans on changed files: clean.
- Secret-pattern scan on changed files: expected token/JWT field names only, no real secrets.
- `pre-commit` on changed files: passed, including detect-secrets.
- `npx gitnexus analyze`: completed.
- `npx gitnexus status`: up to date at `bde03da`.

## Notes

- Existing warning observed in route policy tests: SQLAlchemy `declarative_base` deprecation warning.
- No frontend, migration, deployment, package, lockfile, protected branch, or secret access changes were made.

## Verdict

DC-6B makes malformed export `job_id` values fail closed without raw exception disclosure while preserving permission and tenant isolation behavior.
