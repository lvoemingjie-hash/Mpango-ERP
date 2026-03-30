# Platform Proposal CTO Review

Reviewed document:

- `docs/ERP-Platform-Proposal-v3.2-APPROVED.md`

Review date:

- 2026-03-30

## Executive Verdict

The proposal contains useful platform direction, but it is not safe to implement as written without alignment corrections.

The biggest risk is tenancy-model drift.

Current repository truth is:

- primary isolation model: `schema-per-tenant`
- tenant identity carried in JWT: `tenant_id` plus `tenant_schema`
- runtime database routing: `SET LOCAL search_path TO "<tenant_schema>", public`
- additional ORM guardrail: tenant-key filtering using `tenant_id` or `wholesaler_id` where applicable

Therefore the correct CTO reading is:

- Mpango has **schema-per-tenant as the architectural isolation model**
- It also uses **tenant-key guardrails as defense in depth**
- It has **not** switched to a shared-table row-level tenancy architecture

Any platform plan that assumes "continue with tenant_id model instead of schema-per-tenant" is currently misaligned with approved repository decisions.

## P0 Findings

### P0-1 Tenancy Model Conflict

The proposal states or implies that the system should continue with a `tenant_id` row-level model in place of schema-per-tenant.

This conflicts with:

- `decision-register/DR-001_schema-per-tenant.md`
- `docs/contracts/multi_tenancy_spec.md`
- `docs/arch/tenant-isolation.md`

CTO ruling:

- Do not let platform work rewrite tenancy assumptions by proposal text alone
- Until a new formal decision is made, platform work must assume `schema-per-tenant` remains authoritative

### P0-2 Platform Work Starting Too Wide

The proposal includes data model, governance, API evolution, billing, admin console, audit design, performance targets, and deployment posture all at once.

This is too broad for a platform track that has not yet begun implementation and has not yet reconciled with the active product architecture.

CTO ruling:

- Platform track must start in bounded foundation mode
- First implementation slices should be documentation, interfaces, scaffolding, and isolated admin/platform tables only

## P1 Findings

### P1-1 Global Tenant Filter Must Not Replace Schema Routing

The proposal treats a global tenant filter as if it can be the primary tenancy mechanism.

Repository evidence shows it should be treated as a secondary guardrail layered on top of schema routing.

CTO ruling:

- keep global tenant filtering as defense in depth
- do not redesign the system around shared-table filtering

### P1-2 Platform Table Scope Needs Clear Boundary

Some proposed platform tables are reasonable:

- `tenants`
- `subscriptions`
- `invoices`
- `audit_logs`

But their relationship to `public.wholesalers`, tenant provisioning, and tenant schemas needs explicit mapping before implementation.

CTO ruling:

- platform tables may be introduced only after the ownership and lifecycle of each table is mapped against current product tenant creation flow

### P1-3 Progressive Contract Rule Needs Narrower Use

Backward-compatible API evolution is a reasonable principle.

However, platform APIs and product APIs should not be treated as one undifferentiated contract surface if they evolve at different speeds and carry different risks.

CTO ruling:

- progressive contract is acceptable in principle
- but platform API evolution must not silently destabilize product-side frontend or auth assumptions

## P2 Findings

### P2-1 Infra Ambition Is Mostly Correctly Reduced

The proposal is directionally right to reject premature mesh complexity and heavyweight audit infrastructure at the current stage.

This aligns with current CTO posture:

- avoid infra theater
- build only what current scale and operational need justify

## Approved Direction From The Proposal

These elements are directionally acceptable:

- platform work should begin with tenant registry, admin console, audit logging, and lightweight billing
- avoid premature Istio/service-mesh complexity
- keep audit implementation simple at first
- use migrations and governance discipline
- stage platform growth across maturity levels rather than overbuilding now

## Required Corrections Before Platform Implementation

1. Replace any wording that frames row-level `tenant_id` isolation as the primary tenancy architecture
2. Add a section explaining how platform-level entities relate to:
   - `public.wholesalers`
   - tenant schema provisioning
   - JWT tenant claims
   - search-path-based session routing
3. Clarify whether platform tables live in `public` and how they are administered
4. Define exactly which platform changes are allowed without touching frozen product zones
5. Narrow Phase 1 to one approved slice before coding begins

## CTO-Approved Platform Start Order

1. Alignment note on tenancy model and shared vocabulary
2. Platform data-boundary mapping
3. Tenant registry scope note
4. Minimal scaffolding or docs-first implementation
5. Review before any billing or assume-role work

## Final Ruling

The proposal is usable as a strategic reference, not as a direct build specification.

Platform implementation must begin only after tenancy alignment corrections are made and the first slice is narrowed.
