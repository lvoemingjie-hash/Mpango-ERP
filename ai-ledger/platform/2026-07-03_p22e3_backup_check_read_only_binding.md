# P22-E3 Backup / Status Read-Only Source Binding

**Phase:** P22-E3 backup.check read-only source binding
**Date:** 2026-07-03
**Branch:** `codex/platform-p22e3-backup-check-read-only-binding-2026-07-03`
**Base:** `0955495` (`origin/platform-dev` -- includes P17-D-B.1 and the P17-D-C
backup/status source runtime merge)
**Author:** Codex (Claude worker)
**Status:** Complete. R0 = additive read-only source probe. R1 = CTO fix: wired the
probe into a guarded read-only P22 route so it is operator-visible (R0 had no
runtime caller; GitNexus `affected_count` 0 -> 4). R2 = CTO text-consistency fix:
corrected two stale docstrings that still claimed "no HTTP route / wiring out of
scope" after R1 (docstring-only; no runtime logic change). Never executes; ready
for CTO review.

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
execution. R1 (CTO fix) exposes the probe through a READ-ONLY P22 route -- that
route is NOT an execution entry point (it reads status and returns; it does not
execute, dispatch, drain, or mutate).

> **Unknown is never healthy. Null is never zero. Success is never stale.** A
> `backup.check` read-only probe never fabricates a healthy read and never claims
> execution.

---

## 1A. R1 -- CTO fix: wire the probe into a real P22 runtime read path

**CTO finding on R0:** R0 added `source_probe.py` + tests only;
`read_backup_check_source()` had NO runtime caller (no P22 service / route /
adapter / catalog path invoked it), so GitNexus `detect_changes` returned
`affected_count = 0` and `backup.check` remained user-invisible and still fully
`source_unknown` / `not_implemented`. This was a P1 completion gap.

**R1 fix (option (b) of the task's allowed approaches -- a read-only P22 route):**
added `GET /api/v1/platform/p22/backup-check/source` to the existing guarded P22
router (`backend/api/v1/platform/p22/routes.py`). The route:

- is behind the SAME guard as every other P22 endpoint
  (`require_platform_operator_with_p22_audit` -- the P10 identity-only guard with
  a best-effort access-denied audit);
- `await read_backup_check_source(db, tenant_id=tenant_id)` -- the probe is now
  reached from a real runtime entry point (rg proof:
  `backend/api/v1/platform/p22/routes.py:368`);
- returns `BackupCheckSourceRead` (the honest known | unknown | degraded read);
- records a best-effort outcome audit with `executed=False` /
  `execution_allowed=False` (mirrors the other P22 read routes);
- performs NO execution: no backup / restore / dump / shell / SQL / script, no
  worker, no queue, no tenant mutation.

The static `backup.check` execution adapter stays `not_implemented` /
`source_unknown` (G15 preserved); `seam.py`, `adapters.py`, and all P17 code are
unchanged. R1 modifies only `routes.py` (one new import + one new route handler)
and adds 5 route tests; it changes no existing route's behavior.

**Why a route (not a catalog/dry-run field):** the probe is `async` and needs a
DB session; the catalog (`build_catalog`) and dry-run (`evaluate_dry_run`) are
sync and session-less. Threading a session into them would change their
signatures and break the existing P22-B tests. The route naturally carries the
async session (`Depends(get_db)`) and sits under the existing guarded P22 surface.

---

## 1B. R2 -- CTO text-consistency fix (docstring-only, no runtime change)

**CTO finding on R1:** after R1 wired the read-only route, two top-level
docstrings still carried the stale pre-R1 narrative -- "no HTTP route / wiring
out of scope" -- which was now factually wrong. R2 is a documentation-only fix.

**R2 fix (no runtime logic change; the diff is entirely inside triple-quoted
docstrings):**

- `backend/api/v1/platform/p22/source_probe.py` -- the "What this probe is NOT"
  bullet previously said the probe "is NOT a wired HTTP route ... Wiring such a
  route is out of P22-E3 scope." Reworded to: this module is a library-level
  read-only source reader (defines no route itself); P22-E3-R1 EXPOSES it through
  the guarded READ-ONLY `GET /backup-check/source` route; neither the probe nor
  the route is a public EXECUTION entry point; a future real governed EXECUTION
  would still route through the P22-E1 seam.
- `backend/tests/test_platform_p22e3_backup_check_source_probe.py` -- the closing
  docstring line "it adds no HTTP route and no public execution entry point" was
  stale; rewrote it and added an R1 route-coverage bullet to the "Required
  coverage" list.

**Facts held accurate (unchanged by R2):** P22-E3 has a guarded read-only route;
that route is NOT an execution entry point; the static `backup.check` adapter
stays `not_implemented` / `source_unknown` (G15); no execution, no migration, no
P17 logic change. R2 touched NO runtime code -- `routes.py`, the probe function
bodies, the schemas, and the tests' executable code are byte-for-byte unchanged
(`git diff` is docstring-only; 20 insertions / 9 deletions, all inside
docstrings).

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
  probe + tests) -> `dc305ba` (R0 ledger) -> `18338dd` (R1: route wiring + route
  tests, the CTO fix) -> `235576b` (R1 ledger) -> R2 docstring fix -> R2 ledger
  (this update). The final tip SHA is reported in the chat report, not
  self-referenced here (this update is part of the R2 ledger commit).

`platform-dev` is NOT merged and is NOT the push target. Only the isolated P22-E3
branch carries this work and is published to its own remote ref.

---

## 3. Changed Files

| File | Status | Scope |
|---|---|---|
| `backend/api/v1/platform/p22/source_probe.py` | New (R0) | The read-only `backup.check` source probe: `read_backup_check_source(db, tenant_id, now)` reuses the P17-D-C durable read path verbatim and maps it to an honest P22 result; the `BackupCheckSourceRead` model; the P17->P22 mapping. Non-executing. |
| `backend/api/v1/platform/p22/routes.py` | Modified (R1) | Added one import + one read-only route handler `backup_check_source_route` (`GET /backup-check/source`) that awaits the probe and returns `BackupCheckSourceRead` behind the existing P22 guard. No existing route changed. |
| `backend/tests/test_platform_p22e3_backup_check_source_probe.py` | New (R0) + extended (R1) | 28 unit tests: the 23 R0 cases (no-outcome, fresh, stale, failed/partial redacted, read-failure fail-closed, dry-run/request never execute, no-execution AST scan, G15 descriptor-unchanged, read-only no mutations) + 5 R1 route tests (runtime-caller spy, fresh visible as known, no-outcome unknown, read-failure unavailable no-500, guard requires auth). |
| `ai-ledger/platform/2026-07-03_p22e3_backup_check_read_only_binding.md` | New (R0) + updated (R1) | This ledger. |

`git diff --name-only origin/platform-dev..HEAD` returns exactly the four paths
above. The only existing file modified is `routes.py` (one new import + one new
read-only route handler; no existing route's behavior changes). No other
`backend/` file is modified (in particular no `seam.py` / `adapters.py` /
`services.py` / `schemas.py` edit), no `frontend/`, no `migrations/`,
no `alembic/env.py`, no `scripts/platform_worktree_executor.py` or any P16 asset,
no `product-dev-recovered/`, no product / payment / billing / order / invoice /
customer / inventory path, no `package.json` / lockfile, no CI / `.github` /
`.claude` file (the gitnexus-managed `CLAUDE.md` is gitignored / local-only), no
configured secrets baseline file.

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
| Changed files | exactly four paths: `source_probe.py` (new), `routes.py` (modified, R1), the test file (new + R1), this ledger |
| Non-ASCII byte scan on changed source files | 0 non-ASCII bytes across all three source files (Python byte scan) |
| detect-secrets (configured baseline) | clean (exit 0); baseline unmodified; pre-commit detect-secrets passed at every commit |
| Forbidden path audit | clean (section 9) |
| Runtime-caller proof (rg) | `backend/api/v1/platform/p22/routes.py:368` -- `source = await read_backup_check_source(db, tenant_id=tenant_id)` (non-test caller) |
| `npx gitnexus analyze .` | indexed successfully -- ~8,683 nodes / 26,506 edges / ~545 clusters / 300 flows at the R1 tip (band, not a point) |
| `npx gitnexus status` | up-to-date at tip `18338dd` (indexed commit == current commit == R1 code tip) |
| GitNexus `detect_changes` vs `origin/platform-dev` (MCP, `scope=compare`, `base_ref=origin/platform-dev`, `repo=<worktree>`) | **`changed_count=73, affected_count=4, changed_files=4, risk_level=medium`** (R0 was `affected_count=0`). All 4 affected processes are platform-P22-internal (rooted at `Require_platform_operator_with_p22_audit` -> PlatformAuditLog / _http_exc / Get / _is_test_env); 0 product business flow. |
| P22-E3 tests | 28 passed (23 R0 + 5 R1 route) |
| Platform suite (P0-P22) | 900 passed, 37 skipped (DB-dependent integration), 0 failed |

---

## 7. Test Execution

- P22-E3 suite: **28 passed** (23 R0 + 5 R1 route tests). The R1 route tests prove
  a real P22 runtime entry point calls `read_backup_check_source` (a spy test
  asserts the route awaits it with the tenant_id), surface a fresh success as
  `known`, keep a no-outcome read `unknown` (never healthy), degrade a read
  failure to `unavailable` with HTTP 200 (fail-closed, no 500), keep every
  execution flag `False`, and require the platform-operator guard (401/403
  without the auth header).
- Wider platform regression (all `test_platform_*.py` unit files, excluding the
  ephemeral-postgres migration-integration test): **900 passed, 37 skipped
  (DB-dependent integration), 0 failed** in ~49s. Includes the full P22 controlled
  execution suite (which exercises every P22 route -- confirming the `routes.py`
  edit broke no existing endpoint), the P22-E1 seam (whose no-execution AST scans
  now also scan `source_probe.py` AND the modified `routes.py`), and all P17-D-C
  read / model tests (including the G15 invariant).
- The migration-integration test (`test_platform_p17dc_backup_migration.py`) is
  not re-run here (it needs an ephemeral postgres:15 container); P22-E3 touches no
  migration and no P17 ORM model, so it is structurally out of the blast radius.

Tests run via the shared windsurf-mpango `.venv` with `PYTHONPATH=backend` from
the worktree's `backend/` directory (the project's worktree test-env reuse
discipline).

---

## 8. GitNexus

- `npx gitnexus analyze .` at the R1 code tip (`18338dd`): indexed successfully in
  ~20s -- **~8,683 nodes / 26,506 edges / ~545 clusters / 300 flows**. Edges rose
  from 26,440 (R0) to 26,506 -- the new `backup_check_source_route` ->
  `read_backup_check_source` -> P17 `_load_backup_status_map` / `_build_backup_status`
  call edges are now in the graph. Documented as a band, not a point (node /
  cluster counts wobble +/- a few across fresh builds).
- `npx gitnexus status`: re-indexed at the R1 code tip -- indexed commit ==
  current commit == `18338dd`, status up-to-date.
- `detect_changes` (MCP, `scope=compare`, `base_ref=origin/platform-dev`,
  `repo=codex-platform-p22e3-...`): **returned successfully** with
  `changed_count=73, affected_count=4, changed_files=4, risk_level=medium`. The
  4 changed files are exactly the P22-E3 set (`source_probe.py`, `routes.py`, the
  test file, this ledger). The 4 affected processes are all platform-P22-internal,
  rooted at `Require_platform_operator_with_p22_audit` (the guard the new route
  shares) -> `PlatformAuditLog` / `_http_exc` / `Get` / `_is_test_env`; **ZERO
  product / order / payment / invoice / customer / inventory business flow.** This
  inverts the R0 result (`affected_count=0`, the CTO finding) -- the probe is now
  reachable through the guarded P22 route surface. The stop-condition gate
  ("GitNexus shows product business affected processes") does not fire.
- Note on the MCP driver: the first `detect_changes` attempts used wrong parameter
  names (`compare_against` / `base`) and silently degraded to a working-tree-vs-index
  comparison (0 changes); and an earlier session saw the stdio call hang on a fresh
  worktree (the E2 racy behavior). The correct invocation requires `scope=compare`
  + `base_ref` + the `repo` name (the worktree dir name, NOT the path) when
  multiple repos are indexed -- see [[gitnexus-platform-validation-workflow]].

---

## 9. Forbidden Path Audit

The change set is four paths, all under `backend/api/v1/platform/p22/`,
`backend/tests/`, and `ai-ledger/platform/`. None matches any forbidden prefix or
fragment:

- The only existing file modified is `backend/api/v1/platform/p22/routes.py`, and
  only additively (one new import + one new read-only route handler; no existing
  route's behavior changes). No `seam.py` / `adapters.py` / `services.py` /
  `schemas.py` edit.
- No `frontend/`; no `migrations/`; no `alembic/env.py`.
- No `scripts/` change -- in particular no `scripts/platform_worktree_executor.py`
  or any P16 asset.
- No `product-dev-recovered/` or any product / business path.
- No auth / RBAC / session / tenancy rewrite (the route reuses the existing P10
  identity-only guard via `Depends`).
- No `package.json`, no lockfiles, no dependency changes.
- No `.github/`, no `.claude/` (the gitnexus-managed `CLAUDE.md` is gitignored),
  no configured secrets baseline file, no CI / deploy files.
- No real execution / worker / harness invocation / source wiring / shell / SQL /
  script / dump / restore / queue drain.

The new module's imports are also AST-scanned clean: it imports only from
`..p17.schemas` / `..p17.services` (platform siblings), `pydantic`, `datetime`,
and `typing`. No `subprocess` / `p16` / `product` / `order` / `payment` /
`invoice` / `customer` / `inventory` / `ledger` / `billing` import (the P22-E1
forbidden-import scan, which now scans `source_probe.py`, passes).

---

## 10. Self-Review

- Did P22-E3 add execution power? No -- a read-only source probe behind a
  read-only route; every execution flag is False; `result_state` is always
  `blocked`.
- Did it wire a route? Yes (R1) -- a READ-ONLY status route
  (`GET /backup-check/source`) behind the existing P22 guard. Did it add a public
  EXECUTION entry point? No -- the route reads status and returns; it does not
  execute, dispatch, drain, or mutate.
- Did it change the seam, the adapters, or any P17 code? No -- the static
  `backup.check` descriptor stays `not_implemented` / `source_unknown` (G15); the
  seam is unchanged; P17-D-C semantics are untouched (the probe reuses the P17
  read path verbatim). The only existing file edited is `routes.py` (additive:
  one import + one read-only handler).
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

**Low.** P22-E3 adds one new module + one new test file + this ledger, and
additively extends `routes.py` (one import + one read-only handler; no existing
route changed). It adds a READ-ONLY status route but grants no execution power:
every execution flag is pinned False and `result_state` is always `blocked`. It
touches no migration, no schema, no seam / adapter mutation, no P17 code, no P16
code, no frontend, no dependency, and no product / payment / tenant business path.
The blast radius is platform-only (`backend/api/v1/platform/p22/`); GitNexus
`detect_changes` confirms 4 affected processes, all platform-P22-internal, 0
product.

---

## 12. Blockers / Forward Gates

- **P22-E3 is not execution.** The probe + its read-only route bind the source
  read-only; they do not realize the adapter and do not execute. The `backup.check`
  ADAPTER (execution realization) stays `not_implemented` behind a separately
  CTO-approved real-execution phase.
- **The route is read-only.** A future phase that turns this into a governed
  EXECUTION (e.g. a refresh-and-record action) MUST route it through the runtime
  governed action adapter seam (P22-E1) behind the full preflight / audit /
  idempotency gate, and even then the read-only status probe itself is a read,
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
- **No execution-adapter wiring.** The adapter (execution realization) stays
  `not_implemented` / `source_unknown` (G15); the seam is unchanged; no P17-D-C
  semantics change. A READ-ONLY HTTP route is added (R1), but it is NOT a public
  execution entry point -- it reads status and returns.
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
