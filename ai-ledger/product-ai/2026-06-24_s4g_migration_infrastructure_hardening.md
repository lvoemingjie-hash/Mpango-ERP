# S4-G: Migration Infrastructure Hardening

| Field | Value |
|-------|-------|
| Date | 2026-06-24 |
| Branch | `opencode/s4g-migration-infrastructure-hardening-2026-06-24` |
| Base | `origin/product-dev-recovered` @ `4e5dc7a` (`merge: S4-F business invariant closeout gate`) |
| Commit | Pending until branch push; final commit is reported in handoff because the commit hash cannot be embedded in the same commit that creates this ledger. |
| Verdict | PASS_FOR_CTO_REVIEW |

---

## Changed Files

- `backend/alembic/env.py`
- `backend/alembic/versions/017_retailer_prices.py`
- `backend/tests/test_s4g_migration_infrastructure_hardening.py`
- `ai-ledger/product-ai/2026-06-24_s4g_migration_infrastructure_hardening.md`

No business API, services, frontend, deployment scripts, or migration revision chain files were changed.

---

## Scope

S4-G hardens migration/test infrastructure exposed by Lubuntu S4-F post-merge validation:

- Alembic's default `public.alembic_version.version_num VARCHAR(32)` cannot store this repo's long revision id `021_tenant_payments_retailer_id_transaction_id` during upgrade.
- Migration `017_retailer_prices` was not idempotent when a tenant schema already had `retailer_prices`.

This is not a product behavior fix.

---

## Alembic Version Table Research

Official Alembic docs confirm `EnvironmentContext.configure()` supports:

- `version_table`
- `version_table_schema`
- `version_table_pk`

It does not expose a `version_num` length option.

Installed Alembic 1.18.1 implementation confirms the default table still uses `String(32)`:

```python
Column("version_num", String(32), nullable=False)
```

S4-G therefore implements a repo-owned, repeatable `env.py` hardening step before migrations run:

- Create `public.alembic_version` as `VARCHAR(128)` if absent.
- Widen existing `VARCHAR(n)` where `n < 128` to `VARCHAR(128)`.
- Accept existing `VARCHAR(128+)`, unbounded `VARCHAR`, or `TEXT`.
- Fail closed if `version_num` has an unsupported type.

This avoids relying on manual pre-creation as the only solution.

---

## Migration 017 Safety

`017_retailer_prices` now behaves as follows:

- Fresh tenant schema: creates `retailer_prices` exactly as before.
- Existing compatible table: validates required columns, then reconciles missing named unique/check constraints and indexes.
- Existing incompatible table: raises `RuntimeError` before destructive changes.

No data is deleted or rewritten.

Choice explanation:

- Missing indexes/constraints are safe to reconcile because PostgreSQL will fail if existing data violates the constraint; this is fail-closed for bad data.
- Missing or incompatible columns are not auto-added because that can silently bless unknown historical schemas/data. S4-G stops for manual review instead.

---

## DB Evidence

Tests used local PostgreSQL only:

- `POSTGRES_HOST=127.0.0.1`
- `POSTGRES_PORT=5432`
- `POSTGRES_DB=mpango_erp`
- password masked and sourced from the local `mpango_postgres` container

Fresh DB evidence:

- Targeted test created a temporary database `s4g_version_<suffix>`.
- Ran `alembic upgrade head` from an empty database.
- Verified `public.alembic_version.version_num` has length `>= 128`.
- Verified final head row is `023_inventory_reservations`.

Existing `VARCHAR(32)` evidence:

- Targeted test created a temporary database `s4g_existing_<suffix>`.
- Pre-created `public.alembic_version(version_num VARCHAR(32) PRIMARY KEY)`.
- Ran `alembic upgrade head`.
- Verified `version_num` was widened to length `>= 128` and final head row is `023_inventory_reservations`.

Pre-existing compatible `retailer_prices` evidence:

- Targeted test created a tenant schema with a compatible `retailer_prices` table and one row.
- Ran migration 017 through Alembic `Operations` against that schema.
- Verified named constraints/indexes exist after migration.
- Verified the existing row count remained `1`.

Incompatible schema behavior evidence:

- Targeted test created a tenant schema with `retailer_prices` missing `price` and other required columns.
- Ran migration 017.
- Verified it raises `RuntimeError` matching `missing column 'price'`.

---

## Exact Test Results

Targeted S4-G migration infrastructure tests:

```text
poetry run pytest tests/test_s4g_migration_infrastructure_hardening.py -q -rxX --tb=short
5 passed, 1 warning
```

S4-F closeout regression:

```text
poetry run pytest tests/business/test_s4f_business_invariant_closeout.py -q -rxX --tb=short
8 passed, 19 warnings
```

S4 jobs regression:

```text
poetry run pytest tests/test_s4_jobs_local.py tests/test_s4_jobs_persistence.py -q --tb=short
16 passed, 283 warnings
```

S5/Phase5 regression:

```text
poetry run pytest tests/test_s5_order_state_machine.py tests/test_phase5_order_payment.py -q --tb=short
66 passed, 1 xfailed, 46 warnings
```

The remaining `1 xfailed` is pre-existing in Phase5 payment tests and unrelated to S4-G.

---

## Remaining Risks

- `env.py` hardening is PostgreSQL-specific by design; non-PostgreSQL dialects are ignored because this product's migration target is PostgreSQL.
- Offline SQL generation emits unconditional `ALTER TABLE public.alembic_version ALTER COLUMN version_num TYPE VARCHAR(128)` after `CREATE TABLE IF NOT EXISTS`; this is safe for the intended PostgreSQL SQL output path but less nuanced than the online type inspection.
- Migration 017 deliberately fails closed rather than adding missing columns to an incompatible existing table; this may require manual CTO-approved data/schema remediation if a real tenant has a partial historical table.

---

## Hygiene

```text
git diff --check
PASS
```

```text
Changed-line ASCII/mojibake scan
PASS
```

Note: whole-file scan flags a pre-existing non-ASCII arrow in `017_retailer_prices.py` original docstring. No changed line introduces non-ASCII.

GitNexus analyze:

```text
npx gitnexus analyze
Repository indexed successfully (16.2s)
5,678 nodes | 16,483 edges | 371 clusters | 222 flows
```

GitNexus detect changes, staged and compare vs `origin/product-dev-recovered`:

```text
risk_level: medium
changed_files: 4
changed_count: 47
affected_count: 4
affected_processes:
- Upgrade -> _columns
- Upgrade -> _constraint_exists
- Upgrade -> _index_exists
- Upgrade -> Create_index
```

Reason: S4-G intentionally changes Alembic migration infrastructure and migration 017 upgrade flow. No business API/service/frontend execution flow is changed.
