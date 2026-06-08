# Platform Product P10-A-R1 Test Plan

**Phase**: P10-A-R1
**Date**: 2026-06-05
**Status**: Contract-only — test plan proving scope boundaries
**Source map**: `PLATFORM_PRODUCT_P10_DATA_SOURCE_MAP.md` (P9-R2)

---

## 1. Scope Definition

This test plan covers **contract-only validation** aligned to P9-R2. It does NOT test:

- Backend API endpoints
- Database queries or migrations
- Front-end rendering
- Authentication or authorization
- Runtime behavior of any system component

The tests prove:
1. Each contract's field types, nullability, and enum values match the P9-R2 data source map.
2. Each field carries a valid P10-A source status.
3. Each fixture conforms to its contract.
4. Each counterexample is correctly rejected.
5. No forbidden scope is touched by P10-A-R1 deliverables.
6. No unapproved implementation assertions exist (no storage location claims, no table structure claims).

---

## 2. Test Categories

### 2.1 Contract Structure Tests (Field-by-Field vs P9-R2)

| Test ID | Description | Pass Criteria |
|---------|-------------|---------------|
| CS-001 | TenantSummary has all 11 P9-R2 fields | `tenant_id`, `tenant_name`, `tenant_schema`, `status`, `tier`, `created_at`, `last_activity_at`, `user_count`, `health_status`, `recent_error_count`, `support_mode_active` |
| CS-002 | TenantSummary field nullability matches source map | Nullable: `tenant_id`, `tenant_name`, `tenant_schema`, `tier`, `created_at`, `last_activity_at`, `user_count`, `recent_error_count`. Not-null: `status`, `health_status`, `support_mode_active` |
| CS-003 | TenantSummary status enum matches P9-R2 | `draft`, `active`, `paused`, `suspended`, `archived`, `unknown` |
| CS-004 | TenantSummary health_status enum matches P9-R2 | `healthy`, `degraded`, `unhealthy`, `unknown` |
| CS-005 | TenantHealth has all 10 P9-R2 fields | `tenant_id`, `tenant_schema`, `health_status`, `schema_status`, `last_login_at`, `activity_counters`, `recent_errors`, `slow_routes`, `failed_jobs`, `last_health_check_at` |
| CS-006 | TenantHealth sub-structures valid | ErrorSummary has `error_class`, `count`, `correlation_ids`. SlowRoute has `route`, `latency_bucket_ms`, `count`. FailedJob has `job_class`, `count` |
| CS-007 | TenantHealth schema_status enum valid | `exists`, `unreachable`, `migration_misaligned`, `missing`, `unknown` |
| CS-008 | SystemHealth has all 11 P9-R2 fields | `overall_status`, `api_status`, `database_status`, `database_connections`, `queue_status`, `cpu_status`, `memory_status`, `disk_status`, `error_rate`, `slow_request_count`, `generated_at` |
| CS-009 | SystemHealth component status enum valid | `healthy`, `degraded`, `down`, `unknown` |
| CS-010 | SystemHealth overall_status enum valid | `healthy`, `degraded`, `down`, `unknown` |
| CS-011 | SystemHealth cpu/memory/disk nullable per P9-R2 | These fields are nullable because "optional in local/dev environments" |
| CS-012 | PlatformAuditEvent has all 11 P9-R2 fields | `event_id`, `actor_id`, `actor_role`, `tenant_id`, `scope`, `action`, `reason`, `result`, `metadata_redacted`, `correlation_id`, `created_at` |
| CS-013 | PlatformAuditEvent actor_role enum valid | `super_admin`, `support_operator`, `engineering_operator` |
| CS-014 | PlatformAuditEvent scope enum valid | `global`, `tenant`, `system`, `support` |
| CS-015 | PlatformAuditEvent result enum valid | `allowed`, `denied`, `failed`, `completed` |

### 2.2 Source Status Tests (P9-R2 Vocabulary)

| Test ID | Description | Pass Criteria |
|---------|-------------|---------------|
| SS-001 | Every field has a P10-A status | Each field lists one of: `available_now`, `proposed_public_metadata`, `tenant_aggregate_required`, `telemetry_required`, `manual_or_unknown`, `deferred` |
| SS-002 | Unknown behavior documented per field | Nullable → `null`. Non-nullable enum → documented fallback value. Non-nullable boolean → `false`. |
| SS-003 | `unknown` ≠ `healthy` enforced | No contract field may treat unknown as equivalent to healthy. |

### 2.3 Fixture Conformance Tests

| Test ID | Fixture | Pass Criteria |
|---------|---------|---------------|
| FC-001 | Healthy Tenant Summary | All fields populated, health_status = "healthy", support_mode_active = false |
| FC-002 | Healthy Tenant Health | No errors, no slow routes, no failed jobs, activity_counters are counts only |
| FC-003 | Degraded Tenant Summary | health_status = "degraded", recent_error_count > 0 |
| FC-004 | Degraded Tenant Health | Errors/slow routes/failed jobs present with redacted data only |
| FC-005 | Unknown Tenant Summary | health_status = "unknown", nullable fields null |
| FC-006 | Unknown Tenant Health | schema_status = "unreachable", all telemetry-backed fields null |
| FC-007 | Degraded System | overall_status = "degraded", cpu/memory/disk null |
| FC-008 | Support Bundle Denied | scope = "support", reason = null, result = "denied" |
| FC-009 | Support Operator Denied | scope = "support", denial_code = "unassigned_tenant" |

### 2.4 Counterexample Rejection Tests

| Test ID | Counterexample | Rejection Reason |
|---------|---------------|------------------|
| CR-001 | healthy when unknown | `unknown` ≠ `healthy` |
| CR-002 | support scope without reason | Support requires reason |
| CR-003 | healthy overall with degraded component | Contradicts derivation |
| CR-004 | raw error payload | Only redacted fields allowed |
| CR-005 | tenant scope without tenant_id | scope/tenant_id mismatch |
| CR-006 | actor_role = "admin" | Invalid enum value |

### 2.5 Scope Boundary Tests

| Test ID | Description | Pass Criteria |
|---------|-------------|---------------|
| SB-001 | No backend files | Nothing under `backend/` |
| SB-002 | No frontend files | Nothing under `frontend/` |
| SB-003 | No migration files | Nothing under migrations paths |
| SB-004 | No auth/RBAC/tenancy/session/payment | No file paths with those keywords |
| SB-005 | Only docs/ai and ai-ledger | All files under `docs/ai/` or `ai-ledger/platform/` |
| SB-006 | No unapproved implementation assertions | No claims about storage location, table names, or schema prefixes |

---

## 3. Validation Commands

```bash
# Scope boundary
git diff --name-only origin/platform-dev..HEAD
# Must show only docs/ai/* and ai-ledger/platform/* files

# Forbidden path audit
# No backend/, frontend/, .github/, .claude/, auth, rbac, tenancy, etc.

# Whitespace check
git diff --check origin/platform-dev..HEAD

# GitNexus
npx gitnexus analyze
# Expected: LOW risk / docs-only / 0 affected processes

# GitNexus detect_changes compare
# Expected: changes limited to docs and ledger, no process impact
```

---

## 4. Expected Results

| Metric | Expected |
|--------|----------|
| Files changed | 4-5 (docs/ai/* + ai-ledger/platform/*) |
| Backend files | 0 |
| Frontend files | 0 |
| Migration files | 0 |
| GitNexus risk | LOW / docs-only |
| Affected processes | 0 |
| Forbidden violations | 0 |
| Counterexamples rejected | 6/6 |
| Unapproved assertions | 0 |

---

## 5. Alignment Verification

This test plan explicitly verifies alignment with P9-R2 by:

1. Checking every contract has exactly the fields listed in `PLATFORM_PRODUCT_P10_DATA_SOURCE_MAP.md`.
2. Checking every field has the correct P10-A source status from the source map.
3. Checking unknown behavior is documented for every field.
4. Checking no field exists in contracts that is not in the source map.
5. Checking no storage location assertions exist beyond what P9-R2 approves.
