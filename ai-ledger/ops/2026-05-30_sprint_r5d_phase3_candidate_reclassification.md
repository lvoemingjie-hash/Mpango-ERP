# Sprint R-5D: Phase 3 Candidate Reclassification -- Read-Only Investigation

**Execution Date**: 2026-05-30 05:53 UTC
**Status**: INVESTIGATION_COMPLETE
**Target**: Canonical India VPS `143.110.177.2` (`ubuntu-s-1vcpu-1gb-blr1-01`)
**Preceding Gate**: R-5C Phase 2 (`248a1c7`, pushed to origin)
**Scope**: READ-ONLY ONLY. No `docker rmi`, `docker image prune`, `docker builder prune`, container/volume/deploy/migration/.env operations.

> **CTO Trigger**: R-5C Phase 2 report showed `postgres:15` (`7064d8f3d970`) appearing in both "Active Images Present" and "Legacy Images" sections. CTO halted Phase 3 pending reclassification of all 5 legacy candidates into: SAFE_TO_REMOVE, PROTECTED_SHARED, or UNCLEAR_STOP_AND_REPORT.

---

## 1. Investigation Summary

| # | Image ID | Repository:Tag | Container Refs | Compose Reference | Classification |
|---|---|---|---|---|---|
| 1 | `eaacea1cbf22` | `app_backend:latest` | NONE | Legacy `/root/app/docker-compose.yml` (build context only) | **SAFE_TO_REMOVE** |
| 2 | `6c19708eb35c` | `app_frontend:latest` | NONE | Legacy `/root/app/docker-compose.yml` (build context only) | **SAFE_TO_REMOVE** |
| 3 | `fa659464a114` | `python:3.11-slim` | NONE | None (was build base for app_backend) | **SAFE_TO_REMOVE** |
| 4 | `7064d8f3d970` | `postgres:15` | NONE | Legacy `/root/app/docker-compose.yml` line 6 | **SAFE_TO_REMOVE** |
| 5 | `ee77c6cd7c18` | `node:18-alpine` | NONE | None (was build base for app_frontend) | **SAFE_TO_REMOVE** |

**All 5 legacy candidates are SAFE_TO_REMOVE.** Zero container references. Zero active dependencies. No PROTECTED_SHARED or UNCLEAR items found.

---

## 2. Per-Image Detailed Evidence

### 2.1 `eaacea1cbf22` / `app_backend:latest`

```
Container refs (docker ps -a --filter ancestor=eaacea1cbf22 -q): (empty)
Image inspect:
  ID=sha256:eaacea1cbf22bc6e884760f3bd693c4430e5b9099fb587f3cf9d7deb431672cb
  RepoTags=[app_backend:latest]
  Created=2026-01-21T08:22:59Z
  Size=997864946 (998 MB)
  Parent=sha256:43d94af0ab04... (intermediate layer, already removed in Phase 2)

docker system df -v:
  Shared=997.9MB  Unique=0B  Containers=0
```

**Analysis**: Locally built image from old `app_*` stack. All layers shared with other images (Unique=0B). Legacy compose at `/root/app/docker-compose.yml` uses `build: context: ./backend`, not `image: app_backend`. No runtime dependency.

**Classification**: **SAFE_TO_REMOVE**

---

### 2.2 `6c19708eb35c` / `app_frontend:latest`

```
Container refs (docker ps -a --filter ancestor=6c19708eb35c -q): (empty)
Image inspect:
  ID=sha256:6c19708eb35c21cf407a1edc41d0b13e709aa270263176c386c1328870f72f1b
  RepoTags=[app_frontend:latest]
  Created=2026-01-18T02:25:28Z
  Size=442666393 (443 MB)
  Parent=sha256:38de73448d89... (intermediate layer, already removed in Phase 2)

docker system df -v:
  Shared=442.7MB  Unique=0B  Containers=0
```

**Analysis**: Locally built image from old `app_*` stack. All layers shared. Legacy compose uses `build: context: ./frontend`, not this tag. No runtime dependency.

**Classification**: **SAFE_TO_REMOVE**

---

### 2.3 `fa659464a114` / `python:3.11-slim`

```
Container refs (docker ps -a --filter ancestor=fa659464a114 -q): (empty)
Image inspect:
  ID=sha256:fa659464a114c340e31c7b7954a1aa679de7e7f5346e4b5804e8422b2596aff9
  RepoTags=[python:3.11-slim]
  Created=2026-01-13T03:14:21Z
  Size=124446642 (124 MB)
  Parent=(empty -- base image, no parent)

docker system df -v:
  Shared=124.4MB  Unique=0B  Containers=0
```

**Analysis**: Pulled base image used during `docker build` of `app_backend`. Not referenced in any compose file. No container ever runs from this image. Its layers are shared with `app_backend` (which itself is unused).

**Classification**: **SAFE_TO_REMOVE**

---

### 2.4 `7064d8f3d970` / `postgres:15` -- PRIMARY INVESTIGATION TARGET

```
Container refs (docker ps -a --filter ancestor=7064d8f3d970 -q): (empty)
Image inspect:
  ID=sha256:7064d8f3d97089dad48d711f2ac4b60bd71edc79f09ea9f65b1806383eeb0987
  RepoTags=[postgres:15]
  RepoDigests=[postgres@sha256:42283dfbd8b955b4ddf43b6df49356ee2cf10a5957839a0e8d1b568c38b54fc2]
  Created=2026-01-13T01:53:15Z
  Size=444429221 (444 MB)
  Architecture=amd64  Os=linux
  Parent=(empty -- pulled base image)

docker system df -v:
  Shared=78.61MB  Unique=365.8MB  Containers=0

Compose references:
  - /root/mpango-erp/docker-compose.yml:       image: postgres:15-alpine  (DIFFERENT IMAGE)
  - /root/mpango-erp/docker-compose.prod.yml:  image: postgres:15-alpine  (DIFFERENT IMAGE)
  - /root/app/docker-compose.yml line 6:       image: postgres:15         (THIS IMAGE -- legacy)

Active postgres container:
  mpango_prod_postgres uses Image=sha256:36a937f48ac7... (postgres:15-alpine, NOT this image)

Cron/scripts: No references to 'postgres:15' (without '-alpine') in any .sh/.py/.yml files.
```

#### Root Cause of "Dual Appearance" in Phase 2 Report

The Phase 2 post-check used:
```bash
docker images | grep -E 'postgres'
```

This returned BOTH postgres images:
```
postgres:15          7064d8f3d970   444MB
postgres:15-alpine   36a937f48ac7   274MB
```

Making it appear that `postgres:15` was an "active" image. **This was a reporting artifact from a too-broad grep pattern.**

#### Proof They Are Completely Different Images

| Attribute | `postgres:15` (Legacy) | `postgres:15-alpine` (Active) |
|---|---|---|
| Image ID | `7064d8f3d970` | `36a937f48ac7` |
| Full SHA256 | `7064d8f3d97089dad...` | `36a937f48ac758ae...` |
| Base OS | Debian (full) | Alpine Linux |
| Size | 444 MB | 274 MB |
| Shared Size | 78.61 MB | 0B |
| Unique Size | 365.8 MB | 273.8 MB |
| RootFS Layers | 14 layers (Debian) | 11 layers (Alpine) |
| Layer Overlap | **NONE** -- completely different RootFS chains |
| Containers | 0 | 1 (mpango_prod_postgres) |
| Compose ref | Legacy `/root/app/docker-compose.yml` only | Current `/root/mpango-erp/docker-compose.yml` |

**The two images share ZERO RootFS layers.** They are completely independent. Removing `postgres:15` has zero impact on the running `mpango_prod_postgres` container.

**Classification**: **SAFE_TO_REMOVE**

---

### 2.5 `ee77c6cd7c18` / `node:18-alpine`

```
Container refs (docker ps -a --filter ancestor=ee77c6cd7c18 -q): (empty)
Image inspect:
  ID=sha256:ee77c6cd7c1886ecc802ad6cedef3a8ec1ea27d1fb96162bf03dd3710839b8da
  RepoTags=[node:18-alpine]
  Created=2025-03-27T14:23:08Z
  Size=126988140 (127 MB)
  Parent=(empty -- pulled base image)

docker system df -v:
  Shared=127MB  Unique=0B  Containers=0
```

**Analysis**: Pulled base image used during `docker build` of `app_frontend`. Not referenced in any compose file. No container runs from this image. Oldest image on the system (14 months).

**Classification**: **SAFE_TO_REMOVE**

---

## 3. Additional Context: Compose File Inventory

| File | Status | Postgres Image Spec |
|---|---|---|
| `/root/mpango-erp/docker-compose.yml` | **ACTIVE** (current production) | `postgres:15-alpine` |
| `/root/mpango-erp/docker-compose.prod.yml` | **ACTIVE** (production overrides) | `postgres:15-alpine` |
| `/root/mpango-erp/docker-compose.override.yml` | **ACTIVE** (no image specs) | N/A |
| `/root/app/docker-compose.yml` | **LEGACY** (old `app_*` stack, not running) | `postgres:15` |

The legacy compose at `/root/app/docker-compose.yml` is the only file referencing `postgres:15`. This stack has no running containers. Its containers (`mpango_postgres`, `mpango_redis`, `mpango_backend`, `mpango_frontend`) do not exist (replaced by `mpango_prod_*`).

---

## 4. Shared Layer Analysis

From `docker system df -v` after Phase 2:

| Image | Shared | Unique | Why Shared |
|---|---|---|---|
| `app_backend:latest` | 997.9 MB | 0B | Layers shared with `python:3.11-slim` and other build artifacts |
| `app_frontend:latest` | 442.7 MB | 0B | Layers shared with `node:18-alpine` and other build artifacts |
| `python:3.11-slim` | 124.4 MB | 0B | Base layers shared with `app_backend` |
| `postgres:15` | 78.61 MB | 365.8 MB | Some layers shared with Debian-based images; 365.8 MB unique |
| `node:18-alpine` | 127 MB | 0B | Layers shared with `app_frontend` |

**Total Docker reclaimable from images**: 1.868 GB (from `docker system df`). This will be freed when all 5 legacy images are removed, because shared layers become unreferenced and Docker garbage-collects them.

---

## 5. Reclamation Prediction (Phase 3)

| Metric | Current | After Phase 3 (predicted) |
|---|---|---|
| Images total | 10 | **5** (active only) |
| Docker image space | 2.679 GB | **~0.81 GB** (5 active images) |
| Docker image reclaimable | 1.868 GB | ~0B |
| Disk free | 12 GB (53%) | **~14 GB (~44%)** |

---

## 6. System Context Verification

| Check | Result |
|---|---|
| Hostname | `ubuntu-s-1vcpu-1gb-blr1-01` |
| 5 containers | All Up healthy |
| sing-box | PID 132529, running |
| Port 443 | LISTEN |
| Port 80 | HTTP 200 |
| R-4B backup | 10967 bytes, intact |
| Crontab | Empty (no cron jobs) |
| Scripts referencing legacy images | None found |

---

## 7. R-5D Confirmation

- **No cleanup commands executed**: READ-ONLY ONLY
- **No `docker rmi`**: NOT executed
- **No `docker image prune -f`**: NOT executed
- **No `docker builder prune`**: NOT executed
- **No container/volume/deploy operations**: NOT executed
- **No `.env` read**: NOT accessed
- **SSH commands**: `docker ps`, `docker inspect`, `docker image inspect`, `docker image ls`, `docker system df`, `grep`, `cat`, `find`, `crontab` only

---

## 8. Recommendation for CTO

**All 5 legacy candidates are SAFE_TO_REMOVE:**

1. Zero container references for all 5 images
2. Zero runtime dependencies (no cron, no scripts, no active compose references)
3. `postgres:15` (7064d8f3d970) is NOT the active postgres image -- the active one is `postgres:15-alpine` (36a937f48ac7), a completely different image with zero shared RootFS layers
4. The "dual appearance" in Phase 2 report was a grep artifact (pattern `postgres` matched both tags)
5. Legacy compose at `/root/app/docker-compose.yml` is the sole reference to `postgres:15` and has no running containers
6. No PROTECTED_SHARED or UNCLEAR items identified

**Phase 3 is clear to proceed upon CTO approval.** Expected reclamation: ~1.868 GB (Docker image space), ~2 GB additional disk free.

---

## 9. Git Commit (R-5D)

| Item | Value |
|---|---|
| Repo | `phase6-closeout-promotion-2026-05-15` |
| Branch | `ops/sprint-r2-vps-script-recovery-2026-05-25` |
| Commit message | `docs(ops): R-5D Phase 3 candidate reclassification -- all 5 legacy SAFE_TO_REMOVE, postgres:15 proven distinct from 15-alpine` |
| Files changed | New: `ai-ledger/ops/2026-05-30_sprint_r5d_phase3_candidate_reclassification.md` |
| Push | **No** -- awaiting CTO review |
