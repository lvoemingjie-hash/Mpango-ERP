# Decision Register: Retailer Payment Declaration & Cashier Confirmation (R4-R1 Final)

**Date:** 2026-07-31 (R4-R2 correction; integrates H3 baseline `0f9d259b`)
**Status:** PASS_FOR_CTO_DC12R1_S3_S2B_IMPLEMENTATION_PLANNING_R4_R2
**Supersedes:** R4-R1 DR (`8103b9bf`) — superseded
**Related:** DC-12R1-S3-S2B-D-R4-R1 contract (`ai-ledger/product-ai/2026-07-30_dc12r1_s3_s2b_payment_declaration_contract.md`)

---

## Complete Decision Register (DR-01 through DR-17)

| ID | Decision | Detail |
|---|---|---|
| DR-01 | Tenant-local storage | Declarations in `{tenant}.payment_declarations`; isolation by construction |
| DR-02 | State machine | `PENDING → CONFIRMED` (terminal); `PENDING → REJECTED` (terminal); no retailer cancellation; no expiry in MVP |
| DR-03 | Idempotent confirmation | Replay returns same declaration/payment/receipt; zero duplicate writes; FOR UPDATE + double-check; concurrent = one result |
| DR-04 | CanonicalPaymentService extraction | Transaction-level service; both `pay_order` and confirmation call it; never route-to-route; caller owns transaction |
| DR-05 | Receipt single source | `payments.receipt_number`; removed from declarations; format `RCT-YYYYMMDD-NNNNNN` UTC; `receipt_sequences.business_date CHAR(8)`; partial unique index |
| DR-06 | Server-authoritative statement | Dual-key projection; no tenant-wide `LedgerService.get_balance`; opening/closing balance DEFERRED from MVP |
| DR-07 | Immutable declarations | No `is_deleted`; FK RESTRICT on `order_id` and `confirmation_payment_id`; `reason` column unified |
| DR-08 | Migration 037 forward-only | Live tenant enum via `tenant_registrations JOIN wholesalers`; no per-tenant `alembic_version`; real catalog preflight; no downgrade |
| DR-09 | No notification emission | Deferred until transactional outbox designed |
| DR-10 | Permissions | `client:payments:declare` replaces `client:payments:create`; `payments:confirm_declaration` in `ADMIN_PERMISSIONS`; retailer_operator never gets it |
| DR-11 | Maker/checker boundary | Retailer = maker; wholesaler admin = checker; different identities by role |
| DR-12 | Declaration idempotency | `UNIQUE(retailer_id, idempotency_key)`; same retailer+key+payload=existing; different payload=409; different retailers independent |
| DR-13 | Exact 035/036 live-status-set | `("pending_email_verification", "email_verified", "provisioning", "active", "failed")`; NOT `provisioned` |
| DR-14 | transfer_reference → transaction_id | Trim; reject blank; 1–128; no truncation; widen `transaction_id` to `VARCHAR(128)`; bootstrap parity; duplicate → 409 |
| DR-15 | Canonical confirm key | `decl-confirm-{declaration_id.hex}`; never the retailer declaration idempotency key; independent namespace |
| DR-16 | Declaration vs payment key independence | Two independent idempotency namespaces; no collision; cross-retailer key reuse allowed |
| DR-17 | Partial/final confirmation lifecycle | Every confirmation = `status='completed'`; partial → `PARTIALLY_PAID`; final → `PAID`; receipt only for completed; direct `pay_order` unchanged |

---

## FIND-to-DR Mapping (Mechanical Accounting)

| FIND ID | DR ID(s) |
|---|---|
| FIND-01 | DR-04 |
| FIND-02 | DR-04 |
| FIND-03 | DR-04 |
| FIND-04 | DR-04 |
| FIND-05 | DR-06 |
| FIND-06 | DR-04 |
| FIND-07 | DR-04 |
| FIND-08 | DR-04 |
| FIND-09 | DR-10 |
| FIND-10 | DR-05 |
| FIND-11 | DR-05 |
| FIND-12 | DR-05 |
| FIND-13 | DR-07 |
| FIND-14 | DR-06 |
| FIND-15 | DR-06 |
| FIND-16 | DR-12 |
| FIND-17 | DR-12 |
| FIND-18 | DR-10 |
| FIND-19 | DR-10 |
| FIND-20 | DR-10 |
| FIND-21 | DR-10 |
| FIND-22 | DR-06 |
| FIND-23 | DR-06 |
| FIND-24 | DR-12 |
| FIND-25 | DR-02 |
| FIND-26 | DR-02 |
| FIND-27 | DR-02 |
| FIND-28 | DR-03 |
| FIND-29 | DR-02 |
| FIND-30 | DR-02 |
| FIND-31 | DR-02 |
| FIND-32 | DR-10 |
| FIND-33 | DR-08 |
| FIND-34 | DR-08 |
| FIND-35 | DR-08 |
| FIND-36 | DR-07 |
| FIND-37 | DR-09 |
| FIND-38 | DR-08 |
| FIND-39 | DR-10, DR-11 |
| FIND-40 | DR-06 |
| FIND-41 | DR-06 |
| FIND-42 | DR-04 |
| FIND-43 | DR-13 |
| FIND-44 | DR-14 |
| FIND-45 | DR-15, DR-16 |
| FIND-46 | DR-17 |

**Mechanical accounting: findings=46, unique_findings=46, mapped=46, invalid_dr_refs=0, register_csv_mismatches=0, gap=0.**

---

## Verdict

```
PASS_FOR_CTO_DC12R1_S3_S2B_IMPLEMENTATION_PLANNING_R4_R2
```
