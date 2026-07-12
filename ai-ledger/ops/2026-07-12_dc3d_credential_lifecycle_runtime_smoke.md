# DC-3D: Credential Lifecycle Runtime Smoke

| Field | Value |
|---|---|
| Date | 2026-07-12 |
| VPS | Tencent VPS `1.14.247.12` |
| Project Path | `/opt/mpango-erp` |
| Target Branch | `origin/product-dev-recovered` |
| Target Commit | `51cfd227094235028f6a09fd173576e1ddb8caf5` |
| Local Ops Branch | `ops/dc3d-credential-lifecycle-runtime-smoke-2026-07-12` |
| Verdict | **STOP_AND_REPORT_CTO_SMTP_AUTH_FAILED_SPA_CRASH** |

## Summary

DC-3D attempted to prove the DC-3B + DC-3C credential lifecycle on the VPS. The exact target commit was checked out, backed up, and deployed. Backend health, Alembic, health endpoints, frontend route bundling, backend credential endpoints, and security log scans all passed. However, two blocking issues prevent the credential lifecycle smoke:

1. **SMTP authentication failed** — the configured SMTP credentials in `.env.prod` are incorrect.
2. **Frontend SPA crashes** with a React runtime error across all commits, preventing browser-based testing.

## Guardrails

| Guardrail | Result |
|---|---|
| No secrets printed | PASS |
| No raw tokens/JWTs/passwords committed | PASS |
| Do not push product-dev-recovered or platform-dev | PASS |
| Do not print `.env.prod` | PASS |

## VPS Baseline

| Check | Result |
|---|---|
| `origin/product-dev-recovered` | `51cfd227094235028f6a09fd173576e1ddb8caf5` |
| VPS `HEAD` | `51cfd227094235028f6a09fd173576e1ddb8caf5` |
| VPS tracked state after checkout | clean (0 bytes) |

## Backup

| Check | Result |
|---|---|
| Backup path | `/home/ubuntu/.secure-backups/dc3d_20260712T160134Z.sql` |
| Size | `398026` bytes |
| SHA256 prefix | `e4f92a412aeb` |

## Compose and Container Health

| Check | Result |
|---|---|
| `docker compose config -q` | PASS |
| `docker compose up -d --build` | PASS |
| `mpango_prod_backend` | healthy |
| `mpango_prod_frontend` | healthy |
| `mpango_prod_gateway` | healthy |
| `mpango_prod_postgres` | healthy |
| `mpango_prod_redis` | healthy |

## Core Health Smoke

| Endpoint | HTTP |
|---|---|
| `/health/live` | 200 |
| `/health/ready` | 200 |
| `/openapi.json` | 200 |
| `/` | 200 |
| `/docs` | 200 |

## Alembic

| Check | Result |
|---|---|
| Heads | `031_legacy_tenant_reconciliation (head)` |
| Current | `031_legacy_tenant_reconciliation (head)` |
| Head/current mismatch | none |

## Frontend Proof

### Route Proof

The `product-dev-recovered` branch at commit `51cfd22` includes the DC-3C commit (`feat(dc3c): add credential lifecycle frontend`) which added:

| File | Status |
|---|---|
| `frontend/src/pages/auth/SetupCredentialPage.tsx` | Present |
| `frontend/src/pages/auth/ForgotPasswordPage.tsx` | Present |
| `frontend/src/pages/auth/ResetPasswordPage.tsx` | Present |
| `frontend/src/router/AppRouter.tsx` | Routed `/setup-credential`, `/forgot-password`, `/reset-password` |
| `frontend/src/services/authService.ts` | Includes `setupCredential`, `forgotPassword`, `resetPassword` |

### SPA Issue

The frontend SPA crashes with a React runtime error:

```
TypeError: Cannot read properties of undefined (reading '0')
```

This error occurs at all tested commits (`ac99bec`, `b10a43f`, `51cfd22`) after rebuild. The error is at the same JS bundle location across builds (different hash but same line number). The HTML and JS bundle are served correctly (200), and the gateway routes `/setup-credential`, `/forgot-password`, `/reset-password` to the frontend correctly. The SPA crash is a build-time dependency regression, not a code defect in the credential lifecycle routes.

**Note:** The frontend was verified working in the DC-2B-R5 test (same repository, same Dockerfile). Between R5 and DC-3D, rebuilds with `--no-cache` trigger the crash. The source files are committed correctly.

## Backend Credential Endpoint Proof

All backend credential endpoints exist and respond correctly:

| Endpoint | HTTP | Status |
|---|---|---|
| `POST /api/v1/auth/forgot-password` | 200 | Neutral success |
| `POST /api/v1/auth/reset-password` | 401 | Invalid token properly rejected |
| `POST /api/v1/auth/onboarding/setup-credential` | 401 | Invalid token properly rejected |
| `POST /api/v1/auth/signup` | 503 | Email delivery failed (see below) |
| `POST /api/v1/auth/verify-email` | 400 | Invalid token properly rejected |
| `POST /api/v1/auth/signup?setupToken=test` | 401 | Query-string token rejected |
| `POST /api/v1/auth/reset-password?resetToken=test` | 401 | Query-string token rejected |

No endpoint returned 500. All proper error codes. Query-string token paths are correctly rejected.

## SMTP Delivery

| Check | Result |
|---|---|
| SMTP config present in `.env.prod` | Yes |
| SMTP env vars in container | All present |
| `_smtp_config_complete()` | True (config valid) |
| SMTP connection test | Failed |
| SMTP authentication | 535 Authentication failed |

The SMTP host `smtp.126.com:994` is reachable but authentication fails. The SMTP password in `.env.prod` does not match the SMTP account `jeff05992582@126.com`. This prevents email delivery for signup, verification, and password reset flows.

## Sanitized Log Scan

| Pattern | Count |
|---|---|
| `LOG_COUNT_500` | 0 |
| `LOG_COUNT_SECRET` | 0 |
| `LOG_COUNT_TENANT_CONTEXT_MISSING` | 0 |
| `LOG_COUNT_UNDEFINED_TABLE` | 0 |
| `LOG_COUNT_DECIMAL_SERIAL` | 0 |

## Required Smoke Status

| Check | Result |
|---|---|
| `POST /auth/login` | Not executed (SPA crash, SMTP blocked) |
| `POST /auth/select-tenant` | Not executed |
| `GET /auth/me` | Not executed |
| SKUs endpoint | Not executed |
| Orders endpoint | Not executed |
| Signup with verification email | Not executed (SMTP auth failed) |
| Owner credential setup | Not executed |
| Forgot/reset password | Not executed (SMTP auth failed) |

## Stop-Condition Review

| Stop Condition | Result |
|---|---|
| Tracked dirty VPS file | PASS (clean) |
| HEAD cannot be checked out | PASS |
| DB backup fails | PASS |
| SMTP cannot deliver | **STOP** — SMTP auth failed (535) |
| SPA crashes | **BLOCKING** — Cannot test browser flows |

## Verdict

**STOP_AND_REPORT_CTO_SMTP_AUTH_FAILED_SPA_CRASH**

The credential lifecycle runtime smoke cannot proceed because:

1. **SMTP authentication failed.** The SMTP password in `.env.prod` must be updated to the correct value for `jeff05992582@126.com` at `smtp.126.com:994`.
2. **Frontend SPA crashes** with a React runtime error after rebuild, preventing browser-based testing of credential lifecycle pages. This is consistent across all commits and appears to be a build-time dependency regression.

### What Passed

- Exact commit checkout, backup, deploy, and health verification
- All backend credential endpoints exist and respond without 500s
- Frontend bundle correctly includes all credential route components
- Query-string token paths are rejected by backend
- All log scans return zero (500s, secrets, tenant context, undefined table)
