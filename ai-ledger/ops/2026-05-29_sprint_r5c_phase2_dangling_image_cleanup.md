# Sprint R-5C Phase 2: Dangling Image Cleanup (21 Images) -- Audit Evidence

**Execution Date**: 2026-05-29 21:49 - 21:50 UTC
**Status**: PHASE_2_COMPLETE -- PHASE_3_FROZEN
**Target**: Canonical India VPS `143.110.177.2` (`ubuntu-s-1vcpu-1gb-blr1-01`)
**Preceding Gate**: R-5C Phase 1 (`0f243d5`, pushed to origin) -- CTO approved R-5C Phase 2 only
**CTO Approval**: Explicit approval given 2026-05-30. Phase 3 explicitly NOT approved.

> **CRITICAL**: This document is the audit evidence for R-5C Phase 2. Only `docker rmi <ID>` x21 was executed. No global prune. No legacy images removed. Phase 3 remains frozen.

---

## 1. Commands NOT Executed (Forbidden List)

The following commands were NOT executed during R-5C Phase 2:

- `docker image prune -f` -- FORBIDDEN (explicitly prohibited by R-5B-R4)
- `docker rmi` for any of the 5 legacy named images -- FORBIDDEN (Phase 3 not approved)
- `docker stop` / `docker rm` -- FORBIDDEN (containers are PROTECTED)
- `docker volume rm` -- FORBIDDEN (volumes are PROTECTED)
- `docker compose up` -- FORBIDDEN (deployment command)
- `git pull` -- FORBIDDEN (deployment command)
- `alembic` -- FORBIDDEN (deployment command)
- `.env` read -- FORBIDDEN (secrets not accessed)

## 2. Commands Executed (Authorized)

| # | Command | Result |
|---|---|---|
| Pre-checks | Hostname, containers, sing-box, port 80, backup, disk, docker system df | All PASS |
| ID lock | `comm -3 <(current dangling) <(authorized 21 IDs)>` | 0 lines (identical) |
| P2-EXEC-01 | `docker rmi 45955866e977` | Deleted. Exit 0 |
| P2-EXEC-02 | `docker rmi 122a0d4c7867` | Deleted. Exit 0 |
| P2-EXEC-03 | `docker rmi 293b68d1c370` | Deleted. Exit 0 |
| P2-EXEC-04 | `docker rmi 587f897f8071` | Deleted. Exit 0 |
| P2-EXEC-05 | `docker rmi 286acb7e6b9d` | Deleted. Exit 0 |
| P2-EXEC-06 | `docker rmi b95a0bc81cd9` | Deleted. Exit 0 |
| P2-EXEC-07 | `docker rmi 8244f128221f` | Deleted. Exit 0 |
| P2-EXEC-08 | `docker rmi 47e863014dbe` | Deleted. Exit 0 |
| P2-EXEC-09 | `docker rmi eac6ffa36989` | Deleted. Exit 0 |
| P2-EXEC-10 | `docker rmi d6515b8ba9ee` | Deleted. Exit 0 |
| P2-EXEC-11 | `docker rmi 909b056c210f` | Deleted. Exit 0 |
| P2-EXEC-12 | `docker rmi dcbfb8239c22` | Deleted. Exit 0 |
| P2-EXEC-13 | `docker rmi d5f4089faf35` | Deleted. Exit 0 |
| P2-EXEC-14 | `docker rmi 562d9c89a30d` | Deleted. Exit 0 |
| P2-EXEC-15 | `docker rmi 0fc496c615d6` | Deleted + 11 cascaded layers. Exit 0 |
| P2-EXEC-16 | `docker rmi f45583cac65c` | Deleted + 15 cascaded layers. Exit 0 |
| P2-EXEC-17 | `docker rmi c3f6445fba2c` | Deleted + multiple cascaded layers. Exit 0 |
| P2-EXEC-18 | `docker rmi e923c0c55f1d` | Deleted + multiple cascaded layers. Exit 0 |
| P2-EXEC-19 | `docker rmi 322bdf3e0aaa` | Deleted + multiple cascaded layers. Exit 0 |
| P2-EXEC-20 | `docker rmi d363a698cfb4` | Deleted + multiple cascaded layers. Exit 0 |
| P2-EXEC-21 | `docker rmi b8ecc4501e86` | Deleted + 16 cascaded layers. Exit 0 |
| Post-checks | Containers, sing-box, port 80, backup, disk, docker system df, dangling count | All PASS |

**Total cleanup commands executed**: 21 (`docker rmi` x21)
**Total exit code failures**: 0
**Fail-closed rule**: Never triggered (all 21 succeeded)

> **Note on cascaded deletions**: Several `docker rmi` commands removed additional intermediate build layers beyond the single target ID. This is expected Docker behavior: when a dangling image is removed, any intermediate layers that were parents of that image and have no other children are automatically garbage-collected. This is why the total number of `Deleted:` lines exceeds 21.

---

## 3. Pre-Check Evidence

### P2-PRE-01: Hostname

```
ubuntu-s-1vcpu-1gb-blr1-01
```

**Result**: Matches canonical VPS. PASS.

### P2-PRE-02: Container Health

```
NAMES                  STATUS
mpango_prod_gateway    Up 2 months (healthy)
mpango_prod_backend    Up 2 months (healthy)
mpango_prod_frontend   Up 2 months (healthy)
mpango_prod_postgres   Up 2 months (healthy)
mpango_prod_redis      Up 2 months (healthy)
```

**Result**: All 5 containers Up and healthy. PASS.

### P2-PRE-03: Exact ID Lock

Authorized IDs (from R-5A-R3 Appendix E.3.3): 21 IDs written to `/tmp/r5a_r3_authorized_dangling_ids.txt`.

```
Authorized count: 21
Current dangling count: 21
Symmetric diff (comm -3): 0 lines
```

**Result**: Current dangling IDs are IDENTICAL to authorized set. Zero discrepancy. PASS.

### P2-PRE-04: sing-box Process and Port 443

```
sing-box  132529  0.1  2.5 1273184 24524 ?  Ssl  2025 402:19  /usr/bin/sing-box ...
LISTEN 0  4096  *:443  *:*  users:(("sing-box",pid=132529,fd=7))
```

**Result**: sing-box running, :443 LISTEN. PASS.

### P2-PRE-05: Port 80

```
HTTP 200
```

**Result**: PASS.

### P2-PRE-06: R-4B Backup File

```
-rw------- 1 root root 10967 May 26 22:38 /root/mpango-backups/mpango_erp_20260527_063830.sql.gz
```

**Result**: PASS.

### P2-PRE-07: Disk and Docker Space Baseline

```
Filesystem      Size  Used Avail Use%  Mounted on
/dev/vda1       25G   17G   7.2G  71%  /

TYPE            TOTAL     ACTIVE    SIZE      RECLAIMABLE
Images          31        5         9.992GB   9.663GB (96%)
Containers      5         5         2.725kB   0B (0%)
Local Volumes   4         2         115MB     48.18MB (41%)
Build Cache     103       0         0B        0B
```

**Result**: 7.2 GB free, Images 31 (5 active + 5 legacy + 21 dangling). Recorded.

---

## 4. Execution Evidence

### P2-EXEC: `docker rmi` x21 (Individual Commands)

**Start time**: 2026-05-29T21:49:53Z
**End time**: 2026-05-29T21:50:26Z
**Duration**: ~33 seconds

| # | Image ID | Exit Code | Cascaded Layers |
|---|---|---|---|
| 1 | `45955866e977` | 0 | 0 extra |
| 2 | `122a0d4c7867` | 0 | 0 extra |
| 3 | `293b68d1c370` | 0 | 0 extra |
| 4 | `587f897f8071` | 0 | 0 extra |
| 5 | `286acb7e6b9d` | 0 | 0 extra |
| 6 | `b95a0bc81cd9` | 0 | 0 extra |
| 7 | `8244f128221f` | 0 | 0 extra |
| 8 | `47e863014dbe` | 0 | 0 extra |
| 9 | `eac6ffa36989` | 0 | 0 extra |
| 10 | `d6515b8ba9ee` | 0 | 0 extra |
| 11 | `909b056c210f` | 0 | 0 extra |
| 12 | `dcbfb8239c22` | 0 | 0 extra |
| 13 | `d5f4089faf35` | 0 | 0 extra |
| 14 | `562d9c89a30d` | 0 | 0 extra |
| 15 | `0fc496c615d6` | 0 | 11 cascaded |
| 16 | `f45583cac65c` | 0 | 15 cascaded |
| 17 | `c3f6445fba2c` | 0 | multiple cascaded |
| 18 | `e923c0c55f1d` | 0 | multiple cascaded |
| 19 | `322bdf3e0aaa` | 0 | multiple cascaded |
| 20 | `d363a698cfb4` | 0 | multiple cascaded |
| 21 | `b8ecc4501e86` | 0 | 16 cascaded |

**Total**: 21/21 succeeded. 0 failures. Fail-closed rule never triggered.

---

## 5. Post-Check Evidence

### P2-POST-01: Container Health

```
NAMES                  STATUS
mpango_prod_gateway    Up 2 months (healthy)
mpango_prod_backend    Up 2 months (healthy)
mpango_prod_frontend   Up 2 months (healthy)
mpango_prod_postgres   Up 2 months (healthy)
mpango_prod_redis      Up 2 months (healthy)
```

**Result**: All 5 containers Up and healthy. Unchanged. PASS.

### P2-POST-02: sing-box Process

```
sing-box  132529  0.1  1.9 1273184 18776 ?  Ssl  2025 402:19  /usr/bin/sing-box ...
```

**Result**: sing-box process running. Unchanged. PASS.

### P2-POST-03: Port 443 Listener

```
LISTEN 0  4096  *:443  *:*  users:(("sing-box",pid=132529,fd=7))
```

**Result**: Port 443 LISTEN. Unchanged. PASS.

### P2-POST-04: Port 80 HTTP Check

```
HTTP 200
```

**Result**: Unchanged. PASS.

### P2-POST-05: R-4B Backup File

```
-rw------- 1 root root 10967 May 26 22:38 /root/mpango-backups/mpango_erp_20260527_063830.sql.gz
```

**Result**: Unchanged. PASS.

### P2-POST-06: Disk Space

```
Filesystem      Size  Used Avail Use%  Mounted on
/dev/vda1       25G   13G   12G   53%  /
```

**Result**: 12 GB free (up from 7.2 GB). +4.8 GB reclaimed. Use% down from 71% to 53%. PASS.

### P2-POST-07: Docker System Space

```
TYPE            TOTAL     ACTIVE    SIZE      RECLAIMABLE
Images          10        5         2.679GB   1.868GB (69%)
Containers      5         5         2.725kB   0B (0%)
Local Volumes   4         2         115MB     48.18MB (41%)
Build Cache     103       0         3.486GB   3.486GB
```

**Result**:
- Images: 10 (down from 31). 5 active + 5 legacy. 0 dangling.
- Image space: 2.679 GB (down from 9.992 GB). 1.868 GB reclaimable (the 5 legacy images).
- PASS.

### P2-POST-08: Dangling Image Count

```
0
```

**Result**: Zero dangling images remain. PASS.

### P2-POST-09: Active Images Present

```
mpango-erp-backend:latest    aa7d810494f6   619MB
mpango-erp-frontend:latest   1e0a7c9d2cc6   62.6MB
nginx:alpine                 b76de378d572   62.1MB
postgres:15                  7064d8f3d970   444MB
postgres:15-alpine           36a937f48ac7   274MB
redis:7-alpine               13105d2858de   41.4MB
```

**Result**: All 5 active images present (plus postgres:15 shared with legacy). PASS.

### P2-POST-10: Legacy Images (Phase 3 Not Executed)

```
app_backend:latest     eaacea1cbf22   998MB
app_frontend:latest    6c19708eb35c   443MB
node:18-alpine         ee77c6cd7c18   127MB
postgres:15            7064d8f3d970   444MB
python:3.11-slim       fa659464a114   124MB
```

**Result**: All 5 legacy images still present. Phase 3 not executed. As expected.

---

## 6. Reclamation Summary

| Metric | Before Phase 2 | After Phase 2 | Delta |
|---|---|---|---|
| Dangling images | 21 | **0** | **-21** |
| Total images (top-level) | 31 | **10** | -21 |
| Docker image space | 9.992 GB | **2.679 GB** | **-7.313 GB** |
| Docker image reclaimable | 9.663 GB (96%) | 1.868 GB (69%) | -7.795 GB (legacy remaining) |
| Disk free | 7.2 GB (71%) | **12 GB (53%)** | **+4.8 GB** |
| Containers | 5 healthy | 5 healthy | unchanged |
| sing-box / :443 | OK | OK | unchanged |
| Port 80 | HTTP 200 | HTTP 200 | unchanged |
| Backup file | 10967 bytes | 10967 bytes | unchanged |
| Legacy images | 5 | 5 | unchanged (Phase 3 frozen) |

> **Note**: Docker reports 3.486 GB build cache (up from 0B after Phase 1). This is expected: removing dangling images exposed previously hidden build cache entries that were sharing layers with the now-removed dangling images. These are safe to prune in a future cycle if needed, but are NOT in R-5C scope.

---

## 7. R-5C Phase 2 Confirmation

- **Only cleanup commands executed**: `docker rmi <ID>` x21 (exact authorized IDs only)
- **No `docker image prune -f`**: NOT executed
- **No legacy image removal**: 5 legacy images untouched (Phase 3 not approved)
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
- **Fail-closed rule**: All 21 `docker rmi` returned exit 0; rule never triggered
- **Exact ID lock**: Pre-check confirmed 21 current IDs = 21 authorized IDs (zero diff)

---

## 8. Phase 3 Status

**FROZEN**. CTO has NOT approved Phase 3. No legacy image removal commands will be executed until CTO explicitly approves.

Remaining reclaimable (5 legacy named images):
| # | Image ID | Repository:Tag | Size |
|---|---|---|---|
| 1 | `eaacea1cbf22` | `app_backend:latest` | 998 MB |
| 2 | `6c19708eb35c` | `app_frontend:latest` | 443 MB |
| 3 | `fa659464a114` | `python:3.11-slim` | 124 MB |
| 4 | `7064d8f3d970` | `postgres:15` | 444 MB |
| 5 | `ee77c6cd7c18` | `node:18-alpine` | 127 MB |

Plus newly exposed build cache: 3.486 GB (not in R-5C scope).

---

## 9. Cumulative R-5C Results (Phase 1 + Phase 2)

| Metric | Before R-5C | After Phase 1 + 2 | Total Delta |
|---|---|---|---|
| Disk free | 6.0 GB (76%) | **12 GB (53%)** | **+6.0 GB** |
| Build cache reclaimed | 945.4 MB | 945.4 MB | -945.4 MB |
| Images removed | 0 | 21 dangling + cascaded layers | -21 images |
| Docker image space | 9.992 GB | 2.679 GB | -7.313 GB |

---

## 10. Git Commit (R-5C Phase 2)

| Item | Value |
|---|---|
| Repo | `phase6-closeout-promotion-2026-05-15` |
| Branch | `ops/sprint-r2-vps-script-recovery-2026-05-25` |
| Commit message | `docs(ops): R-5C Phase 2 dangling image cleanup -- 21 rmi executed, 0 dangling remain, +4.8 GB disk freed` |
| Files changed | New: `ai-ledger/ops/2026-05-29_sprint_r5c_phase2_dangling_image_cleanup.md` |
| Push | **No** -- awaiting CTO review |
