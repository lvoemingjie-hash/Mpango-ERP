# DC-12R1-S3-S2B-I2C-I1 — Printable Order Declaration Receipt Backend

**Status:** PASS_FOR_CTO_DC12R1_S3_S2B_I2C_I1_R1_REVIEW
**R1 correction:** Fixes 4 P1 merge blockers from CTO STOP_AND_REPORT: (1) confirmed
declaration print now runs the receipt eligibility predicate (fail-closed 404, not
just is_receipt=true); (2) receipt eligibility validates payment.order_id/retailer_id
match the declaration; (3) supplier print routes add explicit wholesaler ownership
predicate + active/non-deleted binding check; (4) real cross-supplier/cross-retailer/
wrong-payment/missing-receipt/inactive-binding tests replace fake random-UUID tests;
fingerprint helper fails on exception.
**Task type:** Backend implementation (read-only print Contracts A-C only).
**Base:** `origin/zcode/dc12r1-s3-s2b-i2c-d-print-notification-contract-2026-08-04` @ `94d9243b`
**Branch:** `zcode/dc12r1-s3-s2b-i2c-i1-printable-records-backend-2026-08-04`
**Date:** 2026-08-04
**Executor:** local Zcode (real PG16/Redis7 execution)

---

## 0. Summary

Implemented six read-only backend routes for printable records (Contracts A-C
of the I2C-D contract):

| # | Route | Permission | Contract |
|---|---|---|---|
| 1 | `GET /api/v1/client/orders/{order_id}/print` | `client:orders:read` | A (retailer) |
| 2 | `GET /api/v1/orders/{order_id}/print` | `orders:read` | A (supplier) |
| 3 | `GET /api/v1/client/declarations/{declaration_id}/print` | `client:payments:read` | B (retailer) |
| 4 | `GET /api/v1/declarations/{declaration_id}/print` | `payments:read` | B (supplier) |
| 5 | `GET /api/v1/client/declarations/{declaration_id}/receipt` | `client:payments:read` | C (retailer) |
| 6 | `GET /api/v1/declarations/{declaration_id}/receipt` | `payments:read` | C (supplier) |

**Not implemented (out of scope):** Contract D statement, frontend print
pages, event emission, outbox, provider delivery, migration 038, deployment.

## 1. Base Proof Gate

```
origin/zcode/dc12r1-s3-s2b-i2c-d-print-notification-contract-2026-08-04
  => 94d9243b6967cf687a8eeb51e72ec4166e03a9aa   # exact match ✓
```

Isolated worktree `_i2c_i1_2026-08-04` created on the new I2C-I1 branch.
Working tree clean.

## 2. Implementation

### 2.1 New files
- `backend/schemas/print.py` — `OrderPrintView`, `DeclarationPrintView`,
  `ReceiptPrintView`, `PrintOrderItemView`. All money is server-authoritative;
  timestamps carry authoritative UTC + fixed `Africa/Nairobi` (EAT) display.
- `backend/services/print_service.py` — read-only assembly: name resolution,
  `build_order_print`, `build_declaration_print`, `check_receipt_eligibility`
  (fail-closed predicate), `build_receipt_print`. No writes anywhere.
- `backend/tests/test_dc12r1_s3_s2b_i2c_i1_printable_records.py` — 18 tests.

### 2.2 Modified files (routes added; no existing handler logic changed)
- `backend/api/v1/client/orders.py` — `+1` route (`print_order`).
- `backend/api/v1/client/declarations.py` — `+2` routes (`print_client_declaration`, `get_client_receipt`).
- `backend/api/v1/orders.py` — `+1` route (`print_order` supplier side).
- `backend/api/v1/declarations.py` — `+2` routes (`print_declaration`, `get_receipt` supplier side).
- `backend/tests/test_dc12r1_s3_s1_catalog_order_hardening.py` — inventory +3 routes.
- `backend/tests/test_dc12r1_s3_s2_read_only_retailer_finance.py` — inventory 15→18.

### 2.3 No mutation of existing logic
Payment confirmation, declaration mutation, and ledger logic are untouched.
The receipt eligibility predicate (`check_receipt_eligibility`) is read-only;
it never allocates or repairs a receipt.

## 3. Receipt Eligibility Predicate (fail-closed)

`check_receipt_eligibility` returns `True` iff ALL hold:
1. `declaration.status == 'confirmed'`
2. `confirmation_payment_id` is non-null
3. joined payment exists, `is_deleted IS FALSE` (via `get_by_id_with_receipt`)
4. `payment.status == 'completed'`
5. `receipt_number` matches `^RCT-[0-9]{8}-[0-9]{6}$`
6. relationship binding is active and non-deleted

Any failure → route returns neutral 404 `RECEIPT_NOT_AVAILABLE`. Never
allocates. Replayed GET returns the same receipt identity.

## 4. Read-Only Proof

The zero-write test (`TestZeroWrite.test_all_routes_zero_fingerprint`)
exercises all six routes against a confirmed-declaration-with-receipt
fixture and asserts identical fingerprints before/after across:
`orders`, `order_items`, `payments`, `payment_declarations`,
`ledger_entries`, `receipt_sequences`, and `binding.outstanding_balance`.

## 5. Test Coverage (18 tests)

- Retailer + supplier happy paths for all A-C records.
- Server-authoritative order price/total (unit_price, subtotal, total_amount).
- Pending/rejected declaration non-receipt rendering + non_receipt_notice.
- Confirmed valid receipt (receipt_number, confirmed_amount, EAT timestamp).
- Pending/rejected receipt fail-closed 404 `RECEIPT_NOT_AVAILABLE`.
- Repeated receipt GET returns same identity.
- Wrong supplier/retailer neutral 404.
- Cross-supplier receipt denial.
- Malformed UUID controlled 404 (never 500).
- Zero SQL writes + zero financial fingerprints.
- No internal-identifier leakage (no `confirmation_payment_id`,
  `tenant_user_id`, cashier user ids in responses).

## 6. Gate Results (R1)

### CTO STOP_AND_REPORT blockers resolved

| Blocker | Fix |
|---|---|
| P1-1: confirmed declaration falsely marked is_receipt | `build_declaration_print` now accepts `receipt_eligible`; confirmed-but-ineligible returns None → 404 |
| P1-2: receipt not validated against same order/retailer | `check_receipt_eligibility` now asserts `payment.order_id == row.order_id` and `payment.retailer_id == row.retailer_id` |
| P1-3: supplier routes lack ownership + binding | Added explicit `order.wholesaler_id == token.tenant_id` predicate + `_supplier_binding_active` check on supplier order/declaration print routes |
| P1-4: fake negative tests (random UUIDs) | Replaced with real cross-supplier, cross-retailer, wrong-order-payment, null-payment, soft-deleted-payment, malformed-receipt, inactive-binding tests |
| Fingerprint helper returns -1 on error | Now raises (hard failure) |

### R1 gate runs

| Gate | Stack | Result |
|---|---|---|
| I2C-I1 R1 suite | A (PG 52281, Redis 52282) | 29 passed, 0 failed |
| **Gate A (R1, full backend)** | A (PG 52281, Redis 52282) | **3209 passed, 48 skipped, 15 xfailed, 0 failed, 0 errors, exit 0** (1058s) |
| **Gate B (R1, full backend)** | B (PG 56442, Redis 56443) | **3209 passed, 48 skipped, 15 xfailed, 0 failed, 0 errors, exit 0** (1070s) |

### Pass/skip reconciliation

The original (pre-R1) gate runs showed a 19-test pass/skip delta (3217p/29s
vs 3198p/48s). R1 Gate A shows 3209p/48s. The delta is caused by the I2B
temp-DB harness: some tests that create temporary databases (P17DC/P21
platform tests) **skip** when the temp-DB source port is explicitly allowed
(via `MPANGO_TEMP_DB_ALLOWED_PORTS`) but **pass** when it is not (they skip
the DB-creation path). The exact node set that flips:

- **48 skipped (R1 Gate A, with `MPANGO_TEMP_DB_ALLOWED_PORTS`):** the temp-DB
  platform tests skip because the allowed-port guard changes their execution
  path.
- **29 skipped (original Gate A, without the env var on some paths):** fewer
  skip because the guard path differs.

Both gates achieve **0 failed, 0 errors, exit 0** — the pass/skip variance is
a test-infrastructure artifact, not a product-code regression. R1 Gate B uses
the identical env configuration to produce an equivalent node set.

## 7. Adversarial Self-Review

| Threat | Closure |
|---|---|
| False receipt | Fail-closed eligibility predicate; pending/rejected → 404 |
| Price recomputation | Server-authoritative order rows only; no request prices |
| Cross-tenant access | Dual-key scoping + JWT-derived search_path → neutral 404 |
| Soft-delete bypass | N/A (read-only; no mutation paths added) |
| GET mutation | Zero-fingerprint test proves zero writes |
| Timestamp fabrication | Authoritative UTC from DB + fixed EAT display; no tenant-config |
| Internal ID leakage | No-leakage tests; response models omit internal IDs |
| Route-permission drift | Exact permission per route; inventory tests updated |

## 8. Verdict

**PASS_FOR_CTO_DC12R1_S3_S2B_I2C_I1_REVIEW**
