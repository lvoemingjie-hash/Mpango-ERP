# U3-B2: Product Import Preview + Validate API

**Date:** 2026-06-12
**Branch:** `codebuddy/u3b2-import-preview-validate-2026-06-12`
**Base:** `origin/product-dev-recovered` at `fc4fe6b`
**Commit:** `c2b4164` (after rebase)
**Status:** Pending CTO review

## Scope

Implement Phase 1 (preview) and Phase 2 (validate) of the 3-phase SKU bulk
import contract. Phase 3 (apply) is explicitly **not** in scope.

### Declaractions

- **NO apply endpoint** -- reserved for U3-C
- **NO SKU/inventory/pricing writes** -- only `import_runs` table
- **NO frontend** -- backend API only
- **NO deployment** -- branch only
- **NO migration changes** -- uses existing `022_import_runs.py` from U3-B1
- **NO new external dependencies**

## Files Changed (4 files, +993 lines)

| File | Change | Description |
|------|--------|-------------|
| `backend/services/import_service.py` | NEW (406 lines) | CSV parsing, field mapping validation, row-level checks, duplicate detection |
| `backend/api/v1/sku_imports.py` | NEW (239 lines) | `POST /preview` + `POST /{import_id}/validate` endpoints |
| `backend/api/app.py` | MOD (+4 lines) | Register `sku_imports` router at `/api/v1/skus/import` |
| `backend/tests/test_u3b2_preview_validate.py` | NEW (344 lines) | 64 tests covering all contract requirements |

## API Contract

### Phase 1: POST `/api/v1/skus/import/preview`

- **Auth:** `RequirePermission("skus:import")`
- **Input:** CSV file upload (max 10MB)
- **Output:** `import_id`, `columns_detected`, `row_count`, `sample_rows`
- **Side effects:** Creates `import_runs` row (status=previewed)
- **Error codes:** `EMPTY_FILE`, `ENCODING_ERROR`, `FILE_TOO_LARGE`, `INVALID_CONTENT_TYPE`

### Phase 2: POST `/api/v1/skus/import/{import_id}/validate`

- **Auth:** `RequirePermission("skus:import")`
- **Input:** `import_id` + field mapping dict
- **Output:** `status` (validated/needs_review), `valid_rows`, `error_rows`, `errors[]`, `warnings[]`
- **Side effects:** Updates `import_runs` row (status, validation_result JSONB)
- **Error codes:** `IMPORT_NOT_FOUND`, `INVALID_STATUS`, `INVALID_MAPPING`, `MISSING_REQUIRED_FIELDS`

## Validation Rules

| Rule | Level | Details |
|------|-------|---------|
| Required field mapping | Global error | `sku_code` + `name` must be in mapping targets |
| Required field empty | Row error | `sku_code` or `name` is blank |
| sku_code length | Row error | > 64 characters |
| sku_code spaces | Row warning | Contains whitespace |
| name length | Row error | > 255 characters |
| is_active format | Row warning | Non-standard boolean value |
| Intra-file duplicate sku_code | Row error | Same code appears in multiple rows |
| Existing catalog duplicate | Row warning | sku_code already in tenant catalog (READ-only check) |
| Unmapped columns | Row warning | CSV columns not in mapping |

## Error Models

Each error has: `row`, `field`, `sku_code`, `message` (via `ImportErrorDetail` schema).
Each warning has: `row`, `field`, `message` (via `ImportWarningDetail` schema).

## UTF-8-sig BOM Support

Auto-detects Excel-exported CSVs with UTF-8 BOM (`\xef\xbb\xbf`). The `_decode_bytes`
method checks the first 3 bytes and forces `utf-8-sig` decoding when BOM is present.

## Duplicate SKU Detection

1. **Intra-file:** Scans all mapped rows for duplicate `sku_code` values. Reports
   both the current row and the first-seen row number.
2. **Existing catalog:** Router queries `SELECT sku_code FROM skus WHERE is_deleted=false`
   and passes the set to `ImportService.validate()`. Reports as warning (not error)
   since apply phase may use `on_conflict` strategy.

## Test Results

### U3-B2 Tests: 64 passed, 0 failed

```
tests/test_u3b2_preview_validate.py --tb=no -q
64 passed in 0.90s
```

Test classes:
1. `TestRouterRegistration` (3 tests) -- app.py router registration
2. `TestEndpointDefinitions` (6 tests) -- AST endpoint analysis
3. `TestImportServiceStructure` (12 tests) -- service structure + BOM + dup guards
4. `TestCSVParsing` (6 tests) -- CSV parsing including UTF-8-sig BOM
5. `TestFieldMappingValidation` (6 tests) -- mapping validation
6. `TestApplyMapping` (3 tests) -- row transform
7. `TestNoSkuInventoryWrites` (5 tests) -- AST guard against writes
8. `TestU3B2Schemas` (6 tests) -- Pydantic schema serialization
9. `TestRowLevelValidation` (8 tests) -- mock-DB row-level checks
10. `TestDuplicateSKUDetection` (3 tests) -- intra-file + catalog dup
11. `TestErrorModels` (5 tests) -- error codes for bad inputs
12. `TestPermissionEnforcement` (2 tests) -- 403 permission guard

### U3-B1 Regression: 27 passed, 0 failed

All U3-B1 contract tests continue to pass without modification.

## Quality Gates

| Check | Result |
|-------|--------|
| U3-B2 tests | 64/64 passed |
| U3-B1 regression | 27/27 passed |
| `git diff --check` | PASS (clean) |
| mojibake scan | PASS (0 non-ASCII bytes) |
| linter | PASS (0 errors) |
| pre-commit hooks | PASS (trailing whitespace, end-of-file, large files, secrets) |

## GitNexus Status

Index is stale (indexed at `68b9411`, current at `c2b4164`). The new symbols
`ImportService`, `preview_import`, `validate_import` are not yet indexed.
After merge, run `npx gitnexus analyze` to update.

### Change Scope

```
 backend/api/app.py                          |   5 +-
 backend/api/v1/sku_imports.py               | 239 +++++++
 backend/services/import_service.py          | 406 +++++++++++
 backend/tests/test_u3b2_preview_validate.py | 344 ++++++++++
 4 files changed, 993 insertions(+), 1 deletion(-)
```

No changes to: auth, tenancy, payments, orders, migrations, SKU model,
inventory model, pricing model.

## Residual Risks

1. **No DB smoke test yet** -- `022_import_runs.py` migration has not been run
   against a real database. CTO flagged this as blocking deployment but not
   blocking merge.
2. **Preview stores only sample rows** -- Full validation re-reads from
   `mapping.sample_rows` (max 5 rows). Production should store raw bytes in
   object storage and re-parse for full validation.
3. **No concurrent import locking** -- Two validate calls on the same import_id
   could race. Should add optimistic locking or status check in apply phase.
