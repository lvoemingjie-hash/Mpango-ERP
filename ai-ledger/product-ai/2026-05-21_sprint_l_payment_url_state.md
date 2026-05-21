# Sprint L - Payment History URL Page State

**Date:** 2026-05-21
**Branch:** codex/sprint-l-payment-url-state-2026-05-21
**Base commit:** 482d341 (feat(finance): polish payment history context)
**Status:** NOT PUSHED

---

## Summary

Make the wholesaler Payment History page (`/payments`) preserve its current page
in the URL query string (`/payments?page=N`), matching the pattern already used
by the Finance receivables page.

## Modified Files

| File | Action |
|------|--------|
| `frontend/src/pages/finance/PaymentListPage.tsx` | Modified |
| `ai-ledger/product-ai/2026-05-21_sprint_l_payment_url_state.md` | Added |

## Implementation Details

1. **`useSearchParams` from react-router-dom** replaces local `useState(1)` for
   page state. The URL query string is now the single source of truth.

2. **`parsePage` helper** - module-level pure function:
   - `null` / missing -> 1
   - Non-integer or non-positive -> 1
   - Valid positive integer -> that value

3. **Canonicalization effect** - strips noisy/invalid params via `replace`
   navigation. If URL has `?page=abc` or `?foo=bar`, it is cleaned to the
   canonical form (no params for page 1, `?page=N` otherwise) without extra
   history entries.

4. **`changePage` handler** - builds canonical `URLSearchParams` and calls
   `setSearchParams(next)`. This is wired to the `Pagination` component's
   `onPageChange` prop instead of the old `setPage`, preserving browser history
   for user-initiated page changes.

5. **Preserved behavior:**
   - Refresh button still calls `load` directly (no URL change).
   - Sprint K context bar (page X of Y, record count, totals, status badges)
     reads from the same `page` derived from URL.
   - Page size remains 20. No new API calls. `paymentService` untouched.

## Counterexample Coverage

| Scenario | Expected Behavior |
|----------|-------------------|
| `/payments` | page=1, no query string |
| `/payments?page=3` | page=3 |
| `/payments?page=0` | canonicalized to page=1 |
| `/payments?page=-5` | canonicalized to page=1 |
| `/payments?page=abc` | canonicalized to page=1 |
| `/payments?page=2.5` | canonicalized to page=1 |
| `/payments?page=3&foo=bar` | canonicalized to `?page=3` |
| Navigate to page 2, then Refresh | stays on page 2, data reloads |
| Browser back after paginating | returns to previous page |

## Test Evidence

### Frontend TypeScript check
- **Command:** `pnpm --dir frontend run build`
- **Preparation:** `pnpm --dir frontend install --offline --frozen-lockfile`
  reused the local pnpm store (`downloaded 0`) and did not modify package files.
- **Result:** PASS - `tsc && vite build`, 1225 modules transformed, built in
  4.95s. Vite emitted the existing chunk-size warning only.

### Frontend lint
- **Command:** `pnpm --dir frontend run lint`
- **Result:** PASS - eslint completed with zero warnings.

### Backend payment regression
- **Command:** `REPORTING_USER_PASSWORD=MpangoTest_2026; cd backend; poetry run pytest tests/test_phase5_order_payment.py -q --tb=short`
- **Result:** PASS - 53 passed, 1 xfailed, 48 warnings in 13.84s.

### Git checks
- `git status --short` before edits: clean worktree
- `git diff --check` after edits: no whitespace errors

## CTO Instruction Compliance

| Requirement | Status |
|-------------|--------|
| Use `useSearchParams` from react-router-dom | Done |
| Parse/canonicalize helper for invalid/missing page | Done (`parsePage`) |
| `onPageChange` updates URL, not local state | Done (`changePage`) |
| Preserve Refresh behavior | Preserved |
| Preserve Sprint K context bar | Preserved |
| No new API calls or paymentService changes | None |
| Page size stays 20 | Unchanged |
| No backend/API/migration/auth/tenancy/platform changes | None |
| No package.json or lockfile changes | None |
| No package/lockfile mutation | Confirmed |
| ASCII-safe text only | Confirmed |
| Do not push | Confirmed - not pushed |

## Validation Gaps

No validation gaps remain for this bounded frontend slice. Frontend dependencies
were restored from the local pnpm store in offline/frozen mode for validation
only; no package file or lockfile was modified.

## Risk Classification

**Risk: LOW**

- Single-file change, ~30 lines of diff.
- Follows established pattern from `FinancePage.tsx` (receivables).
- No API, routing, or state management library changes.
- Pure UI state management: local `useState` replaced with URL-derived value.
- Backward-compatible: `/payments` without query string still works as page 1.

## Commit

```
feat(finance): preserve payment history page in url
```

**Not pushed.**
