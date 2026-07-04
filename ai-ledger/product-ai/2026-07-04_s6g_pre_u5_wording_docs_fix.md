# S6-G Pre-U5 Wording and Docs Fix

Date: 2026-07-04
Branch: codex/s6g-pre-u5-wording-docs-fix
Verdict: PASS_FOR_CTO_REVIEW

## Trigger

Independent pre-U5 audit returned NEEDS_FIX_BEFORE_U5 with two P1 findings:

- Products UI still used stale import wording and implied sellable readiness.
- S5-B smoke test still asserted stale import modal wording.

The same audit also found active payment docs that still described the disabled legacy
`POST /api/v1/payments` write path as active.

## Changes

- Updated Products page import action wording to "Import Catalog SKUs".
- Updated empty-state copy to state that catalog SKUs still require stock and retailer pricing before selling.
- Updated S5-B and SKU list tests to assert catalog-only wording.
- Updated active RBAC/API/domain docs to show canonical payment writes through
  `POST /api/v1/orders/{order_id}/pay`.
- Documented that legacy `POST /api/v1/payments` is disabled with
  `PAYMENT_WRITE_PATH_DISABLED`.

## Scope

Changed files:

- `frontend/src/pages/skus/SKUListPage.tsx`
- `frontend/src/tests/S5BRealUserSmoke.test.tsx`
- `frontend/src/tests/SKUListPage.test.tsx`
- `docs/RBAC_MATRIX_v0.2.0.md`
- `docs/contracts/api_contract.md`
- `docs/contracts/domain_workflows.md`

No backend runtime logic, API implementation, migration, RBAC middleware, payment service,
deployment, or VPS action was changed.

## Validation

- GitNexus pre-edit impact:
  - `SKUListPage`: LOW
  - `SKUImportModal`: LOW
- GitNexus detect_changes after edit: MEDIUM, one affected frontend process
  (`SKUListPage -> IsAdmin`), expected for wording/test changes.
- Frontend targeted tests:
  - `SKUListPage.test.tsx`
  - `S5BRealUserSmoke.test.tsx`
  - `SKUImportModal.test.tsx`
  - `SKUImportE2E.test.tsx`
  - Result: 31 passed
- Frontend build: PASS, with existing Browserslist/chunk-size warnings only.
- `git diff --check`: PASS, with line-ending warnings only.
- Stale active wording grep: PASS except intentional stale phrase guard list in
  `SKUImportModal.test.tsx`.
- Secret keyword scan: documentation-only JWT terms, no secret values.

## Result

The P1 pre-U5 blockers are resolved. U5 may proceed after CTO merge/review and any
desired third-party re-audit.
