# Track E2: Staging Environment (v0.2.0)

**Date**: 2026-02-15 20:00–20:30 UTC+08:00
**Role**: Senior DevOps Engineer
**Prerequisite**: Track E1 (Backend Guardrail) COMPLETE and PASSING

---

## Objective

Take the hardened backend out of localhost and make it run in a reproducible Staging Environment with demo data, CI/CD pipeline, and production-ready Docker configuration.

## Deliverables

### 1. Seed Script — `scripts/seed_demo_data.py`

**Key design decision**: Uses backend Service methods (not raw SQL) so Track E1 tenant guardrails are exercised during seeding.

| Data | Count | Method |
|------|-------|--------|
| Wholesaler (public) | 1 | Raw SQL with `run_as_system` bypass |
| Retailer (public) | 1 | Raw SQL with `run_as_system` bypass |
| Admin User | 1 | Raw SQL + bcrypt (direct, not passlib) |
| RBAC Roles | 4 | Raw SQL (admin, sales, warehouse, finance) |
| Permissions | 16 | Raw SQL |
| SKUs | 10 | `SKUService.create_sku()` — **guardrail active** |
| Orders | 5 | ORM + `OrderService.transition()` — **guardrail active** |
| Ledger Entries | auto | Created by `LedgerService` during transitions |

Order states seeded: Draft, Confirmed, Paid, Fulfilled, Cancelled.

### 2. Reset Script — `scripts/reset-staging.sh`

Idempotent bash script that:
1. Drops all `t_*` tenant schemas
2. Clears `alembic_version` and public tables
3. Runs Alembic public migrations (001-006)
4. Runs seed script with `--allow-production`
5. Verifies counts

### 3. Docker Production Config — `docker-compose.prod.yml`

- **No development mounts** (no source code volumes)
- **Strict env vars** — all required vars use `${VAR:?must be set}` syntax
- **Health checks** on all services (postgres, redis, backend, gateway)
- **No frontend** (Track E3 scope)
- `restart: always` on all services

### 4. CI/CD Pipeline — `.github/workflows/deploy-staging.yml`

Three-stage pipeline triggered on push to `main`:
1. **Test** — Backend tests against PostgreSQL 15 + Redis 7 services
   - Tests fail → deployment blocked
2. **Build** — Docker image built and pushed to GHCR
3. **Deploy** — Outputs manual deployment instructions (no real cloud target yet)

### 5. Deployment Guide — `README_DEPLOY.md`

Complete guide covering: prerequisites, quick start, env vars, architecture, troubleshooting.

## Infrastructure Changes

### `backend/core/config.py`
- Added `"staging"` to `MPANGO_ENV` Literal type and field validator
- Required for seed script and staging Docker stack

### `backend/alembic.ini`
- Updated DB password from `MpangoDBV0.1.2` to `MpangoDBV0.1.4` (matches Docker)

## Verification

### Seed script execution (against Docker PostgreSQL)
```
=== Mpango ERP Demo Seeder (Track E2) ===

[1/5] System data (public schema)...
  + Wholesaler DEMO001 created
  + Retailer created
[2/5] Tenant schema bootstrap...
  + Tenant schema t_a0000000000040008000000000000001 bootstrapped
[3/5] RBAC (admin + roles + permissions)...
  + RBAC seeded: admin user + 4 roles + 16 perms
[4/5] SKUs (10 products via SKUService)...
  + SKUs: 10 created, 0 already existed
[5/5] Orders (5 orders via OrderService)...
  + Order 1/5: draft
  + Order 2/5: confirmed
  + Order 3/5: paid
  + Order 4/5: fulfilled
  + Order 5/5: cancelled
  + 5 demo orders seeded with ledger entries

=== Seed Complete ===
  Tenant code : DEMO001
  Admin login : admin@mpango.demo / DemoAdmin2026!
```

### E1 regression test (post config.py change)
```
48 passed, 1 warning in 11.30s
```

All Track E1 tests remain green after adding `"staging"` to MPANGO_ENV.

## Files Created/Modified

| File | Action |
|------|--------|
| `scripts/seed_demo_data.py` | Created — demo data seeder |
| `scripts/reset-staging.sh` | Created — full reset script |
| `docker-compose.prod.yml` | Created — production-like stack |
| `.github/workflows/deploy-staging.yml` | Created — CI/CD pipeline |
| `README_DEPLOY.md` | Created — deployment guide |
| `backend/core/config.py` | Modified — added "staging" to MPANGO_ENV |
| `backend/alembic.ini` | Modified — updated DB password |

## Outcome

Track E2 deliverables complete. The staging environment can be launched from zero with:
```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
bash scripts/reset-staging.sh
```
