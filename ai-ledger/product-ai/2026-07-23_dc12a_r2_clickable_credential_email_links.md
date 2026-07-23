# DC-12A-R3 Clickable Credential Email Links + Verify Email UX

| Field | Value |
|---|---|
| Date | 2026-07-23 |
| Task ID | DC-12A-R3 (Credential Link Merge Blocker Correction) |
| Classification | P1 DELIVERY BLOCKER |
| Base | `origin/product-dev-recovered @ 21df3b50f045f618fc932bae46bfb469c2cda099` |
| Branch | `opencode/dc12a-r2-clickable-credential-email-links-2026-07-23` |
| R2 commit | `0ba0b29a` |
| Verdict | `PASS_FOR_CTO_DC12A_R3_MERGE_REVIEW` |

## R3 Corrections

### 1. Fixed self.settings NameError in module-level function

`complete_email_verified_onboarding` is a module-level function. It was
calling `build_owner_setup_link(issued.raw_token, self.settings)` but `self`
does not exist in module scope. Fixed to use the function-local `settings`
parameter. A regression test (`test_dc12a_r3_orchestration_link_regression.py`)
statically inspects the source to prove the fix and prevent regression.

### 2. Removed query-token fallback from all 3 frontend pages

All three credential pages (VerifyEmailPage, SetupCredentialPage,
ResetPasswordPage) previously had a backwards-compatibility query-string
fallback. R3 removes this: query-string tokens are rejected with a
controlled "Invalid Link" state and are NEVER submitted to any API.

### 3. Query rejection behavior

When a query-string token is present:
- URL is scrubbed via `history.replaceState`
- Controlled "Invalid Link" / "Invalid Link" state is shown
- `authService` is never called (zero API calls)

### 4. Updated CredentialLifecyclePages tests

Tests now use fragment tokens (`#setupToken=...`, `#resetToken=...`)
instead of query params. Added negative tests proving query tokens cause
zero API calls on setup and reset pages.

### 5. Added VerifyEmailPage tests

7 tests covering: processing state, fragment success, no-token state,
invalid token, query rejection (zero API calls), URL scrubbing,
no localStorage/sessionStorage storage.

### 6. Updated U6L orchestration test

`_setup_token_from_smtp_message` now reads the token from the URL fragment
(consistent with R3 link builders) instead of the query string.

### 7. Removed inaccurate compatibility claim

The R2 ledger claimed "query fallback for backwards compatibility." R3
removes this claim and the fallback entirely. Old email links with query
tokens will show a controlled invalid-link message.

## Changed Files (R3 delta from R2)

| File | Change |
|---|---|
| `backend/services/onboarding_service.py` | Fixed `self.settings` -> `settings` |
| `backend/tests/test_dc12a_r3_orchestration_link_regression.py` | New: 3 regression tests |
| `backend/tests/test_u6l_email_verified_onboarding_orchestration.py` | Updated: fragment token parsing |
| `frontend/src/pages/auth/VerifyEmailPage.tsx` | Removed query fallback; added query-rejected state |
| `frontend/src/pages/auth/SetupCredentialPage.tsx` | Removed query fallback; added queryRejected state |
| `frontend/src/pages/auth/ResetPasswordPage.tsx` | Removed query fallback; added queryRejected state |
| `frontend/src/tests/CredentialLifecyclePages.test.tsx` | Updated: fragment tokens; query rejection tests |
| `frontend/src/tests/VerifyEmailPage.test.tsx` | Updated: TS fixes, no-token assertion fix |
| `ai-ledger/product-ai/2026-07-23_dc12a_r2_clickable_credential_email_links.md` | This ledger |

## Test Results

| Suite | Count |
|---|---|
| `test_dc12a_r2_credential_email_links.py` | 14 passed |
| `test_dc12a_r3_orchestration_link_regression.py` | 3 passed |
| `test_u6l` + `test_u6i6` | 8 passed |
| `test_dc3b_credential_recovery_backend.py` | 16 passed |
| auth + route + u6c + u6d regression | 37 passed |
| Frontend vitest | 100 passed |
| `pnpm build` | SUCCESS |

## R4 Addendum: Strict Sensitive-Query Rejection

| Field | Value |
|---|---|
| Task ID | DC-12A-R4 Strict Sensitive-Query Rejection |
| Branch | `opencode/dc12a-r2-clickable-credential-email-links-2026-07-23` |
| Starting tip | `94ab98cdf2b05c0ae2f77ce1a133b1f836770e0a` |
| Delivery note | R4 changes exactly three frontend production credential pages, frontend/backend tests, and the ledger. No backend production code, migration, deploy, protected-branch, or secret/config value changes. |

### R4 Corrections

All three credential pages now reject sensitive query parameters before parsing
URL fragments. The rejection path scrubs the URL, shows the controlled Invalid
Link state, returns immediately, and makes zero API calls.

Sensitive query coverage:
- verify: `token`, `verificationToken`, `verification_token`
- setup: `setupToken`, `setup_token`, `password`
- reset: `resetToken`, `reset_token`, `token`, `newPassword`, `new_password`

Added mixed attack coverage:
- `/verify-email?token=query#token=fragment`
- `/setup-credential?setupToken=query#setupToken=fragment`
- `/reset-password?resetToken=query#resetToken=fragment`

Each mixed attack test proves the page displays Invalid Link, removes search and
hash from the browser URL, and makes zero API calls.

### R4 No-Token Contract

The VerifyEmailPage no-token test now waits for and asserts the specific
controlled no-token Invalid Link copy. The transient processing state is no
longer accepted as a passing result.

### R4 Static Source Guard Label

`test_dc12a_r3_orchestration_link_regression.py` is now explicitly labeled as a
static source guard. It protects the static link-construction regression only.
The actual orchestration runtime proof remains the U6L suite.

### R4 Validation Evidence

| Suite | Result |
|---|---|
| `pnpm vitest run src/tests/VerifyEmailPage.test.tsx src/tests/CredentialLifecyclePages.test.tsx` | 28 passed |
| `poetry run pytest tests/test_dc12a_r2_credential_email_links.py tests/test_dc12a_r3_orchestration_link_regression.py -q` | 17 passed |
| `poetry run pytest tests/test_u6l_email_verified_onboarding_orchestration.py tests/test_u6i6_onboarding_e2e_closeout.py -q` | 8 passed |
| `pnpm vitest run` | 114 passed |
| `pnpm build` | SUCCESS |

## Verdict

**PASS_FOR_CTO_DC12A_R4_MERGE_REVIEW**
