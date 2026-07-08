# U6-I0 Owner Credential Setup Contract Gate

Date: 2026-07-08
Branch: `opencode/u6i0-owner-credential-setup-contract-2026-07-08`
Base: `origin/product-dev-recovered` at `5beccba9eedcbf658c55f8b1beae5d067acaaba2`
Verdict: `PASS_FOR_CTO_REVIEW_PENDING_FINAL_GITNEXUS`

## Scope

U6-I0 is a contract-only decision gate for the owner credential setup flow needed after tenant provisioning. It resolves the U6-H4 stop condition: completed tenant provisioning clears the public registration credential hash, so first tenant admin creation cannot safely reuse registration credentials.

Included:

- Durable contract decisions for owner credential setup.
- Static tests for credential setup boundaries and runtime no-change guarantees.

Excluded:

- No production code.
- No migration.
- No frontend.
- No endpoint.
- No `User`, `Role`, or `Permission` model changes.
- No `TenantProvisioningService` changes.
- No deploy or VPS changes.
- No credential delivery implementation.

## Contract Decisions

### 1. No Invented Admin Credentials

First tenant admin creation MUST NOT invent credentials for the owner account. The system MUST NOT create an account using any temporary, default, generated, or otherwise system-selected credential value.

### 2. Token-Based Owner Setup

Owner credential setup MUST use a setup-token flow.

- Persist only a hash of the setup token.
- The raw setup token is delivered exactly once by a future email path or local development sink.
- Raw setup tokens MUST NOT be transported in URL query strings.
- Setup-token proof MUST be sent in a POST body or an HTTP header only.
- Setup tokens MUST expire.
- Setup tokens MUST be single-use.
- Setup-token replay after successful use MUST fail closed.

### 3. First Admin Creation Boundary

Credential setup SHOULD happen before or atomically with first tenant admin creation. Tenant admin creation MUST NOT be separated from credential proof in a way that can create an unreachable admin user.

### 4. Proof Before Tenant User Creation

The tenant admin user MUST be created only after the owner proves possession of a valid, unexpired, unused setup token.

### 5. Registration Credential Cleanup Remains Valid

The current `TenantRegistration` credential cleanup remains valid. U6-I credential setup MUST NOT require preserving, restoring, logging, or exposing the registration credential hash after provisioning completion.

### 6. U6-H4 Dependency

U6-H4 first tenant admin and RBAC creation remains blocked until U6-I owner credential setup exists. U6-H4 may resume only after a credential setup flow can prove owner possession and produce a tenant user password hash without using the cleared registration credential.

### 7. Public Endpoint Disclosure Boundary

Public signup, verify-email, onboarding-status, and future provisioning/status endpoints MUST NOT expose:

- Public registration credential hashes.
- Raw setup tokens.
- Setup-token hashes.
- Tenant schema names.
- Whether the first tenant admin user exists.

## Future U6-I Test Plan

Future implementation tests must prove:

- Setup token is stored hash-only.
- Raw setup token is delivered once through the approved email/dev-sink boundary.
- Query-string setup-token transport is rejected.
- POST body or HTTP header setup-token transport is accepted.
- Expired setup tokens are rejected.
- Reused setup tokens are rejected.
- First tenant admin user is created only after valid setup-token proof.
- U6-H4 admin RBAC provisioning depends on credential setup completion.
- Public onboarding endpoints never return credential hashes, raw setup tokens, setup-token hashes, tenant schema names, or admin existence.

## Validation Results

Completed:

- `poetry run pytest tests/test_u6i0_owner_credential_setup_contract.py -q`: `9 passed`.
- `poetry run python -m py_compile tests/test_u6i0_owner_credential_setup_contract.py`: passed.
- `git diff --check`: passed.
- ASCII scan on changed files: passed, no matches.
- Mojibake scan on changed files: passed, no matches.
- Secret-pattern scan on changed files: reviewed; matches were expected contract/test vocabulary for setup-token and password-hash boundaries, with no actual secrets.
- `pre-commit run --files backend/tests/test_u6i0_owner_credential_setup_contract.py ai-ledger/product-ai/2026-07-08_u6i0_owner_credential_setup_contract.md`: passed.

Pending:

- Commit.
- GitNexus analyze/status.
