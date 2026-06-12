# U3-B2.2 Migration Contract Fix Report

| Field | Value |
|-------|-------|
| **Task ID** | U3-B2.2 |
| **Date** | 2026-06-12 |
| **Branch** | `codebuddy/u3b2-2-import-runs-migration-fix-2026-06-12` |
| **Base** | `origin/product-dev-recovered` @ `b65aa98` |
| **Verdict** | **PASS_FOR_CTO_REVIEW** |

---

## 1. Executive Summary

Fixed the `022_import_runs` Alembic migration to include `is_deleted` and
`deleted_at` columns from `AuditMixin`. Updated U3-B1 contract tests to
verify these columns. Replaced the U3-B2.1 live DB test helper with real
migration execution. All **110 tests pass** (27 U3-B1 + 69 U3-B2 + 14 U3-B2.1).

---

## 2. Changes

### 2.1 `backend/alembic/versions/022_import_runs.py`

Added two columns to `op.create_table("import_runs", ...)`:

```python
sa.Column("is_deleted", sa.Boolean(), nullable=False,
          server_default=sa.text("false")),
sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
```

These match the `AuditMixin` that `ImportRun(Base, AuditMixin)` inherits.

### 2.2 `backend/tests/test_u3b1_contract_foundation.py`

Updated `EXPECTED_COLUMNS` and `EXPECTED_ATTRS` sets to include
`"is_deleted"` and `"deleted_at"`. This ensures the static migration
analysis test catches any future column mismatch.

### 2.3 `backend/tests/test_u3b2_live_db_import_preview_validate.py` (NEW)

14 live DB tests that use the **real 022 migration** via `_run_022_upgrade()`,
not a hand-crafted SQL helper. The helper loads the migration module from
file, patches Alembic's `op` module, and executes `upgrade()` via
SQLAlchemy's `run_sync` (required for asyncpg).

---

## 3. Test Results

### 3.1 Combined Run

```
110 passed, 1 warning in 5.38s
```

| Suite | Tests | Status |
|-------|-------|--------|
| U3-B1 Contract Foundation | 27 | PASS |
| U3-B2 Preview+Validate | 69 | PASS |
| U3-B2.2 Live DB (via real migration) | 14 | PASS |

### 3.2 Live DB Test Details (14 tests)

| Class | Tests | Verified |
|-------|-------|----------|
| `TestMigrationSmoke` | 4 | Real 022 migration creates table with all 22 columns, public has no import_runs |
| `TestPreviewLiveDB` | 3 | INSERT into migration-created table, UTF-8-sig BOM, 7-row sample vs full |
| `TestValidateLiveDB` | 3 | Status update, row 6 error, duplicate detection |
| `TestNoSkuWrites` | 3 | SKU/inventory/pricing counts unchanged |
| `TestFullRoundtrip` | 1 | 6-row CSV: error_rows=1 (duplicate+empty counted once) |

---

## 4. Key Design Decision: Real Migration Execution

The `_run_022_upgrade()` helper:

1. Sets `search_path` to tenant schema (passes migration's `t_*` guard)
2. Loads migration module from file via `importlib.util.spec_from_file_location`
3. Creates Alembic `Operations` with `MigrationContext` on the sync connection
4. Patches `alembic.op` module functions (`create_table`, `create_index`, `get_bind`)
5. Calls `migration_mod.upgrade()` directly
6. Runs via `await session.connection().run_sync(callback)` to bridge
   async/sync gap with asyncpg

This proves the real migration DDL works, not a hand-crafted approximation.

---

## 5. Quality Gates

| Gate | Result |
|------|--------|
| `git diff --check` | PASS (no whitespace errors) |
| UTF-8 encoding check | PASS (all files valid) |
| 110 combined tests | PASS |
| No SKU writes | PASS |
| No apply endpoint | PASS |
| No frontend/deployment | PASS |

---

## 6. Files Changed

| File | Change |
|------|--------|
| `backend/alembic/versions/022_import_runs.py` | +2 columns (`is_deleted`, `deleted_at`) |
| `backend/tests/test_u3b1_contract_foundation.py` | +2 entries in EXPECTED_COLUMNS/EXPECTED_ATTRS |
| `backend/tests/test_u3b2_live_db_import_preview_validate.py` | NEW -- 14 live DB tests via real migration |

---

## 7. Hard Prohibitions Compliance

- [x] No U3-C apply
- [x] No SKU / inventory / pricing writes
- [x] No frontend changes
- [x] No deployment
- [x] No Tencent/India VPS connection
- [x] No new 023 migration (fixed 022 directly)
