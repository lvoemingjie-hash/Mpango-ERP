# Mpango ERP System

**Version:** 0.2.0
**Author:** Jeff Lee + AI Engineering
**Description:** Multi-tenant wholesale-retail ERP system built for the African market. Supports digital operations for Kenyan wholesalers and their retailer networks.

---

## 🚀 Quick Start (Demo Mode)

The fastest way to see the system in action. Resets the database, runs migrations, and seeds demo data.

```bash
# Prerequisites: Docker Compose running (postgres + redis)
docker compose up -d postgres redis

# One-command staging reset (creates demo tenant + seed data)
bash scripts/reset-staging.sh

# Login credentials:
#   Email:    admin@mpango.demo
#   Password: DemoAdmin2026!
```

After reset, the backend is available at `http://localhost:8000` and the frontend at `http://localhost:5173`.

For manual setup, see [Full Setup](#full-setup) below.

---

## ✅ Feature Status (v0.2.0)

| Module | Status | Key Capabilities |
|---|---|---|
| **Authentication** | ✅ Production | JWT + refresh tokens, multi-tenant login, tenant isolation |
| **User & Role Management** | ✅ Production | RBAC with 22+ permissions, role CRUD, user lifecycle |
| **Order Management** | ✅ Production | Full state machine (Draft → Confirmed → Paid → Fulfilled), returns |
| **Inventory** | ✅ Production | SKU catalog, stock levels, `SELECT FOR UPDATE` concurrency |
| **Payments** | ✅ Production | Payment recording, idempotency, ledger integration |
| **Finance** | ✅ Production | Invoice generation (JSON), accounts receivable, financial summary |
| **Dashboard & BI** | ✅ Production | KPI endpoints, chart data, ad-hoc analysis, semantic query layer |
| **Notifications** | ⚡ Stub | Email/SMS logged to file (provider-agnostic interface ready) |
| **Data Export** | ✅ Production | Streaming CSV (orders, inventory) + async job-based exports |
| **Audit Trail** | ✅ Production | Structured logging, operation tracking |
| **Security** | ✅ Hardened | RBAC on all endpoints, tenant isolation, environment guards |
| **M-Pesa Integration** | 🔲 Planned | STK Push webhook + reconciliation (Phase 2) |
| **Multi-Warehouse** | 🔲 Planned | Single warehouse per tenant in MVP (Phase 2) |
| **Offline Mode** | 🔲 Planned | Requires PWA framework (Phase 3) |

> See [`docs/MVP_LIMITATIONS.md`](docs/MVP_LIMITATIONS.md) for detailed limitations and timelines.

---

## 🏗️ Architecture Overview

- **Pattern**: Modular Monolith (FastAPI + React + PostgreSQL)
- **Multi-Tenant**: Schema-per-tenant isolation (JWT-derived `search_path`)
- **Auth**: JWT + RBAC permission checks on every endpoint
- **State Machine**: Accounting-grade order lifecycle with row-level locking

## Tech Stack

### Backend
- **Framework**: FastAPI (Python 3.11+)
- **Database**: PostgreSQL 15+
- **ORM**: SQLAlchemy 2.0 (async)
- **Migrations**: Alembic
- **Job Queue**: In-process async (Redis-backed in production)

### Frontend
- **Framework**: React 18 + Vite + TypeScript
- **Styling**: TailwindCSS
- **State Management**: Zustand
- **Forms**: React Hook Form + Zod

---

## 📦 Full Setup

```bash
# 1. Start infrastructure
docker compose up -d postgres redis

# 2. Backend (port 8000)
cd backend
pip install -r requirements.txt
alembic upgrade head
uvicorn main:app --reload

# 3. Frontend (port 5173)
cd frontend
npm install
npm run dev
```

---

## 📂 Project Structure

```
Mpango/
├── backend/              # FastAPI application
│   ├── api/v1/           # API routes (orders, users, finance, exports, etc.)
│   ├── core/             # Config, security, domain logic
│   ├── models/           # SQLAlchemy models
│   ├── services/         # Business logic (OrderService, NotificationService, etc.)
│   ├── crud/             # Data access layer
│   └── scripts/          # Tenant onboarding, seeders
├── frontend/             # React + Vite application
│   ├── src/pages/        # Page components (Orders, Finance, Dashboard)
│   ├── src/services/     # API client layer
│   └── src/components/   # Shared UI components
├── scripts/              # DevOps scripts (reset-staging.sh)
├── docs/                 # Project documentation
│   ├── RBAC_MATRIX_v0.2.0.md
│   ├── MVP_LIMITATIONS.md
│   └── policies/         # Exception strategy, security policies
└── ai-ledger/            # Architectural decision records
```

---

## 🔒 Security & RBAC

All API endpoints are protected by the `RequirePermission` RBAC middleware. Permissions are:
- **Seeded** during tenant onboarding (22+ permission codes)
- **Assigned** to roles (`admin`, `sales`, `warehouse`, `finance`)
- **Checked** per-request from JWT token claims

> See [`docs/RBAC_MATRIX_v0.2.0.md`](docs/RBAC_MATRIX_v0.2.0.md) for the full permission matrix.

---

## 🏛️ Multi-Tenant Architecture

- **Tenant Identifier**: `tenant_code` (login) + `tenant_schema` (data isolation)
- **Data Isolation**: Each wholesaler gets an independent PostgreSQL schema (`t_{wholesaler_id}`)
- **Permission Control**: JWT claims carry `tenant_schema` + `permissions[]` → enforced at middleware level
- **Cross-Tenant Access**: Structurally impossible (no URL parameter or header overrides schema)

---

## 📜 Development Contracts

Please follow the contracts in `docs/contracts/`:

- **Boot Contract** (`docs/contracts/Boot contract.md`): Production-grade L0.5 constraints
- **API Contract** (`docs/API_CONTRACT_v0.1.7.md`): REST conventions and response formats
- **Exception Strategy** (`docs/policies/exception_strategy.md`): Error codes, timeouts, concurrency

---

## 📋 Changelog

See [`docs/CHANGELOG_v0.1.9.md`](docs/CHANGELOG_v0.1.9.md) for version history.
