# U6-H0 Tenant Provisioning Schema Gap Decision

Status: READY_FOR_U6H1_WITHOUT_MIGRATION
Date: 2026-07-08
Base: origin/product-dev-recovered at a2e01bd3
Branch: codebuddy/u6h0-tenant-provisioning-schema-gap-decision-2026-07-08

## Purpose

Contract/test-only decision gate for the 7 schema gaps identified in U6-G. This is NOT provisioning. No tenant creation is implemented here.

## Context

U6-G identified schema gaps in the current `tenant_registrations` table. This decision gate resolves whether U6-H1 provisioning service can safely start with the current schema without a migration.

The current schema was established by:
- Migration 026 (`026_tenant_onboarding_auth_contract`, 2026-07-05): full `tenant_registrations` DDL
- Migration 027 (`027_onboarding_status_tokens`, 2026-07-07): onboarding status tokens table
- No further migrations modified `tenant_registrations`

## Decision Points

### 1. provisioned_at

**Current**: `tenant_registrations.provisioning_completed_at` (DateTime, nullable).

**Decision**: CANONICAL_ENOUGH.

The current `provisioning_completed_at` timestamp precisely marks when provisioning finishes. The U6-G contract and the provisioning contract both explicitly reference `provisioning_completed_at` as the canonical equivalent of `provisioned_at`. The `public.wholesalers` table separately has its own `provisioned_at` column for the wholesaler-side timeline.

**Verdict**: No migration needed. `provisioning_completed_at` is the canonical provisioning completion timestamp.

---

### 2. provisioning_attempt_count

**Current**: Missing. Schema has `failed_at`, `failure_code`, `failure_message`, `retry_allowed_until`.

**Decision**: DEFERRED_FOR_MVP.

For MVP, the provisioning saga has well-defined deterministic states (`email_verified` → `provisioning` → `active` or `failed`). Attempt count can be inferred from status transitions and the presence/non-null of `failed_at`/`retry_allowed_until`. The retry window bounded by `retry_allowed_until` provides sufficient back-off enforcement.

**Verdict**: No migration needed. Existing failure/retry fields suffice for MVP. `provisioning_attempt_count` should be added in a future schema hardening slice if needed for production observability.

---

### 3. provisioning_lock / version

**Current**: Missing. No `version`, `lock`, or stale-worker column exists.

**Decision**: DEFERRED_FOR_MVP.

The U6-G contract already documents acceptable locking strategies without schema changes:
- `SELECT ... FOR UPDATE` on the registration row (row-level lock)
- PostgreSQL advisory lock keyed by registration id
- Existing partial unique indexes (`ux_tenant_registrations_tenant_schema`, `ux_tenant_registrations_wholesaler_id`) prevent duplicate provisioning artifacts at the database level

**Verdict**: No migration needed. Row-level locks + advisory locks + unique indexes are sufficient for safe U6-H1 provisioning. A version column for stale-worker detection can be deferred.

---

### 4. provisioning_last_error

**Current**: Schema has `failure_code` (String(64)), `failure_message` (Text), `failed_at` (DateTime), `retry_allowed_until` (DateTime).

**Decision**: CANONICAL_ENOUGH.

These four fields together form a complete error reporting contract: a machine-readable code, a human-readable message (sanitized), the failure timestamp, and the retry deadline. The U6-G contract acknowledges this: "Current fields are failure_code, failure_message, failed_at, and retry_allowed_until." The label `provisioning_last_error` would be semantically identical to this set.

**Verdict**: No migration needed. `failure_code` + `failure_message` + `failed_at` + `retry_allowed_until` ARE the canonical provisioning error state.

---

### 5. admin linkage (admin_user_id)

**Current**: Missing from `tenant_registrations`. No column links to the first admin user.

**Decision**: DEFERRED_FOR_MVP.

The U6-G contract explicitly states: "U6-H can derive the first admin by owner email in the tenant schema." The derivation is:
1. Registration has `owner_email` (normalized, lowercase, trimmed).
2. Upon provisioning, the first admin user in the tenant schema is created deterministically from `owner_email`.
3. Finding the admin user in the tenant schema by normalized email is deterministic and reliable.

**Verdict**: No migration needed. Deriving first admin by owner_email in tenant schema is acceptable for MVP. A permanent `admin_user_id` column can be added later if durable audit linkage is required.

---

### 6. provisioning event / audit table

**Current**: Missing. No dedicated provisioning event table exists.

**Decision**: DEFERRED_FOR_MVP.

For MVP, the status transitions and timestamps in `tenant_registrations` serve as a sufficient audit trail:
- `provisioning_started_at` (claim timestamp)
- `provisioning_completed_at` (success timestamp)
- `failed_at` + `failure_code` + `failure_message` (failure audit)
- `retry_allowed_until` (retry policy timestamp)
- Standard `created_at`/`updated_at` audit columns

**Verdict**: No migration needed. Status transitions and timestamps are sufficient for MVP audit. A dedicated provisioning event table can be deferred.

---

### 7. wholesaler linkage

**Current - Indexes**:
- `ux_tenant_registrations_tenant_schema`: partial unique index WHERE `tenant_schema IS NOT NULL` ✅
- `ux_tenant_registrations_wholesaler_id`: partial unique index WHERE `wholesaler_id IS NOT NULL` ✅

**Current - public.wholesalers fields**:
- `id` (UUID PK), `code` (UNIQUE), `name`, `address`, `contact`, `plan_type`
- `status` (active/suspended/provisioning/deactivated)
- `provisioned_at` (DateTime, nullable)
- `suspended_at`, `suspension_reason`
- `get_tenant_schema()` method: `t_<uuid_without_dashes>`
- `derive_schema_from_id()` static method

**Decision**: VERIFIED_OK.

All partial unique indexes exist as described. `public.wholesalers` has every field needed for deterministic provisioning: identity, status lifecycle, provisioning timestamp, schema derivation. The foreign key `tenant_registrations.wholesaler_id → public.wholesalers.id` is already defined with a partial unique index ensuring at most one registration maps to one wholesaler.

**Verdict**: No migration needed. Wholesaler linkage is fully supported by current schema and indexes.

---

## Final Verdict: READY_FOR_U6H1_WITHOUT_MIGRATION

All 7 decision points confirm that U6-H1 provisioning service can safely start with the **current schema**:

| # | Decision Point | Verdict |
|---|---|---|
| 1 | `provisioned_at` | CANONICAL_ENOUGH (`provisioning_completed_at`) |
| 2 | `provisioning_attempt_count` | DEFERRED_FOR_MVP |
| 3 | `provisioning_lock` / `version` | DEFERRED_FOR_MVP |
| 4 | `provisioning_last_error` | CANONICAL_ENOUGH (`failure_code`/`failure_message`) |
| 5 | `admin_user_id` linkage | DEFERRED_FOR_MVP |
| 6 | Provisioning event/audit table | DEFERRED_FOR_MVP |
| 7 | Wholesaler linkage | VERIFIED_OK |

**Zero migrations required. Zero production code changes needed.**

### What U6-H1 MUST use from current schema:
- `provisioning_completed_at` as the canonical provisioning timestamp
- `failure_code`/`failure_message`/`failed_at`/`retry_allowed_until` as canonical error state
- `SELECT ... FOR UPDATE` or advisory lock for concurrency safety
- Partial unique indexes for duplicate prevention
- `owner_email` for deriving admin user in tenant schema

### Public boundary confirmation:
- `POST /api/v1/auth/signup` remains non-provisioning
- `POST /api/v1/auth/verify-email` remains non-provisioning
- `POST /api/v1/auth/onboarding/status` remains non-provisioning
- No production code, migration, frontend, or deploy artifacts were changed by this decision gate

### Scope confirmation:
- Allowed files only: `ai-ledger/` decision doc, `backend/tests/` static test, optional contract appendix
- No forbidden files touched: zero production code, zero migration, zero frontend, zero deploy/VPS
