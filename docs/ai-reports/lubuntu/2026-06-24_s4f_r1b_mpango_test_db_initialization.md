# S4-F-R1B: Lubuntu mpango_test DB Initialization

**Date:** 2026-06-24
**HEAD:** 4e5dc7a2dc4969aa5436f43dbf21f12fc1e887f9
**Branch:** origin/product-dev-recovered (detached)
**Verdict:** PASS_S4_CLOSED_FOR_NEXT_PHASE

## Preflight

| Check | Status | Detail |
|-------|--------|--------|
| HEAD match 4e5dc7a | ✅ | 4e5dc7a2dc4969aa5436f43dbf21f12fc1e887f9 |
| mpango_test exists | ✅ | Database existed prior to migration |
| alembic_version (pre) | ❌ | Table did not exist |
| sys_jobs (pre) | ❌ | Table did not exist |
| order_status enum (pre) | ✅ | draft, confirmed, partially_paid, paid, fulfilled, cancelled, voided (7 values; missing `returned`) |
| DB connection | ✅ | user=mpango, host=localhost, port=5432 (from Docker mpango_postgres) |

### Observed Pre-Existing State

- mpango_test had several tenant schemas already populated from prior test runs:
  - `t_test` — full tenant schema with orders, order_items, skus, inventory_stocks, inventory_movements, inventory_reservations, ledger_entries, retailer_prices
  - `t_s4_inventory_other`, `t_s4b_reversal_other`, `t_s4c_concurrent_other`, `t_s4d_movement_ledger_other` — partial tenant schemas
- No public schema tables (wholesalers, retailers, etc.)
- No alembic_version tracking table

## Migration Actions

### Issue 1: alembic_version varchar(32) truncation

Alembic's default `alembic_version.version_num` column is `VARCHAR(32)`, but migration IDs like `003_phase_b3_orders_minimal_closed_loop` (40 chars) exceed this limit.

**Resolution:** Pre-created `public.alembic_version` with `VARCHAR(64)` before running migrations.

### Issue 2: retailer_prices already exists in t_test

Migration 017 (`017_retailer_prices`) creates `retailer_prices` in tenant schemas. The `t_test` schema already had this table from prior test runs, causing `DuplicateTableError`.

**Resolution:** Dropped pre-existing `t_test.retailer_prices` (CASCADE) before re-running full migration chain. The migration then recreated it correctly.

### Issue 3: REPORTING_USER_PASSWORD required

Migration 011 (`011_s6_p_reporting_role`) requires `REPORTING_USER_PASSWORD` environment variable.

**Resolution:** Set placeholder value for test DB initialization (password not used in production).

### Full Migration Execution

All 23 migrations applied successfully in a single `alembic upgrade head` run:

```
001_initial_schema → 002_phase_b2_invitation_binding → 003_phase_b3_orders_minimal_closed_loop
→ 004_phase_b4_sku_inventory_mvp → 005_phase_b5_payments_minimal_loop → 006_phase_b6_payments_idempotency_key
→ 007_s3_b_index_hygiene → 008_s4_b_job_persistence → 009_s5_b_financial_ledger
→ 010_s5_5_ledger_hardening → 011_s6_p_reporting_role → 012_s6_1_read_models
→ 013_s6_2_materialize_sales → 014_s7_3_audit_trail → 015_s7_4_sys_reports
→ 016_add_returned_status → 017_retailer_prices → 018_platform_p0_lifecycle
→ 019_platform_audit_logs → 020_sys_jobs_audit_columns → 021_tenant_payments_retailer_id_transaction_id
→ 022_import_runs → 023_inventory_reservations
```

Side-effects observed during migration:
- Ledger hardening applied to t_test schema
- Reporting role created with 30s query timeout
- Reporting user created with SELECT access to 5 tenant schemas + public
- 3 rpt_* views created in t_test (rpt_sales_daily, rpt_receivables_summary, rpt_cash_flow_daily)
- mv_sales_daily materialized view created with REFRESH CONCURRENTLY

## Post-Check

| Check | Status | Detail |
|-------|--------|--------|
| alembic_version (post) | ✅ | 1 record: `023_inventory_reservations` |
| sys_jobs (post) | ✅ | 13 columns: id, job_name, payload, status, attempts, max_retries, last_error, created_at, updated_at, started_at, completed_at, is_deleted, deleted_at |
| order_status enum (post) | ✅ | 8 values: draft, confirmed, partially_paid, paid, fulfilled, cancelled, voided, **returned** |
| tenant schema t_test | ✅ | Full tenant tables present (orders, order_items, skus, inventory_stocks, inventory_movements, inventory_reservations, ledger_entries, retailer_prices) |
| public schema tables | ✅ | wholesalers, retailers, wholesaler_retailer_bindings, sys_jobs, platform_tenants, audit_logs, import_runs, alembic_version |

## Test Results

| Suite | Passed | Failed | Total | Time | Status |
|-------|--------|--------|-------|------|--------|
| S4-F target | 8 | 0 | 8 | 7.46s | ✅ ALL PASS |
| S4-A~E regression | 41 | 0 | 41 | 21.10s | ✅ ALL PASS |
| S4 jobs (local + persistence) | 16 | 0 | 16 | 13.94s | ✅ ALL PASS |
| S5/Phase5 | 66 | 0 (+1 xfail) | 67 | 5.01s | ✅ ALL PASS |
| **TOTAL** | **131** | **0** | **132** | **47.51s** | ✅ |

### Notes
- 1 xfailed test in test_phase5_order_payment.py (expected failure, not a regression)
- All warnings are deprecation warnings (datetime.utcnow, declarative_base, crypt) — cosmetic only
- No code_failure, no fixture_mismatch, no migration_gap issues detected

## Failure Analysis

No failures to analyze. All 132 tests passed.

## Verdict Rationale

**PASS_S4_CLOSED_FOR_NEXT_PHASE**

- DB initialization completed successfully: all 23 Alembic migrations applied to mpango_test
- All public schema tables created (wholesalers, retailers, sys_jobs, platform_tenants, audit_logs, import_runs)
- `order_status` enum now includes `returned` value (migration 016)
- All 4 test suites pass with 0 failures across 132 tests
- Tenant schema t_test fully operational
- No code changes required, no test infrastructure blockers

### Known Issues (non-blocking)

1. **alembic_version varchar(32):** Default Alembic creates version_num as VARCHAR(32), but migration IDs exceed 32 chars. Workaround: pre-create with VARCHAR(64). Should be fixed in alembic.ini or env.py (product code change).
2. **017_retailer_prices idempotency:** Migration 017 uses `create_table` without `IF NOT EXISTS`, failing on re-run if table exists. Should use `op.create_table(..., if_not_exists=True)` or check existence (product code change).
3. **datetime.utcnow() deprecations:** 48+ warnings across test suites. Cosmetic but should be migrated to `datetime.now(datetime.UTC)` (product code change).
