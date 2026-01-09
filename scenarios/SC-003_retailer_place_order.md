# SC-003: Retailer Place Order

## Scenario ID
`SC-003`

## Feature
**Sales Order Management**

## User Story
```
As a Sales Staff
I want to create orders for retailers
So that I can process their purchase requests and track sales
```

## Authority
- **L0**: `RBAC Matrix (MVP).md` - orders:create permission
- **L1**: `Domain Workflows (MVP).md` - Order creation flow

---

## Scenario: Sales Staff Creates Order for Retailer

### Given (前置条件)
```gherkin
Given I am logged in as "sales@acme.com" with role "sales"
And my JWT contains tenant_schema "t_acme01"
And a retailer exists with:
  | field | value |
  | id    | "retailer-uuid-001" |
  | name  | "Corner Shop" |

And products exist in inventory:
  | id | name | price | stock_quantity |
  | "prod-001" | "Product A" | 100.00 | 50 |
  | "prod-002" | "Product B" | 200.00 | 30 |
```

### When (触发动作)
```gherkin
When I send POST /api/v1/orders with:
  {
    "retailer_id": "retailer-uuid-001",
    "items": [
      { "product_id": "prod-001", "quantity": 5 },
      { "product_id": "prod-002", "quantity": 3 }
    ],
    "notes": "Urgent delivery requested"
  }
```


### Then (预期结果)
```gherkin
Then the response status code is 201
And the response body contains:
  {
    "id": "<UUID>",
    "retailer_id": "retailer-uuid-001",
    "status": "pending",
    "total_amount": 1100.00,
    "items": [
      { "product_id": "prod-001", "quantity": 5, "unit_price": 100.00, "subtotal": 500.00 },
      { "product_id": "prod-002", "quantity": 3, "unit_price": 200.00, "subtotal": 600.00 }
    ],
    "notes": "Urgent delivery requested",
    "created_at": "<timestamp>",
    "created_by": "<sales_user_id>"
  }
And a new order record exists in tenant schema
And order_items records are created for each line item
```

---

## Scenario: Create Order Without Permission

### Given
```gherkin
Given I am logged in as "warehouse@acme.com" with role "warehouse"
And the "warehouse" role does NOT have "orders:create" permission
```

### When
```gherkin
When I send POST /api/v1/orders with valid order data
```

### Then
```gherkin
Then the response status code is 403
And the response body contains:
  {
    "detail": "Permission denied"
  }
```

---

## Scenario: Create Order with Invalid Retailer

### Given
```gherkin
Given I am logged in as sales staff
And no retailer exists with id "invalid-retailer-id"
```

### When
```gherkin
When I send POST /api/v1/orders with:
  {
    "retailer_id": "invalid-retailer-id",
    "items": [...]
  }
```

### Then
```gherkin
Then the response status code is 404
And the response body contains:
  {
    "detail": "Retailer not found"
  }
```

---

## Scenario: Create Order with Insufficient Stock

### Given
```gherkin
Given I am logged in as sales staff
And product "prod-001" has stock_quantity = 5
```

### When
```gherkin
When I send POST /api/v1/orders with:
  {
    "retailer_id": "retailer-uuid-001",
    "items": [
      { "product_id": "prod-001", "quantity": 10 }
    ]
  }
```

### Then
```gherkin
Then the response status code is 400
And the response body contains:
  {
    "detail": "Insufficient stock for product: prod-001"
  }
```

---

## Implementation Checklist

### Backend AI
- [ ] Implement `POST /api/v1/orders` endpoint
- [ ] Require `orders:create` permission
- [ ] Validate retailer exists in tenant schema
- [ ] Validate all products exist and have sufficient stock
- [ ] Calculate total_amount from items
- [ ] Create order and order_items in transaction
- [ ] Set created_by from JWT user_id

### Frontend AI
- [ ] Implement order creation form
- [ ] Product search/selection component
- [ ] Quantity input with stock validation
- [ ] Order summary with total calculation
- [ ] Submit and display confirmation

---

## Permission Requirements
| Role | Can Execute | Reason |
|------|-------------|--------|
| admin | ✅ Yes | Has ALL permissions |
| sales | ✅ Yes | Has `orders:create` permission |
| warehouse | ❌ No | Does not have `orders:create` |
| finance | ❌ No | Does not have `orders:create` |

---

## Data Model Dependencies
- `retailers` table (tenant schema)
- `products` table (tenant schema)
- `orders` table (tenant schema) - to be created
- `order_items` table (tenant schema) - to be created

---

**Created by:** Architect AI  
**Date:** 2025-01-09  
**Status:** 📝 Defined