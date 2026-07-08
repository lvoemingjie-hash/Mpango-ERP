# U6-I5 Owner Credential Setup Public Endpoint

Date: 2026-07-08
Branch: `opencode/u6i5-owner-credential-setup-endpoint-2026-07-08`
Base: `origin/product-dev-recovered` at `2a5a31479faf8cf64e87cb5ba0fc4a7092f6d3f5`
Verdict: `PASS_FOR_CTO_REVIEW`

## Scope

U6-I5 adds the public backend endpoint that allows a tenant owner to submit a one-time setup token and password, triggering owner/admin RBAC creation using U6-I3 and U6-I4 services atomically.

Included:

- New `POST /api/v1/auth/onboarding/setup-credential` public endpoint.
- New `OwnerCredentialSetupRequest` and `OwnerCredentialSetupResponse` schemas in `backend/schemas/auth_signup.py`.
- Endpoint consumes setup token, creates/reconciles first admin RBAC, commits atomically.
- Idempotent retry recovery: if the setup token is already consumed but admin already exists, the endpoint returns success without re-consuming the token.
- Neutral 401 error for invalid, expired, revoked, used, deleted, or wrong-purpose tokens (when admin does not already exist).
- Admin creation failure rolls back the token consumption.
- Response never exposes raw token, token_hash, password_hash, tenant_schema, user_id, role_id, or permission IDs.
- GET and query-string token paths are rejected with 405.
- Public route policy allowlist updated in `test_route_authorization_policy.py` and `test_u6f_onboarding_auth_chain_closeout.py`.

Excluded:

- No migration.
- No frontend.
- No deploy/VPS.
- No `product-dev-recovered` push.
- No raw token/password logging.
- No query-string token support.
- No placeholder/random credentials.
- No weakening RBAC.
- No changes to `TenantProvisioningService`.

## Endpoint Boundary Decisions

- Token consumption and admin creation happen within the same DB transaction for atomicity.
- If `OwnerCredentialSetupAdminCreationError` is raised, the endpoint rolls back so the token is not consumed.
- On `OwnerCredentialSetupTokenInvalidError`, the endpoint checks whether the setup token was already consumed and whether the admin already exists in the tenant schema. If both conditions hold, the endpoint returns success (idempotent retry). Otherwise, it returns a neutral 401.
- The idempotent recovery uses `hash_token()` from `onboarding_service` to look up the consumed `OwnerCredentialSetupToken` row, resolves the registration, and validates that `tenant_schema` and admin user/role mappings exist before succeeding.
- The recovery never creates a new admin or revives an unused token.

## RED/GREEN Evidence

- RED: `poetry run pytest tests/test_u6i5_owner_credential_setup_endpoint.py -q` failed with 404 because the endpoint did not exist.
- GREEN: after adding schema, endpoint, and public allowlist entries, `poetry run pytest tests/test_u6i5_owner_credential_setup_endpoint.py -q` passed with `9 passed` using disposable Postgres container `opencode_u6i5_pg` on localhost port `55436`.

## Validation Results

Completed:

- `poetry run pytest tests/test_u6i5_owner_credential_setup_endpoint.py -q`: `9 passed`.
- `poetry run pytest tests/test_route_authorization_policy.py tests/test_u6i4_first_admin_rbac_creation.py tests/test_u6i3_owner_credential_setup_consume.py -q`: `55 passed`.
- `git diff --check`: passed.
- ASCII scan on changed files: passed, no matches.
- Mojibake scan on changed files: passed, no matches.
- Secret-pattern scan on changed files: reviewed; matches were expected token/credential/password terminology and no actual secrets.
- `pre-commit run` on all changed files: passed.
- Implementation commit: `3fe87503 feat(U6-I5): add owner credential setup public endpoint`.
- `npx gitnexus analyze`: repository indexed successfully, `7,042 nodes | 20,126 edges | 473 clusters | 239 flows`.
- `npx gitnexus status`: indexed commit `3fe8750`, current commit `3fe8750`, status up to date.

## R1 Replay Safety Fix

- Finding: the endpoint's used-token recovery path called `create_first_admin_rbac` with a fresh `hash_password(request.password)`, meaning a consumed setup token could be replayed to change the owner's password_hash.
- Fix 1: removed `_recover_if_already_setup` and `_admin_already_exists` helpers entirely. Used/consumed tokens now return neutral 401.
- Fix 2: added `test_replay_with_different_password_does_not_change_password_hash` regression test verifying that a second POST with a different password does not alter the stored `password_hash`.
- Fix 3: added query-param rejection at the top of the endpoint handler. POST requests with `setup_token` or `password` query parameters return neutral 401 before processing the body.
- Fix 4: removed `registration_id` from `OwnerCredentialSetupResponseData`; public response now contains only `success`, `data` (empty), `message`, and `timestamp`.

### R1 Validation

- `poetry run pytest tests/test_u6i5_owner_credential_setup_endpoint.py -q`: `10 passed`.
- `poetry run pytest tests/test_route_authorization_policy.py tests/test_u6i4_first_admin_rbac_creation.py tests/test_u6i3_owner_credential_setup_consume.py -q`: `55 passed`.
- `git diff --check`: passed.
- ASCII/mojibake scans: clean.
- Secret-pattern scan: reviewed, false positives only.
- `pre-commit run`: passed.
- `npx gitnexus analyze`: passed.
- `npx gitnexus status`: up to date.
