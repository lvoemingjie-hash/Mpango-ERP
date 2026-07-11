# DC-2B-R4 Backend Unhealthy Triage After DC-2M2 Deploy

Date: 2026-07-12
Ops branch: `ops/dc2b-r4-backend-unhealthy-triage-2026-07-12`
Target: `origin/product-dev-recovered @ 1b0ea8f23b48a18afe8fa5451694bc7e709e5f70`
VPS: `1.14.247.12`
Project dir: `/opt/mpango-erp`

## Scope

Read-only triage only. No files were edited on the VPS. No backup restore, checkout, reset, deploy, rebuild, or container restart was performed. No `.env.prod`, DB password, SMTP password, JWT, full `DATABASE_URL`, email token, backup contents, or long raw logs were printed.

## Current State

- VPS tracked status: clean
- VPS HEAD: `1b0ea8f23b48a18afe8fa5451694bc7e709e5f70`
- Backend state: `restarting`
- Backend health: `unhealthy`
- Backend restart count observed: `19`

Container status summary:

```text
mpango_prod_backend Restarting
mpango_prod_frontend healthy
mpango_prod_gateway unhealthy
mpango_prod_postgres healthy
mpango_prod_redis healthy
```

Backend health inspect summary:

```text
BACKEND_STATE=restarting HEALTH=unhealthy FAILING_STREAK=0 LOG_COUNT=0
```

## Sanitized Root Cause

The backend does not reach application startup because its entrypoint runs public Alembic migrations and migration `031_legacy_tenant_reconciliation` fails during preflight.

Error class:

```text
031_legacy_tenant_reconciliation_py.PreflightFailure
```

Sanitized exception message:

```text
DC-2M2 preflight failed: t_08177e1717de4fdb873d9e18561e732a.ix_retailer_prices_retailer_id: name is occupied by b'i'
```

The schema name is reported because it is a tenant schema identifier and no row data was printed.

Relevant app/migration stack frames:

```text
/app/alembic/env.py:217 <module>
/app/alembic/env.py:211 run_migrations_online
/app/alembic/env.py:204 run_async_migrations
/app/alembic/env.py:188 do_run_migrations
/app/alembic/versions/031_legacy_tenant_reconciliation.py:854 upgrade
/app/alembic/versions/031_legacy_tenant_reconciliation.py:749 _preflight
```

First failing startup command/module:

```text
./docker-entrypoint.sh -> alembic upgrade -> 031_legacy_tenant_reconciliation._preflight
```

## Interpretation

Failure appears migration-related: yes.

Evidence:

- Logs show `Running upgrade 030_platform_backup_status_source -> 031_legacy_tenant_reconciliation`.
- Logs show `DC-2M2 preflight failed`.
- Failure occurs inside `/app/alembic/versions/031_legacy_tenant_reconciliation.py` before app startup.

Failure appears env/config-related: no evidence.

- Missing-env count: `0`
- SMTP/email config count: `0`

Failure appears code/import-related: yes, narrowly in migration preflight code behavior.

- Import/module error count: `0`
- The failing object type is reported as `b'i'`, indicating the catalog `relkind` value was surfaced as bytes for an index. Local code inspection shows `_validate_or_plan_index` compares `row["relkind"]` to string values `("i", "I")`; a bytes value `b'i'` therefore falls through to the failure path even though it denotes an index.

## Sanitized Failure Counts

Counts from recent backend logs only; no raw log lines were printed beyond the selected redacted stack/error signature above.

- Alembic/SQLAlchemy-related count: `69`
- Missing env var count: `0`
- Migration/preflight-related count: `102`
- `retailer_prices` count: `4`
- `mv_sales_daily` count: `0`
- SMTP/email config count: `0`
- Database connection/auth keyword count: `3`
- Import/module error count: `0`

## Image And Code Provenance

- Backend container path: `./docker-entrypoint.sh`
- Backend args: none
- Backend image ID: `sha256:60895f33cc92c7be4631f09c8d0a1756c49f4fe78cd191109ccd6621c8612561`
- Backend image created: `2026-07-11T06:39:07.343076374Z`
- `docker compose images` reported `mpango-erp-backend:latest` image ID prefix `60895f33cc92`, size `291MB`, created about 10 minutes before triage.
- This confirms the backend image was newly built during the R3 deploy attempt.

## Exact Stop Condition

`mpango_prod_backend` is unhealthy/restarting after deploy. The root startup failure is Alembic migration `031_legacy_tenant_reconciliation` preflight failure.

## Recommended CTO Next Action

Approve a product fix slice for `031_legacy_tenant_reconciliation` preflight handling of PostgreSQL catalog `relkind` values returned as bytes.

Recommended implementation direction:

- Normalize `relkind` values from catalog queries before comparison and labeling, for example decode bytes to strings centrally.
- Add a focused regression test where `relkind` is `b'i'` for a valid non-unique index named `ix_retailer_prices_retailer_id`, and assert the preflight accepts it when the index targets `retailer_prices(retailer_id)`.
- Preserve existing fail-closed behavior for incompatible object types, wrong target relation, wrong uniqueness, invalid indexes, predicates, or wrong columns.
- After merge, rerun exact VPS runtime recheck from the verified backup baseline.

## Verdict

`STOP_AND_REPORT_CTO_WITH_ROOT_CAUSE`
