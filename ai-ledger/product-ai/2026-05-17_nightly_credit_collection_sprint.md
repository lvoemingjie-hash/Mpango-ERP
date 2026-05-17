# Nightly Credit Collection Sprint

## Objective

Run the first bounded Claude Code overnight-style implementation trial for the credit sale collection loop. The goal was to improve operator clarity around outstanding receivables without changing accounting, tenancy, auth, migrations, or backend schema.

## Branch And Base

- Branch: `codex/nightly-credit-collection-2026-05-17`
- Base commit: `c20fa71cc3921137faed047b454e627182f54ee9`
- Source branch: `origin/codex/mvp-sprint-credit-loop-2026-05-15`

## Execution Notes

Claude Code was invoked as the bounded implementation agent. It produced an initial frontend-only change in `FinancePage.tsx` but hit the CTO budget guard before writing the ledger, committing, or running the full validation set.

CTO then reviewed the partial diff, found that the new `?collect=<order_id>` affordance was not consumed by the orders page, and added the minimum `OrderListPage` query handling so the collection CTA opens the existing payment modal instead of becoming a dead link.

## Files Changed

- `frontend/src/pages/finance/FinancePage.tsx`
  - Added clearer aging labels, balance styling, payment progress bars, retry/loading states, overdue emphasis, and row-level collection CTAs.
- `frontend/src/pages/orders/OrderListPage.tsx`
  - Added `collect` query-parameter handling that opens the existing `PaymentRecordModal` for a matching payable order.
- `ai-ledger/product-ai/2026-05-17_nightly_credit_collection_sprint.md`
  - This evidence ledger.

## GitNexus

- CTO impact precheck: `FinancePage` upstream risk LOW, 0 direct callers.
- CTO impact precheck: `PaymentRecordModal` upstream risk LOW, 0 direct callers.
- CTO impact precheck before CTO patch: `OrderListPage` upstream risk LOW, 0 direct callers.
- `financeService` was not directly found as a GitNexus target; no service changes were made.
- `gitnexus detect_changes --scope all` after indexing this worktree: LOW risk, 2 changed code files, 0 affected processes. GitNexus reported changed frontend symbols only in `FinancePage.tsx` and `OrderListPage.tsx`.

## Validation

Initial status before CTO review:

```text
 M frontend/src/pages/finance/FinancePage.tsx
```

Frontend dependency handling:

- The new worktree had no `frontend/node_modules`.
- CTO reused the already-validated sibling worktree dependency tree with a local ignored junction instead of downloading dependencies.

Commands:

```text
cd frontend
pnpm run lint
```

Result: PASS, exit code 0.

```text
cd frontend
pnpm run build
```

Result: PASS, exit code 0. Vite large chunk warning only.

```text
cd backend
REPORTING_USER_PASSWORD=MpangoTest_2026 poetry run pytest tests/test_finance_receivables_api.py tests/test_receivables_service.py -q --tb=short
```

Result: PASS, `38 passed`.

```text
cd backend
REPORTING_USER_PASSWORD=MpangoTest_2026 poetry run pytest tests/test_phase5_order_payment.py -q --tb=short
```

Result: PASS, `53 passed, 1 xfailed`.

Transient validation notes:

- Running backend tests in parallel initially caused a Poetry virtualenv creation race in this new worktree.
- The first payment regression attempt also failed because `REPORTING_USER_PASSWORD` was not set in the shell environment.
- Sequential reruns with the explicit test password passed.

## User Experience Change

- Finance receivable rows now communicate payment progress, outstanding balance, aging severity, and collection priority more directly.
- Overdue rows receive stronger visual treatment and use `Collect Now`.
- The Finance `Collect` action routes to Orders with the target order id.
- The Orders page consumes that query parameter and opens the existing payment modal for a valid payable order.

## Stop Conditions Checked

- No auth, tenancy, search path, migration, backend model, or schema changes.
- No backend product code changes.
- No new dependencies installed.
- No product branch push.
- No merge or rebase.
- No destructive git operations.

## Remaining Risks

- The order list still loads the first 50 orders only; if the target receivable is outside that page, the modal will not auto-open. This is acceptable for the small UX polish slice but should be revisited if collection workflows need direct deep-link reliability.
- The frontend has an existing Vite chunk-size warning.
- This was a mixed Claude/CTO completion because Claude hit the budget guard before final self-verification.

## Verdict

PASS_FOR_CTO_REVIEW
