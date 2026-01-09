# RBAC Matrix (MVP)

## Roles
- admin
- sales
- warehouse
- finance

## Permission naming (MVP frozen)

Permission code format (MVP frozen): `<resource>:<action>` (with colon). Examples: users:read, orders:confirm, purchase_orders:receive

## Permissions

### Users & Access
- users:read
- users:create
- users:update
- users:deactivate
- roles:read
- roles:assign

### Master Data
- products:read
- products:create
- products:update
- products:import
- retailers:read
- retailers:create
- retailers:update
- suppliers:read
- suppliers:create
- suppliers:update

### Inventory
- inventory:read
- inventory:adjust
- inventory_logs:read

### Procurement
- purchase_orders:read
- purchase_orders:create
- purchase_orders:update
- purchase_orders:submit
- purchase_orders:receive

### Sales
- orders:read
- orders:create
- orders:update
- orders:confirm
- orders:ship
- orders:cancel

### Finance
- payments:read
- payments:create
- payments:confirm
- payments:refund

## Role mapping
- **admin**: ALL permissions
- **sales**:
  - products:read
  - retailers:read, retailers:create, retailers:update
  - orders:read, orders:create, orders:update, orders:confirm, orders:cancel
  - payments:create (可选：若销售端允许录入收款)
- **warehouse**:
  - products:read
  - inventory:read, inventory:adjust, inventory_logs:read
  - purchase_orders:read, purchase_orders:receive
  - orders:read, orders:ship
- **finance**:
  - orders:read
  - payments:read, payments:create, payments:confirm, payments:refund