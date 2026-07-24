# DC-12R1-D Retailer MVP Identity, Invitation and Supplier-Privacy Design Gate

> **Revision R2 (2026-07-23).** This revision tightens the trust model so a wholesaler can **never**
> change a retailer's canonical password or verified email: wholesaler-initiated password reset is
> **removed**; a wholesaler may only suspend **its own** binding. Setup-token reissue is restricted to
> the no-established-password window and the canonical verified email. The retailer now owns a
> **canonical verified email** (`public.retailers` normalized email + `email_verified_at`) that setup
> consumption verifies and wholesalers cannot alter after verification. Credential tokens are bound to
> the **public identity** (`retailer_id`, and `binding_id` for setup); reset tokens are retailer-scoped.
> Retailer self-service forgot/reset endpoints are added. Migration `036` is updated for the
> verified-email column and the retailer-bound setup/reset token structure. Supersedes R1's
> wholesaler-reissue/reset language.
>
> **Revision R1 (2026-07-23).** Corrected the identity model to an explicit
> `wholesaler_retailer_bindings.tenant_user_id` mapping (authoritative), defined unified retailer
> credential semantics across mapped tenant-user copies, corrected email delivery to a fail-closed
> SMTP-before-commit pattern, hardened retailer login with explicit preconditions, fixed the migration
> contract to revision `036_retailer_mvp_identity` (down_revision `035`), specified an exact
> BrowserRouter-compatible setup link, and extended the test matrix. Email is **never** used to infer
> `retailer_id` after authentication.

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

**PASS_FOR_CTO_DC12R1_S1_IMPLEMENTATION**

All design-decision areas are resolved with explicit, evidence-grounded decisions. The R1 corrections
make the retailer identity mapping explicit and authoritative (`binding.tenant_user_id`), unify
credentials across mapped copies, and remove every email-based inference after authentication. One
forward-only migration (`036_retailer_mvp_identity`) is required. No unresolved architectural decision
remains.

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
| F-02 phone/email identity-key mismatch | P1 | §1 (identity mapping decision) |
| F-03 `available_tenants` discloses other wholesalers | P1 | §3 (supplier-private login) |
| F-04 no revoke / optional expiry / TOCTOU single-use | P1 | §4 (invitation lifecycle) |
| F-05 no retailer balance page | P1 | §6 (retailer financial MVP) |
| F-06 no frontend role/route guard | P1 | §5 (retailer authorization) |
| F-07 termination not first-class | P2 | §4.6 (deferred to R2; out of MVP critical path) |
| F-08 invitation token in URL path | P2 | §4.5 (token transport) |
| F-09 deep-link client-side only | P2 | §3.3 (folded into supplier-private login) |
| F-10 `is_identity_only` OR semantics | P3 | §5.5 (AND semantics, R2) |
| F-11 dead onboarding route | P3 | §3.5 (R2 cleanup) |

---

## 1. Identity Model

### 1.1 Decision (authoritative mapping, not email inference)

The retailer identity is anchored on an **explicit, stored mapping** between the canonical retailer
business identity and its tenant-local login user. **Email is never used to infer `retailer_id` after
authentication.**

| Concept | Value | Storage | Role |
|---|---|---|---|
| **Canonical retailer business identity** | `public.retailers.id` (UUID) | `public.retailers` | The stable, immutable business entity. Already the PK; referenced by `wholesaler_retailer_bindings.retailer_id`. Never reused, never merged. |
| **Canonical verified email (retailer-owned)** | normalized email + `email_verified_at` (new — §1.6) | `public.retailers` | The retailer's owned, verified contact email. Credential setup/reset tokens are delivered **only** here. Once verified, **wholesalers cannot change it** (§1.6). This is the single source of truth for "where do credential emails go." |
| **Authoritative identity mapping** | `wholesaler_retailer_bindings.tenant_user_id` (UUID, **nullable**, new column — §1.2) | `public.wholesaler_retailer_bindings` | The single source of truth linking a binding to exactly one tenant-local `users` row. Client identity resolution reads `token.user_id → binding.tenant_user_id`. |
| **Tenant-local auth copy** | normalized email + password | `tenant_schema.users` (`email`, `password_hash`) | Used **only** at login to authenticate the tenant-local user (email match + `verify_password`). The tenant `users.email` mirrors the canonical verified email at provisioning; it is a credential, **not** an identity authority. After login, the contextual JWT carries `user_id`, and the binding is resolved by `tenant_user_id`, never by email. |
| **Phone** | contact + invitation-match data | `public.retailers.phone` | The unique business contact key and the **invitation-match field** (`invitation.retailer_phone`). Not the authentication root, not used post-auth. |

This **replaces the earlier "email as locator" idea**: email authenticates the user, but the
retailer↔user link is the stored `tenant_user_id` on the binding. There is no runtime email→retailer
lookup in any authenticated path. `retailer_id` is **never** inferred from email, schema name, or
`users.*` strings — only from credential tokens bound to the public identity (§2.5) or from
`binding.tenant_user_id` (§1.3).

### 1.2 The `tenant_user_id` mapping column

`wholesaler_retailer_bindings` gains a new **nullable** column:

```sql
ALTER TABLE public.wholesaler_retailer_bindings
  ADD COLUMN tenant_user_id UUID;          -- the tenant-local users.id this binding maps to (nullable)
```

With constraints:

- **Unique constraint:** `(wholesaler_id, tenant_user_id)` — within one wholesaler, a tenant-local user
  maps to at most one retailer binding. (Implemented as a partial unique index
  `WHERE tenant_user_id IS NOT NULL AND is_deleted IS FALSE` so NULLs — pre-R1 bindings — do not
  collide.)
- **No cross-schema foreign key.** `tenant_user_id` references a row in `t_<wholesaler>.users`, which
  lives in a different schema. Per the existing codebase convention (the invitation table stores
  `used_retailer_id` as a plain UUID, not a cross-schema FK, `backend/models/invitation.py:66`), this is
  a **plain UUID column with no FK**, enforced by application logic + the unique constraint. Cross-schema
  FKs are intentionally avoided (they couple schema lifecycles and complicate per-tenant migrations).
- **The binding remains authoritative:** the triple
  `(wholesaler_id, retailer_id, tenant_user_id)` fully describes a login-capable retailer relationship.
  The existing `(wholesaler_id, retailer_id)` uniqueness (migration `002`) is preserved; the new
  `(wholesaler_id, tenant_user_id)` uniqueness is added.

`tenant_user_id` is **nullable** so existing pre-R1 bindings (which have no tenant user — the F-01 gap)
remain valid business relationships; they simply have no login mapping until a credential setup
invitation populates it (§7.2).

### 1.3 Client identity resolution (no email lookup)

`resolve_client_identity` (`backend/api/v1/client/dependencies.py:39-122`) is changed from
email→retailer lookup to **binding lookup by `tenant_user_id`**:

```sql
SELECT retailer_id, wholesaler_id, status
  FROM public.wholesaler_retailer_bindings
 WHERE wholesaler_id = :token_tenant_id
   AND tenant_user_id = :token_user_id
   AND is_deleted IS FALSE
 LIMIT 1;
```

- `token.user_id` (from the signed contextual JWT) is matched against `binding.tenant_user_id`.
- No `users.email`, no `public.retailers.email` read. Email cannot mis-resolve because it is not in the
  query.
- Missing binding → `BINDING_NOT_FOUND` (403). Non-active binding → `BINDING_NOT_ACTIVE` (403).

### 1.4 Collision rules (explicit)

| Case | Rule | Result |
|---|---|---|
| **Duplicate email, same wholesaler** | The `(wholesaler_id, tenant_user_id)` uniqueness and the per-tenant `ux_users_email_active` index (§2.8) together prevent two login identities with the same email in one tenant. | Acceptance **fails closed** `RETAILER_EMAIL_ALREADY_BOUND` (409); no second user/binding. |
| **Duplicate email, different wholesaler** | Allowed (unified identity). The same normalized email may be a `users` row in A and B; each maps via its own binding's `tenant_user_id`. | Two bindings, two tenant-local users, one canonical retailer. Credentials are unified per §2.2. |
| **Changed phone** | Phone is mutable contact data on `public.retailers`. | Does not affect login or the mapping; invitation match uses phone only at acceptance. |
| **Existing retailer (same phone), new invitation from another wholesaler** | `get_by_phone` finds the existing `public.retailers` row; a new binding (with its own `tenant_user_id`) + a new tenant-local user are created in the new wholesaler's schema. | One canonical retailer, two bindings each carrying its own `tenant_user_id`. |
| **Existing retailer, same wholesaler re-invites** | The `(wholesaler_id, retailer_id)` uniqueness prevents a duplicate binding. | Idempotent re-bind: the existing relationship is returned; the invitation is consumed; no duplicate binding/user. |
| **Ambiguous mapping** (e.g., a `tenant_user_id` that does not match the expected retailer, or two retailers sharing a tenant user) | **Fail closed.** | `RETAILER_IDENTITY_CONFLICT` (409); surfaces for manual resolution. |

**No silent merges. No destructive cleanup.** Every ambiguous case fails closed with a distinct code.

### 1.5 One retailer, multiple wholesalers (data shape)

For retailer R (canonical UUID `R_id`) belonging to wholesalers A and B:

```
public.retailers:        one row   { id=R_id, phone=..., email=r@example.com }
public.wholesaler_retailer_bindings: two rows
   { wholesaler_id=A, retailer_id=R_id, tenant_user_id=U_A, status=active, ... }
   { wholesaler_id=B, retailer_id=R_id, tenant_user_id=U_B, status=active, ... }
t_A.users:  one row { id=U_A, email=r@example.com, password_hash=H, roles=[retailer_operator] }
t_B.users:  one row { id=U_B, email=r@example.com, password_hash=H, roles=[retailer_operator] }
```

`H` is the **one effective password hash** shared by both mapped copies (§2.2 unified credential
semantics). The retailer login (§3.2) targets exactly one wholesaler's schema, resolves `U_A` (or `U_B`),
and the contextual JWT carries that `user_id`; the binding is then resolved by `tenant_user_id`.
`available_tenants` is **never produced for retailer login** (§3.2), so R never learns of B from A's
entry.

### 1.6 Canonical verified email (retailer-owned)

The canonical email lives on `public.retailers` as **normalized email + `email_verified_at`** (new column,
§2.9 migration). Ownership and change rules:

- **Retailer-owned.** The canonical email is the retailer's credential-delivery address. It is set during
  the first credential setup (the retailer confirms it by consuming the setup token, §2.5) and recorded
  with `email_verified_at = now`. Until then it is unverified.
- **Setup consumption verifies it.** Consuming a setup token sets/affirms the canonical email and stamps
  `email_verified_at`. Setup/reset emails are delivered **only** to this verified canonical email (never
  to a wholesaler-supplied address).
- **Wholesalers cannot change it after verification.** A wholesaler may invite a retailer (the invitation
  carries `retailer_phone`, not a mutable canonical email) and may suspend **its own** binding (§4.6), but
  has **no endpoint** to change the retailer's canonical email or `email_verified_at`. Only the retailer,
  via an authenticated self-service email-change + re-verification flow (post-MVP), can change it.
- **Mirror at provisioning.** When a new relationship is provisioned (§2.1), the tenant-local
  `users.email` is set to the canonical verified email. The tenant copy is a credential mirror, not an
  authority — the authority is `public.retailers.email` / `email_verified_at`.

This places the retailer's credential email fully outside wholesaler control, consistent with §2.6
(wholesaler cannot reset password) and §2.4 (reissue restricted to the canonical email).

---

## 2. Login-Capable Provisioning & Unified Credentials

### 2.1 The exact transaction (after invitation acceptance)

Invitation acceptance is a **single atomic transaction**. Email delivery is **fail-closed inside the
transaction** (SMTP-before-commit, §2.4). The steps, in order:

1. **retailer** — `public.retailers` row (lookup-by-phone-or-create; canonical identity `R_id`).
2. **binding** — `public.wholesaler_retailer_bindings` row `(wholesaler_id, retailer_id=R_id,
   tenant_user_id=NULL-for-now, status=active, outstanding_balance=0.00)` (respecting the
   `(wholesaler_id, retailer_id)` unique constraint).
3. **tenant-local user** — `t_<wholesaler>.users` row `{ email=normalized_retailer_email,
   password_hash=<per §2.2>, is_active=true, roles=[] }`. (The password hash is set per the unified
   credential rules, not blanket-NULL.)
4. **write back the mapping** — set `binding.tenant_user_id = <new user id>` (closes the authoritative
   mapping; respects the `(wholesaler_id, tenant_user_id)` uniqueness).
5. **retailer role grant** — attach the `retailer_operator` role (§5.1) to the user row.
6. **credential setup token** (only when §2.2 requires one) — `public.retailer_credential_setup_tokens`
   row **bound to the public identity** `(retailer_id, binding_id)` (§2.5b), with `token_hash`, finite
   `expires_at`, `used_at=NULL`, `revoked_at=NULL`. The token carries no tenant-user-identifying string
   beyond what is needed to route redemption; `retailer_id` is read from the token row, never inferred
   from email/schema.
7. **send setup email (fail-closed)** — perform SMTP delivery of the clickable setup link (§4.5)
   **before commit**, addressed to the **canonical email** (`public.retailers.email`, §1.6). SMTP failure
   rolls back the entire transaction (§2.4). If no setup token was issued (§2.2 copy-hash case), no
   setup email is sent.

### 2.2 Unified retailer credential semantics

**One canonical retailer identity has one effective password across all mapped tenant-user copies.**
Provisioning a new relationship (a new binding + tenant user for an existing `retailer_id`) resolves the
password as follows, by inspecting the **existing mapped copies for the same `retailer_id`** (not every
user sharing the email):

| Situation | Rule | Action |
|---|---|---|
| **No mapped copy has a password** (first relationship, or all copies `password_hash IS NULL`) | Issue a setup token. | New tenant user gets `password_hash = NULL`; a setup token + setup email are produced (§2.1 step 6-7). |
| **Existing mapped hashes are identical** (the retailer already set up credentials via another wholesaler) | **Copy the existing hash** into the new tenant user. **No forced reset.** | New tenant user gets `password_hash = <existing identical hash>`; no setup token, no setup email. The retailer logs in with the password they already know. |
| **Conflicting hashes** (mapped copies for the same `retailer_id` have different `password_hash` values) | **Fail closed.** | `RETAILER_CREDENTIAL_CONFLICT` (409). No new tenant user/binding created. Requires controlled recovery: the **retailer** completes a self-service password reset (§2.5b), which re-unifies all mapped copies under one new hash. A wholesaler **cannot** resolve this (§2.6). |

**Scope of setup/reset updates.** When a retailer sets or resets a password (§2.5), the new hash is
written to **every tenant user mapped to the same `retailer_id`** via
`wholesaler_retailer_bindings.tenant_user_id` — i.e., all copies of *this canonical retailer*. It is
**not** written to unrelated users who happen to share the email but map to a different `retailer_id`.
This is the critical difference from email-scoped updates: the update is keyed on the authoritative
`retailer_id` mapping (read from the credential token bound to the public identity), not on `users.email`.

**Existing wholesaler-owner DC-3B behavior remains unchanged.** The owner credential propagation
(`backend/services/owner_credential_service.py`, DC-3B-R1) keys on email across owner accounts and is
not altered. Unified credential semantics apply **only to retailer_operator users reached through
bindings**.

### 2.3 Setup-before-login fails closed

If a tenant user has `password_hash IS NULL` (setup token issued but not yet redeemed), login
verification fails → `INVALID_CREDENTIALS` (401), indistinguishable from a wrong password (no
user-enumeration leak). A created-but-unset-up retailer identity cannot authenticate, and no partial
state is exposed.

### 2.4 Email delivery semantics (fail-closed, MVP)

For MVP, email delivery uses the **existing fail-closed pattern** (the same shape already used by
wholesaler-owner credential setup):

- **Raw token remains memory-only.** Only `token_hash` is persisted
  (`public.retailer_credential_setup_tokens.token_hash` / `retailer_password_reset_tokens.token_hash`);
  the raw token exists only in process memory long enough to build the link and hand it to SMTP.
- **SMTP delivery occurs before transaction commit.** The email send is performed while the DB
  transaction is still open.
- **SMTP failure rolls back.** If SMTP raises, the transaction is rolled back — for provisioning (§2.1),
  no retailer/binding/user/role/token row survives and the invitation is **not** consumed (503
  `SETUP_EMAIL_DELIVERY_FAILED`, retriable per §4.3).
- **No automatic out-of-band retry is claimed.** The design intentionally does **not** promise a
  background retry queue. (A future post-MVP revision may add a durable outbox; MVP does not.)

**Setup reissue — restricted (authenticated wholesaler, narrow window).** A wholesaler admin may
**reissue a setup token only while the canonical retailer has no established password** (i.e., no mapped
copy has a non-NULL `password_hash`). `POST /api/v1/retailers/{retailer_id}/reissue-setup`
(permission `retailers:write`):

1. If any mapped copy for `retailer_id` already has a `password_hash`, return **409
   `CREDENTIAL_ALREADY_ESTABLISHED`** — the retailer owns their credential now; the wholesaler cannot
   reset or reissue it (§2.6).
2. Otherwise revoke the previous active setup token for that `retailer_id`
   (`UPDATE ... SET revoked_at=now WHERE used_at IS NULL AND revoked_at IS NULL`), create a new setup
   token (new `token_hash`, new `expires_at`), and send a new setup email **addressed only to the
   canonical email** (`public.retailers.email`, §1.6) — fail-closed within the reissue transaction.

Once the retailer has established a password, the only recovery path is the retailer's own self-service
reset (§2.5b). This prevents a wholesaler from using "reissue" to take over a retailer's credential.

**Rare send-success / commit-failure case.** If SMTP returns success but the subsequent DB commit fails
(e.g., connection drop between send and commit), the retailer receives an email containing a link whose
token hash was never committed. Clicking it yields `SETUP_TOKEN_INVALID` / `RESET_TOKEN_INVALID` (§2.5)
because the row does not exist. This is an **invalid link** — not a data-integrity breach (no partial
committed state) — resolved by the retailer requesting a new self-service reset (§2.5b) or, in the
pre-password window only, a wholesaler reissue (above).

### 2.5 Credential setup / reset — token binding & redemption

**2.5a Tokens are bound to the public identity, not to tenant-user strings.**

- **Setup tokens** (`public.retailer_credential_setup_tokens`) carry `retailer_id` **plus `binding_id`**
  for setup purpose (a setup token is tied to the specific relationship that triggered it). Redemption
  resolves `retailer_id` directly from the token row.
- **Reset tokens** (`public.retailer_password_reset_tokens`, new — §2.5b) are **retailer-scoped** (carry
  `retailer_id`, no `wholesaler_id`/`binding_id`), because a reset applies to the unified credential
  across all of the retailer's wholesalers.
- **`retailer_id` is never inferred from email, schema name, or `users.*` strings.** It is read only
  from the token row (setup/reset) or from `binding.tenant_user_id` (authenticated session, §1.3).

**2.5b Retailer self-service forgot/reset (new endpoints).**

`POST /api/v1/client/auth/forgot-password` and `POST /api/v1/client/auth/reset-password` (both public;
JSON body only — §4.5):

- **Forgot-password** — accepts `{ email, wholesaler_code }`. Lookup is **neutral**: regardless of
  whether a verified retailer with that canonical email exists for that wholesaler, the response is the
  same 200 neutral acknowledgement (no enumeration). If a match exists and has an established password, a
  `retailer_password_reset_tokens` row is created (`token_hash`, finite `expires_at`, single-use
  `used_at=NULL`, `revoked_at=NULL`, scoped to `retailer_id`) and a reset email is sent to the **canonical
  email only**, fail-closed before commit. If no match, no row, no email, same neutral response.
- **Reset-password** — accepts `{ reset_token, new_password }` in the body. It (1) validates the token by
  `token_hash` (reject not-found / `used_at IS NOT NULL` / `revoked_at IS NOT NULL` / `expires_at < now`
  → `RESET_TOKEN_INVALID`); (2) resolves `retailer_id` from the token row (no email); (3) atomically
  consumes it (conditional `UPDATE ... SET used_at=now WHERE used_at IS NULL AND revoked_at IS NULL`,
  rowcount==0 → `RESET_TOKEN_INVALID`); (4) computes `new_hash = hash_password(new_password)` (bcrypt,
  72-byte truncate, `backend/core/security.py:238-268`); (5) **writes `new_hash` to every tenant user
  mapped to the same `retailer_id`** (§2.2 scope); (6) commits.

**2.5c Setup redemption.** `POST /api/v1/retailers/setup-credential` (public; body-only token — §4.5)
follows the same shape as reset: validate by `token_hash` → resolve `retailer_id` from the token row →
consume conditionally → compute `new_hash` → write to every mapped copy for that `retailer_id` →
**additionally set the canonical `public.retailers.email_verified_at = now`** (§1.6 setup-verifies-email)
→ commit. Used/expired/revoked/unknown tokens all return `SETUP_TOKEN_INVALID`.

Both setup and reset mirror the proven `OwnerCredentialSetupToken.consume_setup_token`
(`backend/services/owner_credential_service.py:185-218`) for hash-only storage and single-active
semantics, but extend the write to **all mapped copies for the `retailer_id`** and bind the token to the
public identity rather than a tenant-user string.

### 2.6 Wholesaler authority boundary (no credential / no email control)

A wholesaler's authority over a retailer relationship is **strictly limited to its own binding**:

- **May:** create invitations (§4), suspend/terminate **its own** `wholesaler_retailer_bindings` row
  (§4.6), reissue a setup token **only while the retailer has no established password** (§2.4), read the
  retailer's business data within the relationship.
- **Must never:** change the retailer's canonical password, change the retailer's verified canonical
  email or `email_verified_at`, reset an established credential, or touch **another wholesaler's**
  binding. There is **no wholesaler endpoint** for password reset or email change; the only reset path is
  the retailer's self-service `forgot/reset-password` (§2.5b).

This is the D-R2 trust inversion: credentials and the verified email are **retailer-owned**; the
wholesaler controls only the relationship's commercial status.

### 2.7 Rollback behavior (zero partial state)

The entire §2.1 sequence (including the SMTP send) runs inside **one DB transaction**. Because SMTP is
performed before commit (§2.4), any failure — DB or SMTP — rolls back every row. Failure semantics:

| Step that fails | Rollback | Client result |
|---|---|---|
| 1 retailer (phone conflict / ambiguous) | whole txn aborts | `INVITATION_PHONE_MISMATCH` / `RETAILER_IDENTITY_CONFLICT` (409); **no retailer row** |
| 2 binding (unique-violation = already bound) | txn aborts; §1.4 idempotent re-bind | existing relationship returned, **no duplicate** |
| 3 tenant user (email conflict in tenant) | whole txn aborts | `RETAILER_EMAIL_ALREADY_BOUND` (409); **no retailer/binding/user** |
| 3 tenant user (credential conflict, §2.2) | whole txn aborts | `RETAILER_CREDENTIAL_CONFLICT` (409); **no partial state** |
| 4 write-back `tenant_user_id` (unique-violation) | whole txn aborts | `RETAILER_IDENTITY_CONFLICT` (409); user row rolled back |
| 5 role grant | whole txn aborts | 500; **no partial user** |
| 6 setup token | whole txn aborts | 500; **no partial user** |
| 7 SMTP send | whole txn aborts | 503 `SETUP_EMAIL_DELIVERY_FAILED`; **no committed rows; invitation not consumed** |

**Invariant:** after any failed acceptance, either **all artifacts are committed** or **none of
{retailer (newly created), binding (newly created), tenant user, `tenant_user_id` mapping, role grant,
setup token} exist**. The rare send-success/commit-failure case (§2.4) leaves no committed rows; its
only artifact is an undeliverable link, recovered by the retailer's self-service reset (§2.5b) or, in
the pre-password window, a restricted wholesaler reissue (§2.4).

### 2.8 Per-tenant email uniqueness

A partial unique index enforces one-login-per-email-per-tenant (supports the §1.4 collision rule):

```sql
CREATE UNIQUE INDEX ux_users_email_active
  ON "t_<schema>".users (email)
  WHERE is_deleted IS FALSE;
```

### 2.9 Migration contract — `036_retailer_mvp_identity`

**Revision:** `036_retailer_mvp_identity`. **down_revision:** `035_receivable_collection_integrity`
(the current single head — preserves the Finance Preservation Gate). This is the **only** migration R1
requires.

- **Enumerate tenants only from the authoritative live registry:** the set of tenant schemas to touch is
  computed from `public.tenant_registrations JOIN public.wholesalers` (live, registered tenants only) —
  never from a filesystem scan or a guess. This matches the existing DC-2M2 reconciliation source.
- **Read-only preflight first.** Before any mutation, a preflight pass over the live registry detects:
  (a) duplicate emails within a tenant; (b) conflicting `tenant_user_id` mappings or password hashes
  across existing bindings; (c) incompatible catalog objects (e.g., a binding whose `retailer_id` has no
  `public.retailers` row). Preflight **does not mutate**; it either passes or aborts the migration with
  a written report for manual OPS resolution (fail-closed, §7.3).
- **Mutations (only after a clean preflight):**
  - `ALTER TABLE public.wholesaler_retailer_bindings ADD COLUMN tenant_user_id UUID;` + the partial
    unique index `(wholesaler_id, tenant_user_id)` (§1.2).
  - `ALTER TABLE public.retailers ADD COLUMN email_verified_at TIMESTAMPTZ;` (§1.6 canonical verified
    email). Existing rows get `email_verified_at = NULL` (unverified until the retailer completes setup,
    §2.5c); no email is rewritten.
  - `ALTER TABLE public.invitations` — `expires_at` becomes **NOT NULL** with server default
    `now() + interval '7 days'`; existing NULL rows backfilled to `created_at + 7 days`. Add
    `revoked_at`, `revoked_by` (nullable) (§4.2-4.3).
  - `CREATE TABLE public.retailer_credential_setup_tokens` — **bound to the public identity**
    (`retailer_id`, `binding_id`) per §2.5a: `id`, `retailer_id` (UUID FK → `public.retailers.id`),
    `binding_id` (UUID FK → `public.wholesaler_retailer_bindings.id`), `token_hash` (unique), `purpose`
    (check-constrained constant), `expires_at` NOT NULL, `used_at`, `revoked_at`, `is_deleted`,
    timestamps; CheckConstraint `used_at IS NULL OR revoked_at IS NULL`; one-active unique index on
    `retailer_id WHERE used_at IS NULL AND revoked_at IS NULL AND is_deleted=false`. (No
    `user_tenant_schema`/`user_id` columns — the token does not carry tenant-user strings; `retailer_id`
    is the identity, §2.5a.)
  - `CREATE TABLE public.retailer_password_reset_tokens` — **retailer-scoped** per §2.5a/§2.5b:
    `id`, `retailer_id` (UUID FK → `public.retailers.id`), `token_hash` (unique), `purpose`
    (check-constrained), `expires_at` NOT NULL, `used_at`, `revoked_at`, `is_deleted`, timestamps;
    CheckConstraint `used_at IS NULL OR revoked_at IS NULL`; one-active unique index on
    `retailer_id WHERE used_at IS NULL AND revoked_at IS NULL AND is_deleted=false`. No `wholesaler_id`
    / `binding_id` — a reset is retailer-scoped, not wholesaler-scoped.
  - Per live-registry tenant: seed the `retailer_operator` role + its permission grants (§5.1,
    idempotent `INSERT ... ON CONFLICT DO NOTHING`); add `ux_users_email_active` (§2.8).
- **Forward-only.** Rollback is **application-level rollback** (the migration runs inside a transaction;
  any error rolls it back) **plus a verified DB restore** for disaster recovery. There is **no
  destructive downgrade** — no down-revision that drops columns/tables is provided as an operational
  path (an Alembic down-revision may exist solely for local dev convenience and is never used against
  shared environments).
- **No existing column is dropped; no data is rewritten destructively.** Existing bindings get
  `tenant_user_id = NULL` (§7.2). No retailer/user/order/payment row is deleted or overwritten.

---

## 3. Supplier-Private Entry

### 3.1 Wholesaler-specific retailer entry/login flow

A retailer reaches Mpango **through one wholesaler at a time**. The entry is wholesaler-specific:

- Each wholesaler has a stable **retailer portal URL** of the form
  `/retail/login?w=<wholesaler_code>` (the `wholesaler_code` is the existing `wholesalers.code`, e.g.
  `JAMBO01`).
- The frontend `ClientLoginPage` reads `w` and submits it to the **new** retailer login endpoint
  `POST /api/v1/client/auth/login` together with `email` + `password`.

### 3.2 Retailer login — hardened, returns ONLY the requested wholesaler context

`POST /api/v1/client/auth/login` (new, retailer-dedicated; separate from the wholesaler-owner
`POST /api/v1/auth/login`). **Before any token is issued**, all six preconditions must hold; any
mismatch returns a **neutral `INVALID_CREDENTIALS` (401)** or a **controlled 403** that reveals no other
supplier:

1. **Exact wholesaler portal resolution** — `wholesaler_code` → exactly one `public.wholesalers` row by
   code. Missing/unknown → `INVALID_CREDENTIALS` (neutral; do **not** confirm whether the wholesaler
   exists).
2. **Successful password verification** — in **that one tenant schema only**, look up `users` by
   normalized email (the tenant copy mirrors the canonical verified email, §1.6);
   `verify_password(password, user.password_hash)` must succeed. Any failure (no user, NULL hash, wrong
   password) → `INVALID_CREDENTIALS` (neutral). Email is used **only** here, to find the auth copy; it is
   not used to infer `retailer_id` (§1.1).
3. **Binding found by `tenant_user_id`** — `public.wholesaler_retailer_bindings` must have a row with
   `wholesaler_id = <resolved wholesaler>` AND `tenant_user_id = <user.id>` AND `is_deleted IS FALSE`.
   Missing → `INVALID_CREDENTIALS` (neutral; the user authenticated but is not a retailer of *this*
   wholesaler).
4. **`binding.wholesaler_id` matches the requested wholesaler** — redundant with (3) but explicit: the
   binding must belong to the portal the retailer entered through. A user who is a retailer of B but not
   A, entering via A, fails here → `INVALID_CREDENTIALS` (neutral; A is never told the user is a B
   retailer).
5. **`binding.status == 'active'`** — inactive/suspended binding → controlled 403
   `RETAILER_INACTIVE` (or neutral `INVALID_CREDENTIALS`; either way no other supplier disclosed).
6. **`retailer_operator` role present** — the tenant user must carry the `retailer_operator` role
   (§5.1). A user without it (e.g., a wholesaler staff account) cannot use client login →
   `INVALID_CREDENTIALS` (neutral).

Only after all six pass: issue a **contextual JWT directly** (`tenant_id` + `tenant_schema` for that one
wholesaler, `roles=['retailer_operator']`, `user_id` = the tenant-local user id). **Skip the identity
phase entirely** for retailer login. **No `available_tenants` list is ever computed or returned.**
Response: `{ access_token, refresh_token, user:{...}, retailer:{id, name}, wholesaler:{code, name} }`.
B is never mentioned.

Because the retailer login scans **only** the requested wholesaler's schema and resolves the binding by
`tenant_user_id`, R entering via A physically cannot discover B — B's `users`/binding rows are never
queried. This makes F-03/F-09 impossible at the source.

### 3.3 No cross-wholesaler workspace picker for retailers

- The `/select-workspace` picker and `available_tenants` are **wholesaler-owner-only** concepts.
- Retailer login produces a single contextual token; there is **no retailer workspace picker**.
- Retailers who legitimately belong to two wholesalers use each wholesaler's portal URL independently —
  two separate sessions, two separate tokens, no shared UI state disclosing the other.

### 3.4 Preserve wholesaler-owner multi-tenant behavior

**Unchanged.** Wholesaler owners/admins continue to use `POST /api/v1/auth/login` → identity JWT →
`available_tenants` → `POST /api/v1/auth/select-tenant` exactly as today
(`backend/api/v1/auth.py:240-427`). The audit found this flow correct for wholesalers (they *should* see
their own properties). The retailer login uses the new dedicated endpoint (§3.2), so disclosure risk is
removed for retailers without altering owner behavior. The DC-3B owner credential behavior is likewise
unchanged (§2.2).

### 3.5 Frontend entry routing (UX)

- `/retail/login?w=<code>` → `ClientLoginPage` (retailer).
- `/login` → wholesaler-owner `LoginPage` (unchanged).
- The dead `/onboarding/create-tenant` navigation (F-11) is repaired in R2 (out of MVP critical path);
  the zero-`available_tenants` branch instead shows a clear "contact your wholesaler" message.

---

## 4. Invitation Lifecycle

### 4.1 Mandatory finite expiry + default TTL

- `expires_at` becomes **NOT NULL** (§2.9). Default TTL = **7 days** (server default
  `now() + interval '7 days'`).
- The create-invitation endpoint accepts an optional `ttl_hours` (clamped to `[1, 720]` — 1 hour to 30
  days). Out-of-range → 422.
- Expiry is enforced on **both** the pre-flight lookup and the consume path (§4.4).

### 4.2 Wholesaler revoke endpoint + permission

- New endpoint: `POST /api/v1/invitations/{id}/revoke` (or by `code`), permission `invitations:revoke`
  (new permission code, granted to `admin` by default). Body optional `reason`.
- Sets `invitations.revoked_at = now`, `revoked_by = token.user_id`, and `status = 'revoked'` (to match
  the `status` string used by `register_with_invitation`, `backend/services/retailer_service.py:44`).
  This closes the F-04 "revoked enumerated but never written" gap.
- Revocation of an already-used invitation is a no-op success (idempotent).

### 4.3 Atomic single-use consumption (conditional update)

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

`rowcount == 1` → this caller won the race; proceed with §2.1 steps 1-7 (same transaction).
`rowcount == 0` → another caller consumed/revoked/expired it → load the row to classify and return the
specific code (§4.4). On **SMTP failure** (§2.4) the transaction rolls back, which rolls back this
`status='used'` flip too — so the invitation is **not consumed** by a failed delivery and the retailer
can retry.

### 4.4 Controlled results for every lifecycle state

| Request state | Result (HTTP + code) |
|---|---|
| **Expired** (`expires_at <= now`) | 410 `INVITATION_EXPIRED` (pre-flight) / consume returns same via the conditional-update miss |
| **Revoked** (`status='revoked'` or `revoked_at IS NOT NULL`) | 410 `INVITATION_REVOKED` |
| **Reused** (`status='used'`, `used_at IS NOT NULL`) | 410 `INVITATION_ALREADY_USED` |
| **Phone mismatch** (`retailer_phone` set and != submitted) | 409 `INVITATION_PHONE_MISMATCH` (checked before the conditional update) |
| **Concurrent** (two accepts same code simultaneously) | Exactly one gets 200 (rowcount==1); the other loads the now-`used` row and gets 410 `INVITATION_ALREADY_USED` |
| **Not found** | 404 `INVITATION_NOT_FOUND` |
| **Valid, first use, SMTP ok** | 200 + retailer/binding/user/mapping/token created (§2.1) |
| **Valid, first use, SMTP failed** | 503 `SETUP_EMAIL_DELIVERY_FAILED`; **no rows committed; invitation not consumed** (§2.4) |

All error responses are **neutral** and reveal no other wholesaler's data.

### 4.5 Token transport and link contract

- The **consume** endpoint (`POST /api/v1/retailers/register`) takes `invitation_code` in the **JSON
  body** (already the case — `backend/schemas/retailer.py:11`). No query/path token.
- **Exact setup link contract (BrowserRouter-compatible):**

  ```
  https://<origin>/retailer/setup-credential#setupToken=<token>
  ```

  - The token travels in the **URL fragment** (`#setupToken=...`). BrowserRouter (React Router v6, which
    the frontend uses — `frontend/src/router/AppRouter.tsx`) preserves the hash client-side and **never
    sends the fragment to the server** (no `Referer`, no server access log, no proxy log).
  - The frontend `SetupCredentialPage` reads `location.hash`, **clears the fragment immediately**
    (`history.replaceState(null, '', location.pathname)`), and submits the token to
    `POST /api/v1/retailers/setup-credential` in the **JSON body** (`{"setup_token": "..."}`) — never as
    a query/path parameter.
- **Exact reset link contract (BrowserRouter-compatible), parallel to setup:**

  ```
  https://<origin>/retailer/reset-password#resetToken=<token>
  ```

  Same fragment handling: `ResetPasswordPage` reads `location.hash`, clears it immediately, and submits
  to `POST /api/v1/client/auth/reset-password` in the **JSON body** (`{"reset_token": "...",
  "new_password": "..."}`). `POST /api/v1/client/auth/forgot-password` takes only `{ email,
  wholesaler_code }` in the body and returns a neutral 200.
- All redemption endpoints take the token in the **body** only.
- The existing public `GET /api/v1/invitations/{code}` pre-flight lookup (F-08) is **deprecated** in R1
  (replaced by a body-POST pre-flight `POST /api/v1/invitations/lookup`) and removed in R2. During R1 it
  must be excluded from request-body logging and must not echo the code beyond what the caller supplied.

### 4.6 Termination & suspension (F-07)

**MVP suspend (in scope):** a wholesaler may suspend **its own** binding by flipping
`wholesaler_retailer_bindings.status` to `inactive` (the authority boundary, §2.6, permits this and only
this relationship-status action). Suspension blocks new business for that relationship via the existing
`status='active'` gate (`backend/api/v1/orders.py:343-348`, `backend/api/v1/client/dependencies.py`) and
the login precondition `binding.status == 'active'` (§3.2). Critically (T20), suspending the A binding
does **not** affect the B binding or the shared retailer credential — A's authority ends at A's own row.

**First-class termination (R2):** a dedicated terminate endpoint, audit hook, retention tests, and
reactivation are **deferred to R2**. The MVP needs only active/inactive; full lifecycle is R2.

---

## 5. Retailer Authorization

### 5.1 `retailer_operator` role + minimum permissions

A new tenant-local role **`retailer_operator`** (seeded by the §2.9 migration, idempotent) is granted
exactly this minimum permission set — scoped to **client/self-service** actions only:

| Permission code | Allows | Source endpoint |
|---|---|---|
| `orders:read` (self) | view own orders | `GET /api/v1/client/orders` |
| `orders:create` (self) | create own orders | `POST /api/v1/client/orders` |
| `orders:update` (self, cancel-only) | cancel own orders | `POST /api/v1/client/orders/{id}/cancel` |
| `payments:create` (self) | pay own orders | `POST /api/v1/orders/{id}/pay` (retailer-scoped) |
| `payments:read` (self) | view own payment history | `GET /api/v1/client/payments` (new, §6) |
| `finance:read` (self) | view own outstanding balance | `GET /api/v1/client/finance` (new, §6) |

The "(self)" qualifier is enforced by `resolve_client_identity`, which now resolves `retailer_id` from
`token.user_id → binding.tenant_user_id` (§1.3) and restricts every query to that retailer + current
tenant. **No wholesaler-management permission** (`retailers:write`, `pricing:write`,
`invitations:create`, `system:admin`, `exports:create`, etc.) is granted to `retailer_operator`.

### 5.2 Retailer token must never enter wholesaler/platform routes

- The retailer contextual JWT (§3.2) carries `tenant_id`/`tenant_schema` + `roles=['retailer_operator']`.
- All wholesaler-management routes require wholesaler permissions the retailer lacks → `RequirePermission`
  returns 403 (`backend/api/middleware/rbac.py:60-66`).
- All `/api/v1/platform/**` routes require `RequirePlatformAdmin` strict identity-only super_admin
  (`backend/api/middleware/rbac.py:78-137`) → retailer's contextual token is rejected (it has tenant
  context).
- The route-authorization policy test (`backend/tests/test_route_authorization_policy.py`) is extended
  (R1-S3 test matrix) to assert a `retailer_operator` token is classified as tenant-scoped and is denied
  every platform route and every wholesaler-management route.

### 5.3 Backend authorization remains authoritative

Frontend guards (§5.4) are **UX and defense-in-depth only**. Every enforcement decision is made by the
backend (`RequirePermission`, the ORM tenant filter `backend/db/tenant_filter.py:148-174`, and
`resolve_client_identity` via `tenant_user_id`). A retailer who bypasses the frontend guard still gets
403/404 from the backend. No client-side check is trusted.

### 5.4 Frontend `RetailerRoute` / `WholesalerRoute` guards (UX + defense-in-depth)

- New `RetailerRoute` guard (`frontend/src/router/guards.tsx`): admits only tokens whose roles include
  `retailer_operator`; redirects others away from `/client/*`.
- New `WholesalerRoute` guard: admits only tokens **without** `retailer_operator` (i.e., wholesaler
  staff/owner); redirects retailers away from `/`, `/orders`, `/inventory`, etc.
- `PlatformRoute` unchanged (identity-only super_admin).
- These prevent confusing UX and add a defense layer; they are **never** the sole enforcement.

### 5.5 `is_identity_only` AND semantics (F-10, R2)

Tighten `TokenPayload.is_identity_only` (`backend/core/security.py:65-68`) from OR to AND
(`tenant_id IS NULL AND tenant_schema IS NULL`) in R2, after confirming no consumer relies on OR. The
platform boundary already uses a strict AND locally (`backend/api/middleware/rbac.py:121-123`), so this
is a consistency hardening.

---

## 6. Retailer Financial MVP

### 6.1 Scope: only the selected wholesaler relationship

A retailer session (entered via wholesaler A's portal, §3) sees **only** the A relationship:

- Own orders (where `wholesaler_id=A` and `retailer_id=R`).
- Own payments against those orders.
- Own outstanding balance on the `(A, R)` binding.

**No cross-wholesaler totals, no comparison, no aggregation.** Even though R may also belong to B, the
A-session never queries B's data (retailer login scanned only A's schema, §3.2, and the contextual token
carries only A).

### 6.2 Accounting source-of-truth APIs (frontend must not recompute)

The frontend **must not** recompute balances from order/payment lists. Three server-authoritative
endpoints (new, retailer-scoped) are the single source of truth:

| Endpoint | Returns | Backed by |
|---|---|---|
| `GET /api/v1/client/finance` | `{ outstanding_balance, currency, as_of }` for the `(current_wholesaler, retailer)` binding | `public.wholesaler_retailer_bindings.outstanding_balance` (the same DB-constrained, non-negative column used by wholesaler finance — `backend/models/binding.py:19-22,50`) |
| `GET /api/v1/client/payments` | paginated own payments | `payments` joined to own orders, tenant-scoped |
| `GET /api/v1/client/orders` (+ `/{id}`) | own orders + items | existing client order endpoints |

The outstanding balance is the **same** column the wholesaler finance runtime maintains
(`backend/services/payment_service.py:169-216` applies deltas under the
`outstanding_balance + delta >= 0` guard). Retailer and wholesaler see **numerically identical** balances
for the same binding — no second ledger, no drift.

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

At migration time (§2.9), the existing `public.retailers`, `public.wholesaler_retailer_bindings`, and
per-tenant `users` rows are **inventoried, not modified destructively**. The migration (after a clean
preflight): adds `tenant_user_id` (NULL for all existing bindings), adds `public.retailers.email_verified_at`
(NULL for all existing rows), backfills invitation expiry, adds invitation revoke columns, creates
`retailer_credential_setup_tokens` and `retailer_password_reset_tokens` (bound to the public identity per
§2.5a), seeds `retailer_operator` + permissions per live-registry tenant, and adds `ux_users_email_active`.

### 7.2 Existing retailers without a login identity

Existing `public.retailers` / binding rows created before this change have `tenant_user_id = NULL` and
`email_verified_at = NULL` (the F-01 gap). These are **not** silently given credentials, a mapping, or a
verified email. Instead:

- They remain valid business entities with their bindings and historical orders intact.
- A wholesaler admin may **re-issue a credential setup invitation** to such a retailer (setup reissue is
  allowed precisely because the retailer has no established password, §2.4). Acceptance creates the
  missing tenant user, writes back `binding.tenant_user_id` (§2.1 step 4), and issues a setup token bound
  to `(retailer_id, binding_id)` — respecting the §1.4 collision rules and the §2.9 preflight. The
  canonical email is verified when the retailer consumes the setup token (§2.5c).
- Until then, they simply cannot log in — which is the safe, current state.

### 7.3 Forward-only, fail-closed on ambiguity

- **No silent merges:** if two `public.retailers` rows share an email but differ in phone, they remain
  distinct identities (§1.4). The migration does not collapse them.
- **No destructive cleanup:** no retailer/binding/user/order/payment row is deleted or rewritten by the
  migration.
- **Fail closed on ambiguous email/mapping:** the §2.9 preflight detects duplicate emails, conflicting
  `tenant_user_id` mappings/hashes, and incompatible catalog objects **before mutation**. On any
  ambiguity, the migration **does not guess** — it writes a reconciliation report and aborts, surfacing
  the case for manual OPS resolution.

### 7.4 Wholesaler-owner login behavior unchanged

`POST /api/v1/auth/login` (owner) is untouched (§3.4). Existing owners, admins, and staff log in exactly
as before; DC-3B owner credential propagation is unchanged (§2.2).

---

## 8. Implementation Slicing (independently reviewable)

Each slice is reviewable on its own and leaves the system in a working state.

### R1-S1 — Identity mapping / provisioning / unified credentials / invitation atomicity (F-01, F-02, F-04)

- Migration `036_retailer_mvp_identity` (§2.9): `tenant_user_id` column + uniqueness,
  `public.retailers.email_verified_at`, invitation expiry/revoke columns,
  `retailer_credential_setup_tokens` + `retailer_password_reset_tokens` (bound to public identity per
  §2.5a), `retailer_operator` seed, `ux_users_email_active`; live-registry enumeration + read-only
  preflight.
- Rewrite `register_with_invitation` as the §2.1 atomic transaction (with `tenant_user_id` write-back,
  unified-credential resolution §2.2, fail-closed SMTP to canonical email §2.4, rollback §2.7,
  conditional-update single-use §4.3).
- `resolve_client_identity` → `token.user_id → binding.tenant_user_id` (§1.3, no email).
- `POST /api/v1/retailers/setup-credential` (§2.5c; verifies canonical email, writes all mapped copies).
- **Retailer self-service** `POST /api/v1/client/auth/forgot-password` + `POST /api/v1/client/auth/reset-password`
  (neutral, hash-only, finite/single-use, JSON body; reset writes all mapped copies for the `retailer_id`,
  §2.5b). **No wholesaler password-reset endpoint.**
- `POST /api/v1/invitations/{id}/revoke` + `invitations:revoke` (§4.2).
- `POST /api/v1/retailers/{retailer_id}/reissue-setup` — restricted to the no-established-password window,
  canonical email only, else `CREDENTIAL_ALREADY_ESTABLISHED` (§2.4).
- **Reviewable proof:** T1, T4a–T4e, T5a–T6, T7, T10, T11–T24 (§9).

### R1-S2 — Supplier-scoped login / privacy (F-03, F-09)

- New `POST /api/v1/client/auth/login` with the six preconditions (§3.2); single contextual token; no
  `available_tenants`.
- Frontend `/retail/login?w=<code>` → `ClientLoginPage` (§3.1, §3.5); `SetupCredentialPage` honoring the
  §4.5 link contract.
- Wholesaler-owner `/api/v1/auth/login` untouched (§3.4).
- Deprecate `GET /api/v1/invitations/{code}` path-token pre-flight in favor of body-POST lookup (§4.5).
- **Reviewable proof:** T2, T8, T9, T14 (§9).

### R1-S3 — Retailer financial UI + role guards (F-05, F-06)

- New `GET /api/v1/client/finance`, `GET /api/v1/client/payments` (retailer-scoped, §6.2).
- `RetailerRoute` / `WholesalerRoute` frontend guards (§5.4).
- `/client/finance` page + Finance tab (§6.4).
- Route-authorization policy test extended to classify `retailer_operator` and assert denial of all
  wholesaler-management + platform routes (§5.2).
- **Reviewable proof:** T3, T15 (§9).

### R1-S4 — Cross-environment + runtime journey closure

- Worktree-local Poetry env with lockfile-faithful deps (bcrypt 4.0.1 / passlib 1.7.4 — per DC-12R0-R1,
  the parent-venv bcrypt 5.0.0 broke `test_dc3b`).
- Full end-to-end journey test (T1) and the entire test matrix run in that env.
- Close F-10/F-11 if time permits, else R2.
- **Reviewable proof:** green T1–T24 in a clean environment with provenance.

### Sequencing

R1-S1 must land before R1-S2 (provisioning + mapping must exist before login targets it). R1-S3 depends
on R1-S2. R1-S4 depends on all three. F-07/F-10/F-11 are R2.

---

## 9. Required Test Matrix

Every test runs in the worktree-local Poetry environment (lockfile-faithful deps). Each test has a
deterministic assertion; no flaky or environment-attributable failure is accepted.

| ID | Scenario | Asserts | Slice |
|---|---|---|---|
| **T1** | Fresh invitation → setup password → login → order → payment | End-to-end success; retailer authenticates, creates an order, pays; balance updates; all provisioning artifacts exist incl. `binding.tenant_user_id` | R1-S1/S2/S4 |
| **T2** | Same retailer R with wholesalers A+B, entering via A reveals only A | A-session has no `available_tenants`, no B name/code/id; A token has only A context | R1-S2 |
| **T3** | A-session cannot read B product/price/order/payment/balance | Each cross-tenant read returns 404/empty; no B data in any A response | R1-S2/S3 |
| **T4a** | Duplicate (replayed) invitation consumption | Second consume → `INVITATION_ALREADY_USED` (410) | R1-S1 |
| **T4b** | Concurrent invitation consumption | Exactly one 200; other `INVITATION_ALREADY_USED` (410); one binding/user | R1-S1 |
| **T4c** | Revoked invitation | After revoke, consume → `INVITATION_REVOKED` (410) | R1-S1 |
| **T4d** | Expired invitation | Consume after `expires_at` → `INVITATION_EXPIRED` (410) | R1-S1 |
| **T4e** | Phone-mismatched invitation | `INVITATION_PHONE_MISMATCH` (409) | R1-S1 |
| **T5a** | Duplicate email, same wholesaler | `RETAILER_EMAIL_ALREADY_BOUND` (409); no second user | R1-S1 |
| **T5b** | Phone-change case | Phone update does not affect login/mapping; match only at acceptance | R1-S1 |
| **T6** | Duplicate email, different wholesaler (unified identity) | Distinct tenant users in A and B; both bindings carry their own `tenant_user_id`; one effective password (§2.2) | R1-S1/S2 |
| **T7** | Transaction rollback with zero partial state | Force failure at each of §2.7 steps (incl. SMTP); no newly-created retailer/binding/user/mapping/token survives | R1-S1 |
| **T8** | Retailer denied wholesaler + platform routes | `retailer_operator` token → 403 on every wholesaler-management + `/platform/**` route | R1-S3 |
| **T9** | Wholesaler-owner login behavior unchanged | Owner `/auth/login` → identity JWT → `available_tenants` → `/select-tenant` exactly as before | R1-S2 |
| **T10** | Setup-before-login fails closed | `password_hash IS NULL` → `INVALID_CREDENTIALS`; no enumeration | R1-S1 |
| **T11** | `token.user_id` maps to exact retailer binding without email lookup | Authenticated client request resolves `retailer_id` via `binding.tenant_user_id`; no `users.email`/`retailers.email` read in the resolution path (asserted by query inspection/mock) | R1-S1 |
| **T12** | Unrelated users sharing email are never linked or password-updated | A second `retailer_id` whose tenant user coincidentally shares the email is **not** linked to the first retailer's binding, and a password reset for retailer R1 does **not** change R2's tenant-user hash (update keyed on `retailer_id`, not email) | R1-S1 |
| **T13** | A+B credential setup and reset preserve one effective password | After R sets a password via A, the B copy has the identical hash (copied per §2.2); a retailer self-service reset updates **both** mapped copies; both logins accept the same password | R1-S1 |
| **T14** | Inactive / missing / wrong-wholesaler binding denies login | Each of the six §3.2 precondition failures returns neutral `INVALID_CREDENTIALS` (or controlled 403) with no other-supplier disclosure | R1-S2 |
| **T15** | User without `retailer_operator` cannot use client login | A wholesaler-staff tenant user authenticating at `/client/auth/login` → `INVALID_CREDENTIALS` (neutral) | R1-S2/S3 |
| **T16** | SMTP failure rolls back every provisioning row | SMTP raised during §2.1 → 503 `SETUP_EMAIL_DELIVERY_FAILED`; zero committed rows; invitation **not** consumed (retriable) | R1-S1 |
| **T17** | Setup reissue (pre-password) revokes the previous token | `POST /retailers/{id}/reissue-setup` while no password established → prior active setup token `revoked_at` set; new token issued; old link → `SETUP_TOKEN_INVALID`; email sent only to canonical email | R1-S1 |
| **T18** | Wholesaler cannot reset retailer password | No wholesaler password-reset endpoint exists; any attempt (incl. via `reissue-setup` after a password is established) → `CREDENTIAL_ALREADY_ESTABLISHED` (409); retailer hash unchanged | R1-S1 |
| **T19** | Wholesaler cannot change verified canonical email | After `email_verified_at` is set, no wholesaler endpoint can alter `public.retailers.email`/`email_verified_at`; the column is immutable via wholesaler paths (asserted by route absence + service-layer guard) | R1-S1 |
| **T20** | A suspension leaves B login working | Wholesaler A suspends **its own** binding (`status=inactive`); R's login via B's portal still succeeds and returns B context; A's suspension did not touch B's binding or the shared credential | R1-S1/S2 |
| **T21** | Retailer reset updates A+B copies | A retailer self-service reset (via A's portal) writes the new hash to **both** the A and B tenant-user copies (same `retailer_id`); both logins accept the new password | R1-S1 |
| **T22** | Unrelated same-email user unchanged by reset | A reset for retailer R does not change an unrelated retailer Q's tenant-user hash even if Q's tenant user shares the email (reset keyed on `retailer_id`, §2.5a) | R1-S1 |
| **T23** | No supplier names disclosed in credential flows | `forgot-password`, `reset-password`, setup, and reissue responses never include another wholesaler's name/code/id; neutral acknowledgements only | R1-S1/S2 |
| **T24** | Used / expired / revoked reset tokens rejected | Each → `RESET_TOKEN_INVALID`; no password change; the one-active constraint prevents a second concurrent reset token for the same `retailer_id` | R1-S1 |

Additionally, the existing DC-12R0 validation suites must remain green (auth regressions, route
authorization policy, tenant isolation, global tenant filter, dc1g, pricing, orders, payments, finance
receivables, exports, dc3b credential recovery — all in the worktree-local env).

---

## 10. Mpango Is Not a Retailer Comparison Platform

**Explicit:** This design enforces wholesaler-centric privacy. A retailer session is **always**
single-wholesaler-scoped. There is no retailer-facing supplier list, no cross-wholesaler totals, no
balance comparison, no aggregation. Unified identity is a security capability (one canonical retailer,
many private relationships), not a product feature for browsing suppliers. The supplier-private login
(§3) makes cross-wholesaler disclosure **impossible at the source** for retailers.

---

## 11. Quality Gates (this design task)

This is a docs-only deliverable. The gates below are met by this document:

- **`git diff --check`:** clean (no whitespace errors).
- **ASCII/mojibake scan:** UTF-8, no U+FFFD replacement characters (CJK quotations are intentional).
- **detect-secrets:** `results: {}` on this file (no secrets, tokens, or production credentials).
- **pre-commit:** trailing-whitespace, end-of-file-fixer, detect-secrets all pass on the report.
- **GitNexus analyze/status:** analyze succeeds; status up-to-date; no execution flow affected (docs-only).
- **base..HEAD docs-only proof:** only this `.md` file is changed; zero `.py/.tsx/.ts/.sql/.yaml/.toml/
  .json/.lock/.env/.sh` files changed.

Exact proof is recorded in the commit and the push output.

---

## 12. Unresolved Architectural Decisions

**None.** Every required decision is resolved: the identity mapping is explicit and authoritative
(`binding.tenant_user_id`); credentials are unified across mapped copies with explicit conflict handling
recovered **only** by the retailer; email delivery is fail-closed; retailer login has six explicit
preconditions; the migration contract is fixed (`036`, down_revision `035`, live-registry enumeration,
read-only preflight, forward-only); the link contract is exact and BrowserRouter-compatible. D-R2
additionally resolves the **trust boundary**: the canonical verified email and the password are
**retailer-owned** — wholesalers can neither reset a password nor alter a verified email nor reissue
setup once a password exists (§2.4, §2.5, §2.6); credential tokens are bound to the public identity
(`retailer_id`/`binding_id`), never inferred from email or schema strings (§2.5a); retailer self-service
forgot/reset is provided (§2.5b). The design requires exactly one forward-only migration and introduces
no backward-incompatible change to wholesaler-owner or DC-3B behavior. No STOP condition applies.

---

## 13. Verdict

**PASS_FOR_CTO_DC12R1_S1_IMPLEMENTATION**

The design is complete, internally consistent, grounded in the audited source, and resolves all
DC-12R0/R1 findings on the retailer MVP critical path. R1 made the retailer identity mapping explicit
(`tenant_user_id`) and unified credentials; D-R2 tightened the trust model so credentials and the
verified email are retailer-owned, removed wholesaler password reset, restricted setup reissue to the
pre-password window, bound credential tokens to the public identity, and added retailer self-service
recovery. It is ready to be split into the R1-S1 … R1-S4 implementation slices, each independently
reviewable against the §9 test matrix (T1–T24).
