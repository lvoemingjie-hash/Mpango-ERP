# U6-E Onboarding Status Endpoint

Date: 2026-07-07
Branch: `opencode/u6e-onboarding-status-endpoint-2026-07-07`
Base: `origin/product-dev-recovered` at `73fa8ec9 merge: U6-E0 onboarding status token schema`
Verdict: `PASS_FOR_CTO_U6E_REVIEW_READY`

## Scope

U6-E implements the backend-only public onboarding status endpoint using the U6-E0 `public.onboarding_status_tokens` table.

Included:

- `POST /api/v1/auth/onboarding/status` as a public pre-auth endpoint.
- Body token input via `statusToken`.
- Optional `X-Onboarding-Status-Token` header input.
- Neutral failure when body and header tokens are both present and differ.
- HMAC-SHA256 hashing of the submitted opaque token with the existing token hash helper.
- Lookup by `public.onboarding_status_tokens.token_hash` only.
- Signup creation of one active hash-only onboarding status token row for new registrations.
- Coarse public status response with only `pending_email_verification`, `email_verified`, `expired`, `cancelled`, `failed`, or `active`.
- Exact route policy allowlist update for `/api/v1/auth/onboarding/status`.

Excluded:

- No GET onboarding status endpoint.
- No query-string status token support.
- No raw status token return path.
- No tenant provisioning.
- No first admin/user creation.
- No RBAC assignment.
- No tenant schema, inventory, orders, finance, workspace, or admin account creation.
- No frontend, deploy, VPS, or migration changes.

## Security Decisions

- Raw onboarding status tokens are never stored, logged, or returned.
- Status lookup does not accept email address or registration id as public input.
- Failure cases use only `INVALID_OR_EXPIRED_ONBOARDING_STATUS_TOKEN` and do not reveal whether an email, registration, tenant, or token exists.
- Expired, revoked, soft-deleted, missing, and unknown status tokens all fail neutrally.
- Public success responses do not include registration id, owner email, tenant id, tenant schema, wholesaler id, user id, role/RBAC details, raw token, token hash, password hash, or DB row details.
- The same opaque signup token is used to seed both the email verification token hash and onboarding status token hash so the existing non-production verification sink can support tests without adding a new sink field or returning a token publicly.

## Validation Results

Tests used a temporary throwaway Postgres container on `127.0.0.1:55434` with trust auth and a passwordless local test URL. No `.env` or runtime secret values were read or printed.

Completed:

- RED check: initial U6-E test run failed before implementation; after implementation one expiry-helper assertion failed because the test violated the U6-E0 `expires_at > created_at` check. The helper was corrected to preserve that constraint.
- `poetry run pytest tests/test_u6e_onboarding_status_endpoint.py -q`: `13 passed`.
- `poetry run pytest tests/test_u6d_verify_email_endpoint.py tests/test_u6c_signup_email_verification_skeleton.py -q`: `18 passed`.
- `poetry run pytest tests/test_auth_regressions.py tests/test_route_authorization_policy.py tests/test_u6b_tenant_onboarding_schema.py -q`: `47 passed`.
- `poetry run alembic heads`: `027_onboarding_status_tokens (head)`.
- `poetry run python -m py_compile api/v1/auth.py services/onboarding_service.py schemas/auth_signup.py tests/test_u6e_onboarding_status_endpoint.py tests/test_u6c_signup_email_verification_skeleton.py tests/test_route_authorization_policy.py`: passed.
- `git diff --check`: passed with CRLF working-copy warnings only.
- ASCII scan on changed files: passed.
- Mojibake scan on changed files: passed.
- Broad secret-pattern scan: matched only expected token/password/security field names, constants, and allowlisted synthetic test literals; no real secret values were present.
- Pre-commit on changed files: passed.
- `npx gitnexus analyze`: repository indexed successfully at commit `77b923a`.
- `npx gitnexus status`: up to date at commit `77b923a`.

Pending: none.

## Result

U6-E enables safe coarse onboarding status checks using hash-only status tokens while preserving public signup neutrality and avoiding tenant provisioning.
