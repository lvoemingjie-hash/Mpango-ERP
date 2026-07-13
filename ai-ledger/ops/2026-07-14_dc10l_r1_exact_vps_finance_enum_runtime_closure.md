# DC-10L-R1 Exact VPS Finance Enum Runtime Closure

## Verdict

**PASS_DC10L_FINANCE_ENUM_RUNTIME_CLOSED**

## Deployment

| Field | Value |
|---|---|
| Target branch | `origin/product-dev-recovered` |
| Exact deployed SHA | `cb1b1fffc63ed19e320701043eed38b8f2bea0c7` |
| VPS project path | `/opt/mpango-erp` |
| Deploy command | `docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build` |
| Protected branch pushed | false |
| Release tag changed | false |
| Secrets printed in report | false |

## Backup

| Field | Value |
|---|---|
| Backup path | `/home/ubuntu/.secure-backups/dc10l_r1_20260713T185607Z.sql` |
| Backup size | `860033` bytes |
| SHA256 prefix | `7142d2ddb92d` |
| Non-empty | true |
| Readable dump format | true |

## Runtime Health

| Container | Status |
|---|---|
| `mpango_prod_backend` | healthy |
| `mpango_prod_frontend` | healthy |
| `mpango_prod_gateway` | healthy |
| `mpango_prod_postgres` | healthy |
| `mpango_prod_redis` | healthy |
| Healthy count | 5/5 |

## Alembic Proof

| Check | Result |
|---|---|
| Alembic heads | `033_order_status_enum_reconciliation (head)` |
| Alembic current | `033_order_status_enum_reconciliation (head)` |
| Multiple heads present | false |

## Live Tenant Enum Proof

| Metric | Count |
|---|---:|
| Live registered tenants checked | 8 |
| Live tenants with schema-local canonical `order_status` | 8 |
| Live tenant enum failures | 0 |
| Non-canonical live order rows | 0 |

Required assertion: `LIVE_TENANT_ENUM_FAILURE_COUNT=0`

## Credentialed Finance API Smoke

| Metric | Value |
|---|---|
| Secure smoke credential present | true |
| Secure smoke credential valid | true |
| Login status | 200 |
| Available tenant count | 1 |
| Select-tenant status | 200 |
| `/api/v1/auth/me` status | 200 |
| `/api/v1/finance/summary` status | 200 |
| `/api/v1/finance/receivables/summary` status | 200 |
| `/api/v1/finance/receivables/orders?page=1&size=20` status | 200 |
| `/api/v1/orders` status | 200 |
| API receivable count | 1 |
| DB receivable count for selected scope | 1 |
| Current scope match | true |
| `FINANCE_500_COUNT` | 0 |
| `ENUM_COERCION_ERROR_COUNT` | 0 |
| `CROSS_TENANT_DATA_INCLUDED` | false |

## Browser Proof

| Check | Result |
|---|---|
| Browser login succeeded | true |
| Finance entry clicked | true |
| Accounts Receivable rendered | true |
| `Could not load accounts receivable data` present | false |
| Finance summary network status | 200 |
| Finance receivables summary network status | 200 |
| Finance receivables orders network status | 200 |
| Console errors | 0 |
| Page errors observed | 0 |

## Sanitized Post-Deploy Log Counts

| Pattern | Count |
|---|---:|
| HTTP 500 | 0 |
| Invalid input value for enum `order_status` | 0 |
| Enum coercion / `InvalidTextRepresentation` | 0 |
| `TenantContextMissing` | 0 |
| `UndefinedTable` | 0 |
| Decimal serialization | 0 |
| Traceback | 0 |
| JWT/token/password/SMTP/DB secret indicators | 0 |

## Rollback Readiness

| Item | Status |
|---|---|
| Exact deployed SHA recorded | true |
| Pre-deploy backup available | true |
| Backup path recorded | true |
| Backup size and SHA prefix recorded | true |
| Previous runtime reports available | true |

## Final Confirmation

DC-10L migration 033 is applied as the single Alembic head, all live tenant `orders.status` columns use schema-local canonical `order_status`, Finance receivables/orders no longer returns 500 for the credentialed smoke tenant, browser Finance rendering is clean, and sanitized post-deploy logs show zero unexpected error classes.
