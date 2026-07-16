# DC-11T1-V1B Platform P17 Backup Classification

## Scope

- Code baseline: `7a972d1dca944db3476c405b807ddb5313f5ef95`
- Inventory: `67d2696b1b89cbf1ed6cda686797d395b8ef7801`
- Inventory branch: `reports/dc11t1-v0-stable-failure-inventory-2026-07-15`
- Scoped files:
  - `tests/test_platform_p17dc_backup_registry_read.py` (10 inventory nodes)
  - `tests/test_platform_p17dc_backup_migration.py` (9 inventory nodes)
- Accounting target: 19 nodes

`git diff --stat 7a972d1dca944db3476c405b807ddb5313f5ef95 67d2696b1b89cbf1ed6cda686797d395b8ef7801` is docs-only. No product, test, migration, or config code changed between the code baseline and the inventory commit.

## Environment

- Disposable worktree branch: `reports/dc11t1-v1b-platform-p17-backup-2026-07-16`
- Poetry env path: `/home/ivy/Desktop/dc11t1-v1b-platform-p17-backup-wt/backend/.venv`
- `poetry run python --version`: `Python 3.12.3`
- `poetry run pytest --version`: `pytest 8.4.2`
- `backend/pyproject.toml` and `backend/poetry.lock` remained unchanged
- Disposable infrastructure: fresh PostgreSQL 16 and Redis 7

## Procedure

1. Created a clean disposable worktree from exact baseline commit `7a972d1dca944db3476c405b807ddb5313f5ef95`.
2. Started fresh PostgreSQL 16 and Redis 7 containers.
3. Ran each scoped file in a fresh pytest process.
4. Ran both files together in both orders in fresh pytest processes:
   - registry -> migration
   - migration -> registry
5. Inspected current P17 registry source, migration revision chain, schema qualification, and the registry freshness / read-only assumptions.

Artifacts were captured under `/tmp/dc11t1-v1b-platform-backup`:

- `isolated_registry.xml` / `.out`
- `isolated_migration.xml` / `.out`
- `group_registry_migration.xml` / `.out`
- `group_migration_registry.xml` / `.out`

## Run Matrix

| Run | Result |
| --- | --- |
| `tests/test_platform_p17dc_backup_registry_read.py` | 24 passed, 2 failed |
| `tests/test_platform_p17dc_backup_migration.py` | 9 failed |
| registry -> migration | 24 passed, 11 failed |
| migration -> registry | 24 passed, 11 failed |

The grouped results were identical in both orders. No node in this 19-node inventory changed outcome between the two grouped-order runs.

## Source Inspection

### P17 registry read path

- `backend/api/v1/platform/p17/services.py:319-421` loads backup outcomes and policy with read-only `SELECT` queries inside `db.begin_nested()`, filters to `completed_at IS NOT NULL`, prefers tenant-specific rows over platform-wide fallback, and returns `None` on read failure rather than raising.
- `backend/api/v1/platform/p17/services.py:424-503` builds the `TenantBackupStatus` and always routes `last_backup_status` through `enforce_backup_freshness(...)`.
- `backend/api/v1/platform/p17/services.py:583` and `681` compute `now = _utcnow()` at request time for list and single-tenant registry reads.
- `backend/api/v1/platform/p17/schemas.py:263-265` defines `BACKUP_FRESHNESS_WINDOW = timedelta(hours=24)`.

### P17 migration chain and schema qualification

- `backend/tests/test_platform_p17dc_backup_migration.py:42-43` pins:
  - `BASE_REV = "020_durable_approval_store"`
  - `HEAD_REV = "021_platform_backup_status_source"`
- The current migration file is:
  - `backend/alembic/versions/030_platform_backup_status_source.py:1-5`
  - revision `030_platform_backup_status_source`
  - revises `029_durable_approval_store`
- The current versions directory contains `029_durable_approval_store.py` and `030_platform_backup_status_source.py`, not `020_durable_approval_store.py` or `021_platform_backup_status_source.py`.
- `backend/alembic/versions/030_platform_backup_status_source.py:83-174` creates the tables and indexes explicitly in `public`, and `177-186` downgrades them from `public`.

## Findings

### 1. All 9 migration inventory nodes are `STALE_TEST_CONTRACT`

The migration test file is pinned to an obsolete revision pair:

- `backend/tests/test_platform_p17dc_backup_migration.py:42-43`

The current durable approval / backup chain is:

- `backend/alembic/versions/029_durable_approval_store.py`
- `backend/alembic/versions/030_platform_backup_status_source.py`

The test still asks Alembic for:

- `021_platform_backup_status_source`
- `020_durable_approval_store`

That fails before any migration-behavior assertion can run:

- `alembic.util.exc.CommandError: Can't locate revision identified by '021_platform_backup_status_source'`
- `alembic.util.exc.CommandError: Can't locate revision identified by '020_durable_approval_store'`

This is a stale migration-contract problem, not a current product defect. The current source and revision chain are internally consistent; the test’s pinned revision names are obsolete.

### 2. Two registry assembly inventory nodes are `STALE_TEST_CONTRACT`

The two failing inventory nodes are:

- `TestRegistryAssembly::test_fresh_success_attached_to_registry`
- `TestRegistryAssembly::test_tenant_specific_wins_over_platform_at_registry`

The test module defines:

- `NOW = datetime(2026, 7, 3, 12, 0, 0, tzinfo=timezone.utc)` at `backend/tests/test_platform_p17dc_backup_registry_read.py:54`

Those tests build backup rows relative to that fixed timestamp:

- `completed_at=NOW - timedelta(hours=2)` at line `469`
- `completed_at=NOW - timedelta(hours=10)` at line `510`

and then assert the route returns `"success"`:

- lines `473-477`
- lines `514-518`

But the route does not use the fixed test constant. It calls `_utcnow()` at request time:

- `backend/api/v1/platform/p17/services.py:583`
- `backend/api/v1/platform/p17/services.py:681`

On the actual run date, Thursday, July 16, 2026, a row anchored to July 3, 2026 is about 13 days old, not 2 or 10 hours old. The current P17 contract explicitly downgrades any backup older than 24 hours:

- `backend/api/v1/platform/p17/schemas.py:263-265`
- `backend/api/v1/platform/p17/services.py:445-452`

So the route’s `"stale"` result is correct under the current source. The obsolete part is the test assumption that the route still sees the row as fresh without patching `_utcnow()`.

### 3. The other 8 registry inventory nodes are `TEST_INFRASTRUCTURE`

The remaining 8 inventory nodes are the `TestLoadBackupStatusMap` cases:

- `test_empty_tenant_ids`
- `test_read_failure_returns_none`
- `test_no_outcomes_yields_unknown_per_tenant`
- `test_tenant_specific_preferred_over_platform_wide`
- `test_platform_wide_fallback_when_no_tenant_outcome`
- `test_latest_completed_chosen_per_kind`
- `test_policy_tenant_then_platform_default`
- `test_load_map_performs_no_mutations`

All 8:

- were `failed` in the V0 inventory
- passed in isolated execution
- passed in grouped execution with registry -> migration
- passed in grouped execution with migration -> registry

Because the inventory commit is docs-only and both grouped orders are clean on the exact baseline, there is no current source-level failure to classify as stale contract or product defect inside this two-file slice. The V0 failures therefore depended on broader suite/harness state outside the scoped isolated and two-order grouped matrix.

Within this focused V1B scope, that is a `TEST_INFRASTRUCTURE` classification.

## Classification Summary

| File | Inventory nodes | Classification |
| --- | ---: | --- |
| `tests/test_platform_p17dc_backup_registry_read.py` | 8 | `TEST_INFRASTRUCTURE` |
| `tests/test_platform_p17dc_backup_registry_read.py` | 2 | `STALE_TEST_CONTRACT` |
| `tests/test_platform_p17dc_backup_migration.py` | 9 | `STALE_TEST_CONTRACT` |

## 19-Node Accounting

| Classification | Count |
| --- | ---: |
| `TEST_INFRASTRUCTURE` | 8 |
| `STALE_TEST_CONTRACT` | 11 |
| `CURRENT_PRODUCT_DEFECT` | 0 |
| `ENVIRONMENT_GATED` | 0 |
| total | 19 |

Accounting check: `8 + 11 + 0 + 0 = 19`, gap `0`.

## Verdict

`PASS_DC11T1_V1B_CLASSIFICATION_COMPLETE`
