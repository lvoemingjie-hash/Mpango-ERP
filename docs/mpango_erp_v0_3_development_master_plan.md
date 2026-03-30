
# Mpango ERP v0.3 Development Master Plan
Author: CTO Office
Purpose: Provide a unified development blueprint for the next stage of Mpango ERP using a dual‑track development model.

---

# 1. Strategic Objective

Mpango ERP v0.3 focuses on transforming the current MVP prototype into a stable, usable B2B ERP system for wholesalers and retailers while simultaneously building the foundation of the Mpango SaaS platform.

Core business loop:
Supplier → Wholesaler → Retailer → Order → Inventory → Payment → Reporting

The v0.3 milestone ensures:
- A wholesaler can operate daily business
- Retailers can place orders smoothly
- Data isolation between tenants is guaranteed
- The platform foundation is ready for multi‑tenant SaaS expansion

---

# 2. Dual‑Track Development Structure

Two parallel development tracks will operate simultaneously.

Track A – Product Line (User Side)
Focus: Wholesaler ERP + Retailer Portal

Track B – Platform Line
Focus: Mpango SaaS Platform Management Layer

Product Layer handles tenant business operations.
Platform Layer handles tenant lifecycle, billing, monitoring, and support tools.

---

# 3. Machine Assignment

Computer A – Product Development
Responsibilities:
- ERP business modules
- Frontend UI
- Retailer ordering portal
- Mobile web experience

Tools:
Codex
Windsurf

Computer B – Platform Development
Responsibilities:
- Tenant registry
- Platform admin console
- Billing system
- Operational monitoring

Tools:
OpenCode

---

# 4. Coordination Rules (Avoiding “Two Separate Systems”)

All code must synchronize through GitHub.

Branch structure:
main – stable releases
product-dev – user side development
platform-dev – platform infrastructure

Merge policy:
Platform features must never break Product APIs.
Product features must always respect tenant isolation.

API Contract Lock:
Before each sprint, the API schema must be frozen.

Database governance:
Shared tables:
tenants
users
audit_logs

All tenant data tables must include tenant_id.

---

# 5. Product Line Development Plan (Computer A)

Phase P1 – ERP Completion

CRM Module
GET /retailers
GET /retailers/{id}
PUT /retailers/{id}

Orders
Fix retailer_name display
Improve order filtering

Inventory
POST /inventory/adjust
GET /inventory/logs

Payments
GET /payments
GET /payments/{id}

Phase P2 – Retailer Ordering Portal
Capabilities:
Browse catalog
Place orders
View order history

Technology:
React + PWA

Phase P3 – UX Improvements
Dashboard
Orders tables
Customer list
Inventory overview

---

# 6. Platform Line Development Plan (Computer B)

Phase S1 – Tenant Registry
Table: tenants

Fields:
tenant_id
name
plan
status
created_at

APIs:
GET /platform/tenants
GET /platform/tenants/{id}

Phase S2 – Admin Console
Display:
Tenant count
Active users
Order volume
Error rate

Phase S3 – Support Tools
Assume Role feature for debugging tenants.
All actions logged in audit_logs.

---

# 7. Synchronization Protocol

Weekly coordination between both tracks.

Checklist:
API compatibility
Database schema changes
Migration safety
Tenant isolation validation

Release cycle:
Merge development branches into main every two weeks.

---

# 8. AI Development Team Guidelines

Rules for AI agents:
- Never manipulate database directly without migrations
- All schema changes via Alembic
- Never bypass tenant guardrails
- Avoid hardcoded hosts like 127.0.0.1
- Each PR must include summary and migration notes

---

# 9. High‑Risk Areas

Special attention required for:
Tenant isolation
Database migrations
Authentication flow
Inventory consistency
Payment recording

---

# 10. Release Milestones

v0.2.3
Stabilization release
Core bug fixes
Track H verification

v0.3
Complete ERP operational loop

v0.4
SaaS platform maturity

---

# 11. Final CTO Directive

Project priorities:

1. Make ERP usable for real wholesalers
2. Ensure retailer ordering works smoothly
3. Maintain strict tenant isolation
4. Build SaaS platform gradually without blocking product development

Success metric for v0.3:
A real wholesaler can run daily operations using Mpango ERP.
