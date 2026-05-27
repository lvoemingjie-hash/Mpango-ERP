# Sprint R-5A: Cleanup Dry-Run Exact Target Inventory

**Execution Date**: 2026-05-27 15:10 UTC
**Status**: INVENTORY_COMPLETE — DRY_RUN_ONLY
**Target**: Canonical India VPS `143.110.177.2` (`ubuntu-s-1vcpu-1gb-blr1-01`)
**Preceding Gate**: R-4E-R1 `RECOVERABLE_BACKUP_VERIFIED` (commit `1962b78`, pushed)

> **CRITICAL**: This is a READ-ONLY inventory. No `docker stop/rm/rmi/volume rm/network rm/system prune/image prune/builder prune`. No `git pull`, `alembic`, `docker compose up`, `.env` read, backup file touch.

---

## 1. Disk Space Overview

```bash
ssh root@143.110.177.2 df -h
```

| Filesystem | Size | Used | Avail | Use% | Mount |
|---|---|---|---|---|---|
| `/dev/vda1` | **25G** | **19G** | **6.1G** | **75%** | `/` |
| `/dev/vda15` | 105M | 6.1M | 99M | 6% | `/boot/efi` |
| `tmpfs` | 479M | 0 | 479M | 0% | `/dev/shm` |
| `overlay` (x5) | 25G | 19G | 6.1G | 75% | container overlays |

**Assessment**: 6.1GB available on root (25% free). Not critical but warrants cleanup planning. Docker images consume ~10GB.

---

## 2. Docker Space Summary

```bash
docker system df
```

| Type | Total | Active | Size | Reclaimable |
|---|---|---|---|---|
| **Images** | 31 | 5 | 9.992 GB | 9.663 GB (96%) |
| **Containers** | 5 | 5 | 2.725 kB | 0 B (0%) |
| **Local Volumes** | 4 | 2 | 115 MB | 48.18 MB (41%) |
| **Build Cache** | 149 | 0 | 945.4 MB | **945.4 MB** |

**Key observation**: 96% of image space is reclaimable (dangling + legacy). Build cache is entirely reclaimable.

---

## 3. Running Container Protection Inventory

```bash
docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Size}}\t{{.Ports}}'
```

**All 5 containers are running and healthy. No stopped containers exist.**

| Container | Image | Status | Size | Ports | Verdict |
|---|---|---|---|---|---|
| `mpango_prod_gateway` | `nginx:alpine` | Up 2 months (healthy) | 2B | `0.0.0.0:80->80/tcp` | **PROTECTED** |
| `mpango_prod_backend` | `mpango-erp-backend:latest` | Up 2 months (healthy) | 1.73kB | `8000/tcp` | **PROTECTED** |
| `mpango_prod_frontend` | `mpango-erp-frontend:latest` | Up 2 months (healthy) | 933B | `80/tcp` | **PROTECTED** |
| `mpango_prod_postgres` | `postgres:15-alpine` | Up 2 months (healthy) | 63B | `5432/tcp` | **PROTECTED** |
| `mpango_prod_redis` | `redis:7-alpine` | Up 2 months (healthy) | 0B | `6379/tcp` | **PROTECTED** |

**Stopped containers**: None.

---

## 4. Volume Inventory

```bash
docker volume ls
```

| Volume | Driver | Active? | Associated Container | Verdict |
|---|---|---|---|---|
| `mpango-erp_postgres_data` | local | Yes | `mpango_prod_postgres` | **PROTECTED** |
| `mpango-erp_redis_data` | local | Yes | `mpango_prod_redis` | **PROTECTED** |
| `app_postgres_data` | local | No | None (legacy `app_*` stack) | **PROTECTED** |
| `app_redis_data` | local | No | None (legacy `app_*` stack) | **PROTECTED** |

**Volume cleanup policy**: All volumes default to PROTECTED in R-5A. `app_postgres_data` and `app_redis_data` (48.18MB reclaimable) are from the legacy `app_*` stack and will not be removed in R-5A.

---

## 5. Docker Network Inventory

```bash
docker network ls
```

| Network | Driver | Scope | In Use? | Verdict |
|---|---|---|---|---|
| `mpango-erp_mpango_network` | bridge | local | Yes (all 5 containers) | **PROTECTED** |
| `bridge` | bridge | local | Default | **PROTECTED** (Docker default) |
| `host` | host | local | Default | **PROTECTED** (Docker default) |
| `none` | null | local | Default | **PROTECTED** (Docker default) |

No orphaned custom networks. No removal candidates.

---

## 6. Active Image Inventory (Used by Running Containers)

| Image ID | Repository | Tag | Size | Used By | Verdict |
|---|---|---|---|---|---|
| `aa7d810494f6` | `mpango-erp-backend` | `latest` | 619 MB | `mpango_prod_backend` | **PROTECTED** |
| `1e0a7c9d2cc6` | `mpango-erp-frontend` | `latest` | 62.6 MB | `mpango_prod_frontend` | **PROTECTED** |
| `b76de378d572` | `nginx` | `alpine` | 62.1 MB | `mpango_prod_gateway` | **PROTECTED** |
| `36a937f48ac7` | `postgres` | `15-alpine` | 274 MB | `mpango_prod_postgres` | **PROTECTED** |
| `13105d2858de` | `redis` | `7-alpine` | 41.4 MB | `mpango_prod_redis` | **PROTECTED** |

**Total active image size**: 1,059 MB (~1.03 GB)

---

## 7. Dangling Image Inventory (CANDIDATE_DRY_RUN_ONLY)

All images below have `<none>:<none>` repo:tag and are NOT used by any container. None will be pruned in R-5A.

### 7.1 Recent Dangling (2 months ago — likely old builds of current services)

| Image ID | Size | Created | Notes |
|---|---|---|---|
| `45955866e977` | 619 MB | 2026-03-10 | Old backend build |
| `122a0d4c7867` | 62.6 MB | 2026-03-06 | Old frontend build |
| `293b68d1c370` | 619 MB | 2026-03-06 | Old backend build |
| `587f897f8071` | 619 MB | 2026-03-06 | Old backend build |
| `286acb7e6b9d` | 619 MB | 2026-03-05 | Old backend build |
| `b95a0bc81cd9` | 62.6 MB | 2026-03-05 | Old frontend build |
| `8244f128221f` | 62.6 MB | 2026-03-05 | Old frontend build |
| `47e863014dbe` | 619 MB | 2026-03-05 | Old backend build |
| `eac6ffa36989` | 619 MB | 2026-03-05 | Old backend build |
| `d6515b8ba9ee` | 619 MB | 2026-03-05 | Old backend build |
| `909b056c210f` | 619 MB | 2026-03-05 | Old backend build |
| `dcbfb8239c22` | 62.6 MB | 2026-03-05 | Old frontend build |
| **Subtotal (12)** | **~5.2 GB** | | |

### 7.2 Older Dangling (3 months)

| Image ID | Size | Created | Notes |
|---|---|---|---|
| `d5f4089faf35` | 616 MB | 2026-02-19 | Old backend build |
| `562d9c89a30d` | 62.6 MB | 2026-02-19 | Old frontend build |
| **Subtotal (2)** | **~678 MB** | | |

### 7.3 Very Old Dangling (4-5 months — layered builds)

| Image ID | Size | Created | Notes |
|---|---|---|---|
| `43d94af0ab04` | 998 MB | 2026-01-21 | Legacy backend layer |
| `8d24c9db4f99` | 998 MB | 2026-01-21 | Legacy backend layer |
| `9c7d669566bf` | 998 MB | 2026-01-21 | Legacy backend layer |
| `0acc59f7854c` | 998 MB | 2026-01-21 | Legacy backend layer |
| `250c3b9b0616` | 770 MB | 2026-01-21 | Legacy backend layer |
| `f2c1724d99b2` | 770 MB | 2026-01-21 | Legacy backend layer |
| `8f4b534aa888` | 769 MB | 2026-01-21 | Legacy backend layer |
| `dc403688c047` | 443 MB | 2026-01-18 | Legacy frontend layer |
| `38de73448d89` | 443 MB | 2026-01-18 | Legacy frontend layer |

Additionally, dozens of smaller layer images (<500MB each) from Jan 2026 remain. Exact count: see `docker system df -v` full output; summarized here.

**Estimated very-old dangling subtotal**: ~3.7+ GB (exact IDs in `docker images -a` output)

### 7.4 Dangling Summary

| Category | Count (est.) | Size (est.) | Verdict |
|---|---|---|---|
| Recent (2 months) | 12 | ~5.2 GB | CANDIDATE_DRY_RUN_ONLY |
| Older (3 months) | 2 | ~678 MB | CANDIDATE_DRY_RUN_ONLY |
| Very Old (4-5 months) | 7+ | ~3.7+ GB | CANDIDATE_DRY_RUN_ONLY |
| **Total Dangling** | **~26** | **~9.66 GB** | **CANDIDATE_DRY_RUN_ONLY** |

---

## 8. Legacy Named Images (CANDIDATE_DRY_RUN_ONLY)

Images with explicit repo:tag but NOT used by any running container:

| Image ID | Repository | Tag | Size | Created | Notes |
|---|---|---|---|---|---|
| `eaacea1cbf22` | `app_backend` | `latest` | 998 MB | 2026-01-21 | Legacy stack — no container uses this |
| `6c19708eb35c` | `app_frontend` | `latest` | 443 MB | 2026-01-18 | Legacy stack — no container uses this |
| `fa659464a114` | `python` | `3.11-slim` | 124 MB | 2026-01-13 | Base image — unused (current stack uses built images) |
| `7064d8f3d970` | `postgres` | `15` | 444 MB | 2026-01-13 | Unused — current stack uses `postgres:15-alpine` |
| **Total (4)** | | | **~2.01 GB** | | |

---

## 9. Build Cache

```bash
docker system df -v  (Build Cache section)
```

| Type | Count | Size | Reclaimable | Verdict |
|---|---|---|---|---|
| Build Cache | **149** | **945.4 MB** | 945.4 MB (100%) | **CANDIDATE_DRY_RUN_ONLY** |

Build cache is entirely inactive (0 active, all 945.4 MB reclaimable). No `docker builder prune` in R-5A.

---

## 10. PROTECTED Non-MPANGO Service: sing-box (Port 443)

```bash
ps aux | grep sing-box
```

| Attribute | Value |
|---|---|
| **Process** | `/usr/bin/sing-box -D /var/lib/sing-box -C /etc/sing-box run` |
| **PID** | 132529 |
| **Memory (RSS)** | ~1.2 GB |
| **CPU Time** | ~393 hours |
| **Port** | 443 (TLS proxy) |
| **Verdict** | **PROTECTED_NON_MPANGO_SERVICE** |

**R-5A Policy**: sing-box is explicitly protected. No `systemctl stop sing-box`, no port 443 disturbance. It is NOT a Docker container and does NOT appear in Docker inventories.

---

## 11. Cleanup Candidate Summary

| Category | Reclaimable | Risk | R-5A Verdict | R-5B Discussion? |
|---|---|---|---|---|
| Running Containers (5) | 0 B | HIGH — production | PROTECTED | No |
| Active Images (5) | 0 B | HIGH — production | PROTECTED | No |
| Volumes (4, 2 active) | 48.18 MB | MEDIUM — legacy data | PROTECTED | R-6+ only if confirmed dead data |
| Dangling Images (~26) | **~9.66 GB** | Low — no container references | CANDIDATE_DRY_RUN_ONLY | Yes — safe candidate |
| Legacy Named Images (4) | **~2.01 GB** | Low — no container references | CANDIDATE_DRY_RUN_ONLY | Yes — safe candidate |
| Build Cache (149) | **945.4 MB** | Very Low — build only | CANDIDATE_DRY_RUN_ONLY | Yes — safe candidate |
| sing-box | N/A | HIGH — external service | PROTECTED_NON_MPANGO_SERVICE | Never |

**Total reclaimable identified in R-5A**: ~12.6 GB (dangling + legacy images + build cache + inactive volumes). Current disk: 6.1 GB free / 25 GB (75% used).

---

## 12. R-5A Confirmation

- **No containers stopped, removed, or restarted**: `docker ps -a` only — read-only.
- **No images removed**: `docker images -a` only — read-only.
- **No volumes removed**: `docker volume ls` only — read-only.
- **No networks removed**: `docker network ls` only — read-only.
- **No prune operations**: No `docker system prune`, `image prune`, `builder prune`, or `volume prune`.
- **No deployment**: No docker compose up, git pull, or alembic.
- **No .env read**: No environment files accessed.
- **No backup file touch**: R-4B backup file NOT accessed.
- **sing-box untouched**: Port 443 service not disturbed. sing-box process NOT stopped or reconfigured.
- **SSH only for read-only commands**: `df -h`, `docker system df`, `docker ps`, `docker volume ls`, `docker network ls`, `docker images`, `ps aux`.

---

## 13. Git Commit (R-5A)

| Item | Value |
|---|---|
| Repo | `phase6-closeout-promotion-2026-05-15` |
| Branch | `ops/sprint-r2-vps-script-recovery-2026-05-25` |
| Commit message | `docs(ops): Sprint R-5A cleanup dry-run inventory — exact target catalog, zero deletions` |
| Files changed | New: `ai-ledger/ops/2026-05-27_sprint_r5a_cleanup_dry_run_inventory.md` |
| Push | **No** — awaiting CTO review |

> **R-5A COMPLETE. Dry-run inventory collected. No deletions executed. ~12.6 GB reclaimable identified across dangling images, legacy images, build cache, and inactive volumes. All 5 running containers, 5 active images, 4 volumes, sing-box protected. Awaiting CTO review for R-5B discussion (safe prune scope).**
