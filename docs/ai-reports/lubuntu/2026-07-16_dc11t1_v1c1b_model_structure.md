# DC-11T1-V1C1-B Model Structure Classification

## Verdict

`PASS_DC11T1_V1C1B_CLASSIFICATION_COMPLETE`

All four V0 inventory nodes in `test_models_structure.py` are `STALE_TEST_CONTRACT`. No current product defect or migration defect was found in this slice.

## Scope

- Code baseline: `7a972d1dca944db3476c405b807ddb5313f5ef95`
- V0 inventory: `67d2696b1b89cbf1ed6cda686797d395b8ef7801`
- Scoped file: `backend/tests/test_models_structure.py`
- Inventory nodes: 4
- Product code changes: none
- Test changes: none
- Migration changes: none
- Configuration and lockfile changes: none

The V0 inventory commit differs from the baseline by two report files only. Product and test source are identical.

## Environment

- Host: Windows local workstation
- Python: 3.12.10
- Poetry-managed in-project environment: `backend/.venv`
- pytest: 8.4.2
- Database services: not required for this model-metadata slice
- GitNexus baseline index: up to date at `7a972d1`

## Reproduction Matrix

The complete model-structure file was first run three times in independent pytest processes.

| Run | Tests | Passed | Failed | Errors |
| --- | ---: | ---: | ---: | ---: |
| isolated run 1 | 8 | 8 | 0 | 0 |
| isolated run 2 | 8 | 8 | 0 | 0 |
| isolated run 3 | 8 | 8 | 0 | 0 |

The platform model modules were then explicitly imported before pytest in clean Python processes:

| Pre-import state | Tests | Passed | Failed | Failed V0 nodes |
| --- | ---: | ---: | ---: | ---: |
| P17 models | 8 | 4 | 4 | 4 |
| P21 models | 8 | 5 | 3 | 3 |
| P17 and P21 models | 8 | 4 | 4 | 4 |

Finally, the dedicated P17 and P21 model-contract suites were collected with the generic structure test:

- Dedicated P17/P21 model contracts: 40 passed.
- Generic structure test: 4 passed, 4 failed.
- Combined result: 44 passed, 4 failed.

This reproduces the full-suite outcome without a database and proves that the four failures are controlled by which model modules have entered the process-global SQLAlchemy registry before the generic test runs.

## Current Contract Evidence

### The generic test is import-order dependent

`get_all_model_classes()` enumerates `Base.registry.mappers` at runtime:

- `backend/tests/test_models_structure.py:35-47`

The test imports only `models.base`, not every module that shares `Base`. P17 and P21 models live below `backend/api/v1/platform/` and enter the registry only when another collected test imports them. This explains why the file passes in isolation but fails in the full suite and in the explicit pre-import matrix.

### The generic primary-key rule is obsolete for P17/P21

The generic assertion requires every mapped primary key to be named `id`:

- `backend/tests/test_models_structure.py:89-109`

Current platform contracts deliberately use domain-specific primary keys:

- P17: `outcome_id` and `policy_id`.
- P21: `approval_id`, `event_id`, `decision_id`, `idempotency_id`, and `job_id`.

The dedicated tests explicitly assert these names:

- `backend/tests/test_platform_p17dc_backup_models.py:64-65`
- `backend/tests/test_platform_p17dc_backup_models.py:106-112`
- `backend/tests/test_platform_p21_durable_approval_models.py:96-100`
- `backend/tests/test_platform_p21_durable_approval_models.py:144-150`

The migration-owned schemas use the same keys in `029_durable_approval_store.py` and `030_platform_backup_status_source.py`. Changing the ORM to a generic `id` field would create migration drift and break the actual platform schema.

### The generic audit-column rule is obsolete for append-only/domain tables

The generic test requires `created_at`, `updated_at`, `is_deleted`, and `deleted_at` on nearly every mapper:

- `backend/tests/test_models_structure.py:112-129`

P17 backup outcomes and P21 audit/idempotency/decision records intentionally omit soft-delete columns. Their model modules explain why they extend `Base` directly instead of `PublicBaseModel`:

- `backend/api/v1/platform/p17/models.py:13-24`
- `backend/api/v1/platform/p21/models.py:19-30`

The dedicated model tests assert that `is_deleted` and `deleted_at` are absent. Those 40 contract tests passed in the same process that made the generic test fail.

### The public-model helper uses the wrong type boundary

`get_public_model_classes()` includes a model whenever its table schema is `public`:

- `backend/tests/test_models_structure.py:50-70`

It does not test whether the class actually subclasses `PublicBaseModel`. P17 and P21 deliberately subclass `Base` directly, so the generic `TestPublicBaseModel` assertion is applied to classes outside its stated type boundary.

### The plural-table rule conflicts with a migration-owned table

The generic test requires every table name to end in `s`:

- `backend/tests/test_models_structure.py:131-145`

P17 uses the migration-owned table name `platform_backup_outcome`. Migration 030 and the dedicated model contract require that exact name. Renaming the ORM table only to satisfy the generic test would disconnect the runtime mapping from the deployed schema.

## Node Classification

| Node | Classification | Reason |
| --- | --- | --- |
| `test_all_models_have_uuid_primary_key` | `STALE_TEST_CONTRACT` | Universal `id` rule conflicts with current domain-specific platform keys. |
| `test_all_models_have_audit_columns` | `STALE_TEST_CONTRACT` | Universal soft-delete rule conflicts with append-only/domain table contracts. |
| `test_all_models_have_explicit_tablename` | `STALE_TEST_CONTRACT` | Simplistic plural rule conflicts with the migration-owned P17 table name. |
| `test_public_base_model_has_audit_columns` | `STALE_TEST_CONTRACT` | Helper confuses public-schema direct-`Base` models with `PublicBaseModel` subclasses. |

The import-order dependency is a test-isolation weakness, but each final node classification is `STALE_TEST_CONTRACT` because the assertions themselves conflict with the current, dedicated, migration-backed model contracts.

## Accounting

| Classification | Count |
| --- | ---: |
| `TEST_INFRASTRUCTURE` | 0 |
| `STALE_TEST_CONTRACT` | 4 |
| `CURRENT_PRODUCT_DEFECT` | 0 |
| `ENVIRONMENT_GATED` | 0 |
| Total | 4 |

Accounting: `0 + 4 + 0 + 0 = 4`, gap `0`.

The node-level ledger is `docs/ai-reports/lubuntu/2026-07-16_dc11t1_v1c1b_model_structure.csv`.

## Non-Node Documentation Note

The P17/P21 model-module docstrings retain historical task-revision labels `021` and `020`, while the current Alembic files are `030_platform_backup_status_source` and `029_durable_approval_store`. This is documentation drift, not an ORM or migration behavior defect, and it is not counted among the four V0 nodes.

## Recommended Test Correction

Do not alter P17/P21 models or historical migrations to satisfy this generic test. In a later test-contract cleanup slice:

1. Build the generic model set from an explicit supported-model registry rather than process-global import state.
2. Check `issubclass(model, PublicBaseModel)` for PublicBaseModel-specific assertions instead of using `schema == "public"`.
3. Keep P17/P21 domain models under their dedicated model-contract suites.
4. Preserve all current dedicated primary-key, table-name, and no-soft-delete assertions.

No skip, xfail, assertion weakening, or production-code change was made in this classification task.

## Cleanup and Safety

- No disposable database was required or started.
- No product database or VPS was accessed.
- No credentials, tokens, database URLs, passwords, or email addresses were recorded.
- No protected branch was pushed.
