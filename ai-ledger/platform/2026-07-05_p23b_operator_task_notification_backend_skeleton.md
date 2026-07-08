# P23-B -- Operator Task / Notification Queue Backend Skeleton

**Phase:** P23-B Operator Task / Notification Queue (non-executing, non-sending, in-memory backend skeleton)
**Date:** 2026-07-05
**Branch:** `codex/platform-p23b-operator-task-notification-backend-skeleton-2026-07-05`
**Base:** `87f2ead4` (origin/platform-dev -- P23-A operator task / notification queue
contract merged; P22 controlled-execution closeout + first safe governed
backup.check action all merged; P23_FIRST_BACKEND_SKELETON)
**Tip commit:** `e9e8373d` -- `feat(P23-B): operator task / notification queue backend skeleton`
**Author:** Codex (Claude worker)

> **A task is a view, not an executor. A notification is a record, not a delivery.**
> No task state transition executes a P22 action, approves a P19/P20/P21 approval,
> mutates a P17 registry field, or sends any external message. No notification event
> is delivered; it stays at `delivery_state == recorded | suppressed`.

---

## 1. Branch / base / commit chain

- Isolated git worktree at `C:\Users\Jeff0\MPANGO ERP\_p23b_2026-07-05`.
- Created via `git worktree add -b
  codex/platform-p23b-operator-task-notification-backend-skeleton-2026-07-05 <path>
  origin/platform-dev` from the latest `origin/platform-dev` (`87f2ead4`, the P23-A
  merge). Per the worktree-upstream-push gotcha, the branch tracks platform-dev
  locally; feature pushes will use `git push -u origin <br>:<br>` (no bare `git push`).
- Single implementation commit on top of base:
  - `e9e8373d feat(P23-B): operator task / notification queue backend skeleton`
- `origin/platform-dev` is untouched (not merged, not pushed). `product-dev-recovered`
  is untouched. P24 / P25 are not started.

Commit chain: `87f2ead4` (P23-A merge) -> `e9e8373d` (P23-B skeleton). This ledger
ships in a follow-up commit on the same branch.

## 2. Modified files (exactly the P23-B allowed scope)

New package + test + one app.py include + this ledger. No other file changed.

```
backend/api/v1/platform/p23/__init__.py                                 (new)
backend/api/v1/platform/p23/schemas.py                                  (new)
backend/api/v1/platform/p23/services.py                                 (new)
backend/api/v1/platform/p23/routes.py                                   (new)
backend/api/app.py                                                      (modified: P23 router include only)
backend/tests/test_platform_p23_operator_task_queue.py                  (new)
ai-ledger/platform/2026-07-05_p23b_operator_task_notification_backend_skeleton.md  (this ledger)
```

`backend/api/app.py` change is exactly 7 added lines (a router include block,
mirroring the P22 include); no existing line modified, no signature change, no
other app setup touched. (3 pre-existing non-ASCII lines in app.py at 126/165/210
shifted to 126/165/218; P23-B introduced zero new non-ASCII.)

## 3. Exact behavior delivered

**schemas.py** -- closed vocabularies and models, all `extra="forbid"`:
- Task types (exactly 10): `action_request_created`, `approval_pending`,
  `approval_decision_required`, `execution_ready`, `execution_completed`,
  `execution_failed`, `source_unknown`, `backup_check_warning`,
  `incident_followup_required`, `runbook_step_required`.
- States (exactly 9): `open`, `acknowledged`, `in_progress`, `waiting_on_approval`,
  `waiting_on_source`, `completed`, `dismissed`, `expired`, `failed`. Terminal =
  {completed, dismissed, expired, failed}; active = the other five.
- Severity (3): `low | medium | high` (no `critical` auto-execute tier).
- Source statuses: `known | unknown | degraded`. Actor scopes: `platform |
  tenant_contextual`. Owner roles: `super_admin | engineering_operator |
  support_operator`. Audit actor roles add `system`.
- Notification channels `in_app | email | webhook` (planned; none wired) and
  delivery states `recorded | queued_for_delivery | delivered | failed_delivery |
  suppressed` (P23-B only ever produces `recorded` / `suppressed`).
- Section-4.1 transition graph (`ALLOWED_TRANSITIONS`), terminal/active sets,
  default severity per type, force-high types (`source_unknown`,
  `backup_check_warning`, `execution_failed`), and the closed denial-code set.
- 9 models: `OperatorTask`, `OperatorTaskQueue`, `OperatorTaskDetail`,
  `OperatorTaskTransitionRequest`, `OperatorTaskTransitionResponse`,
  `OperatorNotificationEvent`, `OperatorTaskAuditEvent`, `OperatorTaskIntakeEvent`,
  `OperatorTaskIntakeResponse`. No order/payment/invoice/customer/inventory/ledger
  field anywhere; intake is typed/redacted only and rejects raw payload via
  `extra="forbid"`.

**services.py** -- ephemeral, process-local, in-memory read model + state machine:
- `reset_store()` (tests), `audit_log()`, `task_audit_log()`, `notifications_log()`,
  `task_notifications()`, and a public `redact_text()`.
- `upsert_task_from_event(event)`: materializes a task, or dedup-bumps an existing
  ACTIVE task. Dedup via one-way SHA-256 `dedup_key_digest` over
  `(task_type, linked object id, tenant_id, source_status, follow-up variant)`. Many
  events -> one ACTIVE task; terminal tasks are exempt (a recurrence re-opens as a
  NEW task); no cross-tenant dedup (tenant_id is part of the key); idempotent replay
  bumps `updated_at` / re-ranks severity and writes no new task and no duplicate
  success audit.
- `list_tasks(...)`: filters (severity, task_type, state, tenant_id, source_status,
  owner_actor_id, correlation_id) + `limit`/`offset` pagination; ranked severity-DESC
  then recency; `total` + `active_count`. Read-only.
- `read_task(task_id)`: redacted record + full append-only audit history +
  notification events; `None` when missing; dismissed/expired retain full history.
- Presentation-only transitions (each records exactly one `OperatorTaskAuditEvent`):
  `acknowledge_task`, `self_assign_task` (owner only, no state change, grants no
  privilege), `mark_in_progress_task`, `complete_task`, `dismiss_task`. Terminal
  states accept no exit; invalid transitions are rejected and audited as denials.
  Completion requires a redacted evidence note or a linked completed id AND a closed
  linked gate (`linked_gate_open == False`); else denied (`COMPLETE_DENIED_NO_EVIDENCE`
  / `COMPLETE_DENIED_GATE_OPEN`).
- `display_status` is computed (never overridable): `source_unknown` is never healthy
  and `backup_check_warning` is never success -- in every state, including
  `completed`.
- Severity is monotonic upward within a correlation; force-high types force high
  (`_rerank_correlation` lifts active peers).
- `record_notification_event(...)`: delivery_state `recorded` (or `suppressed` when
  the redacted summary is empty); per-(task, channel) in-flight dedup so a replay
  writes no duplicate. Resolves no recipient address and sends nothing.
- A content redactor scrubs every free-text field (DSN schemes, `user:pass@host`,
  `host:port`, `key=value` secrets, Bearer/Authorization/Cookie values, shell/SQL/
  dump tokens) before storage, response, or audit. UTC timestamps throughout.

**routes.py** -- prefix `/api/v1/platform/p23/operator-tasks`, tag `platform-p23`,
8 endpoints, all behind the reused P10 identity-only `require_platform_operator`
guard (no `get_db`, no auth/RBAC rewrite):
- `GET  /tasks` (list + filters + pagination)
- `GET  /tasks/{task_id}` (detail; 404 missing)
- `POST /tasks/{task_id}/acknowledge`
- `POST /tasks/{task_id}/self-assign`
- `POST /tasks/{task_id}/in-progress`
- `POST /tasks/{task_id}/complete`
- `POST /tasks/{task_id}/dismiss`
- `POST /internal/intake` (typed/redacted `OperatorTaskIntakeEvent` only; 201 created
  / 200 deduped).

The actor is the authenticated identity (read from the token via the reused guard),
never the request body (no identity spoof), mirroring P20-B-R1 / P22. Transitions
return 200 accepted / 409 denied / 404 missing.

## 4. Tests and counts

`backend/tests/test_platform_p23_operator_task_queue.py` -- **42 tests, all pass**
(shared `windsurf mpango erp` .venv, PYTHONPATH=worktree backend, MPANGO_ENV=test):

- Closed vocabularies (10 task types, 9 states, terminal/active partition, 3
  severities, no `critical`, channels, delivery states); state-machine graph matches
  contract 4.1; no product-business task type.
- Intake creates then dedups replay; terminal tasks exempt from dedup (re-opens new);
  no cross-tenant dedup; intake rejects raw/product payload (422) and unknown
  task_type (422).
- List filters + severity-DESC ranking + pagination; read detail + 404.
- Transitions: acknowledge, self-assign (owner set, no state change), in-progress,
  complete (evidence + closed gate; evidence-ref accepted; evidence-note stored as a
  digest pointer, redacted note on the audit), invalid transition rejected + audited,
  terminal cannot exit, dismiss keeps audit history.
- Notification event is record-only (`recorded`, never `delivered`), per-(task,
  channel) in-flight dedup; no delivery-channel module imported.
- `source_unknown` never healthy (incl. after completed); `backup_check_warning`
  never success.
- Severity monotonic upward in correlation; force-high types are high.
- Redaction: raw secret / DSN / host:port / Bearer / cookie / pg_dump / DROP TABLE
  scrubbed from text, stored summary, and audit JSON.
- Route auth: 401 (no credential; tenant-contextual token w/o header), 403 (wrong
  operator secret), 200 (valid test-override / operator secret / identity super_admin).
- Route-level transitions end-to-end (200/409/404); self-assign sets owner; intake
  201 then 200.
- App wiring: `app.py` includes the P23 router; the router exposes exactly the 8
  contract endpoints.
- Forbidden-primitive AST scan: no `subprocess`/shell/`pg_dump`/`pg_restore`/worker/
  scheduler/drain/`send_email`/`post_webhook` call tokens; no persistence
  (`alembic`/`migrate`/`sqlalchemy`/`psycopg`), product (`order`/`payment`/`invoice`/
  `customer`/`inventory`/`ledger`/`billing`), or P22-execution (`p22.governed_execution`/
  `p22.services`/`p22.adapters`) imports; `p23.services` exposes no
  execute/dispatch/drain/deliver/schedule function name.

Sibling regression (in-memory skeletons, same harness, no DB): **446 tests pass** --
P22 controlled execution + P22-E1 seam + P22-G governed backup.check + P21 adapter
skeleton + P20 governance + P19 approval workflow + P18 controlled actions + P10
contracts. (DB-dependent platform suites were not run in this worktree; the only
non-P23 file touched is `app.py`, whose change is an additive router include, and
those suites are unaffected by route registration.)

## 5. GitNexus result

Index built for the worktree repo (`_p23b_2026-07-05`):
- `npx gitnexus analyze` -> **9,001 nodes | 27,535 edges | 571 clusters | 300 flows**
  (per the analyze-count-variance note, these wobble +/-2-3 across fresh rebuilds;
  edges/flows stable; recorded as observed).

`detect_changes` (MCP, scope `compare`, base `origin/platform-dev`, repo
`_p23b_2026-07-05`):
- summary: `changed_count 82, affected_count 13, changed_files 6, risk_level high`.
- `changed_symbols`: **all P23-B-internal** (the new `p23/{__init__,schemas,services,
  routes}.py` symbols, the eight `Route:/tasks/...`, and `Route:/internal/intake`)
  plus the one pre-existing symbol edited -- `Function:backend/api/app.py:configure_app`
  and `File:backend/api/app.py` (the router-include site). No product-business symbol
  in the changed set.
- The MCP stdio driver is flaky for this large response (the tool returned the
  summary + changed_symbols on the first run; subsequent re-captures of the literal
  13-entry affected list timed out under stdio framing). The affected set is
  corroborated below by the `impact` CLI on the single pre-existing modified symbol.

`npx gitnexus impact configure_app --repo _p23b_2026-07-05` (the only pre-existing
symbol touched; additive `include_router` inside it):
- `impactedCount 4`, **`risk LOW`**, `summary { direct: 1, processes_affected: 0,
  modules_affected: 0 }`, `affected_processes: []`, `affected_modules: []`.
- Blast radius (upstream): `backend/main.py` (CALLS configure_app, depth 1),
  `backend/api/dependencies_jobs.py`, `backend/api/v1/exports.py` (IMPORTS, depth 2),
  `backend/api/app.py` (depth 3). All app-bootstrap-internal; **0 product-business
  processes, 0 product-business modules**.

Risk interpretation: `detect_changes risk_level high` reflects the volume of new
code (changed_count 82 in a brand-new package), not product-business blast radius.
The new `p23` package is imported by nothing except the additive `app.py` include,
so it cannot affect any existing flow except by registering new routes under
`/api/v1/platform/p23/*`. The `impact` analysis confirms the single pre-existing
edit has LOW risk and 0 processes / 0 modules affected. **All affected flows are
platform-P23-internal / app-bootstrap-internal; zero product-business flows are
affected.** The HIGH/CRITICAL stop condition (any product-business flow affected)
is not triggered.

## 6. Forbidden audit (scope guard)

Only `backend/api/v1/platform/p23/*`, `backend/api/app.py` (router include only),
`backend/tests/test_platform_p23_operator_task_queue.py`, and this ledger are
touched. Verified absent:
- no frontend;
- no migrations / alembic / env.py / ORM models / tables / columns;
- no package / lockfile / dependency change;
- no auth / RBAC / session rewrite (the reused P10 identity-only guard is consumed
  unchanged; no new token / role / session model);
- no `product-dev-recovered` or product business path
  (orders/payments/invoices/customers/inventory/ledger/billing);
- no P22 action execution (no `p22.governed_execution` / `p22.services` /
  `p22.adapters` import; no execute/dispatch/drain function);
- no backup/restore/pg_dump/script/subprocess/shell/worker/queue-drain/scheduler;
- no real notification delivery (no `smtplib`/`socket`/`requests`/`httpx`/`aiohttp`/
  slack/push import; notification events stay `recorded | suppressed`);
- no P24 / P25.

## 7. Validation run

- `git diff --check origin/platform-dev..HEAD` (and working tree): clean, no
  whitespace errors.
- Changed files: exactly the 7 listed in section 2.
- Non-ASCII scan: 0 new non-ASCII lines introduced by P23-B (all p23 files + the
  test are pure ASCII; the 3 non-ASCII lines in `app.py` are pre-existing on
  `origin/platform-dev` at 126/165/210, renumbered to 126/165/218 by the insert).
- detect-secrets (1.5.0) against the configured baseline (`.secrets.baseline` at
  repo root): **0 findings** on all changed files (the two intentional fake-secret
  redaction fixtures in the test are assembled at runtime so no source line carries
  a literal `user:pass@host` token; the baseline was not modified). Pre-commit hooks
  (trim trailing whitespace, fix end of files, detect-secrets) all **Passed** at
  commit time.
- Forbidden path audit: all changed paths within the P23-B allowed scope (section 6).
- P23 targeted tests: **42 passed**.
- P22/P21/P20/P19/P18/P10 regression subset (in-memory skeletons): **446 passed**.
- `npx gitnexus analyze`: success (counts in section 5); `detect_changes` + `impact`
  in section 5.
- Worktree clean of stray/temp files; code committed.

## 8. Risk / blockers

- **Risk:** LOW to the platform; NONE to product business. `detect_changes` reports
  `risk_level high` purely from new-code volume (changed_count 82); `impact
  configure_app` reports LOW with 0 processes / 0 modules affected. All affected
  flows are platform-P23-internal / app-bootstrap-internal. No product-business flow
  is affected.
- **Blockers:** none.
- **Open / deferred (by design, not blockers):** the read model is in-memory and
  resets per process; there is no persisted store, no worker, no scheduler, no
  drain loop, no real notification channel, and no frontend. Real persistence,
  delivery, and the queue UI are reserved for separately approved future phases.
  DB-dependent platform suites were not re-run in this worktree (no DB env); the
  only non-P23 change is an additive router include.

## 9. Explicit statements (P23-B entry gate)

- A task is a view, not an executor.
- A notification is a record, not a delivery.
- No P22 action is executed by any task transition.
- No real notification is sent (events stay `recorded | suppressed`).
- No migration, no alembic change, no table, no column.
- No frontend.
- No auth / RBAC / session / tenancy rewrite (reused P10 identity-only guard).
- No product business path touched; no tenant business mutation.
- `origin/platform-dev` and `product-dev-recovered` are untouched (not merged, not
  pushed).
- P24 / P25 are not started.
