# DevOps Audit Report — Mpango ERP v0.2.0 Deployment Artifacts

**Date**: 2026-02-15 22:23 (UTC+08:00)  
**Auditor**: DevOps Auditor  
**Scope**: `docker-compose.prod.yml`, `scripts/reset-staging.sh`, `.env.example`

---

## Executive Summary

| Task | Status | Finding |
|------|--------|---------|
| **Task 1: Docker Security** | ⚠️ **WARN** | Minor host mount issues; env vars and health checks pass |
| **Task 2: Script Idempotency** | ✅ **SAFE** | Fully idempotent, graceful error handling |
| **Task 3: Secret Hygiene** | ❌ **FAIL** | `.env.example` template missing; `.env` contains real credentials |

---

## Task 1: Docker Security Check

### File: `docker-compose.prod.yml`

#### Constraint 1: No Source Mounts
**Status**: ⚠️ **WARN**

**Findings**:
- ✅ **No source code mounts** (e.g., `./backend:/app`) — Backend is built from Dockerfile
- ⚠️ **Host mounts present** (acceptable for init/config):
  - `./database/init.sql:/docker-entrypoint-initdb.d/init.sql:ro` — Read-only init script
  - `./nginx/gateway.conf:/etc/nginx/conf.d/default.conf:ro` — Read-only nginx config

**Assessment**: The host mounts are configuration files mounted read-only, not source code. This is acceptable for production but could be further hardened by embedding these configs in images.

#### Constraint 2: Strict Environment Variables
**Status**: ✅ **PASS**

**Findings**:
All critical variables use proper variable substitution with error-on-missing syntax:

```yaml
# PostgreSQL — strict validation
POSTGRES_DB: ${POSTGRES_DB:?POSTGRES_DB must be set}
POSTGRES_USER: ${POSTGRES_USER:?POSTGRES_USER must be set}
POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?POSTGRES_PASSWORD must be set}

# Backend — strict validation
MPANGO_ENV=${MPANGO_ENV:?MPANGO_ENV must be set}
SECRET_KEY=${SECRET_KEY:?SECRET_KEY must be set}
REPORTING_USER_PASSWORD=${REPORTING_USER_PASSWORD:?REPORTING_USER_PASSWORD must be set}
```

**No hardcoded secrets detected.**

#### Constraint 3: Health Checks
**Status**: ✅ **PASS**

**Findings**:
All services have healthcheck blocks defined:

| Service | Health Check | Interval | Timeout | Retries |
|---------|--------------|----------|---------|---------|
| `postgres` | `pg_isready` | 10s | 5s | 5 |
| `redis` | `redis-cli ping` | 10s | 5s | 5 |
| `backend` | `curl /health/live` | 30s | 10s | 5 |
| `gateway` | `wget /health` | 30s | 5s | 3 |

**Dependencies use `condition: service_healthy`** — Proper startup ordering enforced.

---

## Task 2: Script Idempotency

### File: `scripts/reset-staging.sh`

**Status**: ✅ **SAFE**

### Scenario: Running twice in a row
**Result**: ✅ **Idempotent — Safe to re-run**

**Evidence**:

1. **Schema dropping uses `IF EXISTS`**:
   ```bash
   run_psql "DROP SCHEMA IF EXISTS \"$schema\" CASCADE;" >/dev/null 2>&1
   ```

2. **Table dropping uses `IF EXISTS`**:
   ```bash
   run_psql "DROP TABLE IF EXISTS public.wholesaler_retailer_bindings CASCADE;" >/dev/null 2>&1 || true
   ```

3. **Graceful failure handling**: `|| true` on cleanup operations prevents script exit on "already dropped" errors.

4. **Alembic version reset**:
   ```bash
   run_psql "DELETE FROM public.alembic_version;" >/dev/null 2>&1 || true
   ```
   This allows migrations to re-run cleanly even if already applied.

### Risk Assessment
| Risk | Mitigation | Status |
|------|------------|--------|
| Database already dropped | `IF EXISTS` + `|| true` | ✅ Handled |
| Schemas don't exist | `IF EXISTS` clause | ✅ Handled |
| Partial previous run | Full cleanup before re-run | ✅ Handled |
| Running inside/outside container | `--inside-container` flag | ✅ Handled |

---

## Task 3: Secret Hygiene

### Subdirectory `.env.example` Files — CORRECTED FINDING

**Status**: ✅ **PASS**

The `.env.example` files **DO exist** in subdirectories and contain development-safe placeholders:

| File | Content | Assessment |
|------|---------|------------|
| `backend/.env.example` | `DATABASE_URL=postgresql://mpango:mpango123@...`<br>`SECRET_KEY=EXAMPLE_ONLY_REPLACE_WITH_...` | ⚠️ Weak defaults, but **protected by S2-1 validation** |
| `frontend/.env.example` | `VITE_API_URL=http://localhost:8000/api/v1` | ✅ Clean, no secrets |

### Backend Protection Mechanism

The backend `config.py` has fail-fast validation (S2-1 compliance) that rejects these defaults in production:

- **`@/backend/core/config.py:206-212`**: Production crashes if `postgres:postgres@localhost` pattern detected
- **`@/backend/core/config.py:180-193`**: Validator rejects weak SECRET_KEY patterns including "example", "secret", "password"

### Root-Level Gap Identified

**`/.env.example` (root) is still MISSING** — Docker Compose setup at `@/docker-compose.prod.yml:7` references `.env.prod` which has no template. Root-level template should include Docker-specific variables:
- `POSTGRES_PASSWORD`
- `SECRET_KEY`
- `REPORTING_USER_PASSWORD`
- `POSTGRES_DB`, `POSTGRES_USER`

### Original Finding (Retained for Reference)

The `.env` file in repo root contains **real credentials** and should be audited:
```
POSTGRES_PASSWORD=MpangoDBV0.1.4
SECRET_KEY=ax6SvjxO9JzAwg1LQiams0hTlGzdjjEZPRYLNUtLzOB8IcBX1MYRqb29e9eJU0yn9YdR5FdiCET-vCyilqcdoD
VITE_V0_API_KEY=0Ggp09HBtPnbOcQss
```

**Risk**: `.env` (with real secrets) appears to be tracked in version control despite warnings in file header.

---

## Recommendations

### Immediate (Before v0.2.0 Release)
1. **Create `.env.example`** with placeholder values — **CRITICAL**
2. **Review `.env` in version control** — Ensure it's not committed with real secrets

### Nice to Have
3. **Embed init scripts in images** — Remove `./database/init.sql` host mount
4. **Embed nginx config in image** — Remove `./nginx/gateway.conf` host mount

---

## Evidence Files

| File | Status |
|------|--------|
| `docker-compose.prod.yml` | Audited |
| `scripts/reset-staging.sh` | Audited |
| `.env.example` | **MISSING** |
| `.env` | Contains real secrets |
