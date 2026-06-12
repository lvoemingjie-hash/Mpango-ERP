# U3-B1: Product Import Contract Foundation

**Branch:** `codebuddy/u3b1-product-import-contract-foundation-2026-06-12`
**Base:** `origin/product-dev-recovered`
**Date:** 2026-06-12
**Sprint:** U3-B1 (Contract Foundation — No Endpoints, No CSV, No Frontend)
**Author:** AI Engineer
**Status:** Pending CTO Review

---

## 1. Objective

Land the minimal code foundation for the U3-A-R2 agent-operable import contract without implementing any import business logic. This slice establishes:

- A new `skus:import` permission in the RBAC seed scripts
- An `import_runs` table DDL via Alembic migration
- An `ImportRun` ORM model
- Pydantic contract schemas for the 3-phase import pipeline (preview → validate → apply)

---

## 2. Deliverables

| Deliverable | File | Status |
|-------------|------|--------|
| `skus:import` permission in create_wholesaler.py | `backend/scripts/create_wholesaler.py` | Done |
| `skus:import` permission in seed_demo_data.py | `backend/scripts/seed_demo_data.py` | Done |
| `import_runs` table migration | `backend/alembic/versions/022_import_runs.py` | Done |
| `ImportRun` ORM model | `backend/models/import_run.py` | New |
| Pydantic contract schemas | `backend/schemas/import_schemas.py` | New |
| Test suite (15 unit + 2 integration) | `backend/tests/test_u3b1_contract_foundation.py` | New |

---

## 3. Modified Files

```
M  backend/scripts/create_wholesaler.py          (1 line: added skus:import to permissions_data)
M  backend/scripts/seed_demo_data.py             (1 line: added skus:import to PERMISSION_CODES)
A  backend/alembic/versions/022_import_runs.py    (new: import_runs table DDL)
A  backend/models/import_run.py                   (new: ImportRun ORM model)
A  backend/schemas/import_schemas.py              (new: 3-phase Pydantic contract schemas)
A  backend/tests/test_u3b1_contract_foundation.py (new: 17 tests)
```

---

## 4. Contract Schema Summary

### 4.1 Row-Level Detail Types

| Schema | Purpose |
|--------|---------|
| `ImportErrorDetail` | Row-level error with `row`, `field`, `sku_code`, `message` |
| `ImportWarningDetail` | Row-level warning with `row`, `field`, `message` |

### 4.2 Phase 1: Preview

| Schema | Direction |
|--------|-----------|
| `ImportSourceInfo` | Embedded in response: `filename`, `encoding`, `row_count` |
| `ImportPreviewResponse` | Response: `import_id`, `source`, `columns_detected`, `sample_rows` |

### 4.3 Phase 2: Validate

| Schema | Direction |
|--------|-----------|
| `ImportValidateRequest` | Request: `mapping` (Dict[str, str]) |
| `ImportValidateResponse` | Response: `import_id`, `status`, `valid_rows`, `error_rows`, `warning_rows`, `errors[]`, `warnings[]` |

### 4.4 Phase 3: Apply

| Schema | Direction |
|--------|-----------|
| `ImportApplyRequest` | Request: `on_conflict` (skip / update / error) |
| `ImportApplyResponse` | Response: `import_id`, `status`, `created`, `skipped`, `updated`, `errors[]`, `audit_run_id`, `applied_at`, `applied_by` |

---

## 5. Test Results

```
pytest tests/test_u3b1_contract_foundation.py -v -m "not integration"

15 passed, 2 deselected (integration, requires DB), 14 warnings
```

### Test Coverage

| Test Class | Tests | What It Proves |
|------------|-------|---------------|
| `TestSkusImportPermission` | 3 | `skus:import` in create_wholesaler.py + seed_demo_data.py + admin gets all |
| `TestImportRunsTable` | 2 | DDL applies + all 20 columns exist (integration, requires DB) |
| `TestImportRunModel` | 3 | ORM model has all 20 columns, correct tablename, repr works |
| `TestImportPydanticSchemas` | 7 | All 7 schemas serialize/deserialize correctly |
| `TestNoImportEndpoints` | 1 | No `/import/` routes registered in FastAPI app |

---

## 6. GitNexus Impact Analysis

**Index status:** Stale (indexed 2026-05-06, current commit newer). Impact queries returned empty due to stale index.

**Manual assessment:**
- `permissions_data` in `create_wholesaler.py`: append-only (new tuple). No callers affected. Risk: NONE.
- `PERMISSION_CODES` in `seed_demo_data.py`: append-only (new tuple). `_seed_rbac` iterates all codes. Risk: NONE.
- New files (`import_run.py`, `import_schemas.py`, `022_import_runs.py`): no existing code depends on them. Risk: NONE.
- `test_u3b1_contract_foundation.py`: new test file, no side effects. Risk: NONE.

**Overall risk: NONE.** All changes are additive — no existing symbol signatures were modified.

---

## 7. Confirmations

| Item | Status |
|------|--------|
| No `POST /api/v1/skus/import/*` endpoints | Confirmed (test_no_import_routes_registered PASSED) |
| No CSV parser | Confirmed |
| No apply write logic | Confirmed |
| No frontend changes | Confirmed |
| No deployment | Confirmed |
| No new heavy dependencies | Confirmed (only stdlib + sqlalchemy + pydantic, all existing) |
| `git diff --check` | PASSED (0 whitespace issues) |
| Pre-commit hooks | PASSED (trim trailing whitespace, fix end of files, check large files, detect secrets) |

---

## 8. Next Steps

U3-B2: Backend Preview + Validate (read-only endpoints)
- Implement `POST /api/v1/skus/import/preview` (CSV upload -> import_id + columns + sample)
- Implement `POST /api/v1/skus/import/{import_id}/validate` (mapping -> errors/warnings)
- Add `custom_attributes JSONB` column to `skus` table
- Both endpoints protected by `RequirePermission("skus:import")`

---

## 9. U3-B1-R1 Revision (CTO Review Fixes)

**Date:** 2026-06-12 (same day)
**Trigger:** CTO review identified 4 gaps in the initial U3-B1 delivery.

### 9.1 Issues Found

| # | Issue | Root Cause | Fix |
|---|-------|-----------|-----|
| 1 | `skus:import` only in 2 of 4 seed scripts | Missed `onboard_tenant.py` and `seed_test_tenant.py` | Added to both |
| 2 | `ImportRun` not exported from `models/__init__.py` | Oversight | Added import + `__all__` entry |
| 3 | Tests used hand-written DDL pseudo-validation | Did not actually validate the migration file | Rewrote with AST/static analysis of `022_import_runs.py` |
| 4 | `test_no_import_routes_registered` imported `main` | Could fail on env vars like `REPORTING_USER_PASSWORD` | Changed to static AST check of `backend/api/v1/skus.py` |

### 9.2 Files Changed in R1

```
M  backend/scripts/onboard_tenant.py       (+1 line: skus:import in permissions_data)
M  backend/scripts/seed_test_tenant.py      (+1 line: skus:import in permission_codes)
M  backend/models/__init__.py               (+3 lines: ImportRun import + __all__ entry)
M  backend/tests/test_u3b1_contract_foundation.py  (rewrite: 27 tests, AST-based)
```

### 9.3 Test Results (R1)

```
27 passed in 0.81s
```

| Test Class | Tests | What It Proves |
|------------|-------|---------------|
| `TestSkusImportPermission` | 4 | `skus:import` in ALL 4 scripts (create_wholesaler, seed_demo_data, onboard_tenant, seed_test_tenant) |
| `TestImportRunsMigration` | 10 | Migration file: upgrade/downgrade exist, create_table + 20 columns, 4 indexes, tenant guard, table_exists guard, revision metadata |
| `TestImportRunModel` | 4 | ORM: 20 columns, tablename, repr, exported from `models.__init__` |
| `TestImportPydanticSchemas` | 8 | All schemas serialize/deserialize round-trip |
| `TestNoImportEndpoints` | 1 | Static AST check: no `/import` routes in `skus.py` |

### 9.4 Quality Gates (R1)

| Check | Result |
|-------|--------|
| `git diff --check` | PASS (0 whitespace issues) |
| Mojibake scan (rg) | PASS (0 hits in all new Python files) |
| AST parse check | PASS (all 4 new .py files parse cleanly) |
| Pre-commit hooks | PASS |

### 9.5 Confirmations (unchanged)

- No endpoint added
- No CSV parser added
- No frontend changes
- No deployment
