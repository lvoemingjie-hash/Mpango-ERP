# Platform Product P25 -- Platform Frontend Customer Readiness Contract

**Status:** Contract only (P25-A). No runtime code, no backend handlers, no frontend UI,
no migrations, no alembic changes, no tests, and no dependency changes. Accepted by the
CTO before any P25-B frontend validation / smoke harness may begin.
**Phase:** P25-A Platform Frontend Customer Readiness Contract
**Date:** 2026-07-06
**Base:** `e5c28ec` (origin/platform-dev -- P24 incident + runbook closeout: P24-A
contract, P24-B non-executing / non-sending backend skeleton, P24-C frontend console,
and P24-D closeout all merged; P24_INCIDENT_RUNBOOK_CLOSEOUT_READY)
**Depends on:** P10 (identity-only super_admin `PlatformRoute` guard, PlatformAuditEvent,
source-status vocabulary, redact_metadata allowlist), P11 (Platform Admin Cockpit
boundary, `PlatformRoute` super_admin-only entry), P12 (Support Console support-safe
subset, support package / diagnostics bundle), P13 / P14 (Operations Observability
cockpit plus `unavailable_reason` / `degraded_reason`), P15 (Incident Triage read-only
console), P16 (Worktree Execution Harness -- development-time only, never a runtime
executor), P17 (Platform Registry, Tenant Lifecycle, `TenantOperationalFlags.incident_active`,
backup / status source read wiring), P18 (Controlled Platform Actions request layer, the
`executed` flag, `incident.flag_set` / `incident.flag_clear`), P19 (Approval Workflow),
P20 (Durable Approval Governance), P21 (Durable Approval Store + runtime adapter), P22
(Controlled Execution v0, runtime governed action adapter seam, recorded-request-bound
read-only `backup.check`, the `backup.check` console, source-status honesty), P23 (Operator
Task / Notification Queue -- the ten-type task catalog, the nine-state triage machine, the
notification EVENT boundary, the never-leaked list, "a task is a view, not an executor"),
P24 (Incident + Runbook Closeout -- the eight-state closeout lifecycle, the runbook step
model, PUSH intake, "a closeout is a view / a step is a pointer / a follow-up is a record").
**Author:** Codex (Claude worker)

---

## 1. Goal and Non-Goals

### 1.1 Goal

P10 through P24 built the platform product track one capability at a time, each behind a
contract-first gate, each landing only a non-executing / non-sending slice (or, for
`backup.check` only, a single read-only governed action). The as-built surface is now
wide: a platform overview, a system / tenant health pair, an audit feed, a tenant
directory, a support console, a P13 / P14 operations observability cockpit, a P15
read-only incident triage page, a P17 registry, a P18 controlled-actions console, a P19
approvals console, a P20 / P21 durable-approvals console, a P22 controlled-execution
console (where the read-only `backup.check` governed action is bound), a P23 operator
task / notification queue console, and a P24 incident closeout / runbook console. Every
one of these routes sits behind the P10 / P11 `PlatformRoute` identity-only global
`super_admin` guard (a tenant-contextual `super_admin` is explicitly denied).

None of that work has been validated end-to-end as a *customer / operator readiness*
surface. Each phase proved its own invariants with unit tests and (for some slices) a
GitNexus blast-radius check, but no phase stitched the routes together into a single
readiness story: can an identity-only platform operator log in, navigate the sidebar to
every platform route, see a sane empty state, a sane loading state, a sane error state,
and a sane denied state, read every list, open every detail, drive every record / action
/ approval / triage / closeout form that the invariants permit, and never see a secret, a
raw payload, a clipped control, an overlap, a tenant leak, a `source_unknown` shown
healthy, or a `backup_check_warning` shown as success?

**P25 is that readiness story.** It is **not a new platform capability**. It is a
validation / readiness layer over the as-built P10 through P24 surface. P25 defines:

1. A **customer / operator readiness definition** -- what "ready" means for the platform
   cockpit as a whole (login, navigation reach, state coverage, copy / leak safety,
   layout integrity, console consistency).
2. A **route inventory** -- the closed set of platform routes that must be exercised,
   grounded in the as-built `router/AppRouter.tsx` and `components/layout/Sidebar.tsx`,
   not invented.
3. A **validation matrix** -- the dimensions every route is checked against (smoke,
   login, screenshots, empty / loading / error / denied, sidebar-to-detail-to-form
   navigation, copy review, no-overlap / no-clipped-text, frontend console consistency).
4. A **safety boundary** -- P25 adds no new backend capability, no migration, no product
   branch merge, no product business mutation, no auth / RBAC rewrite, no P22 execution
   expansion, and no notification delivery.
5. An **evidence plan** -- the artifacts a P25-B validation pass must produce
   (screenshots, commands, the route list, test counts, known warnings, a demo script).
6. **Acceptance criteria and counterexamples** that bound all later P25 validation work,
   plus the **P25-B entry gate** (frontend validation / smoke harness only; no feature
   implementation unless separately approved).

P25 is the **last** platform track gate before the surface is declared customer / operator
ready. It does not add a capability; it certifies the capabilities P10 through P24 already
shipped are usable, leak-safe, and consistent as a whole.

### 1.2 In scope (readiness / validation layer)

This contract, and a future P25-B validation harness, may:

- enumerate and smoke every as-built platform route (section 3);
- run a real login smoke against the platform cockpit where a runnable stack is available,
  and record the result (pass, skip-with-reason, or fail) honestly;
- capture Playwright (or equivalent) screenshots of each route in its empty, loading,
  error, and denied states where feasible;
- assert the sidebar-to-detail-to-action / record / approval / triage / closeout form
  navigation path for each capability;
- review on-screen copy against the never-leaked list (no secrets / DSNs / host:port /
  tokens / cookies / auth headers / raw payloads / shell / SQL / tenant payload);
- check for clipped text, overlapping controls, and inconsistent badge / tone conventions
  across the P22 / P23 / P24 consoles;
- record a demo script, the validation command list, the route list, test counts, and
  known warnings as evidence;
- add a docs / ledger readiness record and (in P25-B only) a non-shipping, non-merging
  frontend validation / smoke harness.

### 1.3 Non-goals

#### 1.3.1 P25-A-only non-goals (this contract)

P25-A is **docs and ledger only**. It does not:

- add any runtime code, backend handler, frontend page, component, test, fixture, or
  dependency;
- add any migration, alembic change, table, column, or seed;
- add the validation harness itself (that is P25-B, behind the section 9 gate);
- merge anything into `platform-dev` or `product-dev-recovered`;
- push to `platform-dev` (the feature branch is pushed with an explicit `X:X` refspec;
  `origin/platform-dev` is left unchanged);
- start P25-B.

#### 1.3.2 All-P25 non-goals (bind P25-A and every later P25 slice)

Across all of P25 (A and any later slice):

- **No new platform capability.** P25 validates the as-built P10-P24 surface; it does not
  add a new console, a new task type, a new closeout state, a new action, or a new route.
- **No migration.** No alembic change, table, column, index, or seed lands under P25.
- **No product branch merge.** P25 does not merge into `product-dev-recovered` and does
  not merge into `platform-dev`; it stays on its own feature branch until the CTO
  approves a merge.
- **No product business mutation.** P25 touches no order / payment / invoice / customer /
  inventory / ledger record; readiness validation reads platform surfaces only.
- **No auth / RBAC rewrite.** P25 reuses the P10 / P11 `PlatformRoute` identity-only
  global `super_admin` guard and the existing roles / session transport; any auth, RBAC,
  session, or tenancy change requires a separately approved contract.
- **No P22 execution expansion.** P25 does not add a governed action, does not dispatch a
  worker, does not run a real `backup.check` beyond what P22-G already bound, and does not
  widen the v0 allowlist.
- **No notification delivery.** P25 does not wire a channel; notification events stay at
  P23 `delivery_state == recorded` (a record, not a delivery).
- **No tenant data leak.** A readiness sweep that exposes tenant-A data in a tenant-B
  context is a defect to record, not a behavior to ship.
- **No `source_unknown` shown healthy, no `backup_check_warning` shown as success.**
  Readiness validation must confirm the P23 / P24 display invariants hold in the UI; if
  they do not, that is a recorded defect, not an accepted regression.
- **No deletion of audit history.** P25 changes no audit trail.
- **No AI agent execution / auto-approval / auto-close.** P25 adds no autonomous action.

## 2. Customer / Operator Readiness Definition

A platform cockpit route is **customer / operator ready** when ALL of the following hold
against the as-built P10-P24 surface, evidenced under section 6:

1. **Reachable under the identity-only guard.** The route is entered through the
   `PlatformRoute` guard, which admits only a global (`tenant_id == null`) `super_admin`.
   A tenant-contextual `super_admin` (`tenant_id != null`) is denied; a non-super_admin
   is denied. The denied path renders a sane denied / unauthorized state, not a crash.
2. **Navigable from the sidebar.** The route (or its parent group) is reachable from
   `components/layout/Sidebar.tsx`; the sidebar entry is visible only to operators who
   pass `isPlatformAdmin`, and the active-link highlight is correct.
3. **Empty state is sane.** With no data, the route renders an explicit empty state (not a
   blank pane, not a stale spinner, not a stack trace).
4. **Loading state is sane.** While data is in flight, the route renders a loading state;
   it does not flash empty-then-data in a way that looks like an error.
5. **Error state is sane.** When the backing read fails, the route renders a redacted error
   state (HTTP status / safe reason; no raw payload, no stack, no secret, no DSN).
6. **Denied / forbidden state is sane.** When the operator lacks the role or the read
   returns 401 / 403, the route renders a denied state, not a leak.
7. **Detail and forms are reachable.** Where the route has a detail view or a record /
   action / approval / triage / closeout form, that detail / form is reachable and renders
   its own empty / loading / error states.
8. **Copy is leak-safe.** On-screen text contains no secret, DSN, host:port, token,
   cookie, auth header, raw payload, shell, SQL, or tenant business payload (the P23
   never-leaked list applies in full).
9. **Layout is intact.** No clipped text and no overlapping controls at the validated
   viewport(s); the active sidebar highlight, badges, and tone classes render correctly.
10. **Console is consistent.** Tone / badge / status-pill conventions are consistent
    across the P22 (controlled execution), P23 (operator tasks), and P24 (incident
    closeout) consoles -- e.g. `source_unknown` is the same gray/unknown tone everywhere,
    `backup_check_warning` is the same warning tone everywhere, terminal success is the
    same success tone everywhere.
11. **No regression of a prior invariant.** The route does not display `source_unknown` as
    healthy, does not display `backup_check_warning` as success, does not expose tenant-A
    data in tenant-B context, and does not surface an execute / approve / flag-mutate /
    deliver control that the prior-phase invariant forbids.

The **whole cockpit** is customer / operator ready when every route in the section 3
inventory meets this definition and the section 6 evidence set is complete.

## 3. Route Inventory to Validate

This is the closed set of platform routes P25 must exercise. It is grounded in the as-built
`frontend/src/router/AppRouter.tsx` (the `PlatformRoute` subtree) and
`frontend/src/components/layout/Sidebar.tsx`. Every route is behind the P10 / P11
identity-only global `super_admin` guard. The runbook checklist is part of the P24 incident
closeout page (P24-C); there is no separate runbook route.

### 3.1 Overview, health, registry, support, operations

- `/platform` -- PlatformOverviewPage (overview / landing).
- `/platform/system/health` -- PlatformSystemHealthPage.
- `/platform/tenants` -- PlatformTenantDirectoryPage.
- `/platform/tenants/:tenantId/health` -- PlatformTenantHealthPage.
- `/platform/audit` -- PlatformAuditEventsPage.
- `/platform/registry` -- PlatformRegistryPage (P17; read-only registry / tenant lifecycle
  / `TenantOperationalFlags.incident_active` mirror).
- `/platform/support` -- SupportConsolePage (P12; support-safe subset, support package /
  diagnostics bundle).
- `/platform/ops/health` -- OpsHealthPage (P13).
- `/platform/ops/errors` -- OpsErrorsPage.
- `/platform/ops/slow-routes` -- OpsSlowRoutesPage.
- `/platform/ops/resources` -- OpsResourcesPage.
- `/platform/ops/noisy-neighbors` -- OpsNoisyNeighborsPage.
- `/platform/ops/incidents/triage` -- IncidentTriagePage (P15; read-only detect / classify
  / inspect / explain / handoff / close-as-observation).

### 3.2 Controlled actions, approvals, durable approvals

- `/platform/controlled-actions` -- PlatformControlledActionsPage (P18; action request
  layer; `executed` flag; `incident.flag_set` / `incident.flag_clear` requests).
- `/platform/approvals` -- PlatformApprovalsPage (P19; approve resolves to
  `execution_blocked`).
- `/platform/durable-approvals` -- PlatformDurableApprovalsPage (P20 / P21; maker-checker,
  quorum, `approved_execution_blocked` ceiling, durable records).

### 3.3 Controlled execution, backup check

- `/platform/controlled-execution` -- PlatformControlledExecutionConsolePage (P22; catalog,
  dry-run-first, record-request-only; the read-only `backup.check` governed action bound
  per P22-G / P22-E3 lives behind this console). No real dispatch, no worker.

### 3.4 Operator tasks

- `/platform/operator-tasks` -- PlatformOperatorTasksPage (P23; the ten-type task queue,
  nine-state triage machine, notification EVENT boundary; ack / self-assign / in-progress
  / complete / dismiss as pure state; materialize; record, not delivery).

### 3.5 Incident closeouts, runbooks

- `/platform/incident-closeouts` -- PlatformIncidentCloseoutsPage (P24; eight-state closeout
  lifecycle, runbook step checklist embedded here per P24-C; closeout / step transitions as
  pure state; honest close gate; a closeout is a view, a step is a pointer, a follow-up is
  a record).

### 3.6 Guard

Every route above is wrapped by `<PlatformRoute />` (`frontend/src/router/guards.tsx`),
which admits only an identity-only global `super_admin` (`roles` includes `super_admin`
AND `tenant_id` is `null`). Tenant-contextual `super_admin` and any non-super_admin are
denied. P25 must validate both the admit path and the deny path.

## 4. Required Validation Matrix

Every route in section 3 is validated against the following dimensions. The P25-B harness
records a result for each cell (pass / skip-with-reason / fail) and a screenshot or a
command transcript where feasible.

1. **Route smoke.** The route mounts without a runtime error under the identity-only guard;
   the backing read is issued; a deterministic, leak-safe render is produced. A route that
   throws on mount is a fail.
2. **Real login smoke (where available).** Where a runnable stack is available, a real
   identity-only `super_admin` logs in and reaches the route; the deny path is exercised
   for a tenant-contextual `super_admin` and for a non-super_admin. Where no runnable
   stack is available, this cell is `skip-with-reason` (recorded honestly), and a
   component-level guard test substitutes.
3. **Playwright screenshots where feasible.** Each route is captured in its empty, loading,
   error, and denied states where a runnable stack or a mocked backend makes that feasible.
   Screenshots are scrubbed (no secrets, no real tenant names beyond a documented fixture,
   no real tokens).
4. **Empty state.** Zero rows / no data renders an explicit empty state.
5. **Loading state.** In-flight data renders a loading state, not a flash of empty or error.
6. **Error state.** A failed backing read renders a redacted error state.
7. **Denied state.** A 401 / 403 / missing-role renders a denied state.
8. **Navigation path.** The sidebar -> route -> detail -> record / action / approval /
   triage / closeout form path is reachable and correct; the active sidebar highlight is
   correct on each route.
9. **Copy review.** On-screen text is checked against the never-leaked list.
10. **No-overlap / no-clipped-text.** At the validated viewport(s), no text is clipped and
    no controls overlap; badges and pills wrap or truncate cleanly.
11. **Frontend console consistency.** Tone / badge conventions are consistent across the
    P22 / P23 / P24 consoles (`source_unknown` gray everywhere, `backup_check_warning`
    warning everywhere, terminal success consistent).
12. **Invariant preservation.** The route does not regress a prior-phase display invariant
    (`source_unknown` never healthy, `backup_check_warning` never success, no tenant leak,
    no forbidden execute / approve / flag-mutate / deliver control).

The matrix is the unit of readiness: a route is ready when every applicable cell is pass
(or skip-with-reason with an honest recorded reason), and the cockpit is ready when every
route is ready.

## 5. Safety Boundaries

P25 is a readiness / validation layer. The following boundaries bind all of P25 (A and any
later slice):

1. **No new backend capability.** No new route handler, service, model, task type, closeout
   state, action, or governed slice. P25 reads the as-built surface; it does not extend it.
2. **No migration.** No alembic change, table, column, index, or seed. (The as-built
   surface is in-memory for the non-executing skeletons; P25 changes no storage.)
3. **No product branch merge.** P25 stays on its feature branch; it is not merged into
   `platform-dev` or `product-dev-recovered` unless and until the CTO approves a merge in
   a separate step.
4. **No product business mutation.** P25 touches no order / payment / invoice / customer /
   inventory / ledger record.
5. **No auth / RBAC rewrite.** P25 reuses the P10 / P11 `PlatformRoute` identity-only
   global `super_admin` guard and the existing roles / session transport. Any change to
   auth, RBAC, session, or tenancy requires a separately approved contract.
6. **No P22 execution expansion.** P25 does not add a governed action, does not dispatch a
   worker, does not run a real `backup.check` beyond the P22-G read-only binding, and does
   not widen the v0 allowlist.
7. **No notification delivery.** Notification events stay at P23 `delivery_state ==
   recorded`; P25 wires no channel (no in-app push, no email, no webhook).
8. **No tenant data leak.** A readiness sweep that leaks tenant-A data into tenant-B
   context is a recorded defect, never an accepted behavior.
9. **No `source_unknown` shown healthy; no `backup_check_warning` shown as success.**
   Readiness validates the P23 / P24 display invariants; a regression is a recorded
   defect.
10. **No audit-history deletion.** P25 changes no audit trail.
11. **No AI agent execution / auto-approval / auto-close.** P25 adds no autonomous action.
12. **No secret / payload leak in evidence.** Screenshots and transcripts are scrubbed
    against the never-leaked list before they are committed.

## 6. Evidence Plan

A P25-B validation pass produces the following evidence set (planning only in P25-A; no
artifacts are produced in P25-A beyond this contract and its ledger):

1. **Route list.** The closed set from section 3, each with its component, guard, and
   backing read endpoint, verified against the as-built `AppRouter.tsx` and `Sidebar.tsx`.
2. **Validation matrix result.** One row per route, one column per section 4 dimension,
   each cell pass / skip-with-reason / fail.
3. **Screenshots.** Playwright (or equivalent) captures per route for empty / loading /
   error / denied where feasible, scrubbed against the never-leaked list.
4. **Commands.** The exact commands used to run the harness, the stack (or the recorded
   "no runnable stack" reason), the login smoke, and the unit / component tests.
5. **Test counts.** The platform backend test count, the frontend suite count, and the
   P25-B harness assertion count, each recorded as a number (or a skip-with-reason), with
   any pre-existing flakes called out (the known P17-D-C / P22-E3 date-roll flakes are
   documented, not hidden).
6. **Known warnings.** Every console warning, deprecation, or skip recorded with a reason;
   no silent truncation (a silent cell reads as "covered everything" when it did not).
7. **Demo script.** A short, repeatable, copy-safe walkthrough: log in as an identity-only
   global `super_admin`, traverse the sidebar, open one detail per capability group, drive
   one record / action / approval / triage / closeout form that the invariants permit, and
   show the deny path for a tenant-contextual `super_admin`.
8. **Defect list.** Any readiness defect found (a clipped control, an overlap, an
   inconsistent tone, a missing empty state, a regression of a display invariant) is
   recorded as a defect for a later, separately approved fix slice -- not fixed inline by
   P25-B (P25-B is a harness, not a feature slice).

## 7. Acceptance Criteria

A future P25 validation pass is accepted only when all of the following hold:

1. **P25-A is docs and ledger only.** No runtime code, backend, frontend, migration,
   alembic change, table, test code, or dependency change ships in P25-A.
2. **P25 is readiness, not a capability.** No P25 slice adds a new platform route, task
   type, closeout state, action, governed slice, or notification channel.
3. **The route inventory is the as-built inventory.** Every route P25 validates is in the
   section 3 set, and every route in the section 3 set exists in the as-built
   `AppRouter.tsx` `PlatformRoute` subtree; none is invented, none is silently dropped.
4. **The identity-only guard is preserved.** Every validated route remains behind
   `PlatformRoute` (global `super_admin`, `tenant_id == null`); the tenant-contextual
   `super_admin` deny path and the non-super_admin deny path are both exercised.
5. **Empty state is present on every route.** No validated route renders a blank pane or a
   stack trace on empty data.
6. **Loading state is present on every route.** No validated route flashes empty-then-data
   as an error.
7. **Error state is present and redacted on every route.** A failed backing read renders a
   redacted error (no raw payload, no secret, no DSN, no stack).
8. **Denied state is present on every route.** A 401 / 403 / missing-role renders a denied
   state, never a leak.
9. **Sidebar navigation is correct.** Every route (or its parent group) is reachable from
   the sidebar; the active-link highlight is correct on each route; the sidebar is hidden
   from non-platform-admin operators.
10. **Detail and forms are reachable.** Every detail view and every record / action /
    approval / triage / closeout form the invariants permit is reachable from its list.
11. **Copy is leak-safe.** On-screen text across the validated routes contains no secret,
    DSN, host:port, token, cookie, auth header, raw payload, shell, SQL, or tenant payload
    (the never-leaked list).
12. **No clipped text and no overlapping controls** at the validated viewport(s).
13. **Console consistency holds.** `source_unknown`, `backup_check_warning`, and terminal
    success render in the same tone / badge convention across the P22, P23, and P24
    consoles.
14. **`source_unknown` is never shown healthy** in any validated route.
15. **`backup_check_warning` is never shown as success** in any validated route.
16. **No tenant leak.** No validated route exposes tenant-A data in tenant-B context.
17. **No forbidden control.** No validated route surfaces an execute / approve /
    flag-mutate / deliver control that the prior-phase invariant forbids (e.g. no bare
    "execute" button on the controlled-actions console; no "deliver notification" button on
    the operator-tasks console; no "clear flag" control on the incident-closeouts console
    beyond invariant-mirror prose).
18. **No migration.** No P25 slice adds an alembic change, table, column, index, or seed.
19. **No product branch merge.** P25 is not merged into `platform-dev` or
    `product-dev-recovered` without a separate CTO-approved merge step; the feature branch
    is pushed with an explicit `X:X` refspec and `origin/platform-dev` is left unchanged.
20. **No auth / RBAC rewrite.** P25 reuses the `PlatformRoute` guard and the existing
    roles / session transport unchanged.
21. **No P22 execution expansion.** P25 adds no governed action, dispatches no worker, and
    widens no allowlist.
22. **No notification delivery.** Notification events stay at `delivery_state == recorded`.
23. **Evidence is complete and scrubbed.** The section 6 evidence set is produced (route
    list, matrix, screenshots, commands, test counts, known warnings, demo script, defect
    list); every screenshot and transcript is scrubbed against the never-leaked list; no
    silent skip is recorded as a pass.
24. **P25-B stays a harness.** A later P25-B is a non-shipping, non-merging frontend
    validation / smoke harness only; it implements no feature unless separately approved.
25. **Validation, ASCII, secret-baseline, and forbidden-path gates are clean.** `git diff
    --check` is clean; the new docs are pure ASCII; detect-secrets passes against the
    configured baseline (the baseline file itself is not modified); the changed paths are
    docs / ledger only.

## 8. Counterexamples (must fail or be rejected)

1. **C1 -- a new backend capability under P25.** A P25 slice that adds a route handler,
   service, model, task type, closeout state, action, or governed slice -- rejected; P25 is
   readiness, not a capability.
2. **C2 -- a migration under P25.** A P25 slice that adds an alembic change, table, column,
   index, or seed -- rejected; P25 changes no storage.
3. **C3 -- a merge into `platform-dev` or `product-dev-recovered` under P25.** A P25 slice
   that fast-forwards or merges into either -- rejected; P25 stays on its feature branch
   until a separate CTO-approved merge.
4. **C4 -- a push to `platform-dev`.** A P25 push that updates `origin/platform-dev`
   (e.g. a bare `git push` after a worktree created from `origin/platform-dev`) --
   rejected; the feature branch is pushed with an explicit `X:X` refspec only.
5. **C5 -- a product business mutation under P25.** A P25 slice that reads or writes an
   order / payment / invoice / customer / inventory / ledger record -- rejected.
6. **C6 -- an auth / RBAC rewrite under P25.** A P25 slice that changes the `PlatformRoute`
   guard, the roles, the session transport, or the tenancy model -- rejected without a
   separately approved contract.
7. **C7 -- a P22 execution expansion under P25.** A P25 slice that adds a governed action,
   dispatches a worker, runs a real `backup.check` beyond the P22-G read-only binding, or
   widens the v0 allowlist -- rejected.
8. **C8 -- real notification delivery under P25.** A P25 slice that wires an in-app push,
   email, or webhook channel -- rejected; events stay at `delivery_state == recorded`.
9. **C9 -- a readiness sign-off without the empty state.** A route signed off ready whose
   empty state was never exercised -- rejected; the empty cell is a required matrix cell.
10. **C10 -- a readiness sign-off without the error / denied state.** A route signed off
    ready whose error and denied states were never exercised -- rejected.
11. **C11 -- a route omitted from the inventory.** A readiness pass that skips an as-built
    `PlatformRoute` route (e.g. `/platform/audit` or `/platform/ops/noisy-neighbors`) --
    rejected; the inventory is closed.
12. **C12 -- an invented route in the inventory.** A readiness pass that validates a route
    that does not exist in the as-built `AppRouter.tsx` -- rejected; the inventory is
    grounded in the code.
13. **C13 -- the identity-only guard bypassed.** A readiness pass that admits a
    tenant-contextual `super_admin` or a non-super_admin to a platform route -- rejected;
    the deny path is mandatory.
14. **C14 -- `source_unknown` shown healthy.** A validated route that renders `source_unknown`
    in a success / healthy tone -- rejected; the P23 / P24 invariant is not relaxed by P25.
15. **C15 -- `backup_check_warning` shown as success.** A validated route that renders a
    warning / `completed_with_warning` outcome as success -- rejected.
16. **C16 -- a clipped or overlapping control accepted as ready.** A route signed off ready
    with clipped text or overlapping controls at the validated viewport -- rejected.
17. **C17 -- inconsistent console tone accepted as ready.** A readiness pass that accepts
    different tones for the same status across the P22 / P23 / P24 consoles -- rejected.
18. **C18 -- a tenant leak in the readiness sweep.** A validated route that exposes
    tenant-A data in tenant-B context, accepted as ready -- rejected.
19. **C19 -- a forbidden control surfaced.** A validated route that surfaces a bare
    "execute", "deliver notification", or "clear flag" control the prior-phase invariant
    forbids -- rejected.
20. **C20 -- a secret / payload leak in evidence.** A screenshot or transcript committed
    with a secret, DSN, token, cookie, auth header, raw payload, or real tenant business
    data -- rejected; evidence is scrubbed against the never-leaked list.
21. **C21 -- a silent skip recorded as a pass.** A matrix cell recorded as pass without an
    executable command, screenshot, or honest skip-with-reason -- rejected; a silent skip
    reads as "covered everything" when it did not.
22. **C22 -- P25-B implements a feature.** A P25-B slice that ships a new feature (not a
    validation / smoke harness), or that is merged / shipped -- rejected; P25-B is a
    harness only, behind the section 9 gate.

## 9. P25-B Entry Gate (future)

A future P25-B is permitted to implement **only a non-shipping, non-merging frontend
validation / smoke harness** over the as-built P10-P24 surface: a Playwright (or
equivalent) harness that logs in as an identity-only global `super_admin` (or, where no
runnable stack exists, exercises the `PlatformRoute` guard and the page components at the
unit / component level with a mocked backend), traverses the section 3 route inventory,
captures the section 4 matrix per route (empty / loading / error / denied / navigation /
copy / no-overlap / consistency / invariant), and writes the section 6 evidence set
(route list, matrix result, scrubbed screenshots, commands, test counts, known warnings,
demo script, defect list).

This gate is the counterpart to the P25-A-only non-goals (1.3.1): the harness itself, the
captured screenshots, the matrix runner, and the demo script that are forbidden in P25-A
are exactly the validation harness P25-B may begin to build. The all-P25 non-goals (1.3.2)
bind P25-B equally; nothing in this section relaxes them.

P25-B (and all of P25 before a separately approved feature / fix slice) **must not**:

- add any new platform capability, route, task type, closeout state, action, or governed
  slice;
- add any migration, alembic change, table, column, index, or seed;
- merge into `platform-dev` or `product-dev-recovered`, or push to `platform-dev` (the
  harness branch is pushed with an explicit `X:X` refspec; `origin/platform-dev` is left
  unchanged);
- mutate any product business record (order / payment / invoice / customer / inventory /
  ledger);
- rewrite auth / RBAC / session / tenancy, or relax the `PlatformRoute` identity-only
  global `super_admin` guard;
- expand P22 execution (no new action, no worker dispatch, no allowlist widening);
- deliver any notification (no channel wiring; events stay `delivery_state == recorded`);
- display `source_unknown` as healthy or `backup_check_warning` as success, or accept such
  a regression as ready;
- expose tenant-A data in tenant-B context, or accept such a leak as ready;
- commit a screenshot or transcript that contains a secret, DSN, token, cookie, auth
  header, raw payload, or real tenant business data (evidence is scrubbed);
- ship or merge the harness as a product feature; it is a read-only validation tool;
- fix a readiness defect inline (a clipped control, an overlap, a missing empty state, a
  tone inconsistency, a display-invariant regression); defects are recorded for a later,
  separately approved fix slice;
- record a matrix cell as pass without an executable command, screenshot, or honest
  skip-with-reason;
- touch `product-dev-recovered` or any product business path.

**Any feature implementation, any real defect fix, any auth / RBAC change, any migration,
any execution expansion, and any notification delivery are reserved for separately
approved phases** and must remain behind the never-leaked list and the identity-only
platform-operator guard. P25-B must begin from this contract and may not change the route
inventory, the validation matrix, the readiness definition, the safety boundaries, the
evidence plan, the acceptance criteria, the counterexamples, or the never-leaked list
without a new contract revision accepted by the CTO.

## 10. Docs-Only and Contract-Only Statement

P25-A is docs and ledger only. It creates one contract markdown
(`docs/ai/PLATFORM_PRODUCT_P25_FRONTEND_CUSTOMER_READINESS_CONTRACT.md`), updates the
`docs/ai/README.md` Platform Product Track read order (entry #25 plus a readiness
paragraph), and adds one ledger
(`ai-ledger/platform/2026-07-06_p25a_platform_frontend_customer_readiness_contract.md`).
There is no runtime code, no backend, no frontend, no migration, no alembic change, no
table, no column, no test code, and no dependency change. The branch is pushed with an
explicit `X:X` refspec; `origin/platform-dev` is left unchanged at `e5c28ec`; nothing is
merged. P25-B is not started. The harness, the screenshots, the matrix runner, and the
demo script are reserved for P25-B under the section 9 gate.
