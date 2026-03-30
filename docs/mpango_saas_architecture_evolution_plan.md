
# Mpango SaaS Architecture Evolution Plan

Author: CTO Office

## 1. Purpose
Define the architectural evolution of Mpango from MVP ERP to scalable SaaS.

Guiding principle:
Build the simplest architecture that supports the current scale while keeping a clear upgrade path.

---

## 2. Evolution Stages
Stage 1 — MVP ERP
Stage 2 — SaaS Foundation
Stage 3 — Scalable SaaS
Stage 4 — Enterprise SaaS

---

## 3. Stage 1 — MVP ERP (v0.2–v0.3)

Scale: 1–10 tenants

Architecture:
Monolithic backend API
Single PostgreSQL database
Multi‑tenant using tenant_id column

Core Components:
Backend API
React frontend
Retailer ordering portal
PostgreSQL

Infrastructure:
Docker
Basic CI/CD

Focus:
Operational stability and usable ERP features.

---

## 4. Stage 2 — SaaS Foundation (v0.3–v0.5)

Scale: 10–100 tenants

New platform components:
Tenant Registry
Platform Admin Console
Audit logging
Lightweight billing

Database additions:
tenants
subscriptions
invoices
audit_logs

Audit logs follow WORM model:
Write once
Read many
No update or delete

Goal:
Operate Mpango as a managed SaaS platform.
