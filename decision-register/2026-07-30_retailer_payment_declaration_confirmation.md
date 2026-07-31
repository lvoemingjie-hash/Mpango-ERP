# Decision Record: Retailer Payment Declaration & Cashier Confirmation (R4 Final)

**Date:** 2026-07-31 (R4 correction; integrates H3 baseline `0f9d259b`)
**Status:** PASS_FOR_CTO_DC12R1_S3_S2B_IMPLEMENTATION_PLANNING_R4
**Supersedes:** R2 DR (`03f18a44`) — superseded
**Related:** DC-12R1-S3-S2B-D-R4 contract (`ai-ledger/product-ai/2026-07-30_dc12r1_s3_s2b_payment_declaration_contract.md`)

---

## R4 Corrections (on top of R2)

| ID | Decision | R2 → R4 Change |
|---|---|---|
| DR-13 | Exact 035/036 live-status-set | **R4.1:** Stale `'provisioned'` removed; correct set includes `'failed'` not `'provisioned'` |
| DR-14 | transfer_reference → transaction_id mapping | **R4.2 (NEW):** Declaration's `transfer_reference` stored as canonical payment's `transaction_id`; duplicate → 409 |
| DR-15 | Declaration key vs canonical payment key | **R4.3 (NEW):** Two independent idempotency namespaces; no collision |
| DR-16 | Partial/final confirmation lifecycle | **R4.4 (NEW):** Partial → PARTIALLY_PAID; final → PAID; receipt only for completed |
| DR-17 | Duplicate transfer reference 409 | **R4.5 (NEW):** Canonical path's existing `get_by_transaction_id` check at confirmation |

---

## Verdict

```
PASS_FOR_CTO_DC12R1_S3_S2B_IMPLEMENTATION_PLANNING_R4
```

All R4 corrections applied. No unresolved design defects. FIND-01 through FIND-46 mapped (gap=0).
