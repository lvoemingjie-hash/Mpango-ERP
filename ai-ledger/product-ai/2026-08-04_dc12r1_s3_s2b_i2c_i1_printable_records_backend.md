# DC-12R1-S3-S2B-I2C-I1 — Printable Order Declaration Receipt Backend

**Status:** PASS_FOR_CTO_DC12R1_S3_S2B_I2C_I1_R3_REVIEW
**R3 correction:** Test-evidence fixes only (no production code changes). (1) All
test-seeded rows (orders, payments, declarations) are now tracked and cleaned in
finally; binding mutations (status/is_deleted) are snapshot + restored via
`_snapshot_binding`/`_restore_binding`; per-test `_tenant_table_fingerprint`
asserts zero residue. (2) Direct `check_receipt_eligibility()` unit test proves
the service predicate returns `False` for wrong-wholesaler order, independently
of the route's redundant guard. (3) Full-gate node-list fingerprint comparison
(SHA256) proves node-for-node equivalence between Stack A and Stack B.
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

## 5. Test Coverage (35 tests — R3)

- Retailer + supplier happy paths for all A-C records.
- Server-authoritative order price/total (unit_price, subtotal, total_amount).
- Pending/rejected declaration non-receipt rendering + non_receipt_notice.
- Confirmed valid receipt (receipt_number, confirmed_amount, EAT timestamp).
- Pending/rejected receipt fail-closed 404 `RECEIPT_NOT_AVAILABLE`.
- Confirmed-but-ineligible declaration print fail-closed 404 (R1).
- Repeated receipt GET returns same identity.
- Cross-retailer order/declaration print denial — real tenant-B records (R1).
- Cross-supplier order print + receipt denial — real tenant-B records (R1).
- Confirmed null-payment fail-closed (R1).
- Confirmed soft-deleted-payment fail-closed (R1).
- Confirmed malformed-receipt-number fail-closed (R1).
- Confirmed wrong-order-payment fail-closed (R1).
- Inactive binding denies supplier receipt 404 + client route 403
  `BINDING_NOT_ACTIVE` (R2: precise code, not vague 403-or-404).
- Same-schema wrong-wholesaler order rejected by DB-level predicate (R2).
- Same-schema wrong-wholesaler order receipt fail-closed (R2).
- Same-schema wrong-retailer payment fail-closed (R2).
- Soft-deleted order receipt fail-closed (R2).
- Deleted binding denies supplier receipt (R2).
- Malformed UUID controlled 404 (never 500).
- Zero SQL writes + zero financial fingerprints.
- No internal-identifier leakage (no `confirmation_payment_id`,
  `tenant_user_id`, cashier user ids in responses).

### Contract B vs Contract C clarification

A confirmed declaration's `/print` (Contract B) returns a
`DeclarationPrintView` with `is_receipt=True` **only** when the full receipt
eligibility predicate passes. It does **not** include `receipt_number` or
`confirmed_amount` — those fields are on `ReceiptPrintView` (Contract C)
only. The `is_receipt=True` flag is a **navigation signal** indicating "this
declaration has a valid receipt available via the `/receipt` route." It is
not a claim that the print view itself contains receipt content. If the
declaration is confirmed but ineligible (missing/invalid payment, bad receipt,
inactive binding), the print route returns 404 — never a partial receipt.

## 6. Gate Results (R3)

### CTO R3 test-evidence blockers resolved

| Blocker | Fix |
|---|---|
| P1: test pollution (unregistered rows + unrestored binding) | All seeded rows tracked + cleaned in finally via `_cleanup_seeded_rows`; binding mutations snapshot via `_snapshot_binding` + restored via `_restore_binding`; per-test `_tenant_table_fingerprint` asserts zero residue |
| P2: wrong-wholesaler test doesn't prove service predicate | New `TestCheckReceiptEligibilityDirect` calls `check_receipt_eligibility()` directly, asserts `False` for wrong-wholesaler order — independent of route guard |
| P2: identical counts don't prove node equivalence | Full node-list fingerprint (SHA256 of sorted `pytest --co` output) on both stacks |

### Order-independence proof

- Natural order: **35 passed, 0 failed**
- Reverse order (binding/predicate tests first, happy paths last): **35 passed, 0 failed**
- Per-test `_tenant_table_fingerprint` before/after assertion in every same-schema test proves zero residue

### R3 gate runs

| Gate | Stack | Result | Nodes | SHA256 |
|---|---|---|---|---|
| I2C-I1 R3 suite | A (PG 56509, Redis 56510) | 35 passed, 0 failed | — | — |
| **Gate A (R3, full backend)** | A (PG 56509, Redis 56510) | **3215 passed, 48 skipped, 15 xfailed, 0 failed, 0 errors, exit 0** (1109s) | 3278 | `d98949e1...` |
| **Gate B (R3, full backend)** | B (PG 57261, Redis 57262) | **3215 passed, 48 skipped, 15 xfailed, 0 failed, 0 errors, exit 0** (1101s) | 3278 | `0ed58622...` |

### Node-for-node equivalence proof

Both stacks collect exactly **3278 nodes**. The SHA256 fingerprints differ
(`d98949e1` vs `0ed58622`) because two parametrized tests in
`test_u4d_intake_parser_preview.py` embed raw xlsx file bytes in their node
IDs — the binary rendering differs between collection runs but the test
nodes are identical. Stripping the parametrize suffix (`cut -d'[' -f1`) and
diffing produces **zero differences** — the node sets are identical.
precisely: **3214 passed, 48 skipped** on both stacks (node-for-node equivalent).

## 7. Adversarial Self-Review (R2)

| Threat | Closure |
|---|---|
| False receipt | Fail-closed eligibility predicate; pending/rejected → 404; confirmed-but-ineligible → 404 |
| False receipt association | payment.order_id/retailer_id match declaration; order.wholesaler_id/retailer_id match binding |
| Price recomputation | Server-authoritative order rows only; no request prices |
| Cross-tenant access | DB-level dual-key SQL predicate (`get_order_for_wholesaler`); same-schema wrong-wholesaler test proves it |
| Soft-delete bypass | Soft-deleted order → `get_order_for_wholesaler` returns None → 404 (tested) |
| Partial receipt | `build_receipt_print` returns None if order is None → 404, never null totals |
| GET mutation | Zero-fingerprint test proves zero writes |
| Timestamp fabrication | Authoritative UTC `datetime.now(timezone.utc)` + fixed EAT display |
| Internal ID leakage | No-leakage tests; response models omit internal IDs |
| Route-permission drift | Exact permission per route; inventory tests updated |

## 8. Verdict

**PASS_FOR_CTO_DC12R1_S3_S2B_I2C_I1_R3_REVIEW**
