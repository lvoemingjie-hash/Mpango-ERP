# Phase 6 — MVP Credit Payment Implementation Ledger

**Date:** 2026-05-06 (revised 2026-05-07)
**Author:** CodeBuddy (Product AI)
**Branch:** product-dev-recovered
**Status:** COMPLETE — CTO-corrected x2, ready for review

---

## Summary

Implemented the approved CTO Model A credit payment semantics as the minimum viable
credit-payment slice. After two CTO corrections:

1. **Correction 1:** Credit closes the order lifecycle (PAID) without inflating `paid_total`.
2. **Correction 2:** Phase 6 MVP supports full-credit sale only — no partial credit, no split tender.

## Approved Semantics (Model A — Payment-Centric, CTO-Corrected)

| Concept | Rule |
|---------|------|
| `outstanding_balance` | Payment-facing cache of net receivable. Positive = retailer owes. |
| Cash/Transfer delta | `-amount` (receivable decreases) |
| Credit delta | `+amount` (new receivable created) |
| `paid_total` | Sum of cash + transfer only. Credit excluded. |
| Credit payment status | Always `pending` |
| Credit & order state | Full credit → PAID (closes lifecycle) |
| Duplicate credit | Only ONE credit payment allowed per order (409 on repeat) |
| Partial credit | **NOT SUPPORTED** — credit amount must equal remaining balance (400 `CREDIT_AMOUNT_MISMATCH`) |
| Split tender | **NOT SUPPORTED** in this slice |

## CTO Corrections

### Correction 1 (2026-05-07): Credit closes order lifecycle

> Credit does not count toward cash `paid_total`, but a full credit sale should still
> close the order as `PAID` from the order lifecycle / fulfillment perspective.

- Reverted `settlement_amount = 0 for credit` → `cumulative = prior_paid + pay_amount`
- Added duplicate credit guard

### Correction 2 (2026-05-07): Full-credit sale only

> For Phase 6 MVP, credit is full-credit sale only. Do not support partial credit
> or split tender in this slice.

- Added `pay_amount != remaining_balance` check for credit → 400 `CREDIT_AMOUNT_MISMATCH`
- Removed partial credit test, replaced with rejection test

## Changes Made

### 1. `backend/api/v1/orders.py` — `pay_order()`

**Method-dependent balance delta:**
- credit → `delta = +amount` (receivable increases)
- cash/transfer → `delta = -amount` (receivable decreases)

**Order state: Credit closes lifecycle.**
- `cumulative = prior_paid + pay_amount` for ALL methods
- Full credit → PAID (order lifecycle closed)

**Duplicate credit guard.**
- `count_order_payments(method='credit')` query → 409 `DUPLICATE_CREDIT_PAYMENT`

**Full-credit-only guard (Correction 2).**
- `pay_amount != remaining_balance` for credit → 400 `CREDIT_AMOUNT_MISMATCH`

### 2. `backend/repositories/payment_repository.py`

**`get_order_paid_total()`:** `AND method IN ('cash', 'transfer')` filter.

**`count_order_payments()`:** New method for duplicate credit guard.

### 3. `backend/schemas/order.py`

`PayOrderRequest.method` description updated to `"cash, transfer, credit"`.

### 4. `backend/tests/test_phase5_order_payment.py`

16 tests in Sections 10a-10f:

| Test | Validates |
|------|-----------|
| `test_credit_payment_applies_positive_balance_delta` | Credit → delta = +amount |
| `test_cash_payment_applies_negative_balance_delta` | Cash → delta = -amount |
| `test_transfer_payment_applies_negative_balance_delta` | Transfer → delta = -amount |
| `test_get_order_paid_total_sql_excludes_credit` | SQL filter correct |
| `test_get_order_paid_total_only_counts_cash_and_transfer` | Credit excluded from sum |
| `test_credit_payment_status_is_pending` | Credit payment status = pending |
| `test_credit_full_amount_advances_order_to_paid` | Full credit → PAID |
| `test_credit_partial_amount_rejected` | Partial credit → 400 CREDIT_AMOUNT_MISMATCH |
| `test_credit_plus_cash_not_supported_in_mvp` | Documents split-tender constraint |
| `test_credit_rejected_when_amount_exceeds_remaining` | Credit > remaining → PAYMENT_EXCEEDS_REMAINING |
| `test_payment_service_credit_applies_positive_delta` | PaymentService credit → +delta |
| `test_payment_service_cash_applies_negative_delta` | PaymentService cash → -delta |
| `test_pay_order_request_accepts_credit_method` | Schema accepts credit |
| `test_pay_order_request_accepts_transfer_method` | Schema accepts transfer |
| `test_duplicate_credit_payment_rejected` | Second credit → 409 |
| `test_first_credit_payment_allowed` | First credit passes through to PAID |

## Test Results

```
50 passed, 0 failed (excluding 4 pre-existing route-level env-var failures)
```

## Key Behavioral Summary

> **Phase 6 MVP supports full-credit sale only.**
>
> - Credit amount must exactly equal remaining balance
> - Partial credit → 400 `CREDIT_AMOUNT_MISMATCH`
> - Split tender (credit + cash) not supported in this slice
> - `paid_total` = cash + transfer only (financial reporting unchanged)
> - Full credit → order state = PAID (lifecycle closed)
> - Only one credit per order → 409 on duplicate
> - Balance delta credit = +amount (receivable exposure recorded)

## Files Modified

| File | Change Type |
|------|-------------|
| `backend/api/v1/orders.py` | Feature + guards |
| `backend/repositories/payment_repository.py` | Bug fix + new method |
| `backend/schemas/order.py` | Documentation |
| `backend/tests/test_phase5_order_payment.py` | Test suite |
| `ai-ledger/product-ai/2026-05-06_phase6_credit_payment_mvp_implementation.md` | Ledger |

## Risk Assessment

All changes have LOW impact radius. No HIGH or CRITICAL risk.

## Out of Scope (Deferred to Phase 6.1+)

- Partial credit support
- Split tender (credit + cash on same order)
- Credit limit enforcement
- Credit aging / overdue tracking
- Cancel/return credit reversal
- UI changes for credit method selection

## Approval Gate

- [ ] CTO review and approval required before push
- [ ] No push without explicit CTO approval
