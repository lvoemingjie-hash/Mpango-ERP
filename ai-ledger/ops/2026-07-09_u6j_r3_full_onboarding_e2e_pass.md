# U6-J-R3 Full Onboarding Runtime Smoke — PASS

**Date:** 2026-07-09
**Branch:** product-dev-recovered at 0f278f1 (U6-L merged)
**Verdict:** PASS_U6J_R3_FULL_ONBOARDING_E2E

## Executive Summary

The entire U6-J onboarding chain now works end-to-end with real SMTP email delivery via 126.com. All 7 steps of the onboarding chain completed successfully:

1. Signup → 202 accepted
2. Email verification → 200, email_verified_at set
3. Provisioning → wholesaler created, tenant schema bootstrapped
4. Setup credential → owner admin user created in tenant schema
5. Login → JWT access + refresh tokens returned
6. Select tenant → contextual JWT with tenant_id + tenant_schema
7. /me endpoint → returns email, roles, permissions with tenant context

## SMTP Configuration

| Field | Value |
|-------|-------|
| Provider | smtp.126.com |
| Port | 994 (SSL) |
| TLS | True (SMTP_SSL) |
| STARTTLS | False |
| User | jeff05992582@126.com |
| From | jeff05992582@126.com |

**Key finding:** 126.com does NOT support `+` alias addressing. `jeff05992582+xxx@126.com` returns 550 User not found. Must use plain email address.

## Backup

- **Pre-R3 backup:** `~/.secure-backups/mpango_erp_u6j_r3_20260709-124948.sql` (237K, SHA256 `512b9c1`)
- **Post-verification backup:** Not created (runtime only)

## Onboarding Chain Detail

### Step 1: Signup
```
POST /api/v1/auth/signup
{"email":"jeff05992582@126.com","name":"Jeff Onboarding Test","companyName":"Jeff Company","country":"TZ","password":"TestPass2026!"}
→ HTTP 202, registration a829867b created
```

### Step 2: Email Verification
```
POST /api/v1/auth/verify-email
{"token":"rhAeIC2mzUY9-HZvzdRIqfAu8Ja_xHZGfXkcxHjr-ec"}
→ HTTP 200, accepted:true
Registration status: active, email_verified_at set
```

### Step 3: Provisioning (automatic after verification)
- Wholesaler created: `14927915-6c85-487c-adb1-c1a595b8b8d7` (Jeff Company)
- Tenant schema: `t_149279156c85487cadb1c1a595b8b8d7`
- 21 tables bootstrapped (users, roles, permissions, skus, orders, etc.)
- Owner setup token issued: `7nBzipMxfN5TSyncv_cznoRXNr82fOXEUW43bYxyZ58`

### Step 4: Setup Credential
```
POST /api/v1/auth/onboarding/setup-credential
{"setup_token":"7nBzipMxfN5TSyncv_cznoRXNr82fOXEUW43bYxyZ58","password":"AdminPass2026!"}
→ HTTP 200, credential setup complete
Owner admin user created: jeff05992582@126.com in tenant schema
```

### Step 5: Login
```
POST /api/v1/auth/login
{"email":"jeff05992582@126.com","password":"AdminPass2026!"}
→ HTTP 200, access_token + refresh_token returned
available_tenants: [{"id":"14927915-...","name":"Jeff Company"}]
```

### Step 6: Select Tenant
```
POST /api/v1/auth/select-tenant
{"tenant_id":"14927915-6c85-487c-adb1-c1a595b8b8d7"}
→ HTTP 200, contextual JWT with tenant_id + tenant_schema
```

### Step 7: Authenticated Access
```
GET /api/v1/auth/me
→ HTTP 200
{
  "id": "f10b8da5-...",
  "email": "jeff05992582@126.com",
  "full_name": "Owner Admin",
  "tenant_id": "14927915-...",
  "tenant_schema": "t_14927915...",
  "roles": ["admin"],
  "permissions": ["users:create", "roles:create", "skus:import", "inventory:update", ...]
}
```

## Known Issues (Non-Blocking)

1. **`onboarding_status_tokens` table empty:** Signup creates email verification tokens but onboarding status tokens are not persisted to DB. Not blocking since the onboarding flow proceeds via owner setup token.

2. **`platform_tenants` / `platform_users` empty:** These platform-level tables are not populated during onboarding. The tenant context is derived from the JWT claims and the `wholesalers` table.

3. **VPS outbound TCP blocked for most ports:** Only ICMP, DNS (TCP 53), and specific SMTP ports (994, 465, 587) work. Gmail (smtp.gmail.com) is blocked. 126.com SMTP works.

## Files Modified

None — all verification done against deployed code at commit `0f278f1`.

## Test Evidence

All tests performed via SSH to VPS `1.14.247.12` from Windows machine `100.122.159.70` via Tailscale.
