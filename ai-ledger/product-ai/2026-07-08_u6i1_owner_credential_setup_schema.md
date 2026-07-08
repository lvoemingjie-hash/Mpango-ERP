# U6-I1 Owner Credential Setup Schema Foundation

Date: 2026-07-08
Branch: `opencode/u6i1-owner-credential-setup-schema-2026-07-08`
Base: `origin/product-dev-recovered` at `3726aa767d4d572c30e601ac53ceb1938cc6d014`
Implementation commit: `712db0c1 feat(U6-I1): add owner credential setup token schema`
Verdict: `PASS_FOR_CTO_REVIEW`

## Scope

U6-I1 adds the schema foundation for owner credential setup tokens so U6-H4 can later create the first tenant admin only after the owner proves possession of a setup token.

Included:

- Public table `owner_credential_setup_tokens`.
- ORM model `OwnerCredentialSetupToken`.
- Alembic revision `028_owner_credential_setup_tokens`.
- Static schema tests proving hash-only token storage and no runtime behavior changes.

Excluded:

- No endpoint.
- No frontend.
- No `TenantProvisioningService` edit.
- No `User`, `Role`, or `Permission` edit.
- No admin creation.
- No deploy/VPS changes.
- No raw token storage.
- No query-string token support.

## Schema Decisions

- `public.owner_credential_setup_tokens.id`: UUID primary key with `gen_random_uuid()` default.
- `registration_id`: required FK to `public.tenant_registrations(id)` with `ON DELETE CASCADE`.
- `token_hash`: required `VARCHAR(128)`, unique, hash-only storage.
- Forbidden columns: `raw_token`, `token_plaintext`, `plaintext_token`.
- `purpose`: required, default/check constrained to `owner_credential_setup`.
- `expires_at`: required.
- `used_at` and `revoked_at`: nullable lifecycle markers.
- `created_at`, `updated_at`, `is_deleted`, and `deleted_at`: included through the public audit-column convention.
- Active-token index: unique partial index on `registration_id` where `used_at IS NULL AND revoked_at IS NULL AND is_deleted = false`.

## RED/GREEN Evidence

- RED: `poetry run pytest tests/test_u6i1_owner_credential_setup_schema.py -q` failed because `OwnerCredentialSetupToken` was not exported from `models`.
- GREEN: after adding the migration/model/export, `poetry run pytest tests/test_u6i1_owner_credential_setup_schema.py -q` passed with `7 passed, 1 warning`.

## Validation Results

CTO validation update: `tests/test_u6i0_owner_credential_setup_contract.py` is intentionally skipped for U6-I1 because it is a U6-I0 exact branch-scope test and is not reusable on U6-I1 branches.

Completed:

- `poetry run pytest tests/test_u6i1_owner_credential_setup_schema.py -q`: `7 passed, 1 warning`.
- `poetry run pytest tests/test_u6b_tenant_onboarding_schema.py -q`: `11 passed`.
- `poetry run alembic heads`: `028_owner_credential_setup_tokens (head)`.
- `poetry run python -m py_compile tests/test_u6i1_owner_credential_setup_schema.py models/tenant_onboarding.py models/__init__.py alembic/versions/028_owner_credential_setup_tokens.py`: passed.
- `git diff --check`: passed.
- Forbidden runtime file check: no changes to `TenantProvisioningService`, `User`/`Role`/`Permission`, auth route, or onboarding service.
- ASCII scan on changed files: passed, no matches.
- Mojibake scan on changed files: passed, no matches.
- Secret-pattern scan on changed files: reviewed; matches were expected schema/test vocabulary for token hash, forbidden raw-token column names, and existing password-hash fields, with no actual secrets.
- `pre-commit run --files backend/alembic/versions/028_owner_credential_setup_tokens.py backend/models/tenant_onboarding.py backend/models/__init__.py backend/tests/test_u6i1_owner_credential_setup_schema.py ai-ledger/product-ai/2026-07-08_u6i1_owner_credential_setup_schema.md`: passed.

Pending:

- Commit: `712db0c1 feat(U6-I1): add owner credential setup token schema`.
- `npx gitnexus analyze`: repository indexed successfully; `6,874 nodes`, `19,483 edges`, `461 clusters`, `229 flows`.
- `npx gitnexus status`: indexed commit `712db0c`, current commit `712db0c`, status up-to-date.
