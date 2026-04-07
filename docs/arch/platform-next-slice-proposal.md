# Platform Track P0 — Next Slice Proposal

**Track**: Platform P0 - Next slice proposal  
**Date**: 2026-04-07  
**Status**: Draft — pending CTO approval  
**Decision authority**: CTO  
**Branch**: platform-dev

---

## 1. What We Have

| Slice | Status | Commit |
|-------|--------|--------|
| Routing scaffold (health/info) | ✅ Done | `10f876e` |
| Boundary note (revised) | ✅ Done | `9bbb270` |
| Information model draft | ✅ Done | `9fbb571` |
| Tenant lifecycle scaffold (migration 018 + models + read-only API) | ✅ Done | `1b8737a` |

## 2. Chosen Next Slice: Platform Audit Log Boundary

**Objective**: Implement `public.platform_audit_logs` — an append-only, public-schema table for platform-level administrative actions, with a read-only query API.

### Why This Slice

| Criterion | Assessment |
|-----------|------------|
| **Safest pattern** | Append-only = no UPDATE, no DELETE, simplest possible write pattern |
| **No tenant-schema changes** | Table lives in public schema, never touches tenant data at rest |
| **No auth changes** | Does not modify JWT, login flow, or RBAC |
| **No billing** | Purely operational/administrative audit trail |
| **Information model alignment** | Already proposed in the information model draft (Section 3.2) |
| **Distinct from sys_audit_logs** | `sys_audit_logs` tracks BI access patterns (product track); `platform_audit_logs` tracks platform admin actions (platform track) — different domain, different retention |
| **Clear bounded scope** | One table, one model, one write endpoint (insert only), one read endpoint |
| **CTO checkpoint alignment** | PLATFORM_PROPOSAL_CTO_REVIEW explicitly mentions audit logging as a safe early platform feature |

### Why Not the Alternatives

| Alternative | Rejected because |
|-------------|-----------------|
| Read-only tenant list refinement | Low value — already functional, refinement is cosmetic |
| Tenant lifecycle write endpoints (suspend/activate) | Requires provisioning logic coordination, wider surface area |
| Billing/subscription fields | Explicitly blocked by CTO |
| Quota/limits table | No approved information model for it yet |
| Admin console / UI | Not a backend platform-track concern |

## 3. Exact Scope

### Files/modules to create or modify

| File | Action | Description |
|------|--------|-------------|
| `backend/alembic/versions/019_platform_audit_logs.py` | CREATE | Migration: create `public.platform_audit_logs` table |
| `backend/models/platform_audit_log.py` | CREATE | Append-only model (Base, NOT AuditMixin — no updated_at, no soft delete) |
| `backend/models/__init__.py` | MODIFY | Add PlatformAuditLog import |
| `backend/api/v1/platform/audit.py` | CREATE | Read-only query API + appender service for platform actions |
| `backend/api/app.py` | MODIFY | Register audit router |
| `backend/tests/test_platform_audit.py` | CREATE | Model field tests + FK verification |
| `docs/arch/platform-next-slice-proposal.md` | CREATE | This proposal |
| `ai-ledger/platform/2026-04-07_p0_next_slice_proposal.md` | CREATE | Ledger entry |

### Table definition (public.platform_audit_logs)

```
id              UUID (PK, auto-generated)
actor_type      VARCHAR(20), NOT NULL — 'system', 'admin', 'api'
actor_id        UUID, nullable — who performed the action
wholesaler_id   UUID, nullable — affected tenant (NULL for global actions)
action          VARCHAR(100), NOT NULL — e.g., 'tenant.suspend', 'tier.change'
resource        VARCHAR(255), NOT NULL — e.g., 'wholesalers/<id>'
metadata        JSONB, nullable — action details (before/after, context)
created_at      TIMESTAMPTZ, NOT NULL, auto-generated
```

**Constraints**: Append-only. Inherit from `Base` directly (no `AuditMixin`). No `updated_at`, no `is_deleted`. DB-level `REVOKE UPDATE, DELETE` on this table deferred to ops task (same pattern as `sys_audit_logs`).

### API endpoints

| Method | Path | Purpose | Mutating? |
|--------|------|---------|-----------|
| GET | `/api/v1/platform/audit/` | Query audit log (paginated, filterable by wholesaler_id/action/actor_type) | No |
| GET | `/api/v1/platform/audit/{log_id}` | Single audit entry | No |

Write side (appender service) will NOT be exposed as an endpoint in this slice. Platform code that needs to write audit entries will import and call the service function directly. This keeps the API surface read-only and prevents external actors from forging audit entries.

### Migration impact

- Single new table in public schema
- No FK to wholesalers (nullable reference, index only — keeping it simple for first iteration)
- No changes to any existing table
- Downgrade: drop table only

### Risks and Guardrails

| Risk | Mitigation |
|------|------------|
| Audit log grows unbounded | Monitor row count; partitioning deferred until >10M rows (documented) |
| Platform code forgets to log actions | Create appender service function; add to coding guidelines |
| Actor identity spoofing | actor_type/actor_id set server-side, never from client input |
| Performance impact of JSONB column | JSONB is indexed only if needed; first slice uses sequential reads |
| Overlap with sys_audit_logs | Clear domain separation documented: sys_audit_logs = BI access, platform_audit_logs = admin actions |

## 4. What Stays Out of Scope

- ❌ Billing engine
- ❌ Subscription workflow
- ❌ Write endpoints for tenant lifecycle (suspend/activate)
- ❌ Tenant-schema changes
- ❌ Auth/RBAC changes
- ❌ Product API behavior changes
- ❌ Audit log UI/dashboard
- ❌ DB-level REVOKE UPDATE/DELETE (ops task, later)
- ❌ Partitioning strategy (later)
- ❌ Retention policy enforcement (later)

## 5. Definition of Done for This Slice

- [ ] Migration 019 creates `public.platform_audit_logs` with correct columns
- [ ] `PlatformAuditLog` model is append-only (no AuditMixin)
- [ ] Read-only query API returns paginated results
- [ ] Appender service function available for internal use
- [ ] All 8 self-check gates PASS
- [ ] Tests pass
- [ ] Ledger entry written
- [ ] No product architecture drift

---

*PROPOSAL — awaiting CTO approval before implementation.*
