# Platform Track — Next Slice Proposal (v2)

**Track**: Platform P0+ — Post audit-log closure  
**Date**: 2026-04-09  
**Status**: Draft — pending CTO approval  
**Decision authority**: CTO  
**Branch**: platform-dev

---

## 1. What We Have (Closed Slices)

| Slice | Status | Tests |
|-------|--------|-------|
| Routing scaffold (health/info) | ✅ Closed | — |
| Boundary note (revised) | ✅ Closed | — |
| Information model draft | ✅ Closed | — |
| Tenant lifecycle scaffold (migration 018, models, read-only API) | ✅ Closed | 13 tests |
| Platform audit logs (migration 019, model, appender service, read-only API) | ✅ Closed | 32 tests |

**Current platform endpoints:**
- `GET /api/v1/platform/health`
- `GET /api/v1/platform/info`
- `GET /api/v1/platform/tenants/` (list)
- `GET /api/v1/platform/tenants/{id}` (detail)
- `GET /api/v1/platform/audit/` (list, paginated)
- `GET /api/v1/platform/audit/{id}` (detail)

## 2. Candidates Evaluated

### Candidate A: Platform Operational Reporting Boundary

**What**: A read-only endpoint that aggregates platform-wide metrics — tenant count, active/suspended counts, recent audit activity — providing a platform-wide status dashboard API.

| Criterion | Assessment |
|-----------|------------|
| Safety | ✅ Read-only aggregation of public schema data |
| Value | ⚠️ Medium — useful but no new platform capability |
| Complexity | ✅ Low — SQL aggregation, no new tables |
| Dependencies | None — uses existing data |

**Verdict**: Low risk, moderate value. Could be done anytime.

### Candidate B: Platform Tenant Read-Model Refinement

**What**: Enhance the existing tenants endpoint with richer public-schema data — plan_type display, schema status, provisioning timeline from platform_tenants.

| Criterion | Assessment |
|-----------|------------|
| Safety | ✅ Read-only, no new tables |
| Value | ⚠️ Low-Medium — cosmetic improvement to existing endpoint |
| Complexity | ✅ Very low — SQL joins, no migration |
| Dependencies | None |

**Verdict**: Too small to be a "slice" — more of a refinement task.

### Candidate C: Quota/Limits Information Model Proposal

**What**: Design a `platform_quotas` table and model for per-tenant resource limits (users, storage, etc.).

| Criterion | Assessment |
|-----------|------------|
| Safety | ⚠️ New table + enforcement logic = wider surface |
| Value | ✅ High — essential SaaS capability |
| Complexity | ⚠️ Medium — requires design decisions before implementation |
| Dependencies | Requires provisioning logic, potentially billing coupling |

**Verdict**: Too early. No approved information model. Requires CTO design input first.

### Candidate D: Platform Registry Sync Boundary

**What**: Ensure platform_tenants stays in sync with wholesalers — an internal sync service that creates/updates platform_tenants records when wholesalers change, plus a reconciliation API.

| Criterion | Assessment |
|-----------|------------|
| Safety | ⚠️ Write operations — but internal only, no external endpoint |
| Value | ✅ High — closes the data consistency gap between wholesalers and platform_tenants |
| Complexity | ⚠️ Medium — sync logic + reconciliation |
| Dependencies | None new — uses existing tables |

**Verdict**: Important but complex. Write operations require careful design.

### ✅ Chosen: Candidate A — Platform Operational Reporting Boundary

**Why this is the safest and most natural next step:**

1. **Purest possible read-only pattern** — aggregates existing data, zero writes, zero new tables
2. **Zero migration impact** — no schema changes whatsoever
3. **Proves platform layer can add value** — demonstrates platform-wide visibility without touching any frozen zone
4. **Natural extension of closed slices** — uses wholesalers + platform_tenants + platform_audit_logs data already in place
5. **No design decisions needed** — the data model is already established
6. **Lowest possible blast radius** — a single new read-only endpoint file + tests

## 3. Exact Scope

### Files to create/modify

| File | Action | Description |
|------|--------|-------------|
| `backend/api/v1/platform/stats.py` | CREATE | Read-only platform-wide metrics endpoint |
| `backend/api/app.py` | MODIFY | Register stats router |
| `backend/tests/test_platform_stats_api.py` | CREATE | Request-level tests for stats endpoint |
| `docs/arch/platform-next-slice-proposal-v2.md` | CREATE | This proposal |
| `ai-ledger/platform/2026-04-09_p0_next_slice_proposal_v2.md` | CREATE | Ledger entry |

### No migration needed
No new tables, no schema changes.

### Proposed API endpoint

| Method | Path | Purpose | Mutating? |
|--------|------|---------|-----------|
| GET | `/api/v1/platform/stats/` | Platform-wide aggregated metrics | No |

**Response shape (proposed):**
```json
{
  "tenants": {
    "total": 5,
    "active": 4,
    "suspended": 1
  },
  "provisioning": {
    "complete": 4,
    "pending": 1,
    "failed": 0
  },
  "audit": {
    "total_entries": 150,
    "last_24h": 12
  },
  "generated_at": "2026-04-09T16:00:00Z"
}
```

### Risks and Guardrails

| Risk | Mitigation |
|------|------------|
| Slow aggregation on large tenant count | Count queries are O(1) with indexes; add explicit note for future materialization |
| Counts may be stale | Document that stats are point-in-time reads, not materialized |
| Scope creep into dashboard UI | This slice is API only — no frontend |

## 4. What Stays Out of Scope

- ❌ No new tables or migrations
- ❌ No billing/subscription
- ❌ No tenant lifecycle write endpoints
- ❌ No auth/RBAC changes
- ❌ No tenant-schema changes
- ❌ No product API changes
- ❌ No dashboard UI
- ❌ No materialized views (future optimization)
- ❌ No scheduled reporting

## 5. Why Not the Others

| Alternative | Rejected because |
|-------------|-----------------|
| B: Read-model refinement | Too small for a named slice — more of a polish task |
| C: Quota/limits | No approved design; needs CTO input before implementation |
| D: Registry sync | Write operations; important but more complex; better as a dedicated slice |

## 6. Definition of Done

- [ ] Single read-only stats endpoint
- [ ] Response covers tenant counts, provisioning status, audit activity
- [ ] Tests verify response shape and read-only contract
- [ ] All 8 self-check gates PASS
- [ ] No migration, no new tables
- [ ] Ledger entry written
- [ ] No product architecture drift

---

*PROPOSAL — awaiting CTO approval before implementation.*
