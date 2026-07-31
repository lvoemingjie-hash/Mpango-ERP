# DC-12R1-S3-S2B-D-R4-R2: Retailer Payment Declaration, Cashier Confirmation, Receipt & Print Contract (Final)

**Date:** 2026-07-31 (R4-R2 correction of R4-R1; integrates H3 baseline)
**Branch:** `zcode/dc12r1-s3-s2b-d-payment-declaration-contract-2026-07-30`
**Product baseline:** `origin/product-dev-recovered` @ `0f9d259b` (H3 merged)
**Doc checkpoint:** `origin/codex/dc12-project-status-s3-s2-2026-07-30` @ `2359fc0d`
**Task type:** Docs-only financial design/audit gate. No product code implemented.

---

## 0. R4 Correction Summary

This document supersedes the R2 contract (`03f18a44`). The H3 product baseline (`0f9d259b`) is merged and is an ancestor of this branch's HEAD.

R2 applied seven corrections (R2.1–R2.7). R4 applies six additional corrections:

| # | R4 Correction |
|---|---|
| R4.1 | Stale `'provisioned'` status removed; exact 035/036 live set is `("pending_email_verification", "email_verified", "provisioning", "active", "failed")` — includes `'failed'`, not `'provisioned'` |
| R4.2 | `transfer_reference` → `transaction_id` exact mapping specified: declaration's `transfer_reference` is stored as canonical payment's `transaction_id` at confirmation (DD-15) |
| R4.3 | Declaration key vs canonical payment key: two independent idempotency namespaces; declaration key never passed as payment key; no collision possible (DD-16) |
| R4.4 | Partial and final confirmation lifecycle specified: partial → PARTIALLY_PAID; final → PAID; exposure closure for credit; receipt only for completed payment (DD-17) |
| R4.5 | Duplicate transfer reference at confirmation → controlled 409 `DUPLICATE_TRANSFER_REFERENCE` (canonical path's existing check) |
| R4.6 | Test matrix expanded with 8 new R4 tests (TM-33 through TM-40) covering all above |

R2 corrections (R2.1–R2.7) remain in effect and are not repeated here.

R4-R1 applies six additional corrections on top of R4:

| # | R4-R1 Correction |
|---|---|
| R4-R1.1 | Canonical confirmation payment key is exactly `decl-confirm-{declaration_id.hex}` — never the retailer declaration idempotency key (DD-16) |
| R4-R1.2 | `transfer_reference`: trim first; reject blank; length 1–128; no truncation; widen `payments.transaction_id` to `VARCHAR(128)` in migration 037 + bootstrap parity (DD-15) |
| R4-R1.3 | Every cashier-confirmed declaration creates `status='completed'` payment; removed all "pending confirmation" language; direct `pay_order` status behavior unchanged (DD-17) |
| R4-R1.4 | Restored DR-01 through DR-12 in decision register; all FIND-01–FIND-46 mapped to valid DR IDs; CSV `decision_ref` validated |
| R4-R1.5 | `CTO_CURRENT_OPS.md` and `PROJECT.md` updated to baseline `0f9d259b`; stale `0aec0f0b` removed |
| R4-R1.6 | Added design tests TM-41 through TM-48 for exact key, cross-retailer reuse, 128/129 boundary, blank rejection, duplicate 409, partial/final completed, direct-pay preservation, DR/FIND gap |

---

## 1. Executive Summary

This document locks the final contract for retailer-initiated payment declarations: a **non-canonical** payment submission that has **zero accounting effect** until an authorized wholesaler cashier confirms it. Confirmation triggers the canonical payment write path via a transaction-level service.

The H3 product defect (frontend `orders:update` vs backend `payments:create`) has been resolved and merged into the product baseline. The S2B design can now proceed with the corrected permission model.

**Financial blast radius: HIGH.** This design touches the canonical payment write path. Any defect in extraction, idempotency, or receipt allocation could cause duplicate payments, lost payments, or corrupted receivables.

---

## 2. CURRENT_PRODUCT_DEFECT Status

| Defect | Status | Resolution |
|---|---|---|
| Frontend pay button checks `orders:update` (`OrderListPage.tsx:70`) while backend requires `payments:create` (`orders.py:561`) | **RESOLVED** | Fixed in H3 (`280a06c3`), merged into product baseline `0f9d259b`. H3 is ancestor of this branch. |

---

## 3. Business Contract (Locked)

| # | Rule |
|---|---|
| BC-1 | Retailer submission is a **payment declaration**, not a canonical payment. |
| BC-2 | Submission has **zero effect** on payments, order status, ledger, inventory, outstanding balance, receivables, or reporting. |
| BC-3 | Only an **authorized wholesaler** with `payments:confirm_declaration` may confirm or reject. |
| BC-4 | Confirmation must **call the transaction-level CanonicalPaymentService** (DD-04), not a route handler. |
| BC-5 | Confirmation must be **atomic** across payment, order, ledger and receivables. |
| BC-6 | Retailer sees **pending, confirmed and rejected** states only inside the selected supplier relationship. |
| BC-7 | Only **confirmed** payment may be labelled "received" or rendered as a receipt. |
| BC-8 | Pending declarations may print only as **"Payment Declaration — Not Received"**. |
| BC-9 | **No notification emission** — deferred until transactional outbox is designed. |
| BC-10 | **No cross-supplier** workspace, comparison, identifiers or financial data. |

---

## 4. Source Audit Evidence

### 4.1 Canonical Payment Write Path

| Component | File:Line | Summary |
|---|---|---|
| **Pay route** | `api/v1/orders.py:558-861` | `POST /api/v1/orders/{order_id}/pay`; `payments:create` (L561); `SELECT FOR UPDATE` (L623); payment INSERT (L746); balance delta (L770/L789); order transition (L796); ledger (L778) |
| **Alt pay path disabled** | `api/v1/payments.py:83-97` | Returns 409 `PAYMENT_WRITE_PATH_DISABLED` |
| **PaymentRepository.create** | `repositories/payment_repository.py:236-298` | Raw-SQL INSERT; no `receipt_number` column currently exists |
| **PaymentService._apply_outstanding_balance_delta** | `services/payment_service.py:169-216` | `UPDATE outstanding_balance` with non-negative guard |
| **LedgerService.get_balance** | `services/ledger_service.py:183-195` | **Tenant-wide** — takes `account_type` only; **no retailer_id parameter**. Cannot be used for retailer-scoped statements (R2.5). |
| **LedgerService.post_payment_received** | `services/ledger_service.py:281-317` | Debit CASH / Credit RECEIVABLE |
| **OrderService.transition** | `services/order_service.py:53-164` | The ONLY order state mutation path |
| **Frontend pay button** | `OrderListPage.tsx:70` (H3 fixed) | Now checks `payments:create` via `hasPayPermission` |

### 4.2 Tenant Registration and Schema Derivation (R2.1)

| Component | File:Line | Summary |
|---|---|---|
| **Live tenant enumeration** | `alembic/versions/035_receivable_collection_integrity.py:82-108` | `SELECT ... FROM public.tenant_registrations tr JOIN public.wholesalers w ON w.id = tr.wholesaler_id WHERE tr.is_deleted IS FALSE AND tr.status IN :registration_statuses AND w.is_deleted IS FALSE AND w.status IN :wholesaler_statuses` |
| **LIVE_REGISTRATION_STATUSES** | `alembic/versions/035:29-34` and `036:43-49` | `("pending_email_verification", "email_verified", "provisioning", "active", "failed")` |
| **WHOLESALER_ACTIVE_STATUSES** | `alembic/versions/035:35` and `036:50` | `("active", "provisioning")` |
| **Schema derivation** | `models/wholesaler.py:93` | `derive_schema_from_id(tenant_id)` → `t_{uuid_without_dashes}` |
| **alembic_version table** | `alembic/env.py:43` | `ALEMBIC_VERSION_TABLE = "alembic_version"` — exists only in **public** schema; no per-tenant alembic_version |

**R2.1 Correction:** Migration 037 must enumerate live tenants using the exact pattern from migration 035 (lines 82-108). It must NOT check `alembic_version` in tenant schemas. The sole-head and current-revision checks apply to the global `public.alembic_version` chain only. Rogue/unregistered schemas remain untouched.

### 4.3 Payments Table Schema (R2.3)

The current payments table DDL (`scripts/bootstrap_tenant_schema.py`) does **not** have a `receipt_number` column. Migration 037 must add it:

```
ALTER TABLE "{schema}".payments ADD COLUMN receipt_number VARCHAR(32);
CREATE UNIQUE INDEX ux_payments_receipt_number
  ON "{schema}".payments (receipt_number) WHERE receipt_number IS NOT NULL;
```

### 4.4 GAP-07 / Permission Evidence

| Component | File:Line | Summary |
|---|---|---|
| **client:payments:create defined** | `core/permission_registry.py:69` | Granted to retailers but unused by any route |
| **GAP-07 freeze test** | `tests/test_dc12r1_s3_s1_catalog_order_hardening.py:560-563` | No client route consumes `client:payments:create` |
| **Canonical pay permission** | `tests/test_route_authorization_policy.py:904-915` | `POST /orders/{id}/pay` requires `payments:create` |

---

## 5. Mandatory Design Decisions (R2 Final)

### DD-01: Storage — Tenant-Local

Declarations stored in the **tenant schema** (`{tenant}.payment_declarations`). Tenant-local storage enforces isolation by construction.

### DD-02: State Machine

```
PENDING → CONFIRMED (terminal)
PENDING → REJECTED  (terminal)
```

No retailer cancellation. No expiry in MVP. Both terminal states are immutable.

### DD-03: Idempotent Confirmation

Confirmation replay returns the **same** declaration, payment ID, and receipt — with **zero** duplicate financial writes. Mechanism: `SELECT FOR UPDATE` on declaration row + double-check status. Concurrent confirms serialize via the lock; the second sees `confirmed` and returns the existing result (200, not 409).

### DD-04: Transaction-Level Canonical Payment Service

Extract payment write logic from `pay_order` (orders.py:558-861) into `CanonicalPaymentService.confirm_payment(...)`. Both `pay_order` and declaration confirmation call this service. **Never call one route handler from another.** Transaction ownership: `db: AsyncSession` passed in; service does not commit (caller owns lifecycle).

### DD-05: Receipt Number — Single Source of Truth (R2.3 Corrected)

**Single source of truth:** `payments.receipt_number` (new column added by migration 037).

**Removed from declarations:** `payment_declarations` has **no `receipt_number` column**. The receipt is resolved through `confirmation_payment_id → payments.receipt_number`.

**Format:** `RCT-YYYYMMDD-NNNNNN` using UTC confirmation date.

**Allocator:** `{tenant}.receipt_sequences` with `business_date CHAR(8)` as primary key (e.g. `'20260731'`):
```sql
INSERT INTO receipt_sequences (business_date, next_seq) VALUES (:bd, 1)
ON CONFLICT (business_date) DO UPDATE
SET next_seq = receipt_sequences.next_seq + 1
RETURNING next_seq;
-- receipt_number = 'RCT-' || :bd || '-' || LPAD(next_seq::text, 6, '0')
```

Allocation occurs **in the same transaction** as payment/declaration confirmation. Only `CanonicalPaymentService.confirm_payment` allocates receipt numbers.

**Partial unique index:** `CREATE UNIQUE INDEX ux_payments_receipt_number ON payments (receipt_number) WHERE receipt_number IS NOT NULL`.

### DD-06: Server-Authoritative Bounded Statement (R2.5 Corrected)

**Decision:** Define a server-side statement endpoint, but **defer opening/closing balance** if it cannot be proven from retailer-scoped tables.

**Problem with `LedgerService.get_balance`:** It takes `account_type` only (`ledger_service.py:183-195`) — it is **tenant-wide** with no `retailer_id` boundary. It cannot be used for retailer-scoped statements.

**Retailer-scoped projection:** The statement query must join payments through retailer-owned orders:
```sql
SELECT p.* FROM "{schema}".payments p
JOIN "{schema}".orders o ON p.order_id = o.id
WHERE o.retailer_id = :retailer_id
  AND o.wholesaler_id = :wholesaler_id
  AND p.is_deleted IS FALSE
  AND p.created_at BETWEEN :from AND :to
ORDER BY p.created_at;
```

Declarations use the same dual-key scope:
```sql
SELECT d.* FROM "{schema}".payment_declarations d
WHERE d.retailer_id = :retailer_id
  AND d.wholesaler_id = :wholesaler_id
  AND d.submitted_at BETWEEN :from AND :to
ORDER BY d.submitted_at;
```

**Opening/closing balance:** The current `outstanding_balance` on `wholesaler_retailer_bindings` is a **current point-in-time** value — it cannot reconstruct a historical period opening balance without a balance history table or a retailer-scoped ledger projection. Since `LedgerService.get_balance` is tenant-wide (no retailer filter), **opening/closing balance is DEFERRED** from S2B MVP. The statement shows line items only (declarations + payments in the period). A separate task must design retailer-scoped balance history.

**No frontend financial aggregation or running-balance calculation.**

### DD-07: Immutable Declarations — No is_deleted (R2.3 FK additions)

**No `is_deleted` column.** Declarations are immutable audit records.

**Same-schema foreign keys with RESTRICT semantics:**
```sql
confirmation_payment_id UUID REFERENCES "{schema}".payments(id) ON DELETE RESTRICT
order_id UUID NOT NULL REFERENCES "{schema}".orders(id) ON DELETE RESTRICT
```

RESTRICT (no cascade) ensures immutable financial evidence — a payment or order referenced by a declaration cannot be deleted while the declaration exists.

**Rejection reason:** Column named `reason` (unified). Set on rejection only; NULL otherwise.

### DD-08: Migration 037 — Forward-Only, Fail-Closed (R2.1 + R2.2 Corrected)

**Tenant enumeration (R2.1):**
- Enumerate live tenants through `public.tenant_registrations JOIN public.wholesalers` with the exact status/is_deleted filters from migration 035:
  - `tr.is_deleted IS FALSE AND tr.status IN ('pending_email_verification', 'email_verified', 'provisioning', 'active', 'failed')`
  - `w.is_deleted IS FALSE AND w.status IN ('active', 'provisioning')`
- Derive and validate each schema: `'t_' || replace(w.id::text, '-', '')` must match `tr.tenant_schema`.
- Rogue/unregistered schemas are **not touched**.
- `alembic_version` exists only in **public**. No per-tenant version checks. Sole-head/current checks apply to the global public migration chain only.

**Semantic preflight (R2.2):**
- For every live tenant schema, preflight:
  - `payments` table exists with expected columns (`id`, `order_id`, `retailer_id`, `transaction_id`, `amount`, `method`, `status`, `idempotency_key`)
  - `orders` table exists with `id` column
  - `client:payments:create` permission exists in `permissions` table
- **Missing objects** (e.g. `receipt_number` column) may be **created**.
- **Incompatible partial objects** (wrong type, wrong constraint) → **fail closed** with exact schema name and object name.
- **Do NOT rely on `CREATE TABLE IF NOT EXISTS`** to hide incompatible catalogs. Each object is checked against the information_schema before creation.
- **Bootstrap parity** is proven by **real tests** (`test_payments_schema_contract.py` pattern), not asserted inside `upgrade()`.
- **Second alembic upgrade** is verified **externally** as a no-op (standard alembic behavior; verified by a test, not by code in upgrade()).
- **Downgrade:** forward-only/fail-closed. No `downgrade()` or raises `NotImplementedError`.

**Forward DDL per live tenant schema:**
```sql
-- Add receipt_number to payments
ALTER TABLE "{s}".payments ADD COLUMN IF NOT EXISTS receipt_number VARCHAR(32);
CREATE UNIQUE INDEX IF NOT EXISTS ux_payments_receipt_number
  ON "{s}".payments (receipt_number) WHERE receipt_number IS NOT NULL;

-- Create payment_declarations
CREATE TABLE "{s}".payment_declarations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  order_id UUID NOT NULL REFERENCES "{s}".orders(id) ON DELETE RESTRICT,
  retailer_id UUID NOT NULL,
  wholesaler_id UUID NOT NULL,
  declared_amount NUMERIC(12,2) NOT NULL CHECK (declared_amount > 0),
  method VARCHAR(16) NOT NULL CHECK (method IN ('cash', 'transfer')),
  transfer_reference VARCHAR(128),
  status VARCHAR(16) NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'confirmed', 'rejected')),
  idempotency_key VARCHAR(64) NOT NULL,
  submitted_by UUID NOT NULL,
  submitted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  confirmed_by UUID,
  confirmed_at TIMESTAMPTZ,
  confirmation_payment_id UUID REFERENCES "{s}".payments(id) ON DELETE RESTRICT,
  rejected_by UUID,
  rejected_at TIMESTAMPTZ,
  reason VARCHAR(256)
);
CREATE UNIQUE INDEX ux_payment_declarations_retailer_idem
  ON "{s}".payment_declarations (retailer_id, idempotency_key);
CREATE INDEX ix_payment_declarations_retailer_status
  ON "{s}".payment_declarations (retailer_id, status);
CREATE INDEX ix_payment_declarations_wholesaler_status
  ON "{s}".payment_declarations (wholesaler_id, status);

-- Create receipt_sequences
CREATE TABLE "{s}".receipt_sequences (
  business_date CHAR(8) PRIMARY KEY,
  next_seq INTEGER NOT NULL DEFAULT 1
);

-- Permission rename
UPDATE "{s}".permissions SET code = 'client:payments:declare'
  WHERE code = 'client:payments:create';
-- New permission
INSERT INTO "{s}".permissions (code, description)
  VALUES ('payments:confirm_declaration',
          'Confirm or reject a retailer payment declaration')
  ON CONFLICT (code) DO NOTHING;
```

### DD-09: Notification Emission Deferred

No notification emission in S2B. Events removed. Deferred until transactional outbox is designed.

### DD-10: Permissions (R2.6 Corrected)

| Permission | Scope | Registry Action |
|---|---|---|
| `client:payments:declare` | Retailer | **Replace** `client:payments:create` in `RETAILER_OPERATOR_PERMISSIONS` |
| `client:payments:read` | Retailer | Exists, unchanged |
| `payments:confirm_declaration` | Wholesaler | **Add** to `ADMIN_PERMISSIONS` in `core/permission_registry.py` |
| `payments:create` | Wholesaler | Exists, unchanged |

**No dedicated cashier role in MVP.** The existing `admin` role receives `payments:confirm_declaration` idempotently through `ADMIN_PERMISSIONS`. `retailer_operator` must **never** receive it. Future custom cashier roles may receive it through normal role management.

**Reconciliation:** All supported seeders (`onboard_tenant.setup_admin`, `create_wholesaler.assign_all_permissions_to_admin`, `seed_test_tenant._seed_admin_rbac`, `seed_demo_data._seed_rbac`) must be reconciled to include `payments:confirm_declaration` in the admin set. The R3 reconciliation pattern (DELETE stale + re-seed) handles this automatically once the registry is updated.

**Test requirements:** Exact PostgreSQL catalog assertion that `payments:confirm_declaration` exists in every live tenant's `permissions` table and is granted to `admin` but not `retailer_operator`. Route-policy test that the confirm/reject routes require this permission.

### DD-11: Maker/Checker Boundary

Maker = retailer (retailer_operator). Checker = wholesaler (admin with `payments:confirm_declaration`). Different identities by role separation.

### DD-12: Declaration Idempotency (R2.4 Corrected)

**Unique constraint:** `UNIQUE(retailer_id, idempotency_key)` — NOT `(order_id, idempotency_key)`.

- Same retailer + same key + same payload → return existing declaration.
- Same retailer + same key + different order/payload → 409 `DECLARATION_IDEMPOTENCY_KEY_CONFLICT`.
- Different retailers may independently use the same key.

Concurrent submission and confirmation tests must prove one canonical result.

### DD-13: Print Contracts

| Document | Label | Content |
|---|---|---|
| Declaration (pending) | "Payment Declaration — Not Received" | Amount, method, reference, date |
| Confirmed receipt | "Payment Received" | Receipt number (from `payments.receipt_number`), order, amount, method, date |
| Statement | Period label | Line items only (no opening/closing balance in MVP — DD-06) |

Browser-native `window.print()`. No server-side PDF.

### DD-14: API Routes

| Method | Path | Permission |
|---|---|---|
| `POST` | `/api/v1/client/orders/{order_id}/declare` | `client:payments:declare` |
| `GET` | `/api/v1/client/declarations` | `client:payments:read` |
| `GET` | `/api/v1/client/declarations/{id}` | `client:payments:read` |
| `GET` | `/api/v1/client/statements` | `client:payments:read` |
| `POST` | `/api/v1/declarations/{id}/confirm` | `payments:confirm_declaration` |
| `POST` | `/api/v1/declarations/{id}/reject` | `payments:confirm_declaration` |
| `GET` | `/api/v1/declarations` | `payments:read` |
| `GET` | `/api/v1/declarations/{id}` | `payments:read` |

### DD-15: Transfer Reference → Transaction ID Mapping (R4/R4-R1)

**Exact mapping:** When a cashier confirms a declaration, the declaration's `transfer_reference` is passed to `CanonicalPaymentService.confirm_payment` as the canonical payment's `transaction_id`.

**Validation rules (R4-R1):**
- `transfer_reference` is **trimmed** (leading/trailing whitespace removed) before any processing.
- After trim, a **blank** reference (empty string or whitespace-only) for a transfer declaration is **rejected** with 400 `DECLARATION_TRANSFER_REFERENCE_REQUIRED`.
- After trim, the length must be **1–128 characters**. No truncation is performed — a reference exceeding 128 characters is rejected with 400 `DECLARATION_TRANSFER_REFERENCE_TOO_LONG`.
- For cash declarations, `transfer_reference` is NULL; `transaction_id` on the payment is also NULL.

**Schema widening (R4-R1):**
- Declaration field: `transfer_reference VARCHAR(128)` (no truncation; reject if > 128 after trim).
- Payment field: `transaction_id` is currently `VARCHAR(64)` (`scripts/bootstrap_tenant_schema.py` payments DDL). Migration 037 must **widen** `payments.transaction_id` to `VARCHAR(128)` in every live tenant schema:
  ```sql
  ALTER TABLE "{schema}".payments ALTER COLUMN transaction_id TYPE VARCHAR(128);
  ```
- **Fresh-bootstrap parity:** `bootstrap_tenant_schema.py` payments DDL must also use `VARCHAR(128)` for `transaction_id` so new tenants match migrated tenants.
- **Existing-schema reconciliation:** Migration 037 must apply the `ALTER COLUMN ... TYPE VARCHAR(128)` to every enumerated live tenant schema (same enumeration as R2.1).

**Duplicate detection:**
- The canonical path's duplicate-transfer check (`get_by_transaction_id`, `orders.py:732-739`) runs at confirmation. A duplicate tenant-local `transaction_id` returns controlled 409 `DUPLICATE_TRANSFER_REFERENCE`.

### DD-16: Declaration Key vs Canonical Payment Key (R4)

**Two independent idempotency keys:**

| Key | Scope | Unique Constraint | Purpose |
|---|---|---|---|
| Declaration key | `UNIQUE(retailer_id, idempotency_key)` on `payment_declarations` | Prevents duplicate declarations by the same retailer |
| Canonical payment key | `UNIQUE(idempotency_key)` on `payments` (existing) | Prevents duplicate canonical payments |

**No collision:** The declaration's `idempotency_key` is NOT passed as the canonical payment's `idempotency_key`. The canonical payment key is exactly:

```
decl-confirm-{declaration_id.hex}
```

where `declaration_id.hex` is the hex representation of the declaration's UUID (32 chars, no dashes). This key is **never** the retailer's declaration idempotency key. This ensures:

- A declaration key and a canonical payment key can never collide (different namespaces).
- Two retailers can use the same declaration key independently (different `retailer_id` in the unique constraint).
- Concurrent confirmation of the same declaration produces exactly one canonical payment (FOR UPDATE + double-check).

### DD-17: Partial and Final Confirmation Lifecycle (R4/R4-R1)

**Every cashier-confirmed declaration creates a canonical payment with `status='completed'.** There is no path where confirmation produces a `pending` payment. The existing `pay_order` route handler's logic for determining `completed` vs `pending` status (orders.py:746-764) applies only to **direct** wholesaler-initiated payments — it is **unchanged** by this design. The declaration confirmation path always sets `status='completed'` because the cashier has verified the payment before confirming.

**Partial confirmation:** A cashier may confirm a declaration for an amount less than the order's remaining balance. The canonical payment is created with `status='completed'`, the order transitions from `CONFIRMED` to `PARTIALLY_PAID` (via `OrderService.transition`), and the `outstanding_balance` is reduced by the confirmed amount.

**Final confirmation:** When cumulative confirmed payments reach or exceed the order total, the order transitions to `PAID`. The `receipt_number` is allocated for the canonical payment row.

**Receipt-on-completed-only:** A receipt (`payments.receipt_number`) exists only on `completed` canonical payments. Since every confirmation creates a `completed` payment, every confirmed declaration has a receipt. Pending declarations (not yet confirmed) have no receipt and no payment row.

**Direct pay_order behavior preserved (R4-R1):** The existing `POST /api/v1/orders/{order_id}/pay` route handler retains its current status logic unchanged — it may still create `pending` payments for transfers that don't fully settle, and complete them later via `update_cash_transfer_to_completed` (orders.py:806-810). This behavior is **not modified** by the declaration confirmation design. The declaration confirmation path uses `CanonicalPaymentService.confirm_payment` with `force_completed=True`, which is a new parameter that does not affect the direct `pay_order` path.

**Exposure closure:** For credit-collection declarations, final confirmation reduces `outstanding_balance` to 0 via `_apply_outstanding_balance_delta(delta=-amount)`. The order remains `PAID` (credit orders enter payment flow already PAID; confirmation collects the exposure).

---

## 6. Data Model (R2/R4 Final)

### Table: `{tenant}.payment_declarations`

| Column | Type | Constraints |
|---|---|---|
| `id` | UUID PK | DEFAULT gen_random_uuid() |
| `order_id` | UUID | NOT NULL, FK → orders(id) ON DELETE RESTRICT |
| `retailer_id` | UUID | NOT NULL |
| `wholesaler_id` | UUID | NOT NULL |
| `declared_amount` | NUMERIC(12,2) | NOT NULL, CHECK (> 0) |
| `method` | VARCHAR(16) | NOT NULL, CHECK IN ('cash', 'transfer') |
| `transfer_reference` | VARCHAR(128) | NULL |
| `status` | VARCHAR(16) | NOT NULL DEFAULT 'pending', CHECK IN ('pending','confirmed','rejected') |
| `idempotency_key` | VARCHAR(64) | NOT NULL |
| `submitted_by` | UUID | NOT NULL |
| `submitted_at` | TIMESTAMPTZ | NOT NULL DEFAULT now() |
| `confirmed_by` | UUID | NULL |
| `confirmed_at` | TIMESTAMPTZ | NULL |
| `confirmation_payment_id` | UUID | NULL, FK → payments(id) ON DELETE RESTRICT |
| `rejected_by` | UUID | NULL |
| `rejected_at` | TIMESTAMPTZ | NULL |
| `reason` | VARCHAR(256) | NULL |

**R2 changes from R1:**
- `receipt_number` **REMOVED** — resolved via `confirmation_payment_id → payments.receipt_number` (R2.3)
- `order_id` FK added with RESTRICT (R2.3)
- `confirmation_payment_id` FK added with RESTRICT (R2.3)
- Unique index changed to `(retailer_id, idempotency_key)` (R2.4)

**Indexes:**
- UNIQUE `(retailer_id, idempotency_key)` — replay protection (R2.4)
- INDEX `(retailer_id, status)` — retailer listing
- INDEX `(wholesaler_id, status)` — cashier queue

### Table: `{tenant}.receipt_sequences`

| Column | Type | Constraints |
|---|---|---|
| `business_date` | CHAR(8) PK | e.g. '20260731' (UTC) |
| `next_seq` | INTEGER | NOT NULL DEFAULT 1 |

### Column addition: `{tenant}.payments.receipt_number`

| Column | Type | Constraints |
|---|---|---|
| `receipt_number` | VARCHAR(32) | NULL; UNIQUE WHERE NOT NULL |

---

## 7. Required Test Matrix (R2 Final)

| # | Test | Decision Ref |
|---|---|---|
| TM-01 | Zero accounting on submit | BC-2 |
| TM-02 | A/B supplier isolation | BC-10 |
| TM-03 | Same-schema wrong-retailer denial | BC-10 |
| TM-04 | Duplicate submit: same retailer+key+payload → existing; different payload → 409 | DD-12 |
| TM-05 | Concurrent confirm: one canonical payment, same receipt | DD-03 |
| TM-06 | Sequential confirm replay: same payment_id, same receipt, zero writes | DD-03 |
| TM-07 | Reject: terminal, no financial effect | DD-02 |
| TM-08 | Non-pending confirm/reject → DECLARATION_NOT_PENDING | DD-14 |
| TM-09 | Overpayment at confirm → PAYMENT_EXCEEDS_REMAINING | DD-04 |
| TM-10 | Negative/zero amount → 400 | DD-14 |
| TM-11 | Invalid method (credit) → 400 | DD-14 |
| TM-12 | Malformed order_id → 404 | DD-14 |
| TM-13 | Unauthorized retailer (no client:payments:declare) → 403 | DD-10 |
| TM-14 | Unauthorized cashier (no payments:confirm_declaration) → 403 | DD-10 |
| TM-15 | Inactive binding → 403 | BC-6 |
| TM-16 | Confirmed receipt visible via confirmation_payment_id → payments.receipt_number | DD-05 |
| TM-17 | Pending print → "Not Received" | BC-8 |
| TM-18 | Print privacy: no internal identifiers | DD-13 |
| TM-19 | Canonical payment/ledger/receivable/order regressions unchanged | DD-04 |
| TM-20 | Route inventory: GAP-07 updated; client:payments:declare on one route | DD-10 |
| TM-21 | Permission registry: client:payments:create removed; client:payments:declare + payments:confirm_declaration added; admin has it, retailer_operator does not | DD-10 |
| TM-22 | No notification emission | DD-09 |
| TM-23 | Receipt number uniqueness: concurrent confirms → unique receipt numbers | DD-05 |
| TM-24 | Statement server-side projection: dual-key scoped; no tenant-wide query | DD-06 |
| TM-25 | Statement: no opening/closing balance in MVP (deferred) | DD-06 |
| TM-26 | CanonicalPaymentService: both pay_order and confirmation call it; neither calls the other | DD-04 |
| TM-27 | FK RESTRICT: cannot delete payment referenced by confirmed declaration | DD-07 |
| TM-28 | Migration 037: live tenant enumeration via tenant_registrations JOIN wholesalers | DD-08 |
| TM-29 | Migration 037: no per-tenant alembic_version check | DD-08 |
| TM-30 | Migration 037: semantic preflight fails closed on incompatible catalog | DD-08 |
| TM-31 | Migration 037: rogue schemas untouched | DD-08 |
| TM-32 | Migration 037: second upgrade is no-op | DD-08 |
| TM-33 | Exact 035/036 live-status-set contract: migration 037 uses `("pending_email_verification", "email_verified", "provisioning", "active", "failed")` for registrations and `("active", "provisioning")` for wholesalers — matching 035 and 036 exactly (R4) | DD-08 |
| TM-34 | Declaration key vs canonical payment key: no collision; declaration key not passed as payment key (R4) | DD-16 |
| TM-35 | Two retailers using the same declaration key independently: both succeed, independent payments, no collision (R4) | DD-12, DD-16 |
| TM-36 | Partial cashier-confirmed payment: order transitions CONFIRMED → PARTIALLY_PAID; payment completed; balance reduced (R4) | DD-17 |
| TM-37 | Final confirmation closes exposure: cumulative payments reach total; order → PAID; balance → 0 (R4) | DD-17 |
| TM-38 | Receipt only for cashier-confirmed completed payment: pending declaration has no receipt_number on payment row (R4) | DD-05, DD-17 |
| TM-39 | transfer_reference maps exactly to transaction_id on canonical payment row (R4) | DD-15 |
| TM-40 | Duplicate transfer reference at confirmation → controlled 409 DUPLICATE_TRANSFER_REFERENCE (R4) | DD-15 |
| TM-41 | Exact canonical confirm key: payment.idempotency_key = `decl-confirm-{declaration_id.hex}`; never the retailer declaration key (R4-R1) | DD-16 |
| TM-42 | Cross-retailer key reuse: two retailers use the same declaration idempotency_key; both succeed independently; different canonical payments (R4-R1) | DD-12, DD-16 |
| TM-43 | transfer_reference 128 chars accepted; 129 chars rejected with 400 DECLARATION_TRANSFER_REFERENCE_TOO_LONG; no truncation (R4-R1) | DD-15 |
| TM-44 | Blank/whitespace-only transfer_reference rejected with 400 DECLARATION_TRANSFER_REFERENCE_REQUIRED (R4-R1) | DD-15 |
| TM-45 | Duplicate transfer reference → controlled 409 DUPLICATE_TRANSFER_REFERENCE; tenant-local scope (R4-R1) | DD-15 |
| TM-46 | Every confirmation creates status='completed' payment; no path produces pending payment from confirmation (R4-R1) | DD-17 |
| TM-47 | Direct pay_order behavior preserved: existing pending/completed status logic unchanged after CanonicalPaymentService extraction (R4-R1) | DD-04, DD-17 |
| TM-48 | DR/FIND mechanical accounting: findings=46, mapped=46, gap=0; every CSV decision_ref is a valid DR ID (R4-R1) | DD-01 through DD-17 |

---

## 8. Risk Assessment (R2.7 Corrected)

| Risk | Level | Rationale |
|---|---|---|
| **Overall financial blast radius** | **HIGH** | Touches canonical payment write path |
| CanonicalPaymentService extraction regression | **HIGH** | Refactoring sole money-movement path |
| Confirmation bypasses canonical path | **HIGH** | Prevented by DD-04 |
| Frontend permission mismatch | **RESOLVED** | Fixed in H3 (merged) |
| `configure_app` route registration | **MEDIUM** | New routes under existing prefixes; must update GAP-07 inventory tests |
| Concurrent double-confirmation | **MEDIUM** | Mitigated by FOR UPDATE + idempotent replay |
| Receipt number collision | **MEDIUM** | Mitigated by atomic sequence allocator |
| Statement balance computation | **DEFERRED** | Opening/closing balance removed from MVP |
| Permission rename | **LOW** | client:payments:create proven unused |

### Required Regression Bundles (R2.7)

| Bundle | Tests |
|---|---|
| Payment integrity | `test_dc11d_payment_replay_concurrency_integrity.py`, `test_dc10f_payment_method_integrity.py`, `test_payments_api.py`, `test_payment_atomicity.py` |
| Ledger integrity | `test_s5_ledger.py`, `test_s5_5_ledger_hardening.py` |
| Receivable integrity | `test_dc11t4h_receivable_collection_integrity.py`, `test_receivables_service.py` |
| Order-state integrity | `test_dc11d` state tests, `test_s4*` inventory invariant tests |
| Concurrency | `test_dc11d` concurrent tests, `test_dc11t4h` concurrent tests |
| Migration | `test_dc12r1_s1_r5_migration_preflight_exact_catalog.py`, `test_s4g_migration_infrastructure_hardening.py`, `test_payments_schema_contract.py` |
| RBAC | `test_route_authorization_policy.py`, `test_rbac_enforcement.py`, `test_dc12r1_s3_s1_catalog_order_hardening.py` (GAP-07) |
| Retailer isolation | `test_dc12r1_s3_s2_read_only_retailer_finance.py`, `test_dc12r1_s2_supplier_scoped_retailer_login.py` |

**Two fresh PG16/Redis7 full backend gates** required during implementation.

**Frontend Vitest/build** required.

**Independent post-implementation review** required.

---

## 9. Character Encoding Note

No mojibake detected (scan for U+FFFD: zero hits). Non-ASCII punctuation (em-dash) is intentional valid UTF-8, not mojibake.

---

## 10. GitNexus Impact

| Symbol | Change | Risk |
|---|---|---|
| `pay_order` (orders.py:558) | Refactored — logic extracted to CanonicalPaymentService | **HIGH** |
| `CanonicalPaymentService` (NEW) | New service | **HIGH** |
| `configure_app` (app.py) | New routes registered | **MEDIUM** |
| `permission_registry.py` | Permission rename + addition | LOW |
| `LedgerService.get_balance` | NOT used for retailer statements (R2.5) | LOW |

---

## 11. Out of Scope

- Migration 037 implementation, routes, services, UI, financial writes
- SMS/WhatsApp, file upload, server-side PDF
- Notification emission / transactional outbox
- Opening/closing balance on statements (deferred — DD-06)
- S3-S3, S4 implementation

---

## 12. Pre-Commit Self-Review

| # | Check | Result |
|---|---|---|
| 1 | Tenant enumeration via tenant_registrations JOIN wholesalers with 035/036 filters | PASS |
| 2 | No per-tenant alembic_version claims | PASS |
| 3 | alembic_version sole-head checks are public-only | PASS |
| 4 | Migration 037 preflight checks real catalog, not IF NOT EXISTS | PASS |
| 5 | Bootstrap parity proven by real tests, not upgrade() assertions | PASS |
| 6 | receipt_number single source = payments.receipt_number | PASS |
| 7 | receipt_number removed from payment_declarations | PASS |
| 8 | Replay resolves receipt through confirmation_payment_id | PASS |
| 9 | Same-schema FKs with RESTRICT semantics | PASS |
| 10 | Receipt format RCT-YYYYMMDD-NNNNNN using UTC | PASS |
| 11 | receipt_sequences uses business_date CHAR(8) | PASS |
| 12 | Idempotency UNIQUE(retailer_id, idempotency_key) | PASS |
| 13 | No LedgerService.get_balance for retailer statements | PASS |
| 14 | Statement uses dual-key projection (wholesaler_id + retailer_id) | PASS |
| 15 | Opening/closing balance deferred if not provable | PASS |
| 16 | payments:confirm_declaration in registry + ADMIN_PERMISSIONS | PASS |
| 17 | retailer_operator never receives confirm permission | PASS |
| 18 | configure_app risk = MEDIUM | PASS |
| 19 | Full regression bundles defined | PASS |
| 20 | Two PG16/Redis7 gates required | PASS |
| 21 | Frontend Vitest/build required | PASS |
| 22 | Post-implementation review required | PASS |
| 23 | git diff --check | PASS |
| 24 | No mojibake; non-ASCII intentional | PASS |
| 25 | detect-secrets | PASS |
| 26 | Exact changed-file proof | PASS |
| 27 | No product code implemented | PASS |
| 28 | Report/CSV accounting gap = 0 | PASS |
| 29 | Stale `'provisioned'` status removed; exact 035/036 set has `'failed'` not `'provisioned'` (R4.1) | PASS |
| 30 | transfer_reference maps exactly to transaction_id (R4.2, DD-15) | PASS |
| 31 | Declaration key vs canonical payment key: no collision (R4.3, DD-16) | PASS |
| 32 | Partial confirmation → PARTIALLY_PAID; final → PAID (R4.4, DD-17) | PASS |
| 33 | Receipt only for completed payment, never pending (R4.4, DD-17) | PASS |
| 34 | Duplicate transfer reference → 409 DUPLICATE_TRANSFER_REFERENCE (R4.5, DD-15) | PASS |
| 35 | No stale 0aec baseline reference (product baseline is 0f9d259b) | PASS |
| 36 | FIND-01 through FIND-46 all mapped in CSV (gap=0) | PASS |
| 37 | Canonical confirm key = `decl-confirm-{declaration_id.hex}`; never declaration key (R4-R1.1) | PASS |
| 38 | transfer_reference: trim, reject blank, 1-128, no truncation, widen transaction_id VARCHAR(128) (R4-R1.2) | PASS |
| 39 | Every confirmation creates status='completed'; no pending-from-confirmation language (R4-R1.3) | PASS |
| 40 | Direct pay_order status behavior preserved unchanged (R4-R1.3) | PASS |
| 41 | DR-01 through DR-12 restored in decision register; FIND-01–FIND-46 mapped to valid DR IDs (R4-R1.4) | PASS |
| 42 | CTO_CURRENT_OPS.md + PROJECT.md updated to 0f9d259b; stale 0aec removed (R4-R1.5) | PASS |
| 43 | No contradictory pending-confirmation language found | PASS |

---

## 13. Verdict

```
PASS_FOR_CTO_DC12R1_S3_S2B_IMPLEMENTATION_PLANNING_R4_R2
```

All accounting sources of truth resolved. No tenant-wide statement query exposed to a retailer. No duplicate receipt source. No migration relying on per-tenant alembic_version. No product code or migration implementation started.
