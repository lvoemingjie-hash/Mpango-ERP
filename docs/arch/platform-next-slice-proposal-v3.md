# Platform Track — Next Slice Proposal (v3)

**Track**: Platform P0+ — Post operational reporting closure
**Date**: 2026-04-14
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
| Operational reporting stats (read-only aggregation endpoint) | ✅ Closed | 10 tests |

**Current platform endpoints (all read-only):**
- GET /api/v1/platform/health
- GET /api/v1/platform/info
- GET /api/v1/platform/tenants/ (list)
- GET /api/v1/platform/tenants/{id} (detail)
- GET /api/v1/platform/audit/ (list, paginated, filterable)
- GET /api/v1/platform/audit/{id} (detail)
- GET /api/v1/platform/stats/ (platform-wide summary)

## 2. Candidates Evaluated

### Candidate A: Platform Tenant Read-Model Refinement
**What**: Enrich existing tenants endpoint with plan_type breakdown, optional field selection.
- Safety: ✅ Read-only | Value: ⚠️ Low | Complexity: ✅ Very low
- **Verdict**: Too small for a named slice. Polish task.

### Candidate B: Platform Tenant Registry Sync Boundary
**What**: Internal service to keep platform_tenants in sync with wholesalers + reconciliation endpoint.
- Safety: ⚠️ Introduces internal write path | Value: ✅ High | Complexity: ⚠️ Medium
- **Verdict**: Important but write operations add surface. Deserves dedicated focused proposal.

### Candidate C: Quota/Limits Information Model
**What**: Design platform_quotas table for per-tenant resource limits.
- Safety: ⚠️ New table + enforcement | Value: ✅ High | Complexity: ⚠️ High
- **Verdict**: Too early. Needs CTO design input.

### Candidate D: Audit Activity Enhancement ✅ CHOSEN
**What**: Time-range filtering on audit list + action-grouped activity summary endpoint.
- Safety: ✅ Pure read-only | Value: ✅ Medium-High | Complexity: ✅ Low
- **Verdict**: Safest valuable step. Extends proven patterns from closed audit slice.

## 3. Chosen Slice: Audit Activity Enhancement

### Objective
Make platform audit data operationally useful by adding time-range filtering and action-grouped summaries — the two features operators need most.

### Why safest/highest-value
1. Pure read-only — extends existing closed slice, zero writes, zero new tables, zero migrations
2. Closes the biggest operational gap — without time filtering, audit data is nearly useless
3. Lowest complexity of all valuable candidates
4. No design decisions needed — data model and query patterns are proven
5. Natural progression: stats gave counts, activity feed gives "what happened and when"

### Files to change
| File | Action | Description |
|------|--------|-------------|
| backend/api/v1/platform/audit.py | MODIFY | Add since/before query params; add /audit/summary sub-endpoint |
| backend/tests/test_platform_audit_api.py | MODIFY | Tests for filtering, summary, read-only contract |

### No migration needed

### API additions
| Method | Path | Purpose |
|--------|------|---------|
| GET | /api/v1/platform/audit/ | **Enhanced** — add since (ISO), before (ISO) query params |
| GET | /api/v1/platform/audit/summary | **New** — action-grouped counts with optional since/before |

Default: since = 7 days ago, max range = 90 days.

### Risks and Guardrails
| Risk | Mitigation |
|------|------------|
| Large time ranges heavy queries | Default 7-day window; cap at 90 days; existing limit param |
| Slow GROUP BY on large tables | action column is indexed |
| Scope creep into notifications | Query/display only — no webhook, no alert |

### Migration impact: None
### API impact: Backward-compatible — new params are optional with sensible defaults

## 4. Explicit Out-of-Scope

- No new tables or migrations
- No billing/subscription
- No tenant lifecycle write endpoints
- No auth/RBAC changes
- No tenant-schema changes
- No product API changes
- No dashboard UI
- No registry sync (deferred)
- No quota/limits (deferred)
- No notification/webhook on audit events

## 5. Definition of Done

- Time-range filtering on audit list endpoint
- New read-only audit summary endpoint
- 7-day default, 90-day max cap
- Tests: filtering, defaults, max cap, empty results, summary shape, read-only
- All 8 self-check gates PASS
- No migration, no new tables
- Ledger entry written

---

*PROPOSAL — awaiting CTO approval before implementation.*
