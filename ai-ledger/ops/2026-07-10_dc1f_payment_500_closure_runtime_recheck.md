# DC-1F Payment 500 Closure Runtime Recheck

- **Date**: 2026-07-10
- **Target branch**: `origin/product-dev-recovered`
- **Deployed HEAD**: `bce3dcfc72b459a6a5ca429874ae3cb6be794b88`
- **Expected DC-1E commit**: `bce3dcfc72b459a6a5ca429874ae3cb6be794b88`
- **Ops branch**: `ops/dc1f-payment-500-closure-runtime-recheck-2026-07-10`
- **Report**: `ai-ledger/ops/2026-07-10_dc1f_payment_500_closure_runtime_recheck.md`
- **Verdict**: `STOP_AND_REPORT_CTO`

## Summary

DC-1E is deployed and reachable from `origin/product-dev-recovered`; the exact DC-1D repro is closed.
The previously failing invalid canonical pay request now returns a clean 4xx JSON validation response,
and backend logs show zero new Decimal serialization tracebacks.

DC-1F still stops because the required normal canonical payment sanity could not be completed through
approved API setup. The only usable tenant in the existing owner path had zero retailers and zero orders,
so a valid payment flow required creating normal test data through the invitation/register API. Invitation
creation succeeded, but public retailer registration returned a new backend 500 caused by a database
integrity failure on `public.wholesaler_retailer_bindings.outstanding_balance`. No manual DB repair was used.

## 1. Exact Checkout

VPS commands executed:

```bash
git fetch origin
git checkout -B product-dev-recovered origin/product-dev-recovered
git rev-parse HEAD
git log --oneline --decorate -n 20
```

Results:

| Check | Result |
|---|---|
| HEAD | `bce3dcfc72b459a6a5ca429874ae3cb6be794b88` |
| DC-1E reachable from HEAD | PASS |
| Reachability proof | HEAD itself is `bce3dcfc...` |

Recent history began with:

```text
bce3dcf fix(dc1e): serialize validation errors safely
3d30222 docs(dc1c-r2): enforce ASCII rollback runbook evidence
22fed06 ops: DC-1C-R1 rollback runbook confirmation (clean, secrets redacted)
```

Observed VPS drift note:

- `git status --short` on the VPS still showed a pre-existing local modification:
  `M docker-compose.prod.yml`
- This file was not edited during DC-1F

## 2. Backup

Fresh pre-recheck backup created outside the repo.

| Field | Value |
|---|---|
| Path | `/home/ubuntu/.secure-backups/mpango_erp_dc1f_20260710-090800.sql` |
| Size | `395948` bytes |
| SHA256 prefix | `bfe825335230989c` |

Backup content was not printed.

## 3. Rebuild / Redeploy

Command executed:

```bash
cd /opt/mpango-erp
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
```

Result: completed successfully.

## 4. Health / Baseline

### Container health

| Container | Status |
|---|---|
| `mpango_prod_backend` | healthy |
| `mpango_prod_frontend` | healthy |
| `mpango_prod_gateway` | healthy |
| `mpango_prod_postgres` | healthy |
| `mpango_prod_redis` | healthy |

Mpango runtime health: **5/5 healthy**.

### Endpoint health

| Endpoint | HTTP | Result |
|---|---|---|
| `/health/live` | 200 | PASS |
| `/health/ready` | 200 | PASS |
| `/openapi.json` | 200 | PASS |
| `/` | 200 | PASS |

### Alembic baseline

| Check | Result |
|---|---|
| `alembic heads` | `030_platform_backup_status_source (head)` |
| `alembic current` | `030_platform_backup_status_source (head)` |
| Multiple heads | No |

## 5. Primary DC-1D Repro Recheck

Re-ran the same failing class of request as DC-1D:

`POST /api/v1/orders/{order_id}/pay` with invalid amount payload `{ "amount": 0 }`

Result:

| Check | Result |
|---|---|
| HTTP status | `422` |
| Response body valid JSON | PASS |
| Contains `Object of type Decimal is not JSON serializable` | No |
| Contains `traceback` | No |
| Contains internal stack details | No |
| New Decimal traceback in backend logs for this repro | `0` |
| New generic traceback in backend logs for this repro | `0` |

Observed response shape:

```json
{"code":"VALIDATION_ERROR","message":"Request validation failed"}
```

Conclusion: **the DC-1D canonical pay-route 500 is closed**.

## 6. Canonical Payment Sanity

Required normal sanity was to create or use a valid confirmed order and then pay it through
`POST /api/v1/orders/{id}/pay`.

Runtime findings in the usable tenant owner path:

| Check | Result |
|---|---|
| Existing usable tenant count | `1` usable tenant selected successfully |
| Existing retailers in usable tenant | `0` |
| Existing orders in usable tenant | `0` |

Because there was no existing retailer/order to reuse, the recheck attempted the approved API setup path:

1. `POST /api/v1/invitations` -> **201** PASS
2. `POST /api/v1/retailers/register` -> **500** STOP

Retailer registration response:

```json
{"code":"INTERNAL_SERVER_ERROR","message":"An internal server error occurred. Please contact support."}
```

Backend log root cause:

```text
sqlalchemy.exc.IntegrityError: null value in column "outstanding_balance" of relation
"wholesaler_retailer_bindings" violates not-null constraint
```

Impact on DC-1F:

- A valid order could not be created through approved API setup
- No manual DB repair was used
- Step 6 therefore cannot be completed safely in this runtime recheck

This is a stop-gate condition for DC-1F.

## 7. Legacy Payment Route Sanity

| Check | Result |
|---|---|
| `POST /api/v1/payments` HTTP | `409` |
| Disabled-write-path semantics present | PASS |
| Backend 500 | Not observed from this route |

Observed legacy route body semantics:

```json
{"code":"CONFLICT","message":"{'code': 'PAYMENT_WRITE_PATH_DISABLED', ... }"}
```

The top-level envelope code is still `CONFLICT`, but the route continues to direct callers to the
canonical order pay path with `PAYMENT_WRITE_PATH_DISABLED` semantics.

## 8. Platform / Auth Boundary Sanity

| Check | HTTP | Result |
|---|---|---|
| `/api/v1/platform/health` | 200 | PASS |
| `/api/v1/platform/info` | 200 | PASS |
| `/api/v1/platform/tenants/` with tenant token | 401 | PASS |
| `TenantContextMissing` in logs | `0` | PASS |

The tenant token remained blocked from platform-only routes as expected.

## 9. U6 Minimal Sanity

No fresh full-mailbox onboarding rerun was required for DC-1F.

Required minimal auth baseline passed:

| Check | HTTP | Result |
|---|---|---|
| Existing active owner login | 200 | PASS |
| Select tenant | 200 | PASS |
| `/api/v1/auth/me` | 200 | PASS |

## 10. Rollback Spot Check

No restore was executed.

| Check | Result |
|---|---|
| DC-1A backup still exists | PASS |
| DC-1C runbook exists in repo | PASS |
| Restore tool remains available | PASS |
| `docker compose ... config --quiet` parses | PASS |

## 11. Log Scan

Post-recheck runtime log scan:

| Check | Result |
|---|---|
| Decimal serialization tracebacks | `0` |
| Backend 500 count | `2` |
| Gateway 500 count | `4` |
| `TenantContextMissing` | `0` |
| JWT-like leakage | `0` |
| SMTP password leakage | `0` |
| DB password leakage | `0` |

Interpretation:

- The original DC-1D Decimal serialization 500 is gone
- The observed new 500s are explained by the retailer registration failure during Step 6 setup
- No secret leakage was observed

## 12. Known Limitations

1. The VPS worktree still carries a pre-existing local modification to `docker-compose.prod.yml`.
2. The only usable tenant in the existing owner path had no retailers and no orders, so Step 6 depended on creating valid test data through the invitation/register API.
3. Public retailer registration currently fails with a backend 500 caused by a binding row integrity issue on `outstanding_balance`, which prevented completion of normal canonical payment sanity.

## 13. Final Verdict

**STOP_AND_REPORT_CTO**

Why:

- DC-1E is deployed and reachable from HEAD
- The exact DC-1D invalid canonical pay repro is fixed: it now returns clean 422 JSON with zero Decimal tracebacks
- Health, Alembic, platform boundary, legacy payment route, rollback spot-check, and U6 minimal auth baseline all passed
- DC-1F still cannot sign off because Step 6 normal canonical payment sanity is blocked by a **different runtime 500** on the approved retailer registration setup path

Net: **the original payment validation serialization bug is closed, but the release candidate is still not clean enough to pass DC-1F end-to-end runtime closure**.

## 14. Push Scope

- Branch: `ops/dc1f-payment-500-closure-runtime-recheck-2026-07-10`
- File committed: `ai-ledger/ops/2026-07-10_dc1f_payment_500_closure_runtime_recheck.md`
- `product-dev-recovered` was not pushed
- No product/platform code was modified
