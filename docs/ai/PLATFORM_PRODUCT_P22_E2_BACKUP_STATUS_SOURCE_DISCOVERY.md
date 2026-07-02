# Platform Product P22-E2 -- Backup / Status Source Discovery Gate

**Status:** Docs-only source-discovery gate (P22-E2). No runtime code, no backend change, no
frontend, no migration, no alembic change, no table, no column, no test code, no dependency change,
no P16 change, no seam / adapter edit, and no product / payment / billing / order / invoice /
customer / inventory / ledger path. P22-E2 performs NO execution, dispatches NO worker, reads NO
production external system, wires NO source, and changes NO `backend/api/v1/platform/p22/seam.py`
or `backend/api/v1/platform/p22/adapters.py` (they are cited as read-only evidence only).
**Phase:** P22-E2 Backup / Status Source Discovery Gate
**Date:** 2026-07-02
**Base:** `e87323f` (`origin/platform-dev` -- the P22-E1 merge; the runtime governed action adapter
seam skeleton is on the books: `backend/api/v1/platform/p22/seam.py` + `adapters.py`).
**Answers:** P22-E0 section 5 / section 6 (the `backup.check` future path + the P17 backup-source
dependency) and gates the P22-E1 entry-gate term "No real `backup.check` until the source is proven".
**Author:** Codex (Claude worker)

---

## 1. Goal and Scope

P22-E0 fixed two preconditions before the first real READ-FIRST action (`backup.check`) may begin:
(a) the runtime governed action adapter seam must be CTO-accepted and realized (DONE: P22-E1 landed
the non-executing seam skeleton, merged at `e87323f`), and (b) the `backup.check` data source must
be explicitly identified before implementation. P22-E2 is the discovery gate for (b): it determines,
with file-level evidence, whether a real, queryable, non-fabricated backup / status source exists in
the repository today, and if not, it records exactly what P17 must add and what the minimum P22-E3
entry gate is.

P22-E2 has two jobs and does nothing else:

1. **Source discovery.** Answer, with as-built evidence at base `e87323f`: does a real backup /
   status source exist? If yes, record its exact file / function / field / state enum / freshness
   rule / error semantics / permission boundary. If no, STOP and keep `backup.check` at
   source_unknown / not_implemented.
2. **Forward gates.** Record (a) what P17 must add for `backup.check` to really read in a future
   E3 / E4, and (b) the minimum P22-E3 entry gate (a source-adapter skeleton or a read-only probe
   only -- never an execution success).

P22-E2 writes no runtime code and wires nothing. **The single invariant, carried from P22-E0 / P22-A
/ P17, holds absolutely: unknown is never healthy, null is never zero, and a `backup.check` adapter
never fabricates a healthy read.**

### 1.1 In scope (docs only)

- The source-discovery verdict with file-level as-built evidence (section 2 / section 3).
- The backup-status contract SHAPE that already exists (so a future source knows its target) and the
  exact absence-of-source evidence (section 4).
- What P17 must add (section 5) and the minimum P22-E3 entry gate (section 6).
- Acceptance criteria (section 7) and explicit statements (section 9).

### 1.2 Non-goals

- No runtime code, no backend change, no seam / adapter edit, no frontend, no test code, no migration,
  no alembic change, no table, no column, no dependency change, no P16 change.
- **No real `backup.check`.** No adapter is wired, no source is read, no production external system
  is contacted, and no execution success is claimed.
- No new shell / subprocess / SQL / script executor.
- No change to `backend/api/v1/platform/p22/seam.py` or `backend/api/v1/platform/p22/adapters.py`
  (cited read-only).
- No merge or push of platform-dev.

---

## 2. Verdict

**SOURCE_UNKNOWN -- no real backup / status source exists. STOP_AND_REPORT_SOURCE_UNKNOWN.**

There is no queryable, non-fabricated backup / status source in the repository at base `e87323f`.
`backup.check` therefore cannot really read anything today; it must remain
`source_unknown` / `not_implemented` in the P22-E1 seam (unchanged). P22-E2 fabricates nothing and
wires nothing. The `backup.check` slot stays an honest non-executing slot.

The backup-status contract SHAPE exists (P17 `TenantBackupStatus`: fields, enums, a 24h freshness
window, a freshness helper, and a validator -- section 4.2), but the SOURCE that would populate it
does not. P17-B explicitly defers wiring it.

---

## 3. Question 1 -- Does a real backup / status source exist?

**No.** Five independent lines of as-built evidence at `e87323f` establish the absence:

1. **P17 registry assembly hard-codes the source as absent.**
   `backend/api/v1/platform/p17/services.py`:
   - `_BACKUP_UNAVAILABLE_REASON = "Backup system source is not yet wired; backup status is
     unavailable."` (services.py:217-219).
   - The registry builder sets `backup_status=None` on every assembled registry
     (`backup_status=None, # no backup source -> null + reason (never success)`, services.py:271)
     and always appends `_BACKUP_UNAVAILABLE_REASON` to the registry `unavailable_reason`
     (services.py:254).
   - An explicit code comment states the deferral: "No backup source exists in P17-B, so the backup
     sub-contract is null at the registry level with the reason surfaced on the registry record."
     (services.py:222-225).

2. **No persistence layer records backup status.** A search of `backend/models` for
   `backup | last_backup | restore_test` returns ZERO matches -- there is no ORM model and no column
   that stores backup status. A search of every `backend/alembic` migration for
   `backup | last_backup | restore_test | backup_status` returns ZERO files -- there is no table or
   column migration for backup status. There is nothing in the database for a future adapter to read.

3. **The platform action source resolver resolves `backup.check` to "no source".**
   `backend/api/v1/platform/p18/services.py` `_action_source_status` maps a backup action to its P17
   sub-source: `backup = registry.backup_status; return backup.backup_source_status if backup is not
   None else "unavailable"` (p18/services.py:174-176). Because `registry.backup_status` is always
   `None`, `_action_source_status("backup.check")` ALWAYS returns `"unavailable"`. The whole platform
   therefore resolves `backup.check` to an absent source before any P22 layer is reached.

4. **The P22-E1 seam already records the slot as source_unknown / not_implemented.**
   `backend/api/v1/platform/p22/adapters.py` `_source_status_for("backup.check")` returns
   `("unknown", _BACKUP_SOURCE_NOT_WIRED)` (adapters.py), and `AdapterDescriptor` for `backup.check`
   carries `source_status="unknown"`, `realizes_execution=False`, `adapter_result="not_implemented"`.
   This is the honest, unchanged state P22-E2 leaves in place.

5. **No backup source is defined in the data-source foundation.** The P10 data source map
   (`docs/ai/PLATFORM_PRODUCT_P10_DATA_SOURCE_MAP.md`) has NO backup entry; backup status is entirely
   a P17 sub-contract, and P17-B does not wire it.

### 3.1 The only operational backup mechanism is NOT a queryable source

The repository contains one operational backup artifact: `ai-ledger/ops/backup_postgres.sh` (with
`ai-ledger/ops/backup_postgres_cron.md`). It is a cron-driven `pg_dump` script: it runs
`docker exec mpango_postgres pg_dump ...`, writes a compressed dump file under a backup directory,
appends a line to a host-side `backup.log`, and retains the last seven days. This mechanism
PRODUCES backups but does NOT EXPOSE a status source to the platform runtime:

- There is no API, no endpoint, no table, and no model the application reads to obtain
  `last_backup_at`, `last_backup_status`, restore-test result, or `export_available`.
- The application (P17) does not parse `backup.log` or list the dump directory; `backup_status` is
  `None` regardless of whether the cron ran.
- It therefore cannot serve a real `backup.check` read; at most it is a candidate INPUT a future
  source could be built on (section 5), not a source itself.

(Operational note, out of P22-E2 scope: `backup_postgres.sh` carries a hardcoded default database
password. That is a pre-existing ops-script concern; P22-E2 does not modify it and surfaces it only
as an observation.)

---

## 4. Question 2 -- The shape that DOES exist (so a future source knows its target)

There is no source, but P17 already freezes the target SHAPE a future source must populate
(`docs/ai/PLATFORM_PRODUCT_P17_REGISTRY_LIFECYCLE_CONTRACT.md` section 4.5;
`backend/api/v1/platform/p17/schemas.py`). Field names only; no values, no secrets:

- **Model:** `TenantBackupStatus` (P17 schemas.py:267). Nullable; `null + unavailable_reason` when
  the backup system is absent.
- **Fields:** `last_backup_at`, `last_backup_status`, `last_restore_test_at`,
  `restore_test_status`, `export_available`, `retention_policy`, `failure_reason_redacted`,
  `backup_source_status`, `last_status_check_at`.
- **State enums:** `LastBackupStatus = success | partial | failed | in_progress | stale | unknown`
  (P17 contract 4.5; schemas.py:245); `RestoreTestStatus = passed | failed | stale | unknown`
  (schemas.py:248).
- **Source-status vocabulary (shared):** `RegistrySourceStatus = available | unavailable | unknown`
  (schemas.py:40). The backup sub-source reads `unavailable` today.
- **Failure reason allowlist:** `BACKUP_FAILURE_REASONS` (schemas.py:251) -- only allowlisted reason
  codes; `failure_reason_redacted` is redacted, never raw.
- **Freshness rule (C4):** `BACKUP_FRESHNESS_WINDOW = 24h` (schemas.py:264). A `last_backup_status`
  of `success` is valid ONLY when `last_backup_at` is within the window AND
  `backup_source_status == "available"`. The helper `enforce_backup_freshness`
  (schemas.py:461) downgrades a stale `success` to `stale`; the validator
  `success_requires_fresh_timestamp` (schemas.py:319) is the hard backstop. "Success is never stale,
  and stale is never success."
- **Permission / visibility boundary (P17 contract section 6):** backup diagnostics are
  `support-summary` / `eng-full` visible (summary exposes only `last_backup_status` +
  `export_available`); `failure_reason_redacted` and restore-test detail are `eng-full` only. A future
  source must respect this visibility split.

This SHAPE is the contract a future backup source must satisfy; it is NOT evidence that a source
exists. The shape is unwired (section 3).

---

## 5. Question 4 -- What P17 must add before `backup.check` can really read (E3 / E4)

`backup.check` may not really execute until P17 (or a CTO-approved sibling) provisions a real,
named, queryable backup / status source. The minimum P17 prerequisite set:

1. **A real source of backup outcomes.** A read function that returns, per tenant (or platform-wide),
   a real `last_backup_at`, `last_backup_status`, restore-test result, `export_available`, and
   `retention_policy` -- sourced from one of: a backup-status persistence table (model + migration),
   a parse of the operational backup log / dump directory, a backup-system API / client, or an
   object-store / snapshot listing. "Unknown is never healthy; null is never zero" must hold inside
   it.
2. **Persistence or a live client.** Because no model and no migration exist today, P17 must add
   either (a) a `TenantBackupStatus`-shaped persistence model + an alembic migration that the
   operational backup process writes, or (b) a live, bounded read client against the real backup
   system. Either is a schema / infrastructure change that is a P17 decision, not a P22 one.
3. **Registry wiring.** `_build_registry` (`backend/api/v1/platform/p17/services.py`) must replace
   `backup_status=None` with a real `TenantBackupStatus` built from the source, with
   `backup_source_status` honest (`available` only when the source is healthy and fresh), and must
   stop appending `_BACKUP_UNAVAILABLE_REASON` when the source is wired.
4. **Freshness + restore-test cadence.** The source must route through
   `enforce_backup_freshness` and the `success_requires_fresh_timestamp` validator (already in P17
   schemas), and must define a restore-test cadence that populates `restore_test_status`.
5. **Error semantics.** A source read failure must degrade to `null + unavailable_reason`
   (never a 500, never a fabricated `success`) -- exactly the P17 degrade-on-failure discipline the
   other sub-sources already follow.

Until items 1-5 land, `backup.check` has nothing real to read. This is the
**STOP_AND_REPORT_P17_PREREQUISITE** condition: P22-E2 does not build the P17 source (out of scope),
and no P22 phase may fabricate one.

---

## 6. Question 5 -- Minimum P22-E3 entry gate

P22-E3 (not started by P22-E2) is the earliest phase that MAY touch `backup.check` again, and ONLY
under these constraints (all conjunctive):

1. **Source proven first.** P22-E3 may begin real `backup.check` work ONLY after the P17 source
   (section 5) is CTO-accepted and wired. If the source is still absent, E3 does nothing real and
   `backup.check` stays `source_unknown` / `not_implemented`.
2. **Source-adapter skeleton or read-only probe ONLY -- never an execution success.** E3 may at most
   (a) upgrade the `backup.check` adapter descriptor in `adapters.py` from `not_implemented` to a
   real source-binding source-adapter skeleton, OR (b) add a read-only probe that reads the proven
   P17 backup source and returns an honest `known | degraded` result (a degraded source may return a
   degraded read that changes no state). It must NOT set `result_state = executed` and must NOT emit
   a real `execution_succeeded`. Real execution success remains a later, separately approved phase.
3. **Through the seam only.** Any E3 read runs ONLY through the runtime governed action adapter seam
   (P22-E1), behind revised G5 + G1-G4 + G6-G7, fail-closed, before / after / failure-audited, with
   the digest-only idempotency guard. No direct in-process bypass, no side channel, and no generic
   shell / SQL / script / subprocess.
4. **Read-only, no restore.** `backup.check` refreshes and READS backup STATUS only. It performs NO
   real restore, mutates NOTHING, and enters NO product / payment / billing path.
5. **Source-honest.** The adapter reports the real source status (`known | unknown | degraded`);
   unknown is never healthy; a degraded read changes no state; null is never zero; success is never
   stale. No fabricated healthy status, ever.

In one line: P22-E3 may bind `backup.check` to a PROVEN P17 source behind the seam as a read-only
source-adapter / probe that never claims execution -- and only after the P17 prerequisite lands.

---

## 7. Acceptance Criteria

P22-E2 is accepted only when ALL hold:

1. **Docs-only.** No runtime code, backend change, seam / adapter edit, frontend, migration, alembic
   change, table, test code, or dependency change ships in P22-E2.
2. **Verdict is SOURCE_UNKNOWN with evidence.** Section 3 records five independent as-built lines of
   absence evidence at `e87323f` (P17 hard-coded None; no model; no migration; P18 resolves
   unavailable; P10 has no backup source).
3. **`backup.check` stays source_unknown / not_implemented.** P22-E2 changes no seam / adapter code;
   the honest slot is preserved and nothing healthy is fabricated.
4. **The existing shape is documented.** Section 4 records the P17 `TenantBackupStatus` shape (fields,
   enums, 24h freshness window, validator, visibility boundary) so a future source knows its target.
5. **P17 prerequisite is enumerated.** Section 5 records the exact P17 additions (real source,
   persistence / client, registry wiring, freshness + cadence, error semantics) gated as a P17
   decision (STOP_AND_REPORT_P17_PREREQUISITE).
6. **P22-E3 entry gate is fixed.** Section 6 fixes the minimum E3 gate (source proven first;
   source-adapter skeleton or read-only probe only; never an execution success; through the seam;
   read-only; source-honest).
7. **No execution.** P22-E2 performs no execution, wires no source, reads no production external
   system, and adds no executor.
8. **No seam / adapter / P16 change.** `seam.py`, `adapters.py`, and all P16 assets are unchanged
   (cited read-only).
9. **platform-dev untouched.** Only the isolated P22-E2 branch carries these docs.

---

## 8. Relationship to Prior Phases

- **P22-E0** (contract): fixed that `backup.check` may not begin until (a) the seam is realized and
  (b) its data source is identified. (a) is DONE (P22-E1 merged). P22-E2 is the (b) discovery: the
  source is NOT identified -- it does not exist -- so `backup.check` still may not begin.
- **P22-E1** (seam skeleton): landed the non-executing seam and the `backup.check` source_unknown /
  not_implemented slot. P22-E2 changes none of it and confirms the slot is correct.
- **P17** (registry / lifecycle): defines the `TenantBackupStatus` shape and explicitly defers wiring
  the backup source (`backup_status=None` + reason). P22-E2 records that deferral as the blocker for
  any real `backup.check`.
- **P18** (controlled actions): models `backup.check` as "Recorded only; not executed" and resolves
  its source to `unavailable`. P22-E2 confirms this is still the as-built resolution.

---

## 9. Explicit Statements

- **No real execution.** P22-E2 performs no execution, wires no source, reads no production external
  system, and claims no execution success.
- **No adapter wiring.** No `backup.check` adapter is wired or realized; the slot stays
  source_unknown / not_implemented.
- **No P16 change.** No `scripts/platform_worktree_executor.py` or any P16 asset is touched.
- **No seam / adapter edit.** `backend/api/v1/platform/p22/seam.py` and
  `backend/api/v1/platform/p22/adapters.py` are unchanged (cited read-only as evidence).
- **No migration / schema / storage change.** None.
- **No frontend.** None.
- **No product / payment / tenant business mutation.** None.
- **No new shell / subprocess / SQL / script executor.** None.
- **platform-dev untouched.** `origin/platform-dev` is not merged and not pushed from P22-E2.
- **P22-E3 not started.** P22-E2 begins no source-adapter or probe work; E3 may begin only after the
  P17 backup source is CTO-accepted and wired, and only as a read-only source-adapter / probe that
  never claims execution.

---

## 10. Docs-Only Statement

P22-E2 ships:

- `docs/ai/PLATFORM_PRODUCT_P22_E2_BACKUP_STATUS_SOURCE_DISCOVERY.md` -- this discovery note (the
  verdict, the five absence-evidence lines, the existing shape, the P17 prerequisite, the P22-E3
  entry gate, acceptance criteria, and explicit statements).
- `ai-ledger/platform/2026-07-02_p22e2_backup_status_source_discovery.md` -- the ledger.

There is **no runtime code, no backend change, no seam / adapter edit, no frontend, no migration, no
alembic change, no table, no test code, and no dependency change** in P22-E2. **The verdict is
SOURCE_UNKNOWN: no real backup / status source exists; `backup.check` stays
source_unknown / not_implemented; nothing healthy is fabricated. P22-E3 is not started.**
