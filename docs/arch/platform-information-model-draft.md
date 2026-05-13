# Platform Information Model Draft

**Track**: Platform P0 - Alignment/Foundation  
**Date**: 2026-04-07  
**Status**: Draft — pending CTO review  
**Decision authority**: CTO  
**Branch**: platform-dev

---

## Context

This draft defines the minimal public-schema platform information model that enables the SaaS platform line to evolve without polluting tenant business schemas or duplicating tenant identity.

**Key constraints** (from CTO truth and DR-001):
- Schema-per-tenant remains the primary tenancy model
- Platform identity must reference `wholesalers.id`, never duplicate it
- No tenant-schema migrations, no auth rewrite, no business-schema redesign

---

## 1. Current Public Schema Inventory

Before proposing extensions, document what already exists:

| Table | Owner | Purpose |
|-------|-------|---------|
| `public.wholesalers` | Product | Tenant registry (id, code, name, address, contact, plan_type) |
| `public.retailers` | Product | Global customer registry |
| `public.wholesaler_retailer_bindings` | Product | Wholesaler-retailer relationship |
| `public.invitations` | Product | Retailer invitation flow |
| `public.sys_audit_logs` | Product (S7-3) | Append-only BI access audit trail |
| `public.sys_jobs` | Product (S4-B) | Persistent job tracking |
| `public.sys_reports` | Product (S6-3) | Report definitions |

**Observation**: The public schema already has system tables (`sys_*`). Platform tables should follow a clear naming convention to avoid collision.

---

## 2. Proposed Extension to `public.wholesalers`

These are **operational/lifecycle metadata columns** that extend the existing tenant registry. They belong on `wholesalers` because they are attributes of the tenant entity itself, not separate domain concepts.

| Field | Type | Nullable | Category | Purpose |
|-------|------|----------|----------|---------|
| `status` | `varchar(20)` | No, default `'active'` | **Lifecycle** | Tenant lifecycle state: `active`, `suspended`, `provisioning`, `deactivated` |
| `tier` | `varchar(30)` | Yes | **Billing metadata** | Platform subscription tier (nullable until billing is implemented) |
| `trial_ends_at` | `timestamptz` | Yes | **Billing metadata** | Trial period end time |
| `suspended_at` | `timestamptz` | Yes | **Lifecycle** | When tenant was suspended (NULL if not suspended) |
| `suspension_reason` | `text` | Yes | **Lifecycle** | Human-readable reason for suspension |
| `provisioned_at` | `timestamptz` | Yes | **Operational** | When tenant schema provisioning completed |

### Why these fields, and not a separate table?

These fields are **intrinsic attributes of the tenant entity**. A wholesaler's status, tier, and trial state are queried every time the system evaluates access or routing. Splitting them into a separate table would require a JOIN on every request for no architectural benefit.

### What is NOT proposed for wholesalers

- `billing_email`, `payment_method_id` — these belong in a billing context, not the tenant registry
- `admin_user_id` — duplicates identity; use existing auth relationship
- `max_users`, `max_retailers` — quota management belongs in a separate limits/quota table
- `settings_json` — opaque JSON blobs in the tenant registry are an anti-pattern

---

## 3. Proposed New Public-Schema Platform Tables

### 3.1 `public.platform_tenants` — Platform-level tenant lifecycle

**Responsibility**: Track platform-level operations that span across tenant provisioning, suspension, and deactivation. This is NOT a replacement for `wholesalers` — it is an operational journal for platform admin actions.

| Field | Type | Purpose |
|-------|------|---------|
| `id` | UUID (PK) | Platform tenant record ID |
| `wholesaler_id` | UUID (FK → wholesalers.id, UNIQUE) | Reference to tenant (one-to-one) |
| `provisioning_status` | varchar(20) | `pending`, `schema_created`, `seed_complete`, `failed` |
| `provisioning_log` | JSONB | Structured provisioning event log |
| `activated_at` | timestamptz | When platform activation completed |
| `deactivated_at` | timestamptz | When platform deactivation occurred |
| `deactivation_reason` | text | Reason for deactivation |
| `created_at` | timestamptz | Record creation time |
| `updated_at` | timestamptz | Record update time |

**Relationship**: One-to-one with `wholesalers` via `wholesaler_id`. Does NOT duplicate tenant identity — references it.

**Why a separate table**: Provisioning is a multi-step async process with its own state machine and log. Embedding this in `wholesalers` would mix tenant registry concerns with platform operational concerns. The `status` field on `wholesalers` gives a simple current-state view; `platform_tenants` gives the full operational history.

### 3.2 `public.platform_audit_logs` — Cross-tenant platform audit

**Responsibility**: Append-only log of platform-level administrative actions (NOT tenant business audit). This is distinct from `sys_audit_logs` (which tracks BI access patterns) and from future tenant-scoped business audit.

| Field | Type | Purpose |
|-------|------|---------|
| `id` | UUID (PK) | Log entry ID |
| `actor_type` | varchar(20) | `system`, `admin`, `api` |
| `actor_id` | UUID, nullable | Who performed the action (NULL for system) |
| `wholesaler_id` | UUID, nullable | Affected tenant (NULL for global actions) |
| `action` | varchar(100) | Action identifier (e.g., `tenant.suspend`, `tier.change`) |
| `resource` | varchar(255) | Affected resource path (e.g., `wholesalers/<id>`) |
| `metadata` | JSONB | Action details (before/after values, context) |
| `created_at` | timestamptz | Immutable creation time |

**Constraints**: Append-only. No UPDATE, no DELETE. Inherit from `Base` directly (no `AuditMixin` soft-delete), similar to `sys_audit_logs`.

**Why a separate table**: `sys_audit_logs` is for BI access patterns (S7-3, product track). Platform admin actions (tenant suspension, tier changes, deactivation) are a different domain with different retention and access-control requirements.

---

## 4. Data That Must NOT Go Here

### 4.1 Must NOT go into `public.wholesalers`

| Category | Example | Why not |
|----------|---------|---------|
| Business data | `order_count`, `revenue_total` | Belongs in tenant schemas; aggregations go through read-only queries |
| Quota/limits | `max_users`, `max_retailers`, `storage_limit_mb` | Belongs in a dedicated `platform_quotas` table (future) |
| Billing details | `payment_method_id`, `billing_email`, `invoice_address` | Belongs in `platform_billing` context (future, blocked) |
| Admin settings | `admin_user_id`, `allowed_features` | Duplicates identity or creates coupling |
| JSON blobs | `settings_json`, `metadata_json` | Opaque blobs defeat schema governance |

### 4.2 Must NOT go into new platform tables

| Category | Example | Why not |
|----------|---------|---------|
| Tenant business data | orders, products, inventory | Must remain in tenant schemas (DR-001) |
| Auth credentials | passwords, tokens, sessions | Must remain in tenant schemas |
| Product API state | shopping cart, checkout | Must remain in tenant schemas |
| Duplicate tenant identity | `tenant_code`, `tenant_schema` on platform tables | Use FK to `wholesalers.id` only |

---

## 5. Naming Convention

To avoid collision with existing `sys_*` product tables:

| Prefix | Scope | Examples |
|--------|-------|---------|
| (none) | Product business tables | `wholesalers`, `retailers`, `invitations` |
| `sys_` | Product system tables | `sys_audit_logs`, `sys_jobs`, `sys_reports` |
| `platform_` | **Platform tables** | `platform_tenants`, `platform_audit_logs` |

This convention gives clear ownership boundaries. All `platform_*` tables are platform-track territory.

---

## 6. Relationship Diagram

```
public.wholesalers (tenant registry — product track)
    │
    ├── 1:1 ── platform_tenants (provisioning journal — platform track)
    │
    ├── 1:N ── platform_audit_logs (admin actions — platform track)
    │
    ├── 1:N ── wholesalers_retailer_bindings (product track)
    │
    ├── 1:N ── invitations (product track)
    │
    └── tenants (per-schema) ─── all business tables
```

---

## 7. Recommendation: Safest First Implementation Slice

After this draft is reviewed and approved, the safest next step is:

### Slice: `wholesalers` extension + `platform_tenants` creation

**Rationale**:
1. Adding `status` and `provisioned_at` to `wholesalers` is a backward-compatible ALTER TABLE (new nullable columns with defaults). Zero product API breakage.
2. Creating `platform_tenants` as an empty table adds no runtime behavior — it's a data container for future provisioning work.
3. Neither change requires tenant-schema migrations.
4. Neither change touches auth, RBAC, or guardrails.

**Deliverables for the slice**:
- Alembic migration 018 (backward-compatible, adding columns + creating table)
- Updated `Wholesaler` model with new fields
- New `PlatformTenant` model
- Platform admin endpoints for reading (not mutating) tenant lifecycle status
- Ledger entry

**What this slice does NOT include**:
- `platform_audit_logs` (defer to next slice)
- Billing fields (`tier`, `trial_ends_at`) — only if CTO approves adding them now, otherwise defer
- Any endpoint that writes/mutates tenant state
- Any changes to tenant schemas

---

## 8. Open Questions for CTO

1. Should `tier` and `trial_ends_at` be included in the first slice, or deferred until billing is closer to implementation?
2. Should `platform_tenants` be populated retroactively for existing wholesalers, or only for new ones?
3. Is the `platform_` naming prefix acceptable, or does CTO prefer a different convention?
4. Should `platform_audit_logs` be part of the first slice or explicitly deferred?

---

*DRAFT — awaiting CTO review before implementation.*
