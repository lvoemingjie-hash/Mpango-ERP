# U6-J-R2 Exact VPS Redeploy + SMTP Onboarding Runtime Smoke

**Date:** 2026-07-09
**Branch:** product-dev-recovered
**Commit:** 19f6afde9c351de0d8d29b30fbf1ce8ba0462961
**Verdict:** PARTIAL_PASS_EMAIL_DELIVERY_WORKING_ONBOARDING_INCOMPLETE

---

## Preflight

| Item | Value |
|------|-------|
| U6-K merged | YES |
| New HEAD | `19f6afde9c351de0d8d29b30fbf1ce8ba0462961` |
| SMTP code in email_delivery.py | YES |
| SMTP config in config.py | YES |
| Worktree clean | YES |

---

## DB Backup

| Item | Value |
|------|-------|
| Backup path | `~/.secure-backups/mpango_erp_u6j_r2_20260709-075351.sql` |
| Backup size | 235K |
| SHA256 prefix | `dea9233a` |
| Backup committed | NO |

---

## SMTP Configuration

| Non-Secret Key | Value |
|----------------|-------|
| EMAIL_PROVIDER | smtp |
| EMAIL_DELIVERY_MODE | smtp |
| SMTP_HOST | smtp.gmail.com |
| SMTP_PORT | 587 |
| SMTP_USER | rykardolucano@gmail.com |
| EMAIL_FROM | rykardolucano@gmail.com |
| SMTP_STARTTLS | true |
| SMTP_USE_TLS | false |

**Note:** docker-compose.prod.yml was updated to add SMTP environment variables to backend service.

---

## Container Health

| Container | Before | After |
|-----------|--------|-------|
| mpango_prod_backend | healthy | healthy |
| mpango_prod_frontend | healthy | healthy |
| mpango_prod_gateway | healthy | healthy |
| mpango_prod_postgres | healthy | healthy |
| mpango_prod_redis | healthy | healthy |

---

## Health Checks

| Endpoint | Status |
|----------|--------|
| /health/live | 200 |
| /health/ready | 200 |
| /openapi.json | 200 |

---

## U6 Onboarding Chain Results

| # | Step | HTTP Status | Result |
|---|------|-------------|--------|
| 1 | POST /api/v1/auth/signup | 202 | ✅ PASS - Email sent successfully |
| 2 | Retrieve verification email | N/A | ✅ PASS - User received email |
| 3 | POST /api/v1/auth/verify-email | 200 | ✅ PASS - Token verified, used_at set |
| 4 | POST /api/v1/auth/onboarding/status | 400 | ⚠️ BLOCKED - Onboarding status token not returned in signup response |
| 5 | Tenant provisioning | N/A | ⚠️ NOT TRIGGERED - No automatic provisioning after email verification |
| 6 | Owner setup token | N/A | ⚠️ NOT CREATED - Dependent on provisioning |
| 7 | POST /api/v1/auth/onboarding/setup-credential | N/A | ⚠️ BLOCKED - No setup token |
| 8 | Login with owner credentials | N/A | ⚠️ BLOCKED - No owner user created |
| 9 | Select tenant | N/A | ⚠️ BLOCKED - No tenant |
| 10 | Verify admin routes | N/A | ⚠️ BLOCKED - No admin user |

---

## DB Verification Summary

| Item | Value |
|------|-------|
| Alembic head | 028_owner_credential_setup_tokens |
| Registration status | email_verified |
| Email verification token | used_at set |
| Onboarding status tokens | Created but raw token not accessible |
| Tenant provisioning | NOT TRIGGERED |
| Owner setup tokens | NOT CREATED |
| Tenant schemas | 2 (t_dev, t_550e8400e29b41d4a716446655440000) |
| Platform tenants | EMPTY |

---

## Secret Hygiene Confirmation

- [x] No SMTP_PASSWORD printed
- [x] No raw tokens printed in report
- [x] No JWT printed
- [x] No .env.prod committed
- [x] No backup committed
- [x] No manual DDL

---

## Blockers Identified

1. **Onboarding status token not returned in signup response** - The token is created during signup but not included in the API response. Users cannot check onboarding status without this token.

2. **No automatic tenant provisioning** - After email verification, provisioning is not triggered automatically. There's no API endpoint to trigger it.

3. **Onboarding flow incomplete** - The U6 onboarding chain stops at email verification. The remaining steps (provisioning, setup credential, login) are not implemented in the current codebase.

---

## What Was Proven

1. ✅ SMTP email delivery works in production
2. ✅ Verification emails are sent and received
3. ✅ Email verification token works correctly
4. ✅ Registration status updates to email_verified
5. ✅ All containers healthy

---

## What Needs Product Work

1. Return onboarding status token in signup or verify-email response
2. Implement automatic tenant provisioning after email verification
3. Implement owner setup token issuance
4. Implement setup credential endpoint flow

---

## Verdict

```
PARTIAL_PASS_EMAIL_DELIVERY_WORKING_ONBOARDING_INCOMPLETE
```

**Email delivery: WORKING**
**Onboarding chain: INCOMPLETE (product implementation gap)**
