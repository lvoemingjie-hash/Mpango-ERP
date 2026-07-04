# RBAC Permission Matrix (v0.2.0)

**Last Updated:** 2026-02-18
**Source of Truth:** `backend/scripts/onboard_tenant.py` (lines 167-194)
**Enforcement:** `backend/api/middleware/rbac.py` → `RequirePermission` class

---

## 1. Permission Registry

All permission codes follow the `{resource}:{action}` naming convention.

### Users & Access

| Permission Code | Description | Enforced At | Default Roles |
|---|---|---|---|
| `users:read` | Read user profiles | `GET /api/v1/users` | admin, sales, warehouse, finance |
| `users:create` | Create new users | `POST /api/v1/users` | admin |
| `users:update` | Update user profiles | `PUT /api/v1/users/{id}` | admin |
| `users:deactivate` | Deactivate user accounts | `POST /api/v1/users/{id}/deactivate` | admin |

### Roles & Permissions

| Permission Code | Description | Enforced At | Default Roles |
|---|---|---|---|
| `roles:read` | View roles and their permissions | `GET /api/v1/roles` | admin |
| `roles:create` | Create new roles | `POST /api/v1/roles` | admin |
| `roles:update` | Update role definitions | `PUT /api/v1/roles/{id}` | admin |
| `roles:delete` | Delete roles | `DELETE /api/v1/roles/{id}` | admin |
| `roles:assign` | Assign roles to users | `POST /api/v1/users/{id}/roles` | admin |

### Wholesalers

| Permission Code | Description | Enforced At | Default Roles |
|---|---|---|---|
| `wholesalers:read` | View wholesaler profiles | `GET /api/v1/wholesalers` | admin |
| `wholesalers:write` | Create/update/delete wholesalers | `POST/PUT/DELETE /api/v1/wholesalers` | admin |

### Retailers

| Permission Code | Description | Enforced At | Default Roles |
|---|---|---|---|
| `retailers:read` | View retailer profiles | `GET /api/v1/retailers` | admin, sales |

### Invitations

| Permission Code | Description | Enforced At | Default Roles |
|---|---|---|---|
| `invitations:create` | Send retailer invitations | `POST /api/v1/invitations` | admin, sales |

### Orders (Sales)

| Permission Code | Description | Enforced At | Default Roles |
|---|---|---|---|
| `orders:read` | View orders + invoices | `GET /api/v1/orders`, `GET /api/v1/orders/{id}/invoice` | admin, sales, finance |
| `orders:create` | Create new orders | `POST /api/v1/orders` | admin, sales |
| `orders:update` | Confirm/cancel/return orders | `POST /api/v1/orders/{id}/confirm|cancel|return` | admin, sales |
| `orders:confirm` | Confirm orders specifically | (available for fine-grained RBAC) | admin, sales |
| `orders:ship` | Ship orders (mark as dispatched) | (available for fine-grained RBAC) | admin, warehouse |
| `orders:cancel` | Cancel orders specifically | (available for fine-grained RBAC) | admin, sales |

### SKUs (Products)

| Permission Code | Description | Enforced At | Default Roles |
|---|---|---|---|
| `skus:read` | View SKU catalog | `GET /api/v1/skus` | admin, sales, warehouse |
| `skus:create` | Create new SKUs | `POST /api/v1/skus` | admin |
| `skus:update` | Update SKU details | `PUT /api/v1/skus/{id}` | admin |

### Inventory

| Permission Code | Description | Enforced At | Default Roles |
|---|---|---|---|
| `inventory:read` | View stock levels | `GET /api/v1/inventory` | admin, sales, warehouse |
| `inventory:write` | Update stock (adjust, deduct, restock) | `POST /api/v1/inventory/adjust` | admin, warehouse |

### Payments

| Permission Code | Description | Enforced At | Default Roles |
|---|---|---|---|
| `payments:create` | Record payments through the canonical order payment path | `POST /api/v1/orders/{order_id}/pay` | admin, finance |

Legacy `POST /api/v1/payments` is intentionally disabled with `PAYMENT_WRITE_PATH_DISABLED`; payment writes must go through the order payment route so order status, payment status, and ledger invariants stay synchronized.

### Finance (Phase P-A)

| Permission Code | Description | Enforced At | Default Roles |
|---|---|---|---|
| `finance:read` | View receivables, financial summary | `GET /api/v1/finance/receivables`, `GET /api/v1/finance/summary` | admin, finance |

### Dashboards & Reporting

| Permission Code | Description | Enforced At | Default Roles |
|---|---|---|---|
| `dashboards:read` | View dashboard KPIs and charts | `GET /api/v1/dashboards/*` | admin, sales, finance |

### Data Export (Phase P-A/B)

| Permission Code | Description | Enforced At | Default Roles |
|---|---|---|---|
| `exports:create` | Request data exports (CSV streaming + async jobs) | `POST /api/v1/exports`, `GET /api/v1/orders/export`, `GET /api/v1/inventory/export` | admin |

### System Administration (Phase P-A Security)

| Permission Code | Description | Enforced At | Default Roles |
|---|---|---|---|
| `system:admin` | Full system administration (job queues, debug endpoints) | `POST/GET /api/v1/test/jobs/*` | admin |
| `metrics:admin` | Reset application metrics (destructive) | `DELETE /api/v1/metrics` | admin |

---

## 2. Role Definitions

### admin
**Scope:** Full system access — all permissions listed above.

The admin role receives ALL permissions automatically during tenant onboarding (`onboard_tenant.py` line 229-239).

### sales
**Scope:** Customer-facing order management.

| Permission |
|---|
| `users:read` |
| `retailers:read` |
| `invitations:create` |
| `orders:read`, `orders:create`, `orders:update`, `orders:confirm`, `orders:cancel` |
| `skus:read` |
| `inventory:read` |
| `dashboards:read` |

### warehouse
**Scope:** Inventory and fulfillment.

| Permission |
|---|
| `skus:read` |
| `inventory:read`, `inventory:write` |
| `orders:read`, `orders:ship` |

### finance
**Scope:** Financial operations and reporting.

| Permission |
|---|
| `orders:read` |
| `payments:create` |
| `finance:read` |
| `dashboards:read` |
| `exports:create` |

---

## 3. Enforcement Mechanism

```python
# backend/api/middleware/rbac.py
class RequirePermission:
    def __init__(self, permission_code: str):
        self.permission_code = permission_code

    def __call__(self, token: TokenPayload = Depends(get_current_user_context)):
        if self.permission_code not in token.permissions:
            raise permission_denied()  # HTTP 403
        return token
```

**Usage in endpoints:**
```python
@router.get("/orders")
async def list_orders(
    token: TokenPayload = Depends(RequirePermission("orders:read")),
    db: AsyncSession = Depends(get_tenant_db_session),
):
```

---

## 4. Notes

1. **Tenant isolation** is enforced separately via `get_tenant_db_session` (JWT-derived PostgreSQL `search_path`). RBAC permissions are checked *within* a tenant — there is no cross-tenant access regardless of permissions.

2. **Permission seeding** happens during tenant onboarding (`onboard_tenant.py`) and wholesaler creation (`create_wholesaler.py`). Both scripts maintain identical permission lists.

3. **Fine-grained vs. coarse permissions:** Some permissions (e.g., `orders:confirm`, `orders:ship`, `orders:cancel`) exist as seeds but are not yet enforced at the route level — the current routes use the broader `orders:update`. These can be activated for finer-grained control without schema changes.
