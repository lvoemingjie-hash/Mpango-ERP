# U6-J Exact VPS Redeploy + Onboarding Runtime Smoke

**Date:** 2026-07-09
**Branch:** product-dev-recovered
**Commit:** 66e8371bf159fff4c2e8ea526a2c842da0783775
**Verdict:** STOP_AND_REPORT_CTO

---

## Preflight

| Item | Value |
|------|-------|
| Repo path | `/opt/mpango-erp` |
| Git remote | `https://github.com/lvoemingjie-hash/Mpango-ERP.git` |
| HEAD before deploy | `eac7642eefeee4539086f2a42fa7b87f0082fc4c` |
| Docker compose | `docker-compose.prod.yml` + `.env.prod` |
| 5 containers health | ALL HEALTHY |

---

## Backup

| Item | Value |
|------|-------|
| Backup path | `~/.secure-backups/mpango_erp_u6j_20260709-031238.sql` |
| Backup size | 215K |
| SHA256 prefix | `7b3f929c` |
| Backup committed | NO |

---

## Exact Checkout

| Item | Value |
|------|-------|
| git fetch origin | OK |
| git checkout -B product-dev-recovered origin/product-dev-recovered | OK |
| New HEAD | `66e8371bf159fff4c2e8ea526a2c842da0783775` |
| git status --short | CLEAN |

---

## Build/Deploy

| Item | Value |
|------|-------|
| Build command | `docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build` |
| Build result | OK |
| Container health after deploy | ALL HEALTHY |

| Container | Status |
|-----------|--------|
| mpango_prod_backend | Up (healthy) |
| mpango_prod_frontend | Up (healthy) |
| mpango_prod_gateway | Up (healthy) |
| mpango_prod_postgres | Up (healthy) |
| mpango_prod_redis | Up (healthy) |

---

## Migration/Head Check

| Item | Value |
|------|-------|
| Alembic version in DB (before) | `025_intake_apply_audit` |
| Alembic head in code | `028_owner_credential_setup_tokens` |
| Migration executed | `alembic upgrade head` |
| Alembic version in DB (after) | `028_owner_credential_setup_tokens` |
| Migration status | AT HEAD |

---

## Runtime Smoke: U6 Onboarding Chain

| # | Test | Result | Notes |
|---|------|--------|-------|
| 1 | POST /api/v1/auth/signup | FAIL | `EMAIL_DELIVERY_NOT_CONFIGURED` |
| 2 | Email verification token retrieval | FAIL | No safe email sink exists |
| 3 | POST /api/v1/auth/verify-email | BLOCKED | Cannot complete without token |
| 4 | POST /api/v1/auth/onboarding/status | FAIL | METHOD_NOT_ALLOWED |
| 5 | Tenant provisioning | EMPTY | No tenants in platform_tenants |
| 6 | Owner setup token issued | EMPTY | No tokens in owner_credential_setup_tokens |
| 7 | POST /api/v1/auth/onboarding/setup-credential | BLOCKED | Cannot complete without token |
| 8 | Tenant admin user exists | EMPTY | No users in tenant schema |
| 9 | Replay setup token returns 401 | N/A | No token to test |
| 10 | Query-string setup token fails | N/A | No token to test |
| 11 | Public responses leak internal data | N/A | Cannot test |

---

## Existing MVP Smoke

| # | Test | Result |
|---|------|--------|
| 1 | /health/live 200 | PASS |
| 2 | /health/ready 200 | PASS |
| 3 | Login existing admin | N/A (no admin user) |
| 4 | Products/SKUs page/API | N/A (no products) |
| 5 | Orders/Payments basic route | N/A (no orders) |
| 6 | No 500s in backend logs | PASS |

---

## DB Verification Summary

| Item | Value |
|------|-------|
| Database | `mpango_erp` |
| User | `mpango` |
| Alembic head | `028_owner_credential_setup_tokens` |
| Tenant schemas | `t_dev`, `t_550e8400e29b41d4a716446655440000` |
| Platform tenants | EMPTY |
| Owner setup tokens | EMPTY |
| Email verification tokens | EMPTY |
| Tenant users | EMPTY |

---

## Log Review Summary

- Backend logs show `EMAIL_DELIVERY_NOT_CONFIGURED` error
- No 500 errors in backend logs
- All health checks passing

---

## Stop Conditions Met

1. **No safe email/token delivery path exists** - Signup requires email verification but email delivery is not configured
2. **Database tables are empty** - No existing tenants, users, or tokens

---

## Required CTO Decisions

1. **Email delivery configuration**: How should email verification work in production?
   - Option A: Configure SMTP (e.g., SendGrid, AWS SES)
   - Option B: Use dev/test email sink for staging
   - Option C: Disable email verification for now

2. **Tenant provisioning**: Should we provision a default tenant for testing?

3. **Admin user**: Should we create an admin user for testing?

---

## Verdict

```
STOP_AND_REPORT_CTO
```

**Reason:** Email delivery not configured, blocking U6 onboarding chain. Cannot complete signup → verify → onboard → setup-credential flow without email delivery.
