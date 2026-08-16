# Phase 1 — Formal Deterministic Provisioning (PW1-R4-B4-V3)

**Product candidate:** `9f24d969e30a2c8ed3ae9e0eddebae170089292a` (B4 app, ran as live system)
**Authoritative harness:** `db84b1325c51a484af55029ce3485d9995b0669a` (browser suite)
**Runtime:** fresh PostgreSQL 16 + Redis 7 (new volumes), MPANGO_ENV=staging (real JwtAuthStrategy), dev_sink email.

## Canonical names (verified via official API)
- Retailer A: **PW1R1 Retailer A**
- Retailer B: **PW1R1 Retailer B**

## Method — only official signup / invitation / register / setup-credential APIs
1. `POST /auth/signup` (owner) → `POST /auth/verify-email` (token from in-process dev_sink) → `POST /auth/onboarding/setup-credential`.
2. `POST /auth/login` → `POST /auth/select-tenant` → `GET /auth/me` (real JWT, role + tenant asserted).
3. `POST /invitations` (wholesaler admin) → `POST /retailers/register` → `POST /retailers/setup-credential` (formal invitation lifecycle).
4. Retailer A bound to BOTH W1 and W2 (multi-tenant); Retailer B bound to W1 only (single-tenant).
5. Negative proofs: wrong password → 401; client login wrong password → 401.

## Status
- Provisioning steps executed: **27**, all OK: **27**.
- Identity emails created: W1=`pw1r4.w1.b4v3@pw1r4.dev`, W2=`pw1r4.w2.b4v3@pw1r4.dev`, RA=`pw1r4.ra.b4v3@pw1r4.dev`, RB=`pw1r4.rb.b4v3@pw1r4.dev`.
- Names/bindings/tenant-belonging verified via official API after provisioning (see verify_provision_r4b4v3.py output).
- NO SQL INSERT/UPDATE/DELETE was used to fix test data; passwords hashed by the product's own services.

## Start-from-empty-database proof
- PG volume `pw1r4b4v3_pg` was created empty; Alembic migrated from base to `037_payment_declarations_schema`.
- First signup created tenant schemas dynamically (no pre-existing tenants).
