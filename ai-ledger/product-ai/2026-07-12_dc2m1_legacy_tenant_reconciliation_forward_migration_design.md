# DC-2M1 Legacy Tenant Reconciliation Forward-Migration Design Gate

Date: 2026-07-12
Branch: `opencode/dc2m1-legacy-tenant-reconciliation-design-2026-07-12`
Baseline: `origin/product-dev-recovered @ 458c0219ddea27fef9754e67521402d145743161`
Status: `DESIGN_READY_FOR_CTO_REVIEW`

## Scope

This gate is design and test planning only. It does not modify production code, Alembic migrations, tenant bootstrap code, frontend code, configuration, lockfiles, deployed infrastructure, or VPS state.

The confirmed gap is in legacy tenant reconciliation: a tenant schema can already have `retailer_prices` with the correct business uniqueness on `(retailer_id, sku_id)` but under a noncanonical legacy name. Current reconciliation requires the canonical name `uq_retailer_prices_retailer_sku`; when that name is absent, G1 fails and the same reconcile run never reaches the reporting reconciliation that should ensure `mv_sales_daily` and `idx_mv_sales_daily_u1` exist.

## Non-Negotiable Decision

Historical migration `017_retailer_prices.py` must not be modified.

Reasons:

- It is already part of the historical Alembic chain and may have run in existing environments.
- Rewriting history would make database state depend on when an environment first migrated.
- The safe repair is a new forward migration plus matching reconciliation/test coverage.

## Current Contract Summary

`backend/alembic/versions/017_retailer_prices.py` defines the tenant table contract:

- Table: `retailer_prices`
- Required columns include `id`, `retailer_id`, `sku_id`, `price`, audit columns, and soft-delete columns.
- Required unique constraint name: `uq_retailer_prices_retailer_sku`
- Required check constraint name: `ck_retailer_prices_positive_price`
- Required indexes: `ix_retailer_prices_retailer_id`, `ix_retailer_prices_sku_id`

`backend/alembic/versions/013_s6_2_materialize_sales.py` defines the sales materialized view contract:

- Materialized view: `mv_sales_daily`
- Unique index: `idx_mv_sales_daily_u1` on `(transaction_date, reporting_currency_code)`
- The unique index is required for `REFRESH MATERIALIZED VIEW CONCURRENTLY`.

`backend/scripts/bootstrap_tenant_schema.py` currently runs reconciliation in this order:

1. `_reconcile_payments`
2. `_reconcile_retailer_prices`
3. `_reconcile_reporting`
4. `_reconcile_import_runs`
5. `_reconcile_intake_tables`

Therefore, G1 must not stop on a compatible legacy unique name, or G2 is blocked in the same run.

## Forward-Migration Design

Create a new forward migration after the current head:

- File: `backend/alembic/versions/031_legacy_tenant_reconciliation.py`
- Revision: `031_legacy_tenant_reconciliation`
- Down revision: `030_platform_backup_status_source`
- Mode: public Alembic run that discovers tenant schemas; do not run with `-x tenant_schema`.

The migration must iterate tenant schemas that are eligible for reconciliation. Eligibility should be conservative:

- Include schemas matching the tenant schema convention, such as `t_%`.
- For G1, operate only when `retailer_prices` exists.
- For G2, operate only when `ledger_entries` exists, because the materialized view depends on it.
- If a schema has neither object, skip it as not relevant to this repair.

### G1: Legacy `retailer_prices` Unique Name Compatibility

The migration must validate the existing `retailer_prices` table before changing it.

Required validation:

- Required columns exist.
- Column types are compatible with migration `017` expectations.
- Required non-null columns are non-nullable.
- `price` is `numeric(12,2)`.
- Existing canonical constraints, if present, match the expected definition.
- Existing same-name indexes, if present, match the expected definition.
- Existing data has no duplicate `(retailer_id, sku_id)` pairs.
- Existing data has no rows violating `price > 0` before adding or validating the check constraint.

Repair behavior:

- If `uq_retailer_prices_retailer_sku` exists and is exactly a unique constraint over `(retailer_id, sku_id)`, leave it untouched.
- If the canonical unique constraint is absent but the table shape and data are compatible, add the canonical unique constraint with `ALTER TABLE ... ADD CONSTRAINT uq_retailer_prices_retailer_sku UNIQUE (retailer_id, sku_id)`.
- Do not drop or rename legacy noncanonical unique constraints in this slice. Keeping the legacy constraint preserves rollback simplicity and avoids destructive assumptions.
- If a compatible noncanonical unique constraint already exists, the canonical constraint may duplicate the same guarantee. That is acceptable for this repair because it preserves all rows and creates the canonical contract required by code/tests.
- If the canonical name is already used for an incompatible object, fail closed.
- If duplicate data prevents adding the canonical unique constraint, fail closed and report the schema/table needing manual data resolution.

This approach is forward-compatible with old unique names because it does not require knowing every old name. It validates the table and data, then establishes the canonical named guarantee additively.

### G2: Continue To Reporting Reconciliation In The Same Flow

After G1 succeeds for a schema, the same migration flow must continue to reporting reconciliation for that schema.

Required G2 behavior:

- If `ledger_entries` exists and `mv_sales_daily` is missing, create `mv_sales_daily` with the same SQL shape as migration `013`.
- If legacy `rpt_sales_daily` exists and `mv_sales_daily` is missing, drop only the old view before creating the materialized view, matching migration `013` behavior.
- Always ensure `idx_mv_sales_daily_u1` exists and is a unique index over `(transaction_date, reporting_currency_code)`.
- If an index named `idx_mv_sales_daily_u1` exists with any incompatible definition, fail closed.
- Grant `SELECT` on `mv_sales_daily` to `reporting_role` after the object exists.
- If `reporting_role` is missing, fail closed because migration `011` should have created it.

The implementation test must prove that a legacy tenant with a noncanonical `retailer_prices` unique name and no `mv_sales_daily` is repaired in one run: the canonical unique constraint is present, `mv_sales_daily` is present, and `idx_mv_sales_daily_u1` is present.

## Idempotency And Data Preservation

The migration and bootstrap reconciliation changes must be repeatable.

Idempotency requirements:

- Running the migration twice must be a no-op after the first successful run.
- Running bootstrap reconciliation twice on the same tenant must be a no-op after the first successful run.
- Existing business rows in `retailer_prices`, `ledger_entries`, and all other tenant tables must remain intact.
- The migration must not delete, truncate, rewrite, or deduplicate business rows.

Data preservation rules:

- Never resolve duplicates automatically.
- Never coerce unknown column types automatically.
- Never silently replace incompatible constraints or indexes.
- Fail with a schema-qualified error message instead.

## Fail-Closed Rules

The implementation must raise and stop on unknown or incompatible structures, including:

- Missing required `retailer_prices` columns on an existing table.
- Nullable required columns.
- Incompatible `retailer_id`, `sku_id`, `price`, or audit column types.
- `price` precision/scale that is not `numeric(12,2)`.
- Duplicate `(retailer_id, sku_id)` pairs.
- `price <= 0` rows before check constraint enforcement.
- Canonical constraint name present with wrong columns or wrong constraint type.
- Canonical index name present with wrong uniqueness, columns, predicate, expression, or target relation.
- `mv_sales_daily` present as a non-materialized relation when a materialized view is required.
- `idx_mv_sales_daily_u1` present but not a unique index on `(transaction_date, reporting_currency_code)`.
- Missing `reporting_role` when reporting objects need grants.

Failure must happen before destructive changes. Error messages must identify the tenant schema and object.

## New-Tenant Bootstrap Behavior

New tenant bootstrap behavior must not change.

The existing `CREATE TABLE IF NOT EXISTS` path for a missing `retailer_prices` table already creates the canonical `uq_retailer_prices_retailer_sku` constraint. The next implementation slice must not change:

- Tenant schema naming.
- Onboarding claim/provisioning state transitions.
- RBAC seeding behavior.
- New tenant table list.
- Public `wholesalers` or `tenant_registrations` behavior.
- Frontend onboarding behavior.

Only the reconciliation branch for already-existing tenant objects should be changed.

## Next Implementation Slice Boundaries

Allowed files for the next implementation slice:

- `backend/alembic/versions/031_legacy_tenant_reconciliation.py`
- `backend/scripts/bootstrap_tenant_schema.py`
- `backend/tests/test_dc2m2_legacy_tenant_reconciliation_forward_migration.py`
- `backend/tests/test_u6h3_tenant_provisioning_reconcile_cleanup.py` only if existing reconcile tests need a new targeted case
- `backend/tests/test_payments_schema_contract.py` only if static contract coverage must be extended
- `ai-ledger/product-ai/2026-07-12_dc2m2_legacy_tenant_reconciliation_implementation.md`

Forbidden files for the next implementation slice:

- `backend/alembic/versions/017_retailer_prices.py`
- Any already-applied historical migration before `031`
- Frontend files
- Production compose/config/env files
- Lockfiles
- Onboarding API/service files unless CTO explicitly expands scope
- Auth, RBAC, pricing API, reporting API, or dashboard runtime logic unless CTO explicitly expands scope

Migration numbering strategy:

- Use exactly one new revision after the current head: `031_legacy_tenant_reconciliation`.
- Do not branch the Alembic graph.
- Do not edit old revisions.
- The migration should be additive and schema-repair oriented.

Rollback boundary:

- Downgrade may drop only objects introduced by `031` when safe, primarily the canonical duplicate `uq_retailer_prices_retailer_sku` added by the migration and `idx_mv_sales_daily_u1` / `mv_sales_daily` only when they were created by this migration.
- Downgrade must not drop or alter legacy noncanonical constraints.
- Downgrade must not delete business rows.
- Downgrade must not attempt to restore broken legacy drift.
- Operational rollback for a failed deploy is application rollback plus database restore/snapshot if the migration already committed in production.

## Test Matrix For Next Slice

Static tests:

- Verify migration `031` exists and has `down_revision = '030_platform_backup_status_source'`.
- Verify migration `017_retailer_prices.py` is unchanged from baseline.
- Verify forbidden files are not changed.
- Verify bootstrap source still creates new `retailer_prices` with canonical `uq_retailer_prices_retailer_sku`.
- Verify migration source contains no row-deleting operations for tenant business tables.

Unit-style helper tests:

- Existing canonical unique constraint: pass and remain idempotent.
- Legacy noncanonical unique constraint over `(retailer_id, sku_id)`: add canonical constraint and preserve rows.
- Missing unique constraint with no duplicates: add canonical constraint and preserve rows.
- Missing unique constraint with duplicates: fail closed before changes.
- Canonical unique name with wrong definition: fail closed.
- Unknown or incompatible column type: fail closed.
- Existing compatible check constraint: pass.
- Missing check constraint with all positive prices: add or validate canonical check.
- Missing check constraint with nonpositive rows: fail closed.

Integration tests with PostgreSQL:

- Create a tenant schema with legacy `retailer_prices` using an unnamed or noncanonical unique constraint, existing business rows, `ledger_entries`, no `mv_sales_daily`, and no `idx_mv_sales_daily_u1`. Run the migration. Assert canonical unique constraint exists, row count is unchanged, `mv_sales_daily` exists, and `idx_mv_sales_daily_u1` is unique.
- Run the migration a second time. Assert no errors and no row changes.
- Create a tenant schema where `idx_mv_sales_daily_u1` exists with an incompatible definition. Assert migration fails closed.
- Create a tenant schema where `mv_sales_daily` exists as a standard view or table. Assert migration fails closed unless the implementation explicitly handles that case safely.
- Bootstrap reconciliation test: create a partial failed tenant schema with noncanonical `retailer_prices` uniqueness and missing reporting objects, then run `bootstrap`. Assert the same run reaches both G1 and G2.

New-tenant regression tests:

- Fresh bootstrap still creates all expected tenant tables.
- Fresh bootstrap still creates canonical `retailer_prices` constraint directly.
- Fresh bootstrap still creates `mv_sales_daily` and `idx_mv_sales_daily_u1`.
- Tenant provisioning reconcile still does not seed RBAC/admin rows unexpectedly.
- Complete schema provisioning still does not rerun bootstrap unnecessarily.

Validation commands for next slice:

- `poetry run pytest tests/test_dc2m2_legacy_tenant_reconciliation_forward_migration.py -q`
- `poetry run pytest tests/test_payments_schema_contract.py -q --tb=short`
- `poetry run pytest tests/test_u6h3_tenant_provisioning_reconcile_cleanup.py -q --tb=short`
- `poetry run pytest tests/test_u1r1_bootstrap_completeness.py -q --tb=short`
- `git diff --check`
- ASCII and mojibake scan on changed files and added diff lines
- `pre-commit run --files <changed files>`
- `npx gitnexus analyze`
- `npx gitnexus status`

## Risk Assessment

Risk: Medium.

Reasons:

- The change touches tenant schema reconciliation and database DDL.
- It must run against potentially drifted legacy schemas.
- It is data-preserving and additive, but database DDL failures can stop deployment if incompatible drift exists.

Risk controls:

- Fail closed on unknown/incompatible structures.
- Preserve all business rows.
- Keep historical migration `017` immutable.
- Use a new forward migration only.
- Test both migration and bootstrap reconciliation paths.
- Keep new-tenant bootstrap behavior unchanged.

## Evidence For This Design Gate

- `git diff --check`: passed.
- ASCII scan: passed; no non-ASCII matches in the report.
- Mojibake scan: passed; no mojibake matches in the report.
- `poetry run detect-secrets scan ..\ai-ledger\product-ai\2026-07-12_dc2m1_legacy_tenant_reconciliation_forward_migration_design.md`: passed with empty `results`.
- `poetry run pre-commit run --config ..\.pre-commit-config.yaml --files ..\ai-ledger\product-ai\2026-07-12_dc2m1_legacy_tenant_reconciliation_forward_migration_design.md`: passed, including `Detect secrets`.
- `npx gitnexus analyze`: repository indexed successfully; `12,444 nodes`, `37,590 edges`, `797 clusters`, `300 flows`.
- `npx gitnexus status`: indexed commit `458c021`, current commit `458c021`, status up to date.

## Verdict

`PASS_FOR_IMPLEMENTATION_PLANNING_REVIEW`
