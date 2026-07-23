# DC-12R0 Retailer Role and Capability Truth Audit

> **Revision R1 (2026-07-23).** This document supersedes the initial DC-12R0 issue. R1 corrects the
> retailer journey, adds the missing "no login-capable retailer identity" P1 finding, reclassifies the
> `available_tenants` disclosure as a single P1 commercial/privacy blocker (no P0), states the
> platform-operator lifecycle truth accurately, normalizes all CSV statuses, and reconciles report vs
> CSV severity totals to a zero gap. Tests were re-run in a worktree-local Poetry environment with
> lockfile-faithful dependencies (see §12).

## AI Role

Third-party independent code reviewer (read-only source audit + disposable local validation + docs-only delivery).

## Verdict

**PASS_FOR_CTO_DC12R1_IMPLEMENTATION_PLANNING**

No genuinely confirmed P0 (cross-tenant *data* exposure, retailer-token escalation into wholesaler/platform
administration, or finance regression) was found. The backend tenant-isolation *enforcement* layer is
sound and finance integrity is fully preserved. However, the audit found **eleven findings (0×P0, 6×P1,
3×P2, 2×P3)** that block retailer MVP delivery and must be addressed in DC-12R1. The most consequential
is **F-01**: invitation acceptance creates **no login-capable retailer identity**, so the
login → order → payment self-service loop is currently **unproven/broken at the first step**.

Severity totals in this report and in the companion CSV are identical (see §8 and the CSV header):
**P0=0, P1=6, P2=3, P3=2, total=11.**

---

## 1. Exact Base SHA and Branch

- Base branch: `origin/product-dev-recovered`
- **Base SHA: `757aef26b116370a066076ad6a17284a4c6288b9`** (verified equal to `origin/product-dev-recovered`
  after `git fetch` — Hard Rule #2 satisfied)
- Working branch: `opencode/dc12r0-retailer-role-capability-truth-audit-2026-07-23`
- R0 tip: `e12fb78577d6896f5fa5659555b5ee4c8aa3c731`
- R1 tip: the R1 correction commit at the head of this branch (SHA recorded in the push output; the
  base..HEAD changed-file proof in §13 lists exactly the two deliverables).
- Work mode: docs-only. No production code, tests, migrations, config, lockfile, frontend source, or
  deployment files were modified.

---

## 2. Current Architecture and Execution-Flow Map

Mpango ERP is a FastAPI + SQLAlchemy (async) multi-tenant backend with a React/TypeScript frontend.
Tenant isolation is **schema-per-tenant** (DR-001): each wholesaler owns a private PostgreSQL schema
named `t_<32-hex>`; cross-tenant tables live in the `public` schema.

**Request execution flow (authenticated business route):**

1. `AuthenticationMiddleware.dispatch` (`backend/api/middleware/auth.py:31-122`) runs on every request.
2. `JwtAuthStrategy.authenticate` (`backend/auth/strategies/jwt.py:21-25`) extracts the Bearer token and
   calls `resolve_auth_context` (`backend/api/context/auth.py:41-50`) → decodes + signature-verifies the
   JWT (`backend/core/security.py:208-234`).
3. `resolve_tenant_context` (`backend/api/context/tenant.py:80-113`) derives `tenant_schema` **solely
   from the signed JWT claim** `token.tenant_schema`, opens a session, and runs
   `SET LOCAL search_path TO "<tenant_schema>", public`. Identity-only tokens (no tenant claim) yield
   `None` and skip tenant attachment (`backend/auth/strategies/jwt.py:30-31`).
4. The middleware sets the request-scoped context var via `set_current_tenant(tenant_id, tenant_schema)`
   (`backend/api/middleware/auth.py:54-57`) which arms the **global ORM tenant filter**
   (`backend/db/tenant_filter.py:185-204`). A fail-safe check raises 500 if `tenant_schema` is empty
   after auth (`backend/api/middleware/auth.py:59-72`).
5. Route-level authorization is enforced by `RequirePermission(code)`
   (`backend/api/middleware/rbac.py:12-75`), `RequirePlatformAdmin` (`:78-137`), or the P10 platform
   guard (`backend/api/v1/platform/p10/guard.py:124-175`).
6. On every ORM SELECT/UPDATE/DELETE, the `do_orm_execute` event listener injects
   `WHERE tenant_id = :tenant_id` (or `wholesaler_id = :uuid`) server-side
   (`backend/db/tenant_filter.py:148-174`). Bypass requires explicit `run_as_system(reason=...)` or
   `.execution_options(ignore_tenant=True)`.
7. The `finally` block always clears context + resets tenant (`backend/api/middleware/auth.py:115-124`).

**Two-phase authentication model:**

- **Identity phase** — `POST /auth/login` returns an *identity* JWT (no tenant context) carrying a signed
  `tmap` (`{tenant_id: tenant_local_user_id}`) plus an `available_tenants` list in the response body.
  Login is resolved by `find_user_across_tenants` (`backend/crud/user.py:29-100`), which scans each
  tenant schema's **`users` table** by email and verifies that table's `password_hash`.
- **Context phase** — `POST /auth/select-tenant` upgrades the identity JWT to a *contextual* JWT
  (carries `tenant_id` + `tenant_schema`) after verifying the requested tenant is in `tmap` and the
  user is active in that schema.

> **Critical consequence for retailers (F-01):** because login scans tenant **`users`** tables, any
> party without a `users` row in a tenant schema — including every retailer created by invitation
> acceptance — **cannot log in at all**. See §4 and F-01.

**Role taxonomy (actual, not the audit's assumed names):** the codebase has **no**
`retailer_operator` / `wholesaler_owner` / `wholesaler_admin` / `wholesaler_staff` constants. Roles are
free-form strings stored per-tenant in `roles.name`. Observed values: `super_admin` (global, JWT-borne),
`admin` (tenant, the BI admin-bypass trigger `backend/core/governance/roles.py:94`), plus `finance`,
`sales`, `warehouse`, `viewer` (BI baselines). The MVP retailer capability set is expressed implicitly
through `/api/v1/client/*` routes guarded by `resolve_client_identity`, **not** by a named
`retailer_operator` role.

---

## 3. Actor and Permission Truth Table

| Actor | How materialized | Tenant context source | Can cross tenants? | Evidence |
|---|---|---|---|---|
| Wholesaler owner/admin | tenant `users` row with `admin` role + all perms | contextual JWT `tenant_id` | No — single tenant per session | `backend/scripts/create_wholesaler.py:137,214-223`; `backend/api/middleware/rbac.py:12-75` |
| Wholesaler operational staff | tenant `users` row with scoped role (finance/sales/warehouse/viewer) | contextual JWT `tenant_id` | No | `backend/core/governance/roles.py:48-64` |
| **Retailer Operator MVP** | `public.retailers` + `public.wholesaler_retailer_bindings` only — **no tenant `users` row, no credential** (F-01) | n/a — cannot authenticate today | n/a | `backend/services/retailer_service.py:53-83`; `backend/crud/user.py:29-100` |
| Platform operator | `public.platform_operators` table + model exist (schema groundwork); **not yet wired into the P10 guard**, which keys off a shared secret / identity-only super_admin JWT / test-override | identity JWT (super_admin) | Yes by design (platform scope) | `backend/alembic/versions/034_platform_operators.py`; `backend/models/platform_operator.py:29-120`; `backend/api/v1/platform/p10/guard.py:13-31,61-84` |
| Human OPS / DB operator | direct DB access / platform console | n/a | n/a | out of app-code scope |
| Future AI agent identity | **does not exist** | n/a | n/a | grep: no agent identity/role — correctly deferred |

**Permission model:** string codes (`orders:read`, `payments:create`, `finance:read`, `exports:create`,
`system:admin`, `platform:admin`, etc.) granted via `roles ↔ permissions` join in each tenant schema.
`RequirePermission` collects `perm.code` from `user.roles[].permissions[]` and checks membership
(`backend/api/middleware/rbac.py:60-66`). `super_admin` with an identity-only token bypasses all checks
(`backend/api/middleware/rbac.py:38-39`).

---

## 4. Invitation-to-First-Order Journey (Corrected)

1. **Wholesaler creates invitation** — `POST /api/v1/invitations` (`backend/api/v1/invitations.py:31-57`)
   requires `invitations:create`, derives `wholesaler_id` from `token.tenant_id`, generates
   `code = secrets.token_urlsafe(24)` (`backend/services/invitation_service.py:32`), persists
   `status="active"`. The `code` is returned to the wholesaler in the response body for out-of-band
   delivery. **No email-send step** exists in the service.
2. **Retailer accepts** — `POST /api/v1/retailers/register` (`backend/api/v1/retailers.py:50-80`, public)
   calls `RetailerService.register_with_invitation` (`backend/services/retailer_service.py:25-85`), which
   validates the code (exists → `status == "active"` → not expired → phone matches) and then creates
   **exactly two records**:
   - a `public.retailers` row (looked up or created **by phone**, `:53-61`), and
   - a `public.wholesaler_retailer_bindings` row with `outstanding_balance = 0.00` (`:63-76`).
   It then calls `mark_used` (`:78-83`).
3. **Retailer attempts to log in** — `POST /auth/login` → `find_user_across_tenants`
   (`backend/crud/user.py:29-100`) scans each tenant schema's `users` table for the email and verifies
   that table's `password_hash`.

**The journey is broken at step 3.** Invitation acceptance creates a *business entity* (`retailers`) and
a *relationship* (`bindings`) but **no tenant-schema `users` row, no password hash, and no credential
setup token**. There is no code path — in `retailer_service.py`, `onboarding_service.py`, or elsewhere —
that provisions a login-capable identity for an invited retailer. (`onboarding_service.create_signup_registration`
at `backend/services/onboarding_service.py:266-320` creates a `TenantRegistration` for **wholesaler owner
signup** with `company_name`/`business_type`; it is a different flow and does not serve retailers.)

Therefore `find_user_across_tenants` returns `(None, [])` for a registered retailer → login returns
`INVALID_CREDENTIALS` 401 → the retailer can never obtain an identity or contextual JWT → the entire
`/api/v1/client/*` self-service surface (browse, order, view history) is **unreachable by the retailer**,
and the **login → order → payment self-service loop is unproven**. This is the single most material gap
in the retailer MVP and is recorded as **F-01 (P1)**. (The `/api/v1/client/*` endpoints and their
isolation guards are themselves implemented and tested as wholesaler-side capabilities, but no retailer
identity can currently reach them.)

---

## 5. Same-Email Multi-Wholesaler Truth

- **The unified-identity key for retailers is `phone`, not `email`.** `public.retailers.phone` is
  globally unique (`backend/models/retailer.py:16`; migration `002_phase_b2_invitation_binding.py:40,43`).
  Registration looks up or creates the retailer **by phone**
  (`backend/services/retailer_service.py:53-61`); `email` is optional, non-unique metadata
  (`backend/models/retailer.py:32-35`). There is no `get_by_email` in any retailer repository.
- **Tenant-local users ARE keyed by email.** `find_user_across_tenants` scans tenant schemas for a
  matching `email` and verifies `password_hash` (`backend/crud/user.py:29-100`).
- **`tmap` resolves the correct per-tenant `user_id`.** When the same email has different `user_id`s
  across tenants, the signed `tmap` lets `/select-tenant` resolve the right copy
  (`backend/api/v1/auth.py:360-371`). `tmap` is signed but not encrypted — integrity-only,
  client-decodable by design (`backend/core/security.py:54-63`).

**Authoritative identity-key decision required for DC-12R1 (F-02).** The codebase currently uses two
different keys for the "same identity" concept — **phone** for the retailer business entity and
**email** for tenant login users — and the in-session client identity resolver looks up the retailer
**by email** (`backend/api/v1/client/dependencies.py:76-92`). DC-12R1 must pick one authoritative key
and make registration, client-identity resolution, binding lookup, and (once F-01 is fixed) retailer
login all use it. Recommendation: adopt **phone** as the retailer identity key (already the global unique
key) and stop resolving client identity by the non-unique email. This decision is a prerequisite for
both F-01 and F-02.

---

## 6. Relationship Termination Truth

- The binding model documents only `active|inactive` (`backend/models/binding.py:42-48`). There is
  **no `terminated`/`suspended` value on the binding**, no `terminate`/`deactivate` endpoint in
  `api/v1/retailers.py` or `services/retailer_service.py`, and no audit hook on status change. `suspended`
  exists only at the wholesaler/tenant level (`backend/models/wholesaler.py:65,72-75`).
- **Post-termination block:** the `status = 'active'` gate appears in every new-business path —
  wholesaler order create (`backend/api/v1/orders.py:343-348`), client identity resolution
  (`backend/api/v1/client/dependencies.py:97-104`), and pricing (`backend/api/v1/pricing.py:170`).
- **Historical retention:** no cascade delete/hiding on inactivation; orders/payments are soft-delete
  models and remain queryable; receivables filter `is_deleted IS FALSE`, not `status`
  (`backend/services/receivables_service.py:80-95`).

---

## 7. Current Frontend Entry/Navigation Truth

The frontend (`frontend/src`) provides three route trees (`frontend/src/router/AppRouter.tsx`):

- **Wholesaler ERP** (`/`, `/orders`, `/inventory`, `/skus`, `/retailers`, `/pricing`, `/finance`,
  `/payments`, …) under `MainLayout`.
- **Retailer "Client App"** (`/client`, `/client/products/:id`, `/client/orders`, `/client/orders/new`,
  `/client/orders/:id`) under `ClientLayout` (`AppRouter.tsx:104-113`). Pages exist for product browse
  (`ProductListPage.tsx:16`), detail, order-create (`CreateOrderPage.tsx:16`), order history
  (`OrderListPage.tsx:25`), and order detail/cancel (`OrderDetailPage.tsx:16`).
- **Platform admin** (`/platform/*`) under `PlatformRoute`.

**Workspace picker:** `LoginPage.tsx:40-108` branches on `available_tenants.length`. The picker
(`WorkspaceSelectorPage.tsx:14`) renders each tenant's `name` and `code`. **Retailer login
(`ClientLoginPage.tsx:42-53`) hard-takes the first tenant** with no picker.

**Token storage:** localStorage via Zustand `persist` (`frontend/src/stores/authStore.ts:28-60`,
key `mpango-auth`); a single `accessToken`/`refreshToken` slot is reused (identity token is a transient
local variable by design).

**Frontend gaps (F-05, F-06):** no retailer payments/outstanding-balance page; no role-based route guard
separating `/client/*` from the wholesaler tree — both sit under the same auth-only `ProtectedRoute`
(`frontend/src/router/guards.tsx:8-16`). No `'retailer'` role string exists anywhere in frontend source.

---

## 8. Findings (P0/P1/P2/P3) with exact file:line evidence

> These 11 findings are the **single source of truth** shared with the companion CSV. Severity totals:
> **P0 = 0, P1 = 6, P2 = 3, P3 = 2 (total 11).** The CSV `gap_severity` column uses the same counts.

### F-01 [P1] Invitation acceptance creates no login-capable retailer identity
`register_with_invitation` (`backend/services/retailer_service.py:25-85`) creates only a
`public.retailers` row (by phone) and a `public.wholesaler_retailer_bindings` row. It does **not**
create a tenant-schema `users` row, a `password_hash`, or any credential-setup token. Login
(`backend/crud/user.py:29-100`) scans tenant `users` tables, so a registered retailer gets
`INVALID_CREDENTIALS` and can never authenticate. The login → order → payment self-service loop is
**unproven/broken at step 1**. No test asserts a retailer can log in after accepting an invitation.

### F-02 [P1] Identity-key mismatch (phone vs email) — authoritative decision required
Registration keys on phone (`backend/services/retailer_service.py:53-61`; `backend/models/retailer.py:16`);
login and client-identity resolution key on email (`backend/crud/user.py:64-81`;
`backend/api/v1/client/dependencies.py:76-92`). A retailer without email, or two retailers sharing an
email, will break or mis-resolve. DC-12R1 must pick one authoritative key (recommend phone) and unify
all lookups. Prerequisite for F-01.

### F-03 [P1] available_tenants discloses every linked wholesaler's name (commercial/privacy blocker)
`POST /auth/login` returns `available_tenants` with `{id, code, name}` for **every** verified tenant
(`backend/api/v1/auth.py:271-278`; `backend/schemas/auth.py:34-38`). The endpoint takes only
`email + password` and ignores any `tenant_code`, so it cannot be constrained to one wholesaler entry.
A retailer belonging to A and B learns both names on any login — a commercial/privacy violation of
Product Truth and Mandatory Scenarios #2/#10. The frontend propagates this
(`frontend/src/pages/auth/WorkspaceSelectorPage.tsx:98-99`). The signed `tmap` itself is correctly
absent from the response body; the leak is the `name`/`code` list. (Reclassified from the initial
issue's P0 to a single consolidated P1: it is a delivery blocker, not a confirmed cross-tenant *data*
exposure at the enforcement layer.)

### F-04 [P1] Invitation tokens: no revoke, optional expiry, single-use TOCTOU race
`status='revoked'` is enumerated (`backend/models/invitation.py:33-39`) but **never written**; there is
no `revoked_at` column and no revoke endpoint/service method. `expires_at` is nullable
(`backend/models/invitation.py:54-58`), so invitations without it **never expire**
(`backend/services/retailer_service.py:47-48` only rejects when set and past). Single-use has a TOCTOU
race: `register_with_invitation` reads `status` then later calls `mark_used` (`:44-45` vs `:78-83`)
without `SELECT … FOR UPDATE`. No test covers NOT_ACTIVE/EXPIRED/PHONE_MISMATCH/revoked/double-use or
concurrent acceptance.

### F-05 [P1] No retailer-facing payments / outstanding-balance / statement page
Grep across `frontend/src/pages/client`, client services, and client types returned **zero** matches for
`outstanding|balance|payment`. `ClientLayout`'s bottom nav exposes only Products + Orders
(`frontend/src/components/layout/ClientLayout.tsx:9-12`). A retailer cannot see amount owed or payment
history. The backend `/finance` endpoints are wholesaler-scoped (`finance:read`).

### F-06 [P1] No frontend role-based route guard (retailer vs wholesaler)
`/client/*` and the wholesaler `/` tree share the same auth-only `ProtectedRoute`
(`frontend/src/router/guards.tsx:8-16`) which checks only `accessToken` presence. There is no
`RetailerRoute`/`WholesalerRoute` and no `'retailer'` role string in frontend source. A retailer user
can navigate to `/orders`, `/inventory`, etc.; success depends entirely on backend 403s. Defense-in-depth
weakness, not a backend isolation hole.

### F-07 [P2] Relationship termination is not a first-class lifecycle state
See §6. No dedicated endpoint, no audit hook, no test for "terminated retailer blocked." Only a status
string flip is possible via direct DB edit; the `status='active'` gate is the sole enforcement.

### F-08 [P2] Invitation pre-flight lookup exposes the token in a URL path segment
`GET /api/v1/invitations/{code}` (`backend/api/v1/invitations.py:60-88`) places the token in the URL path
— visible in access logs, browser history, referrers. It is a validation lookup, not the consume endpoint
(consume is `POST /retailers/register` with the code in the body), so impact is limited, but it is below
the "token must not travel in URLs" bar. No query-string `?code=` route exists (good).

### F-09 [P2] Wholesaler-specific deep-link is client-side only
`?tenant_code=` is consumed by the frontend (`frontend/src/pages/auth/LoginPage.tsx:24-26`) to
auto-resolve a tenant, but the backend `/auth/login` does not accept or enforce `tenant_code`, so it
cannot reduce `available_tenants` to the requested wholesaler (compounds F-03).

### F-10 [P3] TokenPayload.is_identity_only uses OR semantics
`backend/core/security.py:65-68` — `tenant_id is None OR tenant_schema is None`. The platform boundary
correctly works around this with a strict AND check (`backend/api/middleware/rbac.py:121-123`), but the
OR semantics remain a footgun for future consumers.

### F-11 [P3] Dead onboarding route
`frontend/src/pages/auth/LoginPage.tsx:108` navigates to `/onboarding/create-tenant`, which is not
registered in `AppRouter` → NotFoundPage.

---

## 9. Untested or Environment-Blocked Behaviors

**R1 re-ran the three required suites in a worktree-local Poetry environment with lockfile-faithful
dependencies** (see §12). All now PASS; the prior R0 `test_dc3b` failures were an artifact of the
parent/global venv's `bcrypt 5.0.0` and are **not** attributable to product code. No behavior is
classified as blocked by a parent/global environment.

**Untested branches (no test coverage):**

- A retailer logging in after accepting an invitation (the F-01 gap — currently impossible by design).
- Invitation `INVITATION_NOT_ACTIVE`, `INVITATION_EXPIRED`, `INVITATION_PHONE_MISMATCH`, revoked, and
  double-use rejection paths (`backend/services/retailer_service.py:44-51`) — `test_dc1g` covers only
  the happy path.
- Concurrent invitation acceptance (F-04 TOCTOU).
- "Terminated retailer cannot transact" (F-07).
- F-03 multi-wholesaler name disclosure (no test asserts a retailer does *not* learn of others).

---

## 10. Proposed DC-12R1 / R2 Implementation Slices

### DC-12R1 (must precede retailer MVP)

- **R1-S1 [fixes F-01]: Retailer login identity.** On invitation acceptance (or via a retailer
  credential-setup token mirroring the wholesaler owner setup token), create a tenant-schema `users` row
  with a password hash so `find_user_across_tenants` can authenticate the retailer. Add an end-to-end
  test: accept invitation → log in → select tenant → create order → pay.
- **R1-S2 [fixes F-02]: Authoritative identity key.** Adopt phone (or an explicitly chosen key) as the
  single retailer identity key; unify registration, client-identity resolution, binding lookup, and the
  new retailer login. Prerequisite for R1-S1.
- **R1-S3 [fixes F-03, F-09]: Tenant-scoped login.** Accept an optional `tenant_code` on `/auth/login`;
  when present, restrict `available_tenants` to that single tenant and do not disclose others. Preserve
  unified identity as a security capability without exposing the relationship graph.
- **R1-S4 [fixes F-04]: Invitation hardening.** Add `revoked_at` + revoke endpoint; make `expires_at`
  non-null with a sane default; race-safe single-use (`SELECT … FOR UPDATE` or conditional
  `UPDATE … WHERE status='active'`); tests for all rejection branches + concurrency.
- **R1-S5 [fixes F-05]: Retailer balance page.** Add `/api/v1/client/finance` (scoped to the retailer's
  own binding in the current tenant) + a frontend page under `/client`.
- **R1-S6 [fixes F-06]: Frontend role/route guards.** Introduce `RetailerRoute`/`WholesalerRoute` and a
  `'retailer'` role concept; prevent cross-navigation between `/client/*` and the wholesaler tree.

### DC-12R2 (post-MVP / experience)

- **R2-S1 [fixes F-07]:** First-class relationship termination (endpoint, audit, tests, retention).
- **R2-S2 [fixes F-08]:** Move invitation pre-flight to a body-POST lookup or document the log exposure.
- **R2-S3 [fixes F-10, F-11]:** Tighten `is_identity_only` to AND semantics; repair the dead onboarding
  route.
- **R2-S4:** Role expansion scaffolding (`retailer_buyer`, `retailer_inventory`, `retailer_finance`)
  preserving the boundaries documented here.
- **R2-S5:** Wire the `platform_operators` lifecycle (operator-row login, setup-token redemption,
  revoke/lock) into the P10 guard so it no longer relies solely on a shared secret / super_admin JWT.

---

## 11. Mpango Is Not a Retailer Comparison Platform

**Explicit statement:** Mpango ERP is a **wholesaler-centric private B2B channel operating system**. It
is **not** a retailer comparison platform, a supplier directory, a cross-wholesaler search/aggregation
product, a price-comparison tool, or a shared-cart/merged-reporting product.

Confirmed by the source audit:

- No cross-wholesaler product search, catalog aggregation, or price-comparison API. SKU and price reads
  are scoped to the single current tenant.
- The unified identity is a **security capability** (one credential, many private relationships), not a
  product feature for retailers to browse suppliers. The current `available_tenants` disclosure (F-03)
  is a **bug to be fixed**, not the intended product behavior.
- One session holds exactly one wholesaler tenant context (contextual JWT carries one `tenant_id`).

---

## 12. Finance Preservation Results & Local Validation (worktree-local Poetry env)

**Dependency provenance (R1, worktree-local Poetry environment):**

- Created with `poetry env use` Python 3.12.10, then `poetry install --sync` (exit 0).
- Installed versions match the target lockfile exactly: **bcrypt 4.0.1**, **passlib 1.7.4**,
  Python 3.12.10. `bcrypt.__about__` is present (the attribute absent in bcrypt 5.x that broke R0).
- This is distinct from the parent/global venv (Python 3.14, bcrypt 5.0.0) used in the initial R0 run.

**Finance Preservation Gate — all PASS:**

1. Migrations 032–035 present (`032_payment_method_integrity`, `033_order_status_enum_reconciliation`,
   `034_platform_operators`, `035_receivable_collection_integrity`).
2. Single Alembic head: `035_receivable_collection_integrity (head)`; `035.down_revision = "034_platform_operators"`.
   Full `alembic upgrade head` succeeded on the disposable PG16 DB.
3. Payment-method set unchanged: `cash | transfer | credit` only
   (`backend/schemas/payment.py:11-14`; re-validated at `backend/api/v1/orders.py:104-123`).
4. Idempotency + duplicate-transfer protection present
   (`backend/api/v1/orders.py:602-652,732-739`; `backend/repositories/payment_repository.py:13-51`).
5. No negative outstanding balance: DB CheckConstraint `ck_wrb_outstanding_balance_non_negative`
   (`backend/models/binding.py:19-22`) + runtime guard `RECEIVABLE_BALANCE_UNDERFLOW`
   (`backend/services/payment_service.py:186-212`).
6. No over-collection / cross-tenant receivable: `ORDER_ALREADY_PAID` / `PAYMENT_EXCEEDS_REMAINING`
   (`backend/api/v1/orders.py:670-691`); receivables filter `WHERE wholesaler_id = :wholesaler_id`
   (`backend/services/receivables_service.py:80-95,278`).
7. No Finance regression introduced — docs-only delivery.

**R1 required-suite results (disposable PG16 @127.0.0.1:55128 + Redis7 @127.0.0.1:55129,
worktree-local Poetry env, bcrypt 4.0.1 / passlib 1.7.4):**

| Suite | Result |
|---|---|
| `test_dc3b_credential_recovery_backend.py` | ✅ **16 passed** (was 16 errors in R0 parent venv — confirmed environment artifact, now resolved) |
| `test_auth_regressions.py` + `test_auth_bypass.py` | ✅ **7 passed** |
| `test_route_authorization_policy.py` | ✅ **35 passed** |

(R0's broader 12-suite validation — tenant isolation, global filter, dc1g, pricing, orders, payments,
finance, exports — all PASS; details in the R0 run retained in the disposable worktree logs. The R0
`test_dc3b` "environment-blocked" note is superseded: with lockfile-faithful deps it passes.)

Raw R1 log: `_dc12r0_test_logs/r1_required_tests.log` (git-ignored, retained only in the disposable
worktree).

---

## 13. Changed-File Proof, Secret Scan, GitNexus Evidence

**Changed-file proof (docs-only), base `757aef2` → R1 HEAD:**

Only files under `ai-ledger/product-ai/` are touched. Zero production code, tests, migrations, config,
lockfile, frontend source, or deployment files changed. `git diff --name-only 757aef2..HEAD` lists only
the two deliverables; no `.py`, `.tsx`, `.ts`, `.sql`, `.yaml/.yml`, `.toml`, `.json`, `.lock`, `.env`,
or `.sh` file appears. Disposable artifacts (`.env.dc12r0r1`, `_dc12r0_test_logs/`, the Poetry env) are
git-ignored and not committed (`git check-ignore` verified).

**`git diff --check`:** clean (no whitespace errors).

**Secret scan:** `detect-secrets scan` on both deliverables returns `"results": {}` (no secrets). No
real tokens, DB URLs, or production credentials appear; the only DB/Redis references point to disposable
loopback containers and are not committed.

**ASCII/mojibake scan:** both deliverables are UTF-8 with no U+FFFD replacement characters (automated
scan). The report intentionally contains CJK product-truth quotations (legitimate, not mojibake).

**GitNexus evidence:**

- `npx gitnexus analyze` indexed the worktree repository successfully (13,203 nodes, 40,448 edges, 844
  clusters, 300 flows).
- `npx gitnexus status` reports `✅ up-to-date` (indexed commit = current commit).
- GitNexus 1.5.3 has **no `detect_changes` subcommand** (only `impact <target>` symbol blast-radius).
  The docs-only / no-affected-execution-flow guarantee is therefore proven directly from git: because
  no code file changed, no indexed symbol or flow can be affected.

---

## Mandatory Scenarios — Truth Table

| # | Scenario | Truth | Evidence |
|---|---|---|---|
| 1 | R has relationships with A and B | Possible: one phone → one `retailers` row; two `wholesaler_retailer_bindings` rows | `backend/services/retailer_service.py:53-76`; migration `002` unique `(wholesaler_id, retailer_id)` |
| 2 | From A's entry, B's existence must not be disclosed | **VIOLATED (F-03)** | `/auth/login` returns `available_tenants` for all verified tenants incl. names (`backend/api/v1/auth.py:271-278`) |
| 3 | A's token reading B's SKU/price/order/payment/export must fail | **HELD** (enforcement layer) | contextual JWT carries one `tenant_id`; ORM filter + search_path + binding guard (`backend/db/tenant_filter.py:148-174`; `backend/api/v1/client/dependencies.py:97-115`) |
| 4 | B's data must not appear in A's API/browser state/cache/logs | **HELD at runtime; browser risk via F-03** | no cross-tenant query path; login response carries B's name to the browser |
| 5 | After terminating A, R cannot initiate new A business | **HELD (gated)** | `status='active'` gate on all create paths (`backend/api/v1/orders.py:343-348`; `backend/api/v1/client/dependencies.py:97-104`) |
| 6 | History retained after termination | **HELD** | soft-delete only; receivables filter `is_deleted IS FALSE` not status (`backend/services/receivables_service.py:80-95`) |
| 7 | Retailer token must not reach wholesaler/platform admin | **HELD (backend); frontend weak (F-06)** | `backend/api/middleware/rbac.py:78-137` strict identity-only platform gate; client dep rejects identity-only tokens |
| 8 | Invitation token expiry/single-use/revoke/query-string rejection | **PARTIAL (F-04)** | expiry optional; single-use TOCTOU race; **no revoke**; no query-string route (good) |
| 9 | Same-email → correct per-tenant `user_id` mapping | **HELD** (for users that exist) | signed `tmap` resolves per-tenant user_id (`backend/api/v1/auth.py:360-371`); note retailers have no `users` row (F-01) |
| 10 | No full supplier-relationship graph via public response or client-readable token | **VIOLATED (F-03)** | `available_tenants` exposes every linked wholesaler name in the login response body |

---

## Severity Reconciliation (report ↔ CSV)

Both this report (§8) and the companion CSV (`gap_severity` column) use the identical finding set:

| Severity | Count | Findings |
|---|---|---|
| P0 | 0 | — |
| P1 | 6 | F-01, F-02, F-03, F-04, F-05, F-06 |
| P2 | 3 | F-07, F-08, F-09 |
| P3 | 2 | F-10, F-11 |
| **Total** | **11** | |

The CSV maps each finding to one or more `capability_id` rows; the `gap_severity` values across all CSV
rows aggregate to exactly the counts above. **Accounting gap = 0.**

---

## Conclusion

The backend's tenant-isolation *enforcement* layer is sound: contextual JWTs, server-side ORM tenant
filtering, server-derived `retailer_id`, binding-active gates, and a strict platform boundary prevent
cross-tenant *data* access and retailer-token escalation. Finance integrity is fully preserved
(migrations 032–035, single head 035, all guards present and tested in a lockfile-faithful environment).

The retailer MVP is **not yet deliverable**: the most material gap is **F-01** — invitation acceptance
creates no login-capable retailer identity, so the login → order → payment self-service loop is unproven
at the first step. Together with the identity-key decision (F-02), the login disclosure (F-03),
invitation hardening (F-04), the missing balance page (F-05), and frontend route guards (F-06), these
six P1 items define the DC-12R1 scope. None is a confirmed P0.

**Verdict: PASS_FOR_CTO_DC12R1_IMPLEMENTATION_PLANNING.**
