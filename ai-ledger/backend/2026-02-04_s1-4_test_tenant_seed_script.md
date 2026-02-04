# S1-4: Test Tenant Migration / Seed Script

## Objective
After S1-2 removed `MPANGO_TEST_MODE` and deprecated bypass logic, we need a reproducible way to initialize a known test tenant + admin user so JWT-based auth flows (login + tenant/user resolution) have concrete database records.

## Deliverable
**Script:** `scripts/seed_test_tenant.py`

This script creates/updates the “gold standard” test tenant and admin user.

## Gold Standard Test Tenant
The seed is aligned to the existing verification scripts and tenant schema derivation logic (`models.wholesaler.derive_schema_from_id`).

- **Tenant code:** `TEST001`
- **Tenant id:** `550e8400-e29b-41d4-a716-446655440000`
- **Tenant schema:** `t_550e8400e29b41d4a716446655440000`

## Gold Standard Admin User
- **Email:** `admin@test.com`
- **Password:** `testpassword`
- **Role:** `admin`
- **Permissions seeded (minimum set used by tests):**
  - `payments:create`
  - `payments:read`
  - `orders:read`
  - `orders:write`
  - `users:read`
  - `users:create`

## Idempotency Guarantees
The script is safe to run multiple times:
- **Tenant registry (public.wholesalers)**
  - Creates row if missing
  - Updates name if present
  - Refuses to proceed if `TEST001` exists with a different tenant UUID (prevents schema mismatch/corruption)
- **Tenant schema + RBAC tables**
  - `CREATE SCHEMA IF NOT EXISTS`
  - `CREATE TABLE IF NOT EXISTS` for `users`, `roles`, `permissions`, `user_roles`, `role_permissions`
- **Admin user**
  - Upserts by email (updates password hash + full_name, re-activates)
- **Role + permissions**
  - Upserts by unique keys
  - M2M links use `ON CONFLICT DO NOTHING`

## Environment Safety
The script is designed primarily for `MPANGO_ENV=test` or `dev`:
- Refuses to run if `MPANGO_ENV` is not `test`/`dev` unless you pass `--allow-production`.
- Also refuses to run if `DATABASE_URL` doesn’t look local (`localhost`/`127.0.0.1`) unless you pass `--allow-production`.

## Integration Notes
### JWT / Production auth path
This seed enables the real login flow (`/api/v1/auth/login`) to work in a test DB because:
- `tenant_code` resolves via `public.wholesalers`
- tenant schema is derived from the seeded wholesaler UUID
- user exists in the tenant schema

### Mock strategy (`MockAuthStrategy`)
The mock strategy defaults to `tenant_schema=t_dev`. The script **also seeds `t_dev` by default** so code paths that expect tenant-scoped RBAC tables exist in `t_dev` as well.

If you do not want `t_dev` seeded, pass `--no-seed-t-dev`.

## How to Run
From repo root:

```powershell
$env:MPANGO_ENV = "test"
python .\scripts\seed_test_tenant.py
```

Optional override:
- `python .\scripts\seed_test_tenant.py --no-seed-t-dev`
- `python .\scripts\seed_test_tenant.py --allow-production`

## Assumptions
- Postgres is reachable via `DATABASE_URL` (from `backend/core/config.py` settings).
- `public.wholesalers` table exists (migrations applied).
- Script may create tenant-scoped RBAC tables if they don’t exist yet.
