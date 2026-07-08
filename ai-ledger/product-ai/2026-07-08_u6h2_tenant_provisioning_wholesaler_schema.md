# U6-H2 Tenant Provisioning Wholesaler + Schema Bootstrap

Date: 2026-07-08
Branch: `opencode/u6h2-tenant-provisioning-wholesaler-schema-2026-07-08`
Base: `origin/product-dev-recovered` at `d275e1b0 merge: U6-H1 tenant provisioning service skeleton`
Verdict: `PASS_FOR_CTO_MERGE_REVIEW`
Implementation commit: `0402ba97 feat(U6-H2): provision wholesaler and tenant schema`
R1 fix commit: `ea1da996 fix(U6-H2): sanitize provisioning failure messages`

## CTO Decision

Pre-edit GitNexus impact analysis found `Wholesaler` as `HIGH` risk because it is used by API, CRUD, repository, platform tenant, scripts, and test paths. CTO accepted this only as read/write data-use risk. U6-H2 therefore does not edit the Wholesaler model, API, CRUD, repository, or platform tenant APIs.

Pre-edit impact results:

- `TenantProvisioningService`: `LOW`, `0` impacted.
- `TenantRegistration`: `LOW`, `8` impacted.
- `Wholesaler`: `HIGH`, `39` impacted, accepted by CTO as data-use only.
- `bootstrap_tenant_schema.bootstrap`: exact GitNexus target was not found, so source was inspected directly and called as-is.

## Scope

U6-H2 extends `TenantProvisioningService` from claim-only to the first real provisioning side effect: create the public wholesaler row, derive/store tenant schema, call the canonical tenant schema bootstrap, then mark provisioning complete and active only after bootstrap succeeds.

Included:

- `provision_wholesaler_and_schema(registration_id)`.
- `SELECT ... FOR UPDATE` row lock on `public.tenant_registrations`.
- Existing `Wholesaler` model used as-is for `public.wholesalers` inserts/updates.
- Canonical `scripts.bootstrap_tenant_schema.bootstrap` called as imported function without editing it.
- Idempotent active-existing result when `wholesaler_id`, `tenant_schema`, and a bootstrapped schema already exist.
- Fail-closed bootstrap failure path that rolls back uncommitted wholesaler/registration side effects, does not mark active/completed, and records concise failure fields.
- Registration credential hash cleanup required by the existing terminal-state constraint when marking `active`; no credential is created, delivered, or logged.

Excluded:

- No migration.
- No frontend.
- No public API endpoint.
- No admin user creation.
- No role, permission, user-role, or role-permission row seeding.
- No password delivery.
- No deploy/VPS changes.
- No `product-dev-recovered` push.

## Bootstrap Prerequisite

`bootstrap_tenant_schema.bootstrap` requires the migration-created database role `reporting_role`. The U6-H2 tests create that role in the disposable test database to mirror the migrated production/test database prerequisite. No bootstrap code was edited.

## R1 Failure Message Sanitization

Finding: U6-H2 initially persisted `str(exc)` into `TenantRegistration.failure_message` on bootstrap failure. That risk could store DSNs, embedded credentials, tokens, or other sensitive connection details if a lower-level exception included them.

Fix: `failure_message` now stores only an allowlisted generic message in the form `<ExceptionClass>: bootstrap failed`, while preserving `failure_code = BOOTSTRAP_FAILED`. A regression test raises a fake DSN with a fake password and asserts neither the DSN, password, token text, nor connection string scheme is persisted.

Residual P2 risk: `bootstrap_tenant_schema.bootstrap` commits independently inside its own engine/session. If bootstrap fails after creating or reconciling part of a tenant schema, the service rollback prevents active/completed registration state and public wholesaler linkage from being persisted, but it cannot transactionally undo already-committed schema DDL/reconcile work from bootstrap. Cleanup/reconcile of partial tenant schemas belongs to U6-H3.

Confirmed unchanged in R1:

- `backend/models/wholesaler.py` not edited.
- `backend/api/v1/wholesalers.py` not edited.
- `backend/crud/wholesaler.py` not edited.
- `backend/repositories/wholesaler_repository.py` not edited.
- Platform tenant APIs not edited.
- `backend/scripts/bootstrap_tenant_schema.py` not edited.

## Validation Results

Completed using disposable local Postgres container `opencode_u6h2_pg` on localhost port `55433`:

- `poetry run pytest tests/test_u6h2_tenant_provisioning_wholesaler_schema.py -q`: `13 passed`.
- `poetry run pytest tests/test_u6h1_tenant_provisioning_service_skeleton.py tests/test_u6f_onboarding_auth_chain_closeout.py -q`: `17 passed, 17 warnings`.
- `poetry run python -m py_compile services/tenant_provisioning_service.py tests/test_u6h2_tenant_provisioning_wholesaler_schema.py`: passed.
- `git diff --check`: passed.
- ASCII scan on changed files: passed.
- Mojibake scan on changed files: passed.
- Secret-pattern scan on changed files: expected text-only matches for credential-cleanup/test/ledger terms; no actual secrets printed.
- `pre-commit run --files <changed-files>`: passed.
- Commit: `0402ba97 feat(U6-H2): provision wholesaler and tenant schema`.
- `npx gitnexus analyze`: repository indexed successfully, `6,760 nodes | 19,196 edges | 448 clusters | 229 flows`.
- `npx gitnexus status`: indexed commit `0402ba9`, current commit `0402ba9`, status up-to-date.

R1 validation completed using disposable local Postgres container `opencode_u6h2_r1_pg` on localhost port `55433`:

- `poetry run pytest tests/test_u6h2_tenant_provisioning_wholesaler_schema.py -q`: `14 passed`.
- `poetry run pytest tests/test_u6h1_tenant_provisioning_service_skeleton.py tests/test_u6f_onboarding_auth_chain_closeout.py -q`: `17 passed, 17 warnings`.

Completed R1 hygiene:

- `poetry run python -m py_compile services/tenant_provisioning_service.py tests/test_u6h2_tenant_provisioning_wholesaler_schema.py`: passed.
- `git diff --check`: passed.
- ASCII scan on changed files: passed.
- Mojibake scan on changed files: passed.
- Secret-pattern scan on changed files: expected fake-secret regression test values and credential-cleanup/ledger terms only; no real secrets printed.
- `pre-commit run --files <changed-files>`: passed.
- Commit: `ea1da996 fix(U6-H2): sanitize provisioning failure messages`.
- `npx gitnexus analyze`: repository indexed successfully, `6,763 nodes | 19,204 edges | 448 clusters | 229 flows`.
- `npx gitnexus status`: indexed commit `ea1da99`, current commit `ea1da99`, status up-to-date.

## Result

U6-H2 provisions the public wholesaler and canonical tenant schema only for registrations already in `provisioning`. It remains backend-only and does not create admin users, RBAC rows, credentials, public endpoints, frontend behavior, migrations, or deploy changes.
