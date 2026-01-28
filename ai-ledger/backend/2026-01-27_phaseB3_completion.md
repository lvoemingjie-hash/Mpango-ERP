# 2026-01-27 Phase B3 Completion — Order Minimal Closed Loop

## Goal
Implement a minimal sales order lifecycle so the system "feels like an ERP".

Scope delivered:
- Create Order (master + items)
- List Orders (filter by status/retailer)
- Get Order Detail
- Manual status transitions

Out of scope (explicit):
- Payments
- Inventory deduction / stock checks
- Shipping / logistics integrations
- Automatic tax/discount engine

## Architecture Decisions (CTO)
- Schema placement: `orders` and `order_items` are tenant-scoped tables (tenant schema).
- Authentication: all order APIs require authentication.
- `wholesaler_id` is inferred from authenticated context: `wholesaler_id = token.tenant_id`.
- Permission simplification: for Phase B3, no complex role checks; any authenticated user can operate on orders.

## New / Updated APIs
Base path: `/api/v1/orders`

- `POST /api/v1/orders`
  - Create order in `draft` status
  - `wholesaler_id` inferred from token
  - Request body includes `retailer_id` and `items[]` snapshots

- `GET /api/v1/orders`
  - List orders (pagination)
  - Filters: `status`, `retailer_id`

- `GET /api/v1/orders/{order_id}`
  - Order detail (includes items)

- `POST /api/v1/orders/{order_id}/confirm`
  - Manual transition: `draft -> confirmed`

- `POST /api/v1/orders/{order_id}/cancel`
  - Manual transition: `draft/confirmed -> cancelled`

## Data Model / DB Tables
Tenant schema tables:

### `orders`
- `id` (UUID PK)
- `wholesaler_id` (UUID, NOT NULL) — inferred from token (`tenant_id`)
- `retailer_id` (UUID, NOT NULL)
- `status` (enum `draft|confirmed|cancelled`)
- `total_amount` (numeric)
- `notes` (text, nullable)
- audit columns: `created_at`, `updated_at`, `is_deleted`, `deleted_at`
- user tracking: `created_by`, `updated_by`

### `order_items`
- `id` (UUID PK)
- `order_id` (UUID FK -> orders.id, CASCADE)
- `product_name` (text, NOT NULL) — snapshot
- `sku_code` (varchar(64), NOT NULL) — snapshot
- `quantity` (int, NOT NULL)
- `unit_price` (numeric, NOT NULL)
- `subtotal` (numeric, NOT NULL)
- audit columns + user tracking

## State Machine
Implemented states:
- `draft` (initial)
- `confirmed` (manual)
- `cancelled` (manual)

Allowed transitions:
- `draft -> confirmed`
- `draft -> cancelled`
- `confirmed -> cancelled`

Forbidden transitions:
- `cancelled -> confirmed`
- `confirmed -> draft`

## Migrations
- `backend/alembic/versions/003_phase_b3_orders_minimal_closed_loop.py`
  - Tenant-schema migration evolving existing order tables to Phase B3:
    - Update `order_status` enum to `draft|confirmed|cancelled` (maps `pending -> draft`, `shipped -> confirmed`)
    - Add `orders.wholesaler_id`
    - Add `order_items.product_name` and `order_items.sku_code`
    - Drop `order_items.product_id` if present

## OpenAPI
- Updated: `docs/contracts/openapi.yaml`
  - Removed `/orders/{order_id}/ship`
  - Updated order schemas to snapshot items
  - Updated `OrderStatus` enum values
  - Added `wholesaler_id` to `Order`
  - Removed orders RBAC permission wording from order endpoints (auth-only)

## Frozen zone statement
- 是否触碰冻结区：否

## Verification (curl)
Prereqs:
- Obtain access token via `/api/v1/auth/login`.
- Use tenant schema-aware token (includes `tenant_id`, `tenant_schema`, `user_id`).

### 1) Create Order (Draft)
```bash
curl.exe -s -X POST http://127.0.0.1:8000/api/v1/orders \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d "{\"retailer_id\":\"<RETAILER_UUID>\",\"items\":[{\"product_name\":\"Sugar 1kg\",\"sku_code\":\"SUGAR-1KG\",\"quantity\":2,\"unit_price\":10.00}],\"notes\":\"B3 test order\"}"
```
Expected:
- `201`
- response `data.status == "draft"`
- response includes `wholesaler_id` inferred from token

### 2) Confirm Order
```bash
curl.exe -s -X POST http://127.0.0.1:8000/api/v1/orders/<ORDER_ID>/confirm \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d "{}"
```
Expected:
- `200`
- response `data.status == "confirmed"`

### 3) Cancel Order
```bash
curl.exe -s -X POST http://127.0.0.1:8000/api/v1/orders/<ORDER_ID>/cancel \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d "{}"
```
Expected:
- `200`
- response `data.status == "cancelled"`

---

## Notes / Known Limitations
- No inventory validation or deductions.
- Item pricing is passed in payload and stored as snapshot values.
- Retailer/wholesaler relationship validation is not enforced beyond storing UUIDs (Phase B4+ may enforce stronger constraints).
