# S5-D6C-R1 Transfer Partial Settlement Root Cause Audit

| Field | Value |
|---|---|
| **Date** | 2026-06-30 |
| **Previous Verdict** | PASS_RUNTIME_S5D6_MULTI_PARTIAL_PAYMENT_STATE_MACHINE_UNBLOCKED |
| **Corrected Verdict** | FAIL_TRANSFER_MULTI_PARTIAL_SETTLEMENT_INCOMPLETE |
| **Operator** | automated |
| **Environment** | Tencent VPS 1.14.247.12, prod stack, commit fe4b375 |

## Corrected Verdict

**From:** PASS_RUNTIME_S5D6_MULTI_PARTIAL_PAYMENT_STATE_MACHINE_UNBLOCKED
**To:** FAIL_TRANSFER_MULTI_PARTIAL_SETTLEMENT_INCOMPLETE

Reason: Cash flow passed, but transfer flow 30+40+30 remained `partially_paid` with empty ledger. Transfer partial settlement is incomplete.

## Audit 1: PaymentRepository.get_order_paid_total

```python
async def get_order_paid_total(self, db, *, order_id):
    result = await db.execute(
        text(
            "SELECT COALESCE(SUM(amount), 0) "
            "FROM payments "
            "WHERE order_id = :order_id AND is_deleted IS FALSE "
            "AND method IN ('cash', 'transfer')"
        ),
        {"order_id": order_id},
    )
```

**Finding:** No status filter. Counts ALL cash/transfer payments regardless of `pending`/`completed`. This is correct — pending transfers represent actual money in transit.

## Audit 2: Transfer Order DB State

**Transfer order (99b7c498):**

| Field | Value |
|---|---|
| order.status | `partially_paid` |
| order.total_amount | 150.00 |

**Payments:**

| id | amount | method | status | is_deleted |
|---|---|---|---|---|
| 8b554cea | 30.00 | transfer | pending | false |
| 2b6d170a | 40.00 | transfer | pending | false |
| 3011684f | 30.00 | transfer | pending | false |

**Sum by status:** pending|transfer|3|100.00
**get_order_paid_total:** 100.00
**Ledger entries:** (empty)

**Cash order (8a535f51) for comparison:**

| Field | Value |
|---|---|
| order.status | `paid` |
| order.total_amount | 150.00 |

**Payments:**

| id | amount | method | status | is_deleted |
|---|---|---|---|---|
| bd7fc1f9 | 30.00 | cash | completed | false |
| 4fcd23e8 | 40.00 | cash | completed | false |
| 994af000 | 30.00 | cash | completed | false |
| 223b2cf8 | 50.00 | cash | completed | false |

**Sum by status:** completed|cash|4|150.00
**get_order_paid_total:** 150.00
**Ledger entries:** 2 (cash +150, receivable -150, balanced)

## Audit 3: Root Cause — Why Cash Reaches Paid but Transfer Does Not

### Cash Flow (works)

1. Each cash payment is created with `status="pending"`
2. `target_state` is calculated: `cumulative >= total ? PAID : PARTIALLY_PAID`
3. After each payment, `order_service.transition()` is called
4. When `target_state == PAID`, the transition succeeds
5. After transition, `update_cash_transfer_to_completed()` updates all pending payments to `completed`
6. `_post_ledger_entries()` fires on `PAID` transition → ledger entries created

### Transfer Flow (broken)

1. Each transfer payment is created with `status="pending"`
2. `target_state` is calculated: `cumulative >= total ? PAID : PARTIALLY_PAID`
3. After each payment, `order_service.transition()` is called
4. `target_state == PARTIALLY_PAID` (because 30 < 150, 70 < 150, 100 < 150)
5. The S5-D6 guard allows `partially_paid → partially_paid` ✓
6. `update_cash_transfer_to_completed()` is ONLY called when `order_status == PAID.value` — **NOT called for PARTIALLY_PAID**
7. `_post_ledger_entries()` fires on every transition, but only creates entries for `CONFIRMED`, `PAID`, and `RETURNED` — **NOT for PARTIALLY_PAID**

### Deadlock

Transfer payments remain `pending` forever because:
- `update_cash_transfer_to_completed()` requires `order_status == PAID`
- Order can never reach `PAID` because `get_order_paid_total()` sums all payments (including pending), but the state machine only allows `PAID` when `cumulative >= total`
- If the user pays exactly the total in one transfer payment, it works (single payment → PAID → ledger posted)
- If the user pays in multiple partial transfers, it deadlocks: order stays `partially_paid`, payments stay `pending`, ledger never posted

## Audit 4: Payment Status Logic

```python
status=(
    "completed"
    if (
        payment_input.method == "transfer"
        and target_state == OrderState.PAID
    )
    else "pending"
),
```

**Finding:** Transfer payments are only created as `completed` when `target_state == PAID`. For partial payments, `target_state == PARTIALLY_PAID`, so status is `pending`. This is correct — pending means awaiting verification.

The issue is NOT in the status logic. The issue is in `update_cash_transfer_to_completed()` which is only called on `PAID` transition.

## Audit 5: Ledger Posting Logic

```python
if to_state == OrderState.CONFIRMED:
    # Debit RECEIVABLE, Credit REVENUE
    await ledger_service.post_order_confirmation(...)

elif to_state == OrderState.PAID:
    if payment_method == "credit":
        # Skip cash-settlement entries
        pass
    else:
        # Debit CASH, Credit RECEIVABLE
        await ledger_service.post_payment_received(...)

elif to_state == OrderState.RETURNED:
    # Reverse entries
```

**Finding:** `_post_ledger_entries()` only creates entries for `CONFIRMED`, `PAID`, and `RETURNED`. It does NOT create entries for `PARTIALLY_PAID`. This means:
- Transfer orders that never reach `PAID` have no ledger entries
- The ledger is incomplete for multi-partial transfer settlements

## Hypothesis Confirmed

**Root cause:** Transfer partial settlement deadlock. Three interacting defects:

1. **`update_cash_transfer_to_completed()`** is only called when `order_status == PAID`. For multi-partial transfers, the order stays `partially_paid`, so payments stay `pending` forever.

2. **`_post_ledger_entries()`** only fires on `PAID` transition. Multi-partial transfer orders that never reach `PAID` have no ledger entries.

3. **`get_order_paid_total()`** counts all payments regardless of status. This is correct for financial reporting, but the state machine uses the same value to determine `target_state`. For multi-partial transfers, `cumulative < total` → `target_state = PARTIALLY_PAID` → no ledger → no payment status update.

## Verdict

**FAIL_TRANSFER_MULTI_PARTIAL_SETTLEMENT_INCOMPLETE**

Transfer partial settlement is a product defect. Multi-partial transfer payments deadlock: payments stay `pending`, order stays `partially_paid`, ledger never posted. Cash flow works because each payment triggers a transition check, and the final payment transitions to `PAID` which triggers both `update_cash_transfer_to_completed()` and `_post_ledger_entries()`.

**Requires product fix.** Do not proceed with S5-D6C verification until transfer partial settlement is resolved. CTO approval required for code changes.
