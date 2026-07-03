# S6-A Tenant Provisioning Truth Gate

Date: 2026-07-03

Branch: `opencode/s6a-tenant-provisioning-truth-gate-2026-07-03`

Baseline: `origin/product-dev-recovered` at `61a6a534725fb1c54a83b7ade679e0b120c9906e`

Verdict: PASS_FOR_CTO_REVIEW

## Current Truth

The customer creation UI and `POST /api/v1/wholesalers` path are registry-only after S6-A. They create a `public.wholesalers` registry record and do not create a usable tenant workspace.

Read-only audit findings:

- `frontend/src/pages/tenants/TenantListPage.tsx:75-87` calls `tenantService.create(...)` for new records and now displays a registry-only success notice.
- `frontend/src/pages/tenants/TenantListPage.tsx:115-132` labels the page `System Tenant Registry` or `Customer Registry`, downgrades the button to `Create registry record`, and shows the registry-only warning.
- `frontend/src/pages/tenants/TenantFormModal.tsx:71-83` labels the modal `Create customer registry record` and repeats the registry-only warning inside the form.
- `frontend/src/services/tenantService.ts:11-26` documents that create is registry-only and types the optional registry-only response message.
- `backend/api/v1/wholesalers.py:86-123` creates the registry record and returns the existing response envelope with a `message` that explicitly says schema, login, admin user, RBAC, inventory, orders, and finance workspace were not provisioned.
- `backend/scripts/create_wholesaler.py:12-16` documents the older script bootstrap path for schema, public record, admin user, and admin role.
- `backend/scripts/create_wholesaler.py:294-335` shows that full login-capable bootstrap is separate from the API path and includes schema creation, admin user creation, role/permission setup, and credential output.
- `backend/scripts/onboard_tenant.py:17-23` documents the fuller onboarding path: public record, isolated tenant schema, migrations, admin user, optional demo data, and validation.
- `backend/scripts/bootstrap_tenant_schema.py:3-5` documents the table/schema bootstrap helper used to create tenant schema tables.

This round did not implement full SaaS provisioning, first-admin creation, password delivery, Gmail/social login, tenant schema bootstrap from the API, migration orchestration, or rollback/idempotency for onboarding.

## Changed Files

- `frontend/src/pages/tenants/TenantListPage.tsx`
- `frontend/src/pages/tenants/TenantFormModal.tsx`
- `frontend/src/services/tenantService.ts`
- `frontend/src/tests/TenantListPage.test.tsx`
- `backend/api/v1/wholesalers.py`
- `backend/tests/api/test_wholesaler.py`
- `ai-ledger/product-ai/2026-07-03_s6a_tenant_provisioning_truth_gate.md`

No deployment files, migrations, external auth, Gmail/social login, password generation/display, VPS access, or full onboarding execution were added.

## Implementation

- Reworded the tenant page to `System Tenant Registry` / `Customer Registry`.
- Replaced `Create Customer` with `Create registry record`.
- Added a visible page-level warning: `This creates a registry record only. It does not provision login, tenant schema, admin user, RBAC, inventory, orders, or finance workspace.`
- Added the same warning inside the create modal.
- Changed create success feedback to avoid implying the customer is ready to log in or use the system.
- Added an API create docstring and response `message` clarifying the registry-only contract while preserving the existing `WholesalerResponse` schema and `data` shape.
- Added tests that assert the registry-only warning is present and misleading ready/provisioned copy is absent.
- Added backend contract tests that assert create returns a registry-only message while preserving list/read basics.

## GitNexus

Pre-edit setup:

- `npx gitnexus analyze`: indexed the isolated worktree; `6,174 nodes`, `17,875 edges`, `427 clusters`, `227 flows`.

Pre-edit impact checks:

- `TenantListPage`: LOW, `0` impacted symbols.
- `TenantFormModal`: LOW, `0` impacted symbols.
- `tenantService.create`: target not found; manually reviewed and kept to a narrow type/comment change.
- `create_wholesaler` was ambiguous; script function impact was LOW, `3` impacted symbols, limited to script bootstrap flow.
- API route context `Function:backend/api/v1/wholesalers.py:create_wholesaler`: no incoming callers in GitNexus; outgoing calls are expected CRUD, serializer, response, and RBAC dependencies.
- `WholesalerRead`: HIGH, so the shared response data schema was not changed.
- `WholesalerResponse`: HIGH, so the shared response wrapper schema was not changed.

Post-edit checks:

- `npx gitnexus analyze`: already up to date.
- `npx gitnexus status`: up to date at commit `61a6a53`.
- `gitnexus detect_changes`: unavailable in this CLI; `npx gitnexus --help` lists no `detect_changes` command.

## Validation

- `pnpm install --frozen-lockfile`: PASS, installed frontend dependencies in the isolated worktree from the lockfile after initial `vitest` command reported the local binary was missing.
- `pnpm exec vitest run src/tests/TenantListPage.test.tsx`: PASS, 2 tests passed.
- `pytest backend/tests/api/test_wholesaler.py`: PASS, 4 tests passed.
- `pnpm build`: PASS.
- `git diff --check`: PASS; Git printed CRLF working-copy warnings only.
- Changed-file ASCII scan: PASS after converting existing decorative Unicode in changed frontend files to ASCII.
- Changed-file mojibake scan: PASS.
- Changed-file sensitive-value scan: PASS with false-positive symbol-name hits only for existing `TokenPayload` / `token` parameters in auth-dependent backend route/test code; no secret values were printed or introduced.
- `pre-commit run --files backend/api/v1/wholesalers.py backend/tests/api/test_wholesaler.py frontend/src/pages/tenants/TenantFormModal.tsx frontend/src/pages/tenants/TenantListPage.tsx frontend/src/services/tenantService.ts frontend/src/tests/TenantListPage.test.tsx`: PASS, including Detect Secrets.

Build warnings observed but not introduced by S6-A:

- Browserslist data is 6 months old.
- Vite reports a main chunk larger than 500 kB after minification.

## Remaining Gap

True self-service onboarding remains future S6/P10 work. The following are still not complete and must not be represented as done:

- tenant schema bootstrap from the product UI/API;
- first admin user creation;
- RBAC setup for the first admin;
- secure password delivery or invitation flow;
- Gmail/social login;
- inventory, orders, and finance workspace initialization;
- transactional idempotency, failure rollback, and operational recovery for full provisioning.

Product still needs a decision on the future onboarding model: operator-run bootstrap, invite-based SaaS onboarding, or a fully automated provisioning workflow.
