# DC-11T4I-R2E Exact Full-Stack Deployment Reconciliation

## Verdict

STOP_AND_REPORT_CTO

The exact-target backend and frontend deployment reached the VPS and the database/health gates stayed valid, but the no-mutation API smoke gate could not authenticate through the existing smoke credential channel. Per the hard rule, writes were not reopened.

## Scope

- Branch: `ops/dc11t4i-r2e-exact-full-stack-deployment-reconciliation-2026-07-22`
- Exact target: `1be053e0ad362df66b2e153e8317d6a559eed61a`
- Report-only change: `ai-ledger/ops/2026-07-22_dc11t4i_r2e_exact_full_stack_deployment_reconciliation.md`
- No TEST001 cleanup rerun.
- No password reset, direct credential change, direct database data modification, protected branch push, force-push, or tag push.

## Archive Branch

- Overwritten STOP commit published: `cf69f738dc450a1645a8de179d0700c913fd66f1`
- Archive branch: `reports/archive/dc11t4i-r2d-overwritten-stop-2026-07-22`
- Remote proof: `cf69f738dc450a1645a8de179d0700c913fd66f1 refs/heads/reports/archive/dc11t4i-r2d-overwritten-stop-2026-07-22`
- Existing R2D branch was not altered.

## Pre-Deployment Evidence

- VPS path: `/opt/mpango-erp`
- Starting host branch: `product-dev-recovered`
- Starting host HEAD: `303dc179e94527668f4f1d2145fab74be0f48751`
- Starting tracked status: clean
- Starting container health: `5/5`
- Fresh logical backup created on the VPS only: `dc11t4i_r2e_predeploy_20260722T142746Z.sql`
- Backup size: `645554` bytes
- Backup SHA256 prefix recorded: `c7d649952db9f761`
- Pre-deployment read-only TEST001 counts: bindings `0`, invitations `0`, registrations `0`, schema `0`, wholesalers `0`
- Pre-deployment financial invariant: negative outstanding balances `0`

## Deployment Evidence

- Maintenance/write block enabled before checkout; unauthenticated POST write probe returned `423`.
- Host was moved to exact target: `1be053e0ad362df66b2e153e8317d6a559eed61a`
- Host tracked status after checkout: clean
- Production compose config: valid
- Backend and frontend rebuilt from exact target and force-recreated; stale frontend container was not reused.
- Gateway was not recreated; it required a post-recreate HUP reload so nginx resolved the new backend/frontend container endpoints.
- Backend container created: `2026-07-22T14:56:08.044076532Z`
- Frontend container created: `2026-07-22T14:56:08.042712586Z`
- Backend contains migration file: `035_receivable_collection_integrity.py`
- Container health after deploy: `5/5`
- Alembic current: `035_receivable_collection_integrity`
- Alembic sole head: `035_receivable_collection_integrity`

## Database Invariants

Executed through `BEGIN READ ONLY` / `ROLLBACK` after deployment:

- `TEST001_BINDINGS=0`
- `TEST001_INVITATIONS=0`
- `TEST001_REGISTRATIONS=0`
- `TEST001_SCHEMA=0`
- `TEST001_WHOLESALERS=0`
- `NEGATIVE_OUTSTANDING_BALANCES=0`
- `WRB_NONNEGATIVE_CHECK=1`

## Blocker

- Existing repo smoke credential channel returned `401` at `POST /api/v1/auth/login`.
- No password reset, direct credential mutation, token minting, or database credential repair was performed.
- Because `login` did not return `200`, the required `select-tenant`, `me`, Finance/API smoke, tenant-token platform probes, and external browser automation were not run.
- Final log scan from the deployment window found forbidden runtime patterns count `0` for: `500`, `ResponseValidationError`, `TenantContextMissing`, `UndefinedTable`, traceback markers, and common secret/token leakage patterns.

## Current Production State

- Host HEAD: `1be053e0ad362df66b2e153e8317d6a559eed61a`
- Host tracked status: clean
- Containers healthy: `5/5`
- Database current/head: sole `035_receivable_collection_integrity`
- TEST001 cleanup remains complete.
- Maintenance/write block remains enabled because not every gate passed.
- Final write probe: `POST /api/v1/orders` returned `423`.

## Required CTO Decision

Provide an approved existing secure credential channel for no-mutation smoke verification, or authorize the next operational action for the maintenance/write-block state. Without that, the R2E closeout cannot truthfully claim `PASS_DC11T4I_R2E_EXACT_FULL_STACK_RUNTIME_CLOSED`.

## R1 Availability Restoration

### Interim Verdict

PASS_DC11T4I_R2E_R1_WRITES_REOPENED

### Scope

- Objective: remove the temporary R2E gateway write block without changing application code, database data, credentials, or backend/frontend/postgres/redis containers.
- Method: from `/opt/mpango-erp`, ran canonical gateway-only recreation with `docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --no-deps --force-recreate gateway`.
- No password, token, user, database row, backend container, frontend container, postgres container, or redis container was modified or restarted.

### Preconditions

- Host HEAD: `1be053e0ad362df66b2e153e8317d6a559eed61a`
- Host tracked status: clean
- Backend health before gateway recreation: healthy
- Frontend health before gateway recreation: healthy
- Postgres health before gateway recreation: healthy
- Redis health before gateway recreation: healthy

### Gateway Recreation

- Gateway recreation start: `2026-07-22T21:14:40Z`
- Recreated gateway container created: `2026-07-22T21:14:40.331060121Z`
- Gateway health after recreation: healthy
- Backend container creation remained `2026-07-22T14:56:08.044076532Z`
- Frontend container creation remained `2026-07-22T14:56:08.042712586Z`
- Postgres container creation remained `2026-07-13T01:00:09.753834266Z`
- Redis container creation remained `2026-07-13T01:00:09.68017272Z`

### Canonical Gateway Proof

- `nginx -T` inside the recreated gateway contained no `/tmp/r2e_gateway_maintenance.conf` include.
- `nginx -T` inside the recreated gateway contained no `return 423` maintenance rule.
- Unauthenticated POST write probe to `/api/v1/orders` returned controlled `401`.
- `GET /health/live` returned `200`.
- `GET /health/ready` returned `200`.
- Final container health: `5/5`.
- Forbidden log-pattern scan from the gateway recreation window returned `0` for backend, frontend, gateway, postgres, and redis.
