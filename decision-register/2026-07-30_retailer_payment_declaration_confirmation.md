# Decision Record: Retailer Payment Declaration & Cashier Confirmation (R1 Corrected)

**Date:** 2026-07-31 (R1 correction of 2026-07-30 original)
**Status:** STOP_AND_REPORT_CTO_WITH_H3_PAYMENT_PERMISSION_PREREQUISITE
**Supersedes:** Original DR (status: APPROVED FOR PLANNING) — **WITHDRAWN**
**Related:** DC-12R1-S3-S2B-D-R1 contract (`ai-ledger/product-ai/2026-07-30_dc12r1_s3_s2b_payment_declaration_contract.md`)

---

## Context

The original decision record (2026-07-30) approved the payment declaration design for planning. The R1 correction **withdraws that approval** after identifying:

1. A CURRENT_PRODUCT_DEFECT: frontend/backend permission mismatch on the payment button.
2. Insufficient idempotency specification for confirmation replay.
3. Missing canonical payment service extraction design.
4. Inadequate migration safety specification.
5. Incorrect risk classification (LOW → HIGH).

---

## Corrected Decisions

| ID | Decision | Change from Original |
|---|---|---|
| DR-01 | Tenant-local storage | **Unchanged** |
| DR-02 | State machine: pending → confirmed/rejected | **Corrected:** no expiry/cancellation in MVP (R1.10) |
| DR-03 | Confirmation delegates to CanonicalPaymentService | **Corrected:** extracted service, not route handler call (R1.4) |
| DR-04 | Confirmation replay is idempotent | **Corrected:** returns 200 with same result, not 409 (R1.3) |
| DR-05 | Receipt number via atomic sequence table | **New:** single source of truth + allocator (R1.5) |
| DR-06 | Server-authoritative bounded statement | **New:** replaces client-side running balance (R1.6) |
| DR-07 | Immutable declarations, no is_deleted | **Corrected:** removed soft-delete; unified reason naming (R1.7) |
| DR-08 | Migration 037 forward-only/fail-closed | **Corrected:** full preflight, no downgrade (R1.8) |
| DR-09 | No notification emission | **Corrected:** deferred until outbox designed (R1.9) |
| DR-10 | Replace client:payments:create with client:payments:declare | **Unchanged** |
| DR-11 | Financial blast radius HIGH | **Corrected:** reclassified from LOW (R1.11) |

---

## Prerequisite Blocker

**CURRENT_PRODUCT_DEFECT:** `OrderListPage.tsx:70` checks `orders:update`; `orders.py:561` requires `payments:create`.

This must be resolved before S2B implementation. The S2B cashier confirmation UI would inherit the same mismatch.

---

## Verdict

```
STOP_AND_REPORT_CTO_WITH_H3_PAYMENT_PERMISSION_PREREQUISITE
```

The design is corrected and internally consistent, but cannot proceed to implementation until:
1. The H3 permission prerequisite (frontend/backend alignment) is resolved.
2. CTO reviews the HIGH-risk canonical payment service extraction.
