# Tenant Onboarding Provisioning Contract

Status: Proposed for U6-H implementation
Date: 2026-07-07
Scope: Contract only. No runtime provisioning is implemented by this document.

## 1. Preconditions

Provisioning is the boundary that converts a verified public registration into a real tenant workspace. It MUST NOT be triggered by public signup, public verify-email, or public onboarding-status routes.

Required registration preconditions:

- `tenant_registrations.status` MUST be exactly `email_verified` before a new provisioning attempt can begin.
- `tenant_registrations.wholesaler_id` MUST be `NULL`.
- `tenant_registrations.tenant_schema` MUST be `NULL`.
- Current schema has `provisioning_completed_at`, not `provisioned_at`; this field MUST be `NULL` before first activation. If U6-H requires the exact name `provisioned_at`, U6-H0 MUST add it before implementation.
- The registration MUST NOT be `pending_email_verification`, `provisioning`, `active`, `failed`, `cancelled`, or `expired` when starting a new first attempt.
- The registration `expires_at` MUST be greater than the provisioning start time.
- The normalized owner email MUST pass the existing lowercase/trim/no-space constraint and application email validation.
- `company_name` MUST be present and non-empty after trimming.
- `country` MUST be a valid two-letter uppercase country code already accepted by signup validation.
- `password_hash` MUST be present before creating the first tenant admin user, unless a future credential-reset-only activation flow explicitly replaces this requirement.
- Email verification tokens and onboarding status tokens MUST NOT be accepted as authorization for provisioning.
- Provisioning MUST be triggered only by a controlled backend process, queue worker, or future explicit authenticated endpoint with idempotency and authorization. A public pre-auth endpoint MUST NOT trigger provisioning.

Provisioning claim preconditions:

- The worker MUST acquire a per-registration lock before any side effect. Acceptable current options are `SELECT ... FOR UPDATE` on the registration row inside a public DB transaction or a transaction-scoped PostgreSQL advisory lock keyed by registration id.
- The worker MUST re-read the registration after acquiring the lock.
- If the row is already `active` and has both `wholesaler_id` and `tenant_schema`, the request is idempotent and returns the existing result without creating anything new.
- If the row is `provisioning`, the worker MUST treat the row as already claimed unless the retry policy proves that the prior attempt is stale and safe to resume.

## 2. Provisioning Outputs

The successful provisioning result MUST create exactly one tenant workspace for one registration.

Required public output:

- One `public.wholesalers` registry row.
- `wholesalers.code` generated deterministically from registration data or a reserved tenant code and constrained by existing uniqueness.
- `wholesalers.name` copied from `tenant_registrations.company_name` after validation.
- `wholesalers.status = 'active'` at completion.
- `wholesalers.provisioned_at` set when the tenant schema and first admin are complete.

Required tenant output:

- One tenant schema derived from the wholesaler id using the canonical `Wholesaler.get_tenant_schema()` format: `t_<uuid_without_dashes>`.
- Tenant schema created and reconciled through the canonical `backend/scripts/bootstrap_tenant_schema.py` bootstrap path or a production service wrapper that calls the same DDL/reconciliation logic.
- Tenant tables from the canonical bootstrap, including users, roles, permissions, user_roles, role_permissions, inventory, orders, payments/ledger, reporting, import, and intake tables.
- One first admin user in the tenant schema using the registration owner email.
- The admin user's password hash moved from `tenant_registrations.password_hash`; raw password MUST NOT be needed or logged.
- One `admin` role assigned to the admin user.
- Full MVP admin permissions assigned to the admin role. At minimum this MUST include every permission enforced by route policy plus `system:admin` and `metrics:admin` if those are required for internal/admin operations.
- Optional default workspace metadata only if it is already modeled in the canonical bootstrap or existing tenant tables. U6-H MUST NOT invent a new workspace table without a schema slice.

Required registration update:

- `tenant_registrations.status = 'active'`.
- `tenant_registrations.wholesaler_id` set to the created public wholesaler id.
- `tenant_registrations.tenant_schema` set to the created tenant schema name.
- Current schema equivalent of `provisioned_at` is `tenant_registrations.provisioning_completed_at`; set it at completion.
- `tenant_registrations.password_hash = NULL`.
- `tenant_registrations.password_hash_cleared_at` set at completion.
- `tenant_registrations.password_hash_cleanup_reason = 'provisioned'`. <!-- pragma: allowlist secret -->
- If U6-H0 adds `provisioning_attempt_count`, increment it for each claimed attempt.
- If U6-H0 adds `provisioning_last_error`, store sanitized failure codes/details there only after failures. Current schema has `failure_code`, `failure_message`, `failed_at`, and `retry_allowed_until`.

## 3. Transaction And Rollback Boundary

Provisioning SHOULD be a multi-step saga with fail-closed compensation rather than one monolithic transaction. The reason is that tenant schema DDL/bootstrap, public registry updates, admin creation, and RBAC seeding are high-impact operations that may need safe retries and reconciliation. PostgreSQL DDL can be transactional, but the existing canonical bootstrap path owns its connection/commit boundary; the contract must tolerate partial side effects.

Saga phases:

- Phase 1: claim registration. In a public transaction, lock the registration row, verify preconditions, set `status = 'provisioning'`, set `provisioning_started_at`, and commit. If the claim fails, do not create any side effects.
- Phase 2: create or find public wholesaler. This step MUST be idempotent by registration id or deterministic tenant code. If a matching wholesaler already exists for this registration retry, reuse it. If an unrelated conflicting wholesaler exists, fail closed.
- Phase 3: create or reconcile tenant schema through canonical bootstrap. `CREATE SCHEMA IF NOT EXISTS` and table reconciliation are acceptable only for the exact expected schema name.
- Phase 4: create or find first admin user by owner email in that tenant schema.
- Phase 5: create or find admin role, create or find permissions, assign all permissions, and assign admin role to user.
- Phase 6: finalize public registration and wholesaler. Set active fields and clear registration password hash in one public transaction.

Fail-closed behavior:

- Wholesaler created but schema bootstrap fails: registration remains or transitions to `failed` with sanitized `failure_code`; password hash may remain only if `retry_allowed_until` is set, matching the U6-B failed-state cleanup constraint. Retry MUST reuse the same wholesaler or compensate by marking it non-active if a future status field supports that.
- Schema created but admin user fails: registration MUST NOT become `active`; retry MUST re-run canonical bootstrap/reconciliation and then create/find admin user. Do not drop schema automatically because schema bootstrap may have created durable objects; destructive compensation requires a separate explicit cleanup workflow.
- Admin user created but RBAC assignment fails: registration MUST NOT become `active`; retry MUST find the existing admin user and complete role/permission assignment idempotently.
- Registration final update fails: public wholesaler and tenant schema may exist, but registration MUST NOT be considered active until the final public transaction succeeds. Retry MUST find the existing tenant artifacts and complete the final update.
- Duplicate retry after partial failure: retry MUST use the same registration id, lock the same registration row, find existing artifacts by deterministic tenant schema/wholesaler linkage, and complete missing steps without creating duplicates.

Failure reporting:

- Public status endpoint may continue to expose only coarse `failed` once status is set to failed.
- Internal logs may include sanitized failure codes but MUST NOT include raw passwords, raw tokens, password hashes, token hashes, full DB URLs, or JWTs.

## 4. Idempotency

The primary idempotency key SHOULD be `tenant_registrations.id`. Future explicit endpoint requests MAY also accept an operation idempotency key, but it MUST be scoped to the registration id and caller authorization.

Required idempotency behavior:

- Repeated provisioning for an already-active registration returns the same `wholesaler_id` and `tenant_schema` and creates no duplicate schema, user, role, permissions, or wholesaler.
- Failed partial attempts are retryable if the registration is still eligible or marked failed with `retry_allowed_until` in the future.
- Concurrent provisioning requests MUST NOT create duplicate tenant schemas or admin users. The implementation MUST use row locks/advisory locks plus existing unique indexes on `tenant_schema` and `wholesaler_id`.
- Tenant schema name MUST be deterministic from `wholesaler_id`; once chosen, all retries MUST use the same schema name.
- First admin user creation MUST be idempotent by normalized owner email inside the tenant schema.
- Admin role creation MUST be idempotent by role name `admin`.
- Permission creation MUST be idempotent by permission code.
- Role and user assignment inserts MUST use conflict-safe semantics or pre-checks.

## 5. Security And Public Boundaries

- `POST /api/v1/auth/signup` MUST NOT provision tenants.
- `POST /api/v1/auth/verify-email` MUST NOT provision tenants.
- `POST /api/v1/auth/onboarding/status` MUST NOT provision tenants.
- Email verification tokens and onboarding status tokens are status/verification artifacts only. They are never provisioning authorization.
- Provisioning MUST run as a backend-controlled operation or future authenticated endpoint.
- If exposed as a future endpoint, it MUST require platform-level authorization. Recommended requirement: identity-only super admin via the existing platform-admin gate and/or explicit `system:admin` equivalent for platform operations. Tenant-context JWTs MUST NOT be sufficient to create a new tenant.
- Raw passwords MUST never be logged. U6-H should not need raw passwords because signup stores a password hash.
- The registration password hash MUST be moved/copied into the first tenant admin user carefully, then cleared from the registration according to the U6-A/U6-B credential cleanup contract.
- Public responses MUST NOT leak raw tokens, token hashes, password hashes, DB errors, tenant schema names before active finalization, internal retry state, stack traces, or secrets.
- Internal provisioning result objects may include `registration_id`, `wholesaler_id`, and `tenant_schema` only inside authenticated/authorized backend contexts.

## 6. Schema Gaps

Current schema audit:

- `tenant_registrations.provisioned_at`: missing. Current equivalent is `provisioning_completed_at`. If product/API language requires exact `provisioned_at`, U6-H0 must add it or explicitly adopt `provisioning_completed_at` as canonical.
- `tenant_registrations.provisioning_attempt_count`: missing. U6-H can infer from logs, but robust user/support visibility needs U6-H0 schema.
- `tenant_registrations.provisioning_last_error`: missing by that exact name. Current fields are `failure_code`, `failure_message`, `failed_at`, and `retry_allowed_until`.
- `tenant_registrations.provisioning_lock` or `version`: missing. Safe implementation can use row-level locks or advisory locks without schema changes, but a version column would improve stale-worker detection.
- `tenant_registrations.tenant_schema` uniqueness: present via partial unique index `ux_tenant_registrations_tenant_schema` where non-null.
- `tenant_registrations.wholesaler_id` uniqueness: present via partial unique index `ux_tenant_registrations_wholesaler_id` where non-null.
- Admin user linkage from registration: missing. U6-H can derive the first admin by owner email in the tenant schema, but durable audit linkage would need a schema field if required.
- Public `wholesalers` has `provisioned_at`, but `tenant_registrations` does not.
- There is no durable provisioning event table. U6-H can proceed with existing fields for MVP, but U6-H0 should consider an event/audit table if operations need detailed retry history.

Safe provisioning is not impossible with the current schema because row locks/advisory locks, unique tenant schema/wholesaler indexes, and existing failure fields can support an MVP saga. However, U6-H0 is recommended before broad production rollout to add attempt count, stale-worker/versioning, and explicit error/audit fields.

## 7. Future U6-H Test Plan

U6-H implementation MUST include tests for:

- Happy path creates public wholesaler, tenant schema, first admin user, admin role, full MVP admin permissions, and marks registration active.
- Registration that is not `email_verified` is blocked without side effects.
- Expired, cancelled, failed without retry window, and already-active states behave according to this contract.
- Duplicate provisioning for an already-active registration is idempotent and returns the same result.
- Same registration retried after partial failure completes missing steps without duplicates.
- Concurrent provisioning requests cannot create duplicate wholesaler, schema, admin user, admin role, or permissions.
- Fail-closed behavior when wholesaler creation succeeds but schema bootstrap fails.
- Fail-closed behavior when schema bootstrap succeeds but admin user creation fails.
- Fail-closed behavior when admin user creation succeeds but RBAC assignment fails.
- Fail-closed behavior when final registration update fails.
- Public signup, verify-email, and onboarding-status endpoints remain no-provisioning gates.
- No raw password, token, token hash, password hash, JWT, or DB credential leakage in responses or logs.
- Canonical bootstrap schema completeness on a fresh DB.
- RBAC completeness for first admin, including every permission enforced by route policy.
- Runtime smoke on a fresh DB using the same migration/bootstrap path as production.

## 8. Recommended Implementation Plan

- U6-H0 schema gaps: decide whether to add `provisioned_at` or standardize on `provisioning_completed_at`; add attempt count, last sanitized error, stale-worker/version field, and optional admin linkage/audit table if required.
- U6-H1 provisioning service skeleton: create a backend-only service with row/advisory locking, precondition checks, idempotency lookup, and no public route behavior changes.
- U6-H2 happy path: create/find wholesaler, run canonical bootstrap, create first admin user, seed admin RBAC, mark registration active, clear registration password hash.
- U6-H3 idempotency/concurrency: add retry/resume behavior, conflict-safe inserts, concurrent worker tests, stale provisioning handling, and sanitized failure states.
- U6-H4 runtime proof/deploy gate: run a fresh-DB provisioning smoke test, verify tenant isolation, verify first-admin login/select-tenant, verify route policy permissions, and document rollback/cleanup operations.
