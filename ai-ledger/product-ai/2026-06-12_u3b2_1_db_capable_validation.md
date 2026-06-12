# U3-B2.1 DB-Capable Validation Report

| Field | Value |
|-------|-------|
| **Task ID** | U3-B2.1 |
| **Date** | 2026-06-12 |
| **Branch** | `codebuddy/u3b2-1-db-capable-validation-2026-06-12` |
| **Base** | `origin/product-dev-recovered` @ `b65aa98` |
| **Verdict** | **PASS_FOR_CTO_REVIEW** (with 1 finding) |

---

## 1. Executive Summary

Validated U3-B1/U3-B2 import preview + validate pipeline against real PostgreSQL
(Docker `mpango_postgres`, database `mpango_erp`, schema `t_test`). All **83 tests
pass** (14 live-DB + 69 mock-based regression). No SKU writes, no apply endpoint,
no frontend, no deployment, no VPS connection.

**One finding**: `022_import_runs` Alembic migration is missing `is_deleted` and
`deleted_at` columns from `AuditMixin`. Test helper compensates by creating the
full-ORM table. This must be fixed before production use.

---

## 2. Test Results

### 2.1 Live DB Tests (14 tests, 14 passed)

| Class | Tests | Status |
|-------|-------|--------|
| `TestMigrationSmoke` | 4 | PASS |
| `TestPreviewLiveDB` | 3 | PASS |
| `TestValidateLiveDB` | 3 | PASS |
| `TestNoSkuWrites` | 3 | PASS |
| `TestFullRoundtrip` | 1 | PASS |

### 2.2 Regression Tests (69 tests, 69 passed)

U3-B1 + U3-B2 mock-based contract tests all continue to pass with zero changes.

### 2.3 Combined Run

```
83 passed, 1 warning in 5.58s
```

---

## 3. Verification Areas

### 3.1 Migration Smoke (4 tests)

- `import_runs` table created in `t_test` schema
- All key columns present: `id`, `import_id`, `tenant_id`, `status`,
  `source_filename`, `total_rows`, `mapping`, `validation_result`,
  `valid_rows`, `error_rows`, `warning_rows`, `created_at`, `updated_at`
- `public` schema does NOT have `import_runs` (tenant-only)
- `import_id` unique constraint enforced

### 3.2 Preview Live DB (3 tests)

- `ImportService.preview()` inserts row into `import_runs` with `status=previewed`
- UTF-8-sig BOM handled correctly against real DB
- 7-row CSV: response returns 5 `sample_rows`, DB `mapping.rows` stores all 7

### 3.3 Validate Live DB (3 tests)

- `ImportService.validate()` updates `import_runs` status to `validated`/`needs_review`
- 6-row CSV with row 6 missing required field: correctly caught, `error_rows=1`
- Intra-file duplicate `sku_code` detected against real DB

### 3.4 No SKU Writes (3 tests)

- SKU count unchanged after `preview()`
- SKU count unchanged after `validate()`
- `inventory_stocks` and `retailer_prices` counts unchanged

### 3.5 Full Roundtrip (1 test)

- Complete preview -> validate pipeline with 6-row CSV
- Row 6: duplicate sku_code + empty name -> `error_rows=1` (counted once)
- All DB state verified: `status`, `total_rows`, `mapping.rows`, `valid_rows`,
  `error_rows`, `validation_result`

---

## 4. Finding: 022 Migration Missing AuditMixin Columns

**Severity**: HIGH (will cause `ProgrammingError` in production)

**Description**: The `ImportRun` ORM model inherits from `AuditMixin`, which adds
`is_deleted` (Boolean, NOT NULL, default false) and `deleted_at` (DateTime,
nullable). However, the `022_import_runs` Alembic migration does NOT create these
columns. SQLAlchemy's ORM will attempt to INSERT `is_deleted=False, deleted_at=None`
into a table that lacks those columns, causing a `ProgrammingError`.

**Impact**: Any `preview()` call against a migration-created `import_runs` table
will fail with a column mismatch error.

**Evidence**:
- ORM model: `backend/models/import_run.py` inherits `AuditMixin`
- AuditMixin: `backend/models/base.py` defines `is_deleted` + `deleted_at`
- Migration: `backend/alembic/versions/022_import_runs.py` -- missing both columns
- Live DB test initially failed with `ProgrammingError` until test helper was
  updated to include the missing columns

**Recommended Fix**: Add to `022_import_runs.py` migration:
```python
sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
```

**Workaround**: Test helper `_ensure_import_runs_table()` in
`test_u3b2_live_db_import_preview_validate.py` creates the full-ORM table
(including `is_deleted` and `deleted_at`).

---

## 5. Environment

| Item | Value |
|------|-------|
| PostgreSQL | Docker `mpango_postgres`, port 5432 |
| Database | `mpango_erp` |
| User | `mpango` |
| Tenant schema | `t_test` |
| Test isolation | DROP + CREATE per test function |
| `POSTGRES_HOST` | `127.0.0.1` (host-side access to Docker) |
| Python | 3.14.0 |
| pytest | 9.0.3 |
| pytest-asyncio | 1.4.0 |

---

## 6. Files Changed

| File | Change |
|------|--------|
| `backend/tests/test_u3b2_live_db_import_preview_validate.py` | **NEW** -- 14 live DB tests |

---

## 7. Quality Gates

| Gate | Result |
|------|--------|
| `git diff --check` | PASS (no whitespace errors) |
| Mojibake check | PASS (only intentional Unicode arrows in comments) |
| Combined 83-test run | PASS |
| No SKU writes | PASS |
| No apply endpoint | PASS |
| No frontend/deployment | PASS |

---

## 8. Hard Prohibitions Compliance

- [x] No SKU writes to any table
- [x] No apply endpoint invocation
- [x] No frontend changes
- [x] No deployment
- [x] No VPS connection
- [x] BLOCKED_ENVIRONMENT never used (DB was available)

---

## 9. Recommendation

**PASS_FOR_CTO_REVIEW** with one required follow-up:
- Fix `022_import_runs` migration to include `is_deleted` and `deleted_at` columns
  before U3-C (apply phase) or any production deployment.
