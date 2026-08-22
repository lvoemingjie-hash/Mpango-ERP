# Provisioning Steps

## W1
1. POST /api/v1/auth/signup (companyName=W1 Wholesale Co, country=KE, email=w1task_v2_20260822093910@example.org)
2. GET /api/v1/auth/debug/dev-emails (retrieved verification token from dev_sink)
3. POST /api/v1/auth/verify-email (token verified, wholesaler + tenant schema provisioned)
4. GET /api/v1/auth/debug/dev-emails (retrieved owner_setup token)
5. POST /api/v1/auth/onboarding/setup-credential (password set)
6. POST /api/v1/auth/login (identity JWT + tenant selection)
7. POST /api/v1/auth/select-tenant (contextual JWT issued)
  - Tenant ID: a7a745b0-dfcd-414e-a19a-2e77a2cb006e
  - Tenant Code: TR303AE67F0A0B4A648E94DE4CE3DA1F

## W2
1-6. Same lifecycle as W1
  - Email: w2task_v2_20260822093927@example.org
  - Tenant ID: 791f2ffd-4b78-40c8-84db-561350d87983
  - Tenant Code: TRC86D141EFEBE41A093517F812F49DF
