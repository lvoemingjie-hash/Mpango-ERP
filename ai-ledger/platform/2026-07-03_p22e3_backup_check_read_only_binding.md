# P22-E3 Backup / Status Read-Only Source Binding

**Phase:** P22-E3 backup.check read-only source binding
**Date:** 2026-07-03
**Branch:** `codex/platform-p22e3-backup-check-read-only-binding-2026-07-03`
**Base:** `0955495` (`origin/platform-dev` -- includes P17-D-B.1 and the P17-D-C
backup/status source runtime merge)
**Author:** Codex (Claude worker)
**Status:** Complete; additive read-only source binding; never executes; ready for CTO review

---

## 1. Summary

P22-E3 binds `backup.check` to the now-PROVEN, MERGED, TESTED P17-D-C backup /
status source as a READ-ONLY governed adapter result. It is the realization of
the P22-E2 entry gate (option (b)): "a read-only probe that reads the proven P17
backup source and returns an honest `known | degraded` result ... It must NOT set
`result_state = executed` and must NOT emit a real `execution_succeeded`."

P22-E2 (base `e87323f`) returned SOURCE_UNKNOWN: no real source existed, so
`backup.check` stayed `source_unknown` / `not_implemented` and E3 was explicitly
not started. P17-D-C landed that source on `origin/platform-dev` (`0955495`):
migration `021_platform_backup_status_source`, the read ORM models, and the
durable registry read path. E3 is therefore unblocked and binds `backup.check`
to that proven source -- but ONLY as a read-only probe.

The binding is **additive**: one new module
(`backend/api/v1/platform/p22/source_probe.py`) plus its test file. No existing
file is modified, so:

- the static `backup.check` adapter descriptor in `adapters.py` stays
  `not_implemented` / `source_unknown` (the P17-D-C G15 invariant,
  `test_p22_backup_check_still_not_implemented`, still passes);
- the runtime governed action adapter seam (`seam.py`) is unchanged;
- no P17-D-C semantics change (the probe reuses the P17 read path verbatim).

The probe NEVER executes. It performs no backup, no restore, no dump, no shell /
child process / SQL script, no queue drain, no harness job, and no tenant
mutation. `realizes_execution` / `executed` / `execution_started` /
`execution_allowed` are ALWAYS `False` and `result_state` is ALWAYS `blocked`.
Approval is not execution; a read is not execution; a source binding is not
execution. It adds no HTTP route and no public execution entry point.

> **Unknown is never healthy. Null is never zero. Success is never stale.** A
> `backup.check` read-only probe never fabricates a healthy read and never claims
> execution.

---

## 2. Base / Branch / Commit Chain

- **Base SHA:** `0955495` (`origin/platform-dev`; the P17-D-C merge).
- **Worktree:** `MPANGO ERP/codex-platform-p22e3-backup-check-read-only-binding-2026-07-03`,
  created from `origin/platform-dev` via
  `git worktree add --no-track -b <branch> <path> origin/platform-dev`. Upstream is
  unset, so a bare `git push` cannot fast-forward `platform-dev`; the branch is
  published with the explicit refspec `git push -u origin <branch>:<branch>` (the
  worktree-push gotcha).
- **Commit chain (base..tip):** `0955495` (base) -> `8668493` (R0: the source
  probe + tests) -> R1 (this ledger). The R1 tip SHA is reported in the chat
  report, not self-referenced here (this ledger is part of the R1 commit).

`platform-dev` is NOT merged and is NOT the push target. Only the isolated P22-E3
branch carries this work and is published to its own remote ref.

---

## 3. Added Files (exactly the three allowed)

| File | Status | Scope |
|---|---|---|
| `backend/api/v1/platform/p22/source_probe.py` | New | The read-only `backup.check` source probe: `read_backup_check_source(db, tenant_id, now)` reuses the P17-D-C durable read path verbatim and maps it to an honest P22 result; the `BackupCheckSourceRead` model; the P17->P22 mapping. Non-executing. |
| `backend/tests/test_platform_p22e3_backup_check_source_probe.py` | New | 23 unit tests covering every required case (no-outcome, fresh, stale, failed/partial redacted, read-failure fail-closed, dry-run/request never execute, no-execution AST scan, G15 descriptor-unchanged, read-only no mutations). |
| `ai-ledger/platform/2026-07-03_p22e3_backup_check_read_only_binding.md` | New | This ledger. |

`git diff --name-only origin/platform-dev..HEAD` returns exactly the two source
paths above (R0) plus this ledger (R1). No other path is touched. No existing
`backend/` file is modified (in particular no `seam.py` / `adapters.py` /
`services.py` / `routes.py` / `schemas.py` edit), no `frontend/`, no `migrations/`,
no `alembic/env.py`, no `scripts/platform_worktree_executor.py` or any P16 asset,
no `product-dev-recovered/`, no product / payment / billing / order / invoice /
customer / inventory path, no `package.json` / lockfile, no CI / `.github` /
`.claude` file, no configured secrets baseline file.

---

## 4. The Binding -- read-only probe (E2 entry-gate option (b))

E2's section-6 entry gate allowed E3 to EITHER (a) upgrade the `backup.check`
adapter descriptor from `not_implemented`, OR (b) add a read-only probe. E3 chose
**(b)**, and is forced to: the P17-D-C G15 invariant
(`test_p22_backup_check_still_not_implemented`) requires the static descriptor to
stay `not_implemented` / `source_unknown`, and the task requires that test to keep
passing. Modifying the descriptor (option (a)) would break G15 and change P17-D-C
semantics. The additive probe (option (b)) keeps G15 green and changes nothing in
P17 or the seam.

The probe `read_backup_check_source(db, tenant_id=None, now=None)` reuses the
P17-D-C durable read path VERBATIM:

- `from ..p17.services import _build_backup_status, _load_backup_status_map` --
  the proven, merged, tested readers. No new query, no new source, no new table.
- The read is read-only (a SELECT of completed outcome rows + policy); mutations
  are writer-only (the P17-D-C G16 read-only invariant). The probe issues no
  `add` / `commit` / `flush` / `delete` on the session (asserted in tests).
- `tenant_id` scopes the read to a tenant with the P17 platform-wide fallback;
  `None` reads the platform-wide outcome via the loader's own platform-fallback
  resolution (a nil-UUID sentinel through the same loader -- no duplicated logic).

### 4.1 P17 -> P22 honest mapping

The P17 `TenantBackupStatus` (or its absence) is mapped to the P22 vocabulary
(`known | unknown | degraded`) plus a one-line honest summary:

| P17 outcome | `source_summary` | `source_status` |
|---|---|---|
| read failure (loader returns None / raises) | `unavailable` | `unknown` (fail-closed) |
| no outcome (source `unknown`, status None) | `unknown` | `unknown` |
| available + fresh `success` | `fresh_success` | `known` |
| available + `stale` | `stale` | `degraded` |
| available + `failed` | `failed` | `degraded` (+ allowlisted reason) |
| available + `partial` | `partial` | `degraded` (+ allowlisted reason) |
| available + `in_progress` | `in_progress` | `degraded` |
| available but no completed backup verdict | `unknown` | `degraded` |

Only a fresh success reads `known` (healthy). Everything else is `degraded` or
`unknown`. `unknown` is never healthy; `null` is never zero; `success` is never
`stale`. `failure_reason_redacted` is the closed `BACKUP_FAILURE_REASONS`
vocabulary only -- carried verbatim from P17 (which already collapses the raw
reason via `redact_failure_reason`) and re-asserted against the allowlist here; the
raw exception / log / command line never appears.

### 4.2 The result never executes

`BackupCheckSourceRead` carries `realizes_execution=False`, `executed=False`,
`execution_started=False`, `execution_allowed=False`, `result_state="blocked"`,
`read_only=True`, `adapter_result="not_implemented"`,
`binding="read_only_source_probe"`. The adapter (execution realization) is still
`not_implemented`; this probe is a read-only source read, which is not execution.

---

## 5. Required-Test Coverage

All required cases are covered in
`test_platform_p22e3_backup_check_source_probe.py` (23 tests):

| Required case | Test |
|---|---|
| no outcome -> honest unknown, never healthy | `TestSourceMapping.test_no_outcome_is_unknown_never_healthy` |
| fresh success -> readable summary, still non-executing | `test_fresh_success_is_known_readable_summary` |
| stale success -> stale, never success | `test_stale_success_is_stale_never_success` |
| failed/partial -> redacted allowlisted reason only | `test_failed_carries_allowlisted_reason_only` / `test_partial_carries_allowlisted_reason_only` / `test_raw_failure_reason_is_collapsed_to_unknown` |
| source read failure -> unavailable / fail-closed, no 500 | `TestFailClosed.test_read_exception_returns_unavailable_no_500` / `test_loader_returns_none_is_unavailable` |
| request / dry-run never sets execution flags true | `TestDryRunAndRequestNeverExecute.*` |
| no shell / subprocess / dump / execution primitives | `TestNoExecutionPrimitives.*` (AST + text scan) |
| P17-D-C read tests still pass | `test_platform_p17dc_backup_registry_read.py` (incl. G15) -- run, green |
| P22 existing suite still passes | `test_platform_p22_controlled_execution.py` + `..._p22e1_...` -- run, green |

Bonus coverage: the G15 invariant is mirrored
(`TestStaticDescriptorUnchanged`) to document that E3 is additive; the read-only
no-mutation invariant (`TestReadOnly.test_probe_performs_no_session_mutations`);
and a platform-wide read via the loader's own fallback.

---

## 6. Validation Gates

| Gate | Result |
|---|---|
| `git diff --check origin/platform-dev..HEAD` | clean (exit 0; no whitespace errors) |
| Changed files | exactly the two source paths (R0) + this ledger (R1) |
| Non-ASCII byte scan on changed source files | 0 non-ASCII bytes across both files (Python byte scan) |
| detect-secrets (configured baseline) | clean (exit 0); baseline unmodified; pre-commit detect-secrets also passed at R0 commit |
| Forbidden path audit | clean (section 9) |
| `npx gitnexus analyze .` | indexed successfully in ~21s -- ~8,649 nodes / 26,440 edges / ~541 clusters / 300 flows (band, not a point) |
| `npx gitnexus status` | up-to-date at tip `8668493` (indexed commit == current commit == R0 tip) |
| GitNexus `detect_changes` vs `origin/platform-dev` | the MCP stdio call hung on this fresh worktree (the racy behavior E2 also hit). Authoritative fallback: `git diff --name-only origin/platform-dev..HEAD` returns exactly two platform-internal files (a `p22/` module + a `tests/` file) and ZERO product files -> 0 product business flow by construction. |
| P22-E3 tests | 23 passed |
| Platform suite (P0-P22) | 895 passed, 37 skipped (DB-dependent integration), 0 failed |

---

## 7. Test Execution

- P22-E3 new suite: **23 passed**.
- Wider platform regression (all `test_platform_*.py` unit files, excluding the
  ephemeral-postgres migration-integration test): **895 passed, 37 skipped
  (DB-dependent integration), 0 failed** in ~54s. Includes the full P22 controlled
  execution suite, the P22-E1 seam (whose no-execution AST scans now also scan
  `source_probe.py`), and all P17-D-C read / model tests (including the G15
  invariant).
- The migration-integration test (`test_platform_p17dc_backup_migration.py`) is
  not re-run here (it needs an ephemeral postgres:15 container); P22-E3 touches no
  migration and no P17 ORM model, so it is structurally out of the blast radius.

Tests run via the shared windsurf-mpango `.venv` with `PYTHONPATH=backend` from
the worktree's `backend/` directory (the project's worktree test-env reuse
discipline).

---

## 8. GitNexus

- `npx gitnexus analyze .` at the R0 tip: indexed successfully in ~21s -- **~8,649
  nodes / 26,440 edges / ~541 clusters / 300 flows**. Edges and flows are stable
  vs the `0955495` base; the node-count change is only the new module's + the new
  test's graph nodes. Documented as a band, not a point (node / cluster counts
  wobble +/- a few across fresh builds).
- `npx gitnexus status`: re-indexed at the tip after commit -- indexed commit ==
  current commit == `8668493`, status up-to-date.
- `detect_changes` (MCP compare vs `origin/platform-dev`): the GitNexus MCP
  `tools/call` did not return across attempts on this fresh worktree (initialize
  answers, then the call hangs -- the intermittent racy behavior of the MCP
  driver, identical to the P22-E2 experience). The authoritative proof is the
  sanctioned fallback: `git diff --name-only origin/platform-dev..HEAD` returns
  exactly two platform-internal files (`backend/api/v1/platform/p22/source_probe.py`
  + `backend/tests/test_platform_p22e3_backup_check_source_probe.py`) and ZERO
  product files (no product / order / payment / invoice / customer / inventory
  path) -> platform-only blast radius -> 0 product business flow by construction.
  The stop-condition gate ("GitNexus shows product business affected processes")
  does not fire: no product business flow is touched.

---

## 9. Forbidden Path Audit

The change set is three paths, all under `backend/api/v1/platform/p22/`,
`backend/tests/`, and `ai-ledger/platform/`. None matches any forbidden prefix or
fragment:

- No existing `backend/` file modified (no `seam.py` / `adapters.py` /
  `services.py` / `routes.py` / `schemas.py` edit) -- additive only.
- No `frontend/`; no `migrations/`; no `alembic/env.py`.
- No `scripts/` change -- in particular no `scripts/platform_worktree_executor.py`
  or any P16 asset.
- No `product-dev-recovered/` or any product / business path.
- No auth / RBAC / session / tenancy rewrite.
- No `package.json`, no lockfiles, no dependency changes.
- No `.github/`, no `.claude/`, no configured secrets baseline file, no CI / deploy files.
- No real execution / worker / harness invocation / source wiring / shell / SQL /
  script / dump / restore / queue drain.

The new module's imports are also AST-scanned clean: it imports only from
`..p17.schemas` / `..p17.services` (platform siblings), `pydantic`, `datetime`,
and `typing`. No `subprocess` / `p16` / `product` / `order` / `payment` /
`invoice` / `customer` / `inventory` / `ledger` / `billing` import (the P22-E1
forbidden-import scan, which now scans `source_probe.py`, passes).

---

## 10. Self-Review

- Did P22-E3 add execution power? No -- a read-only source probe; every execution
  flag is False; `result_state` is always `blocked`.
- Did it wire a route or a public execution entry point? No -- it is a
  library-level source-binding skeleton, import-tested only.
- Did it change the seam, the adapters, or any P17 code? No -- purely additive;
  the static `backup.check` descriptor stays `not_implemented` / `source_unknown`
  (G15); the seam is unchanged; P17-D-C semantics are untouched (the probe reuses
  the P17 read path verbatim).
- Did it fabricate a healthy source? No -- only a fresh success reads `known`;
  stale / failed / partial / in_progress read `degraded`; no outcome and read
  failure read `unknown` (fail-closed).
- Did it touch P16, migration, frontend, or a product path? No.
- Is it ASCII-clean and secrets-clean? Yes -- 0 non-ASCII bytes; detect-secrets
  (configured baseline) passed (R0 pre-commit and explicit hook); only short SHAs
  are used and the baseline is referenced as "the configured baseline".
- Does it claim execution success? No -- `result_state` is `blocked`, never
  `executed`; no real `execution_succeeded`.

---

## 11. Risk

**Low.** P22-E3 is additive (one new module + one new test file + this ledger; no
existing file modified). It touches no runtime path that existed before (the probe
is import-tested only and wired into no route), no migration, no schema, no seam /
adapter mutation, no P17 code, no P16 code, no frontend, no dependency, and no
product / payment / tenant business path. It grants no execution power: every
execution flag is pinned False and `result_state` is always `blocked`. The blast
radius is platform-only (`backend/api/v1/platform/p22/`).

---

## 12. Blockers / Forward Gates

- **P22-E3 is not execution.** The probe binds the source read-only; it does not
  realize the adapter and does not execute. The `backup.check` ADAPTER (execution
  realization) stays `not_implemented` behind a separately CTO-approved
  real-execution phase.
- **No route is wired.** A future phase that exposes this read through an HTTP
  route MUST route it through the runtime governed action adapter seam (P22-E1)
  behind the full preflight / audit / idempotency gate, and even then it is a read,
  never an execution.
- **Real backup execution / restore** remains excluded from v0 forever
  (`backup.restore_test_request` is the only write-request in the allowlist, and
  it is itself non-executing in P22-B).

---

## 13. Explicit Statements

- **No real execution.** P22-E3 performs no execution, dispatches no worker,
  drains no queue, invokes no P16 harness, runs no shell / SQL / script / external
  process, performs no backup / restore / dump, and claims no execution success.
- **Read-only.** The probe reuses the P17-D-C durable read path verbatim; it issues
  no mutation on the session and reads no tenant business record.
- **Additive only.** No existing file is modified; the static `backup.check`
  descriptor stays `not_implemented` / `source_unknown` (G15); the seam is
  unchanged; no P17-D-C semantics change.
- **No adapter wiring / no route.** The adapter (execution realization) stays
  `not_implemented`; no HTTP route or public execution entry point is added.
- **No P16 change.** No `scripts/platform_worktree_executor.py` or any P16 code /
  contract / asset is touched.
- **No migration / schema / storage change.** None (P22-E3 adds no migration and
  reuses migration 021's tables read-only).
- **No frontend.** None.
- **No product / payment / tenant business mutation.** None.
- **No new shell / subprocess / SQL / script / dump / restore executor.** None.
- **Source-honest.** `unknown` is never healthy; `null` is never zero; `success`
  is never `stale`; no fabricated healthy status, ever.
- **platform-dev untouched.** `origin/platform-dev` is not merged and not pushed
  from P22-E3; only the isolated P22-E3 branch is published.
