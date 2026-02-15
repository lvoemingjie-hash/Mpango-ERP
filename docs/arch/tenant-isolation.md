# Tenant Isolation Guardrail (Track E1, v0.2.0)

## 1) Objective

Make cross-tenant data leakage architecturally impossible by default in backend ORM flows.

This guardrail enforces three rules:

1. Every tenant-scoped ORM query must run with tenant context.
2. Tenant-keyed models are auto-filtered (`tenant_id` / `wholesaler_id`) at ORM execution time.
3. Any system-wide access must be explicit and reasoned (auditable bypass).

---

## 2) Request-Scoped Tenant Context

Tenant context is established as early as authentication middleware and then carried through request handling.

### 2.1 Context Source

- JWT claims provide `tenant_id` and `tenant_schema`.
- Middleware/session plumbing sets context for both:
  - request state (for endpoint dependencies)
  - `ContextVar` values (for global guardrail checks)

### 2.2 Session Binding

For tenant-scoped sessions:

- `session.info["tenant_schema"]` is set.
- `SET LOCAL search_path TO "<tenant_schema>", public` is executed.

This preserves schema-per-tenant isolation while allowing global filter logic to validate context presence and apply row predicates where tenant key columns exist.

---

## 3) ORM Guardrail Interceptor

The guardrail is implemented via SQLAlchemy `Session.do_orm_execute` hook.

### 3.1 Intercept Scope

For ORM `SELECT`, `UPDATE`, `DELETE` statements:

1. Check bypass first.
2. If not bypassed, require tenant context.
3. Inject tenant criteria where model metadata indicates tenant-keyed columns.

### 3.2 Fail-Safe Behavior

If context is missing/invalid, raise `TenantContextMissingError`:

- `"Tenant context required"` when schema context is absent.
- `"Tenant context missing: tenant_id required for tenant-scoped query"` when querying models requiring tenant key filtering without `tenant_id`.
- `"Tenant context invalid: tenant_id must be a UUID for wholesaler-scoped query"` for invalid UUID tenant IDs used against `wholesaler_id` models.

No silent fallback to unscoped query is allowed.

### 3.3 Automatic Tenant Predicate

The hook adds `with_loader_criteria(DeclarativeBase, ...)` and applies:

- `tenant_id == :mpango_tenant_id` for models exposing `tenant_id`
- `wholesaler_id == :mpango_tenant_uuid` for models exposing `wholesaler_id`

Tenant values are bound with `bindparam` for type-safe parameterization.

---

## 4) Explicit System-Wide Bypass

Two explicit bypass mechanisms are allowed:

1. **Per-query bypass**: `.execution_options(ignore_tenant=True)`
2. **Scoped bypass wrapper**: `run_as_system(reason="...")`
   - Requires non-empty reason
   - Applies only inside wrapper scope

A session-level marker helper (`mark_session_as_system`) is also available for controlled infrastructure-style use cases.

### 4.1 Current Approved Public Flows

Bypass is intentionally used for public entrypoints that cannot have authenticated tenant context:

- invitation status lookup by code
- retailer registration by invitation code

Both are wrapped in `run_as_system(...)` with explicit reason strings.

---

## 5) Proof of Protection (Red Test)

Red tests verify guardrail failure mode for missing tenant context:

- Querying tenant-keyed rows without tenant context raises `TenantContextMissingError`.
- Querying Orders-like `wholesaler_id` rows with schema set but missing `tenant_id` raises:
  `"Tenant context missing: tenant_id required for tenant-scoped query"`.

This proves the system fails closed (error) rather than failing open (empty or cross-tenant data).

---

## 6) Usage Guidelines

1. Default path: always run tenant business logic with request tenant context.
2. If bypass is needed, use the smallest possible scope and include a reason.
3. Never introduce implicit bypasses.
4. Keep tests for both:
   - enforcement (`TenantContextMissingError`)
   - explicit bypass behavior (`ignore_tenant=True`, `run_as_system`).
