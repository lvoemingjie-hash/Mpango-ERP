# U6-F Signup / Verify / Status Closeout Gate

Date: 2026-07-07
Branch: `opencode/u6f-onboarding-auth-chain-closeout-2026-07-07`
Base: `origin/product-dev-recovered` at `c8e2c475 merge: U6-E onboarding status endpoint`
Verdict: `PASS_FOR_CTO_U6F_REVIEW_READY`

## Scope

U6-F adds a tests/evidence-only closeout gate for the backend-only onboarding auth chain from U6-C, U6-D, U6-E0, and U6-E.

Included:

- End-to-end signup -> onboarding status -> verify-email -> onboarding status closeout coverage.
- Duplicate normalized email neutrality checks.
- Idempotency retry and conflict checks.
- Query-string token transport rejection checks.
- Invalid, missing, expired, and reused token neutral-failure checks.
- No-provisioning side-effect checks.
- Route policy allowlist checks for signup, verify-email, and onboarding status.
- Alembic/model schema sanity checks for the U6-E0 token table chain.

Excluded:

- No production code changes.
- No migration.
- No frontend.
- No tenant provisioning, tenant schema creation, first admin/user creation, roles, RBAC, inventory, orders, finance workspace, or deploy/VPS changes.

## Security Evidence

- Public signup, verify-email, and onboarding-status responses do not expose raw token values, token hashes, owner email, tenant id/schema, wholesaler id, user id, role/RBAC details, or password hashes.
- Signup remains neutral with `registrationId: null` and no public status token return.
- Status lookup remains body/header only; query-string token input is rejected neutrally.
- Verify-email query-string token input is rejected neutrally.
- Duplicate signup and idempotency paths do not create extra live registration or active status-token rows.
- Token tables remain hash-only.

## Validation Results

Tests used a temporary throwaway Postgres container on `127.0.0.1:55435` with trust auth and a passwordless local test URL. No `.env` or runtime secret values were read or printed.

Completed:

- `poetry run pytest tests/test_u6f_onboarding_auth_chain_closeout.py -q`: `7 passed`.
- `poetry run pytest tests/test_u6e_onboarding_status_endpoint.py tests/test_u6d_verify_email_endpoint.py tests/test_u6c_signup_email_verification_skeleton.py -q`: `31 passed`.
- `poetry run pytest tests/test_auth_regressions.py tests/test_route_authorization_policy.py tests/test_u6b_tenant_onboarding_schema.py -q`: `47 passed`.
- `poetry run alembic heads`: `027_onboarding_status_tokens (head)`.
- `poetry run python -m py_compile tests/test_u6f_onboarding_auth_chain_closeout.py`: passed.
- `git diff --check`: passed.
- ASCII scan on changed files: passed.
- Mojibake scan on changed files: passed.
- Broad secret-pattern scan: matched only expected token/password/security field names, constants, and allowlisted synthetic test literals; no real secret values were present.
- Pre-commit on changed files: passed.
- `npx gitnexus analyze`: repository indexed successfully at commit `823b886`.
- `npx gitnexus status`: up to date at commit `823b886`.

Pending: none.

## Result

The U6-C/D/E0/E backend onboarding auth chain is internally consistent, neutral at public boundaries, and still does not provision tenants.
