# DC-10I Exact VPS Redeploy + Runtime Financial Integrity Closure

| Field | Value |
|---|---|
| Date | 2026-07-13 |
| Owner | OPS / OpenCode |
| VPS | Tencent VPS `1.14.247.12` |
| Project path | `/opt/mpango-erp` |
| Target branch | `origin/product-dev-recovered` |
| Exact deployed SHA | `3dd881165f30aae283cf99bb830125293e1b963a` |
| Precondition | DC-10H independent validation PASS, `reports/lubuntu-validation @ 3362d15` |
| Ops branch | `ops/dc10i-exact-vps-runtime-integrity-closure-2026-07-13` |
| Verdict | **PASS_DC10I_RUNTIME_INTEGRITY_CLOSED** |

## Guardrails

| Guardrail | Result |
|---|---|
| No credentials/JWTs/tokens/emails/SMTP values/DB URLs in report | PASS |
| No protected branch pushed | PASS |
| No release tag moved/recreated | PASS |
| `release-2026-07-13` untouched | PASS |

## Preflight, Backup, Deploy

| Check | Result |
|---|---|
| VPS tracked worktree before checkout | clean |
| `origin/product-dev-recovered` target | `3dd881165f30aae283cf99bb830125293e1b963a` |
| VPS checked-out SHA | `3dd881165f30aae283cf99bb830125293e1b963a` |
| VPS tracked worktree after checkout | clean |
| PostgreSQL backup | `/home/ubuntu/.secure-backups/dc10i_20260713T121915Z.sql` |
| Backup byte size | `530090` |
| Backup SHA256 prefix | `8f85eafbfe6c` |
| Compose config | PASS, `docker compose -f docker-compose.prod.yml --env-file .env.prod config -q` |
| Deploy command | PASS, `docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build` |
| Backend/frontend recreated from exact source | PASS |

## Container And Health Results

| Check | Result |
|---|---|
| Mpango containers healthy | 5/5 |
| `mpango_prod_backend` | healthy |
| `mpango_prod_frontend` | healthy |
| `mpango_prod_gateway` | healthy |
| `mpango_prod_postgres` | healthy |
| `mpango_prod_redis` | healthy |
| `/health/live` | 200 |
| `/health/ready` | 200 |
| `/` | 200 |
| `/openapi.json` | 200 |
| `/docs` | 200 |

## Alembic Evidence

| Check | Result |
|---|---|
| Alembic current | `032_payment_method_integrity (head)` |
| Alembic heads | `032_payment_method_integrity (head)` |
| Head count | 1 |

## DC-10F Payment Integrity Runtime Proof

| Check | Result |
|---|---|
| Active registered tenant schemas checked | 3 |
| Compatible `ck_payments_method_canonical` constraints | 3 |
| Bad/missing compatible constraints | 0 |
| Fresh signup/login/select-tenant/auth-me | PASS, 43 permissions |
| Catalog SKU intake | PASS |
| Stock setup | PASS |
| Retailer invitation/register | PASS |
| Retailer pricing | PASS |
| Cash order pay via canonical route | PASS, status `paid` |
| Transfer order pay via canonical route | PASS, status `paid` |
| Credit valid product-state path | PASS, status `paid` |
| Invalid `method=banana` | controlled 422 |
| Invalid payment side effects | unchanged |

### Payment Side-Effect Comparison

| Runtime Row | Order Status | Methods | Payment Count | Paid Amount | Ledger Rows | Ledger Sum | Receivable Sum | Retailer Outstanding |
|---|---|---|---:|---:|---:|---:|---:|---:|
| Cash payment | `paid` | `cash` | 1 | 50.00 | 2 | 0.0000 | -50.0000 | -50.00 |
| Transfer payment | `paid` | `transfer` | 1 | 50.00 | 2 | 0.0000 | -50.0000 | -50.00 |
| Credit valid path | `paid` | `credit` | 1 | 50.00 | 0 | 0 | 0 | -50.00 |
| Invalid banana attempt | `confirmed` | `none` | 0 | 0 | 0 | 0 | 0 | -50.00 |

Invalid payment before/after hash comparison matched, and the final DB state confirms the invalid request did not create payments, change order status, change paid amount, add receivable movement, or add ledger rows.

## DC-10E Export Runtime Proof

| Check | Result |
|---|---|
| Authenticated tenant export create | 202 |
| Export terminal state | `completed` |
| Export download | 200 with non-empty response |
| Export job DB status | `completed` |
| Export job tenant payload | present |
| Export job error | empty |
| Wrong-tenant well-formed export ID | hidden with 404 |
| Malformed export status ID | controlled 400 |
| Malformed export download ID | controlled 400 |
| Worker tenant-context error | 0 occurrences after redeploy |
| Raw enqueue exception text | none observed |

The backend log contains one `Export job completed` line after redeploy and zero `Tenant context required` matches.

## DC-10G Platform UUID Runtime Proof

No `PLATFORM_OPERATOR_SECRET` was configured in the backend container, so the browser-supported identity-only platform credential path was used. A disposable test identity was safely promoted inside its own test tenant with a `super_admin` role, then used only as an identity-only platform operator token.

| Check | Result |
|---|---|
| Identity-only platform operator token | PASS |
| Malformed platform tenant UUID | controlled 404 |
| Well-formed missing platform tenant UUID | controlled 404 |
| Malformed audit UUID | controlled 404 |
| Well-formed missing audit UUID | controlled 404 |
| Unauthenticated tenant detail | 401 |
| Unauthenticated audit detail | 401 |
| Platform health | 200 |
| Platform info | 200 |
| Tenant contextual token against platform route | denied with 401 |
| UUID parser/driver traceback in logs | 0 |

## Regression Smoke

| Check | Result |
|---|---|
| Login -> select tenant -> `/api/v1/auth/me` | PASS |
| SKU read path | PASS |
| Orders read path | PASS |
| Dashboard/finance summary read path | PASS |
| Desktop `/login` browser load | PASS, 0 console errors |
| Mobile `/orders` deep link | redirected to `/login`, 0 console errors |
| Mobile deep-link refresh | PASS, 0 console errors |
| Payment modal label/canonical method | PASS |
| Targeted frontend test | `npx vitest run src/tests/PaymentRecordModal.test.tsx`, 1 passed |

Payment modal proof: frontend option label is `Bank Transfer / Mobile Money` with canonical value `transfer`, and the targeted test asserts submit payload `method: 'transfer'`.

## Sanitized Log Scan

| Pattern | Unexpected Count |
|---|---:|
| HTTP 500 | 0 |
| Traceback | 0 |
| `TenantContextMissing` / `Tenant context required` | 0 |
| `UndefinedTable` | 0 |
| Decimal serialization errors | 0 |
| Invalid UUID driver errors | 0 |
| Payment CHECK violations | 0 |
| Credential indicators / DB URLs / Bearer tokens | 0 |

Benign classified matches:

| Match | Count | Classification |
|---|---:|---|
| `ensured ck_payments_method_canonical` | 1 | expected migration/reconciliation evidence |
| non-credential Redis URL field | 1 | non-secret internal service URL, not a DB URL or credential |
| `Export job completed` | 1 | expected export completion evidence |

## Retained Temporary Data

No destructive cleanup was performed because the task requested runtime evidence closure and retained artifacts help audit the run.

| Retained Item | Count |
|---|---:|
| DC-10I tenant registrations | 5 |
| DC-10I active tenant registrations | 5 |
| DC-10I completed export jobs | 1 |
| DC-10I failed export jobs | 0 |

## Rollback Readiness

| Rollback Asset | Result |
|---|---|
| Database backup available | `/home/ubuntu/.secure-backups/dc10i_20260713T121915Z.sql` |
| Backup validated non-empty | PASS |
| Exact deployed SHA known | `3dd881165f30aae283cf99bb830125293e1b963a` |
| Previous release SHA known from prior DC-10B report | `547b0b294aa387d6179f53eca3ec162532a1e29e` |

## Verdict

**PASS_DC10I_RUNTIME_INTEGRITY_CLOSED**

DC-10E export worker tenant context, DC-10F payment method integrity, and DC-10G platform UUID/error hardening are closed on the exact VPS runtime candidate. No protected branch or release tag was pushed, moved, or recreated.
