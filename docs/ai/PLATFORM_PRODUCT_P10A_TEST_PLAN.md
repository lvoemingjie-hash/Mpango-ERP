# Platform Product P10-A Test Plan

**Phase**: P10-A
**Date**: 2026-06-04
**Status**: Contract-only — test plan proving scope boundaries
**Scope**: Verify that data contracts are structurally correct, fixtures conform, and counterexamples are rejected.

---

## 1. Scope Definition

This test plan covers **contract-only validation**. It does NOT test:

- Backend API endpoints
- Database queries or migrations
- Front-end rendering
- Authentication or authorization
- Runtime behavior of any system component

The tests prove:
1. Each contract's field types, nullability, and enum values are correctly specified.
2. Each fixture conforms to its contract.
3. Each counterexample is correctly rejected.
4. No forbidden scope is touched by the P10-A deliverables.

---

## 2. Test Categories

### 2.1 Contract Structure Tests

| Test ID | Description | Pass Criteria |
|---------|-------------|---------------|
| CS-001 | TenantSummary has all required fields | `tenant_id`, `tenant_name`, `schema_name`, `status`, `retailer_count`, `created_at`, `source_zone` are present and non-null |
| CS-002 | TenantSummary nullable fields | `plan` and `last_activity_at` may be null |
| CS-003 | TenantSummary status enum | `status` is one of: `active`, `suspended`, `provisioning`, `decommissioned` |
| CS-004 | TenantSummary retailer_count sentinel | `retailer_count` is `>= 0` or exactly `-1` (unreachable) |
| CS-005 | TenantHealth has all required fields | `tenant_id`, `healthy`, `checks`, `assessed_at`, `source_zone` present |
| CS-006 | TenantHealth checks non-empty | `checks` array has `>= 1` entry |
| CS-007 | TenantHealth check status enum | Each `CheckResult.status` is: `pass`, `fail`, `degraded`, or `unknown` |
| CS-008 | TenantHealth healthy derivation | `healthy = true` iff ALL checks have `status = "pass"` |
| CS-009 | SystemHealth has all required fields | All 8 fields present, `source_zone = "platform"` |
| CS-010 | SystemHealth status enum | `status` is: `healthy`, `degraded`, `down`, or `unknown` |
| CS-011 | SystemHealth count invariant | `tenant_healthy + tenant_degraded + tenant_unreachable <= tenant_total` |
| CS-012 | PlatformAuditEvent has all required fields | All 9 fields present |
| CS-013 | PlatformAuditEvent event_type namespaced | Contains at least one `.` separator |
| CS-014 | PlatformAuditEvent actor_type enum | `actor_type` is: `system`, `operator`, `tenant_admin`, or `unknown` |
| CS-015 | PlatformAuditEvent payload type | `payload` is a JSON object or `null`, never a string |

### 2.2 Cross-Contract Tests

| Test ID | Description | Pass Criteria |
|---------|-------------|---------------|
| XC-001 | All UUIDs are valid v4/v7 | Regex: `^[0-9a-f]{8}-[0-9a-f]{4}-[4-7][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$` |
| XC-002 | All timestamps are UTC ISO-8601 | Regex: `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$` |
| XC-003 | source_zone values | Always one of: `platform`, `tenant`, `unknown` |
| XC-004 | source_status values | Always one of: `live`, `cached`, `unknown` |
| XC-005 | No tenant business data | Contracts contain no order, payment, product, or pricing fields |

### 2.3 Fixture Conformance Tests

| Test ID | Fixture | Contract | Pass Criteria |
|---------|---------|----------|---------------|
| FC-001 | Healthy Tenant Summary | TenantSummary | All fields valid, retailer_count >= 0 |
| FC-002 | Healthy Tenant Health | TenantHealth | healthy=true, all checks pass |
| FC-003 | Degraded Tenant Summary | TenantSummary | All fields valid |
| FC-004 | Degraded Tenant Health | TenantHealth | healthy=false, one check degraded |
| FC-005 | Unknown Tenant Summary | TenantSummary | source_zone="unknown", retailer_count=-1 |
| FC-006 | Unknown Tenant Health | TenantHealth | healthy=false, all checks unknown |
| FC-007 | Degraded System | SystemHealth | status="degraded", counts consistent |
| FC-008 | Support Bundle Denied | PlatformAuditEvent | payload.reason=null, denial_code present |
| FC-009 | Support Operator Denied | PlatformAuditEvent | denial_code="unassigned_tenant" |

### 2.4 Counterexample Rejection Tests

| Test ID | Counterexample | Rejection Reason |
|---------|---------------|------------------|
| CR-001 | C1: tenant_id as string | Not a valid UUID |
| CR-002 | C2: status as "deleted" | Invalid enum value |
| CR-003 | C3: healthy=true with fail check | Contradicts derivation rule |
| CR-004 | C4: payload as string | Must be object or null |
| CR-005 | C5: event_type without dot | Missing namespace separator |
| CR-006 | C6: tenant_healthy > tenant_total | Count invariant violation |

### 2.5 Scope Boundary Tests

| Test ID | Description | Pass Criteria |
|---------|-------------|---------------|
| SB-001 | No backend files changed | `git diff origin/platform-dev --name-only` shows nothing under `backend/` |
| SB-002 | No frontend files changed | Nothing under `frontend/` |
| SB-003 | No migration files | Nothing under `backend/alembic/` or `migrations/` |
| SB-004 | No auth/RBAC/tenancy/session files | No file paths containing those keywords |
| SB-005 | Only docs/ai and ai-ledger changed | All changed files start with `docs/ai/` or `ai-ledger/platform/` |
| SB-006 | No product-dev-recovered changes | No changes to `product-dev-recovered/` |
| SB-007 | No platform-dev merge | Branch is isolated, not merged to `platform-dev` |

---

## 3. Test Execution Order

1. **Scope boundary tests** (SB-001 through SB-007) — run first to confirm no forbidden scope.
2. **Contract structure tests** (CS-001 through CS-015) — verify contract definitions.
3. **Cross-contract tests** (XC-001 through XC-005) — verify cross-cutting rules.
4. **Fixture conformance tests** (FC-001 through FC-009) — verify all fixtures are valid.
5. **Counterexample rejection tests** (CR-001 through CR-006) — verify all counterexamples are rejected.

---

## 4. Validation Commands

```bash
# Scope boundary
git diff --name-only origin/platform-dev..HEAD
# Must show only docs/ai/* and ai-ledger/platform/* files

# Forbidden path audit
# No backend/, frontend/, .github/, .claude/, auth, rbac, tenancy, migration, payment, session

# Whitespace check
git diff --check origin/platform-dev..HEAD

# GitNexus
npx gitnexus analyze
# Expected: LOW risk / docs-only / 0 affected processes

# GitNexus detect_changes
# Expected: changes limited to docs and ledger files, no process impact
```

---

## 5. Expected Results

| Metric | Expected |
|--------|----------|
| Files changed | 3-5 (docs/ai/* + ai-ledger/platform/*) |
| Backend files | 0 |
| Frontend files | 0 |
| Migration files | 0 |
| Test suites run | 0 (contract-only, no executable tests in P10-A) |
| GitNexus risk | LOW / docs-only |
| Affected processes | 0 |
| Forbidden violations | 0 |
| Counterexamples rejected | 6/6 |

---

## 6. Out of Scope for P10-A

- Implementing a contract validator script (future phase).
- Generating TypeScript or Python types from contracts (future phase).
- Creating API endpoints that serve these contracts (future phase).
- Writing database schemas for platform tables (future phase).
- Any modification to tenant business data or tenant schema structure.
