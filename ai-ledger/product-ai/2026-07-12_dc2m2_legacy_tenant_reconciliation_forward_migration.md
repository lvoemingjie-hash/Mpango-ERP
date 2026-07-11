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
- Live registration statuses are imported from `models.tenant_onboarding.LIVE_REGISTRATION_STATUSES`.
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
- DC-2M2 database tests were added but local execution is blocked by local PostgreSQL TCP authentication; no credentials or URLs are recorded here.

## Verdict

Implementation is ready for environment-backed test execution and CTO review once a valid test database connection is available.
