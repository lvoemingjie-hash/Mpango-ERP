# Mpango ERP — Staging Deployment Guide (Track E2)

## Prerequisites

| Tool | Version |
|------|---------|
| Docker | 24+ |
| Docker Compose | v2+ |
| Git | 2.x |

## Quick Start (from zero)

```bash
# 1. Clone and enter repo
git clone <repo-url> && cd mpango-erp

# 2. Create production env file
cp .env.example .env.prod

# 3. Edit .env.prod — set ALL required values:
#    POSTGRES_DB=mpango_erp
#    POSTGRES_USER=mpango
#    POSTGRES_PASSWORD=<strong-password>
#    SECRET_KEY=<generate: python -c "import secrets; print(secrets.token_urlsafe(64))">
#    MPANGO_ENV=staging
#    REPORTING_USER_PASSWORD=<any-password>

# 4. Start the stack
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build

# 5. Wait for healthy status
docker compose -f docker-compose.prod.yml ps

# 6. Run migrations + seed demo data
bash scripts/reset-staging.sh
```

## Environment Variables (Required)

| Variable | Description | Example |
|----------|-------------|---------|
| `POSTGRES_DB` | Database name | `mpango_erp` |
| `POSTGRES_USER` | Database user | `mpango` |
| `POSTGRES_PASSWORD` | Database password | `<strong>` |
| `SECRET_KEY` | JWT signing key (min 32 chars) | `<token_urlsafe(64)>` |
| `MPANGO_ENV` | Must be `staging` or `production` | `staging` |
| `REPORTING_USER_PASSWORD` | PG reporting role password | `<any>` |

## Architecture

```
[Browser] → :80 gateway (nginx)
              └── /api/* → backend:8000 (FastAPI + Uvicorn)
            backend → postgres:5432 + redis:6379
```

## Services

| Service | Container | Port | Health Check |
|---------|-----------|------|-------------|
| PostgreSQL 15 | `mpango_prod_postgres` | 5432 (internal) | `pg_isready` |
| Redis 7 | `mpango_prod_redis` | 6379 (internal) | `redis-cli ping` |
| Backend | `mpango_prod_backend` | 8000 (internal) | `GET /health/live` |
| Gateway | `mpango_prod_gateway` | 80 (exposed) | `wget /health` |

## Reset Staging (for demos)

```bash
# Drops all tenant schemas, re-runs migrations, seeds demo data
bash scripts/reset-staging.sh
```

This creates:
- **1 Wholesaler**: Mpango Demo Wholesaler (DEMO001)
- **1 Retailer**: Nairobi Central Duka
- **1 Admin User**: `admin@mpango.demo` / `DemoAdmin2026!`
- **4 RBAC Roles**: admin, sales, warehouse, finance
- **10 SKUs**: Realistic Kenyan FMCG products
- **5 Orders**: Draft, Confirmed, Paid, Fulfilled, Cancelled
- **Ledger entries**: Auto-created by OrderService transitions

## Seed Script Details

The seed script (`scripts/seed_demo_data.py`) uses **backend Service methods** — not raw SQL — to create demo data. This means:

1. **Tenant guardrails are exercised** during seeding (Track E1 validation)
2. **OrderService.transition()** creates proper state machine transitions
3. **LedgerService** auto-posts double-entry bookkeeping entries
4. **SKUService** creates SKUs with inventory stock rows

## CI/CD Pipeline

The GitHub Actions workflow (`.github/workflows/deploy-staging.yml`) runs on every push to `main`:

1. **Test** — Runs backend test suite against PostgreSQL 15 + Redis 7
   - If tests fail → **deployment is blocked**
2. **Build** — Builds production Docker image, pushes to GHCR
3. **Deploy** — Outputs deployment instructions (manual step)

## Docker Files

| File | Purpose |
|------|---------|
| `backend/Dockerfile` | Production backend image (Python 3.11-slim, non-root) |
| `docker-compose.prod.yml` | Production-like stack (no dev mounts, strict env) |
| `docker-compose.yml` | Development stack (with overrides) |

## Troubleshooting

### "relation does not exist" during seed
Migrations haven't been run. The reset script handles this automatically. If running manually:
```bash
docker compose exec backend python -m alembic upgrade 006_phase_b6_payments_idempotency_key
```

### "password authentication failed"
Check that `POSTGRES_PASSWORD` in your `.env.prod` matches what the PostgreSQL container was initialized with. If you changed the password, you need to remove the volume:
```bash
docker compose -f docker-compose.prod.yml down -v
docker compose -f docker-compose.prod.yml up -d --build
```

### bcrypt/passlib version error
The seed script uses `bcrypt` directly (not `passlib`) to avoid version incompatibility. This is by design.

## Multi-Tenant Migration Strategy

Alembic migrations are split into two phases:
1. **Public schema** (001-006): `alembic upgrade 006_...` — creates `wholesalers`, `retailers`, etc.
2. **Tenant schema**: Created by the seed script's DDL bootstrap — creates `users`, `orders`, `skus`, `ledger_entries`, etc.

Migration 007+ targets tenant-scoped tables and requires `-x tenant_schema=<schema>`. The seed script bypasses this by bootstrapping tables directly via DDL.
