# DC-3B Credential Recovery Backend

| Field | Value |
|---|---|
| Date | 2026-07-12 |
| Task ID | DC-3B (Credential Recovery Backend) |
| Mode | Backend implementation (no frontend, no deploy, no migration) |
| Baseline | `origin/product-dev-recovered @ ac99bec7e020ef3f85ebb263ee24019c37958bba` (verified identical to remote tip; no drift) |
| Branch | `opencode/dc3b-credential-recovery-backend-2026-07-12` |
| Worktree | `C:/Users/Jeff0/MPANGO ERP/_dc3b_credential_backend_2026-07-12` (isolated) |
| Reference | DC-3A audit `ai-ledger/product-ai/2026-07-12_dc3a_credential_lifecycle_activation_ux_audit.md` |
| Verdict | `PASS_FOR_CTO_DC3B_REVIEW` |

## 1. Summary

DC-3B implements self-service password recovery and fixes the multi-tenant
same-email password-consistency hazard identified in DC-3A. It is backend-only
(no frontend, no deploy, no VPS) and reuses the existing
`public.password_reset_tokens` table (migration 026) -- **no new migration was
required**.

Implemented:
1. `POST /api/v1/auth/forgot-password` -- neutral 200 always; issues one canonical
   reset token when active tenant users exist; production fail-closed on email
   delivery; no account-existence leak.
2. `POST /api/v1/auth/reset-password` -- body-only token (query-string rejected);
   hash-only token lookup; validates expires/used/revoked/is_deleted; marks
   `used_at` only after the password update succeeds; neutral error on any
   invalid state.
3. Multi-tenant canonical rule: reset and setup-credential now fan-out the
   password to ALL active same-email tenant copies; `/auth/login` now succeeds if
   ANY active copy verifies (closes the stale-hash 401 hazard reproduced in
   DC-2B-R6).
4. Shared password policy (`validate_password_policy`: non-blank, length >= 8)
   reused by signup, setup-credential, and reset.
5. Reset email template + dev delivery sink in `email_delivery.py`.

## 2. Pre-Edit GitNexus Impact

Ran `gitnexus impact` (depth 2) on every touched symbol before edits:

| Symbol | Risk | Affected processes | Verdict |
|---|---|---|---|
| `find_user_across_tenants` | LOW | login (onSubmit), Auth/Schemas | within expected auth path |
| `_ensure_owner_user` | LOW | setup_credential, Services | within expected setup path |
| `verify_password` | LOW | login (onSubmit), Schemas/Crud | within expected auth path |
| `hash_token` | CRITICAL | setup_credential, get_onboarding_status, signup, verify_email_token, complete_email_verified_onboarding | 100% within auth/onboarding token paths; **reused unchanged** (not modified) |
| `consume_setup_token` | LOW | setup_credential, Services | within expected setup path |

No HIGH/CRITICAL impact outside the expected auth/onboarding/user credential
paths. The one CRITICAL (`hash_token`) is the token-hashing primitive that DC-3B
**reuses without modifying**. Gate result: PASS -- proceeded with edits.

## 3. Changed Files

Allowed-file changes (within the task's allowed list):
- `backend/api/v1/auth.py` -- added `/forgot-password` and `/reset-password` endpoints + imports.
- `backend/schemas/auth_signup.py` -- added `ForgotPassword*` and `ResetPassword*` schemas.
- `backend/services/email_delivery.py` -- added the reset delivery helper, a reset-delivery dataclass, and `get_dev_reset_email_deliveries`; `clear_dev_email_deliveries` now clears the reset sink too.
- `backend/services/onboarding_service.py` -- added `validate_password_policy` (shared; `validate_signup_password` delegates to it) and `build_password_reset_link`.
- `backend/services/owner_credential_service.py` -- `_ensure_owner_user` now fans out the password to other active same-email tenant copies via `_propagate_password_to_other_tenants` (SAVEPOINT-isolated per tenant).
- `backend/crud/user.py` -- `find_user_across_tenants` now collects all active copies first and succeeds if ANY copy verifies (no more first-copy short-circuit that let a stale hash block a valid login).
- `backend/services/password_reset_service.py` (NEW) -- `PasswordResetService.request_reset` / `consume_reset` with multi-tenant fan-out, hash-only tokens, fail-closed email.
- `backend/tests/test_dc3b_credential_recovery_backend.py` (NEW) -- 10 required test cases.
- `backend/tests/test_route_authorization_policy.py` -- registered the two new public auth routes in `PUBLIC_ALLOWLIST` and its minimality expectation (necessary behavior alignment for the new pre-auth endpoints; CTO-authorized via the DC-3B spec).

No migration, no frontend, no config, no lockfile, no `.env`/secrets touched.
`.secrets.baseline` was accidentally modified by a diagnostic scan and immediately
restored to HEAD (confirmed clean).

## 4. Design Decisions

- **One canonical reset token** (`tenant_id = NULL`): the `password_reset_tokens`
  unique partial index `ux_password_reset_tokens_email_active_global` already
  enforces one active reset per email. `request_reset` revokes any prior active
  token before issuing the new one.
- **Email resolution at consume without storing plaintext**: the token stores
  only `user_email_hash` (SHA-256 of the normalized email). `consume_reset`
  resolves the affected tenant copies by enumerating active tenant users and
  matching `SHA-256(email)` against the stored hash. No plaintext email is needed
  at consume time and none is stored on the token.
- **Canonical multi-tenant rule**: a reset/setup updates ALL active same-email
  copies; login verifies against any copy (defense-in-depth). Both fan-outs use
  per-tenant SAVEPOINTs so one bad schema cannot abort the whole operation.
- **Token TTL**: 1 hour (`PASSWORD_RESET_TOKEN_TTL`), shorter than the 24h
  setup/verification tokens because reset is higher-risk.
- **Fail-closed**: production `request_reset` raises before commit if SMTP is
  unavailable; the API maps that to a neutral 200 (after rollback) -- no token is
  persisted without a delivered email.

## 5. Security Review

| Control | Status |
|---|---|
| Raw token never persisted | PASS -- only `token_hash` (HMAC-SHA256 via `hash_token`) stored |
| No password hash in public response | PASS -- response schemas expose no `password_hash` |
| Query-string token rejected | PASS -- `/reset-password` returns 401 if `reset_token`/`resetToken`/`new_password`/`token` appear in query params |
| Token expiry / used_at / revoked_at enforced | PASS -- `_is_actionable` + `with_for_update` |
| Single-use (mark used only after success) | PASS -- `used_at` set after the password UPDATE |
| Production email fail-closed | PASS -- `EmailDeliveryNotConfiguredError` propagates before commit |
| No account-existence leak | PASS -- identical neutral 200 for existing/nonexistent email |
| No raw token logging | PASS -- no logger of the token; dev sink is test-only |

## 6. Test Results

DC-3B focused tests (`tests/test_dc3b_credential_recovery_backend.py`) -- 10/10 passed:
1. forgot-password neutral for existing and nonexistent email
2. production fail-closed creates no token if delivery unavailable
3. reset token stored hash-only, raw never persisted
4. reset with valid token updates password
5. expired/used/revoked/invalid token fails neutrally
6. query-string token rejected
7. same email across two tenant schemas: reset updates both hashes
8. login succeeds after reset with multiple tenant copies
9. setup-credential propagates to other tenant copies (no drift)
10. no internal IDs/tokens/hashes in public responses

Regression suites (all PASS):
- `tests/test_dc3b_credential_recovery_backend.py`: 10 passed
- `tests/test_u6c_signup_email_verification_skeleton.py tests/test_u6d_verify_email_endpoint.py tests/test_u6e_onboarding_status_endpoint.py`: 31 passed
- `tests/test_u6i5_owner_credential_setup_endpoint.py`: 10 passed (no regression; SAVEPOINT fix preserved tenant-isolation semantics)
- `tests/test_auth_regressions.py tests/test_route_authorization_policy.py`: 36 passed
- **Total: 87 passed, 0 failed**

## 7. Migration

**No migration was required.** The existing `public.password_reset_tokens` table
(migration 026) had all needed columns (`token_hash`, `user_email_hash`,
`tenant_id`, `tenant_schema`, `expires_at`, `used_at`, `revoked_at`,
`request_fingerprint_hash`) and the right unique partial indexes. No
`STOP_AND_REPORT_CTO` schema-insufficiency condition was hit.

## 8. Validation

| Check | Result |
|---|---|
| `poetry run pytest tests/test_dc3b_credential_recovery_backend.py -q` | 10 passed |
| U6 + auth regression suites | 77 passed (87 total with DC-3B) |
| `py_compile` on all touched files | PASS |
| `git diff --check` | PASS |
| ASCII / mojibake scan (all changed files) | PASS (pure ASCII) |
| `detect-secrets` / pre-commit (all changed files) | PASS (false-positive string constants annotated with `# pragma: allowlist secret`) |
| `npx gitnexus analyze` | indexed successfully; up-to-date |
| `npx gitnexus status` | up-to-date at `ac99bec` |

## 9. Proof No Secrets Printed/Persisted

- No password, JWT, refresh token, raw reset token, or full email is printed or
  logged by the implementation. Responses are neutral and contain only a fixed
  message string.
- Reset tokens are stored HMAC-hashed; the raw token exists only in memory and
  the email channel (test case 3 asserts `stored_hash != raw_token` and the raw
  token is not a substring of any persisted value).
- Test-only constants that resemble secrets are annotated with
  `# pragma: allowlist secret` (same convention as existing onboarding code).
- The throwaway test Postgres container used for validation was removed.

## 10. Verdict

**PASS_FOR_CTO_DC3B_REVIEW**

Backend credential recovery is implemented and fully tested. Forgot-password,
reset-password (hash-only, body-only, fail-closed, single-use), and the
multi-tenant same-email password-consistency fix (fan-out on reset + setup,
login verifies any copy) are in place. No migration was needed. DC-3C (frontend
setup-credential/forgot/reset pages) remains the other delivery dependency
identified in DC-3A.

## 11. DC-3B-R1 Auth Tenant Selection Consistency (CTO review fixes)

Date: 2026-07-12 (revision R1). Base: `b23bcfb9`. CTO verdict on R0:
`REQUEST_CHANGES_BEFORE_MERGE`. This section documents the R1 fixes.

### R1.1 Verified-tenant-only match list
`find_user_across_tenants` (`backend/crud/user.py`) now returns ONLY tenant
copies whose own `password_hash` verifies against the supplied password. An
unverified copy (same email, different password in another tenant) is no longer
granted or listed. `verified_user_id` is the user_id of the first verified copy;
the match list contains only verified copies. (Previously it returned ALL
copies once any one verified.)

### R1.2 Signed tenant_id -> user_id map in the identity JWT
`create_identity_token` (`backend/core/security.py`) now accepts an optional
`tenant_user_map: {tenant_id: tenant_local_user_id}` of VERIFIED matches and
embeds it as a signed `tmap` JWT claim. `TokenPayload` gained a `tmap` field.
The login endpoint (`backend/api/v1/auth.py`) builds the map from verified
matches and passes it to both access and refresh identity tokens. The map is
signed (part of the JWT) so it cannot be tampered with, and it is NEVER exposed
in the public response body.

### R1.3 select-tenant uses the per-tenant user_id
`/auth/select-tenant` (`backend/api/v1/auth.py`) resolves the tenant-local
user_id from `tmap` for identity-only tokens, so the correct per-tenant user is
selected even when the same email has different user IDs across tenants.
Contextual tokens and legacy/mock tokens without `tmap` fall back to
`token.user_id` (`getattr(token, "tmap", None)` tolerates mock tokens). A
tenant not present in `tmap` is rejected with 403.

### R1.4 Identity refresh preserves the map
`/auth/refresh` (`backend/api/v1/auth.py`) preserves `tmap` across identity
refresh. Also fixed: the refresh endpoint `response_model` was `LoginResponse`
(required `tenant_id`/`tenant_schema`) but the identity-refresh branch returns
`IdentityLoginResponse`; changed to `Union[LoginResponse, IdentityLoginResponse]`
so identity refresh no longer triggers a 500 ResponseValidationError.

### R1.5 Query-string token rejection unchanged
No change to the `/reset-password` and `/setup-credential` query-string token
rejection. Still enforced.

### R1.6 Tests (5 new in test_dc3b_credential_recovery_backend.py)
- `test_r1_different_passwords_isolates_unverified_tenant`: same email, two
  tenants, different passwords -> login with password A lists/selects only
  tenant A; the other tenant is not selectable (403).
- `test_r1_same_password_different_user_ids_selects_both`: same email + same
  password but distinct user IDs -> login lists both and select-tenant succeeds
  for both (uses tmap per-tenant user_id).
- `test_r1_after_reset_both_copies_login_and_select`: after password reset
  fan-out, both tenant copies can login and select-tenant succeeds for both.
- `test_r1_identity_refresh_preserves_tenant_selection`: after identity refresh,
  every originally-available tenant is still selectable.
- `test_r1_no_internal_mapping_in_public_responses`: no `tmap`, no
  `tenant_user_map`, no `password_hash`/`token_hash`, and not both tenant user
  IDs simultaneously in any login/select/refresh response body.

The R1 tests use a module-level `_real_token_dependency` that overrides
`get_current_user_context` to decode the real bearer JWT (the default
`MockAuthStrategy` in test mode ignores the Authorization header and injects a
fixed mock token without `tmap`).

### R1.7 Changed files (R1)
- `backend/core/security.py` -- `TokenPayload.tmap`; `create_identity_token(tenant_user_map=...)`.
- `backend/crud/user.py` -- verified-tenant-only match list.
- `backend/api/v1/auth.py` -- login builds tmap; select-tenant uses tmap; refresh preserves tmap; refresh response_model union.
- `backend/tests/test_dc3b_credential_recovery_backend.py` -- 5 R1 tests + `_client_with_real_auth` helper.

No migration, no frontend, no deploy, no `.env`/secrets. `.secrets.baseline`
not modified.

### R1.8 Validation (R1)
- `poetry run pytest tests/test_dc3b_credential_recovery_backend.py -q`: **15 passed** (10 R0 + 5 R1).
- `poetry run pytest tests/test_auth_regressions.py tests/test_route_authorization_policy.py -q`: **36 passed**.
- U6 regression (u6c/d/e + u6i5): **41 passed**.
- `py_compile` on `core/security.py`, `crud/user.py`, `api/v1/auth.py`, `schemas/auth.py`: PASS.
- `git diff --check`: PASS.
- ASCII / mojibake scan on all changed files: PASS.
- `detect-secrets` / pre-commit on all changed files: PASS.
- `npx gitnexus analyze`: indexed successfully (12,585 nodes); `npx gitnexus status`: up-to-date.

### R1.9 Selectability guarantee
Every tenant returned in `available_tenants` is selectable: `available_tenants`
is built from the verified-only match list, and `tmap` carries the signed
user_id for each of those exact tenants, so `select-tenant` resolves and admits
each one. A tenant not verified at login is neither listed nor selectable.

### R1.10 R1 Verdict
**PASS_FOR_CTO_DC3B_REVIEW** (R1 fixes applied; all R1 + regression tests green).
