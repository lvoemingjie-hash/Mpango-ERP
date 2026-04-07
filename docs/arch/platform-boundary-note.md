# Platform Boundary & Model Direction Note

**Track**: Platform P0 - Alignment/Foundation  
**Date**: 2026-04-07  
**Status**: Initial boundary mapping  
**Decision authority**: CTO

---

## 1. What Belongs in public.wholesalers Extensions

These are **attribute extensions** to the existing tenant registry. They extend the current wholesalers table without changing its structure or tenancy semantics.

Examples:
- Additional platform metadata columns on wholesalers (e.g., subscription_tier, trial_end_date)
- Index changes for platform reporting queries
- Read-only computed views on wholesalers data

**Rule**: Any change to public.wholesalers must NOT break existing product APIs or tenant provisioning flow.

## 2. What Requires New public-schema Platform Tables

These are **new platform-only tables** in public schema that serve cross-tenant administrative purposes.

Examples:
- platform_tenants (platform-level tenant lifecycle management)
- platform_subscriptions (SaaS subscription records)
- platform_audit_logs (cross-tenant audit trail)
- platform_api_keys (platform-level API credentials)

**Rule**: New public platform tables must:
1. Use PublicBaseModel (stored in public schema)
2. Reference wholesalers.id as foreign key (NOT duplicate tenant identity)
3. Never store tenant-scoped business data
4. Be opt-in for tenants (no automatic creation during tenant provisioning)

## 3. What Must Remain in Tenant Business Schemas

These are **tenant-scoped business tables** that belong in individual tenant schemas (t_xxx).

Examples:
- users, roles, permissions (auth/RBAC)
- orders, order_items (sales)
- products, inventory (catalog)
- payments (finance)
- retailers (CRM)
- All current product-line tables

**Rule**: Platform work MUST NOT:
1. Read or write tenant schema data for cross-tenant purposes
2. Modify tenant schema table structures
3. Add columns to tenant-scoped models
4. Create migrations that touch tenant schemas

## 4. Frozen Zones

The following are architecturally frozen for Platform Track P0:

- Authentication model (JWT claims, login flow, token lifecycle)
- Schema-per-tenant isolation architecture (DR-001)
- Tenant provisioning workflow
- Product API endpoints (/api/v1/auth, /api/v1/orders, etc.)
- Tenant ORM guardrail interceptor
- Search-path routing mechanism

## 5. Approval Gates

Before any platform work expands beyond Track P0:
1. Boundary mapping must be reviewed by CTO
2. New platform tables need formal decision records (DR-xxx)
3. Migration ownership must be explicitly assigned
4. Impact on product bootability must be verified
