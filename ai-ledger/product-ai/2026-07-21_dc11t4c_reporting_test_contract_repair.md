# DC-11T4C Reporting Test Contract Repair

Date: 2026-07-21

## Verdict

`PASS_FOR_CTO_DC11T4C_REVIEW`

## Branch

- Branch: `opencode/dc11t4c-reporting-test-contract-repair-2026-07-21`
- Base: `origin/product-dev-recovered @ 6daa32bf3fd41b37ac53205b86764df757e2e4c7`
- Commit: `6daa32bf3fd41b37ac53205b86764df757e2e4c7` plus uncommitted working-tree repair

## Modified Files

- `backend/tests/test_s6_2_materialized_views.py`
- `backend/tests/test_s6_3_dashboard_api.py`
- `backend/tests/test_s6_p_reporting_constraints.py`
- `backend/tests/reporting_bootstrap_contract_helpers.py`
- `backend/tests/test_dc11t4c_reporting_bootstrap_contract.py`
- `ai-ledger/product-ai/2026-07-21_dc11t4c_reporting_test_contract_repair.md`

## Scope

- Repaired the 12 DC-11T4A-H2-R1A stale reporting contracts by replacing hard-coded `t_test` reporting-object assumptions with tenant schemas created through `TenantProvisioningService`.
- Preserved public-Alembic expectations separately: `test_public_alembic_alone_does_not_manufacture_tenant_schema` is read-only and proves public migrations alone do not create arbitrary tenant schemas.
- Added fail-closed supported-bootstrap coverage: `test_supported_tenant_bootstrap_creates_reporting_contract` proves provisioned tenants receive `mv_sales_daily`, `rpt_receivables_summary`, `rpt_cash_flow_daily`, `idx_mv_sales_daily_u1`, and `reporting_role` SELECT grants.
- Added teardown proof: `test_reporting_tenant_teardown_removes_schema_and_registry_rows` proves the helper removes its generated tenant schema, `public.tenant_registrations` row, and `public.wholesalers` row.
- No product routes, services, models, Alembic migrations, production bootstrap/reconciliation logic, `create_all`, skips, xfails, deselection, assertion weakening, or manual reporting DDL/GRANT repair were added.

## Tests

- Fresh infra run 1:
  - Infrastructure: PostgreSQL `16.14`, Redis `7.4.7`.
  - Migration: `poetry run alembic upgrade head` completed through `034_platform_operators`; reporting migrations logged 0 tenant schemas at public migration time.
  - Command: `poetry run pytest -q tests/test_s6_2_materialized_views.py tests/test_s6_3_dashboard_api.py tests/test_s6_p_reporting_constraints.py tests/test_dc11t4c_reporting_bootstrap_contract.py --tb=short`
  - Result: `43 passed in 58.49s`
- Fresh infra run 2:
  - Infrastructure: PostgreSQL `16.14`, Redis `7.4.7`.
  - Migration: `poetry run alembic upgrade head` completed through `034_platform_operators`; reporting migrations logged 0 tenant schemas at public migration time.
  - Command: `poetry run pytest -q tests/test_s6_2_materialized_views.py tests/test_s6_3_dashboard_api.py tests/test_s6_p_reporting_constraints.py tests/test_dc11t4c_reporting_bootstrap_contract.py --tb=short`
  - Result: `43 passed in 58.77s`
- Bootstrap and migration regressions:
  - Command: `poetry run pytest -q tests/test_u6h2_tenant_provisioning_wholesaler_schema.py tests/test_u6h3_tenant_provisioning_reconcile_cleanup.py tests/test_dc2m2_legacy_tenant_reconciliation_forward_migration.py tests/test_alembic_migrations.py --tb=short`
  - Result: `37 passed, 3 skipped in 19.51s`
- Hygiene:
  - Command: `python -m py_compile tests/test_s6_2_materialized_views.py tests/test_s6_3_dashboard_api.py tests/test_s6_p_reporting_constraints.py tests/test_dc11t4c_reporting_bootstrap_contract.py tests/reporting_bootstrap_contract_helpers.py`
  - Result: pass
  - Command: `poetry run pytest --collect-only -q tests/test_s6_2_materialized_views.py tests/test_s6_3_dashboard_api.py tests/test_s6_p_reporting_constraints.py tests/test_dc11t4c_reporting_bootstrap_contract.py`
  - Result: `42 tests collected`
  - Command: `git diff --check`
  - Result: pass

## GitNexus Impact

- Command: `npx gitnexus analyze`
  - Result: repository indexed successfully; `13,056 nodes`, `39,994 edges`, `848 clusters`, `300 flows`; indexed/current commit `6daa32b`.
- Command: `npx gitnexus status`
  - Result: active worktree index `up-to-date`.
- Context target: `TenantProvisioningService.provision_wholesaler_and_schema` in `backend/services/tenant_provisioning_service.py`.
  - Result: target found at lines 112-167; new helper direct caller is `_provision_reporting_tenant` in `backend/tests/reporting_bootstrap_contract_helpers.py`.
- Impact target: `provision_wholesaler_and_schema`, direction `upstream`, include tests, max depth 3, min confidence 0.8.
  - Result: `HIGH` blast-radius classification for changing the service itself: `19` impacted symbols, `17` direct, `2` affected service processes (`verify_email_token`, `complete_email_verified_onboarding`).
  - Interpretation: this branch does not modify the high-blast-radius service; it only invokes the service from test helper code and covers existing bootstrap/provisioning regressions.
- Changed-flow detection: `detect_changes(scope=all, base_ref=origin/product-dev-recovered)`.
  - Result: `low` risk, `64` changed symbols, `6` changed files, `0` affected processes reported for the current test/helper/report diff.

## Teardown Proof

- `cleanup_reporting_tenant` deletes the generated `public.tenant_registrations` row scoped by `tenant_schema` and DC-11T4C test email prefix.
- `cleanup_reporting_tenant` deletes the generated `public.wholesalers` row by the generated wholesaler UUID.
- `cleanup_reporting_tenant` drops only the generated safe `t_...` tenant schema after validating the schema-name prefix and characters.
- `test_reporting_tenant_teardown_removes_schema_and_registry_rows` asserts post-cleanup state is `schema_exists=False`, `registration_count=0`, and `wholesaler_count=0`.

## Risk

- Low. The patch is test-contract only and routes reporting-object-dependent tests through the existing supported tenant provisioning/bootstrap path.
- Residual operational note: local Windows Alembic runs require UTF-8 output (`PYTHONIOENCODING=utf-8` or `PYTHONUTF8=1`) to avoid console encoding failure on existing migration status emoji; this is an environment execution detail, not a source regression in this repair.
