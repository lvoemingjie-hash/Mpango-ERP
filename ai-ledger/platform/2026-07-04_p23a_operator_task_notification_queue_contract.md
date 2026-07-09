# P23-A Operator Task / Notification Queue Contract

Date: 2026-07-04
Phase: P23-A (contract-only design for the operator task / notification queue; the task
type catalog and exclusions, task triage state machine, data-model plan, notification
event boundary, queue API plan, frontend plan, RBAC visibility boundary, task audit
contract, severity / dedup / correlation rules, acceptance criteria, and counterexamples
that bound all later P23 implementation).
Branch: codex/platform-p23a-operator-task-notification-queue-contract-2026-07-04
Base: origin/platform-dev = 18306b1 (P22 controlled execution closeout and first safe
governed backup.check action: P22-A contract, P22-B non-executing execution skeleton,
P22-C console, P22-D readiness lock, P22-E0 runtime governed adapter contract, P22-E1
runtime governed adapter seam skeleton, P22-E2 backup status source discovery, P22-E3
read-only backup.check binding, P22-E4 backup.check console, P22-F closeout, and P22-G
first safe governed backup.check action all merged; P22_FIRST_SAFE_GOVERNED_ACTION_READY).
Scope: docs / ledger only. No new feature, no backend runtime code, no frontend runtime
code, no migration, no alembic change, no package or lockfile change, no test code.

This phase defines the operator task / notification queue contract only. It does not
implement, execute, approve, dispatch, queue, schedule, deliver, migrate, or merge
anything into platform-dev. It is an isolated, docs-only branch. P23-B is not started.

## 1. Phase inventory

P23-A - operator task / notification queue contract (docs-only)
- Source branch: codex/platform-p23a-operator-task-notification-queue-contract-2026-07-04
- Base: origin/platform-dev = 18306b1
- Report path: ai-ledger/platform/2026-07-04_p23a_operator_task_notification_queue_contract.md
  (this file)
- Scope: docs-only contract for the operator task / notification queue on top of P17
  through P22 (task type catalog + exclusions, triage state machine, data-model plan,
  notification event boundary, queue API plan, frontend plan, RBAC visibility, task audit
  contract, severity / dedup / correlation rules, future AI Operator Copilot boundary)
- Risk: LOW (docs-only, no runtime code, no migration, no execution, no approval, no
  notification delivery, no storage switch)
- Status: contract on isolated branch; not merged to platform-dev

## 2. Capability statement

P23-A defines (contract only, no runtime code) the operator task / notification queue
layer that aggregates the work P17 through P22 already produce but leave scattered: P18
created action requests, P19 / P20 / P21 gathered and durably stored approval, and P22
defined and (for backup.check) performed governed execution, but each left its piece of an
incident on its own page and ledger. P23 turns those events into a single, deduplicated,
severity-ranked, tenant-scoped queue of operator tasks with typed follow-ups, a triage
state machine, and evidence links back to the P18 / P19 / P20 / P21 / P22 / P17 ids, plus
a notification event boundary. After P23-A is accepted, a future P23-B may implement --
under its own entry gate -- a NON-EXECUTING, NON-SENDING backend skeleton (an in-memory
read model that materializes tasks from prior-phase events, task-state management
endpoints as pure state transitions, dedup / severity / correlation logic, and tests); a
real persisted queue / worker, real notification delivery, and the Operator Task Queue
frontend are each reserved for separately approved phases. P23-A fixes the boundary for:

- Task type catalog: exactly ten types (action_request_created, approval_pending,
  approval_decision_required, execution_ready, execution_completed, execution_failed,
  source_unknown, backup_check_warning, incident_followup_required,
  runbook_step_required), each mapped to the prior-phase event(s) that materialize it, the
  suggested owner role (presentation only, not authorization), the default severity, and
  the follow-up. The v0 executor / checker visibility is always bounded by the existing
  P10 / P18 / P20 / P22 identity-only guard.
- Explicit exclusion list (never a P23 task): product business tasks, tenant business
  payload, synthetic execution tasks, self-approved / auto-approved tasks, cross-tenant
  broadcast tasks, and channel-specific delivery tasks.
- Task triage state machine: nine states (open, acknowledged, in_progress,
  waiting_on_approval, waiting_on_source, completed, dismissed, expired, failed) with
  allowed / forbidden transitions; terminal states accept no exit; completion requires
  evidence and a closed linked gate; NO transition executes a controlled action, approves
  an approval, or mutates a registry field. The state machine is a presentation / triage
  lifecycle, entirely separate from the P19 / P20 / P21 approval state machine and the P22
  execution-record state machine.
- Data-model plan (planning only): logical platform_operator_task (task_id, task_type,
  severity, state, tenant_id scoped id only, actor_scope, owner_role / owner_actor_id,
  correlation_id, linked_action_id / linked_approval_id / linked_execution_id /
  linked_dry_run_ref / linked_source_ref / linked_incident_id, summary_redacted,
  reason_redacted, evidence_ref, source_status, dedup_key_digest, ttl_expires_at,
  redaction_applied, timestamps) and logical platform_operator_notification_event
  (event_id, task_id, channel enum in_app / email / webhook, delivery_state default
  recorded, severity, tenant_id, actor_scope, recipient_role, summary_redacted,
  correlation_id, redaction_applied, created_at); indexes, a dedup unique over active
  states (Postgres partial-unique discipline, scoped to active states not a NULL column),
  source-link indexes, and the relationship to P18 / P19 / P20 / P21 / P22 / P17 ids as
  evidence pointers only. P23-A creates NO table, NO migration, NO ORM model, NO enum
  column.
- Notification boundary: a notification event is a record of attention, not an outbound
  delivery; P23-A defines the event shape, the closed channel enum, and the never-leaked
  list, and names future channels (in-app, email, webhook) it does not implement;
  delivery_state stays recorded; no recipient address is resolved; no retry / escalation
  engine.
- Queue API plan (planning only): GET operator-tasks, GET operator-tasks/{id}, POST
  acknowledge, POST assign, POST in-progress, POST complete (with evidence; rejects if the
  linked gate is still open), POST dismiss; all behind the P10 identity-only
  platform-operator guard; none executes a P22 action, approves an approval, or mutates a
  registry field.
- Frontend plan (planning only): Operator Task Queue page, task detail drawer, filters
  (severity / type / state / tenant / source / owner / correlation_id), evidence links
  into P12 / P13 / P22 read-only views (never an execute / approve button), empty / error
  / loading states, and a notification badge that counts records of attention (no
  delivery, no execution).
- Security / RBAC boundary: identity-only platform-operator visibility
  (support_operator, engineering_operator, super_admin) reusing the existing auth / RBAC
  / session transport; no auth rewrite; tenant scope enforced at the read; owner is
  presentation, not authorization; runtime authorization left to the existing P10 / P18 /
  P20 / P22 per-action boundary.
- Audit contract: every task state change is auditable in a future phase with actor,
  transition, previous_state, next_state, reason_redacted, correlation_id, and linked
  object ids; one event per transition; append-only; the never-leaked list applies in
  full.
- Severity / dedup / correlation rules: three severity levels (low / medium / high) with
  no critical auto-execute tier, monotonic-upward-within-a-correlation ranking, and
  never-lowered-to-healthy; many-to-one event-to-task dedup via dedup_key_digest over
  (task_type, linked object id, tenant_id, source_status, follow-up variant), terminal
  tasks exempt, no cross-tenant dedup, replays idempotent; correlation_id threads P18 ->
  P19 -> P20 -> P21 -> P22 -> P15 -> P17 events into one triage thread.
- Future AI Operator Copilot boundary: the AI may read the queue and propose triage
  actions / draft evidence notes, may apply a triage action only after explicit operator
  confirmation, can never execute / approve / auto-dismiss / auto-complete, every AI
  action is audited, AI tool calls are linked to the task and underlying ids, and real
  delivery / execution stay separately gated.

## 3. Safety statement

- A task is a view, not an executor, and a notification is a record, not a delivery. No
  task state transition -- acknowledge, assign, in_progress, complete, dismiss -- executes
  a P22 action, approves a P19 / P20 / P21 approval, bypasses a checker, or mutates a
  registry field. P23-A defines the queue contract; it performs no execution, no
  approval, and no delivery.
- No real controlled action execution, no approval, and no notification delivery exists
  anywhere in P23-A (contract only). The queue aggregates and presents; it never
  short-circuits a gate that P17 through P22 put in place.
- No tenant business mutation: no order, payment, invoice, customer, inventory, or ledger
  record is read or written by any task or notification (contract forbids it for all
  future P23 phases; tenant_id is a scoped identifier only, never a business payload and
  never joinable to business tables).
- No product business task: the queue carries platform operational tasks only; an order /
  payment / invoice / customer / inventory / ledger follow-up is a product concern, not a
  platform P23 task.
- No migration and no storage switch: no migrations, alembic changes, tables, or columns
  are introduced in P23-A. P23-A changes no P17 / P18 / P19 / P20 / P21 / P22 table,
  field, enum, or migration.
- No auth / RBAC rewrite: P23-A reuses the P10 identity-only platform-operator guard and
  the existing operator roles conceptually; no new auth transport, token, session, or
  role is defined or implemented.
- Redaction-before-record is total by contract: the P10 allowlist applies before any
  record, response, audit, or notification field; redaction_applied == true is required
  everywhere; the never-leaked list (raw secrets / DSNs / host:port / tokens / cookies /
  auth headers / raw idempotency key / raw request or response body / shell / SQL /
  tenant payload / log lines) binds every task, notification, response, queue item, and
  audit event.
- Audit history is never deleted: dismissed and expired remove a task from the active
  queue only; the underlying P18 / P19 / P20 / P21 / P22 / P17 audit trail is retained;
  the queue is a view, not the system of record.
- Unknown is never healthy and a warning is never a success: source_unknown is never
  displayed healthy and cannot be completed as healthy; a backup_check_warning
  (P22-G completed_with_warning) is never displayed as success (P10 / P17 / P22 rule,
  carried into P23).
- No tenant data leak across contexts: a task scoped to tenant A is never visible to an
  operator in tenant B's context; cross-tenant visibility requires the identity-only
  platform-scope path and is audited.
- No AI agent execution or auto-approval: P23-A names a future AI Operator Copilot
  boundary only; it grants no AI the power to execute, approve, auto-dismiss, or
  auto-complete a task.

## 4. Verification (docs-only branch, all must pass)

Verified on this branch versus origin/platform-dev = 18306b1:

- git diff --check origin/platform-dev..HEAD : clean (no whitespace errors).
- Commit: branch tip (short SHA recorded in the session report; kept out of this file so
  the ledger stays non-self-referential; no 40-char SHA in this file).
- Changed files exactly equal three docs / ledger files:
  - docs/ai/PLATFORM_PRODUCT_P23_OPERATOR_TASK_NOTIFICATION_QUEUE_CONTRACT.md (new)
  - docs/ai/README.md (Platform Product Track read order updated; P23 entry + paragraph)
  - ai-ledger/platform/2026-07-04_p23a_operator_task_notification_queue_contract.md (new,
    this file)
- Non-ASCII scan of the three files: 0 hits (pure ASCII; no section sign, box-drawing, em
  dash, middot, smart quotes, or arrows).
- detect-secrets (detect-secrets-hook against the configured secret baseline) on the three
  files: PASS, exit 0, no new secrets. The configured baseline file was not modified
  (working-tree status clean for it). No 40-char SHAs are present in any new file.
- Forbidden path audit (changed paths under backend/, frontend/, migrations/, alembic/,
  package or lock files, auth / RBAC / session, payment / billing, tenant business code,
  product-dev-recovered/, .github/, .claude/, or the configured secret baseline): 0 hits.
- npx gitnexus analyze : graph intact; no execution / approval / delivery flow affected by
  a docs-only change.
- GitNexus detect_changes (MCP, tools/call) compare base_ref origin/platform-dev vs HEAD
  on this repo: risk_level none, changed_count 0, affected_count 0, message "No changes
  detected", changed_symbols [], affected_processes []. Markdown docs / ledger files are
  not code symbols in the knowledge graph, so a docs-only change yields zero changed code
  symbols and zero affected runtime processes -- the cleanest possible docs-only result,
  and strictly stronger than the risk-level "low" seen with older gitnexus versions that
  indexed markdown File / Section nodes. (The detect_changes tool is MCP-only; it was
  driven over stdio JSON-RPC against `npx gitnexus mcp`, which serves all indexed repos,
  with base_ref and repo parameters per call.)
- Working tree clean after commit.

## 5. GitNexus summary

- P23-A is docs-only: a contract markdown doc, a README read-order edit, and a ledger. No
  runtime symbols, no execution-flow impact, no approval-flow impact, no
  notification-delivery impact.
- detect_changes (MCP) base_ref origin/platform-dev vs HEAD : risk_level none / 0 changed
  code symbols / 0 affected runtime processes (changed_symbols [], affected_processes [],
  "No changes detected"). Verified on this branch. The change adds documentation only; no
  backend, frontend, migration, package, auth, payment, tenant, product, or
  notification-sender path is touched.

## 6. Forbidden audit summary

P23-A touches none of the following (all verified by the changed-path audit):

- No backend / runtime code path.
- No frontend code path.
- No migration or alembic change.
- No payment or billing change.
- No package.json, pnpm-lock, package-lock, or yarn.lock change.
- No product-dev-recovered path.
- No auth / RBAC / session rewrite.
- No .github / CI change.
- No .claude change.
- No change to the configured secret baseline.
- No execution path (contract only; a task is a view, not an executor; no v0 action, no
  approval, and no notification delivery is performed in P23-A).
- No tenant mutation path (tenant_id is a scoped identifier only; tasks target platform
  requests / approvals / executions / source status / incident follow-up / runbook steps
  only).
- No notification-sender path (the notification event is a record of attention;
  delivery_state stays recorded; no channel is wired).

## 7. Open risks / non-goals

The following are intentionally not done in P23-A and are NOT P23-A blockers. They are
deferred to P23-B (and later) under their own entry gates, contract-first:

- Non-executing, non-sending backend skeleton (in-memory read model that materializes
  tasks from prior-phase events, task-state management endpoints as pure state
  transitions, dedup / severity / correlation logic, tests) -- P23-B only; no execution,
  no approval, no delivery, no worker, no scheduler.
- Real persisted queue / worker / scheduler / drain loop -- a separately approved future
  phase; not a hidden execution or delivery path.
- Real notification delivery (in-app push, email, webhook) -- a separately approved future
  phase; bound by the never-leaked list and the identity-only platform-operator guard.
- Operator Task Queue frontend (page, drawer, filters, badge) -- a separately approved
  future slice.
- Materialization from live prior-phase event streams / webhooks / polling -- P23-B (or
  later) decides the source-of-truth read path; P23-A only plans the logical read model.
- Lifting any P23 exclusion (product business task, tenant payload, synthetic execution,
  auto-approval, cross-tenant broadcast, channel delivery) -- a new contract revision
  accepted by the CTO and a new phase.
- AI Operator Copilot implementation (named as a future boundary only; no AI execution /
  approval / auto-triage power, no AI-specific runtime code in P23-A).
- Emergency override / auto-dismiss / auto-complete (forbidden by default; any override
  requires a separately approved future contract).

## 8. P23-B entry gate

P23-B may implement ONLY a non-executing, non-sending backend skeleton: an in-memory (or
existing-safe) read model that materializes tasks from prior-phase events, the task-state
management endpoints (acknowledge / assign / in-progress / complete / dismiss) as pure
state transitions, the dedup / severity / correlation logic, and unit tests, wired to the
P18 / P21 / P22 read paths and the P10 identity-only guard. P23-B must not execute any P22
action, approve any approval, mutate any registry field, or deliver any notification (no
in-app push, no email, no webhook); must not add a real queue worker, drain loop,
scheduler, or escalation engine unless separately and explicitly approved; must not add
any migration, alembic change, table, or column unless explicitly approved in the P23-B
contract review (an in-memory / existing-safe read model is preferred); must not implement
any frontend; must not carry any product business task or tenant business payload; must
not rewrite auth / RBAC / session; must not delete or truncate audit history on dismiss /
expire; must not display source_unknown or backup_check_warning as healthy / success; and
must not touch product-dev-recovered. Real notification delivery and a persisted queue /
worker are reserved for separately approved phases and must stay behind the never-leaked
list and the identity-only platform-operator guard. P23-B must begin from this contract
and may not change the task type catalog, the exclusion list, the state machine, the
data-model fields, the notification boundary, the API shapes, the RBAC visibility rules,
the audit fields, the dedup / severity / correlation rules, or the never-leaked list
without a new contract revision accepted by the CTO.

## 9. Final verdict

P23-A_CONTRACT_READY (docs-only, isolated branch, not merged to platform-dev).

P23-A defines the operator task / notification queue contract only. There is no runtime
code, no migration, no execution, no approval, no notification delivery, no tenant
mutation, no product business task, no tenant data leak across contexts, no auth / RBAC
rewrite, no frontend, no backend, no AI agent execution or auto-approval, no deletion of
audit history on dismiss / expire, no source_unknown displayed healthy, no
backup_check_warning displayed as success, and no change to the configured secret
baseline. P23-B is not started. A task is a view, not an executor, and a notification is a
record, not a delivery.
