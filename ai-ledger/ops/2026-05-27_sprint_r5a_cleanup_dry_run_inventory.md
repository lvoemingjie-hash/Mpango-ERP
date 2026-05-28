# Sprint R-5A: Cleanup Dry-Run Exact Target Inventory

**Execution Date**: 2026-05-27 15:10 UTC
**Status**: INVENTORY_COMPLETE -- DRY_RUN_ONLY
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

**Assessment**: 6.1GB available on root (25% free). Not critical but warrants cleanup planning. Docker reports 9.663 GB image space + 945.4 MB build cache reclaimable (see `docker system df`).

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

## 7. Dangling Image Inventory (SUPERSEDED -- see Appendix A Section A.4)

> **R-5A-R2 NOTE**: Sections 7 and 8 below were the original R-5A estimates with approximate counts. They have been superseded by the exact per-image catalog in Appendix A. The exact figures are: 100 dangling images (not ~26), 5 legacy named images (not 4). See Appendix A sections A.3 through A.10 for the authoritative catalog with per-image container reference verification.

| Category | Exact Count (from Appendix A) | Verdict |
|---|---|---|
| Dangling images | 100 | CANDIDATE_DRY_RUN_ONLY |
| Legacy named images | 5 | CANDIDATE_DRY_RUN_ONLY |

All 105 candidate images verified: zero container references (NONE). See Appendix A for full ID-level detail.

---

## 8. Legacy Named Images (SUPERSEDED -- see Appendix A Section A.3)

> **R-5A-R2 NOTE**: The original R-5A listed only 4 legacy images at ~2.01 GB. The exact R-5A-R1 catalog found 5 legacy named images (added `node:18-alpine`). Display sizes sum to 998+443+124+444+127 = 2,136 MB, but due to Docker shared layers the unique reclaimable space is reported by `docker system df` as part of the total 9.663 GB reclaimable image space. See Appendix A.3 for the exact per-image table.

| Exact Count | Displayed Size Sum | Docker Unique Reclaimable | Verdict |
|---|---|---|---|
| 5 | 2,136 MB | included in 9.663 GB total | CANDIDATE_DRY_RUN_ONLY |

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

## 11. Cleanup Candidate Summary (exact counts from Appendix A)

| Category | Exact Count | Reclaimable (Docker unique) | Risk | R-5A Verdict | R-5B Discussion? |
|---|---|---|---|---|---|
| Running Containers (5) | 5 | 0 B | HIGH -- production | PROTECTED | No |
| Active Images (5) | 5 | 0 B | HIGH -- production | PROTECTED | No |
| Volumes (4, 2 active) | 4 | 48.18 MB | MEDIUM -- legacy data | PROTECTED | R-6+ only if confirmed dead data |
| Dangling Images | 100 | included in 9.663 GB | Low -- zero container refs verified | CANDIDATE_DRY_RUN_ONLY | Yes -- safe candidate |
| Legacy Named Images | 5 | included in 9.663 GB | Low -- zero container refs verified | CANDIDATE_DRY_RUN_ONLY | Yes -- safe candidate |
| Build Cache (149) | 149 | 945.4 MB | Very Low -- build only | CANDIDATE_DRY_RUN_ONLY | Yes -- safe candidate |
| sing-box | N/A | N/A | HIGH -- external service | PROTECTED_NON_MPANGO_SERVICE | Never |

**Total reclaimable identified**: 9.663 GB (images: 100 dangling + 5 legacy named) + 945.4 MB (build cache) = 10.6 GB per `docker system df`. Current disk: 6.1 GB free / 25 GB (75% used).

---

## 12. R-5A Confirmation

- **No containers stopped, removed, or restarted**: `docker ps -a` only -- read-only.
- **No images removed**: `docker images -a` only -- read-only.
- **No volumes removed**: `docker volume ls` only -- read-only.
- **No networks removed**: `docker network ls` only -- read-only.
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
| Commit message | `docs(ops): Sprint R-5A cleanup dry-run inventory -- exact target catalog, zero deletions` |
| Files changed | New: `ai-ledger/ops/2026-05-27_sprint_r5a_cleanup_dry_run_inventory.md` |
| Push | **No** -- awaiting CTO review |

> **R-5A COMPLETE (initial). See Appendix A (R-5A-R1) for exact candidate catalog with per-image container reference verification.**

---

# Appendix A: R-5A-R1 Exact Candidate Catalog Correction

**Execution Date**: 2026-05-28 09:57 UTC
**Status**: EXACT_INVENTORY_VERIFIED
**Scope**: Read-only. No deletions. Per-image container reference check for every non-active image.
**Correction**: Replaces Section 7 (Dangling) and Section 8 (Legacy) estimates with exact counts.

## A.1 Methodology

1. `docker images -a --format` on canonical VPS `143.110.177.2` to get all 110 images with exact ID/repo/tag/size/created.
2. `docker ps -a --format {{.Image}}` to identify 5 images referenced by containers (running or stopped).
3. For each non-active image: `docker ps -a --filter ancestor=<IMAGE_ID>` to verify zero container references.
4. All 105 non-active images confirmed: **zero container references** (result: NONE for every image).

## A.2 Active Images (PROTECTED -- 5 total, 1,059 MB)

These images are in use by running containers. Must NOT be removed.

| # | Image ID | Repository | Tag | Size | Created | Used By |
|---|---|---|---|---|---|---|
| 1 | `aa7d810494f6` | `mpango-erp-backend` | `latest` | 619MB | 2026-03-11 | `mpango_prod_backend` |
| 2 | `1e0a7c9d2cc6` | `mpango-erp-frontend` | `latest` | 62.6MB | 2026-03-10 | `mpango_prod_frontend` |
| 3 | `b76de378d572` | `nginx` | `alpine` | 62.1MB | 2026-02-05 | `mpango_prod_gateway` |
| 4 | `36a937f48ac7` | `postgres` | `15-alpine` | 274MB | 2025-12-18 | `mpango_prod_postgres` |
| 5 | `13105d2858de` | `redis` | `7-alpine` | 41.4MB | 2025-11-03 | `mpango_prod_redis` |

## A.3 Legacy Named Images (CANDIDATE -- 5 total)

Images with explicit repo:tag, NOT referenced by any container. Verified via `docker ps -a --filter ancestor=<ID>`.

| # | Image ID | Repository | Tag | Size | Created | Container Refs |
|---|---|---|---|---|---|---|
| 1 | `eaacea1cbf22` | `app_backend` | `latest` | 998MB | 2026-01-21 | NONE |
| 2 | `6c19708eb35c` | `app_frontend` | `latest` | 443MB | 2026-01-18 | NONE |
| 3 | `fa659464a114` | `python` | `3.11-slim` | 124MB | 2026-01-13 | NONE |
| 4 | `7064d8f3d970` | `postgres` | `15` | 444MB | 2026-01-13 | NONE |
| 5 | `ee77c6cd7c18` | `node` | `18-alpine` | 127MB | 2025-03-27 | NONE |

**Legacy named subtotal**: 5 images. Displayed size sum: 998+443+124+444+127 = 2,136 MB. Unique reclaimable space is shared with other image layers per `docker system df` (included in the 9.663 GB total image reclaimable).

## A.4 Dangling Images (CANDIDATE -- 100 total)

All have `<none>:<none>` repo:tag. Each verified: `docker ps -a --filter ancestor=<ID>` returns NONE.

### A.4.1 March 2026 (current-gen old builds -- 14 images)

| # | Image ID | Size | Created | Container Refs |
|---|---|---|---|---|
| 1 | `45955866e977` | 619MB | 2026-03-10 | NONE |
| 2 | `122a0d4c7867` | 62.6MB | 2026-03-06 | NONE |
| 3 | `293b68d1c370` | 619MB | 2026-03-06 | NONE |
| 4 | `587f897f8071` | 619MB | 2026-03-06 | NONE |
| 5 | `286acb7e6b9d` | 619MB | 2026-03-05 | NONE |
| 6 | `b95a0bc81cd9` | 62.6MB | 2026-03-05 | NONE |
| 7 | `8244f128221f` | 62.6MB | 2026-03-05 | NONE |
| 8 | `47e863014dbe` | 619MB | 2026-03-05 | NONE |
| 9 | `eac6ffa36989` | 619MB | 2026-03-05 | NONE |
| 10 | `d6515b8ba9ee` | 619MB | 2026-03-05 | NONE |
| 11 | `909b056c210f` | 619MB | 2026-03-05 | NONE |
| 12 | `dcbfb8239c22` | 62.6MB | 2026-03-05 | NONE |
| 13 | `d5f4089faf35` | 616MB | 2026-02-19 | NONE |
| 14 | `562d9c89a30d` | 62.6MB | 2026-02-19 | NONE |
| | **Subtotal** | **6,968 MB** | | |

### A.4.2 January 2026 -- legacy app_backend build layers (21 images)

| # | Image ID | Size | Created | Container Refs |
|---|---|---|---|---|
| 1 | `43d94af0ab04` | 998MB | 2026-01-21 | NONE |
| 2 | `8d24c9db4f99` | 998MB | 2026-01-21 | NONE |
| 3 | `9c7d669566bf` | 998MB | 2026-01-21 | NONE |
| 4 | `0acc59f7854c` | 998MB | 2026-01-21 | NONE |
| 5 | `250c3b9b0616` | 770MB | 2026-01-21 | NONE |
| 6 | `f2c1724d99b2` | 770MB | 2026-01-21 | NONE |
| 7 | `8f4b534aa888` | 769MB | 2026-01-21 | NONE |
| 8 | `260d3c6b1288` | 443MB | 2026-01-18 | NONE |
| 9 | `38de73448d89` | 443MB | 2026-01-18 | NONE |
| 10 | `bfda92ceae58` | 298MB | 2026-01-18 | NONE |
| 11 | `1197fc9cc1e9` | 298MB | 2026-01-18 | NONE |
| 12 | `8bfbb4c27786` | 298MB | 2026-01-18 | NONE |
| 13 | `c94066a36aad` | 298MB | 2026-01-18 | NONE |
| 14 | `5a0eaedc974e` | 127MB | 2026-01-18 | NONE |
| 15 | `813f62cc26d5` | 127MB | 2026-01-18 | NONE |
| 16 | `dd383cb55634` | 124MB | 2026-01-18 | NONE |
| 17 | `54003690b6d9` | 1.08GB | 2026-01-18 | NONE |
| 18 | `c94e54c50c36` | 1.08GB | 2026-01-18 | NONE |
| 19 | `a8a3a618e918` | 1.08GB | 2026-01-18 | NONE |
| 20 | `0fc496c615d6` | 1.08GB | 2026-01-18 | NONE |
| 21 | `c45949708ea4` | 1.08GB | 2026-01-18 | NONE |
| | **Subtotal** | **11,492 MB** | | |

### A.4.3 January 2026 -- legacy app_frontend build layers (10 images)

| # | Image ID | Size | Created | Container Refs |
|---|---|---|---|---|
| 1 | `dc403688c047` | 443MB | 2026-01-18 | NONE |
| 2 | `22b36114bdd0` | 854MB | 2026-01-18 | NONE |
| 3 | `319d261b82f0` | 854MB | 2026-01-18 | NONE |
| 4 | `10c88a9a1674` | 853MB | 2026-01-18 | NONE |
| 5 | `1d0100e1ce48` | 451MB | 2026-01-18 | NONE |
| 6 | `72455b8847bb` | 451MB | 2026-01-18 | NONE |
| 7 | `444bd1fceb9d` | 451MB | 2026-01-18 | NONE |
| 8 | `d1a684dc46e9` | 352MB | 2026-01-18 | NONE |
| 9 | `f45583cac65c` | 443MB | 2026-01-18 | NONE |
| 10 | `743d8bba937a` | 443MB | 2026-01-18 | NONE |
| | **Subtotal** | **5,595 MB** | | |

### A.4.4 January 2026 -- older frontend builds (14 images)

| # | Image ID | Size | Created | Container Refs |
|---|---|---|---|---|
| 1 | `9c1f263f3a16` | 443MB | 2026-01-18 | NONE |
| 2 | `66f141f6bce3` | 443MB | 2026-01-18 | NONE |
| 3 | `6657bf592a72` | 298MB | 2026-01-18 | NONE |
| 4 | `d58a9f76353a` | 298MB | 2026-01-18 | NONE |
| 5 | `bfd1b81c4e5b` | 298MB | 2026-01-18 | NONE |
| 6 | `867c1e81347b` | 298MB | 2026-01-18 | NONE |
| 7 | `0ebfd8458b19` | 127MB | 2026-01-18 | NONE |
| 8 | `bc597e892cb6` | 127MB | 2026-01-18 | NONE |
| 9 | `1ce84a5f05e6` | 1.08GB | 2026-01-18 | NONE |
| 10 | `a248c185462f` | 1.08GB | 2026-01-18 | NONE |
| 11 | `1c6e88ea3ae6` | 1.08GB | 2026-01-18 | NONE |
| 12 | `e4940490c593` | 1.08GB | 2026-01-18 | NONE |
| 13 | `c3f6445fba2c` | 1.08GB | 2026-01-18 | NONE |
| 14 | `3c39f110628a` | 854MB | 2026-01-18 | NONE |
| | **Subtotal** | **8,816 MB** | | |

### A.4.5 January 2026 -- more legacy layers (13 images)

| # | Image ID | Size | Created | Container Refs |
|---|---|---|---|---|
| 1 | `31155d7f306a` | 854MB | 2026-01-18 | NONE |
| 2 | `85069dc8b37c` | 853MB | 2026-01-18 | NONE |
| 3 | `c37593ea4c1d` | 451MB | 2026-01-18 | NONE |
| 4 | `9bd62bb9745c` | 451MB | 2026-01-18 | NONE |
| 5 | `cb649b08bf63` | 451MB | 2026-01-18 | NONE |
| 6 | `91d51f432a95` | 352MB | 2026-01-18 | NONE |
| 7 | `74bcbd45bac7` | 124MB | 2026-01-18 | NONE |
| 8 | `49339eec7bd5` | 443MB | 2026-01-18 | NONE |
| 9 | `29d052d1aab2` | 443MB | 2026-01-18 | NONE |
| 10 | `e923c0c55f1d` | 443MB | 2026-01-18 | NONE |
| 11 | `3be728897d14` | 443MB | 2026-01-18 | NONE |
| 12 | `eccdc128546c` | 298MB | 2026-01-18 | NONE |
| 13 | `77ea8d52aaa4` | 298MB | 2026-01-18 | NONE |
| | **Subtotal** | **5,905 MB** | | |

### A.4.6 January 2026 -- earliest layers (14 images)

| # | Image ID | Size | Created | Container Refs |
|---|---|---|---|---|
| 1 | `1419058f2445` | 298MB | 2026-01-18 | NONE |
| 2 | `307431b5adc5` | 298MB | 2026-01-18 | NONE |
| 3 | `bf4e1e8a4b0b` | 127MB | 2026-01-18 | NONE |
| 4 | `cf5d59a64752` | 127MB | 2026-01-18 | NONE |
| 5 | `089e179ddbe2` | 1.08GB | 2026-01-18 | NONE |
| 6 | `2fda947af8ac` | 1.08GB | 2026-01-18 | NONE |
| 7 | `322bdf3e0aaa` | 1.08GB | 2026-01-18 | NONE |
| 8 | `7ab9ced4e313` | 1.08GB | 2026-01-18 | NONE |
| 9 | `b53064b1f50a` | 1.08GB | 2026-01-18 | NONE |
| 10 | `09fce7640c0f` | 854MB | 2026-01-18 | NONE |
| 11 | `55338c78d6d7` | 854MB | 2026-01-18 | NONE |
| 12 | `abda8436c092` | 853MB | 2026-01-18 | NONE |
| 13 | `d030960f9d2b` | 451MB | 2026-01-18 | NONE |
| 14 | `58f8f1a9a61c` | 451MB | 2026-01-18 | NONE |
| | **Subtotal** | **9,888 MB** | | |

### A.4.7 January 2026 -- final batch (8 images)

| # | Image ID | Size | Created | Container Refs |
|---|---|---|---|---|
| 1 | `984eeb5dc1fe` | 451MB | 2026-01-18 | NONE |
| 2 | `a996f819a23a` | 352MB | 2026-01-18 | NONE |
| 3 | `cdded6143ff1` | 124MB | 2026-01-18 | NONE |
| 4 | `d363a698cfb4` | 458MB | 2026-01-16 | NONE |
| 5 | `022ba8b8c49a` | 458MB | 2026-01-16 | NONE |
| 6 | `93b16d243162` | 458MB | 2026-01-16 | NONE |
| 7 | `7d37d2fd132d` | 458MB | 2026-01-16 | NONE |
| 8 | `246abb951ad1` | 458MB | 2026-01-16 | NONE |
| | **Subtotal** | **3,167 MB** | | |

### A.4.8 January 2026 -- earliest proto-builds (6 images)

| # | Image ID | Size | Created | Container Refs |
|---|---|---|---|---|
| 1 | `a61b4b77381b` | 458MB | 2026-01-16 | NONE |
| 2 | `e0d5332d3748` | 458MB | 2026-01-16 | NONE |
| 3 | `4db9b209f19e` | 457MB | 2026-01-16 | NONE |
| 4 | `3b4f72ce8cab` | 451MB | 2026-01-16 | NONE |
| 5 | `3e3c0181edd7` | 451MB | 2026-01-16 | NONE |
| 6 | `3af6bffe4fb8` | 451MB | 2026-01-16 | NONE |
| | **Subtotal** | **2,726 MB** | | |

### A.4.9 January 2026 -- oldest proto-builds (10 images)

| # | Image ID | Size | Created | Container Refs |
|---|---|---|---|---|
| 1 | `3d2549d64f00` | 352MB | 2026-01-16 | NONE |
| 2 | `7b2cf277a4ee` | 124MB | 2026-01-16 | NONE |
| 3 | `bf2839f295fa` | 443MB | 2026-01-16 | NONE |
| 4 | `b8ecc4501e86` | 443MB | 2026-01-16 | NONE |
| 5 | `6c053077a94a` | 443MB | 2026-01-16 | NONE |
| 6 | `638b97d29a53` | 443MB | 2026-01-16 | NONE |
| 7 | `94ff3f6866c6` | 298MB | 2026-01-16 | NONE |
| 8 | `2cbf448a188f` | 298MB | 2026-01-16 | NONE |
| 9 | `1fe40758005e` | 298MB | 2026-01-16 | NONE |
| 10 | `1dbac28b010e` | 298MB | 2026-01-16 | NONE |
| | **Subtotal** | **3,440 MB** | | |

### A.4.10 January 2026 -- final 2 proto-build layers

| # | Image ID | Size | Created | Container Refs |
|---|---|---|---|---|
| 1 | `52fd62d6da5a` | 127MB | 2026-01-16 | NONE |
| 2 | `4f1c48272ed0` | 127MB | 2026-01-16 | NONE |
| | **Subtotal** | **254 MB** | | |

### A.5 Dangling Image Grand Total

| Group | Count | Size |
|---|---|---|
| A.4.1 March 2026 (current-gen) | 14 | 6,968 MB |
| A.4.2 Jan 2026 (backend layers) | 21 | 11,492 MB |
| A.4.3 Jan 2026 (frontend layers) | 10 | 5,595 MB |
| A.4.4 Jan 2026 (older frontend) | 14 | 8,816 MB |
| A.4.5 Jan 2026 (more legacy) | 13 | 5,905 MB |
| A.4.6 Jan 2026 (earliest) | 14 | 9,888 MB |
| A.4.7 Jan 2026 (final batch) | 8 | 3,167 MB |
| A.4.8 Jan 2026 (proto-builds) | 6 | 2,726 MB |
| A.4.9 Jan 2026 (oldest) | 10 | 3,440 MB |
| A.4.10 Jan 2026 (final 2) | 2 | 254 MB |
| **Grand Total** | **100** | **(docker system df reports total image space 9.992 GB, shared across layers)** |

> Note: Summing individual image sizes exceeds `docker system df` total (9.992 GB) because Docker uses shared layers. The unique reclaimable space reported by Docker is 9.663 GB (96% of total image space).

## A.6 Build Cache Summary (CANDIDATE)

From `docker system df`:

| Metric | Value |
|---|---|
| Build cache entries | 149 |
| Total build cache size | 945.4 MB |
| Reclaimable | 945.4 MB (100%) |
| Active | 0 |

No `docker builder prune` executed. Dry-run only.

## A.7 Volume Reaffirmation: All PROTECTED

R-5B will NOT discuss volume removal. All 4 volumes remain PROTECTED.

| Volume | Status |
|---|---|
| `mpango-erp_postgres_data` | PROTECTED (active) |
| `mpango-erp_redis_data` | PROTECTED (active) |
| `app_postgres_data` | PROTECTED (legacy, 48.18 MB -- deferred beyond R-5B) |
| `app_redis_data` | PROTECTED (legacy -- deferred beyond R-5B) |

## A.8 Corrected Candidate Summary for R-5B Discussion

| Category | Exact Count | Reclaimable (unique, per Docker) | Container Refs | R-5B Scope |
|---|---|---|---|---|
| Active images (PROTECTED) | 5 | 0 B | 5 containers | Not in scope |
| Legacy named images | 5 | shared w/ layers | NONE (verified) | In scope |
| Dangling images | 100 | shared w/ layers | NONE (verified) | In scope |
| Build cache | 149 entries | 945.4 MB | 0 active | In scope |
| Volumes | 4 | N/A | N/A | NOT in scope |
| **Docker total reclaimable** | -- | **9.663 GB (images) + 945.4 MB (cache)** | -- | -- |

## A.9 R-5A-R1 Confirmation

- **No deletions**: No `docker rmi`, `image prune`, `builder prune`, `system prune`, `volume rm`, `stop`, `rm`.
- **No deployment**: No `docker compose up`, `git pull`, `alembic`.
- **No .env read**: No environment files accessed.
- **No backup file touch**: R-4B backup file NOT accessed.
- **sing-box untouched**: Port 443 service not disturbed.
- **Read-only only**: `docker images`, `docker ps`, `docker system df` queries only.

## A.10 Git Commit (R-5A-R1)

| Item | Value |
|---|---|
| Repo | `phase6-closeout-promotion-2026-05-15` |
| Branch | `ops/sprint-r2-vps-script-recovery-2026-05-25` |
| Commit message | `docs(ops): R-5A-R1 exact candidate catalog -- 105 images verified zero container refs` |
| Files changed | `ai-ledger/ops/2026-05-27_sprint_r5a_cleanup_dry_run_inventory.md` (appended Appendix A) |
| Push | **No** -- awaiting CTO review |

> **R-5A-R1 COMPLETE. Exact catalog: 105 non-active images (100 dangling + 5 legacy named), each verified with zero container references. Build cache: 945.4 MB, 100% reclaimable. All volumes PROTECTED, not in R-5B scope.**

---

## Appendix B: R-5A-R2 Ledger Consistency Correction

**Execution Date**: 2026-05-28 12:45 UTC
**Status**: LEDGER_NORMALIZED
**Scope**: Text-only corrections to this ledger file. No VPS connection, no Docker commands, no SSH.

### B.1 Corrections Applied

| Issue | Location | Correction |
|---|---|---|
| Old Section 7 had estimate-based dangling tables | Lines 114-169 | Replaced with brief reference to Appendix A exact catalog. Exact count: 100 (not ~26). |
| Old Section 8 had estimate-based legacy table | Lines 173-183 | Replaced with brief reference to Appendix A.3. Exact count: 5 (not 4). Added `node:18-alpine`. |
| Section 11 cleanup summary had estimates | Lines 220-232 | Replaced with exact counts from Appendix A. Removed `~`, `est.`, `dozens`. |
| Section 1 said "Docker images consume ~10GB" | Line 25 | Replaced with exact Docker-reported values (9.663 GB + 945.4 MB). |
| A.3 header said "1,338 MB" but subtotal said "1,736 MB" | Lines 291, 303 | Header now omits size; subtotal explains displayed-size sum (2,136 MB) vs Docker unique reclaimable (shared layers, included in 9.663 GB). |
| 26 em-dash characters (U+2014 `--`) | Throughout file | All replaced with ASCII `--`. Verified: 0 non-ASCII characters remaining. |

### B.2 Single Source of Truth

After R-5A-R2, the authoritative candidate catalog exists in **Appendix A only** (sections A.2 through A.10). Sections 7, 8, and 11 in the main body are summary references that point to Appendix A for exact per-image detail.

### B.3 Git Commit (R-5A-R2)

| Item | Value |
|---|---|
| Repo | `phase6-closeout-promotion-2026-05-15` |
| Branch | `ops/sprint-r2-vps-script-recovery-2026-05-25` |
| Commit message | `docs(ops): R-5A-R2 ledger normalization -- single source of truth, ASCII-clean` |
| Files changed | `ai-ledger/ops/2026-05-27_sprint_r5a_cleanup_dry_run_inventory.md` |
| Push | **No** -- awaiting CTO review |

> **R-5A-R2 SUPERSEDED_BY_R5A_R3. Appendix A (R-5A-R1) contained a critical miscount: 100 "dangling" images were actually 21 true dangling + 79 intermediate build layers. See Appendix E for the corrected truth recount.**

---

## Appendix E: R-5A-R3 Truth Reconciliation (VPS Read-Only Recount)

**Execution Date**: 2026-05-28 15:06 UTC
**Status**: SUPERSEDED_BY_R5A_R3 -- COUNT_CORRECTED
**Scope**: Read-only SSH to canonical VPS `143.110.177.2`. No modifications. No cleanup commands.
**Preceding Gate**: R-5B-R2 (`8741c11`) -- CTO rejected pending count reconciliation.
**Correction Trigger**: CTO detected R-5B-R2 heredoc contained 112 IDs despite claiming 100. Cross-reference with `docker system df` Images Total = 31 revealed fundamental miscount in R-5A-R1.

### E.1 Root Cause of R-5A-R1 Miscount

R-5A-R1 ran `docker images -a` (with `-a` flag) which returns ALL images including intermediate build layers. The output contained 122 rows. R-5A-R1 classified these as:

- 5 active (correct)
- 5 legacy named (correct)
- ~100 "dangling" (INCORRECT -- conflated true dangling images with intermediate build layers)

**The `-a` flag includes intermediate layers that are NOT dangling.** `docker image prune` does NOT remove these layers -- only `docker rmi` of their parent images would cascade-remove them.

### E.2 Corrected Count Reconciliation

| Metric | Command | R-5A-R1 Claim | Actual (R-5A-R3) |
|---|---|---|---|
| `docker system df` Images Total | `docker system df` | 31 | **31** |
| Top-level named images | `docker image ls` (no `-a`) | N/A (not queried) | **10** |
| True dangling images | `docker image ls -f dangling=true` | 100 | **21** |
| All images incl. intermediate | `docker image ls -a` | 110 | **122** |
| Intermediate build layers | 122 - 31 | N/A (not distinguished) | **91** |
| Build cache entries | `docker system df` | 149 | **149** |

**Verification**: 5 (active) + 5 (legacy) + 21 (dangling) = **31** = `docker system df` Images Total. Consistent.

### E.3 Corrected Top-Level Image Catalog (31 images)

Source: `docker system df -v` on `143.110.177.2`, 2026-05-28 15:10 UTC.

#### E.3.1 Active Images (PROTECTED -- 5 total)

| # | Image ID | Repository | Tag | Size | Containers |
|---|---|---|---|---|---|
| 1 | `aa7d810494f6` | `mpango-erp-backend` | `latest` | 619 MB | 1 |
| 2 | `1e0a7c9d2cc6` | `mpango-erp-frontend` | `latest` | 62.6 MB | 1 |
| 3 | `b76de378d572` | `nginx` | `alpine` | 62.1 MB | 1 |
| 4 | `36a937f48ac7` | `postgres` | `15-alpine` | 274 MB | 1 |
| 5 | `13105d2858de` | `redis` | `7-alpine` | 41.4 MB | 1 |

#### E.3.2 Legacy Named Images (CANDIDATE -- 5 total)

| # | Image ID | Repository | Tag | Size | Containers |
|---|---|---|---|---|---|
| 1 | `eaacea1cbf22` | `app_backend` | `latest` | 998 MB | 0 |
| 2 | `6c19708eb35c` | `app_frontend` | `latest` | 443 MB | 0 |
| 3 | `fa659464a114` | `python` | `3.11-slim` | 124 MB | 0 |
| 4 | `7064d8f3d970` | `postgres` | `15` | 444 MB | 0 |
| 5 | `ee77c6cd7c18` | `node` | `18-alpine` | 127 MB | 0 |

#### E.3.3 True Dangling Images (CANDIDATE -- 21 total)

All have `<none>:<none>` repo:tag. Source: `docker image ls -f dangling=true --no-trunc`.

| # | Image ID | Size | Created | Containers |
|---|---|---|---|---|
| 1 | `45955866e977` | 619 MB | 2 months ago | 0 |
| 2 | `122a0d4c7867` | 62.6 MB | 2 months ago | 0 |
| 3 | `293b68d1c370` | 619 MB | 2 months ago | 0 |
| 4 | `587f897f8071` | 619 MB | 2 months ago | 0 |
| 5 | `286acb7e6b9d` | 619 MB | 2 months ago | 0 |
| 6 | `b95a0bc81cd9` | 62.6 MB | 2 months ago | 0 |
| 7 | `8244f128221f` | 62.6 MB | 2 months ago | 0 |
| 8 | `47e863014dbe` | 619 MB | 2 months ago | 0 |
| 9 | `eac6ffa36989` | 619 MB | 2 months ago | 0 |
| 10 | `d6515b8ba9ee` | 619 MB | 2 months ago | 0 |
| 11 | `909b056c210f` | 619 MB | 2 months ago | 0 |
| 12 | `dcbfb8239c22` | 62.6 MB | 2 months ago | 0 |
| 13 | `d5f4089faf35` | 616 MB | 3 months ago | 0 |
| 14 | `562d9c89a30d` | 62.6 MB | 3 months ago | 0 |
| 15 | `0fc496c615d6` | 1.08 GB | 4 months ago | 0 |
| 16 | `f45583cac65c` | 443 MB | 4 months ago | 0 |
| 17 | `c3f6445fba2c` | 1.08 GB | 4 months ago | 0 |
| 18 | `e923c0c55f1d` | 443 MB | 4 months ago | 0 |
| 19 | `322bdf3e0aaa` | 1.08 GB | 4 months ago | 0 |
| 20 | `d363a698cfb4` | 458 MB | 4 months ago | 0 |
| 21 | `b8ecc4501e86` | 443 MB | 4 months ago | 0 |

### E.4 Concept Clarification: Image vs Layer vs Build Cache

| Concept | Docker Command | Count | Removal Method |
|---|---|---|---|
| **Top-level image** (named) | `docker image ls` | 10 | `docker rmi <ID>` |
| **Top-level image** (dangling) | `docker image ls -f dangling=true` | 21 | `docker image prune` or `docker rmi <ID>` each |
| **Intermediate build layer** | `docker image ls -a` (diff vs top-level) | 91 | Automatically freed when parent image removed |
| **Build cache** | `docker system df` Build Cache | 149 | `docker builder prune` |

**Key insight**: Intermediate layers are NOT independent images. They are filesystem layers created during `docker build` that serve as parents of top-level images. They appear in `docker image ls -a` but NOT in `docker image ls` (without `-a`). They are NOT dangling -- they are referenced by child images. When all child images of a layer are removed, Docker automatically garbage-collects the layer.

### E.5 What This Means for R-5C Cleanup

1. `docker image prune` will remove **21** dangling images (not 100)
2. Removing the 5 legacy named images via `docker rmi` will cascade-free their intermediate layers
3. `docker builder prune` will remove **149** build cache entries (945.4 MB)
4. Total reclaimable remains **9.663 GB (images) + 945.4 MB (build cache)** per `docker system df`
5. The reclaimable amount is unchanged; only our understanding of the image breakdown is corrected

### E.6 Status of Previous Appendices

| Appendix | Status | Reason |
|---|---|---|
| A (R-5A-R1) | **SUPERSEDED_BY_R5A_R3** | Miscounted dangling images as 100 instead of 21. Included 79 intermediate layers as "dangling". |
| B (R-5A-R2) | **SUPERSEDED_BY_R5A_R3** | Normalized incorrect data. Single source of truth was Appendix A which contained wrong counts. |
| E (R-5A-R3) | **CURRENT -- AUTHORITATIVE** | Ground truth from VPS read-only recount. 31 top-level images = 5 active + 5 legacy + 21 dangling. 91 intermediate layers. 149 build cache entries. |

### E.7 Git Commit (R-5A-R3)

| Item | Value |
|---|---|
| Repo | `phase6-closeout-promotion-2026-05-15` |
| Branch | `ops/sprint-r2-vps-script-recovery-2026-05-25` |
| Commit message | `docs(ops): R-5A-R3 truth recount -- 21 dangling (not 100), 91 intermediate layers, Appendix A/B SUPERSEDED` |
| Files changed | `ai-ledger/ops/2026-05-27_sprint_r5a_cleanup_dry_run_inventory.md`, `ai-ledger/ops/2026-05-28_sprint_r5b_cleanup_execution_plan.md` |
| Push | **No** -- awaiting CTO review |

> **R-5A-R3 COMPLETE. Truth reconciliation: 31 top-level images (5 active + 5 legacy + 21 dangling), 91 intermediate build layers, 149 build cache entries. Appendix A (R-5A-R1) and B (R-5A-R2) SUPERSEDED. Corrected catalog in Appendix E is the new single source of truth.**
