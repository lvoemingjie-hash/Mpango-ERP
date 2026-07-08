# P22-C Controlled Execution v0 -- Non-Executing Operator Console

**Phase:** P22-C Controlled Execution v0 (non-executing frontend operator console)
**Date:** 2026-07-02
**Branch:** `codex/platform-p22c-controlled-execution-console-2026-07-02`
**Base:** `ca5b2c4` (`origin/platform-dev` -- "merge: P22-B controlled execution backend skeleton")
**Contract:** `docs/ai/PLATFORM_PRODUCT_P22_CONTROLLED_EXECUTION_V0_CONTRACT.md` (P22-A)
**Author:** Codex (Claude worker)
**Status:** C0-C4 complete; CTO R1 applied (payload-binding invalidation + README ASCII + tests); ready for CTO re-review

---

## 1. Summary

P22-C implements the **non-executing** frontend operator console on top of the
already-merged P22-B backend skeleton. An identity-only platform operator can:

1. view the closed v0 execution catalog (read-only),
2. inspect the explicitly excluded actions and the safety boundaries,
3. run a no-mutation dry-run,
4. record a non-executing execution request **only** after a passed dry-run and
   an explicit typed acknowledgement,
5. list and read recorded execution requests,
6. clearly see block reasons, source status, result_state, redaction, the
   idempotency digest, and the no-execution status throughout.

The console NEVER executes anything. There is no execute button, no worker, no
queue drain, no harness invocation, no shell / SQL / script, and no tenant /
payment / billing / product mutation. Every response is rendered with
`executed === false`, `execution_allowed === false`, `execution_started === false`,
and a `result_state` of only `dry_run_passed | blocked`. The raw idempotency key
is typed into the boundary only; it is hashed there and only its one-way digest
is ever rendered from a response.

> **Approval is not execution. Request recording is not execution.** A passed
> dry-run is a precondition, never an execution; a recorded request is recorded
> only and is never executed.

## 2. Base / Branch / Commit Chain

- **Base SHA:** `ca5b2c4` (`origin/platform-dev`)
- **Worktree:** `MPANGO ERP/codex-platform-p22c-controlled-execution-console-2026-07-02`
  (created from `origin/platform-dev` via `git worktree add -b`; the branch
  tracks `origin/platform-dev`, so per the worktree-push gotcha it is pushed with
  an explicit `git push -u origin <branch>:<branch>` -- a bare `git push` is
  avoided so `platform-dev` cannot be fast-forwarded)
- **Commit chain (base..documented tip):**
  - `ca5b2c4` -- base (origin/platform-dev, P22-B merge)
  - `79d3c97` -- `platform(p22c): controlled execution console types + API client (C1)`
  - `6da310a` -- `platform(p22c): controlled execution console page + route + nav (C2)`
  - `183b6fe` -- `platform(p22c): controlled execution console tests (C3)`
  - `b95da4c` -- `platform(p22c): controlled execution console ledger + read-order note (C4)`
  - `292947d` -- `platform(p22c-r1): ledger commit-pointer accuracy fix` (records the real C4 SHA)
  - `9ac3a75` -- `platform(p22c-r1): payload-binding invalidation + README ASCII + tests` (**CTO R1 code/test/docs fix**)
  - this ledger update (CTO R1 ledger; documented branch tip -- its own SHA is intentionally not self-referenced)

`platform-dev` was NOT merged after branch creation and NOT pushed. Only the
isolated P22-C branch carries these changes.

## 3. Modified / Added Files

All changes are frontend-only and additive (1,955 insertions, 0 deletions across
the 9 code/test files; plus this ledger and one docs sentence).

| File | Status | Scope |
|---|---|---|
| `frontend/src/types/platformControlledExecution.ts` | New | P22 types field-for-field aligned to the P22-B backend schemas; closed 7-action allowlist tuple; vocabularies; response shapes never model a raw idempotency key (only the digest) |
| `frontend/src/services/platformApi.ts` | Modified (additive) | 5 new methods on `platformService`: `getExecutionCatalog`, `dryRunExecution`, `recordExecutionRequest`, `listExecutionRequests`, `getExecutionRequest` (+ a `P22_BASE` const). No existing method changed |
| `frontend/src/pages/platform/PlatformControlledExecutionConsolePage.tsx` | New | The non-executing console: catalog cards, separated excluded-actions area, dry-run form + result, record section gated on passed dry-run + ack, record result, queue list, read-by-id; empty/loading/error/blocked/success states. R1: every `buildPayload()` input now invalidates a prior passed dry-run on change |
| `frontend/src/router/AppRouter.tsx` | Modified (additive) | Route `/platform/controlled-execution` under the existing identity-only `PlatformRoute` guard |
| `frontend/src/components/layout/Sidebar.tsx` | Modified (additive) | "Controlled Execution" nav entry inside the existing `showPlatformNav` (identity-only) block |
| `frontend/src/services/__tests__/platformControlledExecutionApi.test.ts` | New | 8 API client tests |
| `frontend/src/types/__tests__/platformControlledExecution.test.ts` | New | 5 type contract tests |
| `frontend/src/pages/platform/__tests__/PlatformControlledExecutionConsolePage.test.tsx` | New | 16 page behavior tests (12 original spec cases + 4 R1 payload-invalidation cases) |
| `frontend/src/pages/platform/__tests__/PlatformControlledExecutionNav.test.tsx` | New | 5 nav + guard tests (the 14-case spec, cases 13-14) |
| `docs/ai/README.md` | Modified (additive) | One cumulative-state sentence appended to the P22 read-order paragraph (ASCII-only as of R1; the U+2014 em dash was replaced with `--`) |
| `ai-ledger/platform/2026-07-02_p22c_controlled_execution_console.md` | New | This ledger |

No other paths were touched.

## 4. Endpoint Coverage

All five P22-B endpoints are covered by the API client (and exercised by tests):

| Endpoint | Method | Client function |
|---|---|---|
| `/api/v1/platform/p22/execution/catalog` | GET | `getExecutionCatalog` |
| `/api/v1/platform/p22/execution/dry-run` | POST | `dryRunExecution` |
| `/api/v1/platform/p22/execution/requests` | POST | `recordExecutionRequest` |
| `/api/v1/platform/p22/execution/requests` | GET | `listExecutionRequests` (limit/offset + result_state/action_type/durable_approval_id filters) |
| `/api/v1/platform/p22/execution/requests/{id}` | GET | `getExecutionRequest` |

Shapes are preserved from the backend; an `unwrap<T>` helper tolerates either a
raw body or a `{data: {...}}` envelope. Every response is treated as
non-executing.

## 5. UI Capabilities

- First screen is the operator console (title + non-execution banner), not a
  marketing/hero page.
- Catalog cards show `action_type`, `action_class`, `reversible`,
  `reversibility_via`, and `tenant_business_mutation` (always `none`).
- Excluded actions are shown in a clearly separated, read-only area and are NOT
  selectable in the dry-run action select (the select contains only the seven
  allowlisted actions).
- Dry-run form: `durable_approval_id`, allowlisted `action_type`, optional
  `tenant_id`, optional `requested_state`, required `reason`, required
  `idempotency_key`, `execution_mode` (sync/queued), optional `correlation_id`,
  optional `metadata` (JSON object textarea, validated client-side).
- Dry-run result panel: `verdict`, `executable`, `block_reasons`, `source_status`,
  `reversible`, `dry_run_id`, `expected_audit_shape` summary (event names only),
  `idempotency_key_digest`, and `executed/execution_allowed/execution_started`
  (all false).
- Record-request section appears ONLY after a passed dry-run and requires the
  explicit typed acknowledgement checkbox; the button is labelled "Record
  non-executing request" (never "Execute"). Editing any bound field invalidates
  the prior dry-run, forcing a re-run.
- Record-result panel: `result_state`, `result`, `action_type`,
  `durable_approval_id`, actor role/context, `redaction_applied`,
  `idempotency_key_digest`, `payload_digest`, `created_at`.
- Queue list + read-by-id panels; queue summary repeats `executed=false`.
- Empty, loading, error, blocked, and success states are all implemented.
- UI copy repeats throughout: approval is not execution; request recording is
  not execution; this console never executes.

## 6. Tests and Exact Counts

- **P22-C targeted tests: 34 pass** (30 original + 4 R1 invalidation cases)
  - API client: 8 (`platformControlledExecutionApi.test.ts`)
  - Type contract: 5 (`platformControlledExecution.test.ts`)
  - Page behavior: 16 (`PlatformControlledExecutionConsolePage.test.tsx` -- 12 original + 4 R1)
  - Nav + guard: 5 (`PlatformControlledExecutionNav.test.tsx`)
- **Full frontend suite: 33 files / 302 tests pass** (was 298 before R1; no regressions; vitest 1.6.1)
- **Backend P22 regression: 56 pass** (`tests/test_platform_p22_controlled_execution.py`, run with the shared `.venv` Python 3.14 + a 32+ char SECRET_KEY + PYTHONPATH=backend; the P22-B contract is intact and unchanged)

The 14-case C3 spec is covered, plus 4 R1 payload-invalidation cases:
1. catalog shows exactly seven allowlisted actions (P22-P01)
2. excluded actions visible and not selectable (P22-P02)
3. passed dry-run enables recording (P22-P03)
4. blocked dry-run shows block reasons and keeps recording unavailable (P22-P04)
5. missing/invalid fields show validation and disable the dry-run (P22-P05)
6. recording requires the acknowledgement (P22-P06)
7. record success shows `dry_run_passed` + `executed=false` (P22-P07)
8. digest shown, raw idempotency key not echoed after response (P22-P08)
9. list and read work (P22-P09)
10. API errors show non-crashing operator feedback (P22-P10)
11. no button/label commands "Execute" (P22-P11)
12. no product/payment business action wording; every action shows
    mutation=none (P22-P12)
13. sidebar nav entry exists for identity-only operators (P22-N01..N03)
14. permission/guard matches the existing PlatformRoute pattern (P22-N04..N05)
15. editing reason after a passed dry-run forces a fresh dry-run (P22-P13, R1)
16. editing the idempotency key after a passed dry-run forces a fresh dry-run (P22-P14, R1)
17. editing metadata after a passed dry-run forces a fresh dry-run (P22-P15, R1)
18. editing correlation id after a passed dry-run forces a fresh dry-run (P22-P16, R1)

## 7. GitNexus

- `npx gitnexus analyze .` (HEAD, re-run after R1): repository indexed
  successfully -- 8,340 nodes / 25,560 edges / 528 clusters / 300 flows
  (was 8,326 nodes / 25,546 edges before R1; the +14/+14 reflect the added
  test cases and page wiring). `gitnexus status` reports the index fresh at
  the R1 tip.
- `gitnexus detect_changes` (MCP-only tool; driven over stdio JSON-RPC against
  `npx gitnexus mcp`): returned `risk_level: none`, `changed_count: 0`,
  `affected_count: 0`, no changed symbols, no affected processes -- no
  product / payment / backend / execution flows flagged. (Note: this worktree
  path was freshly indexed in this session, so detect_changes had no prior
  per-path baseline to diff; the conclusive isolation evidence is the git diff
  below.)
- `gitnexus impact Sidebar --repo <this-worktree> --depth 1`: `risk: LOW`,
  `impactedCount: 0`, 0 processes, 0 modules affected.
- `gitnexus impact platformService`: not a graph node (it is an object literal);
  the P22 additions are additive properties, so there is no caller blast radius.

## 8. Forbidden Path Audit

`git diff --name-only origin/platform-dev..HEAD` (excluding this ledger commit)
returns exactly nine paths, all under `frontend/src/`. None match any forbidden
prefix:

- No `backend/`, no `migrations/`, no `alembic/`, no `env.py`.
- No `product-dev-recovered/`.
- No product/business paths: no orders, payments, billing, finance, inventory,
  client, customer, invoice, ledger.
- No auth / RBAC / session rewrite.
- No `package.json`, no lockfiles, no dependency changes.
- No `.github/`, no `.claude/`, no configured secrets baseline file, no CI/deploy
  files.
- No real execution / worker / harness / shell / SQL / script.

## 8a. CTO R1 Findings and Fixes

CTO R1 raised two findings; both are fixed in commit `9ac3a75` (frontend-only;
no backend / migration / product / auth / package / lockfile change):

- **P1 -- payload-binding gap.** Only five of the nine `buildPayload()` inputs
  invalidated a prior passed dry-run on change. `reason`, `idempotency_key`,
  `correlation_id`, and `metadata` did not, so an operator could pass a dry-run,
  then edit one of those fields while the record section stayed bound to a stale
  `dry_run_ref`. **Fix:** all nine payload inputs (`durable_approval_id`,
  `action_type`, `tenant_id`, `requested_state`, `reason`, `idempotency_key`,
  `execution_mode`, `correlation_id`, `metadata`) now call `invalidateDryRun()`
  on change, which clears `dryRunResult`, `recordResult`, and the
  acknowledgement -- so the record section disappears and a fresh dry-run is
  required before a request can be recorded against a new `dry_run_ref`.
  Verified by P22-P13..P22-P16.
- **P2 -- non-ASCII in docs/ai/README.md.** The P22-C read-order sentence
  contained a U+2014 em dash (3 non-ASCII bytes). The earlier Git Bash
  `LC_ALL=C grep -nlP` scan missed it on Windows; a Python byte scan caught it.
  **Fix:** replaced the em dash with ASCII `--`. The full changed-set
  non-ASCII scan is now 0 bytes (Python byte scan, the reliable method here).

R1 added 4 tests (page total 12 -> 16; targeted 30 -> 34; full suite
298 -> 302). Per the R1 instruction, the ledger's own commit SHA is
intentionally not self-referenced in the chain above.

## 9. Self-Review

Two rounds were performed.

**Round 1 -- security / boundary.** Grep of the changed files for execution
primitives (`subprocess`, `popen`, `shell`, `spawn`, `exec(`, `child_process`,
`psql`, `cursor.execute`, `drain`, `dispatch`, `harness`) returns only
safety/exclusion copy (e.g. "never dispatches a worker", "never drains a queue",
"never invokes the governed harness", and the `'arbitrary shell / SQL / script'`
excluded-action text that mirrors the backend). No button or label commands
"Execute". No backend, migration, package/lockfile, auth/RBAC/session, or
product/payment path is changed.

**Round 2 -- reproducibility / evidence.** `git diff --check origin/platform-dev..HEAD`
reports no whitespace errors. A non-ASCII scan of all changed files is clean
(**0 non-ASCII bytes**, verified with a Python byte scan -- the reliable method
on Windows; the earlier Git Bash `grep` scan missed the README em dash that R1
fixed). `detect-secrets-hook` against the configured secrets baseline on all
changed files exits 0 (no new secrets); the pre-commit hook also passed on every
commit. The forbidden-path audit is clean (section 8). Fresh test command
outputs and exact counts are in section 6.

## 10. Risk

- **Low.** The change is frontend-only, additive (0 deletions), and reuses the
  existing `platformService`, `PlatformRoute` guard, `Skeleton`, and Tailwind
  conventions. It consumes the unchanged P22-B backend read/recording paths.
- The page trusts the typed contract for response shapes (mirroring the existing
  P18 console); the backend guarantees well-formed, redacted, non-executing
  responses.
- The raw idempotency key is held only in the form input the operator types; it
  is never rendered from a response, stored, or logged by the frontend. Only the
  one-way digest and the payload digest are rendered.
- TypeScript: no new errors are introduced by these files (41 pre-existing
  baseline errors in unrelated ops/test files remain on `origin/platform-dev`,
  unchanged by this work).

## 11. Blockers

None.

## 12. Explicit Statements

- **No execution.** There is no execute button, worker, queue drain, harness
  invocation, or shell/SQL/script path. Every UI path states no execution and
  never implies a real action landed. `executed`, `execution_allowed`, and
  `execution_started` are always `false`; `result_state` is only ever
  `dry_run_passed | blocked`.
- **No backend change.** No `backend/` file is touched; the P22-B backend is
  consumed as-is and its 56 regression tests pass.
- **No migration / schema / storage change.** None.
- **No product / payment / tenant business mutation.** None; every catalog
  action shows `tenant_business_mutation: none`.
- **No auth / RBAC / session rewrite.** The route reuses the existing
  identity-only `PlatformRoute` guard unchanged.
- **No package / lockfile / dependency change.** None.
- **No raw key / secret display.** Only the one-way `idempotency_key_digest` and
  `payload_digest` are ever rendered from a response; the raw idempotency key is
  never echoed after submit (asserted by P22-P08).
- **P22-D not started.** No work toward P22-D (or any executing phase) was
  begun. Real execution of any v0 action remains reserved for a separately
  approved phase that must run through the P16 governed harness.
