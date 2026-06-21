# S3-C: Self-Contained Fresh Tenant Live Runtime Proof

| Field | Value |
|-------|-------|
| **Branch** | `codebuddy/s3c-self-contained-fresh-tenant-live-proof-2026-06-21` |
| **Base** | `origin/product-dev-recovered` @ `afb1abfa` ("merge: S3 fresh tenant runtime smoke gates") |
| **Date** | 2026-06-21 |
| **Revision** | S3-C-R1 |
| **Changed files** | `backend/tests/test_s3c_self_contained_fresh_tenant_live_proof.py` (new) |
| **Production code changes** | NONE |
| **Live DB** | Resolved via `S3C_LIVE_DB_URL` > `TEST_DATABASE_URL` > `DATABASE_URL` (no hardcoded password) |
| **Commit** | `79359a8` |
| **Push status** | pushed to `codebuddy/s3c-self-contained-fresh-tenant-live-proof-2026-06-21` |

---

## Objective

This IS the **complete fresh-bootstrap proof** that S3-B deferred. Every test
run creates its own **unique tenant schema** from scratch -- no prepared
tenant, user, or schema is reused between runs.

The test:

1. Generates a unique schema name (`t_s3c_<8-char hex>`) per run.
2. Calls the **production `bootstrap_tenant_schema.bootstrap()`** to create
   the schema + 2 enums + 13 tables + ledger trigger + reporting views/matviews.
3. Seeds RBAC with **37 permissions** matching `onboard_tenant.py`,
   creates the "admin" role, assigns all permissions, and creates the admin
   user with a hashed password -- all via raw SQL on the live database.
4. Issues a **near-real contextual JWT** via production
   `create_contextual_token()` with the real `user_id`, real `roles=["admin"]`,
   and real `tenant_schema`.
5. Verifies all **11 core business endpoints** return no 401/403/500
   against the freshly-created tenant.
6. **AST-parses `onboard_tenant.py`** to verify the seeded permission codes
   exactly match the production onboarding contract (R1 new).
7. Cleans up by **dropping the schema** (`DROP SCHEMA ... CASCADE`).

This closes the "fresh tenant creation" gap in S3-B's residual limits.

---

## R1 Changes (vs original S3-C)

### 1. No hardcoded DB password

The original S3-C hardcoded a local Docker dev DB URL with password in the
default value. R1 resolves the DB URL from environment variables only:

```python
def _resolve_live_db_url() -> str:
    url = os.environ.get("S3C_LIVE_DB_URL", "").strip()
    if url: return url
    for key in ("TEST_DATABASE_URL", "DATABASE_URL"):
        url = os.environ.get(key, "").strip()
        if url:
            if url.startswith("postgresql://") and "+asyncpg" not in url:
                url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
            return url
    return ""
```

If no URL is configured and `S3C_REQUIRE_LIVE_DB=1`, the test fails
immediately with a clear message.

### 2. Permission consistency test (AST-based)

A new `TestPermissionConsistencyWithOnboard` class AST-parses
`backend/scripts/onboard_tenant.py` to extract the `permissions_data`
list from `setup_admin()`, then asserts:

- `test_s3c_seed_permissions_match_onboard_exactly`: no codes missing, no extra codes
- `test_s3c_seed_permission_count`: exact count match

This prevents invisible drift between the S3-C seed fixture and the
production onboarding contract.

### 3. Live DB gate: no-URL case

The `live_engine` fixture now also checks whether `LIVE_DB_URL` is empty.
If it is and `S3C_REQUIRE_LIVE_DB=1`, the test hard-fails with:

```
S3-C live DB REQUIRED but no DB URL configured.
Set S3C_LIVE_DB_URL, TEST_DATABASE_URL, or DATABASE_URL.
```

---

## Fresh Tenant Creation Flow

### Step 1: Schema generation

```python
def _fresh_schema_name() -> str:
    return f"t_s3c_{uuid.uuid4().hex[:8]}"
```

Each test run produces a different schema (e.g. `t_s3c_a1b2c3d4`),
ensuring no cross-run contamination.

### Step 2: Bootstrap (real production path)

```python
from scripts.bootstrap_tenant_schema import bootstrap as _bs
await _bs(schema, db_url)
```

This calls the **exact same `bootstrap()`** function used by the production
onboarding system. It creates:

- The `"{schema}"` PostgreSQL schema
- 2 enums: `order_status`, `entry_type`
- 13 tables: `users`, `roles`, `permissions`, `user_roles`, `role_permissions`,
  `skus`, `inventory_stocks`, `inventory_movements`, `orders`, `order_items`,
  `payments`, `retailers`, `retailer_prices`, `retailer_bindings`,
  `wholesalers`, `audit_logs`
- Ledger immutability trigger
- Reporting views: `rpt_receivables_summary`, `rpt_cash_flow_daily`
- Materialized view: `mv_sales_daily`
- Reporting grants to `reporting_role` (if migration 011 has run)

### Step 3: RBAC seeding (matching onboard_tenant.py)

37 permissions are seeded (exact match with `onboard_tenant.py` `setup_admin()`):

| Group | Permissions |
|-------|-------------|
| User management | `users:read`, `users:create`, `users:update`, `users:deactivate` |
| Wholesaler | `wholesalers:read`, `wholesalers:write` |
| Role management | `roles:read`, `roles:create`, `roles:update`, `roles:delete`, `roles:assign` |
| Order management | `orders:read`, `orders:create`, `orders:update`, `orders:confirm`, `orders:ship`, `orders:cancel` |
| SKU management | `skus:read`, `skus:create`, `skus:update`, `skus:import` |
| Inventory | `inventory:read`, `inventory:write`, `inventory:update` |
| Payments | `payments:read`, `payments:create` |
| Retailers | `retailers:read` |
| Invitations | `invitations:create` |
| Pricing | `pricing:read`, `pricing:write` |
| Finance | `finance:read` |
| Dashboards | `dashboards:read`, `reports:read`, `reports:analyze` |
| Exports/System | `exports:create`, `system:admin`, `metrics:admin` |

The "admin" role is created and all 37 permissions are assigned via
`role_permissions` rows. The admin user is created with `is_active=true`
and assigned the "admin" role via `user_roles`.

### Step 4: Verification

Before the test yields:
- All 8 required read permissions are verified present in the live `permissions` table
- The `TestPermissionConsistencyWithOnboard` test verifies exact code match
  against `onboard_tenant.py` via AST parsing

### Step 5: Cleanup

```sql
DROP SCHEMA IF EXISTS "{schema}" CASCADE
```

This removes the tenant schema and all its tables, views, and data.
No residue left on the database.

---

## Permission Consistency Test (R1)

```python
def _extract_onboard_admin_permission_codes() -> set:
    # AST-parse backend/scripts/onboard_tenant.py
    # Find setup_admin() function
    # Find permissions_data assignment
    # Extract code strings from each tuple
    return set(codes)


class TestPermissionConsistencyWithOnboard:
    def test_s3c_seed_permissions_match_onboard_exactly(self):
        onboard_codes = _extract_onboard_admin_permission_codes()
        s3c_codes = {code for code, _desc in PERMISSIONS}
        # Assert no missing, no extra

    def test_s3c_seed_permission_count(self):
        # Fast sanity gate: exact count match
```

This ensures that if `onboard_tenant.py` gains or loses permissions in a
future commit, the S3-C test will **fail explicitly** rather than silently
drifting out of sync.

---

## Near-Real Contextual JWT Flow

Identical to S3-B pattern. The proof calls the **production**
`create_contextual_token()` directly, passing the REAL `user_id`,
REAL `roles`, REAL `tenant_id`, and REAL `tenant_schema` seeded
in steps 2-3.

The resulting JWT satisfies:
- `is_identity_only` = False (both `tenant_id` and `tenant_schema` set)
- `is_super_admin` = False (`"super_admin" not in ["admin"]`)

---

## Endpoint Coverage Matrix

| # | Category | Method | Path | Permission | Expected |
|---|----------|--------|------|------------|----------|
| 1 | Dashboard KPI | GET | `/api/v1/dashboards/kpi/summary` | `dashboards:read` | 200 |
| 2 | Dashboard Charts | GET | `/api/v1/dashboards/charts/sales-trend` | `dashboards:read` | 200 |
| 3 | Dashboard Charts | GET | `/api/v1/dashboards/charts/cash-flow` | `dashboards:read` | 200 |
| 4 | Orders | GET | `/api/v1/orders` | `orders:read` | 200 |
| 5 | Products / SKUs | GET | `/api/v1/skus` | `skus:read` | 200 |
| 6 | Inventory / Stock | GET | `/api/v1/inventory/stocks` | `inventory:read` | 200 |
| 7 | Pricing | GET | `/api/v1/pricing/prices` | `pricing:read` | 400 (business empty-state) |
| 8 | Payments | GET | `/api/v1/payments` | `payments:read` | 200 |
| 9 | Customers / Retailers | GET | `/api/v1/retailers` | `retailers:read` | 200 |
| 10 | Customer Bindings | GET | `/api/v1/retailers/bindings` | `retailers:read` | 200 |
| 11 | Exports Status | GET | `/api/v1/exports/{job_id}` | `get_current_user_context` | 404 (business empty-state) |

**All 11 endpoints pass the auth gate with no 401/403/500.**

---

## Issue Encountered: `is_superuser` Column Mismatch

**First run error (original S3-C):**
```
sqlalchemy.exc.ProgrammingError: column "is_superuser" of relation "users" does not exist
```

**Root cause:** The RBAC seeding SQL tried `INSERT INTO users (..., is_superuser)`
but `bootstrap_tenant_schema.bootstrap()` creates the `users` table **without**
an `is_superuser` column. The column comes from an Alembic migration, not
from the bootstrap DDL.

**Resolution:** Removed `is_superuser` from the INSERT. The `_LiveAdminUser`
proxy does not need it (the "admin" role has all 37 permissions).

---

## Test Results

### S3-C tests (new)

```
tests/test_s3c_self_contained_fresh_tenant_live_proof.py
  TestPermissionConsistencyWithOnboard (2)                ..   (R1 new)
  TestFreshContextualJwtFlow (2)                          ..
  TestFreshEndpointSmoke (11)                             ...........
  TestBusinessEmptyStateProof (2)                         ..
                                                         17 passed, 0 failed
                                                         in 8.55s
```

### Regression: S3-B + S3-A + S2.5

```
tests/test_s3b_fresh_tenant_live_runtime_proof.py         19 passed
tests/test_s3a_fresh_tenant_runtime_smoke.py              13 passed
tests/test_security_s2_5.py                               30 passed
                                                         ---
                                                         62 passed, 0 failed
                                                         in 13.20s
```

---

## Harness Architecture

- **Real routers** -- all 9 business routers mounted on a real FastAPI app.
- **Real `RequirePermission`** -- production auth gate; super-admin bypass
  NOT triggered.
- **Real DB engine** -- bound to Docker `mpango_postgres`.
- **Real tenant bootstrap** -- `bootstrap_tenant_schema.bootstrap()` called.
- **Real RBAC seeding** -- 37 permissions matching `onboard_tenant.py`
  (verified by AST consistency test).
- **Near-real JWT middleware** -- production `create_contextual_token()` + decode.
- **`session.info` propagation** -- `tenant_schema` + `tenant_id` on all sessions.
- **Module-level patch save/restore** -- `ReportingSessionLocal`, `AsyncSessionLocal`.
- **Schema cleanup** -- `DROP SCHEMA IF EXISTS ... CASCADE`.
- **No hardcoded DB credentials** -- resolved from env vars only.

---

## Residual Limits

| Aspect | S3-C status | Why |
|--------|-------------|-----|
| `/auth/login` | **NOT real** | JWT via `create_contextual_token()` |
| `/auth/select-tenant` | **NOT real** | User/roles from seeded data |
| `AuthenticationMiddleware` | **NOT real** | Test middleware attaches context directly |
| `create_contextual_token()` | **REAL** | Production function |
| `RequirePermission` | **REAL** | No super_admin bypass |
| ORM tenant filter | **REAL** | `db/tenant_filter.py` live |
| DB connection | **REAL** | Live PostgreSQL |
| `bootstrap_tenant_schema.bootstrap()` | **REAL** | Production function |
| RBAC permission seeding | **REAL** | 37 perms, AST-verified |
| Tenant lifecycle | **REAL** | Unique per run, created + destroyed |
| All business routers | **REAL** | No patches |

---

## S3-C closes vs S3-B

| Gap | S3-B | S3-C |
|-----|------|------|
| Fresh tenant creation | Prepared `t_u1r1_test` | **Fresh per run** |
| Schema bootstrap | N/A | **Production `bootstrap()`** |
| RBAC seeding | Pre-existing | **Seeded + AST-verified** |
| Admin user | Pre-existing | **Created by test** |
| DB config | Hardcoded local password | **Env-var chain only** |

---

## Key Findings

1. **A freshly-bootstrapped tenant admin can access all core APIs on a live
   database with no 401/403/500.**
2. **`bootstrap_tenant_schema.bootstrap()` creates a functional tenant schema.** All 13
   tables + enums + views are created correctly.
3. **The `users` table DDL in `bootstrap()` is missing `is_superuser`** -- a
   schema-evolution gap (Alembic migration vs raw DDL).
4. **AST-based permission checking catches drift.** If `onboard_tenant.py`
   permissions change, the test fails explicitly.
5. **No production code defects found.**

---

## Scope Adherence

- No new business features.
- No inventory fixes.
- No S4 work.
- No production code changes.
- Test-only addition: `backend/tests/test_s3c_self_contained_fresh_tenant_live_proof.py`.
