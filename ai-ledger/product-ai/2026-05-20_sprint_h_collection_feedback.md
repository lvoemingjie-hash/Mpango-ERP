# 2026-05-20 Sprint H — Collection Completion Feedback

## Scope

Add a small frontend-only reassurance step after the Finance -> Orders -> Finance collection flow.

## CTO Harness Notes

- Worktree: `C:\Users\Jeff0\MPANGO ERP\sprint-h-collection-feedback-2026-05-20`
- Branch: `codex/sprint-h-collection-feedback-2026-05-20`
- Base: `origin/product-dev-recovered@537462f`
- Claude Code was invoked first but timed out without modifying project files.
- CTO implemented the bounded patch directly to keep the sprint moving.

## GitNexus Impact

- `FinancePage`: LOW, 0 direct callers, 0 affected processes.
- `OrderListPage`: LOW, 0 direct callers, 0 affected processes.

## Changes

- `OrderListPage` appends safe transient markers when returning to Finance after a successful collection:
  - `collection=recorded`
  - `collectedOrder=<order id>`
- `FinancePage` preserves valid transient collection markers during URL canonicalization.
- `FinancePage` shows a dismissible success notice after return.
- Dismissal removes only the transient collection notice and preserves Finance tab/page URL state.

## Guardrails

- No backend code changed.
- No tests changed.
- No payment/accounting semantics changed.
- No auth, tenancy, migration, workflow, package, or lockfile changes.
- No push by validation agents.

## Validation

- `git diff --check`: PASS.
- `cd frontend && pnpm install --offline --frozen-lockfile`: PASS, dependency cache reused with 0 downloads.
- `cd frontend && pnpm run lint`: PASS.
- `cd frontend && pnpm run build`: PASS, existing Vite large chunk warning only.
- `cd backend && poetry run pytest tests/test_receivables_service.py tests/test_finance_receivables_api.py -q --tb=short`: 38 passed.
- `cd backend && poetry run pytest tests/test_phase5_order_payment.py -q --tb=short`: first run failed because `REPORTING_USER_PASSWORD` was not set in local shell; no product code failure.
- `cd backend && REPORTING_USER_PASSWORD=MpangoTest_2026 poetry run pytest tests/test_phase5_order_payment.py -q --tb=short`: 53 passed, 1 xfailed.

## Status

Local CTO validation passed. Awaiting GitNexus detect_changes, commit, push, and Leo DB-capable validation.
