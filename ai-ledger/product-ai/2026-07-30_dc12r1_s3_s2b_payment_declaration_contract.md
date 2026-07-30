# DC-12R1-S3-S2B-D-R1: Retailer Payment Declaration, Cashier Confirmation, Receipt & Print Contract (Corrected)

**Date:** 2026-07-31 (R1 correction of 2026-07-30 original)
**Branch:** `zcode/dc12r1-s3-s2b-d-payment-declaration-contract-2026-07-30`
**Product baseline:** `origin/product-dev-recovered` @ `0aec0f0b`
**Doc checkpoint:** `origin/codex/dc12-project-status-s3-s2-2026-07-30` @ `2359fc0d`
**Task type:** Docs-only financial design/audit gate. No product code implemented.

---

## 0. R1 Correction Summary

This document supersedes the original DC-12R1-S3-S2B-D contract (`f8a99e89`). The original PASS verdict is **WITHDRAWN**. The following 13 corrections are applied:

| # | Correction |
|---|---|
| R1.1 | Original PASS verdict withdrawn. |
| R1.2 | CURRENT_PRODUCT_DEFECT recorded: frontend uses `orders:update` while backend requires `payments:create`. |
| R1.3 | Confirmation replay made idempotent: same declaration/payment/receipt returned; no duplicate writes. |
| R1.4 | Transaction-level canonical payment service extraction specified. Never call one route handler from another. |
| R1.5 | Single `receipt_number` source of truth + concurrency-safe allocator specified. |
| R1.6 | Server-authoritative bounded statement endpoint specified (not client-side running balance). |
| R1.7 | `is_deleted` removed from immutable declarations; rejection reason naming unified. |
| R1.8 | Migration 037 made forward-only/fail-closed with full semantic preflight. |
| R1.9 | Notification emission deferred — no transactional outbox designed yet. |
| R1.10 | Cancel/expiry/stale test-matrix claims corrected with exact route/test references. |
| R1.11 | Financial blast radius reclassified as **HIGH**. |
| R1.12 | ASCII/mojibake claim corrected: non-ASCII ≠ mojibake. |
| R1.13 | Strict self-review performed; report/CSV reconciled gap=0. |

---

## 1. Executive Summary

This document locks the contract for retailer-initiated payment declarations: a **non-canonical** payment submission that has **zero accounting effect** until an authorized wholesaler cashier confirms it. The retailer submits a declaration of intent ("I paid via cash/transfer, here is the reference"). The cashier reviews and either confirms (triggering the canonical payment write semantics) or rejects. Only confirmed declarations produce canonical payments, ledger entries, order transitions, and receivable updates.

**The original PASS verdict is withdrawn.** The expected verdict is `STOP_AND_REPORT_CTO_WITH_H3_PAYMENT_PERMISSION_PREREQUISITE` because a CURRENT_PRODUCT_DEFECT exists (R1.2) that must be resolved before S2B implementation can proceed.

The design preserves the GAP-07 invariant (no client route performs financial mutation) by introducing a **declaration-only** write path that is strictly isolated from canonical payment semantics.

**Financial blast radius: HIGH.** This design touches the canonical payment write path — the sole mechanism for money movement in the system. Any defect in the extraction (R1.4), idempotency (R1.3), or receipt allocation (R1.5) could cause duplicate payments, lost payments, or corrupted receivables. The design must be reviewed by the CTO before implementation.

---

## 2. CURRENT_PRODUCT_DEFECT (R1.2)

### Defect: Frontend/backend payment permission mismatch

| Layer | Permission Checked | File:Line |
|---|---|---|
| **Frontend** | `orders:update` | `frontend/src/pages/orders/OrderListPage.tsx:70` — `user?.permissions.includes('orders:update')` |
| **Backend** | `payments:create` | `backend/api/v1/orders.py:561` — `Depends(RequirePermission("payments:create"))` |

**Impact:** The "Record Payment" button in the wholesaler UI is gated by `orders:update`, but the backend `POST /api/v1/orders/{order_id}/pay` requires `payments:create`. A user with `orders:update` but not `payments:create` sees the button, can open the modal, and submits a payment — only to receive a 403 `PERMISSION_DENIED` from the backend. Conversely, a user with `payments:create` but not `orders:update` cannot see the button at all.

**Classification:** `CURRENT_PRODUCT_DEFECT` — this is an existing defect in the product baseline (`0aec0f0b`), not introduced by this design.

**Prerequisite for S2B:** This defect must be resolved (frontend changed to check `payments:create`, or a new `payments:create`-derived UI permission) before S2B implementation begins. The S2B declaration confirmation UI will face the same permission mismatch unless resolved first.

**This is why the verdict is STOP, not PASS.**

---

## 3. Business Contract (Locked)

| # | Rule |
|---|---|
| BC-1 | Retailer submission is a **payment declaration**, not a canonical payment. |
| BC-2 | Submission has **zero effect** on payments, order status, ledger, inventory, outstanding balance, receivables, or reporting. |
| BC-3 | Only an **authorized wholesaler cashier** may confirm or reject. |
| BC-4 | Confirmation must **call the transaction-level canonical payment service** (R1.4), not a route handler. |
| BC-5 | Confirmation must be **atomic** across payment, order, ledger and receivables. |
| BC-6 | Retailer sees **pending, confirmed and rejected** states only inside the selected supplier relationship. |
| BC-7 | Only **confirmed** payment may be labelled "received" or rendered as a receipt. |
| BC-8 | Pending declarations may print only as **"Payment Declaration — Not Received"**. |
| BC-9 | **No notification emission** in this scope — deferred until a transactional outbox is designed (R1.9). |
| BC-10 | **No cross-supplier** workspace, comparison, identifiers or financial data. |

---

## 4. Source Audit Evidence

### 4.1 Canonical Payment Write Path

| Component | File:Line | Summary |
|---|---|---|
| **Pay route** | `api/v1/orders.py:558-861` | `POST /api/v1/orders/{order_id}/pay`; requires `payments:create` (L561); `X-Idempotency-Key` mandatory (L564); `SELECT FOR UPDATE` lock (L623); payment INSERT (L746); outstanding_balance delta (L770/L789); order transition (L796); ledger posting (L778) |
| **Alt pay path disabled** | `api/v1/payments.py:83-97` | `POST /api/v1/payments` returns 409 `PAYMENT_WRITE_PATH_DISABLED` |
| **PaymentRepository.create** | `repositories/payment_repository.py:236-298` | Raw-SQL INSERT into `payments` table |
| **PaymentService._apply_outstanding_balance_delta** | `services/payment_service.py:169-216` | UPDATE outstanding_balance with non-negative guard |
| **LedgerService.post_payment_received** | `services/ledger_service.py:281-317` | Debit CASH / Credit RECEIVABLE |
| **OrderService.transition** | `services/order_service.py:53-164` | The ONLY order state mutation path; FOR UPDATE; invariants; ledger |
| **OrderState matrix** | `core/domain/order_state.py:49-73` | `CONFIRMED → {PAID, PARTIALLY_PAID, CANCELLED}` |
| **Frontend pay button permission** | `frontend/src/pages/orders/OrderListPage.tsx:70` | Checks `orders:update` — **MISMATCHES backend** (DEFECT R1.2) |

### 4.2 Retailer Client Finance (Read-Only)

| Component | File:Line | Summary |
|---|---|---|
| **ClientIdentity** | `api/v1/client/dependencies.py:35-42` | `user_id`, `retailer_id`, `tenant_id`, `token` — all server-derived |
| **resolve_client_identity** | `api/v1/client/dependencies.py:45-128` | Binding lookup; 403 on missing/inactive |
| **GET /api/v1/client/payments** | `api/v1/client/payments.py:42-90` | `client:payments:read`; read-only; dual-key scoped |
| **GET /api/v1/client/finance/balance** | `api/v1/client/finance.py:31-64` | `client:finance:read`; read-only |
| **ClientFinanceRepository** | `repositories/client_finance_repository.py:79-102` | `get_balance`: reads stored `outstanding_balance` |

### 4.3 GAP-07 / Permission Evidence

| Component | File:Line | Summary |
|---|---|---|
| **client:payments:create defined** | `core/permission_registry.py:69` | Granted to retailers but **unused by any route** |
| **GAP-07 freeze test** | `tests/test_dc12r1_s3_s1_catalog_order_hardening.py:560-563` | Proves no client route consumes `client:payments:create` |
| **Canonical pay permission** | `tests/test_route_authorization_policy.py:904-915` | `POST /orders/{id}/pay` requires `payments:create` |

### 4.4 Financial Integrity Test Ground-Truth

| Test File | Key Tests | Verifies |
|---|---|---|
| `test_dc11d_payment_replay_concurrency_integrity.py` | L340-721 | Replay idempotency, concurrent single-settlement, overpay rejection, rollback invariance |
| `test_dc11t4h_receivable_collection_integrity.py` | L113-976 | Credit collection, over-collection rejection, concurrent lock, migration 035 fail-closed |
| `test_s5_ledger.py` | L96, L379 | Unbalanced rejection, ledger immutability |
| `test_s5_5_ledger_hardening.py` | L32, L88 | DB-level UPDATE/DELETE blocks |
| `test_dc10f_payment_method_integrity.py` | L44-115 | Non-canonical method rejection before side effects |

### 4.5 Frontend Evidence

| Component | File:Line | Summary |
|---|---|---|
| **Wholesaler pay modal** | `frontend/src/pages/orders/OrderListPage.tsx:125-152,437-446` | "Record Payment" button; gated by `orders:update` (DEFECT) |
| **Retailer finance UI** | `frontend/src/pages/client/FinanceBalancePage.tsx:14-67` | Read-only balance display |
| **Retailer payment history** | `frontend/src/pages/client/PaymentHistoryPage.tsx:37-101` | Read-only |
| **Client routes** | `frontend/src/router/AppRouter.tsx:122-140` | 6 routes; no pay route |
| **Print support** | *(none)* | No print/PDF/receipt capability exists |

---

## 5. Mandatory Design Decisions (Corrected)

### DD-01: Storage — Tenant-Local

**Decision:** Declarations stored in the **tenant schema** (`{tenant}.payment_declarations`), not public.

**Justification:** Declarations are retailer-supplier-relationship-scoped. Tenant-local storage enforces isolation by construction and matches the existing pattern.

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
              └──────────┘ └──────────┘
                terminal      terminal
```

**Permitted transitions:** `PENDING → CONFIRMED`, `PENDING → REJECTED`. No other transitions. Both are terminal.

**No retailer cancellation.** Once submitted, a declaration cannot be withdrawn by the retailer. Only the cashier moves it to terminal state.

**R1.10 Correction — No expiry in MVP.** The original contract mentioned "optional auto-expiry" to REJECTED. This is **removed from the MVP scope**. There is no expiry or auto-cancellation mechanism. A PENDING declaration remains PENDING until the cashier explicitly confirms or rejects it. This eliminates stale-state ambiguity. Future expiry is a separate enhancement.

### DD-03: Idempotent Confirmation (R1.3 Correction)

**Declaration submission idempotency (unchanged):**
- `X-Declaration-Idempotency-Key` (8-64 visible ASCII).
- Replay with same key + same payload → return existing declaration.
- Replay with same key + different payload → 409 `DECLARATION_IDEMPOTENCY_KEY_CONFLICT`.

**Confirmation replay idempotency (R1.3 — corrected):**

The original contract stated a second confirm returns 409 `DECLARATION_ALREADY_CONFIRMED`. **This is corrected.** A repeated or concurrent confirmation of the same declaration must:

1. **Return the same confirmed declaration** — same declaration_id, same payment_id, same receipt_number.
2. **Perform zero duplicate financial writes** — no second payment INSERT, no second ledger entry, no second outstanding_balance delta, no second order transition.
3. **Not raise 409** — replay is safe and returns 200 with the original confirmation result.

**Mechanism:** The confirmation service checks the declaration status inside the same transaction:
- If `status == 'confirmed'`: return the existing `confirmation_payment_id` and `receipt_number` immediately. No canonical payment service call.
- If `status == 'pending'`: acquire `SELECT FOR UPDATE` on the declaration row (same pattern as `orders.py:623`), re-check status (double-checked locking), then call the canonical payment service.
- Concurrent confirms: the FOR UPDATE lock serializes them. The first acquires the lock, confirms, commits. The second acquires the lock, sees `status == 'confirmed'`, returns the existing result.

**This makes confirmation replay-safe and concurrent-safe without 409 errors on legitimate retries.**

### DD-04: Transaction-Level Canonical Payment Service (R1.4)

**Decision:** Extract the payment write logic from `pay_order` (orders.py:558-861) into a **transaction-level service method** `CanonicalPaymentService.confirm_payment(...)` that both the existing `pay_order` route handler and the declaration confirmation path call.

**Critical rule:** **Never call one FastAPI route handler from another.** The existing `pay_order` is a route handler with HTTP-specific concerns (headers, request parsing, HTTP exceptions). The declaration confirmation route must not invoke `pay_order` as a function. Instead, both route handlers call the same transaction-level service.

**Service specification:**

```python
class CanonicalPaymentService:
    async def confirm_payment(
        self,
        db: AsyncSession,
        *,
        order_id: UUID,
        amount: Decimal,
        method: str,  # 'cash' | 'transfer' | 'credit'
        idempotency_key: str,
        transfer_reference: str | None = None,
        created_by: UUID,
    ) -> PaymentResult:
        """
        The single canonical payment write path.

        Extracted from pay_order (orders.py:558-861). Contains:
        - SELECT FOR UPDATE on order
        - Idempotency replay check (double-checked locking)
        - Remaining balance validation
        - PaymentRepository.create
        - Outstanding balance delta
        - OrderService.transition
        - LedgerService.post_payment_received
        - Cash/transfer settlement

        Called by:
        1. pay_order route handler (existing, refactored to delegate)
        2. Declaration confirmation route handler (new)

        Never called from another route handler directly.
        """
```

**Extraction plan:**
1. Extract lines 598-854 of `pay_order` into `CanonicalPaymentService.confirm_payment`.
2. `pay_order` becomes a thin HTTP adapter: parse request → call `confirm_payment` → format response.
3. Declaration confirmation route: check declaration status (idempotent) → call `confirm_payment` → link declaration to payment.

**Transaction ownership:** The `db: AsyncSession` is passed in. The caller (route handler via `get_tenant_db` dependency) owns the transaction lifecycle. `confirm_payment` does not call `db.commit()` — it flushes and relies on the caller's commit, matching the existing pattern proven by `test_payment_atomicity.py:57`.

### DD-05: Receipt Number Source of Truth and Allocator (R1.5)

**Single source of truth:** The `receipt_number` is stored **on the canonical payment row** (`payments.receipt_number`), not on the declaration. The declaration's `receipt_number` is a denormalized copy set at confirmation time.

**Concurrency-safe allocator:**

```sql
-- Tenant-local sequence table: {tenant}.receipt_sequences
CREATE TABLE receipt_sequences (
    year_month CHAR(6) PRIMARY KEY,  -- '202607'
    next_seq INTEGER NOT NULL DEFAULT 1
);

-- Allocation (inside the confirmation transaction, after FOR UPDATE on declaration):
INSERT INTO receipt_sequences (year_month, next_seq) VALUES (:ym, 1)
ON CONFLICT (year_month) DO UPDATE
SET next_seq = receipt_sequences.next_seq + 1
RETURNING next_seq;
-- receipt_number = 'RCT-' || :ym || '-' || LPAD(next_seq::text, 6, '0')
```

**Why not a DB sequence?** PostgreSQL sequences are not transactional (they don't roll back), creating gaps. The `INSERT ... ON CONFLICT ... RETURNING` pattern is atomic within the transaction: if the confirmation rolls back, the sequence increment rolls back too, preventing gaps and guaranteeing no duplicate receipt numbers.

**Single allocator:** Only `CanonicalPaymentService.confirm_payment` allocates receipt numbers. No other code path may generate them.

### DD-06: Server-Authoritative Bounded Statement (R1.6)

**Decision:** Define a **server-authoritative bounded statement endpoint**.

The original contract proposed client-side "running balance" printing. **This is corrected.** The retailer must not compute balances client-side. A statement is a server-generated, bounded (start_date, end_date) document.

**Endpoint:**
```
GET /api/v1/client/statements?from=2026-07-01&to=2026-07-31
Permission: client:payments:read
```

**Response:** Server computes the statement from canonical records:
- Opening balance (stored `outstanding_balance` at `from` date — requires a balance snapshot or ledger projection)
- All declarations (pending/confirmed/rejected) in the period
- All canonical payments in the period
- Closing balance (stored `outstanding_balance` at `to` date)
- Each line item carries its authoritative server timestamp

**The retailer never computes a running balance.** The print template renders the server-provided statement data as-is.

**Note:** This endpoint requires either a balance history mechanism (not currently present) or a ledger-based projection. The ledger projection (`LedgerService.get_balance`, `ledger_service.py:183-215`) can compute period balances. This is specified as part of the S2B implementation plan, not implemented in this docs-only task.

### DD-07: Immutable Declarations — Remove is_deleted (R1.7)

**Decision:** The `payment_declarations` table has **no `is_deleted` column**. Declarations are immutable audit records — they are never soft-deleted or hard-deleted.

**Rejection reason naming unified:**
- Column: `reason` (not `rejected_reason` or `rejection_reason`).
- Set at rejection time: `reason`, `rejected_at`, `rejected_by`.
- For confirmed declarations: `reason` is NULL.
- For pending declarations: `reason` is NULL.

**Updated table DDL (see §6).**

### DD-08: Migration 037 — Forward-Only, Fail-Closed (R1.8)

**Decision:** Migration 037 is **forward-only** with comprehensive preflight. No downgrade.

**Preflight checks (all must pass before any DDL):**
1. **Semantic catalog preflight:** Assert `client:payments:create` exists in `permissions` table for all enumerated tenant schemas. If missing in any schema, fail closed with exact schema name.
2. **Registered-tenant enumeration:** Query `public.wholesalers` for all tenant schemas. Enumerate each. Do not rely on filesystem or hardcoded list.
3. **Bootstrap parity:** Assert the `payment_declarations` table DDL matches what `bootstrap_tenant_schema.py` will create for fresh tenants. If mismatch, fail closed.
4. **Rogue-schema protection:** For each enumerated schema, assert it has the expected `alembic_version` head (036). If a schema is at a different revision, fail closed with the schema name and revision.
5. **Sole-head proof:** Assert `alembic_version` table has exactly one row at revision 036. If multiple heads, fail closed.
6. **Idempotent second upgrade:** Running `alembic upgrade head` twice must be a no-op (alembic's standard behavior, but asserted in the migration's `upgrade()` via `op.get_context()` check).

**Forward DDL:**
```sql
-- For each tenant schema (enumerated from public.wholesalers):
CREATE TABLE IF NOT EXISTS "{schema}".payment_declarations (...);
CREATE TABLE IF NOT EXISTS "{schema}".receipt_sequences (...);
-- Permission rename:
UPDATE "{schema}".permissions SET code = 'client:payments:declare' WHERE code = 'client:payments:create';
-- New permissions:
INSERT INTO "{schema}".permissions (code, description) VALUES
  ('payments:confirm_declaration', 'Confirm or reject a retailer payment declaration')
ON CONFLICT (code) DO NOTHING;
```

**No downgrade.** The migration has no `downgrade()` function (or it raises `NotImplementedError`). Reverting a payment system migration is unsafe.

### DD-09: Notification Emission Deferred (R1.9)

**Decision:** **No notification emission** in S2B. The original contract specified event contracts (`PaymentDeclarationConfirmed`, `PaymentDeclarationRejected`). **These are removed.**

**Rationale:** Emitting events without a transactional outbox risks lost notifications (event emitted but transaction rolls back, or vice versa). A transactional outbox pattern requires its own design (table, poller, delivery retry). This is out of scope for S2B MVP.

**When notifications are needed:** A separate task must design the transactional outbox. Only then can declaration events be emitted.

### DD-10: Permissions

| Permission | Scope | Action | Status |
|---|---|---|---|
| `client:payments:declare` | Retailer | Submit a payment declaration | NEW (replaces `client:payments:create`) |
| `client:payments:read` | Retailer | View own declarations + confirmed payments | EXISTS |
| `payments:confirm_declaration` | Wholesaler cashier | Confirm or reject a declaration | NEW |
| `payments:create` | Wholesaler | Record payment (canonical path) | EXISTS |
| `payments:read` | Wholesaler | View all declarations in tenant | EXISTS |

**Note on `client:payments:create`:** Replaced by `client:payments:declare` (DD-09 of original, confirmed here). The rename occurs in migration 037.

### DD-11: Maker/Checker and Self-Confirmation Boundary

- **Maker:** The retailer (retailer_operator) submits.
- **Checker:** The wholesaler cashier confirms or rejects.
- A wholesaler cashier cannot submit (not a retailer). A retailer cannot confirm (lacks `payments:confirm_declaration`).
- No user can be both maker and checker for the same declaration.

### DD-12: Receipt Fields and Privacy

**Retailer-visible receipt fields:** receipt_number, order_id, order_total, amount_paid, method, confirmed_at, wholesaler_name.

**Not visible:** cashier user_id, internal ledger IDs, internal payment row ID.

### DD-13: Print Contracts

| Document | Trigger | Status Label | Content |
|---|---|---|---|
| **Order** | Retailer or cashier print | Order status | Order items, totals, parties, dates |
| **Declaration (pending)** | Retailer prints pending | **"Payment Declaration — Not Received"** | Amount, method, reference, date, "NOT A RECEIPT" |
| **Confirmed receipt** | Print confirmed declaration | **"Payment Received"** | Receipt number, order, amount, method, date |
| **Statement** | Print server-generated statement | Period label | Server-authoritative opening/closing balance + line items (DD-06) |

**Implementation:** Browser-native `window.print()` with print CSS. No server-side PDF.

### DD-14: API Routes (Corrected)

#### New Routes

| Method | Path | Permission | Purpose |
|---|---|---|---|
| `POST` | `/api/v1/client/orders/{order_id}/declare` | `client:payments:declare` | Retailer submits declaration |
| `GET` | `/api/v1/client/declarations` | `client:payments:read` | Retailer lists own declarations |
| `GET` | `/api/v1/client/declarations/{id}` | `client:payments:read` | Retailer views single declaration |
| `GET` | `/api/v1/client/statements` | `client:payments:read` | Server-authoritative bounded statement (DD-06) |
| `POST` | `/api/v1/declarations/{id}/confirm` | `payments:confirm_declaration` | Cashier confirms (calls CanonicalPaymentService) |
| `POST` | `/api/v1/declarations/{id}/reject` | `payments:confirm_declaration` | Cashier rejects with reason |
| `GET` | `/api/v1/declarations` | `payments:read` | Cashier lists all declarations |
| `GET` | `/api/v1/declarations/{id}` | `payments:read` | Cashier views single declaration |

#### Confirmation Response (Idempotent — R1.3)

```json
// POST /api/v1/declarations/{id}/confirm
// First call: 200 OK
// Replay/concurrent call: 200 OK (same response, no duplicate writes)
{
  "success": true,
  "data": {
    "declaration_id": "<uuid>",
    "status": "confirmed",
    "payment_id": "<uuid>",
    "receipt_number": "RCT-20260731-000001",
    "order_status": "paid",
    "confirmed_at": "2026-07-31T12:05:00Z"
  }
}
// On overpayment (first call only): 409 PAYMENT_EXCEEDS_REMAINING
// (replay of an already-confirmed declaration never reaches this check)
```

#### Controlled Errors

| Code | HTTP | When |
|---|---|---|
| `DECLARATION_BODY_REQUIRED` | 400 | Empty body |
| `DECLARATION_AMOUNT_REQUIRED` | 400 | Missing amount |
| `DECLARATION_AMOUNT_INVALID` | 400 | Amount ≤ 0 |
| `DECLARATION_METHOD_INVALID` | 400 | Method not in {cash, transfer} |
| `DECLARATION_TRANSFER_REFERENCE_REQUIRED` | 400 | Transfer without reference |
| `DECLARATION_IDEMPOTENCY_KEY_CONFLICT` | 409 | Same key, different payload |
| `DECLARATION_NOT_PENDING` | 409 | Confirm/reject on non-pending (with status in detail) |
| `PAYMENT_EXCEEDS_REMAINING` | 409 | Confirmation overpayment |
| `PERMISSION_DENIED` | 403 | Missing permission |
| `ORDER_NOT_FOUND` | 404 | Order not in scope |

**R1.10 Note:** `DECLARATION_ALREADY_CONFIRMED` and `DECLARATION_ALREADY_REJECTED` are replaced by `DECLARATION_NOT_PENDING` with the current status in the detail field. For confirmed declarations, a replay returns 200 (idempotent), not 409.

### DD-15: Migration 037

See DD-08. Forward-only, fail-closed, with full preflight.

### DD-16: Rollback Semantics

- No changes to existing payment rows. Migration 037 is additive (new table + permission rename of unused code).
- Confirmation rollback: If `CanonicalPaymentService.confirm_payment` fails, the declaration remains PENDING. The transaction rolls back (existing pattern). The declaration's FOR UPDATE lock is released.
- Permission rename is safe: `client:payments:create` is proven unused (GAP-07).

---

## 6. Data Model (Corrected — R1.7)

### Table: `{tenant}.payment_declarations`

| Column | Type | Constraints |
|---|---|---|
| `id` | UUID PK | DEFAULT gen_random_uuid() |
| `order_id` | UUID | NOT NULL |
| `retailer_id` | UUID | NOT NULL |
| `wholesaler_id` | UUID | NOT NULL |
| `declared_amount` | NUMERIC(12,2) | NOT NULL, CHECK (> 0) |
| `method` | VARCHAR(16) | NOT NULL, CHECK IN ('cash', 'transfer') |
| `transfer_reference` | VARCHAR(128) | NULL (required if method='transfer') |
| `status` | VARCHAR(16) | NOT NULL DEFAULT 'pending', CHECK IN ('pending','confirmed','rejected') |
| `idempotency_key` | VARCHAR(64) | NOT NULL |
| `submitted_by` | UUID | NOT NULL |
| `submitted_at` | TIMESTAMPTZ | NOT NULL DEFAULT now() |
| `confirmed_by` | UUID | NULL |
| `confirmed_at` | TIMESTAMPTZ | NULL |
| `confirmation_payment_id` | UUID | NULL |
| `receipt_number` | VARCHAR(32) | NULL (denormalized copy from payment row) |
| `rejected_by` | UUID | NULL |
| `rejected_at` | TIMESTAMPTZ | NULL |
| `reason` | VARCHAR(256) | NULL (unified name — set on rejection only) |

**R1.7 Changes from original:**
- `is_deleted` column **REMOVED**. Declarations are immutable — never deleted.
- `rejected_reason` renamed to `reason` (unified).

**Indexes:**
- UNIQUE `(order_id, idempotency_key)` — replay protection
- INDEX `(retailer_id, status)` — retailer listing
- INDEX `(wholesaler_id, status)` — cashier queue
- UNIQUE `(receipt_number)` WHERE `receipt_number IS NOT NULL`

### Table: `{tenant}.receipt_sequences`

| Column | Type | Constraints |
|---|---|---|
| `year_month` | CHAR(6) PK | e.g. '202607' |
| `next_seq` | INTEGER | NOT NULL DEFAULT 1 |

---

## 7. Required Test Matrix (Corrected — R1.10)

| # | Test | Description | Decision Ref |
|---|---|---|---|
| TM-01 | Zero accounting on submit | Submit → no payment row, no ledger, no order change, no balance change | BC-2 |
| TM-02 | A/B supplier isolation | Declaration in supplier A not visible to retailer in supplier B | BC-10 |
| TM-03 | Same-schema wrong-retailer | Declaration from retailer X not visible to retailer Y | BC-10 |
| TM-04 | Duplicate submit idempotency | Same key + same payload → existing; different payload → 409 | DD-03 |
| TM-05 | Concurrent confirm single payment | Two simultaneous confirms → exactly one payment, same receipt, one 200 + one 200 (idempotent) | DD-03, R1.3 |
| TM-06 | Sequential confirm replay | Confirm twice sequentially → same payment_id, same receipt, zero new writes | DD-03, R1.3 |
| TM-07 | Reject | Reject → status=rejected, reason stored, terminal, no financial effect | DD-02 |
| TM-08 | Non-pending rejection | Reject a confirmed declaration → 409 `DECLARATION_NOT_PENDING` | DD-14 |
| TM-09 | Overpayment at confirm | Confirm where amount > remaining → 409 `PAYMENT_EXCEEDS_REMAINING` | DD-04 |
| TM-10 | Negative/zero amount | Submit amount ≤ 0 → 400 `DECLARATION_AMOUNT_INVALID` | DD-14 |
| TM-11 | Invalid method | Submit method='credit' → 400 `DECLARATION_METHOD_INVALID` | DD-14 |
| TM-12 | Malformed order_id | Malformed UUID → 404 | DD-14 |
| TM-13 | Unauthorized retailer | No `client:payments:declare` → 403 | DD-10 |
| TM-14 | Unauthorized cashier | No `payments:confirm_declaration` → 403 | DD-10 |
| TM-15 | Inactive binding | Inactive binding → 403 `BINDING_NOT_ACTIVE` | BC-6 |
| TM-16 | Confirmed receipt visible | Confirmed → retailer sees receipt_number + "received" | BC-7 |
| TM-17 | Pending not "received" | Pending print → "Payment Declaration — Not Received" | BC-8 |
| TM-18 | Print privacy | No internal identifiers in print output | DD-12, DD-13 |
| TM-19 | Canonical regressions | Existing payment/ledger/receivable tests unchanged | DD-16 |
| TM-20 | Route inventory | New routes correct permissions; GAP-07 updated | DD-10 |
| TM-21 | Permission registry | `client:payments:create` removed; `client:payments:declare` + `payments:confirm_declaration` added | DD-10 |
| TM-22 | No notification emission | No event/outbox call on confirm or reject | DD-09, R1.9 |
| TM-23 | Receipt number uniqueness | Concurrent confirms on different orders → unique receipt numbers, no collision | DD-05 |
| TM-24 | Statement server-authoritative | Statement computed server-side; retailer cannot inject balance | DD-06 |
| TM-25 | CanonicalPaymentService extraction | Both pay_order and confirmation call the same service; neither calls the other | DD-04, R1.4 |

**R1.10 Corrections:**
- TM-05 and TM-06 split: concurrent vs sequential replay, both assert idempotent 200 (not 409).
- TM-08 corrected: non-pending rejection returns `DECLARATION_NOT_PENDING`, not `DECLARATION_ALREADY_REJECTED`.
- TM-22 added: verify no notification emission.
- TM-23 added: receipt number concurrency.
- TM-24 added: statement server-authoritative.
- TM-25 added: service extraction proof.
- Removed original TM-21 (notification event emits after confirmation) — replaced by TM-22.

---

## 8. Risk Assessment (R1.11 — Reclassified)

| Risk | Level | Rationale |
|---|---|---|
| **Overall financial blast radius** | **HIGH** | This design touches the canonical payment write path — the sole money-movement mechanism. Extraction defects could cause duplicate/lost payments. |
| Confirmation bypasses canonical path | **HIGH** | Must be prevented by DD-04 (service extraction). Any bypass is a financial integrity violation. |
| Concurrent double-confirmation | **MEDIUM** | Mitigated by FOR UPDATE + idempotent replay (DD-03). But the locking interaction with the canonical path's own FOR UPDATE needs careful implementation. |
| Receipt number collision | **MEDIUM** | Mitigated by atomic sequence allocator (DD-05). But gap-free guarantee depends on transaction rollback behavior. |
| CanonicalPaymentService extraction regression | **HIGH** | Refactoring `pay_order` into a service risks introducing bugs in the existing path. Must be proven by running all existing payment tests against the refactored code. |
| Permission rename breaks existing | **LOW** | `client:payments:create` proven unused (GAP-07). |
| Frontend permission mismatch (R1.2) | **HIGH** | Existing defect. Must be resolved before S2B. |
| Print leaks internal data | **MEDIUM** | Mitigated by print template field whitelist (TM-18). |
| Statement balance computation | **MEDIUM** | Requires ledger projection or balance snapshot — non-trivial. |

---

## 9. Character Encoding Note (R1.12)

The original self-review claimed "ASCII/mojibake scan: ✅". This was **inaccurate**.

**Correction:**
- **Mojibake** is corrupted text (e.g., UTF-8 bytes decoded as Latin-1 producing replacement characters `\ufffd`). The scan for `\x{fffd}` correctly found none.
- **Non-ASCII** is any character outside ASCII range (e.g., em-dash `—`, curly quotes). This document **intentionally uses** em-dashes (`—`) and other non-ASCII punctuation for readability. This is **not mojibake** — it is deliberate UTF-8 content.

The original claim conflated "no mojibake" with "all ASCII". The correct statement is: **no mojibake detected; non-ASCII punctuation is intentional and valid UTF-8.**

---

## 10. GitNexus Impact Summary

| Symbol | Change Type | Risk | Direct Dependents |
|---|---|---|---|
| `pay_order` (orders.py:558) | **Refactored** — logic extracted to CanonicalPaymentService | **HIGH** | `api/v1/orders.py` router; all payment tests |
| `CanonicalPaymentService` (NEW) | New service; called by pay_order + confirmation | **HIGH** | Two route handlers |
| `PaymentService._apply_outstanding_balance_delta` | Reused (no change) | LOW | CanonicalPaymentService |
| `configure_app` (app.py) | New routes added | LOW | FastAPI app |
| `resolve_client_identity` | Reused (no change) | LOW | All client routes |
| `permission_registry.py` | Permission rename + additions | LOW | All seeders, migration 037 |

---

## 11. Out of Scope

- SMS/WhatsApp delivery (BC-9)
- File/photo upload (DD-06 of original)
- Server-side PDF generation (DD-13)
- S3-S3, S4 implementation
- Notification emission / transactional outbox (DD-09, R1.9)
- Automated declaration expiry (DD-02 — removed from MVP)
- Fixing the frontend permission mismatch (R1.2) — this is a prerequisite, not part of S2B

---

## 12. Pre-Commit Self-Review (R1.13)

| # | Check | Result |
|---|---|---|
| 1 | Every mandatory decision has one unambiguous answer | ✅ DD-01 through DD-16 |
| 2 | Report findings and CSV reconciled by finding_id; gap = 0 | ✅ (CSV updated, 35 rows) |
| 3 | No stale claim says declaration = payment or receipt | ✅ BC-1, BC-7, BC-8 |
| 4 | No design duplicates or bypasses canonical payment path | ✅ DD-04 (service extraction), DD-16 |
| 5 | Changed scope is docs-only | ✅ No code modified |
| 6 | git diff --check | ✅ |
| 7 | Encoding: no mojibake; non-ASCII is intentional UTF-8 | ✅ (R1.12 corrected) |
| 8 | detect-secrets | ✅ |
| 9 | GitNexus risk assessment accurate | ✅ (HIGH for extraction) |
| 10 | No protected ref or tag modified | ✅ |
| 11 | PASS verdict withdrawn | ✅ (R1.1) |
| 12 | CURRENT_PRODUCT_DEFECT recorded | ✅ (R1.2, §2) |
| 13 | Confirmation replay idempotent (not 409) | ✅ (R1.3, DD-03) |
| 14 | Canonical payment service extraction specified | ✅ (R1.4, DD-04) |
| 15 | Single receipt_number source + allocator | ✅ (R1.5, DD-05) |
| 16 | Server-authoritative statement or removed | ✅ (R1.6, DD-06 — server-authoritative) |
| 17 | is_deleted removed; reason unified | ✅ (R1.7, DD-07, §6) |
| 18 | Migration 037 forward-only/fail-closed | ✅ (R1.8, DD-08) |
| 19 | Notification deferred | ✅ (R1.9, DD-09) |
| 20 | Test-matrix corrected | ✅ (R1.10, §7) |
| 21 | Blast radius HIGH | ✅ (R1.11, §8) |
| 22 | ASCII claim corrected | ✅ (R1.12, §9) |

---

## 13. Verdict

```
STOP_AND_REPORT_CTO_WITH_H3_PAYMENT_PERMISSION_PREREQUISITE
```

**Reason for STOP (not PASS):**

1. **CURRENT_PRODUCT_DEFECT (R1.2):** The frontend "Record Payment" button checks `orders:update` while the backend requires `payments:create`. This must be resolved before S2B implementation.
2. **HIGH financial blast radius (R1.11):** The canonical payment service extraction (DD-04) refactors the sole money-movement path. CTO review required.
3. **Prerequisite:** The H3 payment permission gate (frontend/backend alignment) must be resolved as a separate task before S2B proceeds.

**No product code implemented. No deployment. No S3-S3 or S4.**
