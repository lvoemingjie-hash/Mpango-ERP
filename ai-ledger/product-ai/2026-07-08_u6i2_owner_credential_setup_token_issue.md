# U6-I2 Owner Credential Setup Token Issue Service

Date: 2026-07-08
Branch: `opencode/u6i2-owner-credential-setup-token-issue-2026-07-08`
Base: `origin/product-dev-recovered` at `551b9e787a0513bdd2be7b9071bfd11fb6568301`
Verdict: `PASS_FOR_CTO_MERGE_REVIEW`

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
- Duplicate issue with a lifecycle-active and unexpired token (`used_at IS NULL`, `revoked_at IS NULL`, `is_deleted = false`, `expires_at > now`) does not create a second active row and does not return the original raw token.
- Expired lifecycle-active tokens are closed before replacement issue so the U6-I1 partial unique index can permit exactly one new active token without a migration.
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
- Implementation commit: `431f5111 feat(U6-I2): issue owner credential setup tokens`.
- `npx gitnexus analyze`: repository indexed successfully, `6,907 nodes | 19,585 edges | 462 clusters | 229 flows`.
- `npx gitnexus status`: indexed commit `431f511`, current commit `431f511`, status up to date.

## R1 Expired Token Reissue Fix

- Finding: `_active_token` treated expired unused tokens as active, causing `issue_setup_token` to return `action="existing"` after expiry instead of issuing a replacement.
- RED: added `test_expired_prior_token_allows_new_setup_token_issue`; it failed with `assert 'existing' == 'issued'` while used/revoked prior-token tests already passed.
- Fix: `_active_token` now requires `expires_at > now` in addition to lifecycle-active predicates.
- Fix: expired lifecycle-active rows are retained for audit and closed with `revoked_at=now` before inserting the replacement token, because the existing U6-I1 partial unique index excludes only used/revoked/deleted rows.
- Coverage added for expired, used, and revoked prior-token reissue behavior while preserving duplicate unexpired-token behavior and hash-only storage.
- GREEN: `poetry run pytest tests/test_u6i2_owner_credential_setup_token_issue.py -q`: `14 passed`.

Completed R1 Final Validation:

- `poetry run pytest tests/test_u6i2_owner_credential_setup_token_issue.py -q`: `14 passed`.
- `poetry run pytest tests/test_u6i1_owner_credential_setup_schema.py tests/test_u6h3_tenant_provisioning_reconcile_cleanup.py -q -k "not test_branch_changes_only_allowed_schema_foundation_files"`: `14 passed, 1 deselected, 1 warning`.
- `git diff --check`: passed.
- ASCII scan on changed files: passed, no matches.
- Mojibake scan on changed files: passed, no matches.
- Secret-pattern scan on changed files: reviewed; matches were expected token/hash/credential terminology and existing password-hash test field names, with no actual secrets.
- `pre-commit run --files backend/services/owner_credential_service.py backend/tests/test_u6i2_owner_credential_setup_token_issue.py ai-ledger/product-ai/2026-07-08_u6i2_owner_credential_setup_token_issue.md`: passed.
- R1 implementation commit: `7c59c731 fix(U6-I2): reissue expired owner setup tokens`.
- `npx gitnexus analyze`: repository indexed successfully, `6,911 nodes | 19,616 edges | 460 clusters | 229 flows`.
- `npx gitnexus status`: indexed commit `7c59c73`, current commit `7c59c73`, status up to date.
