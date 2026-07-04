# S6-F Intake Wording Residual Sweep

Date: 2026-07-04
Branch: `opencode/s6f-intake-wording-residual-sweep-2026-07-04`
Base: `origin/product-dev-recovered` at `0538e9e3389acead5a6e86dd2b645697bb3e1e71`
Scope: SKU import modal wording and tests only

## Intent

Remove residual SKU Import modal wording that implied full product creation instead of catalog SKU record creation only.

The S6-D truth remains explicit:

- Apply creates catalog SKU records only.
- It does not write inventory.
- It does not create retailer pricing.
- It does not perform barcode lookup.
- It does not create images or custom attributes.
- It does not make SKUs sellable/order-ready by itself.

## Files Changed

- `frontend/src/pages/skus/SKUImportModal.tsx`
- `frontend/src/tests/SKUImportModal.test.tsx`
- `ai-ledger/product-ai/2026-07-04_s6f_intake_wording_residual_sweep.md`

## What Changed

- Renamed the SKU import modal upload title from `Import Products` to `Import Catalog SKUs`.
- Replaced duplicate conflict wording:
- `New products are still created` -> `New catalog SKU records are still created`.
- `No products are created` -> `No catalog SKU records are created`.
- Replaced failed apply wording:
- `No products were created` -> `No catalog SKU records were created`.
- Added modal tests that assert stale SKU import phrases are absent from rendered upload, conflict, and failed apply states.
- Preserved the existing catalog-only warning that apply does not write inventory, pricing, barcode lookup, images, custom attributes, or sellable readiness.

## Scope Discipline

- No backend changes.
- No API changes.
- No migration changes.
- No business logic changes.
- No permission or RBAC changes.
- No deploy or VPS access.
- No push to `product-dev-recovered`.

Out-of-scope note:

- `SKUListPage.tsx` and broader smoke tests still contain `Import Products` button/test labels, but this task only allowed `SKUImportModal.tsx` and targeted SKU import modal tests. The modal runtime file itself has no matches for the stale phrases after this change.

## Validation

- Initial `pnpm exec vitest run src/tests/SKUImportModal.test.tsx src/tests/SKUImportE2E.test.tsx` -> ENV SETUP BLOCKED before dependency install: `Command "vitest" not found` because the fresh worktree had no `node_modules`.
- `pnpm install --frozen-lockfile` -> PASS; lockfile unchanged.
- `pnpm exec vitest run src/tests/SKUImportModal.test.tsx src/tests/SKUImportE2E.test.tsx` -> PASS (`2 passed`, `22 passed`, `7.59s`).
- `pnpm build` -> PASS; Vite emitted existing browserslist/chunk-size warnings.
- `git diff --check` -> PASS, with Git LF/CRLF working-copy warnings only.
- Changed-file ASCII scan -> PASS, no non-ASCII matches.
- Changed-file mojibake scan -> PASS, no matches.
- Changed-file secret keyword scan -> PASS, no matches.
- `pre-commit run --files frontend/src/pages/skus/SKUImportModal.tsx frontend/src/tests/SKUImportModal.test.tsx` -> PASS.
- `npx gitnexus analyze` -> PASS (`6,175 nodes | 17,914 edges | 412 clusters | 227 flows`).
- `npx gitnexus status` -> PASS, indexed commit and current commit both `0538e9e`, status `up-to-date`.

## Risk

Low. This is a copy/test-only frontend modal change. It does not alter API calls, import behavior, permissions, or backend state.

Remaining risk:

- Broader product-era labels outside the allowed S6-F file scope may need a separate wording sweep if product leadership wants all SKU list entry labels changed too.
