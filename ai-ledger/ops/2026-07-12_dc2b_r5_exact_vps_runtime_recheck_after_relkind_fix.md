# DC-2B-R5: Exact VPS Runtime Recheck After Relkind Fix

| Field | Value |
|---|---|
| Date | 2026-07-12 |
| VPS | Tencent VPS `1.14.247.12` |
| Project Path | `/opt/mpango-erp` |
| Target Branch | `origin/product-dev-recovered` |
| Target Commit | `ac99bec7e020ef3f85ebb263ee24019c37958bba` |
| Local Ops Branch | `ops/dc2b-r5-exact-vps-runtime-recheck-after-relkind-fix-2026-07-12` |
| Verdict | **PASS_RUNTIME_RECHECK_WITH_AUTH_CAVEATS** |

## Summary

DC-2B-R5 rechecked the exact VPS runtime after the DC-2M2-R2 relkind normalization fix. The prior R4 blocker was `031_legacy_tenant_reconciliation_py.PreflightFailure` caused by PostgreSQL catalog `relkind` bytes (`b'i'`) not being normalized before DC-2M2 preflight comparison.

R5 confirms the deployed exact target commit boots cleanly, Alembic reaches head/current `031_legacy_tenant_reconciliation`, DC-2M2 tenant objects exist in all active tenant schemas, product smoke routes return non-500 statuses, and the order create -> confirm -> structured payment flow completes with a paid, balanced ledger.

## Guardrails

| Guardrail | Result |
|---|---|
| Do not print secrets | PASS |
| Do not print `.env.prod` | PASS |
| Do not print `DATABASE_URL`, DB password, SMTP password, JWT, email tokens, or backup contents | PASS |
| Do not skip backup | PASS |
| Do not push `product-dev-recovered` or `platform-dev` | PASS |
| Stop on tracked dirty VPS file | PASS after count-based recheck |

## Exact Source State

| Check | Result |
|---|---|
| `origin/product-dev-recovered` | `ac99bec7e020ef3f85ebb263ee24019c37958bba` |
| VPS `HEAD` after checkout | `ac99bec7e020ef3f85ebb263ee24019c37958bba` |
| VPS tracked state after checkout | clean |
| VPS tracked state after smoke | `TRACKED_DIRTY_BYTE_COUNT=0`, clean |

## Backup

| Check | Result |
|---|---|
| Backup path | `/home/ubuntu/.secure-backups/dc2b_r5_20260711T072726Z.sql` |
| Size | `396350` bytes |
| SHA256 prefix | `9c8ea11b4cbb` |
| Metadata validation | `BACKUP_METADATA_OK=yes` |

No backup contents or database credentials were printed.

## Compose And Container Health

| Check | Result |
|---|---|
| `docker compose -f docker-compose.prod.yml --env-file .env.prod config -q` | PASS |
| `docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build` | PASS |
| `mpango_prod_backend` | healthy |
| `mpango_prod_frontend` | healthy |
| `mpango_prod_gateway` | healthy |
| `mpango_prod_postgres` | healthy |
| `mpango_prod_redis` | healthy |
| Post-smoke backend health | `BACKEND_HEALTH_AFTER_SMOKE=healthy` |

## Alembic

| Check | Result |
|---|---|
| Alembic heads | `031_legacy_tenant_reconciliation (head)` |
| Alembic current | `031_legacy_tenant_reconciliation (head)` |
| Head/current mismatch | none |

## Core Health Smoke

| Endpoint | HTTP |
|---|---|
| `/health/live` | 200 |
| `/health/ready` | 200 |
| `/openapi.json` | 200 |
| `/` | 200 |
| `/docs` | 200 |

## DC-2M2 Schema Proof

All active tenant schemas had the required DC-2M2 objects:

| Tenant Schema | Objects |
|---|---|
| `t_08177e1717de4fdb873d9e18561e732a` | `retailer_prices_table=true`, `uq=true`, `ck=true`, `ix_retailer=true`, `ix_sku=true`, `mv=true`, `mv_idx=true` |
| `t_149279156c85487cadb1c1a595b8b8d7` | `retailer_prices_table=true`, `uq=true`, `ck=true`, `ix_retailer=true`, `ix_sku=true`, `mv=true`, `mv_idx=true` |
| `t_550e8400e29b41d4a716446655440000` | `retailer_prices_table=true`, `uq=true`, `ck=true`, `ix_retailer=true`, `ix_sku=true`, `mv=true`, `mv_idx=true` |

## Sanitized Log Scan

Initial post-deploy scan:

| Pattern Group | Count |
|---|---:|
| `LOG_COUNT_RELKIND_BI_PREFLIGHT` | 0 |
| `LOG_COUNT_031_FAILURE` | 0 |
| `LOG_COUNT_DECIMAL_SERIALIZATION` | 0 |
| `LOG_COUNT_TENANT_CONTEXT_MISSING` | 0 |
| `LOG_COUNT_UNDEFINED_TABLE` | 0 |
| `LOG_COUNT_RETAILER_PRICES_DDL_FAILURE` | 0 |
| `LOG_COUNT_MV_SALES_DAILY_MISSING` | 0 |
| `LOG_COUNT_SECRET_LEAK_KEYWORDS` | 0 |

Post-smoke scan:

| Pattern Group | Count |
|---|---:|
| `POST_SMOKE_LOG_COUNT_KNOWN_FAILURES` | 0 |
| `POST_SMOKE_LOG_COUNT_500` | 0 |
| `POST_SMOKE_LOG_COUNT_SECRET_KEYWORDS` | 0 |

## Authenticated And Product Smoke

No real owner credential source was available in safe non-secret form. To avoid printing or creating credentials, the smoke selected an existing active tenant/user inside the backend container, minted a short-lived contextual JWT in process, did not print the JWT, and exercised runtime routes with sanitized status output only.

| Check | HTTP / Result |
|---|---|
| Context selected | `CONTEXT_SELECTED=yes` |
| `GET /api/v1/auth/me` | 200 |
| `GET /api/v1/skus?page=1&size=1` | 200 |
| `GET /api/v1/inventory/stocks?page=1&size=1` | 200 |
| `GET /api/v1/intake/workspaces?page=1&page_size=1` | 200 |
| `GET /api/v1/retailers/bindings` | 200 |
| `GET /api/v1/payments?page=1&size=1` | 200 |
| `POST /api/v1/payments` legacy write path | 409 |
| `POST /api/v1/retailers/register` with invalid invitation | 400, no 500 |
| `POST /api/v1/orders` | 201 |
| `POST /api/v1/orders/{order_id}/confirm` | 200 |
| `POST /api/v1/orders/{order_id}/pay` structured payment | 200 |
| Final order status | `paid` |
| Ledger balanced | `True` |
| Smoke skips | `SMOKE_SKIP_COUNT=0` |
| Smoke failures | `SMOKE_FAILURE_COUNT=0` |

## Caveats

1. Real `/api/v1/auth/login` and `/api/v1/auth/select-tenant` were not executed because no safe smoke credential source was available and secret printing was forbidden.
2. The legacy payment route implementation raises route-specific detail code `PAYMENT_WRITE_PATH_DISABLED`, but the global `HTTPException` handler normalizes all HTTP 409 responses to public response code `CONFLICT`. Runtime therefore proved HTTP 409 and no 500; it did not expose literal public code `PAYMENT_WRITE_PATH_DISABLED`.
3. One earlier remote command printed a git fatal message due to wrapper context/quoting, before the corrected count-based tracked-clean check. No secret content was printed.

## Stop-Condition Review

| Stop Condition | Result |
|---|---|
| Tracked dirty file exists | PASS, count-based recheck showed 0 bytes |
| Backup fails | PASS |
| Compose/deploy fails | PASS |
| Backend unhealthy/restarting | PASS |
| Alembic head/current mismatch | PASS |
| `031` preflight failure remains | PASS |
| Any canonical smoke returns 500 | PASS |
| DC-2M2 schema objects missing | PASS |
| Any secret printed | PASS |

## Verdict

**PASS_RUNTIME_RECHECK_WITH_AUTH_CAVEATS**

The R4 relkind blocker is resolved at exact VPS runtime for target commit `ac99bec7e020ef3f85ebb263ee24019c37958bba`. Backend health, Alembic head/current, DC-2M2 schema proof, sanitized log scans, authenticated read routes, inventory, intake, retailer binding, payments read, legacy payment 409, and order create-confirm-pay ledger balance all passed without 500s or secret disclosure.
