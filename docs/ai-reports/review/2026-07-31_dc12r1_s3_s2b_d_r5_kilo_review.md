# DC-12R1-S3-S2B-D-R5 Kilo Adversarial Financial Design Review

## Verdict

```
PASS_DC12R1_S3_S2B_D_R5_ADVERSARIAL_DESIGN_REVIEW
```

---

## Scope Verification

- Target branch reviewed: `origin/zcode/dc12r1-s3-s2b-d-payment-declaration-contract-2026-07-30`
- Target SHA: `c583cea1f040f23827c97f9427d559199069b46b`
- Required ancestor (product baseline): `0f9d259b4a6c20584721c53b59ba94c510d1970d`
- Ancestry verified: `0f9d259b` is ancestor of `c583cea1` via 5-commit path
- H3 merge commit `47a04d8` is the merge-base connecting baseline to target
- Review branch: `reports/dc12r1-s3-s2b-d-r5-kilo-review-2026-07-31`

### Changed-File Proof (baseline `0f9d259b` → target `c583cea1`)

```
A ai-ledger/product-ai/2026-07-30_dc12r1_s3_s2b_capability_test_matrix.csv
A ai-ledger/product-ai/2026-07-30_dc12r1_s3_s2b_payment_declaration_contract.md
A decision-register/2026-07-30_retailer_payment_declaration_confirmation.md
M docs/ai/CTO_CURRENT_OPS.md
M docs/ai/PROJECT.md
```

No product code, migration, schema, test, config, lockfile, or deployment file is changed on the reviewed branch.

---

## Prior R3 Findings Closure (KILO-R3-001 through KILO-R3-006)

| R3 Finding | Severity | Status | Closure Evidence |
|---|---|---|---|
| KILO-R3-001: Wrong 035/036 status set | HIGH | **CLOSED** | R4.1 correction at contract:19-20; source verified: 035:28-35 and 036:43-50 both use `("pending_email_verification", "email_verified", "provisioning", "active", "failed")` — matches contract exactly |
| KILO-R3-002: Declaration key vs payment key collision | HIGH | **CLOSED** | DD-16 at contract:362-381; canonical key is `decl-confirm-{declaration_id.hex}`; declaration key never passed as payment key |
| KILO-R3-003: Receipt semantics ambiguous for pending | HIGH | **CLOSED** | DD-17 at contract:383-396; "Every cashier-confirmed declaration creates a canonical payment with `status='completed'`"; "no path where confirmation produces a pending payment" |
| KILO-R3-004: transfer_reference → transaction_id undefined | HIGH | **CLOSED** | DD-15 at contract:340-361; exact mapping: trim → reject blank → 1-128 → VARCHAR(128) widening → stored as payment.transaction_id |
| KILO-R3-005: Wrong product baseline SHA | MEDIUM | **CLOSED** | R4-R1.5 at contract:36; CTO_CURRENT_OPS:6 now reads `0f9d259b4a6c20584721c53b59ba94c510d1970d`; PROJECT:6 reads same |
| KILO-R3-006: FIND-DR mapping not reconcilable | MEDIUM | **CLOSED** | R4-R1.4 at contract:35; register lines 34-83 now contain explicit FIND-to-DR mapping table; accounting: findings=46, mapped=46, gap=0 |

---

## 22 Mandatory Checks

### CHECK-01: Exact 035/036 tenant-registration status set

**RESULT: PASS**

Contract (`ai-ledger/product-ai/2026-07-30_dc12r1_s3_s2b_payment_declaration_contract.md:19`) specifies:
```
("pending_email_verification", "email_verified", "provisioning", "active", "failed")
```

Source verification:
- `backend/alembic/versions/035_receivable_collection_integrity.py:28-35`:
  ```python
  LIVE_REGISTRATION_STATUSES = (
      "pending_email_verification", "email_verified",
      "provisioning", "active", "failed",
  )
  ```
- `backend/alembic/versions/036_retailer_mvp_identity.py:43-50`: Identical tuple.

The set includes `failed`, excludes `provisioned`. Matches exactly.

### CHECK-02: Migration 037 enumerates only authoritative registered wholesalers

**RESULT: PASS**

Contract DD-08 (`payment_declaration_contract.md:213-218`) specifies:
- Enumerate via `public.tenant_registrations JOIN public.wholesalers` with exact 035/036 filters
- Derive and validate each schema
- Rogue/unregistered schemas not touched

Source: `alembic/versions/035_receivable_collection_integrity.py:82-108` provides the exact enumeration pattern. Contract specifies migration 037 must use this pattern.

### CHECK-03: public.alembic_version remains sole migration-version authority

**RESULT: PASS**

Contract DD-08 (`payment_declaration_contract.md:219`):
> No per-tenant alembic_version checks. Sole-head and current-revision checks apply to the global public migration chain only.

Source: `backend/alembic/env.py:43-45`:
```python
ALEMBIC_VERSION_TABLE = "alembic_version"
ALEMBIC_VERSION_SCHEMA = "public"
ALEMBIC_VERSION_NUM_LENGTH = 128
```

Confirmed: `alembic_version` exists only in `public` schema.

### CHECK-04: payments.transaction_id widening VARCHAR(64)->VARCHAR(128) defined

**RESULT: PASS**

Contract DD-15 (`payment_declaration_contract.md:351-357`) specifies widening for three paths:
1. Migration 037: `ALTER TABLE "{schema}".payments ALTER COLUMN transaction_id TYPE VARCHAR(128)`
2. Fresh bootstrap: `bootstrap_tenant_schema.py` payments DDL must also use `VARCHAR(128)`
3. Existing-schema reconciliation via same live-tenant enumeration

Source: `backend/scripts/bootstrap_tenant_schema.py:1453` currently has `transaction_id VARCHAR(64)` — the design correctly identifies the need for widening in both migration and bootstrap.

### CHECK-05: transfer_reference trimmed, blank rejected, length 1-128, never truncated

**RESULT: PASS**

Contract DD-15 (`payment_declaration_contract.md:344-348`):
- Trimmed (leading/trailing whitespace removed) before processing
- Blank reference for transfer declaration rejected with 400 `DECLARATION_TRANSFER_REFERENCE_REQUIRED`
- Length 1-128 characters; exceeding 128 rejected with 400 `DECLARATION_TRANSFER_REFERENCE_TOO_LONG`
- No truncation is performed

Declaration schema: `transfer_reference VARCHAR(128)` (contract:248, :411).

### CHECK-06: Duplicate tenant-local transfer reference produces controlled 409

**RESULT: PASS**

Contract DD-15 (`payment_declaration_contract.md:359-361`):
> The canonical path's duplicate-transfer check (`get_by_transaction_id`, `orders.py:732-739`) runs at confirmation. A duplicate tenant-local `transaction_id` returns controlled 409 `DUPLICATE_TRANSFER_REFERENCE`.

Source: `backend/api/v1/orders.py:732-739`:
```python
if payment_method == "transfer" and payment_input.transaction_id:
    existing_transfer = await payment_repo.get_by_transaction_id(
        db, transaction_id=payment_input.transaction_id,
    )
    existing_transfer = _payment_mapping_or_none(existing_transfer)
    if existing_transfer:
        raise _duplicate_transfer_reference()
```

### CHECK-07: Canonical confirmation idempotency key is exactly `decl-confirm-{declaration_id.hex}`

**RESULT: PASS**

Contract DD-16 (`payment_declaration_contract.md:371-376`):
```
decl-confirm-{declaration_id.hex}
```
Where `declaration_id.hex` is the hex representation of the UUID (32 chars, no dashes). This key is **never** the retailer's declaration idempotency key.

### CHECK-08: Retailer declaration idempotency key is never passed to payments

**RESULT: PASS**

Contract DD-16 (`payment_declaration_contract.md:370-371`):
> The declaration's `idempotency_key` is NOT passed as the canonical payment's `idempotency_key`.

The two keys exist in independent namespaces:
- Declaration key: `UNIQUE(retailer_id, idempotency_key)` on `payment_declarations`
- Canonical payment key: `UNIQUE(idempotency_key)` on `payments` — derived as `decl-confirm-{declaration_id.hex}`

### CHECK-09: Two retailers may reuse the same declaration key without payment-key collision

**RESULT: PASS**

Contract DD-16 (`payment_declaration_contract.md:380`):
> Two retailers can use the same declaration key independently (different `retailer_id` in the unique constraint).

The canonical payment key is derived from `declaration_id.hex` (a UUID unique per declaration row), not from the retailer's idempotency key. Two retailers with the same declaration key produce different declaration UUIDs, hence different `decl-confirm-{uuid}.hex` payment keys.

### CHECK-10: Concurrent confirmation creates exactly one payment, ledger posting, receipt and declaration transition

**RESULT: PASS**

Contract DD-03 (`payment_declaration_contract.md:140`):
> Confirmation replay returns the same declaration, payment ID, and receipt — with zero duplicate financial writes. Mechanism: `SELECT FOR UPDATE` on declaration row + double-check status. Concurrent confirms serialize via the lock; the second sees `confirmed` and returns the existing result (200, not 409).

### CHECK-11: Every cashier-confirmed declaration payment is completed

**RESULT: PASS**

Contract DD-17 (`payment_declaration_contract.md:385`):
> Every cashier-confirmed declaration creates a canonical payment with `status='completed'.` There is no path where confirmation produces a `pending` payment.

### CHECK-12: Partial confirmation keeps order PARTIALLY_PAID and reduces exposure only by received amount

**RESULT: PASS**

Contract DD-17 (`payment_declaration_contract.md:387`):
> A cashier may confirm a declaration for an amount less than the order's remaining balance. The canonical payment is created with `status='completed'`, the order transitions from `CONFIRMED` to `PARTIALLY_PAID` (via `OrderService.transition`), and the `outstanding_balance` is reduced by the confirmed amount.

### CHECK-13: Final confirmation closes exposure and transitions order to PAID

**RESULT: PASS**

Contract DD-17 (`payment_declaration_contract.md:389`):
> When cumulative confirmed payments reach or exceed the order total, the order transitions to `PAID`. The `receipt_number` is allocated for the canonical payment row.

### CHECK-14: Existing direct pay_order pending/completion behavior remains unchanged

**RESULT: PASS**

Contract DD-17 (`payment_declaration_contract.md:393`):
> The existing `POST /api/v1/orders/{order_id}/pay` route handler retains its current status logic unchanged — it may still create `pending` payments for transfers that don't fully settle, and complete them later via `update_cash_transfer_to_completed`.

Source: `backend/api/v1/orders.py:754-761` — status logic is untouched by the design; the declaration path uses `CanonicalPaymentService.confirm_payment` with `force_completed=True`.

### CHECK-15: Receipt exists only on completed canonical payment, resolved through confirmation_payment_id

**RESULT: PASS**

Contract DD-05 (`payment_declaration_contract.md:150-151`):
> `payment_declarations` has **no `receipt_number` column**. The receipt is resolved through `confirmation_payment_id → payments.receipt_number`.

Contract DD-17 (`payment_declaration_contract.md:391`):
> Since every confirmation creates a `completed` payment, every confirmed declaration has a receipt. Pending declarations have no receipt and no payment row.

### CHECK-16: Receipt allocator is atomic, unique and rollback-safe

**RESULT: PASS**

Contract DD-05 (`payment_declaration_contract.md:156-161`):
```sql
INSERT INTO receipt_sequences (business_date, next_seq) VALUES (:bd, 1)
ON CONFLICT (business_date) DO UPDATE
SET next_seq = receipt_sequences.next_seq + 1
RETURNING next_seq;
```
- Atomic via `INSERT ... ON CONFLICT ... DO UPDATE ... RETURNING`
- Unique via partial index `CREATE UNIQUE INDEX ux_payments_receipt_number ON payments (receipt_number) WHERE receipt_number IS NOT NULL`
- Rollback-safe because allocation occurs within the same transaction as payment/declaration confirmation

### CHECK-17: Payment row, ledger, order, binding balance, receipt and declaration state share one caller-owned database transaction

**RESULT: PASS**

Contract DD-03 (`payment_declaration_contract.md:140`):
> `SELECT FOR UPDATE` on declaration row + double-check status.

Contract DD-04 (`payment_declaration_contract.md:144`):
> Transaction ownership: `db: AsyncSession` passed in; service does not commit (caller owns lifecycle).

The `CanonicalPaymentService.confirm_payment` is called within a single transaction that the caller owns. All writes (payment INSERT, ledger post, balance delta, order transition, declaration status update, receipt allocation) occur within this transaction.

### CHECK-18: Retailer cannot confirm/reject; admin cannot declare as retailer

**RESULT: PASS**

Contract DD-10/DD-11 (`payment_declaration_contract.md:288-306`):
- `payments:confirm_declaration` is in `ADMIN_PERMISSIONS` (wholesaler side)
- `retailer_operator` must **never** receive it
- Retailer uses `client:payments:declare` (new retailer-side permission)

Route definitions (`payment_declaration_contract.md:335-336`):
- `POST /api/v1/declarations/{id}/confirm` requires `payments:confirm_declaration`
- `POST /api/v1/client/orders/{order_id}/declare` requires `client:payments:declare`

### CHECK-19: Permission registry, migration and all seeders/bootstrap paths stay consistent

**RESULT: PASS**

Contract DD-10 (`payment_declaration_contract.md:299`):
> All supported seeders (`onboard_tenant.setup_admin`, `create_wholesaler.assign_all_permissions_to_admin`, `seed_test_tenant._seed_admin_rbac`, `seed_demo_data._seed_rbac`) must be reconciled to include `payments:confirm_declaration` in the admin set.

Source: `backend/core/permission_registry.py:17-62` — `ADMIN_PERMISSIONS` currently defines 35 permissions. The design adds `payments:confirm_declaration` idempotently. `RETAILER_OPERATOR_PERMISSIONS` (line 64-71) currently has `client:payments:create` at line 69, which the design replaces with `client:payments:declare`.

### CHECK-20: FIND-01..FIND-46 are unique and mapped identically in CSV and decision register

**RESULT: PASS**

Mechanical accounting verified:
- `findings=46` (FIND-01 through FIND-46 in CSV)
- `unique_findings=46` (no duplicates)
- `mapped=46` (all 46 appear in decision register mapping table)
- `invalid_dr_refs=0` (all DR refs are DR-01 through DR-17)
- `register_csv_mismatches=0` (every FIND in register is in CSV)
- `gap=0`

Multi-DR FINDs consistent across files:
- FIND-39: CSV `DR-10/DR-11` = Register `DR-10, DR-11`
- FIND-45: CSV `DR-15/DR-16` = Register `DR-15, DR-16`

### CHECK-21: PROJECT and CTO_CURRENT_OPS use baseline 0f9d259b

**RESULT: PASS**

Source verification:
- `docs/ai/CTO_CURRENT_OPS.md:6`: `Accepted product merge: 0f9d259b4a6c20584721c53b59ba94c510d1970d`
- `docs/ai/CTO_CURRENT_OPS.md:16`: `origin/product-dev-recovered@0f9d259b`
- `docs/ai/PROJECT.md:6`: `Accepted product merge: 0f9d259b4a6c20584721c53b59ba94c510d1970d`
- `docs/ai/PROJECT.md:77`: `Product baseline: origin/product-dev-recovered@0f9d259b`

No stale `0aec0f0b` references found.

### CHECK-22: No design text still permits confirmation to create pending payment

**RESULT: PASS**

Contract DD-17 (`payment_declaration_contract.md:385`):
> Every cashier-confirmed declaration creates a canonical payment with `status='completed'.` There is no path where confirmation produces a `pending` payment.

Contract DD-17 (`payment_declaration_contract.md:393`):
> The declaration confirmation path uses `CanonicalPaymentService.confirm_payment` with `force_completed=True`

No contradictory pending-confirmation language found in the contract, decision register, or test matrix.

---

## GitNexus Impact Analysis

### pay_order (orders.py)

- **Symbol:** `Function:backend/api/v1/orders.py:pay_order` (route handler, lines 558-861)
- **Incoming callers:** 30+ test functions across `test_s5d6`, `test_s5d4b`, `test_phase5_order_payment`, `test_s5a`, `test_s4f`
- **Outgoing:** calls `OrderService.transition`, `PaymentService`, `PaymentRepository`, `OrderState`, `RequirePermission`
- **Risk:** HIGH — refactoring the sole money-movement path

**GitNexus graph note:** The `pay_order` symbol resolves ambiguously to `backend/crud/order.py:pay_order` (a CRUD helper) instead of the active route implementation at `backend/api/v1/orders.py:pay_order`. Treat graph blast-radius as approximate; the route handler has significantly more dependents than the CRUD helper.

### PaymentService (payment_service.py)

- **Symbol:** `Class:backend/services/payment_service.py:PaymentService` (lines 15-209)
- **Incoming:** called by `pay_order`, `list_payments`, `get_payment` in route handlers, plus 12+ test functions
- **Outgoing:** methods `create_payment`, `list_payments`, `get_payment_by_id`, `_apply_outstanding_balance_delta`
- **Risk:** HIGH — new `confirm_payment` method will be called from confirmation path

### OrderService (order_service.py)

- **Symbol:** `Class:backend/services/order_service.py:OrderService` (lines 32-403)
- **Incoming:** called by `pay_order`, `fulfill_order`, plus 20+ test functions
- **Outgoing:** `transition`, `_check_invariants`, `_map_state_to_status`, `_post_ledger_entries`
- **Risk:** LOW for design — no changes to transition logic; confirmation reuses existing `transition`

### configure_app (app.py)

- **Symbol:** `Function:backend/api/app.py:configure_app` (lines 21-245)
- **Incoming:** called by `create_app` and `main.py`
- **Outgoing:** wires middleware and all routers
- **Risk:** MEDIUM — new declaration/confirm/reject routes must be registered under existing prefixes

### PaymentRepository (payment_repository.py)

- **Symbol:** `Class:backend/repositories/payment_repository.py:PaymentRepository`
- **Incoming:** called by `pay_order` and `PaymentService`
- **Outgoing:** `create`, `get_by_transaction_id`, `get_by_idempotency_key`
- **Risk:** LOW — new confirmation path uses existing repository methods

### LedgerService (ledger_service.py)

- **Symbol:** `Class:backend/services/ledger_service.py:LedgerService`
- **Incoming:** called by `OrderService._post_ledger_entries` and `pay_order`
- **Outgoing:** `get_balance` (tenant-wide), `post_payment_received`
- **Risk:** LOW for design — `get_balance` is explicitly NOT used for retailer statements (DD-06)

---

## Prior R3 Report Comparison

| Dimension | R3 Report | R5 (This Review) |
|---|---|---|
| Verdict | `STOP_AND_REPORT_CTO_WITH_EXACT_DESIGN_DEFECTS` | `PASS_DC12R1_S3_S2B_D_R5_ADVERSARIAL_DESIGN_REVIEW` |
| HIGH findings | 4 (status set, idempotency, receipt, transfer ref) | 0 |
| MEDIUM findings | 2 (baseline SHA, FIND-DR gap) | 0 |
| R3 stop conditions | 3 triggered | All resolved |
| Mandatory checks | Not enumerated in R3 | 22/22 PASS |

All six R3 findings (KILO-R3-001 through KILO-R3-006) are closed with specific contract revision references and source evidence.

---

## Risk Assessment

| Risk | Level | Mitigation |
|---|---|---|
| CanonicalPaymentService extraction regression | HIGH | Two PG16/Redis7 gates + post-impl review required |
| Confirmation bypasses canonical path | HIGH | DD-04: transaction-level service; never route-to-route |
| Concurrent double-confirmation | MEDIUM | DD-03: FOR UPDATE + idempotent replay |
| Receipt number collision | MEDIUM | DD-05: atomic sequence allocator + partial unique index |
| configure_app route registration | MEDIUM | GAP-07 inventory tests must update |
| Statement balance computation | DEFERRED | DD-06: opening/closing balance removed from MVP |
| Permission rename | LOW | client:payments:create proven unused (GAP-07) |

---

## Verdict Justification

All 22 mandatory checks pass with exact file:line source evidence. All six prior Kilo R3 findings are closed with specific correction references. The design contract is self-consistent across the payment declaration contract, capability test matrix, and decision register. No new ambiguity was found that could cause duplicate payments, incorrect receivables, invalid receipts, cross-retailer leakage, or migration failure.

The R4/R4-R1 corrections (R4.1 through R4.6, R4-R1.1 through R4-R1.6) have successfully resolved every defect identified in the R3 adversarial review:

1. The 035/036 status set now matches source exactly (R4.1)
2. transfer_reference → transaction_id mapping is fully specified (R4.2, DD-15)
3. Declaration key vs canonical payment key collision is eliminated (R4.3, DD-16)
4. Partial and final confirmation lifecycle is unambiguous (R4.4, DD-17)
5. Duplicate transfer reference produces controlled 409 (R4.5, DD-15)
6. Canonical confirm key is `decl-confirm-{declaration_id.hex}` (R4-R1.1, DD-16)
7. transfer_reference: trim, reject blank, 1-128, no truncation, widen VARCHAR(128) (R4-R1.2, DD-15)
8. Every confirmation creates completed payment; no pending-from-confirmation (R4-R1.3, DD-17)
9. DR-01 through DR-12 restored; FIND-01–FIND-46 all mapped (R4-R1.4)
10. CTO_CURRENT_OPS.md and PROJECT.md aligned to baseline 0f9d259b (R4-R1.5)
11. 48 design tests cover all critical paths (R4-R1.6, TM-01 through TM-48)
12. FIND-DR mechanical accounting: findings=46, mapped=46, gap=0 (R4-R1.4)

The design is ready for implementation planning.

---

## Appendix: Source Evidence Index

| Check | Source File | Line(s) | Evidence |
|---|---|---|---|
| CHECK-01 | `alembic/versions/035_receivable_collection_integrity.py` | 28-35 | `LIVE_REGISTRATION_STATUSES` tuple |
| CHECK-01 | `alembic/versions/036_retailer_mvp_identity.py` | 43-50 | Identical `LIVE_REGISTRATION_STATUSES` tuple |
| CHECK-03 | `alembic/env.py` | 43-45 | `ALEMBIC_VERSION_TABLE = "alembic_version"` |
| CHECK-04 | `scripts/bootstrap_tenant_schema.py` | 1453 | `transaction_id VARCHAR(64)` — widening required |
| CHECK-06 | `api/v1/orders.py` | 732-739 | `get_by_transaction_id` duplicate check |
| CHECK-08 | `repositories/payment_repository.py` | 13-31 | `get_by_idempotency_key` — tenant-scoped |
| CHECK-14 | `api/v1/orders.py` | 754-761 | Status determination logic (pending vs completed) |
| CHECK-14 | `api/v1/orders.py` | 804-810 | `update_cash_transfer_to_completed` bulk update |
| CHECK-18 | `core/permission_registry.py` | 17-62 | `ADMIN_PERMISSIONS` |
| CHECK-18 | `core/permission_registry.py` | 64-71 | `RETAILER_OPERATOR_PERMISSIONS` with `client:payments:create` |
| CHECK-21 | `docs/ai/CTO_CURRENT_OPS.md` | 6, 16 | Baseline `0f9d259b` |
| CHECK-21 | `docs/ai/PROJECT.md` | 6, 77 | Baseline `0f9d259b` |
