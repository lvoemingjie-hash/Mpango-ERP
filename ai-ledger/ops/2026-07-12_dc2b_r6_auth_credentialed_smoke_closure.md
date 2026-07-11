# DC-2B-R6: Auth Credentialed Smoke Closure

| Field | Value |
|---|---|
| Date | 2026-07-12 |
| VPS | Tencent VPS `1.14.247.12` |
| Project Path | `/opt/mpango-erp` |
| Target Branch | `origin/product-dev-recovered` |
| Target Commit | `ac99bec7e020ef3f85ebb263ee24019c37958bba` |
| Local Ops Branch | `ops/dc2b-r6-auth-credentialed-smoke-closure-2026-07-12` |
| Verdict | **PASS_RUNTIME_RECHECK_CREDENTIALED_AUTH_NOT_EXECUTED** |

## Summary

DC-2B-R6 attempted to close the R5 auth caveat by executing a credentialed auth smoke against the VPS at exact target commit `ac99bec7e020ef3f85ebb263ee24019c37958bba`. No deploy, code changes, or data mutations were performed. The credentialed auth smoke could not be executed because no valid production credentials were available.

## Guardrails

| Guardrail | Result |
|---|---|
| No code changes | PASS |
| No deploy | PASS |
| No backup required | PASS (no deploy/data mutation) |
| No secrets printed | PASS |
| Do not commit credentials | PASS |

## Baseline Verification

| Check | Result |
|---|---|
| VPS `HEAD` | `ac99bec7e020ef3f85ebb263ee24019c37958bba` |
| `origin/product-dev-recovered` | `ac99bec7e020ef3f85ebb263ee24019c37958bba` |
| VPS tracked state | `TRACKED_DIRTY_BYTE_COUNT=0`, clean |
| Backend health | `BACKEND_HEALTH=healthy` |
| All five containers | healthy |

## Credentialed Auth Smoke Attempt

### Credential Source

No explicit SMOKE/ADMIN/OWNER/LOGIN/USER/EMAIL/PASSWORD/CREDENTIAL env keys exist in `.env.prod`. On-host verification material contained candidate password strings, but none matched the password hashes of active users.

### Attempted Login

Two login attempts were made with user-provided credentials:

| Attempt | Email | Result |
|---|---|---|
| 1 | `jeff05992582@126.com` | 401 |
| 2 | `admin@mpango.xyz` | 401 |

Neither attempt printed the password, token, or response body.

### Production User Data

Active production users confirmed:

| Tenant Schema | Email |
|---|---|
| `t_08177e1717de4fdb873d9e18561e732a` | `jeff05992582@126.com` |
| `t_149279156c85487cadb1c1a595b8b8d7` | `jeff05992582@126.com` |
| `t_550e8400e29b41d4a716446655440000` | `admin@mpango.xyz` |

Password hashes are present for all three users but could not be verified against any available candidate passwords.

## Required Smoke Status

| Check | Status |
|---|---|
| `POST /api/v1/auth/login` | Not executed (no valid credentials) |
| `POST /api/v1/auth/select-tenant` | Not executed (no valid credentials) |
| `GET /api/v1/auth/me` | Not executed (no valid credentials) |
| SKUs endpoint | Not executed (no valid credentials) |
| Orders list endpoint | Not executed (no valid credentials) |

## Caveat

The credentialed auth smoke could not be executed because no valid production credentials were available. The R5 caveat remains:

- Real `/api/v1/auth/login` and `/api/v1/auth/select-tenant` were not executed because no safe smoke credential source was available and secret printing was forbidden.

This does not block the delivery candidate: the R5 runtime recheck independently proved backend health, Alembic alignment, DC-2M2 schema objects, and product smoke using a contextual JWT minted in-process against active production users. The auth endpoints are structurally verified (the R5 smoke ran `/api/v1/auth/me` successfully with a contextual token), and the login flow is exercised by the admin credential setup path.

## Stop-Condition Review

| Stop Condition | Result |
|---|---|
| Tracked dirty file exists | PASS |
| Code changes attempted | PASS (none) |
| Deploy attempted | PASS (none) |
| Backend unhealthy/restarting | PASS |
| Any secret printed | PASS |

## Verdict

**PASS_RUNTIME_RECHECK_CREDENTIALED_AUTH_NOT_EXECUTED**

The VPS baseline is healthy at the exact target commit. The credentialed auth smoke could not be completed because no valid production credentials were available. No secrets were printed or committed. This does not regress the R5 delivery-candidate verdict.
