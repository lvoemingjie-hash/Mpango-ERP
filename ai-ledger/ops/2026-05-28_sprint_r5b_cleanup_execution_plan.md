# Sprint R-5B: Cleanup Execution Plan

**Execution Date**: 2026-05-28 14:15 UTC
**Status**: PLAN_ONLY -- AWAITING CTO APPROVAL (R-5B-R2 exact target lock applied)
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

### Phase 2: Dangling Images (100 images)

**Rationale**: Dangling images (`<none>:<none>`) are unreferenced build layers. All verified with `docker ps -a --filter ancestor=<ID>` returning NONE in R-5A-R1. Zero container references. `docker image prune` removes only dangling images -- it cannot touch tagged or active images.

> **Exact Target Lock**: `docker image prune -f` is a Docker-wide operation that removes ALL currently dangling images. If any new dangling images appeared between R-5A-R1 and R-5C, they would also be removed -- potentially exceeding the R-5A-R1 authorization scope. Therefore, R-5C must verify that the current dangling image ID set is an exact match to the R-5A-R1 catalog before executing `docker image prune -f`.

#### Pre-Check (Phase 2)

```bash
# P2-PRE-01: Verify all 5 containers running and healthy
docker ps --format 'table {{.Names}}\t{{.Status}}'

# P2-PRE-02: Record dangling image count (must be 100)
docker images -f "dangling=true" -q | wc -l

# P2-PRE-03: EXACT ID LOCK -- collect current dangling IDs and diff against R-5A-R1 catalog
# Step A: Write the authorized R-5A-R1 dangling image IDs to a reference file on VPS.
# This is the complete set from R-5A-R1 Appendix A sections A.4.1 through A.4.10:
cat > /tmp/r5a_r1_authorized_dangling_ids.txt << 'AUTHORIZED_EOF'
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
43d94af0ab04
8d24c9db4f99
9c7d669566bf
0acc59f7854c
250c3b9b0616
f2c1724d99b2
8f4b534aa888
260d3c6b1288
38de73448d89
bfda92ceae58
1197fc9cc1e9
8bfbb4c27786
c94066a36aad
5a0eaedc974e
813f62cc26d5
dd383cb55634
54003690b6d9
c94e54c50c36
a8a3a618e918
0fc496c615d6
c45949708ea4
dc403688c047
22b36114bdd0
319d261b82f0
10c88a9a1674
1d0100e1ce48
72455b8847bb
444bd1fceb9d
d1a684dc46e9
f45583cac65c
743d8bba937a
9c1f263f3a16
66f141f6bce3
6657bf592a72
d58a9f76353a
bfd1b81c4e5b
867c1e81347b
0ebfd8458b19
bc597e892cb6
1ce84a5f05e6
a248c185462f
1c6e88ea3ae6
e4940490c593
c3f6445fba2c
3c39f110628a
31155d7f306a
85069dc8b37c
c37593ea4c1d
9bd62bb9745c
cb649b08bf63
91d51f432a95
74bcbd45bac7
49339eec7bd5
29d052d1aab2
e923c0c55f1d
3be728897d14
eccdc128546c
77ea8d52aaa4
1419058f2445
307431b5adc5
bf4e1e8a4b0b
cf5d59a64752
089e179ddbe2
2fda947af8ac
322bdf3e0aaa
7ab9ced4e313
b53064b1f50a
09fce7640c0f
55338c78d6d7
abda8436c092
d030960f9d2b
58f8f1a9a61c
984eeb5dc1fe
a996f819a23a
cdded6143ff1
d363a698cfb4
022ba8b8c49a
93b16d243162
7d37d2fd132d
246abb951ad1
a61b4b77381b
e0d5332d3748
4db9b209f19e
3b4f72ce8cab
3e3c0181edd7
3af6bffe4fb8
3d2549d64f00
7b2cf277a4ee
bf2839f295fa
b8ecc4501e86
6c053077a94a
638b97d29a53
94ff3f6866c6
2cbf448a188f
1fe40758005e
1dbac28b010e
52fd62d6da5a
4f1c48272ed0
AUTHORIZED_EOF

# Step B: Collect current dangling IDs on VPS, sort both sets, diff.
docker images -f "dangling=true" -q | sort > /tmp/r5c_current_dangling_ids.txt
sort /tmp/r5a_r1_authorized_dangling_ids.txt > /tmp/r5a_r1_authorized_dangling_ids_sorted.txt

# Step C: Diff -- must show ZERO differences (no output = exact match)
diff /tmp/r5c_current_dangling_ids.txt /tmp/r5a_r1_authorized_dangling_ids_sorted.txt
echo "Diff exit code: $?"
# If exit code != 0: STOP_AND_REPORT_CTO

# P2-PRE-04: Record current Docker space
docker system df

# P2-PRE-05: Record current disk space
df -h /
```

**P2 Pre-Check Pass Criteria** (ALL must pass):
- 5 containers Up/healthy
- Dangling count = 100
- **Exact ID lock: `diff` produces ZERO output and exit code 0** (current dangling IDs are an exact match to R-5A-R1 catalog)
- Disk/Docker space recorded

> **P2 ID Lock Failure**: If `diff` shows any differences (extra IDs = new dangling images appeared; missing IDs = previously dangling images were removed or tagged), the operator must **STOP_AND_REPORT_CTO** with the full diff output. Do NOT execute `docker image prune -f`. New dangling images were NOT part of the R-5A-R1 authorization scope and must not be removed without explicit CTO approval.

#### Execution (Phase 2)

```bash
# P2-EXEC-01: Remove dangling images only
# EXECUTION GATE: This command is authorized ONLY IF P2-PRE-03 exact ID lock diff returned 0 differences.
# If the diff showed any discrepancy, do NOT execute this command.
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
| R-5B commit | `09d5f8b` -- `docs(ops): R-5B cleanup execution plan -- phased commands, rollback checklist, zero execution` |
| R-5B-R1 commit | `82d9522` -- `docs(ops): R-5B-R1 plan safety correction -- STOP_AND_REPORT_CTO, sing-box ps+ss, disk pct fix` |
| R-5B-R2 commit | (this commit) -- `docs(ops): R-5B-R2 exact target lock -- dangling ID diff, build cache active=0 gate` |
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
- Exact cleanup commands (`docker builder prune -f`, `docker image prune -f`, `docker rmi` x5)
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

### D.2 Authorized Dangling Image ID Set

The 100 dangling image IDs below constitute the complete authorized removal set for Phase 2. They were cataloged in R-5A-R1 Appendix A sections A.4.1 through A.4.10 on the canonical India VPS `143.110.177.2`.

```
45955866e977 122a0d4c7867 293b68d1c370 587f897f8071
286acb7e6b9d b95a0bc81cd9 8244f128221f 47e863014dbe
eac6ffa36989 d6515b8ba9ee 909b056c210f dcbfb8239c22
d5f4089faf35 562d9c89a30d 43d94af0ab04 8d24c9db4f99
9c7d669566bf 0acc59f7854c 250c3b9b0616 f2c1724d99b2
8f4b534aa888 260d3c6b1288 38de73448d89 bfda92ceae58
1197fc9cc1e9 8bfbb4c27786 c94066a36aad 5a0eaedc974e
813f62cc26d5 dd383cb55634 54003690b6d9 c94e54c50c36
a8a3a618e918 0fc496c615d6 c45949708ea4 dc403688c047
22b36114bdd0 319d261b82f0 10c88a9a1674 1d0100e1ce48
72455b8847bb 444bd1fceb9d d1a684dc46e9 f45583cac65c
743d8bba937a 9c1f263f3a16 66f141f6bce3 6657bf592a72
d58a9f76353a bfd1b81c4e5b 867c1e81347b 0ebfd8458b19
bc597e892cb6 1ce84a5f05e6 a248c185462f 1c6e88ea3ae6
e4940490c593 c3f6445fba2c 3c39f110628a 31155d7f306a
85069dc8b37c c37593ea4c1d 9bd62bb9745c cb649b08bf63
91d51f432a95 74bcbd45bac7 49339eec7bd5 29d052d1aab2
e923c0c55f1d 3be728897d14 eccdc128546c 77ea8d52aaa4
1419058f2445 307431b5adc5 bf4e1e8a4b0b cf5d59a64752
089e179ddbe2 2fda947af8ac 322bdf3e0aaa 7ab9ced4e313
b53064b1f50a 09fce7640c0f 55338c78d6d7 abda8436c092
d030960f9d2b 58f8f1a9a61c 984eeb5dc1fe a996f819a23a
cdded6143ff1 d363a698cfb4 022ba8b8c49a 93b16d243162
7d37d2fd132d 246abb951ad1 a61b4b77381b e0d5332d3748
4db9b209f19e 3b4f72ce8cab 3e3c0181edd7 3af6bffe4fb8
3d2549d64f00 7b2cf277a4ee bf2839f295fa b8ecc4501e86
6c053077a94a 638b97d29a53 94ff3f6866c6 2cbf448a188f
1fe40758005e 1dbac28b010e 52fd62d6da5a 4f1c48272ed0
```

### D.3 Remaining Unchanged

- Phase 1 execution command (`docker builder prune -f`)
- Phase 3 execution commands (`docker rmi` x5 by explicit ID -- already exact-target by design)
- All post-check commands
- STOP_AND_REPORT_CTO failure policy
- PROTECTED resource list
- Three-phase execution order

> **R-5B-R2 COMPLETE (exact target lock). Awaiting CTO approval to proceed to R-5C execution.**
