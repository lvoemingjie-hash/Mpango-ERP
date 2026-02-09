# S7-3: BI Access Audit Trail — The Recorder

**Track**: S7-3 (Audit Trail)
**Date**: 2026-02-09
**Status**: ✅ COMPLETE
**Author**: Backend AI (Chief Data Engineer)
**Phase**: 7 — Governance & Operations
**Depends On**: S7-2 (Enforcement Layer — The Police)
**Tests**: 38/38 passed (0.82s, 0 RuntimeWarnings)

---

## 1. Objective

Persist every BI policy decision (allow AND deny) to an append-only
audit table, using a **fire-and-forget** pattern that guarantees zero
impact on request latency.

**Before S7-3**: "We enforce the law, but have no record of it."
**After S7-3**: "Every policy decision is an immutable fact, persisted
asynchronously and queryable for compliance."

---

## 2. CTO Mandates (Frozen Constraints)

### 🔒 Constraint S7-3-C1 — Control Plane in Public Schema

> All Audit / Compliance / Security Logs MUST reside in the **public schema**.
> Tenant is a data dimension (column), NOT a schema boundary.

**Rationale**: Compliance officers need cross-tenant, cross-asset, cross-time
unified views. Tenant-scoped audit tables would fracture query capability.

### 🔒 Constraint S7-3-C2 — Append-Only Semantic Object

> `SysAuditLog` is an immutable fact record:
> - No `updated_at`, `is_deleted`, `deleted_at` columns.
> - No `soft_delete()`, `restore()`, `update()` methods.
> - ORM declares `confirm_deleted_rows=False`.
> - DB-level `REVOKE UPDATE/DELETE` is a Phase 8 ops task.

**Anti-pattern avoided**: Inheriting `AuditMixin` (which adds mutable columns)
would be semantically wrong for an immutable fact table.

### 🔒 Constraint S7-3-C3 — Audit Failure Is Observable, Not Fatal

> - The policy decision is already final before audit runs.
> - Audit failure MUST NOT affect the original request result.
> - Audit failure MUST be observable (structured error log).

---

## 3. Architecture

### 3.1 File Structure

```
backend/
├── models/audit.py                    # SysAuditLog ORM model
├── services/audit_writer.py           # write_audit_log() — async persistence
├── api/middleware/bi_access.py         # _audit_hook() — wired to BackgroundTasks
├── alembic/versions/014_s7_3_audit_trail.py  # Migration
└── tests/test_s7_2_enforcement.py     # 38 tests (S7-2 + S7-3 combined)
```

### 3.2 Data Flow

```
enforce_bi_access() / RequireBIPermission.__call__()
    │
    ├── evaluate_policy() → PolicyResult (decision is FINAL)
    │
    ├── _audit_hook(result, tenant_id, background_tasks)
    │       │
    │       └── background_tasks.add_task(write_audit_log, result, tenant_id)
    │               │
    │               └── (AFTER HTTP response is sent)
    │                       AsyncSessionLocal() → public schema
    │                       INSERT INTO sys_audit_logs
    │                       commit()
    │                       on error: logger.error() — swallow, do NOT raise
    │
    ├── if not result.allowed → raise HTTPException(403)
    └── return PolicyResult
```

### 3.3 Key Design Decision: Why Not S4 Job Queue?

| Factor | BackgroundTasks | S4 Job Queue |
|--------|----------------|--------------|
| Latency overhead | ~0 (in-process) | Queue serialization + worker poll |
| Complexity | Minimal | Overkill for single INSERT |
| Failure mode | Log error, swallow | Retry logic, dead-letter queue |
| Appropriate for | High-frequency, low-cost side-effects | Heavy async jobs (exports, reports) |

**Verdict**: BackgroundTasks is the correct choice for audit logging.

---

## 4. Database Schema

### `sys_audit_logs` (public schema)

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `id` | UUID | PK | `gen_random_uuid()` |
| `created_at` | TIMESTAMPTZ | NOT NULL | Server-generated, immutable |
| `actor_id` | VARCHAR(255) | NOT NULL | `user_id` from PolicySubject |
| `tenant_id` | VARCHAR(255) | NOT NULL | `tenant_id` from PolicySubject |
| `action` | VARCHAR(50) | NOT NULL | BIAction value |
| `asset_urn` | VARCHAR(512) | NOT NULL | Full URN of target asset |
| `allowed` | BOOLEAN | NOT NULL | Policy decision |
| `policy_name` | VARCHAR(100) | NOT NULL | Which policy rule decided |
| `reason` | TEXT | NOT NULL | Sanitized reason (no PII) |
| `metadata` | JSONB | NULL | Extensible context |

### Indexes

| Name | Columns | Purpose |
|------|---------|---------|
| `ix_sys_audit_logs_tenant_created` | `(tenant_id, created_at)` | Compliance queries by tenant + date range |
| `ix_sys_audit_logs_actor` | `(actor_id)` | "What did user X do?" |
| `ix_sys_audit_logs_asset_urn` | `(asset_urn)` | "Who accessed asset Y?" |
| `ix_sys_audit_logs_allowed` | `(allowed)` | Filter denied-only for security review |

### Partitioning Strategy (Deferred)

> **Threshold**: When `sys_audit_logs` exceeds **10M rows**, Ops MUST enable
> monthly range partitioning on `created_at` + retention policy.
>
> Current state: standard table with composite index. Sufficient for
> early-stage volumes.

---

## 5. Model Design: Why NOT AuditMixin

```
BaseModel (standard business objects)
├── inherits: Base + AuditMixin + UserTrackingMixin
├── has: id, created_at, updated_at, is_deleted, deleted_at, created_by, updated_by
└── semantics: mutable business entity

SysAuditLog (immutable fact record)
├── inherits: Base only
├── has: id, created_at (and domain columns)
├── missing: updated_at, is_deleted, deleted_at, created_by, updated_by
└── semantics: append-only fact, never modified
```

This is a deliberate architectural choice, not an omission.

---

## 6. Test Coverage (38 tests)

| Category | Count | Description |
|----------|-------|-------------|
| Trust Boundary | 6 | Subject building, roles from DB, missing context → 401 |
| Declarative Enforcement | 7 | Admin allow, viewer deny, finance export, cross-tenant |
| Imperative Enforcement | 6 | Allow/deny, BIAsset object, invalid URN fail-safe |
| Fail-Safe | 2 | No roles, unknown role |
| Error Detail Security | 3 | Tenant isolation generic msg, no role leak |
| **Audit Hook (S7-3)** | **5** | **Enqueue on allow/deny, BackgroundTasks wiring, skip when None, swallow enqueue error** |
| Full Request Flow | 6 | End-to-end scenarios + audit enqueue verification |
| **Audit Writer Service** | **3** | **Session mock: creates entry, swallows DB error, passes metadata** |

---

## 7. Migration

**File**: `alembic/versions/014_s7_3_audit_trail.py`
**Revision**: `014_s7_3_audit_trail`
**Down Revision**: `013_s6_2_materialize_sales`

```bash
# Apply migration
alembic upgrade 014_s7_3_audit_trail

# Rollback
alembic downgrade 013_s6_2_materialize_sales
```

---

## 8. Usage Examples

### Declarative (static URN) — audit is automatic

```python
@router.get("/kpi/summary")
async def kpi_summary(
    _policy=Depends(RequireBIPermission(
        BIAction.VIEW,
        "urn:bi:dashboard:executive:executive_summary",
    )),
):
    # _audit_hook is called inside RequireBIPermission.__call__
    # BackgroundTasks is injected by FastAPI automatically
    ...
```

### Imperative (dynamic URN) — pass background_tasks explicitly

```python
@router.post("/reports/analyze")
async def analyze(
    body: SemanticQueryRequest,
    subject: PolicySubject = Depends(get_policy_subject),
    background_tasks: BackgroundTasks,
):
    urn = f"urn:bi:report:sales:adhoc_{body.view.value}_analysis"
    enforce_bi_access(subject, BIAction.INTERACT, urn,
                      background_tasks=background_tasks)
    ...
```

---

## 9. Future Phases

| Phase | What It Adds | Relationship to S7-3 |
|-------|-------------|---------------------|
| P7-4 | Compliance dashboard | Queries `sys_audit_logs` directly |
| P7-5 | "Explain Why" UX | Uses `reason` + `policy_name` from audit log |
| P8-ops | DB-level REVOKE UPDATE/DELETE | Hardens S7-3-C2 at infrastructure layer |
| P8-ops | Monthly partitioning | Triggered when >10M rows |
| P8-ops | Retention policy | Archive/purge old audit records |

---

**Document Status**: ✅ COMPLETE
**Last Updated**: 2026-02-09
