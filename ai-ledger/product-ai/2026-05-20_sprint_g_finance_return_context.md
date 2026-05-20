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
- CTO repair changed the design to make the URL the source of truth for `tab` and `page`; this avoids stale local state and supports browser back/forward navigation.

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
- Browser back/forward navigation is handled because `tab` and `page` are derived from `useSearchParams` on every render.
- No frontend unit tests for router query-state behavior were added in this slice.

## Commit

Hash: `2322c58`
Message: `feat(finance): preserve receivables return context`

## CTO Repair - 2026-05-20

### Issue Found

CTO review found that the original local-state + `syncingRef` implementation could skip URL synchronization when changing tabs. It also overstated browser back/forward behavior because React state initializers do not re-run on query-string changes.

### Repair Applied

- Removed local React state for `tab` and `page`
- Derived `tab` and `page` directly from `useSearchParams`
- Added `buildFinanceSearchParams()` to canonicalize URL state
- Updated `changeTab()` and pagination to write validated query params directly
- Kept default URL cleanup (`tab=all`, `page=1` omitted)

### CTO Repair Validation

- `git diff --check`: PASS
- `cd frontend && pnpm install --offline --frozen-lockfile`: PASS
- `cd frontend && pnpm run lint`: PASS
- `cd frontend && pnpm run build`: PASS, with existing Vite large chunk warning
- `cd backend && poetry run pytest tests/test_receivables_service.py tests/test_finance_receivables_api.py -q --tb=short`: 38 passed, 0 failed
- `cd backend && poetry run pytest tests/test_phase5_order_payment.py -q --tb=short`: 53 passed, 1 xfailed, 0 failed

### CTO Repair Commit Plan

Message: `fix(finance): make receivables URL state authoritative`
