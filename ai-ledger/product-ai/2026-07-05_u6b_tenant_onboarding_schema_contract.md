# U6-B Tenant Onboarding Schema Contract Gate

Date: 2026-07-05
Branch: `opencode/u6b-tenant-onboarding-schema-contract-2026-07-05`
Base: `origin/product-dev-recovered` at `1f77be4d merge: U6-A tenant onboarding email auth contract`
Verdict: `PASS_FOR_CTO_U6B_REVIEW`

## Scope

U6-B implements only the public database schema and ORM foundation for the U6-A/R1 tenant onboarding and email-auth contract.

Included:

- `public.tenant_registrations`
- `public.email_verification_tokens`
- `public.password_reset_tokens`
- ORM models and exports for those public tables.
- Schema contract tests for columns, states, constraints, indexes, token-hash-only storage, password-hash cleanup support, and absence of query-string status-token storage design.

Excluded:

- Runtime signup, verify-email, resend, forgot-password, reset-password, or onboarding-status routes.
- Email provider integration.
- Tenant provisioning service implementation.
- Frontend signup/verify/reset/setup pages.
- Deployment or runtime VPS changes.

## GitNexus Safety Gate

GitNexus impact checks were attempted before shared schema/model edits.

- `PublicBaseModel` resolved with HIGH impact: 89 impacted symbols and 4 affected processes.
- `PublicBaseModel` was not edited.
- File-path targets for `backend/models/__init__.py` and migration files were not resolvable by GitNexus in this index.
- Changes remained additive: new migration, new public model module, export update, and tests.

## Schema Decisions

`tenant_registrations` stores the registration lifecycle before tenant activation.

- Allowed states are constrained to `pending_email_verification`, `email_verified`, `provisioning`, `active`, `failed`, `cancelled`, and `expired`.
- `owner_email` is stored normalized and constrained to lowercase/trimmed form.
- `password_hash` is nullable to support the U6-A-R1 preferred cleanup path.
- `password_hash_cleared_at` and `password_hash_cleanup_reason` preserve cleanup auditability without retaining credential material.
- Terminal states `active`, `cancelled`, and `expired` require `password_hash IS NULL` and `password_hash_cleared_at IS NOT NULL`.
- Design B minimal is followed: `failed` means retryable/live failed state and continues to reserve `owner_email`.
- `failed` may retain `password_hash` only if `retry_allowed_until` is set.
- `failed` with `retry_allowed_until IS NULL` is valid only when `password_hash IS NULL` and `password_hash_cleared_at IS NOT NULL`.
- Abandoned failures must transition to `cancelled` or `expired` before `owner_email` can be reused.
- Live duplicate owner emails are prevented for `pending_email_verification`, `email_verified`, `provisioning`, `active`, and `failed`, while `cancelled` and `expired` can be restarted.
- Partial unique indexes reserve tenant code, tenant schema, wholesaler link, and idempotency key only when present.

`email_verification_tokens` stores only token hashes.

- `token_hash` is unique.
- One active unused/unrevoked verification token per registration is enforced with a partial unique index.
- `expires_at`, `used_at`, `revoked_at`, resend count, last sent timestamp, and request fingerprint fields are present.

`password_reset_tokens` uses a separate table for clearer constraints.

- `token_hash` is unique.
- `user_email_hash` is used instead of raw email.
- Optional `tenant_id`/`tenant_schema` support tenant selection after token validation.
- Active-token partial uniqueness is split for global pre-tenant reset and tenant-scoped reset cases.

No raw token columns were added. No status token query-string storage design was added.

## Validation Results

Completed:

- RED check: `pytest tests/test_u6b_tenant_onboarding_schema.py` failed before implementation with `ModuleNotFoundError: No module named 'models.tenant_onboarding'`.
- Targeted U6-B schema tests: `5 passed`.
- Focused backend gate with local DB/reporting/Redis env: `78 passed, 3 skipped, 5 xfailed`.

Focused gate command covered:

- `tests/test_u6b_tenant_onboarding_schema.py`
- `tests/test_alembic_migrations.py`
- `tests/test_s4g_migration_infrastructure_hardening.py`
- `tests/test_auth_regressions.py`
- `tests/test_route_authorization_policy.py`
- `tests/test_s6e_rbac_permission_registry_drift_gate.py`
- `tests/test_u1_bootstrap_permission_completeness.py`
- `tests/test_u1r1_bootstrap_completeness.py`

Environment note:

- The first focused run failed because DB env vars were unset and app settings pointed to container service hostnames from outside Docker.
- The rerun loaded local Docker Postgres credentials into process env without printing them, set `REPORTING_DATABASE_URL` to the same local test DB, and set `REDIS_URL=redis://127.0.0.1:6379/0`.

Tooling note:

- `python -m black ...` could not run because `black` is not installed in the active tool Python.
- `ruff check ...` could not run because `ruff` is not installed on PATH.
- Project pre-commit config does not include Black or Ruff hooks.

Final hygiene:

- `git diff --check`: passed with CRLF working-copy warnings only.
- ASCII scan on changed files: passed.
- Mojibake scan on changed files: passed.
- Secret-pattern scan: matched only documented environment-variable names in this ledger, the words `secret scan`, and allowlisted `password_reset` schema-purpose constants. No secret values were present.
- Pre-commit on changed files: passed.
- GitNexus analyze/status after commit: pending until commit exists.

## U6-B-R1 Tenant Onboarding Schema Contract Correction

CTO decision: Design B minimal.

Changes:

- Kept `failed` inside `LIVE_REGISTRATION_STATUSES`.
- Added no status and no terminal-failed flag.
- Tightened `ck_tenant_registrations_failed_password_hash_retry_bound` to require: `status <> 'failed' OR retry_allowed_until IS NOT NULL OR (password_hash IS NULL AND password_hash_cleared_at IS NOT NULL)`.
- Added schema tests proving retryable failed rows may retain the registration-level password hash, failed rows without retry cannot retain it, failed rows without retry must record cleanup time, failed remains in live owner-email uniqueness, and `cancelled`/`expired` remain excluded from live uniqueness.

R1 targeted validation:

- RED check: `poetry run pytest tests/test_u6b_tenant_onboarding_schema.py -q` failed before the constraint change with 4 failed tests against the old failed-state constraint.
- GREEN check: `poetry run pytest tests/test_u6b_tenant_onboarding_schema.py -q`: `11 passed`.

R1 final hygiene:

- `git diff --check`: passed with CRLF working-copy warnings only.
- ASCII scan on R1 changed files: passed.
- Mojibake scan on R1 changed files: passed.
- Secret-pattern scan: matched only documented environment-variable names in this ledger and allowlisted schema/test literals for `password_reset` and `password_hash`. No secret values were present.
- Pre-commit on R1 changed files: passed.
- GitNexus analyze/status after R1 commit: pending until commit exists.

## Result

U6-B is schema-only and follows Design B minimal for failed registration cleanup semantics.
