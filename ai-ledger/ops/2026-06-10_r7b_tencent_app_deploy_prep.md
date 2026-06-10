# R-7B Tencent App Deploy Prep

**Date:** 2026-06-10
**Operator:** opencode
**Target:** Tencent VPS (1.14.247.12) — VM-0-3-ubuntu
**Final Verdict:** NEEDS_ENV_INPUT

---

## Pre-flight Gates

| Gate | Result |
|------|--------|
| R-7A report committed | `8036bc4` ✅ |
| R-7A report pushed | `docs/ops/r7a-tencent-base-bootstrap-2026-06-10` ✅ |
| R-7A verdict | READY_FOR_R7B_TENCENT_APP_DEPLOY_PREP ✅ |
| VPS Docker 29.5.3 | ✅ |
| VPS Docker Compose 5.1.4 | ✅ |
| Docker functional (nginx:alpine ran) | ✅ |

---

## Step 1 — VPS Snapshot

| Check | Value |
|-------|-------|
| **Hostname** | VM-0-3-ubuntu |
| **Date** | 2026-06-10 08:22 UTC |
| **Kernel** | 6.8.0-117-generic x86_64 |
| **OS** | Ubuntu 24.04.4 LTS |
| **Disk** | 40G, 5.8G used (16%) |
| **Memory** | 3.6GB total, 619MB used |
| **Docker version** | 29.5.3 |
| **Docker Compose** | v5.1.4 |
| **Docker containers** | 0 |
| **Docker images** | 0 |
| **Open ports** | 22 (SSH), 53 (DNS) |

---

## Step 2 — Repo Checkout

| Check | Result |
|-------|--------|
| Repo cloned to `/opt/mpango-erp` | ✅ |
| Checkout target | `b8a31f8` (detached) |
| `git rev-parse HEAD` | `b8a31f875241e7ebcfc3cd11be05e993f5050259` ✅ |
| `git status --short` | Empty ✅ |
| `git log --oneline -3` | `b8a31f8`, `a9bd6ac`, `d2887b2` ✅ |

---

## Step 3 — Required File Validation

| File | Status |
|------|--------|
| `docker-compose.prod.yml` | ✅ |
| `backend/Dockerfile` | ✅ |
| `frontend/Dockerfile` | ✅ |
| `nginx/gateway.conf` | ✅ |
| `backend/pyproject.toml` | ✅ |
| `backend/poetry.lock` | ✅ |
| `frontend/package.json` | ✅ |
| `frontend/pnpm-lock.yaml` | ✅ |

### Backend Build Fix Validation

| Check | Result |
|-------|--------|
| `pyproject.toml` has `[[tool.poetry.source]]` aliyun | ✅ `https://mirrors.aliyun.com/pypi/simple/` |
| `poetry.lock` package count | 116 (normal) |
| Dockerfile has `POETRY_PYPI_MIRROR_URL` | ❌ 0 occurrences (clean) |
| Dockerfile `poetry install` | ✅ `--no-root --only main --no-ansi` |

---

## Step 4 — Env Readiness Checklist

### Required env vars (MUST be provided by Jeff)

| Key | Category | Source | Provided by |
|-----|----------|--------|-------------|
| `POSTGRES_USER` | Database | `docker-compose.yml` (required) | Jeff |
| `POSTGRES_PASSWORD` | Database | `docker-compose.yml` (required) | Jeff |
| `POSTGRES_DB` | Database | `docker-compose.yml` (required) | Jeff |
| `SECRET_KEY` | Security | `docker-compose.yml` (required) | Jeff — see requirements below |
| `MPANGO_ENV` | Application | `docker-compose.yml` (required) | Jeff — set to `production` |
| `REPORTING_USER_PASSWORD` | Security | `docker-compose.yml` (required) | Jeff |
| `GATEWAY_PORT` | Network | `docker-compose.yml` (default: 80) | Jeff — 80 or custom |
| `CORS_ORIGINS` | Security | `backend/config.py` | Jeff — frontend domain |
| `VITE_API_URL` | Frontend | `frontend/.env` | Jeff — e.g. `https://api.yourdomain.com` |

### Optional vars (sensible defaults exist)

| Key | Default |
|-----|---------|
| `ALGORITHM` | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` |
| `APP_NAME` | `Mpango ERP` |
| `DEBUG` | `false` |
| `LOG_LEVEL` | `INFO` |
| `DEFAULT_TENANT_SCHEMA` | `t_dev` |
| `DB_POOL_SIZE` | `10` |
| `DB_MAX_OVERFLOW` | `20` |
| `DB_CONNECT_TIMEOUT` | `10` |
| `REQUEST_TIMEOUT_SECONDS` | `30` |
| `SLOW_QUERY_THRESHOLD_MS` | `100` |
| `ENABLE_METRICS` | `true` |
| `ENABLE_REQUEST_LOGGING` | `true` |

### SECRET_KEY requirements

- MUST be a strong random value (at least 64 bytes)
- Generate with: `python3 -c "import secrets; print(secrets.token_urlsafe(64))"`
- MUST NOT contain weak words: `weak`, `secret`, `test`, `demo`, `placeholder`
- Staging/dev may use a separate key from production

### `DATABASE_URL` / `REDIS_URL` / domain

These are composed automatically by `docker-compose.yml` from the individual POSTGRES_* vars:
```yaml
DATABASE_URL: postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}
REDIS_URL: redis://redis:6379/0
```

### ⚠️ Prohibitions

- ❌ NEVER commit `.env.prod` or real secrets to git
- ❌ NEVER print secrets in reports or logs
- ❌ NEVER use production secrets in build-only/staging tests

---

## Step 5 — Build Dry-Run

| Step | Result |
|------|--------|
| `docker compose config` (with placeholder env) | ✅ Config valid |
| `docker compose build backend` | ✅ Image `mpango-erp-backend` built |
| `docker compose build frontend` | ✅ Image `mpango-erp-frontend` built |
| `docker compose build gateway` | 🟡 Uses pre-built `nginx:alpine` — no build step |
| Build images cleaned up after test | ✅ |

**Note:** Frontend build initially failed due to Docker Hub inaccessibility from China. Resolved by configuring Tencent Cloud registry mirror (`mirror.ccs.tencentyun.com`).

---

## Compliance Confirmation

| Requirement | Status |
|-------------|--------|
| No app started (`docker compose up`) | ✅ |
| No migration executed (`alembic upgrade`) | ✅ |
| No real `.env.prod` written | ✅ |
| No real secret printed or logged | ✅ |
| No prune/cleanup executed | ✅ |
| No India VPS connection | ✅ |

---

## Final Verdict

**NEEDS_ENV_INPUT**

All deploy-prep steps pass except env provisioning:

1. ✅ Pre-flight gates (R-7A committed, verdict valid, Docker verified)
2. ✅ VPS snapshot
3. ✅ Repo cloned, commit b8a31f8 checked out
4. ✅ Required files validated (8/8 present)
5. ✅ Backend build fix confirmed (aliyun source, clean Dockerfile)
6. ✅ Build dry-run: backend + frontend images built successfully
7. ⏳ **Env file `.env.prod` needed** — 6 required values must be provided by Jeff

Jeff needs to provide a `.env.prod` file with:
- `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB`
- `SECRET_KEY` (strong random, no weak words)
- `MPANGO_ENV=production`
- `REPORTING_USER_PASSWORD`
- `GATEWAY_PORT` and domain/CORS config
- Frontend `VITE_API_URL`

**Next:** R-7C — Env provision & deploy apply (requires Jeff's env input first)
