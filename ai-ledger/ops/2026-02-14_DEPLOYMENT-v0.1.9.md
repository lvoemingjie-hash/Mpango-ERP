# Mpango ERP — Staging Deployment Guide (v0.1.9-contract-polish)

**Date**: 2026-02-14
**Track**: D — Deployment & Orchestration
**Author**: Senior DevOps Engineer (AI)
**Codebase**: Frozen at v0.1.9-contract-polish — NO backend/frontend logic changes

---

## 1. Architecture

```
[Browser] → :80 gateway (nginx reverse proxy)
              ├── /api/*    → backend:8000  (FastAPI + Uvicorn)
              ├── /health*  → backend:8000  (Health probes)
              ├── /healthz  → backend:8000  (K8s liveness)
              ├── /readyz   → backend:8000  (K8s readiness)
              ├── /metrics  → backend:8000  (Prometheus scrape)
              └── /*        → frontend:80   (React SPA via nginx)

backend depends on:
  ├── postgres:5432  (PostgreSQL 15 Alpine)
  └── redis:6379     (Redis 7 Alpine)
```

**Why a gateway?** Single origin eliminates CORS issues. Browser only talks to `:80`.

---

## 2. Pre-requisites

| Tool | Minimum Version |
|------|----------------|
| Docker | 24+ |
| Docker Compose | v2 (bundled with Docker Desktop) |
| Git | any |

---

## 3. File Inventory

| File | Purpose |
|------|---------|
| `backend/Dockerfile` | Python 3.11-slim, Poetry 2.2.1, Aliyun mirrors, non-root user |
| `frontend/Dockerfile` | Multi-stage: Node 18 + pnpm build → nginx:alpine serving SPA |
| `frontend/nginx.conf` | SPA-aware nginx config (`try_files → /index.html`) |
| `nginx/gateway.conf` | Reverse proxy: `/api/` → backend, `/` → frontend |
| `docker-compose.yml` | Full stack: postgres, redis, backend, frontend, gateway |
| `docker-compose.override.yml` | Dev override: exposes individual service ports |
| `backend/docker-entrypoint.sh` | Startup script: logs banner, starts Uvicorn (migrations manual) |
| `database/init.sql` | DB prerequisites: pgcrypto extension, alembic_version(VARCHAR 128), t_dev schema |

---

## 4. How to Configure `.env`

```bash
# Copy the backend example as your base
cp backend/.env.example .env
```

**Required variables** (app crashes without these):

| Variable | Example | Notes |
|----------|---------|-------|
| `POSTGRES_PASSWORD` | `MyStr0ngP@ss!` | Used by postgres container AND backend DATABASE_URL |
| `SECRET_KEY` | `python -c "import secrets; print(secrets.token_urlsafe(32))"` | Min 32 chars, no weak patterns |

**Optional overrides** (have sane defaults):

| Variable | Default | Notes |
|----------|---------|-------|
| `MPANGO_ENV` | `test` | Set `production` for prod enforcement |
| `DATABASE_URL` | `postgresql://mpango:${POSTGRES_PASSWORD}@postgres:5432/mpango_erp` | Auto-composed (no +asyncpg — validator requires plain prefix) |
| `REDIS_URL` | `redis://redis:6379/0` | Internal network |
| `GATEWAY_PORT` | `80` | Host port for the gateway |
| `CORS_ORIGINS` | *(removed from compose)* | Handled by pydantic-settings default; JSON brackets break YAML interpolation |
| `LOG_LEVEL` | `INFO` | DEBUG/INFO/WARNING/ERROR |

Minimal `.env` for staging:

```env
POSTGRES_PASSWORD=ChangeMeToSomethingStrong123!
SECRET_KEY=<output of: python -c "import secrets; print(secrets.token_urlsafe(32))">
```

---

## 5. One-Liner to Start

```bash
# Build and start everything (detached)
docker compose up -d --build
```

Or use the init script:

```bash
chmod +x deploy/init_staging.sh
./deploy/init_staging.sh
```

**Staging-only mode** (skip dev port overrides):

```bash
docker compose -f docker-compose.yml up -d --build
```

---

## 6. How to View Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f gateway

# Last 100 lines of backend
docker compose logs --tail=100 backend
```

---

## 7. Health Checks

```bash
# Via gateway (production path)
curl http://localhost/health/live     # → 200 {"status":"healthy"}
curl http://localhost/healthz         # → 200 (K8s liveness)
curl http://localhost/readyz          # → 200 (K8s readiness — checks DB+Redis)

# Direct backend (only with dev override)
curl http://localhost:8000/health/live
```

---

## 8. Service Dependency Chain

```
postgres  ──healthcheck──→  backend  ──healthcheck──→  gateway
redis     ──healthcheck──→  backend
                            backend  ──started──→  frontend
```

- **postgres**: `pg_isready` every 10s
- **redis**: `redis-cli ping` every 10s
- **backend**: `curl /health/live` every 30s, start_period 40s
- **frontend**: `wget /` every 30s
- **gateway**: starts only after backend is healthy + frontend is started

---

## 9. Stopping / Teardown

```bash
# Stop all containers (keep volumes)
docker compose down

# Stop and destroy volumes (DELETES DATA)
docker compose down -v

# Rebuild a single service
docker compose up -d --build backend
```

---

## 10. Container Details

### Backend Startup Sequence

1. Poetry installs runtime deps (cached in image layer)
2. `docker-entrypoint.sh` starts Uvicorn directly (migrations are **manual** — see below)
3. FastAPI startup: validates config → structured logging → signal handlers → job queue → routers

### ⚠️ Database Migrations (Manual)

The multi-tenant migration architecture requires separate runs for public and tenant schemas:

```bash
# Step 1: Public schema (wholesalers table)
docker compose exec backend alembic upgrade head

# Step 2: Tenant schema (users, roles, orders, etc.)
docker compose exec backend alembic upgrade head -x tenant_schema=t_dev
```

**Why manual?** Migration 001 checks `search_path` to decide public vs tenant tables.
Later migrations (007+) assume tenant tables exist. Running `upgrade head` without
`-x tenant_schema` only creates public tables, causing `UndefinedTableError` on migration 007.

### Frontend Build

1. `pnpm install --frozen-lockfile` (deterministic deps)
2. `pnpm build` with `VITE_API_URL=/api/v1` (relative path — gateway proxies)
3. Static files copied to nginx:alpine → served with SPA `try_files` routing

### Gateway Routing

| Path | Target | Notes |
|------|--------|-------|
| `/api/*` | `backend:8000` | All API requests |
| `/health*` | `backend:8000` | Health probes |
| `/healthz` | `backend:8000` | K8s liveness |
| `/readyz` | `backend:8000` | K8s readiness |
| `/metrics` | `backend:8000` | Prometheus scrape |
| `/*` | `frontend:80` | React SPA (fallback) |

---

## 11. Optional: Prometheus Monitoring

Prometheus is defined but gated behind the `monitoring` profile:

```bash
# Start with monitoring
docker compose --profile monitoring up -d --build

# Access Prometheus UI
open http://localhost:9090
```

---

## 12. Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `POSTGRES_PASSWORD must be set` | Missing `.env` | Create `.env` with `POSTGRES_PASSWORD=...` |
| `SECRET_KEY must be set` | Missing `.env` | Add `SECRET_KEY=...` to `.env` |
| Backend crash loop | Bad SECRET_KEY / DB unreachable | Check `docker compose logs backend` |
| Frontend 502 | Frontend container not ready | Wait for healthcheck, check `docker compose logs frontend` |
| Gateway 502 on `/api/` | Backend not healthy yet | Wait for `start_period` (40s), check backend logs |
| `alembic upgrade head` fails | DB schema issues | Check migration files, ensure postgres is healthy first |
| `UndefinedTableError: users` | Ran public migration only | Must also run with `-x tenant_schema=t_dev` |
| `StringDataRightTruncationError` on alembic_version | Revision ID > 32 chars | `init.sql` pre-creates `alembic_version` with VARCHAR(128) |
| `CORS_ORIGINS` parse error | JSON brackets in `.env` | Remove `CORS_ORIGINS` from `.env`; use pydantic default |
| `DATABASE_URL must start with postgresql://` | Used `+asyncpg` prefix | Use `postgresql://` (no driver suffix) |

---

*Generated by Track D — Deployment & Orchestration*
*Codebase: v0.1.9-contract-polish (frozen)*
