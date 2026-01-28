# 2026-01-27 Phase B4 Completion — Inventory MVP

## 1. New API list

Base path: `/api/v1`

### SKU master
- `GET /api/v1/skus`
  - Purpose: List SKU master data (tenant-scoped)
  - Query: `page`, `size`, `is_active?`, `q?`
  - Response: `DataResponse[{ items: SKURead[], pagination: Pagination }]`

- `POST /api/v1/skus`
  - Purpose: Create a SKU master record
  - Request: `SKUCreateRequest`
  - Response: `DataResponse[SKURead]`

- `GET /api/v1/skus/{sku_code}`
  - Purpose: Get SKU detail by stable key `sku_code`
  - Response: `DataResponse[SKURead]`

- `PUT /api/v1/skus/{sku_code}`
  - Purpose: Update SKU attributes (name/unit/category/is_active)
  - Request: `SKUUpdateRequest`
  - Response: `DataResponse[SKURead]`

### Inventory stock view (read-only)
- `GET /api/v1/inventory/stocks`
  - Purpose: List stock view by SKU (read-only)
  - Query: `page`, `size`, `sku_code?`, `is_active?`
  - Response: `DataResponse[{ items: StockViewRead[], pagination: Pagination }]`

- `GET /api/v1/inventory/stocks/{sku_code}`
  - Purpose: Stock view detail for one SKU (read-only)
  - Response: `DataResponse[StockViewRead]`

- `GET /api/v1/inventory/orders/{order_id}/stocks`
  - Purpose: Read-only stock view for all SKU codes referenced by an existing order’s order_items
  - Response: `DataResponse[{ order_id: string, items: StockViewRead[] }]`

## 2. New DB tables and relationships

All new tables are created in **tenant schema** (same strategy as Phase B3 orders).

### `skus`
- `id` UUID PK
- `sku_code` varchar(64) UNIQUE (stable key)
- `name` varchar(255)
- `description` text nullable
- `unit` varchar(32)
- `category` varchar(64) nullable
- `is_active` boolean
- standard audit columns + user tracking (`created_at`, `updated_at`, `is_deleted`, `deleted_at`, `created_by`, `updated_by`)

### `inventory_stocks`
- `id` UUID PK
- `sku_id` UUID UNIQUE FK -> `skus.id` (CASCADE)
- `quantity_on_hand` numeric(12,2)
- `quantity_reserved` numeric(12,2)
- standard audit columns + user tracking

### Relationship to Orders / OrderItems (read-only)
- Phase B3 `order_items` already contains `sku_code` snapshot.
- Phase B4 uses `sku_code` as the stable link to `skus.sku_code` for display/validation.
- **No schema or API breaking changes** were made to B3 orders.

Explicit confirmation:
- **NO stock movement journal**
- **NO stock transactions/event sourcing**
- **NO reservation/commit/release workflow**

## 3. Inventory behavior guarantees
- Orders reference real SKUs by stable key `sku_code`.
- Inventory quantities are **not mutated** by order create/confirm/cancel in Phase B4.
- Any stock validation/display is **read-only**.

## 4. Unimplemented items (intentional)
- Purchasing / inbound receiving
- Stock movement journals / inventory transactions
- Auto reservation / release
- Picking / packing / shipment
- Warehouse / location hierarchy (multi-warehouse, bins, zones)
- Returns / exchanges

## 5. Frozen zone statement
- 是否触碰冻结区：否

## Migration
- `backend/alembic/versions/004_phase_b4_sku_inventory_mvp.py`

Apply to a tenant schema:
```bash
alembic upgrade head -x tenant_schema=t_<tenant_uuid>
```

## Verification (curl)
Prereqs:
- Obtain access token via `/api/v1/auth/login`.
- Use tenant token (includes `tenant_schema`, `tenant_id`, `user_id`).

### 1) Create SKU
```bash
curl.exe -s -X POST http://127.0.0.1:8000/api/v1/skus \
  -H "Authorization: Bearer <ACCESS_TOKEN>" \
  -H "Content-Type: application/json" \
  -d "{\"sku_code\":\"SUGAR-1KG\",\"name\":\"Sugar 1kg\",\"unit\":\"kg\",\"is_active\":true}"
```

### 2) Get Stock View (should be 0/0 initially)
```bash
curl.exe -s http://127.0.0.1:8000/api/v1/inventory/stocks/SUGAR-1KG \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

### 3) List SKUs
```bash
curl.exe -s "http://127.0.0.1:8000/api/v1/skus?page=1&size=10" \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```

### 4) Stock view for an order (read-only)
```bash
curl.exe -s http://127.0.0.1:8000/api/v1/inventory/orders/<ORDER_ID>/stocks \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
```
