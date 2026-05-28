# Sprint R-5B: Cleanup Execution Plan

**Execution Date**: 2026-05-28 14:15 UTC
**Status**: PLAN_ONLY -- AWAITING CTO APPROVAL (R-5B-R3 count reconciliation + exact-ID removal strategy)
**Target**: Canonical India VPS `143.110.177.2` (`ubuntu-s-1vcpu-1gb-blr1-01`)
**Preceding Gate**: R-5A-R3 `SUPERSEDED_BY_R5A_R3` (truth recount: 21 dangling, not 100)

> **CRITICAL**: This is a PLAN document only. R-5B does NOT execute any cleanup commands. All commands below are proposed for R-5C execution, contingent on CTO approval of this plan.
>
> **R-5B-R3 NOTE**: R-5A-R1 through R-5B-R2 are SUPERSEDED. The original R-5A-R1 catalog claimed 100 dangling images; the true count is 21. R-5A-R1 used `docker image ls -a` (includes intermediate build layers) and conflated 79 intermediate layers with true dangling images. All counts below are corrected per R-5A-R3 VPS truth recount.
>
> **CURRENT AUTHORIZED COMMAND SET (R-5B-R4)**:
> - **Phase 1**: `docker builder prune -f` (build cache, 149 entries)
> - **Phase 2**: `docker rmi <ID>` x21 (exact dangling image IDs from R-5A-R3 Appendix E.3.3)
> - **Phase 3**: `docker rmi <ID>` x5 (exact legacy named image IDs)
> - **EXPLICITLY FORBIDDEN**: `docker image prune -f` -- global prune removed from R-5B-R3; exact-ID removal only

---

## 1. R-5B Scope

| Category | Count | Reclaimable (Docker unique) | R-5C Eligible? |
|---|---|---|---|
| True dangling images (`<none>:<none>`, top-level) | **21** | Included in 9.663 GB | Yes |
| Legacy named images | **5** | Included in 9.663 GB | Yes |
| Build cache entries | **149** | 945.4 MB | Yes |
| Intermediate build layers (91) | **91** | Auto-freed when parents removed | Indirect (freed by Phase 2+3) |
| Running containers (5) | 5 | 0 B | PROTECTED |
| Active images (5) | 5 | 0 B | PROTECTED |
| Volumes (4) | 4 | 48.18 MB | PROTECTED |
| Networks (4) | 4 | 0 B | PROTECTED |
| sing-box (port 443) | N/A | N/A | PROTECTED_NON_MPANGO_SERVICE |
| R-4B backup file | 1 | N/A | PROTECTED |

**Total proposed reclaimable**: 9.663 GB (images) + 945.4 MB (build cache) = **~10.6 GB**

**Current disk**: 6.1 GB free / 25 GB total (75% used). After cleanup: ~16.7 GB free (~33% used).

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

> **Scope of `docker builder prune -f`**: This command removes ALL inactive Docker build cache entries across the entire Docker daemon. It is a Docker-wide operation, not scoped to any single project. R-5A-R1 confirmed 149 entries totaling 945.4 MB, with 0 active. If any build cache entry has become active since R-5A-R1 (e.g. from an intermediate build), `docker builder prune` will NOT remove it -- Docker only prunes inactive cache.

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

# P1-PRE-05: Verify build cache has 0 active entries
docker system df -v | grep -A5 "Build Cache"
# Confirm "Active" column shows 0 before proceeding.
```

**P1 Pre-Check Pass Criteria**: All 5 containers show "Up" and "(healthy)". sing-box process present. Disk/docker space recorded. **Build Cache Active = 0**. If Active > 0: **STOP_AND_REPORT_CTO** -- do not prune.

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

# P1-POST-06: Verify sing-box still listening on port 443 (process + socket)
ps aux | grep sing-box | grep -v grep
ss -ltnp | grep ':443'
```

**P1 Post-Check Pass Criteria**:
- 5 containers: all Up, all healthy
- sing-box: process present
- Disk: free space increased by ~945 MB
- Port 80: HTTP 200 or 301/302 (any non-timeout response)
- Port 443: sing-box process present AND `ss -ltnp` shows LISTEN on `:443`

**P1 Failure Policy**: Build cache removal has no impact on running containers. If any P1 post-check fails: **STOP_AND_REPORT_CTO**. Do NOT run `docker compose up` or any deployment/restart command. The operator must halt all phases, record the exact failure output, and await CTO instruction.

**P1 Decision Gate**: If ALL P1 post-checks pass, proceed to Phase 2. If ANY fail, STOP and report to CTO.

---

### Phase 2: Dangling Images (21 images -- exact-ID removal)

**Rationale**: 21 true dangling images (`<none>:<none>`), verified as top-level via `docker image ls -f dangling=true`. All have zero container references. R-5A-R3 Appendix E.3.3 contains the authoritative catalog.

> **Strategy Change (R-5B-R3)**: Previous iterations used `docker image prune -f` (global prune of all dangling). R-5B-R3 replaces this with explicit `docker rmi <ID>` for each of the 21 authorized dangling IDs. This ensures only the exact authorized IDs are removed, with zero risk of removing newly-created dangling images.

#### Pre-Check (Phase 2)

```bash
# P2-PRE-01: Verify all 5 containers running and healthy
docker ps --format 'table {{.Names}}\t{{.Status}}'

# P2-PRE-02: Record dangling image count (must be 21)
docker images -f "dangling=true" -q | wc -l

# P2-PRE-03: EXACT ID LOCK -- verify current dangling IDs match R-5A-R3 catalog
cat > /tmp/r5a_r3_authorized_dangling_ids.txt << 'AUTHORIZED_EOF'
45955866e977
122a0d4c7867
293b68d1c370
587f897f8071
286acb7e6b9d
b95a0bc81cd9
8244f128221f
47e863014dbe
eac6ffa36989
d6515b8ba9ee
909b056c210f
dcbfb8239c22
d5f4089faf35
562d9c89a30d
0fc496c615d6
f45583cac65c
c3f6445fba2c
e923c0c55f1d
322bdf3e0aaa
d363a698cfb4
b8ecc4501e86
AUTHORIZED_EOF

docker images -f "dangling=true" -q | sort > /tmp/r5c_current_dangling_ids.txt
sort /tmp/r5a_r3_authorized_dangling_ids.txt > /tmp/r5a_r3_sorted.txt
diff /tmp/r5c_current_dangling_ids.txt /tmp/r5a_r3_sorted.txt
echo "Diff exit code: $?"
# If exit code != 0: STOP_AND_REPORT_CTO

# P2-PRE-04: Record current Docker space
docker system df

# P2-PRE-05: Record current disk space
df -h /
```

**P2 Pre-Check Pass Criteria** (ALL must pass):
- 5 containers Up/healthy
- Dangling count = 21
- **Exact ID lock: `diff` produces ZERO output and exit code 0**
- Disk/Docker space recorded

> **P2 ID Lock Failure**: If `diff` shows any differences, **STOP_AND_REPORT_CTO** with full diff output. Do NOT proceed.

#### Execution (Phase 2)

```bash
# P2-EXEC-01 through P2-EXEC-21: Remove each authorized dangling image by exact ID.
# Each command removes exactly one authorized image. No global prune.
# EXECUTION GATE: Authorized ONLY IF P2-PRE-03 exact ID lock diff returned 0.
docker rmi 45955866e977
docker rmi 122a0d4c7867
docker rmi 293b68d1c370
docker rmi 587f897f8071
docker rmi 286acb7e6b9d
docker rmi b95a0bc81cd9
docker rmi 8244f128221f
docker rmi 47e863014dbe
docker rmi eac6ffa36989
docker rmi d6515b8ba9ee
docker rmi 909b056c210f
docker rmi dcbfb8239c22
docker rmi d5f4089faf35
docker rmi 562d9c89a30d
docker rmi 0fc496c615d6
docker rmi f45583cac65c
docker rmi c3f6445fba2c
docker rmi e923c0c55f1d
docker rmi 322bdf3e0aaa
docker rmi d363a698cfb4
docker rmi b8ecc4501e86
```

**Expected output**: Each `docker rmi` untags and frees layers not shared with remaining images.

> **FAIL-CLOSED RULE (Phase 2)**: Execute each `docker rmi` command individually. After EACH command, check the exit code. If **any** `docker rmi` returns a non-zero exit code: **immediately STOP_AND_REPORT_CTO**. Do NOT execute the next `docker rmi` command. Do NOT proceed to Phase 3. Record the exact error output from the failed command and await CTO instruction. There is NO automatic continue-on-error.

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

# P2-POST-07: Verify sing-box still listening on port 443
ps aux | grep sing-box | grep -v grep
ss -ltnp | grep ':443'

# P2-POST-08: Verify all 5 active images still present
docker images | grep -E "mpango-erp-backend|mpango-erp-frontend|nginx|postgres|redis"
```

**P2 Post-Check Pass Criteria**:
- 5 containers: all Up, all healthy
- sing-box: process present
- Dangling count: 0
- 5 active images: all present
- Port 80: HTTP response (non-timeout)
- Port 443: sing-box process present AND `ss -ltnp` shows LISTEN on `:443`

**P2 Failure Policy**: Dangling images cannot be restored (unreferenced build layers with no repo:tag). The 5 active images are NOT affected by `docker image prune` (which only targets `<none>:<none>`). If any P2 post-check fails: **STOP_AND_REPORT_CTO**. Do NOT run `docker compose up` or any deployment/restart command. The operator must halt all phases, record the exact failure output, and await CTO instruction.

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

> **FAIL-CLOSED RULE (Phase 3)**: Execute each `docker rmi` command individually. After EACH command, check the exit code. If **any** `docker rmi` returns a non-zero exit code: **immediately STOP_AND_REPORT_CTO**. Do NOT execute the next `docker rmi` command. Record the exact error output from the failed command and await CTO instruction. There is NO automatic continue-on-error.

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

# P3-POST-08: Verify sing-box still listening on port 443
ps aux | grep sing-box | grep -v grep
ss -ltnp | grep ':443'
```

**P3 Post-Check Pass Criteria**:
- 5 containers: all Up, all healthy
- sing-box: process present
- Legacy images: 0 remain (grep returns nothing)
- 5 active images: all present
- Port 80: HTTP response (non-timeout)
- Port 443: sing-box process present AND `ss -ltnp` shows LISTEN on `:443`

**P3 Failure Policy**: Legacy named images cannot be restored without re-pulling or re-building. Since none are referenced by any container (verified in R-5A-R1 and P3-PRE-02), their removal has zero impact on running services. If any P3 post-check fails: **STOP_AND_REPORT_CTO**. Do NOT run `docker compose up` or any deployment/restart command. The operator must halt all phases, record the exact failure output, and await CTO instruction.

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

# FINAL-07: sing-box process and port 443 listener
ps aux | grep sing-box | grep -v grep
ss -ltnp | grep ':443'

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
- Port 443: sing-box process present, `ss -ltnp` shows LISTEN on `:443`
- 4 volumes: intact
- 4 networks: intact
- Backup file: intact at `/root/mpango-backups/`

---

## 5. PROTECTED Resources (No-Go Checklist)

Before executing any R-5C phase, the operator must confirm ALL of the following are UNTOUCHED:

| Resource | Container Name | Image ID | Why Protected |
|---|---|---|---|
| Production backend | `mpango_prod_backend` | `aa7d810494f6` | Production backend container |
| Production frontend | `mpango_prod_frontend` | `1e0a7c9d2cc6` | Production frontend container |
| Production gateway | `mpango_prod_gateway` | `b76de378d572` | Production nginx reverse proxy |
| Production database | `mpango_prod_postgres` | `36a937f48ac7` | Production database container |
| Production cache | `mpango_prod_redis` | `13105d2858de` | Production cache container |
| `mpango-erp_postgres_data` | -- | -- | Volume: production DB data |
| `mpango-erp_redis_data` | -- | -- | Volume: production cache data |
| `app_postgres_data` | -- | -- | Volume: legacy data, deferred |
| `app_redis_data` | -- | -- | Volume: legacy data, deferred |
| `mpango-erp_mpango_network` | -- | -- | Network: container connectivity |
| sing-box | -- | -- | Process: non-MPANGO TLS proxy on port 443 |
| R-4B backup | -- | -- | File: `/root/mpango-backups/mpango_erp_20260527_063830.sql.gz` |

---

## 6. Expected Reclamation Summary

| Phase | Target | Docker Reclaimable | Cumulative Free Disk |
|---|---|---|---|
| Before R-5C | -- | -- | 6.1 GB |
| Phase 1: Build Cache | 149 entries | 945.4 MB | ~7.0 GB |
| Phase 2: Dangling Images (exact rmi) | 21 images | portion of 9.663 GB | ~TBD per `docker system df` |
| Phase 3: Legacy Named (exact rmi) | 5 images | remaining of 9.663 GB | ~16.7 GB |

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
| R-5B commit | `09d5f8b` -- `docs(ops): R-5B cleanup execution plan -- phased commands, rollback checklist, zero execution` |
| R-5B-R1 commit | `82d9522` -- `docs(ops): R-5B-R1 plan safety correction -- STOP_AND_REPORT_CTO, sing-box ps+ss, disk pct fix` |
| R-5B-R2 commit | `8741c11` -- `docs(ops): R-5B-R2 exact target lock -- dangling ID diff, build cache active=0 gate` (SUPERSEDED: IDs were wrong) |
| R-5B-R3 commit | (this commit) -- `docs(ops): R-5B-R3 count reconciliation + exact-ID removal -- 21 dangling (not 100), no docker image prune` |
| Push | **No** -- awaiting CTO review |

---

## Appendix C: R-5B-R1 Plan Safety Corrections

**Execution Date**: 2026-05-28 14:31 UTC
**Status**: PLAN_CORRECTED
**Scope**: Text-only corrections to this plan. No VPS connection, no Docker commands, no SSH.

### C.1 Corrections Applied

| Issue | Location | Correction |
|---|---|---|
| Rollback sections prescribed `docker compose up -d` | Phase 1 (line ~112), Phase 2 (line ~185), Phase 3 (line ~277) | Removed all `docker compose up` references. Replaced with **STOP_AND_REPORT_CTO** policy: halt all phases, record failure output, await CTO instruction. |
| Port 443 health used `curl https://` (HTTP semantic check on non-HTTP proxy) | P1-POST-06, P2-POST-07, P3-POST-08, FINAL-07 | Replaced with `ps aux \| grep sing-box` + `ss -ltnp \| grep ':443'` (process + TCP listener check, no HTTP semantics). |
| Disk percentage miscalculation: "67% used" after cleanup | Section 1, line ~28 | 16.7 GB free of 25 GB = 8.3 GB used = ~33% used. Corrected. |
| Protected resources table conflated container name and image ID | Section 5, lines ~337-348 | Separated into distinct columns: Resource description, Container Name, Image ID. |

### C.2 Remaining Unchanged

- Three-phase execution order (build cache -> dangling images -> legacy named images)
- ~~Exact cleanup commands (`docker builder prune -f`, `docker image prune -f`, `docker rmi` x5)~~ SUPERSEDED_BY_R5B_R3: `docker image prune -f` replaced by `docker rmi <ID>` x21. Current authorized commands: `docker builder prune -f`, `docker rmi` x21, `docker rmi` x5.
- Pre-check and post-check commands for containers, disk, Docker space
- Port 80 HTTP check (valid for nginx reverse proxy)
- PROTECTED status of all volumes, containers, active images, networks, sing-box, backup file

> **R-5B-R1 COMPLETE (plan corrections). Awaiting CTO approval to proceed to R-5C execution.**

---

## Appendix D: R-5B-R2 Exact Target Lock Correction

**Execution Date**: 2026-05-28 15:06 UTC
**Status**: PLAN_CORRECTED
**Scope**: Text-only corrections to this plan. No VPS connection, no Docker commands, no SSH.

### D.1 Corrections Applied

| Issue | Location | Correction |
|---|---|---|
| Phase 2 pre-check only verified dangling count=100, not exact IDs | P2-PRE-02 | Added P2-PRE-03: exact ID lock. Write R-5A-R1 authorized 100 dangling IDs to file on VPS, collect current dangling IDs, sort both, `diff`. Must produce zero output. |
| `docker image prune -f` could remove new dangling images beyond R-5A-R1 scope | P2-EXEC-01 | Added EXECUTION GATE: `docker image prune -f` is authorized ONLY IF P2-PRE-03 exact ID lock diff returned 0 differences. If diff shows discrepancy: STOP_AND_REPORT_CTO. |
| Phase 1 `docker builder prune -f` scope not documented | Phase 1 rationale | Added scope note: `docker builder prune -f` removes ALL inactive Docker build cache (Docker-wide). Docker only prunes inactive cache, so any new active entries are protected. |
| Phase 1 did not verify build cache active=0 | P1-PRE-05 | Added pre-check: `docker system df -v` to confirm Build Cache Active = 0 before pruning. If Active > 0: STOP_AND_REPORT_CTO. |

### D.2 Authorized Dangling Image ID Set (SUPERSEDED -- contained 112 IDs, not 100)

The R-5B-R2 heredoc listed 112 unique IDs but claimed 100. This was because R-5A-R1's Appendix A sections A.4.1-A.4.10 also contained an inflated count (group subtotals summed to 112 while grand total said 100). **The entire R-5A-R1 catalog is SUPERSEDED by R-5A-R3 Appendix E.3.3 which identifies the true 21 dangling images.**

The correct 21 authorized dangling image IDs are in Phase 2 pre-check P2-PRE-03 above and in R-5A-R3 Appendix E.3.3.

### D.3 Remaining Unchanged

- Phase 1 execution command (`docker builder prune -f`)
- Phase 3 execution commands (`docker rmi` x5 by explicit ID -- already exact-target by design)
- All post-check commands
- STOP_AND_REPORT_CTO failure policy
- PROTECTED resource list
- Three-phase execution order

> **R-5B-R2 SUPERSEDED_BY_R5B_R3. The 112-ID heredoc and `docker image prune` strategy are replaced by R-5B-R3 exact-ID removal.**

---

## Appendix E: R-5B-R3 Count Reconciliation + Exact-ID Removal Strategy

**Execution Date**: 2026-05-28 15:24 UTC
**Status**: PLAN_CORRECTED
**Scope**: Read-only SSH to VPS `143.110.177.2` for truth recount. No cleanup commands executed.

### E.1 Root Cause

R-5A-R1 used `docker images -a` which includes 91 intermediate build layers. These layers were misclassified as "dangling images". True dangling count is 21 (via `docker image ls -f dangling=true`), not 100.

| Metric | R-5A-R1 Claim | R-5A-R3 Actual |
|---|---|---|
| `docker system df` Images Total | 31 | 31 |
| True dangling images | 100 | **21** |
| Legacy named images | 5 | 5 |
| Active images | 5 | 5 |
| All images incl. intermediate (`docker image ls -a`) | 110 | **122** |
| Intermediate build layers | not distinguished | **91** |
| Build cache entries | 149 | 149 |

### E.2 Strategy Change

| Aspect | R-5B-R2 (old) | R-5B-R3 (current) |
|---|---|---|
| Dangling count | 100 | **21** |
| Removal method | `docker image prune -f` (global) | `docker rmi <ID>` x21 (exact per-ID) |
| ID lock | Diff against 112-ID heredoc | Diff against 21-ID heredoc |
| Risk of removing new images | Present (global prune) | Eliminated (explicit IDs only) |

### E.3 Previous Appendices Status

| Appendix | Status |
|---|---|
| C (R-5B-R1) | Kept for audit trail |
| D (R-5B-R2) | SUPERSEDED_BY_R5B_R3 -- contained wrong ID set (112, not 100 or 21) |
| E (R-5B-R3) | CURRENT -- AUTHORITATIVE |

> **R-5B-R3 COMPLETE. Awaiting CTO approval to proceed to R-5C execution. True counts: 21 dangling + 5 legacy = 26 images to remove via explicit `docker rmi`. No global `docker image prune`.**
