# Decision Record: Retailer Payment Declaration & Cashier Confirmation (R2 Final)

**Date:** 2026-07-31 (R2 correction; integrates H3 baseline `0f9d259b`)
**Status:** PASS_FOR_CTO_DC12R1_S3_S2B_IMPLEMENTATION_PLANNING
**Supersedes:** R1 DR (`78a2bce3`, status: STOP) — superseded
**Related:** DC-12R1-S3-S2B-D-R2 contract (`ai-ledger/product-ai/2026-07-30_dc12r1_s3_s2b_payment_declaration_contract.md`)

---

## H3 Baseline Integration

The H3 product defect (frontend `orders:update` vs backend `payments:create`) has been resolved and merged into the product baseline (`0f9d259b`). The H3 commit (`280a06c3`) is an ancestor of this branch. The defect that caused the R1 STOP is now closed.

---

## R2 Corrections

| ID | Decision | R1 → R2 Change |
|---|---|---|
| DR-01 | Tenant-local storage | Unchanged |
| DR-02 | State machine: pending → confirmed/rejected | Unchanged from R1 |
| DR-03 | CanonicalPaymentService extraction | Unchanged from R1 |
| DR-04 | Idempotent confirmation replay (200, not 409) | Unchanged from R1 |
| DR-05 | Receipt: single source = payments.receipt_number | **R2 corrected:** removed from declarations; FK RESTRICT; format RCT-YYYYMMDD-NNNNNN; receipt_sequences.business_date CHAR(8) |
| DR-06 | Statement: server-side, dual-key, no opening/closing balance | **R2 corrected:** LedgerService.get_balance is tenant-wide, cannot use; opening/closing deferred |
| DR-07 | Immutable declarations, no is_deleted, reason unified | Unchanged from R1; FK RESTRICT added in R2 |
| DR-08 | Migration 037 forward-only/fail-closed | **R2 corrected:** live tenant enum via tenant_registrations JOIN wholesalers; no per-tenant alembic_version; real catalog preflight |
| DR-09 | No notification emission | Unchanged from R1 |
| DR-10 | Replace client:payments:create; add payments:confirm_declaration to ADMIN | **R2 corrected:** explicit registry + seeder reconciliation requirement |
| DR-11 | Idempotency: UNIQUE(retailer_id, idempotency_key) | **R2 corrected:** was (order_id, idempotency_key) |
| DR-12 | configure_app risk = MEDIUM | **R2 corrected:** was LOW |

---

## Verdict

```
PASS_FOR_CTO_DC12R1_S3_S2B_IMPLEMENTATION_PLANNING
```

All R2 corrections applied. All accounting sources of truth resolved. No unresolved decisions remain.
