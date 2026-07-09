# DC-1D Final RC Runtime Recheck

- **Date**: 2026-07-09
- **Task ID**: DC-1D
- **Target commit**: `3d302222c2700b8f2adbb2d2339732f5255278fd`
- **Target branch**: `origin/product-dev-recovered`
- **Ops branch**: `ops/dc1d-final-rc-runtime-recheck-2026-07-09`
- **Verdict**: `STOP_AND_REPORT_CTO`

## Summary

The final RC runtime recheck was executed on the VPS and the target commit was deployed.
Exact HEAD matched `3d302222c2700b8f2adbb2d2339732f5255278fd`, pre-recheck backup succeeded,
`docker compose ... up -d --build` succeeded, Mpango containers were healthy, core health
endpoints were 200, and Alembic head/current stayed at
`030_platform_backup_status_source`.

The release candidate is **not sign-off ready** because product smoke exposed a new 500 on
the canonical payment write path `POST /api/v1/orders/{order_id}/pay`. The failure is on the
validation/error path itself: backend logs show `TypeError: Object of type Decimal is not JSON serializable`
inside `core.error_codes.validation_exception_handler`, so an invalid client request is escalating
to HTTP 500 instead of remaining on a 4xx path.

Fresh U6 new-mailbox onboarding was also not fully re-proven on this commit because the current
SMTP provider still requires a real deliverable recipient mailbox and the fresh synthetic 126
mailbox attempt was rejected by the provider path and surfaced by the app as
`EMAIL_DELIVERY_NOT_CONFIGURED`. No manual DB repair or off-script workaround was used.

## 1. Exact Checkout

VPS commands executed:

```bash
git fetch origin
git checkout -B product-dev-recovered origin/product-dev-recovered
git rev-parse HEAD
```

Result:

| Check | Result |
|---|---|
| `git rev-parse HEAD` | `3d302222c2700b8f2adbb2d2339732f5255278fd` |
| Matches target | Yes |

Observed note:

- `git checkout -B ...` reported a pre-existing local VPS worktree modification:
  `M docker-compose.prod.yml`
- `git status --short` after deploy still showed `M docker-compose.prod.yml`
- This file was **not edited during DC-1D**; the recheck used the already-present VPS ops drift

## 2. Pre-Recheck Backup

| Field | Value |
|---|---|
| Backup path | `/home/ubuntu/.secure-backups/mpango_erp_dc1d_20260709-230343.sql` |
| Size | `395948` bytes |
| SHA256 prefix | `baef2577ce175dd9` |

Backup content was not printed.

## 3. Rebuild / Redeploy

Deploy command executed:

```bash
cd /opt/mpango-erp
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
```

Result: completed successfully.

## 4. Container Health

Mpango production containers after deploy:

| Container | Status |
|---|---|
| `mpango_prod_backend` | healthy |
| `mpango_prod_frontend` | healthy |
| `mpango_prod_gateway` | healthy |
| `mpango_prod_postgres` | healthy |
| `mpango_prod_redis` | healthy |

Notes:

- Mpango runtime health: **5/5 healthy**
- An unrelated `procurement-workspace` container was also healthy, but it is outside the Mpango RC scope

## 5. Core Health Endpoints

| Endpoint | HTTP | Result |
|---|---|---|
| `/health/live` | 200 | PASS |
| `/health/ready` | 200 | PASS |
| `/openapi.json` | 200 | PASS |
| `/` | 200 | PASS |
| `/docs` | 200 | PASS |

## 6. Alembic / DB Baseline

| Check | Result |
|---|---|
| `alembic heads` | `030_platform_backup_status_source (head)` |
| `alembic current` | `030_platform_backup_status_source (head)` |
| Multiple heads | No |
| Missing migration/table | Not observed |

## 7. U6 Onboarding Smoke

### Fresh new-mailbox recheck

Attempted a fresh public signup using the current SMTP provider and a synthetic new 126 mailbox
that was not a `+alias`.

| Step | Result |
|---|---|
| Signup | `503 SERVICE_UNAVAILABLE` |
| Returned error | `EMAIL_DELIVERY_NOT_CONFIGURED` |

Additional evidence gathered during the same run:

- Backend runtime settings resolved to `EMAIL_PROVIDER=smtp` and `EMAIL_DELIVERY_MODE=smtp`
- SMTP host/user/from/port were present in the running backend container
- Direct SMTP authentication to the configured provider succeeded from inside the backend container

Interpretation:

- This matches the already-documented runtime provider constraint: the current provider requires a
  real deliverable recipient mailbox, and synthetic/non-existent 126 recipients are rejected on the
  delivery path and collapsed by the app into `EMAIL_DELIVERY_NOT_CONFIGURED`
- The only confirmed real mailbox from prior runtime proof already has an active live registration,
  so a fresh end-to-end U6 new-mailbox chain could not be re-proven here without stepping outside
  the approved process
- No manual tenant/admin/RBAC creation and no DB repair was attempted

### Existing active owner path

To confirm auth and tenant context still work for the known active owner path:

| Step | HTTP | Result |
|---|---|---|
| Login | 200 | PASS |
| `available_tenants` | N/A | `2` returned |
| Select tenant | 200 | PASS |
| `/api/v1/auth/me` | 200 | PASS |

U6 conclusion:

- Existing active owner login/context path is healthy
- Fresh new-mailbox U6 onboarding was **not fully re-proven** in DC-1D because of current mailbox/provider constraints

## 8. Product Smoke

Tenant-scoped product checks were run after successful login and tenant selection.

| Check | HTTP | Result |
|---|---|---|
| `GET /api/v1/skus` | 200 | PASS |
| `GET /api/v1/intake/workspaces` | 200 | PASS |
| `GET /api/v1/orders` | 200 | PASS |
| `GET /api/v1/inventory/stocks` | 200 | PASS |
| `GET /api/v1/inventory/logs` | 200 | PASS |
| `POST /api/v1/payments` with valid shape | 409 | PASS (disabled write path) |
| `POST /api/v1/orders/{id}/pay` with invalid payload | 500 | **STOP** |

Important details:

- The legacy payments route returned HTTP 409 as expected; the response message still contained
  `PAYMENT_WRITE_PATH_DISABLED`, but the top-level error envelope normalized the code to `CONFLICT`
- The canonical payment route returned:

```json
{"code":"INTERNAL_SERVER_ERROR","message":"An internal server error occurred. Please contact support."}
```

- Backend traceback showed the failing path was the validation exception handler, not tenant context:

```text
TypeError: Object of type Decimal is not JSON serializable
```

This is a **new 500 in product smoke**, which is an explicit DC-1D stop condition.

## 9. Platform Smoke

| Check | HTTP | Result |
|---|---|---|
| `GET /api/v1/platform/health` | 200 | PASS |
| `GET /api/v1/platform/info` | 200 | PASS |
| `GET /api/v1/platform/tenants/` with tenant token | 401 | PASS (boundary enforced) |
| `GET /api/v1/platform/stats/` with tenant token | 401 | PASS (boundary enforced) |

Platform notes:

- Tenant token could not access platform-only routes, which is correct
- No `TenantContextMissing` was observed in the runtime log scan
- No new platform-path 500 was observed during the platform smoke itself

## 10. Rollback Readiness Spot Check

No restore was executed.

| Check | Result |
|---|---|
| DC-1A backup still exists | PASS |
| DC-1C runbook file exists in repo | PASS -- `ai-ledger/ops/2026-07-09_dc1c_rollback_runbook_confirmation.md` |
| Restore tool path still available | PASS -- `psql` present in `mpango_prod_postgres` |
| `docker compose ... config --quiet` parses | PASS |

## 11. Logs / Error Scan

Post-deploy log scan after the product smoke repro:

| Check | Result |
|---|---|
| Backend tracebacks (10m window) | `14` |
| Backend 500 hits (10m window) | `2` |
| Gateway 500 hits (10m window) | `2` |
| `TenantContextMissing` hits (10m window) | `0` |
| JWT-like leakage (`eyJ`) | `0` |
| SMTP password leakage | `0` |

Interpretation:

- The traceback/500 counts were introduced by the canonical pay route repro above
- No SMTP credential leakage, raw JWT leakage, or `TenantContextMissing` leakage was observed

## 12. Known Limitations

1. VPS worktree still carries a pre-existing local modification to `docker-compose.prod.yml`; it was not changed in DC-1D, but the runtime recheck used that already-drifted ops file.
2. Fresh U6 new-mailbox onboarding was not fully re-proven because current SMTP/runtime constraints still require a real existing recipient mailbox, and no second approved real mailbox was introduced during DC-1D.
3. Legacy `POST /api/v1/payments` still semantically points callers to `PAYMENT_WRITE_PATH_DISABLED`, but the top-level envelope code is normalized to `CONFLICT`.

## 13. Final Verdict

**STOP_AND_REPORT_CTO**

Reason:

- Exact target checkout, backup, redeploy, container health, core health endpoints, Alembic baseline,
  platform auth boundary, rollback spot-check, and log secrecy checks all passed
- **Hard stop condition hit**: product smoke produced a new backend 500 on the canonical payment
  write path `POST /api/v1/orders/{order_id}/pay`
- Fresh new-mailbox U6 onboarding was not fully re-proven under the current provider/mailbox constraints,
  although the existing active owner login/select-tenant/`/me` path remained healthy

This RC should not be promoted further until the canonical pay-route 500 is resolved and the fresh
U6 recheck is re-run with an approved real deliverable mailbox.

## 14. Branch / Push Scope

- Ops branch: `ops/dc1d-final-rc-runtime-recheck-2026-07-09`
- Report file: `ai-ledger/ops/2026-07-09_dc1d_final_rc_runtime_recheck.md`
- `product-dev-recovered` was **not** pushed by DC-1D
- No product code was modified
- No rollback restore was executed
