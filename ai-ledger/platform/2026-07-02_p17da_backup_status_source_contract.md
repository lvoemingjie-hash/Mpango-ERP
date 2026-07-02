# P17-D-A Backup / Status Source Contract

**Phase:** P17-D-A Backup / Status Source Contract (docs-only source contract)
**Date:** 2026-07-02
**Branch:** `codex/platform-p17da-backup-status-source-contract-2026-07-02`
**Base:** `e87323f` (`origin/platform-dev` -- the P22-E1 merge)
**Contract:** `docs/ai/PLATFORM_PRODUCT_P17_BACKUP_STATUS_SOURCE_CONTRACT.md` (this slice)
**Unblocks (contract only):** the P22-E2 `STOP_AND_REPORT_P17_PREREQUISITE` verdict (SOURCE_UNKNOWN)
**Author:** Codex (Claude worker)
**Status:** Complete; docs-only; ready for CTO review

---

## 1. Summary

P17-D-A is a **docs-only** source contract. It does three things and nothing else:

1. Defines **what the backup / status source must be** for a future P22 `backup.check` read:
   recommends a durable, additive, public-schema table / model (Option A) that records backup-job
   and restore-test outcomes, and rejects a live ops-artifact reader (Option B) as the runtime
   source (Option B may serve only as the writer that feeds the table).
2. Fixes **how the source maps onto the existing P17 `TenantBackupStatus` shape** and the
   freshness / honesty / redaction / visibility rules it must obey, plus the additive
   public-schema migration boundary and the read-only registry adapter boundary for the future
   implementation phases.
3. **Gates the successors**: a future P17-D-B (schema / model / test plan), a future P17-D-C
   (registry read wiring), and the P22-E3 re-entry gate, so no source is built, no registry is
   rewired, and no `backup.check` read begins until this contract is CTO-accepted.

P17-D-A performs NO execution, wires NO backup source, reads NO production external system, does
NO pg_dump, does NO restore, and mutates NO tenant / product / payment / billing / registry /
provisioning / backup data. It ships NO runtime code, NO backend, NO ORM model, NO migration, NO
alembic change, NO table, NO test code, NO dependency change, and NO P22 / P16 code change. It
grants no execution power and builds no source.

> **Unknown is never healthy, null is never zero, success is never stale, and a backup source is
> never fabricated healthy. Approval is not execution and a contract is not a source.** P17-D-A
> names the source a future phase must build; it does not build it, and it does not run anything.

## 2. Base / Branch / Commit Chain

- **Base SHA:** `e87323f` (`origin/platform-dev`, the P22-E1 merge -- the runtime governed action
  adapter seam skeleton is on the books).
- **Worktree:** `MPANGO ERP/codex-platform-p17da-backup-status-source-contract-2026-07-02`,
  created from `origin/platform-dev` via `git worktree add -b <branch> <path> origin/platform-dev`,
  then `git branch --unset-upstream`. Upstream is unset, so a bare `git push` cannot fast-forward
  `platform-dev`; the branch is published with the explicit refspec
  `git push -u origin <branch>:<branch>` (the worktree-push gotcha).
- **Commit chain (base..tip):** one commit on top of `e87323f` carrying the contract doc + the
  README cumulative-state line + this ledger. The tip SHA is reported in the chat report, not
  self-referenced here (this ledger is part of that commit); only short SHAs are used.

`platform-dev` was NOT merged and is NOT the push target. Only the isolated P17-D-A branch carries
these changes and is published to its own remote ref.

## 3. Modified / Added Files (exactly the three allowed)

| File | Status | Scope |
|---|---|---|
| `docs/ai/PLATFORM_PRODUCT_P17_BACKUP_STATUS_SOURCE_CONTRACT.md` | New | The contract: goal / non-goals; the P22-E2 relationship (SOURCE_UNKNOWN); data-source options (Option A durable table recommended; Option B ops-artifact reader rejected as source, accepted as writer; Option C noted); the TenantBackupStatus field-by-field mapping; freshness / honesty rules (24h window, restore-test cadence, success-requires-fresh+available, unknown-never-healthy, null-never-zero, stale-never-success, fail-closed); closed-vocabulary redaction; summary-vs-full visibility (P22 reads summary only); the additive public-schema migration boundary; the read-only registry adapter boundary; 18 acceptance criteria; 18 counterexamples (incl. fabricated healthy, stale success, raw-log exposure, restore mistaken for check, product-data mutation, P22 adapter before source); P17-D-B entry gate; P22-E3 re-entry gate; relationship to prior phases; docs-only statement |
| `docs/ai/README.md` | Modified (additive) | One cumulative-state sentence appended to the P17 paragraph (ASCII-only) |
| `ai-ledger/platform/2026-07-02_p17da_backup_status_source_contract.md` | New | This ledger |

No other paths were touched. `git diff --name-only origin/platform-dev..HEAD` returns exactly these
three paths. No `backend/`, no `frontend/`, no `migrations/`, no `alembic/env.py`, no
`scripts/platform_worktree_executor.py` or any other P16 asset, no `product-dev-recovered/`, no
product / payment / billing / order / invoice / customer / inventory / ledger path, no test file, no
`package.json` / lockfile, no CI / `.github` / `.claude` file, and no secrets baseline file.

## 4. Why P17-D-A Exists

P22-E2 (source-discovery gate, base `e87323f`) returned **SOURCE_UNKNOWN**: no queryable,
non-fabricated backup / status source exists, so a real `backup.check` read has nothing to read. Its
five as-built evidence lines (P17 hard-codes `backup_status=None`; no model; no migration; P18
resolves `backup.check` to `unavailable`; the P22-E1 seam slot is `source_unknown` /
`not_implemented`; the P10 data-source map has no backup entry) are all statements about the code at
`e87323f`, which is this contract's base. P22-E2 enumerated the *minimum P17 prerequisite set* a real
source must satisfy and stopped at `STOP_AND_REPORT_P17_PREREQUISITE`, explicitly leaving the source
definition to P17. P17-D-A is that definition -- at the contract layer only.

The only operational backup mechanism today is `ai-ledger/ops/backup_postgres.sh` (a cron-driven
`pg_dump` that writes a dump file and appends to a host-side `backup.log`). P22-E2 established that
it PRODUCES backups but does NOT EXPOSE a status source to the platform runtime: there is no API,
endpoint, table, or model the application reads for `last_backup_at` / `last_backup_status` /
restore-test / `export_available`, and P17 does not parse the log or list the dump directory. It is
therefore a candidate *input* (a writer) a future source could be built on, not a source itself --
which is exactly what section 3 records.

## 5. Recommendation (Option A)

Section 3 recommends a **durable, additive, public-schema table / model** (Option A) as the default
source kind, because the runtime API requires a source that is auditable (append-only rows with a
writer and a timestamp), testable (a test inserts a known outcome row and asserts the rendered
status without touching the host filesystem or running pg_dump), and permissionable (read through
the ORM behind the identity-only guard with a summary / full projection). A bounded live client over
ops artifacts (Option B) is rejected as the runtime source -- it is host / filesystem / log-coupled,
format-fragile, cannot represent the full `TenantBackupStatus` shape (the cron runs no restore
test), and is security-coupled (the script's hardcoded default password, file paths, log content).
Option B may serve as the *writer* that feeds the table; the runtime never reads ops artifacts
directly.

## 6. Mapping + Rules (summary)

- **TenantBackupStatus mapping (section 4):** every field (`last_backup_at`, `last_backup_status`,
  `last_restore_test_at`, `restore_test_status`, `export_available`, `retention_policy`,
  `failure_reason_redacted`, `backup_source_status`, `last_status_check_at`) is derived from the
  latest durable outcome row and routed through `enforce_backup_freshness` +
  `success_requires_fresh_timestamp`. `backup_source_status` is the honest hinge: `available` only
  when a real, fresh outcome backs the status.
- **Freshness / honesty (section 5):** 24h backup window; restore-test cadence; success requires
  fresh + available; unknown never healthy; null never zero; stale never success; fail-closed on
  read failure (degrade to `null + unavailable_reason`, never a 500 / never fabricated).
- **Redaction (section 6):** no raw logs / DSN / host / port / path secrets / dump contents;
  `failure_reason_redacted` is the closed `BACKUP_FAILURE_REASONS` vocabulary, collapsed by
  `redact_failure_reason`, backstopped by the field validator.
- **Visibility (section 7):** support summary = `last_backup_status` + `export_available` only;
  engineering full = all diagnostics; **P22 `backup.check` reads the summary projection only**.

## 7. Validation Gates

| Gate | Result |
|---|---|
| `git diff --check origin/platform-dev..HEAD` | clean (exit 0; no whitespace errors) |
| Changed files | exactly the three allowed paths (section 3) |
| Non-ASCII scan on changed files | 0 non-ASCII bytes across all P17-D-A deliverables |
| detect-secrets (configured baseline) | clean (detect-secrets-hook against the configured baseline on the three changed files) |
| Forbidden path audit | clean (section 9) |
| `npx gitnexus analyze .` | indexed successfully (17.2s); see section 8 |
| `npx gitnexus status` | up-to-date; indexed commit == current commit == branch tip (docs-only adds no code-graph nodes) |
| Worktree clean (post-commit) | tracked tree clean (only gitignored `__pycache__` / `.gitnexus` artifacts, none committed) |

## 8. GitNexus

- `npx gitnexus analyze .` (re-index at the branch tip): repository indexed successfully in ~17-18s
  -- **~8,463-8,481 nodes | 25,855-25,870 edges | ~534-537 clusters | 300 flows**. Flows (300) are
  stable; node / edge / cluster counts wobble slightly across fresh builds and across the pre-commit
  vs post-commit pass (a pre-commit pass at the working tree reported 8,463 / 25,855 / 534 / 300; a
  post-commit pass at the tip reported 8,481 / 25,870 / 537 / 300) -- documented as a band, not a
  point, to avoid amend loops. P17-D-A is docs-only; the code graph is unchanged from the base, but
  the three new tracked docs are indexed as documentation nodes at the tip.
- `npx gitnexus status`: index is **up-to-date** -- indexed commit == current commit == the branch
  tip, NOT the base `e87323f`. P17-D-A is docs-only, so the code graph is unchanged from the base,
  but the index tracks the branch tip. The tip SHA is reported in the chat report, not
  self-referenced here (this ledger is part of the commit).

## 9. Forbidden Path Audit

`git diff --name-only origin/platform-dev..HEAD` returns exactly three paths, all under `docs/ai/`
and `ai-ledger/platform/`:

- `docs/ai/PLATFORM_PRODUCT_P17_BACKUP_STATUS_SOURCE_CONTRACT.md`
- `docs/ai/README.md`
- `ai-ledger/platform/2026-07-02_p17da_backup_status_source_contract.md`

None matches any forbidden prefix or fragment:

- No `backend/`, no `frontend/`, no `migrations/`, no `alembic/env.py`.
- No `scripts/` change -- in particular no `scripts/platform_worktree_executor.py` or any other P16
  asset.
- No `product-dev-recovered/` or any product / business path (no orders, payments, billing, finance,
  inventory, client, customer, invoice, ledger).
- No auth / RBAC / session / tenancy rewrite.
- No `package.json`, no lockfiles, no dependency changes.
- No `.github/`, no `.claude/`, no secrets baseline file, no CI / deploy files.
- No real execution / worker / harness invocation / shell / SQL / script / subprocess.

## 10. Self-Review

- Did P17-D-A build a source? No -- it is docs-only; no table, no model, no migration, no writer,
  no read path.
- Did it weaken a gate? No -- it tightens: it fixes the source-honesty invariants and adds the
  P17-D-B / P17-D-C / P22-E3 gates.
- Did it touch P22 or P16? No -- `seam.py`, `adapters.py`, and all P16 assets are unchanged (cited
  read-only).
- Did it fabricate a backup source? No -- it explicitly records that the source is unwired
  (SOURCE_UNKNOWN) and bars fabrication.
- Did it run pg_dump or a restore? No.
- Is it ASCII-clean and secrets-clean? Yes -- 0 non-ASCII bytes; detect-secrets (configured baseline)
  passed; only short SHAs are used and the baseline is referenced as "the configured baseline".
- Does it start P17-D-B or P22-E3? No -- both are gated behind CTO acceptance (and P22-E3 behind a
  merged + tested P17-D source).

## 11. Risk

**Low.** P17-D-A is docs-only and additive (the README change is a one-sentence append; the other
two files are new). It touches no runtime code, no migration, no tests, no dependencies, no auth /
RBAC / session / tenancy, no P16 code, no P22 code, and no product / payment / tenant business path.
It defines a source contract and gates future work; it grants no execution power and builds no
source.

## 12. Blockers

None.

## 13. Explicit Statements

- **No execution.** P17-D-A performs no execution, wires no source, reads no production external
  system, runs no pg_dump, and runs no restore.
- **No runtime source.** No backup / status source is provisioned, built, wired, or read; no log is
  parsed, no dump directory is listed, no backup API is called.
- **No runtime change.** No `backend/` or `frontend/` file is touched; no adapter, no ORM model, no
  loader is implemented; `_build_registry` is unchanged (`backup_status=None` stands).
- **No P22 / P16 change.** `backend/api/v1/platform/p22/seam.py`, `adapters.py`, and all P16 assets
  are unchanged (cited read-only).
- **No migration / schema / storage change.** None.
- **No product / payment / tenant business mutation.** None.
- **No auth / RBAC / session rewrite.** None.
- **No package / lockfile / dependency change.** None.
- **No tests added or changed.** P17-D-A is docs-only.
- **platform-dev untouched.** `origin/platform-dev` was not merged and not pushed from P17-D-A.
- **P17-D-B not started.** P17-D-A begins no schema / model / test-plan work; P17-D-B may begin only
  after CTO acceptance of this contract, and P17-D-C (the merge that may apply the migration) only
  after P17-D-B.
- **P22-E3 not started.** P17-D-A begins no `backup.check` work; P22-E3 may begin a read-only
  source-adapter / probe only after the P17-D source is implemented, merged, tested, and
  CTO-accepted -- and even then it never claims execution.
