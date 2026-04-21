# Platform Track — Project Handoff Document

**Purpose**: This document captures the essential state, decisions, and context for the Platform Track. Read this first in any new conversation to understand where we are, what we've built, and what matters.

**Last Updated**: 2026-04-21
**Branch**: `platform-dev`
**Agent**: Vibecoder (Platform AI)

---

## 🎯 What is This Project?

The Platform Track builds the SaaS platform infrastructure on top of the existing schema-per-tenant ERP system. It enables multi-tenant administrative operations (tenant lifecycle, audit, reporting) without polluting tenant business schemas or duplicating tenant identity.

**Key Architectural Truths** (Non-negotiable):
- Schema-per-tenant remains the primary tenancy model (DR-001)
- Platform tables reference `wholesalers.id`, never duplicate tenant identity
- **NO tenant-schema migrations** in platform work
- **NO auth/RBAC changes** in platform work
- **NO billing engine** until explicitly approved
- All platform tables live in `public` schema with `platform_` prefix

---

## 📦 What's Built So Far

### Closed Slices (In Order)

| # | Slice | Status | Key Deliverables | Tests |
|---|-------|--------|------------------|-------|
| 1 | Routing scaffold | ✅ Closed | GET /health, /info | — |
| 2 | Boundary note | ✅ Closed | `docs/arch/platform-boundary-note.md` | — |
| 3 | Information model | ✅ Closed | `docs/arch/platform-information-model-draft.md` | — |
| 4 | Tenant lifecycle scaffold | ✅ Closed | Migration 018, `PlatformTenant` model, read-only API | 13 |
| 5 | Platform audit logs | ✅ Closed | Migration 019, `PlatformAuditLog` model, appender service, read-only API | 32 |
| 6 | Operational reporting stats | ✅ Closed | GET /api/v1/platform/stats/ (aggregation endpoint) | 10 |
| 7 | Audit activity enhancement | ✅ Closed | Time-range filtering on audit, GET /api/v1/platform/audit/summary | 32 |

**Total API Endpoints**: 7 (all read-only)
- `GET /api/v1/platform/health`
- `GET /api/v1/platform/info`
- `GET /api/v1/platform/tenants/`
- `GET /api/v1/platform/tenants/{id}`
- `GET /api/v1/platform/audit/`
- `GET /api/v1/platform/audit/{id}`
- `GET /api/v1/platform/audit/summary`
- `GET /api/v1/platform/stats/`

### Database Schema

**Tables in public schema**:
- `wholesalers` — existing tenant registry (product track)
- `platform_tenants` — platform-level lifecycle journal (new, migration 018)
- `platform_audit_logs` — append-only platform admin audit (new, migration 019)

**Key Relationships**:
- `platform_tenants.wholesaler_id` → `wholesalers.id` (1:1)
- `platform_audit_logs.wholesaler_id` → `wholesalers.id` (N:1, nullable)

### Key Files

| File | Purpose |
|------|---------|
| `docs/arch/platform-boundary-note.md` | **READ FIRST** — architectural constraints and frozen zones |
| `docs/arch/platform-information-model-draft.md` | Data model decisions and design rationale |
| `backend/models/platform_tenant.py` | PlatformTenant model |
| `backend/models/platform_audit_log.py` | PlatformAuditLog model (append-only) |
| `backend/api/v1/platform/tenants.py` | Tenant lifecycle read-only API |
| `backend/api/v1/platform/audit.py` | Audit read-only API (with time-range filtering) |
| `backend/api/v1/platform/stats.py` | Platform-wide aggregation stats |
| `backend/services/platform_audit_service.py` | Internal audit appender (write path) |
| `ai-ledger/platform/` | Slice-by-slice decision ledger (NOT this doc) |

---

## 🔒 Frozen Zones (Do Not Touch)

The following are architecturally frozen for Platform Track P0:

- ❌ Authentication model (JWT, login, token lifecycle)
- ❌ Schema-per-tenant isolation architecture (DR-001)
- ❌ Tenant provisioning workflow
- ❌ Product API endpoints (`/api/v1/auth`, `/api/v1/orders`, etc.)
- ❌ Tenant ORM guardrail interceptor
- ❌ Search-path routing mechanism
- ❌ Tenant-schema table structures
- ❌ Auth/RBAC tables and models

---

## 🚫 Out of Scope (Unless CTO Approves)

- ❌ Billing engine (subscription invoicing, payment collection)
- ❌ Subscription management workflows
- ❌ Quota/limits enforcement (`platform_quotas` table)
- ❌ Tenant lifecycle write endpoints (suspend, activate, deactivate)
- ❌ Product API changes
- ❌ Platform admin UI
- ❌ Webhooks or notifications on audit events
- ❌ Registry sync (platform_tenants ↔ wholesalers reconciliation)

---

## 📐 Current Architecture

### Platform Layer Boundaries

```
public.wholesalers (tenant registry — product track)
    │
    ├── 1:1 ── platform_tenants (provisioning journal — platform track)
    │              - provisioning_status: pending | schema_created | seed_complete | failed
    │              - provisioning_log: JSONB event log
    │              - activated_at, deactivated_at, deactivation_reason
    │
    ├── 1:N ── platform_audit_logs (admin actions — platform track)
    │              - Append-only (no UPDATE/DELETE)
    │              - actor_type, actor_id, wholesaler_id, action, resource, audit_metadata
    │
    └── (N) ─── t_xxx schemas (tenant business data — frozen)
```

### API Layer

All platform endpoints under `/api/v1/platform/`:
- `health/`, `info/` — routing scaffold
- `tenants/` — read-only tenant lifecycle data
- `audit/` — read-only audit logs with time-range filtering
- `stats/` — platform-wide aggregation stats

**No write endpoints exposed yet** — all mutations happen via internal services (e.g., `platform_audit_service.py`).

---

## 🎯 Working Rules

### Before Starting Work

1. **Read boundary note** (`docs/arch/platform-boundary-note.md`) — understand frozen zones
2. **Check ai-ledger/platform/** — read the most recent ledger entry for context
3. **Identify the slice** — is this a new slice, or an enhancement to a closed slice?

### For New Slices

1. **Write a proposal** (`docs/arch/platform-next-slice-proposal-v{N}.md`)
2. **Run 8-gate self-check**:
   - Scope: Are we touching frozen zones?
   - Architecture: Schema-per-tenant preserved?
   - API contract: Backward-compatible?
   - Migration: Any tenant-schema changes? (must be NO)
   - Tests: Do we have test coverage?
   - Boot/import: No new imports that break boot?
   - Diff hygiene: No debug prints, clean commit history?
   - CTO-question: Is this the safest next step?
3. **Create ledger entry** in `ai-ledger/platform/YYYY-MM-DD_{slice_name}.md`
4. **Implement, test, commit, push**
5. **Wait for CTO approval** before any further work

### For Enhancements to Closed Slices

1. Must be backward-compatible (no breaking changes)
2. Must follow the same 8-gate self-check
3. Must update the slice's ledger entry

---

## 📊 Test Coverage

Current platform test counts:
- Tenant lifecycle API: 13 tests
- Audit logs API: 32 tests
- Stats endpoint: 10 tests

Total: **55 tests** (all read-only contract tests)

---

## 🔑 Naming Conventions

| Prefix | Scope | Examples |
|--------|-------|---------|
| (none) | Product business tables | `wholesalers`, `retailers` |
| `sys_` | Product system tables | `sys_audit_logs`, `sys_jobs`, `sys_reports` |
| `platform_` | Platform tables | `platform_tenants`, `platform_audit_logs` |
| `ai-ledger/` | AI decision ledger | `ai-ledger/platform/*.md` |

---

## 🚀 Next Candidates (Evaluated but Not Implemented)

| Candidate | Why Not Yet |
|-----------|-------------|
| Platform Tenant Registry Sync Boundary | Write operations — needs dedicated focused proposal |
| Quota/Limits Information Model | No approved design; billing coupling |
| Tenant Read-Model Refinement | Too small — polish task, not architecture |

**Current focus**: More read-only enhancements that add value without write surface.

---

## 📚 How to Use This Document

### Starting a New Conversation

1. Read this file (`PROJECT_HANDOFF.md`) first
2. Read `docs/arch/platform-boundary-note.md` for architectural constraints
3. Check `ai-ledger/platform/` for the most recent work
4. Identify what you need to do (new slice vs. enhancement)
5. Follow the working rules above

### After Completing Work

1. Update the "What's Built So Far" section with new slices
2. Update the "Next Candidates" section if evaluating new work
3. Update the "Last Updated" timestamp
4. Commit this document alongside your work

---

**This document is your living knowledge base for the Platform Track. Keep it updated, keep it accurate, keep it concise.**
