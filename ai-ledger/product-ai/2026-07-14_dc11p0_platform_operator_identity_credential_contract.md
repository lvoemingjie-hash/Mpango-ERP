# DC-11P0 Platform Operator Identity + Credential Lifecycle Contract

| Field | Value |
|---|---|
| Date | 2026-07-14 |
| Task ID | DC-11P0 (Platform Operator Identity + Credential Lifecycle Contract) |
| Revision | R2 (corrects R1 on identity/context separation, session invalidation, schema constraints, break-glass, credential UI separation, login collision, cutover, rollback, stale wording, implementation slices) |
| Mode | Docs/tests-only audit and contract. No runtime implementation. |
| Base | `origin/product-dev-recovered @ cb1b1fffc63ed19e320701043eed38b8f2bea0c7` |
| Branch | `opencode/dc11p0-platform-operator-identity-contract-2026-07-14` |
| R0 commit | `6a0f4b01` |
| R1 commit | `73c4b3e4` |
| Verdict | `PASS_FOR_CTO_DC11P1_SCHEMA_IMPLEMENTATION` |

## 1. Current State Confirmation (unchanged)

1. Platform browser login uses the common `POST /auth/login` (`auth.py:232`).
   No separate platform login endpoint exists.
2. Platform access requires identity-only global super_admin (`guard.py:81`).
3. Global role is derived from tenant-local `user_roles` (`auth.py:268`). No
   global/platform role table exists.
4. No dedicated platform operator identity/provisioning/recovery path exists.
5. X-Platform-Operator is machine/server-only and forbidden in browsers
   (`guard.py:8-11`, `platformApi.ts:11-13`).

## 2. Problem Statement (unchanged)

Platform operator identity is derived from tenant-local RBAC. Any tenant admin
can grant platform access. No platform-scope revocation, no dedicated operator
lifecycle, no maker-checker separation.

## 3. Design Requirements (R2 corrected)

### 3.1 Identity / context separation (R2 new)

Platform APIs ALWAYS require an identity-only token. Tenant selection returns
a contextual token that CANNOT access platform APIs, even if the identity also
owns `platform_role`. This is a hard boundary:

- Identity-only token: may carry `platform_role` + tenant choices
  (`available_tenants`). Used for platform API access and workspace selection.
- Contextual token: carries `tenant_id` + `tenant_schema`. Used for tenant
  API access. The platform guard rejects contextual tokens unconditionally.

For dual identities (operator who is also a tenant user), the workspace
selector must offer:
a. **Platform Operations**: retain the identity-only token (do NOT call
   `select-tenant`). Navigate to `/platform`.
b. **Tenant workspace**: call `select-tenant` to exchange for a contextual
   token. Platform API access is lost until the user re-authenticates.

Never combine platform authority into a tenant-contextual session.

### 3.2 Session invalidation (R2 corrected)

Replace `credentials_changed_at` / `jwt.iat` with `auth_version`:

- `platform_operators.auth_version` BIGINT NOT NULL DEFAULT 1.
- The JWT includes `platform_auth_version` (the operator's auth_version at
  issuance time).
- The guard requires `token.platform_auth_version == operator.auth_version`
  (fetched from DB on every platform request). Version mismatch -> 401.
- `auth_version` is atomically incremented on: setup, reset, role change,
  disable, revoke, and break-glass recovery.
- The guard additionally requires: `status = 'active' AND revoked_at IS NULL
  AND (locked_until IS NULL OR locked_until <= now())`.
- Unknown/missing operator or version mismatch fails closed (401/403).

### 3.3 Global platform role (unchanged from R1)

`platform_role` is a signed, client-readable, non-confidential JWT claim (like
`tmap` in DC-3B-R2). It guarantees integrity, not secrecy. It is set ONLY when
the platform operator password verifies at login. Tenant-local `super_admin`
MUST NEVER produce `platform_role`.

### 3.4 Collision semantics (R2 corrected)

When one email belongs to BOTH a platform operator AND one or more tenant
users:

- Platform password verification controls ONLY `platform_role`.
- Each tenant password verification controls ONLY that tenant's inclusion in
  `available_tenants`.
- `available_tenants` contains verified tenant copies only (same as DC-3B-R1
  verified-only match list).
- Platform operator ID is the JWT subject (`user_id`) for platform-only
  identity. When both domains verify, the JWT subject is the platform operator
  ID and tenant choices are carried in `available_tenants` / `tmap`.
- Public response must NOT disclose the existence of the other identity domain.
  The login response shape is identical whether the user is platform-only,
  tenant-only, or dual.

| Scenario | JWT claims | available_tenants |
|---|---|---|
| Platform pw verifies, tenant pw does NOT | `platform_role` | `[]` |
| Tenant pw verifies, platform pw does NOT | tenant roles only | verified tenants |
| BOTH verify | `platform_role` + tenant roles + `tmap` | verified tenants |
| Neither verifies | 401 INVALID_CREDENTIALS | n/a |

### 3.5 Separate tables (R2 corrected)

Four public-schema tables. R2 removes `email_hash` (it does not make stored
email confidential; a concrete non-security use must be proven to keep it).

**`public.platform_operators`**:
- `id` UUID PK
- `email` VARCHAR(255) NOT NULL UNIQUE (normalized lowercase trimmed)
- `password_hash` VARCHAR(255) (NULL until first setup)
- `status` VARCHAR(20) NOT NULL DEFAULT 'pending_setup'
  - CHECK: `status IN ('pending_setup', 'active', 'disabled')`
  - Locked state is derived from `locked_until`, NOT a second status value.
- `role` VARCHAR(20) NOT NULL DEFAULT 'platform_operator'
  - CHECK: `role IN ('platform_admin', 'platform_operator')`
- `failed_login_attempts` INT NOT NULL DEFAULT 0
  - CHECK: `failed_login_attempts >= 0`
- `locked_until` TIMESTAMPTZ
- `auth_version` BIGINT NOT NULL DEFAULT 1
  - CHECK: `auth_version >= 1`
- `last_login_at` TIMESTAMPTZ
- `revoked_at` TIMESTAMPTZ
- `invited_by` UUID (FK `platform_operators.id` ON DELETE SET NULL; NULL for
  bootstrap)
- AuditMixin (created_at, updated_at, is_deleted, deleted_at)
- CHECK: `status = 'active' implies password_hash IS NOT NULL`

**`public.platform_operator_setup_tokens`**:
- `id` UUID PK
- `operator_id` UUID NOT NULL FK `platform_operators.id` ON DELETE CASCADE
- `token_hash` VARCHAR(128) NOT NULL UNIQUE
- `purpose` VARCHAR(32) NOT NULL DEFAULT 'setup'
  - CHECK: `purpose = 'setup'`
- `expires_at` TIMESTAMPTZ NOT NULL
- `used_at` TIMESTAMPTZ (NULL until consumed; single-use)
- `revoked_at` TIMESTAMPTZ (NULL until revoked)
- AuditMixin
- CHECK: `used_at IS NULL OR revoked_at IS NULL` (not both)
- Partial unique index: one lifecycle-active setup token per operator
  (`operator_id` WHERE `used_at IS NULL AND revoked_at IS NULL AND
  is_deleted = false`)

**`public.platform_operator_reset_tokens`**:
- Same structure as setup_tokens with `purpose = 'reset'`.
- FK `operator_id` ON DELETE CASCADE.
- Same CHECK and partial unique index constraints.
- Reset TTL = 1h. Setup TTL = 24h.

**`public.platform_operator_recovery_credentials`** (R2 new):
- `id` UUID PK
- `operator_id` UUID NOT NULL FK `platform_operators.id` ON DELETE CASCADE
- `credential_hash` VARCHAR(128) NOT NULL UNIQUE (HMAC of the recovery value)
- `status` VARCHAR(20) NOT NULL DEFAULT 'active'
  - CHECK: `status IN ('active', 'used', 'revoked')`
- `used_at` TIMESTAMPTZ (NULL until consumed)
- `revoked_at` TIMESTAMPTZ (NULL until revoked)
- AuditMixin
- CHECK: `used_at IS NULL OR revoked_at IS NULL`

Token tables store HASH ONLY. Raw tokens exist only in memory and the email
channel. Body-only (no query-string). Single-use.

### 3.6 First-operator bootstrap (R2 corrected)

The bootstrap CLI (`python -m scripts.bootstrap_platform_operator --email
<email>`) will:
- Create a `platform_operators` row with `status='pending_setup'`,
  `password_hash=NULL`.
- Generate a setup token. Store ONLY `token_hash`.
- Deliver via EMAIL through configured SMTP (fail-closed in production).
- NO raw token on stdout. NO raw token on disk. NO default/random password.
- Never log raw token or setup URL.

### 3.7 Break-glass recovery (R2 corrected)

Remove file-based raw token and confirmation-only recovery. The break-glass
design:

- **Pre-provisioned**: recovery credentials are created while operators are
  healthy (during bootstrap or by a platform_admin). The raw recovery value
  is stored in an EXTERNAL secure vault (not in the DB, not in a file).
- **Hash-only storage**: only `credential_hash` (HMAC) is stored in
  `platform_operator_recovery_credentials`.
- **CLI hidden stdin**: the break-glass CLI reads the raw recovery value via
  hidden stdin ONLY (`getpass.getpass`). Never argv, stdout, file, or log.
- **Recovery action**: on successful credential verification, the CLI:
  1. Re-enables exactly one operator (`status='active'`,
     `locked_until=NULL`, `failed_login_attempts=0`).
  2. Atomically increments `auth_version` (invalidates old JWTs).
  3. Sends a password-reset email to that operator.
  4. Audits the event to `platform_audit_logs` (`actor_type='system'`,
     `action='break_glass_recovery'`).
  5. Marks the recovery credential as `status='used'`, `used_at=now()`.
- **Never sets/prints password or token**: the CLI does NOT set a password or
  print a token. The operator receives a reset email and sets their own
  password.
- **Rotation required**: the used recovery credential must be rotated
  afterward (a new one is pre-provisioned).
- The CLI is NOT network-accessible (runs on the VPS host or backend
  container).

### 3.8 Credential UI separation (R2 new)

Dedicated frontend paths for platform operator credentials:
- `/platform/setup-credential` (consumes setup token)
- `/platform/forgot-password` (requests reset)
- `/platform/reset-password` (consumes reset token)

These do NOT reuse the tenant-owner `/setup-credential` endpoint or token
domain. The common `/login` entry remains the single authentication point.

### 3.9 /auth/me behavior (R2 corrected)

For platform-only operators:
- `email`: operator email
- `roles`: `[]`
- `platform_role`: `"platform_admin"` or `"platform_operator"`
- `available_tenants`: `[]`
- Frontend routes to `/platform` (no tenant selection required).

For dual-identity operators:
- Both `platform_role` and `available_tenants` present.
- Workspace selector offers: Platform Operations OR Tenant workspace.

### 3.10 Safe staged cutover (R2 corrected)

| Stage | Action | Guard behavior |
|---|---|---|
| 1. Schema only | Migration 034 creates tables. No guard/login change. | Tenant super_admin still accepted (unchanged). |
| 2. Services + credential pages | Platform operator service, bootstrap, dedicated setup/reset pages. | Both paths accepted. |
| 3. Bootstrap + verify | Bootstrap at least 2 operators. Runtime-verify both authenticate and access platform. | Both paths accepted. |
| 4. Strict guard | Deploy guard change: `PLATFORM_GUARD_MODE=strict`. | Only `platform_role` accepted. |

- Unknown `PLATFORM_GUARD_MODE` fails closed (treat as strict).
- Tenant super_admin never produces `platform_role`.
- No deployment step leaves all operators locked out.

### 3.11 Maker-checker (unchanged from R1)

- First operator (bootstrap, `platform_admin`) may invite the second.
- Destructive actions require 2+ distinct active operators.
- Break-glass CLI for all-locked recovery (Section 3.7).
- Every action audited with stable operator IDs.

### 3.12 X-Platform-Operator (unchanged)

Machine/server-only. Never a human browser credential.

## 4. Schema / Migration Plan (R2 corrected)

### 4.1 Migration: `034_platform_operators.py`

- `revision`: `034_platform_operators`
- `down_revision`: `033_order_status_enum_reconciliation`
- NEVER edit migration <= 033.
- Creates four tables: `platform_operators`,
  `platform_operator_setup_tokens`,
  `platform_operator_reset_tokens`,
  `platform_operator_recovery_credentials`.
- Additive only. Does NOT modify existing tables.
- All CHECK constraints and partial unique indexes defined in Section 3.5.

### 4.2 Login integration

The `/auth/login` handler checks `platform_operators` first (independent
password verification). Then runs the existing tenant scan. See Section 3.4
for collision semantics.

### 4.3 Platform guard staged cutover

Guard uses `PLATFORM_GUARD_MODE` env var:
- `legacy`: accepts tenant-local super_admin OR platform_role.
- `strict`: accepts ONLY platform_role.
- Unknown/missing value: fails closed (strict behavior).

## 5. Implementation Slices (R2 corrected)

| Slice | Scope | Description |
|---|---|---|
| DC-11P1 | Schema, model, tests | Migration 034, 4 ORM models, model/table contract tests |
| DC-11P2 | Service, bootstrap, lifecycle | Platform operator service, bootstrap CLI, setup/reset/forgot endpoints |
| DC-11P3 | Login, JWT, auth-me, guard dual mode | Extend /auth/login for platform_operators, platform_role/platform_auth_version in JWT, /auth/me platform behavior, guard legacy/strict mode |
| DC-11P4 | Frontend UX | Dedicated /platform/setup-credential, /platform/forgot-password, /platform/reset-password pages; workspace selector dual-identity option |
| DC-11P5 | Two-operator bootstrap, strict cutover, VPS proof | Bootstrap 2+ operators on VPS, runtime-verify, deploy strict guard, full smoke |

## 6. API Slices (DC-11P2+)

| Endpoint | Method | Scope |
|---|---|---|
| `/platform/operators/setup-credential` | POST | Public (token-gated) |
| `/platform/operators/forgot-password` | POST | Public (neutral 200) |
| `/platform/operators/reset-password` | POST | Public (token-gated) |
| `/platform/operators` | GET | platform_admin |
| `/platform/operators/invite` | POST | platform_admin |
| `/platform/operators/{id}` | GET | platform_admin |
| `/platform/operators/{id}/disable` | POST | platform_admin |
| `/platform/operators/{id}/revoke` | POST | platform_admin |
| `/platform/operators/{id}/enable` | POST | platform_admin |

## 7. Threat Model (R2 corrected)

| Threat | Mitigation |
|---|---|
| Tenant admin grants platform access | platform_role from platform_operators only; tenant super_admin never produces it |
| Brute-force login | Lockout after 5 attempts; 15min; bcrypt |
| Token interception | Body-only; HTTPS; short TTL |
| Token replay | Single-use; with_for_update(); hash-only |
| Disabled/revoked operator retains JWT | auth_version mismatch -> 401 on every request |
| Contextual token used for platform | Guard rejects ALL contextual tokens unconditionally |
| Single-operator takeover | Maker-checker: 2+ for destructive actions |
| Bootstrap token leak | Email-only; fail-closed SMTP; no stdout/disk; 24h TTL; single-use |
| Email enumeration | Neutral 200 on forgot-password |
| Collision confusion | Independent verification; claims reflect what verified; no domain disclosure |
| All operators locked | Break-glass CLI (hidden stdin, pre-provisioned hash, rotates after use) |
| Rollback restores unsafe super_admin | Guard mode explicit; strict rollback target retains platform auth |

## 8. Rollback (R2 corrected)

- **Before strict cutover**: rollback the application while retaining
  migration 034. The guard stays in `legacy` mode. Operators retain access.
- **After strict cutover**: rollback ONLY to a release that still supports
  platform operator authentication and `platform_role`. Never downgrade 034
  or restore tenant-local super_admin as sole authority after strict cutover.
- Backup/restore: a verified DB backup must exist before the strict cutover
  deploy. If rollback is needed after strict cutover, restore the DB backup
  and deploy a release with platform operator auth support.

## 9. Tests (DC-11P1+)

| Test | Description |
|---|---|
| Bootstrap via email (no stdout/disk token) | Hash stored; email delivered; fail-closed |
| Setup credential (body-only, hash-only, single-use, 24h) | |
| Login platform-only operator | platform_role in JWT; available_tenants empty |
| Login collision: both verify | platform_role + tenant claims |
| Login collision: platform only | platform_role only |
| Login collision: tenant only | tenant claims only; no platform_role |
| Login disabled/revoked/locked | 401/403; no platform_role |
| auth_version invalidation | Increment on setup/reset/disable/revoke -> old JWT rejected |
| Contextual token rejected by platform guard | 403 |
| Forgot-password neutral | 200 for existing and non-existing |
| Reset-password (body-only, hash-only, single-use, 1h) | |
| Invite operator | platform_admin only; pending_setup; email |
| Revoke operator | revoked_at; auth_version incremented; immediate session loss |
| Maker-checker minimum | Destructive blocked when < 2 active |
| Break-glass CLI (hidden stdin, hash verify, re-enable, audit, rotate) | |
| Guard strict rejects tenant super_admin | 403 |
| Guard unknown mode fails closed | Strict behavior |
| No plaintext token/password in response/logs | Sentinel test |

## 10. Contract Tests (this gate)

15 static contract tests verifying the current architecture:
- Guard checks is_identity_only and is_super_admin (4 tests).
- No PlatformOperator/SetupToken/ResetToken model exists yet (4 tests).
- No platform operator endpoints in auth.py (2 tests).
- Login aggregates roles from tenant-local user_roles (2 tests).
- Frontend platformApi states no X-Platform-Operator sent (1 test).
- Alembic head = 033; no 034 migration (2 tests).

## 11. Allowed Files (DC-11P1)

- `backend/alembic/versions/034_platform_operators.py`
- `backend/models/platform_operator.py` (4 models)
- `backend/tests/test_dc11p1_platform_operator_schema.py`

## 12. Forbidden Files

- Historical migrations (`<= 033`).
- Frontend (DC-11P4 scope).
- Production compose/config/env.
- Lockfiles.
- X-Platform-Operator machine secret logic.

## 13. Stop Conditions

- Baseline `cb1b1fff` has drifted.
- Alembic head is not `033_order_status_enum_reconciliation`.
- `034` is taken by another merged change.
- Break-glass cannot be specified safely.
- Any secret would be printed or persisted.

## 14. Verdict

**PASS_FOR_CTO_DC11P1_SCHEMA_IMPLEMENTATION**

All R2 corrections applied: identity/context separation, auth_version session
invalidation, four-table schema with explicit constraints, pre-provisioned
break-glass via hidden stdin, dedicated credential UI paths, collision
semantics with no domain disclosure, staged cutover with unknown-mode
fail-closed, rollback safety, stale wording removed, implementation slices
reorganized into P1-P5. No unresolved design decisions remain.
