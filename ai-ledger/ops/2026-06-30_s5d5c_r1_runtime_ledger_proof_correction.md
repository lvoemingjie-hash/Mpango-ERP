# S5-D5C-R1: Runtime Ledger Proof Correction

**Date:** 2026-06-30
**Sprint:** S5-D5C-R1 (Correct verdict, prove ledger invariant)
**Target Commit:** `bc6e2b16ebc5666dd5ed4ec11ffb39b8b48e95a4`
**Deployed Commit:** `bc6e2b16ebc5666dd5ed4ec11ffb39b8b48e95a4` (applied via patch + rebuild)
**Rebuild:** YES (S5-D5 guard was missing from deployed container)
**Corrected Verdict:** FAIL_RUNTIME_LEDGER_PROOF_INCOMPLETE

**Reason:** Partial transfer final settlement failed due to state machine defect. S5-D5 runtime invariant not fully proven.

**OPS Branch:** `opencode/s5d4c-redeploy-settled-payment-smoke-2026-06-29`

---

## Corrected Prior Verdict

| Field | Prior | Corrected |
|-------|-------|-----------|
| Verdict | PASS_EXACT_MERGE_RUNTIME_PAYMENT_LEDGER_PROOF | **FAIL_RUNTIME_LEDGER_PROOF_INCOMPLETE** |

**Reason:** The partial transfer flow could not complete because the state machine rejects `partially_paid -> partially_paid` transitions. This prevents multiple partial payments on the same order, which is required for the S5-D5 partial transfer proof.

---

## Task 1: Verify Deployed Code

### 1a. Transfer Guard in orders.py

**Location:** `/app/api/v1/orders.py` line 557

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

**Result:** Guard present and correct ✓

### 1b. Ledger Path in order_service.py

**Location:** `/app/services/order_service.py` line 131

```python
await self._post_ledger_entries(order, current_state, target_state, payment_method=payment_method)
```

**Result:** Ledger integration present ✓

### 1c. LedgerService Implementation

**Location:** `/app/services/ledger_service.py`

- `post_payment_received()` method exists (line 281)
- Creates Cash debit + Receivable credit entries
- Uses `reference_type='order'`

**Result:** Ledger service implemented correctly ✓

---

## Task 2: Full Cash Payment Proof

### Setup
- Order: `ae515631-dbca-4fad-b044-98f625ec1604` (shortened: `ae515631`)
- Total: 150.00
- Payment: `2f9e37b2-fa0b-4e4a-81d2-5cb6de45aa18` (shortened: `2f9e37b2`)

### HTTP Flow
| Step | Result |
|------|--------|
| Create order | `ORDER id=ae515631 total=150.0` |
| Confirm | `CONFIRMED` |
| Pay (amount=150, method=cash) | `PAID payment_id=2f9e37b2` |

### DB Verification
```
Payment: 2f9e37b2|completed|cash|150.00
Order:   ae515631|paid
```

### Ledger Verification
| Account Type | Entry Type | Amount |
|--------------|------------|--------|
| cash | debit | 150.00 |
| receivable | credit | -150.00 |

**Ledger Balance:** 0.00 ✓
**Entry Count:** 2 ✓

**Result:** FULL CASH PAYMENT PASS ✓

---

## Task 3: Partial Transfer Proof

### Setup
- Order: `dc44a406-c048-4c9b-a428-9745474ac88d` (shortened: `dc44a406`)
- Total: 300.00

### HTTP Flow
| Step | Result |
|------|--------|
| Create order | `ORDER id=dc44a406 total=300.0` |
| Confirm | `CONFIRMED` |
| First partial (100 transfer) | `PARTIAL1 payment_id=010f3b42 status=pending` |
| Second partial (100 transfer) | **FAILED: `INVALID_STATE_TRANSITION: partially_paid -> partially_paid`** |
| Final (100 transfer) | NOT REACHED |

### DB Verification
```
Payments: 010f3b42|pending|transfer|100.00 (only 1 payment)
Order:    dc44a406|partially_paid
```

### Ledger Verification
| Account Type | Entry Type | Amount |
|--------------|------------|--------|
| (empty) | (empty) | (empty) |

**Ledger Balance:** 0 (no entries)
**Entry Count:** 0

**Result:** PARTIAL TRANSFER FAIL ✗

### Root Cause Analysis

The state machine in `order_service.py` does not allow `partially_paid -> partially_paid` transitions. When a second partial payment is attempted:

1. `prior_paid = 100, pay_amount = 100, cumulative = 200 < 300`
2. `target_state = OrderState.PARTIALLY_PAID`
3. Current state is already `partially_paid`
4. State machine rejects: `partially_paid -> partially_paid`

**Product Defect:** The state machine needs to be updated to allow `partially_paid -> partially_paid` transitions for multiple partial payments.

---

## Task 4: Repeat/Retry Proof

### HTTP Flow
| Step | Result |
|------|--------|
| Retry payment on paid order | HTTP 400: `PAYMENT_EXCEEDS_REMAINING` (correct) |

### DB Verification
- Payment count unchanged: 1 (correct)
- Ledger entry count unchanged: 2 (correct)

**Result:** RETRY PASS ✓

---

## Task 5: Health Post-Check

| Check | Result |
|-------|--------|
| 5/5 containers healthy | YES |
| /health/live | 200 |
| /health/ready | 200 |
| Backend error spike | 3 warnings (409 CONFLICT from state machine — expected) |

---

## Ledger Proof Summary

| Test | Ledger Entries | Balance | Status |
|------|----------------|---------|--------|
| Full cash payment | 2 (cash +150, receivable -150) | 0.00 | PASS |
| Partial transfer | 0 (state machine blocked) | N/A | **FAIL** |
| Repeat/retry | No duplicates | N/A | PASS |

**S5-D5 Runtime Invariant Status:** NOT PROVEN

The S5-D5 guard (transfer payment starts as `pending`) is working correctly. However, the partial transfer flow cannot complete due to the state machine defect, so the full invariant (transfer payments settle to `completed` on PAID with balanced ledger) cannot be demonstrated.

---

## Security Verification

| Check | Result |
|-------|--------|
| Old POSTGRES_PASSWORD in report | ABSENT |
| New POSTGRES_PASSWORD in report | ABSENT |
| JWT tokens in report | ABSENT |
| .env content in report | ABSENT |

---

## Conclusion

**FAIL_RUNTIME_LEDGER_PROOF_INCOMPLETE**

The S5-D5 runtime invariant requires demonstrating:
1. ✅ Transfer payment starts as `pending` (guard working)
2. ❌ Transfer payment settles to `completed` on order PAID (blocked by state machine)
3. ❌ Ledger entries created and balanced for transfer payments (blocked by state machine)

**Product Defect Confirmed:** State machine does not allow `partially_paid -> partially_paid` transitions. Multiple partial payments on the same order are blocked.

**STOP_AND_REPORT_CTO:** This is a product-level defect that prevents the S5-D5 partial transfer proof from completing. The state machine needs to be updated to allow multiple partial payments before the S5-D5 runtime invariant can be fully proven.

---

## Files

| File | Purpose |
|------|---------|
| `ai-ledger/ops/2026-06-30_s5d5c_r1_runtime_ledger_proof_correction.md` | This report |
