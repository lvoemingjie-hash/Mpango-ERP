# S6-D Data Intake Catalog-Only Wording Gate

Date: 2026-07-03
Branch: `kilo/s6-d-data-intake-catalog-only-wording-gate-2026-07-03`
Base: `origin/product-dev-recovered` at `61a6a53`
Scope: frontend UI wording, frontend tests, MVP limitation docs, closeout wording alignment

## Intent

Align the Data Intake user-facing truth with the actual MVP behavior:

- Apply creates catalog SKU records only.
- Apply does not initialize inventory.
- Apply does not create retailer-specific prices.
- Apply does not create image assets, barcode lookup automation, custom attributes, or sellable order readiness.
- Orders still require an active SKU, stock, and retailer price.

## Files Changed

- `frontend/src/pages/skus/DataIntakePage.tsx`
- `frontend/src/pages/skus/SKUImportModal.tsx`
- `frontend/src/tests/DataIntakePage.test.tsx`
- `frontend/src/tests/SKUImportModal.test.tsx`
- `frontend/src/tests/SKUImportE2E.test.tsx`
- `docs/MVP_LIMITATIONS.md`
- `ai-ledger/product-ai/2026-07-03_u4l_data_intake_final_closeout.md`

## What Changed

- Replaced misleading Data Intake apply labels with catalog-focused wording.
- Strengthened confirmation copy to explicitly block false assumptions about stock, pricing, barcode lookup, images, custom attributes, and order readiness.
- Added success-state next steps telling users to adjust stock and retailer prices before creating orders.
- Added `DataIntakePage` test coverage for the catalog-only warning gate.
- Added MVP limitation documentation for the current Data Intake boundary.

## Validation

- `pnpm exec vitest run src/tests/DataIntakePage.test.tsx src/tests/SKUImportModal.test.tsx src/tests/SKUImportE2E.test.tsx` -> PASS (`36 passed`)
- `pnpm build` -> PASS
- `git diff --check` -> PASS
- `rg --line-number "[^\x00-\x7F]" <changed files>` -> REPORT_ONLY; hit pre-existing Unicode punctuation in `docs/MVP_LIMITATIONS.md`, no mojibake introduced
- `rg --line-number --ignore-case "(api[_-]?key|secret|token|password|passwd|jwt|private[_-]?key)" <changed files>` -> REPORT_ONLY; only test fixtures `test-token` and `test-refresh` in `frontend/src/tests/DataIntakePage.test.tsx`
- pre-commit hook on commit -> PASS (`trim trailing whitespace`, `fix end of files`, `check for added large files`, `Detect secrets`)

## GitNexus

- `npx gitnexus analyze` before commit -> PASS (`Already up to date`)
- `npx gitnexus status` before commit -> PASS (`up-to-date`)
- `npx gitnexus analyze` after commit -> PASS (`Repository indexed successfully`)
- `npx gitnexus status` after commit -> REPORT_ONLY; still reported stale with `Indexed commit: 50f7925`, `Current commit: 4c14dc8` despite successful analyze

## Push Confirmation

- Branch pushed: `origin/kilo/s6-d-data-intake-catalog-only-wording-gate-2026-07-03`
- Push command result: PASS
- PR URL offered by remote: `https://github.com/lvoemingjie-hash/Mpango-ERP/pull/new/kilo/s6-d-data-intake-catalog-only-wording-gate-2026-07-03`

## Risk

Low. No backend, migration, order, payment, inventory, or RBAC logic changed.

Remaining risk:

- untouched screens or docs elsewhere may still need a later wording audit for catalog-only truth alignment

## Out Of Scope

- No business logic changes
- No API changes
- No migration changes
- No deploy
- No `product-dev-recovered` push
