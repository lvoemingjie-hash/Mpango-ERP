# Sprint R-5C Phase 3: Legacy Named Image Cleanup (5 Images) -- Audit Evidence

**Execution Date**: 2026-05-29 22:06 UTC
**Status**: PHASE_3_COMPLETE -- R-5C CLEANUP FINISHED
**Target**: Canonical India VPS `143.110.177.2` (`ubuntu-s-1vcpu-1gb-blr1-01`)
**Preceding Gate**: R-5D (`a28f901`, pushed to origin) -- CTO approved Phase 3 after reclassification confirmed all 5 SAFE_TO_REMOVE
**CTO Approval**: Explicit approval given 2026-05-30.

> **CRITICAL**: This document is the audit evidence for R-5C Phase 3 -- the FINAL phase of R-5 cleanup. Only `docker rmi <ID>` x5 was executed. No global prune. R-5C is now complete.

---

## 1. Commands NOT Executed (Forbidden List)

The following commands were NOT executed during R-5C Phase 3:

- `docker image prune -f` -- FORBIDDEN (explicitly prohibited)
- `docker builder prune` -- FORBIDDEN (Phase 1 only, already completed)
- `docker stop` / `docker rm` -- FORBIDDEN (containers are PROTECTED)
- `docker volume rm` -- FORBIDDEN (volumes are PROTECTED)
- `docker compose up` -- FORBIDDEN (deployment command)
- `git pull` -- FORBIDDEN (deployment command)
- `alembic` -- FORBIDDEN (deployment command)
- `.env` read -- FORBIDDEN (secrets not accessed)

## 2. Commands Executed (Authorized)

| # | Command | Result |
|---|---|---|
| Pre-checks | Hostname, containers, sing-box, port 80, backup, disk, docker system df, legacy container refs | All PASS |
| P3-EXEC-01 | `docker rmi eaacea1cbf22` | Untagged + Deleted (20 layers). Exit 0 |
| P3-EXEC-02 | `docker rmi 6c19708eb35c` | Untagged + Deleted (17 layers). Exit 0 |
| P3-EXEC-03 | `docker rmi fa659464a114` | Untagged + Deleted. Exit 0 |
| P3-EXEC-04 | `docker rmi 7064d8f3d970` | Untagged + Deleted (14 layers). Exit 0 |
| P3-EXEC-05 | `docker rmi ee77c6cd7c18` | Untagged + Deleted. Exit 0 |
| Post-checks | Containers, sing-box, port 80, backup, disk, docker system df, images, dangling | All PASS |

**Total cleanup commands executed**: 5 (`docker rmi` x5)
**Total exit code failures**: 0
**Fail-closed rule**: Never triggered (all 5 succeeded)

---

## 3. Pre-Check Evidence

### P3-PRE-01: Hostname

```
ubuntu-s-1vcpu-1gb-blr1-01
```

**Result**: Matches canonical VPS. PASS.

### P3-PRE-02: Container Health

```
NAMES                  STATUS
mpango_prod_gateway    Up 2 months (healthy)
mpango_prod_backend    Up 2 months (healthy)
mpango_prod_frontend   Up 2 months (healthy)
mpango_prod_postgres   Up 2 months (healthy)
mpango_prod_redis      Up 2 months (healthy)
```

**Result**: All 5 containers Up and healthy. PASS.

### P3-PRE-03: Legacy Image Container References

```
-- eaacea1cbf22 -- (empty)
-- 6c19708eb35c -- (empty)
-- fa659464a114 -- (empty)
-- 7064d8f3d970 -- (empty)
-- ee77c6cd7c18 -- (empty)
```

**Result**: All 5 legacy images have ZERO container references. Consistent with R-5D findings. PASS.

### P3-PRE-04: sing-box Process and Port 443

```
sing-box  132529  0.1  2.1 1273184 21424 ?  Ssl  2025 402:21  /usr/bin/sing-box ...
LISTEN 0  4096  *:443  *:*  users:(("sing-box",pid=132529,fd=7))
```

**Result**: PASS.

### P3-PRE-05: Port 80 and R-4B Backup

```
HTTP 200
-rw------- 1 root root 10967 May 26 22:38 /root/mpango-backups/mpango_erp_20260527_063830.sql.gz
```

**Result**: PASS.

### P3-PRE-06: Disk and Docker Space Baseline

```
Filesystem      Size  Used Avail Use%  Mounted on
/dev/vda1       25G   13G   12G   53%  /

TYPE            TOTAL     ACTIVE    SIZE      RECLAIMABLE
Images          10        5         2.679GB   1.868GB (69%)
Containers      5         5         2.725kB   0B (0%)
Local Volumes   4         2         115MB     48.18MB (41%)
Build Cache     103       0         3.486GB   3.486GB
```

**Result**: 12 GB free, Images 10 (5 active + 5 legacy). Recorded.

---

## 4. Execution Evidence

### P3-EXEC: `docker rmi` x5 (Individual Commands)

**Start time**: 2026-05-29T22:06:40Z
**End time**: 2026-05-29T22:06:43Z
**Duration**: ~3 seconds

| # | Image ID | Tag | Exit Code | Layers Removed |
|---|---|---|---|---|
| 1 | `eaacea1cbf22` | `app_backend:latest` | 0 | 1 untagged + 20 deleted |
| 2 | `6c19708eb35c` | `app_frontend:latest` | 0 | 1 untagged + 17 deleted |
| 3 | `fa659464a114` | `python:3.11-slim` | 0 | 2 untagged (incl. digest) + 1 deleted |
| 4 | `7064d8f3d970` | `postgres:15` | 0 | 2 untagged (incl. digest) + 14 deleted |
| 5 | `ee77c6cd7c18` | `node:18-alpine` | 0 | 2 untagged (incl. digest) + 1 deleted |

**Total**: 5/5 succeeded. 0 failures. Fail-closed rule never triggered.

---

## 5. Post-Check Evidence

### P3-POST-01: Container Health

```
NAMES                  STATUS
mpango_prod_gateway    Up 2 months (healthy)
mpango_prod_backend    Up 2 months (healthy)
mpango_prod_frontend   Up 2 months (healthy)
mpango_prod_postgres   Up 2 months (healthy)
mpango_prod_redis      Up 2 months (healthy)
```

**Result**: All 5 containers Up and healthy. Unchanged. PASS.

### P3-POST-02: sing-box Process and Port 443

```
sing-box  132529  0.1  2.1 1273184 20780 ?  Ssl  2025 402:21  /usr/bin/sing-box ...
LISTEN 0  4096  *:443  *:*  users:(("sing-box",pid=132529,fd=7))
```

**Result**: Unchanged. PASS.

### P3-POST-03: Port 80 HTTP Check

```
HTTP 200
```

**Result**: Unchanged. PASS.

### P3-POST-04: R-4B Backup File

```
-rw------- 1 root root 10967 May 26 22:38 /root/mpango-backups/mpango_erp_20260527_063830.sql.gz
```

**Result**: Unchanged. PASS.

### P3-POST-05: Disk Space

```
Filesystem      Size  Used Avail Use%  Mounted on
/dev/vda1       25G   12G   13G   46%  /
```

**Result**: 13 GB free (up from 12 GB). +1 GB. Use% down from 53% to 46%. PASS.

### P3-POST-06: Docker System Space

```
TYPE            TOTAL     ACTIVE    SIZE      RECLAIMABLE
Images          5         5         997MB     62.12MB (6%)
Containers      5         5         2.725kB   0B (0%)
Local Volumes   4         2         115MB     48.18MB (41%)
Build Cache     103       0         3.486GB   3.486GB
```

**Result**:
- Images: 5 (down from 10). All 5 are active. Reclaimable down from 1.868 GB to 62 MB.
- PASS.

### P3-POST-07: Dangling Image Count

```
0
```

**Result**: Zero dangling. PASS.

### P3-POST-08: Total Image Count

```
5
```

**Result**: Exactly 5 images remain (all active). PASS.

### P3-POST-09: Full Image List

```
mpango-erp-backend:latest    aa7d810494f6   619MB
mpango-erp-frontend:latest   1e0a7c9d2cc6   62.6MB
nginx:alpine                 b76de378d572   62.1MB
postgres:15-alpine           36a937f48ac7   274MB
redis:7-alpine               13105d2858de   41.4MB
```

**Result**: Only the 5 active production images remain. PASS.

### P3-POST-10: Legacy Image Check

```
NO LEGACY IMAGES FOUND
```

**Result**: All legacy images removed. PASS.

---

## 6. Reclamation Summary

| Metric | Before Phase 3 | After Phase 3 | Delta |
|---|---|---|---|
| Legacy images | 5 | **0** | -5 |
| Total images | 10 | **5** | -5 |
| Docker image space | 2.679 GB | **997 MB** | **-1.682 GB** |
| Docker image reclaimable | 1.868 GB (69%) | 62 MB (6%) | nearly zero |
| Disk free | 12 GB (53%) | **13 GB (46%)** | **+1 GB** |
| Containers | 5 healthy | 5 healthy | unchanged |
| sing-box / :443 | OK | OK | unchanged |
| Port 80 | HTTP 200 | HTTP 200 | unchanged |
| Backup file | intact | intact | unchanged |

---

## 7. R-5C Phase 3 Confirmation

- **Only cleanup commands executed**: `docker rmi <ID>` x5 (exact authorized IDs only)
- **No `docker image prune -f`**: NOT executed
- **No `docker builder prune`**: NOT executed (Phase 1 only, already completed)
- **No containers stopped/restarted**: All 5 remained Up healthy throughout
- **No `docker stop/rm`**: NOT executed
- **No `docker volume rm`**: NOT executed
- **No `docker compose up`**: NOT executed
- **No `git pull`**: NOT executed
- **No `alembic`**: NOT executed
- **No `.env` read**: NOT accessed
- **sing-box untouched**: Process and port 443 unchanged
- **Backup file untouched**: File unchanged
- **Port 80 responding**: Before and after HTTP 200
- **Fail-closed rule**: All 5 `docker rmi` returned exit 0; rule never triggered

---

## 8. R-5C Complete Summary (All 3 Phases)

| Metric | Before R-5C | After R-5C | Total Delta |
|---|---|---|---|
| Disk free | 6.0 GB (76%) | **13 GB (46%)** | **+7.0 GB** |
| Disk use% | 76% | **46%** | -30% |
| Images total | 31 | **5** | -26 removed |
| Active images | 5 | **5** | unchanged |
| Dangling images | 21 | **0** | -21 |
| Legacy images | 5 | **0** | -5 |
| Build cache | 945.4 MB | 0B (cleaned) + 3.486 GB (newly exposed) | Phase 1: -945.4 MB |
| Docker image space | 9.992 GB | **997 MB** | **-9.0 GB** |
| Docker image reclaimable | 9.663 GB (96%) | **62 MB (6%)** | nearly zero |

### Phase-by-Phase Reclamation

| Phase | Target | Space Freed | Disk Delta |
|---|---|---|---|
| Phase 1: Build Cache | 149 entries | 945.4 MB | +1.2 GB |
| Phase 2: Dangling Images | 21 images | 7.313 GB (image space) | +4.8 GB |
| Phase 3: Legacy Named | 5 images | 1.682 GB (image space) | +1.0 GB |
| **Total** | **26 images + 149 cache** | **~10 GB Docker** | **+7.0 GB disk** |

### Services Status (Unchanged Throughout All 3 Phases)

| Service | Status |
|---|---|
| `mpango_prod_backend` | Up 2 months (healthy) |
| `mpango_prod_frontend` | Up 2 months (healthy) |
| `mpango_prod_gateway` | Up 2 months (healthy) |
| `mpango_prod_postgres` | Up 2 months (healthy) |
| `mpango_prod_redis` | Up 2 months (healthy) |
| sing-box (port 443) | Running, LISTEN |
| Port 80 (nginx) | HTTP 200 |
| R-4B backup file | Intact (10967 bytes) |
| All 4 volumes | Intact |
| All 4 networks | Intact |

---

## 9. Post-R-5C VPS State

### Remaining Images (5 -- All Active)

| Image | ID | Size | Container |
|---|---|---|---|
| `mpango-erp-backend:latest` | `aa7d810494f6` | 619 MB | `mpango_prod_backend` |
| `mpango-erp-frontend:latest` | `1e0a7c9d2cc6` | 62.6 MB | `mpango_prod_frontend` |
| `nginx:alpine` | `b76de378d572` | 62.1 MB | `mpango_prod_gateway` |
| `postgres:15-alpine` | `36a937f48ac7` | 274 MB | `mpango_prod_postgres` |
| `redis:7-alpine` | `13105d2858de` | 41.4 MB | `mpango_prod_redis` |

### Known Remaining Reclaimable (Not in R-5C Scope)

- Build cache: 3.486 GB (exposed after Phase 2 layer removals). Can be pruned in future cycle.
- Volume `app_postgres_data` + `app_redis_data`: 48.18 MB (legacy data, PROTECTED).
- Docker image reclaimable: 62 MB (shared layer fragments).

---

## 10. Git Commit (R-5C Phase 3)

| Item | Value |
|---|---|
| Repo | `phase6-closeout-promotion-2026-05-15` |
| Branch | `ops/sprint-r2-vps-script-recovery-2026-05-25` |
| Commit message | `docs(ops): R-5C Phase 3 legacy image cleanup -- 5 rmi executed, 0 legacy remain, +1 GB disk, R-5C COMPLETE` |
| Files changed | New: `ai-ledger/ops/2026-05-30_sprint_r5c_phase3_legacy_image_cleanup.md` |
| Push | **No** -- awaiting CTO review |
