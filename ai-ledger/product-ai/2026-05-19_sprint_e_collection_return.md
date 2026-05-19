# Sprint E: Collection Return Flow

**Date:** 2026-05-19
**Branch:** `codex/sprint-e-collection-return-2026-05-19`
**Base:** `d906f1a merge: promote sprint d collection notes`

## Objective

Make the Accounts Receivable collection loop feel complete: when a user clicks **Collect** from the receivables table, records payment in the Sales payment modal, and succeeds, the UI returns them to Accounts Receivable instead of leaving them on the Sales page.

## Scope

Frontend-only UX slice:

- `frontend/src/pages/finance/FinancePage.tsx`
- `frontend/src/pages/orders/OrderListPage.tsx`
- `ai-ledger/product-ai/2026-05-19_sprint_e_collection_return.md`

No backend schema, migration, auth, tenancy, package, lockfile, CI, automation, or payment-core files were changed.

## Implementation

- Finance `Collect` links now include `returnTo=finance` alongside the existing `collect=<order_id>` deep link.
- Orders page stores the return path before consuming the query string.
- Payment success keeps the existing global success toast, closes the modal, and:
  - returns to `/finance` when the payment was launched from Accounts Receivable
  - keeps the existing Sales-page reload behavior when the payment was launched directly from Sales

## Validation

CTO validation completed:

```text
cd frontend
pnpm run lint
```

Result: PASS, exit code 0.

```text
cd frontend
pnpm run build
```

Result: PASS, exit code 0. Vite reported the existing large chunk warning only.

```text
cd backend
REPORTING_USER_PASSWORD=MpangoTest_2026 poetry run pytest tests/test_phase5_order_payment.py -q --tb=short
```

Result: PASS, `53 passed, 1 xfailed`.

```text
cd backend
REPORTING_USER_PASSWORD=MpangoTest_2026 poetry run pytest tests/test_receivables_service.py tests/test_finance_receivables_api.py -q --tb=short
```

Result: PASS, `38 passed`.

Environment note:

- The first receivables run collided with a parallel Poetry virtualenv creation in the new worktree and failed before tests ran.
- CTO reran it serially; the test suite then passed.
- Live DB schema contract is deferred to Leo/Lubuntu validation because this Windows environment previously had local PostgreSQL credential mismatch for `mpango`.

## Risks

- Low risk: this changes navigation around an already validated payment flow, not payment calculation or persistence.
- If payment fails, the modal remains open as before; no return navigation occurs.
- Direct Sales-page payment still refreshes Sales as before.

## CTO Compliance Checklist

- [x] Clean isolated worktree used.
- [x] GitNexus impact checked for `FinancePage` and `OrderListPage`; both LOW risk.
- [x] Backend/schema changes intentionally avoided.
- [x] No commit yet.
- [x] No push yet.
- [x] CTO validation completed.
