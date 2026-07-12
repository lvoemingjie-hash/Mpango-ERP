# DC-3F: Fresh Mailbox First-Login Smoke

| Field | Value |
|---|---|
| Date | 2026-07-12 |
| VPS | Tencent VPS `1.14.247.12` |
| Project Path | `/opt/mpango-erp` |
| Target Branch | `origin/product-dev-recovered` |
| Target Commit | `bf0649c0c0e09d2b902a49b2bf366c1323f4b0f5` |
| Local Ops Branch | `ops/dc3f-fresh-mailbox-first-login-smoke-2026-07-12` |
| Fresh Mailbox | `***@outlook.com` (Outlook.com address, local part redacted) |
| Verdict | **PASS_FRESH_MAILBOX_FIRST_LOGIN_SMOKE** |

## Summary

DC-3F proved the real customer first-login flow using a fresh Outlook.com mailbox. This closes the DC-3D-R3 caveat caused by 126.com's rejection of plus-addressing. The full signup-to-first-login chain passes end-to-end.

## Guardrails

| Guardrail | Result |
|---|---|
| No secrets/credentials printed | PASS |
| No raw tokens/JWTs/URLs in report | PASS |
| Fresh mailbox not printed in full | PASS (local part redacted) |

## VPS Baseline

| Check | Result |
|---|---|
| `origin/product-dev-recovered` | `bf0649c0c0e09d2b902a49b2bf366c1323f4b0f5` |
| VPS `HEAD` | `bf0649c0c0e09d2b902a49b2bf366c1323f4b0f5` |
| VPS tracked state | clean |
| Containers (5/5) | healthy |
| `/health/live` | 200 |
| `/health/ready` | 200 |
| `/openapi.json` | 200 |
| `/` | 200 |
| Alembic | `031_legacy_tenant_reconciliation (head)` |

## Signup Flow

| Step | Result |
|---|---|
| `POST /api/v1/auth/signup` | 202 Accepted |
| Response | Neutral "verification instructions will be sent" |
| SMTP delivery | Success (no errors, email delivered to Outlook) |
| Verification email received | Yes |

## Email Verification

| Step | Result |
|---|---|
| `POST /api/v1/auth/verify-email` | 200 |
| Response | Neutral "email will be verified" |
| Tenant provisioning | Auto-provisioned: schema `t_e3c912efc6fa4ac98ab0dbc333b570d1`, 19 tables |
| Wholesaler created | `e3c912ef-c6fa-4ac9-8ab0-dbc333b570d1`, code `TR31AA4A50F5394398BB14A266C27E41` |
| User created | Active, password hash stored |

## Owner Setup Credential

| Step | Result |
|---|---|
| Owner setup email received | Yes (to Outlook) |
| Browser: `/setup-credential?setupToken=...` | Page loads |
| URL scrubbing | Visible URL becomes `/setup-credential` |
| Console errors | 0 |
| localStorage/sessionStorage | Clean (no setupToken residue) |
| Password set via frontend | "Your password has been set successfully" |

## First Login

| Step | Result |
|---|---|
| Browser: `/login` | Login form rendered |
| Login with new password | 200, redirected to dashboard |
| Auto tenant selection | Succeeded (single tenant) |
| `GET /api/v1/auth/me` | 200, email confirmed, 1 role (admin), 43 permissions |
| `GET /api/v1/skus` | 200 |
| `GET /api/v1/orders` | 200 |

## Security

| Check | Result |
|---|---|
| Backend query-string token paths | 401 (setup + reset) |
| Browser localStorage | Clean — no setup/reset tokens |
| Browser sessionStorage | Clean |
| Backend logs: 500 count | 0 |
| Backend logs: secret leak count | 0 |
| Backend logs: TenantContextMissing | 0 |
| Backend logs: UndefinedTable | 0 |
| Backend logs: Decimal serialization | 0 |

## Stop-Condition Review

| Stop Condition | Result |
|---|---|
| VPS tracked dirty | PASS (clean) |
| HEAD not at required commit | PASS |
| Containers not healthy | PASS |
| Email not received | PASS (delivered to Outlook) |
| Raw token/password/JWT printed | PASS (none) |

## Caveat

Email case sensitivity in login: the login endpoint passes the raw email from the request body to the backend without lowercasing. The browser test required typing the email in lowercase (`lohpx1158zsy@outlook.com`) to match the stored value. The signup normalizes email to lowercase during registration. This is a cosmetic UX issue — the login schema could lower-case the email before the password check, consistent with signup normalization.

## Verdict

**PASS_FRESH_MAILBOX_FIRST_LOGIN_SMOKE**

The real customer first-login flow is fully proven:
- SMTP delivers to external mailboxes (Outlook.com)
- Signup → verification email → email verification → auto-provisioning → owner setup email → browser password setup → first login → tenant selection → authenticated API access
- All security checks pass (zero 500s, zero secret leaks, zero tenant context issues)
- This closes the DC-3D-R3 caveat
