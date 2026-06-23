# Platform Product P19 -- Controlled Action Approval Workflow Contract

**Status:** Contract only (P19-A). No runtime code, no backend handlers, no frontend
UI, no migrations, no alembic changes, no tests, and no dependency changes. Accepted by
the CTO before any P19-B implementation may begin.
**Phase:** P19-A Controlled Action Approval Workflow Contract
**Date:** 2026-06-24
**Base:** `bacec41` (origin/platform-dev -- P18-D real registry source status + P18-E
controlled action request queue)
**Depends on:** P10 (identity-only super_admin guard, PlatformAuditEvent, source-status
vocabulary, redact_metadata allowlist), P11 (Platform Admin Cockpit boundary), P12
(Support Console support-safe subset), P13/P14 (Operations Observability plus
unavailable_reason / degraded_reason), P15 (Incident Triage read-only contract), P16
(Worktree Execution Harness), P17 (Platform Registry and Tenant Lifecycle Contract), P18
(Controlled Platform Actions Contract: action catalog, validate, request, request detail,
request queue, registry source status).
**Author:** Codex (Claude worker)

---

## 1. Goal and Non-Goals

### 1.1 Goal

P18 delivered the controlled platform actions contract and a request skeleton that can
receive, validate, deny, deduplicate, audit, and queue an action request -- but P18
**never executes** any action. Every P18 response carries `executed == False`. P19 is
the approval boundary that sits on top of the P18 request layer.

P19 defines the **controlled action approval workflow contract**: the safe, audited,
permission-bounded shape for the approve / reject decision that wraps a recorded P18
action request. P19-A fixes five things before any approval code is written:

1. The **approval lifecycle states** and the explicit rule that an approval is a decision
   about intent, not an execution.
2. The **actors and the approval permission matrix** (who may request an approval, who
   may decide, and who is universally denied).
3. The **data contracts** for the approval request, decision, record, queue, and audit
   event.
4. The **safety rules** that every approval must satisfy (approval never executes,
   never mutates tenant state, never bypasses P18 validation, never leaks raw values,
   always expires, reject is final, decisions are idempotent).
5. The **audit event contract** that records every approval transition, including denied
   and duplicate decisions.

P19-A is **contract only**. It ships **no runtime code**.

The single most important invariant of P19, repeated throughout this document:

> **Approval is not execution.** An approved approval changes the approval state to
> `execution_blocked`. It does not run the action, does not mutate any P17 registry field
> or lifecycle state, and leaves `execution_allowed == false`. There is no path in P19
> from approval to execution.

### 1.2 In scope (contract layer)

- Define the approval lifecycle states: `requested`, `pending_review`, `approved`,
  `rejected`, `expired`, `cancelled`, `execution_blocked`.
- Define the actors and the approval permission matrix across identity-only
  super_admin, support_operator, engineering_operator, and the explicitly denied
  tenant admin, tenant-contextual super_admin, and tenant-scoped token.
- Define the data contracts: ControlledActionApprovalRequest,
  ControlledActionApprovalDecision, ControlledActionApprovalRecord,
  ControlledActionApprovalQueue, and ControlledActionApprovalAuditEvent.
- Define the required fields for every approval record, including
  `execution_allowed == false` by default and `redaction_applied == true` by default.
- Define the safety rules and the audit event contract.
- Define the UI expectations (read-only request context, approve / reject only after
  explicit confirmation, no execute button, approved-vs-executed badge distinction).
- Define acceptance criteria and counterexamples.
- Define the P19-B entry gate (backend approval read / write skeleton only).

### 1.3 Non-goals (explicit, for ALL of P19, not only P19-A)

- No runtime code, no backend handlers, no frontend UI, no migrations, no alembic
  changes, no test code, and no dependency changes.
- No auth / RBAC / session / tenancy / payment / business-data code or rewrite.
- **No execution of any controlled action.** Approval changes approval state only. Even
  P19-B is restricted to an approval read / write skeleton and must not execute, must not
  mutate tenant state, and must not add persistent storage.
- **No automation runner.** P19 defines human approval decisions only. There is no
  scheduled, queued, or self-service execution of an approved action in P19.
- No new observability, backup, or provisioning infrastructure. Approvals reuse P18
  signals, the P10 redaction allowlist, and the P18 request layer as their source of
  truth.
- No product business code, no touch of product-dev-recovered, no push to any product
  branch, and no merge or push of platform-dev.

## 2. Relationship to Prior Phases (P10 through P18)

P19 introduces **no new auth, RBAC, session, observability, data-source, or action
concepts**. It composes the existing platform product track and is the approval layer
that P18 left open (P18 records and queues requests but never approves or executes).

| Prior phase | What P19 consumes / extends |
|---|---|
| **P10** identity-only guard, PlatformAuditEvent, source-status vocabulary, redact_metadata allowlist | Every approval operation runs behind the P10 identity-only super_admin guard. ControlledActionApprovalAuditEvent is a typed specialization of PlatformAuditEvent and of the P18 ControlledActionAuditEvent. The P10 redact_metadata allowlist applies to every approval reason and metadata payload. The source-status rules (unknown is never healthy, null is never zero) govern approval denial when the underlying P18 source is unknown. |
| **P11** Cockpit | The Cockpit may, in a future approved phase, render read-only approval request context and approve / reject controls. P19-A adds no cockpit controls and no execute button. |
| **P12** Support Console | A support_operator may open an approval request for the support_mode action only, through the support-safe path. No raw failure detail, no raw payload, and no tenant business data may appear in any approval request, decision, or response. |
| **P13 / P14** Operations Observability | Approvals carry unavailable_reason and degraded_reason from P13/P14 through the underlying P18 request when a source is down. P19 creates no new observability infrastructure. |
| **P15** Incident Triage | An approval request for incident.flag_set / incident.flag_clear links to the P15 IncidentTriageSnapshot context inherited from the underlying P18 request. P19 itself remains contract only. |
| **P16** Worktree Execution Harness | Any future execution of an approved action must run through the P16 governed harness. P19-A defines the approval decision and audit shape; it does not invoke the harness and does not unlock execution. |
| **P17** Registry and Tenant Lifecycle | Every approval wraps a P18 request that targets a P17 PlatformTenantRegistry field or lifecycle transition. Approvals never mutate the P17 registry; they only record a human decision about a request that, if ever executed in a future phase, would mutate it. |
| **P18** Controlled Platform Actions | P19 is the approval layer on top of the P18 request skeleton. An approval request references a recorded P18 `action_id` (a request with P18 `result == accepted`, `executed == False`). Approval never changes the P18 `executed` flag and never re-runs P18 validation destructively. The P18 registry source_status is a hard precondition for any approval decision (section 5). |

## 3. Approval Lifecycle States

An approval moves through exactly seven states. An approval not in one of these states is
not a P19 approval and has no contract.

```text
 requested --> pending_review --+--> approved --> execution_blocked
                                +--> rejected        (terminal, final)
                                +--> cancelled       (terminal)
                                +--> expired         (terminal)
```

| State | Meaning | Terminal | Reachable next |
|---|---|---|---|
| `requested` | An approval request has been submitted, validated, and recorded. The `approval_requested` audit event has fired. | no | `pending_review` |
| `pending_review` | The request is resident in the approval queue, awaiting a reviewer decision. This is the steady pre-decision state. | no | `approved`, `rejected`, `cancelled`, `expired` |
| `approved` | An authorized approver has recorded decision = approve. Momentary: the record immediately transitions to `execution_blocked`. | no (transient) | `execution_blocked` |
| `rejected` | An authorized approver has recorded decision = reject. **Reject is final for that approval_id.** A later approve on the same approval_id is denied and audited. | yes | -- |
| `expired` | `expires_at` elapsed with no decision. An expired approval can never be accepted. | yes | -- |
| `cancelled` | The requester cancelled the approval before any decision. | yes | -- |
| `execution_blocked` | **The default and only post-approval state in P19.** An approved approval is execution_blocked: a human approved the intent, but the action is NOT executed, NOT runnable, and `execution_allowed == false`. It stays execution_blocked until a separately approved future execution phase exists. | yes (in P19) | -- |

Required invariants on the state machine:

1. **approved does not mean executed.** The `approved` state is transient and always
   resolves to `execution_blocked`. There is no `ready_to_execute`, `queued_for_run`, or
   `executed` state in P19.
2. **execution_blocked is the default post-approval safety state.** Until a separately
   approved future phase exists, every approved approval is execution_blocked and
   `execution_allowed == false`. P19 provides no operator action, API, queue, job, or UI
   control that clears execution_blocked.
3. **reject is final for that approval_id.** Once `rejected`, the approval_id accepts no
   further approve; the only audited outcome of a later approve attempt is
   `approval_denied`.
4. **An expired approval cannot be accepted.** Any approve / reject attempt after
   `expires_at` is denied and audited as `approval_expired` (for an approve) and leaves
   the state `expired`.
5. **Every transition emits exactly one audit event** (section 7), including denied and
   duplicate decisions.

## 4. Actors and Permission Matrix

P19 reuses the P10/P18 identity model. The platform approval surface is
**identity-only**. Three roles may participate; three identities are explicitly denied.

### 4.1 Actors

- **identity-only super_admin** -- the only role that may approve or reject any approval.
  May also submit and cancel approval requests for any action.
- **support_operator** -- may submit an approval request for `support_mode.on` /
  `support_mode.off` only, and may cancel a support_mode approval request they opened. May
  NOT approve or reject anything.
- **engineering_operator** -- may submit an approval request for the two read actions
  (`provisioning.recheck`, `backup.check`) only, and may cancel such a request they
  opened. May NOT approve or reject anything. (Read actions do not require approval to be
  useful, but an approval request is still a valid, no-op-safe envelope.)

### 4.2 Explicitly denied identities

- **tenant admin** -- denied on every approval operation (submit, decide, read, cancel).
  A tenant-scoped actor must never participate in platform approval decisions, even for
  its own tenant. The platform approval surface is cross-tenant and identity-only.
- **tenant-contextual super_admin** -- a super_admin who has selected a tenant context is
  treated as tenant-contextual and is denied (identity-only enforcement, identical to
  P10 / P13 / P15 / P17 / P18).
- **tenant-scoped token** -- any token whose authority is bound to a tenant scope is
  denied on every approval operation.

### 4.3 Approval permission matrix

`yes` = may perform; `no` = denied (and audited as `approval_denied`); `self` = own
requests only.

| Capability | super_admin (identity-only) | support_operator | engineering_operator | tenant admin / tenant-contextual super_admin / tenant-scoped token |
|---|---|---|---|---|
| Submit approval request (write / write_request action) | yes | support_mode.on / off only | no | no |
| Submit approval request (read action) | yes | no | provisioning.recheck / backup.check only | no |
| Approve | yes | no | no | no |
| Reject | yes | no | no | no |
| Cancel a pending approval | self (and any as super_admin) | self (support_mode) | self (reads) | no |
| Read approval request context | yes | self (support_mode) | self (reads) | no |
| Read the approval queue | yes | no | no | no |

Explicit rules (required by the contract):

1. **Only identity-only super_admin may approve or reject.** Any approve / reject attempt
   by support_operator, engineering_operator, tenant admin, a tenant-contextual
   super_admin, or a tenant-scoped token is denied and audited as `approval_denied`.
2. **tenant admin, tenant-contextual super_admin, and tenant-scoped token are denied on
   every approval operation** (submit, decide, read, cancel), and every denial is
   audited.
3. **Decision authority is super_admin only.** The requester and the reviewer may be the
   same identity (recorded transparently in `requested_by` and `reviewed_by`); the
   contract does not hard-block self-approval in P19-A, but it records both identities and
   a future phase may enforce separation of duties. The contract RECOMMENDS that
   `reviewed_by != requested_by` for write and write_request approvals.
4. **support_operator and engineering_operator may submit only within their P18 request
   scope.** They may not decide, may not read the full queue, and may not see another
   operator's requests.
5. **No role may execute an approved action in P19.** Execution is reserved for a
   separately approved future phase and must run through the P16 governed harness.

## 5. Data Contracts

P19 defines five contracts. All models are `extra = forbid` (no undeclared fields, no
leaks). All timestamps are UTC ISO-8601. All `reason` and `metadata` values are passed
through the P10 redact_metadata allowlist before they are stored or audited.

### 5.1 ControlledActionApprovalRequest

The inbound body to open an approval request. It wraps a recorded P18 action request.

```text
ControlledActionApprovalRequest {
  action_id        : uuid      -- required. A recorded P18 ActionRequestResponse.action_id
                                -- whose P18 result == accepted and executed == False.
  tenant_id        : uuid      -- nullable. Null for platform-wide actions (for example
                                -- incident.flag_set without a tenant).
  action_type      : enum      -- required. A P18 action_type. Must be a write or
                                -- write_request action, or one of the two read actions.
  requested_by     : string    -- required. The identity-only actor id opening the request.
  reason           : string    -- required. Non-empty; redacted via the P10 allowlist.
  idempotency_key  : string    -- required. Client-supplied; dedup within
                                -- (requested_by, action_id).
  expires_at       : timestamp -- required. UTC ISO-8601; MUST be in the future at
                                -- creation. An approval must expire.
  confirm          : bool      -- required. Explicit confirmation token to open the
                                -- request (mirrors P18 confirmation).
  correlation_id   : string    -- nullable.
  metadata         : object    -- nullable. Redacted before audit; never raw secrets.
}
```

### 5.2 ControlledActionApprovalDecision

The inbound body to approve or reject a pending approval. Only identity-only super_admin
may supply a valid one.

```text
ControlledActionApprovalDecision {
  approval_id      : uuid      -- required. The approval record being decided.
  decision         : enum      -- required. approve | reject.
  reviewed_by      : string    -- required. The identity-only super_admin actor id.
  reason           : string    -- required. Non-empty; redacted via the P10 allowlist.
  idempotency_key  : string    -- required. Client-supplied; dedup within
                                -- (approval_id, decision).
  confirm          : bool      -- required. Explicit confirmation token to decide.
                                -- Approve / reject land only after this is true.
  correlation_id   : string    -- nullable.
  metadata         : object    -- nullable. Redacted before audit; never raw secrets.
}
```

### 5.3 ControlledActionApprovalRecord

The persisted approval record. This is the single source of truth for an approval's
state. It is append-mostly; a state transition updates `state`, `previous_state`,
`reviewed_*`, `decision`, `audit_event_id`, and `updated_at` only.

```text
ControlledActionApprovalRecord {
  action_id           : uuid      -- required. The wrapped P18 action request id.
  approval_id         : uuid      -- required. Unique per approval.
  tenant_id           : uuid      -- nullable.
  action_type         : enum      -- required. The P18 action_type.
  state               : enum      -- required. requested | pending_review | approved |
                                  -- rejected | expired | cancelled | execution_blocked.
  requested_by        : string    -- required. Identity-only actor id.
  requested_at        : timestamp -- required. UTC ISO-8601.
  reviewed_by         : string    -- nullable. Null until a decision; then the super_admin.
  reviewed_at         : timestamp -- nullable. Null until a decision.
  decision            : enum      -- nullable. approve | reject. Null until decided.
  reason              : string    -- required. Redacted. The request reason, and (after a
                                  -- decision) the decision reason.
  expires_at          : timestamp -- required. UTC ISO-8601. The request expiry.
  execution_allowed   : bool      -- required. DEFAULT false. Always false in P19.
  redaction_applied   : bool      -- required. DEFAULT true.
  idempotency_key     : string    -- required. The request idempotency key.
  previous_state      : enum      -- nullable. The state before the last transition.
  storage             : string    -- required. memory | existing-safe. Never a new
                                  -- persistent store introduced in P19.
  audit_event_id      : uuid      -- required. The id of the last
                                  -- ControlledActionApprovalAuditEvent for this approval.
  correlation_id      : string    -- nullable.
  created_at          : timestamp -- required. UTC ISO-8601.
  updated_at          : timestamp -- required. UTC ISO-8601.
}
```

### 5.4 ControlledActionApprovalQueue

The ephemeral operator queue of approval records. It is read-only and never executes.

```text
ControlledActionApprovalQueue {
  items    : list[ControlledActionApprovalRecord] -- required. Redacted records.
  total    : int      -- required.
  limit    : int      -- required.
  offset   : int      -- required.
  storage  : string   -- required. memory | existing-safe. No database persistence in P19.
  executed : bool     -- required. DEFAULT false. Listing the queue never executes.
}
```

### 5.5 ControlledActionApprovalAuditEvent

Every approval transition emits exactly one. It is a typed specialization of the P10
PlatformAuditEvent and of the P18 ControlledActionAuditEvent. It is append-only; two
events never share an `audit_event_id`. Denied, duplicate, expired, and cancelled
outcomes are audited with the same shape as approved outcomes.

```text
ControlledActionApprovalAuditEvent {
  audit_event_id    : uuid      -- required. Unique.
  event_type        : enum      -- required. approval_requested | approval_approved |
                                -- approval_rejected | approval_expired |
                                -- approval_cancelled | approval_read | approval_denied.
  actor             : string    -- required. The identity-only actor id (nullable
                                -- semantics for a system / expiry actor are recorded in
                                -- identity_context).
  identity_context  : enum      -- required. identity_only | tenant_contextual |
                                -- tenant_scoped_token | tenant_admin | system | unknown.
  tenant_id         : uuid      -- nullable.
  action_id         : uuid      -- nullable. Null where no P18 action is involved (for
                                -- example a denied submit that never recorded an action).
  approval_id       : uuid      -- nullable. Null until the approval record exists.
  decision          : enum      -- nullable. approve | reject | null.
  redaction_applied : bool      -- required. DEFAULT true.
  reason            : string    -- required. Redacted via the P10 allowlist.
  timestamp         : timestamp -- required. UTC ISO-8601.
}
```

## 6. Required Fields (per approval record)

Every ControlledActionApprovalRecord MUST carry all of the following. A record missing
any required field, or carrying `execution_allowed == true` or `redaction_applied ==
false`, is a contract violation.

| Field | Required | Default | Notes |
|---|---|---|---|
| `action_id` | yes | -- | The wrapped P18 recorded request id. |
| `approval_id` | yes | -- | Unique per approval. |
| `tenant_id` | yes (nullable ok) | null | Null for platform-wide actions. |
| `action_type` | yes | -- | A P18 action_type. |
| `requested_by` | yes | -- | Identity-only actor id. |
| `requested_at` | yes | -- | UTC ISO-8601. |
| `reviewed_by` | yes (nullable ok) | null | The deciding super_admin; null pre-decision. |
| `reviewed_at` | yes (nullable ok) | null | UTC ISO-8601; null pre-decision. |
| `decision` | yes (nullable ok) | null | approve \| reject; null pre-decision. |
| `reason` | yes | -- | Redacted; non-empty. |
| `expires_at` | yes | -- | UTC ISO-8601; must be in the future at creation. |
| `execution_allowed` | yes | **false** | Always false in P19. |
| `redaction_applied` | yes | **true** | Always true. |
| `audit_event_id` | yes | -- | The last audit event for this approval. |

Additional required fields defined in section 5.3 (`state`, `idempotency_key`,
`previous_state`, `storage`, `correlation_id`, `created_at`, `updated_at`) are also
mandatory; the table above lists the fields the contract calls out by name.

## 7. Safety Rules

Every approval operation, in every phase that implements this contract, must satisfy all
of the following. A violation rejects the operation and records an `approval_denied`
audit event.

1. **Approval cannot execute the action.** An approve changes the approval state to
   `execution_blocked` only. It must not run, schedule, queue for run, or otherwise cause
   the underlying P18 action to execute. The P18 `executed` flag stays false.
2. **Approval cannot mutate tenant state.** An approval changes approval state only. It
   must never read, write, create, update, or delete tenant business records (orders,
   payments, invoices, customers, inventory, ledgers) and must never mutate a P17 registry
   field or lifecycle state.
3. **Approval cannot bypass P18 validation.** An approval request must reference a P18
   request that already passed P18 validation with a known registry source (or, for the
   two read actions, an explicitly allowed degraded request). An approval must not
   manufacture a passing P18 source_status, must not downgrade an unknown source to known,
   and must not approve a write whose P18 source_status is unknown. The P18 source_status
   is a hard precondition; unknown is never healthy and never approvable for a write.
4. **Approval must not expose raw reason, metadata, or idempotency values.** The `reason`
   and `metadata` fields are passed through the P10 redact_metadata allowlist before
   storage, response, or audit. The `idempotency_key` is never returned in a queue or
   read response. No credential, secret, DSN, connection string, hostname, port, stack
   trace, raw exception, or raw log line may appear in any approval request, decision,
   response, record, or audit event.
5. **Approval must expire.** Every approval request carries a non-null `expires_at` in the
   future at creation. When `expires_at` elapses with no decision, the approval becomes
   `expired` and can never be accepted.
6. **Reject must be final for that approval_id.** Once `rejected`, a later approve on the
   same approval_id is denied and audited as `approval_denied`. There is no un-reject.
7. **Duplicate approval decisions must be idempotent.** A second decision with the same
   `(approval_id, decision)` and the same `idempotency_key` returns the prior result and
   records no new state change. A second decision with the same `approval_id` but a
   different `decision` is denied (decision conflict) and audited. There is no flip-flop.
8. **No raw secrets, logs, DSNs, host, or port in any response or audit.** Every approval
   response, record, queue item, and audit event is redacted via the P10 allowlist. A
   content scan against the allowlist must return clean.
9. **The approval queue must not become a hidden execution queue.** The
   ControlledActionApprovalQueue is read-only. It lists approval records; it does not
   drain, run, dispatch, or prioritize execution. No queue consumer, worker, scheduler, or
   automation runner is defined in P19. An approved approval stays `execution_blocked`
   forever in P19.

Derived hard rules (consequences of the above):

- No approval operation may proceed without the identity-only platform guard (or the
  narrowed support_operator / engineering_operator submit scope). A tenant-contextual
  identity is denied on every operation.
- No approval may land without an audit event. An implementation that can move an approval
  to `approved` or `execution_blocked` without emitting exactly one
  ControlledActionApprovalAuditEvent is a contract violation.
- No approval may fabricate a healthy P18 source. An approval must inherit the P18
  source_status verbatim; unknown stays unknown and blocks a write approval.

## 8. Audit Event Contract

Every approval transition emits exactly one ControlledActionApprovalAuditEvent. The
event types are closed:

| event_type | When it fires |
|---|---|
| `approval_requested` | An approval request is submitted, validated, and recorded (state -> requested / pending_review). |
| `approval_approved` | An identity-only super_admin records decision = approve; the record moves toward execution_blocked. |
| `approval_rejected` | An identity-only super_admin records decision = reject; reject is final. |
| `approval_expired` | expires_at elapses with no decision, or a decision is attempted on an expired approval. |
| `approval_cancelled` | The requester cancels a pending approval before any decision. |
| `approval_read` | An operator reads an approval request context or the queue (audited for visibility; redacted). |
| `approval_denied` | Any operation is denied: permission denied, identity denied, expired approve, reject-then-approve, decision conflict, unknown-source write, or a malformed request. |

Every event (including `approval_denied` and `approval_read`) MUST carry all of:

- `actor` -- the identity-only actor id (or a system actor for expiry).
- `identity_context` -- identity_only | tenant_contextual | tenant_scoped_token |
  tenant_admin | system | unknown.
- `tenant_id` -- nullable.
- `action_id` -- nullable.
- `approval_id` -- nullable until the record exists.
- `decision` -- approve | reject | null.
- `redaction_applied` -- always true.
- `timestamp` -- UTC ISO-8601.

Denied, duplicate, expired, and read outcomes are audited with the same shape as approved
outcomes. There is no unaudited approval operation and no unaudited denial.

## 9. UI Expectations

A future approved phase that renders the approval surface MUST satisfy all of:

1. **Read-only request context.** The approval request view shows the wrapped P18 request
   context (action_type, tenant_id, requested_by, requested_at, reason (redacted),
   expires_at, state). It exposes no raw reason, metadata, idempotency_key, DSN, host, or
   port.
2. **Approve / reject only after explicit confirmation.** Approve and reject controls are
   disabled until the operator supplies an explicit confirmation token (the `confirm`
   field). There is no one-click approve.
3. **No execute button in P19.** There is no execute, run, apply, dispatch, or retry
   control for an approved action. The only decision controls are approve and reject.
4. **Status badges distinguish approved from executed.** An approved approval shows
   "approved (execution blocked)" or equivalent; it never shows "executed", "applied",
   "running", or "done". There is no executed state to badge in P19.
5. **Degraded / unknown must not appear healthy.** If the underlying P18 source_status is
   unknown or unavailable, the UI shows a degraded / unknown badge and disables approve
   for a write; it never renders an unknown source as healthy or approvable.
6. **Tenant-contextual users must not see approval controls.** A tenant admin, a
   tenant-contextual super_admin, or a tenant-scoped token sees no submit, approve,
   reject, cancel, or queue controls. The approval surface is hidden, not merely
   disabled-with-tooltip, for tenant-contextual identities.

## 10. Acceptance Criteria

A future phase that implements this contract is accepted only when all of the following
hold:

1. **Approval never executes.** An approve moves the record to `execution_blocked` and
   leaves `execution_allowed == false` and the P18 `executed == false`. There is no
   execution path.
2. **Only identity-only super_admin may approve or reject.** Any decision attempt by
   support_operator or engineering_operator is denied and audited as `approval_denied`.
3. **tenant admin, tenant-contextual super_admin, and tenant-scoped token are denied on
   every approval operation**, and every denial is audited as `approval_denied`.
4. **The lifecycle states are exactly the seven defined.** No other state exists; there
   is no `ready_to_execute`, `queued_for_run`, or `executed` state.
5. **approved resolves to execution_blocked.** An approve transitions approved ->
   execution_blocked; `execution_allowed` stays false; P19 provides no way to clear
   execution_blocked.
6. **Every approval record carries all required fields** (section 6), with
   `execution_allowed == false` and `redaction_applied == true`.
7. **Every approval request expires.** `expires_at` is required and in the future at
   creation; an approval with no `expires_at`, or with an `expires_at` in the past at
   creation, is rejected and audited.
8. **An expired approval cannot be accepted.** An approve attempted after `expires_at` is
   denied and audited as `approval_expired`; the state is or becomes `expired`.
9. **reject is final for that approval_id.** A later approve on a rejected approval_id is
   denied and audited as `approval_denied`; there is no un-reject.
10. **Duplicate decisions are idempotent.** A second decision with the same
    `(approval_id, decision)` and `idempotency_key` returns the prior result with no new
    state change; a same-approval_id different-decision attempt is denied (decision
    conflict) and audited.
11. **Approval cannot bypass P18 validation or source_status.** An approval request must
    reference a P18 request with a known source (or an explicitly allowed degraded read);
    an approve of a write whose P18 source_status is unknown is denied and audited.
12. **No raw secrets, logs, DSNs, host, or port** appear in any reason, metadata,
    response, record, or audit field (content scan against the P10 allowlist returns
    clean).
13. **The approval queue is read-only and never executes.** `ControlledActionApprovalQueue`
    carries `executed == false` and `storage` in {memory, existing-safe}; no queue worker,
    scheduler, or automation runner exists in P19.
14. **Every transition emits exactly one audit event** with all required fields
    (section 8); denied, duplicate, expired, cancelled, and read outcomes are audited.
15. **The UI hides approval controls for tenant-contextual users**, requires explicit
    confirmation before approve / reject, shows no execute button, badges approved as
    execution-blocked (never executed), and never renders an unknown source as healthy.
16. **No runtime code, migrations, frontend, tests, or dependency changes** ship in
    P19-A; P19-A is docs and ledger only.

## 11. Counterexamples (must fail or be rejected)

1. **C1 -- a tenant admin approving.** Any tenant admin successfully approving an approval
   -- rejected (must 401/403) and audited as `approval_denied`.
2. **C2 -- a tenant-contextual super_admin approving.** A super_admin with a selected
   tenant context successfully approving -- rejected (identity-only enforcement) and
   audited as `approval_denied`.
3. **C3 -- an approved action executing immediately.** An approve that runs, schedules, or
   applies the underlying P18 action, or that sets `execution_allowed == true` -- rejected;
   approved must resolve to `execution_blocked` with no execution.
4. **C4 -- a raw secret in an approval reason.** A reason or metadata value that contains a
   credential, DSN, host, port, connection string, stack trace, or raw exception --
   rejected (redaction allowlist violation).
5. **C5 -- an expired approval accepted.** An approve that lands after `expires_at` --
   rejected and audited as `approval_expired`; the state is `expired`.
6. **C6 -- a rejected approval later approved with the same approval_id.** A second
   approve on a rejected approval_id that succeeds -- rejected; reject is final, audited
   as `approval_denied`.
7. **C7 -- an approval bypassing P18 source_status.** An approve of a write whose P18
   source_status is unknown that proceeds, or any approval that downgrades unknown to known
   -- rejected and audited as `approval_denied`.
8. **C8 -- a migration added in P19-A.** Any backend, frontend, migration, alembic change,
   test, or dependency change added in P19-A -- rejected; P19-A is docs and ledger only.
9. **C9 -- the frontend showing "executed" after approval.** A UI that renders an approved
   approval as "executed", "applied", or "running", or that shows an execute button --
   rejected; approved is execution-blocked and there is no execute control in P19.
10. **C10 -- a tenant-scoped token approving.** Any tenant-scoped token successfully
    approving, rejecting, submitting, or reading the queue -- rejected and audited as
    `approval_denied`.
11. **C11 -- a support_operator approving tenant.pause.** A support_operator successfully
    recording decision = approve on any approval -- rejected and audited as
    `approval_denied`.
12. **C12 -- an engineering_operator approving.** An engineering_operator successfully
    recording any decision -- rejected and audited as `approval_denied`.
13. **C13 -- the approval queue acting as a hidden execution queue.** A queue consumer,
    worker, scheduler, or automation runner that drains approved approvals and runs them --
    rejected; the queue is read-only and there is no automation runner in P19.
14. **C14 -- an unaudited approval transition.** A transition to approved or
    execution_blocked that lands without exactly one ControlledActionApprovalAuditEvent --
    rejected (contract violation).
15. **C15 -- an approval record missing a required field, or with execution_allowed ==
    true.** A record without `expires_at`, `audit_event_id`, or `redaction_applied`, or a
    record that sets `execution_allowed == true` -- rejected.
16. **C16 -- a duplicate approve accepted as a new decision.** A second approve with a
    different `idempotency_key` or reason that records a second approve transition on the
    same approval_id -- rejected; decisions are idempotent, audited as `approval_denied`
    (decision conflict) where the decision differs.
17. **C17 -- an approval mutating tenant business data.** An approval that reads or writes
    an order, payment, invoice, customer, inventory, or ledger record -- rejected
    (boundary violation).
18. **C18 -- runtime code added in P19-A.** Any backend handler, frontend component,
    migration, alembic change, test, or dependency change shipped in P19-A -- rejected;
    P19-A is docs and ledger only.

## 12. P19-B Entry Gate (future)

A future P19-B is permitted to implement **only a backend approval read / write skeleton**:
the approval lifecycle, data contracts, and audit event contract defined here, wired to
the P18 request layer and the P10 identity-only guard, able to receive, validate, record,
decide, expire, cancel, and audit an approval -- but **not to execute any action and not
to mutate any tenant state**.

P19-B (and all of P19) **must**:

- Reuse the P18 redaction (the P10 redact_metadata allowlist) for every reason and
  metadata field; introduce no new redaction path.
- Reuse the P10 identity-only platform guard; introduce no new auth, RBAC, session, or
  tenancy path.
- Store approvals in-memory or in an existing-safe store only; introduce no new
  persistent storage, no new database table, and no migration unless that migration is
  separately gated and approved in the P19-B contract review.
- Include backend tests for the approval skeleton BEFORE any frontend (UI) work begins.
- Keep `execution_allowed == false` and `executed == false` on every response, record,
  and queue item.

P19-B (and all of P19) **must not**:

- Execute any controlled action, approved or otherwise. There is no execution path in
  P19.
- Mutate tenant state or tenant business data.
- Add any migration or alembic change unless separately gated and approved.
- Implement an automation runner, queue worker, scheduler, or any path that turns an
  approved approval into execution.
- Rewrite auth, RBAC, session, or tenancy.
- Add any product business code or touch product-dev-recovered.
- Add cockpit execute / run / apply controls, or any control beyond read, submit,
  approve, reject, and cancel.
- Bypass the audit boundary for any approval operation, including denied and duplicate
  decisions.

P19-B must begin from this contract and may not change the lifecycle states, the actors
and permission matrix, the data contracts, the required fields, the safety rules, or the
audit event fields without a new contract revision accepted by the CTO.

## 13. Docs-Only and Contract-Only Statement

P19-A is **docs-only and contract-only**. It ships:

- `docs/ai/PLATFORM_PRODUCT_P19_APPROVAL_WORKFLOW_CONTRACT.md` -- this contract.
- `docs/ai/README.md` -- the P19 entry in the Platform Product Track read order.
- `ai-ledger/platform/2026-06-24_p19a_approval_workflow_contract.md` -- the ledger.

There is **no runtime code, no backend, no frontend, no migration, no alembic change, no
test code, and no dependency change** in P19-A. P19-A defines the approval workflow
contract only; it does not execute, invoke, or implement any approval or action.
**Approval is not execution.** Execution is reserved for a separately approved future
phase and must run through the P16 governed harness. **P19-B is not started.**
