# B6 Hardening (Backend) — Architecture Note

## Context

Mpango ERP uses **PostgreSQL schema-per-tenant** multi-tenancy.

- Each tenant has its own schema (e.g. `t_<uuid_without_dashes>`).
- Tenant isolation is implemented via `SET LOCAL search_path = <tenant_schema>, public`.

This note explains why the B6 hardening decisions are aligned with this architecture.

## Why schema-per-tenant

We keep schema-per-tenant because:

- It provides strong isolation by default (table namespaces are separate).
- It avoids pervasive `tenant_id` columns on every row and the risk of missing filters.
- Operationally, uniqueness constraints and indexes are naturally tenant-scoped (they live inside a tenant schema).

## Why enforcement is “context-required” (not tenant_id filtering)

Under schema-per-tenant, the primary isolation boundary is the **database search_path**, not a `tenant_id` column.

Therefore, B6 P1 enforces:

- ORM operations must have an explicit tenant context present.
- The application must set the tenant schema context (and therefore ensure correct `search_path`) before running ORM queries.

This catches a large class of bugs:

- Accidentally using a public/unscoped session for tenant ORM queries.
- Background tasks or utility code issuing ORM queries without any tenant selection.

### Future-proofing (tenant_id models)

If a future model *does* have a `tenant_id` column, we also apply a loader criterion:

- `with_loader_criteria(... tenant_id == current_tenant_id ...)`

This is additive hardening for mixed models, but it is not relied upon for current tenant isolation.

## `execution_options(ignore_tenant=True)` escape hatch

Some operations must legitimately run without a tenant context, for example:

- reading public schema tables
- maintenance tasks
- startup checks

For these cases, the global ORM enforcement supports an explicit escape hatch:

- `.execution_options(ignore_tenant=True)`

When set, the enforcement hook will:

- skip the “tenant context required” guard
- skip any tenant_id loader-criteria injection

This keeps the enforcement strict by default while preserving controlled, auditable exceptions.
