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
login verifies any copy) are in place. No migration was needed. 87 tests pass
(10 DC-3B + 77 regressions). DC-3C (frontend setup-credential/forgot/reset
pages) remains the other delivery dependency identified in DC-3A.
