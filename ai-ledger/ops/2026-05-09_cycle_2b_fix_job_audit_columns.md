# Stabilization Cycle 2B-fix — Job Model Audit Columns

Date: 2026-05-09
Branch: ops/integration-rehearsal-clean-2026-05-08
Worktree: C:\Users\Jeff0\MPANGO ERP\product-dev-recovered-review
Agent: Goose
Status: FIX VERIFIED (revised) — awaiting CTO commit approval

---

## GitNexus Impact Summary

| Symbol | d=1 Callers | Risk |
|--------|-------------|------|
| `Job` | `tests/test_s4_jobs_persistence.py` (1 direct import) | **NONE** — 0 production callers |
| `models.__init__` | All model consumers | **NONE** — additive import only |

No HIGH/CRITICAL risk.

## Files Changed

| File | Change | Lines |
|------|--------|-------|
| `backend/models/job.py` | +13/-2 — added `is_deleted`, `deleted_at` columns + `server_default` on `id` | +13, -2 |
| `backend/models/__init__.py` | +4 — import `Job` + add to `__all__` | +4 |
| `backend/alembic/versions/020_sys_jobs_audit_columns.py` | NEW — Alembic migration | +52 |

**Total**: 3 files modified, 1 new file, ~69 net additions.

## Diff Summary (job.py)

- `import`: Added `Boolean, text` to existing `from sqlalchemy import` (JSON import unchanged from original)
- `id`: Added `server_default=text("gen_random_uuid()")` — aligns with migration 008 actual DB behavior
- New columns: `is_deleted = Column(Boolean, nullable=False, default=False, server_default=text("false"))`
- New columns: `deleted_at = Column(DateTime(timezone=True), nullable=True)`
- payload JSON import/type unchanged from original

## Migration Details

- **Revision ID**: `020_sys_jobs_audit_columns`
- **Revises**: `019_platform_audit_logs`
- **Alembic head**: Single head confirmed
- **Upgrade**:
  1. `ALTER TABLE public.sys_jobs ALTER COLUMN id SET DEFAULT gen_random_uuid()`
  2. `ALTER TABLE public.sys_jobs ADD COLUMN is_deleted BOOLEAN NOT NULL DEFAULT false`
  3. `ALTER TABLE public.sys_jobs ADD COLUMN deleted_at TIMESTAMPTZ` (model uses `DateTime(timezone=True)`)
- **Downgrade**:
  1. `DROP COLUMN deleted_at`
  2. `DROP COLUMN is_deleted`
  3. `ALTER COLUMN id DROP DEFAULT`
- **Verified**: downgrade + upgrade cycle passes cleanly

## Test Results

### Smallest failing group (now fixed)
```
poetry run pytest tests/test_s4_jobs_persistence.py tests/test_models_structure.py -q --tb=short
```
**13 passed, 0 failed** ✅

### Broader platform/model subset
```
poetry run pytest tests/test_models_structure.py tests/test_platform_audit.py tests/test_platform_p0.py tests/test_platform_stats_api.py -q --tb=short
```
**49 passed, 0 failed** ✅

### Alembic checks
```
poetry run alembic heads     → 020_sys_jobs_audit_columns (head) ✅
poetry run alembic upgrade head → OK ✅
```

## Revision Changes (v1 → v2)

| Item | v1 | v2 (current) |
|------|----|----|
| `payload` import | Moved to `sqlalchemy.dialects.postgresql.JSON` | **Kept at `sqlalchemy.JSON`** (no churn) |
| Migration 020 | Only added `is_deleted` + `deleted_at` | Also `ALTER id SET DEFAULT gen_random_uuid()` + downgrade `DROP DEFAULT` |
| Ledger claim | "restored JSON from String" | **Removed** — no actual regression existed |

## Confirmations

- [x] No payment/order/session code touched
- [x] No merge to product-dev-recovered/platform-dev
- [x] No commit
- [x] No push
- [x] `resolve_conflict.py` remains untracked
- [x] No `git reset --hard`
- [x] Alembic single head confirmed
- [x] Migration downgrade/upgrade cycle verified
- [x] `JSON` import unchanged from original (no churn)
