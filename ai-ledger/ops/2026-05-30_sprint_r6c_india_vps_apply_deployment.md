# Sprint R-6C: India VPS Apply Deployment -- FAILED (Type A Rollback Executed)

**Execution Date**: 2026-05-30 07:27 UTC
**Status**: DEPLOY_FAILED -- ROLLBACK TYPE A EXECUTED -- PRODUCTION STABLE
**Target**: Canonical India VPS `143.110.177.2` (`ubuntu-s-1vcpu-1gb-blr1-01`)
**Preceding Gate**: R-6B-R1 approved (`204da0f`, pushed to origin)
**Failure**: Frontend Docker build -- `pnpm install` fails with `ERR_VM_DYNAMIC_IMPORT_CALLBACK_MISSING` (Node 18 + pnpm 11 incompatibility)

> **Outcome**: Deployment failed at build step. No containers were rebuilt. No migrations ran. No database changes. Rollback Type A executed (git checkout main). Production is running unchanged at `02d69c0`.

---

## 1. Step 0: Audit Record Sync

| Action | Result |
|---|---|
| Push `75debae..204da0f` to `origin/ops/sprint-r2-vps-script-recovery-2026-05-25` | SUCCESS |
| Git status clean | CONFIRMED |

---

## 2. Step 1: Pre-Deploy Final Gate

All checks executed in parallel. **ALL PASS.**

| # | Check | Expected | Actual | Result |
|---|---|---|---|---|
| 1 | hostname | `ubuntu-s-1vcpu-1gb-blr1-01` | `ubuntu-s-1vcpu-1gb-blr1-01` | PASS |
| 2 | Working tree clean | empty | empty | PASS |
| 3 | HEAD | `02d69c0` | `02d69c00e7aeefdc788a0335a09a6f735b85f07b` | PASS |
| 4 | FETCH_HEAD after fetch | `b30784b` | `b30784b176b2acd59bfdf0602196fb9b0abe3d6a` | PASS |
| 5 | Containers healthy | 5/5 Up healthy | 5/5 Up healthy (2 months) | PASS |
| 6 | Port 80 | HTTP 200 | 200 | PASS |
| 7 | sing-box | Running, :443 LISTEN | PID 132529, :443 LISTEN | PASS |
| 8 | Disk space | ~13 GB free | 13 GB free (46%) | PASS |
| 9 | `.env` exists | YES | YES (2948 B, Mar 11) | PASS |
| 10 | `.env.prod` | NOT exists | NOT exists | PASS |

**Pre-Deploy Gate: ALL GREEN.** Proceeded to Step 2.

---

## 3. Step 2: Fresh R-6C Apply Backup

### 3.1 Backup Execution

```sh
docker exec mpango_prod_postgres pg_dump -U mpango -d mpango_erp --clean --if-exutes | \
  gzip > /root/mpango-backups/mpango_erp_r6c_20260530_072700.sql.gz
```

### 3.2 Backup Evidence

| Property | Value |
|---|---|
| **File** | `/root/mpango-backups/mpango_erp_r6c_20260530_072700.sql.gz` |
| **Size** | 10969 bytes |
| **SHA256** | `f3e24521ccb5f3421e8b25dec4a3b75d276f43131ae320c4cff7ebfe1c370225` |
| **gzip -t verify** | PASS |
| **Created** | 2026-05-30 07:27 UTC (file timestamp May 29 23:28 UTC) |

**Backup Gate: PASS.** Proceeded to Step 3.

---

## 4. Step 3: Checkout Exact Target

### 4.1 Checkout Execution

```sh
cd /root/mpango-erp
git checkout -B product-dev-recovered FETCH_HEAD
```

### 4.2 Checkout Evidence

| Property | Value |
|---|---|
| **Branch created** | `product-dev-recovered` |
| **HEAD** | `b30784b176b2acd59bfdf0602196fb9b0abe3d6a` |
| **Commit message** | `merge: add mvp closeout acceptance evidence` |

**Checkout: PASS.** Proceeded to Step 4.

---

## 5. Step 4: Build + Deploy -- FAILED

### 5.1 Command Executed

```sh
cd /root/mpango-erp
docker compose -f docker-compose.prod.yml up -d --build
```

### 5.2 Build Output (Key Error)

```
#17 [frontend builder 5/7] RUN pnpm install --frozen-lockfile
#17 1.320 TypeError [ERR_VM_DYNAMIC_IMPORT_CALLBACK_MISSING]: A dynamic import callback was not specified.
#17 1.320     at new NodeError (node:internal/errors:405:5)
#17 1.320     at importModuleDynamicallyCallback (node:internal/modules/esm/utils:182:9)
#17 1.320     at Object.<anonymous> (/root/.cache/node/corepack/v1/pnpm/11.5.0/bin/pnpm.cjs:3:1)
#17 ERROR: process "/bin/sh -c pnpm install --frozen-lockfile" did not complete successfully: exit code: 1
```

### 5.3 Backend Build Status

Backend build was **CANCELED** by Docker when frontend failed:

```
#16 [backend 1/10] FROM docker.io/library/python:3.11-slim
#16 CANCELED
```

### 5.4 Root Cause Analysis

| Factor | Detail |
|---|---|
| **Failing stage** | `frontend` builder, step 5/7: `RUN pnpm install --frozen-lockfile` |
| **Dockerfile line** | `frontend/Dockerfile:15` |
| **Base image** | `node:18-alpine` (Node.js v18.20.8) |
| **pnpm activation** | `corepack enable && corepack prepare pnpm@latest --activate` |
| **pnpm version resolved** | 11.5.0 (latest at time of build) |
| **Error** | `ERR_VM_DYNAMIC_IMPORT_CALLBACK_MISSING` -- pnpm 11.x uses ESM dynamic imports that Node 18 does not support |
| **Previous successful build** | 2026-03-10 (3 months ago) -- `pnpm@latest` would have resolved to an older, compatible version |

**Root cause**: `corepack prepare pnpm@latest` is not pinned. In March 2026, `@latest` resolved to a Node-18-compatible version. Now it resolves to pnpm 11.5.0 which requires Node 20+.

### 5.5 Impact Assessment

| Item | Status |
|---|---|
| New containers started | NONE |
| Migrations executed | NONE |
| Database changed | NO |
| Old containers affected | NO (still running) |
| Git working tree | On `product-dev-recovered @ b30784b` (needs revert) |

**Failure classification**: **Type A** -- Build failure before any migration or container restart.

---

## 6. Rollback Type A Executed

### 6.1 Rollback Actions

```sh
cd /root/mpango-erp
git checkout main
```

### 6.2 Rollback Evidence

| Property | Value |
|---|---|
| **HEAD after rollback** | `02d69c0` (main) |
| **Commit message** | `fix: tenant bootstrap + frontend healthcheck + MPANGO_ENV` |

### 6.3 Post-Rollback Verification

| Check | Result |
|---|---|
| docker ps | 5/5 Up healthy |
| Port 80 | HTTP 200 |
| Backend health | `{"status":"healthy","version":"0.2.0"}` |
| Git HEAD | `02d69c0` (main) |

**Rollback Type A: SUCCESS. Production fully stable at pre-deploy state.**

---

## 7. R-6C Conclusion

### 7.1 What Worked

- Pre-deploy gate: All 10 checks passed
- Fresh backup: Created, verified, available for future use
- Git checkout: Precise target `b30784b` confirmed
- Rollback Type A: Executed cleanly, production unchanged
- Stop conditions: Followed correctly -- build failure triggered immediate stop, no retry, no self-heal

### 7.2 What Failed

- **Frontend Docker build**: `pnpm@latest` via Corepack resolved to pnpm 11.5.0 which is incompatible with Node 18
- **Backend Docker build**: Canceled (never started)

### 7.3 Required Fix Before R-6C Retry

The `frontend/Dockerfile` must be updated before a retry. The fix is to pin pnpm to a Node-18-compatible version:

**Option A (recommended)**: Pin pnpm version in Dockerfile
```dockerfile
# Before:
RUN corepack enable && corepack prepare pnpm@latest --activate

# After:
RUN corepack enable && corepack prepare pnpm@9 --activate
```

**Option B**: Upgrade Node.js base image to Node 20
```dockerfile
# Before:
FROM node:18-alpine AS builder

# After:
FROM node:20-alpine AS builder
```

**Option C**: Add `packageManager` field to `frontend/package.json`
```json
"packageManager": "pnpm@9.15.4"
```

This fix must be committed to the `product-dev-recovered` branch and the branch re-fetched before retrying R-6C.

### 7.4 Assets Available for Retry

| Asset | Location | Status |
|---|---|---|
| R-6C fresh backup | `/root/mpango-backups/mpango_erp_r6c_20260530_072700.sql.gz` (10969 B) | Available |
| R-6B backup | `/root/mpango-backups/mpango_erp_r6b_20260530_070447.sql.gz` (10965 B) | Available |
| FETCH_HEAD | `b30784b` (will need re-fetch after branch update) | Needs refresh |
| VPS HEAD | `02d69c0` (main) | Stable |

---

## 8. Deployment Timeline

| Time (UTC) | Event |
|---|---|
| 07:27 | Step 0: Push audit records |
| 07:28 | Step 1: Pre-deploy gate -- ALL PASS |
| 07:29 | Step 2: Fresh backup -- PASS |
| 07:29 | Step 3: Git checkout `b30784b` -- PASS |
| 07:30 | Step 4: `docker compose up -d --build` -- FAILED (frontend pnpm 11 + Node 18 incompatibility) |
| 07:31 | Failure classified as Type A (build fail, no migration) |
| 07:32 | Rollback Type A: `git checkout main` -- SUCCESS |
| 07:33 | Post-rollback verification: 5/5 healthy, port 80 = 200, backend healthy |
| 07:33 | **STOP_AND_REPORT_CTO** |

---

## 9. Commands Executed

### Write Operations on VPS

1. `git fetch origin product-dev-recovered` (fetch only)
2. `pg_dump ... | gzip > mpango_erp_r6c_20260530_072700.sql.gz` (backup)
3. `git checkout -B product-dev-recovered FETCH_HEAD` (checkout)
4. `docker compose -f docker-compose.prod.yml up -d --build` (FAILED -- no containers changed)
5. `git checkout main` (rollback)

### Read-Only Operations

`hostname`, `docker ps`, `git status`, `git log`, `git rev-parse`, `curl`, `ps aux`, `ss -ltnp`, `df -h`, `ls -l`, `sha256sum`, `gzip -t`, `docker exec ... curl`, `cat Dockerfile`, `docker inspect`, `docker image inspect`

---

## 10. Git Commit (R-6C)

| Item | Value |
|---|---|
| Repo | `phase6-closeout-promotion-2026-05-15` |
| Branch | `ops/sprint-r2-vps-script-recovery-2026-05-25` |
| Commit | *(this ledger)* |
| Push | **No** -- awaiting CTO review |
| Preceding commit | `204da0f` (R-6B-R1, pushed) |

---

## 11. Commit Chain (Current)

```
[TBD]   docs(ops): R-6C apply deployment -- FAILED (Type A), frontend pnpm 11 + Node 18 incompatibility, rollback executed, production stable
204da0f fix(ops): R-6B-R1 rollback correction  (PUSHED)
75debae docs(ops): R-6B deployment dry-run     (PUSHED)
b6dab2f fix(ops): R-6A-R1                      (PUSHED)
86b9311 docs(ops): R-6A                        (PUSHED)
a63c91e fix(ops): R-5 closeout typo            (PUSHED)
73ab330 docs(ops): R-5 closeout                (PUSHED)
```
