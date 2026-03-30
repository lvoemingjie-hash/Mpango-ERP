# 2026-03-11 — Fix Missing Database Migrations & Frontend Healthcheck

**Version**: v0.2.3-rc1 hotfix  
**Role**: Senior Backend Engineer  
**Trigger**: OPS pre-deployment report `ai-ledger/ops/2026-03-11_v0.2.3-rc1_pre-deployment.md`

---

## Blocking Issues (from OPS report)

| # | Issue | Severity |
|---|-------|----------|
| 1 | `UndefinedTableError: relation "orders" does not exist` — `/api/v1/orders` returns 500 | **P0** |
| 2 | `mpango_frontend` container marked `unhealthy` by Docker | **P1** |

---

## Root Cause Analysis

### Issue 1: Missing tenant tables in `t_dev` schema

The backend uses `MPANGO_ENV=test` + `MockAuthStrategy`, which routes **all** API
requests to tenant schema `t_dev`. However:

- `docker-entrypoint.sh` had automatic Alembic migrations **disabled** (by design).
- `database/init.sql` creates the `t_dev` schema but **no tables**.
- The seed script (`seed_demo_data.py`) bootstraps tables only for the demo
  wholesaler's schema (`t_a000...001`), not for `t_dev`.
- Running `alembic upgrade head -x tenant_schema=t_dev` is a **no-op** because
  Alembic uses a single shared `public.alembic_version` table — it sees version
  `016` already stamped and skips all migrations, even though those migrations
  only ever executed in the public context.

**Result**: `t_dev` schema existed but contained zero tables.

### Issue 2: Frontend healthcheck mismatch

The `docker-compose.yml` healthcheck used `http://localhost:80/`, but Alpine-based
nginx containers resolve `localhost` to IPv6 (`::1`) first. Nginx only listens on
IPv4, causing `wget` to fail with "Connection refused".

The `frontend/Dockerfile` already had the correct healthcheck
(`http://127.0.0.1:80/`), but `docker-compose.yml` overrides the Dockerfile
healthcheck.

---

## Fixes Applied

### Fix 1: `backend/scripts/bootstrap_tenant_schema.py` (NEW)

Standalone async script that creates a tenant schema with all 12 business tables
using raw DDL (`CREATE TABLE IF NOT EXISTS`). Fully idempotent.

Tables created:
- `users`, `roles`, `permissions`, `user_roles`, `role_permissions`
- `skus`, `inventory_stocks`, `inventory_movements`
- `orders`, `order_items`
- `payments`
- `ledger_entries` (with immutability trigger)

Enums created:
- `order_status` (draft → confirmed → partially_paid → paid → fulfilled → cancelled → voided)
- `account_type` (receivable, revenue, cash, liability)

Usage: `python scripts/bootstrap_tenant_schema.py t_dev`

### Fix 2: `backend/docker-entrypoint.sh` (MODIFIED)

Re-enabled automatic migration sequence before Uvicorn startup:

```sh
# 1. Public schema via Alembic (wholesalers, retailers, invitations, etc.)
alembic upgrade head

# 2. Tenant schema via bootstrap script (orders, payments, inventory, etc.)
python scripts/bootstrap_tenant_schema.py "${DEFAULT_TENANT_SCHEMA:-t_dev}"
```

### Fix 3: `docker-compose.yml` (MODIFIED)

```diff
- test: ["CMD", "wget", "-qO-", "http://localhost:80/"]
+ test: ["CMD", "wget", "-qO-", "http://127.0.0.1:80/"]
```

---

## Verification Results

### Container Health

| Service | Status |
|---------|--------|
| mpango_postgres | ✅ healthy |
| mpango_redis | ✅ healthy |
| mpango_backend | ✅ healthy |
| mpango_frontend | ✅ healthy |
| mpango_gateway | ✅ Up |

### Tenant Schema Tables (`t_dev`)

```
inventory_movements, inventory_stocks, ledger_entries,
order_items, orders, payments, permissions, role_permissions,
roles, skus, user_roles, users
```

12 tables — all present.

### API Smoke Tests

| Endpoint | Before | After | Notes |
|----------|--------|-------|-------|
| `GET /health/live` | 200 | 200 | — |
| `GET /api/v1/orders` | **500** | **200** | Orders table now exists |
| `GET /api/v1/retailers` | 403 | 403 | RBAC active, route reachable |
| `GET /api/v1/payments` | 403 | 403 | RBAC active, route reachable |
| `GET /api/v1/inventory/logs` | 403 | 403 | RBAC active, route reachable |
| `GET /` (gateway) | 200 | 200 | Frontend served via nginx |
| `GET /api/v1/orders` (gateway) | 500 | 200 | Proxied through gateway |

---

## Files Changed

| File | Action |
|------|--------|
| `backend/scripts/bootstrap_tenant_schema.py` | **Created** — standalone tenant schema bootstrapper |
| `backend/docker-entrypoint.sh` | **Modified** — runs public migration + tenant bootstrap before Uvicorn |
| `docker-compose.yml` | **Modified** — frontend healthcheck `localhost` → `127.0.0.1` |

---

---

## VPS Deployment (143.110.177.2)

**Date**: 2026-03-11 15:04 (UTC+08:00)  
**Tag**: v0.2.3-r1

### Deployment Steps

1. `scp .env.prod → VPS:/root/mpango-erp/.env`
2. `git pull origin main` (11 commits, v0.2.3-r1)
3. `docker compose -f docker-compose.prod.yml up -d --build`
4. Fixed Alembic version mismatch: `006` → `016` (VPS DB was behind)
5. `seed_demo_data.py --allow-production`

### Verification Results

| Check | Status |
|-------|--------|
| `/health` | ✅ `{"status":"healthy"}` |
| `/` (frontend) | ✅ HTML served |
| Login flow | ✅ 200 |
| Select tenant | ✅ 200 |
| Orders API | ✅ 200 (2 orders) |

### Access

- **URL**: http://143.110.177.2
- **Login**: `admin@mpango.demo` / `DemoAdmin2026!`

---

## Design Notes

- **Why not Alembic for tenant bootstrap?** Alembic's single `alembic_version`
  table in `public` schema cannot distinguish "ran for public" vs "ran for tenant".
  Once public migrations reach HEAD, tenant migrations are a no-op. The seed script
  already solved this with raw DDL — the bootstrap script follows the same pattern.

- **Why a separate script instead of inlining in entrypoint?** The DDL is ~150 lines
  of Python. Keeping it in a standalone script makes it testable, reusable for other
  tenant schemas, and keeps the entrypoint clean.

- **Idempotency**: All DDL uses `CREATE TABLE IF NOT EXISTS` and
  `CREATE TYPE ... EXCEPTION WHEN duplicate_object`. Safe to run on every startup.
