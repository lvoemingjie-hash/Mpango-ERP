# U6-E0 Onboarding Status Token Schema Contract

Date: 2026-07-07
Branch: `opencode/u6e0-onboarding-status-token-schema-2026-07-07`
Base: `origin/product-dev-recovered` at `73136b13 merge: U6-D verify email endpoint skeleton`
Verdict: `PASS_FOR_CTO_U6E0_REVIEW_READY`

## Scope

U6-E0 adds only the schema and ORM foundation needed for a future safe onboarding status endpoint.

Included:

- `public.onboarding_status_tokens` migration.
- `OnboardingStatusToken` public ORM model.
- Hash-only `token_hash` storage for opaque status lookup tokens.
- `registration_id` foreign key to `public.tenant_registrations(id)` with `ON DELETE CASCADE`.
- `purpose = 'onboarding_status'` default and check constraint.
- `expires_at`, `revoked_at`, and standard public audit/soft-delete columns.
- Unique token-hash index and active registration lookup indexes.
- Schema contract tests proving no raw token columns and no onboarding status endpoint.

Excluded:

- No `/api/v1/auth/onboarding/status` endpoint.
- No signup behavior changes.
- No verify-email behavior changes.
- No raw token generation, storage, logging, or return path.
- No tenant provisioning, schema creation, users, roles, RBAC, inventory, orders, finance, workspace, or admin account creation.
- No frontend, deploy, or VPS changes.

## Security Decisions

- Raw onboarding status tokens are intentionally not modeled or stored.
- Future runtime lookup must hash submitted opaque tokens before comparing against `token_hash`.
- The active registration lookup index is scoped to non-revoked, non-deleted status-token rows.
- The schema does not expose owner email, registration id, tenant id, tenant schema, wholesaler id, user id, role/RBAC details, raw token, token hash, or password hashes through any route because no route was added.

## Validation Results

Completed so far:

- RED check: `poetry run pytest tests/test_u6e0_onboarding_status_token_schema.py -q` failed before implementation because `ONBOARDING_STATUS_TOKEN_PURPOSE` / `OnboardingStatusToken` did not exist.
- `poetry run pytest tests/test_u6e0_onboarding_status_token_schema.py -q`: `8 passed`.
- `poetry run pytest tests/test_u6b_tenant_onboarding_schema.py -q`: `11 passed`.
- `poetry run alembic heads`: `027_onboarding_status_tokens (head)`.
- `git diff --check`: passed with CRLF working-copy warnings only.
- ASCII scan on changed files: passed.
- Mojibake scan on changed files: passed.
- Broad secret-pattern scan: matched only expected token/password/security field names, constants, and allowlisted synthetic test literals; no real secret values were present.
- Pre-commit on changed files: passed.
- `npx gitnexus analyze`: repository indexed successfully at commit `c5b2772`.
- `npx gitnexus status`: up to date at commit `c5b2772`.

Pending: none.

## Result

U6-E0 unblocks a future U6-E onboarding status endpoint by adding a hash-only onboarding status token table while keeping the change schema-only.
