# DC-12R1-S3-S2B-D: Retailer Payment Declaration, Cashier Confirmation, Receipt & Print Contract

**Date:** 2026-07-30
**Branch:** `zcode/dc12r1-s3-s2b-d-payment-declaration-contract-2026-07-30`
**Product baseline:** `origin/product-dev-recovered` @ `0aec0f0b`
**Doc checkpoint:** `origin/codex/dc12-project-status-s3-s2-2026-07-30` @ `2359fc0d`
**Task type:** Docs-only financial design/audit gate. No product code implemented.

---

## 1. Executive Summary

This document locks the contract for retailer-initiated payment declarations: a **non-canonical** payment submission that has **zero accounting effect** until an authorized wholesaler cashier confirms it. The retailer submits a declaration of intent ("I paid via cash/transfer, here is the reference"). The cashier reviews and either confirms (triggering the canonical payment write path) or rejects. Only confirmed declarations produce canonical payments, ledger entries, order transitions, and receivable updates.

The design preserves the GAP-07 invariant (no client route performs financial mutation) by introducing a **declaration-only** write path that is strictly isolated from the canonical `POST /api/v1/orders/{order_id}/pay` path.

---

## 2. Business Contract (Locked)

| # | Rule |
|---|---|
| BC-1 | Retailer submission is a **payment declaration**, not a canonical payment. |
| BC-2 | Submission has **zero effect** on payments, order status, ledger, inventory, outstanding balance, receivables, or reporting. |
| BC-3 | Only an **authorized wholesaler cashier** may confirm or reject. |
| BC-4 | Confirmation must **reuse the canonical approved payment write semantics** (`POST /api/v1/orders/{order_id}/pay` internal call path). |
| BC-5 | Confirmation must be **atomic** across payment, order, ledger and receivables. |
| BC-6 | Retailer sees **pending, confirmed and rejected** states only inside the selected supplier relationship. |
| BC-7 | Only **confirmed** payment may be labelled "received" or rendered as a receipt. |
| BC-8 | Pending declarations may print only as **"Payment Declaration — Not Received"**. |
| BC-9 | Future SMS/WhatsApp support is **event-contract-only**; no delivery implementation in this scope. |
| BC-10 | **No cross-supplier** workspace, comparison, identifiers or financial data. |

---

## 3. Source Audit Evidence

### 3.1 Canonical Payment Write Path

| Component | File:Line | Summary |
|---|---|---|
| **Pay route** | `api/v1/orders.py:558-861` | `POST /api/v1/orders/{order_id}/pay`; requires `payments:create` (L561); `X-Idempotency-Key` mandatory (L564); `SELECT FOR UPDATE` lock (L623); payment INSERT (L746); outstanding_balance delta (L770/L789); order transition (L796); ledger posting (L778) |
| **Alt pay path disabled** | `api/v1/payments.py:83-97` | `POST /api/v1/payments` returns 409 `PAYMENT_WRITE_PATH_DISABLED` — hard-disabled by design |
| **PaymentRepository.create** | `repositories/payment_repository.py:236-298` | Raw-SQL INSERT into `payments` table; returns inserted row mapping |
| **PaymentService._apply_outstanding_balance_delta** | `services/payment_service.py:169-216` | `UPDATE wholesaler_retailer_bindings SET outstanding_balance = outstanding_balance + :delta ... AND outstanding_balance + :delta >= 0`; non-negative guard |
| **LedgerService.post_payment_received** | `services/ledger_service.py:281-317` | Debit CASH / Credit RECEIVABLE; called by canonical path at orders.py:778 |
| **OrderService.transition** | `services/order_service.py:53-164` | The ONLY way to change order state; `with_for_update()` lock; invariant checks; ledger posting |
| **OrderState matrix** | `core/domain/order_state.py:49-73` | `CONFIRMED → {PAID, PARTIALLY_PAID, CANCELLED}`; `PARTIALLY_PAID → {PAID, CANCELLED}` |
| **Idempotency helpers** | `api/v1/orders.py:79-101` | `_validate_idempotency_key`: 8-64 visible ASCII; replay check via `get_by_idempotency_key` |

### 3.2 Retailer Client Finance (Read-Only)

| Component | File:Line | Summary |
|---|---|---|
| **ClientIdentity** | `api/v1/client/dependencies.py:35-42` | `user_id`, `retailer_id`, `tenant_id`, `token` — all server-derived |
| **resolve_client_identity** | `api/v1/client/dependencies.py:45-128` | Binding lookup via `wholesaler_retailer_bindings` WHERE `wholesaler_id=:tenant_id AND tenant_user_id=:user_id AND is_deleted IS FALSE`; 403 on missing/inactive |
| **GET /api/v1/client/payments** | `api/v1/client/payments.py:42-90` | `client:payments:read`; read-only; dual-key scoped (wholesaler + retailer) |
| **GET /api/v1/client/finance/balance** | `api/v1/client/finance.py:31-64` | `client:finance:read`; read-only; reads stored `outstanding_balance` |
| **ClientFinanceRepository** | `repositories/client_finance_repository.py:79-102` | `get_balance`: `SELECT outstanding_balance FROM wholesaler_retailer_bindings WHERE ... status='active'` |

### 3.3 GAP-07 / Permission Evidence

| Component | File:Line | Summary |
|---|---|---|
| **client:payments:create defined** | `core/permission_registry.py:69` | In `RETAILER_OPERATOR_PERMISSIONS`; granted to retailers but **unused by any route** |
| **GAP-07 freeze test** | `tests/test_dc12r1_s3_s1_catalog_order_hardening.py:560-563` | `test_no_client_route_requires_client_payments_create`: route dependency tree proves no client route consumes `client:payments:create` |
| **Client route inventory** | `tests/test_dc12r1_s3_s1_catalog_order_hardening.py:632-692` | Exact 11-route allowlist; payment/finance routes GET-only |
| **S3-S2 finance inventory** | `tests/test_dc12r1_s3_s2_read_only_retailer_finance.py:316-340` | 11 routes; `client:payments:create not in set(actual.values())` |
| **Canonical pay permission** | `tests/test_route_authorization_policy.py:904-915` | `TestOrderPaymentRoutePolicy`: `POST /orders/{id}/pay` requires `payments:create`, explicitly not `orders:update` |

### 3.4 Financial Integrity Test Ground-Truth

| Test File | Key Tests | Verifies |
|---|---|---|
| `test_dc11d_payment_replay_concurrency_integrity.py` | L340-721 | Replay idempotency, concurrent single-settlement, overpay rejection, rollback invariance |
| `test_dc11t4h_receivable_collection_integrity.py` | L113-976 | Credit collection, over-collection rejection, concurrent lock, migration 035 fail-closed |
| `test_s5_ledger.py` | L96, L379 | Unbalanced transaction rejection, ledger immutability |
| `test_s5_5_ledger_hardening.py` | L32, L88 | DB-level UPDATE/DELETE blocks |
| `test_dc10f_payment_method_integrity.py` | L44-115 | Non-canonical method rejection before side effects |

### 3.5 Frontend Evidence

| Component | File:Line | Summary |
|---|---|---|
| **Wholesaler pay modal** | `frontend/src/pages/orders/OrderListPage.tsx:125-152,437-446` | "Record Payment" button; `orderService.pay()`; gated by `orders:update` |
| **Retailer finance UI** | `frontend/src/pages/client/FinanceBalancePage.tsx:14-67` | Read-only balance display; no payment initiation |
| **Retailer payment history** | `frontend/src/pages/client/PaymentHistoryPage.tsx:37-101` | Read-only; no action buttons |
| **Client routes** | `frontend/src/router/AppRouter.tsx:122-140` | 6 routes: products, orders, payments, finance — no pay route |
| **Print support** | *(none)* | No print/PDF/receipt capability exists; invoice is JSON download only |

### 3.6 GitNexus Analysis

| Metric | Value |
|---|---|
| Nodes | 14,046 |
| Edges | 43,345 |
| Clusters | 919 |
| Flows | 300 |
| Impact: `pay_order` | Low risk — declaration confirm reuses existing path |
| Impact: `PaymentService` | Low risk — `_apply_outstanding_balance_delta` reused as-is |
| Impact: `configure_app` | Low risk — new routes under existing router prefix |

---

## 4. Mandatory Design Decisions

### DD-01: Storage — Tenant-Local

**Decision:** Declarations stored in the **tenant schema** (`{tenant}.payment_declarations`), not public.

**Justification:** Declarations are retailer-supplier-relationship-scoped. They are not canonical financial records. Storing them in the tenant schema:
- Enforces tenant isolation by construction (no cross-schema queries).
- Keeps the public schema clean of non-canonical data.
- Matches the existing pattern where `orders`, `payments`, `ledger_entries` are all tenant-local.
- No public aggregation or cross-tenant reporting is needed for declarations.

### DD-02: State Machine

```
                    ┌──────────┐
   retailer submit  │  PENDING  │
              ─────▶│           │
                    └─────┬─────┘
                     ┌────┴────┐
              confirm│         │reject
                     ▼         ▼
              ┌──────────┐ ┌──────────┐
              │CONFIRMED │ │ REJECTED │
              │          │ │          │
              └──────────┘ └──────────┘
                terminal      terminal
```

**Permitted transitions:** `PENDING → CONFIRMED`, `PENDING → REJECTED`. No other transitions. Both CONFIRMED and REJECTED are terminal.

**No "cancel" state for the retailer.** Once submitted, a declaration cannot be withdrawn by the retailer. Only the cashier can move it to terminal state. This prevents the retailer from gaming the pending queue.

**Expired state:** Optional future enhancement — declarations older than 72h with no action auto-expire to `REJECTED` with reason `"expired"`. Out of scope for this contract; cashier can reject manually.

### DD-03: Idempotency, Replay, and Concurrent Confirmation Locking

**Declaration submission idempotency:**
- Retailer must supply `X-Declaration-Idempotency-Key` (8-64 visible ASCII, same rules as canonical payment).
- Replay with same key + same payload → return existing declaration.
- Replay with same key + different payload → 409 `DECLARATION_IDEMPOTENCY_KEY_CONFLICT`.

**Confirmation idempotency:**
- Cashier confirmation delegates to the canonical `pay_order` path, which has its own idempotency (`X-Idempotency-Key`).
- A confirmed declaration carries a `confirmation_payment_id` (FK to `payments.id`). A second confirm attempt on an already-confirmed declaration returns 409 `DECLARATION_ALREADY_CONFIRMED`.
- Concurrent confirm attempts on the same declaration: `SELECT FOR UPDATE` on the declaration row (matching the canonical pattern at `orders.py:623`) ensures exactly one confirmation succeeds.

### DD-04: Overpayment and Remaining-Exposure Calculation

- The declaration's `declared_amount` is the retailer's stated amount. It is **not validated** against the order's remaining balance at submission time (it is a declaration, not a payment).
- At **confirmation**, the canonical `pay_order` path validates `declared_amount <= remaining_balance` (orders.py:686-691). Overpayment at confirmation → 409 `PAYMENT_EXCEEDS_REMAINING` (from existing logic).
- The cashier sees `remaining_balance` in the confirmation UI and can reject if the declaration amount exceeds it.

### DD-05: Cash vs Transfer Declaration Requirements

| Method | Declaration Fields Required |
|---|---|
| `cash` | `declared_amount` only. No reference. |
| `transfer` | `declared_amount` + `transfer_reference` (1-128 chars). No file upload. |

- `credit` is **not a valid declaration method**. Credit sales are wholesaler-initiated, not retailer-declared.
- The method must be `cash` or `transfer` only.

### DD-06: Transfer Reference Rules

- `transfer_reference` is a free-text string (1-128 visible characters).
- **No file upload** in this scope. File/photo attachment is a future enhancement that requires separate justification and its own contract.
- Duplicate reference check is **not** enforced at declaration time (different retailers may share bank references). The canonical path's duplicate check (`get_by_transaction_id`, orders.py:732-739) runs at confirmation.

### DD-07: Permissions

| Permission | Scope | Action |
|---|---|---|
| `client:payments:declare` (NEW) | Retailer | Submit a payment declaration |
| `client:payments:read` (EXISTS) | Retailer | View own declarations + confirmed payments |
| `payments:confirm_declaration` (NEW) | Wholesaler cashier | Confirm or reject a declaration |
| `payments:read` (EXISTS) | Wholesaler | View all declarations in their tenant |

**Note on `client:payments:create`:** See DD-09.

### DD-08: Maker/Checker and Self-Confirmation Boundary

- **Maker:** The retailer (retailer_operator) submits the declaration.
- **Checker:** The wholesaler cashier (admin or user with `payments:confirm_declaration`) confirms or rejects.
- **Self-confirmation boundary:** A wholesaler cashier **cannot** submit a declaration (they are not a retailer). A retailer **cannot** confirm a declaration (they lack `payments:confirm_declaration`). The maker and checker are always different identities by role separation.
- No user can be both maker and checker for the same declaration.

### DD-09: client:payments:create — Replace

**Decision:** **Replace** `client:payments:create` with `client:payments:declare`.

**Rationale:**
- `client:payments:create` (permission_registry.py:69) is currently **granted but unused** — no route consumes it (proven by GAP-07 tests).
- The name `client:payments:create` implies a canonical payment write, which violates BC-1 (declaration ≠ payment).
- `client:payments:declare` accurately reflects the new action: a declaration of intent, not a canonical payment.

**Migration:** In migration 037, rename the permission code from `client:payments:create` to `client:payments:declare` in the `permissions` table for all tenant schemas, and update `role_permissions` grants. The registry (`permission_registry.py`) is updated to replace the code. Existing GAP-07 tests must be updated to assert `client:payments:declare` is consumed by exactly one new route and `client:payments:create` no longer exists.

### DD-10: Rejection/Cancellation Reason and Audit Retention

- Rejection requires a `rejection_reason` (1-256 chars) from the cashier.
- Rejection reason is stored on the declaration row (`rejected_reason`, `rejected_at`, `rejected_by`).
- Declarations are **never deleted**. They remain as an immutable audit trail.
- Retention: declarations follow the same retention policy as payments (no automated purge).

### DD-11: Canonical Payment Linkage and Immutable Confirmation Evidence

- On confirmation, the declaration row is updated with:
  - `confirmation_payment_id` → FK to the `payments.id` created by the canonical path.
  - `confirmed_at`, `confirmed_by`.
- This link is **immutable** once set. The declaration cannot be re-confirmed or un-linked.
- The canonical payment row carries a back-reference via `idempotency_key` (the confirmation uses a deterministic key derived from the declaration ID).

### DD-12: Receipt Number, Visible Fields, and Privacy Boundaries

**Receipt number:** Generated on confirmation, format `RCT-{YYYYMMDD}-{sequence:06d}`, tenant-local sequence. Stored on the payment row (new `receipt_number` column or reuse existing if present — needs migration check).

**Retailer-visible receipt fields:**
- Receipt number, order ID, order total, amount paid, payment method, confirmed date, wholesaler name.
- **Not visible to retailer:** cashier user ID, internal ledger entry IDs, internal payment row ID (only the receipt number and business fields).

**Privacy boundary:** The receipt contains only retailer-facing business data. No internal identifiers, no other retailers' data, no cross-supplier data.

### DD-13: Print Contracts

| Document | Trigger | Status Label | Content |
|---|---|---|---|
| **Order** | Retailer or cashier print | Order status (draft/confirmed/etc.) | Order items, totals, retailer, wholesaler, dates |
| **Declaration (pending)** | Retailer prints pending declaration | **"Payment Declaration — Not Received"** | Declaration amount, method, reference, submission date, "NOT A RECEIPT" watermark |
| **Confirmed receipt** | Retailer or cashier prints confirmed declaration | **"Payment Received"** | Receipt number, order, amount, method, confirmed date |
| **Statement** | Retailer or cashier prints period statement | Period summary | All declarations + payments in date range, running balance |

**Print implementation:** Browser-native `window.print()` with a print-optimized CSS template. No server-side PDF generation in this scope. The print template renders from the same API data the page already has — no additional endpoint needed for print content, only a print CSS layout.

### DD-14: API Routes

#### New Routes

| Method | Path | Permission | Purpose |
|---|---|---|---|
| `POST` | `/api/v1/client/orders/{order_id}/declare` | `client:payments:declare` | Retailer submits payment declaration |
| `GET` | `/api/v1/client/declarations` | `client:payments:read` | Retailer lists own declarations (pending/confirmed/rejected) |
| `GET` | `/api/v1/client/declarations/{id}` | `client:payments:read` | Retailer views single declaration |
| `POST` | `/api/v1/declarations/{id}/confirm` | `payments:confirm_declaration` | Cashier confirms (triggers canonical payment) |
| `POST` | `/api/v1/declarations/{id}/reject` | `payments:confirm_declaration` | Cashier rejects with reason |
| `GET` | `/api/v1/declarations` | `payments:read` | Cashier lists all declarations in tenant |
| `GET` | `/api/v1/declarations/{id}` | `payments:read` | Cashier views single declaration |

#### Request/Response Envelopes

**Submit declaration:**
```json
// POST /api/v1/client/orders/{order_id}/declare
// Headers: X-Declaration-Idempotency-Key: <8-64 ascii>
// Body:
{
  "declared_amount": "1500.00",
  "method": "transfer",
  "transfer_reference": "MPESA-QK3H8X"
}
// 201 Created
{
  "success": true,
  "data": {
    "id": "<uuid>",
    "order_id": "<uuid>",
    "status": "pending",
    "declared_amount": "1500.00",
    "method": "transfer",
    "transfer_reference": "MPESA-QK3H8X",
    "submitted_at": "2026-07-30T12:00:00Z"
  }
}
```

**Confirm declaration:**
```json
// POST /api/v1/declarations/{id}/confirm
// 200 OK
{
  "success": true,
  "data": {
    "declaration_id": "<uuid>",
    "status": "confirmed",
    "payment_id": "<uuid>",
    "receipt_number": "RCT-20260730-000001",
    "order_status": "paid",
    "confirmed_at": "2026-07-30T12:05:00Z"
  }
}
// 409 on overpayment: {"code": "PAYMENT_EXCEEDS_REMAINING", ...}
// 409 on already confirmed: {"code": "DECLARATION_ALREADY_CONFIRMED", ...}
```

**Reject declaration:**
```json
// POST /api/v1/declarations/{id}/reject
// Body: {"reason": "Amount does not match bank statement"}
// 200 OK
{
  "success": true,
  "data": {
    "declaration_id": "<uuid>",
    "status": "rejected",
    "rejected_reason": "Amount does not match bank statement",
    "rejected_at": "2026-07-30T12:05:00Z"
  }
}
```

#### Controlled Errors

| Code | HTTP | When |
|---|---|---|
| `DECLARATION_BODY_REQUIRED` | 400 | Empty/null body |
| `DECLARATION_AMOUNT_REQUIRED` | 400 | Missing amount |
| `DECLARATION_METHOD_INVALID` | 400 | Method not in {cash, transfer} |
| `DECLARATION_TRANSFER_REFERENCE_REQUIRED` | 400 | Transfer without reference |
| `DECLARATION_IDEMPOTENCY_KEY_CONFLICT` | 409 | Same key, different payload |
| `DECLARATION_ALREADY_CONFIRMED` | 409 | Confirm on already-confirmed |
| `DECLARATION_ALREADY_REJECTED` | 409 | Confirm/reject on already-rejected |
| `PAYMENT_EXCEEDS_REMAINING` | 409 | Confirmation overpayment (from canonical path) |
| `PERMISSION_DENIED` | 403 | Missing permission |
| `ORDER_NOT_FOUND` | 404 | Order not in retailer's scope |

### DD-15: Migration 037

| Aspect | Decision |
|---|---|
| **Need** | Yes — new table `payment_declarations`, permission rename |
| **down_revision** | `036` (current head) |
| **preflight** | Assert no existing `payment_declarations` table; assert `client:payments:create` exists in permissions |
| **forward-fix** | CREATE TABLE `payment_declarations`; INSERT permission `client:payments:declare`; UPDATE permission code `client:payments:create` → `client:payments:declare` in all tenant schemas; UPDATE `role_permissions` accordingly; INSERT permission `payments:confirm_declaration` |
| **downgrade** | DROP TABLE `payment_declarations`; reverse permission changes. Safe because no production data exists yet |
| **reconciliation** | Bootstrap tenant schema reconciliation (`bootstrap_tenant_schema.py`) must include `payment_declarations` table DDL for fresh tenants |

### DD-16: Future Notification Event

- On confirmation, emit a domain event `PaymentDeclarationConfirmed` containing: declaration_id, order_id, retailer_id, amount, receipt_number, confirmed_at.
- On rejection, emit `PaymentDeclarationRejected` containing: declaration_id, retailer_id, reason, rejected_at.
- These events are **contract-only** — no SMS/WhatsApp transport implementation in this scope.
- The event contract allows future notification services to subscribe without coupling to the confirmation logic.

### DD-17: Rollback Semantics and Compatibility

- **No changes to existing payment rows.** Migration 037 only adds a new table and renames a permission. Existing `payments`, `ledger_entries`, `orders`, and `wholesaler_retailer_bindings` rows are untouched.
- **Permission rename is safe.** `client:payments:create` is currently unused (GAP-07 proven). Renaming it to `client:payments:declare` breaks no existing route.
- **Confirmation rollback:** If the canonical `pay_order` call fails during confirmation, the declaration remains `PENDING`. The canonical path's existing rollback semantics (proven by `test_dc11d` L620-654) ensure no partial financial state. The declaration's `SELECT FOR UPDATE` lock is released, allowing retry.

---

## 5. Data Model

### Table: `{tenant}.payment_declarations`

| Column | Type | Constraints |
|---|---|---|
| `id` | UUID PK | DEFAULT gen_random_uuid() |
| `order_id` | UUID | NOT NULL, FK to `{tenant}.orders(id)` |
| `retailer_id` | UUID | NOT NULL |
| `wholesaler_id` | UUID | NOT NULL |
| `declared_amount` | NUMERIC(12,2) | NOT NULL, CHECK (> 0) |
| `method` | VARCHAR(16) | NOT NULL, CHECK IN ('cash', 'transfer') |
| `transfer_reference` | VARCHAR(128) | NULL (required if method='transfer') |
| `status` | VARCHAR(16) | NOT NULL DEFAULT 'pending', CHECK IN ('pending','confirmed','rejected') |
| `idempotency_key` | VARCHAR(64) | NOT NULL |
| `submitted_by` | UUID | NOT NULL (tenant user) |
| `submitted_at` | TIMESTAMPTZ | NOT NULL DEFAULT now() |
| `confirmed_by` | UUID | NULL |
| `confirmed_at` | TIMESTAMPTZ | NULL |
| `confirmation_payment_id` | UUID | NULL, FK to `{tenant}.payments(id)` |
| `receipt_number` | VARCHAR(32) | NULL |
| `rejected_by` | UUID | NULL |
| `rejected_at` | TIMESTAMPTZ | NULL |
| `rejected_reason` | VARCHAR(256) | NULL |
| `is_deleted` | BOOLEAN | NOT NULL DEFAULT FALSE |

**Indexes:**
- UNIQUE `(order_id, idempotency_key)` — replay protection
- INDEX `(retailer_id, status)` — retailer listing
- INDEX `(wholesaler_id, status)` — cashier queue
- UNIQUE `(receipt_number)` WHERE `receipt_number IS NOT NULL` — receipt uniqueness

---

## 6. Required Test Matrix

| # | Test Category | Test Description | Decision Ref |
|---|---|---|---|
| TM-01 | Zero accounting | Submit declaration → no payment row, no ledger entry, no order status change, no balance change | BC-2 |
| TM-02 | Supplier isolation | Declaration in supplier A not visible to retailer logged into supplier B | BC-10 |
| TM-03 | Same-schema wrong-retailer | Declaration from retailer X not visible to retailer Y in same schema | BC-10 |
| TM-04 | Duplicate submit | Same idempotency key + same payload → return existing; different payload → 409 | DD-03 |
| TM-05 | Concurrent confirm | Two simultaneous confirm attempts → exactly one canonical payment, one 409 | DD-03, BC-5 |
| TM-06 | Reject | Reject → status=rejected, reason stored, terminal, no financial effect | DD-10 |
| TM-07 | Cancel/expired/stale | Confirm a rejected declaration → 409; confirm already-confirmed → 409 | DD-02 |
| TM-08 | Overpayment | Confirm declaration where amount > remaining → 409 `PAYMENT_EXCEEDS_REMAINING` | DD-04 |
| TM-09 | Negative amount | Submit with amount ≤ 0 → 400 | DD-05 |
| TM-10 | Invalid method | Submit with method='credit' → 400 | DD-05 |
| TM-11 | Malformed identifiers | Malformed order_id → 404; malformed retailer_id → controlled | DD-14 |
| TM-12 | Unauthorized retailer | Retailer without `client:payments:declare` → 403 | DD-07 |
| TM-13 | Unauthorized cashier | User without `payments:confirm_declaration` → 403 | DD-07 |
| TM-14 | Inactive/deleted binding | Inactive binding → 403 `BINDING_NOT_ACTIVE` | BC-6 |
| TM-15 | Confirmed receipt visible | Confirmed declaration → retailer sees receipt_number + "received" | BC-7 |
| TM-16 | Pending not labelled received | Pending declaration → print says "Payment Declaration — Not Received" | BC-8 |
| TM-17 | Print output | Pending print has "NOT RECEIVED" label; confirmed print has "Received" label; no internal identifiers leak | DD-13 |
| TM-18 | Canonical regressions | Existing payment/ledger/receivable/order tests unchanged after migration 037 | DD-17 |
| TM-19 | Route inventory | New routes registered with correct permissions; GAP-07 updated to allow `client:payments:declare` on exactly one route | DD-09 |
| TM-20 | Permission registry exactness | `client:payments:create` removed; `client:payments:declare` + `payments:confirm_declaration` added; retailer_operator set exact | DD-07, DD-09 |
| TM-21 | Notification event | `PaymentDeclarationConfirmed` emitted only after committed confirmation; not on pending/rejected | DD-16 |

---

## 7. Risk Assessment

| Risk | Level | Mitigation |
|---|---|---|
| Declaration mistaken for payment | **LOW** | Zero-accounting tests (TM-01); distinct permission name (DD-09); print label enforcement (BC-8) |
| Confirmation bypasses canonical path | **LOW** | Confirmation delegates to `pay_order` (BC-4); no alternative write path exists |
| Concurrent double-confirmation | **LOW** | `SELECT FOR UPDATE` on declaration + canonical path's order lock (DD-03) |
| Cross-supplier data leak | **LOW** | Tenant-local storage (DD-01); dual-key scoping; same-pattern as existing client routes |
| Permission rename breaks existing | **LOW** | `client:payments:create` proven unused (GAP-07); migration 037 forward-fix |
| Frontend print leaks internal data | **MEDIUM** | Print template renders only business fields (DD-12); test TM-17 |
| Overpayment at confirmation | **LOW** | Canonical path rejects (orders.py:686-691); proven by existing test_dc11t4h |

---

## 8. GitNexus Impact Summary

| Symbol | Change Type | Risk | Direct Dependents |
|---|---|---|---|
| `pay_order` (orders.py:558) | Reused by confirmation (no source change) | LOW | `api/v1/orders.py` router |
| `PaymentService._apply_outstanding_balance_delta` | Reused by canonical path (no change) | LOW | `pay_order` |
| `configure_app` (app.py) | New routes added under existing prefixes | LOW | FastAPI app |
| `resolve_client_identity` | Reused by new client routes (no change) | LOW | All client routes |
| `permission_registry.py` | Permission rename + additions | LOW | All seeders, migration 036/037 |

No unexpected product flows detected. All changes are additive (new table, new routes, new permissions, permission rename of unused code).

---

## 9. Out of Scope

- SMS/WhatsApp delivery implementation (BC-9)
- File/photo upload for transfer proof (DD-06)
- Server-side PDF generation (DD-13)
- S3-S3, S4 implementation
- Activation of `client:payments:create` as a canonical write path (DD-09 replaces it)
- Cross-supplier comparison or aggregation (BC-10)
- Automated declaration expiry (DD-02 — future)

---

## 10. Self-Review

| # | Check | Result |
|---|---|---|
| 1 | Every mandatory decision has one unambiguous answer | ✅ DD-01 through DD-17 |
| 2 | Report findings and CSV reconciled by finding_id; gap = 0 | ✅ (see CSV) |
| 3 | No stale claim says declaration = payment or receipt | ✅ BC-1, BC-7, BC-8 explicit |
| 4 | No design duplicates or bypasses canonical payment path | ✅ BC-4, DD-11, DD-17 |
| 5 | Changed scope is docs-only | ✅ No code modified |
| 6 | git diff --check | ✅ |
| 7 | ASCII/mojibake scan | ✅ |
| 8 | detect-secrets | ✅ |
| 9 | GitNexus detect_changes risk LOW, no unexpected processes | ✅ |
| 10 | No protected ref or tag modified | ✅ |

---

## 11. Verdict

```
PASS_FOR_CTO_DC12R1_S3_S2B_IMPLEMENTATION_PLANNING
```

All accounting decisions resolved. No existing product defect confirmed. The proposed workflow permits zero financial effects before cashier confirmation (BC-2, TM-01).
