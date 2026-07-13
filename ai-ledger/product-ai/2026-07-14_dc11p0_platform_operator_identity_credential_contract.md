# DC-11P0 Platform Operator Identity + Credential Lifecycle Contract

| Field | Value |
|---|---|
| Date | 2026-07-14 |
| Task ID | DC-11P0 (Platform Operator Identity + Credential Lifecycle Contract) |
| Revision | R1 (corrects R0 on migration numbering, collision semantics, session invalidation, staged cutover, break-glass, rollback safety) |
| Mode | Docs/tests-only audit and contract. No runtime implementation. |
| Base | `origin/product-dev-recovered @ cb1b1fffc63ed19e320701043eed38b8f2bea0c7` |
| Branch | `opencode/dc11p0-platform-operator-identity-contract-2026-07-14` |
| R0 commit | `6a0f4b01` |
| Verdict | `PASS_FOR_CTO_DC11P1_SCHEMA_IMPLEMENTATION` |

## 1. Current State Confirmation (unchanged from R0)

### 1.1 Platform browser login uses the common /auth/login entry

CONFIRMED. Platform operators log in through `POST /api/v1/auth/login`
(`backend/api/v1/auth.py:232`). No separate platform login endpoint exists.
Evidence: `auth.py:232-236`, `frontend/src/services/authService.ts:15-16`.

### 1.2 Platform access requires identity-only global super_admin

CONFIRMED. The platform guard (`guard.py:81`) requires ALL three: valid JWT
auth context, `super_admin` role, and identity-only token (`tenant_id is None
or tenant_schema is None`). Evidence: `guard.py:61-84, 155-174`.

### 1.3 Current global role is derived from tenant-local user roles

CONFIRMED. `super_admin` is aggregated from tenant-local `user_roles`
(`auth.py:268`) and stamped into the identity JWT. No global/platform role
table exists. Evidence: `crud/user.py:74-79`, `auth.py:268, 287-298`.

### 1.4 No dedicated platform operator identity/provisioning/recovery path exists

CONFIRMED. No `platform_operators` table/model. No platform-specific
signup/provisioning/recovery endpoint.

### 1.5 X-Platform-Operator is machine/server-only and forbidden in browsers

CONFIRMED. Guard docstring (`guard.py:8-11`) and frontend `platformApi.ts`
confirm the header is never sent by the browser.

## 2. Problem Statement (unchanged from R0)

Platform operator identity is derived from tenant-local RBAC. A tenant-local
`super_admin` role (grantable by any tenant admin) is promoted to a "global"
platform-access claim purely by being unioned into the identity JWT. This
means any tenant admin can grant platform access, with no platform-scope
revocation, no dedicated operator lifecycle, and no maker-checker separation.

## 3. Design Requirements (R1 corrected)

### 3.1 One customer-facing login entry

Keep the single `POST /auth/login` entry. Platform operators authenticate
through the same endpoint. R1 correction: platform operator authentication
must be INDEPENDENT of tenant users. A platform-only operator with no
tenant-local user must be able to authenticate safely through /auth/login.

The login handler will be extended to:
1. First check `public.platform_operators` for the email. If found and
   active, verify the platform password independently. If it verifies, issue
   an identity JWT with `platform_role` set from the operator record.
2. Then check tenant schemas (existing flow). If any tenant copy verifies,
   issue tenant claims as today.
3. If BOTH platform and tenant passwords verify (collision case), the JWT
   carries BOTH `platform_role` AND tenant claims. See Section 3.3.

### 3.2 Global platform role must not derive from tenant-local RBAC

R1 correction: `platform_role` is a signed JWT claim that is client-readable
and non-confidential (like `tmap` in DC-3B-R2). It guarantees integrity (not
secrety). It is set ONLY when the platform operator password verifies at
login. Tenant-local `super_admin` MUST NEVER produce `platform_role`. The
platform guard checks `platform_role`, not tenant `super_admin`.

### 3.3 Collision semantics (R1 new)

When one email belongs to BOTH a platform operator AND one or more tenant
users:

| Scenario | JWT claims | Behavior |
|---|---|---|
| Platform password verifies, tenant password does NOT | `platform_role` only | Operator can access platform; cannot select tenants (no tenant matches) |
| Tenant password verifies, platform password does NOT | tenant claims only (no `platform_role`) | User can select tenants; cannot access platform |
| BOTH verify | `platform_role` AND tenant claims | Full access: platform + tenant selection |
| Neither verifies | 401 INVALID_CREDENTIALS | Login rejected |

The login handler verifies the platform password against
`platform_operators.password_hash` and the tenant password(s) against
tenant-local `users.password_hash` independently. They may differ.

### 3.4 Separate token tables (R1 corrected)

Three separate public-schema tables:

**`public.platform_operators`**:
- `id` UUID PK
- `email` VARCHAR UNIQUE NOT NULL (normalized lowercase)
- `email_hash` VARCHAR(128) NOT NULL (SHA-256 of normalized email)
- `password_hash` VARCHAR(255) (NULL until first setup)
- `status` VARCHAR NOT NULL DEFAULT 'pending_setup' (pending_setup, active, disabled, locked)
- `role` VARCHAR NOT NULL DEFAULT 'platform_operator' (platform_admin, platform_operator)
- `failed_login_attempts` INT NOT NULL DEFAULT 0
- `locked_until` TIMESTAMPTZ
- `credentials_changed_at` TIMESTAMPTZ NOT NULL DEFAULT now() (for session invalidation)
- `last_login_at` TIMESTAMPTZ
- `revoked_at` TIMESTAMPTZ
- `invited_by` UUID (FK platform_operators.id; NULL for bootstrap)
- AuditMixin (created_at, updated_at, is_deleted, deleted_at)

**`public.platform_operator_setup_tokens`**:
- `id` UUID PK
- `operator_id` UUID NOT NULL FK platform_operators.id
- `token_hash` VARCHAR(128) NOT NULL UNIQUE
- `purpose` VARCHAR(32) NOT NULL DEFAULT 'setup'
- `expires_at` TIMESTAMPTZ NOT NULL
- `used_at` TIMESTAMPTZ
- `revoked_at` TIMESTAMPTZ
- AuditMixin

**`public.platform_operator_reset_tokens`**:
- `id` UUID PK
- `operator_id` UUID NOT NULL FK platform_operators.id
- `token_hash` VARCHAR(128) NOT NULL UNIQUE
- `purpose` VARCHAR(32) NOT NULL DEFAULT 'reset'
- `expires_at` TIMESTAMPTZ NOT NULL
- `used_at` TIMESTAMPTZ
- `revoked_at` TIMESTAMPTZ
- AuditMixin

Token tables store HASH ONLY. Raw tokens exist only in memory and the email
channel. Body-only (no query-string). Single-use. Setup TTL = 24h, Reset
TTL = 1h.

### 3.5 First-operator bootstrap (R1 corrected)

The bootstrap command (`python -m scripts.bootstrap_platform_operator --email
<email>`) will:
- Create a `platform_operators` row with `status=pending_setup`,
  `password_hash=NULL`.
- Generate a setup token. Store ONLY `token_hash` in
  `platform_operator_setup_tokens`.
- Deliver the setup token VIA EMAIL through the configured SMTP provider
  (reusing the existing `email_delivery.py` fail-closed mechanism).
- NO raw token on stdout. NO raw token written to disk. NO default or random
  password.
- Production email failure MUST fail closed (no token committed without
  delivery). The operator navigates to `/setup-credential?setupToken=<token>`
  from the email.
- Never log the raw token or setup URL.

### 3.6 Immediate session invalidation (R1 new)

Two complementary mechanisms:

1. **`credentials_changed_at` guard**: Every platform operator JWT includes
   a `iat` (issued-at) claim. The platform guard checks
   `operator.credentials_changed_at > jwt.iat`. If true, the JWT is stale
   (password was changed after issuance) and the guard rejects with 401.
2. **Active-state guard validation**: On every platform request, the guard
   fetches the operator row and checks `status=active AND revoked_at IS NULL
   AND locked_until IS NULL OR locked_until < now()`. If the operator was
   disabled/revoked/locked AFTER the JWT was issued, the guard rejects with
   401/403.

This ensures disabled/revoked operators lose access IMMEDIATELY, not at JWT
expiry.

### 3.7 /auth/me behavior for platform-only operators (R1 new)

`GET /auth/me` returns:
- `email`: the operator email
- `roles`: `[]` (no tenant roles for a platform-only operator)
- `platform_role`: `"platform_admin"` or `"platform_operator"` (new field)
- `available_tenants`: `[]` (no tenant matches for a platform-only operator)

Frontend routing: if `platform_role` is present and `available_tenants` is
empty, route directly to `/platform` (platform dashboard). Do NOT require
tenant selection. If both `platform_role` and `available_tenants` are
present, show the workspace selector (tenant selection) as today, with
platform access available after any selection or none.

### 3.8 Safe staged cutover (R1 new)

| Stage | Action | Guard behavior |
|---|---|---|
| 1. Add schema | Migration 034 creates tables. No guard change. | Tenant-local super_admin still accepted. |
| 2. Bootstrap operators | CLI bootstraps at least 2 operators via email. Verify both can log in and access platform. | Both paths accepted (tenant super_admin OR platform_role). |
| 3. Validate | Run smoke tests: both operators authenticate, platform_role in JWT, maker-checker enforced. | Both paths accepted. |
| 4. Switch guard | Deploy guard change: platform access requires `platform_role`. Tenant-local `super_admin` NO LONGER sufficient. | Only `platform_role` accepted. |

No deployment step leaves all operators locked out: stage 4 is deployed only
after stage 2 confirms at least 2 operators can authenticate. If stage 4
fails, rollback to stage 3 guard (both paths) -- operators retain access.

### 3.9 Maker-checker (R1 corrected)

- The first operator (bootstrap) is `platform_admin` and may invite the
  second.
- Destructive actions (revoke, disable, delete tenant) require two distinct
  active operators: the actor and a checker who approves.
- `count(active_operators) < 2` -> destructive endpoints return 409
  `MAKER_CHECKER_MINIMUM_NOT_MET`.
- Break-glass recovery: if ALL operators are disabled/locked, a CLI command
  (`python -m scripts.break_glass_platform_operator --email <email>`)
  re-enables one operator. This command:
  - Requires a file-based token (written by the CTO out-of-band) OR
    interactive confirmation.
  - Logs to `platform_audit_logs` with `actor_type=system`,
    `action=break_glass_enable`.
  - Is NOT network-accessible (CLI only, not an API endpoint).
- Every action is audited with stable operator IDs (the `platform_operators.id`
  UUID, never the email).

### 3.10 X-Platform-Operator remains machine/server-only (unchanged)

The header is for server/operator contexts only. The frontend never sends it.
It is NOT a human browser credential.

## 4. Schema / Migration Plan (R1 corrected)

### 4.1 Migration: `034_platform_operators.py`

- `revision`: `034_platform_operators`
- `down_revision`: `033_order_status_enum_reconciliation`
- NEVER edit migration <= 033.
- Creates three tables: `platform_operators`,
  `platform_operator_setup_tokens`, `platform_operator_reset_tokens`.
- Additive only. Does NOT modify existing tables.

### 4.2 Login integration

The `/auth/login` handler will be extended to check `platform_operators`
FIRST (before the tenant scan). If the email matches an active operator and
the platform password verifies, `platform_role` is added to the JWT. The
tenant scan continues as today (tenant claims added if any tenant copy
verifies). See Section 3.3 for collision semantics.

### 4.3 Platform guard staged cutover

The guard will use a feature flag (env var `PLATFORM_GUARD_MODE`):
- `legacy` (default during cutover): accepts tenant-local `super_admin` OR
  `platform_role`.
- `strict` (after cutover): accepts ONLY `platform_role`.

This allows a safe staged rollout without leaving operators locked out.

## 5. API Slices (DC-11P1+)

| Endpoint | Method | Scope | Description |
|---|---|---|---|
| `/platform/operators/setup-credential` | POST | Public (token-gated) | Set password from setup token |
| `/platform/operators/forgot-password` | POST | Public (neutral 200) | Request reset email |
| `/platform/operators/reset-password` | POST | Public (token-gated) | Set new password from reset token |
| `/platform/operators` | GET | platform_admin | List operators (sanitized) |
| `/platform/operators/invite` | POST | platform_admin | Invite new operator |
| `/platform/operators/{id}` | GET | platform_admin | Get operator detail |
| `/platform/operators/{id}/disable` | POST | platform_admin | Disable operator |
| `/platform/operators/{id}/revoke` | POST | platform_admin | Revoke operator |
| `/platform/operators/{id}/enable` | POST | platform_admin | Re-enable operator |

## 6. Frontend Slices (DC-11P2+)

- `/platform/operators` -- operator management console.
- `/setup-credential`, `/forgot-password`, `/reset-password` -- extend
  existing pages to handle platform operator tokens.
- `/auth/me` response handling: detect `platform_role`, route to platform
  dashboard without requiring tenant selection.

## 7. Threat Model (R1 corrected)

| Threat | Mitigation |
|---|---|
| Tenant admin grants platform access via tenant-local super_admin | platform_role set ONLY from platform_operators table; tenant super_admin never produces platform_role |
| Brute-force platform operator login | Lockout after 5 attempts; 15min lock; bcrypt hash |
| Token interception | Body-only; no query-string; HTTPS; short TTL |
| Token replay | Single-use; with_for_update(); hash-only |
| Disabled/revoked operator retains JWT until expiry | credentials_changed_at + active-state guard validation on every request |
| Single-operator takeover | Maker-checker: 2+ operators for destructive actions |
| Bootstrap token leak | No stdout/disk; email-only delivery; fail-closed SMTP; 24h TTL; single-use |
| Email enumeration | Neutral 200 on forgot-password |
| Collision confusion (same email, different passwords) | Independent verification; JWT claims reflect what actually verified |
| All operators disabled/locked | Break-glass CLI (not network-accessible); audited |
| Rollback restores unsafe tenant super_admin | Rollback keeps strict guard; application rollback + controlled guard mode |

## 8. Rollback (R1 corrected)

- Migration downgrade drops the three tables (additive only; no data loss to
  existing tables).
- Login handler reverts to tenant-only scan (no platform_operators check).
- Guard reverts to `PLATFORM_GUARD_MODE=legacy` (accepts tenant super_admin
  OR platform_role). This is the safe intermediate state.
- R1 correction: rollback must NOT silently restore tenant-local super_admin
  as the sole platform authority. The guard mode is explicitly controlled:
  - `legacy` = both paths (safe during cutover).
  - `strict` = platform_role only (post-cutover).
  - Rolling back from `strict` to `legacy` is a DELIBERATE action, not a
    silent side effect of the migration downgrade.

## 9. Tests (DC-11P1+)

| Test | Description |
|---|---|
| Bootstrap creates operator via email (no stdout/disk token) | setup token hash stored; email delivered; no raw token leaked |
| Setup credential consumes token and sets password | Single-use; 24h TTL; hash-only |
| Login as platform-only operator (no tenant user) | platform_role in JWT; available_tenants empty |
| Login collision: both passwords verify | platform_role AND tenant claims in JWT |
| Login collision: only platform password verifies | platform_role only; no tenant claims |
| Login collision: only tenant password verifies | tenant claims only; no platform_role |
| Login as disabled/revoked/locked operator | 401/403; platform_role not in JWT |
| Session invalidation after password change | credentials_changed_at > jwt.iat -> 401 |
| Session invalidation after disable | Guard active-state check -> 401 on next request |
| Forgot-password neutral response | 200 for existing and non-existing |
| Reset-password body-only token | Query-string rejected; hash-only; single-use; 1h TTL |
| Invite new operator | platform_admin only; pending_setup; setup token emailed |
| Revoke operator | platform_admin only; revoked_at set; immediate session loss |
| Maker-checker minimum | Destructive action blocked when < 2 active operators |
| Break-glass CLI | Re-enables one operator; audited; not network-accessible |
| Platform guard strict mode rejects tenant super_admin | Contextual super_admin -> 403 in strict mode |
| Platform guard legacy mode accepts both | Tenant super_admin OR platform_role accepted |
| No plaintext token/password in response or logs | Sentinel exception test |

## 10. Contract Tests (this gate)

Static contract tests verifying the current architecture matches assumptions.
Updated for R1:

- Platform guard checks is_identity_only and is_super_admin.
- No platform operator model/table exists yet.
- No platform operator token tables exist yet.
- No platform-specific auth endpoints exist.
- Login aggregates roles from tenant-local user_roles.
- Frontend platformApi states no X-Platform-Operator secret sent.
- Alembic head is 033 (confirms 034 is the next migration number).
- No 034 migration exists yet.

## 11. Allowed Files (DC-11P1+)

- `backend/alembic/versions/034_platform_operators.py` (new migration)
- `backend/models/platform_operator.py` (new model, 3 tables)
- `backend/api/v1/platform/operators.py` (new router)
- `backend/services/platform_operator_service.py` (new service)
- `backend/api/v1/auth.py` (extend login for platform_operators check)
- `backend/api/v1/platform/p10/guard.py` (add platform_role + guard mode)
- `backend/scripts/bootstrap_platform_operator.py` (CLI bootstrap)
- `backend/scripts/break_glass_platform_operator.py` (CLI break-glass)
- `backend/tests/test_dc11p1_platform_operator_identity.py` (new tests)
- `ai-ledger/product-ai/2026-07-14_dc11p1_platform_operator_implementation.md`

## 12. Forbidden Files

- Existing historical migrations (`<= 033`).
- Frontend files (DC-11P2 scope).
- Production compose/config/env.
- Lockfiles.
- `X-Platform-Operator` machine secret logic (unchanged).

## 13. Stop Conditions

- Baseline `cb1b1fff` has drifted.
- Alembic head is not `033_order_status_enum_reconciliation`.
- `034` revision number is taken by another merged change.
- Maker-checker cannot be enforced without a broader design decision.
- Break-glass recovery cannot be made safe (CTO decision needed).
- Any secret would be printed or persisted.

## 14. Verdict

**PASS_FOR_CTO_DC11P1_SCHEMA_IMPLEMENTATION**

All 5 current-state confirmations verified. R1 corrections address: migration
numbering (034, down_revision 033), independent platform authentication,
collision semantics, separate token tables, email-only bootstrap (no
stdout/disk), immediate session invalidation, /auth/me for platform-only
operators, safe staged cutover, maker-checker with break-glass, and rollback
safety (no silent restoration of tenant super_admin). No unresolved design
decisions remain.
