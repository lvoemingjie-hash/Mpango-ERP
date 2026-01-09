# Domain Workflows (MVP) — Sync vs Async Boundaries

## 0. MVP decisions (frozen)
### 0.1 Idempotency-Key policy
- REQUIRED (client must provide `Idempotency-Key` header):
  1) Inbound receive (goods receipt)
  2) Transfer payment creation (method=transfer)
- NOT required (keep API simple in MVP):
  - other write operations (create order, update profile, etc.)
- Server behavior:
  - If required Idempotency-Key is missing -> 400 with business error code `MISSING_IDEMPOTENCY_KEY`.
  - Idempotency scope is per-tenant.

### 0.2 Inventory deduction timing
- create order: creates draft only, does NOT reserve or deduct inventory.
- confirm order: deduct inventory; if insufficient inventory -> fail.
- ship order: status change only; no inventory change.
This aligns with Order status and InventoryLog change types already defined. [file:5]

## 1. Architecture boundaries (MVP)
- backend-service: synchronous HTTP APIs; performs state transitions in a single DB transaction.
- worker-service: asynchronous Celery tasks (Redis broker + result backend) for long-running jobs (imports/sync/suggestions). [file:3]

## 2. Common conventions
### 2.1 State machine enforcement
- All transitions must be validated server-side.
- Any invalid transition returns 409 (business/state conflict).

### 2.2 Inventory accounting
- Any inventory movement must create InventoryLog:
  - change_type in {sale, purchase, adjustment, cancel}
  - qty_change signed (+/-)
  - reference_id points to source document id (order.id / purchase_order.id)
  - operator_id is current user [file:5]

### 2.3 Idempotency implementation rule (MVP)
For endpoints that require Idempotency-Key:
- Store an idempotency record keyed by:
  - tenant_id + endpoint_name + idempotency_key
- If the same key repeats:
  - return the same success response without repeating side effects.
- Keys should expire after a retention window (e.g., 24h) (MVP recommendation).

## 3. Sales workflow (Order)
### 3.1 Entities & statuses
- Order status: pending -> confirmed -> shipped -> completed, and canceled. [file:5]
- OrderItem contains product_id, quantity, price. [file:5]

### 3.2 Actions (sync, backend-service)
#### Create Order (orders:create)
- Preconditions:
  - Retailer exists and is allowed under wholesaler (binding rules applied). [file:5]
- Writes (single DB transaction):
  - orders (status=pending)
  - order_items
- Inventory impact: none (MVP frozen).

#### Confirm Order (orders:confirm)
- Preconditions:
  - order.status == pending
  - inventory.quantity sufficient for each item
- Writes (single DB transaction):
  - orders.status = confirmed
  - inventory.quantity -= item.quantity
  - inventory_logs:
    - change_type = sale
    - qty_change = -quantity
    - reference_id = order.id
    - operator_id = current_user [file:5]
- Retry behavior:
  - If order already confirmed -> return success (do not double-deduct).

#### Ship Order (orders:ship)
- Preconditions:
  - order.status == confirmed
- Writes:
  - orders.status = shipped
- Inventory impact: none (MVP frozen).

#### Complete Order
- Preconditions:
  - order.status == shipped
- Writes:
  - orders.status = completed

#### Cancel Order (orders:cancel)
- Preconditions:
  - allowed if status in {pending, confirmed} (MVP decision)
- Writes:
  - orders.status = canceled
  - If cancel from confirmed:
    - inventory.quantity += item.quantity
    - inventory_logs:
      - change_type = cancel
      - qty_change = +quantity
      - reference_id = order.id
      - operator_id = current_user [file:5]
- Retry behavior:
  - If already canceled -> return success (no repeated inventory changes).

## 4. Procurement workflow (PurchaseOrder + Inbound)
### 4.1 Entities & statuses
- PurchaseOrder status: draft -> pending -> received -> completed, and canceled. [file:5]
- InboundLog: purchase_order_id, product_id, quantity, received_at, operator_id. [file:5][file:13]

### 4.2 Actions (sync, backend-service)
#### Create Purchase Order (purchase_orders:create)
- Writes:
  - purchase_orders (status=draft)
  - purchase_order_items

#### Submit Purchase Order (purchase_orders:submit)
- Preconditions:
  - purchase_orders.status == draft
- Writes:
  - purchase_orders.status = pending

#### Receive Inbound / Goods Receipt (purchase_orders:receive)
- Idempotency-Key: REQUIRED.
- Preconditions:
  - purchase_orders.status == pending
- Writes (single DB transaction):
  - inbound_logs rows
  - inventory.quantity += received_qty
  - inventory_logs:
    - change_type = purchase
    - qty_change = +received_qty
    - reference_id = purchase_order.id
    - operator_id = current_user [file:5]
  - purchase_orders.status = received
- Idempotency behavior:
  - same Idempotency-Key repeats -> return same response; do not insert inbound/logs again.

#### Complete Purchase Order
- Preconditions:
  - purchase_orders.status == received
- Writes:
  - purchase_orders.status = completed

#### Cancel Purchase Order
- Preconditions:
  - status in {draft, pending}
- Writes:
  - purchase_orders.status = canceled
- Inventory impact: none.

## 5. Payments workflow (Payment)
### 5.1 Entities & methods
- Payment methods: cash | transfer | credit. [file:5]

### 5.2 Actions (sync, backend-service)
#### Create Payment (payments:create)
- If method == transfer:
  - Idempotency-Key: REQUIRED.
  - transaction_id SHOULD be provided and treated as a unique identifier per tenant (recommended). [file:5]
- Preconditions:
  - order exists
  - amount > 0
- Writes:
  - payments row (includes method, amount, transaction_id when applicable). [file:5]
- Idempotency behavior (transfer):
  - same Idempotency-Key repeats -> return same response; do not create a second payment row.

#### Confirm Payment (payments:confirm)
- MVP note:
  - If Payment has no status field, this action can be omitted.
  - If added, set payment.status=confirmed and store confirmed_at.

#### Refund Payment (optional MVP)
- Record refund as:
  - new payment row with negative amount (MVP recommended),
  - OR a separate refunds table (future).
Pick one and standardize before implementation.

## 6. Async workflows (worker-service)
### 6.1 Product catalog import (products:import)
- Trigger:
  - backend-service creates an import job record + stores file (e.g., S3) then enqueues Celery task. [file:3][file:13]
- Worker responsibilities:
  - parse file
  - validate schema
  - upsert products + product_attributes
  - update job status/progress
- Retry behavior:
  - tasks must be idempotent by job_id (retries do not duplicate products).

### 6.2 Supplier sync / import
- Trigger:
  - backend-service enqueues sync job (MVP: async to avoid request timeouts). [file:13]
- Worker responsibilities:
  - sync supplier catalog
  - write sync status & error logs

### 6.3 Replenishment suggestions
- Trigger:
  - backend-service enqueues suggestion job; API returns job_id for polling. [file:13]
- Worker responsibilities:
  - compute suggestions
  - store results for API retrieval
