# U6-J-R3 Exact VPS Redeploy + Full Onboarding Runtime Smoke

**Date:** 2026-07-09
**Branch:** product-dev-recovered
**Commit:** 0f278f19e799bdab87c16b62999d6e42bc1a7f40
**Verdict:** STOP_AND_REPORT_CTO

---

## Preflight

| Item | Value |
|------|-------|
| U6-K merged | YES |
| U6-L merged | YES |
| HEAD | 0f278f19e799bdab87c16b62999d6e42bc1a7f40 |
| Worktree clean | YES |
| SMTP code present | YES |
| Setup-credential endpoint | YES |
| Onboarding orchestration | YES |

---

## DB Backup

| Item | Value |
|------|-------|
| Backup path | ~/.secure-backups/mpango_erp_u6j_r3_20260709-124948.sql |
| Backup size | 237K |
| SHA256 | 512b9c1994c3537932aab1f63d353676310d3f8807fcd1029142d0535c686ef5 |
| Backup committed | NO |

---

## Container Health

| Container | Status |
|-----------|--------|
| mpango_prod_backend | healthy |
| mpango_prod_frontend | healthy |
| mpango_prod_gateway | healthy |
| mpango_prod_postgres | healthy |
| mpango_prod_redis | healthy |

## Health Checks

| Endpoint | Status |
|----------|--------|
| /health/live | 200 |
| /health/ready | 200 |

---

## BLOCKER: VPS Outbound Internet Completely Blocked

### Evidence

| Test | Result |
|------|--------|
| `curl https://www.google.com` | HTTP 000 (no connection) |
| `nc -zw2 smtp.gmail.com 587` | FAIL |
| `nc -zw2 smtp.gmail.com 465` | FAIL |
| `nc -zw2 smtp.gmail.com 443` | FAIL |
| `python3 smtplib.SMTP('smtp.gmail.com', 587)` | TimeoutError |
| DNS resolution | OK (173.194.43.109) |
| iptables OUTPUT | ACCEPT (no local block) |
| Local services | WORKING (localhost:80 200) |

### Root Cause

Tencent Cloud security group blocks ALL outbound TCP from VPS. DNS resolves but TCP connections to external hosts fail. This is not a code issue — it requires Tencent Cloud Console security group modification to allow outbound TCP 587/465.

### Impact

- SMTP email delivery impossible
- Verification emails cannot be sent
- Full onboarding chain cannot be tested
- Production email-dependent features non-functional

---

## Onboarding Chain Results

| # | Step | Result | Detail |
|---|------|--------|--------|
| 1 | POST /api/v1/auth/signup | 202 | Registration created, token created, email send attempted |
| 2 | Email delivery | FAIL | SMTP timeout — VPS cannot reach smtp.gmail.com |
| 3 | POST /api/v1/auth/verify-email | BLOCKED | No raw verification token available (only hash in DB) |
| 4 | Tenant provisioning | BLOCKED | Depends on verify-email |
| 5 | Owner setup email | BLOCKED | Depends on provisioning |
| 6 | Setup credential | BLOCKED | No setup token |
| 7 | Owner login | BLOCKED | No owner user |
| 8 | Select tenant | BLOCKED | No tenant |
| 9 | MVP routes | BLOCKED | No auth token |

---

## DB State Summary

| Table | Count | Detail |
|-------|-------|--------|
| tenant_registrations | 3 | 1 email_verified, 2 pending_email_verification |
| email_verification_tokens | 3 | 1 used, 2 unused |
| onboarding_status_tokens | 0 | EMPTY |
| owner_credential_setup_tokens | 0 | EMPTY |
| platform_tenants | 0 | EMPTY |
| tenant schemas | 2 | t_dev, t_550e8400e29b41d4a716446655440000 |

### R2 Registration State

| Field | Value |
|-------|-------|
| id | e8139833-0334-41e8-957a-99e4e245e412 |
| email | rykardolucano+u6j_r2f_1783557015@gmail.com |
| status | email_verified |
| email_verified_at | 2026-07-09 00:39:35 |
| provisioning_started_at | NULL |
| provisioning_completed_at | NULL |

**Note:** R2 registration has email_verified but provisioning was never triggered. No onboarding_status_tokens or owner_credential_setup_tokens exist for this registration.

---

## Code Verification

| File | Status |
|------|--------|
| backend/services/email_delivery.py | SMTP implementation present |
| backend/services/onboarding_service.py | U6-L orchestration present |
| backend/api/v1/auth.py | setup-credential endpoint present (line 611) |
| backend/services/tenant_provisioning_service.py | Provisioning service present |

---

## Security Checks

- [x] No SMTP_PASSWORD printed
- [x] No raw tokens printed
- [x] No JWT printed
- [x] No .env.prod contents printed
- [x] No manual DDL
- [x] No manual tenant/admin DB creation
- [x] No dev sink in production
- [x] Backup outside repo

---

## Required CTO Action

1. **Tencent Cloud Console** — Modify security group to allow outbound TCP 587 and 465 (SMTP) from VPS 1.14.247.12
2. After SMTP is unblocked, re-run U6-J-R3 to prove full onboarding chain
3. Consider: outbound 443 (HTTPS) also blocked — may affect other integrations

---

## Verdict

```
STOP_AND_REPORT_CTO
```

**Blocker:** VPS outbound internet completely blocked (Tencent security group). SMTP email delivery impossible. Full onboarding chain cannot be proven without email delivery.
