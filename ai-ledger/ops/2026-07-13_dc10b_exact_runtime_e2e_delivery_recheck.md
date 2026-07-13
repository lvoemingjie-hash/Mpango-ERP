# DC-10B Exact Runtime End-to-End Delivery Recheck

| Field | Value |
|---|---|
| Date | 2026-07-13 |
| VPS | Tencent VPS `1.14.247.12` |
| Project path | `/opt/mpango-erp` |
| Target | `release-2026-07-13 @ 547b0b294aa387d6179f53eca3ec162532a1e29e` |
| Local ops branch | `ops/dc10b-exact-runtime-e2e-delivery-recheck-2026-07-13` |
| Verdict | **HARD_STOP_EXPORT_RUNTIME_FAILURE** |

## Summary

DC-10B reached the export create/status phase and then hard-stopped. Signup, verification, owner credential setup, login, tenant selection, password reset, SKU intake, stock setup, retailer pricing, order confirm, and payment all passed on the exact release runtime. The required export job failed permanently with `Tenant context required`, so export status/download could not be completed.

## Guardrails

| Guardrail | Result |
|---|---|
| No raw tokens/JWTs/passwords in report | PASS |
| No mailbox address in report | PASS |
| No `.env.prod` contents printed | PASS |
| Protected branches not pushed | PASS |

## Preflight, Backup, Deploy

| Check | Result |
|---|---|
| Local tracked tree | clean; unrelated untracked artifacts ignored |
| VPS tracked tree | clean before checkout |
| VPS `HEAD` | `547b0b294aa387d6179f53eca3ec162532a1e29e` |
| DB backup | `/home/ubuntu/.secure-backups/dc10b_20260713T005936Z.sql` |
| DB backup size | `461831` bytes |
| DB backup SHA256 prefix | `9b585a329672` |
| Compose config | PASS |
| Rebuild/recreate | PASS, `docker compose ... up -d --build --force-recreate` |
| Containers | all 5 healthy |
| `/health/live` | 200 |
| `/health/ready` | 200 |
| `/openapi.json` | 200 |
| `/` | 200 |

## Migration And Tenant Reconciliation

| Check | Result |
|---|---|
| Alembic current | `031_legacy_tenant_reconciliation (head)` |
| Alembic heads | `031_legacy_tenant_reconciliation (head)` |
| Active tenant schemas reconciled | PASS |
| Active tenants checked | 5 |
| Missing active tenant schemas | 0 |
| Missing `orders` table | 0 |
| Missing `skus` table | 0 |

Note: this release has `public.platform_tenants` empty; active tenant reconciliation was performed from `public.wholesalers.status = 'active'` plus `public.tenant_registrations.tenant_schema`.

## Runtime Flow Results

| Flow Step | Result |
|---|---|
| Disposable mailbox created | PASS |
| `POST /api/v1/auth/signup` | 202 |
| Verification email received | PASS |
| `POST /api/v1/auth/verify-email` | 200 |
| Owner setup email received | PASS |
| `POST /api/v1/auth/onboarding/setup-credential` | 200 |
| `POST /api/v1/auth/login` | 200, 1 tenant |
| `POST /api/v1/auth/select-tenant` | 200 |
| `GET /api/v1/auth/me` | 200, 43 permissions |
| `POST /api/v1/auth/forgot-password` | 200 |
| Reset email received | PASS |
| `POST /api/v1/auth/reset-password` | 200 |
| Old password after reset | 401 |
| New password after reset | 200 |
| `POST /api/v1/skus` | 201 |
| `POST /api/v1/inventory/adjust` | 200 |
| `POST /api/v1/invitations` | 201 |
| `POST /api/v1/retailers/register` | 201 |
| `PUT /api/v1/pricing/prices` | 200 |
| `POST /api/v1/orders` | 201 |
| `POST /api/v1/orders/{id}/confirm` | 200, `confirmed` |
| `POST /api/v1/orders/{id}/pay` | 200, `paid` |
| `POST /api/v1/exports` | 202 |
| Export background job | FAILED |
| Export download | NOT RUN, blocked by failed job |

## Blocking Failure

| Evidence | Value |
|---|---|
| Failed job status | `failed` |
| Attempts | 2 |
| Error | `Tenant context required` |
| HTTP create route | 202 Accepted |
| HTTP status route | 200, reported failed job |

Recent backend evidence showed the export job was enqueued with tenant metadata, then the detached worker failed twice with `Tenant context required` and marked the job permanently failed. This blocks the required export status/download path on the exact delivery target.

## Not Executed After Hard Stop

The following required checks were intentionally not continued after the blocking export failure:

| Check | Status |
|---|---|
| Export download | blocked |
| Malformed export IDs | not run after hard stop |
| Tenant isolation negative case | not run after hard stop |
| Insufficient-permission negative case | not run after hard stop |
| Desktop/mobile browser width checks | not run after hard stop |
| Deep-link refresh checks | not run after hard stop |

## Log And Security Scan

| Pattern | Count |
|---|---:|
| Backend 500s | 0 |
| Traceback | 0 |
| `TenantContextMissing` / `Tenant context required` | 2 |
| `UndefinedTable` | 0 |
| Serialization errors | 0 |
| Secret leakage patterns | 0 |

## Temporary Data

No destructive cleanup was performed after the hard stop so the failure remains diagnosable.

| Retained Item | Count |
|---|---:|
| DC-10B active wholesaler tenant | 1 |
| DC-10B pending signup registration | 1 |
| DC-10B failed export job | 1 |

## Verdict

**HARD_STOP_EXPORT_RUNTIME_FAILURE**

The exact release target is not delivery-ready because the real runtime export worker fails with `Tenant context required`, preventing the required export status/download completion. No secrets were exposed in this report.
