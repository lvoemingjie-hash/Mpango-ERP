# DC-12R1-S1-V2 Test Contract Reconciliation Evidence

## Verdict

**PASS_DC12R1_S1_V2_TEST_CONTRACT_RECONCILIATION**

All 20 reproduced RED nodes were reconciled as stale test-contract drift within
the allowed scope of five affected backend test files. No product code,
migrations, or non-allowed tests were edited.

## Scope And Branch

- Date: Monday, July 27, 2026
- Target baseline: `origin/product-dev-recovered @ f35346aa98e3098322dbff59599230800548008b`
- Disposable worktree: `/home/ivy/MPANGO/dc12r1-s1-v2-disposable`
- Report branch: `reports/dc12r1-s1-v2-test-contract-reconciliation-2026-07-27`
- Allowed edits only:
  - `backend/tests/test_s3c_self_contained_fresh_tenant_live_proof.py`
  - `backend/tests/test_s4g_migration_infrastructure_hardening.py`
  - `backend/tests/test_s6_p_reporting_constraints.py`
  - `backend/tests/test_s6e_rbac_permission_registry_drift_gate.py`
  - `backend/tests/test_u3b1_contract_foundation.py`
  - this report

## Test-Safe Environment

- PostgreSQL 16 container: `dc12r1-s1-v2-pg16` on `127.0.0.1:56433`
- Redis 7 container: `dc12r1-s1-v2-redis7` on `127.0.0.1:57380`
- `MPANGO_ENV=test`
- `MPANGO_ALLOW_TEMP_DB_CREATE=1`
- `MPANGO_TEMP_DB_ALLOWED_HOSTS=127.0.0.1,localhost`
- `MPANGO_TEMP_DB_ALLOWED_PORTS=56433`
- `REDIS_URL=redis://127.0.0.1:57380/0`
- `TEST_DATABASE_URL` and `DATABASE_URL` used only loopback, non-production test
  database names, and non-production test users
- `TEST_REPORTING_DATABASE_URL` used explicit reporting-user DSNs with
  `postgresql+asyncpg://reporting_user:...@127.0.0.1:56433/<test_db>`

## RED Baseline

Comparable RED evidence was taken only after preheating a fresh disposable
database to Alembic `head`.

- Database: `test_backend_v2_red_head`
- Log: `/tmp/dc12r1-s1-v2/backend_full_red_head.log`
- JUnit: `/tmp/dc12r1-s1-v2/backend_full_red_head.xml`
- Result:
  - `15 failed, 2850 passed, 48 skipped, 15 xfailed, 1740 warnings, 5 errors in 645.18s`

The exact 20 RED nodes reproduced were:

1. `tests/test_s3c_self_contained_fresh_tenant_live_proof.py::TestPermissionConsistencyWithOnboard::test_s3c_seed_permissions_match_onboard_exactly`
2. `tests/test_s3c_self_contained_fresh_tenant_live_proof.py::TestPermissionConsistencyWithOnboard::test_s3c_seed_permission_count`
3. `tests/test_s4g_migration_infrastructure_hardening.py::test_alembic_upgrade_head_creates_wide_version_table_on_fresh_database`
4. `tests/test_s4g_migration_infrastructure_hardening.py::test_alembic_upgrade_head_widens_existing_varchar32_version_table`
5. `tests/test_s4g_migration_infrastructure_hardening.py::test_migration_017_creates_retailer_prices_on_fresh_tenant_schema`
6. `tests/test_s4g_migration_infrastructure_hardening.py::test_migration_017_reconciles_compatible_preexisting_retailer_prices`
7. `tests/test_s4g_migration_infrastructure_hardening.py::test_migration_017_fails_closed_for_incompatible_retailer_prices`
8. `tests/test_s6_p_reporting_constraints.py::test_reporting_query_timeout`
9. `tests/test_s6_p_reporting_constraints.py::test_reporting_user_can_read_public_tables`
10. `tests/test_s6e_rbac_permission_registry_drift_gate.py::test_api_route_permissions_are_seeded_in_all_tenant_provisioning_paths`
11. `tests/test_s6e_rbac_permission_registry_drift_gate.py::test_provisioning_paths_seed_required_data_intake_permissions`
12. `tests/test_s6e_rbac_permission_registry_drift_gate.py::test_frontend_permission_references_are_seeded`
13. `tests/test_u3b1_contract_foundation.py::TestSkusImportPermission::test_create_wholesaler_has_skus_import`
14. `tests/test_u3b1_contract_foundation.py::TestSkusImportPermission::test_onboard_tenant_has_skus_import`
15. `tests/test_u3b1_contract_foundation.py::TestSkusImportPermission::test_seed_test_tenant_has_skus_import`
16. `tests/test_s6_p_reporting_constraints.py::test_reporting_user_cannot_insert`
17. `tests/test_s6_p_reporting_constraints.py::test_reporting_user_cannot_update`
18. `tests/test_s6_p_reporting_constraints.py::test_reporting_user_cannot_delete`
19. `tests/test_s6_p_reporting_constraints.py::test_reporting_user_can_select`
20. `tests/test_s6_p_reporting_constraints.py::test_reporting_role_has_timeout`

Accounting: 20 reproduced, 20 resolved, gap 0.

## Reconciliation Changes

- `test_s3c_self_contained_fresh_tenant_live_proof.py`
  - Replaced source-literal parsing with the authoritative permission registry.
- `test_s4g_migration_infrastructure_hardening.py`
  - Replaced ad hoc database setup with `TEST_DATABASE_URL` plus
    `temporary_database_url(...)` and `run_alembic_upgrade(...)`.
- `test_s6_p_reporting_constraints.py`
  - Switched reporting DSN construction to the supported reporting-session path
    and explicit test reporting credentials.
- `test_s6e_rbac_permission_registry_drift_gate.py`
  - Replaced source-literal parsing with authoritative registry checks for the
    real tenant-provisioning paths.
- `test_u3b1_contract_foundation.py`
  - Replaced static permission-string expectations with authoritative registry
    and runtime object identity checks.

Classification of all 20 original RED nodes:

- `STALE_TEST_CONTRACT`: 20
- `CURRENT_PRODUCT_DEFECT`: 0
- `TEST_INFRASTRUCTURE`: 0
- `ENVIRONMENT_GATED`: 0

## Focused GREEN Proof

Focused reruns after reconciliation:

- `tests/test_s3c_self_contained_fresh_tenant_live_proof.py`
  - PASS: `17 passed`
  - Log: `/tmp/dc12r1-s1-v2/targeted_s3c.log`
- `tests/test_s4g_migration_infrastructure_hardening.py`
  - PASS: `5 passed`
  - Log: `/tmp/dc12r1-s1-v2/targeted_s4g.log`
- `tests/test_s6_p_reporting_constraints.py`
  - PASS: `8 passed`
  - Log: `/tmp/dc12r1-s1-v2/targeted_s6p.log`
- `tests/test_s6e_rbac_permission_registry_drift_gate.py`
  - first rerun exposed legacy `seed_demo_data.py` scope drift
  - final PASS: `4 passed`
  - Logs:
    - `/tmp/dc12r1-s1-v2/targeted_s6e.log`
    - `/tmp/dc12r1-s1-v2/targeted_s6e_rerun.log`
- `tests/test_u3b1_contract_foundation.py`
  - PASS: `27 passed`
  - Log: `/tmp/dc12r1-s1-v2/targeted_u3b1.log`

## Full Backend Gate

Full backend suite was run twice consecutively against two separate fresh
databases, each preheated serially to Alembic `head`.

- Run 1
  - Database: `test_backend_v2_green2`
  - Log: `/tmp/dc12r1-s1-v2/backend_full_green1.log`
  - JUnit: `/tmp/dc12r1-s1-v2/backend_full_green1.xml`
  - Result: `2870 passed, 48 skipped, 15 xfailed, 1743 warnings in 673.50s`
- Run 2
  - Database: `test_backend_v2_green_run2`
  - Log: `/tmp/dc12r1-s1-v2/backend_full_green2.log`
  - JUnit: `/tmp/dc12r1-s1-v2/backend_full_green2.xml`
  - Result: `2870 passed, 48 skipped, 15 xfailed, 1744 warnings in 645.68s`

Note: a discarded parallel migration preheat attempt against two databases at
once hit PostgreSQL role-catalog contention on migration `011_s6_p_reporting_role`
(`ALTER ROLE reporting_role ... tuple concurrently updated`). The accepted gate
evidence uses serialized database preheats only.

## Frontend Gate

- `pnpm build`
  - PASS
- `pnpm vitest run`
  - first attempt was discarded because it was incorrectly run in parallel with
    `pnpm build` and hit one 5s timeout in `S5BRealUserSmoke`
  - accepted serial rerun PASS: `14 passed`, `123 passed`

Non-failing warnings observed:

- duplicate `jsdom` key warning from `package.json`
- Vite bundle-size warning for a chunk larger than 500 kB
- React Router future-flag warnings
- React `act(...)` warnings in existing frontend tests

## Independent Review

Independent fresh-process review was run after the main gate on a new review
source database `test_backend_v2_review_source`.

- `tests/test_dc12r1_s1_r4_exact_catalog.py`
  - PASS: `8 passed`
  - Log: `/tmp/dc12r1-s1-v2/independent_r4.log`
- `tests/test_dc12r1_s1_r5_migration_preflight_exact_catalog.py`
  - PASS: `41 passed, 6 warnings`
  - Log: `/tmp/dc12r1-s1-v2/independent_r5.log`

This independent review re-proved the exact-catalog/RBAC gate and the actual
035->036 fail-closed rollback-and-repair migration proof on fresh disposable
databases created from `TEST_DATABASE_URL`.

## Guardrails Satisfied

- No product code edits
- No migration edits
- No skip additions
- No xfail additions
- No deselection
- No assertion weakening
- No backend test-file exclusions
- No unresolved current product defect

