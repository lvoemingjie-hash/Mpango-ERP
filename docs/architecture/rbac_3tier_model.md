# Mpango ERP RBAC Model

## Tier 1 Platform Roles

superadmin
support_ops
billing_admin

Capabilities:
- tenant registry
- platform metrics
- billing

---

## Tier 2 Tenant Roles

wholesaler_admin
sales_manager
warehouse_staff
finance

Capabilities:
- orders
- pricing
- inventory
- financial reporting

Security:
All queries filtered by tenant_id.

---

## Tier 3 Retailer Roles

retailer_admin
retailer_buyer

Capabilities:
- view catalog
- place orders
- view order history

Restrictions:
Retailers cannot see internal inventory or other retailers.