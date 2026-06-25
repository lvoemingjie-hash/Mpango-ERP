# S5-C-R6A -- import_runs Bootstrap/Reconcile Durable Fix

**Date**: 2026-06-25
**Branch**: `opencode/s5c-r6a-import-runs-bootstrap-reconcile-2026-06-25`
**Verdict**: `PASS_FOR_CTO_REVIEW`
**Lineage**: product-dev-recovered

---

## Problem

S5-C deployed browser smoke gate revealed that existing tenant schemas bootstrapped
before migration 022 was created lack the `import_runs` table. This causes the
U3-B1 3-phase import contract (preview -> validate -> apply) to fail on those
tenants because `ImportService.preview()` tries to INSERT into a non-existent table.

Root cause: `alembic upgrade head -x tenant_schema=t_X` is a no-op when the shared
public `alembic_version` table is already at HEAD. The 022 migration's tenant-side
DDL never executes for existing tenants.

The S5-C diagnostic proved the import API works when `import_runs` exists, confirming
this is purely a schema-availability gap -- not an application code bug.

## Solution

Add `import_runs` DDL and index reconciliation to `backend/scripts/bootstrap_tenant_schema.py`,
the canonical idempotent script that creates/reconciles tenant schemas. This is the
same pattern already used for `payments` (migration 021) and `retailer_prices` (migration 017).

**No raw DDL on production. No new migration.** The bootstrap script is the single
code path -- it handles both fresh tenants (`CREATE TABLE IF NOT EXISTS`) and
existing tenants (`_reconcile_import_runs()`).

### Changes

#### 1. `backend/scripts/bootstrap_tenant_schema.py` -- DDL + reconcile

- **DDL**: Added `import_runs` `CREATE TABLE IF NOT EXISTS` to the `tables` list,
  mirroring migration 022 contract exactly: 22 columns including
  `id`, `import_id` (UNIQUE), `tenant_id`, `status`, `source_filename`,
  `source_encoding`, `total_rows`, `valid_rows`, `error_rows`, `warning_rows`,
  `mapping` (JSONB), `validation_result` (JSONB), `apply_result` (JSONB),
  `created_rows`, `skipped_rows`, `updated_rows`, `applied_by`, `applied_at`,
  `created_at`, `updated_at`, `is_deleted`, `deleted_at`.

- **Reconcile function**: Created `_reconcile_import_runs()`:
  - Checks `_table_exists(db, ts, "import_runs")` -- returns early if table absent
    (CREATE TABLE handles it)
  - Ensures 4 indexes via `_ensure_index()`:
    1. `ix_import_runs_import_id` -- UNIQUE on `(import_id)`
    2. `ix_import_runs_status` -- on `(status)`
    3. `ix_import_runs_tenant_id` -- on `(tenant_id)`
    4. `ix_import_runs_created_at` -- on `(created_at)`
  - `_ensure_index` validates existing index definitions; raises `RuntimeError`
    on incompatible index; skips if index matches exactly
  - Called from `bootstrap()` after `_reconcile_reporting()`

- **Index naming**: Uses migration naming convention (`ix_` prefix), NOT model's
  `ux_import_runs_import_id`. This aligns with the actual DB artifacts created by
  migration 022 and the test expectation in `test_u3b1_contract_foundation.py`.

#### 2. `backend/tests/test_u1r1_bootstrap_completeness.py` -- Tests

- Added `"import_runs"` to `EXPECTED_MVP_TABLES`

- **`TestBootstrapImportRuns`** (new class, 5 tests):
  1. `test_import_runs_table_exists` -- table exists after bootstrap
  2. `test_import_runs_all_columns_present` -- all 22 columns present
  3. `test_import_runs_all_indexes_present` -- all 4 indexes present
  4. `test_import_runs_import_id_unique_index` -- `ix_import_runs_import_id` is UNIQUE
  5. `test_double_bootstrap_import_runs_idempotent` -- second bootstrap preserves indexes

- **`TestBootstrapImportPreviewValidate`** (new class, 2 tests):
  1. `test_preview_creates_row_in_bootstrapped_import_runs` -- preview() against bootstrapped table inserts correctly
  2. `test_validate_updates_bootstrapped_import_runs` -- validate() updates status/valid_rows/error_rows

## Test Results

### Static Contract Tests (PASS)

```
poetry run pytest tests/test_u3b1_contract_foundation.py -q -rxX --tb=short
======================== 27 passed in 0.74s ========================
```

All 27 U3-B1 contract tests pass. This includes `EXPECTED_INDEX_NAMES` validation
that confirms the 4 import_runs indexes use the migration naming convention.

### Live DB Proof: U1-R1 Bootstrap Completeness (PASS)

```
poetry run pytest tests/test_u1r1_bootstrap_completeness.py -q -rxX --tb=short
================= 17 passed, 6 xfailed, 0 failed in 24.17s =================
```

All 7 new import_runs tests pass against a live bootstrapped PostgreSQL tenant.
The 6 xfailed tests are pre-existing platform diagnostics (unchanged from
U1-R2 baseline).

### U3-B2 Live DB Import Preview/Validate (PASS)

```
poetry run pytest tests/test_u3b2_live_db_import_preview_validate.py -q -rxX --tb=short
============================= 14 passed in 5.21s =============================
```

CTO clean merge gate reran this suite with local Docker PostgreSQL connection
environment set from the `mpango_postgres` container. The live DB import
preview/validate path passes.

## Risk Assessment

- **GitNexus impact**: **HIGH** -- `bootstrap()` is the tenant schema lifecycle path.
  Every tenant creation, every Docker entrypoint startup, and every existing
  tenant reconciliation passes through this function. **Risk accepted** because
  all DDL is idempotent and covered by live DB test (see R2 section below).

- **Database safety**: All DDL is idempotent -- `CREATE TABLE IF NOT EXISTS`,
  `CREATE INDEX IF NOT EXISTS`. The `_reconcile_import_runs` function validates
  existing indexes before skipping, raising `RuntimeError` on mismatch.

- **Rollback**: Revert commit. No data loss possible -- tables are created, not
  dropped. If the table was already in use, both bootstrap and reconcile are
  no-ops.

- **Product code impact**: Product code changed in `bootstrap_tenant_schema.py`,
  but it is additive/idempotent tenant schema lifecycle code. The import API
  (`ImportService`) already has correct logic and was not modified.

## Files Changed

| File | Change |
|------|--------|
| `backend/scripts/bootstrap_tenant_schema.py` | R6A: +81 lines (import_runs DDL + _reconcile_import_runs() + call site). R2: 2 ASCII comment fixes |
| `backend/tests/test_u1r1_bootstrap_completeness.py` | R6A: +235 lines (TestBootstrapImportRuns + TestBootstrapImportPreviewValidate + EXPECTED_MVP_TABLES). R2: +15 lines (SET LOCAL search_path fix + _prepare_session helper) |
| `ai-ledger/product-ai/2026-06-25_s5c_r6a_import_runs_bootstrap_reconcile.md` | R6A: initial ledger. R2: added R1/R2 closeout sections |

## Next Steps

1. OPS: Run `python scripts/bootstrap_tenant_schema.py t_prod` (or equivalent)
   in a deployment window against all existing tenant schemas to reconcile
   `import_runs` into existing production tenants.
2. Future tenants will get `import_runs` automatically via `docker-entrypoint.sh`.
3. No deploy, no frontend changes, no product-dev-recovered push required.

## R1 -- CTO Review: SET LOCAL search_path Fix

### CTO Finding

`TestBootstrapImportPreviewValidate.test_validate_updates_bootstrapped_import_runs`
called `ImportService.validate()` after `db.commit()`, which loses the
`SET LOCAL search_path` scope.  Without re-setting search_path, the ORM
cannot resolve `ImportRun` to the tenant schema because `search_path`
reverts to `public`.

### Fix

Before calling `ImportService.validate()` (which uses ORM tables unqualified),
re-apply `SET LOCAL search_path TO "{tenant_schema}", public`.
Also added `_prepare_session()` helper to configure `db.info` with
`tenant_schema` and `tenant_id` so the tenant_filter middleware can
resolve ORM operations.

Changes in `backend/tests/test_u1r1_bootstrap_completeness.py`:
- Added `_prepare_session(db)` static method on `TestBootstrapImportPreviewValidate`
- Added `self._prepare_session(db)` call before preview and validate
- Added `SET LOCAL search_path` re-application after commit, before validate
- Added explanatory comments documenting the search_path lifecycle

### Evidence

```
poetry run pytest tests/test_u1r1_bootstrap_completeness.py -q -rxX --tb=short
================= 17 passed, 6 xfailed, 0 failed in 24.17s =================
```

All 7 new import_runs tests pass:
- TestBootstrapImportRuns: 5/5 PASS (table, columns, indexes, unique, idempotent)
- TestBootstrapImportPreviewValidate: 2/2 PASS (preview inserts, validate updates)

### ASCII Scan

```
rg -n "[non-ASCII chars]" backend/scripts/bootstrap_tenant_schema.py
  -> CLEAN (em-dash and arrow fixed to -- and ->)

rg -n "[non-ASCII chars]" backend/tests/test_u1r1_bootstrap_completeness.py
  -> Pre-existing non-ASCII on OLD lines (em-dash, arrows in docstrings
     written before R6A).  Not changed in this commit.
  -> R6A-added lines are ASCII-clean.
```

## R2 -- GitNexus Impact Reassessment

### bootstrap_tenant_schema.py

- **Symbol**: `bootstrap()` in `backend/scripts/bootstrap_tenant_schema.py`
- **GitNexus impact**: **HIGH** -- this is the tenant schema lifecycle path.
  Every tenant creation, every Docker entrypoint startup, and every existing
  tenant reconciliation passes through this function.
- **Risk accepted** because:
  1. All DDL is idempotent (`CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`)
  2. `_ensure_index()` validates existing index definitions before skipping;
     raises `RuntimeError` on incompatible index (fail-fast, no silent corruption)
  3. `_reconcile_import_runs()` returns early if table absent (CREATE TABLE handles it)
4. Covered by live DB test (`test_u1r1_bootstrap_completeness.py`) that
     proves the full bootstrap -> preview -> validate flow works end-to-end
  5. Covered by live DB U3-B2 import preview/validate regression: 14/14 PASS
  6. Same pattern already proven safe for payments (migration 021) and
     retailer_prices (migration 017) reconciliations
- **No raw DDL on production. No new migration.**  The bootstrap script is the
  single code path for both fresh and existing tenants.

### test_u1r1_bootstrap_completeness.py

- **GitNexus impact**: N/A -- test-only file, no production callers
- New classes `TestBootstrapImportRuns` and `TestBootstrapImportPreviewValidate`
  are test fixtures only

### Verdict

```
PASS_FOR_CTO_REVIEW
```

The CTO finding (SET LOCAL search_path loss after commit) has been fixed.
The GitNexus HIGH impact on bootstrap() is acknowledged and accepted
with documented risk mitigations.  All tests pass with live DB verification.

## Evidence Trail

- S5-C browser smoke: deploy gate passed, import CSV works when table exists
- S5-C-R1: ledger cleanup, verdict corrected
- U3-B1 static contract: 27/27 PASS (this branch)
- U1-R1 bootstrap completeness: 17 passed, 6 xfailed, 0 failed (this branch)
- U3-B2 live DB import preview/validate: 14 passed, 0 failed (CTO clean gate)
- GitNexus impact: HIGH on `bootstrap()` (accepted -- idempotent DDL, live DB tested)
