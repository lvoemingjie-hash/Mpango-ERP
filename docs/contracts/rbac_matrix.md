# RBAC Matrix (MVP)

## Status

This document records the current product-side MVP permission vocabulary used by route guards and tenant bootstrap code. It is a contract reference, not a promise that every named business role is fully provisioned.

Current tenant bootstrap paths provision an `admin` role and assign all seeded permissions to that role. Non-admin business role mappings such as sales, warehouse, and finance remain product policy examples until they are explicitly seeded and tested.

## Permission Naming

Permission code format: `<resource>:<action>`.

Examples: `users:read`, `orders:confirm`, `skus:import`, `exports:create`.

## Current MVP Permission Vocabulary

### Users, Roles, And Tenant Admin

- `users:read`
- `users:create`
- `users:update`
- `users:deactivate`
- `wholesalers:read`
- `wholesalers:write`
- `roles:read`
- `roles:create`
- `roles:update`
- `roles:delete`
- `roles:assign`

### Orders

- `orders:read`
- `orders:create`
- `orders:update`
- `orders:confirm`
- `orders:ship`
- `orders:cancel`

### SKUs

- `skus:read`
- `skus:create`
- `skus:update`
- `skus:import`

`products:*` is stale vocabulary and must not be used for current MVP route contracts.

### Data Intake

- `intake:read`
- `intake:create`
- `intake:update`
- `intake:approve`
- `intake:export`
- `intake:import_to_erp`

Current intake route guards use `intake:read`, `intake:create`, `intake:update`, and `skus:import` for ERP import application. The additional intake permissions above are seeded for workflow policy but are not all independently enforced by current MVP routes.

### Inventory

- `inventory:read`
- `inventory:write`
- `inventory:update`

`inventory:write` is a legacy seeded alias. Current inventory adjustment routes use `inventory:update`; read routes use `inventory:read`.

### Payments And Finance

- `payments:read`
- `payments:create`
- `finance:read`

Current payment write routes use `payments:create`; payment read routes use `payments:read`. Finance invoice/receivable views also use existing order/payment permissions where the route is an order/payment projection.

### Retailers, Invitations, And Pricing

- `retailers:read`
- `invitations:create`
- `pricing:read`
- `pricing:write`

### Dashboards, Reports, And Exports

- `dashboards:read`
- `reports:read`
- `reports:analyze`
- `exports:create`

`exports:create` gates export creation, export status polling, and export file download in the MVP. No separate `exports:read` or `exports:download` permission is currently seeded.

### System

- `system:admin`
- `metrics:admin`

These are elevated operational permissions and are not a substitute for platform identity-only operator checks on platform routes.

## Role Mapping

### Seeded MVP Role

- `admin`: all current MVP permissions listed above.

### Not Fully Seeded For MVP

The following role mappings are examples only until tenant bootstrap/owner credential creation seeds them and tests prove the mapping:

- `sales`: typical read/write access to SKUs, retailers, orders, and payment capture.
- `warehouse`: typical read/update access to SKUs, inventory, and shipping workflows.
- `finance`: typical read access to orders plus payment and finance permissions.

Do not claim these non-admin roles are provisioned in production unless the tenant seed/bootstrap path assigns their role permissions explicitly.
