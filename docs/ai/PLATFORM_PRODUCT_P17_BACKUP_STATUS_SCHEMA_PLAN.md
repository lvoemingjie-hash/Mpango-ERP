# Platform Product P17-D-B -- Backup / Status Source Schema + Model + Test Plan

**Status:** Docs-only / planning-only schema + model + test plan (P17-D-B). No runtime code, no backend
handler, no ORM model file, no model registration, no migration, no alembic change, no table, no column,
no test code, and no dependency change. No `backend/`, no `frontend/`, no `migrations/`, no
`alembic/env.py`, no `scripts/` (P16 or otherwise), no `package` / lockfile, no `.github/`, no `.claude/`,
no secrets baseline file, and no `product-dev-recovered/` is touched. No product / payment / billing /
order / invoice / customer / inventory / ledger path is touched. P17-D-B performs NO execution, wires
NO backup source, reads NO production external system, does NO pg_dump, does NO restore, registers NO
ORM model, and changes NO P22 seam or adapter (`backend/api/v1/platform/p22/seam.py` and `adapters.py`
are cited read-only as evidence only). It converts the accepted P17-D-A contract into an
implementation-ready schema / enum / model-mapping / writer-contract / migration / test plan that a
future P17-D-C may implement. P17-D-B ships no source, no table, and no execution power.
**Phase:** P17-D-B Backup / Status Source Schema + Model + Test Plan
**Date:** 2026-07-02
**Base:** `eb5268c` (`origin/platform-dev` -- the P17-D-A merge; the backup / status source contract is
on the books: `docs/ai/PLATFORM_PRODUCT_P17_BACKUP_STATUS_SOURCE_CONTRACT.md`).
**Implements (planning only):** the P17-D-A contract's recommended Option A durable platform-schema
table / model. P17-D-B is the PLAN; P17-D-C is the earliest phase that MAY create the migration, the ORM
model, and the registry read wiring, and even then no P22 wiring.
**Depends on:** P17-D-A (the backup / status source contract -- the recommended source, the field
mapping, the freshness / honesty / redaction / visibility rules, the migration + adapter boundaries, the
P17-D-C and P22-E3 gates), P17 (Registry and Tenant Lifecycle Contract -- the `TenantBackupStatus`
shape, the 24h freshness window, the `BACKUP_FAILURE_REASONS` allowlist, the summary / full visibility
split), P22-E2 (the SOURCE_UNKNOWN discovery + the minimum P17 prerequisite set), P22-E0 / P22-E1 (the
runtime governed adapter seam -- cited read-only; P17-D-B touches none of it), P21-C1 (the additive
public-schema-only migration precedent), the P21 ORM-enum decode lesson (`postgresql.ENUM` value lists
must match the migration exactly).
**Author:** Codex (Claude worker)

---

## 1. Goal and Non-Goals

### 1.1 Goal

P17-D-A (merged at `eb5268c`) defined the backup / status source *contract*: it recommended a durable,
additive, public-schema table / model (Option A), fixed how every `TenantBackupStatus` field is derived,
and fixed the freshness / honesty / redaction / visibility rules plus the migration + adapter boundaries.
P17-D-A deliberately did NOT define the implementation -- it named the source a future phase must build.

**P17-D-B is that implementation-ready plan.** It converts the P17-D-A contract into a precise blueprint
a future P17-D-C can build from, with no ambiguity left to invent at build time. P17-D-B has four jobs
and does nothing else:

1. **Schema plan (section 2).** The exact additive, public-schema tables -- column names, Postgres types,
   nullability, defaults, indexes, uniqueness, CHECK constraints, and the FK-like (soft, non-enforced)
   `tenant_id` relationship. No migration file is created.
2. **Enum + closed-vocabulary plan (section 3).** The additive stored enum types, the closed-vocabulary
   `failure_reason_code` (text + CHECK, mirroring `BACKUP_FAILURE_REASONS`), and the DERIVED (non-stored)
   status values (`stale`, `unknown`) that the adapter computes at read time.
3. **Mapping, freshness, redaction, write-source boundary, registry read plan, migration plan, test
   plan, acceptance criteria, counterexamples (sections 4-11).** The field-by-field mapping onto
   `TenantBackupStatus`, the freshness windows (24h backup + the restore-test cadence P17-D-B pins), the
   redaction rules, the writer contract (what the ops backup process must record), the read-only registry
   read wiring plan for P17-D-C, the additive migration plan for P17-D-C, and the G1-G18 test plan.
4. **Gate the successors (sections 12-13).** Fix the P17-D-C entry gate and the P22-E3 re-entry gate so
   no migration, no model, no registry rewiring, and no `backup.check` read begins until this plan is
   CTO-accepted and the upstream contract is accepted.

P17-D-B plans and gates; it implements nothing. **No migration is added, no ORM model is created or
registered, no table exists, no registry code is changed, and no `backup.check` execution or read is
started by P17-D-B.** The single invariant, carried from P10 / P17 / P22-E0, holds absolutely inside this
plan:

> **Unknown is never healthy, null is never zero, success is never stale, and a backup source is never
> fabricated healthy. A plan is not a table and a table is not an execution: P17-D-B specifies the
> schema a future phase may build; it does not build it, register it, or run anything.**

### 1.2 Non-goals

- No runtime code, no backend handler, no ORM model FILE, no model registration in the declarative base,
  no repository / loader, no migration, no alembic change, no table, no column, no test code, and no
  dependency change.
- **No real source.** P17-D-B does not provision, build, wire, or read any backup / status source. It
  does not parse `backup.log`, list a dump directory, call any backup API, or contact any production
  external system.
- **No pg_dump, no restore, no restore test.** P17-D-B runs no backup and no restore and adds no script
  that does.
- **No migration / model.** P17-D-B creates no alembic revision, creates no ORM model file, registers no
  model, and creates no table. Those are P17-D-C, separately gated.
- **No P22 change.** `backend/api/v1/platform/p22/seam.py` and `adapters.py` are unchanged (cited
  read-only). No `backup.check` adapter is wired, upgraded, or probed.
- **No P16 change.** No `scripts/platform_worktree_executor.py` or any P16 asset is touched.
- **No registry rewrite.** `_build_registry` (`backend/api/v1/platform/p17/services.py`) is unchanged;
  `backup_status` stays `None` with the reason surfaced (cited read-only).
- **No auth / RBAC / session / tenancy rewrite, no product / payment / billing path.**
- **No merge or push of platform-dev, and no push to any product branch.**

---

## 2. Relationship to P17-D-A and P22-E2

P17-D-B is the implementation-ready refinement of the P17-D-A contract. The relationship is exact and
one-directional:

- **P17-D-A** said *what kind* of source to build (Option A durable table / model) and *how it behaves*
  (mapping, freshness, redaction, visibility, migration + adapter boundaries). It gave a *planning
  shape* for the tables (field names only) and explicitly deferred the exact types / nullability /
  indexes / constraints / enum values / cadence / writer contract / test plan to P17-D-B.
- **P17-D-B** (this plan) fills exactly those deferred details. Where this plan refines the P17-D-A
  planning shape (e.g. it adds `restore_test_cadence_hours` to the policy table, and it separates stored
  outcome status from derived read-time status), the refinement is **additive and consistent** with the
  P17-D-A rules (additive only, public-schema only, nullable / safe-default columns, closed-vocabulary
  redaction, no FK into tenant business tables). P17-D-B changes no P17-D-A contract term.
- **P22-E2** returned SOURCE_UNKNOWN and enumerated the minimum P17 prerequisite set (a real source of
  outcomes; persistence or a live client; registry wiring; freshness + restore-test cadence;
  degrade-on-failure error semantics). P17-D-B specifies exactly how P17-D-C will satisfy items 1-5 at
  the schema / model / wiring layer. P17-D-B does NOT lift the P22-E3 gate: `backup.check` stays
  `source_unknown` / `not_implemented` until P17-D-C lands AND P22-E3 begins.

P17-D-B is plan-only; until P17-D-C lands the migration + model + registry wiring, the P22-E2 verdict
stands verbatim, `_build_registry` keeps `backup_status=None`, and `backup.check` is unchanged.

---

## 3. Schema Plan

Two additive tables in the **public platform schema** (the same additive, public-schema discipline the
P21-C1 durable-approval migration established). Field names refine the P17-D-A planning shape; types /
nullability / defaults / indexes / constraints are fixed here. P17-D-B creates NONE of this -- it is the
plan only.

### 3.1 `platform_backup_outcome` (append-only outcome rows)

One row per backup-job or restore-test-job run. Append-only: the registry adapter (P17-D-C) only ever
INSERTs are performed by the writer and only ever SELECTs by the adapter; there is no in-place UPDATE of
an outcome row in the registry read path.

| Column | Postgres type | Null | Default | Notes |
|---|---|---|---|---|
| `outcome_id` | `uuid` | NOT NULL | `gen_random_uuid()` | Primary key. Requires `pgcrypto` (the same extension the P21-C1 / init.sql prerequisite set enables). |
| `tenant_id` | `uuid` | NULL | -- | NULL = platform-wide outcome (today's writer is platform-wide). **Scoped identifier only -- NOT a foreign key, never joinable to tenant business tables** (orders / payments / invoices / customers / inventory / ledgers). |
| `job_kind` | `platform_backup_job_kind` | NOT NULL | -- | `backup_job` or `restore_test_job`. |
| `status` | `platform_backup_outcome_status` | NOT NULL | -- | `success` / `partial` / `failed` / `in_progress`. **Does NOT include `stale` or `unknown`** -- those are DERIVED at read time (section 4). |
| `started_at` | `timestamptz` | NOT NULL | -- | UTC; when the job began. |
| `completed_at` | `timestamptz` | NULL | -- | UTC; NULL iff `status = 'in_progress'`. |
| `bytes_written` | `bigint` | NULL | -- | Dump size in bytes ONLY (a magnitude). NEVER a path, file name, host, or DSN. NULL when not applicable (in_progress / failed). `> 0` required when `status = 'success'`. |
| `failure_reason_code` | `text` | NULL | -- | Closed vocabulary only (section 3 / CHECK constraint mirrors `BACKUP_FAILURE_REASONS`). Required when `status = 'failed'`; forbidden when `status` in (`success`, `in_progress`). NEVER the raw exception / stack / exit code / command line / log line. |
| `source_writer_id` | `text` | NULL | -- | A stable writer LABEL (e.g. `backup_postgres.sh`, `restore_test_runner`). NEVER a path, host, DSN, or credential. |
| `created_at` | `timestamptz` | NOT NULL | `now()` | Row insert time (append-only). |

**Primary key:** `outcome_id`.

**Indexes (recency reads without a full scan):**

```text
idx_pbo_tenant_kind_completed:
    (tenant_id, job_kind, completed_at DESC NULLS LAST)
    -- backs the "latest completed outcome per (tenant|platform-wide) per job_kind" read.
    -- NULLS LAST keeps in_progress (completed_at IS NULL) off the top of a DESC scan.
```

A single composite index serves both the tenant-specific branch (`tenant_id = X`) and the platform-wide
branch (`tenant_id IS NULL`); Postgres btree indexes NULLs by default.

**Uniqueness:** `outcome_id` (PK) only. Outcomes are append-only; no natural unique key (a writer may
legitimately record multiple rows per run-attempt).

**CHECK constraints (encode the honesty invariants at the DB layer, defense in depth):**

```text
pbo_completed_iff_not_in_progress:
    (status = 'in_progress') = (completed_at IS NULL)
    -- completed_at IS NULL exactly when the job is still running.

pbo_failure_reason_scope:
    (failure_reason_code IS NOT NULL) = (status IN ('failed', 'partial'))
    -- a failure/partial verdict carries an allowlisted code; success/in_progress carry none.

pbo_bytes_scope:
    (bytes_written IS NULL) OR (status IN ('success', 'partial'))
    -- bytes only for jobs that produced output.

pbo_success_has_bytes:
    (status <> 'success') OR (bytes_written IS NOT NULL AND bytes_written > 0)
    -- success requires a non-empty dump (mirrors backup_postgres.sh `[ -s file ]`).

pbo_failure_reason_allowlist:
    failure_reason_code IS NULL OR failure_reason_code IN
    ('backup_job_timeout', 'restore_checksum_mismatch', 'backup_source_unreachable',
     'restore_test_failed', 'backup_incomplete', 'unknown')
    -- mirrors BACKUP_FAILURE_REASONS exactly; raw reasons cannot persist.
```

### 3.2 `platform_backup_policy` (optional per-tenant / platform-default config)

A small admin-managed config table. At most one row per tenant plus at most one platform-default row
(`tenant_id IS NULL`). P17-D-B refines the P17-D-A planning shape by adding `restore_test_cadence_hours`
(additive; needed so restore-test freshness is configurable, section 5).

| Column | Postgres type | Null | Default | Notes |
|---|---|---|---|---|
| `policy_id` | `uuid` | NOT NULL | `gen_random_uuid()` | Primary key (pgcrypto). |
| `tenant_id` | `uuid` | NULL | -- | NULL = platform default. Scoped identifier only -- NOT a FK. |
| `retention_policy` | `text` | NULL | -- | Short human label only (e.g. `7 daily`). No secrets / paths. |
| `export_enabled` | `boolean` | NULL | -- | NULL = unset (null != false). |
| `restore_test_cadence_hours` | `integer` | NULL | -- | NULL = use the platform default cadence. Overrides the default restore-test window for this tenant. |
| `created_at` | `timestamptz` | NOT NULL | `now()` | |
| `updated_at` | `timestamptz` | NOT NULL | `now()` | Last config edit. |

**Primary key:** `policy_id`.

**Uniqueness:**

```text
uq_pbp_tenant:
    UNIQUE (tenant_id)
    -- at most one policy per tenant.
idx_pbp_platform_default (partial unique):
    UNIQUE (tenant_id) WHERE tenant_id IS NULL
    -- at most one platform-default row (a partial unique index, because Postgres UNIQUE treats
       multiple NULLs as distinct and so cannot alone enforce a single NULL row).
```

### 3.3 FK-like relationships

- **`tenant_id` is a scoped identifier, NOT a database foreign key.** The contract (P17-D-A section 8)
  forbids any FK into tenant business tables. An optional, NON-enforced soft reference to the platform
  tenant identity (`public.platform_tenants.wholesaler_id`, the same identifier P17 services use) is
  administratively meaningful, but P17-D-C does NOT add a hard FK (it would couple the additive backup
  migration to the provisioning journal and risk a tenant-business adjacency). The column is just a
  scoped UUID.
- **No relationship between the two backup tables is enforced.** `platform_backup_policy.tenant_id` and
  `platform_backup_outcome.tenant_id` share a convention (the scoped identifier), not a constraint.

---

## 4. Enum Plan

### 4.1 Additive STORED enum types (created by the P17-D-C migration)

```text
platform_backup_job_kind       AS ENUM ('backup_job', 'restore_test_job')
platform_backup_outcome_status AS ENUM ('success', 'partial', 'failed', 'in_progress')
```

Stored status deliberately EXCLUDES `stale` and `unknown`. Those are read-time DERIVATIONS, not facts
about a job: a job either succeeded / partly succeeded / failed or is still running. The adapter
computes `stale` (timestamp outside its window) and `unknown` (no outcome / read cannot confirm) when it
builds `TenantBackupStatus`. This separation is the core honesty mechanism: the table cannot lie that a
stale backup is fresh, because freshness is never stored.

New enum values are appended in future revisions; existing values are not removed or reordered (Postgres
ENUM ordering is load-bearing).

### 4.2 Closed-vocabulary `failure_reason_code` (text + CHECK, NOT an enum)

Stored as `text` with a CHECK constraint that mirrors the Python `BACKUP_FAILURE_REASONS` frozenset
EXACTLY (`backend/api/v1/platform/p17/schemas.py:251-260`):

```text
backup_job_timeout
restore_checksum_mismatch
backup_source_unreachable
restore_test_failed
backup_incomplete
unknown
```

Using `text` + CHECK (not a Postgres enum) keeps the vocabulary editable in lock-step with the Python
allowlist without an enum-type migration; the CHECK and the frozenset MUST stay in sync (the
`failure_reason_is_allowlisted` field validator and `redact_failure_reason` collapse are the runtime
backstops). Any raw reason not in the set is collapsed to `unknown` by the writer before insert and
rejected by the CHECK if it ever reaches the DB.

### 4.3 DERIVED (non-stored) status values (computed by the P17-D-C adapter)

| Response enum (P17) | Stored basis | Derived additions | Derivation |
|---|---|---|---|
| `LastBackupStatus` (`success` / `partial` / `failed` / `in_progress` / **`stale`** / **`unknown`**) | latest `backup_job` row `status` | `stale`, `unknown` | `stale`: a `success` whose `completed_at` is outside the 24h window (`enforce_backup_freshness`). `unknown`: no outcome row, or a read that cannot confirm. |
| `RestoreTestStatus` (`passed` / `failed` / **`stale`** / **`unknown`**) | latest `restore_test_job` row `status` (`success` -> `passed`) | `stale`, `unknown` | `stale`: a `passed`/`failed` older than the restore-test cadence. `unknown`: no restore-test outcome. |
| `RegistrySourceStatus` (`available` / `unavailable` / `unknown`) | table readability + outcome existence | -- | `available`: table readable AND >= 1 outcome exists. `unavailable`: read failure. `unknown`: table readable but no outcome ever recorded. This is the `backup_source_status` hinge. |

### 4.4 Config / retention / export fields

- `retention_policy` (`text`): short human label (e.g. `7 daily`), sourced from
  `platform_backup_policy.retention_policy`. Defaults to the platform-default row, else NULL.
- `export_enabled` (`boolean`): from `platform_backup_policy.export_enabled`; NULL = unset.
- `restore_test_cadence_hours` (`integer`): per-policy override of the restore-test cadence window.

---

## 5. Model Mapping (outcome row -> `TenantBackupStatus`)

The P17-D-C adapter builds `TenantBackupStatus` (`backend/api/v1/platform/p17/schemas.py:267`) from the
latest outcome row(s) + policy, routing every populated status through the existing freshness helper and
validator. No new response shape is invented.

**Resolution rule (latest completed outcome):** for a given tenant, the adapter prefers a
tenant-specific outcome (`tenant_id = X`); if none exists it falls back to the platform-wide outcome
(`tenant_id IS NULL`). This fallback is legitimate because today's only writer
(`backup_postgres.sh`) is a whole-database `pg_dump` whose freshness applies to every tenant. The
fallback is applied independently per `job_kind` (backup vs restore-test).

| `TenantBackupStatus` field | How the durable source populates it | When unavailable |
|---|---|---|
| `last_backup_at` | `completed_at` of the latest COMPLETED `backup_job` row (tenant-specific, else platform-wide). UTC ISO-8601. | `null` if no outcome row exists |
| `last_backup_status` | Mapped from the latest `backup_job` row `status`, then routed through `enforce_backup_freshness`: a `success` whose `completed_at` is older than 24h downgrades to `stale`; a missing timestamp downgrades to `unknown`. | `null` + reason on a read failure; `unknown` if no row; `stale` if outside 24h |
| `last_restore_test_at` | `completed_at` of the latest COMPLETED `restore_test_job` row (tenant-specific, else platform-wide). | `null` if no restore-test was ever recorded |
| `restore_test_status` | `passed`/`failed` from the latest `restore_test_job` row (`status='success'` -> `passed`); `stale` if older than the restore-test cadence; `unknown` if no row. Until a restore-test runner writes `restore_test_job` rows, this reads `unknown`. | `null` + reason on a read failure; `unknown` if none; `stale` if outside cadence |
| `export_available` | Derived: a non-empty dump exists for the tenant/platform within retention AND the latest backup is not `failed` -> `true`; else `false`. | `null` + reason on a read failure |
| `retention_policy` | From `platform_backup_policy.retention_policy` (tenant row, else platform-default). | `null` if no policy row |
| `failure_reason_redacted` | The allowlisted `failure_reason_code` of the latest `failed`/`partial` `backup_job` outcome; collapsed by `redact_failure_reason` otherwise. | `null` if the latest outcome is not a failure/partial |
| `backup_source_status` | `available` ONLY when the table is readable AND at least one outcome exists; `unavailable` on a read failure; `unknown` when readable but no outcome was ever recorded. | always present (required field) |
| `last_status_check_at` | The UTC timestamp at which the adapter performed this read. | `null` if never checked |

Registry-level consequence (unchanged from P17 today): when `backup_source_status` is not `available`,
the registry keeps `backup_status` nullable and surfaces the reason in the registry `unavailable_reason`.
`backup_source_status` is the honest hinge: `available` is asserted only when a real, fresh outcome backs
the rendered status. Every populated status is routed through `enforce_backup_freshness`
(`schemas.py:461`) and the `success_requires_fresh_timestamp` validator (`schemas.py:319`).

---

## 6. Freshness Plan

The source and its adapter obey the P10 / P17 / P22 source-honesty invariants absolutely. P17-D-B pins
the one value P17-D-A deferred -- the restore-test cadence.

1. **24h backup freshness window (exists, unchanged).** `BACKUP_FRESHNESS_WINDOW = timedelta(hours=24)`
   (`schemas.py:264`). A `last_backup_status` of `success` is valid ONLY when `last_backup_at` is within
   24h of the read time AND `backup_source_status` equals `available`. Outside the window, `success`
   downgrades to `stale` (`enforce_backup_freshness`); it never renders as `success`.
2. **Restore-test cadence (PINNED by P17-D-B).** A NEW constant, proposed at
   `RESTORE_TEST_CADENCE_WINDOW = timedelta(hours=168)` (7 days), overridable per-policy via
   `platform_backup_policy.restore_test_cadence_hours`. A `restore_test_status` of `passed`/`failed`
   whose `last_restore_test_at` is older than the (policy-or-default) cadence reads `stale`. *(If the
   CTO prefers a different default cadence -- e.g. monthly -- it is set here in P17-D-B, once.)*
3. **Success requires a fresh timestamp AND an available source.** The `success_requires_fresh_timestamp`
   validator rejects `last_backup_status='success'` with a null `last_backup_at` or with
   `backup_source_status != 'available'`. There is no success without proof.
4. **Unknown is never healthy.** An `unknown` source (no outcome ever recorded, or a read that cannot
   confirm) never yields `success` / `active` / `healthy`; it yields `unknown` (or `null` plus a reason).
5. **Null is never zero.** An unavailable `bytes_written` / `export_available` / timestamp is `null`,
   never `0` / bare `false`.
6. **Stale is never success.** A timestamp outside its window downgrades the rendered status; the adapter
   never preserves `success` across a stale timestamp, and never preserves `passed` across a stale
   restore-test timestamp.
7. **Fail closed on read failure.** A source read failure degrades to `null` plus an
   `unavailable_reason` (`backup_source_status='unavailable'`), never a 500 and never a fabricated
   `success` / `available` -- the degrade-on-failure discipline every other P17 sub-source follows.
8. **Read consistency.** The adapter reads the last COMMITTED, COMPLETED outcome row
   (`completed_at IS NOT NULL`); it does not synthesize a status from partial or in-flight state.

---

## 7. Redaction Plan

The source, its writer, and the adapter NEVER store or expose raw operational detail. The following are
forbidden in any outcome row, policy row, registry response, audit payload, or support bundle:

- **Raw backup logs** -- the free-text `backup.log` lines, `pg_dump` stdout / stderr, exit-code detail.
- **DSNs, connection strings, host, port, credentials** -- including the hardcoded default password in
  `backup_postgres.sh` (`MpangoDBV0.1.2`, a pre-existing ops-script concern; it must never flow into the
  source).
- **File path secrets** -- dump directory paths (`/opt/mpango/backups`), dump file names
  (`mpango_backup_<ts>.sql`), volume mounts, container paths (`/tmp/backup.dump`).
- **Dump contents** -- the `.dump` / `.sql` bytes are never read, stored, or echoed.

Persistent columns that could leak are constrained to safe shapes:

- `failure_reason_code` is the closed `BACKUP_FAILURE_REASONS` vocabulary, enforced by CHECK + the
  `failure_reason_is_allowlisted` validator + the `redact_failure_reason` collapse. A raw reason is
  collapsed to `unknown` before insert.
- `bytes_written` is a magnitude only (never a path).
- `source_writer_id` is a stable writer LABEL (never a path / host / DSN / credential).
- `retention_policy` is a short human label (never a path / DSN).

---

## 8. Write-Source Boundary

The writer is the operational backup process (or a thin recorder it calls). P17-D-B specifies the
**insert contract**; P17-D-B does NOT implement the writer (wiring the recorder into `backup_postgres.sh`
or a restore-test runner is a separate operational task, not a P17-D-C runtime scope item).

**Today's writer -- `ai-ledger/ops/backup_postgres.sh`** (a cron-driven whole-database `pg_dump`):
- is **platform-wide** (dumps the whole `mpango_erp` database), so it records `tenant_id = NULL`;
- emits only `job_kind = 'backup_job'` (it runs no restore test);
- maps its two outcomes to `status`: exit 0 + non-empty file -> `success`; empty/missing file or any
  `pg_dump` / `docker` failure (`set -e`) -> `failed`;
- sets `bytes_written` to the dump file size (`stat` bytes) on `success`, NULL on `failed`;
- sets `failure_reason_code = 'backup_incomplete'` on the empty/missing-file case, `'unknown'` on a
  `pg_dump` / `docker` failure (after collapsing any raw output), NULL on `success`;
- sets `source_writer_id = 'backup_postgres.sh'`;
- sets `started_at` / `completed_at` to the run start / end (UTC).

**Consequences the plan fixes in advance:**
- `restore_test_job` outcomes are NOT producible by today's writer, so `restore_test_status` reads
  `unknown` until a separate restore-test runner exists and records `restore_test_job` rows. P17-D-B /
  P17-D-C do NOT build that runner.
- `partial` and `in_progress` are reserved for future finer-grained writers; today's writer emits neither.

**The runtime read path is READ-ONLY.** The P17-D-C registry adapter only SELECTs outcome rows; it never
INSERTs, UPDATEs, or DELETEs them. Writes are writer-only.

---

## 9. Registry Read Plan (for future P17-D-C)

P17-D-C wires the registry READ path to the durable source, mirroring the existing
`_load_provisioning_map` / `_build_provisioning_status` pattern in
`backend/api/v1/platform/p17/services.py`.

1. **Best-effort loader.** Add `_load_backup_status(db, tenant_id, now)` analogous to
   `_load_provisioning_map` (`services.py:56`): it SELECTs the latest completed `backup_job` and
   `restore_test_job` outcome rows (tenant-specific preferred, else platform-wide) and the tenant / \
   platform-default policy. On ANY error it returns a degraded sentinel (never raises), exactly as
   `_load_provisioning_map` returns `{}` on error.
2. **Builder.** Add `_build_backup_status(...)` analogous to `_build_provisioning_status`
   (`services.py:182`): it constructs an `Optional[TenantBackupStatus]` from the loaded rows, routes
   `last_backup_status` through `enforce_backup_freshness` and `restore_test_status` through the cadence
   window, applies `redact_failure_reason`, and returns `None` (registry-level null + reason) when the
   source is absent.
3. **Assembly.** In `_build_registry` (`services.py:231`), replace `backup_status=None`
   (`services.py:271`) with the built status, and STOP appending `_BACKUP_UNAVAILABLE_REASON`
   (`services.py:217`) to the registry `unavailable_reason` when the source reads `available`. When the
   source is `unavailable` / `unknown`, `backup_status` stays nullable and the reason is surfaced -- the
   existing degrade path is reused unchanged.
4. **`backup_source_status` hinge.** `available` only when the table is readable and an outcome exists;
   `unavailable` on read failure; `unknown` when readable but empty.
5. **Read-only, no P22.** The loader / builder touch ONLY the P17 registry read path. They do NOT touch
   `backend/api/v1/platform/p22/seam.py` or `adapters.py`, do NOT wire or probe `backup.check`, and claim
   NO execution. `backup.check` stays `source_unknown` / `not_implemented` until P22-E3.
6. **Freshness + validator.** Every populated status routes through `enforce_backup_freshness` and the
   `success_requires_fresh_timestamp` backstop.

---

## 10. Migration Plan (for future P17-D-C)

P17-D-C is the EARLIEST phase that MAY create the migration (P17-D-B creates none). The migration MUST
obey (all conjunctive):

1. **One additive alembic revision** (the P21-C1 precedent): `CREATE TYPE` the two enum types, `CREATE
   TABLE` the two tables, `CREATE INDEX` the recency index + uniqueness, and add the CHECK constraints.
2. **Public / platform schema only.** No tenant business schema, no tenant business table, no FK into
   orders / payments / invoices / customers / inventory / ledgers. `tenant_id` is a scoped column, not a
   joinable key.
3. **Additive only.** New tables / columns / indexes / enum types only. No existing column is narrowed,
   renamed, retyped, or dropped; no existing row is rewritten; no storage switch.
4. **Nullable columns / safe defaults.** Every new column is nullable or has a safe default, so the up
   migration is instant and online; no backfill that locks tenant tables.
5. **pgcrypto prerequisite.** `outcome_id` / `policy_id` use `gen_random_uuid()`, which needs `pgcrypto`
   (the init.sql prerequisite set already enables it; the migration asserts it is enabled, mirroring the
   P21-C1 / ephemeral-Postgres testing prerequisite).
6. **ORM enum decode must match.** The ORM model's `postgresql.ENUM(create_type=False)` value lists for
   `platform_backup_job_kind` and `platform_backup_outcome_status` MUST match the migration exactly so
   rows decode (the P21 ORM-enum lesson). Values are not invented at runtime.
7. **Safe rollback / downgrade.** The down revision drops ONLY the additive tables / enums / indexes /
   constraints created by the up revision. Because the tables are additive and hold only
   platform-operational data, downgrade loses no tenant or business data. The downgrade is tested.
8. **Dry-run / pre / post checks.** `alembic upgrade --sql` review (pre); after apply, assert the two
   tables exist, the enum values match sections 4.1, the recency index exists, and the CHECK constraints
   reject a bad `failure_reason_code` (post). Run against the ephemeral-postgres migration-testing
   container (never `mpango_erp`).

P17-D-C also creates the ORM model file and registers the models; P17-D-B specifies the plan only and
creates none of it.

---

## 11. Test Plan (G1-G18)

Tests are authored in P17-D-C (P17-D-B authors none). The plan fixes the gates so P17-D-C has nothing to
invent. Coverage mandated by the task is explicitly mapped.

- **G1 -- fresh success renders success.** Insert a `backup_job` outcome `status='success'`,
  `completed_at` within 24h -> `last_backup_status='success'`, `backup_source_status='available'`.
  (mandated: fresh success)
- **G2 -- stale success downgrades to stale.** `status='success'`, `completed_at` > 24h -> reads `stale`,
  never `success`. (mandated: stale success downgrade)
- **G3 -- unknown is never healthy.** No outcome row -> `last_backup_status='unknown'`,
  `backup_source_status='unknown'`; never `success` / `active` / `healthy`. (mandated: unknown never
  healthy)
- **G4 -- null is never zero.** No `bytes_written` / no `export_available` -> `null`, not `0` / bare
  `false`. (mandated: null never zero)
- **G5 -- failed outcome renders failed + allowlisted reason.** `status='failed'`,
  `failure_reason_code='backup_incomplete'` -> `last_backup_status='failed'`,
  `failure_reason_redacted='backup_incomplete'`.
- **G6 -- raw failure reason is redacted.** A writer attempt to persist a raw log string as
  `failure_reason_code` is collapsed to `unknown` (and rejected by the CHECK constraint if it reaches the
  DB); the response never echoes raw output. (mandated: redaction)
- **G7 -- restore-test freshness.** A `restore_test_job` `status='success'` (`-> passed`) within cadence
  reads `passed`; older than the cadence reads `stale`.
- **G8 -- restore-test unknown until a runner exists.** No `restore_test_job` row -> `restore_test_status
  ='unknown'` (the expected state until a restore-test runner is built).
- **G9 -- success requires fresh timestamp + available source.** The `success_requires_fresh_timestamp`
  validator rejects `success` with a null `last_backup_at` or `backup_source_status != 'available'`.
- **G10 -- summary projection (support).** A support / bundle view exposes ONLY `last_backup_status` and
  `export_available`; `failure_reason_redacted` and restore-test detail are hidden. (mandated:
  summary/full visibility)
- **G11 -- full projection (engineering / identity-only super_admin).** The full `TenantBackupStatus`,
  including `failure_reason_redacted` and restore-test detail, is readable read-only.
  (mandated: summary/full visibility)
- **G12 -- read failure degrades.** A simulated DB read error -> `backup_status=None` +
  `unavailable_reason` + `backup_source_status='unavailable'`; never a 500, never a fabricated `success`.
  (mandated: read failure degrade)
- **G13 -- tenant-specific preferred over platform-wide.** When both a tenant-specific and a
  platform-wide outcome exist, the tenant-specific one wins; the platform-wide row is the fallback only.
- **G14 -- closed-vocabulary enforced at the DB.** An insert with a non-allowlisted `failure_reason_code`
  is rejected by the CHECK constraint; the Python `failure_reason_is_allowlisted` validator rejects the
  same at construction.
- **G15 -- no P22 wiring.** After P17-D-C, `backend/api/v1/platform/p22/seam.py` and `adapters.py` are
  unchanged; `backup.check` stays `source_unknown` / `not_implemented`. (mandated: no P22 wiring)
- **G16 -- read path is read-only.** A registry read inserts / updates / deletes no outcome row (append-
  only; writer-only mutations).
- **G17 -- in_progress excluded from latest-completed.** An `in_progress` row (`completed_at IS NULL`)
  is not returned as the latest completed outcome (NULLS LAST / `completed_at IS NOT NULL`).
- **G18 -- bytes is a magnitude, success needs bytes.** `bytes_written` is an integer (never a path); a
  `success` row requires `bytes_written > 0` (the CHECK constraint + the `[ -s file ]` semantics).

---

## 12. Acceptance Criteria (P17-D-B is accepted only when ALL hold)

1. **P17-D-B is docs-only / planning-only.** No runtime code, backend, ORM model FILE, model registration,
   migration, alembic change, table, test code, or dependency change ships in P17-D-B.
2. **The schema plan is complete and exact.** Section 3 fixes both tables' columns, Postgres types,
   nullability, defaults, primary keys, indexes, uniqueness, and CHECK constraints.
3. **`tenant_id` is a scoped identifier, not a FK.** Section 3.3 records that no FK into tenant business
   tables is added and `tenant_id` is never joinable to orders / payments / invoices / customers /
   inventory / ledgers.
4. **The enum plan separates stored from derived.** Section 4 records the two stored enum types
   (`platform_backup_job_kind`, `platform_backup_outcome_status` -- excluding `stale`/`unknown`), the
   closed-vocabulary `failure_reason_code` (mirroring `BACKUP_FAILURE_REASONS`), and the derived
   `stale`/`unknown` read-time values.
5. **The mapping is total.** Section 5 maps every `TenantBackupStatus` field to its outcome-row
   derivation + policy + unavailable fallback, including the tenant-specific-vs-platform-wide resolution
   rule.
6. **The restore-test cadence is pinned.** Section 6 pins `RESTORE_TEST_CADENCE_WINDOW` (proposed 168h,
   per-policy overridable) -- the one value P17-D-A deferred.
7. **Freshness rules are fixed.** Section 6 fixes the 24h backup window, the restore-test cadence,
   success-requires-fresh+available, unknown-never-healthy, null-never-zero, stale-never-success, and
   fail-closed-on-read-failure.
8. **Redaction is closed-vocabulary and shape-constrained.** Section 7 forbids raw logs / DSN / host /
   port / path secrets / dump contents and constrains `failure_reason_code` / `bytes_written` /
   `source_writer_id` / `retention_policy` to safe shapes.
9. **The writer contract is honest about today's writer.** Section 8 records that `backup_postgres.sh`
   emits platform-wide `backup_job` outcomes only (success/failed), that `restore_test_job` outcomes
   require a not-yet-built runner, and that the read path is read-only.
10. **The registry read plan is read-only and source-gated.** Section 9 fixes the loader / builder /
    assembly shape, the `backup_source_status` hinge, degrade-on-failure, and that P17-D-C touches no P22
    code.
11. **The migration plan is additive + public-schema.** Section 10 fixes one additive revision,
    public-schema-only, nullable/default columns, pgcrypto prerequisite, ORM-enum-decode-match, safe
    rollback, and dry-run / pre / post checks.
12. **The test plan covers the mandated cases.** Section 11 fixes G1-G18 including fresh success, stale
    success downgrade, unknown-never-healthy, null-never-zero, redaction, summary/full visibility,
    read-failure degrade, and no-P22-wiring.
13. **No real source is built.** P17-D-B provisions, builds, wires, registers, and reads no source; it
    parses no log, lists no dump directory, calls no backup API, contacts no production system.
14. **No pg_dump / restore / restore-test.** P17-D-B runs no backup, no restore, and no restore test.
15. **No migration / model.** P17-D-B creates no alembic revision, no ORM model file, registers no model,
    and creates no table.
16. **No P22 / P16 change.** `seam.py`, `adapters.py`, and all P16 assets are unchanged (cited
    read-only).
17. **No registry rewrite.** `_build_registry` is unchanged; `backup_status=None` + the reason stands.
18. **No auth / RBAC / session / tenancy / payment change, no product business path.**
19. **platform-dev untouched.** `origin/platform-dev` is not merged and not pushed from P17-D-B; only the
    isolated branch carries the changes.
20. **Counterexamples covered.** Section 13 enumerates the misuse patterns this plan rejects, including
    fabricated healthy, stale success, raw-log exposure, restore mistaken for check, product-data
    mutation, and a P22 adapter wired before the source.
21. **P17-D-C not started.** P17-D-B begins no migration / model / registry-wiring work; P17-D-C may begin
    only after CTO acceptance of this plan (section 14).
22. **P22-E3 not started.** P17-D-B begins no `backup.check` work; P22-E3 may begin only after P17-D-C is
    merged + tested (section 15).

---

## 13. Counterexamples (this plan must reject these)

Each is REJECTED. The six mandated families are called out at the top.

1. **Fabricated healthy status.** A writer / adapter that synthesizes `status='success'` or a fresh
   `completed_at` for an empty / unknown source -- rejected; `success` requires a real, fresh, available
   outcome. (Sections 5, 6.)
2. **Stale success.** A `last_backup_status='success'` rendered while `completed_at` is outside 24h --
   rejected; it must read `stale`. (Section 6.)
3. **Raw-log / path / credential exposure.** A writer / adapter / bundle that persists or echoes a
   `backup.log` line, a dump file path / name, a host / port, a DSN, the hardcoded script password, or
   dump bytes -- rejected. (Section 7.)
4. **Restore mistaken for check.** Treating `backup.check` (a read-only status read) as a restore /
   restore-test / state-changing op, or routing restore through the read-only check path -- rejected.
   (Sections 8, 9, 15.)
5. **Product / tenant business data mutation.** A migration / model / adapter that writes, joins, or
   foreign-keys into orders / payments / invoices / customers / inventory / ledgers, or enters a product
   / payment / billing code path -- rejected. (Sections 3.3, 10.)
6. **P22 adapter wired before the source.** A P22-E3 `backup.check` adapter / probe that begins before
   P17-D-C is merged + tested -- rejected by the P22-E3 re-entry gate. (Section 15.)
7. **Runtime reads ops artifacts directly (Option B as the source).** An adapter that parses
   `backup.log` or lists the dump directory at request time instead of reading the durable table --
   rejected. (Sections 3, 9.)
8. **`success` without an available source.** `last_backup_status='success'` with
   `backup_source_status != 'available'` or a null `last_backup_at` -- rejected. (Sections 5, 6.)
9. **`null` reported as `0`.** An unavailable `bytes_written` / `export_available` rendered as `0` / bare
   `false` instead of `null` -- rejected. (Sections 5, 6.)
10. **`unknown` reported as healthy.** A source with no outcome row rendered as `success` / `active` /
    `healthy` -- rejected. (Section 6.)
11. **Storing `stale` / `unknown` in the outcome table.** A schema that stores `stale` or `unknown` as a
    `status` value (they are read-time derivations) -- rejected; it would let the table lie about
    freshness. (Section 4.)
12. **Non-allowlisted `failure_reason_code`.** A row / response carrying the raw exception, exit code,
    command line, stack trace, log line, or any value outside `BACKUP_FAILURE_REASONS` -- rejected by the
    CHECK constraint, the field validator, and `redact_failure_reason`. (Sections 4, 7.)
13. **Non-additive migration.** A P17-D-C migration that narrows / renames / retypes / drops an existing
    column, adds a tenant-schema table or a tenant-business FK, or switches storage -- rejected.
    (Section 10.)
14. **Unsafe rollback.** A down migration that drops or rewrites non-additive / tenant / business data --
    rejected. (Section 10.)
15. **ORM enum mismatch.** An ORM `postgresql.ENUM` value list that does not match the migration's enum
    exactly -- rejected (rows would not decode). (Section 10; P21 lesson.)
16. **`in_progress` mistaken for the latest completed.** An adapter that returns an `in_progress` row
    (`completed_at IS NULL`) as the latest backup -- rejected. (Sections 3, 11/G17.)
17. **`bytes_written` as a path.** A `bytes_written` value that is a path / file name / DSN rather than a
    magnitude -- rejected; `success` must carry `bytes_written > 0`. (Sections 3, 11/G18.)
18. **Registry rewired before the source exists.** A P17-D-C that replaces `backup_status=None` before
    the migration + model land -- rejected. (Section 9.)
19. **Writer mutates from the read path.** A registry read that INSERTs / UPDATEs / DELETEs an outcome row
    -- rejected; outcomes are append-only, writer-only. (Sections 3, 8, 11/G16.)
20. **P22 `backup.check` reads full diagnostics.** A `backup.check` adapter that reads
    `failure_reason_redacted` or restore-test detail instead of the summary projection -- rejected.
    (Section 15.)
21. **P17-D-B ships runtime code.** Any backend, ORM model file, model registration, migration, adapter,
    test, or dependency change shipped inside P17-D-B itself -- rejected; P17-D-B is plan-only.
    (Section 1.2.)

---

## 14. P17-D-C Entry Gate

P17-D-C (not started by P17-D-B) is the EARLIEST phase that MAY create the migration, the ORM model file,
the model registration, and the registry read wiring. It may begin ONLY after explicit CTO acceptance of
this plan, and ONLY under these constraints:

1. **Follow this plan.** The migration, model, and wiring implement sections 3-10 exactly; deviations
   require a new plan revision, not an in-flight change.
2. **Additive + public-schema boundary respected.** Section 10 is the binding constraint; tenant business
   tables / foreign keys / storage switches require separate approval.
3. **No P22 wiring.** P17-D-C touches no `seam.py`, no `adapters.py`, and no `backup.check` path;
   `backup.check` stays `source_unknown` / `not_implemented`.
4. **No registry rewrite beyond the read path.** `_build_registry` gains the loader / builder / assembly
   in section 9 only; no other registry behavior changes.
5. **No execution, no pg_dump, no restore, no restore-test runner, no production system contact.**
   P17-D-C implements the read path; the writer / restore-test runner are separate operational tasks.
6. **P22-E3 remains gated** and may begin only after P17-D-C is merged + tested (section 15).

---

## 15. P22-E3 Re-Entry Gate

P22-E3 (not started) is the earliest phase that MAY touch `backup.check` again. P22-E3 may begin a real
`backup.check` **read-only** source-adapter / probe ONLY after ALL of:

1. **P17-D-C is implemented and merged.** The migration, ORM model, and registry read wiring are merged
   to `platform-dev`, so a real durable backup / status source exists and the registry reads it.
2. **The source is tested.** The G1-G18 tests pass (freshness / staleness, success-requires-fresh,
   unknown-never-healthy, null-never-zero, closed-vocabulary redaction, summary / full projection,
   degrade-on-failure, read-only, no-P22-wiring).
3. **CTO acceptance.** The P17-D source is explicitly accepted by the CTO.
4. **Through the seam only.** Any P22-E3 read runs ONLY through the runtime governed action adapter seam
   (P22-E1), behind revised G5 + G1-G4 + G6-G7, fail-closed, before / after / failure-audited, with the
   digest-only idempotency guard. No direct in-process bypass, no side channel, no generic shell / SQL /
   script / subprocess.
5. **Read-only, no restore.** `backup.check` refreshes and READS backup status only; it performs NO
   restore, mutates NOTHING, and enters NO product / payment / billing path.
6. **Summary projection only.** P22-E3 reads only `last_backup_status` and `export_available` (and the
   source status needed to report `known` / `degraded` honestly); never `failure_reason_redacted`, never
   restore-test detail.
7. **Never an execution success.** P22-E3 may at most upgrade the `backup.check` adapter from
   `not_implemented` to a source-binding read-only probe returning an honest `known` / `degraded` result.
   It must NOT set `result_state='executed'` and must NOT emit a real `execution_succeeded`.

In one line: P22-E3 may bind `backup.check` to the PROVEN, MERGED, TESTED, CTO-ACCEPTED P17-D source
behind the seam as a read-only summary probe that never claims execution -- and only after P17-D-C lands.

---

## 16. Relationship to Prior Phases

- **P17-D-A** (merged at `eb5268c`) is the source contract this plan implements. P17-D-B changes no
  P17-D-A contract term; it refines the planning shape into implementation-ready detail (additively).
- **P17 (Registry and Tenant Lifecycle Contract)** freezes the `TenantBackupStatus` target shape, the 24h
  freshness window, the `BACKUP_FAILURE_REASONS` allowlist, and the summary / full visibility split.
  P17-D-B reuses all of them unchanged.
- **P22-E2** returned SOURCE_UNKNOWN and the minimum P17 prerequisite set; P17-D-B specifies how P17-D-C
  satisfies items 1-5 at the schema / model / wiring layer.
- **P22-E0 / P22-E1** fixed the seam and landed the non-executing skeleton. P17-D-B cites them read-only;
  it touches no P22 code.
- **P21-C1 / the P21 ORM-enum lesson** supply the additive public-schema migration precedent and the
  enum-decode discipline this plan reuses.

---

## 17. Docs-Only Statement

P17-D-B ships:

- `docs/ai/PLATFORM_PRODUCT_P17_BACKUP_STATUS_SCHEMA_PLAN.md` -- this plan (schema, enums, mapping,
  freshness, redaction, write-source boundary, registry read plan, migration plan, test plan,
  acceptance criteria, counterexamples, and the P17-D-C / P22-E3 gates).
- `docs/ai/README.md` -- one cumulative-state sentence appended to the P17 paragraph (ASCII-only).
- `ai-ledger/platform/2026-07-02_p17db_backup_status_schema_plan.md` -- the ledger.

There is **no runtime code, no backend, no ORM model file, no model registration, no migration, no alembic
change, no table, no test code, and no dependency change** in P17-D-B. P17-D-B specifies the
implementation-ready schema / model / test plan a future P17-D-C may build; it builds no table, registers
no model, wires no adapter, executes nothing, runs no pg_dump, runs no restore, and reads no production
system. **Unknown is never healthy, null is never zero, success is never stale, and a backup source is
never fabricated healthy. A plan is not a table and a table is not an execution.** P17-D-C is not
started. P22-E3 is not started.
