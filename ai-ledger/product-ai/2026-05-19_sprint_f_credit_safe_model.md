# Sprint F: Credit-Safe Collection Usability and Evidence Closeout

**Branch:** `codex/sprint-f-credit-safe-model-2026-05-19`
**Base commit:** `911c72a655f2a4d36b909c39e487ce85d4b0f8ca`
**Date:** 2026-05-19
**Agent:** Claude Code (bounded product-line implementation agent)

## Objective

Improve the credit-sale / receivables / repayment loop by making the credit sale option in the payment modal harder to misuse. The backend credit semantics are already solid (full-credit-only, no split tender, positive balance delta, duplicate prevention, credit ledger skip). The gap is purely frontend UX.

## Recon Findings

### Backend Credit Semantics (already validated, no changes needed)

- `pay_order()` enforces full-credit-only (`CREDIT_AMOUNT_MISMATCH` if amount != total)
- Split tender rejected (`CREDIT_SPLIT_TENDER_UNSUPPORTED` if prior payments exist)
- Duplicate credit rejected (`DUPLICATE_CREDIT_PAYMENT`, 409)
- Credit creates positive outstanding balance delta (+amount)
- Credit payments excluded from `get_order_paid_total`
- Credit PAID orders skip cash-settlement ledger entries
- 33+ tests cover credit semantics in `test_phase5_order_payment.py`

### Frontend Current State

- `PaymentRecordModal.tsx` has 4 methods including "Credit Sale"
- Credit validation exists in `handleSubmit` (lines 50-58) but AFTER the user has already filled in fields
- No auto-fill: user must manually type the exact order total when selecting credit
- No credit info banner: no visual guidance that credit creates a receivable, not cash received
- Amount field is editable for credit: user can type wrong amount and get error
- The green "Full payment" banner appears for credit, which is misleading (credit is NOT cash received)

### Identified Improvement

**Make the credit sale flow self-guiding in the payment modal:**

1. Auto-fill amount with `orderTotal` when "Credit Sale" is selected
2. Make the amount field read-only for credit (must be full total, enforced by backend anyway)
3. Add a credit info banner explaining the receivable implications
4. Replace the generic "Full payment" banner with a credit-specific confirmation for credit method

## Plan

**Loop 1 (this implementation):** Edit `PaymentRecordModal.tsx` only.

- When method changes to "credit", set amount to `orderTotal` as string
- When method changes away from "credit", clear amount
- Make amount input read-only when method is "credit"
- Add a blue credit info banner when credit is selected
- Show credit-specific confirmation banner instead of generic "Full payment" banner

**Risk:** LOW. Changes are purely local to PaymentRecordModal.tsx, no new props, no backend changes, no API changes. CTO impact notes already cleared this symbol (0 direct callers, 0 affected processes).

## Checkpoint 1 — Recon Complete

- Branch: `codex/sprint-f-credit-safe-model-2026-05-19`
- Base: `911c72a`
- Files changed: (none yet)
- Next: implement PaymentRecordModal.tsx improvements

## Checkpoint 2 — Implementation Complete

### Files Changed

1. `frontend/src/components/ui/PaymentRecordModal.tsx` — 3 edits:
   - Method select `onChange`: auto-fill amount to `orderTotal` when "Credit Sale" selected, clear when switching away
   - Amount input: `readOnly` + grey background when method is credit, updated placeholder
   - Banners: credit-specific blue info banner replaces generic green "Full payment" banner for credit method

2. `ai-ledger/product-ai/2026-05-19_sprint_f_credit_safe_model.md` — this ledger

### Why This Slice Is Safe

- Purely local UI changes within one component
- No new props, no interface changes, no API changes
- No backend production code touched
- Component already had backend-level validation guards (which remain unchanged)
- CTO impact notes: PaymentRecordModal LOW risk, 0 direct callers, 0 affected processes

### Validation Evidence

**git status:**
```
 M frontend/src/components/ui/PaymentRecordModal.tsx
?? ai-ledger/product-ai/2026-05-19_sprint_f_credit_safe_model.md
```

**git diff --check:** clean (no whitespace errors)

**Frontend lint + build:**
```
pnpm run lint — passed (0 warnings)
pnpm run build — passed (1225 modules, built in 3.95s)
```

**Backend test_phase5_order_payment.py:**
```
53 passed, 1 xfailed, 0 failed
```

**Backend test_receivables_service.py + test_finance_receivables_api.py:**
```
38 passed, 0 failed
```

### Risk Classification

**LOW** — single frontend component, no backend changes, all existing guards preserved, all tests pass.

### Known Gaps

- Credit Sale option still appears for partially-paid orders (the `isValid` guard prevents submission, but the option is visible). Removing it from the dropdown would require conditional rendering based on `remainingAmount !== orderTotal`, which is a safe follow-up but not strictly necessary since validation catches it.
- No frontend unit tests exist for PaymentRecordModal (no test file to add to). If CTO wants test coverage, a `PaymentRecordModal.test.tsx` would need to be created.

### Commit

Will commit with message: `feat(finance): improve credit-safe collection flow`
