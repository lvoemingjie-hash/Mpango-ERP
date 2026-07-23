# DC-12R0 Retailer Role and Capability Truth Audit

## AI Role

Third-party independent code reviewer (read-only source audit + disposable local validation + docs-only delivery).

## Verdict

**PASS_DC12R0_TRUTH_AUDIT_COMPLETE_NEEDS_DC12R1**

No Mandatory Stop Condition was triggered. No confirmed cross-tenant *data* exposure at the backend
enforcement layer, no retailer-token path into wholesaler/platform administration, and no finance
regression. However, the audit found **one P0 product-truth violation** (multi-tenant login discloses
every linked wholesaler's name to a retailer) and several P1 gaps that must be closed in DC-12R1
before retailer MVP delivery. These are documented below with exact evidence.

---

## 1. Exact Base SHA and Branch

- Base branch: `origin/product-dev-recovered`
- **Base SHA: `757aef26b116370a066076ad6a17284a4c6288b9`** (verified equal to `origin/product-dev-recovered` after `git fetch` — Hard Rule #2 satisfied)
- Working branch: `opencode/dc12r0-retailer-role-capability-truth-audit-2026-07-23`
- Work mode: docs-only. No production code, tests, migrations, config, lockfile, frontend source, or
  deployment files were modified (see §13 Changed-file proof).

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
   (`backend/api/middleware/rbac.py:12-75`), `RequirePlatformAdmin` (`:78-137`), or
   `require_platform_operator` (`backend/api/v1/platform/p10/guard.py:124-175`).
6. On every ORM SELECT/UPDATE/DELETE, the `do_orm_execute` event listener injects
   `WHERE tenant_id = :tenant_id` (or `wholesaler_id = :uuid`) server-side
   (`backend/db/tenant_filter.py:148-174`), so application code cannot accidentally omit the tenant
   filter. Bypass requires an explicit `run_as_system(reason=...)` or `.execution_options(ignore_tenant=True)`.
7. The `finally` block always clears context + resets tenant (`backend/api/middleware/auth.py:115-124`).

**Two-phase authentication model:**

- **Identity phase** — `POST /auth/login` returns an *identity* JWT (no tenant context) carrying a signed
  `tmap` (`{tenant_id: tenant_local_user_id}`) plus an `available_tenants` list in the response body.
- **Context phase** — `POST /auth/select-tenant` upgrades the identity JWT to a *contextual* JWT
  (carries `tenant_id` + `tenant_schema`) after verifying the requested tenant is in `tmap` and the
  user is active in that schema.

**Role taxonomy (actual, not the audit's assumed names):** the codebase has **no**
`retailer_operator` / `wholesaler_owner` / `wholesaler_admin` / `wholesaler_staff` constants. Roles are
free-form strings stored per-tenant in `roles.name`. Observed values: `super_admin` (global, JWT-borne),
`admin` (tenant, the BI admin-bypass trigger `core/governance/roles.py:94`), plus `finance`, `sales`,
`warehouse`, `viewer` (BI baselines), and platform roles `platform_admin` / `platform_operator`
(`backend/alembic/versions/034_platform_operators.py:73`). The MVP uses a single implicit retailer
capability set expressed through `/api/v1/client/*` routes guarded by `resolve_client_identity`, not a
named `retailer_operator` role.

---

## 3. Actor and Permission Truth Table

| Actor | How materialized | Tenant context source | Can cross tenants? | Evidence |
|---|---|---|---|---|
| Wholesaler owner/admin | tenant `users` row with `admin` role + all perms | contextual JWT `tenant_id` | No — single tenant per session | `backend/scripts/create_wholesaler.py:137,214-223`; `rbac.py:12-75` |
| Wholesaler operational staff | tenant `users` row with scoped role (finance/sales/warehouse/viewer) | contextual JWT `tenant_id` | No | `core/governance/roles.py:48-64` |
| Retailer Operator MVP | `public.retailers` + `public.wholesaler_retailer_bindings` row; tenant `users` row created on invite accept | contextual JWT `tenant_id` + server-derived `retailer_id` | No — `resolve_client_identity` enforces active binding | `backend/api/v1/client/dependencies.py:39-122` |
| Platform operator | `public.platform_operators` row; identity-only `super_admin` JWT | identity JWT (no tenant) | Yes by design (platform scope) | `backend/alembic/versions/034_platform_operators.py`; `rbac.py:78-137` |
| Human OPS / DB operator | direct DB access / platform console | n/a | n/a | out of app-code scope |
| Future AI agent identity | **does not exist** | n/a | n/a | grep: no agent identity/role — correctly deferred (CSV DC12R0-C030) |

**Permission model:** string codes (`orders:read`, `payments:create`, `finance:read`, `exports:create`,
`system:admin`, `platform:admin`, etc.) granted via `roles ↔ permissions` join in each tenant schema.
`RequirePermission` collects `perm.code` from `user.roles[].permissions[]` and checks membership
(`backend/api/middleware/rbac.py:60-66`). `super_admin` with an identity-only token bypasses all checks
(`rbac.py:38-39`).

---

## 4. Invitation-to-First-Order Journey

1. **Wholesaler creates invitation** — `POST /api/v1/invitations` (`backend/api/v1/invitations.py:31-57`)
   requires `invitations:create`, derives `wholesaler_id` from `token.tenant_id`, generates
   `code = secrets.token_urlsafe(24)` (`backend/services/invitation_service.py:32`), persists
   `status="active"`. The `code` is returned to the wholesaler in the response body for out-of-band
   delivery. There is **no email-send step** in the service.
2. **Retailer accepts** — `POST /api/v1/retailers/register` (`backend/api/v1/retailers.py:50-80`, public)
   calls `RetailerService.register_with_invitation` (`backend/services/retailer_service.py:25-85`),
   which runs system-scoped and validates: code exists → `status == "active"` → not expired → phone
   matches. It then looks up or creates a `public.retailers` row **by phone** (`:53-61`), creates the
   `wholesaler_retailer_bindings` row with `outstanding_balance = 0.00`, and calls `mark_used`
   (`:78-83`).
3. **Retailer authenticates** — `POST /auth/login` → identity JWT → `POST /auth/select-tenant` →
   contextual JWT.
4. **Retailer browses & orders** — `/api/v1/client/products` → `/api/v1/client/orders` (POST). The
   client identity dependency (`backend/api/v1/client/dependencies.py:39-122`) resolves `retailer_id`
   server-side and verifies an active binding; price is resolved server-side from `retailer_prices`.

**Gaps in this journey:** no email delivery (§invitations), identity key is phone not email (§5),
no revoke/expiry-default (§7), single-use TOCTOU race, and **no client-side payments/balance step**
(§7).

---

## 5. Same-Email Multi-Wholesaler Truth

This is the audit's most important correction to its own premise.

- **The unified-identity key is `phone`, not `email`.** `public.retailers.phone` is globally unique
  (`backend/models/retailer.py:16` unique index; migration `002_phase_b2_invitation_binding.py:40,43`).
  Registration looks up or creates the retailer **by phone**
  (`backend/services/retailer_service.py:53-61`); `email` is optional, non-unique metadata
  (`backend/models/retailer.py:32-35`). There is no `get_by_email` in any retailer repository.
- **Tenant-local users ARE keyed by email.** `find_user_across_tenants`
  (`backend/crud/user.py:29-100`) scans every tenant schema for a matching `email`, then a second pass
  keeps only copies whose own `password_hash` verifies (DC-3B-R1 fix, `:86-95`).
- **`tmap` resolves the correct per-tenant `user_id`.** When the same email has different `user_id`s
  across tenants, the signed `tmap` (`{tenant_id: tenant_local_user_id}`) lets `/select-tenant`
  resolve the right copy (`backend/api/v1/auth.py:360-371`). `tmap` is signed but not encrypted —
  integrity-only, client-decodable by design (`backend/core/security.py:54-63`).

**Consequence:** two retailers sharing an email but differing in phone are *distinct* identities, and
the client-identity resolver (`backend/api/v1/client/dependencies.py:76-92`) looks up the retailer **by
email** — which conflicts with the phone-based registration key. See Finding F-02.

---

## 6. Relationship Termination Truth

- The binding model documents only `active|inactive` (`backend/models/binding.py:42-48`). There is
  **no `terminated`/`suspended` value on the binding**, no `terminate`/`deactivate` endpoint in
  `api/v1/retailers.py` or `services/retailer_service.py` (grep confirmed), and no audit hook on
  status change. `suspended` exists only at the wholesaler/tenant level
  (`backend/models/wholesaler.py:65,72-75`), not on the retailer relationship.
- **Post-termination block:** the `status = 'active'` gate appears in every new-business path —
  wholesaler order create (`backend/api/v1/orders.py:343-348`), client identity resolution
  (`backend/api/v1/client/dependencies.py:97-104`), and pricing list/set
  (`backend/api/v1/pricing.py:170`). A non-active binding therefore blocks new orders/payments.
- **Historical retention:** there is no cascade delete or hiding of historical orders/payments on
  inactivation. Orders/payments are soft-delete models (`is_deleted`) and remain queryable; receivables
  filter `is_deleted IS FALSE`, not `status` (`backend/services/receivables_service.py:80-95`). History
  is preserved.

**Gap:** termination is not a first-class lifecycle state — only a status string flip possible via
direct DB edit, with no test asserting "terminated retailer cannot transact" specifically.

---

## 7. Current Frontend Entry/Navigation Truth

The frontend (`frontend/src`) provides **three** distinct route trees
(`frontend/src/router/AppRouter.tsx`):

- **Wholesaler ERP** (`/`, `/orders`, `/inventory`, `/skus`, `/retailers`, `/pricing`, `/finance`,
  `/payments`, …) under `MainLayout`.
- **Retailer "Client App"** (`/client`, `/client/products/:id`, `/client/orders`, `/client/orders/new`,
  `/client/orders/:id`) under `ClientLayout` (`AppRouter.tsx:104-113`). Pages exist for product browse
  (`ProductListPage.tsx:16`), detail, cart/order-create (`CreateOrderPage.tsx:16`), order history
  (`OrderListPage.tsx:25`), and order detail/cancel (`OrderDetailPage.tsx:16`).
- **Platform admin** (`/platform/*`) under `PlatformRoute`.

**Workspace picker:** `LoginPage.tsx:40-108` branches on `available_tenants.length`: super_admin → `/`;
length 1 → auto-select; length > 1 → `?tenant_code=` auto-resolve else navigate to `/select-workspace`
passing `availableTenants` via router state; length 0 → `/onboarding/create-tenant` (**dead route — not
registered**, falls through to NotFound). The picker (`WorkspaceSelectorPage.tsx:14`) renders each
tenant's `name` and `code`. **Retailer login (`ClientLoginPage.tsx:42-53`) hard-takes the first tenant**
with no picker.

**Token storage:** localStorage via Zustand `persist` (`frontend/src/stores/authStore.ts:28-60`,
key `mpango-auth`). A single `accessToken`/`refreshToken` slot is reused; the identity token is a
transient local variable by design. No sessionStorage/cookie.

**Frontend gaps (see Findings F-04, F-05):** no retailer payments/outstanding-balance page; no
role-based route guard separating `/client/*` from the wholesaler tree — both sit under the same
auth-only `ProtectedRoute` (`frontend/src/router/guards.tsx:8-16`). No `'retailer'` role string exists
anywhere in frontend source.

---

## 8. P0/P1/P2/P3 Findings (with exact file:line evidence)

### F-01 [P0] Multi-tenant login discloses every linked wholesaler's name to a retailer
`POST /auth/login` returns `available_tenants` containing `{id, code, name}` for **every** tenant whose
copy of the user verified (`backend/api/v1/auth.py:271-278`; `backend/schemas/auth.py:34-38`). The
endpoint accepts only `email + password` and **ignores any `tenant_code`**, so it cannot be constrained
to a single wholesaler entry. A retailer R belonging to wholesalers A and B will, on any login, learn
both A's and B's names — a direct violation of Product Truth ("零售商不得看到其他批发商关系、名称") and
Mandatory Scenario #2/#10. The frontend propagates this: `LoginPage.tsx:96-104` passes the full list to
`WorkspaceSelectorPage`, which renders every name (`WorkspaceSelectorPage.tsx:98-99`). The signed `tmap`
itself is integrity-only and correctly absent from the response body — the leak is the `name`/`code` in
`available_tenants`, not `tmap`.

### F-02 [P1] Identity-key inconsistency: registration keys on phone, client resolution keys on email
Registration looks up/creates the retailer **by phone**
(`backend/services/retailer_service.py:53-61`; `backend/models/retailer.py:16`), but the in-session
client identity resolver looks up the retailer **by email**
(`backend/api/v1/client/dependencies.py:76-92`). A retailer registered without an email, or two
retailers sharing an email, will break or mis-resolve the client identity. This also means the audit's
"same email → one identity" premise is implemented as "same phone → one identity."

### F-03 [P1] No invitation revocation and optional expiry
`status='revoked'` is enumerated in the model comment (`backend/models/invitation.py:33-39`) but **no
code path ever writes it**; there is no `revoked_at` column, no revoke endpoint, and no revoke service
method (grep confirmed — only unrelated Postgres `REVOKE` in `011_s6_p_reporting_role.py`). `expires_at`
is nullable (`backend/models/invitation.py:54-58`), so invitations without it **never expire**
(`backend/services/retailer_service.py:47-48` only rejects when `expires_at` is set and past). Both
violate least-privilege for MVP invitation tokens.

### F-04 [P1] No retailer-facing payments / outstanding-balance / statement page
Grep across `frontend/src/pages/client`, client services, and client types returned **zero** matches for
`outstanding|balance|payment`. `ClientLayout`'s bottom nav exposes only Products + Orders
(`frontend/src/components/layout/ClientLayout.tsx:9-12`). A retailer therefore cannot see amount owed or
payment history, which is a core MVP retailer capability. The backend `/finance` endpoints are
wholesaler-scoped (`finance:read`).

### F-05 [P1] No frontend role-based route guard (retailer vs wholesaler)
`/client/*` and the wholesaler `/` tree share the same auth-only `ProtectedRoute`
(`frontend/src/router/guards.tsx:8-16`) which checks only `accessToken` presence. There is no
`RetailerRoute`/`WholesalerRoute`, and no `'retailer'` role string anywhere in frontend source. A
retailer user can navigate to `/orders`, `/inventory`, etc.; success depends entirely on backend 403s.
This is defense-in-depth weakness, not a backend isolation hole.

### F-06 [P1] Invitation single-use has a TOCTOU race
`register_with_invitation` reads `status`, then later calls `mark_used`
(`backend/services/retailer_service.py:44-45` vs `:78-83`) without a `SELECT … FOR UPDATE`. Two
concurrent acceptances of the same code can both pass the `status == "active"` check before either marks
it used. No test covers concurrent acceptance.

### F-07 [P2] Invitation pre-flight lookup exposes the token in a URL path segment
`GET /api/v1/invitations/{code}` (`backend/api/v1/invitations.py:60-88`) places the token in the URL
path — visible in server access logs, browser history, and referrers. It is a validation lookup, not the
consume endpoint (consume is `POST /retailers/register` with the code in the body), so impact is limited,
but it is below the "token must not travel in URLs" bar. No query-string `?code=` route exists for
invitations (good), and DC-3B password-reset tokens are body-only
(`tests/test_route_authorization_policy.py:147`).

### F-08 [P2] Termination is not a first-class lifecycle state
See §6. No dedicated endpoint, no audit hook, no test for "terminated retailer blocked." The
`status='active'` gate is the only enforcement.

### F-09 [P2] Wholesaler-specific deep-link is client-side only
`?tenant_code=` is consumed by the frontend (`LoginPage.tsx:24-26`) to auto-resolve a tenant, but the
backend `/auth/login` does not accept or enforce `tenant_code`, so it cannot reduce `available_tenants`
to the requested wholesaler (compounds F-01).

### F-10 [P3] `TokenPayload.is_identity_only` uses OR semantics
`backend/core/security.py:65-68` — `tenant_id is None OR tenant_schema is None`. The platform boundary
correctly works around this with a strict AND check (`rbac.py:121-123`), but the OR semantics remain a
footgun for any future consumer of `is_identity_only`.

### F-11 [P3] Dead onboarding route
`LoginPage.tsx:108` navigates to `/onboarding/create-tenant`, which is not registered in `AppRouter`
→ NotFoundPage.

---

## 9. Untested or Environment-Blocked Behaviors

**Environment-blocked (NOT code defects):**

- `tests/test_dc3b_credential_recovery_backend.py` — **16 tests errored** in this disposable
  environment due to a `passlib 1.7.4` + `bcrypt 5.0.0` incompatibility in the parent venv
  (`AttributeError: module 'bcrypt' has no attribute '__about__'` and
  `ValueError: password cannot be longer than 72 bytes`). This is a known passlib/bcrypt-version issue,
  not a product-code defect: `hash_password`/`verify_password`
  (`backend/core/security.py:238-268`) correctly truncate to 72 bytes. **Recommended:** pin
  `passlib>=1.7.4` with `bcrypt<4.1` OR migrate to `argon2`/native `bcrypt`. The dc3b *contract*
  (neutral forgot-password, hash-only reset tokens, query-string rejection, dual-copy reset) is
  verified at the source level but could not be executed here.

**Untested branches (no test coverage):**

- Invitation `INVITATION_NOT_ACTIVE`, `INVITATION_EXPIRED`, `INVITATION_PHONE_MISMATCH`, and
  double-use rejection paths (`backend/services/retailer_service.py:44-51`) — `test_dc1g` covers only
  the happy path.
- Concurrent invitation acceptance (F-06 TOCTOU).
- "Terminated retailer cannot create orders/payments" (F-08).
- F-01 multi-wholesaler name disclosure (no test asserts a retailer does *not* learn of other
  wholesalers).

**All other required validation suites PASS** (see §12).

---

## 10. Proposed DC-12R1 / R2 Implementation Slices

### DC-12R1 (must precede retailer MVP)

- **R1-S1 [fixes F-01, F-09]: Tenant-scoped login.** Accept an optional `tenant_code` on `/auth/login`;
  when present (wholesaler-specific entry), restrict `available_tenants` to that single tenant and do not
  disclose others. When absent and the caller is a retailer-type identity, require a tenant context or
  fail closed. Preserve the unified-identity *capability* without exposing the relationship graph.
- **R1-S2 [fixes F-02]: Reconcile identity key.** Decide phone-vs-email as the single retailer identity
  key and make registration, client-identity resolution, and binding lookup all use the same key.
  Recommend phone (already the global unique key) and have the client resolver fall back to the binding's
  `retailer_id` rather than an email lookup.
- **R1-S3 [fixes F-03]: Invitation hardening.** Add a `revoked_at` column + revoke endpoint/service
  method; make `expires_at` non-null with a sane default (e.g. 7 days); add tests for NOT_ACTIVE,
  EXPIRED, PHONE_MISMATCH, revoked, and double-use.
- **R1-S4 [fixes F-06]: Race-safe single-use.** Wrap invitation consume in `SELECT … FOR UPDATE` (or a
  conditional `UPDATE … WHERE status='active'` with rowcount check) and add a concurrency test.
- **R1-S5 [fixes F-04]: Retailer payments/balance page.** Add `/api/v1/client/finance` (scoped to the
  retailer's own binding in the current tenant) and a frontend page under `/client`.
- **R1-S6 [fixes F-05]: Frontend role/route guards.** Introduce `RetailerRoute`/`WholesalerRoute` and a
  `'retailer'` role concept; prevent cross-navigation between `/client/*` and the wholesaler tree.

### DC-12R2 (post-MVP / experience)

- **R2-S1 [fixes F-07]:** Move invitation pre-flight to a body-POST lookup or accept that it is a public
  validation lookup and document the log exposure; avoid path-segment tokens.
- **R2-S2 [fixes F-08]:** First-class relationship termination (endpoint, audit, dedicated tests,
  retention guarantees).
- **R2-S3 [fixes F-10, F-11]:** Tighten `is_identity_only` to AND semantics; remove/repair the dead
  onboarding route.
- **R2-S4:** Role expansion scaffolding (`retailer_buyer`, `retailer_inventory`, `retailer_finance`)
  preserving the model/permission boundaries documented here.

---

## 11. Mpango Is Not a Retailer Comparison Platform

**Explicit statement:** Mpango ERP is a **wholesaler-centric private B2B channel operating system**. It
is **not** a retailer comparison platform, a supplier directory, a cross-wholesaler search/aggregation
product, a price-comparison tool, or a shared-cart/merged-reporting product.

Confirmed by the source audit:

- There is **no** cross-wholesaler product search, catalog aggregation, or price-comparison API. SKU and
  price reads are scoped to the single current tenant (search_path + retailer_prices join on the
  validated `retailer_id`).
- The unified identity is a **security capability** (one credential, many private relationships), not a
  product feature for retailers to browse suppliers. The current `available_tenants` disclosure (F-01) is
  a **bug to be fixed**, not the intended product behavior.
- One session holds exactly one wholesaler tenant context (contextual JWT carries one `tenant_id`).
- DC-12A product positioning (`ai-ledger/product-ai/2026-07-23_dc12a_product_positioning_value_boundary.md`)
  already codified "retailer sessions are supplier-scoped." This audit confirms the backend enforcement
  matches that positioning *except* for the login-disclosure bug (F-01).

---

## 12. Finance Preservation Results

All Finance Preservation Gate checks **PASS**:

1. **Migrations 032–035 present** — `032_payment_method_integrity.py`,
   `033_order_status_enum_reconciliation.py`, `034_platform_operators.py`,
   `035_receivable_collection_integrity.py` (verified via `ls alembic/versions/`).
2. **Single Alembic head** — `alembic heads` returns exactly one head:
   `035_receivable_collection_integrity (head)`; `035.down_revision = "034_platform_operators"`.
   Full `upgrade head` succeeded on the disposable PG16 DB.
3. **Payment-method set unchanged** — `cash | transfer | credit` only
   (`backend/schemas/payment.py:11-14`; re-validated at `backend/api/v1/orders.py:104-123`).
4. **Idempotency + duplicate-transfer protection present** — idempotency-key conflict lookup
   (`backend/api/v1/orders.py:602-652`; `backend/repositories/payment_repository.py:13-31`) and duplicate
   `transaction_id` rejection (`backend/api/v1/orders.py:732-739`;
   `backend/repositories/payment_repository.py:33-51`).
5. **No negative outstanding balance** — DB CheckConstraint
   `ck_wrb_outstanding_balance_non_negative` (`backend/models/binding.py:19-22`) + runtime conditional
   UPDATE (`backend/services/payment_service.py:186`) → `RECEIVABLE_BALANCE_UNDERFLOW` 409
   (`:191-212`).
6. **No over-collection / cross-tenant receivable** — `ORDER_ALREADY_PAID` /
   `PAYMENT_EXCEEDS_REMAINING` (`backend/api/v1/orders.py:670-691`); receivables query filters
   `WHERE wholesaler_id = :wholesaler_id` (`backend/services/receivables_service.py:80-95, 278`);
   cross-tenant credit isolation asserted by `test_dc11t4h_receivable_collection_integrity.py:411-492`.
7. **No Finance regression introduced** — docs-only delivery; no finance code touched.

**Local validation results (disposable PG16 + Redis7, no production data):**

| Suite | Result |
|---|---|
| `test_dc3b_credential_recovery_backend.py` | ⚠️ 16 errors — **environment-blocked** (passlib/bcrypt incompat; see §9). Source contract verified. |
| `test_auth_regressions.py` + `test_auth_bypass.py` | ✅ PASS |
| `test_route_authorization_policy.py` | ✅ PASS |
| `test_r4_middleware_tenant_context_contract.py` | ✅ PASS |
| `test_tenant_isolation.py` + `test_global_tenant_filter.py` | ✅ PASS |
| `test_dc1g_retailer_registration_binding_balance.py` | ✅ PASS |
| `test_phase4_pricing_safe_orders.py` | ✅ PASS |
| `test_orders_api.py` + `test_payments_api.py` | ✅ PASS |
| `test_dc11d_payment_replay_concurrency_integrity.py` | ✅ PASS |
| `test_dc10f_payment_method_integrity.py` | ✅ PASS |
| `test_dc10k_finance_receivables_runtime.py` + `test_finance_receivables_api.py` | ✅ PASS |
| `test_s6_4_async_exports.py` + `test_dc10e_export_worker_tenant_context.py` | ✅ PASS (after `alembic upgrade head` provisioned `reporting_role`) |
| `alembic heads` | ✅ single head `035_receivable_collection_integrity` |

Raw logs: `_dc12r0_test_logs/validation_full.log`, `_dc12r0_test_logs/migration.log`,
`_dc12r0_test_logs/rerun_failed.log` (these are git-ignored, retained only in the disposable worktree).

---

## 13. Changed-File Proof and Secret-Scan Result

**Changed-file proof (docs-only):**

```
$ git status --short
A ai-ledger/product-ai/2026-07-23_dc12r0_retailer_capability_matrix.csv
A ai-ledger/product-ai/2026-07-23_dc12r0_retailer_role_capability_truth_audit.md
```

Only two files are added; both under `ai-ledger/product-ai/`. **Zero** production code, tests,
migrations, config, lockfile, frontend source, or deployment files were modified. The disposable test
artifacts (`.env.dc12r0`, `_dc12r0_test_logs/`, `_dc12r0_run_validation.sh`) are git-ignored and are
**not** committed (verified via `git check-ignore`).

**`git diff --check`:** clean (no whitespace errors).

**Secret scan:** no real secrets, tokens, DB URLs, or production credentials appear in either
deliverable. The only DB/Redis references point to disposable local containers on loopback ports
55126/55127 with a throwaway container credential that is never committed. `detect-secrets` and
`.gitleaks.toml` are present in the repo; the only detect-secrets hit on these deliverables is a
false-positive "Secret Keyword" heuristic on the word "password" in this very sentence (unverified).

**ASCII/mojibake scan:** both deliverables are UTF-8; the report intentionally contains CJK product-truth
quotations (legitimate, not mojibake) and standard ASCII. No U+FFFD replacement characters or
double-encoded sequences are present in either deliverable (verified by automated scan).

**gitnexus:** `npx gitnexus status` reports the repository index (last indexed commit `c0ed872`) is
stale relative to the working tree — expected, since this is a docs-only delta on a feature branch.
There is no `gitnexus detect_changes` subcommand in the installed version; the docs-only / no-execution-flow
guarantee is instead proven directly against the base SHA: `git diff --name-only 757aef2..HEAD` is empty
(no tracked file modified), and the only untracked additions are the two `.md`/`.csv` deliverables under
`ai-ledger/product-ai/`. Because no `.py`, `.tsx`, `.ts`, `.sql`, `.yaml`, `.toml`, `.json`, `.lock`,
`.env`, or `.sh` file changed, no execution flow can be affected.

---

## Mandatory Scenarios — Truth Table

| # | Scenario | Truth | Evidence |
|---|---|---|---|
| 1 | R has relationships with A and B | Possible: one phone → one `retailers` row; two `wholesaler_retailer_bindings` rows | `services/retailer_service.py:53-76`; migration `002` unique `(wholesaler_id, retailer_id)` |
| 2 | From A's entry, B's existence must not be disclosed | **VIOLATED (F-01)** | `/auth/login` returns `available_tenants` for all verified tenants incl. names (`api/v1/auth.py:271-278`) |
| 3 | A's token reading B's SKU/price/order/payment/export must fail | **HELD** | contextual JWT carries one `tenant_id`; ORM filter + search_path + binding guard (`db/tenant_filter.py:148-174`; `client/dependencies.py:97-115`) |
| 4 | B's data must not appear in A's API/browser state/cache/logs | **HELD at runtime; browser risk via F-01** | no cross-tenant query path; but login response itself carries B's name to the browser |
| 5 | After terminating A, R cannot initiate new A business | **HELD (gated)** | `status='active'` gate on all create paths (`orders.py:343-348`; `client/dependencies.py:97-104`) |
| 6 | History retained after termination | **HELD** | soft-delete only; receivables filter `is_deleted IS FALSE` not status (`receivables_service.py:80-95`) |
| 7 | Retailer token must not reach wholesaler/platform admin | **HELD (backend); frontend weak (F-05)** | `rbac.py:78-137` strict identity-only platform gate; client dep rejects identity-only tokens |
| 8 | Invitation token expiry/single-use/revoke/query-string rejection | **PARTIAL** | expiry optional (F-03); single-use has TOCTOU race (F-06); **no revoke** (F-03); no query-string route (good) |
| 9 | Same-email → correct per-tenant `user_id` mapping | **HELD** | signed `tmap` resolves per-tenant user_id (`api/v1/auth.py:360-371`) — note key is phone for retailers (F-02) |
| 10 | No full supplier-relationship graph via public response or client-readable token | **VIOLATED (F-01)** | `available_tenants` exposes every linked wholesaler name in the login response body |

---

## Conclusion

The backend's tenant-isolation *enforcement* layer is sound: contextual JWTs, server-side ORM tenant
filtering, identity-derived `retailer_id`, binding-active gates, and a strict platform boundary prevent
cross-tenant *data* access and retailer-token escalation. Finance integrity is fully preserved
(migrations 032–035, single head 035, all guards present and tested).

The blocking issue for retailer MVP is **F-01**: the unified-identity login flow discloses every linked
wholesaler's name to the authenticating retailer, which contradicts the product's non-disclosure truth
and Mandatory Scenarios #2 and #10. This is a product-contract violation fixable in DC-12R1 without
re-architecting the (correct) isolation primitives. The remaining P1 items (identity-key reconciliation,
invitation revocation/expiry, retailer balance page, frontend route guards) are scoped, evidenced, and
sliced in §10.

**Verdict: PASS_DC12R0_TRUTH_AUDIT_COMPLETE_NEEDS_DC12R1.**
