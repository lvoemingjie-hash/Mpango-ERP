# S5-D6C-R2 Transfer Final Settlement Rerun

| Field | Value |
|---|---|
| **Date** | 2026-06-30 |
| **Previous Verdict** | FAIL_TRANSFER_MULTI_PARTIAL_SETTLEMENT_INCOMPLETE |
| **Corrected Verdict** | PASS_RUNTIME_MULTI_PARTIAL_TRANSFER_SETTLEMENT |
| **Operator** | automated |
| **Environment** | Tencent VPS 1.14.247.12, prod stack, commit fe4b375 |

## Corrected Verdict

**From:** FAIL_TRANSFER_MULTI_PARTIAL_SETTLEMENT_INCOMPLETE
**To:** PASS_RUNTIME_MULTI_PARTIAL_TRANSFER_SETTLEMENT

Reason: R1 used order total 150 (retailer price override) with payments 30+40+30=100. This correctly remains `partially_paid` because 100 < 150. R2 reruns with payments 50+50+50=150, which correctly reaches `paid` with balanced ledger.

## Test Configuration

- **SKU:** S5D2-20260626111011-LAPTOP01
- **Retailer:** 22eb3fb6-3029-4fff-ad50-648259c0dcf4
- **Retailer price:** 150.00 (overrides unit_price)
- **Order total:** 150.00
- **Payment method:** transfer
- **Payment amounts:** 50 + 50 + 50 = 150.00 (matches total exactly)

## Step-by-Step Proof

### Step 1: Create Order

| Field | Value |
|---|---|
| order_id | `3742b1c6-6cdc-45b9-b3c0-35dc433124a3` |
| order_total | 150.00 |
| items | 1× LAPTOP01 @ retailer_price 150.00 |

### Step 2: Confirm Order

| Field | Value |
|---|---|
| status | `confirmed` |
| ledger entries | 2 (receivable +150, revenue +150) |

### Step 3: Pay Transfer 50.00

| Field | Value |
|---|---|
| order.status | `partially_paid` |
| payment.amount | 50.00 |
| payment.method | transfer |
| payment.status | `pending` (API) / `completed` (DB after transition) |
| cumulative_paid | 50.00 |
| target_state | PARTIALLY_PAID |
| ledger settlement entries | 0 |

**DB verification:**
- Payments: 1 row (50.00, transfer, completed)
- Order: partially_paid

### Step 4: Pay Transfer 50.00

| Field | Value |
|---|---|
| order.status | `partially_paid` |
| payment.amount | 50.00 |
| payment.method | transfer |
| payment.status | `pending` (API) / `completed` (DB after transition) |
| cumulative_paid | 100.00 |
| target_state | PARTIALLY_PAID |
| ledger settlement entries | 0 |

**DB verification:**
- Payments: 2 rows (50+50=100, transfer, completed)
- Order: partially_paid

### Step 5: Pay Transfer 50.00 (Final)

| Field | Value |
|---|---|
| order.status | `paid` |
| payment.amount | 50.00 |
| payment.method | transfer |
| payment.status | `completed` |
| cumulative_paid | 150.00 |
| target_state | PAID |
| ledger settlement entries | 2 |

**DB verification:**
- Payments: 3 rows (50+50+50=150, transfer, completed)
- Order: `paid`
- Ledger: 2 entries (cash +150, receivable -150), balanced at 0.00

### Step 6: Retry After Paid

| Field | Value |
|---|---|
| response | 400 INVALID_INPUT |
| error | PAYMENT_EXCEEDS_REMAINING — Payment amount (25) exceeds remaining balance (0.00). Order total: 150.00, already paid: 150.00. |
| payment count unchanged | ✓ |
| ledger entry count unchanged | ✓ |

## DB State After Each Payment

| Payment # | Amount | Cumulative | Order Status | Payment Status | Ledger Entries |
|---|---|---|---|---|---|
| 1 | 50.00 | 50.00 | partially_paid | completed | 0 |
| 2 | 50.00 | 100.00 | partially_paid | completed | 0 |
| 3 (final) | 50.00 | 150.00 | paid | completed | 2 |
| retry | 25.00 | — | paid | — | 2 (unchanged) |

## Ledger Verification

| Entry | account_type | entry_type | amount |
|---|---|---|---|
| 1 | cash | debit | +150.0000 |
| 2 | receivable | credit | -150.0000 |

**Sum:** 0.0000 (balanced) ✓
**Entry count:** 2 ✓

## Health Post-Check

| Check | Result |
|---|---|
| mpango_prod_backend | ✓ healthy |
| mpango_prod_gateway | ✓ healthy |
| /health/live | 200 |
| /health/ready | 200 |

## Verdict

**PASS_RUNTIME_MULTI_PARTIAL_TRANSFER_SETTLEMENT**

Multi-partial transfer settlement works correctly when payment amounts sum to the order total. 50+50+50=150 (order total) reached `paid`. All 3 payments `completed`. Ledger entries posted (cash +150, receivable -150, balanced at 0.00). Retry blocked with PAYMENT_EXCEEDS_REMAINING.

**R1 root cause was incorrect test setup, not product defect.** R1 used 30+40+30=100 against order total 150, which correctly remained `partially_paid`. R2 confirms the product works correctly with matching amounts.
