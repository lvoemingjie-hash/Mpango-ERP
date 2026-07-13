# DC-10K-R1 Exact VPS Finance Runtime Closure

| Field | Value |
|---|---|
| Date | 2026-07-13 |
| Owner | OPS / OpenCode |
| VPS | Tencent VPS `1.14.247.12` |
| Project path | `/opt/mpango-erp` |
| Target branch | `origin/product-dev-recovered` |
| Exact target SHA | `280c5629ee46efbcb9b890c105320bfdac8bc694` |
| Deployed SHA | `280c5629ee46efbcb9b890c105320bfdac8bc694` |
| Ops branch | `ops/dc10k-r1-exact-vps-finance-runtime-closure-2026-07-13` |
| Verdict | **PASS_DC10K_FINANCE_RUNTIME_CLOSED** |

## Guardrails

| Guardrail | Result |
|---|---|
| No protected branch pushed | PASS |
| No release tag moved/recreated | PASS |
| No `.env.prod`, passwords, JWTs, SMTP values, DB URLs, or customer data in report | PASS |
| No empty-state-only smoke | PASS |

## Preflight And Backup

| Check | Result |
|---|---|
| `git fetch origin --prune` | PASS |
| `origin/product-dev-recovered` | `280c5629ee46efbcb9b890c105320bfdac8bc694` |
| VPS tracked worktree before checkout | clean |
| VPS-side backup path | `/home/ubuntu/.secure-backups/dc10k_r1_20260713T150946Z.sql` |
| VPS-side backup size | `857877` bytes |
| VPS-side backup SHA256 prefix | `7f7b2b867627` |

## Deploy Evidence

| Check | Result |
|---|---|
| Checkout exact target | PASS |
| VPS `HEAD` after checkout/deploy | `280c5629ee46efbcb9b890c105320bfdac8bc694` |
| Compose config validation | PASS |
| Deploy command | `docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build` |
| Backend recreated | PASS |
| Frontend recreated | PASS |
| Mpango containers healthy | 5/5 |
| `mpango_prod_backend` | healthy |
| `mpango_prod_frontend` | healthy |
| `mpango_prod_gateway` | healthy |
| `mpango_prod_postgres` | healthy |
| `mpango_prod_redis` | healthy |
| VPS tracked worktree after smoke | clean |

## Alembic Evidence

| Check | Result |
|---|---|
| Alembic current | `032_payment_method_integrity (head)` |
| Alembic head | `032_payment_method_integrity (head)` |

## Credentialed Finance API Smoke

The credentialed smoke used a non-customer test tenant. The tenant initially had zero orders, so minimal runtime data was created through normal APIs only: invitation, retailer registration, SKU creation, inventory adjustment, retailer pricing, order creation, and order confirmation. No business data was inserted or updated directly in the database.

| Check | Result |
|---|---|
| Login | 200 |
| Select tenant | 200 |
| Initial `/api/v1/orders` | 200, empty before setup |
| API-only minimal receivable setup | PASS |
| `GET /api/v1/finance/summary` | 200, valid JSON |
| `GET /api/v1/finance/receivables/summary` | 200, valid JSON |
| `GET /api/v1/finance/receivables/orders?page=1&size=20` | 200, valid JSON |
| Receivable-order result count | 1 |
| `age_days` values | non-negative integers |
| Naive/aware datetime error response | none |
| Generic Finance error response | none |
| Finance 500 during credentialed API smoke | 0 |

## Sanitized DB Aggregate Comparison

| Check | Result |
|---|---|
| Current wholesaler DB receivable-order count | 1 |
| Current wholesaler DB summary total outstanding | `0.00` |
| API receivables summary total outstanding | `0.0` |
| Other wholesalers with outstanding balances present in DB | yes, 3 |
| Other-wholesaler outstanding total present in DB | `-2621.90` |
| `CURRENT_WHOLESALER_SCOPE_MATCH` | `true` |
| `CROSS_WHOLESALER_DATA_INCLUDED` | `false` |

## Browser Proof

| Check | Result |
|---|---|
| Deployed app opened with Playwright | PASS |
| Sidebar label `Finance` present | PASS |
| Sidebar label `Money` absent | PASS |
| Finance click navigated to Accounts Receivable | PASS |
| Accounts Receivable page rendered | PASS |
| `Could not load accounts receivable data` | absent |
| Current-navigation console errors | 0 |
| Page error / 403 toast / 500 toast | none observed |
| Finance browser network statuses | `finance/summary=200`, `receivables/summary=200`, `receivables/orders=200` |
| Sanitized screenshot | `dc10k-r1-finance-redacted.png` |

## Regression Sanity

| Check | Result |
|---|---|
| Login | 200 |
| Select tenant | 200 |
| `/api/v1/auth/me` | 200 |
| `GET /api/v1/orders` | 200 |
| Canonical payment validation path | controlled 422, no 500 |
| Legacy `POST /api/v1/payments` with valid body | disabled with 409 |

## Post-Smoke Log Scan

Backend logs since deployment were scanned for the required unexpected patterns.

| Pattern | Unexpected Count |
|---|---:|
| `can't subtract offset-naive and offset-aware datetimes` | 0 |
| `TypeError` | 0 |
| `HTTP 500` | 0 |
| `TenantContextMissing` | 0 |
| `UndefinedTable` | 0 |
| Decimal serialization errors | 0 |
| `traceback` | 0 |
| JWT/password/SMTP/DB credential leakage indicators | 0 |

## Verdict

**PASS_DC10K_FINANCE_RUNTIME_CLOSED**

The exact DC-10K merge commit was deployed on the VPS, Finance receivables endpoints returned 200 with valid JSON against non-empty runtime receivable-order data, browser rendering of Accounts Receivable succeeded without current-navigation console errors or Finance 500s, and cross-wholesaler data was not included.
