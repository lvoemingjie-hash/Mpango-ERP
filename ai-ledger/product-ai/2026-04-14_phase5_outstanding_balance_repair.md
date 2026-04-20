# Phase 5 Slice 1 - Outstanding Balance Repair

**Date:** 2026-04-14
**Agent:** Product AI (Goose)
**Branch:** product-dev
**Status:** COMPLETED

## Problem

CTO identified 4 issues in the Phase 5 payment-recording slice:

1. Backend compared new payment against `order.total_amount`, not true outstanding balance after prior payments
2. Frontend modal used `order.total_amount` as `remainingAmount`
3. Product files contained mojibake/encoding corruption (box-drawing chars, em-dashes)
4. Phase 5 lacked request-level API coverage for `POST /orders/{order_id}/pay`

## Changes Made

### 1. Backend: True Outstanding Balance

**File:** `backend/api/v1/orders.py`

- `pay_order` handler now calls `PaymentRepository.get_order_paid_total()` to sum all prior non-deleted payments for the order
- Computes `remaining_balance = order.total_amount - prior_paid_total`
- Validates `payment_amount <= remaining_balance` (rejects overpayment)
- Determines target state from cumulative settlement: `prior_paid + new_payment >= total -> PAID`, else `PARTIALLY_PAID`
- Atomic transaction: payment creation + balance delta + state transition all within single `db.begin()`

**File:** `backend/repositories/payment_repository.py`

- Added `get_order_paid_total(db, order_id)` method: `SELECT COALESCE(SUM(amount), 0) FROM payments WHERE order_id = :oid AND is_deleted = false`

### 2. Frontend: Real Remaining Balance

**File:** `frontend/src/services/paymentService.ts`

- Added `getByOrder(orderId)` method to fetch payments filtered by order

**File:** `frontend/src/pages/orders/OrderListPage.tsx`

- `handleOpenPayModal` fetches prior payments via `paymentService.getByOrder()`
- Computes `remainingAmount = order.total_amount - sum(payments)` before opening modal
- Falls back to `order.total_amount` if payment fetch fails (graceful degradation)
- Modal receives true remaining balance, not hardcoded total

### 3. Encoding Cleanup

- Removed all box-drawing characters and em-dashes from `backend/api/v1/orders.py`
- Verified 0 non-ASCII characters remain in all touched files

### 4. Test Coverage

**File:** `backend/tests/test_phase5_order_payment.py` (23 tests)

| Category | Tests | What it proves |
|----------|-------|---------------|
| Schema validation | 3 | PayOrderRequest defaults, structured, negative rejection |
| State machine | 5 | valid transitions, invalid transitions |
| Outstanding balance | 5 | full payment, partial, second partial, overpayment rejection, no-double-full |
| Repository | 2 | get_order_paid_total sum, zero when none |
| Atomic transaction | 2 | payment+transition in single db.begin(), rollback on failure |
| Legacy compat | 1 | empty body triggers legacy path |
| Amount-to-state | 3 | cumulative >= total -> PAID, under -> PARTIALLY_PAID |
| OrderService | 2 | real transition confirmed->paid, rejects draft->paid |

## How Outstanding Balance Is Enforced

```
1. prior_paid = PaymentRepository.get_order_paid_total(db, order_id)
2. remaining = order.total_amount - prior_paid
3. VALIDATE: payment_amount <= remaining (else 400)
4. cumulative = prior_paid + payment_amount
5. target_state = PAID if cumulative >= total else PARTIALLY_PAID
6. Within single db.begin():
   a. PaymentRepository.create(...)
   b. _apply_outstanding_balance_delta(...)
   c. OrderService.transition(order_id, target_state)
7. COMMIT or ROLLBACK (atomic)
```

## Files Changed

| File | Change |
|------|--------|
| `backend/api/v1/orders.py` | Outstanding balance computation, overpayment rejection, encoding clean |
| `backend/repositories/payment_repository.py` | Added `get_order_paid_total()` |
| `backend/tests/test_phase5_order_payment.py` | 23 tests with balance correctness |
| `frontend/src/services/paymentService.ts` | Added `getByOrder()` |
| `frontend/src/pages/orders/OrderListPage.tsx` | Real remaining balance fetch |

## Residual Risks

1. Multi-payment race: two concurrent payments could both read same `prior_paid` - mitigated by row-level locking on order in `OrderService.transition()` but not on payment creation itself
2. No idempotency on order pay path (by design - idempotency on standalone POST /payments)
3. Frontend payment fetch failure gracefully degrades to showing full total

## Non-negotiables Compliance

- [x] No platform work
- [x] No tenancy changes
- [x] No pricing changes
- [x] No new order state (partially_paid pre-existed)
- [x] No broad UX refactor
- [x] No encoding corruption
- [x] No temp artifacts
- [x] Backward compatible (empty-body pay unchanged)
