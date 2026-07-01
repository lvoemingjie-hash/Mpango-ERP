# Platform Product P22 -- Controlled Execution v0 Contract

**Status:** Contract only (P22-A). No runtime code, no backend handlers, no frontend
UI, no migrations, no alembic changes, no tests, and no dependency changes. Accepted by
the CTO before any P22-B execution skeleton may begin.
**Phase:** P22-A Controlled Execution v0 Contract
**Date:** 2026-07-01
**Base:** `41c003e` (origin/platform-dev -- P21 durable approval store closeout: P21-A
contract, P21-B schema / migration plan, P21-C0/C1 migration readiness and public durable
tables, P21-D runtime adapter implementation and storage cutover, and P21-E runtime
closeout all merged; P21_DURABLE_APPROVAL_STORE_READY)
**Depends on:** P10 (identity-only super_admin guard, PlatformAuditEvent, source-status
vocabulary, redact_metadata allowlist), P11 (Platform Admin Cockpit boundary), P12
(Support Console support-safe subset), P13/P14 (Operations Observability plus
unavailable_reason / degraded_reason), P15 (Incident Triage read-only contract), P16
(Worktree Execution Harness), P17 (Platform Registry and Tenant Lifecycle Contract), P18
(Controlled Platform Actions Contract: action catalog, classification, permission matrix,
safety rules, ControlledActionAuditEvent), P19 (Approval Workflow Contract: approve
resolves to execution_blocked), P20 (Durable Approval Governance Contract: persistent
record shape, dual-control policy, execution readiness gate, durable audit, state machine;
approved_execution_blocked is the ceiling), P21 (Durable Approval Store Contract + schema
plan + public durable tables + runtime adapter + closeout: durable storage records,
restart-safe consistency, digest-only idempotency, redaction-before-persistence, durable
append-only audit, retention / purge / export, API compatibility).
**Author:** Codex (Claude worker)

---

## 1. Goal and Non-Goals

### 1.1 Goal

P18 created controlled action *requests* but did not execute them. P19 *approved /
rejected* but every approval resolved to `execution_blocked`. P20 added maker-checker /
quorum *governance* but capped every approval at `approved_execution_blocked`. P21 made
those approvals *durable* (restart-safe records, digest-only idempotency,
redaction-before-persistence, append-only audit, retention). Across P18 through P21 a
single invariant held without exception: an approved, quorum-met, durable approval never
executed. `execution_allowed` stayed `false`, `execution_gate` stayed `blocked`, and the
P18 `executed` flag stayed `false`.

P22 is the **controlled execution** layer. It is the first phase permitted to define --
not perform -- the carefully bounded bridge from an approved durable approval to a real
platform action. P22 defines the smallest, lowest-risk, most-audited execution surface in
the platform: an allowlist of conservative actions, a dry-run-first gate, a fully audited
request / result lifecycle, digest-only idempotency, total redaction, operator
separation, and a fail-closed safety envelope. P22 v0 execution **never mutates tenant
business data**; every v0 action is read-only, reversible through a paired action, or a
non-destructive test request only.

P22-A fixes the boundary before any execution code is written:

1. The **v0 execution allowlist**: the exact, closed set of action types that v0 may
   execute, and the explicit exclusion list (destructive lifecycle, real restore, schema
   migration, data deletion, payment / billing, tenant business records, and arbitrary
   shell / SQL / script execution).
2. The **execution precondition contract**: every condition that must hold before a v0
   action may even be dry-run, let alone executed (identity-only super_admin executor,
   matching durable approval id, approval at `approved_execution_blocked` with quorum met,
   source available, action in allowlist, idempotency key, a passed dry-run, execution
   acknowledgement, no expired / superseded / cancelled / rejected approval, and operator
   separation).
3. The **dry-run model**: a no-mutation validation pass that returns
   `executable == true | false`, the expected audit / event shape, and the precondition
   verdict, before any execution request is accepted.
4. The **execution request model**: the recorded fields of an execution attempt
   (digest-only idempotency, redacted reason / metadata, executor identity, dry-run
   reference, correlation id).
5. The **execution result model**: the execution-record state machine
   (`dry_run_passed | blocked | execution_queued | executing | executed |
   execution_failed | compensation_required | compensation_completed | cancelled`), which
   is a separate lifecycle from the durable approval state machine and does not add an
   `executed` state to the approval.
6. The **audit contract**: the closed set of execution audit events, the never-logged
   list, and the append-only / one-event-per-transition rule.
7. The **idempotency contract**: digest-only replay, same-key-different-payload conflict,
   retry rules for failed execution, and no duplicate audit success.
8. The **safety rules**: allowlist only, dry-run first, fail closed, no silent fallback,
   no arbitrary tool / shell / SQL, no tenant business mutation, no product code path, no
   payment / billing, no raw secrets, unknown is never healthy, approval is not execution,
   durability is not execution.
9. The **operator separation policy**: the maker / checker / executor distinctness rule
   for v0.
10. The **API shape proposal**: planning only (catalog, dry-run, request create / list /
    detail).
11. The **test plan, acceptance criteria, and counterexamples**.
12. The **P22-B entry gate**: what a future execution skeleton may implement and under
    what gates.

P22-A is **contract only**. It ships **no runtime code, no migration, no endpoint, no
queue, no worker**.

The single most important invariant of P22, repeated throughout this document:

> **Approval is not execution. Durable approval is not execution.** A durable,
> restart-safe, quorum-met approval at `approved_execution_blocked` is a precondition for
> v0 execution; it is not execution itself. Even when a v0 action is eventually executed
> under this contract, the action never mutates tenant business data, never runs arbitrary
> shell / SQL / script, never touches payment / billing or product code, and is fully
> audited and reversible where possible. P22-A defines this contract; it performs no
> execution.

### 1.2 In scope (contract layer)

- Define the v0 execution allowlist and the explicit exclusion list (section 3).
- Define the execution precondition contract (section 4).
- Define the dry-run model (request / response shape, no mutation, exclusion verdict,
  expected audit shape) (section 5).
- Define the execution request model (recorded fields, digest-only idempotency, redacted
  reason / metadata, dry-run reference) (section 6).
- Define the execution result model (the execution-record state machine, sync vs queued,
  compensation / reversal) (section 7).
- Define the execution audit contract (closed event set, never-logged list, append-only
  rule) (section 8).
- Define the execution idempotency contract (digest-only replay, conflict, retry,
  no-duplicate-success) (section 9).
- Define the safety rules (section 10).
- Define the operator separation policy (maker / checker / executor) (section 11).
- Define the API shape proposal (planning only) (section 12).
- Define the test plan, acceptance criteria, and counterexamples (sections 13-15).
- Define the P22-B entry gate (section 16).
- Define the future AI Operator Copilot boundary against this execution substrate
  (section 17).

### 1.3 Non-goals

The non-goals split into two groups so the contract does not accidentally forbid the
P22-B work it explicitly permits (section 16):

- **P22-A-only non-goals** (1.3.1) are forbidden in P22-A, but a future P22-B may
  implement the corresponding **non-executing** skeleton under its own entry gate.
- **All-P22 non-goals** (1.3.2) are forbidden across **every** P22 phase unless a new
  contract revision is accepted by the CTO.

#### 1.3.1 P22-A-only non-goals (P22-B may implement these under its gate)

- No runtime code, no backend handlers, no frontend UI, no test code, and no dependency
  changes in P22-A.
- No migrations, no alembic changes, and no new tables or columns in P22-A. (A future
  P22-B migration, if any, requires separate explicit approval in the P22-B contract
  review; see section 16.)
- **No real execution in P22-A.** P22-A defines the contract only. No v0 action is
  executed, dispatched, queued, scheduled, or run in P22-A. (P22-B may add a
  non-executing execution skeleton; real execution of any v0 action is separately
  approved.)
- **No execution scheduler, no queue drain, and no automation runner in P22-A.** (P22-B
  may add a non-executing skeleton; a dispatching worker / queue drain is reserved for a
  separately approved phase.)
- **No notification / escalation implementation in P22-A.** P22-A may name notification as
  a future contract; it implements no outbound channels, templates, or recipients.

#### 1.3.2 All-P22 non-goals (every P22 phase, unless a new contract revision is accepted)

- **No uncontrolled execution.** No v0 action executes outside this contract's
  precondition / dry-run / allowlist / audit envelope, and no excluded action (section 3.2)
  is ever executable in any P22 phase.
- **No tenant business mutation, ever.** No v0 action reads, writes, creates, updates, or
  deletes tenant business records (orders, payments, invoices, customers, inventory,
  ledgers). The v0 allowlist is restricted to platform operational flags (reversible),
  read-only status refreshes, and a non-destructive restore *test* request.
- **No destructive tenant lifecycle execution.** `tenant.pause`, `tenant.resume`, and
  `lifecycle.transition` are excluded from v0 and remain at `approved_execution_blocked`
  with no execution; lifting any exclusion is a new contract revision and a new phase.
- **No real restore.** `backup.restore_test_request` is request-only and targets an
  isolated test environment; it never restores real tenant data and never mutates tenant
  business data.
- **No schema migration and no data deletion as executable v0 actions.** Both are excluded
  from the allowlist forever in v0. (This is distinct from committing migration files,
  which is a P22-A-only non-goal in 1.3.1 and a P22-B gate question in section 16.)
- **No arbitrary shell / SQL / script execution.** No general code-execution surface
  exists or is introduced in any P22 phase.
- **No payment / billing and no product code path.** No v0 action touches any payment,
  billing, invoice, or financial record, or invokes product business code /
  product-dev-recovered.
- **No auth / RBAC / session / tenancy rewrite.** P22 reuses the P10 identity-only guard
  conceptually; no new auth transport is defined or implemented.
- **No AI agent execution.** P22 names a future AI Operator Copilot boundary (section 17);
  it grants no AI execution power and adds no AI-specific runtime code in any P22 phase.
- **No new durable approval execution state.** P22 adds no `executed`, `ready_to_execute`,
  or `execution_ready` state to the durable approval state machine; the execution lifecycle
  lives on the separate execution record. Introducing an approval-level execution state is
  a separate future contract change.
- No merge or push of platform-dev and no push to any product branch from any P22 phase.

## 2. Relationship to Prior Phases (P10 through P21)

P22 introduces **no new auth, RBAC, session, observability, data-source, registry, or
storage concepts**. It is the controlled *execution* layer that P18 through P21
deliberately left open: every prior phase created, approved, and durably stored intent,
and every prior phase explicitly refused to execute it.

| Prior phase | What P22 consumes / extends |
|---|---|
| **P10** identity-only guard, PlatformAuditEvent, source-status vocabulary, redact_metadata allowlist | Every v0 execution runs behind the P10 identity-only super_admin guard. The execution audit events are typed specializations of PlatformAuditEvent. The P10 redact_metadata allowlist is applied to every execution reason, metadata value, and audit field before it is recorded or returned. The source-status rules (unknown is never healthy, null is never zero) gate dry-run and execution. |
| **P11 / P12 / P13 / P14 / P15** Cockpit, Support Console, Observability, Incident Triage | P22-A changes none of these surfaces. A future approved phase may surface execution status badges; P22-A adds no cockpit or console controls and no execute button. |
| **P16** Worktree Execution Harness | Any future real execution must run through the P16 governed harness. P22-A defines the execution contract; it never invokes the harness and unlocks nothing. |
| **P17** Registry and Tenant Lifecycle | A v0 execution targets a P17 platform operational flag (support_mode, incident_active) or a status refresh (provisioning, backup), never a destructive lifecycle transition and never tenant business data. P22-A defines no mutation of the P17 registry in P22-A (contract only). |
| **P18** Controlled Platform Actions | P18 created action *requests* with an `executed == false` flag and `result` enum. P22 is the first phase permitted -- under its own contract and the P16 harness -- to define flipping the P18 `executed` flag to `true` and recording a `completed` / `executed` result, but only for v0 allowlisted actions. P22-A flips nothing. P18 `source_status` remains a hard precondition for dry-run and execution. |
| **P19** Approval Workflow | P19 approved / rejected but every approval resolved to `execution_blocked`. P22 defines the bounded execution that may follow a P19-approved (and P20/P21-durable) approval. Approval alone never executes; P22 execution requires the full precondition set (section 4). |
| **P20** Durable Approval Governance | P20 added maker-checker / quorum and capped approvals at `approved_execution_blocked` (`execution_allowed == false`, `execution_gate == blocked`). P22 execution requires a durable approval at exactly `approved_execution_blocked` with `quorum_met == true`. P22-A does not weaken any P20 safety rule and adds no approval-level execution state. |
| **P21** Durable Approval Store | P21 made approvals restart-safe and auditable. P22 execution references a durable `approval_id` (`durable_approval_id`), re-validates it at dry-run and execution time, and records execution audit events alongside the durable approval audit trail. P22-A reuses P21 digest-only idempotency, redaction, and audit discipline for the execution record. P22-A changes no P21 table, field, enum, or migration. |

In one line, restated for the record: P18 creates requests but does not execute; P19
approves but approval is not execution; P20 adds quorum and caps approval at
`approved_execution_blocked`; P21 makes approvals durable; P22 defines the bounded, dry-run
-first, allowlisted, fully-audited execution contract that may -- under separate approval
-- eventually run the smallest conservative action set, never touching tenant business
data.

## 3. v0 Execution Allowlist

P22 v0 execution is **allowlist only**. The allowlist is closed: an action type not listed
here has no v0 execution path, regardless of how many approvals it carries. The allowlist
is deliberately conservative -- every v0 action is read-only, reversible through a paired
action, or a non-destructive test request, and none mutates tenant business data.

### 3.1 Master allowlist

| action_type | P18 class | v0 executor | reversibility | tenant business mutation |
|---|---|---|---|---|
| `support_mode.on` | write | super_admin (identity-only) | reversible via `support_mode.off` | none (platform operational flag) |
| `support_mode.off` | write | super_admin (identity-only) | reversible via `support_mode.on` | none (platform operational flag) |
| `incident.flag_set` | write | super_admin (identity-only) | reversible via `incident.flag_clear` | none (platform operational flag) |
| `incident.flag_clear` | write | super_admin (identity-only) | reversible via `incident.flag_set` | none (platform operational flag) |
| `provisioning.recheck` | read | super_admin (identity-only) | n/a (no mutation) | none (status refresh) |
| `backup.check` | read | super_admin (identity-only) | n/a (no mutation) | none (status refresh) |
| `backup.restore_test_request` | write-request | super_admin (identity-only) | n/a (isolated test, no real restore) | none (test environment only) |

Notes on the allowlist:

- **Executor is always identity-only super_admin in v0.** Even where P18 / P20 permit a
  support_operator maker for `support_mode` or an engineering_operator maker for the two
  reads, the v0 *executor* is always an identity-only super_admin. support_operator and
  engineering_operator may be makers within their P18 scope; they may never be v0
  executors.
- **Reversibility is structural.** Each write has a paired counter-action
  (`support_mode.on` / `off`, `incident.flag_set` / `clear`). Reads need no reversal. The
  restore *test* request targets an isolated environment and mutates no real data, so no
  reversal of tenant data is required.
- **No destructive lifecycle action is allowlisted.** `tenant.pause`, `tenant.resume`, and
  `lifecycle.transition` are writes that block or move a tenant's lifecycle; they are too
  high-risk for v0 and remain at `approved_execution_blocked` with no execution.

### 3.2 Explicit exclusion list (never executable in v0)

The following are excluded from v0 execution forever in this contract, regardless of
approval state. An approval for any excluded action reaches at most
`approved_execution_blocked` and never executes:

- **`tenant.pause`** -- destructive lifecycle (blocks tenant logins / writes).
- **`tenant.resume`** -- destructive lifecycle (moves tenant out of paused / suspended).
- **`lifecycle.transition`** -- generic destructive lifecycle transition.
- **Real restore** -- restoring real tenant data from a backup (only
  `backup.restore_test_request`, which is test-only, is allowlisted).
- **Schema migration** -- any DDL / alembic / schema change.
- **Data deletion** -- any deletion of tenant or platform records.
- **Payment / billing** -- any payment, billing, invoice, or financial-record action.
- **Tenant business records** -- any read / write of orders, payments, invoices, customers,
  inventory, or ledgers.
- **Arbitrary shell / SQL / script execution** -- no general code-execution surface exists
  or is introduced; v0 actions are bounded, named operations only.

These exclusions are absolute for v0. Lifting any exclusion is a new contract revision
accepted by the CTO and a new phase, not an extension of P22-A.

## 4. Execution Preconditions

Every v0 execution must satisfy all of the following before it may even be dry-run, let
alone executed. A failed precondition produces a blocked dry-run (`executable == false`)
and, if an execution request is attempted anyway, an `execution_denied` audit event. No
precondition may be silently waived.

1. **Identity-only super_admin executor.** The execution requester and the eventual
   executor are the same authenticated identity-only super_admin actor. support_operator,
   engineering_operator, tenant admin, tenant-contextual super_admin, and tenant-scoped
   token are denied on every execution operation.
2. **Matching durable approval id.** The request carries a `durable_approval_id` that
   resolves to a real P21 durable approval record.
3. **Durable approval state is `approved_execution_blocked`.** The approval must be at
   exactly `approved_execution_blocked` (the P20 ceiling). It must not be `pending_review`,
   `rejected`, `expired`, `cancelled`, `superseded`, or `failed_validation`. If a future
   contract explicitly introduces an approval-level `execution_ready` /
   `approved_for_execution` state, that state is an additional valid precondition -- but
   P22-A introduces no such state and anchors v0 on `approved_execution_blocked`.
4. **Quorum met.** `quorum_met == true` on the approval, with the P20/P21 floor satisfied
   (write / write-request: at least two distinct approve checkers, none the maker; read: at
   least one checker distinct from the maker if a durable approval was opened).
5. **Source status valid / available.** The P17 / P18 source for the action's target field
   is `known` / `available` (not `unknown`). For write and write-request actions, an
   unknown source blocks execution. For read actions (`provisioning.recheck`,
   `backup.check`), execution may proceed against a degraded source and return a
  `degraded` result with `degraded_reason`, changing no state -- the only degraded-execution
  allowance in v0, mirroring P18.
6. **action_type in the v0 allowlist.** The approval's `action_type` is one of the seven
   allowlisted types (section 3.1). Any excluded action is blocked.
7. **Idempotency key present.** The execution request carries a client-supplied
   idempotency key. Only its SHA-256 digest is recorded (section 9).
8. **Dry-run succeeded.** The execution request carries a `dry_run_ref` that resolves to a
   prior dry-run with `executable == true` and `verdict == passed`, for the same approval,
   action, target, and executor. No dry-run, or a blocked dry-run, blocks execution.
9. **Execution acknowledgement.** The executor supplies an explicit, typed execution
   acknowledgement token (stronger than the P18 confirmation), recorded with the request.
   Execution without the acknowledgement is denied.
10. **No expired / superseded / cancelled / rejected approval.** Re-validated at dry-run
    and execution time; any terminal or stale approval state blocks execution.
11. **Operator separation holds.** The executor is a distinct identity from the maker and
    from every checker on the approval (section 11).
12. **No same-actor maker / checker / executor violation.** A request whose executor equals
    the maker, or equals any checker, is denied and audited.

## 5. Dry-Run Model

Dry-run is the no-mutation validation gate. It validates the action, target, source
status, approval, idempotency, and actor, and returns an executability verdict plus the
expected audit / event shape. Dry-run changes no platform state and records only a
dry-run audit event. **Dry-run is mandatory before any execution request is accepted.**

### 5.1 Dry-run request (planning shape)

```text
ExecutionDryRunRequest {
  durable_approval_id   : uuid      -- required. Must resolve to a real approval.
  action_type           : enum      -- required. Must match the approval's action_type.
  tenant_id             : uuid      -- nullable. Scoped id only; null for platform-wide.
  requested_state       : enum      -- nullable. Null for reads / no-target actions.
  reason                : string    -- required. REDACTED via P10 allowlist before any
                                     -- record or response.
  idempotency_key       : string    -- required. Hashed to a digest at the boundary; the
                                     -- raw key is never stored, logged, or returned.
  actor_id              : string    -- required. The identity-only super_admin executor.
  actor_role            : enum      -- required. super_admin.
  execution_mode        : enum      -- required. sync | queued.
  correlation_id        : string    -- nullable.
  metadata_redacted     : object    -- nullable. REDACTED via P10 allowlist.
}
```

### 5.2 Dry-run response

```text
ExecutionDryRunResponse {
  dry_run_id            : uuid      -- required. Reference carried by the execution
                                     -- request as dry_run_ref.
  durable_approval_id   : uuid      -- required.
  action_type           : enum      -- required.
  executable            : bool      -- required. true only if every precondition (4) holds.
  verdict               : enum      -- required. passed | blocked.
  block_reasons         : list      -- nullable. Empty when passed; the failed
                                     -- precondition codes when blocked.
  expected_audit_shape  : object    -- required. The event_type(s) that execution would
                                     -- emit, with field names only -- never values, never
                                     -- secrets, never raw payloads.
  execution_mode        : enum      -- required. sync | queued (echoed).
  source_status         : enum      -- required. known | unknown | degraded.
  reversible            : bool      -- required. Whether a paired reversal action exists.
  redaction_applied     : bool      -- required. DEFAULT true.
  created_at            : timestamp -- required. UTC ISO-8601.
}
```

### 5.3 Dry-run rules

- Dry-run returns `executable == false` for every excluded action (section 3.2), regardless
  of approval state.
- Dry-run returns `executable == false` for an approval not at `approved_execution_blocked`
  with `quorum_met == true`.
- Dry-run returns `executable == false` for an unknown source on a write / write-request;
  for a read it may return `executable == true` with `source_status == degraded`.
- Dry-run records exactly one audit event (`execution_dry_run_requested`, plus
  `execution_dry_run_passed` or `execution_dry_run_blocked`) and mutates nothing.
- Dry-run is replayable: the same dry-run inputs return the same verdict within the dry-run
  validity window. A dry-run is single-use as an execution precondition only when bound to
  an execution request by `dry_run_ref`.

## 6. Execution Request Model

An execution request is the recorded intent to execute one v0 action against one durable
approval. It is created only after a passed dry-run. The record is the source of truth for
the execution attempt; it is fully redacted and digest-only for idempotency.

```text
ExecutionRequest {
  execution_request_id  : uuid        -- PK. required. Unique per execution attempt.
  durable_approval_id   : uuid        -- required. FK-like -> P21 durable approval. Must
                                       -- be approved_execution_blocked, quorum_met.
  action_type           : enum        -- required. A v0 allowlisted action_type.
  tenant_id             : uuid        -- nullable. Scoped identifier only. Null for
                                       -- platform-wide actions. Never a business payload
                                       -- and never an FK into a product business table.
  requested_state       : enum        -- nullable. Null for reads / no-target actions.
  reason_redacted       : text        -- required. REDACTED via P10 allowlist before any
                                       -- record or response.
  idempotency_key_digest: char(64)    -- required. SHA-256 of the client key. The RAW key
                                       -- is NEVER stored, logged, returned, or audited.
  payload_digest        : char(64)    -- required. SHA-256 of the canonical execution
                                       -- payload (approval_id, action_type, tenant_id,
                                       -- requested_state, executor). Drives replay dedup.
  actor_id              : varchar     -- required. Identity-only super_admin executor.
  actor_role            : enum        -- required. super_admin.
  identity_context      : enum        -- required. identity_only (the only permitted
                                       -- value for v0 execution).
  execution_mode        : enum        -- required. sync | queued.
  dry_run_ref           : uuid        -- required. The dry_run_id of a passed dry-run for
                                       -- the same approval / action / target / executor.
  execution_ack         : bool        -- required. The typed execution acknowledgement.
                                       -- A request lands only after this is true.
  correlation_id        : varchar     -- nullable.
  metadata_redacted     : object      -- nullable. REDACTED via P10 allowlist.
  redaction_applied     : bool        -- required. DEFAULT true.
  result_state          : enum        -- required. DEFAULT dry_run_passed. The execution-
                                       -- record state (section 7).
  created_at            : timestamptz -- required. UTC ISO-8601.
  updated_at            : timestamptz -- required. UTC ISO-8601.
}
```

Rules:

- The raw idempotency key is hashed at the boundary and discarded; only the digest is
  recorded (section 9).
- `reason_redacted` and `metadata_redacted` pass through the P10 allowlist before any
  record, response, or audit field.
- `tenant_id` is a scoped identifier only and is never joinable to tenant business data.
- The request references the durable approval and the dry-run; it does not store the raw
  approval envelope or the raw P18 request body (only `durable_approval_id` and digests).
- No execution request is created without a passed dry-run and execution acknowledgement.

## 7. Execution Result Model

The execution record carries its own state machine, separate from the durable approval
state machine. **P22-A adds no `executed` / `execution_ready` state to the approval.** The
approval stays at `approved_execution_blocked`; the execution outcome lives on the
execution record and in audit events. v0 may execute synchronously or via a queue, but
must audit both paths identically.

### 7.1 Execution-record states

```text
 dry_run_passed --+--> blocked               (terminal; precondition failed at execution)
                  +--> execution_queued       (queued mode only; awaiting a worker)
                  +--> cancelled              (terminal; maker / super_admin before start)

 execution_queued --+--> executing
                    +--> cancelled

 executing --+--> executed                    (terminal; action landed, audited)
             +--> execution_failed            (terminal; errored, no state landed)

 executed --+--> compensation_required        (a reversal / compensation must run)
 execution_failed --+--> compensation_required

 compensation_required --+--> compensation_completed  (terminal; reversal recorded)
```

State semantics:

| state | Meaning |
|---|---|
| `dry_run_passed` | A passed dry-run is bound and an execution request recorded; execution has not started. Initial state. |
| `blocked` | A precondition failed at execution time (source, approval, separation, allowlist). Terminal. |
| `execution_queued` | Queued mode: the request is accepted and awaiting a worker. Not an execution yet. |
| `executing` | The action is running (behind the P16 governed harness, in a future approved phase). |
| `executed` | The action landed successfully and is audited. Terminal. |
| `execution_failed` | The action errored; no state landed. Terminal unless compensation is required. |
| `compensation_required` | A reversal / compensation action must run (for a reversible write that landed partially or wrongly). |
| `compensation_completed` | The paired reversal action landed and is audited. Terminal. |
| `cancelled` | The maker / super_admin cancelled before execution started. Terminal. |

### 7.2 Sync vs queued

- **Synchronous** (`execution_mode == sync`): dry_run_passed -> executing -> executed |
  execution_failed in one request lifecycle. The whole transition is audited.
- **Queued** (`execution_mode == queued`): dry_run_passed -> execution_queued -> executing
  -> executed | execution_failed. The queued state is audited; a future worker (separately
  approved) drains it through the P16 harness.
- **Both paths audit identically**: `execution_requested`, `execution_started`,
  `execution_succeeded` / `execution_failed`, plus `execution_compensation_recorded` if
  compensation runs. P22-A implements neither path; it defines both.

### 7.3 Compensation / reversal

- For reversible writes (`support_mode.*`, `incident.flag_*`), a compensation action is the
  paired counter-action. `compensation_required` triggers the paired action as its own
  audited, dry-run-first execution; it never mutates tenant business data.
- For reads, no compensation is possible or required (no mutation).
- For `backup.restore_test_request`, compensation is test-environment cleanup only; no real
  tenant data is touched.

## 8. Audit Contract

Every dry-run, execution request, state transition, denial, and compensation emits exactly
one execution audit event. The execution audit log is append-only; no UPDATE path; no
single-row DELETE; only whole-record retention purge (P21 discipline), itself audited.
Denied, blocked, duplicate, and failed attempts are audited with the same shape as
successes.

### 8.1 Execution audit event (planning shape)

```text
ExecutionAuditEvent {
  event_id              : uuid        -- PK. required. Unique.
  execution_request_id  : uuid        -- nullable. Null before the request is created.
  durable_approval_id   : uuid        -- required. The approval the execution targets.
  action_id             : uuid        -- nullable. The P18 action_id, where applicable.
  actor_id              : varchar     -- required. Identity-only super_admin; SYSTEM for
                                       -- automated compensation / sweep.
  actor_role            : enum        -- required. super_admin | system.
  identity_context      : enum        -- required. identity_only | system.
  event_type            : enum        -- required. Closed set (8.2).
  action_type           : enum        -- required. The v0 allowlisted action_type.
  tenant_id             : uuid        -- nullable. Scoped identifier only.
  result_state          : enum        -- nullable. Execution-record state after this event.
  previous_state        : enum        -- nullable. Execution-record state before this event.
  reason_redacted       : text        -- required. REDACTED via P10 allowlist. Never a raw
                                       -- request / response body.
  payload_digest        : char(64)    -- nullable. SHA-256 of the canonical payload.
  idempotency_key_digest: char(64)    -- nullable. SHA-256 of the client key. RAW key never
                                       -- stored.
  source_status         : enum        -- nullable. known | unknown | degraded.
  dry_run_ref           : uuid        -- nullable. The bound dry-run id.
  redaction_applied     : bool        -- required. DEFAULT true.
  correlation_id        : varchar     -- nullable.
  sequence_no           : bigint      -- required. Monotonic per-execution-request sequence.
  created_at            : timestamptz -- required. UTC ISO-8601.
}
```

### 8.2 Closed event_type set

| event_type | When it fires |
|---|---|
| `execution_dry_run_requested` | An identity-only super_admin requests a dry-run. |
| `execution_dry_run_passed` | The dry-run verdict is `passed` (`executable == true`). |
| `execution_dry_run_blocked` | The dry-run verdict is `blocked` (`executable == false`), with `block_reasons`. |
| `execution_requested` | An execution request is recorded after a passed dry-run and acknowledgement. |
| `execution_started` | The action begins executing (sync or queued worker). |
| `execution_succeeded` | The action landed; result_state -> executed. |
| `execution_failed` | The action errored; no state landed; result_state -> execution_failed. |
| `execution_compensation_recorded` | A reversal / compensation action landed; result_state -> compensation_completed. |
| `execution_denied` | Any execution operation is denied: permission, identity, expired / rejected / superseded / cancelled approval, allowlist violation, source unknown for a write, self-execution, maker / checker / executor collision, missing dry-run, missing acknowledgement, or idempotency conflict. |

### 8.3 The never-logged list

The following must NEVER appear in any execution audit field, response, queue item,
backup, or export:

- raw secret, DSN, connection string, hostname, port, host:port pair;
- token, password, API key, cookie, auth header (for example `X-Platform-Operator`,
  `Authorization`, `Cookie`, `Set-Cookie`);
- raw idempotency key (digest only);
- stack trace, raw exception, raw log line;
- raw request body or raw response body of the underlying P18 action or the execution
  payload (only digests and redacted reason);
- tenant business payload: orders, payments, invoices, customers, inventory, ledgers;
- any shell command, SQL statement, or script body (v0 executes no such thing, and none is
  ever recorded).

## 9. Idempotency

Execution idempotency is digest-only and reuses the P21 discipline.

- **Digest-only.** The client `idempotency_key` is hashed to a SHA-256 digest at the
  boundary; the raw key is never stored, logged, returned, or audited. Only
  `idempotency_key_digest` and a `payload_digest` are recorded.
- **Replay returns the original result.** A repeat execution request with the same
  `(durable_approval_id, idempotency_key_digest)` and a matching `payload_digest` returns
  the original execution result and writes no new state and no new success audit event. It
  is an idempotent replay, not a second execution.
- **Same key, different payload conflicts.** A repeat with the same
  `idempotency_key_digest` but a different `payload_digest` is a conflict: it is rejected
  and audited as `execution_denied`. It never applies a second state change.
- **Failed execution retry.** An execution that reached `execution_failed` or
  `compensation_required` may be retried only with a **new** idempotency key and a fresh
  passed dry-run. The prior failed record is terminal for that key; it is not re-opened.
  `executed` records are never retried (a replay returns the original success).
- **No duplicate audit success.** An idempotent replay of an `executed` request emits no
  second `execution_succeeded` event; the original event stands. Denied / blocked replays
  are audited as `execution_denied` (a denial is always auditable), but never as a second
  success.
- **Idempotency window.** The dedup window is bounded by the durable approval's
  `durable_retain_until` and the execution request retention. After expiry, the record is
  eligible for retention purge (P21 discipline, SYSTEM actor only).

## 10. Safety Rules

Every v0 execution, in every phase that implements this contract, must satisfy all of the
following. A violation rejects the execution and records an `execution_denied` audit event.

1. **Allowlist only.** Only the seven v0 actions (section 3.1) may execute. Every excluded
   action (section 3.2) is blocked.
2. **Dry-run first.** No execution without a passed dry-run bound by `dry_run_ref`.
3. **Fail closed.** Any failed precondition, unknown source (for a write / write-request),
   unknown approval state, or validation error blocks execution. Unknown is never healthy;
   the system never fabricates a passing state.
4. **No silent fallback.** If execution cannot proceed safely, it is denied and audited.
   There is no read-only fallback that silently mutates, and no degraded write path.
5. **No arbitrary tool / shell / SQL / script execution.** v0 actions are bounded, named
   operations only. No general code-execution surface exists or is introduced.
6. **No tenant business mutation.** A v0 execution changes platform operational flags or
   refreshes status only. It must never read, write, create, update, or delete tenant
   business records (orders, payments, invoices, customers, inventory, ledgers).
7. **No product code path.** Execution never invokes product business code, never touches
   product-dev-recovered, and never enters a product payment / billing flow.
8. **No payment / billing.** No v0 action touches any payment, billing, invoice, or
   financial record.
9. **No raw secrets.** No credential, DSN, host, port, connection string, token, password,
   cookie, auth header, stack trace, raw exception, raw idempotency key, or raw request /
   response body appears in any execution field, response, queue item, or audit event.
10. **Unknown is not healthy.** A source status of `unknown` blocks write / write-request
    execution; a `degraded` read returns a `degraded` result and changes no state.
11. **Approval is not execution.** A durable, quorum-met approval at
    `approved_execution_blocked` is a precondition, not an execution. Approval alone never
    runs anything.
12. **Durability is not execution.** A restart-safe, retained approval does not execute by
    surviving; it still requires the full precondition set and a passed dry-run.
13. **Every execution is audited.** Every dry-run, request, transition, denial, failure,
    and compensation emits exactly one execution audit event. There is no unaudited
    execution and no unaudited denial.
14. **Operator separation holds.** The executor is distinct from the maker and every
    checker (section 11).
15. **Reversible where possible.** Each v0 write has a paired reversal action;
    compensation is itself an audited, dry-run-first execution.

Derived hard rules (consequences of the above):

- No v0 execution may run outside the audit boundary or the dry-run gate.
- No v0 execution may run for an excluded action, even with full approval and quorum.
- No v0 execution may proceed when its source is unknown (for a write / write-request) or
  its approval is not at `approved_execution_blocked` with quorum met.

## 11. Operator Separation Policy

P22 v0 fixes a strong maker / checker / executor separation policy. It is not deferred.

- **Maker** opens the underlying P18 request and (with checkers) the durable approval. The
  maker is an identity-only super_admin for write / write-request approvals, or a
  support_operator / engineering_operator within their P18 scope for the delegated actions
  (P18 / P20). The maker is never a checker and never a v0 executor.
- **Checker** approves / rejects the durable approval. Checkers are identity-only
  super_admin identities, distinct from the maker and from each other (P20 / P21). A
  checker is never a v0 executor for the approval it checked.
- **Executor** runs the v0 action. The executor is always an identity-only super_admin,
  distinct from the maker and from every checker on the approval.

Hard rules:

1. **No self-execution.** An execution whose `actor_id == maker` is denied and audited as
   `execution_denied`. The maker can never execute its own request.
2. **No checker-execution.** An execution whose `actor_id` equals any checker on the
   approval is denied and audited. A checker can never execute what it approved.
3. **Executor is identity-only super_admin.** support_operator, engineering_operator,
   tenant admin, tenant-contextual super_admin, and tenant-scoped token are denied as
   executors on every v0 action and audited.
4. **Three-distinct for write / write-request.** For `support_mode.*`,
   `incident.flag_*`, and `backup.restore_test_request`, maker, every checker, and executor
   are three-or-more distinct identities.
5. **Read floor.** For `provisioning.recheck` and `backup.check`, the read quorum floor is
   one checker distinct from the maker; the executor is still distinct from the maker.
6. **Enforcement point.** Separation is re-validated at dry-run and at execution-request
   creation, against the durable approval's persisted maker / checkers. The precise storage
   of the executor identity is a P22-B implementation concern; the separation rule itself
   is fixed in P22-A and may not be weakened without a new contract revision.

## 12. API Shape Proposal (planning only)

P22-A proposes -- does not implement -- the following read / dry-run / request surface.
Every endpoint is behind the P10 identity-only super_admin guard; none executes in P22-A.

- **GET /platform/p22/execution/catalog** -- return the v0 allowlist (action_type, class,
  executor, reversibility) and the exclusion list. Read-only; audited as a read.
- **POST /platform/p22/execution/dry-run** -- validate an execution against the
  preconditions and return `executable`, `verdict`, `block_reasons`, and
  `expected_audit_shape`. Mutates nothing; records dry-run audit events.
- **POST /platform/p22/execution/requests** -- record an execution request after a passed
  dry-run and execution acknowledgement. Does not execute; records `execution_requested`.
- **GET /platform/p22/execution/requests** -- list execution requests with the same
  filters / pagination discipline as the P20 / P21 queue. Read-only; audited as a read.
- **GET /platform/p22/execution/requests/{id}** -- read one execution request's redacted
  record and state. Read-only; audited as a read.

Compatibility notes:

- No response field carries a secret, raw key, raw body, shell / SQL, or tenant payload.
- No endpoint returns an executing / executed state without a matching audit trail.
- A future durable backend preserves these shapes unless a new versioned contract is
  approved. The P20-C / P21 frontend needs no semantic change for P22-A (no frontend ships).

## 13. Test Plan (future phases)

P22-A defines the expected tests; it writes none. The plan totals at least 60 tests across
the categories below.

**T1 contract / types (6)**
- T1.1 the execution-request record has exactly its declared fields, types, nullability,
  and `extra = forbid` discipline; no undeclared field.
- T1.2 the execution-record state enum is exactly the nine defined states; no
  `ready_to_execute` / `executing` approval state is introduced.
- T1.3 the event_type enum is exactly the nine defined execution events.
- T1.4 the action_type allowlist enum is exactly the seven v0 actions.
- T1.5 the identity_context for v0 execution is `identity_only` only; `system` only for
  automated compensation / sweep.
- T1.6 the execution state machine has exactly the allowed transitions and forbids the
  forbidden ones.

**T2 dry-run (8)**
- T2.1 a dry-run against a valid approval returns `executable == true`, `verdict == passed`.
- T2.2 a dry-run against an excluded action returns `executable == false`, `blocked`.
- T2.3 a dry-run against an approval not at `approved_execution_blocked` returns blocked.
- T2.4 a dry-run against an approval without quorum returns blocked.
- T2.5 a dry-run for a write with unknown source returns blocked.
- T2.6 a dry-run for a read with degraded source returns `executable == true`, `degraded`.
- T2.7 a dry-run returns the expected audit shape with field names only, no values.
- T2.8 a dry-run mutates no platform state and records only dry-run audit events.

**T3 preconditions (8)**
- T3.1 a non-super_admin executor is denied at dry-run and execution.
- T3.2 an execution without a matching durable approval id is denied.
- T3.3 an execution without a passed dry-run (`dry_run_ref`) is denied.
- T3.4 an execution without the execution acknowledgement is denied.
- T3.5 an execution for an expired approval is denied.
- T3.6 an execution for a superseded approval is denied.
- T3.7 an execution for a cancelled approval is denied.
- T3.8 an execution for a rejected approval is denied.

**T4 allowlist / exclusions (8)**
- T4.1 `support_mode.on` is executable in v0; `tenant.pause` is not.
- T4.2 `support_mode.off` is executable; `tenant.resume` is not.
- T4.3 `incident.flag_set` / `incident.flag_clear` are executable; `lifecycle.transition`
  is not.
- T4.4 `provisioning.recheck` / `backup.check` are executable (read).
- T4.5 `backup.restore_test_request` is executable (test-only); real restore is not an
  action and is excluded.
- T4.6 schema migration is not an executable v0 action.
- T4.7 data deletion is not an executable v0 action.
- T4.8 arbitrary shell / SQL / script execution has no v0 surface and is rejected.

**T5 idempotency (7)**
- T5.1 the raw idempotency key is never stored; only the digest is present.
- T5.2 a replay with matching `payload_digest` returns the original result and no new
  success event.
- T5.3 a replay with a different `payload_digest` is rejected as a conflict and audited.
- T5.4 an `executed` record is never re-executed; replay returns the original success.
- T5.5 a failed execution is retried only with a new key and a fresh dry-run.
- T5.6 a `compensation_required` record is retried only with a new key.
- T5.7 no duplicate `execution_succeeded` event is emitted on replay.

**T6 audit (8)**
- T6.1 every dry-run emits `execution_dry_run_requested` plus passed / blocked.
- T6.2 every execution request emits `execution_requested`.
- T6.3 every start emits `execution_started`; every success `execution_succeeded`.
- T6.4 every failure emits `execution_failed`; every compensation
  `execution_compensation_recorded`.
- T6.5 every denial emits `execution_denied` with a reason code.
- T6.6 the audit log is append-only; no UPDATE; no single-row DELETE.
- T6.7 `sequence_no` is monotonic per execution request.
- T6.8 no audit field contains a never-logged value (content scan against the P10
  allowlist and the never-logged list).

**T7 no-execution for blocked paths (6)**
- T7.1 an excluded action with full approval and quorum still does not execute.
- T7.2 a write with unknown source does not execute.
- T7.3 an approval at `pending_review` does not execute.
- T7.4 an approval without quorum does not execute.
- T7.5 a dry-run-skipped request does not execute.
- T7.6 a same-actor (maker / checker) executor does not execute.

**T8 no tenant business mutation (5)**
- T8.1 no v0 action reads or writes an order, payment, invoice, customer, inventory, or
  ledger record.
- T8.2 `tenant_id` is a scoped id and is not joinable to business tables.
- T8.3 `backup.restore_test_request` targets an isolated test environment and mutates no
  real tenant data.
- T8.4 support_mode / incident flags change platform operational state, not tenant business
  data.
- T8.5 no execution references a product business table.

**T9 no raw leak (5)**
- T9.1 no raw idempotency key in any field, response, queue item, or audit event.
- T9.2 no raw secret / DSN / host / port / token / password / cookie / auth header.
- T9.3 no raw request / response body; only digests and redacted reason.
- T9.4 no shell command, SQL statement, or script body is recorded.
- T9.5 `redaction_applied == true` on every record and event.

**T10 source unavailable (5)**
- T10.1 a write against an unknown source is blocked at dry-run and execution.
- T10.2 a read against a degraded source returns `degraded` and changes no state.
- T10.3 a read against an unknown source does not fabricate a healthy status.
- T10.4 `backup.restore_test_request` against an unavailable backup source is blocked.
- T10.5 source status is re-validated at execution time, not just at approval time.

**T11 approval expired / rejected (5)**
- T11.1 an approval that expires between dry-run and execution is denied.
- T11.2 an approval that is superseded between dry-run and execution is denied.
- T11.3 a rejected approval never executes.
- T11.4 a cancelled approval never executes.
- T11.5 a `failed_validation` approval never executes.

**T12 duplicate / retry (5)**
- T12.1 a duplicate execution request with the same key and payload is an idempotent
  replay.
- T12.2 a duplicate with the same key and a different payload is a conflict.
- T12.3 a retry after `execution_failed` requires a new key and fresh dry-run.
- T12.4 a retry after `executed` is rejected (replay only).
- T12.5 a compensation retry requires a new key.

**Total: 76 planned tests (>= 60 required).** A future implementation must include all of
them; P22-A writes none.

## 14. Acceptance Criteria

A future phase that implements this contract is accepted only when all of the following
hold:

1. **P22-A is docs and ledger only.** No runtime code, backend, frontend, migration,
   alembic change, table, test code, or dependency change ships in P22-A.
2. **The v0 allowlist is exactly the seven actions;** every excluded action has no
   execution path.
3. **Approval is not execution.** A durable, quorum-met approval at
   `approved_execution_blocked` is a precondition; it never executes by itself.
4. **Durability is not execution.** A restart-safe approval still requires the full
   precondition set and a passed dry-run to execute.
5. **Dry-run is mandatory and first.** No execution request is accepted without a passed
   dry-run bound by `dry_run_ref`.
6. **Every precondition is enforced;** a failed precondition blocks dry-run and denies
   execution, with no silent waiver.
7. **The executor is always identity-only super_admin;** support_operator,
   engineering_operator, tenant admin, tenant-contextual super_admin, and tenant-scoped
   token are denied as executors and every denial is audited.
8. **Operator separation holds;** the executor is distinct from the maker and every
   checker; self-execution and checker-execution are denied and audited.
9. **No tenant business mutation;** no v0 action reads or writes orders, payments,
   invoices, customers, inventory, or ledgers; `tenant_id` is a scoped id only.
10. **No destructive lifecycle execution;** `tenant.pause`, `tenant.resume`, and
    `lifecycle.transition` never execute in v0.
11. **No real restore;** `backup.restore_test_request` is test-only and targets an isolated
    environment.
12. **No arbitrary shell / SQL / script;** no general code-execution surface exists.
13. **Fail closed;** unknown source (for a write / write-request), unknown approval state,
    or validation error blocks execution; unknown is never healthy.
14. **The idempotency key is digest-only;** an audit / content scan finds no raw
    idempotency key in any field, response, queue item, or audit event; replay returns the
    original result; same-key-different-payload is a conflict.
15. **Redaction is total;** every reason / metadata / audit field scans clean against the
    P10 allowlist; `redaction_applied == true` everywhere.
16. **No raw secrets / DSNs / hosts / ports / tokens / passwords / cookies / auth headers,
    raw bodies, shell / SQL, or tenant payload** appear in any field, response, or audit
    event.
17. **Every execution is audited;** every dry-run, request, transition, denial, failure,
    and compensation emits exactly one execution audit event; the log is append-only.
18. **No new approval state and no migration in P22-A;** the execution lifecycle lives on
    the execution record; the approval stays at `approved_execution_blocked`; no table,
    migration, or alembic change ships in P22-A.
19. **No AI agent execution;** P22-A names a future AI Operator Copilot boundary only and
    grants no AI execution power.
20. **The API shape is planning only;** no endpoint ships in P22-A; a future backend
    preserves the proposed shapes unless a new versioned contract is approved.

## 15. Counterexamples (must fail or be rejected)

1. **C1 -- an approved approval directly executes.** A quorum-met approval at
   `approved_execution_blocked` that runs the action without a dry-run, request,
   acknowledgement, and executor -- rejected; approval is not execution.
2. **C2 -- `tenant.pause` executes in v0.** A `tenant.pause` approval that executes --
   rejected; destructive lifecycle is excluded from v0.
3. **C3 -- `tenant.resume` or `lifecycle.transition` executes in v0.** Either executing --
   rejected; excluded from v0.
4. **C4 -- real restore executes.** A real restore of tenant data (not a test request) that
   runs -- rejected; only `backup.restore_test_request` (test-only) is allowlisted.
5. **C5 -- an unknown source executes a write.** A `support_mode.on` or
   `incident.flag_set` execution while the operational-flags source is `unknown` --
   rejected; unknown is not healthy.
6. **C6 -- the raw idempotency key is stored.** A field, response, queue item, or audit
   event holding the plaintext key instead of its digest -- rejected (contract violation).
7. **C7 -- a support operator executes a write action.** A support_operator running
   `support_mode.on` as executor -- rejected; the v0 executor is identity-only super_admin.
8. **C8 -- dry-run skipped.** An execution request accepted without a passed dry-run bound
   by `dry_run_ref` -- rejected.
9. **C9 -- same idempotency key, different payload accepted.** A second request reusing a
   key with a different payload that applies a second state change -- rejected as a
   conflict and audited.
10. **C10 -- a shell command allowed.** An execution that runs an arbitrary shell command
    -- rejected; no general code-execution surface exists.
11. **C11 -- a SQL mutation allowed.** An execution that runs an arbitrary SQL mutation --
    rejected.
12. **C12 -- product payment touched.** An execution that reads or writes a payment /
    billing / invoice / financial record -- rejected (boundary violation).
13. **C13 -- tenant business data mutated.** An execution that reads or writes an order,
    customer, inventory, or ledger record -- rejected (boundary violation).
14. **C14 -- self-execution.** An execution whose executor is the maker -- rejected and
    audited.
15. **C15 -- checker-execution.** An execution whose executor is a checker on the approval
    -- rejected and audited.
16. **C16 -- an expired approval executes.** An execution against an approval that expired
    between dry-run and execution -- rejected.
17. **C17 -- a superseded / cancelled / rejected approval executes.** Any of these
    executing -- rejected.
18. **C18 -- a raw secret in an execution field.** A reason / metadata / audit field
    containing a credential, DSN, host, port, connection string, token, password, cookie,
    auth header, stack trace, or raw body -- rejected (redaction violation).
19. **C19 -- an unaudited execution.** A state change that lands without exactly one
    execution audit event -- rejected (contract violation).
20. **C20 -- a duplicate success audited.** An idempotent replay that emits a second
    `execution_succeeded` event -- rejected; replay returns the original result.
21. **C21 -- a migration or table added in P22-A.** Any backend, frontend, migration,
    alembic change, table, test, or dependency change added in P22-A -- rejected; P22-A is
    docs / ledger only.
22. **C22 -- an AI agent executing directly.** Any AI copilot path that executes a v0
    action, sets an executing state, or executes without an identity-only super_admin
    executor -- rejected (section 17).
23. **C23 -- a new approval-level execution state added in P22-A.** Any addition of an
    `executed` / `ready_to_execute` / `execution_ready` state to the durable approval state
    machine in P22-A -- rejected; the execution lifecycle lives on the execution record
    only.
24. **C24 -- a silent-fallback write.** A write that takes a degraded / read-only fallback
    path and silently mutates, or that fabricates a passing state when the source is down
    -- rejected.

## 16. P22-B Entry Gate (future)

A future P22-B is permitted to implement **only a non-executing execution skeleton**: the
catalog read, the dry-run validator (no mutation), execution-request recording (no
execution), and execution-result read -- wired to the P21 durable approval store, the P18
request layer, and the P10 identity-only guard, able to receive, dry-run, validate, deny,
deduplicate, and audit an execution request, but **not to execute any action**.

This gate is the counterpart to the P22-A-only non-goals (1.3.1): the runtime code,
backend handlers, dry-run validator, execution-request recording, and result read that are
forbidden in P22-A are exactly the non-executing skeleton P22-B may begin to implement.
The all-P22 non-goals (1.3.2) bind P22-B equally; nothing in this section relaxes them, and
any P22-B migration requires separate explicit approval in the P22-B contract review.

P22-B (and all of P22 before a separately approved execution phase) **must not**:

- execute any v0 action, dispatch any worker, drain any queue, or invoke the P16 governed
  harness, unless separately and explicitly approved outside this contract;
- add any migration, alembic change, table, or column unless explicitly approved in the
  P22-B contract review;
- implement any frontend execution control or write endpoint beyond the dry-run / request
  skeleton;
- execute any excluded action (section 3.2) under any circumstance;
- mutate tenant business data, run arbitrary shell / SQL / script, or touch payment /
  billing or product code;
- rewrite auth / RBAC / session / tenancy;
- implement notification / escalation, real restore, or an AI execution path;
- add a new approval-level execution state;
- touch product-dev-recovered or any product business path.

**Real execution of any v0 action is reserved for a separately approved phase** and must
run through the P16 governed harness, behind the full precondition set, a passed dry-run,
operator separation, and total audit. P22-B must begin from this contract and may not
change the allowlist, the exclusion list, the preconditions, the dry-run model, the request
/ result models, the audit fields, the idempotency rules, the safety rules, the separation
policy, or the API shapes without a new contract revision accepted by the CTO.

## 17. Future AI Operator Copilot Note

Any future AI Operator Copilot must operate **through** this execution substrate, never
around it. The boundary:

- The AI may **read** the v0 catalog and execution request state via approved, read-only
  tools.
- The AI may **propose** a dry-run or an execution request, but only as a proposal.
- The AI may **create a draft execution request only after explicit operator
  confirmation** -- a human identity-only super_admin must be the executor. The AI is never
  the maker, never the checker, and never the executor.
- The AI **cannot execute actions directly.** There is no AI path to an executing state, no
  AI self-approval, no AI self-execution, and no AI break-glass.
- **Every AI action must be audited** as an execution audit event (for example
  `execution_dry_run_requested` / `execution_denied`, with the AI proposal recorded as
  redacted metadata and actor_role set to the confirming operator's role or `system`).
- **AI tool calls must be linked** to the durable approval and execution request via
  `correlation_id` / `action_id` / `approval_id` / `execution_request_id`, so every AI
  proposal is traceable to a human-gated approval and a human executor.
- **Real execution remains separately gated** behind a future execution phase that must run
  through the P16 governed harness. The execution substrate records AI-assisted proposals;
  it does not run them.

This section names a future boundary only. P22-A implements no AI copilot, grants no AI
execution power, and adds no AI-specific runtime code.

## 18. Docs-Only and Contract-Only Statement

P22-A is **docs-only and contract-only**. It ships:

- `docs/ai/PLATFORM_PRODUCT_P22_CONTROLLED_EXECUTION_V0_CONTRACT.md` -- this contract.
- `docs/ai/README.md` -- the P22 entry in the Platform Product Track read order.
- `ai-ledger/platform/2026-07-01_p22a_controlled_execution_v0_contract.md` -- the ledger.

There is **no runtime code, no backend, no frontend, no migration, no alembic change, no
table, no test code, and no dependency change** in P22-A. P22-A defines the controlled
execution v0 contract only; it does not execute, dispatch, queue, schedule, migrate, or
implement any execution, approval, action, or storage path. **Approval is not execution,
and durability is not execution.** Real execution of any v0 action is reserved for a
separately approved future phase and must run through the P16 governed harness. **P22-B is
not started.**
