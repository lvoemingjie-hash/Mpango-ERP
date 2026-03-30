# Mpango ERP System Blueprint (High-Level Architecture)

## Purpose
Defines the architectural blueprint for Mpango ERP to ensure the MVP evolves into a scalable SaaS platform without needing foundational rewrites.

## Two System Branches

### Platform Branch (Mpango Internal)
Roles:
- superadmin
- support_ops
- billing_admin

Capabilities:
- Tenant management
- System monitoring
- Billing & subscription management
- Logged Assume‑Role debugging

Security rule:
Platform staff cannot access tenant business data without audited impersonation.

---

### System User Branch (Business Users)

Hierarchy:

Supplier → Wholesaler → Retailer → Consumer

MVP Scope:
Wholesaler → Retailer

---

## Core Architecture Principles

1. Multi‑tenant isolation
2. RBAC authorization
3. Stateless API + JWT
4. Containerized deployment
5. Infrastructure portability
6. Strict frontend/backend contracts

---

## Data Ownership

Platform Layer
- tenants
- subscriptions
- system metrics

Tenant Layer
- inventory
- orders
- finance
- customers

Retailer Layer
- purchase orders
- order history