# U6-H2 Tenant Provisioning Wholesaler + Schema Bootstrap

Date: 2026-07-08
Branch: `opencode/u6h2-tenant-provisioning-wholesaler-schema-2026-07-08`
Base: `origin/product-dev-recovered` at `d275e1b0 merge: U6-H1 tenant provisioning service skeleton`
Verdict: `PASS_FOR_CTO_REVIEW_PENDING_COMMIT_AND_GITNEXUS`

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

Pending:

- Commit.
- GitNexus analyze/status after commit.

## Result

U6-H2 provisions the public wholesaler and canonical tenant schema only for registrations already in `provisioning`. It remains backend-only and does not create admin users, RBAC rows, credentials, public endpoints, frontend behavior, migrations, or deploy changes.
