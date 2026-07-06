# U6-C Signup Email Verification Skeleton Gate

Date: 2026-07-06
Branch: `opencode/u6c-signup-email-verification-skeleton-2026-07-06`
Base: `origin/product-dev-recovered` at `4b0f8d74 merge: U6-B tenant onboarding schema contract`
Verdict: `PASS_FOR_CTO_U6C_REVIEW`

## Scope

U6-C implements the backend-only public signup and email verification token skeleton on top of the U6-A/U6-B contract.

Included:

- `POST /api/v1/auth/signup` returning `202 Accepted` with a neutral response.
- Signup request/response schemas.
- Pending `public.tenant_registrations` row creation.
- One active `public.email_verification_tokens` row per new registration.
- HMAC-SHA256 token hashing using existing `settings.SECRET_KEY` material.
- Non-production in-memory verification delivery sink for tests/dev inspection.
- Idempotency-key hashing and request fingerprint checks.
- Duplicate live normalized-email handling with neutral success.
- Route authorization policy update for the intentionally public signup route.

Excluded:

- Verify-email endpoint.
- Tenant provisioning.
- First admin creation.
- Login/select-tenant behavior changes.
- Real email provider integration.
- Frontend or deployment changes.
- Onboarding status query-string token route or contract.

## GitNexus Safety Gate

GitNexus impact checks were run before editing auth/router/settings/security/shared-model areas.

- `get_settings`: CRITICAL, 70 impacted symbols and 10 affected processes. `backend/core/config.py` was not edited.
- `auth.py` resolved by GitNexus to `backend/schemas/auth.py`: LOW.
- `select_tenant`: LOW.
- `create_access_token`: LOW.
- `core.security`: target not found.
- `models.__init__`: target not found.
- `backend/api/v1/auth.py` by path: symbol not found.

Changes remained additive to the auth router and new signup/service/schema/test files, with no settings changes.

## Security Decisions

- Raw verification tokens are generated with `secrets.token_urlsafe(32)`.
- Raw verification tokens are never stored in the database.
- `token_hash`, `idempotency_key_hash`, and `request_fingerprint_hash` use HMAC-SHA256 with the existing validated `settings.SECRET_KEY`.
- Signup responses do not include raw tokens.
- The non-production delivery sink records raw tokens only when `MPANGO_ENV != "production"`; production returns without capture.
- The email delivery sink does not log tokens.
- Public onboarding ORM lookups use `execution_options(ignore_tenant=True)` because these public-schema pre-tenant rows have nullable `wholesaler_id` and must not be filtered by tenant context injected by test-mode auth.
- Duplicate live normalized-email signups return neutral success with `registrationId: null` and do not send another verification delivery.
- Same idempotency key plus same request fingerprint returns the original registration id.
- Reused idempotency key with a different request fingerprint returns `409 IDEMPOTENCY_CONFLICT`.

## Validation Results

Completed:

- RED check: `poetry run pytest tests/test_u6c_signup_email_verification_skeleton.py -q` failed before implementation with `ModuleNotFoundError: No module named 'services.email_delivery'`.
- Focused idempotency repro after initial implementation: `test_same_idempotency_key_and_fingerprint_is_safe` failed because tenant-filtered ORM lookup missed public pre-tenant rows.
- Focused idempotency fix check: `1 passed`.
- U6-C tests: `poetry run pytest tests/test_u6c_signup_email_verification_skeleton.py -q`: `7 passed`.
- Auth regression and route policy tests: `poetry run pytest tests/test_auth_regressions.py tests/test_route_authorization_policy.py -q`: first run failed on the route-policy hardcoded allowlist; rerun after policy assertion update: `36 passed`.
- Focused U6-B schema gate: `poetry run pytest tests/test_u6b_tenant_onboarding_schema.py -q`: `11 passed`.
- After ASCII-only docstring/comment cleanup, U6-C tests reran: `7 passed`.
- After ASCII-only docstring/comment cleanup, auth regression and route policy tests reran: `36 passed`.

Final hygiene:

- `git diff --check`: passed with CRLF working-copy warnings only.
- ASCII scan on changed files: passed after normalizing existing docstring/comment arrows in the two modified files.
- Mojibake scan on changed files: passed.
- Broad secret-pattern scan: matched only expected security/token/password field names, allowlisted synthetic test literals, and ledger text; no real secret values were present.
- Pre-commit on changed files: passed after renaming the synthetic test password constant away from a secret-keyword false positive.

Environment note:

- Windows shell test runs loaded local Docker Postgres credentials into process env without printing them.
- Test env used `POSTGRES_HOST=127.0.0.1`, `POSTGRES_DB=mpango_erp`, `MPANGO_ENV=test`, and `REDIS_URL=redis://127.0.0.1:6379/0`.

Post-commit checks:

- Commit: `253fc418 feat(U6-C): add signup email verification skeleton`.
- GitNexus analyze: passed, repository indexed successfully with 6,457 nodes, 18,385 edges, 422 clusters, and 225 flows.
- GitNexus status: up to date at commit `253fc41`.

## Result

U6-C remains backend-only and implements only the public signup plus email verification token skeleton required before U6-D verify-email behavior.
