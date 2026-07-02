# U4-I-B1 Intake Apply Audit Schema Contract

Date: 2026-07-02

Branch: `opencode/u4ib1-intake-apply-audit-schema-contract-2026-07-02`

Base: `origin/product-dev-recovered` at `e7caa48`

Verdict: `PASS_FOR_CTO_U4IB1_REVIEW`

## Scope

U4-I-B1 adds the minimum tenant intake apply lifecycle/audit schema needed for a future staged intake rows -> official SKU apply path.

This branch deliberately does not implement SKU writes, an apply endpoint, frontend changes, deployment changes, or changes to the existing `sku_imports` apply path.

## Schema Contract Added

New tenant migration: `backend/alembic/versions/025_intake_apply_audit.py`.

`intake_workspaces` additions:

- `apply_status VARCHAR(32) NOT NULL DEFAULT 'not_applied'`
- `applied_at TIMESTAMPTZ NULL`
- `applied_by UUID NULL`
- `apply_result JSONB NOT NULL DEFAULT '{}'::jsonb`
- `ck_intake_workspaces_apply_status`: `not_applied`, `applying`, `applied`, `failed`
- `ix_intake_workspaces_apply_status`

`intake_product_rows` additions:

- `target_sku_id UUID NULL`
- `apply_status VARCHAR(32) NOT NULL DEFAULT 'not_applied'`
- `apply_error_code VARCHAR(64) NULL`
- `apply_error_message TEXT NULL`
- `ck_intake_product_rows_apply_status`: `not_applied`, `applied`, `failed`, `skipped`
- `ix_intake_product_rows_target_sku_id`

The migration is no-op when the active `search_path` is not tenant-like (`t_*`) and returns without action if the U4 intake skeleton tables are absent.

## Bootstrap And Reconcile

Updated `backend/scripts/bootstrap_tenant_schema.py` so both fresh and existing tenant paths converge on the same apply audit contract.

- Fresh tenant DDL now creates the new columns, defaults, check constraints, and indexes.
- Existing tenant reconciliation adds missing columns idempotently.
- Existing tenant reconciliation adds missing check constraints idempotently.
- Existing tenant reconciliation ensures the new indexes with the existing `_ensure_index` path.

## ORM Contract

Updated `backend/models/intake.py` only.

- Added apply audit fields to `IntakeWorkspace`.
- Added future target/apply audit fields to `IntakeProductRow`.
- No SKU model, SKU service, SKU router, or SKU import apply code was edited.

## No SKU Write Proof

No code path was added that writes official SKUs.

- No apply endpoint was added.
- No `skus` table write was added.
- No `sku_imports` apply path was edited.
- New static test `test_u4_intake_routes_still_have_no_sku_write_surface` checks U4 intake routes for forbidden SKU/apply/public-token surface strings.
- Existing U4-C/U4-D focused runtime-style tests still pass and continue to exercise staging-only workspace/upload/mapping/validation flows.

## GitNexus Impact

Pre-edit impact checks were run for planned symbols/areas.

- `IntakeWorkspace`: `LOW`
- `IntakeProductRow`: `LOW`
- `_create_indexes`: `LOW`
- `upgrade`: `LOW`
- `024_intake_skeleton`: target not found
- `bootstrap_tenant_schema`: target not found
- `_reconcile_intake_tables`: `HIGH`

The `_reconcile_intake_tables` result is accepted as bounded risk because the implementation is additive, tenant-schema scoped, idempotent, and limited to U4 intake tables. It does not rewrite existing data, does not drop data, and does not touch official SKU tables or apply flows.

Post-edit GitNexus validation:

```text
npx gitnexus analyze
Already up to date

npx gitnexus status
Indexed commit: e7caa48
Current commit: e7caa48
Status: up-to-date
```

## Tests Added Or Updated

Added `backend/tests/test_u4ib1_intake_apply_audit_schema.py`:

- `test_025_migration_adds_apply_audit_columns_defaults_indexes_and_constraints`
- `test_bootstrap_fresh_tenant_has_apply_audit_columns`
- `test_bootstrap_reconciles_existing_tenant_missing_apply_audit_columns`
- `test_u4_intake_routes_still_have_no_sku_write_surface`

Updated existing tests:

- `backend/tests/test_u4c_intake_api_contract.py` now runs `025_intake_apply_audit` after `024_intake_skeleton` in the runtime-style intake API migration helper.
- `backend/tests/test_u4c_intake_backend_schema.py` now expects the new U4-I-B1 indexes.

## Validation

U4-I-B1 contract tests:

```text
poetry run pytest tests/test_u4ib1_intake_apply_audit_schema.py -q
4 passed, 1 warning
```

Focused U4 intake regression suite:

```text
poetry run pytest tests/test_u4c_intake_backend_schema.py tests/test_u4c_intake_api_contract.py tests/test_u4d_intake_parser_preview.py tests/test_u4ib1_intake_apply_audit_schema.py -q
37 passed, 13 warnings
```

Static validation:

```text
git diff --check
passed

poetry run python -m py_compile alembic/versions/025_intake_apply_audit.py models/intake.py scripts/bootstrap_tenant_schema.py tests/test_u4c_intake_api_contract.py tests/test_u4c_intake_backend_schema.py tests/test_u4ib1_intake_apply_audit_schema.py
passed

non-ASCII scan of changed Python files
passed
```

Secret scan note: a broad keyword-only scan found benign existing/test references such as `token`/`public_token` guard strings and environment variable names; no secret values were printed or introduced.

Optional lint note: `poetry run ruff check` on all changed Python files was attempted and is not used as this branch's gate because the touched legacy files currently fail the repo Ruff profile on pre-existing style findings such as `Optional[...]` annotations and import ordering. New actionable findings in the added migration/test helper were cleaned up, and the focused pytest plus compile gates pass.

## Remaining Risks

- This is a schema contract only; the future apply implementation must still enforce tenant ownership, idempotency, SKU write invariants, and audit semantics before writing official SKUs.
- This branch was not deployed by design.
- Existing warnings from pytest configuration and `datetime.utcnow()` remain out of scope.
