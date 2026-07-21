# DC-11T4E U6I5 Tenant-Schema Teardown Repair

| Field | Value |
|---|---|
| Date | 2026-07-21 |
| Task ID | DC-11T4E (U6I5 Tenant-Schema Teardown Repair) |
| Base | `origin/product-dev-recovered @ 6daa32bf3fd41b37ac53205b86764df757e2e4c7` |
| Branch | `opencode/dc11t4e-u6i5-tenant-schema-teardown-2026-07-21` |
| Verdict | `PASS_FOR_CTO_DC11T4E_REVIEW` |

## 1. Problem

`_clear_u6i5_rows()` deleted `tenant_registrations` and `wholesalers` rows
but never dropped the `t_u6i5_<hex>` schemas created by
`_setup_provisioned_tenant()`. This left orphaned tenant schemas accumulating
across test runs, polluting the database and potentially causing constraint
conflicts or cross-test interference.

## 2. Fix

Extended `_clear_u6i5_rows()` to:
1. Derive candidate schemas ONLY from U6I5 registrations
   (`owner_email LIKE 'u6i5_%@example.com'`).
2. Validate each schema name against the exact `^t_u6i5_[0-9a-f]{20}$`
   regex pattern before any DROP.
3. Use safe quoting (`DROP SCHEMA IF EXISTS "<validated>" CASCADE`).
4. Drop validated schemas BEFORE deleting registrations/wholesalers.
5. Also clean up orphaned `owner_credential_setup_tokens`.
6. Remain idempotent: safe to call repeatedly (IF EXISTS guards).

## 3. Regression Tests Added

- `test_dc11t4e_teardown_removes_u6i5_schemas_and_preserves_others`:
  Creates a U6I5 schema + a non-U6I5 sentinel schema. Runs teardown.
  Asserts: U6I5 schema gone, sentinel survives, zero registrations,
  zero wholesalers, zero `t_u6i5_*` in `pg_namespace`.
- `test_dc11t4e_teardown_is_idempotent`: Runs teardown twice; no error.

## 4. Test Results

| Run | Tests | Leftover schemas |
|---|---|---|
| U6I5 alone (run 1) | 12 passed | 0 |
| U6I5 alone (run 2) | 12 passed | 0 |
| U6I5+U6I6+U6K+U6L (order 1) | 25 passed | 0 |
| U6L+U6K+U6I6+U6I5 (order 2) | 25 passed | 0 |

All grouped runs leave zero `t_u6i5_*` schemas in `pg_namespace`.

## 5. Changed Files

| File | Change |
|---|---|
| `backend/tests/test_u6i5_owner_credential_setup_endpoint.py` | Extended `_clear_u6i5_rows()` + 2 regression tests |
| `ai-ledger/product-ai/2026-07-21_dc11t4e_u6i5_tenant_schema_teardown.md` | This ledger |

## 6. Compliance

- No production code, migration, config, lockfile, or frontend changes.
- No protected-branch push.
- `py_compile`: PASS.
- `git diff --check`: PASS.
- ASCII: 0 non-ASCII.
- `pre-commit` / `detect-secrets`: PASS.

## 7. Verdict

**PASS_FOR_CTO_DC11T4E_REVIEW**
