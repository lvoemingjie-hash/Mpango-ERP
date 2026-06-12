# U3-C Product Import Apply — validated import_run -> SKUs

**Date:** 2026-06-12
**Branch:** `codebuddy/u3c-product-import-apply-skus-2026-06-12`
**Base:** `origin/product-dev-recovered` at `a988c52`

## Verdict

**PASS_FOR_CTO_REVIEW** (with one STOP_AND_REPORT_CTO finding)

## Summary

Implements U3-C Phase 3 apply: writes validated import rows to the SKU table.

### Key Changes

| File | Change |
|------|--------|
| `backend/services/import_service.py` | Added `apply()` method — reads validated import_run rows, creates SKU records |
| `backend/api/v1/sku_imports.py` | Added `POST /{import_id}/apply` endpoint with `RequirePermission("skus:import")` |
| `backend/schemas/import_schemas.py` | `ImportApplyRequest.on_conflict` restricted to `skip` / `fail` only (no `update`, no `error`) |
| `backend/tests/test_u3c_import_apply.py` | NEW — 28 tests covering all 10 CTO requirements |
| `backend/tests/test_u3b1_contract_foundation.py` | Updated `test_import_apply_request` to verify only skip/fail accepted |
| `backend/tests/test_u3b2_preview_validate.py` | Updated assertions: apply endpoint exists, SKU import allowed in apply method |

### STOP_AND_REPORT_CTO Finding

**`custom_attributes.*` fields in mapping trigger `STOP_AND_REPORT_CTO` (HTTP 422).**

The `SKU` model (`models/sku.py`) has no `custom_attributes` JSONB column. Per CTO directive:

> "如果 SKU 模型无该字段，必须 STOP_AND_REPORT_CTO，不得静默丢弃"

The apply method detects any `custom_attributes.*` entries in the field mapping and raises an explicit `STOP_AND_REPORT_CTO` error with details. The user must either:
1. Ask CTO to approve adding a `custom_attributes` JSONB column to `SKU` model
2. Remove `custom_attributes.*` mappings before applying

### Design Decisions

1. **Fail strategy uses pre-scan**: Before creating any SKU, the fail strategy pre-scans all rows for conflicts. If any conflict is found, the entire operation is rejected with HTTP 409 and zero SKUs are created. This ensures atomicity without relying on partial rollback.

2. **Skip strategy creates SKUs one-by-one**: Each new SKU is added via `db.add(SKU(...))` and the `existing_sku_codes` set is updated in-memory. This prevents intra-import duplicates.

3. **Transaction management**: The endpoint calls `db.commit()` on success and `db.rollback()` on failure. The service method only uses `db.flush()`, leaving final commit to the caller.

4. **No `update` strategy**: Per CTO directive, `update` is not implemented. It requires separate CTO approval.

### Test Coverage (28 tests)

| Requirement | Tests | Count |
|---|---|---|
| (a) Non-validated status rejected | `TestNonValidatedStatus` | 4 |
| (b) Skip strategy | `TestSkipStrategy` | 3 |
| (c) Fail strategy (409, no partial writes) | `TestFailStrategy` | 2 |
| (d) Status becomes 'applied' | `TestStatusTransition` | 1 |
| (e) Counters/audit correct | `TestCountersAndAudit` | 4 |
| (f) No inventory/stock/pricing writes | `TestNoSideEffects` | 3 |
| (g) Permission enforcement | `TestPermissionGuard` | 2 |
| (h) Duplicate apply idempotent | `TestIdempotency` | 2 |
| (i) custom_attributes STOP_AND_REPORT_CTO | `TestCustomAttributesGuard` | 3 |
| (j) Regression guards | `TestRegressionGuards` | 4 |

### Test Results

```
124 passed, 1 warning in 1.36s
```

- U3-B1: 27 passed
- U3-B2: 69 passed
- U3-C: 28 passed
- U3-B2.1 (live DB): 14 errors (no PostgreSQL available — expected)

### Prohibitions Verified

- No frontend wizard
- No image upload
- No barcode/camera
- No inventory / stock movement writes
- No pricing writes
- No auth / tenancy / payments / orders changes
- No deployment
- No new external dependencies
