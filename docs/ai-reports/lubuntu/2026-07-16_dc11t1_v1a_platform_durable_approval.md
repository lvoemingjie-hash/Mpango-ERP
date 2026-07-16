# DC-11T1-V1A Platform Durable Approval Classification

## Scope

- Code baseline: `codex/dc11t0-r4-narrow-test-infrastructure-2026-07-15` at `7a972d1dca944db3476c405b807ddb5313f5ef95`
- Inventory evidence: `reports/dc11t1-v0-stable-failure-inventory-2026-07-15` at `67d2696b1b89cbf1ed6cda686797d395b8ef7801`
- Classification scope: 53 `PLATFORM` nodes from:
  - `tests/test_platform_p21dd_runtime_storage_cutover_gate.py` (25)
  - `tests/test_platform_p21_durable_approval_adapter_implementation.py` (19)
  - `tests/test_platform_p21_durable_approval_migration.py` (6)
  - `tests/test_platform_p21e_durable_approval_runtime_closeout.py` (2)
  - `tests/test_platform_p21_durable_approval_adapter_skeleton.py` (1)

`git diff --stat 7a972d1dca944db3476c405b807ddb5313f5ef95 67d2696b1b89cbf1ed6cda686797d395b8ef7801` shows a docs-only diff: the inventory branch added only the prior inventory `.csv` and `.md` files. No product, test, migration, or config code changed between the code baseline and the inventory commit.

## Environment

- Disposable worktree: `reports/dc11t1-v1a-platform-durable-approval-2026-07-16`
- Poetry env path: `/home/ivy/Desktop/dc11t1-v1a-platform-durable-approval-wt/backend/.venv`
- `poetry run python --version`: `Python 3.12.3`
- `poetry run pytest --version`: `pytest 8.4.2`
- `backend/pyproject.toml` and `backend/poetry.lock` remained unchanged after environment creation
- Disposable infrastructure: fresh PostgreSQL 16 and Redis 7 containers

## Procedure

1. Created a clean disposable worktree from exact baseline commit `7a972d1dca944db3476c405b807ddb5313f5ef95`.
2. Created fresh PostgreSQL 16 and Redis 7 disposable infrastructure.
3. Verified Poetry environment from the repo itself and installed dependencies without editing lockfiles.
4. Collected the exact test inventory from the five scoped files.
5. Ran each of the five files in a separate pytest process.
6. Ran the five files together once in a new pytest process to detect ordering and fixture pollution.
7. Inspected the durable approval ORM, adapter, migration revision chain, and runtime gate sources.

Artifacts used for classification were captured under `/tmp/dc11t1-v1a-platform-durable`:

- `isolated_p21dd.xml` / `.out`
- `isolated_p21_adapter_impl.xml` / `.out`
- `isolated_p21_migration.xml` / `.out`
- `isolated_p21e_closeout.xml` / `.out`
- `isolated_p21_adapter_skeleton.xml` / `.out`
- `grouped_all_five.xml` / `.out`
- `exit_codes.txt`

## Run Matrix

| Run | Result |
| --- | --- |
| `tests/test_platform_p21dd_runtime_storage_cutover_gate.py` | 36 passed |
| `tests/test_platform_p21_durable_approval_adapter_implementation.py` | 23 passed |
| `tests/test_platform_p21_durable_approval_migration.py` | 6 failed |
| `tests/test_platform_p21e_durable_approval_runtime_closeout.py` | 8 passed |
| `tests/test_platform_p21_durable_approval_adapter_skeleton.py` | 31 passed, 1 failed |
| grouped five-file run | 96 passed, 9 failed |

Grouped failure count matched the only currently reproducible failure set in this slice:

- 6 migration failures
- 2 async closeout failures
- 1 skeleton migration-file assertion failure

## Source Inspection

Current durable approval ORM/schema/runtime surfaces do exist and are internally consistent on this baseline:

- `backend/api/v1/platform/p21/models.py:395-433` defines `DurableApprovalDecision` in `public.durable_approval_decisions` with the expected FKs to `durable_approval_requests` and `durable_approval_audit_events`.
- `backend/api/v1/platform/p21/adapter.py:1279-1286` and `1329-1336` persist `DurableApprovalDecision` rows for reject and approve flows.
- `backend/api/v1/platform/p20/services.py:152-193` enforces the runtime readiness gate by checking for the five durable approval tables in `public`.

No isolated or grouped repro in the 44 currently passing inventory nodes showed an ORM/schema/runtime violation on those surfaces.

## Findings

### 1. Six migration nodes are `STALE_TEST_CONTRACT`

`backend/tests/test_platform_p21_durable_approval_migration.py:35` hardcodes:

- `HEAD_REV = "020_durable_approval_store"`

That revision does not exist on this baseline. The actual durable approval migration is:

- `backend/alembic/versions/029_durable_approval_store.py:1-5`

and the next chained migration is:

- `backend/alembic/versions/030_platform_backup_status_source.py:1-5`

The migration test file then calls Alembic directly at `backend/tests/test_platform_p21_durable_approval_migration.py:213-328`, for example:

- `command.upgrade(alembic_cfg, HEAD_REV)` at lines `216`, `220`, `257`, `282`, `295`, `318`
- `command.downgrade(alembic_cfg, BASE_REV)` at lines `217`, `260`, `281`, `315`, `328`

Those calls fail before any product-behavior assertion can execute:

- `alembic.util.exc.CommandError: Can't locate revision identified by '020_durable_approval_store'`
- `alembic.util.exc.CommandError: Destination 019_platform_audit_logs is not a valid downgrade target from current head(s)`

This is not a current product defect in the durable approval ORM or runtime. The test contract is pinned to an obsolete revision name and obsolete migration-chain assumption.

### 2. One skeleton node is `STALE_TEST_CONTRACT`

`backend/tests/test_platform_p21_durable_approval_adapter_skeleton.py:313` asserts:

- `assert (versions / "020_durable_approval_store.py").is_file()`

That file does not exist on this baseline. The durable approval migration file is `029_durable_approval_store.py`, so the assertion is obsolete and fails with:

- `AssertionError: assert False`

This is again a stale contract, not a runtime defect.

### 3. Two closeout nodes are `TEST_INFRASTRUCTURE`

The two inventory nodes in `tests/test_platform_p21e_durable_approval_runtime_closeout.py` both:

- pass in isolated file execution
- fail in the grouped five-file run

The grouped failure is:

- `RuntimeError: There is no current event loop in thread 'MainThread'.`

The failure occurs after the migration test file has already executed direct Alembic commands. The repo already contains the event-loop preservation wrapper:

- `backend/tests/conftest.py:99-117` defines `run_alembic_upgrade()` and explicitly documents that Alembic `asyncio.run()` closes the pytest-asyncio loop on Python 3.12 unless the loop is restored.

The closeout fixture correctly uses that wrapper:

- `backend/tests/test_platform_p21e_durable_approval_runtime_closeout.py:245-246`

But the migration test file bypasses it and calls Alembic directly:

- `backend/tests/test_platform_p21_durable_approval_migration.py:215-217`
- `backend/tests/test_platform_p21_durable_approval_migration.py:256-260`
- `backend/tests/test_platform_p21_durable_approval_migration.py:280-282`
- `backend/tests/test_platform_p21_durable_approval_migration.py:294-295`
- `backend/tests/test_platform_p21_durable_approval_migration.py:314-318`
- `backend/tests/test_platform_p21_durable_approval_migration.py:327-328`

That gives a concrete order-dependent infrastructure cause inside the grouped run:

1. migration tests run and close the session loop
2. later async closeout tests start
3. pytest-asyncio cannot obtain a current loop and fails before the test body

This satisfies the requirement to identify the fixture/order cause before using `TEST_INFRASTRUCTURE`.

### 4. The other 44 inventory nodes are `TEST_INFRASTRUCTURE`

The remaining inventory nodes are all from:

- `tests/test_platform_p21dd_runtime_storage_cutover_gate.py` (25)
- `tests/test_platform_p21_durable_approval_adapter_implementation.py` (19)

All 44:

- were `failed` in the V0 inventory
- passed in isolated runs on fresh PostgreSQL 16 and Redis 7
- passed again in the grouped five-file run on the same exact baseline code

Because `67d2696b1b89cbf1ed6cda686797d395b8ef7801` differs from the baseline only by the prior inventory docs, the V0 failures cannot be explained by product-code drift between baseline and inventory. Within this scoped repro, no current ORM/schema/runtime defect was reproduced for these nodes. Their V0 failures therefore depend on external suite harness/order state outside this five-file slice.

That is enough to classify them as `TEST_INFRASTRUCTURE` in this focused forensic pass. It is not enough to assign `CURRENT_PRODUCT_DEFECT`, and there is no current evidence that their assertions are stale.

## Classification Summary

| File | Inventory nodes | Classification |
| --- | ---: | --- |
| `tests/test_platform_p21dd_runtime_storage_cutover_gate.py` | 25 | `TEST_INFRASTRUCTURE` |
| `tests/test_platform_p21_durable_approval_adapter_implementation.py` | 19 | `TEST_INFRASTRUCTURE` |
| `tests/test_platform_p21_durable_approval_migration.py` | 6 | `STALE_TEST_CONTRACT` |
| `tests/test_platform_p21e_durable_approval_runtime_closeout.py` | 2 | `TEST_INFRASTRUCTURE` |
| `tests/test_platform_p21_durable_approval_adapter_skeleton.py` | 1 | `STALE_TEST_CONTRACT` |

## 53-Node Accounting

| Classification | Count |
| --- | ---: |
| `TEST_INFRASTRUCTURE` | 46 |
| `STALE_TEST_CONTRACT` | 7 |
| `CURRENT_PRODUCT_DEFECT` | 0 |
| `ENVIRONMENT_GATED` | 0 |
| total | 53 |

Accounting check: `46 + 7 + 0 + 0 = 53`, gap `0`.

## Verdict

`PASS_DC11T1_V1A_CLASSIFICATION_COMPLETE`
