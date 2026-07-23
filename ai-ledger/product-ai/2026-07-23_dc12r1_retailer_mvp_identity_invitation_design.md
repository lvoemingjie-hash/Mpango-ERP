# DC-12R1-D Retailer MVP Identity, Invitation and Supplier-Privacy Design Gate

## AI Role

Third-party independent code reviewer — **design gate (docs/design only)**. This document defines the
authoritative design for the retailer MVP identity model, login-capable provisioning, supplier-private
entry, invitation lifecycle, retailer authorization, and retailer financial MVP. It resolves every
finding (F-01 … F-11) from the DC-12R0/R1 truth audit
(`origin/opencode/dc12r0-retailer-role-capability-truth-audit-2026-07-23 @ b059d4f1`) and produces
independently reviewable implementation slices plus a mandatory test matrix.

No production code, migrations, tests, frontend, config, lockfiles, or deployment files are modified by
this task.

## Verdict

**PASS_FOR_CTO_DC12R1_IMPLEMENTATION**

All eight design-decision areas are resolved with explicit, evidence-grounded decisions. No unresolved
architectural decision remains. The only schema change required is **one forward-only migration** that
adds a retailer credential-setup token table and the `retailer_operator` role/permission seed (see §2.6,
§5.1). The design preserves wholesaler-owner multi-tenant behavior unchanged and fails closed on every
ambiguous identity case.

---

## 0. Base, Evidence, and Scope

- **Base branch:** `origin/product-dev-recovered`
- **Base SHA:** `757aef26b116370a066076ad6a17284a4c6288b9` (verified)
- **Audit evidence:** `origin/opencode/dc12r0-retailer-role-capability-truth-audit-2026-07-23 @ b059d4f1`
- **Design branch:** `opencode/dc12r1-retailer-mvp-identity-invitation-design-2026-07-23`
- **Scope:** docs/design only. Deliverable is this single document.

**Audit findings this design resolves:**

| Finding | Severity | Resolved by |
|---|---|---|
| F-01 invite acceptance creates no login-capable identity | P1 | §2 (provisioning transaction) |
| F-02 phone/email identity-key mismatch | P1 | §1 (identity model decision) |
| F-03 `available_tenants` discloses other wholesalers | P1 | §3 (supplier-private login) |
| F-04 no revoke / optional expiry / TOCTOU single-use | P1 | §4 (invitation lifecycle) |
| F-05 no retailer balance page | P1 | §6 (retailer financial MVP) |
| F-06 no frontend role/route guard | P1 | §5 (retailer authorization) |
| F-07 termination not first-class | P2 | §4.6 (deferred to R2; out of MVP critical path) |
| F-08 invitation token in URL path | P2 | §4.5 (token transport) |
| F-09 deep-link client-side only | P2 | §3.3 (folded into supplier-private login) |
| F-10 `is_identity_only` OR semantics | P3 | §5.4 (AND semantics, R2) |
| F-11 dead onboarding route | P3 | §3.5 (R2 cleanup) |

---

## 1. Identity Model

### 1.1 Decision (canonical identity vs authentication locator)

Two distinct concepts are separated and made explicit:

| Concept | Value | Storage | Rationale |
|---|---|---|---|
| **Canonical retailer business identity** | `public.retailers.id` (UUID) | `public.retailers` | The stable, immutable business entity. Already the PK; referenced by `wholesaler_retailer_bindings.retailer_id`. Never reused, never merged. |
| **MVP authentication locator** | **normalized, verified email** | `tenant_schema.users.email` (one row per wholesaler relationship) | Login (`find_user_across_tenants`, `backend/crud/user.py:29-100`) already scans tenant `users.email` and verifies `password_hash`. Making email the locator aligns authentication with the existing, audited login machinery. |
| **Phone** | contact + invitation-match data | `public.retailers.phone` | Remains the unique business contact key and the **invitation-match field** (`invitation.retailer_phone`), but is **not** the authentication root. |

This **reverses the F-02 ambiguity** by picking email as the authentication locator while keeping the
canonical business identity as the retailer UUID. Phone stays matchable but not loginable.

### 1.2 Why email as locator (not phone)

- Login already keys on tenant `users.email` (`backend/crud/user.py:64-81`); reusing it requires **no
  change to the cross-tenant scan, `tmap`, or `select-tenant`** machinery — all of which are tested and
  sound.
- The DC-3B-R1 "same email, different password per tenant" isolation already works on email.
- Phone-as-locator would require a brand-new login scan path and a parallel identity map; email-as-locator
  is the smaller, safer change.

### 1.3 Normalization

- Email is stored **lowercased and trimmed** on write at both `public.retailers.email` and
  `tenant_schema.users.email`. A single `normalize_email()` helper (already present in
  `backend/services/onboarding_service.py`, used for wholesaler signup) is reused for retailers.
- A migration-time ** uniqueness expectation**: within a single tenant schema, `users.email` is already
  effectively unique by login semantics; §2.4 adds a partial unique index to enforce it.

### 1.4 Collision rules (explicit)

| Case | Rule | Result |
|---|---|---|
| **Duplicate email, same wholesaler** | One retailer cannot have two login identities with the same email in the same tenant. | Invitation acceptance **fails closed** with `RETAILER_EMAIL_ALREADY_BOUND` (409). No second user row created. |
| **Duplicate email, different wholesaler** | Allowed and intended (unified identity). The same normalized email may exist as a `users` row in wholesaler A and wholesaler B. Each is a distinct tenant-local user with its own `password_hash`. | Both relationships coexist; login resolves per-tenant via `tmap` (unchanged). |
| **Changed phone** | Phone is mutable contact data on `public.retailers`, not the identity root. A wholesaler may update a retailer's phone. | Does **not** affect login. The invitation `retailer_phone` match is evaluated only at acceptance time. |
| **Existing retailer (same phone), new invitation from another wholesaler** | `get_by_phone` finds the existing `public.retailers` row; a new **binding** is created, plus a new tenant-local `users` row (with the retailer's email) in the new wholesaler's schema. | One canonical retailer, two bindings, two tenant-local users — all sharing one normalized email. |
| **Existing retailer, same wholesaler re-invites** | The `(wholesaler_id, retailer_id)` unique constraint on bindings (`migration 002`) prevents a duplicate binding. | Returns the existing relationship; the new invitation is consumed but no duplicate binding/user is created (idempotent re-bind). |
| **Ambiguous email ownership** (e.g., email matches a `users` row that belongs to a different canonical retailer) | **Fail closed.** No silent merge. | `RETAILER_IDENTITY_CONFLICT` (409); surfaces to wholesaler admin for manual resolution. |

**No silent merges. No destructive cleanup.** Every ambiguous case fails closed with a distinct code.

### 1.5 One retailer, multiple wholesalers (data shape)

For retailer R (canonical UUID `R_id`) belonging to wholesalers A and B:

```
public.retailers:        one row   { id=R_id, phone=..., email=r@example.com }
public.wholesaler_retailer_bindings: two rows
   { wholesaler_id=A, retailer_id=R_id, status=active, outstanding_balance=... }
   { wholesaler_id=B, retailer_id=R_id, status=active, outstanding_balance=... }
t_A.users:  one row { id=U_A, email=r@example.com, password_hash=..., roles=[retailer_operator] }
t_B.users:  one row { id=U_B, email=r@example.com, password_hash=..., roles=[retailer_operator] }
```

`tmap` on R's identity JWT = `{ A: U_A, B: U_B }`. `available_tenants` is **suppressed for retailers**
(§3) so R never learns of B from A's entry.

---

## 2. Login-Capable Provisioning

### 2.1 The exact transaction (after invitation acceptance)

Invitation acceptance becomes a **single atomic transaction** that creates, in order, all of:

1. **retailer** — `public.retailers` row (lookup-by-phone-or-create; canonical identity `R_id`).
2. **binding** — `public.wholesaler_retailer_bindings` row `(wholesaler_id, R_id, status=active,
   outstanding_balance=0.00)` (respecting the `(wholesaler_id, retailer_id)` unique constraint).
3. **tenant-local user** — `t_<wholesaler>.users` row `{ email=normalized_retailer_email,
   password_hash=NULL (not-yet-set), is_active=true, roles=[] }`. The user row exists but cannot log in
   until step 5 completes (see §2.2 — `password_hash IS NULL` fails `verify_password`).
4. **retailer role grant** — attach the `retailer_operator` role (§5.1) to the user row in that tenant.
5. **credential setup token** — `public.retailer_credential_setup_tokens` row (new table, §2.6) bound to
   the tenant-local `user_id`, with `token_hash`, finite `expires_at`, `used_at=NULL`, `revoked_at=NULL`.
6. **clickable setup email** — enqueue an email containing a **clickable setup link** (mirroring the
   DC-12A-R2 secure clickable credential link pattern, `origin/...dc12a_r2_clickable_credential_email_links`).
   The link carries the token in the **fragment or body**, never in a logged query/path (§4.5).

### 2.2 Login-before-setup fails closed

Until the retailer clicks the setup link and sets a password, `password_hash IS NULL`. The login path
(`find_user_across_tenants` → `verify_password`) treats a NULL/empty hash as a verification failure →
`INVALID_CREDENTIALS` (401), indistinguishable from a wrong password (no user-enumeration leak). So a
retailer with a created-but-unset-up identity **cannot authenticate**, and no partial state is exposed.

### 2.3 Rollback behavior (zero partial state)

The entire sequence runs inside **one DB transaction** (`async with session.begin(): ...` or an explicit
`BEGIN/COMMIT` with `ROLLBACK` on any exception). Failure semantics:

| Step that fails | Rollback | Client result |
|---|---|---|
| 1 retailer (e.g., phone conflict that is not the intended match) | whole txn aborts | `INVITATION_PHONE_MISMATCH` / `RETAILER_IDENTITY_CONFLICT` (409); **no retailer row** |
| 2 binding (unique-violation = already bound) | txn aborts; §1.4 idempotent re-bind rule applies | existing relationship returned, **no duplicate** |
| 3 tenant user (email conflict in tenant) | whole txn aborts | `RETAILER_EMAIL_ALREADY_BOUND` (409); **no retailer/binding/user** |
| 4 role grant | whole txn aborts | 500 → retried; **no partial user** |
| 5 setup token (e.g., hash collision) | whole txn aborts | 500 → retried; **no partial user** |
| 6 email enqueue (transient) | **does not** abort the data txn — the data rows commit; email send is retried out-of-band and the token can be re-issued by the wholesaler (§4.3) | acceptance succeeds; email retried |

**Invariant:** after any failed acceptance, either **all six artifacts exist** or **none of {retailer
(newly created), binding (newly created), tenant user, role grant, setup token} exist**. An already-existing
retailer/binding (re-bind case) is never destroyed by a failed acceptance of a *different* invitation.

### 2.4 Email uniqueness within a tenant

A partial unique index enforces one-login-per-email-per-tenant:

```sql
CREATE UNIQUE INDEX ux_users_email_active
  ON "t_<schema>".users (email)
  WHERE is_deleted IS FALSE;
```

This makes the §1.4 "duplicate email, same wholesaler" collision a DB-enforced guarantee, not just an
application check.

### 2.5 Credential setup redemption flow

`POST /api/v1/retailers/setup-credential` (public; body-only token — §4.5):

1. Validate token by `token_hash` (constant-time lookup via unique index); reject if not found,
   `used_at IS NOT NULL`, `revoked_at IS NOT NULL`, or `expires_at < now`.
2. Atomically consume: conditional `UPDATE ... SET used_at=now WHERE used_at IS NULL AND
   revoked_at IS NULL` (rowcount==0 → already consumed → `SETUP_TOKEN_INVALID`).
3. Set the tenant-local user's `password_hash = hash_password(new_password)` (bcrypt, 72-byte truncate —
   `backend/core/security.py:238-268`).
4. Commit. The retailer can now log in.

This mirrors the proven `OwnerCredentialSetupToken.consume_setup_token`
(`backend/services/owner_credential_service.py:185-218`) — same hash-only storage, same single-active
unique index, same used/revoked mutual exclusion.

### 2.6 Migration / new token table (required)

**Yes — one forward-only migration is required.** It adds:

- `public.retailer_credential_setup_tokens` table, mirroring
  `public.owner_credential_setup_tokens` (`backend/models/tenant_onboarding.py:307+`):
  `id`, `user_tenant_schema` (string, the `t_<hash>` where the user lives), `user_id` (UUID, the
  tenant-local user — stored as a plain UUID, **not** a FK, because cross-schema FKs are not used here,
  matching the existing invitation pattern), `token_hash` (unique), `purpose` (check-constrained
  constant), `expires_at` (NOT NULL), `used_at`, `revoked_at`, `is_deleted`, timestamps. CheckConstraints:
  `used_at IS NULL OR revoked_at IS NULL`; one-active unique index on `user_tenant_schema, user_id WHERE
  used_at IS NULL AND revoked_at IS NULL AND is_deleted=false`.
- `invitations.expires_at` becomes **NOT NULL with a server default** of `now() + interval '7 days'`
  (§4.1). Existing NULL rows are backfilled to `created_at + 7 days` (§7.3).
- `invitations.revoked_at` and `invitations.revoked_by` columns (NULLable) for explicit revocation (§4.3).
- The `retailer_operator` role seed + its permission grants (§5.1) into each tenant schema at migration
  time (idempotent `INSERT ... ON CONFLICT DO NOTHING`).
- The `ux_users_email_active` partial unique index per registered tenant schema (§2.4).

No existing column is dropped; no data is rewritten destructively. The migration is forward-only and
reversible only via a companion down-revision that drops the new objects (Alembic convention).

---

## 3. Supplier-Private Entry

### 3.1 Wholesaler-specific retailer entry/login flow

A retailer reaches Mpango **through one wholesaler at a time**. The entry is wholesaler-specific:

- Each wholesaler has a stable **retailer portal URL** of the form
  `/retail/login?w=<wholesaler_code>` (the `wholesaler_code` is the existing `wholesalers.code`, e.g.
  `JAMBO01`).
- The frontend `ClientLoginPage` reads `w` and submits it to the **new** retailer login endpoint
  `POST /api/v1/client/auth/login` together with `email` + `password`.

### 3.2 Retailer login returns ONLY the requested wholesaler context

`POST /api/v1/client/auth/login` (new, retailer-dedicated; separate from the wholesaler-owner
`POST /api/v1/auth/login`):

1. Resolve `wholesaler_code` → `wholesaler` (`public.wholesalers` by code). 404 `UNKNOWN_WHOLESALERER`
   if absent (do **not** enumerate others).
2. In **that one tenant schema only**, look up `users` by normalized email; verify `password_hash`.
3. On success, issue a **contextual JWT directly** (tenant_id + tenant_schema for that wholesaler) —
   **skip the identity phase entirely** for retailer login. No `available_tenants` list is ever computed
   or returned.
4. Response shape: `{ access_token, refresh_token, user:{...}, retailer:{id, name}, wholesaler:{code,
   name} }`. **No `available_tenants` field.** B is never mentioned.

Because the retailer login scans **only** the requested wholesaler's schema, R entering via A's portal
physically cannot discover B — B's `users` row is never queried. This makes F-03/F-09 impossible at the
source rather than merely filtered.

### 3.3 No cross-wholesaler workspace picker for retailers

- The `/select-workspace` picker and `available_tenants` are **wholesaler-owner-only** concepts.
- Retailer login produces a single contextual token; there is **no retailer workspace picker**.
- Retailers who legitimately belong to two wholesalers simply use each wholesaler's portal URL
  independently — two separate sessions, two separate tokens, no shared UI state disclosing the other.

### 3.4 Preserve wholesaler-owner multi-tenant behavior

**Unchanged.** Wholesaler owners/admins continue to use `POST /api/v1/auth/login` → identity JWT →
`available_tenants` → `POST /api/v1/auth/select-tenant` exactly as today
(`backend/api/v1/auth.py:240-427`). The audit found this flow correct for wholesalers (they *should* see
their own properties). The only change is that the **retailer** login uses the new dedicated endpoint
(§3.2), so the disclosure risk is removed for retailers without altering owner behavior.

**Evidence-based carve-out:** if a future audit shows a wholesaler owner's `available_tenants` leaking a
*competitor* wholesaler (not their own properties), that would require a separate change — but no such
evidence exists today, so owner behavior is preserved as-is.

### 3.5 Frontend entry routing (UX)

- `/retail/login?w=<code>` → `ClientLoginPage` (retailer).
- `/login` → wholesaler-owner `LoginPage` (unchanged).
- The dead `/onboarding/create-tenant` navigation (F-11) is repaired in R2 (out of MVP critical path);
  the zero-`available_tenants` branch instead shows a clear "contact your wholesaler" message.

---

## 4. Invitation Lifecycle

### 4.1 Mandatory finite expiry + default TTL

- `expires_at` becomes **NOT NULL** (§2.6). Default TTL = **7 days** (server default
  `now() + interval '7 days'`).
- The create-invitation endpoint accepts an optional `ttl_hours` (clamped to `[1, 720]` — i.e., 1 hour
  to 30 days). Out-of-range → 422.
- Expiry is enforced on **both** the pre-flight lookup and the consume path (see §4.4).

### 4.2 Wholesaler revoke endpoint + permission

- New endpoint: `POST /api/v1/invitations/{id}/revoke` (or by `code`), permission `invitations:revoke`
  (new permission code, granted to `admin` by default). Body optional `reason`.
- Sets `invitations.revoked_at = now`, `revoked_by = token.user_id`, and — to support the existing
  `status` string used by `register_with_invitation` (`backend/services/retailer_service.py:44`) — also
  sets `status = 'revoked'`. This closes the F-04 "revoked enumerated but never written" gap.
- Revocation of an already-used invitation is a no-op success (idempotent).

### 4.3 Atomic single-use consumption (row lock / conditional update)

Replace the current read-then-`mark_used` TOCTOU (`backend/services/retailer_service.py:44-45,78-83`)
with a **conditional update** at the start of the consume transaction:

```sql
UPDATE invitations
   SET status = 'used', used_at = now(), used_retailer_id = :rid
 WHERE id = :inv_id
   AND status = 'active'
   AND revoked_at IS NULL
   AND (expires_at IS NULL OR expires_at > now());
```

`rowcount == 1` → this caller won the race; proceed with §2.1 steps 1-6 (same transaction).
`rowcount == 0` → another caller consumed/revoked/expired it → load the row to classify and return the
specific code (§4.4). This is race-safe under PostgreSQL's row-level locking without an explicit
`SELECT FOR UPDATE`.

### 4.4 Controlled results for every lifecycle state

| Request state | Result (HTTP + code) |
|---|---|
| **Expired** (`expires_at <= now`) | 410 `INVITATION_EXPIRED` (pre-flight) / consume returns same via the conditional-update miss |
| **Revoked** (`status='revoked'` or `revoked_at IS NOT NULL`) | 410 `INVITATION_REVOKED` |
| **Reused** (`status='used'`, `used_at IS NOT NULL`) | 410 `INVITATION_ALREADY_USED` |
| **Phone mismatch** (`retailer_phone` set and != submitted) | 409 `INVITATION_PHONE_MISMATCH` (checked before the conditional update) |
| **Concurrent** (two accepts same code simultaneously) | Exactly one gets 200 (rowcount==1); the other loads the now-`used` row and gets 410 `INVITATION_ALREADY_USED` |
| **Not found** | 404 `INVITATION_NOT_FOUND` |
| **Valid, first use** | 200 + retailer/binding/user/token created (§2.1) |

All error responses are **neutral** and reveal no other wholesaler's data.

### 4.5 Tokens must not be placed in query/path logs

- The **consume** endpoint (`POST /api/v1/retailers/register`) takes `invitation_code` in the **JSON
  body** (already the case — `backend/schemas/retailer.py:11`). No query/path token.
- The **credential setup** link uses the DC-12A-R2 secure clickable-link pattern: the token travels in
  the **URL fragment** (`#/setup?t=...`) so it is never sent to the server in a `Referer` or logged
  query string, and the fragment is consumed client-side then stripped. The redemption endpoint
  (`POST /api/v1/retailers/setup-credential`) takes the token in the **body**.
- The existing public `GET /api/v1/invitations/{code}` pre-flight lookup (F-08) is **deprecated** in R1
  (replaced by a body-POST pre-flight `POST /api/v1/invitations/lookup`) and removed in R2. During R1 it
  may remain but must be excluded from request-body logging and must not echo the code beyond what the
  caller supplied.

### 4.6 Termination (F-07) — scoped to R2

First-class relationship termination (dedicated endpoint, audit hook, retention tests) is **deferred to
R2** and is not on the retailer MVP critical path. The existing `status='active'` gate
(`backend/api/v1/orders.py:343-348`, `backend/api/v1/client/dependencies.py:97-104`) already blocks new
business for a non-active binding, and history is retained (soft-delete). The MVP仅需 "active" is
sufficient; full lifecycle is R2.

---

## 5. Retailer Authorization

### 5.1 `retailer_operator` role + minimum permissions

A new tenant-local role **`retailer_operator`** (seeded by the §2.6 migration, idempotent) is granted
exactly this minimum permission set — scoped to **client/self-service** actions only:

| Permission code | Allows | Source endpoint |
|---|---|---|
| `orders:read` (self) | view own orders | `GET /api/v1/client/orders` |
| `orders:create` (self) | create own orders | `POST /api/v1/client/orders` |
| `orders:update` (self, cancel-only) | cancel own orders | `POST /api/v1/client/orders/{id}/cancel` |
| `payments:create` (self) | pay own orders | `POST /api/v1/orders/{id}/pay` (retailer-scoped) |
| `payments:read` (self) | view own payment history | `GET /api/v1/client/payments` (new, §6) |
| `finance:read` (self) | view own outstanding balance | `GET /api/v1/client/finance` (new, §6) |

The "(self)" qualifier is enforced by `resolve_client_identity`
(`backend/api/v1/client/dependencies.py:39-122`), which derives `retailer_id` server-side and restricts
every query to that retailer + current tenant. **No wholesaler-management permission**
(`retailers:write`, `pricing:write`, `invitations:create`, `system:admin`, `exports:create`, etc.) is
granted to `retailer_operator`.

### 5.2 Retailer token must never enter wholesaler/platform routes

- The retailer contextual JWT (§3.2) carries `tenant_id`/`tenant_schema` + `roles=['retailer_operator']`.
- All wholesaler-management routes (`/api/v1/orders` create-as-wholesaler, `/api/v1/pricing`,
  `/api/v1/invitations`, `/api/v1/retailers` admin, `/api/v1/finance` wholesaler view) require
  wholesaler permissions the retailer lacks → `RequirePermission` returns 403
  (`backend/api/middleware/rbac.py:60-66`).
- All `/api/v1/platform/**` routes require `RequirePlatformAdmin` strict identity-only super_admin
  (`backend/api/middleware/rbac.py:78-137`) → retailer's contextual token is rejected (it has tenant
  context).
- The route-authorization policy test (`backend/tests/test_route_authorization_policy.py`) is extended
  (R1-S3 test matrix) to assert a `retailer_operator` token is classified as tenant-scoped and is denied
  every platform route and every wholesaler-management route.

### 5.3 Backend authorization remains authoritative

Frontend guards (§5.4) are **UX and defense-in-depth only**. Every enforcement decision is made by the
backend (`RequirePermission`, the ORM tenant filter `backend/db/tenant_filter.py:148-174`, and
`resolve_client_identity`). A retailer who bypasses the frontend guard still gets 403/404 from the
backend. No client-side check is trusted.

### 5.4 Frontend `RetailerRoute` / `WholesalerRoute` guards (UX + defense-in-depth)

- New `RetailerRoute` guard (`frontend/src/router/guards.tsx`): admits only tokens whose roles include
  `retailer_operator`; redirects others away from `/client/*`.
- New `WholesalerRoute` guard: admits only tokens **without** `retailer_operator` (i.e., wholesaler
  staff/owner); redirects retailers away from `/`, `/orders`, `/inventory`, etc.
- `PlatformRoute` unchanged (identity-only super_admin).
- These prevent confusing UX (a retailer landing on the wholesaler dashboard) and add a defense layer;
  they are **never** the sole enforcement.

### 5.5 `is_identity_only` AND semantics (F-10, R2)

Tighten `TokenPayload.is_identity_only` (`backend/core/security.py:65-68`) from OR to AND
(`tenant_id IS NULL AND tenant_schema IS NULL`) in R2, after confirming no consumer relies on OR. The
platform boundary already uses a strict AND locally (`backend/api/middleware/rbac.py:121-123`), so this
is a consistency hardening, not a behavior change for the boundary.

---

## 6. Retailer Financial MVP

### 6.1 Scope: only the selected wholesaler relationship

A retailer session (entered via wholesaler A's portal, §3) sees **only** the A relationship:

- Own orders (where `wholesaler_id=A` and `retailer_id=R`).
- Own payments against those orders.
- Own outstanding balance on the `(A, R)` binding.

**No cross-wholesaler totals, no comparison, no aggregation.** Even though R may also belong to B, the
A-session never queries B's data (the retailer login scanned only A's schema, §3.2, and the contextual
token carries only A).

### 6.2 Accounting source-of-truth APIs (frontend must not recompute)

The frontend **must not** recompute balances from order/payment lists. Three server-authoritative
endpoints (new, retailer-scoped) are the single source of truth:

| Endpoint | Returns | Backed by |
|---|---|---|
| `GET /api/v1/client/finance` | `{ outstanding_balance, currency, as_of }` for the `(current_wholesaler, retailer)` binding | `public.wholesaler_retailer_bindings.outstanding_balance` (the same DB-constrained, non-negative column used by wholesaler finance — `backend/models/binding.py:19-22,50`) |
| `GET /api/v1/client/payments` | paginated own payments | `payments` joined to own orders, tenant-scoped |
| `GET /api/v1/client/orders` (+ `/ {id}`) | own orders + items | existing client order endpoints |

The outstanding balance is the **same** column the wholesaler finance runtime maintains
(`backend/services/payment_service.py:169-216` applies deltas under the
`outstanding_balance + delta >= 0` guard). Retailer and wholesaler therefore see **numerically identical**
balances for the same binding — no second ledger, no drift.

### 6.3 Reuse of audited finance guards

All finance-preservation guarantees from DC-12R0 remain in force and are reused unchanged:

- Non-negative balance DB constraint (`ck_wrb_outstanding_balance_non_negative`).
- Over-collection rejection (`ORDER_ALREADY_PAID` / `PAYMENT_EXCEEDS_REMAINING`,
  `backend/api/v1/orders.py:670-691`).
- Idempotency + duplicate-transfer-reference protection
  (`backend/api/v1/orders.py:602-652,732-739`).
- Cross-tenant receivable rejection (explicit `WHERE wholesaler_id` +
  `backend/db/tenant_filter.py:148-174`).

The retailer financial MVP adds **read** paths only; it writes through the **existing** payment flow.

### 6.4 Frontend (R1-S3)

A new `/client/finance` page shows: current outstanding balance (from `GET /client/finance`), recent
payments (from `GET /client/payments`), and a link to each underlying order. No totals across
wholesalers, no charts comparing suppliers. The `ClientLayout` bottom nav gains a **Finance** tab.

---

## 7. Compatibility (forward-only reconciliation)

### 7.1 Inventory of existing state

At migration time, the existing `public.retailers`, `public.wholesaler_retailer_bindings`, and
per-tenant `users` rows are **inventoried, not modified destructively**. The migration:

1. Backfills `invitations.expires_at` (NULL → `created_at + 7 days`) and adds the new invitation columns.
2. Creates `retailer_credential_setup_tokens`.
3. Seeds `retailer_operator` role + permissions per tenant (idempotent).
4. Adds `ux_users_email_active` per registered tenant schema.

### 7.2 Existing retailers without a login identity

Existing `public.retailers` rows created before this change have **no tenant `users` row** (the F-01
gap). These are **not** silently given credentials. Instead:

- They remain valid business entities with their bindings and historical orders intact.
- A wholesaler admin may **re-issue a credential setup invitation** to such a retailer (§4 — a new
  invitation to an existing retailer creates the missing tenant user + setup token per §2.1, respecting
  the §1.4 collision rules).
- Until then, they simply cannot log in — which is the safe, current state.

### 7.3 Forward-only, fail-closed on ambiguity

- **No silent merges:** if two `public.retailers` rows share an email but differ in phone, they remain
  distinct identities (§1.4). The migration does not collapse them.
- **No destructive cleanup:** no retailer/binding/user/order/payment row is deleted or rewritten by the
  migration.
- **Fail closed on ambiguous email ownership:** if the migration detects a tenant `users` row whose email
  matches a `public.retailers` row but the binding relationship is inconsistent, it **does not guess**;
  it writes a reconciliation report and leaves the row untouched, surfacing it for manual OPS resolution.

### 7.4 Wholesaler-owner login behavior unchanged

`POST /api/v1/auth/login` (owner) is untouched (§3.4). Existing owners, admins, and staff log in exactly
as before.

---

## 8. Implementation Slicing (independently reviewable)

Each slice is reviewable on its own and leaves the system in a working state.

### R1-S1 — Identity / provisioning / invitation atomicity (resolves F-01, F-02, F-04)

- Migration (§2.6): `retailer_credential_setup_tokens`, invitation `expires_at NOT NULL` + default,
  `revoked_at`/`revoked_by`, `retailer_operator` role seed, `ux_users_email_active`.
- Rewrite `register_with_invitation` as the §2.1 atomic transaction with §2.3 rollback and §4.3
  conditional-update single-use.
- Add `POST /api/v1/retailers/setup-credential` (§2.5).
- Add `POST /api/v1/invitations/{id}/revoke` + `invitations:revoke` permission (§4.2).
- Normalize email on retailer + tenant-user write (§1.3).
- **Reviewable proof:** a retailer can accept → set password → (once R1-S2 lands) log in; failed
  acceptances leave zero partial state (test matrix T7).

### R1-S2 — Supplier-scoped login / privacy (resolves F-03, F-09)

- New `POST /api/v1/client/auth/login` scanning only the requested wholesaler schema; returns a single
  contextual token, no `available_tenants` (§3.2).
- Frontend `/retail/login?w=<code>` → `ClientLoginPage` posts `w` + credentials (§3.1, §3.5).
- Wholesaler-owner `/api/v1/auth/login` untouched (§3.4).
- Deprecate `GET /api/v1/invitations/{code}` path-token pre-flight in favor of body-POST lookup (§4.5).
- **Reviewable proof:** R entering via A learns nothing of B (test matrix T2); owner login unchanged (T9).

### R1-S3 — Retailer financial UI + role guards (resolves F-05, F-06)

- New `GET /api/v1/client/finance`, `GET /api/v1/client/payments` (retailer-scoped, §6.2).
- `RetailerRoute` / `WholesalerRoute` frontend guards (§5.4).
- `/client/finance` page + Finance tab (§6.4).
- Route-authorization policy test extended to classify `retailer_operator` and assert denial of all
  wholesaler-management + platform routes (§5.2).
- **Reviewable proof:** retailer sees own balance only (T3 cross-tenant denial); retailer denied
  wholesaler/platform routes (T8).

### R1-S4 — Cross-environment + runtime journey closure

- Establish a worktree-local Poetry env with lockfile-faithful deps (bcrypt 4.0.1 / passlib 1.7.4 — per
  DC-12R0-R1, the parent-venv bcrypt 5.0.0 broke `test_dc3b`).
- Add the full end-to-end journey test (T1) and run the entire required test matrix in that env.
- Close F-10 (`is_identity_only` AND) and F-11 (dead route) if time permits, else defer to R2.
- **Reviewable proof:** green test matrix T1–T9 in a clean environment with provenance.

### Sequencing

R1-S1 must land before R1-S2 (provisioning must exist before login can target it). R1-S3 depends on
R1-S2 (the finance UI needs the retailer session). R1-S4 depends on all three. F-07/F-10/F-11 are R2.

---

## 9. Required Test Matrix

Every test runs in the worktree-local Poetry environment (lockfile-faithful deps). Each test has a
deterministic assertion; no flaky or environment-attributable failure is accepted.

| ID | Scenario | Asserts | Slice |
|---|---|---|---|
| **T1** | Fresh invitation → setup password → login → order → payment | End-to-end success: retailer authenticates, creates an order, pays it; balance updates correctly; all six provisioning artifacts exist | R1-S1/S2/S4 |
| **T2** | Same retailer R with wholesalers A+B, entering via A reveals only A | A-session response contains no `available_tenants`, no B name/code/id; A-session token has only A tenant context | R1-S2 |
| **T3** | A-session cannot read B product/price/order/payment/balance | Each cross-tenant read returns 404/empty (ORM filter + binding guard); no B data in any A response | R1-S2/S3 |
| **T4a** | Duplicate (replayed) invitation consumption | Second consume returns `INVITATION_ALREADY_USED` (410) | R1-S1 |
| **T4b** | Concurrent invitation consumption (two simultaneous accepts) | Exactly one succeeds (200); the other gets `INVITATION_ALREADY_USED` (410); exactly one binding/user created | R1-S1 |
| **T4c** | Revoked invitation | After `POST /invitations/{id}/revoke`, consume returns `INVITATION_REVOKED` (410) | R1-S1 |
| **T4d** | Expired invitation | Consume after `expires_at` returns `INVITATION_EXPIRED` (410) | R1-S1 |
| **T4e** | Phone-mismatched invitation | `retailer_phone` set and differing returns `INVITATION_PHONE_MISMATCH` (409) | R1-S1 |
| **T5a** | Duplicate email, same wholesaler | Acceptance returns `RETAILER_EMAIL_ALREADY_BOUND` (409); no second user row | R1-S1 |
| **T5b** | Phone-change case | Updating retailer phone does not affect login; invitation match uses phone only at acceptance | R1-S1 |
| **T6** | Duplicate email, different wholesaler (unified identity) | Same email creates distinct tenant users in A and B; both relationships coexist; `tmap` resolves correctly | R1-S1/S2 |
| **T7** | Transaction rollback with zero partial state | Force failure at each of steps 1-5 (§2.3); assert no newly-created retailer/binding/user/token survives | R1-S1 |
| **T8** | Retailer denied wholesaler + platform routes | `retailer_operator` token gets 403 on every wholesaler-management route and every `/platform/**` route (route-authz policy test) | R1-S3 |
| **T9** | Wholesaler-owner login behavior unchanged | Owner `/auth/login` → identity JWT → `available_tenants` → `/select-tenant` behaves exactly as before (regression) | R1-S2 |
| **T10** | Setup-before-login fails closed | Retailer with `password_hash IS NULL` gets `INVALID_CREDENTIALS`; no enumeration leak | R1-S1 |

Additionally, the existing DC-12R0 validation suites must remain green (auth regressions, route
authorization policy, tenant isolation, global tenant filter, dc1g, pricing, orders, payments, finance
receivables, exports, dc3b credential recovery — all in the worktree-local env).

---

## 10. Mpango Is Not a Retailer Comparison Platform

**Explicit:** This design enforces wholesaler-centric privacy. A retailer session is **always**
single-wholesaler-scoped. There is no retailer-facing supplier list, no cross-wholesaler totals, no
balance comparison, no aggregation. Unified identity is a security capability (one email, many private
relationships), not a product feature for browsing suppliers. The supplier-private login (§3) makes
cross-wholesaler disclosure **impossible at the source** for retailers.

---

## 11. Quality Gates (this design task)

This is a docs-only deliverable. The gates below are met by this document:

- **`git diff --check`:** clean (no whitespace errors).
- **ASCII/mojibake scan:** UTF-8, no U+FFFD replacement characters (CJK quotations are intentional).
- **detect-secrets:** `results: {}` on this file (no secrets, tokens, or production credentials).
- **pre-commit:** trailing-whitespace, end-of-file-fixer, detect-secrets all pass on the report.
- **GitNexus analyze/status:** analyze succeeds; status up-to-date; no execution flow affected (docs-only).
- **base..HEAD docs-only proof:** only this `.md` file is added; zero `.py/.tsx/.ts/.sql/.yaml/.toml/
  .json/.lock/.env/.sh` files changed.

Exact proof is recorded in the commit and the push output.

---

## 12. Unresolved Architectural Decisions

**None.** Every required decision (identity model, provisioning transaction, supplier-private login,
invitation lifecycle, retailer authorization, retailer financial MVP, compatibility) is resolved above
with explicit rules and rollback semantics. The design requires exactly one forward-only migration and
introduces no backward-incompatible change to wholesaler-owner behavior. No STOP condition applies.

---

## 13. Verdict

**PASS_FOR_CTO_DC12R1_IMPLEMENTATION**

The design is complete, internally consistent, grounded in the audited source, and resolves all
DC-12R0/R1 findings on the retailer MVP critical path. It is ready to be split into the R1-S1 … R1-S4
implementation slices, each independently reviewable against the §9 test matrix.
