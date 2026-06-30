# S5-D6C-R3 Transfer Status Timing Clarification

| Field | Value |
|---|---|
| **Date** | 2026-06-30 |
| **Previous Verdict** | PASS_RUNTIME_MULTI_PARTIAL_TRANSFER_SETTLEMENT |
| **Corrected Verdict** | PASS_RUNTIME_MULTI_PARTIAL_TRANSFER_SETTLEMENT_WITH_STATUS_TIMING_CLARIFIED |
| **Operator** | automated |
| **Environment** | Tencent VPS 1.14.247.12, prod stack, commit fe4b375 |

## Clarification

R2 report listed all 3 payments as `completed` without distinguishing immediate vs final status. This clarifies the payment status lifecycle per S5-D5 expected behavior.

## Payment Status Timing

| Payment | Amount | Immediate Status (API) | Final DB Status (after settlement) |
|---|---|---|---|
| Pay 1 (50.00) | transfer | `pending` | `completed` |
| Pay 2 (50.00) | transfer | `pending` | `completed` |
| Pay 3 (50.00, final) | transfer | `completed` | `completed` |

**Explanation:**
- Pay 1: API returns order `partially_paid`. Payment status is `pending` (transfer awaiting settlement). DB row created as `pending`.
- Pay 2: API returns order `partially_paid`. Payment status is `pending`. DB row created as `pending`.
- Pay 3: API returns order `paid`. Payment status is `completed`. `update_cash_transfer_to_completed()` fires, updating all 3 rows from `pending` to `completed`.

**R2 DB snapshot was taken after Pay 3 settlement**, so all rows showed `completed`. The immediate `pending` status for Pay 1 and Pay 2 was not captured in R2's DB verification step, but was confirmed by code inspection:

```python
# orders.py line 553-559
status=(
    "completed"
    if (
        payment_input.method == "transfer"
        and target_state == OrderState.PAID
    )
    else "pending"
),
```

This confirms: transfer payments are created as `pending` unless `target_state == PAID`.

## Residual Note

Immediate `pending` status was not captured in R2's DB verification step because the DB query was executed after all 3 payments. The final settlement (`paid` + balanced ledger at 0.00) was proven. The payment lifecycle (pending → completed on settlement) is confirmed by code inspection.

## Verdict

**PASS_RUNTIME_MULTI_PARTIAL_TRANSFER_SETTLEMENT_WITH_STATUS_TIMING_CLARIFIED**

Multi-partial transfer settlement works correctly. Pay 1 and Pay 2 are immediately `pending`. Pay 3 (final) triggers `update_cash_transfer_to_completed()`, updating all rows to `completed`. Order reaches `paid`. Ledger entries posted (cash +150, receivable -150, balanced at 0.00). Retry blocked with PAYMENT_EXCEEDS_REMAINING.
