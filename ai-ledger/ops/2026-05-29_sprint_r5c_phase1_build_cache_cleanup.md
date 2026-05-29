# Sprint R-5C Phase 1: Build Cache Cleanup -- Audit Evidence

**Execution Date**: 2026-05-29 14:08 UTC
**Status**: PHASE_1_COMPLETE -- PHASE_2_3_FROZEN
**Target**: Canonical India VPS `143.110.177.2` (`ubuntu-s-1vcpu-1gb-blr1-01`)
**Preceding Gate**: R-5B-R4 (`b65adc9`, pushed to origin) -- CTO approved R-5C Phase 1 only
**CTO Approval**: Explicit approval given 2026-05-29. Phase 2/3 explicitly NOT approved.

> **CRITICAL**: This document is the audit evidence for R-5C Phase 1. Only ONE cleanup command was executed: `docker builder prune -f`. No images were removed. Phase 2/3 remain frozen.

---

## 1. Commands NOT Executed (Forbidden List)

The following commands were NOT executed during R-5C Phase 1:

- `docker image prune -f` -- FORBIDDEN (not authorized in Phase 1)
- `docker rmi` (any ID) -- FORBIDDEN (not authorized in Phase 1)
- `docker stop` / `docker rm` -- FORBIDDEN (containers are PROTECTED)
- `docker volume rm` -- FORBIDDEN (volumes are PROTECTED)
- `docker compose up` -- FORBIDDEN (deployment command)
- `git pull` -- FORBIDDEN (deployment command)
- `alembic` -- FORBIDDEN (deployment command)
- `.env` read -- FORBIDDEN (secrets not accessed)

## 2. Commands Executed (Authorized)

| # | Command | Authorized By | Purpose |
|---|---|---|---|
| 1 | `ssh root@143.110.177.2 hostname` | R-5B plan, CTO approval | Verify target identity |
| 2 | `docker ps --format ...` | P1-PRE-01 | Container health check |
| 3 | `ps aux \| grep sing-box` | P1-PRE-02 | sing-box process check |
| 4 | `ss -ltnp \| grep ':443'` | P1-PRE-02 | Port 443 listener check |
| 5 | `curl ... http://143.110.177.2:80/` | P1-PRE-03 | Port 80 HTTP check |
| 6 | `ls -la /root/mpango-backups/...` | R-5B plan | Backup file integrity |
| 7 | `docker system df` / `docker system df -v` | P1-PRE-04 | Docker space baseline |
| 8 | `df -h /` | P1-PRE-03 | Disk space baseline |
| 9 | **`docker builder prune -f`** | **P1-EXEC-01** | **ONLY cleanup command executed** |
| 10-17 | Post-checks (same as 2-8) | P1-POST-01 through P1-POST-06 | Verify no damage |

**Total cleanup commands executed**: 1 (`docker builder prune -f`)

---

## 3. Pre-Check Evidence

### P1-PRE-01: Container Health

```
NAMES                  STATUS
mpango_prod_gateway    Up 2 months (healthy)
mpango_prod_backend    Up 2 months (healthy)
mpango_prod_frontend   Up 2 months (healthy)
mpango_prod_postgres   Up 2 months (healthy)
mpango_prod_redis      Up 2 months (healthy)
```

**Result**: All 5 containers Up and healthy. PASS.

### P1-PRE-02: sing-box Process and Port 443

```
sing-box  132529  0.1  2.0 1273184 20368 ?  Ssl  2025 401:09  /usr/bin/sing-box -D /var/lib/sing-box -C /etc/sing-box run
```

```
LISTEN 0  4096  *:443  *:*  users:(("sing-box",pid=132529,fd=7))
```

**Result**: sing-box process running (PID 132529), port 443 LISTEN. PASS.

### P1-PRE-03: Port 80 HTTP Check

```
HTTP response code: 200
```

**Result**: Port 80 responding. PASS.

### P1-PRE-04: R-4B Backup File

```
-rw------- 1 root root 10967 May 26 22:38 /root/mpango-backups/mpango_erp_20260527_063830.sql.gz
```

**Result**: Backup file exists, 10967 bytes, owned by root. PASS.

### P1-PRE-05: Build Cache Active = 0

```
TYPE            TOTAL     ACTIVE    SIZE      RECLAIMABLE
Images          31        5         9.992GB   9.663GB (96%)
Containers      5         5         2.725kB   0B (0%)
Local Volumes   4         2         115MB     48.18MB (41%)
Build Cache     149       0         945.4MB   945.4MB
```

**Result**: Build Cache Active = 0, 149 entries, 945.4 MB reclaimable. PASS.

### P1-PRE-06: Disk Space Baseline

```
Filesystem      Size  Used Avail Use%  Mounted on
/dev/vda1       25G   19G   6.0G  76%  /
```

**Result**: 6.0 GB free / 25 GB (76% used). Recorded.

---

## 4. Execution Evidence

### P1-EXEC-01: `docker builder prune -f`

- **Start time**: 2026-05-29T14:08:00Z
- **End time**: 2026-05-29T14:08:12Z
- **Duration**: ~12 seconds
- **Exit code**: 0

```
Total reclaimed space: 945.4MB
```

46 cache entries removed. 103 zero-byte metadata entries remain (0B, no space consumed).

**Result**: 945.4 MB reclaimed. Matches R-5B plan expected value exactly.

---

## 5. Post-Check Evidence

### P1-POST-01: Container Health

```
NAMES                  STATUS
mpango_prod_gateway    Up 2 months (healthy)
mpango_prod_backend    Up 2 months (healthy)
mpango_prod_frontend   Up 2 months (healthy)
mpango_prod_postgres   Up 2 months (healthy)
mpango_prod_redis      Up 2 months (healthy)
```

**Result**: All 5 containers Up and healthy. Unchanged from pre-check. PASS.

### P1-POST-02: sing-box Process

```
sing-box  132529  0.1  1.6 1273184 16048 ?  Ssl  2025 401:09  /usr/bin/sing-box -D /var/lib/sing-box -C /etc/sing-box run
```

**Result**: sing-box process running. Unchanged. PASS.

### P1-POST-03: Port 443 Listener

```
LISTEN 0  4096  *:443  *:*  users:(("sing-box",pid=132529,fd=7))
```

**Result**: Port 443 LISTEN. Unchanged. PASS.

### P1-POST-04: Port 80 HTTP Check

```
HTTP response code: 200
```

**Result**: Port 80 responding. Unchanged. PASS.

### P1-POST-05: R-4B Backup File

```
-rw------- 1 root root 10967 May 26 22:38 /root/mpango-backups/mpango_erp_20260527_063830.sql.gz
```

**Result**: Backup file unchanged. PASS.

### P1-POST-06: Disk Space

```
Filesystem      Size  Used Avail Use%  Mounted on
/dev/vda1       25G   17G   7.2G  71%  /
```

**Result**: 7.2 GB free (up from 6.0 GB). +1.2 GB reclaimed. Use% down from 76% to 71%. PASS.

### P1-POST-07: Docker System Space

```
TYPE            TOTAL     ACTIVE    SIZE      RECLAIMABLE
Images          31        5         9.992GB   9.663GB (96%)
Containers      5         5         2.725kB   0B (0%)
Local Volumes   4         2         115MB     48.18MB (41%)
Build Cache     103       0         0B        0B
```

**Result**:
- Images: 31 unchanged. No images removed. 9.663 GB still reclaimable.
- Containers: 5 unchanged.
- Volumes: 4 unchanged.
- Build Cache: 103 entries, 0B (down from 149 entries, 945.4 MB). 46 entries removed, 945.4 MB freed.
- PASS.

---

## 6. Reclamation Summary

| Metric | Before | After | Delta |
|---|---|---|---|
| Build Cache entries | 149 | 103 | -46 |
| Build Cache size | 945.4 MB | 0B | **-945.4 MB** |
| Disk free | 6.0 GB | 7.2 GB | **+1.2 GB** |
| Disk use% | 76% | 71% | -5% |
| Images total | 31 | 31 | 0 (unchanged) |
| Containers | 5 healthy | 5 healthy | 0 (unchanged) |
| sing-box | PID 132529, :443 LISTEN | PID 132529, :443 LISTEN | 0 (unchanged) |
| Port 80 | HTTP 200 | HTTP 200 | 0 (unchanged) |
| Backup file | 10967 bytes | 10967 bytes | 0 (unchanged) |

---

## 7. R-5C Phase 1 Confirmation

- **Only cleanup command executed**: `docker builder prune -f`
- **No images removed**: `docker system df` Images Total = 31 before and after
- **No containers stopped/restarted**: All 5 remained Up healthy throughout
- **No `docker image prune -f`**: NOT executed
- **No `docker rmi`**: NOT executed
- **No `docker stop/rm`**: NOT executed
- **No `docker volume rm`**: NOT executed
- **No `docker compose up`**: NOT executed
- **No `git pull`**: NOT executed
- **No `alembic`**: NOT executed
- **No `.env` read**: NOT accessed
- **sing-box untouched**: Process and port 443 unchanged
- **Backup file untouched**: File unchanged
- **Port 80 responding**: Before and after HTTP 200

---

## 8. Phase 2/3 Status

**FROZEN**. CTO has NOT approved Phase 2 or Phase 3. No `docker rmi` commands will be executed until CTO explicitly approves.

Remaining reclaimable:
- 21 true dangling images (portion of 9.663 GB)
- 5 legacy named images (portion of 9.663 GB)
- 91 intermediate build layers (auto-freed when parents removed)

---

## 9. Git Commit (R-5C Phase 1)

| Item | Value |
|---|---|
| Repo | `phase6-closeout-promotion-2026-05-15` |
| Branch | `ops/sprint-r2-vps-script-recovery-2026-05-25` |
| Commit message | `docs(ops): R-5C Phase 1 build cache cleanup -- 945.4 MB reclaimed, 0 images touched, all services healthy` |
| Files changed | New: `ai-ledger/ops/2026-05-29_sprint_r5c_phase1_build_cache_cleanup.md` |
| Push | **No** -- awaiting CTO review |
