# Platform Product P20 -- Durable Approval Governance Contract

**Status:** Contract only (P20-A). No runtime code, no backend handlers, no frontend
UI, no migrations, no alembic changes, no tests, and no dependency changes. Accepted by
the CTO before any P20-B implementation may begin.
**Phase:** P20-A Durable Approval Governance Contract
**Date:** 2026-06-25
**Base:** `e831da0` (origin/platform-dev -- P19-D approval workflow closeout,
P19_APPROVAL_WORKFLOW_READY)
**Depends on:** P10 (identity-only super_admin guard, PlatformAuditEvent, source-status
vocabulary, redact_metadata allowlist), P11 (Platform Admin Cockpit boundary), P12
(Support Console support-safe subset), P13/P14 (Operations Observability plus
unavailable_reason / degraded_reason), P15 (Incident Triage read-only contract), P16
(Worktree Execution Harness), P17 (Platform Registry and Tenant Lifecycle Contract), P18
(Controlled Platform Actions Contract: action catalog, validate, request, request detail,
request queue, registry source status), P19 (Controlled Action Approval Workflow
Contract: approval lifecycle, request, decision, record, queue, audit; approve resolves to
execution_blocked; in-memory store only).
**Author:** Codex (Claude worker)

---

## 1. Goal and Non-Goals

### 1.1 Goal

P19 delivered the controlled action approval workflow: a complete, non-executing,
identity-only approve / reject boundary on top of the P18 request layer, with an in-memory
approval store. P19 approvals do not survive a process restart, are single-decision, and
resolve to `execution_blocked` forever. P19 deliberately left five governance gaps open.

P20 is the **durable approval governance** layer. It does not execute anything. It defines
the platform contract for persisted approvals, separation of duties, the execution gate,
and durable audit retention, so that any future implementation is bounded before a single
line of runtime code is written.

P20-A fixes five things before any P20 implementation may begin:

1. The **persistent approval store contract**: the durable `ApprovalRecord` and
   `ApprovalDecision` shapes, digest-only idempotency, full reason / comment redaction,
   retention / purge / export boundaries, and unknown / degraded / read-only fallback.
2. The **dual-control policy contract**: the permission matrix across identity-only
   super_admin, support_operator, and engineering_operator; maker-checker separation;
   quorum; the explicit denial of tenant-contextual identity; and the explicit denial of
   emergency override by default.
3. The **execution readiness gate contract**: approval is not execution,
   `execution_allowed` defaults to and stays `false`, an approved approval is still not
   executable, every destructive or tenant-mutating action stops, and a restore-test
   request is a request only.
4. The **audit contract** for durable governance: every state change is audited with the
   required fields, and no raw secret, DSN, host:port, token, password, operator secret,
   or tenant payload is ever recorded.
5. The **state machine** for durable approvals, with explicit terminals and transitions,
   including `superseded` and `failed_validation`.

P20-A is **contract only**. It ships **no runtime code**.

The single most important invariant of P20, repeated throughout this document:

> **Approval is not execution, and durability is not execution.** A durable approval that
> reaches `approved_execution_blocked` with a satisfied quorum is still not executed. It
> does not run the action, does not mutate any P17 registry field or lifecycle state, and
> leaves `execution_allowed == false`. There is no path in P20 from approval to execution.

### 1.2 In scope (contract layer)

- Define the persistent approval store contract: durable `ApprovalRecord`,
  `ApprovalDecision`, digest-only idempotency, reason / comment redaction, retention /
  purge / export, and unknown / degraded / read-only fallback.
- Define the dual-control policy contract: actors, the permission matrix, maker-checker
  separation, quorum, the denial of tenant-contextual identity, and the denial of
  emergency override by default.
- Define the execution readiness gate contract: `approval != execution`,
  `execution_allowed == false` by default and immutable to `true` in P20, the
  `approved_execution_blocked` ceiling, the stop rule for destructive and tenant-mutating
  actions, and the request-only rule for `backup.restore_test_request`.
- Define the audit contract: required fields per event, append-only durability, and the
  explicit list of values that must never be recorded.
- Define the durable approval state machine with explicit terminals and transitions.
- Define acceptance criteria and counterexamples.
- Define the P20-B entry gate (durable approval read / write skeleton or storage
  abstraction skeleton only; migration default-denied).

### 1.3 Non-goals (explicit, for ALL of P20, not only P20-A)

- No runtime code, no backend handlers, no frontend UI, no migrations, no alembic
  changes, no test code, and no dependency changes.
- No auth / RBAC / session / tenancy / payment / business-data code or rewrite.
- **No execution of any controlled action.** A durable approval that reaches quorum and
  `approved_execution_blocked` still does not execute. Even P20-B is restricted to a
  durable approval read / write skeleton (or a storage abstraction skeleton) and must not
  execute, must not mutate tenant state, and must not introduce a real durable backend or
  a migration unless that migration is separately gated and approved by the CTO.
- **No real durable backend in P20-A.** P20-A defines the durable store contract only. It
  does not pick a database, does not add a table, and does not add a migration.
- **No automation runner, no execution scheduler.** P20 defines human maker-checker
  decisions only. There is no scheduled, queued, or self-service execution of an approved
  action in P20. The durable store is not a hidden execution queue.
- **No real rollback / restore.** `backup.restore_test_request` remains a request only.
  No restore, undo, or rollback path is implemented or unblocked in P20.
- **No notification / escalation implementation.** P20-A may name notification as a
  future contract; it does not implement outbound channels, templates, or recipients.
- No product business code, no touch of product-dev-recovered, no push to any product
  branch, and no merge or push of platform-dev.

## 2. Relationship to Prior Phases (P10 through P19)

P20 introduces **no new auth, RBAC, session, observability, data-source, or action
concepts**. It is the durable governance layer that P19 left open (P19 approvals are
in-memory, single-decision, and execution-blocked forever).

| Prior phase | What P20 consumes / extends |
|---|---|
| **P10** identity-only guard, PlatformAuditEvent, source-status vocabulary, redact_metadata allowlist | Every durable governance operation runs behind the P10 identity-only super_admin guard. The P20 durable audit event is a typed specialization of PlatformAuditEvent. The P10 redact_metadata allowlist applies to every durable reason, comment, and metadata payload. The source-status rules (unknown is never healthy, null is never zero) govern durable re-validation and the `failed_validation` state. |
| **P11** Cockpit | A future approved phase may render a durable approval surface (request context, maker / checker columns, quorum progress). P20-A adds no cockpit controls and no execute button. |
| **P12** Support Console | A support_operator may open a durable approval request for `support_mode.on` / `support_mode.off` only, through the support-safe path. No raw failure detail, raw payload, or tenant business data may appear in any durable request, decision, record, response, or audit event. |
| **P13 / P14** Operations Observability | Durable approvals carry `unavailable_reason` and `degraded_reason` from P13/P14 through the underlying P18 request when a source is down. The durable store's read-only / degraded fallback reuses this vocabulary. P20 creates no new observability infrastructure. |
| **P15** Incident Triage | A durable approval for `incident.flag_set` / `incident.flag_clear` links to the P15 IncidentTriageSnapshot context inherited from the underlying P18 request. P20 itself remains contract only. |
| **P16** Worktree Execution Harness | Any future execution of an approved durable action must run through the P16 governed harness. P20-A defines the execution readiness gate shape; it does not invoke the harness and does not unlock execution. |
| **P17** Registry and Tenant Lifecycle | Every durable approval wraps a P18 request that targets a P17 PlatformTenantRegistry field or lifecycle transition. Durable approvals never mutate the P17 registry; they only record human maker-checker decisions about a request that, if ever executed in a future phase, would mutate it. |
| **P18** Controlled Platform Actions | P20 is the durable governance layer on top of the P18 request skeleton and the P19 approval workflow. A durable approval references a recorded P18 `action_id` (a request with P18 `result == accepted`, `executed == False`) and the P19 approval envelope. Durable approval never changes the P18 `executed` flag. The P18 registry `source_status` is a hard precondition for quorum (section 4) and for durable re-validation (section 3.6, section 6). |
| **P19** Approval Workflow | P20 reuses the P19 approval lifecycle semantics (approve resolves to execution-blocked; reject is final; every transition is audited; identity-only) and tightens them: the store becomes durable, the decision becomes dual-control (maker-checker with quorum), the audit becomes durable with retention, and two new terminal states (`superseded`, `failed_validation`) are added. P20 does not weaken any P19 safety rule. |

## 3. Persistent Approval Store Contract

P20 defines the durable store contract. All models are `extra = forbid` (no undeclared
fields, no leaks). All timestamps are UTC ISO-8601. All `reason`, `comment`, and
`metadata` values are passed through the P10 `redact_metadata` allowlist before they are
stored, responded, or audited. The store is append-mostly for audit and state-journaled
for the record: a transition updates `state`, `previous_state`, the `checkers` log,
`decision`, `quorum_met`, `validation_status`, `audit_event_id`, and `updated_at` only.

### 3.1 ApprovalRecord (durable)

The persisted durable approval record. This is the single source of truth for a durable
approval's state.

```text
ApprovalRecord {
  approval_id          : uuid      -- required. Unique per durable approval.
  action_id            : uuid      -- required. The wrapped P18 ActionRequestResponse
                                    -- action_id (P18 result == accepted, executed == False).
  tenant_id            : uuid      -- nullable. Null for platform-wide actions (for example
                                    -- incident.flag_set without a tenant).
  action_type          : enum      -- required. A P18 action_type.
  action_class         : enum      -- required. read | write | write_request. Maps the P18
                                    -- classification; governs quorum (section 4.5).
  state                : enum      -- required. pending_review | approved_execution_blocked
                                    -- | rejected | expired | cancelled | superseded |
                                    -- failed_validation (section 6).
  maker                : string    -- required. The identity-only actor id that opened the
                                    -- request (requested_by). Never counted as a checker.
  maker_at             : timestamp -- required. UTC ISO-8601.
  checkers             : list      -- required. Append-only log of checker decisions:
                                    -- [{checker_id, decided_at, decision, reason_redacted,
                                    -- audit_event_id}]. Every checker_id is a distinct
                                    -- identity-only super_admin and MUST differ from maker.
  quorum_required      : int       -- required. Floor per action_class (section 4.5):
                                    -- write and write_request >= 2; read >= 1 if opened.
                                    -- The maker is excluded from the quorum count.
  quorum_met           : bool      -- required. True only when count of distinct approve
                                    -- checkers (none the maker) >= quorum_required and no
                                    -- reject has been recorded.
  decision             : enum      -- nullable. approve | reject | null. Null until a
                                    -- terminal decision (collective approve at quorum, or
                                    -- any reject).
  reason               : string    -- required. Redacted. The maker reason, followed by
                                    -- each checker reason in decision order.
  request_digest       : string    -- required. SHA-256 of the canonical request envelope
                                    -- (action_id, action_type, tenant_id, requested_state,
                                    -- maker). Drives supersession and durable dedup.
  idempotency_key_digest : string  -- required. SHA-256 of the client idempotency key. The
                                    -- RAW key is NEVER stored, logged, or returned (3.3).
  expires_at           : timestamp -- required. UTC ISO-8601; MUST be in the future at
                                    -- creation. The decision-window TTL. A durable
                                    -- approval must expire.
  durable_retain_until : timestamp -- required. UTC ISO-8601. The retention TTL: how long
                                    -- the durable record and its audit events are kept
                                    -- after the record reaches a terminal state.
  execution_allowed    : bool      -- required. DEFAULT false. Always false in P20 (5.2).
  execution_gate       : enum      -- required. blocked | not_authorized. DEFAULT blocked.
                                    -- The only value reachable in P20 is blocked.
  redaction_applied    : bool      -- required. DEFAULT true.
  storage_class        : enum      -- required. durable | existing_safe | memory. P20-A
                                    -- defines the durable contract; P20-B may implement a
                                    -- durable skeleton only if separately gated (10).
  retention_class      : enum      -- required. standard | long | legal_hold. legal_hold
                                    -- suspends automated purge (3.5).
  validation_status    : enum      -- required. valid | source_unknown | superseded_scope |
                                    -- stale. The durable re-validation result (3.6).
  superseded_by        : uuid      -- nullable. The approval_id that superseded this one.
  previous_state       : enum      -- nullable. The state before the last transition.
  audit_event_id       : uuid      -- required. The id of the last durable audit event for
                                    -- this approval.
  correlation_id       : string    -- nullable.
  created_at           : timestamp -- required. UTC ISO-8601.
  updated_at           : timestamp -- required. UTC ISO-8601.
  store_version        : int       -- required. Optimistic-concurrency / schema version.
}
```

### 3.2 ApprovalDecision (single checker)

The inbound body for one checker to record an approve or reject on a pending durable
approval. Only an identity-only super_admin who is not the maker may supply a valid one.

```text
ApprovalDecision {
  approval_id        : uuid      -- required. The durable approval being decided.
  decision           : enum      -- required. approve | reject.
  approver_id        : string    -- required. The identity-only super_admin actor id. MUST
                                  -- differ from maker (4.4). A repeat or maker id is
                                  -- denied and audited as approval_denied.
  reason             : string    -- required. Non-empty; redacted via the P10 allowlist.
  idempotency_key    : string    -- required. Client-supplied. Only its SHA-256 digest is
                                  -- stored (3.3); the raw value is discarded after hashing.
  confirm            : bool      -- required. Explicit confirmation token. A decision lands
                                  -- only after this is true.
  correlation_id     : string    -- nullable.
  metadata           : object    -- nullable. Redacted before audit; never raw secrets.
}
```

### 3.3 Idempotency key is digest-only

- The client `idempotency_key` is accepted on `ApprovalDecision` (and on request open) for
  deduplication within `(approval_id, decision)` (and `(maker, action_id)` for open).
- **Only the SHA-256 digest of the key is stored** in `idempotency_key_digest`. The raw
  key is hashed at the boundary and never persisted, never logged, never returned in any
  response, record, queue item, or audit event.
- Dedup compares digests only. An implementation that stores, logs, returns, or audits the
  raw idempotency key is a contract violation (C3, C17).
- A plaintext idempotency key is treated identically to a secret for redaction purposes:
  it must not appear in any audit field.

### 3.4 Reason / comment redaction

- Every `reason`, `comment`, and `metadata` value passes through the P10 `redact_metadata`
  allowlist before storage, response, or audit. Redaction is applied at the boundary,
  before the value touches the durable store or the audit log.
- `redaction_applied == true` is required on every record and every audit event. A record
  or event with `redaction_applied == false` is a contract violation.
- The following must never appear in any reason, comment, metadata, response, record,
  queue item, or audit field: raw secret, DSN, connection string, hostname, port,
  host:port pair, token, password, operator secret (for example an X-Platform-Operator
  value), API key, stack trace, raw exception, raw log line, or tenant payload (orders,
  payments, invoices, customers, inventory, ledgers).
- A content scan of every persisted reason, comment, and metadata value against the P10
  allowlist must return clean.

### 3.5 Retention, purge, export

- **Retention.** A durable record and its audit events are retained until
  `durable_retain_until`. `retention_class` sets the retention floor: `standard`,
  `long`, or `legal_hold`.
- **Purge.** Purge is **automated retention expiry only**, performed by a system actor
  after `durable_retain_until` elapses on a terminal record. Purge is **never an
  operator-initiated action**: no role, including identity-only super_admin, may manually
  delete or purge a durable record or audit event. `legal_hold` suspends automated purge.
  Every purge emits one `approval_purged` audit event (system actor, redacted).
- **Export.** An identity-only super_admin may export a **redacted** audit / retention
  bundle (for example CSV or JSON) for a bounded time window. Export is append-only
  audited as `approval_exported`. Export is always redacted: digest-only idempotency keys,
  redacted reasons, no raw secrets / DSN / host:port / token / password / operator secret
  / tenant payload. Export does not delete or mutate any record.

### 3.6 Unknown / degraded / read-only fallback

- **Unknown is never healthy.** If the durable store cannot confirm an approval's state,
  quorum, or validation result (for example after a partial outage or a store version
  mismatch), the store refuses to advance any approval to `approved_execution_blocked`. It
  serves reads with a `degraded` / `unknown` badge and denies writes with
  `unavailable_reason = store_unknown`. Unknown is never rendered as healthy, valid, or
  approvable.
- **Degraded source.** If the underlying P18 `source_status` is `unknown` or
  `unavailable`, durable re-validation sets `validation_status = source_unknown`. A write
  or write_request approval with `source_unknown` cannot reach `approved_execution_blocked`
  and transitions to (or stays toward) `failed_validation`. A read approval may stay in
  `pending_review` with a degraded badge; it is never rendered as healthy.
- **Read-only fallback.** If the durable store is in read-only mode (maintenance or
  partial outage), every write operation (open, decide, cancel) is denied with a
  `degraded_reason`; reads remain available and are themselves redacted and audited as
  `approval_read`. Read-only fallback never silently drops an audit event: a write denied
  in read-only mode is still audited.

### 3.7 Storage class and durability boundary

- `storage_class` is `durable`, `existing_safe`, or `memory`. P20-A defines the `durable`
  contract; P20-B may implement a durable skeleton only under the entry gate (section 10).
- The durable store is **not** a queue, not a worker, and not a scheduler. It records
  maker-checker decisions and audit events. It does not drain, dispatch, run, or
  prioritize execution.
- Durability applies to the record and the audit log only. Durability does not create an
  execution path, does not persist a runnable intent, and does not survive a decision into
  execution. A durable `approved_execution_blocked` record is still not executed.

## 4. Dual-Control Policy Contract

P20 reuses the P10 / P18 / P19 identity model. The durable governance surface is
**identity-only** and **dual-control**. Three roles may participate; three identities are
explicitly denied.

### 4.1 Actors

- **identity-only super_admin** -- the only role that may serve as a checker (count toward
  quorum) and the only role that may open a durable approval request for any action. May
  also cancel any pending durable approval, read any record, and export a redacted
  retention bundle.
- **support_operator** -- may open a durable approval request for `support_mode.on` /
  `support_mode.off` only, and may cancel such a request they opened. May NOT be a checker,
  may NOT decide, and may NOT read the full durable queue.
- **engineering_operator** -- may open a durable approval request for the two read actions
  (`provisioning.recheck`, `backup.check`) only, and may cancel such a request they opened.
  May NOT be a checker, may NOT decide, and may NOT read the full durable queue.

### 4.2 Explicitly denied identities

- **tenant admin** -- denied on every durable governance operation (open, decide, read,
  cancel, export). A tenant-scoped actor must never participate in platform durable
  approval decisions, even for its own tenant.
- **tenant-contextual super_admin** -- a super_admin who has selected a tenant context is
  treated as tenant-contextual and is denied (identity-only enforcement, identical to
  P10 / P13 / P15 / P17 / P18 / P19), even though the underlying identity is super_admin.
- **tenant-scoped token** -- any token whose authority is bound to a tenant scope is
  denied on every durable governance operation.

### 4.3 Durable governance permission matrix

`yes` = may perform; `no` = denied (and audited as `approval_denied`); `self` = own
requests only; `checker` = may count toward quorum.

| Capability | super_admin (identity-only) | support_operator | engineering_operator | tenant admin / tenant-contextual super_admin / tenant-scoped token |
|---|---|---|---|---|
| Open durable approval request (write / write_request action) | yes | support_mode.on / off only | no | no |
| Open durable approval request (read action) | yes | no | provisioning.recheck / backup.check only | no |
| Be a checker (record approve / reject, count toward quorum) | yes (not the maker) | no | no | no |
| Cancel a pending durable approval | self (and any as super_admin) | self (support_mode) | self (reads) | no |
| Read durable approval record / history | yes | self (support_mode) | self (reads) | no |
| Read the durable queue | yes | no | no | no |
| Export redacted retention bundle | yes | no | no | no |
| Manually purge / delete a record or audit event | no (system-only) | no | no | no |

### 4.4 Maker-checker separation

- The **maker** (the actor who opened the request, recorded in `maker`) and every
  **checker** (an approver recording a decision) MUST be distinct identities. The maker
  can never be a checker on the same approval.
- A decision whose `approver_id == maker` is denied and audited as `approval_denied`
  (self-approval forbidden). This tightens P19, which only recommended separation.
- Every checker on a single approval MUST be distinct from every other checker. A second
  decision from the same `approver_id` is idempotent if the decision matches (returns the
  prior result, no new state change) and is denied as a decision conflict if the decision
  differs.
- Separation of duties is recorded transparently: `maker`, the `checkers` log, and the
  audit events name every identity. There is no anonymous or shared checker identity.

### 4.5 Quorum

- An approval reaches `approved_execution_blocked` only when `quorum_met == true`:
  the count of distinct approve checkers (none of them the maker) is at least
  `quorum_required`, and no reject has been recorded.
- `quorum_required` floor by `action_class`:
  - **write** (`tenant.pause`, `tenant.resume`, `incident.flag_set`, `incident.flag_clear`,
    `lifecycle.transition`): `quorum_required >= 2` distinct checkers, none the maker.
  - **write_request** (`backup.restore_test_request`): `quorum_required >= 2` distinct
    checkers, none the maker. Even at quorum the action stays `execution_blocked`.
  - **read** (`provisioning.recheck`, `backup.check`): a durable approval is optional; if
    opened, `quorum_required >= 1` checker distinct from the maker.
- `quorum_required` may be configured upward per action_type or tenant by a future
  governance change, but never below the floor, and never below 2 for write /
  write_request.
- A partial approve (fewer than `quorum_required` approve checkers, no reject) leaves the
  approval in `pending_review` with `quorum_met == false`. Partial approval is never
  executed and is never rendered as approved.

### 4.6 Emergency override (forbidden by default)

- P20-A defines **no emergency override and no break-glass path**. There is no single
  checker, no super-approver, and no role that can bypass maker-checker separation or
  quorum, and no role that can set `execution_allowed == true`.
- Any emergency override, single-approver bypass, or execution unlock must be a
  **separately approved future contract** accepted by the CTO. Until such a contract is
  accepted, the permission matrix above is closed and execution stays blocked regardless
  of role, quorum, or urgency.
- `execution_allowed` is immutable to `true` by any P20 operation (section 5.2).

### 4.7 Tenant-contextual identity denied

- A tenant admin, a tenant-contextual super_admin, and a tenant-scoped token are denied on
  every durable governance operation, including open, decide, cancel, read, queue, and
  export. Every denial is audited as `approval_denied` with the actor's
  `identity_context`.
- The durable governance surface is cross-tenant and identity-only. A tenant-contextual
  identity must not see durable approval controls (hidden, not merely disabled), must not
  read another operator's records, and must not influence quorum.

## 5. Execution Readiness Gate Contract

### 5.1 Approval is not execution

- A durable approval records a human maker-checker decision about intent. It is not an
  execution, not a schedule, not a dispatch, and not a runnable intent. The P18
  `executed` flag stays `false`.

### 5.2 execution_allowed defaults to false and is immutable in P20

- `execution_allowed` is `false` by default on every durable record and stays `false`. No
  P20 operation, API, queue, worker, scheduler, audit event, or UI control sets
  `execution_allowed = true`.
- `execution_gate` is `blocked` by default. The only value reachable in P20 is `blocked`.
  Any attempt to move it off `blocked` is denied and audited as `approval_denied`
  (`not_authorized`).
- Execution requires a **separately approved future execution contract** (a future
  P-Exec phase) that defines the execution readiness gate, pre-execution re-validation,
  P16 governed harness invocation, and post-execution audit. Until that contract is
  accepted and implemented, there is no execution path.

### 5.3 approved_execution_blocked is the ceiling

- The highest state a durable approval can reach in P20 is
  `approved_execution_blocked`. There is no `ready_to_execute`, `queued_for_run`,
  `executing`, or `executed` state.
- An approval at `approved_execution_blocked` with `quorum_met == true` is still not
  executed, not runnable, and `execution_allowed == false`. It remains
  `approved_execution_blocked` until it transitions to a terminal state (`superseded`,
  `failed_validation`, or `expired` via durable TTL).

### 5.4 Destructive and tenant-mutating actions stop

- Every destructive or tenant-mutating action stops at `approved_execution_blocked`. These
  include `tenant.pause`, `tenant.resume`, `incident.flag_set`, `incident.flag_clear`,
  `lifecycle.transition`, and `backup.restore_test_request`.
- Even with `quorum_met == true`, none of these actions executes, applies, runs, or
  mutates a P17 registry field, lifecycle state, flag, or any tenant business record.
- The durable store is not an execution queue. No consumer, worker, scheduler, or runner
  defined in P20 drains approved approvals.

### 5.5 backup.restore_test_request is request-only

- `backup.restore_test_request` is a **write_request** action. An approved durable
  restore-test request records an approved intent to request a restore test. It does not
  perform a restore, does not touch a backup snapshot, and does not mutate tenant data.
- The restore test itself (non-destructive, isolated) is a **separately gated future
  action**, not part of P20. P20-A does not define, implement, or unlock it.
- `backup.restore_test_request` additionally requires a known backup source
  (`source_status != unknown`); an unknown source sets `validation_status = source_unknown`
  and blocks quorum (4.5) and reaching `approved_execution_blocked`.

## 6. State Machine

A durable approval moves through exactly seven states. An approval not in one of these
states is not a P20 approval and has no contract.

```text
 pending_review --+--> approved_execution_blocked
                  +--> rejected            (terminal, final)
                  +--> expired             (terminal)
                  +--> cancelled           (terminal)
                  +--> failed_validation   (terminal)

 approved_execution_blocked --+--> superseded         (terminal)
                              +--> failed_validation  (terminal)
                              +--> expired            (terminal, durable TTL)
```

| State | Meaning | Terminal | Reachable next |
|---|---|---|---|
| `pending_review` | A durable request is recorded and resident, awaiting checker decisions. Quorum not yet met; no reject recorded. | no | `approved_execution_blocked`, `rejected`, `expired`, `cancelled`, `failed_validation` |
| `approved_execution_blocked` | Quorum met (maker-checker, distinct checkers, no reject). Approved intent recorded. **Not executed.** `execution_allowed == false`, `execution_gate == blocked`. | no | `superseded`, `failed_validation`, `expired` |
| `rejected` | Any checker recorded reject, or the request was denied at decision. **Reject is final for that approval_id.** | yes | -- |
| `expired` | `expires_at` elapsed with no quorum, or a durable approved approval reached the end of its decision-window TTL, or a decision was attempted on an expired approval. | yes | -- |
| `cancelled` | The maker (or super_admin) cancelled the pending approval before quorum. | yes | -- |
| `superseded` | A newer durable approval for the same `request_digest` scope superseded this one. Only reachable from `approved_execution_blocked` (and `pending_review` in the re-issue case). | yes | -- |
| `failed_validation` | Durable re-validation failed: the underlying P18 `source_status` became `unknown`, the registry target became stale, or the store could not confirm validity. Reachable pre- or post-quorum. | yes | -- |

Required invariants on the state machine:

1. **quorum gates approval.** `pending_review` reaches `approved_execution_blocked` only
   when `quorum_met == true` (distinct checkers, none the maker, no reject).
2. **reject is final for that approval_id.** Once `rejected`, the approval_id accepts no
   further approve that changes state; a later approve is denied and audited as
   `approval_denied`.
3. **approved never becomes executed.** `approved_execution_blocked` has no transition to
   any executing or executed state. Its only transitions are to terminals.
4. **supersession is terminal and explicit.** A superseded approval links to
   `superseded_by`; it cannot be revived or re-approved. Supersession is recorded with a
   `approval_superseded` audit event.
5. **failed_validation is terminal.** A durable approval that fails re-validation cannot
   be "re-healed" into `approved_execution_blocked` by the same record; it requires a new
   durable approval. `failed_validation` is audited with the `validation_status`.
6. **every transition emits exactly one audit event** (section 7), including denied,
   duplicate, expired, cancelled, superseded, and failed-validation outcomes.

## 7. Audit Contract

Every durable approval state change emits exactly one durable audit event. The durable
audit log is **append-only**: two events never share an `event_id`, and no event is edited
or deleted (purge is whole-record retention expiry only, section 3.5, and is itself
audited).

Every audit event MUST carry all of the following required fields:

- `event_id` -- uuid, unique.
- `approval_id` -- the durable approval (nullable only before the record exists).
- `action_id` -- the wrapped P18 request (nullable where no P18 action is involved).
- `actor_id` -- the identity-only actor id (a system actor for expiry / purge).
- `actor_role` -- super_admin | support_operator | engineering_operator | system.
- `identity_context` -- identity_only | tenant_contextual | tenant_scoped_token |
  tenant_admin | system | unknown.
- `decision` -- approve | reject | null.
- `previous_status` -- the state before this event (nullable for creation).
- `next_status` -- the state after this event.
- `reason_redacted` -- the redacted reason / comment (P10 allowlist applied).
- `created_at` -- UTC ISO-8601.
- `request_digest` -- the SHA-256 request digest of the approval.
- `redaction_applied` -- always `true`.

Additional recommended fields: `event_type`, `tenant_id` (nullable), `quorum_required`,
`quorum_met`, `checker_id` (for decision events), `validation_status`, `correlation_id`.

Closed `event_type` set:

| event_type | When it fires |
|---|---|
| `approval_opened` | A durable request is opened, validated, and recorded (state -> pending_review). |
| `approval_decision_recorded` | A checker records an approve or reject (per checker). |
| `approval_quorum_met` | The collective approve reaches quorum; state -> approved_execution_blocked. |
| `approval_rejected` | A checker reject lands; reject is final. |
| `approval_expired` | Decision-window TTL elapsed, or a decision was attempted on an expired approval. |
| `approval_cancelled` | The maker / super_admin cancels a pending approval. |
| `approval_superseded` | A newer approval supersedes this one; links superseded_by. |
| `approval_failed_validation` | Durable re-validation fails; records validation_status. |
| `approval_read` | An operator reads a record, the queue, or history (audited; redacted). |
| `approval_exported` | A super_admin exports a redacted retention bundle. |
| `approval_denied` | Any operation is denied: permission, identity, expired, reject-then-approve, decision conflict, unknown-source write, self-approval, read-only fallback, or malformed request. |
| `approval_purged` | Automated retention expiry purges a terminal record (system actor only). |

Must NEVER be recorded in any audit field (or any record / response / queue item):

- raw secret, DSN, connection string, hostname, port, host:port pair;
- token, password, API key, operator secret (for example X-Platform-Operator);
- raw idempotency key (only its SHA-256 digest);
- stack trace, raw exception, raw log line;
- tenant payload: orders, payments, invoices, customers, inventory, ledgers.

Denied, duplicate, expired, cancelled, superseded, failed-validation, read, export, and
purge outcomes are audited with the same shape as approved outcomes. There is no
unaudited durable governance operation and no unaudited denial.

## 8. Acceptance Criteria

A future phase that implements this contract is accepted only when all of the following
hold:

1. **Durable approval never executes.** Quorum-met approval reaches
   `approved_execution_blocked` and leaves `execution_allowed == false`,
   `execution_gate == blocked`, and the P18 `executed == false`. There is no execution
   path.
2. **Maker-checker separation holds.** No approval reaches `approved_execution_blocked`
   with the maker among its checkers; a self-decision is denied and audited as
   `approval_denied`.
3. **Quorum is enforced.** A write or write_request approval reaches
   `approved_execution_blocked` only with at least two distinct approve checkers (none the
   maker); a partial approve stays `pending_review` with `quorum_met == false`.
4. **Only identity-only super_admin may be a checker.** Any decision attempt by
   support_operator, engineering_operator, tenant admin, a tenant-contextual super_admin,
   or a tenant-scoped token is denied and audited as `approval_denied`.
5. **Tenant-contextual identities are denied on every operation**, and every denial is
   audited.
6. **The lifecycle states are exactly the seven defined.** No other state exists; there is
   no `ready_to_execute`, `queued_for_run`, `executing`, or `executed` state.
7. **Reject is final for that approval_id.** A later approve on a rejected approval_id is
   denied and audited; there is no un-reject.
8. **Every durable approval expires.** `expires_at` is required and in the future at
   creation; an expired approval cannot be accepted, and an approved approval also has a
   durable decision-window TTL after which it is `expired`.
9. **The idempotency key is digest-only.** Only the SHA-256 digest is stored; an audit /
   content scan finds no raw idempotency key in any record, response, queue item, or audit
   field.
10. **Reason / comment redaction is total.** A content scan of every persisted reason,
     comment, and metadata value against the P10 allowlist returns clean; every record and
     event carries `redaction_applied == true`.
11. **No raw secrets, DSNs, host, port, tokens, passwords, operator secrets, or tenant
     payload** appear in any field (content scan returns clean).
12. **Destructive and tenant-mutating actions stop.** `tenant.pause` / `resume`,
     `incident.flag_set` / `clear`, `lifecycle.transition`, and
     `backup.restore_test_request` reach at most `approved_execution_blocked` and never
     execute or mutate tenant data.
13. **backup.restore_test_request is request-only.** An approved restore-test request
     performs no restore and touches no snapshot; it requires a known backup source.
14. **Unknown / degraded / read-only fallback is safe.** An unknown store state blocks
     advancement to `approved_execution_blocked`; a `source_unknown` write transitions to
     `failed_validation`; read-only mode denies writes with a `degraded_reason` and still
     audits them; unknown is never rendered as healthy.
15. **Retention / purge / export are bounded.** Purge is automated retention expiry
     (system actor) only; no operator may manually purge; `legal_hold` suspends purge;
     export is redacted and audited as `approval_exported`.
16. **Every transition emits exactly one audit event** with all required fields
     (section 7); denied, duplicate, expired, cancelled, superseded, failed-validation,
     read, export, and purge outcomes are all audited; the audit log is append-only.
17. **Emergency override is absent.** There is no role, quorum, or urgency that bypasses
     maker-checker separation or sets `execution_allowed == true`; any override requires a
     separately approved future contract.
18. **No runtime code, migrations, frontend, tests, or dependency changes** ship in
     P20-A; P20-A is docs and ledger only.

## 9. Counterexamples (must fail or be rejected)

1. **C1 -- an approved action executing.** A quorum-met approve that runs, schedules,
   applies, or dispatches the underlying P18 action, or that sets `execution_allowed ==
   true` -- rejected; approved must be `approved_execution_blocked` with no execution.
2. **C2 -- self-approval (maker is checker).** A decision whose `approver_id == maker` that
   counts toward quorum -- rejected and audited as `approval_denied`.
3. **C3 -- the raw idempotency key stored or returned.** An implementation that persists,
   logs, returns, or audits the plaintext idempotency key instead of its SHA-256 digest --
   rejected (contract violation).
4. **C4 -- a tenant admin approving.** Any tenant admin successfully opening, deciding,
   reading, or exporting -- rejected and audited as `approval_denied`.
5. **C5 -- a tenant-contextual super_admin approving.** A super_admin with a selected
   tenant context successfully acting as checker -- rejected and audited as
   `approval_denied`.
6. **C6 -- a support_operator or engineering_operator acting as checker.** Either role
   successfully recording a decision that counts toward quorum -- rejected and audited as
   `approval_denied`.
7. **C7 -- quorum of one on a write.** A `tenant.pause` approval reaching
   `approved_execution_blocked` with a single checker -- rejected; the write quorum floor
   is two distinct checkers (none the maker).
8. **C8 -- a partial approve executed or badged as approved.** A `pending_review` approval
   with `quorum_met == false` that is executed, or rendered to the operator as approved --
   rejected.
9. **C9 -- an emergency override.** Any path (a role, a flag, a break-glass token) that
   bypasses maker-checker separation or quorum, or that sets `execution_allowed == true` --
   rejected; P20-A defines no override.
10. **C10 -- a raw secret in a reason or comment.** A reason, comment, or metadata value
    that contains a credential, DSN, host, port, connection string, token, password,
    operator secret, stack trace, or raw exception -- rejected (redaction violation).
11. **C11 -- an expired approval accepted.** An approve that lands after `expires_at`, or
    an approved approval kept runnable past its durable TTL -- rejected and audited as
    `approval_expired`; the state is `expired`.
12. **C12 -- a rejected approval later approved.** A second approve on a rejected
    approval_id that changes state -- rejected; reject is final, audited as
    `approval_denied`.
13. **C13 -- a superseded approval revived.** A transition that returns a `superseded`
    approval to `pending_review` or `approved_execution_blocked` -- rejected; supersession
    is terminal.
14. **C14 -- a failed_validation approval re-healed.** A `failed_validation` record that
    moves back to `approved_execution_blocked` without a new durable approval -- rejected;
    `failed_validation` is terminal.
15. **C15 -- a migration added in P20-A.** Any backend, frontend, migration, alembic
    change, test, or dependency change added in P20-A -- rejected; P20-A is docs and ledger
    only.
16. **C16 -- an operator manually purging a record.** Any role (including identity-only
    super_admin) that manually deletes or purges a durable record or audit event --
    rejected; purge is automated retention expiry (system actor) only.
17. **C17 -- an export leaking sensitive data.** An exported bundle that includes a raw
    idempotency key, raw secret, DSN, host:port, token, password, operator secret, or
    tenant payload -- rejected; export is redacted and audited.
18. **C18 -- backup.restore_test_request performing a restore.** An approved restore-test
    request that performs a restore, touches a snapshot, or mutates tenant data --
    rejected; it is request-only and requires a known source.
19. **C19 -- an unknown store state treated as healthy.** A store that advances an
    approval to `approved_execution_blocked` while it cannot confirm state, quorum, or
    validity, or that renders an unknown / degraded source as healthy -- rejected.
20. **C20 -- an unaudited transition.** Any state change (including denied, superseded, or
    failed_validation) that lands without exactly one durable audit event carrying all
    required fields -- rejected (contract violation).
21. **C21 -- the durable store acting as an execution queue.** A consumer, worker,
    scheduler, or runner that drains approved approvals and runs them -- rejected; the
    durable store records decisions only.
22. **C22 -- a notification leaking sensitive info.** (Forward reference.) Any future
    notification tied to a durable approval that emits a raw secret, DSN, host:port,
    token, password, operator secret, raw idempotency key, or tenant payload -- rejected;
    P20-A names notification as a future contract and permits no such leak.

## 10. P20-B Entry Gate (future)

A future P20-B is permitted to implement **only one** of:

- a **backend durable approval read / write skeleton**: the durable lifecycle, data
  contracts, dual-control, and audit event contract defined here, wired to the P18 request
  layer, the P19 approval envelope, and the P10 identity-only guard, able to open, decide,
  expire, cancel, supersede, fail-validation, and audit a durable approval -- but **not to
  execute any action and not to mutate any tenant state**; or
- a **storage abstraction skeleton**: an interface / adapter for the durable store
  (`storage_class` in {memory, existing_safe}) with no real durable backend wiring.

P20-B (and all of P20) **must**:

- Reuse the P18 / P19 redaction (the P10 `redact_metadata` allowlist) for every reason,
  comment, and metadata field; store only the SHA-256 digest of the idempotency key;
  introduce no new redaction path.
- Reuse the P10 identity-only platform guard; introduce no new auth, RBAC, session, or
  tenancy path.
- Enforce maker-checker separation and quorum on every decision; deny self-approval,
  tenant-contextual identity, and any execution attempt.
- Keep `execution_allowed == false`, `execution_gate == blocked`, and P18 `executed ==
  false` on every response, record, queue item, and audit event.
- Include backend tests for the durable skeleton BEFORE any frontend (UI) work begins.
- Keep `storage_class` in {memory, existing_safe} unless a real durable backend is
  separately gated and approved.

P20-B (and all of P20) **must not**:

- Execute any controlled action, approved or otherwise. There is no execution path in
  P20.
- Mutate tenant state or tenant business data.
- **Add any migration, alembic change, new persistent table, or real durable backend
  unless that migration / backend is separately and explicitly approved by the CTO** in a
  contract revision. The default is denied: without that approval, P20-B is in-memory or
  existing-safe only.
- Implement an automation runner, queue worker, scheduler, or any path that turns an
  approved approval into execution.
- Implement a real rollback / restore path; `backup.restore_test_request` stays
  request-only.
- Implement outbound notification / escalation channels, templates, or recipients
  (notification is a future contract).
- Rewrite auth, RBAC, session, or tenancy.
- Add any product business code or touch product-dev-recovered.
- Add cockpit execute / run / apply / override controls, or any control beyond read, open,
  decide, cancel, and export.
- Bypass the audit boundary for any durable governance operation, including denied,
  duplicate, superseded, failed-validation, export, and purge outcomes.

P20-B must begin from this contract and may not change the lifecycle states, the actors
and permission matrix, the dual-control rules, the data contracts, the required fields,
the safety rules, the execution gate, or the audit event fields without a new contract
revision accepted by the CTO.

## 11. Docs-Only and Contract-Only Statement

P20-A is **docs-only and contract-only**. It ships:

- `docs/ai/PLATFORM_PRODUCT_P20_DURABLE_APPROVAL_GOVERNANCE_CONTRACT.md` -- this contract.
- `docs/ai/README.md` -- the P20 entry in the Platform Product Track read order.
- `ai-ledger/platform/2026-06-25_p20a_durable_approval_governance_contract.md` -- the
  ledger.

There is **no runtime code, no backend, no frontend, no migration, no alembic change, no
test code, and no dependency change** in P20-A. P20-A defines the durable approval
governance contract only; it does not execute, persist (beyond defining the contract),
invoke, or implement any approval, action, store, or execution path. **Approval is not
execution, and durability is not execution.** Execution is reserved for a separately
approved future phase and must run through the P16 governed harness. **P20-B is not
started.**
