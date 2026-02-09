# S7-4: Tenant-Scoped Assets — User-Defined Content

**Track**: S7-4 (Tenant-Scoped Assets)
**Date**: 2026-02-09
**Status**: ✅ COMPLETE (Core Infrastructure)
**Author**: Backend AI (Chief Product Architect)
**Phase**: 7 — Governance & Operations
**Depends On**: P7-0 (Models), S7-1 (Policy Engine), S7-2 (Enforcement), S7-3 (Audit)
**Tests**: 147/147 passed (S7-1: 55, S7-2+S7-3: 38, S7-4: 54) — 0.94s

---

## 1. Objective

Evolve from "hardcoded system assets" to "user-defined tenant assets."
Enable users to create, own, and share BI assets within their tenant,
governed by the same policy engine that protects system assets.

**Before S7-4**: "The registry is a static dictionary. Only engineers can add assets."
**After S7-4**: "Users create reports. The registry resolves them dynamically.
Ownership and ACL govern who can see, interact, export, and manage."

---

## 2. CTO Mandates (Frozen Constraints)

### 🔒 S7-4-C1 — URN Does Not Carry tenant_id

> URN only describes "what asset is this."
> tenant_id belongs to "in which context is it accessed."
> Asset ownership is a **data attribute**, not part of the identifier.

**Rationale**: URN stability across tenant lifecycle events (migration,
copy, template). Embedding tenant_id would cause:
- URN/deployment coupling
- Asset migration breakage
- Frontend cache invalidation
- Audit log pollution

**URN format unchanged**: `urn:bi:<type>:<domain>:<id>` (5 segments)

### 🔒 S7-4-C2 — Owner Bypass Constraints

> Owner bypass conditions (ALL must be true):
> 1. `asset.owner_id == subject.user_id`
> 2. `asset.tenant_id == subject.tenant_id`
> 3. `asset.is_system_wide == False`
>
> Owner bypass does NOT apply to system assets.
> Owner cannot bypass tenant isolation.

### 🔒 S7-4-C3′ — ACL Authorization Semantics (Semantic B)

> ACL is an **independent authorization channel** (not gated by Role Matrix).
> - Grants: VIEW, INTERACT, EXPORT (hard ceiling)
> - NEVER grants: MANAGE
> - Does NOT depend on user's Role-Action Matrix permissions
> - ACL is a **sharing mechanism**, not an authorization escalation tool
>
> Product scenario: "Finance user shares a report with a viewer colleague,
> granting them EXPORT capability — even though viewer only has VIEW in
> the role matrix."

### 🔒 S7-4-C4 — Cache Invalidation Canon

> These events MUST trigger cache invalidation:
> 1. Asset CRUD (create/update/delete) → `invalidate_asset(urn)`
> 2. ACL change → `invalidate_asset(urn)`
> 3. Owner change → `invalidate_asset(urn)`
> 4. Tenant deletion → `invalidate_tenant(tenant_id)`

---

## 3. Architecture

### 3.1 File Structure

```
core/governance/
├── models.py      ← MODIFIED: +owner_id, +acl, +ACL_MAX_ACTIONS, +helpers
├── resolver.py    ← NEW: AssetResolver Protocol, CacheInvalidator, NullResolver
├── registry.py    ← MODIFIED: +Dynamic resolution chain, +LRU cache, +invalidation
├── policy.py      ← MODIFIED: +Owner Bypass (step 3), +ACL Check (step 4)
├── __init__.py    ← MODIFIED: +new exports
├── roles.py       ← UNCHANGED
tests/
└── test_s7_4_tenant_assets.py  ← NEW: 54 tests
```

### 3.2 Resolution Chain

```
get_asset_async("urn:bi:report:sales:my_report", tenant_id="tenant-abc")
    │
    ├── 1. Static Registry (GOVERNANCE_REGISTRY dict)  ← O(1)
    │       Found? → return BIAsset
    │
    ├── 2. LRU Cache (dict, max 1024, thread-safe)     ← O(1)
    │       Found? → return BIAsset (move to MRU)
    │
    └── 3. DynamicResolver.resolve(urn, tenant_id)     ← async DB query
            Found? → cache_put + return BIAsset
            Not found? → raise KeyError
```

**Backwards compatibility**: `get_asset()` (sync) still works for static
assets. `get_asset_async()` is the new entry point for full resolution.

### 3.3 Policy Evaluation Order (6 Steps)

```
evaluate_policy(subject, action, asset)
    │
    ├── 1. Tenant Isolation    → DENY if tenant mismatch       (unchanged)
    ├── 2. Admin Bypass        → ALLOW if admin                 (unchanged)
    ├── 3. Owner Bypass (S7-4) → ALLOW if owner matches         (NEW)
    │       Conditions: owner_id match + same tenant + not system asset
    │       Grants: VIEW / INTERACT / EXPORT / MANAGE
    ├── 4. ACL Check (S7-4)    → ALLOW if subject in ACL        (NEW)
    │       Ceiling: VIEW / INTERACT / EXPORT (never MANAGE)
    │       Independent of Role Matrix (Semantic B)
    ├── 5. Role-Action Matrix  → ALLOW if role grants action    (unchanged)
    └── 6. Default Deny        → DENY                           (unchanged)
```

### 3.4 BIAsset Model Extensions

```python
class BIAsset(BaseModel):
    # ... existing fields ...

    # S7-4: Ownership
    owner_id: Optional[str] = None   # User ID of creator. None = system asset.

    # S7-4: Access Control List
    acl: list[str] = []              # "user:<id>", "role:<name>", "tenant:*"

    # S7-4: Helper properties
    is_tenant_scoped: bool           # tenant_id is not None
    has_owner: bool                  # owner_id is not None
    is_shared: bool                  # len(acl) > 0

    # S7-4: Helper methods
    is_owned_by(user_id) -> bool
    check_acl(user_id, roles) -> bool
```

**System assets are unaffected**: `owner_id=None`, `acl=[]` → steps 3-4 are no-ops.

---

## 4. ACL Entry Format

| Pattern | Meaning | Example |
|---------|---------|---------|
| `user:<uuid>` | Specific user | `user:abc-123` |
| `role:<name>` | All users with this role | `role:finance` |
| `tenant:*` | All users in the tenant | `tenant:*` |

ACL entries are validated at model construction time (Pydantic validator).

---

## 5. S7-4-T3: Concrete Implementation

### 5.1 Storage Layer — `sys_reports` (Tenant Schema)

```
Table: sys_reports (tenant schema)
├── id           UUID PK (gen_random_uuid)
├── title        VARCHAR(256) NOT NULL
├── description  TEXT NULL
├── domain       VARCHAR(50) NOT NULL DEFAULT 'custom'
├── config       JSONB NOT NULL (validated: layout + widgets)
├── owner_id     UUID NOT NULL (forced server-side)
├── acl          JSONB NOT NULL DEFAULT '[]'
├── created_at   TIMESTAMPTZ (AuditMixin)
├── updated_at   TIMESTAMPTZ (AuditMixin)
├── is_deleted   BOOLEAN (soft delete)
├── created_by   UUID (UserTrackingMixin)
└── updated_by   UUID (UserTrackingMixin)

Indexes: ix_sys_reports_owner_id, ix_sys_reports_domain
Migration: 015_s7_4_sys_reports.py
```

### 5.2 DbAssetResolver — Row-to-Asset Mapping

```
SysReport (DB Row)              →  BIAsset (Governance Object)
─────────────────────────────      ──────────────────────────────
row.id                          →  BiUrn(report, <domain>, <id>)
row.title                      →  display_name
row.description                →  description
row.owner_id                   →  owner_id (as string)
row.acl                        →  acl (list[str])
row.domain                     →  BiUrn.domain (mapped to BIDomain)
row.created_at                 →  created_at (ISO 8601)
tenant_id (context param)      →  tenant_id
```

Registered at app startup: `main.py` → `lifespan()` → `register_resolver(DbAssetResolver(AsyncSessionLocal))`

### 5.3 CRUD API

| Method | Endpoint | Action | Enforcement |
|--------|----------|--------|-------------|
| `POST` | `/api/bi/assets/reports` | Create report | owner_id forced from auth |
| `GET` | `/api/bi/assets/reports/{id}` | Get report | `enforce_bi_access(VIEW)` → resolution chain |
| `PATCH` | `/api/bi/assets/reports/{id}` | Update report | `enforce_bi_access(MANAGE)` → owner/admin only |
| `DELETE` | `/api/bi/assets/reports/{id}` | Soft-delete | `enforce_bi_access(MANAGE)` → owner/admin only |
| `GET` | `/api/bi/assets/reports` | List reports | Owner sees own; admin sees all |

**Config Validation**: `config` JSONB validated via Pydantic (`ReportConfig` schema: requires `layout` + at least 1 `widget`).

### 5.4 BiUrn Identifier Pattern Update

Pattern relaxed from `^[a-z][a-z0-9_]*$` to `^[a-z0-9][a-z0-9_-]*$` to accept UUID identifiers for tenant-created assets while maintaining backward compatibility with snake_case system asset identifiers.

---

## 6. Test Coverage (184 tests total)

| Category | Count | File | Description |
|----------|-------|------|-------------|
| S7-1 Policy Engine | 55 | `test_s7_1_policy.py` | Evaluation order, role matrix, admin bypass |
| S7-2+S7-3 Enforcement+Audit | 38 | `test_s7_2_enforcement.py` | HTTP enforcement, audit hooks |
| S7-4 Core (Owner+ACL+Registry) | 54 | `test_s7_4_tenant_assets.py` | Owner bypass, ACL Semantic B, dynamic registry, cache |
| S7-4-T3 (Resolver+Schemas+API) | 37 | `test_s7_4_t3_resolver_api.py` | URN parsing, row→asset, Pydantic validation, resolver |

**Full regression**: 184/184 passed in 1.20s.

---

## 7. Remaining Work (Future Phases)

| Item | Phase | Description |
|------|-------|-------------|
| Integration tests | S7-4-T3+ | Full HTTP round-trip tests with test DB |
| Report templates | P8 | Pre-built report templates for common use cases |
| Report versioning | P8 | Config version tracking for schema evolution |

---

## 8. Key Design Decisions

### Why Protocol, not ABC?

`AssetResolver` uses `typing.Protocol` (structural typing) because:
- Resolver is injected at app startup, not inherited
- Mock resolvers in tests match the shape without class hierarchy
- Future resolvers (Redis, external catalog) just need matching methods

### Why dict-based LRU, not functools.lru_cache?

- `lru_cache` doesn't support selective invalidation (by URN or tenant)
- `lru_cache` doesn't support async functions natively
- Our dict-based LRU with `threading.Lock` gives us:
  - O(1) lookup with MRU promotion
  - Selective invalidation per 🔒 S7-4-C4
  - Thread safety for concurrent requests

### Why ACL Semantic B (independent channel)?

CTO ruling: ACL must support the product scenario where a finance user
shares a report with a viewer colleague for export. If ACL were gated
by Role Matrix (Semantic A), this scenario would be impossible because
viewer only has VIEW in the baseline matrix.

---

**Document Status**: ✅ COMPLETE
**Last Updated**: 2026-02-09
