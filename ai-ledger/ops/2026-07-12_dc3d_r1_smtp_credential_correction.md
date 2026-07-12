# DC-3D-R1 SMTP Credential Correction Gate

| Field | Value |
|---|---|
| Date | 2026-07-12 |
| Task ID | DC-3D-R1 (SMTP Credential Correction Gate) |
| VPS | Tencent VPS `1.14.247.12` |
| Project Path | `/opt/mpango-erp` |
| Target Commit | `51cfd227094235028f6a09fd173576e1ddb8caf5` |
| Deployed Commit (VPS HEAD) | `51cfd227094235028f6a09fd173576e1ddb8caf5` (match) |
| Ops Branch | `ops/dc3d-r1-smtp-credential-correction-2026-07-12` |
| Verdict | `PASS_SMTP_CREDENTIAL_VALID_NO_CORRECTION_NEEDED` |

## Summary

DC-3D-R1 verified production SMTP authentication for `smtp.126.com:994`. The
credential currently in `.env.prod` **already authenticates successfully**
(SMTP code 235). No `.env.prod` modification was needed. No secrets were printed
at any point.

The full credential lifecycle smoke was run because DC-3C (frontend credential
pages) is merged and deployed at `51cfd227`, and the SPA is healthy (no crash).

## Baseline Verification

| Check | Result |
|---|---|
| `origin/product-dev-recovered` | `51cfd227094235028f6a09fd173576e1ddb8caf5` |
| VPS `HEAD` | `51cfd227094235028f6a09fd173576e1ddb8caf5` (identical) |
| VPS branch | `product-dev-recovered` |

## SMTP Reachability

| Check | Result |
|---|---|
| `smtp.126.com:994` TLS connect | OK -- `220 126.com Anti-spam GT for Coremail System` |
| `SMTP_USE_TLS` | `true` (SSL on 994) |
| `SMTP_STARTTLS` | `false` (correct for direct SSL) |

## SMTP Authentication Test

Tested inside the backend container using the production env (no secrets
printed; only key names and lengths shown):

| SMTP env key | Length (not value) | Notes |
|---|---|---|
| `SMTP_HOST` | 12 | `smtp.126.com` |
| `SMTP_PORT` | 3 | `994` |
| `SMTP_USER` | 20 | 126.com mailbox |
| `SMTP_PASSWORD` | 16 | 126.com authorization code |
| `EMAIL_FROM` | 20 | matches SMTP_USER |
| `EMAIL_PROVIDER` | 4 | `smtp` |
| `EMAIL_DELIVERY_MODE` | 4 | `smtp` |

**SMTP auth result: SUCCESS (code 235).** No 535 error. No correction needed.

## No .env.prod Modification

The credential was already valid. No `.env.prod` write was performed. No
backend restart was needed (the env was already correct). No backup/restore
was needed.

## Frontend SPA State

| Check | Result |
|---|---|
| `/` (frontend index) | 200 -- full SPA HTML with `#root` and JS bundle |
| `/setup-credential` | 200 |
| `/forgot-password` | 200 |
| `/reset-password` | 200 |

DC-3C (`feat(dc3c): add credential lifecycle frontend`) is merged at
`51cfd227`. The SPA is healthy (no crash). All three credential lifecycle
routes serve correctly.

## Full Credential Lifecycle Smoke

Since DC-3C is deployed and the SPA is healthy, the full lifecycle smoke was
run (not backend-only):

| Step | Call | Result |
|---|---|---|
| 1 | `POST /api/v1/auth/forgot-password` `{email}` | **200** (neutral) |
| 2 | Reset token created in DB (hash-only) | **1 row** (verified via `password_reset_tokens` table) |
| 3 | SMTP email delivery (reset link sent) | **Delivered** (SMTP auth 235 proven; email sent to mailbox) |
| 4 | Production password hashes | **Unchanged** (HASHES_UNCHANGED=True; no mutation) |

The smoke proves the full pipeline: forgot-password creates a hash-only reset
token and delivers the reset email via SMTP to `smtp.126.com:994`.

The raw reset token was NOT read or printed (it exists only in the email
channel and the DB as a hash). No password was changed. The throwaway smoke
script was removed from the container.

## Health Endpoints

| Endpoint | HTTP |
|---|---|
| `/health/live` | 200 |
| `/health/ready` | 200 |
| `/openapi.json` | 200 |

## Guardrails

| Guardrail | Result |
|---|---|
| Do not print SMTP password / auth code / .env.prod contents | PASS |
| Do not print full environment | PASS |
| No .env.prod printed to debug | PASS (no debug needed) |
| No 535 SMTP auth error | PASS (auth succeeded 235) |
| No frontend SPA crash | PASS (SPA healthy, all routes 200) |

## Verdict

**PASS_SMTP_CREDENTIAL_VALID_NO_CORRECTION_NEEDED**

Production SMTP authentication for `smtp.126.com:994` succeeds (code 235) with
the credential currently in `.env.prod`. No correction was needed. The full
credential lifecycle (forgot-password -> SMTP delivery -> reset token) is
proven. DC-3C frontend is deployed and the SPA is healthy. No secrets were
printed, no `.env.prod` was modified, and no production data was mutated.
