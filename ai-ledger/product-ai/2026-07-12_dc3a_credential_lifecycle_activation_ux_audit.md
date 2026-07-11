# DC-3A Credential Lifecycle + Activation UX Audit

| Field | Value |
|---|---|
| Date | 2026-07-12 |
| Task ID | DC-3A (Credential Lifecycle + Activation UX Audit) |
| Mode | Audit / design gate. Read-only. No code, migration, test, frontend, config, or lockfile changes. |
| Baseline | `origin/product-dev-recovered @ ac99bec7e020ef3f85ebb263ee24019c37958bba` (verified identical to remote tip; no drift) |
| Branch | `opencode/dc3a-credential-lifecycle-activation-ux-audit-2026-07-12` |
| Worktree | `C:/Users/Jeff0/MPANGO ERP/_dc3a_credential_audit_2026-07-12` (isolated) |
| Auditor | Codex agent |

## 1. Executive verdict

**NEEDS_DC3B_DC3C_BEFORE_DELIVERY**

The signup -> verify-email -> auto-provision -> owner-setup-token -> set-password backend flow
is **implemented, secure (hash-only tokens, query-string rejection, fail-closed email), and
runtime-proven** (DC-2B-R6 closed the auth caveat with a real 200 login/select-tenant/me
flow). However two delivery-blocking gaps remain:

1. **No self-service password recovery.** A `password_reset_tokens` table + ORM model exist
   (migration 026) but are **dead code** -- no endpoint, no service, no CRUD, no email
   template reads them. An owner who forgets their password after onboarding has **no
   recovery path** except a manual DB intervention (which the platform forbids as a routine
   operation). This is a real customer-delivery blocker.
2. **No frontend for any credential-lifecycle step.** The frontend ships only `/login`,
   `/select-workspace`, `/client/login`, and `/invite/:code`. There is **no** signup,
   verify-email, setup-credential (set-password), forgot-password, or reset-password page,
   and **no** "Forgot password?" link on login. The emailed `/setup-credential?setupToken=...`
   link currently hits the 404 catch-all. Onboarding today is backend-only and is exercised
   via curl/scripts, not the shipped UI.

A secondary, security-relevant hazard: **multi-tenant same-email password consistency**.
Login verifies the password against only the **first** tenant copy it finds and short-circuits
on mismatch (`crud/user.py:74-76`), while setup-credential updates only **one** tenant copy
(`owner_credential_service.py:291-327`). This already caused a real 401 in DC-2B-R6 when one
copy was updated and the other was not. This must be resolved (canonical rule + propagation)
in DC-3B.

This audit makes no code changes. DC-3B (backend) and DC-3C (frontend) are required before
customer delivery; a minimum demo path is described in Section 7.

## 2. Current signup -> verify -> provisioning -> setup-credential flow

The end-to-end onboarding chain is implemented in the backend and was runtime-proven in
DC-1A (U6J-R3 full onboarding E2E) and DC-2B-R6.

### 2.1 Signup
- `POST /api/v1/auth/signup` (`backend/api/v1/auth.py:88`).
- Request schema `SignupRequest` (`backend/schemas/auth_signup.py:11-44`): `email` (EmailStr),
  `password` (`min_length=8, max_length=128`), `company_name`, `country`, optional
  `phone`/`business_type`. Email normalized to lowercase (`:33-36`).
- Service `create_signup_registration` (`backend/services/onboarding_service.py`). It is
  **fail-closed on email delivery**: `:265-266` raises `EmailDeliveryNotConfiguredError` before
  any write if production SMTP is not configured; surfaced as HTTP 503 (`auth.py:109-116`).
- Returns a neutral 202 (`status=PUBLIC_SIGNUP_STATUS`) -- does not reveal whether the email
  is new or duplicate.

### 2.2 Email verification
- `POST /api/v1/auth/verify-email` (`auth.py:134`).
- `verify_email_token` (`onboarding_service.py:107-163`) validates the token (rejects
  `used_at`/`revoked_at`/expired; `:137-146`), then on success runs
  **`complete_email_verified_onboarding`** in the same request -- so verify-email triggers
  auto-provisioning.
- Email-verification token TTL = 24h (`SIGNUP_VERIFICATION_TTL`, `onboarding_service.py:45`).

### 2.3 Automatic provisioning + owner setup-token issuance
- `complete_email_verified_onboarding` (`onboarding_service.py:166-215`):
  1. Fail-closed gate on email delivery config (`:174-175`).
  2. Provisions the tenant: `TenantProvisioningService.claim_registration_for_provisioning`
     then `provision_wholesaler_and_schema`; raises `OnboardingOrchestrationError` on any
     non-{claimed,existing} / non-{provisioned,reconciled,existing} / non-`active` outcome
     (`:177-189`).
  3. **Commits before sending the setup email** (`:194`) so an SMTP failure is retryable
     against the same provisioned schema (the tenant is not orphaned).
  4. Issues the owner setup token via `OwnerCredentialSetupService.issue_setup_token`
     (`:196-200`).
  5. Sends the owner setup email via `record_owner_setup_email(..., setup_link=build_owner_setup_link(...))`
     (`:209-215`).
- Reissue path: if provisioning succeeded but no live setup token remains,
  `_is_retryable_setup_email_failure` (`:414-436`) makes the verification token retryable so
  re-clicking verify re-runs the orchestration and re-issues a setup token.

### 2.4 The setup email + link
- `build_owner_setup_link` (`onboarding_service.py:366-368`):
  `f"/setup-credential?setupToken={quote(token, safe='')}"`.
- Email body is a **fixed template** (`backend/services/email_delivery.py:88-94`):
  "Set up your Mpango ERP owner account" / "Use this link to set your owner administrator
  password: {setup_link}".
- **Important UX/security interplay**: the link carries `setupToken` in the query string, but
  the consuming endpoint **explicitly rejects query-string tokens** (`auth.py:616-625` returns
  401 if `setup_token`/`setupToken`/`password` appear in query params). This is an intentional
  anti-leakage design (tokens must be POSTed in the body), but it means the emailed link is
  informational only -- a dedicated frontend page must extract the token from the URL and
  POST it in the body. **That frontend page does not exist** (Section 3).

### 2.5 Set password (owner credential setup)
- `POST /api/v1/auth/onboarding/setup-credential` (`auth.py:606-610`).
- `OwnerCredentialSetupRequest` (`auth_signup.py:119-125`): `setup_token` (alias `setupToken`,
  max 512), `password` (`min_length=8, max_length=128`).
- Service flow: `OwnerCredentialSetupService.consume_setup_token`
  (`backend/services/owner_credential_service.py:183-216`) -> `create_first_admin_rbac`
  (`:218-242`).
- Token is **single-use**: `consume_setup_token` locks the row `with_for_update()` (`:194`),
  marks `used_at` immediately (`:207`) before hashing the password. A second submission with
  the same token fails the actionable check (`_is_actionable_setup_token`, `:396-405`) and
  returns 401.
- Token TTL = 24h (`OWNER_CREDENTIAL_SETUP_TOKEN_TTL`, `:24`).
- It creates/updates the owner admin user **in exactly one tenant schema**
  (`_ensure_owner_user`, `:291-327`). See Section 5 for the multi-tenant implication.

## 3. Current frontend UX availability

The shipped frontend has an **extremely thin** credential lifecycle. Confirmed by reading
`frontend/src/router/AppRouter.tsx` and `frontend/src/services/authService.ts`.

| Capability | Status | Evidence |
|---|---|---|
| Wholesaler/admin login | Present | `frontend/src/pages/auth/LoginPage.tsx`; route `AppRouter.tsx:53-56` |
| Retailer/client login | Present | `frontend/src/pages/client/ClientLoginPage.tsx`; route `AppRouter.tsx:59-62` |
| Multi-tenant workspace selector | Present | `frontend/src/pages/auth/WorkspaceSelectorPage.tsx`; route `AppRouter.tsx:64-67` |
| Invitation lookup (read-only) | Present (no password set) | `frontend/src/pages/invite/InvitePage.tsx`; route `AppRouter.tsx:68-72` |
| **Setup-credential / set-password page** | **ABSENT** | no route, no page, no `setupToken` consumption anywhere in `frontend/src` |
| **Verify-email page** | **ABSENT** | no route, no page |
| **Forgot-password page** | **ABSENT** | no route, no page |
| **Reset-password page** | **ABSENT** | no route, no page |
| **Signup / register page** | **ABSENT** | no route, no page |
| "Forgot password?" link on login | **ABSENT** | neither LoginPage nor ClientLoginPage markup contains it |
| API client `setupCredential` / `verifyEmail` / `forgotPassword` / `resetPassword` | **ABSENT** | `authService.ts:14-32` has only login/selectTenant/refresh/me/logout |

Two concrete defects follow from this:
- The emailed `/setup-credential?setupToken=...` link lands on the `*` catch-all ->
  `NotFoundPage` (`AppRouter.tsx:162-165`). A new owner cannot set their password through the
  shipped UI today.
- `LoginPage.tsx:104` navigates to `/onboarding/create-tenant` for the "zero tenants" cold
  start case, but that route/page does not exist (dead link -> 404).

## 4. Forgot-password readiness matrix

| Question | Answer | Evidence |
|---|---|---|
| Does a password-reset schema/table exist? | **Yes (but dead)** | `password_reset_tokens` table + `PasswordResetToken` model: `backend/models/tenant_onboarding.py:214-265`; created by migration `026_tenant_onboarding_auth_contract.py:146-178` |
| Are reset tokens hash-only by design? | **Yes (modeled)** | model stores `token_hash`/`user_email_hash`/`request_fingerprint_hash`; no raw-token column (`tenant_onboarding.py:248-265`) |
| Is there an API to **request** a reset? | **No** | no `/forgot-password` or `/password-reset/request` route in `auth.py` or any router (`api/app.py:117` registers only `auth.router`) |
| Is there an API to **consume** a reset and set a new password? | **No** | no consume endpoint; `PasswordResetToken` is imported by zero non-test modules other than `models/__init__.py:29,48` |
| Is there a reset email template? | **No** | `email_delivery.py` has only `record_verification_email` and `record_owner_setup_email`; no `record_password_reset_email` |
| Is there frontend for forgot/reset? | **No** | Section 3 |
| Does production email delivery support reset emails? | **Mechanism yes, wiring no** | `_send_smtp_email` (`email_delivery.py:161-193`) is generic but only the two onboarding templates call it; no reset sender is wired |
| Are query-string tokens forbidden? | **Yes (for setup-credential)** | `auth.py:616-625`; a reset endpoint must repeat the same guard |

**Net readiness: 1 of 9 dimensions ready (the hash-only schema). Everything else is missing.**

Backend-wide search for `forgot_password`, `reset_password`, `forgot-password`,
`reset-password` returned **zero** matches (excluding tests). `password_reset` /
`PasswordResetToken` appear only in the model definition, the model export, and migration 026.

## 5. Multi-tenant same-email password behavior

This is the most important latent defect surfaced by this audit, and it was **reproduced live**
during DC-2B-R6.

### 5.1 How `/auth/login` chooses which user record to verify
- `find_user_across_tenants` (`backend/crud/user.py:29-88`) scans wholesalers **ordered by
  `Wholesaler.created_at`** (`:52-58`) and, for each, looks up the user by email in that
  tenant schema.
- **Password is verified exactly once** -- against the **first** tenant copy found
  (`:73-77`):
  - Line 74: `if verified_user_id is None:` -> verify password against this first copy.
  - Line 75-76: `if not verify_password(password, user.password_hash): return (None, [])` --
    on the **first** mismatch it **immediately returns empty** and does **not** try any other
    tenant copy.
- The code comment (`:73`) states the assumption: "all tenant copies share same email" (and
  implicitly the same password).

### 5.2 What setup-credential updates
- `_ensure_owner_user` (`owner_credential_service.py:291-327`) writes the password hash to
  **exactly one tenant schema** -- the single `registration.tenant_schema`. It does **not**
  touch the same email in any other tenant schema.

### 5.3 The stale-hash 401 hazard (confirmed live)
If the same owner email exists in two tenant schemas and only one copy's password is changed
(e.g., via setup-credential for one registration, or a future reset that updates one copy),
then:
- If the **stale** (un-updated) copy is ordered first by `created_at`, login verifies against
  the stale hash, mismatches, and returns 401 -- **even though the other copy has the correct
  new password**.
- This is **not hypothetical**: in DC-2B-R6, updating only one of two schemas produced a 401
  until both copies were updated. The smoke only passed after setting the temp password in
  **both** schemas.

### 5.4 Canonical product rule (recommended)
For a single business owner who legitimately has the same email across multiple tenant
schemas, the password MUST be consistent. Recommended canonical rule for DC-3B:
- Treat the owner email as the identity; a password set/reset must propagate to **every**
  tenant schema where that email's user is active (fan-out update), performed atomically
  (all-or-nothing per schema, with fail-closed on any schema that cannot be reached).
- Login should verify against the password and, on success, return all matching tenants (it
  already collects `matches`); it must not short-circuit on the first copy in a way that lets
  a stale copy block a valid login. Alternatively (simpler): make password set/reset fan out
  so all copies stay identical, preserving the current single-verify assumption.
- The chosen rule must be explicit and tested (Section 8). The current "first-copy-only
  verify + one-copy update" combination is internally inconsistent and is the bug.

## 6. Security review

| Control | Status | Evidence |
|---|---|---|
| No raw tokens stored | **PASS** | all token models store `token_hash` only; `hash_token` = HMAC-SHA256 keyed by `SECRET_KEY` (`onboarding_service.py:354-358`, `_hmac_sha256:460-465`); setup/verify/status tokens all hashed before persist |
| No password hashes in public responses | **PASS** | response schemas (`auth_signup.py`, `auth.py` responses) expose no `password_hash`; neutral messages only |
| No token in query string (consumption) | **PASS** | `setup-credential` rejects query-string `setup_token`/`setupToken`/`password` -> 401 (`auth.py:616-625`) |
| Token expiry / used_at / revoked_at | **PASS** | verify token: `used_at`+`revoked_at`+`expires_at` (`tenant_onboarding.py:202-203,201`); setup token: `used_at`+`revoked_at`+`expires_at` (`:348-349,347`); status token: `revoked_at`+`expires_at`, no used_at (read-only) (`:303-304`); actionable checks in services |
| Single-use setup token (race-safe) | **PASS** | `consume_setup_token` uses `with_for_update()` + marks `used_at` before password hash (`owner_credential_service.py:194,207`) |
| Production email fail-closed | **PASS** | `is_verification_email_delivery_configured` False in prod unless SMTP complete (`email_delivery.py:34-38,123-139`); SMTP errors re-raised as `EmailDeliveryNotConfiguredError` -> 503 (`:192-193`, `auth.py:150-157`) |
| No secret logging | **PASS (with caveat)** | no `logger.*` of tokens/passwords found; **caveat**: in non-production, raw tokens are captured in the in-memory `_DEV_EMAIL_DELIVERIES` list (`email_delivery.py:61-69,98-107`) -- acceptable for test/dev only |
| Token-hash key strength guard | **PASS** | `_assert_token_hash_key` raises if `SECRET_KEY` missing or < 32 chars (`onboarding_service.py:468-470`) |
| Password-strength policy | **WEAK** | length-only (`min_length=8`): schema `auth_signup.py:17,123`; service `validate_signup_password` (`onboarding_service.py:101-104`). **No complexity, breach-list, or zxcvbn check.** Note: setup-credential relies on Pydantic only (no service-layer re-check). |

**Security gaps to address in DC-3B**: (a) the multi-tenant password-consistency hazard
(Section 5) is a correctness+availability security issue; (b) password-strength policy is
minimal and should be strengthened; (c) the `password_reset_tokens` table is provisioned but
unprotected by any application logic -- DC-3B must implement it with the same hash-only /
single-use / query-string-reject / fail-closed-email disciplines above.

## 7. Required before customer delivery

Delivery-blocking (must close):
1. **Self-service password recovery (DC-3B backend)**. Without it, a customer who forgets
   their password is permanently locked out (no reset endpoint; manual DB reset is not an
   acceptable routine operation). Required before delivery.
2. **Multi-tenant password consistency (DC-3B backend)**. The first-copy-verify + one-copy-
   update inconsistency (Section 5) must be resolved with an explicit canonical rule and
   propagation. Required before delivery.
3. **Credential-lifecycle frontend (DC-3C frontend)**. At minimum: a setup-credential page
   that consumes `setupToken` from the URL and POSTs it in the body (so the emailed link
   works), a forgot-password entry, a reset-password page, and a "Forgot password?" link on
   `/login`. Required before delivery to end-users.

Minimum acceptable MVP path to demo before full reset-password UI:
- **Demo-only**: the existing backend onboarding chain (signup -> verify-email ->
  setup-credential) can be demonstrated via curl/Postman against a staging tenant, proving
  the credential lifecycle works end-to-end without the frontend pages. This is acceptable
  for an internal/stakeholder demo, **not** for customer delivery.
- **Smallest customer-facing slice**: implement the setup-credential frontend page first
  (DC-3C-min), because without it a new owner literally cannot set their password from the
  emailed link. Forgot/reset UI can follow, but the backend reset endpoint (DC-3B) must exist
  before any reset UI is useful.

## 8. Proposed DC-3B backend scope

Allowed files (additive; no edits to historical migrations; `017`/`026` immutable):
- New password-reset service: `backend/services/password_reset_service.py`
  - `request_reset(email)`: hash-only token issue; rate-limited; neutral response (no user
    enumeration); fail-closed email in production; uses the existing `password_reset_tokens`
    table (`tenant_onboarding.py:214-265`) and a new `record_password_reset_email` in
    `email_delivery.py`.
  - `consume_reset(token, new_password)`: `with_for_update()` + `used_at` + expiry/revoked
    check; **fan-out password update to every tenant schema where the email's user is active**
    (canonical rule, Section 5.4); all-or-nothing; fail-closed.
- New endpoints in `backend/api/v1/auth.py`: `POST /auth/forgot-password`,
  `POST /auth/reset-password` -- both must reject query-string tokens (mirror `auth.py:616-625`).
- New request/response schemas in `backend/schemas/auth_signup.py` (or a new
  `auth_reset.py`): `ForgotPasswordRequest {email}`, `ResetPasswordRequest {reset_token, password}`.
- Extend `email_delivery.py` with `record_password_reset_email` (fixed template; fail-closed).
- **Fix multi-tenant consistency**: in `owner_credential_service._ensure_owner_user` and the
  new reset service, update **all** active same-email tenant copies atomically; add a
  canonical-rule test. Consider tightening `find_user_across_tenants` so a stale copy cannot
  block a valid login (verify against any copy that matches, or guarantee copies are kept
  identical by fan-out).
- Strengthen password policy: add a shared `validate_password_strength` (complexity + breach
  list) used by both signup and setup/reset; enforce at the service layer (not Pydantic only).
- New tests: `backend/tests/test_dc3b_password_reset.py` covering request/consume, token
  expiry/used/revoke, query-string rejection, no-enumeration, multi-tenant fan-out,
  stale-copy login, and fail-closed email.

Forbidden files: historical migrations (`<= 030`), `017_retailer_prices.py`, frontend,
production compose/config/env, lockfiles. No `skip`/`xfail` to mask failures.

Migration strategy: the `password_reset_tokens` table already exists (migration 026), so
**no new migration is required for reset** unless additional columns are needed. If a new
migration is needed, it chains on the current single head; do not branch the Alembic graph.

Risks / stop conditions: (a) baseline drift; (b) head not single at
`031_legacy_tenant_reconciliation`; (c) multi-tenant fan-out cannot be made atomic without a
schema change requiring CTO approval; (d) password-reset email deliverability not configured
in the target environment.

## 9. Proposed DC-3C frontend scope

Allowed files (frontend only):
- New pages: `frontend/src/pages/auth/SetupCredentialPage.tsx` (consumes `setupToken` from
  URL `?setupToken=...`, POSTs in body to `/auth/onboarding/setup-credential`),
  `ForgotPasswordPage.tsx` (POST `/auth/forgot-password`), `ResetPasswordPage.tsx`
  (consumes reset token from URL, POST `/auth/reset-password`), and optionally
  `VerifyEmailPage.tsx`, `SignupPage.tsx`.
- New routes in `frontend/src/router/AppRouter.tsx`: `/setup-credential`, `/forgot-password`,
  `/reset-password` (public). Remove/fix the dead `/onboarding/create-tenant` navigation
  (`LoginPage.tsx:104`).
- New API client functions in `frontend/src/services/authService.ts`: `setupCredential`,
  `forgotPassword`, `resetPassword` (+ `verifyEmail`, `signup` if those pages are added).
- Add a "Forgot password?" link on `LoginPage.tsx` and `ClientLoginPage.tsx`.
- Password-strength meter UI aligned to the DC-3B policy.

Forbidden: backend, migrations, config, lockfiles (unless frontend deps genuinely require an
additive change, which must be CTO-approved).

Minimum demo slice: ship `SetupCredentialPage` first (unblocks the emailed link), then
forgot/reset.

## 10. Explicit non-goals

- This audit does NOT change any code, test, migration, frontend, config, or lockfile.
- This audit does NOT deploy, access the VPS, read `.env`/secrets, or print any
  password/JWT/token.
- This audit does NOT implement DC-3B/DC-3C; it only scopes them.
- This audit does NOT certify customer delivery (the verdict is NEEDS work, not PASS).
- This audit does NOT recommend rewriting history or editing migrations `017`/`026`.

## 11. Evidence (file / line references)

Backend:
- `backend/api/v1/auth.py:88` (signup), `:134` (verify-email), `:177` (onboarding/status),
  `:219` (login), `:246-250` (401 INVALID_CREDENTIALS), `:295` (select-tenant),
  `:332-343` (select-tenant user check), `:606-625` (setup-credential + query-string reject).
- `backend/crud/user.py:29-88` -- `find_user_across_tenants`; `:52-58` order-by created_at;
  `:73-77` first-copy verify + short-circuit return.
- `backend/services/onboarding_service.py:45` (24h TTL), `:101-104` (password length check),
  `:107-163` (verify_email_token), `:166-215` (complete_email_verified_onboarding),
  `:265-266` (signup fail-closed), `:354-358` (hash_token HMAC), `:366-368`
  (build_owner_setup_link), `:414-436` (retryable setup email), `:460-470` (HMAC + key guard).
- `backend/services/owner_credential_service.py:24` (24h TTL), `:130-181` (issue_setup_token;
  hash-only `:161`; existing-token idempotency `:148-154`), `:183-216` (consume_setup_token;
  `with_for_update` `:194`; `used_at` `:207`), `:218-242` (create_first_admin_rbac),
  `:291-327` (`_ensure_owner_user` -- single-schema update `:302-312`), `:396-405`
  (`_is_actionable_setup_token`).
- `backend/services/email_delivery.py:34-38` (fail-closed config check), `:72-107`
  (record_owner_setup_email; fixed template `:88-94`), `:123-139` (`_smtp_config_complete`),
  `:161-193` (`_send_smtp_email`); no reset template exists.
- `backend/models/tenant_onboarding.py:44` (PASSWORD_RESET_TOKEN_PURPOSE constant),
  `:156-211` (EmailVerificationToken), `:214-265` (PasswordResetToken -- exists, unused),
  `:268-304` (OnboardingStatusToken), `:307-349` (OwnerCredentialSetupToken).
- `backend/models/__init__.py:29,48` (PasswordResetToken export only).
- `backend/alembic/versions/026_tenant_onboarding_auth_contract.py:146-178` (password_reset_tokens DDL).
- `backend/schemas/auth_signup.py:11-44` (SignupRequest; password min 8 `:17`),
  `:69-74` (VerifyEmailRequest), `:94-99` (OnboardingStatusRequest), `:119-125`
  (OwnerCredentialSetupRequest; password min 8 `:123`).
- Backend-wide search: `forgot_password`/`reset_password`/`forgot-password`/`reset-password`
  -> 0 matches; `password_reset`/`PasswordReset` -> only model + migration + export.

Frontend:
- `frontend/src/router/AppRouter.tsx:53-56` (/login), `:59-62` (/client/login),
  `:64-67` (/select-workspace), `:68-72` (/invite/:code), `:162-165` (`*` catch-all -> 404).
- `frontend/src/pages/auth/LoginPage.tsx:104` (dead `/onboarding/create-tenant` nav),
  `:123-200` (no forgot-password link).
- `frontend/src/services/authService.ts:14-32` (only login/selectTenant/refresh/me/logout).
- No `setupToken`/`setup-credential`/`verify-email`/`forgot`/`reset`/`signup`/`register` page
  or route exists (repo-wide `frontend/src` search).

## 12. Final verdict

**NEEDS_DC3B_DC3C_BEFORE_DELIVERY**

The backend onboarding credential chain is implemented, secure, and runtime-proven, but
customer delivery is blocked by: (1) no self-service password recovery (the reset table is
dead code), (2) no frontend for any credential-lifecycle step (the setup-credential link
404s), and (3) a multi-tenant same-email password-consistency hazard that has already caused
a real 401 in DC-2B-R6. DC-3B (backend: reset endpoints + multi-tenant fan-out + password
policy) and DC-3C (frontend: setup-credential/forgot/reset pages + login link) are both
required before customer delivery. A curl-based demo of the existing backend chain is
acceptable for an internal demo only.
