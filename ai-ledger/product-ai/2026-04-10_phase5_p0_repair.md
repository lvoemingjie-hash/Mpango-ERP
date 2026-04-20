# Phase 5 P0 Repair — Transactional Safety Fix

**Date**: 2026-04-10 (repair pass)
**Agent**: Product AI (Goose)
**Branch**: product-dev
**Status**: READY FOR CTO REVIEW

---

## Problem

The initial Phase 5 implementation called `PaymentService.create_payment()` (which manages its own `async with tenant_db.begin()` transaction), then separately called `OrderService.transition()`. These were two independent transactions. If the state transition failed after payment committed, payment and order state became inconsistent.

CTO assessment: "That is not approved."

---

## Root Cause

`PaymentService.create_payment()` uses `async with tenant_db.begin()` — an independent transaction boundary. The order pay handler called this first (payment commits), then called `OrderService.transition()` (separate session commit). No single atomic unit.

---

## Repair Design

### Decision: Move payment creation into the same transaction as state transition

Instead of calling `PaymentService.create_payment()` (which owns its transaction), the handler now:

1. **Opens a single `async with db.begin()` block**
2. Inside that block:
   - Calls `PaymentRepository.create()` directly (pure data operation, no transaction management)
   - Calls `PaymentService._apply_outstanding_balance_delta()` directly (raw SQL on same session)
   - Calls `OrderService.transition()` (uses `self.db` — no own transaction)
3. If **any** step fails, the entire block rolls back atomically

### Why this is safe:
- `PaymentRepository.create()` is a thin SQL wrapper — no side effects, no own transaction
- `OrderService.transition()` explicitly documents "caller manages transaction" (uses `self.db.flush()`, not commit)
- `_apply_outstanding_balance_delta()` uses the passed session — no own transaction
- All three operations share the same `db` session inside one `begin()` block

### Backward compatibility preserved:
- **Empty body path**: No `db.begin()` wrapper. Calls `OrderService.transition()` directly, same as before. FastAPI session handles commit.
- **Structured body path**: New atomic path inside `db.begin()`.

---

## Files Changed (6 tracked + 3 untracked)

### Backend (modified)
| File | Change |
|------|--------|
| `backend/api/v1/orders.py` | Rewrote `pay_order()`: unified `db.begin()` for structured path |
| `backend/schemas/order.py` | Added `PayOrderRequest` schema (unchanged from initial) |

### Frontend (modified)
| File | Change |
|------|--------|
| `frontend/src/services/orderService.ts` | Extended `pay()` with optional `PayOrderData` |
| `frontend/src/components/ui/PaymentRecordModal.tsx` | New: structured payment recording form |
| `frontend/src/pages/orders/OrderListPage.tsx` | Replaced "Mark Paid" with "Record Payment" → modal |

### Tests (new)
| File | Tests |
|------|-------|
| `backend/tests/test_phase5_order_payment.py` | 17 tests (4 schema, 5 state machine, 4 transaction safety, 4 amount-to-state) |

### Ledger (new)
| File |
|------|
| `ai-ledger/product-ai/2026-04-10_phase5_slice1_implementation.md` |
| `ai-ledger/product-ai/2026-04-10_phase5_p0_repair.md` (this file) |

---

## Transaction Safety Guarantee

The single `async with db.begin()` block in `pay_order()` ensures:

```
BEGIN TRANSACTION
  ├── PaymentRepository.create()        -- INSERT INTO payments
  ├── _apply_outstanding_balance_delta() -- UPDATE wholesaler_retailer_bindings
  └── OrderService.transition()         -- UPDATE orders + INSERT ledger entries
COMMIT  (all succeed)
-- or --
ROLLBACK (any failure — no partial state)
```

Proven by tests:
- `test_structured_payment_uses_single_transaction` → verifies commit on success
- `test_transition_failure_rolls_back_payment` → verifies rollback when transition fails
- `test_payment_creation_failure_rolls_back_all` → verifies rollback when payment creation fails

---

## Self-Check Gates

| # | Gate | Status |
|---|------|--------|
| 1 | No platform work | ✅ PASS |
| 2 | No tenancy changes | ✅ PASS |
| 3 | No pricing redesign | ✅ PASS |
| 4 | No new order state | ✅ PASS (partially_paid pre-existed) |
| 5 | No broad UX refactor | ✅ PASS (only order list pay button) |
| 6 | Backward compatible | ✅ PASS (empty-body pay unchanged) |
| 7 | No encoding corruption | ✅ PASS (all 6 files valid UTF-8) |
| 8 | No temp artifacts | ✅ PASS (no _*.py files remaining) |

---

## Tests Run

```
63 passed, 0 failed, 0 regressions
  - 17 Phase 5 P0 tests (schema + state machine + transaction safety + amount-to-state)
  - 5 Payment API tests
  - 1 Payment atomicity test
  - 10 Order API tests
  - 18 Phase 4 pricing-safe tests
  - 6 B6 hardening tests
  - 6 B6 payment tests
```

---

## Known Residual Risks

1. **Multi-payment accumulation**: Frontend `remainingAmount` doesn't aggregate previous partial payments. Backend handles state correctly (`partially_paid → paid`). Acceptable for first slice.

2. **No idempotency on order pay path**: `idempotency_key=None` on this path. Idempotency enforced only via `POST /payments` endpoint. Acceptable — this path is for wholesaler UI, not API integration.

3. **Cash balance delta**: Always applies negative delta (same as `PaymentService.create_payment` for cash). If business rules change for different methods, handler needs update. Low risk.

---

## Definition of Done

✅ Transactional safety guaranteed via single `db.begin()` block
✅ Backward compatibility verified (empty-body path unchanged)
✅ Tests prove atomic commit and rollback behavior
✅ No encoding corruption in touched files
✅ No temp artifacts remaining
✅ All 8 self-check gates PASS
✅ No push — awaiting CTO review
