# Mpango Engineering Handbook v0.2

Author: CTO Office

---

# 1 Branch Strategy

Main branches:

- `main` - protected release-candidate branch
- `product-dev` - product line integration branch
- `platform-dev` - platform line integration branch
- `coordination/docs-sync` - optional shared-memory and governance sync branch

Feature branches:

- `feature/<module>-<name>` off `product-dev`
- `platform/<module>-<name>` off `platform-dev`
- `docs/<topic>` for governance, strategy, and memory-only changes

Examples:

- `feature/orders-discount`
- `platform/tenant-registry-scaffold`
- `docs/cto-memory-sync`

Rules:

- Never commit directly to `main`
- Do not use `develop` as the default integration branch
- Durable governance and memory docs are first-class project assets and should be committed like code
- Use doc-only commits when strategy, architecture, or operating rules change

---

# 2 Database Migration Rules

All schema changes must use Alembic.

Check migration heads:

`alembic heads`

If multiple heads appear:

`alembic merge`

Platform track must not modify core business tables casually.

Allowed early platform tables:

- `tenants`
- `subscriptions`
- `audit_logs`
- `invoices`

Cross-track migration rules:

- only one machine owns a migration slice at a time
- product and platform must not edit the same migration chain blindly
- durable migration governance decisions must be recorded in repo docs

---

# 3 Multi-Tenant Security

Architecture:

- shared PostgreSQL instance
- primary isolation model: `schema-per-tenant`
- secondary guardrail: tenant-key filtering where applicable

Current repository truth:

- JWT carries `tenant_id` and `tenant_schema`
- request-scoped DB access uses `SET LOCAL search_path TO "<tenant_schema>", public`
- ORM guardrails may apply `tenant_id` or `wholesaler_id` predicates as defense in depth

Do not reinterpret this as migration to a shared-table row-level tenancy architecture.

---

# 4 API Contract Rules

API defined via OpenAPI.

Allowed:

- add optional fields
- add endpoints
- add query parameters where backward compatible

Forbidden:

- remove fields
- change field types incompatibly
- remove endpoints casually

All APIs must remain backward compatible unless a formal decision explicitly says otherwise.

---

# 5 Code Review

Every PR requires review.

Checklist:

- code clarity
- tenant isolation
- migration correctness
- security concerns
- contract alignment
- shared-memory updates when durable decisions changed

---

# 6 Release Process

Release flow:

1. Merge product work into `product-dev` or platform work into `platform-dev`
2. Sync shared-memory docs when architecture, strategy, or governance changed
3. Run integration testing on the relevant track branch
4. Merge approved track branch into `main`
5. Deploy

Database migrations run during deployment only after review and branch alignment.

---

# 7 Shared Memory Commit Policy

The following must be git-tracked and synchronized across machines:

- `docs/ai/`
- `decision-register/`
- `ai-ledger/`

Rules:

- if a durable decision changes, update docs before or with implementation
- if memory changes independently of code, commit docs separately
- both machines must pull shared-memory updates before major work starts
