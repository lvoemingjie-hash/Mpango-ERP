# P23-D - Operator Task Queue Frontend Console

- Status: LANDED on branch, NOT merged (push-ready on request).
- Date: 2026-07-05.
- Branch: `codex/platform-p23d-operator-task-frontend-console-2026-07-05`
- Base: `origin/platform-dev` @ `3ca13431` (merge: P23-C operator task source
  materialization bridge). P23-B (backend skeleton) and P23-C (source bridge)
  ARE merged at this base; the frontend here consumes the P23-B/C REST contract.
- Worktree: `_p23d_2026-07-05`.
- Commits: `cb52d468` (code), + this ledger (R0).

## Objective

Build the frontend-only platform operator task console for the P23-B/C queue: a
read / triage / record surface where a task is a view (not an executor) and a
notification is a record (not a delivery). The console lists the queue, reads a
task with its audit + notification-event history, runs the presentation-only
state machine, and manually reads the safe source surfaces through materialize.
It never executes, never decides an approval, and never delivers a notification.

## What it does

- Typed API client (additive `P23_BASE` section on the existing Axios singleton
  `platformService`): `listOperatorTasks`, `getOperatorTask`,
  `materializeOperatorTasks`, `acknowledgeOperatorTask`,
  `selfAssignOperatorTask`, `markOperatorTaskInProgress`,
  `completeOperatorTask`, `dismissOperatorTask`. The actor for every transition
  is the authenticated identity-only token (read in the route); it is never sent
  in the request body, mirroring the P20-B-R1 / P22 binding. The internal
  `intake` endpoint is system-only and intentionally NOT exposed here.
- `PlatformOperatorTasksPage` console:
  - Task queue with severity / task-type / state / source-status filters, ranked
    by severity then recency; active + total counts; refresh.
  - Detail panel: the redacted record (full grid), the append-only audit
    history (with denied-transition `denial_code` badges), and the
    notification-event list (each surfaced as a RECORD, never a delivery).
  - Materialize (P23-C) button rendering the per-source read / created / deduped
    / skipped / unavailable summary.
  - Presentation-only triage transitions gated by the closed P23-A transition
    graph; `acknowledge` / `self-assign` / `in-progress` / `dismiss` per current
    state.
  - Complete evidence gate: requires a redacted evidence note OR a linked
    completed id (`evidence_ref`) AND a closed `linked_gate_open` AND an explicit
    confirm. A 409 denial (`COMPLETE_DENIED_NO_EVIDENCE` /
    `COMPLETE_DENIED_GATE_OPEN` / `TRANSITION_DENIED_*`) is parsed from the
    FastAPI `{detail:{code,message}}` body and surfaced cleanly inline; the task
    state is unchanged and the denial is recorded in the audit history.
  - source_unknown is NEVER healthy and backup_check_warning is NEVER success:
    the display badge is never green for either task type, defended client-side
    by `resolveOperatorDisplayTone` regardless of the backend label (a drifted
    `display_status:'healthy'` on a `source_unknown` task still renders gray).
  - Empty / loading / error states; redacted-only field rendering;
    `redaction_applied=true` displayed on every task and notification event.
- Route + nav wiring: `/platform/operator-tasks` behind the REUSED identity-only
  `PlatformRoute` guard (no auth / RBAC rewrite); a Sidebar "Operator Tasks" link
  shown only for identity-only super_admin.

## What it does NOT (explicit)

- No execution: no execute / run / apply / dispatch / trigger / send / deliver
  control exists. Completing a task records operator attention only; it never
  runs a P22 action and never makes the completer the P22 executor.
- No approval decision: the console decides no P19/P20/P21 approval.
- No notification delivery: notification events are displayed as RECORDS of
  attention (delivery_state `recorded` | `suppressed`); no channel is wired and
  nothing is delivered.
- No backend / migration / DB: this is frontend-only. No `app.py`, route,
  schema, service, migration, alembic, sqlalchemy, or DB change.
- No product / tenant business path: no order / payment / invoice / inventory /
  finance / customer / ledger / tenant-business module is imported or referenced.
- No auth / RBAC rewrite: the P10 identity-only `require_platform_operator` guard
  and `PlatformRoute` are reused unchanged; owner is presentation only.
- No package / lockfile change: no dependency added or moved.

## Files

`origin/platform-dev..HEAD` = 9 files = 8 frontend code/test files + this ledger.
All 9 are under `frontend/src/` or `ai-ledger/platform/`.

NEW (5):

- `frontend/src/types/platformOperatorTasks.ts` (456 lines): closed P23
  vocabularies (10 task types / 9 states / 3 severities / source statuses /
  display statuses / 5 denial codes) as literal unions + arrays, the task /
  detail / queue / transition-request / transition-response / materialize-source
  / materialize-summary models mirroring
  `backend/api/v1/platform/p23/schemas.py` + `sources.py` field-for-field, the
  terminal / never-healthy / never-success sets, the allowed-transition map, and
  the client-side `resolveOperatorDisplayTone` / `isHealthyOperatorTone`
  defenders.
- `frontend/src/pages/platform/PlatformOperatorTasksPage.tsx` (997 lines): the
  console (queue + filters + detail + audit + notifications + materialize +
  triage transitions + complete gate + denial handling + empty/loading/error).
- `frontend/src/services/__tests__/platformOperatorTasksApi.test.ts` (201 lines):
  13 API client tests.
- `frontend/src/pages/platform/__tests__/PlatformOperatorTasksPage.test.tsx`
  (532 lines): 23 page tests.
- `frontend/src/pages/platform/__tests__/PlatformOperatorTasksNav.test.tsx`
  (126 lines): 5 nav / guard tests.

MODIFIED (3, purely additive):

- `frontend/src/services/platformApi.ts` (+103, 0): P23 type imports, `P23_BASE`,
  and the 8 typed methods appended after the P22 section. No existing method
  touched.
- `frontend/src/router/AppRouter.tsx` (+8, 0): 1 import + 1 route element under
  `PlatformRoute` + `MainLayout`. No existing route touched.
- `frontend/src/components/layout/Sidebar.tsx` (+15, 0): 1 icon import
  (`ClipboardDocumentCheckIcon`) + 1 nav link. No existing link touched.

Diff scope: every changed path is under `frontend/src/` (verified by the
forbidden-path audit below). Zero `backend/`, migration, `alembic/env`,
`app.py`, product, package, lockfile, auth, guard, or docs changes. The new
branch only ADDS frontend files and appends to 3 shared frontend modules.

## Tests

- 41 new P23-D tests pass:
  - API client (13): every method calls the correct P23 URL with the correct
    params/body; the actor is never in the body; queue / transition /
    materialize responses are modelled with `redaction_applied=true` and
    `accepted`/`denial_code`; intake is NOT exercised (out of scope).
  - Page (23): title/subtitle/invariants; queue render + empty/loading/error;
    materialize calls the read-only endpoint and renders the per-source summary;
    apply/reset filters; detail renders redacted record + audit history +
    notification events (records, not deliveries); acknowledge POSTs with no
    actor; complete evidence gate (disabled until evidence + confirm); complete
    POSTs the evidence payload; complete denial (gate open / no evidence)
    surfaces the code; complete blocked while the linked gate is open; terminal
    task shows no transitions; source_unknown never green; backup_check_warning
    never green; source_unknown stays non-green even with a drifted
    `display_status:'healthy'`; a normal healthy task IS green (sanity);
    no execute/run/apply/dispatch/trigger/send/deliver button; tenant-contextual
    identity sees no controls and no queue load; correct list + read endpoints.
  - Nav/guard (5): Sidebar shows the link for identity-only super_admin; hides
    it for tenant-contextual and non-platform users; `PlatformRoute` admits
    identity-only and redirects tenant-contextual away.
- Full frontend suite: 353 passed, 0 failed (36 test files, 0 regressions). The
  stderr warnings are pre-existing React Router v7 future-flag notices and a
  pre-existing `act()` warning in `OpsSlowRoutesPage` (untouched file).

Recipe: vitest via a junction-shared `node_modules`
(`frontend/node_modules` -> the main repo's `frontend/node_modules`);
`npx vitest run` from the worktree `frontend/`. `jsdom` environment. The
`.gitnexus` / `node_modules` artifacts are gitignored and never committed.

## Validation gates

- vitest P23-D (new): 41 green.
- vitest full frontend suite: 353 green, 0 regressions.
- TypeScript: `tsc --noEmit` reports ZERO errors in any P23-D file (the 5 new
  files + the 3 modified files). The remaining `tsc` diagnostics are all
  PRE-EXISTING in untouched files (Ops pages, `PlatformApprovalsPage`,
  `PlatformOverviewPage`, `SidebarOps.test`, `guards.test`, etc.); they reproduce
  on `origin/platform-dev` and are out of scope for a frontend-only phase.
- `git diff --check`: clean (only LF -> CRLF Windows-normalization warnings, per
  prior phase ledgers).
- Added-line ASCII scan on all 8 frontend files: clean (0 non-ASCII bytes). This
  ledger is also ASCII-clean.
- detect-secrets: 0 findings on all 8 frontend files; the configured baseline is
  UNTOUCHED. The pre-commit `Detect secrets` hook Passed on the code commit
  (scanned all 8 staged files).
- Forbidden path/keyword audit: every changed path is under `frontend/src/`
  (confirmed by `git diff --name-only origin/platform-dev` +
  `git ls-files --others --exclude-standard`, then filtered). No path contains
  any forbidden segment: `backend/`, `migration`, `alembic`, `package.json`,
  `pnpm-lock` / `yarn.lock` / `package-lock`, `auth`, `guard`, `rbac`,
  `password`, `secret`, `ops/`, `k8s/`, `docker`, `nginx`, `database/`, or any
  product / business module (`order`, `payment`, `invoice`, `inventory`,
  `finance`, `retailer`, `sku`, product tenant-business, `core/`).

## GitNexus

- `gitnexus analyze` (re-run at the branch code tip `cb52d468`):
  9,134 nodes / 27,917 edges / 571 clusters / 300 flows. Analyzer variance vs.
  the same-worktree run at the base `3ca1343` (9,135 / 27,917 / 572 / 300):
  nodes -1, clusters -1, edges 0, flows 0 - the documented node/cluster wobble;
  same order of magnitude, NOT a stale index passed off as the tip index.
- `gitnexus status`: re-run after the code commit; up-to-date at the branch tip
  `cb52d46`. The indexed code graph INCLUDES the P23-D code (the new symbols
  resolve); it is NOT the base `3ca1343`.
- `gitnexus impact` CLI (`--repo _p23d_2026-07-05`):
  - `PlatformOperatorTasksPage`: impactedCount 0, risk LOW, 0 affected processes,
    0 affected modules. ZERO product-business flows.
  - `Sidebar`: impactedCount 0, risk LOW, 0 processes, 0 modules (the additive
    nav link has no graph blast radius).
  - `resolveOperatorDisplayTone`: risk LOW, impactedCount 1, affected_modules =
    `Types` only (its own module); 0 product.
  - `platformService` / the individual `*OperatorTask` client methods: not
    indexed as standalone symbols (they are properties of a single object
    literal), so `impact` returns "not found"; the page-component impact above
    covers the consumer side, and the additive-only diff to `platformApi.ts`
    (no existing method changed) means zero existing-symbol regression.
  - Sibling sanity: `PlatformApprovalsPage` also reports risk LOW / 0, consistent
    with all platform console pages being LOW / 0 product in this graph.
- `detect_changes` (MCP): not pursued; with 213 indexed repositories the stdio
  MCP requires disambiguation and is the documented flaky path for large repos.
  The impact CLI is the reliable corroborator (per the repo validation
  playbook); together with the git diff scope (every path under
  `frontend/src/`), it establishes platform-only risk with ZERO product-business
  flows.

## Risk

LOW. Frontend-only blast radius. Zero product-business flows. Zero `app.py`,
migration, backend, DB, auth/RBAC, or shared-symbol behavioral changes (the 3
shared frontend files are touched additively: new methods / new route / new nav
link; no existing line altered). No new auth / RBAC / session surface (reuses
the P10 identity-only `PlatformRoute` guard). The stop gate (GitNexus shows
product-business affected flows) is NOT triggered: `PlatformOperatorTasksPage`
and `Sidebar` are both risk LOW / impactedCount 0.

## Blockers

None.

## Explicit statements

- No execution: the console runs no P22 action, decides no approval, restores
  nothing, runs no shell / SQL / script / subprocess. Completing a task records
  operator attention only.
- No delivery: notification events are displayed as RECORDS of attention; no
  channel is wired and nothing is delivered on any channel.
- No product/tenant mutation: the console reads the P23 queue / detail and
  records presentation-only triage; it mutates no product / payment / billing /
  inventory / invoice / customer / ledger / tenant-business record.
- No backend / migration / DB / auth rewrite: this is frontend-only; the route
  reuses the existing identity-only platform-operator guard.

## Revision history

- R0 (`cb52d468` code + this ledger): initial P23-D frontend console. 41 new
  tests; full frontend suite 353 green; GitNexus at the code tip
  `cb52d468` = 9,134 / 27,917 / 571 / 300; impact LOW / 0 product for the new
  page, the touched Sidebar, and the display-tone helper.
