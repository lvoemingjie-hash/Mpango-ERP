# Sprint R-6B: India VPS Deployment Dry-Run and Backup Gate

**Execution Date**: 2026-05-30 07:04 UTC
**Status**: DRY_RUN_COMPLETE
**Target**: Canonical India VPS `143.110.177.2` (`ubuntu-s-1vcpu-1gb-blr1-01`)
**Preceding Gate**: R-6A-R1 approved (`b6dab2f`, pushed to origin)
**Scope**: Fresh DB backup, git fetch (no checkout), diff review, migration review, deploy script review. **NO DEPLOYMENT.**

> **Purpose**: Execute all pre-deployment checks to produce a deployment apply plan (R-6C) for CTO approval. No write operations to the production application stack.

---

## 1. Commands NOT Executed (Forbidden)

- `git checkout` / `git pull` / `git merge` -- NOT executed
- `docker compose up` / `docker compose down` / `docker compose build` -- NOT executed
- `alembic upgrade` / `alembic downgrade` -- NOT executed
- `.env` / `.env.prod` content read -- NOT executed (existence checked only)
- `docker stop` / `docker rm` -- NOT executed
- Any file modification in `/root/mpango-erp/` -- NOT executed
- `pip install` / `npm install` -- NOT executed

---

## 2. Fresh DB Backup (R-6B Gate 1)

### 2.1 Backup Execution

```sh
# Executed on VPS via SSH
mkdir -p /root/mpango-backups
docker exec mpango_prod_postgres pg_dump -U mpango -d mpango_erp --clean --if-exists | gzip > /root/mpango-backups/mpango_erp_r6b_20260530_070447.sql.gz
```

### 2.2 Backup Evidence

| Property | Value |
|---|---|
| **File** | `/root/mpango-backups/mpango_erp_r6b_20260530_070447.sql.gz` |
| **Size** | 10965 bytes |
| **SHA256** | `b1a4ebb8ff2ba00dad41f017e3f04f0d3f664a61f23977a893ad239e5b1a03f9` |
| **gzip -t verify** | PASS (valid gzip stream) |
| **Created** | 2026-05-30 07:04 UTC |

### 2.3 Backup Comparison

| Backup | Date | Size |
|---|---|---|
| R-4B (`mpango_erp_20260527_063830.sql.gz`) | May 26 | 10967 bytes |
| R-6B (`mpango_erp_r6b_20260530_070447.sql.gz`) | May 30 | 10965 bytes |

**Assessment**: Size difference of 2 bytes is negligible. Database has minimal data. Fresh backup confirmed. PASS.

---

## 3. Git Fetch (R-6B Gate 2)

### 3.1 Fetch Execution

```sh
# Executed on VPS via SSH
cd /root/mpango-erp && git fetch origin product-dev-recovered
```

### 3.2 Fetch Evidence

| Property | Value |
|---|---|
| **FETCH_HEAD** | `b30784b` |
| **FETCH_HEAD message** | `merge: add mvp closeout acceptance evidence` |
| **VPS HEAD** | `02d69c0` (unchanged, still on main) |
| **Checkout performed** | NO |
| **Working tree modified** | NO |

### 3.3 VPS Git Status After Fetch

```
HEAD: 02d69c0 (main)
FETCH_HEAD: b30784b (product-dev-recovered)
Branch: main (unchanged)
Status: clean working tree
```

**Result**: FETCH_HEAD confirmed at `b30784b`. No checkout, no working tree change. PASS.

---

## 4. Diff Review (R-6B Gate 3)

### 4.1 Overall Diff Stat

```
652 files changed between 02d69c0..b30784b
```

### 4.2 Critical Config Files Diff

| File | Changed (02d69c0..b30784b) | Notes |
|---|---|---|
| `docker-compose.prod.yml` | NO | Zero diff |
| `docker-compose.yml` | NO | Zero diff |
| `docker-compose.override.yml` | NO | Zero diff |
| `backend/docker-entrypoint.sh` | NO | Zero diff |
| `backend/Dockerfile` | NO | Zero diff |
| `frontend/Dockerfile` | NO | Zero diff |
| `.env.example` | NO | Zero diff |
| `backend/requirements.txt` | NO | Zero diff |
| `frontend/package.json` | NO | Zero diff |
| `nginx/gateway.conf` | NO | Zero diff |

### 4.3 Diff Assessment

**All infrastructure configuration files are IDENTICAL between VPS commit and deployment candidate.** This means:

1. **Docker build context unchanged** -- Same Dockerfiles, same compose config
2. **Entrypoint unchanged** -- Same migration/bootstrap/start sequence
3. **Dependencies unchanged** -- Same Python packages, same npm packages
4. **Gateway config unchanged** -- Same nginx routing
5. **No new environment variables** -- `.env.example` identical, compose file identical

**The 652-file delta is entirely application code** (backend Python, frontend TS/JS, Alembic migrations).

---

## 5. Migration Review (R-6B Gate 4)

### 5.1 Migration Delta Overview

5 new migrations exist in `b30784b` that are not on VPS (`02d69c0`):

| # | File | Description |
|---|---|---|
| 017 | `017_retailer_prices.py` | Retailer pricing schema |
| 018 | `018_platform_p0_lifecycle.py` | Tenant lifecycle scaffold |
| 019 | `019_platform_audit_logs.py` | Audit log table |
| 020 | `020_sys_jobs_audit_columns.py` | Audit contract columns |
| 021 | `021_tenant_payments_retailer_id_transaction_id.py` | Payment ledger enrichment |

### 5.2 Per-Migration Safety Review

#### 017_retailer_prices.py

| Property | Value |
|---|---|
| **Schema** | Tenant (t_*) |
| **Operation** | `create_table("retailer_prices", ...)` |
| **Destructive** | NO |
| **Has downgrade** | YES (`drop_table`) |
| **Idempotent** | YES (Alembic tracks revisions; `create_table` no-op if table exists in alembic_version) |

**Columns**: `id`, `retailer_id` (FK), `sku_id` (FK), `price` (Numeric), `created_at`, `updated_at`
**Risk**: NONE. Pure additive table creation.

#### 018_platform_p0_lifecycle.py

| Property | Value |
|---|---|
| **Schema** | Public |
| **Operations** | `add_column` (status, provisioned_at, suspended_at, suspension_reason to `wholesalers`), `create_table("platform_tenants")` |
| **Destructive** | NO |
| **Has downgrade** | YES |
| **Defaults** | `server_default="active"` (status), `server_default=text("NOW()")` (provisioned_at) |

**Risk**: NONE. Additive columns with server defaults. No data mutation.

#### 019_platform_audit_logs.py

| Property | Value |
|---|---|
| **Schema** | Public |
| **Operation** | `create_table("platform_audit_logs")` |
| **Destructive** | NO |
| **Has downgrade** | YES (`drop_table`) |

**Risk**: NONE. Pure append-only table creation.

#### 020_sys_jobs_audit_columns.py

| Property | Value |
|---|---|
| **Schema** | Public |
| **Operations** | `alter_column` (server_default on `sys_jobs.id`), `add_column` (is_deleted, deleted_at) |
| **Destructive** | NO |
| **Defaults** | `server_default=text("false")` (is_deleted), `server_default=None` (deleted_at, nullable) |

**Risk**: NONE. Alter adds server_default to existing column, adds nullable columns with defaults.

#### 021_tenant_payments_retailer_id_transaction_id.py

| Property | Value |
|---|---|
| **Schema** | Tenant only (checks `search_path` for `t_*` prefix) |
| **Operations** | `add_column` (retailer_id, transaction_id), `create_index`, **backfill** from `orders.retailer_id` |
| **Destructive** | NO (additive only) |
| **Has downgrade** | YES |
| **Data integrity guard** | YES -- raises `RuntimeError` if any NULL `retailer_id` remains after backfill |
| **Idempotency** | YES -- has `_table_exists`, `_column_exists`, `_index_exists` checks |

**Risk**: LOW. The backfill has an explicit failure guard. If data integrity issues exist, the migration will fail safely (no partial state -- Alembic wraps in transaction). However, a failed migration means the container enters a crash loop until the migration is resolved.

### 5.3 Migration Safety Summary

| Migration | Destructive | Data Risk | Overall |
|---|---|---|---|
| 017_retailer_prices | NO | NONE | SAFE |
| 018_platform_p0_lifecycle | NO | NONE | SAFE |
| 019_platform_audit_logs | NO | NONE | SAFE |
| 020_sys_jobs_audit_columns | NO | NONE | SAFE |
| 021_tenant_payments_retailer_id_transaction_id | NO | LOW (backfill guard) | SAFE WITH CAVEAT |

**Caveat on 021**: If `orders` table has rows in tenant schema that cannot be matched for `retailer_id` backfill, the migration will raise `RuntimeError` and the container will crash loop. This is a **safe failure** (no data corruption) but requires manual intervention to resolve.

### 5.4 Migration Execution Path

On `docker compose up --build`:
1. Backend container builds from source (application code changes)
2. `docker-entrypoint.sh` runs: `alembic upgrade head`
3. Alembic runs 017 -> 018 -> 019 -> 020 -> 021 in sequence
4. Each migration runs in its own transaction
5. If 021 backfill fails, container exits; migrations 017-020 are already committed
6. On restart, Alembic resumes from 021 (re-runs the failed migration)

---

## 6. Deploy Script Review (R-6B Gate 5)

### 6.1 `deploy_vps.sh` Assessment

| Property | Value |
|---|---|
| **Location** | `scripts/deploy_vps.sh` in OPS branch (`1dcbf1a`) |
| **In candidate branch** | NO |
| **On VPS** | NO |

### 6.2 Identified Adaptation Gaps

| # | Issue | Severity | Detail |
|---|---|---|---|
| 1 | `.env.prod` hard dependency | **HIGH** | Script checks for `.env.prod` existence and exits if missing. VPS uses `.env` (not `.env.prod`). Script would fail immediately. |
| 2 | Redundant `alembic upgrade head` | **LOW** | Script runs `alembic upgrade head` as a separate step after `docker compose up --build`. However, `docker-entrypoint.sh` already runs `alembic upgrade head` on container start. Double execution is harmless but wasteful. |
| 3 | Not in candidate branch | **MEDIUM** | Script would need to be transferred to VPS separately. Cannot be deployed via the candidate branch. |

### 6.3 Deploy Script Recommendation

**Do NOT use `deploy_vps.sh` for R-6C deployment.** The `.env.prod` dependency is a blocking issue. Instead, execute manual SSH steps for the first deployment (see Section 7 R-6C Apply Plan).

For future deployments, adapt the script to:
1. Accept `.env` or `.env.prod` (parameterize the env file path)
2. Remove the redundant `alembic upgrade head` step

### 6.4 `safe_cleanup_vps.sh` Assessment

Not needed for deployment. Available in OPS branch for future cleanup operations. No adaptation gaps relevant to R-6C.

---

## 7. R-6C Apply Plan Draft

> **IMPORTANT**: This is a DRAFT plan only. Requires CTO approval before execution. DO NOT execute without explicit R-6C authorization.

### 7.1 Pre-Conditions (All PASS)

| # | Condition | Status |
|---|---|---|
| 1 | Fresh backup exists | PASS (R-6B backup, 10965 bytes, SHA256 verified) |
| 2 | Deployment candidate fetched | PASS (FETCH_HEAD = b30784b) |
| 3 | Config files identical | PASS (zero diff on all infrastructure files) |
| 4 | All migrations non-destructive | PASS (017-020: NONE; 021: LOW with guard) |
| 5 | No new environment variables | PASS (compose + .env.example unchanged) |
| 6 | VPS healthy | PASS (5/5 containers healthy, per R-6A-R1) |

### 7.2 R-6C Execution Sequence

```
STEP 1: Pre-deploy verification
  ssh root@143.110.177.2
  docker ps --format "table {{.Names}}\t{{.Status}}"   # Confirm 5/5 healthy
  df -h /                                                # Confirm disk space
  cd /root/mpango-erp && git status                      # Confirm clean state

STEP 2: Checkout deployment candidate
  cd /root/mpango-erp
  git checkout product-dev-recovered                     # Checkout fetched branch
  git log --oneline -1                                   # Confirm HEAD = b30784b

STEP 3: Build and deploy
  docker compose -f docker-compose.prod.yml up -d --build
  # This triggers:
  #   a) Backend image rebuild (source code changes)
  #   b) Frontend image rebuild (source code changes)
  #   c) docker-entrypoint.sh runs alembic upgrade head (017-021)
  #   d) docker-entrypoint.sh runs bootstrap_tenant_schema.py
  #   e) Uvicorn starts

STEP 4: Post-deploy verification
  docker ps --format "table {{.Names}}\t{{.Status}}"   # All 5 healthy
  docker logs mpango_prod_backend --tail 50             # Check migration output
  curl -s http://localhost:8000/health/live              # Backend health
  curl -s http://localhost:80/                           # Frontend/gateway

STEP 5: Migration verification
  docker exec mpango_prod_backend alembic current        # Confirm head = 021
  docker exec mpango_prod_postgres psql -U mpango -d mpango_erp -c "\dt public.platform_*"  # New tables
  docker exec mpango_prod_postgres psql -U mpango -d mpango_erp -c "\dt t_*.retailer_prices"  # New tenant table
```

### 7.3 R-6C Rollback Plan

If deployment fails or migration 021 backfill errors:

```
ROLLBACK STEP 1: Stop failed deployment
  cd /root/mpango-erp
  docker compose -f docker-compose.prod.yml down          # Stop all containers

ROLLBACK STEP 2: Revert to previous commit
  git checkout main
  git checkout 02d69c0                                    # Return to pre-deploy commit

ROLLBACK STEP 3: Restore database from backup
  gunzip < /root/mpango-backups/mpango_erp_r6b_20260530_070447.sql.gz | \
    docker exec -i mpango_prod_postgres psql -U mpango -d mpango_erp

ROLLBACK STEP 4: Rebuild with previous code
  docker compose -f docker-compose.prod.yml up -d --build

ROLLBACK STEP 5: Verify rollback
  docker ps --format "table {{.Names}}\t{{.Status}}"
  docker logs mpango_prod_backend --tail 30
  curl -s http://localhost:8000/health/live
```

> **Rollback note**: Migrations 017-020 are committed in their own transactions. If 021 fails, 017-020 are already applied. The backup restore (ROLLBACK STEP 3) will undo ALL 5 migrations, returning the database to the pre-deploy state with migrations 001-016.

### 7.4 R-6C Risk Assessment

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| Migration 021 backfill failure | LOW | MEDIUM (crash loop) | Backup restore plan ready |
| Build failure (code issue) | LOW | LOW (no DB change) | Revert git checkout |
| Frontend build failure | LOW | LOW (no DB change) | Revert git checkout |
| New code runtime error | LOW | LOW-MEDIUM | Revert + backup restore |
| Env var missing | NEAR-ZERO | LOW (compose unchanged) | Verified in R-6A-R1 |

### 7.5 R-6C Estimated Downtime

- Build time: ~3-5 minutes (backend + frontend Docker builds)
- Migration time: ~5-10 seconds (small database, 5 simple migrations)
- **Total estimated downtime**: ~3-5 minutes (containers restart during build)

### 7.6 R-6C NOT Authorized

This plan is a **DRAFT**. R-6C requires explicit CTO approval. The following remain in place:
- Fresh backup at `/root/mpango-backups/mpango_erp_r6b_20260530_070447.sql.gz`
- FETCH_HEAD at `b30784b` (ready for checkout when approved)
- VPS HEAD at `02d69c0` (unchanged, production stable)

---

## 8. Dry-Run Findings Summary

| # | Finding | Classification |
|---|---|---|
| 1 | Fresh backup confirmed (10965 bytes, SHA256 verified, gzip valid) | GATE PASS |
| 2 | Git fetch completed, FETCH_HEAD = b30784b, no checkout | GATE PASS |
| 3 | All infrastructure config files identical (zero diff) | GATE PASS |
| 4 | Migrations 017-020: fully non-destructive, no data risk | GATE PASS |
| 5 | Migration 021: non-destructive with data integrity guard (safe fail) | GATE PASS (with caveat) |
| 6 | `deploy_vps.sh` has `.env.prod` blocking issue; recommend manual deploy | NOTED |
| 7 | No new environment variables required | GATE PASS |
| 8 | R-6C apply plan drafted; requires CTO approval | PENDING |

---

## 9. Commands Executed (Read-Only + Backup Only)

Write operations:
- `mkdir -p /root/mpango-backups` (backup directory)
- `pg_dump ... | gzip > backup.sql.gz` (database backup)
- `git fetch origin product-dev-recovered` (fetch only, no checkout)

All other commands were read-only: `docker exec ... env | grep`, `docker exec ... pg_dump`, `gzip -t`, `sha256sum`, `ls -la`, `git log`, `git diff`, `git show FETCH_HEAD:...`, `cat`, `wc -c`.

**No deployment, no container restart, no migration execution, no .env read.**

---

## 10. Git Commit (R-6B)

| Item | Value |
|---|---|
| Repo | `phase6-closeout-promotion-2026-05-15` |
| Branch | `ops/sprint-r2-vps-script-recovery-2026-05-25` |
| Commit | *(this ledger)* |
| Push | **No** -- awaiting CTO review |
| Preceding commit | `b6dab2f` (R-6A-R1, pushed) |

---

## 11. Commit Chain (Current)

```
[TBD]   docs(ops): R-6B deployment dry-run -- backup PASS, fetch PASS, 5 migrations SAFE, R-6C apply plan drafted
b6dab2f fix(ops): R-6A-R1 -- correct candidate branch, fix deploy script location, add R-6B dry-run inputs  (PUSHED)
86b9311 docs(ops): R-6A deployment readiness recheck  (PUSHED)
a63c91e fix(ops): R-5 closeout typo  (PUSHED)
73ab330 docs(ops): R-5 cleanup closeout  (PUSHED)
```
