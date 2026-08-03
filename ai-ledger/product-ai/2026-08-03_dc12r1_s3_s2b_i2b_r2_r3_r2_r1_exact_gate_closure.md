# DC-12R1-S3-S2B-I2B-R2-R3-R2-R1: Exact Gate Closure

**Status**: COMPLETE — all gates green  
**Branch**: `codex/dc12r1-s3-s2b-i2b-payment-declaration-runtime-2026-08-03`  
**Prior commit**: `665e534` (R1 — removed `_CASHIER_EMAIL_CACHE`, added `cashier_identity` fixture)  
**This commit**: R2-R1 — replaced test-harness cashier INSERTs with canonical owner lifecycle  
**Date**: 2026-08-03

**SUPersed**: all prior I2B reports in this directory.

---

## What Changed

### R2-R1: Canonical Owner Lifecycle in `cashier_identity` Fixture

**File**: `backend/tests/test_dc12r1_s3_s2b_i2b_payment_declarations.py`

The `cashier_identity` fixture previously used hand-written SQL INSERTs to create
the admin user, assign the bootstrap admin role, and manually insert
`payments:create` into `permissions` + `role_permissions`.  This was a test-only
shortcut that bypassed the production owner credential lifecycle.

The fixture now uses the canonical production path:

1. `OwnerCredentialSetupService.issue_setup_token(reg_id)` — creates setup token
2. `OwnerCredentialSetupService.consume_setup_token(token, password)` — hashes password, returns `OwnerCredentialSetupConsumeResult`
3. `OwnerCredentialSetupService.create_first_admin_rbac(setup)` — creates admin user, admin role, full `ADMIN_PERMISSIONS` catalog, and role_permissions linkage

**Key assertions verified at fixture setup time**:
- `result.permission_count == len(ADMIN_PERMISSION_CODES)` — full canonical set
- `payments:create ∈ admin permission codes` — was missing from naked bootstrap
- `payments:confirm_declaration ∈ admin permission codes` — bootstrap baseline
- `no client:* permissions` — namespace isolation enforced
- Explicit user_roles + users cleanup in `try/finally` teardown
- Setup token pre-cleaned before issue to handle crashed-prior-test recovery

**Removed**: `hash_password` import (now unused — `consume_setup_token` handles hashing internally)

### H5: `InvalidCachedStatementError` Forensics + Repair

**Files**:
- `backend/tests/test_dc12r1_s3_s2b_i2b_payment_declarations.py` — added `_h5_flush_stmt_cache` module-scoped autouse fixture
- `backend/tests/test_dc12r1_h5_prepared_statement_cache_isolation.py` — new forensics test file

**Root cause**: asyncpg maintains a per-connection prepared-statement cache (default 100 entries). When I2A tests run before I2B, the bootstrap DDL invalidates cached plans on pooled connections. I2B then acquires a connection with stale plans, causing `InvalidCachedStatementError`.

**Repair**: Module-scoped autouse fixture disposes `async_engine` after `provisioned_pool` setup (DDL) completes, before function-scoped tests begin. This is the same pattern already used by `conftest.py`'s `async_session` fixture (line 517).

---

## Gate Evidence

### I2B Natural Order (run 1)
```
42 passed, 0 skipped, 0 failed in 137.70s
```

### I2B Exact Reverse Order
```
42 passed, 0 skipped, 0 failed in 137.09s
```

### I2B Natural Order (run 2 — reproducibility)
```
42 passed, 0 skipped, 0 failed in 137.97s
```

### I2A + I2B Interleaved (run 1)
```
60 passed, 0 failed in 134.55s
```

### I2A + I2B Interleaved (run 2 — reproducibility)
```
60 passed, 0 failed in 134.80s
```

### Frontend Build
```
✓ 1283 modules transformed
✓ built in 12.29s
```

### Frontend TypeScript
Pre-existing errors in test files only (`@testing-library/user-event` missing, unused type imports). No new errors from this change. Production build succeeds.

### Backend Lint
`hash_password` unused import removed. No ruff/mypy available in environment (network timeout on install). Syntax verified via `ast.parse`.

---

## Prohibited Files — Untouched

- `scripts/bootstrap_tenant_schema.py` ✓
- `core/permission_registry.py` ✓
- `services/owner_credential_service.py` ✓
- `services/tenant_provisioning_service.py` ✓
- `scripts/seed_test_tenant.py` ✓
- Product API, migrations, config, dependencies, lockfiles ✓

## Files Changed

1. `backend/tests/test_dc12r1_s3_s2b_i2b_payment_declarations.py` — R2-R1 fixture rewrite + H5 flush fixture + removed unused import
2. `backend/tests/test_dc12r1_h5_prepared_statement_cache_isolation.py` — new H5 forensics test file
