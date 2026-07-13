# DC-11P0 Platform Operator Identity + Credential Lifecycle Contract

| Field | Value |
|---|---|
| Date | 2026-07-14 |
| Task ID | DC-11P0 (Platform Operator Identity + Credential Lifecycle Contract) |
| Mode | Docs/tests-only audit and contract. No runtime implementation. |
| Base | `origin/product-dev-recovered @ cb1b1fffc63ed19e320701043eed38b8f2bea0c7` |
| Branch | `opencode/dc11p0-platform-operator-identity-contract-2026-07-14` |
| Verdict | `PASS_FOR_CTO_DC11P1_IMPLEMENTATION` |

## 1. Current State Confirmation

### 1.1 Platform browser login uses the common /auth/login entry

**CONFIRMED.** Platform operators log in through `POST /api/v1/auth/login`
(`backend/api/v1/auth.py:232`) -- the same endpoint as regular tenant users.
No separate platform login endpoint exists. The frontend `LoginPage.tsx:58`
detects `super_admin` in the identity token roles after the common login and
routes to the platform dashboard. Evidence: `auth.py:232-236`,
`frontend/src/services/authService.ts:15-16`.

### 1.2 Platform access requires identity-only global super_admin

**CONFIRMED.** The platform guard (`backend/api/v1/platform/p10/guard.py:81`)
requires ALL three: (a) valid JWT auth context, (b) `super_admin` role in
token, (c) token must be identity-only (`tenant_id is None or tenant_schema
is None`). A contextual super_admin token (with tenant context) is rejected
with 403 `PLATFORM_ACCESS_DENIED`. Evidence: `guard.py:61-84, 155-174`,
`core/security.py:66-68, 71-73`.

### 1.3 Current global role is derived from tenant-local user roles

**CONFIRMED.** The `super_admin` role is aggregated from tenant-local
`user_roles` at login (`backend/api/v1/auth.py:268`: `all_roles = sorted({r
for m in matches for r in m.roles})`) and stamped into the identity JWT.
There is NO global/platform-level role table. The role originates as a
tenant-local `roles.name` / `user_roles` row. Evidence: `crud/user.py:74-79`,
`auth.py:268, 287-298`, `models/user.py:52-57`.

### 1.4 No dedicated platform operator identity/provisioning/recovery path exists

**CONFIRMED.** No `platform_operators` or `platform_users` table/model exists
in `backend/models/`. No platform-specific signup, provisioning, or
forgot/reset password endpoint exists under `backend/api/v1/platform/`.
Operator provisioning is implicitly "give a tenant user the tenant-local
`super_admin` role" with no dedicated flow. The common forgot/reset
endpoints (`auth.py:708-812`) are tenant-user oriented.

### 1.5 X-Platform-Operator is machine/server-only and forbidden in browsers

**CONFIRMED.** The guard docstring (`guard.py:8-11`) states: "The frontend
never receives or sends PLATFORM_OPERATOR_SECRET." The frontend
`platformApi.ts:11-13` explicitly states no X-Platform-Operator secret is
sent or stored. A code search across `frontend/` found only comments and a
test assertion -- no code path attaches the header to outgoing requests.

## 2. Problem Statement

The current architecture has a security gap: platform operator identity is
derived from tenant-local RBAC. A tenant-local `super_admin` role (which can
be granted by any tenant admin via the RBAC system) is promoted to a "global"
platform-access claim purely by being unioned across tenants into the identity
JWT. This means:

- Any tenant admin can grant platform access by assigning `super_admin` to a
  user in their tenant.
- There is no platform-scope role revocation (removing the tenant-local role
  is the only way to revoke platform access).
- There is no dedicated operator lifecycle (provisioning, recovery, lockout,
  disable, audit).
- There is no maker-checker separation for platform operations.

## 3. Design Requirements

### 3.1 One customer-facing login entry

Keep the single `POST /auth/login` entry. Platform operators authenticate
through the same endpoint. The identity JWT will carry a new `platform_role`
claim (separate from tenant-local `roles`) when the authenticated email maps
to a platform operator record. The platform guard will check `platform_role`
instead of (or in addition to) the tenant-local `super_admin` role.

### 3.2 Global platform role must not derive from tenant-local RBAC

Introduce a `platform_operators` table in the public schema with:
- `id` UUID PK
- `email` VARCHAR UNIQUE (the operator's email; normalized to lowercase)
- `email_hash` VARCHAR(128) (SHA-256 of normalized email for indexing)
- `password_hash` VARCHAR(255) (bcrypt hash; NULL until first setup)
- `status` VARCHAR (pending_setup, active, disabled, locked)
- `role` VARCHAR (platform_admin, platform_operator)
- `setup_token_hash` VARCHAR(128) (HMAC-SHA256 hash; NULL after setup)
- `setup_token_expires_at` TIMESTAMPTZ
- `setup_token_used_at` TIMESTAMPTZ (NULL until consumed)
- `reset_token_hash` VARCHAR(128) (HMAC-SHA256 hash; NULL when no active reset)
- `reset_token_expires_at` TIMESTAMPTZ
- `reset_token_used_at` TIMESTAMPTZ
- `failed_login_attempts` INT DEFAULT 0
- `locked_until` TIMESTAMPTZ (NULL when not locked)
- `last_login_at` TIMESTAMPTZ
- `revoked_at` TIMESTAMPTZ (NULL when active)
- `created_by` UUID (the inviting operator's id; NULL for bootstrap)
- `created_at`, `updated_at`, `is_deleted`, `deleted_at` (AuditMixin)

The platform guard will verify the `platform_role` claim from the JWT, which
is set at login ONLY when the email matches an active `platform_operators`
row. Tenant-local `super_admin` will NO LONGER grant platform access.

### 3.3 Operator accounts are invite/bootstrap-only; no public signup

No public `/platform/signup` endpoint. Operators are provisioned by:
- **Bootstrap**: a CLI/management command creates the first operator with a
  setup token (no plaintext password). The setup token is displayed once to
  the bootstrap operator (or written to a secure file). The first operator
  uses the setup-credential flow to set their password.
- **Invite**: an active `platform_admin` invites a new operator via
  `POST /api/v1/platform/operators/invite`. This creates a `platform_operators`
  row with `status=pending_setup` and issues a setup token delivered once via
  email (or secure out-of-band channel for the first operator after bootstrap).

### 3.4 First-operator secure bootstrap without default/random passwords

The bootstrap command (`python -m scripts.bootstrap_platform_operator --email
<email>`) will:
- Create a `platform_operators` row with `status=pending_setup`,
  `password_hash=NULL`.
- Generate a setup token (raw token returned to stdout ONCE or written to a
  file with mode 0600).
- The raw token is never stored; only `setup_token_hash` is persisted.
- The operator navigates to `/setup-credential?setupToken=<token>` (frontend)
  and POSTs the token + new password to `POST /api/v1/platform/operators/
  setup-credential`.
- No default or random password is ever seeded.

### 3.5 Setup, forgot/reset, revoke, disable, lockout, audit lifecycle

| Lifecycle event | Mechanism |
|---|---|
| **Setup** | `POST /platform/operators/setup-credential` (body-only token; hash-only lookup; single-use; 24h TTL) |
| **Forgot password** | `POST /platform/operators/forgot-password` (neutral 200; creates reset token; email delivered; fail-closed in production) |
| **Reset password** | `POST /platform/operators/reset-password` (body-only token; hash-only; single-use; 1h TTL; updates password_hash) |
| **Revoke** | `POST /platform/operators/{id}/revoke` (platform_admin only; sets `revoked_at`; immediate session invalidation via JWT expiry) |
| **Disable** | `POST /platform/operators/{id}/disable` (platform_admin only; sets `status=disabled`; blocks future logins) |
| **Lockout** | Automatic after 5 failed login attempts; sets `locked_until = now + 15min`; `failed_login_attempts` resets on successful login |
| **Audit** | Every lifecycle event (setup, login, reset, revoke, disable, lockout, invite) writes to `platform_audit_logs` with `actor_type=platform_operator` |

### 3.6 Hash-only token storage

All setup and reset tokens are stored as HMAC-SHA256 hashes (reusing the
existing `hash_token` function from `onboarding_service.py`). Raw tokens
exist only in memory and the email/setup channel. Never logged. Never in
query strings (body-only).

### 3.7 Maker-checker (two-operator requirement)

- At least two distinct human operators must exist before any destructive
  platform action (revoke, disable, delete tenant).
- The inviting operator (`created_by`) and the invited operator must be
  different humans.
- The bootstrap creates exactly one operator; a second must be invited before
  destructive actions are permitted. The API enforces: if
  `count(active_operators) < 2`, destructive endpoints return 409
  `MAKER_CHECKER_MINIMUM_NOT_MET`.

### 3.8 No plaintext password or shared operator secrets

- No plaintext password is ever seeded, stored, or logged.
- No shared operator secret exists (each operator has their own
  `password_hash`).
- The `X-Platform-Operator` machine secret remains server-only and is NOT
  used for browser auth.

## 4. Schema / Migration Plan

### 4.1 New migration: `032_platform_operators.py`

- `down_revision`: current single head (verify at implementation time).
- Creates `public.platform_operators` table with the columns in Section 3.2.
- Unique index on `email`; unique partial index on `email_hash WHERE
  is_deleted = false`.
- Unique partial index on `setup_token_hash WHERE setup_token_used_at IS
  NULL AND revoked_at IS NULL`.
- Unique partial index on `reset_token_hash WHERE reset_token_used_at IS
  NULL AND revoked_at IS NULL`.
- Does NOT modify existing tables (additive only).

### 4.2 Login integration

The `/auth/login` handler will be extended to:
1. After successful tenant-user password verification, check if the email
   matches an active `platform_operators` row.
2. If yes, add `platform_role` to the identity JWT claims (in addition to
   tenant roles).
3. The platform guard checks `platform_role` (not tenant `super_admin`).

### 4.3 Platform guard update

`guard.py` will accept EITHER:
- `token.platform_role` in `["platform_admin", "platform_operator"]` (new
  path), OR
- The `X-Platform-Operator` machine secret (unchanged, server-only).

Tenant-local `super_admin` will NO LONGER be sufficient for browser-based
platform access. This is a breaking change for existing operators who have
only the tenant-local role; they must be bootstrapped into the new
`platform_operators` table.

## 5. API Slices (DC-11P1+)

| Endpoint | Method | Scope | Description |
|---|---|---|---|
| `/platform/operators/setup-credential` | POST | Public (token-gated) | Set password from setup token |
| `/platform/operators/forgot-password` | POST | Public (neutral 200) | Request reset email |
| `/platform/operators/reset-password` | POST | Public (token-gated) | Set new password from reset token |
| `/platform/operators` | GET | platform_admin | List operators (sanitized) |
| `/platform/operators/invite` | POST | platform_admin | Invite new operator |
| `/platform/operators/{id}` | GET | platform_admin | Get operator detail (sanitized) |
| `/platform/operators/{id}/disable` | POST | platform_admin | Disable operator |
| `/platform/operators/{id}/revoke` | POST | platform_admin | Revoke operator |
| `/platform/operators/{id}/enable` | POST | platform_admin | Re-enable operator |

## 6. Frontend Slices (DC-11P2+)

- `/platform/operators` -- operator management console (list, invite, disable,
  revoke).
- `/setup-credential` -- reuse the existing page (extend to handle platform
  operator setup tokens).
- `/forgot-password` -- reuse the existing page (extend to handle platform
  operator emails).
- `/reset-password` -- reuse the existing page (extend to handle platform
  operator reset tokens).

## 7. Threat Model

| Threat | Mitigation |
|---|---|
| Tenant admin grants platform access via tenant-local `super_admin` | Platform access requires `platform_operators` row; tenant role no longer sufficient |
| Brute-force platform operator login | Lockout after 5 attempts; 15min lock; bcrypt hash |
| Token interception | Body-only tokens; no query-string; HTTPS; short TTL (1h reset, 24h setup) |
| Token replay | Single-use (`used_at` set on consume); `with_for_update()` row lock |
| Privilege escalation by disabled/revoked operator | Login checks `status=active AND revoked_at IS NULL AND locked_until < now` |
| Single-operator takeover (no maker-checker) | Destructive actions require 2+ active operators |
| Bootstrap token leak | Raw token displayed once; file mode 0600; 24h TTL; single-use |
| Email enumeration via forgot-password | Neutral 200 always; no existence disclosure |
| Secret logging | Only exception class name logged; no raw tokens/passwords |
| X-Platform-Operator browser leak | Header never sent by frontend; documented and tested |

## 8. Rollback

- The migration is additive (new table only). Downgrade drops
  `platform_operators` and reverts the login/guard changes.
- The login handler reverts to checking tenant-local `super_admin`.
- The guard reverts to the current behavior.
- No existing data is modified or lost.

## 9. Tests (DC-11P1+)

| Test | Description |
|---|---|
| Bootstrap creates operator with setup token (no password) | setup_token_hash set; password_hash NULL; raw token returned once |
| Setup credential consumes token and sets password | Single-use; 24h TTL; hash-only lookup |
| Login with platform operator credentials | platform_role in JWT; tenant super_admin no longer sufficient alone |
| Login as disabled/revoked/locked operator | 401/403; no platform_role in JWT |
| Forgot-password neutral response | 200 for existing and non-existing email |
| Reset-password body-only token | Query-string rejected; hash-only; single-use; 1h TTL |
| Invite new operator | platform_admin only; creates pending_setup row; setup token issued |
| Revoke operator | platform_admin only; sets revoked_at; future logins blocked |
| Maker-checker minimum | Destructive action blocked when < 2 active operators |
| No plaintext password/token in response or logs | Sentinel exception test (like DC-10G) |
| Platform guard rejects tenant-local super_admin | Contextual super_admin token -> 403 |
| Lockout after 5 failed attempts | failed_login_attempts increments; locked_until set |

## 10. Contract Tests (this gate)

Static contract tests that verify the current architecture matches the
assumptions in this document:

- Platform guard requires identity-only super_admin (not contextual).
- No platform operator model/table exists yet (confirming the gap).
- No platform-specific auth endpoints exist (confirming the gap).
- Login aggregates roles from tenant-local user_roles (confirming the gap).
- X-Platform-Operator is not sent by the frontend (contract assertion).

## 11. Allowed Files (DC-11P1+)

- `backend/alembic/versions/032_platform_operators.py` (new migration)
- `backend/models/platform_operator.py` (new model)
- `backend/api/v1/platform/operators.py` (new router)
- `backend/services/platform_operator_service.py` (new service)
- `backend/api/v1/auth.py` (extend login to set platform_role)
- `backend/api/v1/platform/p10/guard.py` (check platform_role)
- `backend/scripts/bootstrap_platform_operator.py` (CLI bootstrap)
- `backend/tests/test_dc11p1_platform_operator_identity.py` (new tests)
- `ai-ledger/product-ai/2026-07-14_dc11p1_platform_operator_implementation.md`

## 12. Forbidden Files

- Existing historical migrations (`<= 031`).
- Frontend files (DC-11P2 scope).
- Production compose/config/env.
- Lockfiles.
- `X-Platform-Operator` machine secret logic (unchanged).

## 13. Stop Conditions

- Baseline `cb1b1fff` has drifted.
- Alembic head is not single.
- `032` revision number is taken by another merged change.
- Maker-checker cannot be enforced without a broader design decision.
- Any secret would be printed or persisted.

## 14. Verdict

**PASS_FOR_CTO_DC11P1_IMPLEMENTATION**

All 5 current-state confirmations are verified with file:line evidence. The
design addresses the security gap (platform role derived from tenant-local
RBAC), defines a complete operator lifecycle, and scopes the implementation
into additive migration + API + frontend slices. The contract tests verify
the current architecture matches the assumptions. No unresolved design
decisions remain.
