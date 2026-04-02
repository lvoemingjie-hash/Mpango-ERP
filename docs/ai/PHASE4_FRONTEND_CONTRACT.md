# Phase 4 Frontend Contract — Backend Handoff for GEMINI

**Date:** 2026-04-01
**Author:** Backend AI
**Branch:** `product-dev`
**Status:** Backend complete — ready for frontend integration

---

## 1. Wholesaler Order Creation

### Breaking Change

`POST /api/v1/orders` request schema has changed. The old `OrderItemCreate` (which accepted `product_name`, `sku_code`, `quantity`, `unit_price`) is **replaced** by `WholesalerOrderItemCreate` which accepts **only** `sku_code` + `quantity`.

### New Request Shape

```
POST /api/v1/orders
Authorization: Bearer <token>
Content-Type: application/json

{
  "retailer_id": "uuid-string",
  "items": [
    { "sku_code": "WIDGET-001", "quantity": 5 },
    { "sku_code": "BOLT-002", "quantity": 10 }
  ],
  "notes": "Optional order notes"
}
```

### Key Behaviors

- **No `unit_price` or `product_name` in request** — server resolves both from SKU catalog + `retailer_prices` table
- **Retailer binding validated** — 400 if retailer not bound to this wholesaler
- **Per-item validation** with accumulated errors:
  - SKU not found → error
  - SKU inactive → error
  - Insufficient stock → error with available qty
  - No price configured for this retailer → error
  - Price ≤ 0 → error
- **Error response** (400):
  ```json
  {
    "detail": {
      "code": "ORDER_VALIDATION_FAILED",
      "message": "Some items cannot be ordered",
      "errors": ["No price configured for 'BOLT-002' for this retailer. Set a price before creating orders."]
    }
  }
  ```
- **Success response** — unchanged `OrderResponse` shape with resolved prices in items

### Frontend Requirements

The wholesaler order creation form needs:
1. **Retailer selector** — call `GET /api/v1/retailers/bindings` for bound retailers
2. **Product picker** — needs a wholesaler-facing product list with stock + price for the selected retailer. Use existing `GET /api/v1/skus` for the SKU list, and `GET /api/v1/pricing/prices?retailer_id=<uuid>` for retailer-specific prices
3. **Quantity input** per selected SKU
4. **Submit** — `POST /api/v1/orders` with the new slim shape above

---

## 2. Retailer Price Management

### New Endpoints

#### List prices for a retailer

```
GET /api/v1/pricing/prices?retailer_id=<uuid>&page=1&size=50
Authorization: Bearer <token>
Permission: pricing:read
```

**Response:**
```json
{
  "success": true,
  "data": {
    "items": [
      {
        "sku_id": "uuid",
        "sku_code": "WIDGET-001",
        "sku_name": "Widget A",
        "retailer_id": "uuid",
        "price": 150.00,
        "updated_at": "2026-04-01T00:00:00Z"
      }
    ],
    "total": 1
  },
  "timestamp": "..."
}
```

#### Set or update a retailer price

```
PUT /api/v1/pricing/prices
Authorization: Bearer <token>
Permission: pricing:write
Content-Type: application/json

{
  "retailer_id": "uuid-string",
  "sku_id": "uuid-string",
  "price": 175.50
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "sku_id": "uuid",
    "retailer_id": "uuid",
    "price": 175.50,
    "action": "created"  // or "updated"
  },
  "message": "Price created successfully",
  "timestamp": "..."
}
```

**Validation:**
- `price` must be > 0 (schema + DB constraint)
- Retailer must be bound to this wholesaler (400 if not)
- SKU must exist (404 if not)

### Frontend Requirements

The price management UI needs:
1. **Retailer selector** — same as order creation
2. **Price list table** — call `GET /api/v1/pricing/prices?retailer_id=<uuid>` showing SKU code, name, current price
3. **Inline edit or modal** — to set/update price per SKU
4. **SKU picker** for adding new prices (for SKUs not yet priced for this retailer)

---

## 3. RBAC Permissions Required

| Endpoint | Permission |
|----------|-----------|
| `POST /api/v1/orders` | `orders:create` |
| `GET /api/v1/pricing/prices` | `pricing:read` |
| `PUT /api/v1/pricing/prices` | `pricing:write` |

---

## 4. Existing Endpoints Unchanged

- `GET /api/v1/orders` — list orders (unchanged)
- `GET /api/v1/orders/{id}` — get order (unchanged)
- All state transition endpoints — unchanged
- All client (retailer) endpoints — unchanged
- `GET /api/v1/retailers/bindings` — list bound retailers (unchanged)
- `GET /api/v1/skus` — list SKUs (unchanged)

---

## 5. Error Codes Reference

| Code | HTTP | Meaning |
|------|------|---------|
| `ORDER_VALIDATION_FAILED` | 400 | One or more items failed validation (see `errors` array) |
| `RETAILER_NOT_BOUND` | 400 | Retailer not bound to this wholesaler |
| `SKU_NOT_FOUND` | 404 | SKU UUID not found in catalog |
