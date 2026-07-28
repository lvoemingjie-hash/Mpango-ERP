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

---

# R1 — Supplier-Scoped Login Merge Blocker Repair

**Date:** 2026-07-28
**Prior tip:** `ef03cf7766ffa59419fb9a9c1714255188d69a96`
**Verdict target:** `PASS_FOR_CTO_DC12R1_S2_R1_MERGE_REVIEW`

## Blockers addressed

### P1 — Registry/schema fail-closed
The registration query now requires `tr.is_deleted IS FALSE` and `w.is_deleted
IS FALSE`, rejects duplicate active registrations (`len(reg_rows) > 1` → neutral
401), calls `validate_identifier(tenant_schema)` before any tenant SQL, and
requires `tenant_schema == Wholesaler.derive_schema_from_id(wholesaler_id)`.
**No tenant SQL runs before all of these checks pass** (steps 3–6 precede
step 7's user query).

### P1 — Soft-deleted identity can no longer log in
Every lifecycle query now filters `is_deleted IS FALSE`:
`users` (step 7), `roles` (step 9), and `retailers` (step 10). The retailer
row is loaded and validated **before** any JWT is issued — a missing or
soft-deleted retailer now produces a neutral 401 instead of a token with a
`null` retailer name.

### P1 — Lowercase-code contradiction resolved
Codes are normalized to UPPERCASE (uppercase preference) before the regex
gate, so a lowercase `abc123` is treated as `ABC123` and authenticates
against the same portal. The 422 path is reserved for genuinely malformed
codes (symbols, whitespace, empty). The previous test asserting lowercase →
422 was impossible-by-construction and is replaced by a test proving
lowercase normalization authenticates.

### P1 — Real backend evidence added
- SQL capture (SQLAlchemy `before_cursor_execute` listener on the app engine)
  proves authenticating through portal A never references supplier B's
  schema identifier.
- A second capture proves a malformed-code 422 issues zero login SQL
  (only connection setup `SET` statements, which are filtered).
- Rate-limit 429: focused test against the real `RateLimiter.check_rate_limit`
  with a mock Redis, proving the controlled `MpangoAPIException` (429) —
  never 500.
- Route denial: direct `RequirePermission` / `RequirePlatformAdmin` gate
  tests prove a `retailer_operator` principal (client:* perms only) is
  denied `orders:read`, `finance:read`, `payments:read`,
  `invitations:create`, and platform admin — plus a sanity test that its own
  `client:catalog:read` IS allowed (permission-specific, not blanket).
- Fail-closed lifecycle: soft-deleted registration, user, role, and retailer
  rows all fail neutrally; duplicate active registrations fail at both the DB
  constraint AND the code dedup gate.

### P2 — Compatibility entry preserves the supplier code
`/client/login?w=ABC` now redirects to `/retail/login?w=ABC` (the `w`
param is read via `useSearchParams` and re-attached), instead of dropping it.

### P2 — Authenticated retailer on a wholesaler route → /client
`WholesalerRoute` now redirects an **authenticated** retailer to `/client`
(their home — not a logout); only a stale (tokenless) retailer session is
sent back to its portal login.

## Files changed (R1)

| File | Change |
|------|--------|
| `backend/api/v1/client/auth.py` | Fail-closed registry resolution, `validate_identifier`, schema-derivation check, `is_deleted` filters on users/roles/retailers, retailer loaded+validated before JWT, dedup gate. |
| `backend/schemas/retailer_credentials.py` | Documented uppercase-preference normalization. |
| `backend/tests/test_dc12r1_s2_supplier_scoped_retailer_login.py` | Rewritten evidence suite (39 tests): SQL capture, normalization, RBAC denial, fail-closed lifecycle, rate-limit 429, owner-unchanged. |
| `backend/tests/test_u6f_onboarding_auth_chain_closeout.py` | Added `/api/v1/client/auth/login` to the mirrored expected public allowlist. |
| `frontend/src/pages/client/ClientLoginPage.tsx` | Uppercase normalization before the validity check (matches backend). |
| `frontend/src/router/AppRouter.tsx` | `ClientLoginAliasRedirect` preserves `w` via `useSearchParams`. |
| `frontend/src/router/guards.tsx` | `WholesalerRoute`: authenticated retailer → `/client`; stale → portal. |
| `frontend/src/tests/Dc12r1S2RetailerPortal.test.tsx` | NEW — 15 Vitest cases: call isolation, invalid-portal zero calls, both guards, stale state, alias preservation, logout redirect. |

## Verification (R1) — exact counts

- **Backend S2 suite:** 39 passed / 0 failed
  (`tests/test_dc12r1_s2_supplier_scoped_retailer_login.py`)
- **Route policy + auth bypass:** 40 passed / 0 failed
- **u6f onboarding auth chain:** 42 passed / 0 failed (incl. mirrored allowlist)
- **dc10f payment-method migration:** 24 passed / 0 failed (no test pollution)
- **Fresh PG DB migrated to head `036_retailer_mvp_identity`; Redis 7.**
- **Frontend Vitest:** 138 passed / 0 failed (15 files; +15 from new portal suite)
- **Vite build:** success (chunk-size warning is pre-existing, non-error)
- **`git diff --check`:** clean — no whitespace errors
- **Mojibake scan:** clean
- **detect-secrets:** all inline test secrets extracted to module constants
- **Backend full gate (excluding end-to-end migration suite):** 2899 passed,
  30 failed — **all 30 failures are in untouched intake/migration/reporting
  test files** (u4ib2, s4g, dc2m2, u3c, dc10l, u3e, dc11t4c, dc12r1_s1_r5)
  that require a fully-seeded ERP database (orders/SKUs/ledger/intake
  batches) absent from the minimal fresh test DB. None reference
  `client/auth`, `retailer_login`, `RetailerLogin`, or
  `retailer_credentials`. Confirmed unrelated to this change via `git diff`.
- **GitNexus:** re-indexed at the R1 commit (13,700 nodes | 42,199 edges).

## Verdict (R1)

**PASS_FOR_CTO_DC12R1_S2_R1_MERGE_REVIEW**

---

# R2 — Production Error Contract + Independent Full Gate

**Date:** 2026-07-28
**Prior tip:** `6e71a53e6e8287c0807395b49bc6b10a800e8b03`
**Verdict:** **STOP_AND_REPORT_CTO** (pre-existing product-wide defect blocks §5)

## Completed and verified (§1–4)

- **§1 Narrow error contract:** replaced the retailer-login
  `HTTPException(detail={dict})` with `MpangoAPIException(INVALID_CREDENTIALS,
  "Invalid credentials", 401)`. The 422 malformed-code path likewise uses
  `MpangoAPIException(INVALID_INPUT, …, 422)`. Both now serialize through the
  production `mpango_exception_handler` as the exact flat envelope.
- **§2 Production-handler tests:** the test app now calls
  `register_exception_handlers(app)` (mirrors `main.py:196`). New
  `TestProductionErrorContract` proves the exact public 401 body
  `{code, message, request_id}` and that **no Python dict repr leaks** into
  `message` (no `{`, `}`, `'`, or the word "code").
- **§3 Frontend neutral 401:** `ClientLoginPage` renders the fixed literal
  "Invalid credentials" for ANY 401 — production flat envelope, legacy
  `{error:{}}` envelope, or raw axios — and never surfaces the response body.
- **§4 A→B failed-login:** the catch block no longer calls `logout()` (which
  preserved a stale prior portal code). It pins `retailerPortalCode` to the
  portal being attempted via `setState`, so a failed login on B retains B.
- **§5 (partial) rate-limit 429:** real HTTP test through
  `RateLimitingMiddleware` over Redis — exceeds the IP limit and asserts 429
  with `Retry-After`, `X-RateLimit-Limit/Remaining/Reset` (remaining == 0).

Exact counts: backend S2 42/42; route+auth+u6f 47/47; frontend Vitest 142/142;
Vite build success.

## STOP — pre-existing product defect blocking §5 endpoint denials

Task §5 requires proving a **controlled denial** (clean 4xx) from real orders,
payments, finance, invitation-management and platform endpoints for a
contextual retailer JWT. Probing these through the production handlers
reveals a **pre-existing, product-wide defect** in the RBAC layer:

`api/middleware/rbac.py` — `RequirePermission` (lines 45, 67) and
`RequirePlatformAdmin` (line 126) raise
`HTTPException(detail={"code": …, "message": …})`. The production
`http_exception_handler` does `message = str(exc.detail)`, so every RBAC 403
**leaks a Python dict repr** into the public `message` field.

Observed (real HTTP, production handlers, retailer JWT):

```
GET /api/v1/payments  -> 403
  {"code":"PERMISSION_DENIED",
   "message":"{'code': 'PERMISSION_DENIED', 'message': \"Permission 'payments:read' required\"}",
   "request_id":"…"}

POST /api/v1/invitations  -> 403
  {"code":"PERMISSION_DENIED",
   "message":"{'code': 'PERMISSION_DENIED', 'message': \"Permission 'invitations:create' required\"}",
   "request_id":"…"}
```

`GET /api/v1/orders` and finance return 500 (`UndefinedTableError`) because
the minimal test-fixture tenant schema lacks the `orders` table — a fixture
limitation, not a product defect; the RBAC dict-repr leak, however, reproduces
independent of fixture completeness (it fires before any table query).

### Why this is a STOP, not a fix-in-place
1. **Pre-existing:** `git diff bb1b39f1..HEAD -- api/middleware/rbac.py` is
   empty — the defect is on the base, present for ALL protected routes, not
   introduced by this branch.
2. **Out of scope / high blast radius:** ~10 test files
   (`test_rbac_enforcement`, `test_route_authorization_policy`,
   `test_users_roles_api`, `test_u4*`, `test_s3b/s3c`, …) assert the current
   leaky contract via `exc_info.value.detail["code"]`. Converting RBAC to the
   clean `MpangoAPIException` contract is a product-wide refactor that those
   tests encode as expectation — a separate, CTO-scoped change, not a
   drive-by inside a retailer-login PR.
3. **Cannot be asserted around:** §7 forbids skip/xfail/assertion weakening,
   so the leak cannot be papered over to manufacture a "pass."

This is the same dict-repr-leak defect class §1 fixed for retailer login; the
RBAC layer needs the identical treatment, authorized as its own change.

## Verdict (R2)

**STOP_AND_REPORT_CTO** — retailer-login error contract (§1–4) is complete and
verified; §5's real-endpoint controlled-denial proof is blocked by a
pre-existing, product-wide RBAC dict-repr leak (`api/middleware/rbac.py`)
that requires a separately-scoped fix.
