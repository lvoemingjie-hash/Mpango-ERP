# P17-D-B Backup / Status Source Schema + Model + Test Plan

**Phase:** P17-D-B Backup / Status Source Schema + Model + Test Plan (docs-only / planning-only)
**Date:** 2026-07-02
**Branch:** `codex/platform-p17db-backup-status-schema-plan-2026-07-02`
**Base:** `eb5268c` (`origin/platform-dev` -- the P17-D-A merge)
**Plan:** `docs/ai/PLATFORM_PRODUCT_P17_BACKUP_STATUS_SCHEMA_PLAN.md` (this slice)
**Implements (planning only):** the P17-D-A contract's recommended Option A durable platform-schema
table / model
**Author:** Codex (Claude worker)
**Status:** Complete; docs-only / planning-only; ready for CTO review

---

## 1. Summary

P17-D-B is a **docs-only / planning-only** schema + model + test plan. It does four things and nothing
else:

1. Defines **the exact additive, public-schema tables** a future P17-D-C may build: `platform_backup_outcome`
   (append-only outcome rows) and `platform_backup_policy` (optional per-tenant / platform-default config)
   -- with Postgres types, nullability, defaults, primary keys, a recency index, uniqueness, and CHECK
   constraints that encode the honesty invariants at the DB layer.
2. Fixes **the enum plan**: the two stored enum types (`platform_backup_job_kind`,
   `platform_backup_outcome_status` -- deliberately excluding `stale` / `unknown`, which are read-time
   derivations), the closed-vocabulary `failure_reason_code` (text + CHECK mirroring
   `BACKUP_FAILURE_REASONS`), and the derived `LastBackupStatus` / `RestoreTestStatus` /
   `RegistrySourceStatus` values the adapter computes.
3. Fixes **the mapping, freshness, redaction, write-source boundary, registry read plan, migration plan,
   and test plan**: the field-by-field `TenantBackupStatus` mapping with a tenant-specific-vs-platform-wide
   resolution rule; the 24h backup window plus the restore-test cadence P17-D-B pins (proposed 168h,
   per-policy overridable); closed-vocabulary redaction; the `backup_postgres.sh` writer insert contract;
   the read-only registry read wiring plan for P17-D-C; the additive migration plan; and the G1-G18 test
   plan.
4. **Gates the successors**: a future P17-D-C (migration / ORM model / registry read wiring) and the
   P22-E3 re-entry gate, so no migration is added, no model is registered, no registry is rewired, and no
   `backup.check` read begins until this plan is CTO-accepted.

P17-D-B performs NO execution, wires NO backup source, reads NO production external system, does NO
pg_dump, does NO restore, registers NO ORM model, and mutates NO tenant / product / payment / billing /
registry / provisioning / backup data. It ships NO runtime code, NO backend, NO ORM model file, NO model
registration, NO migration, NO alembic change, NO table, NO test code, NO dependency change, and NO P22 /
P16 code change. It grants no execution power and builds no table.

> **Unknown is never healthy, null is never zero, success is never stale, and a backup source is never
> fabricated healthy. A plan is not a table and a table is not an execution.** P17-D-B specifies the
> schema a future phase may build; it does not build it, register it, or run anything.

## 2. Base / Branch / Commit Chain

- **Base SHA:** `eb5268c` (`origin/platform-dev`, the P17-D-A merge -- the backup / status source contract
  is on the books).
- **Worktree:** `MPANGO ERP/codex-platform-p17db-backup-status-schema-plan-2026-07-02`, created from
  `origin/platform-dev` via `git worktree add -b <branch> <path> origin/platform-dev`, then
  `git branch --unset-upstream`. Upstream is unset, so a bare `git push` cannot fast-forward
  `platform-dev`; the branch is published with the explicit refspec `git push -u origin <branch>:<branch>`
  (the worktree-push gotcha).
- **Commit chain (base..tip):** one commit on top of `eb5268c` carrying the plan doc + the README
  cumulative-state line + this ledger. The tip SHA is reported in the chat report, not self-referenced
  here (this ledger is part of that commit); only short SHAs are used.

`platform-dev` was NOT merged and is NOT the push target. Only the isolated P17-D-B branch carries these
changes and is published to its own remote ref.

## 3. Modified / Added Files (exactly the three allowed)

| File | Status | Scope |
|---|---|---|
| `docs/ai/PLATFORM_PRODUCT_P17_BACKUP_STATUS_SCHEMA_PLAN.md` | New | The plan: goal / non-goals; the P17-D-A + P22-E2 relationship; the exact `platform_backup_outcome` / `platform_backup_policy` schema (types, nullability, defaults, PK, recency index, uniqueness, CHECK constraints); the FK-like scoped-identifier `tenant_id` rule; the stored-vs-derived enum plan; the field-by-field `TenantBackupStatus` mapping with the tenant-specific-vs-platform-wide resolution rule; freshness (24h backup + pinned restore-test cadence); redaction; the `backup_postgres.sh` writer insert contract; the read-only registry read plan; the additive migration plan; the G1-G18 test plan; 22 acceptance criteria; 21 counterexamples (incl. fabricated healthy, stale success, raw-log exposure, restore mistaken for check, product-data mutation, P22 adapter before source); the P17-D-C entry gate; the P22-E3 re-entry gate; relationship to prior phases; docs-only statement |
| `docs/ai/README.md` | Modified (additive) | One cumulative-state sentence appended to the P17 paragraph (ASCII-only) |
| `ai-ledger/platform/2026-07-02_p17db_backup_status_schema_plan.md` | New | This ledger |

No other paths were touched. `git diff --name-only origin/platform-dev..HEAD` returns exactly these three
paths. No `backend/`, no `frontend/`, no `migrations/`, no `alembic/env.py`, no
`scripts/platform_worktree_executor.py` or any other P16 asset, no `product-dev-recovered/`, no product /
payment / billing / order / invoice / customer / inventory / ledger path, no test file, no `package.json`
/ lockfile, no CI / `.github` / `.claude` file, and no secrets baseline file.

## 4. Why P17-D-B Exists

P17-D-A (merged at `eb5268c`) recommended a durable platform-schema table / model (Option A) but gave only
a *planning shape* (field names) and explicitly deferred the exact types / nullability / indexes /
constraints / enum values / restore-test cadence / writer contract / test plan to P17-D-B. P22-E2 had
enumerated the minimum P17 prerequisite set (a real source of outcomes; persistence or a live client;
registry wiring; freshness + restore-test cadence; degrade-on-failure error semantics). P17-D-B is the
implementation-ready plan that resolves every deferred detail so a future P17-D-C has nothing to invent at
build time, while changing no P17-D-A contract term and no P17 / P22 code.

The only operational backup mechanism today is `ai-ledger/ops/backup_postgres.sh` (a cron-driven,
whole-database `pg_dump`). P17-D-B records that it is a candidate *writer* -- platform-wide, `backup_job`
only, `success` / `failed` only -- and that `restore_test_job` outcomes require a not-yet-built
restore-test runner, so `restore_test_status` reads `unknown` until that runner exists. The plan never
reads ops artifacts directly (Option B is rejected as the runtime source).

## 5. Plan Highlights

- **Schema (section 3):** two additive public-schema tables. `platform_backup_outcome` (outcome_id PK;
  tenant_id nullable scoped identifier; job_kind; status; started_at; completed_at; bytes_written;
  failure_reason_code; source_writer_id; created_at) with a `(tenant_id, job_kind, completed_at DESC NULLS
  LAST)` recency index and CHECK constraints encoding in-progress/completed consistency, failure-reason
  scope + allowlist, bytes scope, and success-requires-non-empty-bytes. `platform_backup_policy`
  (policy_id PK; tenant_id; retention_policy; export_enabled; restore_test_cadence_hours; created_at;
  updated_at) with a per-tenant UNIQUE plus a partial unique index for the single platform-default row.
- **Enums (section 4):** stored `platform_backup_job_kind` (backup_job, restore_test_job) and
  `platform_backup_outcome_status` (success, partial, failed, in_progress) -- `stale` / `unknown` are
  derived at read time, never stored. `failure_reason_code` is text + CHECK mirroring
  `BACKUP_FAILURE_REASONS`.
- **Mapping (section 5):** every `TenantBackupStatus` field derived from the latest completed outcome row
  (tenant-specific preferred, else platform-wide) + policy, routed through `enforce_backup_freshness` and
  `success_requires_fresh_timestamp`.
- **Freshness (section 6):** 24h backup window; restore-test cadence PINNED at 168h (per-policy
  overridable); success-requires-fresh+available; unknown-never-healthy; null-never-zero;
  stale-never-success; fail-closed.
- **Writer (section 8):** `backup_postgres.sh` records platform-wide `backup_job` outcomes
  (`success`/`failed`) only; read path is read-only.
- **Registry read (section 9):** P17-D-C adds `_load_backup_status` / `_build_backup_status` mirroring the
  provisioning loader/builder; replaces `backup_status=None` only after the source exists; degrades on
  failure; touches no P22 code.
- **Migration (section 10):** one additive public-schema revision; pgcrypto prerequisite; ORM enum value
  lists match exactly; safe rollback; dry-run / pre / post checks.
- **Tests (section 11):** G1-G18 covering fresh success, stale downgrade, unknown-never-healthy,
  null-never-zero, redaction, summary/full visibility, read-failure degrade, no-P22-wiring, and more.

## 6. Validation Gates

| Gate | Result |
|---|---|
| `git diff --check origin/platform-dev..HEAD` | clean (exit 0; no whitespace errors) |
| Changed files | exactly the three allowed paths (section 3) |
| Non-ASCII scan on changed files | 0 non-ASCII bytes across all P17-D-B deliverables |
| detect-secrets (configured baseline) | clean (detect-secrets-hook against the configured baseline on the three changed files) |
| Forbidden path audit | clean (section 8) |
| `npx gitnexus analyze .` | indexed successfully; see section 7 |
| `npx gitnexus status` | up-to-date; indexed commit == current commit == branch tip (docs-only adds no code-graph nodes) |
| Worktree clean (post-commit) | tracked tree clean (only gitignored `__pycache__` / `.gitnexus` artifacts, none committed) |

## 7. GitNexus

- `npx gitnexus analyze .` (re-index at the branch tip): repository indexed successfully -- **~8,463-8,492
  nodes | 25,855-25,870 edges | ~534-548 clusters | 300 flows**. Flows (300) are stable; node / edge /
  cluster counts wobble slightly across fresh builds (the count-variance convention) -- documented as a
  band, not a point, to avoid amend loops. P17-D-B is docs-only; the code graph is unchanged from the
  base, but the three new tracked docs are indexed as documentation nodes at the tip.
- `npx gitnexus status`: index is **up-to-date** -- indexed commit == current commit == the branch tip,
  NOT the base `eb5268c`. P17-D-B is docs-only, so the code graph is unchanged from the base, but the
  index tracks the branch tip. The tip SHA is reported in the chat report, not self-referenced here (this
  ledger is part of the commit).

## 8. Forbidden Path Audit

`git diff --name-only origin/platform-dev..HEAD` returns exactly three paths, all under `docs/ai/` and
`ai-ledger/platform/`:

- `docs/ai/PLATFORM_PRODUCT_P17_BACKUP_STATUS_SCHEMA_PLAN.md`
- `docs/ai/README.md`
- `ai-ledger/platform/2026-07-02_p17db_backup_status_schema_plan.md`

None matches any forbidden prefix or fragment:

- No `backend/`, no `frontend/`, no `migrations/`, no `alembic/env.py`.
- No `scripts/` change -- in particular no `scripts/platform_worktree_executor.py` or any other P16 asset.
- No `product-dev-recovered/` or any product / business path (no orders, payments, billing, finance,
  inventory, client, customer, invoice, ledger).
- No auth / RBAC / session / tenancy rewrite.
- No `package.json`, no lockfiles, no dependency changes.
- No `.github/`, no `.claude/`, no secrets baseline file, no CI / deploy files.
- No real execution / worker / harness invocation / shell / SQL / script / subprocess.

## 9. Self-Review

- Did P17-D-B build a table / model / migration? No -- it is plan-only; no table, no model file, no model
  registration, no migration, no writer, no read path.
- Did it weaken a gate? No -- it tightens: it pins the restore-test cadence, separates stored from
  derived status, and adds the P17-D-C / P22-E3 gates.
- Did it touch P22 or P16? No -- `seam.py`, `adapters.py`, and all P16 assets are unchanged (cited
  read-only).
- Did it fabricate a backup source? No -- it records that the source is still unwired (P22-E2 verdict
  stands until P17-D-C) and bars fabrication.
- Did it run pg_dump or a restore? No.
- Is it ASCII-clean and secrets-clean? Yes -- 0 non-ASCII bytes; detect-secrets (configured baseline)
  passed; only short SHAs are used and the baseline is referenced as "the configured baseline".
- Does it start P17-D-C or P22-E3? No -- both are gated behind CTO acceptance (and P22-E3 behind a merged
  + tested P17-D-C).

## 10. Risk

**Low.** P17-D-B is docs-only / planning-only and additive (the README change is a one-sentence append;
the other two files are new). It touches no runtime code, no migration, no model file, no model
registration, no tests, no dependencies, no auth / RBAC / session / tenancy, no P16 code, no P22 code, and
no product / payment / tenant business path. It specifies a schema / model / test plan and gates future
work; it grants no execution power and builds no table.

## 11. Blockers

None.

## 12. Explicit Statements

- **No execution.** P17-D-B performs no execution, wires no source, reads no production external system,
  runs no pg_dump, runs no restore, and runs no restore test.
- **No runtime source.** No backup / status source is provisioned, built, wired, registered, or read; no
  log is parsed, no dump directory is listed, no backup API is called.
- **No runtime change.** No `backend/` or `frontend/` file is touched; no adapter, no ORM model FILE, no
  model registration, no loader is implemented; `_build_registry` is unchanged (`backup_status=None`
  stands).
- **No migration / model.** No alembic revision, no ORM model file, no model registration, no table.
- **No P22 / P16 change.** `backend/api/v1/platform/p22/seam.py`, `adapters.py`, and all P16 assets are
  unchanged (cited read-only).
- **No product / payment / tenant business mutation.** None.
- **No auth / RBAC / session rewrite.** None.
- **No package / lockfile / dependency change.** None.
- **No tests added or changed.** P17-D-B is plan-only (the G1-G18 gates are specified, not authored).
- **platform-dev untouched.** `origin/platform-dev` was not merged and not pushed from P17-D-B.
- **P17-D-C not started.** P17-D-B begins no migration / model / registry-wiring work; P17-D-C may begin
  only after CTO acceptance of this plan.
- **P22-E3 not started.** P17-D-B begins no `backup.check` work; P22-E3 may begin a read-only
  source-adapter / probe only after P17-D-C is implemented, merged, tested, and CTO-accepted -- and even
  then it never claims execution.
