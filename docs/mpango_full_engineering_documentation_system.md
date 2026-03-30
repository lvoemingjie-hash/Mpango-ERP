
# Mpango Engineering Documentation System
Author: CTO Office

This document defines the **complete engineering documentation framework** for Mpango ERP and the future Mpango SaaS platform.

Its purpose is to ensure that multi-computer development, AI-assisted development, and parallel engineering tracks remain aligned.

---

# 1. Documentation Architecture

All Mpango documentation should follow this structure:

docs/
 ├─ architecture
 ├─ engineering
 ├─ product
 ├─ platform
 ├─ operations
 └─ security

Each section has a specific responsibility.

---

# 2. Architecture Documents

These documents define the long-term technical architecture.

Required documents:

SaaS Architecture Evolution Plan
System Modules Map
Platform Architecture Specification

Purpose:

Define how Mpango evolves from ERP to SaaS.

Key topics:

• multi‑tenant model
• service architecture
• data model strategy
• infrastructure evolution

---

# 3. Engineering Governance Documents

These documents define how the engineering team works.

Core files:

Engineering Handbook
Branch Strategy
Migration Governance
API Contract Rules

Key rules:

• no direct commit to main
• all database changes via Alembic
• mandatory code review
• backward compatible APIs

---

# 4. Product Specification Documents

These documents define product functionality.

Typical files:

ERP Feature Specification
Retailer Ordering Portal Spec
Inventory Management Spec
Order Processing Spec

Purpose:

Ensure development matches product design.

---

# 5. Platform Layer Documents

Platform layer enables SaaS operations.

Core components:

Tenant Registry
Subscription Management
Billing Engine
Admin Console
Audit Logging

Key database tables:

tenants
subscriptions
invoices
audit_logs

---

# 6. Operations Documents

Operations documentation supports deployment and system maintenance.

Key documents:

Deployment Guide
Release Process
Monitoring Setup
Backup Strategy

Recommended tools:

Docker
CI/CD pipelines
Centralized logging

---

# 7. Security Documentation

Security documentation defines protection policies.

Topics include:

Multi‑tenant isolation
Authentication
Authorization
Audit logging
Data protection

All tables must include:

tenant_id

ORM must automatically enforce tenant filtering.

---

# 8. AI Development Collaboration Protocol

Because Mpango uses AI‑assisted development across multiple computers, a strict protocol is required.

Development tracks:

Track A — Product / User features
Track B — Platform / Infrastructure

Rules:

Track B must not modify business tables owned by Track A.

Database migrations must be merged before release.

Use git branches to isolate work.

---

# 9. Billing System Specification

Mpango initially uses a lightweight billing system.

Core tables:

subscriptions
invoices
payments_platform

Invoice lifecycle:

pending → paid → archived

Billing may initially be manual.

Future integrations may include Stripe or Paddle.

---

# 10. Release Governance

Release flow:

feature branch → develop → main

Before release:

• all migrations merged
• API schema validated
• tenant security verified

CI must run:

alembic upgrade head

---

# 11. Long‑Term Goal

Mpango evolves through stages:

MVP ERP → SaaS Foundation → Scalable SaaS → Enterprise SaaS

Success is measured by:

system reliability
ease of onboarding tenants
low operational complexity
stable architecture evolution

---

End of Document
