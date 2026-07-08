# U6-I4 First Admin RBAC Creation Service

Date: 2026-07-08
Branch: `opencode/u6i4-first-admin-rbac-creation-2026-07-08`
Base: `origin/product-dev-recovered` at `01878eb22815d1f9aa8f19177d69ba088a87bd43`
Verdict: `PASS_FOR_CTO_REVIEW_PENDING_GITNEXUS`

## Scope

U6-I4 adds backend service logic to create or reconcile the first tenant-local owner/admin user and RBAC using the U6-I3 consume result.

Included:

- New `OwnerCredentialSetupService.create_first_admin_rbac(setup)` service method.
- Tenant schema validation and fail-closed checks for absent tenant auth tables.
- Owner user create/reconcile using the provided `password_hash` only.
- Admin role create/reconcile.
- Canonical admin permission registry mirrored from the current onboarding scripts.
- Idempotent user-role and role-permission mapping creation.
- Tests for idempotency, cross-tenant isolation, fail-closed behavior, and no public API side effects.

Excluded:

- No migration.
- No API endpoint.
- No frontend.
- No deploy/VPS.
- No `product-dev-recovered` push.
- No raw password storage or logging.
- No placeholder or generated credentials.
- No public wholesaler or tenant bootstrap behavior changes.

## RBAC Boundary Decisions

- U6-I4 does not import legacy onboarding scripts because they contain CLI credential handling and stale model field usage.
- The service mirrors the current complete admin permission list from `scripts/onboard_tenant.py` / `scripts/create_wholesaler.py` to avoid weakening existing RBAC permissions.
- The service uses schema-qualified raw SQL after `validate_identifier` because tenant schema is dynamic.
- Success writes only to the requested tenant schema auth tables: `users`, `roles`, `permissions`, `user_roles`, and `role_permissions`.
- Existing owner users are reconciled to the provided hash and reactivated, then assigned admin RBAC idempotently.

## RED/GREEN Evidence

- RED: `poetry run pytest tests/test_u6i4_first_admin_rbac_creation.py -q` failed because `OWNER_ADMIN_PERMISSION_REGISTRY` and `create_first_admin_rbac` did not exist.
- GREEN: after implementing first admin/RBAC creation, `poetry run pytest tests/test_u6i4_first_admin_rbac_creation.py -q` passed with `9 passed` using disposable Postgres container `opencode_u6i4_pg` on localhost port `55436`.

## Validation Results

Completed:

- `poetry run pytest tests/test_u6i4_first_admin_rbac_creation.py -q`: `9 passed`.
- `poetry run pytest tests/test_u6i3_owner_credential_setup_consume.py tests/test_u6i2_owner_credential_setup_token_issue.py -q`: `26 passed`.
- `git diff --check`: passed.
- ASCII scan on changed files: passed, no matches.
- Mojibake scan on changed files: passed, no matches.
- Secret-pattern scan on changed files: reviewed; matches were expected token/credential/password terminology and no actual secrets.
- `pre-commit run --files backend/services/owner_credential_service.py backend/tests/test_u6i4_first_admin_rbac_creation.py ai-ledger/product-ai/2026-07-08_u6i4_first_admin_rbac_creation.md`: passed.

Pending:

- GitNexus analyze/status.
