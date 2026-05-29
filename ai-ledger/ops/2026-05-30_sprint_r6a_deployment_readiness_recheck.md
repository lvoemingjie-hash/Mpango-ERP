# Sprint R-6A: India VPS Deployment Readiness Recheck -- Read-Only Investigation

**Execution Date**: 2026-05-30 06:35 UTC
**Status**: INVESTIGATION_COMPLETE
**Target**: Canonical India VPS `143.110.177.2` (`ubuntu-s-1vcpu-1gb-blr1-01`)
**Preceding Gate**: R-5 cleanup CLOSED (`a63c91e`, pushed to origin)
**Scope**: READ-ONLY ONLY. No deployment, no cleanup, no `git pull`, no `docker compose up`, no `alembic`, no `.env` content read.

> **Purpose**: Verify VPS deployment readiness after R-5 cleanup. Confirm system health, git state, compose configuration, backup integrity, and identify the deployment delta between VPS current commit and candidate deployment branch.

---

## 1. Commands NOT Executed (Forbidden)

- `git pull` -- NOT executed
- `docker compose up` / `docker compose down` -- NOT executed
- `alembic upgrade` -- NOT executed
- `.env` / `.env.prod` content read -- NOT executed (existence checked only)
- `docker stop` / `docker rm` -- NOT executed
- `docker image prune` / `docker builder prune` -- NOT executed
- `docker volume rm` -- NOT executed
- Any file modification on VPS -- NOT executed

---

## 2. VPS System State

### 2.1 Host Identity and Uptime

```
Hostname: ubuntu-s-1vcpu-1gb-blr1-01
Uptime: 162 days, 14:22
Load: 0.40, 0.21, 0.11
```

**Result**: Matches canonical VPS. Healthy load. PASS.

### 2.2 Container Health

```
NAMES                  STATUS                  IMAGE
mpango_prod_gateway    Up 2 months (healthy)   nginx:alpine
mpango_prod_backend    Up 2 months (healthy)   mpango-erp-backend
mpango_prod_frontend   Up 2 months (healthy)   mpango-erp-frontend
mpango_prod_postgres   Up 2 months (healthy)   postgres:15-alpine
mpango_prod_redis      Up 2 months (healthy)   redis:7-alpine
```

**Result**: All 5 containers Up, healthy, 2 months uptime. PASS.

### 2.3 Docker Images

```
REPOSITORY            TAG         IMAGE ID       SIZE
mpango-erp-backend    latest      aa7d810494f6   619MB
mpango-erp-frontend   latest      1e0a7c9d2cc6   62.6MB
nginx                 alpine      b76de378d572   62.1MB
postgres              15-alpine   36a937f48ac7   274MB
redis                 7-alpine    13105d2858de   41.4MB
```

**Result**: Exactly 5 active images. Matches R-5C final state. 0 dangling. PASS.

### 2.4 Protected Services

| Service | Status |
|---|---|
| sing-box (PID 132529) | Running |
| Port 443 | LISTEN |
| Port 80 | HTTP 200 |

**Result**: PASS.

### 2.5 Disk and Docker Space

```
Filesystem      Size  Used Avail Use%  Mounted on
/dev/vda1       25G   12G   13G  46%  /

TYPE            TOTAL     ACTIVE    SIZE      RECLAIMABLE
Images          5         5         997MB     62.12MB (6%)
Containers      5         5         2.725kB   0B (0%)
Local Volumes   4         2         115MB     48.18MB (41%)
Build Cache     103       0         3.486GB   3.486GB
```

**Result**: 13 GB free (46%). Stable since R-5C completion. Build cache 3.486 GB reclaimable (R-6/R-7 candidate, not in current scope). PASS.

---

## 3. Git State on VPS

### 3.1 Repository Location

```
Path: /root/mpango-erp/
Remote: https://github.com/lvoemingjie-hash/Mpango-ERP.git
Branch: main
```

### 3.2 Current Commit on VPS

```
02d69c0 fix: tenant bootstrap + frontend healthcheck + MPANGO_ENV
```

**Created**: 2026-03-11 (backend image built same date)

### 3.3 VPS Git Status

```
git status --short: (empty -- clean working tree)
git stash list: (empty)
```

**Result**: No uncommitted changes, no stashed changes. PASS.

### 3.4 VPS Remote Tracking

```
FETCH_HEAD: 02d69c00e7aeefdc788a0335a09a6f735b85f07b  branch 'main' of ...
Remote branches known: origin/main, origin/backend, origin/frontend
```

**Note**: VPS has NOT fetched recent origin/main updates. Last fetch was at `02d69c0`. Current origin/main is `134ea59` (+3 CI/workflow commits ahead).

---

## 4. Compose Configuration

### 4.1 Active Compose Project

```
NAME: mpango-erp
STATUS: running(5)
CONFIG: /root/mpango-erp/docker-compose.prod.yml
```

**Result**: Production compose file in use. 5 services running. PASS.

### 4.2 Compose Files Present

| File | Size | Date |
|---|---|---|
| `docker-compose.yml` | 6138 B | Mar 11 |
| `docker-compose.prod.yml` | 5014 B | Feb 19 |
| `docker-compose.override.yml` | 367 B | Mar 11 |

### 4.3 Compose Services (from docker-compose.prod.yml)

| Service | Image | Build | Healthcheck |
|---|---|---|---|
| postgres | `postgres:15-alpine` | No (pull) | `pg_isready` |
| redis | `redis:7-alpine` | No (pull) | `redis-cli ping` |
| backend | (built from `./backend`) | Yes | `curl http://localhost:8000/health/live` |
| frontend | (built from `./frontend`) | Yes | `wget http://127.0.0.1:80/` |
| gateway | `nginx:alpine` | No (pull) | `wget http://127.0.0.1:80/health` |

### 4.4 Volumes

| Volume | Status |
|---|---|
| `mpango-erp_postgres_data` | Active (production) |
| `mpango-erp_redis_data` | Active (production) |
| `app_postgres_data` | Legacy (PROTECTED) |
| `app_redis_data` | Legacy (PROTECTED) |

### 4.5 Networks

| Network | Driver |
|---|---|
| `mpango-erp_mpango_network` | bridge |
| `bridge` | bridge |
| `host` | host |
| `none` | null |

---

## 5. Environment Configuration

### 5.1 `.env` / `.env.prod` Existence

| File | Exists | Size | Date | Content Read |
|---|---|---|---|---|
| `/root/mpango-erp/.env` | YES | 2948 B | Mar 11 | NO (existence only) |
| `/root/mpango-erp/.env.prod` | NO | -- | -- | -- |

**Finding**: VPS uses `.env` (not `.env.prod`). The `docker-compose.prod.yml` header comment references `.env.prod` but the actual runtime uses `.env`. This is the file that `docker compose` reads by default.

### 5.2 Required Environment Variables (from docker-compose.prod.yml)

The compose file requires these variables (via `${VAR:?error}` syntax):
- `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`
- `MPANGO_ENV`
- `SECRET_KEY`
- `REPORTING_USER_PASSWORD`

Plus optional vars with defaults:
- `ALGORITHM` (HS256), `ACCESS_TOKEN_EXPIRE_MINUTES` (30), `REFRESH_TOKEN_EXPIRE_DAYS` (7)
- `APP_NAME` (Mpango ERP), `LOG_LEVEL` (INFO)
- `DEFAULT_TENANT_SCHEMA` (t_dev), `GATEWAY_PORT` (80)
- `DB_POOL_SIZE` (10), `DB_MAX_OVERFLOW` (20), `DB_CONNECT_TIMEOUT` (10)
- `REQUEST_TIMEOUT_SECONDS` (30)

**Assessment**: All required vars must be present in `.env` since containers are running healthy. Not reading content per scope.

---

## 6. Backend Entrypoint and Migration Strategy

### 6.1 `docker-entrypoint.sh` (from VPS)

```sh
#!/bin/sh
set -e

TENANT="${DEFAULT_TENANT_SCHEMA:-t_dev}"

echo "[migrate] Running public schema migrations..."
alembic upgrade head
echo "[migrate] Public schema up-to-date."

echo "[bootstrap] Bootstrapping tenant schema '${TENANT}'..."
python scripts/bootstrap_tenant_schema.py "${TENANT}"

echo "Starting Uvicorn..."
exec uvicorn main:app --host 0.0.0.0 --port 8000
```

**Key behavior**: On every container start, the entrypoint:
1. Runs `alembic upgrade head` (public schema migration)
2. Runs `bootstrap_tenant_schema.py` for `DEFAULT_TENANT_SCHEMA`
3. Starts Uvicorn

**Deployment implication**: A `docker compose up --build` will automatically run migrations. No separate migration step required. However, migrations must be backwards-compatible or deployment must use a specific strategy (see R-6B).

### 6.2 Alembic Versions on VPS

```
013_s6_2_materialize_sales.py
014_s7_3_audit_trail.py
015_s7_4_sys_reports.py
016_add_returned_status.py
```

**Note**: The candidate deployment branch may contain additional migration files. This delta must be assessed in R-6B.

---

## 7. Backup Status

### 7.1 R-4B Backup

```
-rw------- 1 root root 10967 May 26 22:38 mpango_erp_20260527_063830.sql.gz
-rw------- 1 root root   121 May 26 22:39 mpango_erp_20260527_063830.sql.gz.sha256
```

**Result**: Backup exists with SHA256 checksum. 10967 bytes. Created May 26. PASS.

### 7.2 Backup Adequacy Assessment

- Backup is from May 26 (4 days old)
- Size is very small (10.7 KB) -- likely schema-only or minimal data
- **RECOMMENDATION**: Before any deployment (R-6C), take a fresh backup

---

## 8. Scheduling and Automation

| Item | Status |
|---|---|
| Crontab (root) | EMPTY |
| `/etc/cron.d/` | `e2scrub_all` only (filesystem check) |
| Systemd timers | Standard Ubuntu (dpkg-db-backup, logrotate, apt-daily, man-db) |
| Docker daemon.json | NOT PRESENT (default Docker config) |

**Result**: No custom cron jobs or automated deployment scripts. No Docker GC configured. PASS.

---

## 9. Deployment Delta Analysis

### 9.1 VPS Current State

| Item | Value |
|---|---|
| VPS commit | `02d69c0` (local main) |
| origin/main | `134ea59` (+3 CI commits) |
| Backend image built | 2026-03-11 |
| Last deployment | ~80 days ago (March 11) |

### 9.2 Candidate Deployment Branch

| Branch | Tip | Commits Ahead of main |
|---|---|---|
| `codex/product-night-sprint-n-2026-05-22` | `6da4372` | ~100+ commits |

### 9.3 Key Features in Candidate Branch

Major feature areas in the deployment delta:
- Phase 3: Retailer pricing MVP
- Phase 4: Wholesaler pricing UI, slim-order flow
- Phase 5: Payment flow (draft -> confirm -> pay)
- Phase 6: Credit payment semantics, receivables, collections
- Finance sprint cycles (sprint c through sprint r): Collection notes, credit-safe model, return context, payment history, URL state, accessibility polish
- Platform track: Multi-tenant scaffold, audit logs, operational reporting

### 9.4 Deployment Concern

**The candidate branch has ~100+ commits ahead of main, including multiple database migrations (alembic).** The VPS has not been deployed to since March 11. This is a significant delta.

**Critical items for R-6B dry-run**:
1. How many new alembic migrations exist in the candidate branch?
2. Are all migrations backwards-compatible?
3. What is the rollback strategy if migrations fail?
4. Does the candidate branch require new environment variables not in current `.env`?

---

## 10. Deployment Scripts

**No deployment scripts found** on VPS or in repository. The deployment process is:
1. `git pull` (or `git checkout <branch>`) on VPS
2. `docker compose -f docker-compose.prod.yml up -d --build`

The `docker-entrypoint.sh` handles migrations automatically on container start.

**RECOMMENDATION for R-6B**: A formal `deploy_vps.sh` with `--dry-run` / `--apply` modes should be created to standardize the deployment process with pre-checks, backup, and rollback.

---

## 11. R-6A Readiness Summary

| Check | Status | Notes |
|---|---|---|
| VPS identity | PASS | Canonical India VPS confirmed |
| Container health | PASS | 5/5 healthy, 2 months uptime |
| Docker images | PASS | 5 active, 0 dangling/legacy |
| Protected services | PASS | sing-box/443, port 80 |
| Disk space | PASS | 13 GB free (46%), room for build |
| Git state | PASS | Clean working tree, on main at `02d69c0` |
| Compose config | PASS | `docker-compose.prod.yml`, 5 services |
| `.env` existence | PASS | `.env` exists (2948 B), `.env.prod` does NOT exist |
| Backup | PASS | R-4B backup exists (May 26, 10.7 KB) |
| Cron/automation | PASS | No custom automation |
| Entrypoint/migration | NOTED | `alembic upgrade head` runs on every start |
| Deployment delta | NOTED | ~100+ commits, needs R-6B dry-run |
| Deploy scripts | NOTED | No `deploy_vps.sh` exists |
| Build cache | NOTED | 3.486 GB reclaimable, not in R-6 scope |

---

## 12. R-6A Readiness Classification

**DEPLOYMENT_READINESS: CONDITIONAL**

The VPS infrastructure is healthy and ready for deployment. However:

1. **No deployment script exists** -- deployment will be manual `git pull` + `docker compose up --build`
2. **Deployment delta is large** (~100+ commits, ~80 days since last deploy) -- needs careful dry-run
3. **Migration strategy is auto-run** -- `alembic upgrade head` fires on container start, no manual control
4. **Backup is 4 days old** -- recommend fresh backup before deploy
5. **`.env.prod` does not exist** -- VPS uses `.env`, which differs from compose file documentation
6. **New env vars may be needed** -- candidate branch may require env vars not in current `.env`

**Recommendation**: Proceed to R-6B (Deployment Dry-Run) to assess migration count, env var delta, and create a formal deployment procedure.

---

## 13. Commands Executed (Read-Only Only)

All SSH commands were read-only: `hostname`, `uptime`, `docker ps`, `docker images`, `docker system df`, `df -h`, `ps aux`, `ss -ltnp`, `curl`, `ls`, `cat` (entrypoint.sh), `git log`, `git branch`, `git remote`, `git status`, `git stash list`, `docker inspect`, `docker compose ls`, `docker network ls`, `docker volume ls`, `crontab -l`, `systemctl list-timers`.

**Zero write operations performed.**

---

## 14. Git Commit (R-6A)

| Item | Value |
|---|---|
| Repo | `phase6-closeout-promotion-2026-05-15` |
| Branch | `ops/sprint-r2-vps-script-recovery-2026-05-25` |
| Files changed | New: `ai-ledger/ops/2026-05-30_sprint_r6a_deployment_readiness_recheck.md` |
| Push | **No** -- awaiting CTO review |
