# U4-E Data Intake Frontend MVP Entry

**Date**: 2026-07-01
**Branch**: `opencode/u4e-data-intake-frontend-entry-2026-07-01`
**Base**: `origin/product-dev-recovered` at `5ca1472`
**Executor**: OpenCode GPT-5.5
**Verdict**: `PASS_FOR_CTO_U4E_REVIEW`

## Scope

U4-E adds the first tenant-user frontend entry for the U4-D intake staging backend.

Implemented UI flow:

- Products/SKUs page entry to Data Intake.
- Create intake workspace.
- Upload `.csv` or `.xlsx` file.
- Show parser result: filename, row count, column count, headers.
- Map source headers to staging fields:
  `sku_code`, `name`, `unit`, `category`, `unit_price`, `barcode`.
- Save mapping.
- Validate staging rows.
- Show validation summary: `row_count`, `error_count`, `warning_count`, workspace status.
- Show rows preview and validation issues list.
- Show readable issue copy for invalid unit price, missing SKU/name, duplicate staged SKU, and unmapped extra column.
- Clearly labels the page as MVP staging preview that does not create official SKUs and has no apply button.

## Files Changed

- `frontend/src/pages/skus/DataIntakePage.tsx`
- `frontend/src/pages/skus/SKUListPage.tsx`
- `frontend/src/router/AppRouter.tsx`
- `frontend/src/services/intakeService.ts`
- `frontend/src/tests/DataIntakePage.test.tsx`
- `frontend/src/utils/permissions.ts`
- `ai-ledger/product-ai/2026-07-01_u4e_data_intake_frontend_entry.md`

## Boundaries Preserved

- No backend runtime code changes.
- No migrations.
- No deployment changes.
- No SKU write/apply UI.
- No U3 import apply call.
- No public-link flow.
- No image, barcode scanning, PWA, or mobile scan implementation.

## Validation

Targeted frontend tests:

```text
pnpm exec vitest run src/tests/DataIntakePage.test.tsx
5 passed

pnpm exec vitest run SKUListPage
8 passed
```

Build:

```text
pnpm build
PASS
```

Build warnings:

- Browserslist data is stale.
- Main JS chunk is larger than 500 kB after minification.

Additional checks:

```text
git diff --check
PASS

Changed-file mojibake/non-ASCII scan
PASS

Changed-file credential scan
PASS

npx gitnexus analyze
Repository indexed successfully
```

## Test Coverage

U4-E tests cover:

- Mock API happy path: create workspace -> upload -> mapping -> validate -> rows/issues.
- Friendly 403 permission message.
- Friendly upload parse error message.
- `INVALID_UNIT_PRICE` issue display.
- No `apply` or import-to-SKU button exists.

Existing SKU page tests still pass.

## Screenshots

No browser screenshot was captured in this session. The feature was verified through Vitest DOM assertions and production build.

## Risks

- The UI is a minimal staging preview and does not include workspace listing/reopen behavior.
- The page intentionally does not expose any SKU apply action; export/import-to-ERP remains future scope.
- Large existing bundle warning remains unrelated to U4-E and was not addressed in this slice.

## R1 Validate Sequencing Fix

Finding:

- `DataIntakePage.handleValidate()` previously called `validate`, `listRows`, and `listIssues` in one `Promise.all`.
- That allowed rows/issues to be fetched before backend validation had finished writing fresh issue rows.

Fix:

- `handleValidate()` now awaits `intakeService.validate(workspace_id)` first.
- After validate resolves successfully, rows and issues are fetched concurrently with `Promise.all([listRows, listIssues])`.
- `setValidation` uses the validate response, and rows/issues are populated only from post-validation reads.

R1 test evidence:

```text
pnpm exec vitest run src/tests/DataIntakePage.test.tsx
6 passed

pnpm exec vitest run SKUListPage
8 passed
```

R1 additional checks:

```text
pnpm build
PASS with existing Browserslist and chunk-size warnings

git diff --check
PASS

Changed-file mojibake/non-ASCII scan
PASS

Changed-file credential scan
PASS

npx gitnexus analyze
Repository indexed successfully
```
