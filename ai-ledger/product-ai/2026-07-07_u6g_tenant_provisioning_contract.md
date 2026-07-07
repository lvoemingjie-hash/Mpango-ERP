# U6-G Tenant Provisioning Contract

Date: 2026-07-07
Branch: `opencode/u6g-tenant-provisioning-contract-2026-07-07`
Base: `origin/product-dev-recovered` at `7b2e0b7f merge: U6-F onboarding auth chain closeout`
Verdict: `PASS_FOR_CTO_U6G_REVIEW`
Implementation commit: `f7802118 docs(U6-G): define tenant provisioning contract`

## Scope

U6-G is a contract-first design gate for the future boundary that converts an `email_verified` public registration into a real tenant workspace.

Included:

- Durable contract: `docs/contracts/tenant_onboarding_provisioning_contract.md`.
- Static contract tests: `backend/tests/test_u6g_tenant_provisioning_contract.py`.
- Audit of current schema fields and gaps.
- Audit that public signup, verify-email, and onboarding-status service code does not provision tenants.
- Saga, rollback, idempotency, security, future test plan, and U6-H implementation-slice definitions.

Excluded:

- No production code changes.
- No migration.
- No frontend.
- No deploy/VPS changes.
- No tenant schema, users, roles, RBAC, inventory, orders, finance workspace, or admin account creation.

## Audit Findings

- Public signup/verify/status code does not create wholesalers, tenant schemas, tenant users, roles, permissions, user_roles, or role_permissions.
- Current registration schema has `provisioning_started_at`, `provisioning_completed_at`, `failed_at`, `failure_code`, `failure_message`, `retry_allowed_until`, `wholesaler_id`, and `tenant_schema`.
- Current registration schema does not have exact `provisioned_at`, `provisioning_attempt_count`, `provisioning_last_error`, provisioning lock/version, admin user linkage, or a provisioning event table.
- Current registration schema already has partial unique indexes for non-null `tenant_schema` and `wholesaler_id`.
- Safe MVP provisioning is not impossible with current schema because row locks/advisory locks, deterministic schema names, and existing unique indexes can support a saga. U6-H0 remains recommended before broad production rollout for better attempt/error/stale-worker tracking.

## Validation Results

Completed:

- `poetry run pytest tests/test_u6g_tenant_provisioning_contract.py -q`: `7 passed`.
- `poetry run python -m py_compile tests/test_u6g_tenant_provisioning_contract.py`: passed.
- `git diff --check`: passed.
- ASCII scan on changed files: passed.
- Mojibake scan on changed files: passed.
- Secret-pattern scan on changed files: expected text-only matches for contract/test references to password hashes, tokens, JWTs, and leak-prevention requirements; no actual secrets printed.
- `pre-commit run --files <changed-files>`: passed.
- Commit: `f7802118 docs(U6-G): define tenant provisioning contract`.
- `npx gitnexus analyze`: repository indexed successfully, `6,658 nodes | 18,924 edges | 442 clusters | 229 flows`.
- `npx gitnexus status`: indexed commit `f780211`, current commit `f780211`, status up-to-date.

## Result

U6-G defines the future provisioning boundary without implementing provisioning. The contract requires that public onboarding auth endpoints remain non-provisioning and that U6-H implementation prove saga rollback, idempotency, concurrency safety, credential cleanup, and first-admin RBAC completeness.
