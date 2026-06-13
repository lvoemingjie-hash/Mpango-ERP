# U3-D: Product Import UX Entry Point -- Status Report

> **Task ID**: U3-D
> **Date**: 2026-06-12 -> 2026-06-13
> **Branch**: `codebuddy/u3d-product-import-ux-entry-2026-06-12`
> **Base**: `origin/product-dev-recovered` (merge commit a6f2ade, includes U3-C)
> **Scope**: Frontend-only. No backend changes, no migrations, no deploy.

---

## Executive Summary

U3-D adds a **Product Batch Import** entry point on the Products/SKUs page.
Users can upload CSV, preview columns, map fields, validate, and apply --
completing the full `preview -> validate -> apply` frontend loop.

Permission gate: Import button visible only when user has `skus:import`
permission OR `admin` role.

## Check Results

| Check | Result |
|-------|--------|
| `tsc --noEmit` | PASS (0 errors) |
| `vitest run` | 16/16 passed (2 test files, 6.58s) |
| `vite build` | PASS (production bundle OK) |
| ASCII clean | All 10 U3-D files verified 0 non-ASCII bytes |
| Backend regression | No backend files modified; prior 128/128 still valid |

---

## What Was Built

### New Files (6)

| File | Purpose |
|------|---------|
| `frontend/src/types/import.ts` | TypeScript types mirroring backend `import_schemas.py` + field constants |
| `frontend/src/services/skuImportService.ts` | API client: `preview()`, `validate()`, `apply()` -- uses existing `api` singleton |
| `frontend/src/pages/skus/SKUImportModal.tsx` | 4-step wizard modal (Upload -> Map -> Validate -> Apply) |
| `frontend/src/tests/setup.ts` | vitest setup: jest-dom import + ResizeObserver polyfill for jsdom |
| `frontend/src/tests/SKUImportModal.test.tsx` | 12 tests covering all 7 CTO-required scenarios + extras |
| `frontend/src/tests/SKUListPage.test.tsx` | 4 tests for Import button permission gate |
| `frontend/vitest.config.ts` | vitest configuration (jsdom, path alias, setup file) |

### Modified Files (1 + config)

| File | Change |
|------|--------|
| `frontend/src/pages/skus/SKUListPage.tsx` | Activated "Import Products" button with `skus:import`/`admin` permission gate, added `SKUImportModal` |
| `frontend/package.json` | Added `jsdom`, `@testing-library/user-event` devDependencies (see New Dependencies below) |
| `frontend/pnpm-lock.yaml` | Lock file updated; safety comment header preserved |

---

## Permission Model

- **Import button visibility**: `skus:import` permission OR `admin` role
- **403 handling in modal**: Shows "lacks product import permission" with guidance to get `skus:import` or admin role
- **Backend enforcement**: `RequirePermission("skus:import")` on all three endpoints (preview, validate, apply)
- **Admin bypass**: Backend `super_admin` role bypasses all permission checks; frontend checks `admin` role

---

## New Dependencies -- CTO Approval Requested

Two devDependencies were added to support the vitest test suite:

| Package | Version | Justification |
|---------|---------|---------------|
| `jsdom` | ^23.0.0 | Required by vitest `environment: 'jsdom'` for DOM API simulation |
| `@testing-library/user-event` | ^14.5.1 | Standard `@testing-library` companion for realistic user interaction simulation |

Both are test-only (devDependencies). `vitest`, `@testing-library/react`, and
`@testing-library/jest-dom` were already present in `package.json`.

If CTO prefers, these can be removed by eliminating the test files
(`SKUImportModal.test.tsx`, `SKUListPage.test.tsx`, `setup.ts`, `vitest.config.ts`)
and the `vitest` dependency entirely.

---

## Feature Details

### 4-Step Import Wizard

1. **Upload** -- CSV file selection with validation (CSV-only, max 10MB).
   Shows amber notice: "does NOT import inventory, pricing, images, barcodes,
   or custom attributes."

2. **Map Columns** -- Auto-mapping heuristic matches CSV column names to
   canonical fields (`sku_code`, `name`, `description`, `unit`, `category`,
   `is_active`). Unsupported columns (price, stock, etc.) shown with red
   "Not supported" labels. Manual re-mapping via dropdowns.

3. **Validate** -- Shows valid/error/warning row counts. Lists up to 20
   errors with row number, field, and message. Apply button **blocked** when
   `error_rows > 0`.

4. **Apply** -- Conflict strategy choice (skip/fail). Shows final results:
   created, skipped, updated counts. On success: toast + SKU list refresh.

### Field Constants

| Category | Fields |
|----------|--------|
| Required | `sku_code`, `name` |
| Optional | `description`, `unit`, `category`, `is_active` |
| Unsupported | `stock`, `price`, `image`, `barcode`, `custom_attributes` |

---

## Test Coverage

### SKUImportModal (12 tests)

| # | Test |
|---|------|
| 1 | Renders upload step with file input when open |
| 2 | Does not render when closed |
| 3 | Advances to mapping after successful preview |
| 4 | Advances to validate step with no errors |
| 5 | Shows errors and blocks apply when error_rows > 0 |
| 6 | Calls onSuccess after successful apply |
| 7 | Shows permission error on 403 (mentions admin role) |
| 8 | Marks unsupported columns (price, stock) as not supported |
| 9 | Rejects non-CSV files with clear error |
| 10 | Required fields (sku_code, name) in mappable fields |
| 11 | Unsupported fields excluded from mappable fields |
| 12 | Unsupported fields list completeness check |

### SKUListPage Permission Gate (4 tests)

| # | Test |
|---|------|
| 1 | Import button visible with `skus:import` permission |
| 2 | Import button visible with `admin` role (no `skus:import`) |
| 3 | Import button hidden when user lacks `skus:import` and is not admin |
| 4 | Import button hidden for unauthenticated user |

---

## Scope Compliance

- No backend code modified
- No database migrations
- No deploy scripts
- No Excel/barcode/image support added
- No inventory or pricing import

---

## Files to Commit (U3-D only)

```
M  frontend/package.json
M  frontend/pnpm-lock.yaml
M  frontend/src/pages/skus/SKUListPage.tsx
A  frontend/src/types/import.ts
A  frontend/src/services/skuImportService.ts
A  frontend/src/pages/skus/SKUImportModal.tsx
A  frontend/src/tests/setup.ts
A  frontend/src/tests/SKUImportModal.test.tsx
A  frontend/src/tests/SKUListPage.test.tsx
A  frontend/vitest.config.ts
A  ai-ledger/product-ai/2026-06-12_u3d_product_import_ux_entry.md
```

---

*Report updated: 2026-06-13 (REQUEST_CHANGES fix round)*
