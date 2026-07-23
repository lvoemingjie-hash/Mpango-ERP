# DC-12A-R2 Clickable Credential Email Links + Verify Email UX

| Field | Value |
|---|---|
| Date | 2026-07-23 |
| Task ID | DC-12A-R2 (Clickable Credential Email Links + Verify Email UX) |
| Classification | P1 DELIVERY BLOCKER |
| Base | `origin/product-dev-recovered @ 21df3b50f045f618fc932bae46bfb469c2cda099` |
| Branch | `opencode/dc12a-r2-clickable-credential-email-links-2026-07-23` |
| Verdict | `PASS_FOR_CTO_DC12A_R2_MERGE_REVIEW` |

## 1. Problem

Three credential email link builders generated relative paths
(`/verify-email?token=...` etc.) that email clients cannot resolve. The
frontend had no `/verify-email` page. Query-string tokens appeared in
reverse proxy access logs.

## 2. Changes

### 2.1 Backend

| File | Change |
|---|---|
| `backend/core/config.py` | Added `PUBLIC_FRONTEND_URL` field + validator (rejects credentials/query/fragment/path; strips trailing slash; production requires HTTPS) |
| `backend/services/onboarding_service.py` | All 3 link builders now generate absolute URLs with fragment tokens (e.g. `https://app.mpango.io/verify-email#token=...`) |
| `backend/services/password_reset_service.py` | Updated caller to pass `self.settings` to `build_password_reset_link` |
| `backend/tests/test_dc12a_r2_credential_email_links.py` | 14 tests: link builders, Settings validation, fragment vs query |

### 2.2 Frontend

| File | Change |
|---|---|
| `frontend/src/pages/auth/VerifyEmailPage.tsx` | New page: reads token from fragment, POSTs to `/auth/verify-email`, clears URL, shows processing/success/invalid/no-token states |
| `frontend/src/router/AppRouter.tsx` | Added `/verify-email` route + import |
| `frontend/src/services/authService.ts` | Added `verifyEmail` method |
| `frontend/src/pages/auth/SetupCredentialPage.tsx` | Reads `setupToken` from fragment (falls back to query); clears URL immediately |
| `frontend/src/pages/auth/ResetPasswordPage.tsx` | Reads `resetToken` from fragment (falls back to query); clears URL immediately |

### 2.3 Infrastructure

| File | Change |
|---|---|
| `docker-compose.prod.yml` | Added `PUBLIC_FRONTEND_URL=${PUBLIC_FRONTEND_URL:?...}` (fail-closed) |
| `.env.example` | Documented `PUBLIC_FRONTEND_URL` |

## 3. Absolute Link Examples (tokens fully redacted)

- Verification: `https://[REDACTED_ORIGIN]/verify-email#token=[REDACTED]`
- Setup: `https://[REDACTED_ORIGIN]/setup-credential#setupToken=[REDACTED]`
- Reset: `https://[REDACTED_ORIGIN]/reset-password#resetToken=[REDACTED]`

All tokens are in the URL fragment (`#`), never in the query string (`?`).
Fragments are not sent to the server/proxy, preventing access-log leakage.

## 4. Security Proof

- Token in fragment, not query: prevents proxy/gateway access-log exposure.
- URL cleared immediately via `history.replaceState` on all 3 pages.
- Token submitted via JSON body only (not query string).
- Backend API query-string token rejection unchanged (setup/reset endpoints).
- No token stored in localStorage/sessionStorage.
- Production requires HTTPS `PUBLIC_FRONTEND_URL` (fail-closed).
- No credentials/query/fragment/path in `PUBLIC_FRONTEND_URL` value.

## 5. Test Results

| Suite | Count |
|---|---|
| `test_dc12a_r2_credential_email_links.py` | 14 passed |
| `test_auth_regressions.py` + `test_route_authorization_policy.py` + `test_u6c` + `test_u6d` | 37 passed |
| `test_dc3b_credential_recovery_backend.py` | 16 passed |
| Frontend vitest | 91 passed |
| `pnpm build` | SUCCESS |

## 6. Compliance

- No migration, no DB writes, no deploy.
- No weakening of token expiry, single-use, hash-only, or API query rejection.
- No real secrets/emails/tokens/URLs in this report.
- `product-dev-recovered` and `platform-dev` not pushed.

## 7. Verdict

**PASS_FOR_CTO_DC12A_R2_MERGE_REVIEW**
