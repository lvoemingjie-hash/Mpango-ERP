# RBAC Matrix (MVP)

## Status

`CURRENT_CONTRACT_ENTRY`, reconciled on 2026-09-02 against product baseline
`24a28d76d6d9483d8101f8e0f537c148dc262859`.

The executable permission sets live in `backend/core/permission_registry.py`.
Route enforcement lives in `backend/api/middleware/rbac.py` plus each route's
`RequirePermission(...)` declaration. Bootstrap consumers must import the
registry rather than maintain independent lists. A mismatch among this contract,
the registry, route guards or bootstrap parity tests is a STOP-level contract
drift finding; no one surface silently overrides the others.

The versioned [RBAC matrix v0.2.0](../RBAC_MATRIX_v0.2.0.md) is retained as a
historical implementation snapshot and is superseded by this entry.

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
- `payments:confirm_declaration`
- `finance:read`

Current payment write routes use `payments:create`; payment read routes use `payments:read`. Finance invoice/receivable views also use existing order/payment permissions where the route is an order/payment projection.

### Retailers, Invitations, And Pricing

- `retailers:read`
- `retailers:deactivate`
- `retailers:reissue_credential`
- `invitations:create`
- `invitations:revoke`
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

### Retailer Operator

These permissions are isolated from the wholesaler admin set and are granted to
the seeded `retailer_operator` role:

- `client:catalog:read`
- `client:orders:read`
- `client:orders:create`
- `client:payments:read`
- `client:payments:declare`
- `client:finance:read`

## Role Mapping

### Seeded MVP Role

- `admin`: all non-`client:*` permissions listed above.
- `retailer_operator`: only the six `client:*` permissions listed above.

### Not Fully Seeded For MVP

The following role mappings are examples only until tenant bootstrap/owner credential creation seeds them and tests prove the mapping:

- `sales`: typical read/write access to SKUs, retailers, orders, and payment capture.
- `warehouse`: typical read/update access to SKUs, inventory, and shipping workflows.
- `finance`: typical read access to orders plus payment and finance permissions.

Do not claim these additional business roles are provisioned in production
unless the tenant seed/bootstrap path assigns their role permissions explicitly.
