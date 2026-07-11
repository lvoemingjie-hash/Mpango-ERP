# DC-2M2 Legacy Tenant Reconciliation Forward Migration

Date: 2026-07-12
Branch: `opencode/dc2m2-legacy-tenant-reconciliation-forward-migration-2026-07-12`
Baseline: `origin/product-dev-recovered @ 458c0219ddea27fef9754e67521402d145743161`

## Scope

Implemented a forward-only Alembic migration and matching bootstrap reconciliation for legacy registered tenant schemas whose `retailer_prices` and reporting objects predate the canonical current-head tenant contract.

## Safety Controls

- Historical migration `backend/alembic/versions/017_retailer_prices.py` is not modified.
- New migration is chained after `030_platform_backup_status_source` as `031_legacy_tenant_reconciliation`.
- Tenant enumeration is registry-gated through `public.tenant_registrations` joined to `public.wholesalers`.
- Live registration statuses are defined inside migration `031`; the Alembic migration does not import application models or constants.
- Dynamic migration identifiers are rendered with server-side `quote_ident` before DDL composition.
- Preflight validates all eligible registered schemas before tenant DDL runs.
- Any incompatible schema aborts before mutation with schema/reason evidence only.
- The migration uses `lock_timeout`, `statement_timeout`, and a transaction-scoped advisory lock.
- G1 `retailer_prices` repair runs before G2 reporting repair in the same tenant flow.
- Equivalent legacy unique constraints are renamed to `uq_retailer_prices_retailer_sku`; duplicate canonical constraints are not created.
- Unique-index-only equivalents, partial unique indexes, wrong same-name objects, duplicate business rows, wrong columns/types/nullability, and incompatible reporting objects fail closed.

## Rollback Boundary

This is a forward-only tenant reconciliation. The supported rollback is application-version rollback plus restore from a verified pre-migration database backup/snapshot. The Alembic `downgrade()` raises rather than promising unsafe automatic reversal of tenant-specific legacy drift.

## Validation Status

- `poetry run alembic heads` before implementation: `030_platform_backup_status_source (head)`.
- `poetry run alembic heads` after implementation: `031_legacy_tenant_reconciliation (head)`.
- Python compile validation passed for changed Python files.
- R1 DB environment: local Docker PostgreSQL container `mpango_postgres`, disposable per-run superuser/database over `127.0.0.1:5432`; credentials were generated in-process and not recorded.
- `poetry run pytest tests/test_dc2m2_legacy_tenant_reconciliation_forward_migration.py -q`: 7 passed.
- `poetry run pytest tests/test_u1_bootstrap_permission_completeness.py tests/test_s6_2_materialized_views.py tests/test_s6_3_dashboard_api.py -q`: 38 passed after bootstrapping disposable `t_test` and removing the old bootstrap-only `prevent_ledger_mod` trigger so the pytest fixture owns the ledger immutability trigger.

## DC-2M2-R2 Catalog Relkind Normalization Hotfix

### Runtime Finding

DC-2B-R4 backend unhealthy triage found `031_legacy_tenant_reconciliation` failed closed on a valid index because the PostgreSQL catalog `pg_class.relkind` value was returned by the runtime DBAPI as bytes:

`t_08177e1717de4fdb873d9e18561e732a.ix_retailer_prices_retailer_id: name is occupied by b'i'`

The migration compared raw catalog values against string literals like `"i"`, `"I"`, `"m"`, and `"v"`. That preserved fail-closed behavior but incorrectly rejected valid catalog objects when the driver returned `bytes` or `memoryview` representations.

### Fix

- Added `_catalog_code()` in `backend/alembic/versions/031_legacy_tenant_reconciliation.py`.
- `_catalog_code()` normalizes `None`, `str`, `bytes`, and `memoryview` catalog enum-ish values before compatibility checks.
- `_relation_kind()` now returns normalized relkind values.
- `_label_relkind()`, `_constraint_type()`, and `_validate_or_plan_index()` use normalized catalog values.
- Valid `b"i"`, `b"I"`, and `b"m"` values now compare as `"i"`, `"I"`, and `"m"`.
- Incompatible values such as `b"r"` still fail closed and are labeled as `table`.

### Bootstrap Script Check

`backend/scripts/bootstrap_tenant_schema.py` had the same raw relkind comparison risk in `_relation_kind()` for canonical unique-name checks and reporting object checks. The same `_catalog_code()` normalization was added there. This keeps bootstrap reconcile behavior aligned with migration `031`; no product route/service behavior changed.

### R2 Regression Coverage

- Existing valid index row with `relkind=b"i"` is accepted.
- Existing valid partitioned-index relkind through `memoryview(b"I")` is accepted.
- Existing valid materialized view with `relkind=b"m"` is accepted by reporting preflight.
- Incompatible relkind `b"r"` still fails closed.

### R2 Validation

- `poetry run pytest tests/test_dc2m2_legacy_tenant_reconciliation_forward_migration.py -q`: 11 passed.
- `poetry run pytest tests/test_u1_bootstrap_permission_completeness.py -q`: 6 passed.
- `poetry run alembic heads`: `031_legacy_tenant_reconciliation (head)`.
- `poetry run python -m py_compile alembic/versions/031_legacy_tenant_reconciliation.py scripts/bootstrap_tenant_schema.py tests/test_dc2m2_legacy_tenant_reconciliation_forward_migration.py`: passed.
- Historical migration `backend/alembic/versions/017_retailer_prices.py` was not touched.

## Verdict

Implementation has R1 DB-backed evidence and is ready for CTO review.
