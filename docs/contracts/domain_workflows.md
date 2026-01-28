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

---

## 1. Architecture boundaries (MVP)
- backend-service: synchronous HTTP APIs; performs state transitions in a single DB transaction.
- worker-service: asynchronous Celery tasks (Redis broker + result backend) for long-running jobs.

---

## 2. Common conventions

### 2.1 State machine enforcement
- All transitions must be validated server-side.
- Any invalid transition returns 409 (business/state conflict).

### 2.2 Inventory accounting
- Any inventory movement must create InventoryLog:
  - change_type in {sale, purchase, adjustment, cancel}
  - qty_change signed (+/-)
  - reference_id points to source document id
  - operator_id is current user
  
- **Single Warehouse Assumption (MVP)**:
  - While the database schema includes `warehouse_id`, the system will operate effectively as single-warehouse per tenant for MVP.
  - All inventory queries MUST aggregate quantities by `product_id`.
  - Inter-warehouse transfers are Out of Scope for MVP.

### 2.3 Idempotency implementation rule (MVP)
For endpoints that require Idempotency-Key:
- Store an idempotency record keyed by: tenant_id + endpoint_name + idempotency_key
- If the same key repeats: return the same success response without repeating side effects.
- Keys should expire after a retention window (e.g., 24h).

---

## 3. Sales workflow (Order)

### 3.1 Entities & statuses
- Order status: pending -> confirmed -> shipped -> completed, and canceled.
- OrderItem contains product_id, quantity, price.

### 3.1.1 Retailer–Wholesaler Binding Rules (MVP Clarification)
- **Many-to-Many Model**: A Retailer MAY be bound to multiple Wholesalers. The `Binding` table governs these relationships.
- **Order Validation**: Every Order MUST be linked to a specific `wholesaler_id`. The backend MUST validate that an active `Binding` exists between the `order.retailer_id` and `order.wholesaler_id` at the time of creation.
- **Failure Case**: If no valid binding is found, the API MUST return `403 FORBIDDEN` with error code `BINDINGNOTFOUND`.

### 3.1.2 Credit Limit Policy (MVP Hard Block)
- **Configuration**: Credit limits are defined in `CustomerProfile` per retailer-wholesaler pair.
- **Calculation Formula**: `Current Exposure = Sum(Unpaid Orders Total) - Sum(Payments)`.
- **Enforcement**: When an order transitions to a strictly binding state (e.g., `confirmed`), the backend MUST check:
  `Current Exposure + Order Total <= Credit Limit`
- **Violation**: If the limit is exceeded, the transition MUST fail with `409 CONFLICT` and error code `CREDITLIMITEXCEEDED`. The system MUST NOT allow the order to proceed effectively blocking the shipment.

### 3.1.3 Price Snapshot Rule
- **Logic**: `Product.price` is the dynamic list price. `OrderItem.price` is the transactional snapshot.
- **Constraint**: When an order is created, the backend MUST calculate `OrderItem.price` based on the current `Product.price`.
- **Immutability**: Subsequent changes to the master `Product.price` MUST NOT affect existing `OrderItems`. The order price is locked at creation.

### 3.2 Actions (sync, backend-service)

#### Create Order (orders:create)
- Preconditions: Retailer exists and is allowed under wholesaler.
- Writes: orders (status=pending), order_items
- Inventory impact: none (MVP frozen).

#### Confirm Order (orders:confirm)
- Preconditions: order.status == pending, inventory.quantity sufficient
- Writes:
  - orders.status = confirmed
  - inventory.quantity -= item.quantity
  - inventory_logs: change_type = sale, qty_change = -quantity

#### Ship Order (orders:ship)
- Preconditions: order.status == confirmed
- Writes: orders.status = shipped
- Inventory impact: none (MVP frozen).

#### Cancel Order (orders:cancel)
- Preconditions: status in {pending, confirmed}
- Writes:
  - orders.status = canceled
  - If cancel from confirmed: inventory.quantity += item.quantity, inventory_logs: change_type = cancel

---

## 4. Procurement workflow (PurchaseOrder + Inbound)

### 4.1 Entities & statuses
- PurchaseOrder status: draft -> pending -> received -> completed, and canceled.
- InboundLog: purchase_order_id, product_id, quantity, received_at, operator_id.

### 4.2 Actions (sync, backend-service)

#### Create Purchase Order (purchase_orders:create)
- Writes: purchase_orders (status=draft), purchase_order_items

#### Submit Purchase Order (purchase_orders:submit)
- Preconditions: purchase_orders.status == draft
- Writes: purchase_orders.status = pending

#### Receive Inbound / Goods Receipt (purchase_orders:receive)
- Idempotency-Key: REQUIRED.
- Preconditions: purchase_orders.status == pending
- Writes:
  - inbound_logs rows
  - inventory.quantity += received_qty
  - inventory_logs: change_type = purchase, qty_change = +received_qty
  - purchase_orders.status = received

---

## 5. Payments workflow (Payment)

### 5.1 Entities & methods
- Payment methods: cash | transfer | credit.

### 5.2 Actions (sync, backend-service)

#### Create Payment (payments:create)
- If method == transfer:
  - Idempotency-Key: REQUIRED.
  - transaction_id SHOULD be provided.
- Preconditions: order exists, amount > 0
- Writes: payments row

---

## 6. Async workflows (worker-service)

### 6.1 Product catalog import (products:import)
- Trigger: backend-service creates import job + enqueues Celery task.
- Worker: parse file, validate schema, upsert products.

### 6.2 Supplier sync / import
- Trigger: backend-service enqueues sync job.
- Worker: sync supplier catalog, write sync status.

### 6.3 Replenishment suggestions
- Trigger: backend-service enqueues suggestion job.
- Worker: compute suggestions, store results.
