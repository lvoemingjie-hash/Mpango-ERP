# DC-12R1-S2: Supplier-Scoped Retailer Login + Private Portal Boundary

**Date:** 2026-07-28
**Branch:** `zcode/dc12r1-s2-supplier-scoped-retailer-login-2026-07-28`
**Base:** `origin/product-dev-recovered` @ `bb1b39f137fc7fc1de721b7131e80e5d89b1e2bc`
**Scope:** DC-12R1-S2 only (no S3/S4, no platform, no migrations, no deployment)

---

## Summary

Implemented the supplier-scoped retailer login endpoint and full frontend portal boundary. A retailer authenticates against a single supplier portal (`/retail/login?w=<code>`), receives a single contextual JWT, and is confined to `/client/**` routes. No cross-tenant discovery, no identity-phase handshake, no workspace picker.

---

## Changes

### Backend

| File | Change |
|------|--------|
| `backend/api/v1/client/auth.py` | Added `POST /login` endpoint (DC-12R1-S2). Validates wholesaler_code format (regex, no SQL). Resolves wholesaler via `tenant_registrations JOIN wholesalers`. Queries only the single tenant schema. Verifies user, binding (wholesaler_id + tenant_user_id, active), and `retailer_operator` role. Issues contextual access+refresh JWTs via `create_contextual_token` (reused, not modified). Returns tokens + user + retailer + wholesaler. All mismatches return identical neutral 401 `INVALID_CREDENTIALS`. Unexpected DB/runtime exceptions propagate (not swallowed). |
| `backend/schemas/retailer_credentials.py` | Added schemas: `RetailerLoginRequest`, `RetailerLoginTokens`, `RetailerLoginData`, `RetailerLoginUser`, `RetailerLoginRetailer`, `RetailerLoginWholesaler`, `RetailerLoginResponse`, `WHOLESALER_CODE_RE`. |
| `backend/tests/test_route_authorization_policy.py` | Added `/api/v1/client/auth/login` to `PUBLIC_ALLOWLIST` and exact-set assertion. |

### Frontend

| File | Change |
|------|--------|
| `frontend/src/pages/client/ClientLoginPage.tsx` | Rewrote: reads `?w=<code>` from URL. Missing/malformed code shows controlled invalid-portal state with zero API calls. Calls only `authService.retailerLogin` (→ `/client/auth/login`). Never calls `/auth/login` or `/auth/select-tenant`. Stores session via `retailerLogin()`. No supplier picker or comparison UI. |
| `frontend/src/router/guards.tsx` | Added `RetailerRoute` (only `retailer_operator` enters `/client/**`). Added `WholesalerRoute` (`retailer_operator` blocked from wholesaler ERP routes). Updated `ProtectedRoute` to redirect stale retailer sessions to their portal instead of `/login`. |
| `frontend/src/router/AppRouter.tsx` | Added `/retail/login` as canonical entry. Kept `/client/login` as compatibility redirect to `/retail/login`. Wrapped wholesaler ERP routes with `WholesalerRoute`. Wrapped client routes with `RetailerRoute`. |
| `frontend/src/services/authService.ts` | Added `retailerLogin()` method (→ `POST /client/auth/login`). |
| `frontend/src/services/api.ts` | Updated 401 interceptor: retailer sessions redirect to `/retail/login?w=<code>` instead of `/login`. Added `/client/auth/login` to non-retry endpoints. |
| `frontend/src/stores/authStore.ts` | Added `retailerPortalCode` state (persisted across logout). Added `retailerLogin()` action. `logout()` preserves portal code. `login()` (owner) clears portal code. |
| `frontend/src/types/auth.ts` | Added types: `RetailerLoginRequest`, `RetailerLoginTokens`, `RetailerLoginUser`, `RetailerLoginRetailer`, `RetailerLoginWholesaler`, `RetailerLoginData`, `RetailerLoginResponse`. |

### Tests

| File | Description |
|------|-------------|
| `backend/tests/test_dc12r1_s2_supplier_scoped_retailer_login.py` | Comprehensive backend tests: A+B isolation, neutral 401 for all mismatch types (wrong email/password/code, missing binding/role, pending user, inactive binding), identical 401 bodies, malformed code → 422, JWT is contextual with no tmap/available_tenants, no cross-supplier disclosure, refresh/me/logout preserve context, route access (client vs wholesaler), owner login unchanged. |

---

## Verification Checklist

- [x] `py_compile` — all 4 Python files pass
- [x] `git diff --check` — no whitespace errors
- [x] Mojibake scan — all files clean UTF-8
- [x] Vite build — 1279 modules, 6.84s, success
- [x] Vitest — 14 files, 123 tests, all green
- [x] No forbidden files touched (core/security.py, api/v1/auth.py, migrations, config, Docker, lockfile)
- [x] Migration head remains sole `036_retailer_mvp_identity`
- [x] GitNexus analyze + context/impact on all key symbols

---

## Verdict

**PASS_FOR_CTO_DC12R1_S2_REVIEW**
