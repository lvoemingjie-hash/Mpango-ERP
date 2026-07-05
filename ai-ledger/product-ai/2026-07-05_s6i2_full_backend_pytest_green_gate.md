# S6-I2 Full Backend Pytest Green Gate

Date: 2026-07-05
Branch: `opencode/s6i2-full-backend-pytest-green-gate-2026-07-05`
Base: `e127aaf9 merge: S6-I backend full pytest infrastructure alignment`

## Scope

Goal: make backend full `pytest` green against Docker-backed local PostgreSQL and Redis before U5, without production runtime changes.

Allowed scope used: test fixtures, stale test contracts, and test isolation only. No production runtime, API, service, model, migration, or RBAC behavior was changed.

## Changes

- Disposed shared async SQLAlchemy pools after reporting-role repair and between async fixture setup/truncation and test assertions to prevent asyncpg cached statement and event-loop leakage.
- Built the reporting-role test URL from explicit Docker-backed test environment variables and disposed the reporting engine after the module tests finish.
- Replaced affected `TestClient` usages with async `httpx.AsyncClient` plus `ASGITransport` to keep tests on the pytest-asyncio loop.
- Updated stale hard-coded permission expectations to match the current onboarded intake/SKU-import permission set.
- Updated migration infrastructure tests to assert the current Alembic head dynamically instead of the obsolete `023_inventory_reservations` head.
- Reframed obsolete B5 legacy payment-write tests to assert the current S6-B disabled `/api/v1/payments` write-path contract.
- Added targeted async engine disposal before fresh-tenant and local queue tests that were exposed by full-suite order.
- Moved the dashboard KPI sidebar smoke back into merge-grade coverage after it returned 200 reliably.

## GitNexus Impact

- `ensure_reporting_user_password`: LOW impact, no production dependants.
- `PERMISSIONS`: LOW impact, test-only stale contract alignment.
- `test_alembic_upgrade_head_creates_wide_version_table_on_fresh_database`: LOW impact, test-only stale Alembic head assertion.
- `TestRequestValidation`: LOW impact, test-only client-loop isolation change.

## Validation

Full backend gate:

- Command: `poetry run pytest -q --tb=short` with Docker-backed local env and secrets loaded into process environment only.
- Output file: `C:\Users\Jeff0\.local\share\opencode\tool-output\tool_f3070b1ba001HovASHSjCvetuA`
- Result: `1319 passed, 10 skipped, 15 xfailed, 2717 warnings` in `256.48s`.

Required focused gates after the full suite:

- RBAC gate: `44 passed, 2 warnings`.
- Reporting/dashboard gate: `40 passed`.
- Payment gate: `72 passed, 1 xfailed, 126 warnings`.
- U4 intake gate: `46 passed, 14 warnings`.

Hygiene:

- `git diff --check`: passed with CRLF working-copy warnings only.
- Changed-file non-ASCII scan: only pre-existing Unicode in `test_u1r1_bootstrap_completeness.py`.
- Changed-file mojibake scan: clean.
- Added-line secret-pattern scan: matched only variable/comment names; no secret literals.
- Pre-commit on changed files: passed after staging the detect-secrets baseline line-number refresh.
- GitNexus: `npx gitnexus analyze` reported already up to date; `npx gitnexus status` reported indexed commit and current commit both `e127aaf`.

## Notes

- The change intentionally keeps the fix in tests because the baseline failures were order/isolation drift or stale tests, not proven product defects.
- Reporting role repair remains fail-closed from S6-I and still requires explicit local/test environment conditions.
