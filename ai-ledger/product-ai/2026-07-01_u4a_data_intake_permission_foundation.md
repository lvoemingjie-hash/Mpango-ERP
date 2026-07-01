# U4-A -- Data Intake Permission & Product Gate Foundation

**Date**: 2026-07-01
**Executor**: CodeBuddy
**Branch**: `codebuddy/u4a-data-intake-permission-foundation-2026-07-01`
**Lineage**: `origin/product-dev-recovered`
**Verdict**: `PASS_FOR_CTO_U4A_REVIEW`

---

## 1. Objective

Prepare permission and frontend gate foundation for U4 Data Intake. This is a
small, bounded task: fix an incorrect product gate, add a centralized permission
helper, declare Data Intake permission constants, and seed them in the backend.

**No Data Intake tables, upload/parser, routes, or features are built.**
This is permission vocabulary + gate infrastructure only.

---

## 2. Audit Finding -- Incorrect Product Gate (Bug Fixed)

### Before (BUG)

`frontend/src/pages/skus/SKUListPage.tsx:22`:
```tsx
const canWrite = user?.permissions.includes('inventory:write') || user?.roles.includes('admin');
```

The "Add Product" and "Edit" buttons were gated on **`inventory:write`** -- the
wrong domain. A user with `inventory:write` (a warehouse-adjustment permission)
but without any `skus:*` permission could create/edit products. Conversely, a
user with `skus:create` but not `inventory:write` was **blocked** from creating
products despite having the correct product permission.

### After (FIXED)

Replaced with proper per-action gates using the centralized helper:
```tsx
const canCreate = can(user, SKU_PERMISSIONS.CREATE);  // 'skus:create'
const canUpdate = can(user, SKU_PERMISSIONS.UPDATE);  // 'skus:update'
const canImport = can(user, SKU_PERMISSIONS.IMPORT);  // 'skus:import'
```

Also restructured the action area: the Add Product and Import buttons are now
independently gated (previously Import was nested inside the write gate, so a
user with only `skus:import` could not see the Import button).

---

## 3. Centralized Permission Helper

**New file**: `frontend/src/utils/permissions.ts`

| Function | Behavior |
|----------|----------|
| `isAdmin(user)` | True if user holds `admin` or `super_admin` role |
| `can(user, permission)` | True if admin OR user holds the exact permission code. Null user = false. |
| `canAny(user, permissions[])` | True if admin OR user holds any of the codes. Null user = false. |

**Constants declared**:
- `SKU_PERMISSIONS`: `{READ, CREATE, UPDATE, IMPORT}`
- `INTAKE_PERMISSIONS`: `{READ, CREATE, UPDATE, APPROVE, EXPORT, IMPORT_TO_ERP}`
- `ALL_INTAKE_PERMISSIONS`: array of all 6 intake codes

These constants are documentation/foundation only. No routes or handlers
reference them yet -- U4 will wire the actual Data Intake features.

---

## 4. Backend Permission Seeds

Added 6 Data Intake permissions to all 4 centralized seed scripts:

| Script | Role |
|--------|------|
| `backend/scripts/seed_demo_data.py` | Demo/dev environment |
| `backend/scripts/create_wholesaler.py` | New wholesaler onboarding |
| `backend/scripts/onboard_tenant.py` | Tenant onboarding |
| `backend/scripts/seed_test_tenant.py` | Test tenant bootstrap |

Each script now includes:
```python
("intake:read", "Read data intake batches"),
("intake:create", "Create data intake batches"),
("intake:update", "Update data intake batches"),
("intake:approve", "Approve data intake batches for ERP import"),
("intake:export", "Export data intake batches"),
("intake:import_to_erp", "Import approved data intake into ERP"),
```

These permissions are added to the `admin` role automatically by the existing
seed logic. Non-admin roles do not receive them until explicitly granted.

The `test_u1_bootstrap_permission_completeness.py` `known_valid_extras` set was
updated to include the 6 intake codes (documented as foundation-only, no
API-decorated endpoints yet).

---

## 5. Files Changed

| File | Change |
|------|--------|
| `frontend/src/utils/permissions.ts` | **NEW**: `can()`, `canAny()`, `isAdmin()` + `SKU_PERMISSIONS`, `INTAKE_PERMISSIONS` constants |
| `frontend/src/tests/permissions.test.ts` | **NEW**: 19 tests for permission helper behavior |
| `frontend/src/pages/skus/SKUListPage.tsx | Fixed gate (`inventory:write` -> `skus:create`/`skus:update`), separated Create/Import gates, uses centralized `can()` |
| `frontend/src/tests/SKUListPage.test.tsx` | Updated import tests + added 4 create-gate tests |
| `backend/scripts/seed_demo_data.py` | +6 intake permissions |
| `backend/scripts/create_wholesaler.py` | +6 intake permissions |
| `backend/scripts/onboard_tenant.py` | +6 intake permissions |
| `backend/scripts/seed_test_tenant.py` | +6 intake permissions |
| `backend/tests/test_u1_bootstrap_permission_completeness.py` | +6 intake codes in `known_valid_extras` |

---

## 6. Test Results

### Frontend -- Permission Helper (NEW, 19 tests)

```
src/tests/permissions.test.ts -- 19 passed
```

Covers: `isAdmin` (5), `can` (6), `canAny` (5), constants (3).

### Frontend -- SKUListPage Gate (8 tests)

```
src/tests/SKUListPage.test.tsx -- 8 passed
```

Import gate (4 existing, updated): visible with `skus:import`, visible for
admin, hidden without perm, hidden for unauthenticated.

Create gate (4 new U4-A): visible with `skus:create`, **hidden with
`inventory:write` only** (proves fix), visible for admin, hidden for
unauthenticated.

### Frontend -- Full Suite Regression (50 tests)

```
Total: 50 | Pass: 50 | Fail: 0
```

All existing tests pass alongside the new ones. No regressions.

### Backend -- Seed Permission Completeness (33 tests)

```
poetry run pytest tests/test_u3b1_contract_foundation.py
                     tests/test_u1_bootstrap_permission_completeness.py
======================== 33 passed, 1 warning in 0.99s ========================
```

All permission completeness tests pass after adding intake codes to
`known_valid_extras`.

---

## 7. Quality Gates

| Check | Status |
|-------|--------|
| `git diff --check` | PASS |
| ASCII / mojibake scan on new files | PASS (0 matches) |
| Secret scan | PASS (0 matches) |
| Linter diagnostics | PASS (0 errors on all files) |
| pre-commit hooks | PASS (run at commit) |
| No new dependencies | PASS |
| No Data Intake tables/routes/upload | PASS |
| No deploy / no `product-dev-recovered` push | PASS |

---

## 8. What This Enables for U4

1. **Correct product gates**: Users with `skus:create`/`skus:update` can now
   manage products; `inventory:write` users no longer bypass product gates.
2. **Centralized helper**: Future pages use `can()`/`canAny()`/`isAdmin()`
   instead of repeating ad-hoc permission checks.
3. **Intake permission vocabulary**: Declared in both frontend constants and
   backend seeds, ready for U4 to wire routes, tables, and handlers.
4. **Admin auto-grant**: Any admin user bootstrapped after this change will
   automatically have all 6 intake permissions.

---

## 9. Explicit Non-Actions

- Did NOT create Data Intake tables.
- Did NOT build upload/parser.
- Did NOT add routes.
- Did NOT deploy.
- Did NOT push `product-dev-recovered`.
- Did NOT introduce new dependencies.
