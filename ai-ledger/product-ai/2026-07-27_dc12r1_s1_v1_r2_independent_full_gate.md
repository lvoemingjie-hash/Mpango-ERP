# DC-12R1-S1-V1-R2 Independent Failure Reproduction And Exact Full Gate

Date: Monday, July 27, 2026

Target:
- `origin/product-dev-recovered @ f35346aa98e3098322dbff59599230800548008b`

Report branch:
- `reports/dc12r1-s1-v1-r2-independent-full-gate-2026-07-27`

Verdict:
- `PASS_DC12R1_S1_V1_R2_INDEPENDENT_FULL_GATE`

## Scope

This report corrects the incomplete V1 evidence without modifying product,
test, or migration code. The gate was executed in a fresh disposable worktree
with fresh PostgreSQL 16 and Redis 7, zero backend file exclusions, exact
failed-node extraction, independent per-file reruns in fresh pytest processes,
ordering checks, real PostgreSQL RBAC assertions, real 035->036 fail-closed
rollback proof, frontend Vitest, and production build.

No `CURRENT_PRODUCT_DEFECT` was found. All 20 exact full-suite red nodes
reproduced and classified as `STALE_TEST_CONTRACT`. Accounting gap: zero.

## Clean Disposable Environment

Disposable worktree:
- `/home/ivy/MPANGO/dc12r1-s1-v1-r2-disposable`

Fresh loopback-only infrastructure:
- PostgreSQL 16 container: `dc12r1-s1-v1-r2-pg16` on `127.0.0.1:56432`
- Redis 7 container: `dc12r1-s1-v1-r2-redis7` on `127.0.0.1:57379`

Explicit test-safe environment used for backend execution:
- `MPANGO_ENV=test`
- `MPANGO_ALLOW_TEMP_DB_CREATE=1`
- `MPANGO_TEMP_DB_ALLOWED_PORTS=56432`
- `MPANGO_TEMP_DB_ALLOWED_HOSTS=127.0.0.1,localhost`
- `DATABASE_URL` and `TEST_DATABASE_URL` pointed to fresh disposable,
  non-production loopback databases
- `REDIS_URL=redis://127.0.0.1:57379/0`

Supporting safety facts:
- non-production DB/user names were used
- loopback host was used throughout
- no backend test file was excluded

## Prior V1 Evidence Audit

Historical V1 evidence was incomplete and non-compliant:
- it excluded `backend/tests/test_dc11p1_platform_operator_schema.py`
- it summarized failures at file level instead of exact nodeids

Referenced-path verification:
- every V1-R2 failed/error node path exists in the target checkout
- one stale historical path was corrected during audit:
  `backend/tests/test_dc11d_payment_replay_concurrency.py` does not exist at
  the target commit; the actual file is
  `backend/tests/test_dc11d_payment_replay_concurrency_integrity.py`

## Required Independent Reproduction

Exact full backend suite command result with zero exclusions:
- `15 failed, 2850 passed, 48 skipped, 15 xfailed, 1742 warnings, 5 errors`
- runtime: `1049.37s`
- JUnit XML: `/tmp/dc12r1-s1-v1-r2/backend_full.xml`
- log: `/tmp/dc12r1-s1-v1-r2/backend_full.log`

Independent reruns in fresh pytest processes:
- `tests/test_s3c_self_contained_fresh_tenant_live_proof.py`: exact full-suite
  permission-contract failures reproduced
- `tests/test_s4g_migration_infrastructure_hardening.py`: exact five
  `POSTGRES_DB` failures reproduced
- `tests/test_s6_p_reporting_constraints.py`: exact password-auth failure
  family reproduced after fresh `alembic upgrade head`
- `tests/test_s6e_rbac_permission_registry_drift_gate.py`: exact three seed
  extraction failures reproduced
- `tests/test_u3b1_contract_foundation.py`: exact three `skus:import` static
  failures reproduced

Ordering checks:
- affected-file bundle rerun in original order: reproduced same failure families
- affected-file bundle rerun in reverse order: reproduced same failure families
- no ordering permutation converted any exact red node to green

## Required Proofs

Real PostgreSQL RBAC assertions:
- `retailer_operator` had exactly these six permissions:
  `client:catalog:read`, `client:finance:read`, `client:orders:create`,
  `client:orders:read`, `client:payments:create`, `client:payments:read`
- `retailer_operator` had no generic `orders:*`, `payments:*`, `finance:*`, or
  `platform:*` permissions
- `admin` had `invitations:revoke`
- `admin` had `retailers:reissue_credential`
- result: `PASS`

Real 035->036 fail-closed rollback and fingerprint proof:
- test:
  `tests/test_dc12r1_s1_r5_migration_preflight_exact_catalog.py::test_actual_alembic_035_to_036_failure_rolls_back_then_repaired_upgrade_noops`
- result: `PASS`

Frontend:
- `pnpm vitest run`: `14 passed`, `123 passed`
- `pnpm build`: `PASS`
- warnings only: duplicate `jsdom` key in `package.json`, React Router future
  warnings, `act(...)` warnings, Vite chunk-size warning

## Exact Node Classification

All 20 red nodes below were extracted from the full-suite JUnit XML and
rerun independently. `Phase` reflects the JUnit outcome phase: `call` for
`<failure>` nodes and `setup` for fixture/setup `<error>` nodes.

| Nodeid | Phase | Exception class | Sanitized root cause | Classification |
| --- | --- | --- | --- | --- |
| `tests/test_s3c_self_contained_fresh_tenant_live_proof.py::TestPermissionConsistencyWithOnboard::test_s3c_seed_permissions_match_onboard_exactly` | `call` | `AssertionError` | AST extractor requires a literal `permissions_data` list inside `setup_admin()`, but runtime code uses `permissions_data = ADMIN_PERMISSIONS` from the centralized registry | `STALE_TEST_CONTRACT` |
| `tests/test_s3c_self_contained_fresh_tenant_live_proof.py::TestPermissionConsistencyWithOnboard::test_s3c_seed_permission_count` | `call` | `AssertionError` | same stale AST assumption as the prior node | `STALE_TEST_CONTRACT` |
| `tests/test_s4g_migration_infrastructure_hardening.py::test_alembic_upgrade_head_creates_wide_version_table_on_fresh_database` | `call` | `KeyError` | test hard-requires `POSTGRES_DB` instead of using the supported test-safe DB URL contract | `STALE_TEST_CONTRACT` |
| `tests/test_s4g_migration_infrastructure_hardening.py::test_alembic_upgrade_head_widens_existing_varchar32_version_table` | `call` | `KeyError` | same hard dependency on `POSTGRES_DB` | `STALE_TEST_CONTRACT` |
| `tests/test_s4g_migration_infrastructure_hardening.py::test_migration_017_creates_retailer_prices_on_fresh_tenant_schema` | `call` | `KeyError` | same hard dependency on `POSTGRES_DB` | `STALE_TEST_CONTRACT` |
| `tests/test_s4g_migration_infrastructure_hardening.py::test_migration_017_reconciles_compatible_preexisting_retailer_prices` | `call` | `KeyError` | same hard dependency on `POSTGRES_DB` | `STALE_TEST_CONTRACT` |
| `tests/test_s4g_migration_infrastructure_hardening.py::test_migration_017_fails_closed_for_incompatible_retailer_prices` | `call` | `KeyError` | same hard dependency on `POSTGRES_DB` | `STALE_TEST_CONTRACT` |
| `tests/test_s6_p_reporting_constraints.py::test_reporting_query_timeout` | `call` | `AssertionError` | test expects timeout/cancel semantics but `_build_test_reporting_url()` constructs its own reporting DSN from `POSTGRES_*` and ignores the explicit safe reporting DB URL, leading to password-auth failure instead | `STALE_TEST_CONTRACT` |
| `tests/test_s6_p_reporting_constraints.py::test_reporting_user_can_read_public_tables` | `call` | `InvalidPasswordError` | same unsupported custom DSN path bypasses the provided safe reporting DB URL | `STALE_TEST_CONTRACT` |
| `tests/test_s6e_rbac_permission_registry_drift_gate.py::test_api_route_permissions_are_seeded_in_all_tenant_provisioning_paths` | `call` | `AssertionError` | AST seed extractor only accepts literal list assignments and returns empty for `onboard_tenant.py`, which now imports centralized permissions | `STALE_TEST_CONTRACT` |
| `tests/test_s6e_rbac_permission_registry_drift_gate.py::test_provisioning_paths_seed_required_data_intake_permissions` | `call` | `AssertionError` | same stale literal-list extractor | `STALE_TEST_CONTRACT` |
| `tests/test_s6e_rbac_permission_registry_drift_gate.py::test_frontend_permission_references_are_seeded` | `call` | `AssertionError` | same stale literal-list extractor | `STALE_TEST_CONTRACT` |
| `tests/test_u3b1_contract_foundation.py::TestSkusImportPermission::test_create_wholesaler_has_skus_import` | `call` | `AssertionError` | static source check requires literal `"skus:import"` inside `create_permissions()`, but the function iterates `ADMIN_PERMISSIONS` | `STALE_TEST_CONTRACT` |
| `tests/test_u3b1_contract_foundation.py::TestSkusImportPermission::test_onboard_tenant_has_skus_import` | `call` | `AssertionError` | static source check requires literal `"skus:import"` inside `setup_admin()`, but the function uses `ADMIN_PERMISSIONS` | `STALE_TEST_CONTRACT` |
| `tests/test_u3b1_contract_foundation.py::TestSkusImportPermission::test_seed_test_tenant_has_skus_import` | `call` | `AssertionError` | static source check requires literal `"skus:import"` in `seed_test_tenant.py`, but runtime seeding uses imported `ADMIN_PERMISSIONS` | `STALE_TEST_CONTRACT` |
| `tests/test_s6_p_reporting_constraints.py::test_reporting_user_cannot_insert` | `setup` | `InvalidPasswordError` | reporting fixture uses the same unsupported custom DSN path instead of the provided safe reporting DB URL | `STALE_TEST_CONTRACT` |
| `tests/test_s6_p_reporting_constraints.py::test_reporting_user_cannot_update` | `setup` | `InvalidPasswordError` | same unsupported custom DSN path | `STALE_TEST_CONTRACT` |
| `tests/test_s6_p_reporting_constraints.py::test_reporting_user_cannot_delete` | `setup` | `InvalidPasswordError` | same unsupported custom DSN path | `STALE_TEST_CONTRACT` |
| `tests/test_s6_p_reporting_constraints.py::test_reporting_user_can_select` | `setup` | `InvalidPasswordError` | same unsupported custom DSN path | `STALE_TEST_CONTRACT` |
| `tests/test_s6_p_reporting_constraints.py::test_reporting_role_has_timeout` | `setup` | `InvalidPasswordError` | same unsupported custom DSN path | `STALE_TEST_CONTRACT` |

## Source-Level Basis For Classification

Permission-registry centralization is present in runtime code:
- `backend/scripts/onboard_tenant.py`: imports `ADMIN_PERMISSIONS` and assigns
  `permissions_data = ADMIN_PERMISSIONS`
- `backend/scripts/create_wholesaler.py`: iterates `ADMIN_PERMISSIONS`
- `backend/scripts/seed_test_tenant.py`: assigns
  `permission_codes = ADMIN_PERMISSIONS`
- `backend/core/permission_registry.py`: contains `"skus:import"` and the
  current runtime permission catalog

The stale test contracts are visible in test source:
- `backend/tests/test_s3c_self_contained_fresh_tenant_live_proof.py` only
  extracts a literal `ast.List` assigned to `permissions_data`
- `backend/tests/test_s6e_rbac_permission_registry_drift_gate.py` only extracts
  literal assignments to `PERMISSION_CODES`, `permissions_data`, or
  `permission_codes`
- `backend/tests/test_u3b1_contract_foundation.py` performs literal-string
  source inspection for `"skus:import"`
- `backend/tests/test_s4g_migration_infrastructure_hardening.py` reads
  `os.environ["POSTGRES_DB"]`
- `backend/tests/test_s6_p_reporting_constraints.py::_build_test_reporting_url()`
  builds a DSN from `POSTGRES_HOST`, `POSTGRES_PORT`, and `POSTGRES_DB`, and
  does not honor the explicit safe reporting DB URL contract

## Classification Totals

- `TEST_INFRASTRUCTURE`: 0
- `STALE_TEST_CONTRACT`: 20
- `CURRENT_PRODUCT_DEFECT`: 0
- `ENVIRONMENT_GATED`: 0
- Accounting gap: `0`

## Final Determination

The incomplete V1 evidence has been corrected to exact-node granularity. The
full backend suite was executed with zero exclusions, every exact red node was
verified to exist, every affected file was rerun independently in a fresh
pytest process, order sensitivity was checked in original and reverse order,
RBAC and 035->036 proofs passed on real PostgreSQL, and frontend Vitest plus
production build passed.

Because no exact red node classified as `CURRENT_PRODUCT_DEFECT`, this scope
does not trigger `STOP_AND_REPORT_CTO`.
