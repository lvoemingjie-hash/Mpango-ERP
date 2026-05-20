# Sprint G: Preserve Finance Return Context

**Date:** 2026-05-20
**Branch:** `codex/sprint-g-finance-return-context-2026-05-20`
**Base commit:** `a5db3e10620ee9914c1c04551965736a08a5d399` (origin/product-dev-recovered)

## Objective

Preserve Accounts Receivable tab/page context when navigating to order collection and returning from it. The user should land back on the same tab and page they were viewing before clicking Collect.

## Files Changed

| File | Change |
|------|--------|
| `frontend/src/pages/finance/FinancePage.tsx` | Added URL query param sync for tab/page; extended `goToCollect` to include `financeTab`/`financePage` context |
| `frontend/src/pages/orders/OrderListPage.tsx` | Extended `returnTo=finance` path to build validated `/finance?tab=...&page=...` return URL |

## Safety / Risk Notes

- **FinancePage**: LOW risk per CTO impact analysis (0 direct callers, 0 affected processes).
- **OrderListPage**: LOW risk per CTO impact analysis (0 direct callers, 0 affected processes).
- No backend changes. No payment/accounting/ledger semantics altered.
- Return path is hardcoded to `/finance` — no open redirect.
- `financeTab` validated against allowlist (`all`, `credit_receivable`, `unpaid_order`).
- `financePage` validated as positive integer.
- Default values (`tab=all`, `page=1`) are omitted from URLs to avoid noisy query strings.
- `syncingRef` prevents infinite React render loops when `changeTab` calls both `setTab` and `setPage`.

## Commands Run

### 1. `git status --short`
```
 M frontend/src/pages/finance/FinancePage.tsx
 M frontend/src/pages/orders/OrderListPage.tsx
```

### 2. `git diff --check`
No output (no whitespace errors).

### 3. `cd frontend && pnpm install --offline --frozen-lockfile && pnpm run lint && pnpm run build`

**pnpm install:** Done in 12.7s, lockfile up to date, 394 packages.
**pnpm run lint:** No errors, no warnings.
**pnpm run build:** TypeScript compilation succeeded. Vite build produced 3 assets (33.30 kB CSS, 520.04 kB JS). Build completed in 4.98s.

### 4. `cd backend && poetry run pytest tests/test_receivables_service.py tests/test_finance_receivables_api.py -q --tb=short`

```
38 passed, 88 warnings in 1.15s
```

### 5. `cd backend && poetry run pytest tests/test_phase5_order_payment.py -q --tb=short`

```
53 passed, 1 xfailed, 48 warnings in 14.47s
```

## Known Gaps

- No frontend unit tests for the URL sync behavior (no existing test infrastructure for FinancePage).
- Browser back/forward navigation is handled by React Router's `useSearchParams` re-reading from the URL on popstate, which naturally updates the state initializers on remount.
- The `syncingRef` pattern is a lightweight approach; a more robust solution would use `useSyncExternalStore` or a router-first state model, but that is out of scope for this slice.

## Commit

Message: `feat(finance): preserve receivables return context`
