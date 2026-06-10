# R-6C Retry Tencent Predeploy Gate

**Date:** 2026-06-10
**Operator:** opencode
**Final Verdict:** READY_FOR_TENCENT_DEPLOY_APPLY

---

## Step 1 — Clean Sync

| Check | Result |
|-------|--------|
| `git fetch origin --prune` | PASS |
| `git checkout --detach origin/product-dev-recovered` | PASS |
| `git rev-parse HEAD` | `b8a31f875241e7ebcfc3cd11be05e993f5050259` ✅ |
| `git merge-base --is-ancestor a9bd6ac HEAD` | PASS (exit 0) ✅ |
| `git merge-base --is-ancestor 03054ab HEAD` | PASS (exit 0) ✅ |
| `git status --short` | Empty ✅ |

**Required commits confirmed:**
- `b8a31f8` — Merge commit (backend build reproducibility fix)
- `a9bd6ac` — Backend build fix (ancestor)
- `03054ab` — Frontend pnpm fix (ancestor)

---

## Step 2 — Local/Staging Build Gate

### Backend build
```bash
docker compose -f docker-compose.prod.yml --project-name mpango_staging_rehearsal \
  --env-file .env.staging.local build backend
```
**Result: PASS** — `mpango_staging_rehearsal-backend Built`

### Full stack build
```bash
docker compose -f docker-compose.prod.yml --project-name mpango_staging_rehearsal \
  --env-file .env.staging.local build
```
**Result: PASS** — Both `mpango_staging_rehearsal-backend` and `mpango_staging_rehearsal-frontend` built successfully.

---

## Step 3 — Local/Staging Smoke Test

### Containers started
All 5 services (postgres, redis, backend, frontend, gateway) started and reached healthy state.

### Verification results

| Endpoint | Method | Result | Status |
|----------|--------|--------|--------|
| Backend `/health/live` | `docker exec` | `{"status":"healthy","service":"mpango-erp-backend","version":"0.2.0"}` | ✅ |
| Backend `/health/ready` | `docker exec` | Healthy (db check: 34.93ms, redis: 2.81ms) | ✅ |
| Frontend via gateway `/` | HTTP GET | HTTP 200 | ✅ |
| Gateway `/health` | HTTP GET | `{"status":"healthy"}` | ✅ |
| Backend `/openapi.json` | `docker exec` | OpenAPI 3.1.0 spec loads | ✅ |
| Alembic current | `docker exec` | `021_tenant_payments_retailer_id_transaction_id (head)` | ✅ |
| `docker compose ps` | — | All 5 services healthy | ✅ |

### Containers stopped (no prune, no volume delete)
```bash
docker compose -f docker-compose.prod.yml --project-name mpango_staging_rehearsal stop
```
**Result: PASS** — Containers stopped, volumes preserved.

---

## Step 4 — Tencent VPS Read-Only Inventory

**Host:** `1.14.247.12`
**User:** `ubuntu`
**Hostname:** `VM-0-3-ubuntu`

| Check | Value |
|-------|-------|
| **OS** | Ubuntu 24.04.4 LTS (Noble Numbat) |
| **Kernel** | 6.8.0-117-generic |
| **Date** | 2026-06-10 07:45 UTC |
| **CPU** | 4 vCPU (Intel Xeon Platinum 8255C @ 2.50GHz) |
| **RAM** | 3.6 GB total, 556 MB used |
| **Disk** | 40 GB /dev/vda2, 5.3 GB used (15%) |
| **Docker** | ❌ Not installed |
| **Docker Compose** | ❌ Not installed |
| **Containers** | None |
| **Images** | None |
| **Volumes** | None |
| **Networks** | None |
| **Listening ports** | 22 (SSH), 53 (DNS) |
| **Ports 80/443** | ❌ No listeners |
| **Git repo** | ❌ Not found anywhere on system |
| **`.env` / `.env.prod`** | ❌ Not found |
| **`/opt/`** | Empty |

**Notes:**
- This is a fresh VPS with no prior Mpango installation
- Docker and Docker Compose must be installed before deployment
- Repo must be cloned and configured

---

## Final Verdict

**READY_FOR_TENCENT_DEPLOY_APPLY**

All gates passed:
1. ✅ Clean sync — correct commits, clean working tree
2. ✅ Build gate — backend and frontend images built successfully
3. ✅ Smoke test — all endpoints healthy, migrations at head
4. ✅ VPS inventory — clean, fresh server ready for deployment setup
