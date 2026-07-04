# Platform Product P23 -- Operator Task / Notification Queue Contract

**Status:** Contract only (P23-A). No runtime code, no backend handlers, no frontend
UI, no migrations, no alembic changes, no tests, and no dependency changes. Accepted by
the CTO before any P23-B backend skeleton may begin.
**Phase:** P23-A Operator Task / Notification Queue Contract
**Date:** 2026-07-04
**Base:** `18306b1` (origin/platform-dev -- P22 controlled execution closeout and first
safe governed backup.check action: P22-A contract, P22-B non-executing execution
skeleton, P22-C console, P22-D readiness lock, P22-E0 runtime governed adapter contract,
P22-E1 runtime governed adapter seam skeleton, P22-E2 backup status source discovery,
P22-E3 read-only backup.check binding, P22-E4 backup.check console, P22-F closeout, and
P22-G first safe governed backup.check action all merged; P22_FIRST_SAFE_GOVERNED_ACTION_READY)
**Depends on:** P10 (identity-only super_admin guard, PlatformAuditEvent, source-status
vocabulary, redact_metadata allowlist), P11 (Platform Admin Cockpit boundary), P12
(Support Console support-safe subset), P13/P14 (Operations Observability plus
unavailable_reason / degraded_reason), P15 (Incident Triage read-only contract), P16
(Worktree Execution Harness), P17 (Platform Registry, Tenant Lifecycle, and backup /
status source contract + schema plan + read wiring), P18 (Controlled Platform Actions
Contract: action catalog, classification, permission matrix, action request layer, the
`executed` flag, ControlledActionAuditEvent), P19 (Approval Workflow Contract: approve
resolves to execution_blocked), P20 (Durable Approval Governance Contract: persistent
record shape, dual-control policy, execution readiness gate, durable audit, state machine,
approved_execution_blocked ceiling), P21 (Durable Approval Store Contract + schema plan +
public durable tables + runtime adapter + closeout: durable storage records, restart-safe
consistency, digest-only idempotency, redaction-before-persistence, durable append-only
audit, retention / purge / export, API compatibility), P22 (Controlled Execution v0
Contract + non-executing skeleton + console + readiness lock + runtime governed adapter
contract + seam skeleton + backup status source discovery + read-only backup.check
binding + backup.check console + closeout + first safe governed backup.check action: v0
allowlist, dry-run model, execution request / result lifecycle, execution audit,
idempotency, safety rules, operator separation, runtime governed action adapter seam,
recorded-request-bound read-only completion).
**Author:** Codex (Claude worker)

---

## 1. Goal and Non-Goals

### 1.1 Goal

P18 created controlled action *requests*. P19 *approved / rejected* them. P20 added
maker-checker / quorum *governance*. P21 made approvals *durable*. P22 defined the
controlled *execution* layer and, in P22-G, landed the first safe, read-only, governed
`backup.check` completion. Across P17 through P22 the platform built one disciplined
pipeline: a request is opened, an approval is gathered, a dry-run is run, an action is
executed (or honestly fails), and every step is audited.

What the platform does **not** have is a single place where an on-call operator *sees*
that pipeline as work to do. Today the same incident is scattered across the P18 request
list, the P19 / P20 / P21 approval queue, the P22 execution-record table, the P22-G
backup.check completion, and the P17 backup / status source. An operator has to know
which page to open, in which order, and what each row means, before they can act. Things
fall through the cracks: an approval that needs a second checker, a `backup.check` that
came back `completed_with_warning` because the source was stale, a `provisioning.recheck`
whose source is `unknown`, an incident flag whose follow-up runbook step is owed.

P23 is the **operator task / notification queue** layer. It is the *aggregation and
presentation* boundary on top of P17 through P22. P23 turns the events those phases
already emit into a single, deduplicated, severity-ranked, tenant-scoped queue of
operator tasks, each carrying a typed follow-up, a state machine, and a link back to the
underlying evidence. P23 also defines the **notification event** boundary: a recorded
"this needs attention" event that future channels (in-app, email, webhook) may consume,
but that P23-A does not deliver.

P23 is deliberately the *least* powerful layer in the platform. It adds **no new
execution capability, no new approval capability, no new mutation capability, and no new
auth capability**. Its only power is to surface and triage. The single most important
invariant of P23, repeated throughout this document:

> **A task is a view, not an executor. A notification is a record, not a delivery.** No
> task state transition -- acknowledge, assign, mark in_progress, complete, dismiss --
> executes a P22 action, approves a P19 / P20 / P21 approval, bypasses a checker, mutates
> a registry field, or sends any external message. P23 aggregates and presents the work
> the platform already produces; it never short-circuits a gate that P17 through P22 put
> in place. A `dismissed` task removes it from the active queue; it never deletes the
> audit history behind it. A notification event marks "attention required"; it never
> transmits a secret, a raw payload, a DSN, a host, a port, or a log line.

P23-A fixes the boundary before any queue code is written:

1. The **task type catalog**: the closed set of operator task types P23 may produce,
   each mapped to the prior-phase event(s) that materialize it, and the explicit
   exclusion list (no product business task, no tenant business payload, no synthetic
   execution task).
2. The **task state machine**: the states a task may pass through (`open`,
   `acknowledged`, `in_progress`, `waiting_on_approval`, `waiting_on_source`,
   `completed`, `dismissed`, `expired`, `failed`), the allowed and forbidden
   transitions, and the rule that no transition executes a controlled action.
3. The **data model plan** (planning only): the logical `platform_operator_task` and
   `platform_operator_notification_event` records -- fields, indexes, uniqueness,
   tenant / actor scope, `correlation_id`, source links to P18 / P19 / P20 / P21 / P22
   ids, and idempotency / dedup rules. P23-A creates no table, no migration, no ORM
   model.
4. The **notification boundary**: a notification event is a *record of attention*, not
   an outbound delivery; P23-A defines the event shape and the never-leaked list, and
   names future channels it does not implement.
5. The **queue API plan** (planning only): GET tasks, GET task detail, POST acknowledge,
   POST dismiss, POST assign / self-assign, POST mark in_progress, POST complete with
   evidence. Every endpoint is task-state management only; none executes a P22 action.
6. The **frontend plan** (planning only): the Operator Task Queue page, the task detail
   drawer, filters, evidence links, empty / error / loading states, and the notification
   badge behavior.
7. The **security / RBAC boundary**: identity-only platform-operator visibility
   (`support_operator`, `engineering_operator`, `super_admin`), reusing the existing
   auth / RBAC / session transport; no auth rewrite in P23.
8. The **audit contract**: every task state change is auditable in a future phase, with
   actor, previous_state, next_state, `reason_redacted`, `correlation_id`, and linked
   object ids; no raw payload, no secrets.
9. The **severity, dedup, and correlation rules**: how the queue collapses many events
   into one task, ranks them, and threads a `correlation_id` across P18 through P22.
10. The **acceptance criteria, counterexamples, and the P23-B entry gate**.

P23-A is **contract only**. It ships **no runtime code, no migration, no endpoint, no
queue, no worker, no notification sender, no frontend**.

### 1.2 In scope (contract layer)

- Define the task type catalog and the explicit exclusion list (section 3).
- Define the task state machine and its allowed / forbidden transitions (section 4).
- Define the data model plan for `platform_operator_task` and
  `platform_operator_notification_event` (planning only; section 5).
- Define the notification event boundary and the never-leaked list (section 6).
- Define the queue API plan (planning only; section 7).
- Define the frontend plan (planning only; section 8).
- Define the security / RBAC visibility boundary (section 9).
- Define the audit contract for task state changes (section 10).
- Define the severity, dedup, and correlation rules (section 11).
- Define the acceptance criteria and counterexamples (sections 12 and 13).
- Define the P23-B entry gate (section 14).
- Define the future AI Operator Copilot boundary against this queue substrate
  (section 15).

### 1.3 Non-goals

The non-goals split into two groups so the contract does not accidentally forbid the
P23-B work it explicitly permits (section 14):

- **P23-A-only non-goals** (1.3.1) are forbidden in P23-A, but a future P23-B may
  implement the corresponding **non-executing, non-sending** skeleton under its own
  entry gate.
- **All-P23 non-goals** (1.3.2) are forbidden across **every** P23 phase unless a new
  contract revision is accepted by the CTO.

#### 1.3.1 P23-A-only non-goals (P23-B may implement these under its gate)

- No runtime code, no backend handlers, no frontend UI, no test code, and no dependency
  changes in P23-A.
- No migrations, no alembic changes, and no new tables or columns in P23-A. (A future
  P23-B migration, if any, requires separate explicit approval in the P23-B contract
  review; see section 14.)
- **No real queue, no worker, no scheduler, no drain loop in P23-A.** P23-A defines the
  contract only; no task is materialized, indexed, polled, drained, or dispatched at
  runtime in P23-A. (P23-B may add an in-memory, non-executing read model and task-state
  skeleton; a real persistent queue / worker is reserved for a separately approved
  phase.)
- **No notification / escalation implementation in P23-A.** P23-A defines the
  notification *event* boundary only; it implements no outbound channel, template,
  recipient resolver, retry, or delivery confirmation.
- **No frontend in P23-A.** The Operator Task Queue page, drawer, filters, and badge are
  planned here but implemented in a later, separately approved slice.

#### 1.3.2 All-P23 non-goals (every P23 phase, unless a new contract revision is accepted)

- **No execution by the queue.** No task state transition, notification event, queue
  drain, or worker step executes a P22 action, approves an approval, or mutates a
  registry field. P23 is read / present / triage over P17 through P22; it is never an
  execution path.
- **No bypass of any gate.** P23 never short-circuits the P18 allowlist, the P19
  approve / reject boundary, the P20 maker-checker / quorum policy, the P21 durability
  rules, or the P22 dry-run / precondition / audit envelope. Surfacing a task as
  "execution_ready" is a *presentation* label; it grants no execution.
- **No real notification delivery.** A notification event is a record of attention. Even
  in later P23 phases, no channel sends a secret, raw payload, DSN, host, port, token,
  cookie, auth header, stack trace, raw request / response body, shell / SQL, or tenant
  business payload.
- **No product business task.** The queue carries platform operational tasks only
  (approvals, executions, backup / source status, incident follow-up, runbook steps). It
  never carries a product business task -- an order, payment, invoice, customer,
  inventory, or ledger follow-up is out of scope for platform P23 and belongs to product
  tooling, not this queue.
- **No tenant business mutation.** Completing or dismissing a task changes task state
  only; it never reads, writes, creates, updates, or deletes tenant business records.
- **No tenant data leak across contexts.** A task scoped to tenant A is never visible to
  an operator acting in tenant B's context; cross-tenant visibility requires the
  identity-only, system-scope path and is audited.
- **No auth / RBAC / session / tenancy rewrite.** P23 reuses the P10 identity-only guard
  and the existing operator roles; no new auth transport, token, or session model is
  defined or implemented.
- **No AI agent execution or auto-approval.** P23 names a future AI Operator Copilot
  boundary (section 15); it grants no AI the power to execute, approve, auto-dismiss, or
  auto-complete a task without a human operator.
- **No deletion of audit history.** `dismissed` and `expired` remove a task from the
  active queue; they never delete, overwrite, or truncate the underlying P18 / P19 /
  P20 / P21 / P22 / P17 audit trail. The queue is a view; it is not the system of record.
- **No silent source fabrication.** A `source_unknown` or `backup_check_warning` task is
  never displayed as healthy / success. Unknown is never healthy; a warning is never a
  success (P10 / P17 / P22 rule, carried into P23).
- No merge or push of platform-dev and no push to any product branch from any P23 phase.

## 2. Relationship to Prior Phases (P10 through P22)

P23 introduces **no new auth, RBAC, session, observability, data-source, registry,
storage, approval, or execution concepts**. It is the *aggregation and presentation*
layer that P17 through P22 deliberately left scattered: every prior phase produced
events, requests, approvals, executions, and statuses, and every prior phase left it to
the operator to stitch them together. P23 stitches.

| Prior phase | What P23 consumes / aggregates |
|---|---|
| **P10** identity-only guard, PlatformAuditEvent, source-status vocabulary, redact_metadata allowlist | Every task and notification event is visible only behind the P10 identity-only platform-operator guard. Task audit events are typed specializations of PlatformAuditEvent. The P10 redact_metadata allowlist is applied to every task reason, follow-up note, evidence summary, and notification field before it is recorded, returned, or (in a future phase) delivered. The source-status rules (unknown is never healthy, null is never zero) gate how a task is labeled and ranked. |
| **P11 / P12 / P13 / P14 / P15** Cockpit, Support Console, Observability, Incident Triage | P23-A changes none of these surfaces. P23 is a new aggregation surface that *reads* the same signals; a future approved phase may badge the cockpit / console with task counts. P23-A adds no cockpit / console control and no execute / approve button anywhere. |
| **P16** Worktree Execution Harness | P23 never invokes the P16 harness. A task may *link* to a P22 execution that (in a separately approved phase) ran through the runtime governed adapter seam; the task itself runs nothing. |
| **P17** Registry, Tenant Lifecycle, backup / status source | A task may surface a P17 backup / status source signal (`source_unknown`, `backup_check_warning`) or an incident flag follow-up. P23 mutates no P17 registry field and reads the P17 backup / status source as evidence only. |
| **P18** Controlled Platform Actions | P18 created action *requests* with an `executed` flag and `result` enum. P23 surfaces `action_request_created` tasks (a request was opened) and links a task to the P18 `action_id`. P23 flips no P18 flag and creates no P18 request. |
| **P19** Approval Workflow | P19 approve / reject is the gate. P23 surfaces `approval_pending` and `approval_decision_required` tasks (an approval needs checkers / a decision). Acknowledging or completing such a task executes no approve / reject; it only tracks operator attention. Approval still flows through P19 / P20 / P21. |
| **P20** Durable Approval Governance | P20 maker-checker / quorum caps approvals at `approved_execution_blocked`. P23 surfaces a task as `waiting_on_approval` when quorum is not yet met, and never grants quorum by completing a task. |
| **P21** Durable Approval Store | P21 made approvals durable and restart-safe. P23 links a task to the durable `approval_id` / `durable_approval_id` and reads the durable audit trail as evidence; P23 changes no P21 table, field, enum, or migration. |
| **P22** Controlled Execution v0 | P22 defines the execution-record lifecycle (`dry_run_passed -> ... -> executed / execution_failed / ...`) and ran the first safe `backup.check`. P23 surfaces `execution_ready`, `execution_completed`, `execution_failed`, `source_unknown`, and `backup_check_warning` tasks from P22 execution records and the P22-G completion map (`fresh_success -> succeeded`; `stale / failed / partial / in_progress / no-outcome -> completed_with_warning`; `read-error -> failed`). Marking an `execution_ready` task `in_progress` or `completed` **does not** execute the action; it only records operator attention. Execution still flows through the P22 dry-run / precondition / governed-adapter envelope. |

In one line, restated for the record: P18 creates requests; P19 / P20 / P21 gather and
durably store approval; P22 defines and (for `backup.check`) performs governed execution;
**P23 aggregates all of the above into a single operator task / notification queue so an
on-call human can see, triage, and follow up -- but P23 itself executes nothing, approves
nothing, mutates nothing, and delivers nothing.** A task is a view, not an executor.

## 3. Task Type Catalog

P23 produces a closed set of task types. A task type not listed here has no P23 path,
regardless of what event triggered it. Each task type maps to the prior-phase event(s)
that materialize it, the operator role(s) that may own it, and the default severity
(severity rules are normative in section 11; the values here are defaults).

### 3.1 Master task type catalog

| task_type | Materialized from | Owner role(s) | Default severity | Follow-up |
|---|---|---|---|---|
| `action_request_created` | a P18 action request is opened (`executed == false`) | support_operator / engineering_operator / super_admin by P18 scope | low | review the request; open an approval if one is needed |
| `approval_pending` | a P19 / P20 / P21 durable approval is open and quorum is not yet met | super_admin (checker) | medium | gather the required checkers to meet quorum |
| `approval_decision_required` | a durable approval is awaiting a specific checker decision (expiring soon, or blocked on a named role) | super_admin (checker) | high | approve or reject through P19 / P20 / P21 only |
| `execution_ready` | a P22 dry-run passed and an execution request is recorded at `dry_run_passed` / `execution_queued` behind a durable approval | super_admin (executor) | high | run the governed execution through P22 only (the task does not run it) |
| `execution_completed` | a P22 execution record reached `executed` / `compensation_completed` (success) | super_admin (executor) | low | close out; file compensation follow-up if reversible write |
| `execution_failed` | a P22 execution record reached `execution_failed` / `blocked`, or a read errored | super_admin (executor) / engineering_operator | high | diagnose; retry only via a new P22 dry-run + execution request |
| `source_unknown` | a P17 / P18 source for a target field is `unknown`, or a `backup.check` / `provisioning.recheck` returned `SOURCE_UNKNOWN` | engineering_operator / super_admin | high | restore the source; never display as healthy |
| `backup_check_warning` | a P22-G `backup.check` completion mapped to `completed_with_warning` (stale / failed / partial / in_progress / no-outcome) | engineering_operator / super_admin | high | investigate the backup source; a warning is never a success |
| `incident_followup_required` | a P15 / P17 incident flag (`incident_active`) is set and an operator owes a follow-up | support_operator / super_admin | medium | complete the incident follow-up; clear the flag through P22 only |
| `runbook_step_required` | an operator owes a typed runbook step tied to an incident / execution / approval correlation | support_operator / engineering_operator / super_admin | medium | perform the runbook step; record evidence on the task |

Notes on the catalog:

- **Owner role is presentation, not authorization.** The owner field suggests who
  typically handles a task type. It does not grant that role any new power; runtime
  authorization is the existing P10 / P18 / P20 / P22 boundary, unchanged by P23.
- **Every task type is platform-operational.** Each maps to a platform request, approval,
  execution, source status, incident, or runbook step. No task type carries a product
  business payload.
- **Severity defaults may be raised, not lowered, by correlation.** A task that shares a
  `correlation_id` with an active incident or a failed execution is ranked at least as
  high as its highest-correlated peer (section 11).
- **A task may carry more than one linked id.** An `execution_ready` task links a P18
  `action_id`, a P21 `durable_approval_id`, and a P22 `execution_request_id` /
  `dry_run_ref`. The links are evidence pointers, not joinable business keys.

### 3.2 Explicit exclusion list (never a P23 task)

The following are excluded from the P23 queue forever in this contract:

- **Product business tasks.** An order, payment, invoice, customer, inventory, or ledger
  follow-up is a product concern, not a platform operator task. It belongs to product
  tooling, not this queue.
- **Tenant business payload.** A task never carries an order id, payment id, invoice id,
  customer id, inventory record, or ledger entry as payload. `tenant_id` is a scoped
  identifier only and is never joinable to business tables.
- **Synthetic execution tasks.** The queue never invents a task that, when completed,
  executes an action. The only execution-shaped task is `execution_ready`, and it points
  at a real P22 execution request; completing it executes nothing.
- **Self-approved / auto-approved tasks.** No task grants an approval or waives quorum.
- **Cross-tenant broadcast tasks.** A task is scoped to one tenant (or platform-wide with
  `tenant_id == null`); no task broadcasts tenant-A detail into tenant-B context.
- **Channel-specific delivery tasks.** A task is never "send the email" or "post the
  webhook"; the notification event records attention, and a future channel layer (out of
  P23-A scope) decides delivery.

These exclusions are absolute for P23. Lifting any exclusion is a new contract revision
accepted by the CTO and a new phase, not an extension of P23-A.

## 4. Task State Machine

Every task carries a state. The state machine is a **presentation / triage** lifecycle,
entirely separate from the P19 / P20 / P21 approval state machine and the P22
execution-record state machine. **No task state transition executes a controlled action,
approves an approval, or mutates a registry field.** Transitions only record operator
attention and triage decisions.

### 4.1 States

```text
 open --+--> acknowledged                 (an operator has seen the task)
        +--> in_progress                  (an operator self-assigned and is working)
        +--> waiting_on_approval          (blocked: P19/P20/P21 quorum not met)
        +--> waiting_on_source            (blocked: P17/P18 source unknown / unavailable)
        +--> dismissed                    (operator judged not-actionable; audit kept)
        +--> expired                      (TTL passed with no completion; audit kept)
        +--> failed                       (the underlying work failed and no retry is owed)
        +--> completed                    (operator recorded evidence; follow-up done)

 acknowledged --+--> in_progress
                +--> waiting_on_approval
                +--> waiting_on_source
                +--> completed
                +--> dismissed
                +--> expired

 in_progress --+--> waiting_on_approval
               +--> waiting_on_source
               +--> completed
               +--> failed
               +--> dismissed

 waiting_on_approval --+--> acknowledged   (quorum met; back to a person)
                       +--> in_progress
                       +--> expired
                       +--> failed

 waiting_on_source --+--> acknowledged     (source recovered)
                     +--> in_progress
                     +--> expired
                     +--> failed

 completed  : terminal
 dismissed  : terminal
 expired    : terminal
 failed     : terminal
```

### 4.2 State semantics

| state | Meaning |
|---|---|
| `open` | The task is materialized and visible in the queue; no operator has acted. Initial state. |
| `acknowledged` | An operator has seen the task and taken responsibility for triage (not necessarily for execution). |
| `in_progress` | An operator is actively working the follow-up. For an `execution_ready` task this means the operator is preparing to run the action *through P22*; the task state itself runs nothing. |
| `waiting_on_approval` | The follow-up is blocked because the linked P19 / P20 / P21 approval has not met quorum. The task cannot complete until the approval does -- and the approval flows through P19 / P20 / P21, never through the task. |
| `waiting_on_source` | The follow-up is blocked because the linked P17 / P18 source is `unknown` / unavailable. The task cannot display healthy while it waits. |
| `completed` | The operator recorded evidence and the follow-up is done. Terminal. |
| `dismissed` | The operator judged the task not-actionable. The task leaves the active queue; the audit history is retained. Terminal. |
| `expired` | The task's time-to-live passed without completion. Terminal. |
| `failed` | The underlying work failed (e.g. `execution_failed`) and no further retry is owed on this task. Terminal. |

### 4.3 Transition rules

1. **Transitions are operator-driven or TTL-driven only.** A task moves forward because
   an operator acknowledged / self-assigned / completed it, or because a TTL expired. No
   transition runs an action.
2. **Terminal states are terminal.** `completed`, `dismissed`, `expired`, and `failed`
   accept no outgoing transition. Reopening requires a *new* task (new id, new
   correlation_id link), not a resurrection.
3. **`waiting_on_*` reflects the linked gate, it does not change it.** Moving a task to
   `waiting_on_approval` does not approve it; moving it to `waiting_on_source` does not
   recover the source. The gate (P19-P21 / P17-P18) is the system of record; the task
   mirrors it.
4. **A transition records exactly one task-audit event** (section 10), with previous and
   next state. There is no unaudited transition and no batch transition that hides the
   intermediate states.
5. **No transition touches tenant business data, payments, product code, or secrets.**
6. **No transition sends a notification.** A state change may *materialize* a
   notification event (a record of attention); it never delivers it.

### 4.4 Forbidden transitions (must be rejected)

- `completed -> *`, `dismissed -> *`, `expired -> *`, `failed -> *` (terminal).
- `open -> completed` **without evidence** (a completion must carry a redacted evidence
  note or a linked completed object id).
- `* -> completed` for a task whose linked gate is still open (e.g. an
  `execution_ready` task whose P22 execution is at `dry_run_passed`, not `executed`; an
  `approval_pending` task whose approval is still at `pending_review`). Completing the
  task cannot fabricate completion of the underlying work.
- Any transition that would also flip a P18 `executed` flag, a P19 / P20 / P21 approval
  state, or a P17 registry field.

## 5. Data Model Plan (planning only -- not implemented in P23-A)

P23-A plans, but does not implement, two logical records. No table, migration, ORM model,
enum, or column is created in P23-A. The plan is the input to a future P23-B that may
implement an in-memory read model and, much later, a persisted store under separate
approval.

### 5.1 Logical record: `platform_operator_task`

```text
PlatformOperatorTask {
  task_id              : uuid        -- PK. required. Unique per task instance.
  task_type            : enum        -- required. Closed set (section 3.1).
  severity             : enum        -- required. low | medium | high (section 11).
  state                : enum        -- required. Closed set (section 4.1).
  tenant_id            : uuid        -- nullable. Scoped id only; null for platform-wide.
                                     -- Never a business payload; never joinable to a
                                     -- product business table.
  actor_scope          : enum        -- required. platform | tenant_contextual. The
                                     -- visibility scope at which the task is shown.
  owner_role           : enum        -- nullable. Suggested owner role (presentation only;
                                     -- not authorization).
  owner_actor_id       : varchar     -- nullable. The operator who self-assigned, if any.
  correlation_id       : varchar     -- required. Threads P18 / P19 / P20 / P21 / P22 /
                                     -- P15 events into one triage thread.
  linked_action_id     : uuid        -- nullable. -> P18 action_id, where applicable.
  linked_approval_id   : uuid        -- nullable. -> P21 durable_approval_id, where
                                     -- applicable.
  linked_execution_id  : uuid        -- nullable. -> P22 execution_request_id, where
                                     -- applicable.
  linked_dry_run_ref   : uuid        -- nullable. -> P22 dry_run_id, where applicable.
  linked_source_ref    : varchar     -- nullable. -> P17 backup / status source handle.
  linked_incident_id   : uuid        -- nullable. -> P15 / P17 incident id, if any.
  summary_redacted     : text        -- required. One-line redacted summary. P10 allowlist
                                     -- applied. No secret, no raw payload, no DSN / host /
                                     -- port.
  reason_redacted      : text        -- nullable. Redacted triage reason.
  evidence_ref         : varchar     -- nullable. Pointer to evidence (audit event id,
                                     -- completion record id). Never raw payload.
  source_status        : enum        -- nullable. known | unknown | degraded. Mirrors the
                                     -- linked source; never fabricated healthy.
  dedup_key_digest     : char(64)    -- required. SHA-256 of the canonical dedup key
                                     -- (section 11). Drives collapse of many events into
                                     -- one task.
  ttl_expires_at       : timestamptz -- nullable. When the task auto-expires.
  created_at           : timestamptz -- required. UTC ISO-8601.
  updated_at           : timestamptz -- required. UTC ISO-8601.
  redaction_applied    : bool        -- required. DEFAULT true.
}
```

Planned indexes / uniqueness (planning only):

- **PK**: `task_id`.
- **Dedup unique**: `UNIQUE (task_type, dedup_key_digest)` where `state IN
  (open, acknowledged, in_progress, waiting_on_approval, waiting_on_source)` -- collapses
  repeat events for the same logical follow-up into one *active* task. Terminal tasks are
  exempt so a re-opened follow-up creates a new task (per the Postgres partial-unique NULL
  discipline: scope the unique constraint to active states, not to a NULL column).
- **Queue read index**: `(severity DESC, created_at)` filtered to non-terminal states,
  plus `(tenant_id)` and `(owner_actor_id)` for scoped views.
- **Correlation index**: `(correlation_id)` for threading.
- **Source-link indexes**: `(linked_action_id)`, `(linked_approval_id)`,
  `(linked_execution_id)`, `(linked_incident_id)` for evidence lookups.

### 5.2 Logical record: `platform_operator_notification_event`

```text
PlatformOperatorNotificationEvent {
  event_id             : uuid        -- PK. required. Unique.
  task_id              : uuid        -- required. -> platform_operator_task.task_id.
  channel              : enum        -- required. in_app | email | webhook. PLANNED only;
                                     -- P23-A defines the enum, implements no channel.
  delivery_state       : enum        -- required. recorded | queued_for_delivery |
                                     -- delivered | failed_delivery | suppressed. DEFAULT
                                     -- recorded. P23-A only ever produces recorded.
  severity             : enum        -- required. low | medium | high (echoed from task).
  tenant_id            : uuid        -- nullable. Scoped id only.
  actor_scope          : enum        -- required. platform | tenant_contextual.
  recipient_role       : enum        -- nullable. Intended recipient role (not a resolved
                                     -- address). P23-A resolves no address.
  summary_redacted     : text        -- required. Redacted one-line summary. Never a
                                     -- secret, raw payload, DSN, host, port, token, or
                                     -- log line.
  correlation_id       : varchar     -- required. Echoes the task correlation_id.
  redaction_applied    : bool        -- required. DEFAULT true.
  created_at           : timestamptz -- required. UTC ISO-8601.
}
```

Planned indexes / uniqueness (planning only):

- **PK**: `event_id`.
- **Per-task index**: `(task_id, created_at)`.
- **Delivery dedup**: `UNIQUE (task_id, channel)` where `delivery_state IN (recorded,
  queued_for_delivery, delivered)` -- at most one in-flight notification per task per
  channel; a re-fire after delivery is a new event only if the task re-opens (which, per
  section 4, requires a new task id).

### 5.3 Relationship to prior-phase ids

- `linked_action_id` -> P18 `action_id` (evidence pointer only; not an FK into a product
  table).
- `linked_approval_id` -> P21 `durable_approval_id` (and through it the P19 / P20
  approval envelope).
- `linked_execution_id` -> P22 `execution_request_id`; `linked_dry_run_ref` -> P22
  `dry_run_id`.
- `linked_source_ref` -> P17 backup / status source handle.
- `linked_incident_id` -> P15 / P17 incident id.
- All links are **evidence pointers**. The queue never stores the raw P18 request body,
  the raw P21 approval envelope, the raw P22 execution payload, the raw source artifact,
  or any tenant business payload. Only redacted summaries and digests are stored
  (section 6).

### 5.4 Idempotency / dedup rules (planning only)

- **Event-to-task is many-to-one.** Many prior-phase events that share a
  `correlation_id` and a task type collapse into one active task via `dedup_key_digest`.
- **`dedup_key_digest` is a SHA-256** over the canonical key `(task_type,
  linked object id, tenant_id, source_status, follow-up variant)`. The raw key is
  canonicalized before hashing; only the digest is stored.
- **A terminal task does not absorb a new event.** If the same logical follow-up recurs
  after a task is `completed` / `dismissed` / `expired` / `failed`, a new task is created
  (new `task_id`, fresh `dedup_key_digest` salt, same `correlation_id`).
- **Replays are idempotent.** Re-emitting the same event for the same active task creates
  no new task and no duplicate notification event; it may bump `updated_at` and re-rank
  severity, but writes no duplicate success.
- **No dedup across tenants.** The dedup key includes `tenant_id`; tenant-A and tenant-B
  events never collapse into one task.

## 6. Notification Boundary

A **notification event** is a *record of attention required*, not an outbound delivery.
P23-A defines the event shape, the closed channel enum, and the never-leaked list. It
implements no channel, resolves no recipient address, sends nothing.

### 6.1 What a notification event is

- A redacted, severity-ranked record that says "task X needs an operator's attention".
- Produced by a task state change (e.g. `open` materialized, severity raised,
  `waiting_on_*` entered) or by a TTL approaching.
- Linked to a `task_id` and through it to the P18 / P19 / P20 / P21 / P22 evidence.
- Stored with `delivery_state == recorded` only, in P23-A. Future phases may advance it
  to `queued_for_delivery` / `delivered` / `failed_delivery` / `suppressed`.

### 6.2 What a notification event is not

- **Not a delivery.** P23-A sends nothing. No socket, no SMTP, no HTTP webhook, no push.
- **Not a channel implementation.** The `channel` enum (`in_app`, `email`, `webhook`) is
  planned; no channel is wired, templated, or addressed in P23-A.
- **Not a recipient resolver.** `recipient_role` is a role hint, not a resolved email /
  URL / user id.
- **Not a retry / escalation engine.** P23-A defines no retry policy, no escalation
  chain, no on-call rotation integration.

### 6.3 The never-leaked list

The following must NEVER appear in any notification field, task field, response, queue
item, backup, or export:

- raw secret, DSN, connection string, hostname, port, host:port pair;
- token, password, API key, cookie, auth header (for example `X-Platform-Operator`,
  `Authorization`, `Cookie`, `Set-Cookie`);
- raw idempotency key (digest only, where any prior-phase idempotency key is echoed);
- stack trace, raw exception, raw log line, raw audit body;
- raw request body or raw response body of any P18 action, P21 approval, or P22 execution
  payload (only redacted summaries and digests);
- tenant business payload: orders, payments, invoices, customers, inventory, ledgers;
- any shell command, SQL statement, or script body (the queue executes nothing, and none
  is ever recorded).

### 6.4 Channel plan (future, not P23-A)

Future phases may add channels, each behind its own gate, and each bound by the
never-leaked list:

- **in-app**: a badge / toast on the Operator Task Queue page; the safest default
  channel; no external network.
- **email**: a redacted digest email to an on-call role mailbox; never a raw payload.
- **webhook**: a redacted JSON post to a configured, allowlisted operator endpoint; never
  a secret, never the raw execution payload.

P23-A names these channels and binds them to the never-leaked list; it implements none.

## 7. Queue API Plan (planning only -- not implemented in P23-A)

P23-A proposes -- does not implement -- the following read / triage surface. Every
endpoint is behind the P10 identity-only platform-operator guard; **none executes a P22
action, approves an approval, or mutates a registry field**.

- **GET /platform/p23/operator-tasks** -- list tasks with filters (severity, type, state,
  tenant, source, owner, correlation_id) and pagination. Read-only; audited as a read.
- **GET /platform/p23/operator-tasks/{task_id}** -- read one task's redacted record,
  state, and evidence links. Read-only; audited as a read.
- **POST /platform/p23/operator-tasks/{task_id}/acknowledge** -- move `open ->
  acknowledged`. State management only; executes nothing.
- **POST /platform/p23/operator-tasks/{task_id}/assign** -- assign / self-assign an
  owner. State management only.
- **POST /platform/p23/operator-tasks/{task_id}/in-progress** -- move to `in_progress`.
  For an `execution_ready` task this records operator attention; it does not run the
  action. The action still runs through P22.
- **POST /platform/p23/operator-tasks/{task_id}/complete** -- move to `completed` with a
  redacted evidence note / linked completed object id. Rejects if the linked gate is still
  open. Executes nothing.
- **POST /platform/p23/operator-tasks/{task_id}/dismiss** -- move to `dismissed` with a
  redacted reason. Audit history is retained; nothing is deleted.

Compatibility notes:

- No response field carries a secret, raw key, raw body, shell / SQL, host / port, or
  tenant payload.
- No endpoint returns a `completed` task whose linked gate is still open.
- No endpoint approves, rejects, executes, or dispatches.
- A future backend preserves these shapes unless a new versioned contract is approved.

## 8. Frontend Plan (planning only -- not implemented in P23-A)

P23-A plans -- does not implement -- the following frontend surface. No frontend ships in
P23-A.

- **Operator Task Queue page**: a single page listing active tasks ranked by severity then
  recency, with counts by type and state.
- **Task detail drawer**: opens on a row; shows redacted summary, state, severity,
  `correlation_id`, evidence links (P18 action, P21 approval, P22 execution / dry-run,
  P17 source, P15 incident), the triage state machine buttons (acknowledge, self-assign,
  in-progress, complete, dismiss), and the redacted reason / evidence note field.
- **Filters**: by severity, type, state, tenant, source, owner, `correlation_id`. Tenant
  filter respects the operator's scope (no cross-tenant leak).
- **Evidence links**: deep links into the P12 / P13 / P22 read-only views of the linked
  object; never an execute / approve button.
- **Empty / error / loading states**: empty state explains there is nothing to triage;
  error state never fabricates healthy; loading state never displays partial rows as
  complete.
- **Notification badge behavior**: a badge counts active high-severity tasks /
  notification events for the signed-in operator's scope; clicking opens the queue. The
  badge is a count of records of attention; it triggers no delivery and no execution.

Frontend rules:

- The queue UI executes no action, approves no approval, and sends no notification.
- The UI never displays a `source_unknown` or `backup_check_warning` task as healthy /
  success.
- The UI never displays a task from tenant A in tenant B's context.

## 9. Security / RBAC Boundary

P23 reuses the existing auth / RBAC / session transport. It defines **no new auth, no new
token, no new session model, no new role**. Runtime authorization for *actions* remains
the P10 identity-only guard plus the P18 / P20 / P22 per-action boundary; P23-A only
plans *visibility* of tasks.

### 9.1 Visibility by role (planning only; runtime left to a later gated slice)

- **`support_operator`**: sees tasks within its P18 support-safe scope -- typically
  `action_request_created` for support-scoped actions, `approval_pending` where it is a
  permitted maker, `incident_followup_required`, and `runbook_step_required`. Never sees
  `execution_ready` as an executor (P22 executor is identity-only super_admin).
- **`engineering_operator`**: sees source / execution health tasks within its scope --
  `source_unknown`, `backup_check_warning`, `execution_failed` (as diagnostician),
  `runbook_step_required`. Never an executor or a checker.
- **`super_admin` (identity-only)**: sees the full platform-wide queue, may be checker /
  executor, and may self-assign any task. Tenant-contextual super_admin is bounded by its
  tenant context (no cross-tenant leak).
- **Tenant admin / tenant-scoped token**: never sees platform operator tasks; the queue
  is a platform-operational surface, not a tenant surface.

### 9.2 Hard rules

1. **Identity-only platform-operator guard.** Every queue read and every state-change
   endpoint is behind the P10 identity-only platform-operator guard. Tenant admin,
   tenant-scoped token, and unauthenticated callers are denied.
2. **No auth / RBAC rewrite in P23.** P23 consumes roles; it does not redefine them.
3. **Tenant scope is enforced at the read.** A task with `tenant_id == A` is invisible to
   an operator in tenant B's context unless the operator is on the identity-only
   platform-scope path (and that access is audited).
4. **Owner is not authorization.** `owner_role` / `owner_actor_id` are presentation and
   triage; they grant no new privilege. An operator may self-assign only tasks already
   visible to them.
5. **No privilege escalation through the queue.** Completing an `execution_ready` task
   does not make the completer the P22 executor; running the action still requires the
   P22 identity-only super_admin executor and the full precondition set.

## 10. Audit Contract (planning only -- not implemented in P23-A)

Every task state change is auditable. P23-A defines the audit shape and rules; a future
phase records the events. The task audit log is append-only; no UPDATE path; no
single-row DELETE; only whole-record retention purge (P21 discipline), itself audited.

### 10.1 Task audit event (planning shape)

```text
OperatorTaskAuditEvent {
  event_id              : uuid        -- PK. required. Unique.
  task_id               : uuid        -- required. The task whose state changed.
  task_type             : enum        -- required. Closed set (section 3.1).
  actor_id              : varchar     -- required. The operator (or SYSTEM for TTL /
                                       -- sweep). Identity-only platform-operator.
  actor_role            : enum        -- required. super_admin | engineering_operator |
                                       -- support_operator | system.
  tenant_id             : uuid        -- nullable. Scoped id only.
  transition            : enum        -- required. The state change, e.g.
                                       -- open->acknowledged, in_progress->completed.
  previous_state        : enum        -- required. State before the transition.
  next_state            : enum        -- required. State after the transition.
  reason_redacted       : text        -- nullable. Redacted reason / evidence note. P10
                                       -- allowlist applied. Never raw payload / secret.
  correlation_id        : varchar     -- required. Echoes the task correlation_id.
  linked_action_id      : uuid        -- nullable. Echoed for traceability.
  linked_approval_id    : uuid        -- nullable.
  linked_execution_id   : uuid        -- nullable.
  linked_source_ref     : varchar     -- nullable.
  linked_incident_id    : uuid        -- nullable.
  redaction_applied     : bool        -- required. DEFAULT true.
  sequence_no           : bigint      -- required. Monotonic per-task sequence.
  created_at            : timestamptz -- required. UTC ISO-8601.
}
```

### 10.2 Audit rules

- One event per transition; no batch transition hides intermediate states.
- `previous_state` and `next_state` are always recorded; a terminal-state exit attempt is
  audited as a denied transition.
- `reason_redacted` and every echoed field pass through the P10 allowlist; the never-leaked
  list (section 6.3) applies in full.
- `dismissed` and `expired` are audited like any other transition; the underlying P18 /
  P19 / P20 / P21 / P22 audit trail is untouched.
- Denials (e.g. completing a task whose gate is still open) are audited.
- No audit field contains a secret, raw payload, DSN, host, port, token, cookie, auth
  header, stack trace, raw body, shell / SQL, or tenant business payload.

## 11. Severity, Dedup, and Correlation Rules

### 11.1 Severity

- Three levels: `low`, `medium`, `high`. No `critical` auto-execute tier -- the highest
  severity only ranks the queue; it never triggers execution.
- Defaults come from the task type catalog (section 3.1).
- Severity is **monotonic upward within a correlation**: if any task sharing a
  `correlation_id` is `high`, an active peer task is ranked at least `medium` and a
  `backup_check_warning` / `source_unknown` / `execution_failed` peer forces `high`.
- Severity is **never lowered to healthy** to hide a warning: a `backup_check_warning`
  stays at least `high`; a `source_unknown` task is never displayed as healthy regardless
  of severity.

### 11.2 Dedup

- The dedup key is `(task_type, linked object id, tenant_id, source_status, follow-up
  variant)`, SHA-256 hashed to `dedup_key_digest`.
- Many events -> one active task per `dedup_key_digest` (section 5.4).
- Terminal tasks are exempt from dedup so a recurring follow-up re-opens as a new task.
- No dedup across tenants.

### 11.3 Correlation

- `correlation_id` threads P18 -> P19 -> P20 -> P21 -> P22 -> P15 -> P17 events into one
  triage thread. Where a prior phase already emits a `correlation_id`, P23 reuses it.
- The queue groups tasks by `correlation_id` for the detail drawer's "related tasks" view.
- Correlation is a presentation grouping; it grants no cross-object power.

## 12. Acceptance Criteria

A future phase that implements this contract is accepted only when all of the following
hold:

1. **P23-A is docs and ledger only.** No runtime code, backend, frontend, migration,
   alembic change, table, test code, or dependency change ships in P23-A.
2. **A task is a view, not an executor.** No task state transition -- acknowledge,
   assign, in_progress, complete, dismiss -- executes a P22 action, approves an approval,
   or mutates a registry field.
3. **A notification is a record, not a delivery.** P23-A sends nothing; the
   notification event is stored `delivery_state == recorded` only; no channel is wired.
4. **The task type catalog is exactly the ten defined types;** every excluded item
   (product business, tenant payload, synthetic execution, auto-approval, cross-tenant
   broadcast, channel delivery) has no task path.
5. **The task state machine has exactly the nine defined states** and enforces the
   allowed / forbidden transitions; terminal states accept no exit; completion requires
   evidence and a closed linked gate.
6. **No gate is bypassed.** Surfacing a task as `execution_ready` or
   `approval_decision_required` is a presentation label; it grants no execution and no
   approval.
7. **`source_unknown` is never displayed healthy;** a task whose linked source is
   `unknown` is labeled and ranked accordingly, and cannot be `completed` as healthy.
8. **`backup_check_warning` is never displayed as success;** a P22-G
   `completed_with_warning` completion surfaces as a warning task, never as a success.
9. **`dismissed` does not delete audit history;** the underlying P18 / P19 / P20 / P21 /
   P22 / P17 audit trail is retained; only the active-queue entry is removed.
10. **No tenant leak;** a task scoped to tenant A is invisible in tenant B's context;
    cross-tenant visibility is identity-only platform-scope and audited.
11. **No product business task;** the queue carries platform operational tasks only; no
    order / payment / invoice / customer / inventory / ledger task exists.
12. **No tenant business mutation;** completing or dismissing a task changes task state
    only; no tenant business record is read or written.
13. **No auth / RBAC rewrite;** P23 reuses the P10 identity-only platform-operator guard
    and existing roles; runtime authorization is unchanged.
14. **Owner is not authorization;** `owner_role` / `owner_actor_id` grant no new
    privilege; self-assignment is bounded by existing visibility.
15. **Redaction is total;** every task / notification / audit field scans clean against
    the P10 allowlist and the never-leaked list; `redaction_applied == true` everywhere.
16. **No raw secrets / DSNs / hosts / ports / tokens / passwords / cookies / auth headers,
    raw bodies, shell / SQL, or tenant payload** appear in any task, notification,
    response, queue item, or audit event.
17. **Every task state change is auditable;** one event per transition, with
    `previous_state`, `next_state`, `reason_redacted`, `correlation_id`, and linked
    object ids; the log is append-only.
18. **Dedup is correct;** many events sharing a `dedup_key_digest` collapse into one
    active task; terminal tasks are exempt; no dedup across tenants; replays write no
    duplicate.
19. **Severity is honest;** severity never lowers a warning to healthy, never auto-executes,
    and is monotonic upward within a correlation.
20. **No AI agent execution / auto-approval;** P23-A names a future AI Operator Copilot
    boundary only and grants no AI the power to execute, approve, auto-complete, or
    auto-dismiss a task.
21. **The API and frontend are planning only;** no endpoint and no UI ship in P23-A; a
    future backend / frontend preserves the proposed shapes unless a new versioned
    contract is approved.

## 13. Counterexamples (must fail or be rejected)

1. **C1 -- acknowledging a task executes the action.** An `acknowledge` (or `in_progress`,
   or `complete`) call that runs the linked P22 action -- rejected; a task is a view, not
   an executor.
2. **C2 -- a notification event sends an external message.** A state change that opens a
   socket, sends an email, or posts a webhook -- rejected; P23-A delivers nothing.
3. **C3 -- `approval_pending` bypasses the checker.** Completing an `approval_pending`
   task that also grants P19 / P20 / P21 quorum or approves the approval -- rejected; the
   task mirrors the gate, it never changes it.
4. **C4 -- `source_unknown` displayed healthy.** A `source_unknown` task shown as green /
   success, or completed as healthy while the linked source is still `unknown` --
   rejected; unknown is never healthy.
5. **C5 -- `backup_check_warning` disguised as success.** A P22-G `completed_with_warning`
   completion surfaced as an `execution_completed` / success task -- rejected; a warning
   is never a success.
6. **C6 -- `dismissed` deletes audit history.** A dismiss that removes, overwrites, or
   truncates the underlying P18 / P19 / P20 / P21 / P22 audit trail -- rejected; the queue
   is a view, not the system of record.
7. **C7 -- tenant task leaks across contexts.** A task with `tenant_id == A` visible to an
   operator in tenant B's context (without the identity-only platform-scope path) --
   rejected (boundary violation).
8. **C8 -- a product business task in the platform queue.** An order / payment / invoice /
   customer / inventory / ledger follow-up materialized as a P23 task -- rejected;
   product business tasks are out of scope for platform P23.
9. **C9 -- completing a task whose gate is still open.** Completing an `execution_ready`
   task whose P22 execution is still at `dry_run_passed`, or an `approval_pending` task
   whose approval is still `pending_review` -- rejected; completion cannot fabricate
   completion of the underlying work.
10. **C10 -- a synthetic execution task.** A task that, when completed, runs an action --
    rejected; the only execution-shaped task is `execution_ready`, and it points at a real
    P22 execution request and executes nothing on completion.
11. **C11 -- a terminal task is reopened.** A transition out of `completed` / `dismissed` /
    `expired` / `failed` -- rejected; reopening requires a new task.
12. **C12 -- auto-approval via the queue.** A task completion that flips a P19 / P20 / P21
    approval state, grants quorum, or waives maker-checker -- rejected.
13. **C13 -- an auto-execution severity tier.** A `critical` severity that triggers
    execution -- rejected; the highest severity only ranks the queue.
14. **C14 -- a raw secret in a task / notification field.** A summary, reason, evidence, or
    notification field containing a credential, DSN, host, port, connection string, token,
    password, cookie, auth header, stack trace, raw body, or log line -- rejected
    (redaction violation).
15. **C15 -- a tenant business payload in a task.** A task carrying an order id / payment
    id / invoice id / customer record / inventory record / ledger entry as payload --
    rejected; `tenant_id` is a scoped id only.
16. **C16 -- cross-tenant dedup.** Tenant-A and tenant-B events collapsed into one task --
    rejected; dedup is per-tenant.
17. **C17 -- a duplicate task on replay.** Re-emitting the same event for the same active
    task creating a second active task or a duplicate notification -- rejected; replay is
    idempotent.
18. **C18 -- an unaudited transition.** A state change that lands without exactly one task
    audit event carrying `previous_state`, `next_state`, `correlation_id`, and linked
    ids -- rejected (contract violation).
19. **C19 -- severity lowered to hide a warning.** A `backup_check_warning` or
    `source_unknown` task ranked `low` / healthy to clear the queue -- rejected.
20. **C20 -- an AI agent auto-completing / auto-executing.** An AI copilot path that
    completes, dismisses, approves, or executes a task without a human operator --
    rejected (section 15).
21. **C21 -- a migration or table added in P23-A.** Any backend, frontend, migration,
    alembic change, table, test, or dependency change added in P23-A -- rejected; P23-A is
    docs / ledger only.
22. **C22 -- a real queue / worker / scheduler in P23-A.** Any runtime drain loop, worker,
    scheduler, or notification sender added in P23-A -- rejected; P23-A defines the
    contract only.
23. **C23 -- a new auth transport in P23-A.** Any new token, session model, or role
    introduced in P23-A -- rejected; P23 reuses the existing guard.
24. **C24 -- owner grants privilege.** An operator self-assigning a task outside their
    visibility, or gaining executor / checker power by owning a task -- rejected.

## 14. P23-B Entry Gate (future)

A future P23-B is permitted to implement **only a non-executing, non-sending backend
skeleton**: an in-memory (or existing-safe) read model that materializes tasks from
prior-phase events, the task-state management endpoints (acknowledge / assign /
in-progress / complete / dismiss) as pure state transitions, the dedup / severity /
correlation logic, and unit tests -- wired to the P18 / P21 / P22 read paths and the P10
identity-only guard, able to receive, deduplicate, rank, triage, and audit a task, but
**not to execute any action, not to approve any approval, and not to deliver any
notification**.

This gate is the counterpart to the P23-A-only non-goals (1.3.1): the runtime code,
backend handlers, in-memory read model, and task-state skeleton that are forbidden in
P23-A are exactly the non-executing skeleton P23-B may begin to implement. The all-P23
non-goals (1.3.2) bind P23-B equally; nothing in this section relaxes them, and any P23-B
migration (if a persisted store is proposed) requires separate explicit approval in the
P23-B contract review.

P23-B (and all of P23 before a separately approved delivery / persistence phase) **must
not**:

- execute any P22 action, approve any approval, or mutate any registry field;
- deliver any notification (no in-app push, no email, no webhook); notification events
  stay at `delivery_state == recorded`;
- add a real queue worker, drain loop, scheduler, or on-call / escalation engine, unless
  separately and explicitly approved outside this contract;
- add any migration, alembic change, table, or column unless explicitly approved in the
  P23-B contract review (an in-memory / existing-safe read model is preferred);
- implement any frontend (the queue page / drawer / badge are a later, separately approved
  slice);
- carry any product business task or tenant business payload;
- rewrite auth / RBAC / session / tenancy;
- delete or truncate audit history on dismiss / expire;
- display `source_unknown` or `backup_check_warning` as healthy / success;
- touch product-dev-recovered or any product business path.

**Real notification delivery and a persisted queue / worker are reserved for separately
approved phases** and must remain behind the never-leaked list and the identity-only
platform-operator guard. P23-B must begin from this contract and may not change the task
type catalog, the exclusion list, the state machine, the data model fields, the
notification boundary, the API shapes, the RBAC visibility rules, the audit fields, the
dedup / severity / correlation rules, or the never-leaked list without a new contract
revision accepted by the CTO.

## 15. Future AI Operator Copilot Note

Any future AI Operator Copilot must operate **through** this queue substrate, never
around it. The boundary:

- The AI may **read** the task queue and task detail via approved, read-only tools.
- The AI may **propose** a triage action (acknowledge, self-assign, complete-with-evidence,
  dismiss) and may **draft** an evidence note, but only as a proposal.
- The AI may **apply a triage action only after explicit operator confirmation** -- a
  human identity-only platform-operator must own the action. The AI is never the owner of
  record for an `execution_ready` completion and never the executor.
- The AI **cannot execute actions, approve approvals, auto-dismiss, or auto-complete
  tasks.** There is no AI path to an executing state, no AI self-approval, and no AI
  break-glass.
- **Every AI action must be audited** as a task audit event, with the AI proposal recorded
  as redacted metadata and `actor_role` set to the confirming operator's role.
- **AI tool calls must be linked** to the task, correlation, and underlying approval /
  execution ids, so every AI proposal is traceable to a human-gated action.
- **Real delivery and real execution remain separately gated** behind future phases. The
  queue substrate records AI-assisted triage; it does not run or deliver anything.

This section names a future boundary only. P23-A implements no AI copilot, grants no AI
triage / execution / approval power, and adds no AI-specific runtime code.

## 16. Docs-Only and Contract-Only Statement

P23-A is **docs-only and contract-only**. It ships:

- `docs/ai/PLATFORM_PRODUCT_P23_OPERATOR_TASK_NOTIFICATION_QUEUE_CONTRACT.md` -- this
  contract.
- `docs/ai/README.md` -- the P23 entry in the Platform Product Track read order.
- `ai-ledger/platform/2026-07-04_p23a_operator_task_notification_queue_contract.md` -- the
  ledger.

There is **no runtime code, no backend, no frontend, no migration, no alembic change, no
table, no test code, and no dependency change** in P23-A. P23-A defines the operator task
/ notification queue contract only; it does not execute, approve, dispatch, queue,
schedule, deliver, migrate, or implement any task, notification, action, approval, or
storage path. **A task is a view, not an executor. A notification is a record, not a
delivery.** Real queue materialization, notification delivery, and the frontend are
reserved for separately approved future phases. **P23-B is not started.**
