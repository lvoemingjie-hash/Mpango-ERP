# U6-D Verify Email Endpoint Skeleton

Date: 2026-07-07
Branch: `opencode/u6d-verify-email-endpoint-skeleton-2026-07-07`
Base: `origin/product-dev-recovered` at `b6062705 merge: U6-C signup email verification skeleton`
Verdict: `PASS_FOR_CTO_U6D_REVIEW_READY`

## Scope

U6-D implements only the backend public email verification endpoint skeleton on top of U6-C signup token creation.

Included:

- `POST /api/v1/auth/verify-email` as a public pre-auth endpoint.
- Body-only raw token input via `VerifyEmailRequest`.
- HMAC-SHA256 hashing of the submitted raw token using the U6-C token hash helper.
- Lookup by `public.email_verification_tokens.token_hash`.
- Atomic update of `tenant_registrations.status`, `tenant_registrations.email_verified_at`, and `email_verification_tokens.used_at` for valid pending registrations.
- Neutral success response with no registration, tenant, schema, token, hash, or DB details.
- Neutral failure response with `INVALID_OR_EXPIRED_VERIFICATION_TOKEN` for invalid, expired, reused, missing, query-only, or wrong-state tokens.
- Route policy allowlist update for the exact public verify-email endpoint.

Excluded:

- No GET `/verify-email?token=...` route.
- No query-string token support.
- No tenant provisioning.
- No first admin/user creation.
- No RBAC assignment.
- No tenant schema, inventory, orders, finance, or workspace creation.
- No frontend, provider integration, deploy, or VPS changes.
- No migration; existing U6-B tables were sufficient.

## Security Decisions

- Raw verification tokens are never logged, stored, or returned.
- Token hashes are never returned.
- The verify route accepts body input only; a query-string `token` with an empty body is treated as missing and returns the same neutral failure.
- Failure cases do not reveal whether an email, registration, tenant, or token exists.
- Reused tokens are rejected because `used_at IS NOT NULL` is non-actionable.
- Wrong registration state is rejected without changing the registration or token row.
- The service uses `execution_options(ignore_tenant=True)` for the public pre-tenant token/registration lookup because `tenant_registrations` rows are not tenant-scoped before provisioning.

## Validation Results

Tests used a temporary throwaway Postgres container on `127.0.0.1:55433` with an explicit non-secret test user/password. The container was removed after validation. No `.env` or existing runtime secrets were read or printed.

Completed:

- `poetry run pytest tests/test_u6d_verify_email_endpoint.py -q`: `8 passed`.
- `poetry run pytest tests/test_auth_regressions.py tests/test_route_authorization_policy.py tests/test_u6b_tenant_onboarding_schema.py -q`: `47 passed`.
- `poetry run python -m py_compile api/v1/auth.py services/onboarding_service.py schemas/auth_signup.py tests/test_u6d_verify_email_endpoint.py tests/test_route_authorization_policy.py`: passed.
- `git diff --check`: passed with CRLF working-copy warnings only.
- ASCII scan on changed files: passed.
- Mojibake scan on changed files: passed.
- Broad secret-pattern scan: matched only expected security/token/password field names and allowlisted synthetic test literals; no real secret values were present.
- Pre-commit on changed files: passed.
- `npx gitnexus analyze`: repository indexed successfully at commit `2a17613`.
- `npx gitnexus status`: up to date at commit `2a17613`.

Pending: none.

## Result

U6-D verifies email tokens and marks pending registrations as `email_verified` without provisioning tenants or leaking registration/user/tenant existence through public responses.
