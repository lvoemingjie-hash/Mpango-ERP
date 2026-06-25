# S5-C-R4: Tenant Context Import HTTP Fix - Ledger Report

**Date**: 2026-06-25
**Branch**: `opencode/s5c-r4-tenant-context-import-http-fix-2026-06-25`
**Commits**:
- `0d5bcf9` - tenant_id schema-name vs UUID mismatch fix
- `f61c9ec` - R1 ledger + env-gated runtime HTTP integration test
**Verdict**: `PASS_FOR_CTO_REVIEW`

---

## Problem

`AuthenticationMiddleware.dispatch()` set `request.state.tenant_id` to the tenant schema name, for example `t_xxx`, instead of the tenant UUID string, for example `a0000000-0000-4000-8000-000000000001`.

`sku_imports.py` parses `request.state.tenant_id` with `uuid.UUID(str(tenant_id_str))`. The schema-name value caused `INVALID_TENANT_ID: Could not parse tenant_id from context` during the deployed import HTTP proof.

## Root Cause

The middleware read `tenant_ctx.tenant_schema` where the import route contract requires `tenant_ctx.tenant_id`. `TenantContext` already carries both fields, but the middleware exposed the wrong one through `request.state.tenant_id`.

## Fix

**File**: `backend/api/middleware/auth.py`

```diff
-                    request.state.tenant_id = tenant_ctx.tenant_schema
+                    request.state.tenant_id = str(tenant_ctx.tenant_id)
+                    request.state.tenant_schema = tenant_ctx.tenant_schema
```

- `request.state.tenant_id` is now a UUID string.
- `request.state.tenant_schema` is now available for consumers that need the schema name.

## Blast Radius

- **GitNexus impact**: LOW/MEDIUM review scope, no affected execution flows reported by worker evidence.
- **Changed production symbol**: `AuthenticationMiddleware.dispatch()`.
- **Beneficiary**: SKU import routes can parse tenant UUID correctly.
- **Compatibility check**: no other production code was found depending on `request.state.tenant_id` as a schema name.

## Test Evidence

### Middleware Contract Tests

- `test_middleware_sets_tenant_id_as_uuid` - verifies UUID in `tenant_id`.
- `test_middleware_tenant_id_is_not_schema_name` - regression guard.
- `test_sku_import_can_parse_tenant_id_as_uuid` - import route parsing contract.

Result: `3/3 PASS`.

### Runtime HTTP Integration Test

Added `backend/tests/test_s5c_runtime_sku_import_http_integration.py`.

The test is deployment-gated and skips unless all of these are set:

- `MPANGO_RUNTIME_BASE_URL`
- `MPANGO_RUNTIME_TEST_EMAIL`
- `MPANGO_RUNTIME_TEST_PASSWORD`
- `MPANGO_RUNTIME_TENANT_ID`

Default local result in worker evidence: `2 SKIPPED`, expected because runtime credentials were not provided. This avoids storing deployment secrets or assuming a specific running environment in normal CI.

### Full Regression

Worker-reported aggregate:

| Test Suite | Result |
|------------|--------|
| Middleware contract | 3/3 PASS |
| Runtime HTTP integration | 2 SKIPPED without `MPANGO_RUNTIME_*` |
| S5-A gate | 3/3 PASS |
| S5 state machine | 13/13 PASS |
| S5 ledger | 15/15 PASS |
| Phase5 order payment | 53 passed, 1 xfailed |
| RBAC enforcement | 19 PASS |
| Auth regressions | 2 PASS |
| Search path | 1 PASS |

Total: `113 passed, 2 skipped, 1 xfailed, 0 failed`.

## Quality Gates

- `git diff --check`: CLEAN.
- Mojibake scan: CLEAN after CTO merge-gate ledger normalization.
- GitNexus detect_changes: LOW risk, 0 affected processes per worker report.
- Pre-commit hooks: ALL PASSED.
- No secrets printed.
- No `.env` modified.
- No `product-dev-recovered` push from worker branch.

## Known Issues

These are pre-existing or deployment-state issues and are not introduced by S5-C-R4:

1. Runtime import HTTP proof requires a migrated active tenant schema with `import_runs`.
2. `test_tenant_isolation.py` requires `hypothesis` when that unrelated suite is selected.
3. Deployment validation must be rerun after this merge and redeploy to prove the fix against the live Tencent runtime.

## Verdict

`PASS_FOR_CTO_REVIEW`.

The tenant-context contract fix is isolated, correct, and guarded by unit tests plus an environment-gated runtime HTTP proof. Ready for CTO merge and follow-up deployment validation.
