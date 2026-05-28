# Sprint R-5B: Cleanup Execution Plan

**Execution Date**: 2026-05-28 14:15 UTC
**Status**: PLAN_ONLY -- AWAITING CTO APPROVAL
**Target**: Canonical India VPS `143.110.177.2` (`ubuntu-s-1vcpu-1gb-blr1-01`)
**Preceding Gate**: R-5A-R2 `LEDGER_NORMALIZED` (commit `e40b327`, pushed)

> **CRITICAL**: This is a PLAN document only. R-5B does NOT execute any cleanup commands. All commands below are proposed for R-5C execution, contingent on CTO approval of this plan.

---

## 1. R-5B Scope

| Category | Count | Reclaimable (Docker unique) | R-5C Eligible? |
|---|---|---|---|
| Dangling images (`<none>:<none>`) | 100 | Included in 9.663 GB | Yes |
| Legacy named images | 5 | Included in 9.663 GB | Yes |
| Build cache entries | 149 | 945.4 MB | Yes |
| Running containers (5) | 5 | 0 B | PROTECTED |
| Active images (5) | 5 | 0 B | PROTECTED |
| Volumes (4) | 4 | 48.18 MB | PROTECTED |
| Networks (4) | 4 | 0 B | PROTECTED |
| sing-box (port 443) | N/A | N/A | PROTECTED_NON_MPANGO_SERVICE |
| R-4B backup file | 1 | N/A | PROTECTED |

**Total proposed reclaimable**: 9.663 GB (images) + 945.4 MB (build cache) = **~10.6 GB**

**Current disk**: 6.1 GB free / 25 GB total (75% used). After cleanup: ~16.7 GB free (67% used).

---

## 2. R-5B Hard Prohibitions

The following commands are FORBIDDEN during R-5B and R-5C unless explicitly authorized by CTO:

- `docker rmi <any-active-image-id>` -- 5 active images are PROTECTED
- `docker stop <any-container>` -- all 5 containers are PROTECTED
- `docker rm <any-container>` -- all 5 containers are PROTECTED
- `docker volume rm <any-volume>` -- all 4 volumes are PROTECTED
- `docker network rm <any-custom>` -- all networks PROTECTED
- `docker system prune -a` -- would remove active images
- `systemctl stop sing-box` -- PROTECTED_NON_MPANGO_SERVICE
- Any `rm` on `/root/mpango-backups/*` -- backup files PROTECTED
- Any `docker compose up`, `git pull`, `alembic` -- deployment commands FORBIDDEN

---

## 3. R-5C Phased Execution Order

R-5C must execute in exactly this order. Each phase has a pre-check, execution command, and post-check with explicit rollback.

### Phase 1: Build Cache (Lowest Risk)

**Rationale**: Build cache has zero impact on running containers. 100% reclaimable (0 active). Safest to remove first. Frees 945.4 MB immediately.

#### Pre-Check (Phase 1)

```bash
# P1-PRE-01: Verify all 5 containers running and healthy
docker ps --format 'table {{.Names}}\t{{.Status}}'

# P1-PRE-02: Verify sing-box running
ps aux | grep sing-box | grep -v grep

# P1-PRE-03: Record current disk space
df -h /

# P1-PRE-04: Record current Docker space
docker system df
```

**P1 Pre-Check Pass Criteria**: All 5 containers show "Up" and "(healthy)". sing-box process present. Disk/docker space recorded.

#### Execution (Phase 1)

```bash
# P1-EXEC-01: Remove build cache only
docker builder prune -f
```

**Expected output**: `Total reclaimed space: ~945.4 MB`

#### Post-Check (Phase 1)

```bash
# P1-POST-01: Verify all 5 containers still running and healthy
docker ps --format 'table {{.Names}}\t{{.Status}}'

# P1-POST-02: Verify sing-box still running
ps aux | grep sing-box | grep -v grep

# P1-POST-03: Verify disk space increased
df -h /

# P1-POST-04: Verify Docker space decreased
docker system df

# P1-POST-05: Verify port 80 responds
curl -s -o /dev/null -w "%{http_code}" http://143.110.177.2:80/ --max-time 10

# P1-POST-06: Verify port 443 responds (sing-box)
curl -s -o /dev/null -w "%{http_code}" https://143.110.177.2:443/ --max-time 10 -k
```

**P1 Post-Check Pass Criteria**:
- 5 containers: all Up, all healthy
- sing-box: process present
- Disk: free space increased by ~945 MB
- Port 80: HTTP 200 or 301/302 (any non-timeout response)
- Port 443: any response (sing-box TLS proxy)

**P1 Rollback**: No rollback needed. Build cache is non-functional; removing it has no side effects. If containers stopped (impossible from this command), restart with `docker compose up -d` from `/root/mpango-erp/`.

**P1 Decision Gate**: If ALL P1 post-checks pass, proceed to Phase 2. If ANY fail, STOP and report to CTO.

---

### Phase 2: Dangling Images (100 images)

**Rationale**: Dangling images (`<none>:<none>`) are unreferenced build layers. All 100 verified with `docker ps -a --filter ancestor=<ID>` returning NONE. Zero container references. `docker image prune` removes only dangling images -- it cannot touch tagged or active images.

#### Pre-Check (Phase 2)

```bash
# P2-PRE-01: Verify all 5 containers running and healthy
docker ps --format 'table {{.Names}}\t{{.Status}}'

# P2-PRE-02: Record dangling image count (must be 100)
docker images -f "dangling=true" -q | wc -l

# P2-PRE-03: Record current Docker space
docker system df

# P2-PRE-04: Record current disk space
df -h /
```

**P2 Pre-Check Pass Criteria**: 5 containers Up/healthy. Dangling count = 100. Disk/Docker space recorded.

#### Execution (Phase 2)

```bash
# P2-EXEC-01: Remove dangling images only
docker image prune -f
```

**Expected output**: `Total reclaimed space: portion of 9.663 GB` (dangling layers; some shared with legacy named images so not all 9.663 GB freed here)

#### Post-Check (Phase 2)

```bash
# P2-POST-01: Verify all 5 containers still running and healthy
docker ps --format 'table {{.Names}}\t{{.Status}}'

# P2-POST-02: Verify sing-box still running
ps aux | grep sing-box | grep -v grep

# P2-POST-03: Verify zero dangling images remain
docker images -f "dangling=true" -q | wc -l

# P2-POST-04: Verify disk space increased
df -h /

# P2-POST-05: Verify Docker image space decreased
docker system df

# P2-POST-06: Verify port 80 responds
curl -s -o /dev/null -w "%{http_code}" http://143.110.177.2:80/ --max-time 10

# P2-POST-07: Verify port 443 responds
curl -s -o /dev/null -w "%{http_code}" https://143.110.177.2:443/ --max-time 10 -k

# P2-POST-08: Verify all 5 active images still present
docker images | grep -E "mpango-erp-backend|mpango-erp-frontend|nginx|postgres|redis"
```

**P2 Post-Check Pass Criteria**:
- 5 containers: all Up, all healthy
- sing-box: process present
- Dangling count: 0
- 5 active images: all present
- Port 80: HTTP response (non-timeout)
- Port 443: response (non-timeout)

**P2 Rollback**: Dangling images cannot be restored (they are unreferenced build layers with no repo:tag). However, if containers are somehow affected (should not be possible since none reference dangling images), restart with `docker compose up -d`. The 5 active images are NOT affected by `docker image prune` (which only targets `<none>:<none>`).

**P2 Decision Gate**: If ALL P2 post-checks pass, proceed to Phase 3. If ANY fail, STOP and report to CTO.

---

### Phase 3: Legacy Named Images (5 images)

**Rationale**: 5 tagged images from the old `app_*` stack. All verified with zero container references. These are explicitly named (not dangling), so `docker image prune` will NOT remove them. Must be removed individually by ID.

**Candidate Images** (from R-5A-R1 Appendix A.3):

| # | Image ID | Repository:Tag | Size |
|---|---|---|---|
| 1 | `eaacea1cbf22` | `app_backend:latest` | 998 MB |
| 2 | `6c19708eb35c` | `app_frontend:latest` | 443 MB |
| 3 | `fa659464a114` | `python:3.11-slim` | 124 MB |
| 4 | `7064d8f3d970` | `postgres:15` | 444 MB |
| 5 | `ee77c6cd7c18` | `node:18-alpine` | 127 MB |

#### Pre-Check (Phase 3)

```bash
# P3-PRE-01: Verify all 5 containers running and healthy
docker ps --format 'table {{.Names}}\t{{.Status}}'

# P3-PRE-02: Re-verify zero container refs for each legacy image
docker ps -a --filter ancestor=eaacea1cbf22 -q  # expect empty
docker ps -a --filter ancestor=6c19708eb35c -q  # expect empty
docker ps -a --filter ancestor=fa659464a114 -q  # expect empty
docker ps -a --filter ancestor=7064d8f3d970 -q  # expect empty
docker ps -a --filter ancestor=ee77c6cd7c18 -q  # expect empty

# P3-PRE-03: Record current Docker space
docker system df

# P3-PRE-04: Record current disk space
df -h /
```

**P3 Pre-Check Pass Criteria**: 5 containers Up/healthy. All 5 legacy image container-ref checks return empty. Disk/Docker space recorded.

#### Execution (Phase 3)

```bash
# P3-EXEC-01: Remove each legacy named image individually
docker rmi eaacea1cbf22
docker rmi 6c19708eb35c
docker rmi fa659464a114
docker rmi 7064d8f3d970
docker rmi ee77c6cd7c18
```

**Expected output**: Each `docker rmi` untags and removes layers not shared with other images.

#### Post-Check (Phase 3)

```bash
# P3-POST-01: Verify all 5 containers still running and healthy
docker ps --format 'table {{.Names}}\t{{.Status}}'

# P3-POST-02: Verify sing-box still running
ps aux | grep sing-box | grep -v grep

# P3-POST-03: Verify legacy images are gone
docker images | grep -E "app_backend|app_frontend|python.*3.11-slim|postgres.*15[^-]|node.*18-alpine"
# Expected: no output (all removed)

# P3-POST-04: Verify all 5 active images still present
docker images | grep -E "mpango-erp-backend|mpango-erp-frontend|nginx|postgres|redis"

# P3-POST-05: Verify disk space increased
df -h /

# P3-POST-06: Verify Docker space decreased
docker system df

# P3-POST-07: Verify port 80 responds
curl -s -o /dev/null -w "%{http_code}" http://143.110.177.2:80/ --max-time 10

# P3-POST-08: Verify port 443 responds
curl -s -o /dev/null -w "%{http_code}" https://143.110.177.2:443/ --max-time 10 -k
```

**P3 Post-Check Pass Criteria**:
- 5 containers: all Up, all healthy
- sing-box: process present
- Legacy images: 0 remain (grep returns nothing)
- 5 active images: all present
- Port 80: HTTP response (non-timeout)
- Port 443: response (non-timeout)

**P3 Rollback**: Legacy named images cannot be restored without re-pulling or re-building. However, since none are referenced by any container (verified in R-5A-R1 and P3-PRE-02), their removal has zero impact on running services. If containers somehow stopped, `docker compose up -d` restarts using the 5 active images which are untouched.

---

## 4. R-5C Final Verification (After All 3 Phases)

After Phase 3 completes successfully, run a full system health check:

```bash
# FINAL-01: All 5 containers running and healthy
docker ps --format 'table {{.Names}}\t{{.Status}}'

# FINAL-02: Only 5 images remain (active only)
docker images

# FINAL-03: Docker space summary
docker system df

# FINAL-04: Disk space
df -h /

# FINAL-05: sing-box process
ps aux | grep sing-box | grep -v grep

# FINAL-06: Port 80 health check
curl -s -o /dev/null -w "%{http_code}" http://143.110.177.2:80/ --max-time 10

# FINAL-07: Port 443 health check
curl -s -o /dev/null -w "%{http_code}" https://143.110.177.2:443/ --max-time 10 -k

# FINAL-08: All 4 volumes intact
docker volume ls

# FINAL-09: All 4 networks intact
docker network ls

# FINAL-10: R-4B backup file intact
ls -la /root/mpango-backups/mpango_erp_20260527_063830.sql.gz
```

**FINAL Pass Criteria**:
- 5 containers: Up, healthy
- Images: exactly 5 active images remain, 0 dangling, 0 legacy named
- Disk free: ~16.7 GB (up from 6.1 GB)
- Docker image space: ~1 GB (down from 9.992 GB)
- Build cache: 0 MB (down from 945.4 MB)
- Port 80: responding
- Port 443: responding (sing-box)
- 4 volumes: intact
- 4 networks: intact
- Backup file: intact at `/root/mpango-backups/`

---

## 5. PROTECTED Resources (No-Go Checklist)

Before executing any R-5C phase, the operator must confirm ALL of the following are UNTOUCHED:

| Resource | Identifier | Why Protected |
|---|---|---|
| `mpango_prod_backend` | Container `aa7d810494f6` | Production backend |
| `mpango_prod_frontend` | Container `1e0a7c9d2cc6` | Production frontend |
| `mpango_prod_gateway` | Container `b76de378d572` | Production nginx reverse proxy |
| `mpango_prod_postgres` | Container `36a937f48ac7` | Production database |
| `mpango_prod_redis` | Container `13105d2858de` | Production cache |
| `mpango-erp_postgres_data` | Volume | Production DB data |
| `mpango-erp_redis_data` | Volume | Production cache data |
| `app_postgres_data` | Volume | Legacy data, deferred |
| `app_redis_data` | Volume | Legacy data, deferred |
| `mpango-erp_mpango_network` | Network | Container connectivity |
| sing-box | PID 132529, port 443 | Non-MPANGO TLS proxy |
| R-4B backup | `/root/mpango-backups/mpango_erp_20260527_063830.sql.gz` | Verified backup artifact |

---

## 6. Expected Reclamation Summary

| Phase | Target | Docker Reclaimable | Cumulative Free Disk |
|---|---|---|---|
| Before R-5C | -- | -- | 6.1 GB |
| Phase 1: Build Cache | 149 entries | 945.4 MB | ~7.0 GB |
| Phase 2: Dangling Images | 100 images | ~8.5 GB (estimate, shared layers) | ~15.5 GB |
| Phase 3: Legacy Named | 5 images | ~1.1 GB (remaining shared layers) | ~16.7 GB |

> Note: Phase-by-phase disk reclamation is approximate because Docker shared layers are freed only when the last image referencing a layer is removed. `docker system df` after each phase gives the authoritative figure.

---

## 7. R-5B Confirmation

- **No cleanup commands executed in R-5B**: This document is a plan only.
- **No Docker commands**: No `docker rmi`, `image prune`, `builder prune`, `system prune`, `volume rm`.
- **No SSH**: No VPS connection in R-5B.
- **No deployment**: No `docker compose up`, `git pull`, `alembic`.
- **No .env read**: No environment files accessed.
- **No backup file touch**: R-4B backup file NOT accessed.
- **sing-box untouched**: Port 443 service not disturbed.
- **All volumes PROTECTED**: No volume removal discussed.
- **All containers PROTECTED**: No container stop/restart discussed.

---

## 8. Git Commit (R-5B)

| Item | Value |
|---|---|
| Repo | `phase6-closeout-promotion-2026-05-15` |
| Branch | `ops/sprint-r2-vps-script-recovery-2026-05-25` |
| Commit message | `docs(ops): R-5B cleanup execution plan -- phased commands, rollback checklist, zero execution` |
| Files changed | New: `ai-ledger/ops/2026-05-28_sprint_r5b_cleanup_execution_plan.md` |
| Push | **No** -- awaiting CTO review |

> **R-5B COMPLETE (plan only). Awaiting CTO approval to proceed to R-5C execution. R-5C will follow the 3-phase order: Phase 1 (build cache), Phase 2 (dangling images), Phase 3 (legacy named images), with health checks between every phase.**
