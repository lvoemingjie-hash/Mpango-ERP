# Platform Product P17-D-A -- Backup / Status Source Contract

**Status:** Docs-only source contract (P17-D-A). No runtime code, no backend handler, no ORM model,
no migration, no alembic change, no table, no column, no test code, and no dependency change. No
`backend/`, no `frontend/`, no `migrations/`, no `alembic/env.py`, no `scripts/` (P16 or otherwise),
no `package` / lockfile, no `.github/`, no `.claude/`, no secrets baseline file, and no
`product-dev-recovered/` is touched. No product / payment / billing / order / invoice / customer /
inventory / ledger path is touched. P17-D-A performs NO execution, wires NO backup source, reads
NO production external system, does NO pg_dump, does NO restore, and changes NO P22 seam or adapter
(`backend/api/v1/platform/p22/seam.py` and `adapters.py` are cited read-only as evidence only). It
defines the contract for the backup / status source a future P22 `backup.check` read would need,
recommends a durable platform-schema source, and gates a later P17-D-B (schema / model / test plan)
and P17-D-C (registry read wiring). P17-D-A ships no source and no execution power.
**Phase:** P17-D-A Backup / Status Source Contract
**Date:** 2026-07-02
**Base:** `e87323f` (`origin/platform-dev` -- the P22-E1 merge; the runtime governed action adapter
seam skeleton is on the books: `backend/api/v1/platform/p22/seam.py` + `adapters.py`).
**Unblocks (contract only):** the P22-E2 `STOP_AND_REPORT_P17_PREREQUISITE` verdict
(SOURCE_UNKNOWN -- no real backup / status source exists at `e87323f`). P17-D-A is the *contract*
that removes the prerequisite at the contract layer; it does NOT implement the source and does NOT
remove the P22-E3 execution / read gate.
**Depends on:** P10 (source-status vocabulary, `unknown != healthy`, `null != 0`, redact_metadata
allowlist, identity-only super_admin guard), P13/P14 (`unavailable_reason` / `degraded_reason`),
P17 (Registry and Tenant Lifecycle Contract -- the `TenantBackupStatus` shape, the 24h freshness
window, the failure-reason allowlist, the summary / full visibility split), P18 (the `backup.check`
source resolver), P22-E0 (the runtime governed adapter seam + revised G5), P22-E1 (the non-executing
seam skeleton), P22-E2 (the source-discovery verdict SOURCE_UNKNOWN).
**Author:** Codex (Claude worker)

---

## 1. Goal and Non-Goals

### 1.1 Goal

P22-E2 returned `SOURCE_UNKNOWN`: at base `e87323f` there is no queryable, non-fabricated backup /
status source in the repository, so a real `backup.check` read has nothing to read, and
`backup.check` stays `source_unknown` / `not_implemented`. P22-E2 enumerated the *minimum P17
prerequisite set* a real source must satisfy but deliberately did not define the source itself
(that is a P17 decision, not a P22 one). P17-D-A is that decision -- at the contract layer only.

P17-D-A defines, for a future separately-approved implementation, **what the backup / status source
must be, how it is written and read, how it stays source-honest, and how it maps onto the existing
P17 `TenantBackupStatus` shape** -- so that a future P17-D-B (schema / model / test plan), a future
P17-D-C (registry read wiring), and a future P22-E3 (read-only `backup.check` source-adapter /
probe) each have a single authoritative contract to satisfy. P17-D-A is the entry gate for the
P17-D family and the re-entry reference for P22-E3.

P17-D-A has three jobs and does nothing else:

1. **Define the source contract.** Name the recommended source kind (a durable, platform-schema
   table / model that records backup-job and restore-test outcomes), fix how every
   `TenantBackupStatus` field is populated from it, and fix the freshness, honesty, redaction, and
   visibility rules the source must obey (sections 3-7).
2. **Fix the implementation boundaries.** Record the additive, public-schema-only migration
   boundary for a future P17-D-B (section 8) and the registry-read-only adapter boundary for a
   future P17-D-C (section 9) -- neither of which is started by P17-D-A.
3. **Gate the successors.** Fix the P17-D-B entry gate (section 12) and the P22-E3 re-entry gate
   (section 13), so no source is built, no registry is rewired, and no `backup.check` read begins
   until this contract is CTO-accepted.

P17-D-A defines and gates; it implements nothing. **No real backup / status source is built, no
migration is added, no registry code is changed, and no `backup.check` execution or read is started
by P17-D-A.** The single invariant carried from P10 / P17 / P22 holds absolutely inside this
contract:

> **Unknown is never healthy, null is never zero, success is never stale, and a backup source is
> never fabricated healthy. Approval is not execution and a contract is not a source: P17-D-A names
> the source a future phase must build; it does not build it, and it does not run anything.**

### 1.2 Non-goals

- No runtime code, no backend handler, no ORM model, no repository / loader, no migration, no
  alembic change, no table, no column, no test code, and no dependency change.
- **No real source.** P17-D-A does not provision, build, wire, or read any backup / status source.
  It does not parse `backup.log`, list a dump directory, call any backup API, or contact any
  production external system.
- **No pg_dump, no restore.** P17-D-A runs no backup and no restore and adds no script that does.
- **No P22 change.** `backend/api/v1/platform/p22/seam.py` and `adapters.py` are unchanged (cited
  read-only). No `backup.check` adapter is wired, upgraded, or probed.
- **No P16 change.** No `scripts/platform_worktree_executor.py` or any P16 asset is touched.
- **No registry rewrite.** `_build_registry` (`backend/api/v1/platform/p17/services.py`) is
  unchanged; `backup_status` stays `None` with the reason surfaced (cited read-only).
- **No auth / RBAC / session / tenancy rewrite, no product / payment / billing path.**
- **No merge or push of platform-dev, and no push to any product branch.**

---

## 2. Relationship to P22-E2

P22-E2 (the source-discovery gate, a sibling branch at base `e87323f`) answered the P22-E0 /
P22-E1 question "is a real backup / status source identified?" with the verdict
**SOURCE_UNKNOWN**. Its five as-built evidence lines are all statements about the code at
`e87323f` -- which is this contract's base -- so the verdict holds here unchanged:

1. P17 registry assembly hard-codes the source absent (`backup_status=None` plus the reason "Backup
   system source is not yet wired; backup status is unavailable." in
   `backend/api/v1/platform/p17/services.py`).
2. No persistence layer records backup status (no ORM model, no column, and no alembic migration
   for `backup` / `last_backup` / `restore_test`).
3. The P18 source resolver resolves `backup.check` to `"unavailable"` because
   `registry.backup_status` is always `None`.
4. The P22-E1 seam records the `backup.check` slot as `source_unknown` / `not_implemented`.
5. The P10 data-source map has no backup entry; backup status is entirely a P17 sub-contract, and
   P17-B does not wire it.

P22-E2 then enumerated the **minimum P17 prerequisite set** (a real source of outcomes;
persistence or a live client; registry wiring; freshness + restore-test cadence;
degrade-on-failure error semantics) and stopped at `STOP_AND_REPORT_P17_PREREQUISITE` --
explicitly leaving the source definition to P17. **P17-D-A is the contract that answers that
prerequisite.** The relationship is exact and one-directional:

- P22-E2 said *whether* a source exists (no) and *what* a source must satisfy; it did not say *what
  the source is*. P17-D-A says what the source is (section 3) and how it maps and behaves (sections
  4-7).
- P17-D-A does **not** lift the P22-E3 execution / read gate. P22-E3 may still begin a real
  `backup.check` read only after the P17-D source is *implemented, merged, tested, and
  CTO-accepted* (section 13). P17-D-A is a contract, not an implementation; until P17-D-B and
  P17-D-C land, the P22-E2 verdict stands verbatim and `backup.check` stays `source_unknown` /
  `not_implemented`.

---

## 3. Data Source Options

A future P17-D-B/C must choose a source kind. This contract compares the viable families and
**recommends Option A (a durable platform-schema table / model)** as the default, because the
runtime API requires a source that is auditable, testable, and permissionable.

### 3.1 Option A -- Durable table / model (RECOMMENDED)

A platform-schema, additive table (or small table pair) that records backup-job outcomes and
restore-test outcomes, written by the operational backup process (or a thin recorder invoked after
`pg_dump` succeeds / fails), and read by the P17 registry adapter at request time. Field names only
(planning shape; P17-D-A implements none of it):

```text
platform_backup_outcome {
  outcome_id         : uuid        -- required (PK)
  tenant_id          : uuid        -- nullable (null = platform-wide)
  job_kind           : enum        -- required (backup_job | restore_test_job)
  started_at         : timestamp   -- required (UTC)
  completed_at       : timestamp   -- nullable (null = in_progress)
  status             : enum        -- required (success | partial | failed | in_progress)
  bytes_written      : bigint      -- nullable (size only; never a path)
  failure_reason_code: string      -- nullable (allowlisted code only; never raw)
  source_writer_id   : string      -- nullable (which writer recorded it)
  created_at         : timestamp   -- required (UTC; append-only)
}

platform_backup_policy {           -- optional small config table
  tenant_id       : uuid           -- nullable (null = platform default)
  retention_policy: string         -- nullable (e.g. "7 daily")
  export_enabled  : boolean        -- nullable
}
```

**Why recommended.** The runtime API (P17 registry, P22 `backup.check`) needs a source that is
**auditable** (append-only rows with a writer and a timestamp), **testable** (a test can insert a
known outcome row and assert the rendered status without touching any host filesystem or running
pg_dump), **permissionable** (read through the ORM behind the identity-only guard, with a summary /
full projection), **transactional and restart-safe** (a process crash never loses or fabricates a
status), and **decoupled from ops timing** (the registry reads the last committed row, not a
wall-clock file age). It also honors the P17 degrade-on-failure discipline natively: a read failure
degrades to `null + unavailable_reason`, never a 500 and never a fabricated `success`.

**Cost.** Option A requires an additive, public-schema migration (the P17-D-B / P17-D-C scope) and
a *writer* contract: the operational backup process must record an outcome row after each run. Both
are P17 decisions and are exactly what P17-D-B / P17-D-C are for.

### 3.2 Option B -- Bounded live client / reader over ops artifacts

A read-only client that parses `ai-ledger/ops/backup_postgres.sh` output -- the host-side
`backup.log` line(s) and a directory listing of the dump files -- and synthesizes
`last_backup_at` / `last_backup_status` from log timestamps and file age / size.

**Rejected as the runtime source (acceptable only as a writer feeding Option A).** Option B is the
*only* operational backup mechanism that exists today (`backup_postgres.sh`, a cron-driven
`pg_dump`), and P22-E2 established that it PRODUCES backups but does NOT EXPOSE a status source to
the platform runtime. As a runtime source it fails the contract's hard requirements:

- **Not permissionable / not testable deterministically.** It depends on host filesystem state
  (`/opt/mpango/backups`, file `mtime`, `backup.log` text) the application runtime does not
  normally see and cannot render in a unit test without mocking the host.
- **Format-fragile and log-coupled.** A free-text log line is not a typed, versioned contract; a
  cron format change silently corrupts the status.
- **Cannot represent the full shape.** The cron runs no restore test, so `restore_test_status` is
  always unknown; `export_available` and `retention_policy` are not derivable cleanly from a file
  listing; `unknown` vs `failed` vs `in_progress` cannot be distinguished from a file's absence.
- **Security-coupled.** `backup_postgres.sh` carries a hardcoded default database password (a
  pre-existing ops-script concern, out of P17-D-A scope to fix). A runtime reader over its log or
  paths risks exposing file paths and log content -- exactly what section 6 forbids.
- **Host / container boundary.** The dump directory and log live on the ops host, not in the app
  container; reading them from the runtime crosses a deployment boundary and couples runtime
  availability to host filesystem access.

**Resolution.** Option B is a fine *input* -- the operational backup process (or a recorder it
calls) should translate its own log / dump result into a typed Option A outcome row. The runtime
never reads Option B artifacts directly.

### 3.3 Option C (noted, not available) -- Managed backup-system API / client

If a managed backup service or object-store snapshot API existed, a bounded live client against it
would be a variant of Option B with stronger typing. None exists in the repository today, so it is
not a current option; if one is later introduced it still must feed the Option A durable table so
the runtime gets an auditable, testable, permissionable source.

### 3.4 Recommendation

**Default to Option A (durable platform-schema table / model).** The runtime API requires an
auditable, testable, permissionable source; only a durable table provides all three and honors the
P17 / P22 source-honesty invariants. Option B (ops artifacts) may serve as the writer that feeds
the table; the runtime never reads ops artifacts directly.

---

## 4. TenantBackupStatus Mapping

The source must populate the existing P17 `TenantBackupStatus` shape
(`backend/api/v1/platform/p17/schemas.py`; P17 contract section 4.5) -- no new response shape is
invented. For each field, the durable source (Option A) supplies the value; the registry adapter
routes it through the existing freshness helper and validator before construction.

| `TenantBackupStatus` field | How the durable source populates it | When unavailable |
|---|---|---|
| `last_backup_at` | `completed_at` of the most recent `backup_job` outcome row for the tenant (platform-wide if `tenant_id` is null). UTC ISO-8601. | `null` if no outcome row exists |
| `last_backup_status` | Mapped from the latest `backup_job` row `status` (`success` / `partial` / `failed` / `in_progress`), then routed through `enforce_backup_freshness`: a `success` whose `last_backup_at` is older than the 24h window downgrades to `stale`; a missing timestamp downgrades to `unknown`. | `null` + reason if the source read fails; `unknown` if no row; `stale` if outside the window |
| `last_restore_test_at` | `completed_at` of the most recent `restore_test_job` outcome row | `null` if no restore test was ever recorded |
| `restore_test_status` | `passed` / `failed` from the latest `restore_test_job` row; `stale` if the last test is older than the restore-test cadence window; `unknown` if no row | `null` + reason if the source read fails; `unknown` if none; `stale` if outside cadence |
| `export_available` | Derived: a restorable, non-empty dump exists for the tenant within retention AND the latest backup is not `failed` -> `true`; else `false` | `null` + reason if the source read fails |
| `retention_policy` | From `platform_backup_policy.retention_policy` (e.g. "7 daily"); null if unconfigured | `null` if no policy row |
| `failure_reason_redacted` | The allowlisted `failure_reason_code` of the latest `failed` outcome (must be in `BACKUP_FAILURE_REASONS`); collapsed by `redact_failure_reason` otherwise | `null` if the latest outcome is not a failure |
| `backup_source_status` | `available` ONLY when the source table is readable AND at least one outcome exists; `unavailable` on a read failure; `unknown` when the table is readable but no outcome was ever recorded | always present (required field) |
| `last_status_check_at` | The UTC timestamp at which the adapter performed this read | `null` if never checked |

Registry-level consequence (unchanged from P17 today): when `backup_source_status` is not
`available`, the registry keeps `backup_status` nullable and surfaces the reason in the registry
`unavailable_reason`. `backup_source_status` is the honest hinge: `available` is asserted only when
a real, fresh outcome backs the rendered status.

The adapter MUST route every populated status through `enforce_backup_freshness` and the
`success_requires_fresh_timestamp` model-validator backstop (`schemas.py`). "Success is never stale,
stale is never success" is enforced at two layers, exactly as P17-B already requires.

---

## 5. Freshness and Honesty Rules

The source and its adapter obey the P10 / P17 / P22 source-honesty invariants absolutely:

1. **24h backup freshness window.** `BACKUP_FRESHNESS_WINDOW = 24h` (`schemas.py`). A
   `last_backup_status` of `success` is valid ONLY when `last_backup_at` is within 24h of the read
   time AND `backup_source_status` equals `available`. Outside the window, `success` downgrades to
   `stale` (`enforce_backup_freshness`); it never renders as `success`.
2. **Restore-test cadence.** A separate restore-test cadence window governs
   `restore_test_status`: a `passed` / `failed` older than the cadence reads `stale`. (The exact
   cadence is fixed at P17-D-B; the rule -- stale never reports a fresh verdict -- is fixed here.)
3. **Success requires a fresh timestamp AND an available source.** The
   `success_requires_fresh_timestamp` validator rejects `last_backup_status` of `success` with a
   null `last_backup_at` or with `backup_source_status` not equal to `available`. There is no
   success without proof.
4. **Unknown is never healthy.** An `unknown` source (no outcome ever recorded, or a read that
   cannot confirm) never yields `success` / `active` / `healthy`. It yields `unknown` (or `null`
   plus a reason), never a passing value.
5. **Null is never zero.** An unavailable count, size, or timestamp is `null`, never `0`; an
   unavailable boolean is `null`, never a bare `false` masquerading as a real measurement.
6. **Stale is never success.** A timestamp outside its window downgrades the rendered status; the
   adapter never preserves `success` across a stale timestamp.
7. **Fail closed on read failure.** A source read failure degrades to `null` plus an
   `unavailable_reason` (and `backup_source_status` equal to `unavailable`), never a 500 and never
   a fabricated `success` / `available`. This matches the degrade-on-failure discipline every other
   P17 sub-source already follows.
8. **Read consistency.** The adapter reads the last committed outcome row; it does not synthesize a
   status from partial or in-flight state.

---

## 6. Redaction Policy

The source, its writer, and the adapter NEVER store or expose raw operational detail. The
following are forbidden in any outcome row, registry response, audit payload, or support bundle:

- **Raw backup logs** (the free-text `backup.log` lines, pg_dump stdout / stderr).
- **DSNs, connection strings, host, port, credentials** -- including the hardcoded default password
  in `backup_postgres.sh` (a pre-existing ops concern; it must never flow into the source).
- **File path secrets** -- dump directory paths, file names that reveal host layout, volume mounts.
- **Dump contents** -- the `.dump` / `.sql` bytes are never read, stored, or echoed by the source.

`failure_reason_redacted` is a **closed vocabulary** (the `BACKUP_FAILURE_REASONS` allowlist:
`backup_job_timeout`, `restore_checksum_mismatch`, `backup_source_unreachable`,
`restore_test_failed`, `backup_incomplete`, `unknown`). Any non-allowlisted raw reason is collapsed
to `unknown` by `redact_failure_reason` before it can reach a response; the
`failure_reason_is_allowlisted` field-validator is the hard backstop that rejects a secret-bearing
string at construction. Outcome rows carry an allowlisted `failure_reason_code` only -- never the
raw exception, stack trace, exit-code detail, command line, or log line.

---

## 7. Permission and Visibility

The source inherits the P17 visibility split and adds the projection the runtime enforces:

- **Support / summary projection** (`support_operator`, support bundle): ONLY `last_backup_status`
  and `export_available`. No `failure_reason_redacted`, no restore-test detail, no
  `retention_policy`, no raw outcome rows.
- **Engineering / full projection** (`engineering_operator`, identity-only `super_admin`): the full
  `TenantBackupStatus` including `failure_reason_redacted` and restore-test detail, read-only.

**P22 `backup.check` reads ONLY the safe summary projection.** A future `backup.check`
source-adapter / probe reads `last_backup_status` and `export_available` (and the source-status
needed to report `known` / `degraded` honestly); it never reads `failure_reason_redacted`,
restore-test detail, or any raw outcome row. The projection is enforced by the adapter (it requests
the summary view), not by trusting the caller. `tenant_id` is a scoped identifier only and is never
joinable to tenant business tables.

---

## 8. Migration Boundary (for future P17-D-B)

A future P17-D-B turns this contract into an implementation-ready schema / model / test plan. The
migration boundary it MUST obey (all conjunctive):

1. **Additive only.** New tables / columns / indexes / enum types only. No existing column is
   narrowed, renamed, retyped, or dropped; no existing row is rewritten.
2. **Public / platform schema only.** Tables live in the public platform schema (the same additive,
   public-schema discipline the P21-C1 durable-approval migration established). **No tenant
   business schema, no tenant business tables, and no foreign key into orders / payments / invoices
   / customers / inventory / ledgers.** `tenant_id` is a scoped identifier column, not a joinable
   key.
3. **Separately approved for anything broader.** Any tenant-schema table, any cross-schema foreign
   key, any non-additive change, or any storage switch is a separate explicit CTO approval; the
   default is none of these.
4. **Safe rollback / downgrade.** The down migration drops ONLY the additive tables / enums /
   indexes created by the up migration. Because the tables are additive and hold only
   platform-operational data, downgrade loses no tenant or business data. The downgrade is tested.
5. **Nullable columns, safe defaults.** Every new column is nullable or has a safe default so the up
   migration is instant and online; no backfill that locks tenant tables.
6. **Indexes for recency.** A `(tenant_id, completed_at DESC)` index (and a platform-wide
   `(job_kind, completed_at DESC)` index) backs the "latest outcome" read without a full scan.
7. **Enum types additive.** New enum values are appended; existing values are not removed or
   reordered (Postgres ENUM ordering is load-bearing).
8. **ORM enum decode must match the migration.** Any new `postgresql.ENUM(create_type=False)`
   value list must match the migration exactly so rows decode (the P21 ORM-enum lesson); values are
   not invented at runtime.

P17-D-B creates NO migration files, NO tables, NO ORM registration, and NO runtime code; it is the
plan and the tests only. P17-D-C (the merge that may apply the migration) is separately gated.

---

## 9. Runtime Adapter Boundary (for future P17-D-C)

A future P17-D-C wires the registry READ path to the durable source. The boundary it MUST obey:

1. **Replace `backup_status=None` ONLY after the source exists.** `_build_registry`
   (`backend/api/v1/platform/p17/services.py`) replaces the hard-coded `backup_status=None` with a
   real `TenantBackupStatus` built from the durable source ONLY after P17-D-B/C landed the table and
   a writer is recording outcomes. Until then `backup_status=None` and
   `_BACKUP_UNAVAILABLE_REASON` stand unchanged.
2. **Read-only.** The adapter reads the latest outcome row; it writes nothing to the source and
   mutates no registry / tenant / business record.
3. **No P22 real execution.** P17-D-C touches only the P17 registry read path. It does NOT touch
   `backend/api/v1/platform/p22/seam.py` or `adapters.py`, does NOT wire or probe `backup.check`,
   and does NOT claim any execution. `backup.check` remains `source_unknown` /
   `not_implemented` until P22-E3 (section 13).
4. **Degrade on failure.** A source read failure degrades to `null` plus an `unavailable_reason`
   (`backup_source_status` equal to `unavailable`); never a 500, never a fabricated `success`.
5. **Freshness + validator.** Every populated status routes through `enforce_backup_freshness` and
   the `success_requires_fresh_timestamp` backstop.
6. **Projection + guard.** Full diagnostics behind identity-only `super_admin`; the support subset
   and the P22 summary projection enforced by the adapter.

---

## 10. Acceptance Criteria

P17-D-A is accepted only when ALL hold (a future P17-D-B / P17-D-C is accepted only when it
additionally satisfies sections 8 / 9 and the entry gates in sections 12 / 13):

1. **P17-D-A is docs-only.** No runtime code, backend, ORM model, migration, alembic change, table,
   test code, or dependency change ships in P17-D-A.
2. **The source kind is fixed and recommended.** Section 3 names Option A (durable platform-schema
   table / model) as the recommended default and records why (auditable, testable, permissionable),
   and rejects Option B as the runtime source (acceptable only as a writer).
3. **The TenantBackupStatus mapping is total.** Section 4 maps every `TenantBackupStatus` field
   (`last_backup_at`, `last_backup_status`, `last_restore_test_at`, `restore_test_status`,
   `export_available`, `retention_policy`, `failure_reason_redacted`, `backup_source_status`,
   `last_status_check_at`) to its source derivation and its unavailable fallback.
4. **Freshness rules are fixed.** Section 5 fixes the 24h backup window, the restore-test cadence
   rule, "success requires fresh + available", "unknown is never healthy", "null is never zero",
   "stale is never success", and fail-closed-on-read-failure.
5. **Redaction is closed-vocabulary.** Section 6 forbids raw logs / DSN / host / port / path
   secrets / dump contents and fixes `failure_reason_redacted` to the `BACKUP_FAILURE_REASONS`
   allowlist with `redact_failure_reason` collapse.
6. **Visibility is split.** Section 7 fixes the support-summary vs engineering-full projection and
   fixes that P22 `backup.check` reads only the safe summary.
7. **The migration boundary is additive + public-schema.** Section 8 fixes additive-only, public /
   platform-schema-only, safe rollback, nullable / default columns, recency indexes, and additive
   enums; tenant business tables / foreign keys are forbidden unless separately approved.
8. **The adapter boundary is read-only and source-gated.** Section 9 fixes that the registry
   replaces `backup_status=None` only after the source exists, reads only, degrades on failure,
   routes through freshness, and touches no P22 code.
9. **The P22-E2 relationship is exact.** Section 2 records that P17-D-A answers the P22-E2
   `STOP_AND_REPORT_P17_PREREQUISITE` at the contract layer and does NOT lift the P22-E3 gate.
10. **No real source is built.** P17-D-A provisions, builds, wires, and reads no source; it parses
    no log, lists no dump directory, calls no backup API, and contacts no production system.
11. **No pg_dump / restore.** P17-D-A runs no backup and no restore and adds no script that does.
12. **No P22 / P16 change.** `seam.py`, `adapters.py`, and all P16 assets are unchanged (cited
    read-only).
13. **No registry rewrite.** `_build_registry` is unchanged; `backup_status=None` plus the reason
    stands.
14. **No auth / RBAC / session / tenancy / payment change, no product business path.**
15. **platform-dev untouched.** `origin/platform-dev` is not merged and not pushed from P17-D-A;
    only the isolated branch carries the changes.
16. **P17-D-B not started.** P17-D-A begins no schema / model / test-plan work; P17-D-B may begin
    only after CTO acceptance of this contract (section 12).
17. **P22-E3 not started.** P17-D-A begins no `backup.check` work; P22-E3 may begin only after the
    P17-D source is implemented, merged, tested, and CTO-accepted (section 13).
18. **Counterexamples covered.** Section 11 enumerates the misuse patterns this contract rejects,
    including fabricated healthy, stale success, raw-log exposure, restore mistaken for check,
    product-data mutation, and a P22 adapter wired before the source.

---

## 11. Counterexamples (this contract must reject these)

Each of the following is REJECTED. They are the high-value misuse patterns; the six mandated
families are called out explicitly at the top.

1. **Fabricated healthy status.** A source / adapter that synthesizes a `last_backup_status` of
   `success` or a fresh `last_backup_at` for an unwired / unknown / empty source -- rejected.
   (Section 5; unknown is never healthy.)
2. **Stale success.** A `last_backup_status` of `success` rendered while `last_backup_at` is
   outside the 24h window -- rejected; it must read `stale`. (Section 5; success is never stale.)
3. **Raw-log / path / credential exposure.** A source / adapter / bundle that stores or echoes a
   `backup.log` line, a dump file path, a host / port, a DSN, the hardcoded script password, or
   dump bytes -- rejected. (Section 6.)
4. **Restore mistaken for check.** Treating `backup.check` (a read-only status read) as a restore,
   a restore test, or any state-changing operation; or routing restore through the read-only check
   path -- rejected. (Section 7; Section 9; `backup.check` reads status only.)
5. **Product / tenant business data mutation.** A source / migration / adapter that writes, joins,
   or foreign-keys into orders / payments / invoices / customers / inventory / ledgers, or enters a
   product / payment / billing code path -- rejected. (Section 8; Section 9.)
6. **P22 adapter wired before the source.** A P22-E3 `backup.check` source-adapter / probe that
   begins before the P17-D source is implemented, merged, tested, and CTO-accepted -- rejected by
   the P22-E3 re-entry gate. (Section 13.)
7. **Runtime reads ops artifacts directly (Option B as the source).** A registry adapter that
   parses `backup.log` or lists the dump directory at request time instead of reading the durable
   table -- rejected. (Section 3; Section 9.)
8. **`success` without an available source.** A `last_backup_status` of `success` with
   `backup_source_status` not equal to `available`, or with a null `last_backup_at` -- rejected.
   (Section 5; validator backstop.)
9. **`null` reported as `0`.** An unavailable size / count / timestamp rendered as `0` instead of
   `null` -- rejected. (Section 5; null is never zero.)
10. **`unknown` reported as healthy.** A source with no outcome row rendered as `success` /
    `active` / `healthy` -- rejected. (Section 5.)
11. **Non-additive migration.** A P17-D-B/C migration that narrows, renames, retypes, or drops an
    existing column, or that adds a tenant-schema table or a tenant-business foreign key --
    rejected. (Section 8.)
12. **Unsafe rollback.** A down migration that drops or rewrites non-additive / tenant / business
    data -- rejected. (Section 8.)
13. **Raw failure reason.** A `failure_reason_redacted` carrying the raw exception, exit code,
    command line, stack trace, or log line, or any value outside `BACKUP_FAILURE_REASONS` --
    rejected. (Section 6.)
14. **P22 `backup.check` reads full diagnostics.** A `backup.check` adapter that reads
    `failure_reason_redacted` or restore-test detail instead of the safe summary projection --
    rejected. (Section 7.)
15. **Registry rewired before the source exists.** A P17-D-C that replaces `backup_status=None`
    with a real status before the table and writer land -- rejected. (Section 9.)
16. **P17-D-A ships runtime code.** Any backend, ORM model, migration, adapter, test, or dependency
    change shipped inside P17-D-A itself -- rejected; P17-D-A is docs-only. (Section 1.2.)
17. **Read failure raises / fabricates.** A source read failure that raises a 500 or fabricates a
    passing status instead of degrading to `null` plus an `unavailable_reason` -- rejected.
    (Section 5; Section 9.)
18. **`tenant_id` joinable to business tables.** A source / migration that makes `tenant_id` a
    joinable foreign key into tenant business data -- rejected. (Section 8; Section 9.)

---

## 12. P17-D-B Entry Gate

P17-D-B (not started by P17-D-A) is the earliest phase that MAY convert this contract into an
implementation-ready **schema / model / test plan**. It may begin ONLY after explicit CTO
acceptance of P17-D-A, and ONLY under these constraints:

1. **Plan + tests only.** P17-D-B produces the exact table / column / type / nullability / default
   / index / uniqueness plan for the additive public-schema outcome / policy tables, the ORM model
   plan, the enum plan, the writer contract plan (how `backup_postgres.sh` or a recorder records an
   outcome row), the freshness / restore-test-cadence plan, and the test plan. It creates NO
   migration files, NO tables, NO ORM registration, NO runtime code, and NO storage switch.
2. **No P22 wiring.** P17-D-B touches no `seam.py`, no `adapters.py`, and no `backup.check` path.
3. **No registry rewrite.** `_build_registry` is unchanged; `backup_status=None` stands.
4. **Additive + public-schema boundary respected.** Section 8 is the binding constraint the plan
   must satisfy; tenant business tables / foreign keys require separate approval.
5. **No execution, no pg_dump, no restore, no production system contact.**
6. **P17-D-C (the merge that may apply the migration) is separately gated** and may begin only
   after P17-D-B is accepted.

---

## 13. P22-E3 Re-Entry Gate

P22-E3 (not started) is the earliest phase that MAY touch `backup.check` again. P22-E3 may begin a
real `backup.check` **read-only** source-adapter / probe ONLY after ALL of:

1. **The P17-D source is implemented and merged.** P17-D-B (plan) AND P17-D-C (migration + registry
   read wiring) are merged to `platform-dev`, so a real durable backup / status source exists and
   the registry reads it.
2. **The source is tested.** The P17-D-B/C tests pass: freshness / staleness,
   success-requires-fresh, unknown-never-healthy, null-never-zero, closed-vocabulary redaction, the
   summary / full projection, and degrade-on-failure.
3. **CTO acceptance.** The P17-D source is explicitly accepted by the CTO.
4. **Through the seam only.** Any P22-E3 read runs ONLY through the runtime governed action adapter
   seam (P22-E1), behind revised G5 + G1-G4 + G6-G7, fail-closed, before / after /
   failure-audited, with the digest-only idempotency guard. No direct in-process bypass, no side
   channel, no generic shell / SQL / script / subprocess.
5. **Read-only, no restore.** `backup.check` refreshes and READS backup status only; it performs NO
   restore, mutates NOTHING, and enters NO product / payment / billing path.
6. **Summary projection only.** P22-E3 reads only the safe summary projection; never
   `failure_reason_redacted`, never restore-test detail (Section 7).
7. **Never an execution success.** P22-E3 may at most upgrade the `backup.check` adapter from
   `not_implemented` to a source-binding read-only probe that returns an honest `known` /
   `degraded` result (a degraded source may return a degraded read that changes no state). It must
   NOT set `result_state` to `executed` and must NOT emit a real `execution_succeeded`.

In one line: P22-E3 may bind `backup.check` to the PROVEN, MERGED, TESTED, CTO-ACCEPTED P17-D
source behind the seam as a read-only summary probe that never claims execution -- and only after
P17-D-B and P17-D-C land.

---

## 14. Relationship to Prior Phases

- **P10 / P13 / P14** supply the source-status vocabulary (`available` / `unavailable` /
  `unknown`), the `unknown != healthy` and `null != 0` invariants, the `unavailable_reason` /
  `degraded_reason` convention, the `redact_metadata` allowlist, and the identity-only super_admin
  guard. P17-D-A reuses all of them unchanged.
- **P17 (Registry and Tenant Lifecycle Contract)** freezes the `TenantBackupStatus` target shape
  (fields, enums, the 24h freshness window, the `BACKUP_FAILURE_REASONS` allowlist, the summary /
  full visibility split) and explicitly defers wiring the source. P17-D-A is the deferred source
  contract; it changes no P17 contract term and no P17 code.
- **P18 (Controlled Actions)** resolves `backup.check` to its P17 sub-source; today that resolves
  to `unavailable`. P17-D-A changes no P18 code; it defines the source that will make that
  resolution honest.
- **P22-E0 / P22-E1 / P22-E2** fixed the seam, landed the non-executing skeleton, and returned the
  SOURCE_UNKNOWN discovery. P17-D-A answers the P22-E2 prerequisite at the contract layer and is
  the re-entry reference for P22-E3; it touches no P22 code.

---

## 15. Docs-Only Statement

P17-D-A ships:

- `docs/ai/PLATFORM_PRODUCT_P17_BACKUP_STATUS_SOURCE_CONTRACT.md` -- this contract (goal /
  non-goals, the P22-E2 relationship, the data-source options and recommendation, the
  TenantBackupStatus mapping, freshness / honesty, redaction, visibility, the migration boundary,
  the adapter boundary, acceptance criteria, counterexamples, and the P17-D-B / P22-E3 gates).
- `docs/ai/README.md` -- one cumulative-state sentence appended to the P17 paragraph (ASCII-only).
- `ai-ledger/platform/2026-07-02_p17da_backup_status_source_contract.md` -- the ledger.

There is **no runtime code, no backend, no ORM model, no migration, no alembic change, no table, no
test code, and no dependency change** in P17-D-A. P17-D-A defines the backup / status source
contract and gates a future schema / model plan and a future registry read wiring; it builds no
source, wires no adapter, executes nothing, runs no pg_dump, runs no restore, and reads no
production system. **Unknown is never healthy, null is never zero, success is never stale, and a
backup source is never fabricated healthy. Approval is not execution and a contract is not a
source.** P17-D-B is not started. P22-E3 is not started.
