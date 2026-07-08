# U6-I2 Owner Credential Setup Token Issue Service

Date: 2026-07-08
Branch: `opencode/u6i2-owner-credential-setup-token-issue-2026-07-08`
Base: `origin/product-dev-recovered` at `551b9e787a0513bdd2be7b9071bfd11fb6568301`
Verdict: `PASS_FOR_CTO_REVIEW_PENDING_GITNEXUS`

## Scope

U6-I2 adds backend service logic to issue owner credential setup tokens for active/provisioned tenant registrations.

Included:

- New `OwnerCredentialSetupService.issue_setup_token(registration_id)` service method.
- Hash-only persistence to `public.owner_credential_setup_tokens.token_hash`.
- Raw setup token returned only in-memory for future delivery.
- Idempotent duplicate issue behavior: existing active token returns `action="existing"` and no raw token.
- Static/runtime tests proving no endpoint, no query-string token support, no admin/RBAC creation, and no business data seeding.

Excluded:

- No endpoint.
- No frontend.
- No admin creation.
- No `TenantProvisioningService` edit.
- No `User`, `Role`, or `Permission` edit.
- No email delivery implementation.
- No raw token storage.
- No query-string token support.

## Token Boundary Decisions

- Eligibility requires `TenantRegistration.status == "active"`, `wholesaler_id`, `tenant_schema`, and `provisioning_completed_at`.
- The service reuses existing HMAC token hashing from `onboarding_service.hash_token` and high-entropy token generation from `generate_verification_token`.
- The database stores only `token_hash`; the raw token exists only in the returned dataclass for later delivery integration.
- Duplicate issue with a lifecycle-active token (`used_at IS NULL`, `revoked_at IS NULL`, `is_deleted = false`) does not create a second active row and does not return the original raw token.
- Blocked registrations create no token rows.
- The service does not build links and has no URL query-string token transport.

## RED/GREEN Evidence

- RED: `poetry run pytest tests/test_u6i2_owner_credential_setup_token_issue.py -q` failed because `services.owner_credential_service` did not exist.
- GREEN: after adding `backend/services/owner_credential_service.py`, `poetry run pytest tests/test_u6i2_owner_credential_setup_token_issue.py -q` passed with `11 passed` using disposable Postgres container `opencode_u6i2_pg` on localhost port `55436`.

## Validation Results

Completed:

- `poetry run pytest tests/test_u6i2_owner_credential_setup_token_issue.py -q`: `11 passed`.
- `poetry run pytest tests/test_u6i1_owner_credential_setup_schema.py tests/test_u6h3_tenant_provisioning_reconcile_cleanup.py -q`: `1 failed, 14 passed`; failure was `test_branch_changes_only_allowed_schema_foundation_files`, a U6-I1 exact branch-scope test that is intentionally not reusable on U6-I2 branches.
- `poetry run pytest tests/test_u6i1_owner_credential_setup_schema.py tests/test_u6h3_tenant_provisioning_reconcile_cleanup.py -q -k "not test_branch_changes_only_allowed_schema_foundation_files"`: `14 passed, 1 deselected, 1 warning`.
- `poetry run python -m py_compile services/owner_credential_service.py tests/test_u6i2_owner_credential_setup_token_issue.py`: passed.
- `git diff --check`: passed.
- Forbidden-path check: no changes to `backend/api`, frontend paths, `TenantProvisioningService`, or `User`/`Role`/`Permission` model code.
- ASCII scan on changed files: passed, no matches.
- Mojibake scan on changed files: passed, no matches.
- Secret-pattern scan on changed files: reviewed; matches were expected token/hash terminology and existing password-hash test field names, with no actual secrets.
- `pre-commit run --files backend/services/owner_credential_service.py backend/tests/test_u6i2_owner_credential_setup_token_issue.py ai-ledger/product-ai/2026-07-08_u6i2_owner_credential_setup_token_issue.md`: passed.

Pending:

- Commit.
- GitNexus analyze/status.
