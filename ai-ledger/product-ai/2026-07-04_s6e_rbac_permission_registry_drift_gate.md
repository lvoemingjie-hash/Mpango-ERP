# S6-E RBAC Permission Registry Drift Gate

Date: 2026-07-04
Branch: `opencode/s6e-rbac-permission-registry-drift-gate-2026-07-04`
Base: `origin/product-dev-recovered` at `d531f28db6d1e71624a6722cb0bdcc742c8d71f5`
Scope: RBAC permission registry drift gate, tenant provisioning seed coverage, existing route policy harness alignment

## Intent

Add a machine-verifiable gate that prevents backend API route permissions from drifting away from tenant provisioning seed paths and frontend permission references.

The gate verifies:

- Live FastAPI `/api/v1/**` route dependency permissions, extracted from `APIRoute.dependant.dependencies`.
- Tenant provisioning permission lists in `onboard_tenant.py`, `create_wholesaler.py`, `seed_demo_data.py`, and `seed_test_tenant.py`.
- Frontend permission references under `frontend/src/utils` and `frontend/src/pages`.
- Data Intake permission completeness for `intake:create`, `intake:read`, `intake:update`, and `skus:import`.
- S6-D catalog-only wording did not introduce new Data Intake permission semantics in `DataIntakePage.tsx`.

## Files Changed

- `backend/tests/test_s6e_rbac_permission_registry_drift_gate.py`
- `backend/scripts/seed_demo_data.py`
- `backend/tests/test_route_authorization_policy.py`
- `ai-ledger/product-ai/2026-07-04_s6e_rbac_permission_registry_drift_gate.md`

## What Changed

- Added `test_s6e_rbac_permission_registry_drift_gate.py` as a route-runtime drift gate. The test imports the live FastAPI app and walks dependency objects rather than relying on grep-only route matching.
- Added missing existing permission codes to `seed_demo_data.py` so the demo tenant seed matches route-required permissions.
- Updated the existing route authorization policy harness to recognize Data Intake's existing `RequireAnyIntakePermission` and `RequireAllPermissions` dependencies as RBAC auth dependencies.

No production RBAC middleware, auth model, platform/tenant boundary logic, migration, or business permission semantics changed.

## Route Permission Inventory

The S6-E gate extracts permissions from live route dependencies. For audit readability, the corresponding route declaration inventory includes:

- `dashboards:read`
- `exports:create`
- `finance:read`
- `intake:create`
- `intake:read`
- `intake:update`
- `invitations:create`
- `inventory:read`
- `inventory:update`
- `metrics:admin`
- `orders:create`
- `orders:read`
- `orders:update`
- `payments:create`
- `payments:read`
- `platform:admin`
- `pricing:read`
- `pricing:write`
- `reports:analyze`
- `reports:read`
- `retailers:read`
- `roles:assign`
- `roles:read`
- `skus:create`
- `skus:import`
- `skus:read`
- `skus:update`
- `system:admin`
- `users:create`
- `users:deactivate`
- `users:read`
- `users:update`
- `wholesalers:read`
- `wholesalers:write`

## Drift Found And Fixed

Pre-fix S6-E gate result:

- `seed_demo_data.py` was missing route-required permissions:
- `exports:create`
- `finance:read`
- `invitations:create`
- `metrics:admin`
- `orders:update`
- `pricing:read`
- `pricing:write`
- `retailers:read`
- `roles:assign`
- `roles:read`
- `system:admin`
- `users:deactivate`
- `wholesalers:read`
- `wholesalers:write`

Fix:

- Added those existing permission codes to `backend/scripts/seed_demo_data.py`.
- Did not invent new permission names.
- Did not add migrations.

## Coverage Table

- `backend/scripts/onboard_tenant.py`: PASS, no missing tenant API route permissions.
- `backend/scripts/create_wholesaler.py`: PASS, no missing tenant API route permissions.
- `backend/scripts/seed_demo_data.py`: FAIL before fix, PASS after adding existing missing permissions.
- `backend/scripts/seed_test_tenant.py`: PASS, no missing tenant API route permissions.
- `backend/scripts/bootstrap_tenant_schema.py`: audited; it does not own the seeded permission registry tuples used by this gate.
- `frontend/src/utils/permissions.ts` and frontend pages: PASS, referenced permissions are seeded.
- `frontend/src/pages/skus/DataIntakePage.tsx`: PASS, permission strings remain within the allowed Data Intake/SKU import set.

## GitNexus

Pre-edit impact:

- `backend/api/middleware/rbac.py`: HIGH impact, not edited.
- `backend/scripts/onboard_tenant.py`: LOW impact, audited only.
- `backend/scripts/create_wholesaler.py`: LOW impact, audited only.
- `backend/scripts/seed_demo_data.py`: LOW impact, edited minimally.
- `backend/scripts/seed_test_tenant.py`: LOW impact, audited only.
- `backend/scripts/bootstrap_tenant_schema.py`: MEDIUM impact, audited only.
- `backend/tests/test_route_authorization_policy.py`: LOW impact, test harness alignment only.

Index evidence:

- `npx gitnexus analyze` pre-edit: PASS, `6,156 nodes | 17,876 edges | 408 clusters | 227 flows`.
- `npx gitnexus analyze` post-edit: PASS, `Already up to date`.
- `npx gitnexus status` post-edit: PASS, indexed commit and current commit both `d531f28`, status `up-to-date`.
- `npx gitnexus --help`: `detect_changes` command is not available in this CLI; no detect_changes evidence captured.

## Validation

- `poetry run pytest tests/test_s6e_rbac_permission_registry_drift_gate.py -q` pre-fix -> FAIL as expected, found `seed_demo_data.py` drift.
- `poetry run pytest tests/test_s6e_rbac_permission_registry_drift_gate.py -q` post-fix -> PASS (`4 passed, 1 warning`).
- `poetry run pytest tests/test_s6e_rbac_permission_registry_drift_gate.py tests/test_route_authorization_policy.py tests/test_u1_bootstrap_permission_completeness.py -q` -> PASS (`43 passed, 1 warning`).
- `poetry run pytest tests/test_u3b1_contract_foundation.py -q` -> PASS (`27 passed`).
- `poetry run pytest tests/test_u4c_intake_api_contract.py -q` -> ENV BLOCKED after static/registration tests: `5 passed`, then `7 errors` in DB-backed fixture setup due `socket.gaierror: [Errno 11001] getaddrinfo failed` while asyncpg tried to resolve/connect to the configured PostgreSQL host from `tests/conftest.py` tenant schema bootstrap.
- `git diff --check` -> PASS, with Git LF/CRLF working-copy warnings only.
- Changed-file non-ASCII scan -> REPORT_ONLY; hit pre-existing non-ASCII in `backend/tests/test_route_authorization_policy.py` comments/docstrings.
- Changed-file mojibake scan -> PASS, no matches.
- Changed-file sensitive-keyword scan -> REPORT_ONLY by filename only; hits are allowlisted dummy/test/demo configuration in changed files.
- `pre-commit run --files backend/scripts/seed_demo_data.py backend/tests/test_route_authorization_policy.py backend/tests/test_s6e_rbac_permission_registry_drift_gate.py` -> PASS.

## Risk

Low. The runtime authorization implementation was not changed. The only production-adjacent data change is adding already-existing route-required permissions to the demo seed permission registry.

Remaining risk:

- DB-backed U4C intake contract assertions still need an environment with resolvable PostgreSQL test configuration to run past fixture setup.
- `poetry run python` cannot import FastAPI in this local environment, while `poetry run pytest` can run the project tests successfully; this was not changed because the established validation path is pytest.

## Out Of Scope

- No deployment.
- No VPS access.
- No push to `product-dev-recovered`.
- No migration.
- No production RBAC middleware edit.
- No auth model redesign.
- No broad RBAC rewrite.
- No platform/tenant boundary semantic change.
