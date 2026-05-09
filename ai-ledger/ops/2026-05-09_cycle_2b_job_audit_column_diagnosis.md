# Stabilization Cycle 2B — Job Model Audit Column Boundary Diagnosis

Date: 2026-05-09
Branch: ops/integration-rehearsal-clean-2026-05-08
Worktree: C:\Users\Jeff0\MPANGO ERP\product-dev-recovered-review
Agent: Goose
Status: DIAGNOSIS COMPLETE — awaiting CTO fix direction

---

## Root Cause

**Confidence: 95%**

`Job` model (`models/job.py`) inherits directly from `Base` (raw `DeclarativeBase`) — **not** from `BaseModel` or `PublicBaseModel`. This means it bypasses `AuditMixin` and lacks `is_deleted` and `deleted_at` columns.

### Why it only fails in full/subset test runs

`Job` is **not imported** in `models/__init__.py`, so it doesn't register in `Base.registry` during normal imports. It only gets registered when a test file directly imports it — specifically `tests/test_s4_jobs_persistence.py` line 1: `from models.job import Job`.

**Leak chain:**
1. pytest runs `test_s4_jobs_persistence.py` first (alphabetical or collection order)
2. `from models.job import Job` triggers ORM registration into `Base.registry`
3. `test_models_structure.py::test_all_models_have_audit_columns` iterates `Base.registry.mappers`
4. `Job` is now in the registry → check finds `is_deleted`, `deleted_at` missing → **FAIL**

### Why `test_public_base_model_has_audit_columns` is NOT affected

That test uses `next()` to pick the first matching public model. With Job registered, `next()` picks `PlatformAuditLog` (schema='public', inherits `PublicBaseModel` which has all audit columns) — it never reaches `Job`.

### Verified registration state

| Model | Inherits | Schema | has `is_deleted`? | has `deleted_at`? |
|-------|----------|--------|--------------------|-------------------|
| Job | `Base` (raw) | public | ❌ NO | ❌ NO |
| SysAuditLog | `Base` (raw) | None | ❌ NO (exempt via `_FROZEN_APPEND_ONLY_MODELS`) | ❌ NO (exempt) |
| PlatformAuditLog | `PublicBaseModel` | public | ✅ YES | ✅ YES |

## Reproduction

### Isolation (passes — Job not registered):
```bash
poetry run pytest tests/test_models_structure.py -q --tb=short
# 8 passed
```

### Smallest failing group (1 test fails):
```bash
poetry run pytest tests/test_s4_jobs_persistence.py tests/test_models_structure.py -q --tb=short
# FAILED tests/test_models_structure.py::TestORMModelStructure::test_all_models_have_audit_columns
# AssertionError: Job missing audit columns: {'is_deleted', 'deleted_at'}
```

## Fix Options Analysis

### Option A: Add audit columns to Job model
- **Scope**: `models/job.py` — add `is_deleted` and `deleted_at` columns
- **Migration**: YES — requires ALTER TABLE `public.sys_jobs` ADD COLUMN
- **Production risk**: LOW — adding nullable columns is backward compatible
- **Migration impact**: `is_deleted BOOLEAN NOT NULL DEFAULT false`, `deleted_at TIMESTAMPTZ` — safe additive migration
- **Governance**: Job is an infrastructure model, but it's a *mutable* job tracker (status changes, retry logic). Soft-delete semantics are valid for "cancelled" jobs.
- **Recommendation**: Cleanest long-term fix

### Option B: Exclude Job explicitly in test (like SysAuditLog)
- **Scope**: `tests/test_models_structure.py` — add `"Job"` to `_FROZEN_APPEND_ONLY_MODELS` or a new exclusion set
- **Migration**: NONE
- **Production risk**: NONE
- **Governance concern**: Job is NOT truly append-only (it has `updated_at`, `onupdate`, status transitions). Calling it "frozen append-only" would be inaccurate. Better to create a separate exclusion set: `_INFRASTRUCTURE_MODELS = {"Job"}`.
- **Recommendation**: Quick fix if CTO wants minimal risk

### Option C: Ensure Job is imported consistently in `models/__init__.py`
- **Scope**: `models/__init__.py` — add `from models.job import Job`
- **Migration**: NONE (no schema change)
- **Production risk**: NONE — import-only change
- **Governance benefit**: Makes the failure deterministic (always fails, not order-dependent)
- **Note**: This alone does NOT fix the test failure — it just makes it reproducible in isolation. Must pair with Option A or B.
- **Recommendation**: Should be done regardless of A vs B

### Option D (Combined, recommended): C + A or C + B
1. Add `from models.job import Job` to `models/__init__.py` (deterministic registration)
2. Choose A (add columns + migration) or B (test exclusion)

## Production Risk if Left Unfixed

**MEDIUM** — if Job stays in this ambiguous state:
- Test is order-dependent, masking real regressions
- `Job` has no soft-delete capability, which could cause issues if jobs need cancellation/cleanup
- No migration risk currently since the column simply doesn't exist

## Is This Platform Governance or Test Boundary?

**Both — primarily a model boundary issue.**
- `Job` was created as S4 infrastructure, inheriting raw `Base` to avoid tenant schema coupling
- The audit column contract (`database_contract.md`) says "All tables MUST include these columns"
- `SysAuditLog` got a CTO exemption (frozen append-only) — `Job` has no such exemption
- The test boundary issue (import ordering) is secondary to the governance question: **should Job have audit columns?**

## Confirmations

- [x] No code changes
- [x] No commit
- [x] No push
- [x] No payment/order business logic touched
- [x] No merge

## Next Step

Awaiting CTO decision: **Option A** (add columns + migration) or **Option B** (test exclusion).
