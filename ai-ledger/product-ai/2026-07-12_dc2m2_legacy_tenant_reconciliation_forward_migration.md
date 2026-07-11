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

## Verdict

Implementation has R1 DB-backed evidence and is ready for CTO review.
