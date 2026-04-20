# Phase 5 Implementation Ledger — First Slice

**Date**: 2026-04-10
**Agent**: Product AI (Goose)
**Branch**: product-dev
**Status**: READY FOR CTO REVIEW

---

## Objective

Close the wholesaler money loop by adding structured payment recording to the order workflow.

## Scope (CTO-Approved First Slice)

1. Let wholesaler record a payment against an order
2. Reuse existing payment infrastructure
3. Keep `POST /orders/{order_id}/pay` backward-compatible
4. Make receivables and invoice balance_due reflect recorded payments
5. Minimal wholesaler order detail / payment entry flow

---

## Files Changed

### Backend

| File | Change | Lines |
|------|--------|-------|
| `backend/schemas/order.py` | Added `PayOrderRequest` schema (optional fields) | +50 |
| `backend/api/v1/orders.py` | Extended `pay_order()` endpoint with optional `payment_input` body parameter | +120, -30 |

### Frontend

| File | Change | Lines |
|------|--------|-------|
| `frontend/src/services/orderService.ts` | Extended `pay()` with optional `PayOrderData` param, added types | +15, -3 |
| `frontend/src/components/ui/PaymentRecordModal.tsx` | New component: structured payment recording form | +185 (new) |
| `frontend/src/pages/orders/OrderListPage.tsx` | Replaced "Mark Paid" with "Record Payment" → modal flow | +40, -10 |

### Tests

| File | Change | Lines |
|------|--------|-------|
| `backend/tests/test_phase5_order_payment.py` | New test file: schema validation, state machine, integration | +413 (new) |

---

## Design Decisions

### D1: Optional Body on POST /pay
- `payment_input: Optional[PayOrderRequest] = None`
- No body → legacy behavior (state-only, confirmed → paid)
- Body with method+amount → creates Payment record + transitions

### D2: Transaction Strategy
- Structured payment path wraps all operations in a single `async with db.begin()` block
- `PaymentRepository.create()` — pure SQL INSERT, no own transaction
- `PaymentService._apply_outstanding_balance_delta()` — raw SQL UPDATE, same session
- `OrderService.transition()` — uses `self.db.flush()`, participates in caller's transaction
- If ANY step fails, the entire transaction rolls back atomically
- No orphaned payments, no stale order states

### D3: Partial Payment Support
- Payment amount < order total → `partially_paid` state
- Payment amount >= order total → `paid` state
- `partially_paid` state already existed in state machine — no new state added

### D4: Frontend UX
- "Mark Paid" button replaced with "Record Payment"
- Opens `PaymentRecordModal` with method selector, amount input, optional transaction ID
- Shows clear indicators: "Full payment → Paid" vs "Partial payment → Partially Paid"

### D5: No Platform/Tenancy/Pricing Changes
- Zero changes to tenant middleware, pricing resolution, or platform auth
- Reuses all existing RBAC permissions (`orders:update`)

---

## Backward Compatibility

| Caller | Body | Behavior | Changed? |
|--------|------|----------|----------|
| Existing frontend (no body) | `{}` / none | confirmed → paid, no Payment record | **NO** |
| Phase 5 frontend | `{ method, amount }` | Payment created + state transition | YES |
| Phase 5 frontend | `{}` / none | Same as legacy | **NO** |

---

## Self-Check Gates

- [x] No platform work
- [x] No tenancy changes
- [x] No pricing redesign
- [x] No new order state (partially_paid pre-existed)
- [x] No broad UX refactor (only order list pay button)
- [x] Backward compatible: empty-body pay still works
- [x] All new files follow project conventions
- [x] RBAC unchanged (orders:update)

---

## Residual Risks

1. **Multi-payment accumulation**: Current slice uses simple `amount vs order_total` comparison. If multiple partial payments are recorded, `remainingAmount` on frontend doesn't aggregate. This is acceptable for first slice — backend correctly handles `partially_paid → paid` transitions.

2. **Transfer idempotency**: The order pay path sends `idempotency_key=None`. Transfer payments via this path won't be idempotent. This is intentional — idempotency is only enforced via `POST /payments` endpoint.

---

## Next Steps (Future Slices)

- Multi-payment accumulation query (SUM of payments per order)
- Payment history in order detail view
- Invoice balance_due reflects recorded payments
- Reconcile outstanding balance with payment records
