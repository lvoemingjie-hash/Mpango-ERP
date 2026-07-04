# S6-I Backend Full Pytest Infrastructure Alignment

Date: 2026-07-05
Branch: `opencode/s6i-backend-full-pytest-infra-alignment-2026-07-05`
Base: `origin/product-dev-recovered` at `1d0afa169a106450cac9f142c929ea9b3e22e825`

## Scope

Goal: make backend full `pytest` usable as a trustworthy governance gate before U5, or produce a precise fail map.

Allowed scope used: pytest config, test env loading helpers, test fixtures, and stale test infrastructure only. No production runtime/API/RBAC behavior was changed.

## Changes

- Installed the backend Poetry environment so `poetry run` uses the project dependencies instead of a global pytest entry point.
- Removed inert `pytest.ini` `env_files` config because `pytest-dotenv` is not installed and `tests/conftest.py` already loads `.env.test`/`.env`.
- Added test defaulting for `REPORTING_USER_PASSWORD` from `POSTGRES_PASSWORD` to unblock collection when reporting routes import.
- Added opt-in `ensure_reporting_user_password` fixture that aligns the local test DB `reporting_user` password with the test process `REPORTING_USER_PASSWORD` before reporting-role tests connect.
- S6-I-R1 CTO finding: the reporting-role repair fixture needed an explicit fail-closed safety guard before executing `ALTER ROLE`.
- Added fail-closed guard for the reporting-role repair fixture. It requires `MPANGO_ENV=test` and requires `DATABASE_URL` plus `POSTGRES_HOST` when present to resolve only to `127.0.0.1`, `localhost`, `postgres`, or documented local/CI service name `mpango_postgres`. Refusal raises `TEST_REPORTING_ROLE_REPAIR_REFUSED_NON_TEST_DB` without printing URLs or passwords.
- Scoped `test_s3a_fresh_tenant_runtime_smoke.py` DB session monkeypatches to the `smoke_client` fixture teardown so the mock `AsyncSessionLocal` does not leak into later API tests.

## GitNexus Impact

- `_load_test_env_defaults`: LOW impact, test-only.
- `backend/tests/conftest.py`: LOW impact, test-only.
- `ensure_reporting_user_password`: exact symbol not available before commit because GitNexus indexes committed code; fallback file impact for `conftest.py` stayed LOW and test-only.
- `smoke_client`: LOW impact, no upstream dependants.
- `test_mv_sales_daily_accessible_by_reporting_user`: LOW impact, no upstream dependants.
- `test_query_builder_reporting_user_access`: LOW impact, no upstream dependants.

## Validation

S6-I-R1 serial validation after adding the fail-closed reporting-role repair guard:

- RBAC gate: `44 passed, 2 warnings`.
- Reporting subset: `10 passed`.
- Payment focused gate: `72 passed, 1 xfailed, 126 warnings`.
- U4 intake focused gate: `46 passed, 14 warnings`.
- `git diff --check`: passed with CRLF working-copy warnings only.
- Changed-file secret scan: matched only test variable names and test token strings; no secret values printed or committed.
- Pre-commit on changed files: hooks reported no applicable files to check.

Focused gates after fixes:

- RBAC gate: `44 passed, 2 warnings`.
- Payment gate, serial: `72 passed, 1 xfailed, 126 warnings`.
- U4 intake gate: `46 passed, 14 warnings`.
- Reporting targeted subset: `10 passed`.
- S3-A followed by U4 contamination check: `59 passed, 22 warnings`.

Full backend gate after fixes:

- Command: `poetry run pytest -q` with Docker-backed local env and secrets redacted from logs.
- Output file: `C:\Users\Jeff0\.local\share\opencode\tool-output\tool_f2f3526390011Ap6nW9f5J7O3n`
- Result: `17 failed, 1297 passed, 10 skipped, 15 xfailed, 2491 warnings, 5 errors` in `223.03s`.

## Failure Map

### TEST_INFRA_DRIFT

- Default full pytest collection previously failed on missing `REPORTING_USER_PASSWORD`; fixed in `tests/conftest.py`.
- `pytest.ini` referenced `env_files` without an installed plugin; fixed by removing the inert config.
- Local Poetry virtualenv was missing dependencies while `poetry run pytest` resolved global pytest; repaired with `poetry install --with dev,test`.
- Local `reporting_user` password could drift from `REPORTING_USER_PASSWORD`; targeted reporting tests now repair it via `ensure_reporting_user_password`.
- S3-A smoke test leaked `database.session.AsyncSessionLocal` mock into later tests; fixed by restoring the original factories at fixture teardown.

### FLAKY_CONCURRENCY

- Running focused gates concurrently against the same local DB caused `tuple concurrently updated` in shared schema DDL. Serial rerun passed.
- Full-suite Windows async failures remain around Redis/rate-limiter and asyncpg connection cleanup: `RuntimeError: Event loop is closed`.
- Full-suite reporting-role tests still fail in full order with `InvalidPasswordError`, while the same reporting subset passes immediately before and after the full run. This is remaining order/isolation drift, not a proven reporting product defect.

### STALE_TEST_CONTRACT / LEGACY_OBSOLETE_TEST

- `tests/test_s3c_self_contained_fresh_tenant_live_proof.py` still expects a hard-coded S3-C permission set missing current intake permissions. S6-E registry gate passes and is the current permission drift contract.
- `tests/test_s4g_migration_infrastructure_hardening.py` expects `023_inventory_reservations` in a version-table scenario that currently reports only `025_intake_apply_audit`; classify as stale migration test contract pending owner review.
- `tests/test_b5_real_db.py` uses shared live idempotency keys/state and fails with `409`/`IDEMPOTENCY_CONFLICT`; classify as legacy live-DB test isolation drift.

### PRODUCT_DEFECT

- No production defect was proven. U4 `422` failures from the baseline disappeared after fixing the Poetry/test environment, and U4 focused gate is green.

### STOP / CTO Attention

- Full backend pytest is still not a green governance gate.
- Focused U5-critical gates are green when run serially.
- Remaining full-suite failures should be resolved as a separate test isolation cleanup, not by changing production runtime behavior.
