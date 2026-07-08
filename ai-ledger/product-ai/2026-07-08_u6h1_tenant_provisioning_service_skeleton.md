# U6-H1 Tenant Provisioning Service Skeleton

Date: 2026-07-08
Branch: `opencode/u6h1-tenant-provisioning-service-skeleton-2026-07-08`
Base: `origin/product-dev-recovered` at `68c4a024 merge: U6-H0 tenant provisioning schema gap decision`
Verdict: `PASS_FOR_CTO_REVIEW_PENDING_COMMIT_AND_GITNEXUS`

## Scope

U6-H1 implements a backend-only tenant provisioning claim skeleton. It safely claims an `email_verified` tenant registration for later provisioning work, but does not create tenants.

Included:

- New `TenantProvisioningService` in `backend/services/tenant_provisioning_service.py`.
- `claim_registration_for_provisioning(registration_id)` claim operation.
- Row-level lock with SQLAlchemy `SELECT ... FOR UPDATE` via `.with_for_update()`.
- Tests for claim, blocked statuses, active idempotency, rollback behavior, public route non-provisioning boundary, and no side effects.

Excluded:

- No migration.
- No frontend.
- No API endpoint.
- No tenant schema creation.
- No `public.wholesalers` creation.
- No admin user, role, permission, user-role, or role-permission creation.
- No deploy/VPS changes.
- No `product-dev-recovered` push.

## Implementation Notes

- Only registrations with `status = 'email_verified'`, `wholesaler_id IS NULL`, `tenant_schema IS NULL`, and `provisioning_completed_at IS NULL` can be claimed.
- A successful claim sets `status = 'provisioning'` and `provisioning_started_at` in the caller's transaction.
- `pending_email_verification`, `expired`, `cancelled`, and non-retry `failed` registrations are blocked without mutation.
- Already `active` registrations with both `wholesaler_id` and `tenant_schema` return an idempotent existing result without mutation.
- The service does not import or call tenant bootstrap, Wholesaler creation, tenant users, roles, permissions, RBAC tables, or auth routes.
- The service does not log and does not handle raw tokens, raw passwords, password hashes, JWTs, or secret keys.

## Validation Results

Completed using disposable local Postgres container `opencode_u6h1_pg` on localhost port `55432`:

- Initial red test: `poetry run pytest tests/test_u6h1_tenant_provisioning_service_skeleton.py -q` failed because `services.tenant_provisioning_service` did not exist.
- `poetry run pytest tests/test_u6h1_tenant_provisioning_service_skeleton.py -q`: `10 passed`.
- `poetry run pytest tests/test_u6f_onboarding_auth_chain_closeout.py tests/test_u6e_onboarding_status_endpoint.py -q`: `20 passed, 36 warnings`.
- `poetry run python -m py_compile services/tenant_provisioning_service.py tests/test_u6h1_tenant_provisioning_service_skeleton.py`: passed.
- `git diff --check`: passed.
- ASCII scan on changed files: passed.
- Mojibake scan on changed files: passed.
- Secret-pattern scan on changed files: expected text-only matches for test fixture and leak-prevention terms; no actual secrets printed.
- `pre-commit run --files <changed-files>`: passed.

Pending:

- Commit.
- GitNexus analyze/status after commit.

## Result

U6-H1 is a safe claim-only backend skeleton. It proves the row-lock boundary and state transition for later U6-H provisioning slices while preserving the public signup, verify-email, and onboarding-status non-provisioning boundary.
