# Sprint M - Payment History Out-of-Range Page Recovery

**Date:** 2026-05-21
**Branch:** `codex/sprint-m-payment-page-recovery-2026-05-21`
**Base commit:** `275bf634ca276928006fbc8ad553cb619bdf0a4d` (`feat(finance): preserve payment history page in url`)
**Status:** NOT PUSHED

## Summary

Improve `/payments?page=N` robustness after Sprint L. If a bookmarked or shared
Payment History URL asks for a page beyond the available result set, the page now
recovers to the last valid page after the API returns pagination metadata.

## Modified Files

| File | Action |
|------|--------|
| `frontend/src/pages/finance/PaymentListPage.tsx` | Modified |
| `ai-ledger/product-ai/2026-05-21_sprint_m_payment_page_recovery.md` | Added |

## Implementation Evidence

1. Kept `/payments?page=N` as the source of truth via Sprint L `useSearchParams`
   behavior.
2. Added a stable `totalPages` display value derived from `total` and `size`,
   falling back to `1` when total is zero.
3. After `paymentService.getAll(page, size)` returns, the page compares the
   requested URL page with backend pagination metadata.
4. If `page > pagination.pages` and `pagination.pages > 0`, the component
   redirects to the last valid page with `setSearchParams(recovered, { replace:
   true })`.
5. User-initiated pagination still uses `setSearchParams(next)` so browser
   history remains useful.
6. If total is zero, no redirect occurs; the genuine empty state remains.

## Counterexample Coverage

| Scenario | Expected Behavior |
|----------|-------------------|
| `/payments` with no records | Shows genuine empty state, no redirect |
| `/payments?page=1` with records | Loads page 1 normally |
| `/payments?page=3` when three pages exist | Loads page 3 normally |
| `/payments?page=999` when three pages exist | Replaces URL with `?page=3` and refetches |
| `/payments?page=999` when one page exists | Replaces URL with `/payments` and refetches page 1 |
| User clicks pagination next/previous | Adds normal history entry, preserving Sprint L behavior |
| Invalid page such as `/payments?page=abc` | Sprint L canonicalization still replaces to page 1 |

## Test Evidence

### Frontend Dependency Reuse

- **Command:** `pnpm --dir frontend install --offline --frozen-lockfile --ignore-workspace --ignore-scripts`
- **Result:** PASS - lockfile already up to date; 394 packages reused from local
  pnpm store; `downloaded 0`; no package or lockfile changes.

### Frontend Lint

- **Command:** `pnpm --dir frontend --ignore-workspace run lint`
- **Result:** PASS - eslint completed with zero warnings.

### Frontend Build

- **Command:** `pnpm --dir frontend --ignore-workspace run build`
- **Result:** PASS - `tsc && vite build`; 1225 modules transformed; built in
  4.46s. Vite emitted the existing chunk-size warning only.

### Backend Payment Regression

- **Command:** `REPORTING_USER_PASSWORD=MpangoTest_2026; cd backend; poetry run pytest tests/test_phase5_order_payment.py -q --tb=short`
- **Result:** PASS - 53 passed, 1 xfailed, 48 warnings in 13.77s.

### Git Checks

- **Command:** `git diff --check`
- **Result:** PASS - no whitespace errors.

## CTO Instruction Compliance

| Requirement | Evidence | Status |
|-------------|----------|--------|
| Keep URL page as source of truth | `page` remains derived from `useSearchParams` | PASS |
| Derive stable `totalPages` with fallback | `Math.ceil(total / size) || 1` | PASS |
| Recover only when total exists and page is too high | `page > pagination.pages && pagination.pages > 0` | PASS |
| Use replace navigation for bad bookmarked page | `setSearchParams(recovered, { replace: true })` | PASS |
| Preserve user pagination history | `changePage` still calls `setSearchParams(next)` | PASS |
| Keep page size and paymentService unchanged | No service/API changes | PASS |
| No backend/API/migration/auth/tenancy/platform changes | Only frontend page + ledger | PASS |
| Do not push | Not pushed during implementation | PASS |

## Risk Classification

**Risk: LOW**

Single frontend component behavior change. It uses existing backend pagination
metadata, does not add API calls beyond the redirect-triggered refetch for an
invalid page, and does not affect payment creation or accounting semantics.

## Commit

Planned commit message:

```text
feat(finance): recover out-of-range payment pages
```

**Not pushed at implementation time.**
