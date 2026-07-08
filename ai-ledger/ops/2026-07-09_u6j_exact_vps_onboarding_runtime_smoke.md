# U6-J-R1 Email Delivery Runtime Configuration Gate

**Date:** 2026-07-09
**Branch:** product-dev-recovered
**Commit:** 66e8371bf159fff4c2e8ea526a2c842da0783775
**Verdict:** STOP_EMAIL_DELIVERY_NOT_CONFIGURED

---

## Environment Inventory

### VPS Email Configuration (non-secret keys)

| Key | Status |
|-----|--------|
| MPANGO_ENV | `production` |
| EMAIL_DELIVERY | NOT CONFIGURED |
| SMTP_HOST | NOT CONFIGURED |
| SMTP_PORT | NOT CONFIGURED |
| SMTP_USER | NOT CONFIGURED |
| EMAIL_FROM | NOT CONFIGURED |
| EMAIL_PROVIDER | NOT CONFIGURED |

### .env.prod Email Keys

**No email-related configuration keys exist in .env.prod.**

### .env.example Email Keys

**No email-related configuration keys exist in .env.example.**

### Backend Code Analysis

| File | Finding |
|------|---------|
| `/app/services/email_delivery.py` | Only implements dev email sink |
| `is_verification_email_delivery_configured()` | Returns `settings.MPANGO_ENV != "production"` |
| `record_verification_email()` | Raises `EmailDeliveryNotConfiguredError` when `MPANGO_ENV == "production"` |
| `/app/services/onboarding_service.py` | Calls `record_verification_email()`, propagates error |

### Root Cause

The codebase **only has a dev email sink** for test/staging environments. There is **no production email delivery implementation**. When `MPANGO_ENV=production`, the system correctly refuses to send emails because no production email delivery path exists.

---

## Safe Delivery Path Analysis

| Path | Status | Notes |
|------|--------|-------|
| A. Real SMTP/provider in .env.prod | NOT AVAILABLE | No SMTP config keys in codebase or .env.example |
| B. CTO provides credentials | NOT AVAILABLE | No SMTP config keys to populate |
| C. Local/sandbox mail sink | NOT AVAILABLE | Code only has dev sink, not staging sink |

**Conclusion:** No safe delivery path exists because the codebase lacks production email delivery implementation.

---

## Missing Non-Secret Keys

The following configuration keys would need to be added to support production email delivery:

| Key | Purpose | Example |
|-----|---------|---------|
| `EMAIL_PROVIDER` | Email service provider | `smtp`, `sendgrid`, `ses` |
| `SMTP_HOST` | SMTP server hostname | `smtp.gmail.com` |
| `SMTP_PORT` | SMTP server port | `587` |
| `SMTP_USER` | SMTP username | (secret) |
| `SMTP_PASSWORD` | SMTP password | (secret) |
| `EMAIL_FROM` | Sender email address | `noreply@mpango.com` |
| `EMAIL_DELIVERY_MODE` | Delivery mode | `smtp`, `api`, `dev` |

---

## Recommended Provider Setup

### Option 1: SMTP (Simple)
1. Get SMTP credentials from email provider (Gmail, Outlook, etc.)
2. Add config keys to codebase (`core/config.py`)
3. Implement SMTP email delivery in `email_delivery.py`
4. Add SMTP config to `.env.prod`

### Option 2: Transactional Email API
1. Sign up for SendGrid, AWS SES, or similar
2. Add API key config to codebase
3. Implement API-based email delivery
4. Add API key to `.env.prod`

### Option 3: Development Mode for Staging
1. Change `MPANGO_ENV` to `staging`
2. Use dev email sink
3. **Not recommended for production claim**

---

## Runtime State

| Item | Value |
|------|-------|
| 5/5 containers | HEALTHY |
| /health/live | 200 |
| /health/ready | 200 |
| Alembic head | 028_owner_credential_setup_tokens |
| platform_tenants | EMPTY (ENVIRONMENT_STATE_EMPTY) |
| users | EMPTY (ENVIRONMENT_STATE_EMPTY) |
| owner_credential_setup_tokens | EMPTY (ENVIRONMENT_STATE_EMPTY) |

---

## CTO Decision Required

**Question:** How should production email delivery be implemented?

**Options:**
1. **Implement SMTP email delivery** - Add SMTP config keys and implementation to codebase
2. **Implement API email delivery** - Add SendGrid/SES config and implementation
3. **Change to staging mode** - Set `MPANGO_ENV=staging` to use dev sink (not recommended for production)
4. **Provide credentials out-of-band** - CTO provides SMTP/API credentials, OPS implements

**Blocker:** U6-J cannot complete signup → verify → onboard → setup-credential flow without email delivery.

---

## Verdict

```
STOP_EMAIL_DELIVERY_NOT_CONFIGURED
```

**Reason:** Codebase only has dev email sink. No production email delivery implementation exists. Cannot complete U6 onboarding chain without email delivery.
