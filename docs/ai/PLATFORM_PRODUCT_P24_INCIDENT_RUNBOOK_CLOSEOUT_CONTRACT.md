# Platform Product P24 -- Incident + Runbook Closeout Contract

**Status:** Contract only (P24-A). No runtime code, no backend handlers, no frontend
UI, no migrations, no alembic changes, no tests, and no dependency changes. Accepted by
the CTO before any P24-B backend skeleton may begin.
**Phase:** P24-A Incident + Runbook Closeout Contract
**Date:** 2026-07-05
**Base:** `cf3464db` (origin/platform-dev -- P23 operator task / notification queue: P23-A
contract, P23-B non-executing / non-sending backend skeleton, P23-C read-only source
materialization bridge, P23-D frontend console, and P23-E closeout all merged;
P23_OPERATOR_TASK_QUEUE_READY)
**Depends on:** P10 (identity-only super_admin guard, PlatformAuditEvent, source-status
vocabulary, redact_metadata allowlist), P11 (Platform Admin Cockpit boundary), P12
(Support Console support-safe subset, support package / diagnostics bundle), P13 / P14
(Operations Observability plus unavailable_reason / degraded_reason), P15 (Incident
Triage read-only contract: IncidentSignal, IncidentClassification, IncidentRunbookHint,
IncidentTriageSnapshot, IncidentHandoffSummary, detect / classify / inspect / explain /
handoff / close), P16 (Worktree Execution Harness), P17 (Platform Registry, Tenant
Lifecycle, TenantOperationalFlags.incident_active, backup / status source contract +
schema plan + read wiring), P18 (Controlled Platform Actions Contract: action catalog
including incident.flag_set and incident.flag_clear, classification, permission matrix,
action request layer, the `executed` flag, ControlledActionAuditEvent), P19 (Approval
Workflow Contract: approve resolves to execution_blocked), P20 (Durable Approval
Governance Contract: persistent record shape, dual-control policy, execution readiness
gate, durable audit, state machine, approved_execution_blocked ceiling), P21 (Durable
Approval Store Contract + schema plan + public durable tables + runtime adapter +
closeout: durable storage records, restart-safe consistency, digest-only idempotency,
redaction-before-persistence, durable append-only audit, retention / purge / export, API
compatibility), P22 (Controlled Execution v0 Contract + non-executing skeleton + console
+ readiness lock + runtime governed adapter contract + seam skeleton + backup status
source discovery + read-only backup.check binding + backup.check console + closeout +
first safe governed backup.check action: v0 allowlist, dry-run model, execution request
/ result lifecycle, execution audit, idempotency, safety rules, operator separation,
runtime governed action adapter seam, recorded-request-bound read-only completion),
P23 (Operator Task / Notification Queue Contract + non-executing backend skeleton +
read-only source materialization bridge + frontend console + closeout: the closed
ten-type task catalog, the nine-state triage machine, the notification EVENT boundary,
dedup / severity / correlation, the never-leaked list, and the rule that a task is a
view, not an executor).
**Author:** Codex (Claude worker)

---

## 1. Goal and Non-Goals

### 1.1 Goal

P15 gave platform operators a **read-only incident triage** surface: detect a signal,
classify it, inspect a snapshot, explain missing fields, hand off a redacted summary,
and record a *labeled observation* as a conclusion. P18 then created the controlled
action requests that are the write complement to that read surface -- among them
`incident.flag_set` and `incident.flag_clear`, which set and clear the P17
`TenantOperationalFlags.incident_active` flag. P22 defined the governed execution layer
and, in P22-G, landed the first safe governed action (`backup.check`); a future governed
slice may execute `incident.flag_set` / `incident.flag_clear` the same way. P23
aggregated the events P17 through P22 produce into a single operator task / notification
queue with a closed catalog of ten task types.

Two of those ten task types -- `incident_followup_required` and `runbook_step_required`
-- were deliberately left as **PUSH intake** in P23-C. P23-C is a read-only PULL bridge
that materializes four task types (`approval_pending`, `approval_decision_required`,
`source_unknown`, `backup_check_warning`) from the P19 / P22 read paths; the merged
P23-B AST guard forbids the P23 source from importing execution / approval product
modules, so the remaining types -- the ones tied to an *owed follow-up on an active
incident* and an *owed runbook step* -- arrive via intake PUSH, not via P23-C's pull.
P23-A named those two types and their follow-ups, and P23 left their materialization
contract open. **P24 is that contract.**

P24 is the **incident + runbook closeout** layer. It is the *lifecycle and
materialization* contract for the two P23 task types P23-C did not pull. It defines:

1. The **incident closeout lifecycle** -- a non-executing presentation state machine
   (`detected`, `triaged`, `flagged_active`, `in_remediation`, `awaiting_closeout`,
   `closed`, `withdrawn`, `expired`) that threads P15 detection / classification, the
   P17 `incident_active` flag (mirrored, never owned), the P23 follow-up / runbook-step
   tasks, and the P18 / P19 / P20 / P21 / P22 action / approval / execution outcomes
   into one closeout narrative. It is entirely separate from the P15 triage workflow,
   the P22 execution-record machine, and the P23 task triage machine.
2. The **runbook step model** -- an ordered, typed checklist attached to an incident
   closeout. Each step is one of three kinds: `observation` (a read-only P15
   runbook-hint-style step), `action_pointer` (a pointer to a P18 controlled action
   request that resolves through P22 governed execution), or `approval_pointer` (a
   pointer to a P19 / P20 / P21 durable approval the step is waiting on). A step is a
   pointer and a record, never an execution.
3. The **source boundaries and materialization rules** that turn an active incident +
   owed follow-up + owed runbook steps into `incident_followup_required` and
   `runbook_step_required` tasks (PUSH intake only), and the explicit list of what does
   NOT materialize a task.
4. The **audit / event model** for closeout transitions and runbook step changes.
5. The **acceptance criteria, counterexamples, and the P24-B entry gate**.

P24 is deliberately the *least* powerful closeout layer in the platform. It adds **no
new execution capability, no new approval capability, no new mutation capability, no new
notification delivery capability, and no new auth capability**. Its only power is to
close out -- to record operator judgment that an incident's owed follow-up and runbook
steps are complete and that the flag (if it was set) has since cleared through P22. The
single most important invariant of P24, repeated throughout this document:

> **An incident closeout is a view, not an executor. A runbook step is a pointer, not an
> execution. A follow-up task is a record, not a repair.** No incident closeout state
> transition, no runbook step state change, and no task materialization executes a P22
> action, approves a P19 / P20 / P21 approval, sets or clears the P17 `incident_active`
> flag, bypasses a checker, mutates a registry field, or sends any external message.
> P24 mirrors the flag, the tasks, and the execution outcomes; it never changes them.
> Closing an incident in the P24 view records operator judgment; it does **not** clear
> the flag -- the flag clears only through P22 `incident.flag_clear` under its own
> governed execution envelope. A `withdrawn` or `expired` closeout removes the incident
> from the active closeout view; it never deletes the P15 / P17 / P18 / P19 / P20 / P21
> / P22 / P23 audit history behind it.

P24-A fixes the boundary before any closeout code is written:

1. The **incident closeout lifecycle**: the closed set of states, the allowed and
   forbidden transitions, the rule that no transition sets or clears the flag, and the
   rule that `closed` requires both owed-task completion and (if the flag was set) an
   observed flag clear through P22.
2. The **runbook step model**: the three step kinds, the per-step state, the runbook
   composition rule, the ordering / evidence rules, and the rule that a step is a
   pointer, not an execution.
3. The **source boundaries**: PUSH intake only (not PULL); the closed set of recorded
   events that may advance a closeout; the explicit exclusion list.
4. The **materialization rules** for `incident_followup_required` and
   `runbook_step_required`: when each task type is owed, what dedup key it carries, and
   what does NOT materialize a task.
5. The **data model plan** (planning only): the logical `platform_incident_closeout`,
   `platform_runbook`, and `platform_runbook_step` records -- fields, indexes,
   uniqueness, tenant / actor scope, `correlation_id`, source links to P15 / P17 / P18
   / P19 / P20 / P21 / P22 / P23 ids, and idempotency / dedup rules. P24-A creates no
   table, no migration, no ORM model.
6. The **audit / event model** (planning only): the closeout and runbook-step audit
   shapes; every transition and step change is auditable in a future phase.
7. The **API plan** (planning only): PUSH intake, list / read closeouts and runbooks,
   and closeout transition endpoints. Every endpoint is lifecycle / state management
   only; none executes a P22 action or flips a flag.
8. The **security / RBAC boundary**: identity-only platform-operator visibility
   (`support_operator`, `engineering_operator`, `super_admin`), reusing the existing
   auth / RBAC / session transport; no auth rewrite in P24.
9. The **acceptance criteria, counterexamples, and the P24-B entry gate**.

P24-A is **contract only**. It ships **no runtime code, no migration, no endpoint, no
intake receiver, no closeout worker, no notification sender, no frontend**.

### 1.2 In scope (contract layer)

- Define the incident closeout lifecycle and its allowed / forbidden transitions
  (section 3).
- Define the runbook step model: step kinds, step state, composition, ordering,
  evidence (section 4).
- Define the source boundaries and the PUSH intake contract (section 5.1).
- Define the materialization rules for `incident_followup_required` and
  `runbook_step_required` (section 5.2 / 5.3) and what does NOT materialize (section
  5.4).
- Define the data model plan for `platform_incident_closeout`, `platform_runbook`, and
  `platform_runbook_step` (planning only; section 6).
- Define the audit / event model for closeout transitions and runbook step changes
  (planning only; section 7).
- Define the API plan (planning only; section 9).
- Define the security / RBAC visibility boundary (section 8).
- Define the acceptance criteria and counterexamples (sections 10 and 11).
- Define the P24-B entry gate (section 12).
- Define the future AI Operator Copilot boundary against this closeout substrate
  (section 13).

### 1.3 Non-goals

The non-goals split into two groups so the contract does not accidentally forbid the
P24-B work it explicitly permits (section 12):

- **P24-A-only non-goals** (1.3.1) are forbidden in P24-A, but a future P24-B may
  implement the corresponding **non-executing, non-sending** skeleton under its own
  entry gate.
- **All-P24 non-goals** (1.3.2) are forbidden across **every** P24 phase unless a new
  contract revision is accepted by the CTO.

#### 1.3.1 P24-A-only non-goals (P24-B may implement these under its gate)

- No runtime code, no backend handlers, no frontend UI, no test code, and no dependency
  changes in P24-A.
- No migrations, no alembic changes, and no new tables or columns in P24-A. (A future
  P24-B migration, if any, requires separate explicit approval in the P24-B contract
  review; see section 12.)
- **No real closeout worker, no intake receiver, no scheduler, no drain loop in
  P24-A.** P24-A defines the contract only; no closeout is materialized, indexed,
  polled, drained, or advanced at runtime in P24-A. (P24-B may add an in-memory,
  non-executing closeout read model, runbook step model, PUSH intake receiver, and
  lifecycle / step state skeleton; a real persisted store / worker is reserved for a
  separately approved phase.)
- **No task materialization in P24-A.** P24-A defines when
  `incident_followup_required` and `runbook_step_required` are owed; it materializes no
  task in P24-A. (P24-B may upsert these two task types into the P23-B in-memory queue
  via the existing P23 upsert seam, under the P23 contract unchanged.)
- **No frontend in P24-A.** The Incident Closeout / Runbook page, drawer, and step
  checklist are planned here but implemented in a later, separately approved slice.

#### 1.3.2 All-P24 non-goals (every P24 phase, unless a new contract revision is accepted)

- **No execution by the closeout.** No incident closeout transition, runbook step state
  change, PUSH intake event, or worker step executes a P22 action, approves an approval,
  sets or clears the P17 `incident_active` flag, or mutates a registry field. P24 is
  read / mirror / present / close out over P15 / P17 / P18 / P19 / P20 / P21 / P22 /
  P23; it is never an execution path.
- **No flag mutation.** The `incident_active` flag is owned by P17 and changed only by
  P22 governed execution of `incident.flag_set` / `incident.flag_clear`. P24 *mirrors*
  the observed flag state into the closeout lifecycle; it never sets or clears the flag.
  A transition into `flagged_active` only records that the flag was observed true; a
  transition into `closed` only records that the flag was observed false (if it was ever
  set). The P24 transition flips no P17 field.
- **No bypass of any gate.** P24 never short-circuits the P18 allowlist, the P19
  approve / reject boundary, the P20 maker-checker / quorum policy, the P21 durability
  rules, the P22 dry-run / precondition / audit envelope, or the P23 task triage
  machine. Marking a runbook step `done` or an incident `closed` is a *presentation*
  label conditioned on observed prior-phase state; it grants no execution and no
  approval.
- **No real notification delivery.** A closeout transition or step change may
  *materialize* a P23 notification EVENT (a record of attention); it never delivers it.
  Even in later P24 phases, no channel sends a secret, raw payload, DSN, host, port,
  token, cookie, auth header, stack trace, raw request / response body, shell / SQL, or
  tenant business payload. The P23 never-leaked list binds P24 in full.
- **No product business incident / task.** The closeout carries platform operational
  incidents only (a platform anomaly, an `incident_active` flag, owed runbook steps). It
  never carries a product business incident -- an order, payment, invoice, customer,
  inventory, or ledger follow-up is out of scope for platform P24 and belongs to product
  tooling.
- **No tenant business mutation.** Closing, withdrawing, or advancing a closeout, or
  marking a runbook step, changes closeout / step state only; it never reads, writes,
  creates, updates, or deletes tenant business records.
- **No tenant data leak across contexts.** A closeout scoped to tenant A is never
  visible to an operator acting in tenant B's context; cross-tenant visibility requires
  the identity-only, system-scope path and is audited.
- **No auth / RBAC / session / tenancy rewrite.** P24 reuses the P10 identity-only guard
  and the existing operator roles; no new auth transport, token, or session model is
  defined or implemented.
- **No AI agent execution or auto-approval.** P24 names a future AI Operator Copilot
  boundary (section 13); it grants no AI the power to execute, approve, auto-close,
  auto-withdraw, or auto-complete a closeout or runbook step without a human operator.
- **No deletion of audit history.** `withdrawn` and `expired` remove a closeout from the
  active view; they never delete, overwrite, or truncate the underlying P15 / P17 / P18
  / P19 / P20 / P21 / P22 / P23 audit trail. The closeout is a view; it is not the
  system of record.
- **No silent source fabrication.** A closeout whose linked source is `source_unknown`
  is never displayed or closed as healthy; a `backup_check_warning` linked into a
  closeout is never displayed or closed as success (P10 / P17 / P22 / P23 rule, carried
  into P24). Unknown is never healthy; a warning is never a success.
- No merge or push of platform-dev and no push to any product branch from any P24 phase.

## 2. Relationship to Prior Phases (P10 through P23)

P24 introduces **no new auth, RBAC, session, observability, data-source, registry,
storage, approval, execution, or task-triage concepts**. It is the *closeout and
materialization* layer that connects P15 incident triage, the P17 incident flag, P18
through P22 action / approval / execution, and P23 task triage into one non-executing
incident lifecycle. Every prior phase produced a piece of an incident and left it on its
own page; P24 closes the incident out.

| Prior phase | What P24 consumes / mirrors |
|---|---|
| **P10** identity-only guard, PlatformAuditEvent, source-status vocabulary, redact_metadata allowlist | Every closeout, runbook, step, and audit event is visible only behind the P10 identity-only platform-operator guard. Closeout and step audit events are typed specializations of PlatformAuditEvent. The P10 redact_metadata allowlist is applied to every closeout reason, runbook evidence note, step observation, and audit field before it is recorded or returned. The source-status rules (unknown is never healthy, null is never zero) gate how a closeout is labeled and when it may close. |
| **P11 / P12 / P13 / P14 / P15** Cockpit, Support Console, Observability, Incident Triage | P24-A changes none of these surfaces. P24 reads the P15 IncidentClassification, IncidentTriageSnapshot, IncidentHandoffSummary, and IncidentRunbookHint as evidence and as the seed of a closeout; it reuses the P15 classification vocabulary (`database \| system \| api \| tenant_health \| support_issue`) unchanged. P24 adds no cockpit / console control and no execute / approve / flag button anywhere. The support package / diagnostics bundle (P12) is evidence a runbook step may cite; P24 never packages or delivers it. |
| **P16** Worktree Execution Harness | P24 never invokes the P16 harness. A runbook `action_pointer` step may *link* to a P22 execution that (in a separately approved phase) ran through the runtime governed adapter seam; the step itself runs nothing. |
| **P17** Registry, Tenant Lifecycle, `incident_active` | The P17 `TenantOperationalFlags.incident_active` flag is the authoritative incident state. P24 *mirrors* the observed flag value into the closeout lifecycle (`flagged_active` when observed true; `closed` / `awaiting_closeout` reflect an observed clear); P24 never sets or clears the flag and reads P17 status / source signals as evidence only. |
| **P18** Controlled Platform Actions | P18 created the `incident.flag_set` / `incident.flag_clear` action requests (the write complement to P15 triage) plus `provisioning.recheck`, `backup.check`, and the rest of the v0 catalog. A runbook `action_pointer` step links to a P18 `action_id`; the step is `done` only when the linked request reaches a terminal executed / failed state through P22. P24 flips no P18 `executed` flag and creates no P18 request. |
| **P19** Approval Workflow | P19 approve / reject is the gate. A runbook `approval_pointer` step is `done` only when the linked P19 / P20 / P21 approval resolves. Marking the step done approves nothing; it mirrors the approval outcome. |
| **P20** Durable Approval Governance | P20 maker-checker / quorum caps approvals at `approved_execution_blocked`. A closeout never grants quorum, and a step never waives maker-checker. An `approval_pointer` step mirrors the durable approval state; it changes nothing. |
| **P21** Durable Approval Store | P21 made approvals durable and restart-safe. A closeout / step links to the durable `approval_id` / `durable_approval_id` and reads the durable audit trail as evidence; P24 changes no P21 table, field, enum, or migration. |
| **P22** Controlled Execution v0 | P22 defines the execution-record lifecycle (`dry_run_passed -> ... -> executed / execution_failed / compensation_completed`) and governs `incident.flag_set` / `incident.flag_clear` / `backup.check` / `provisioning.recheck`. A runbook `action_pointer` step is `done` only when the linked execution record is observed at `executed` (or honestly `execution_failed`, recorded with reason); a closeout that depended on a flag may `close` only when `incident.flag_clear` is observed `executed`. P24 observes outcomes; it executes nothing. |
| **P23** Operator Task / Notification Queue | P23 is the substrate P24 materializes **into**. P24 owns the materialization contract for exactly two of the ten P23 task types -- `incident_followup_required` and `runbook_step_required` -- which P23-C deliberately did not pull. P24 upserts these tasks through the existing P23 upsert seam (dedup_key_digest, severity, correlation_id, linked ids unchanged); it does not redefine the P23 task triage machine, the notification boundary, or the never-leaked list. |

In one line, restated for the record: P15 triages an incident read-only; P18 creates the
flag-set / flag-clear requests; P19 / P20 / P21 gather and durably store the approvals
those requests need; P22 governs their execution (and may set / clear the flag);
P23 aggregates all of it into a task queue; **P24 closes the incident out -- it threads
detection, flag state, owed follow-up, owed runbook steps, and execution outcomes into
one non-executing lifecycle and materializes the two task types P23-C left as PUSH
intake -- but P24 itself executes nothing, approves nothing, flips no flag, mutates
nothing, and delivers nothing.** An incident closeout is a view, not an executor.

## 3. Incident Closeout Lifecycle

Every incident closeout carries a lifecycle state. The lifecycle is a **presentation /
closeout** state machine, entirely separate from the P15 triage workflow, the P22
execution-record machine, and the P23 task triage machine. **No closeout transition
executes a controlled action, approves an approval, sets or clears the `incident_active`
flag, or mutates a registry field.** Transitions only record operator judgment and
mirror observed prior-phase state.

### 3.1 States

```text
 detected --+--> triaged                              (P15 classification recorded)
            +--> withdrawn                            (operator judged not-an-incident)
            +--> expired                              (TTL passed with no triage)

 triaged --+--> flagged_active     (P17 incident_active observed true via P22 set)
           +--> in_remediation     (runbook steps owed; flag may be false / not set)
           +--> closed             (triage alone closed it out; no flag, no owed steps)
           +--> withdrawn
           +--> expired

 flagged_active --+--> in_remediation    (steps underway)
                  +--> awaiting_closeout  (follow-up done; awaiting flag clear + judgment)
                  +--> withdrawn
                  +--> expired

 in_remediation --+--> flagged_active      (flag re-observed true; new evidence)
                  +--> awaiting_closeout    (all owed steps recorded terminal)
                  +--> withdrawn
                  +--> expired

 awaiting_closeout --+--> closed            (flag observed cleared via P22 + closeout
                    |                        recorded; OR no flag was ever set)
                    +--> in_remediation      (a step reopened; new follow-up owed)
                    +--> expired

 closed    : terminal
 withdrawn : terminal
 expired   : terminal
```

### 3.2 State semantics

| state | Meaning |
|---|---|
| `detected` | A P15 signal / snapshot has been observed and an incident closeout record opened. The P17 `incident_active` flag may be true or false at this point. Initial state. |
| `triaged` | A P15 IncidentClassification (`database \| system \| api \| tenant_health \| support_issue`) has been recorded against the incident. |
| `flagged_active` | The linked P17 `incident_active` flag is observed true (set via a P22 `incident.flag_set` execution at `executed`, or a P17 read). Follow-up is owed; an `incident_followup_required` P23 task is materialized. P24 set nothing; it mirrors the flag. |
| `in_remediation` | At least one runbook step is `owed` or `in_progress`; `runbook_step_required` P23 task(s) are materialized. The flag may or may not be set. |
| `awaiting_closeout` | All owed follow-up and runbook steps are recorded terminal (`completed` / `done` / honestly `failed` / `not_applicable`) in P23 / P24, and the incident is waiting for an observed flag clear through P22 (if the flag was set) and / or the operator's closeout judgment. |
| `closed` | The operator recorded closeout. All owed follow-up and runbook steps are terminal, and -- if the flag was ever set -- `incident_active` is observed false (cleared via P22 `incident.flag_clear` at `executed`). Terminal. P24 cleared nothing. |
| `withdrawn` | The operator judged the detection a non-incident / false positive. The closeout leaves the active view; the audit history is retained; if the flag had been set it must still be cleared through P22 independently. Terminal. |
| `expired` | The closeout TTL passed without resolution. Terminal. |

### 3.3 Transition rules

1. **Transitions are operator-driven, intake-driven, or TTL-driven only.** A closeout
   advances because an operator recorded triage / closeout, because a recorded PUSH
   intake event reflected new prior-phase state (flag set / cleared, step done,
   execution outcome), or because a TTL expired. No transition runs an action or flips
   a flag.
2. **The flag is mirrored, never owned.** A transition into `flagged_active` is
   permitted only when the linked `incident_active` flag is *observed* true; a
   transition into `closed` (from a state where the flag was set) is permitted only when
   the flag is *observed* false. The observation is evidence (a P22 execution record at
   `executed`, or a P17 read); the P24 transition writes no P17 field.
3. **Terminal states are terminal.** `closed`, `withdrawn`, and `expired` accept no
   outgoing transition. Reopening requires a *new* closeout (new id, same
   `correlation_id` link), not a resurrection.
4. **`closed` requires honest completion.** `closed` requires (a) every linked
   `incident_followup_required` and `runbook_step_required` P23 task at a terminal state
   (`completed`, `dismissed` with redacted reason, or honestly `failed`), AND (b) if the
   flag was ever set, the flag observed false via P22 `incident.flag_clear`. A closeout
   whose linked source is `source_unknown` or whose linked execution is at
   `backup_check_warning` cannot be `closed` as healthy.
5. **A transition records exactly one closeout audit event** (section 7), with previous
   and next state, observed flag state, and linked ids. There is no unaudited transition
   and no batch transition that hides intermediate states.
6. **No transition touches tenant business data, payments, product code, or secrets.**
7. **No transition sends a notification.** A state change may *materialize* a P23
   notification event (a record of attention); it never delivers it.

### 3.4 Forbidden transitions (must be rejected)

- `closed -> *`, `withdrawn -> *`, `expired -> *` (terminal).
- `* -> flagged_active` when the linked `incident_active` flag is **not** observed true
  -- rejected; P24 may not fabricate an active flag.
- `* -> closed` when the flag was set and is **not** observed false -- rejected; the
  closeout may not fabricate a flag clear. (The flag clears only through P22
  `incident.flag_clear`.)
- `* -> closed` when any linked `incident_followup_required` / `runbook_step_required`
  task is still non-terminal -- rejected; closeout cannot fabricate follow-up
  completion.
- `* -> closed` displayed / recorded as healthy while a linked source is `source_unknown`
  or a linked execution is at `backup_check_warning` -- rejected; unknown is never
  healthy, a warning is never a success.
- Any transition that would also flip a P17 `incident_active` field, a P18 `executed`
  flag, a P19 / P20 / P21 approval state, or a P22 execution-record state.

## 4. Runbook Step Model

A **runbook** is an ordered, typed checklist attached to an incident closeout. It is the
machine-readable refinement of the P15 IncidentRunbookHint (which is a static,
doc-driven, observation-only hint). A runbook step is one of three kinds; **every kind
is a pointer and a record, never an execution.**

### 4.1 Step kinds

| step kind | What it represents | What "done" means | Executes? |
|---|---|---|---|
| `observation` | A read-only observation step (P15 runbook-hint style: "read P13 ops.resources.database", "inspect P14 DB probe", "read P15 snapshot"). | A redacted evidence / observation note is recorded on the step. | No. Reads only; never writes. |
| `action_pointer` | A pointer to a P18 controlled action request (e.g. `provisioning.recheck`, `backup.check`, `incident.flag_clear`, `backup.restore_test_request`). | The linked P22 execution record is observed at `executed` (or honestly `execution_failed`, recorded with redacted reason). | No. The step points; the action runs through P22 governed execution under its own approval / dry-run / audit envelope. |
| `approval_pointer` | A pointer to a P19 / P20 / P21 durable approval the step is waiting on (e.g. "obtain DBA quorum before the restore-test"). | The linked durable approval is observed resolved (approved at `approved_execution_blocked` or rejected). | No. The step mirrors; it approves nothing. |

Notes:

- **An `action_pointer` step is not an execution.** Marking it `done` does not run the
  action and does not flip the P18 `executed` flag; it records that the linked execution
  was *observed* at a terminal state through P22.
- **An `approval_pointer` step is not an approval.** Marking it `done` does not grant
  quorum or approve the approval; it records that the linked approval was *observed*
  resolved through P19 / P20 / P21.
- **Approvals are not execution.** An `action_pointer` step whose linked action needs an
  approval is `done` only when the *execution* is observed `executed` -- not when the
  approval alone is granted. An `approval_pointer` step and an `action_pointer` step are
  distinct; conflating them would let an approval masquerade as an execution.

### 4.2 Step state

```text
 owed --+--> in_progress        (operator / intake began the step)
        +--> done               (terminal: observation note recorded, or linked
        |                        action / approval observed terminal through P22 / P19-21)
        +--> not_applicable     (terminal: operator marked the step out of scope, with
        |                        a redacted reason)
        +--> blocked            (linked source unknown / approval deadlocked; cannot
                                 complete honestly)

 in_progress --+--> done
               +--> not_applicable
               +--> blocked

 blocked --+--> owed            (linked source recovered / approval re-opened)
           +--> not_applicable

 done            : terminal
 not_applicable  : terminal
```

- A `runbook_step_required` P23 task is materialized for each step in `owed`,
  `in_progress`, or `blocked` (section 5.3).
- `done` for an `action_pointer` step requires the linked P22 execution at `executed`
  (or `execution_failed` / `compensation_completed` recorded honestly); `done` for an
  `approval_pointer` step requires the linked approval resolved; `done` for an
  `observation` step requires a redacted evidence note. The step never executes.
- A `blocked` step whose linked source is `source_unknown` is never displayed as
  healthy and never auto-completes.

### 4.3 Runbook composition

- A runbook belongs to exactly one incident closeout (`incident_closeout_id`).
- Steps are ordered (`sequence_no`); ordering is presentation / guidance, not an
  execution order -- the closeout never executes the steps, so order is a hint for the
  operator.
- A runbook may be seeded from a doc-driven template keyed by the P15 classification
  category; the template is authored in docs / config (as P15 runbook hints are), never
  generated from tenant data.
- A step carries evidence pointers only (`linked_action_id`, `linked_approval_id`,
  `linked_execution_id`, `evidence_ref`); it never stores a raw payload, a secret, or a
  tenant business record.

### 4.4 What a runbook step is NOT

- **Not an executor.** No step kind runs an action, approves an approval, or flips a
  flag.
- **Not a delivery.** No step sends a notification; it may materialize a P23
  notification event (a record), nothing more.
- **Not a tenant business object.** A step never carries an order / payment / invoice /
  customer / inventory / ledger reference as payload.
- **Not a resurrection.** A `done` / `not_applicable` step is terminal; reopening
  requires a new step (new id, same `correlation_id`).

## 5. Source Boundaries and Materialization Rules

### 5.1 PUSH intake (not PULL)

P24 is a **PUSH intake** closeout layer, the counterpart to P23-C's read-only PULL
bridge. P23-C pulls four task types from the P19 / P22 read paths; the two P24-owned
types -- `incident_followup_required` and `runbook_step_required` -- arrive via recorded
intake events, because they depend on operator / lifecycle judgment (an incident was
detected and triaged; a follow-up is owed; a runbook step is owed) that no read path
alone produces.

P24-A defines the closed set of recorded intake events a future P24-B may accept (behind
the P10 identity-only platform-operator guard):

- `incident_detected` -- a P15 snapshot / signal was observed; opens a closeout at
  `detected`.
- `incident_classified` -- a P15 classification was recorded; advances to `triaged`.
- `incident_flag_observed` -- the P17 `incident_active` flag was observed set or cleared
  (evidence: a P22 execution record at `executed` for `incident.flag_set` /
  `incident.flag_clear`, or a P17 read); advances to / mirrors `flagged_active` /
  `awaiting_closeout` / `closed`.
- `runbook_step_owed` / `runbook_step_progress` / `runbook_step_terminal` -- a runbook
  step changed state; advances the step and, derivatively, the closeout
  (`in_remediation` / `awaiting_closeout`).
- `closeout_transition` -- an operator recorded a closeout judgment (advance to
  `awaiting_closeout` / `closed` / `withdrawn`).

**Intake is record-only and non-executing.** Accepting an event updates the in-memory
closeout / step / task view; it runs no action, flips no flag, approves nothing, and
delivers nothing. The receiver is read from the P10 identity-only guard's actor (the
token), never from the event body; the event body carries redacted evidence and linked
ids only. The P23 never-leaked list binds every intake field.

### 5.2 `incident_followup_required` materialization

A `incident_followup_required` P23 task is materialized when **all** of:

- an incident closeout exists and is non-terminal;
- the linked P17 `incident_active` flag is observed true (closeout at `flagged_active`,
  or `in_remediation` with the flag set); AND
- no completion evidence has been recorded (the follow-up is owed).

Dedup key (canonical, SHA-256 hashed to `dedup_key_digest` per P23 section 5.4):
`(incident_followup_required, incident_closeout_id, tenant_id, follow-up variant)`.
Severity: default `medium`, raised to `high` when a correlated peer (failed execution,
`source_unknown`, `backup_check_warning`) shares the `correlation_id` (P23 severity
rules). Follow-up: "complete the incident follow-up; clear the flag through P22
`incident.flag_clear` only."

The task flows through the P23 triage machine unchanged; P24 only owns *when it is owed*
and *when it leaves the active queue* (when the closeout leaves `flagged_active` with
follow-up complete, or the incident is closed / withdrawn / expired).

### 5.3 `runbook_step_required` materialization

A `runbook_step_required` P23 task is materialized per runbook step when **all** of:

- the step belongs to a non-terminal incident closeout; AND
- the step is in `owed`, `in_progress`, or `blocked`.

Dedup key: `(runbook_step_required, runbook_step_id, incident_closeout_id, tenant_id)`.
Severity: default `medium`, raised to `high` for an `action_pointer` step whose linked
action is destructive-class or whose linked execution is at `execution_failed`, and for
any step blocked on `source_unknown`. Follow-up: "perform the runbook step; record
evidence on the task; for an action_pointer, run the action through P22 only."

When a step goes terminal (`done` / `not_applicable`), its task is resolved through the
P23 triage machine (completed with evidence, or dismissed with a redacted reason). The
step / task executes nothing.

### 5.4 What does NOT materialize a task

- A closeout that is `closed`, `withdrawn`, or `expired` materializes no task.
- A `detected` closeout with no classification, no flag, and no owed steps materializes
  no task (it is an unresolved observation, not owed work).
- A runbook step that is `done` or `not_applicable` materializes no task.
- A `flagged_active` closeout with completion evidence already recorded materializes no
  *new* `incident_followup_required` task (the existing one, if any, is resolved).
- A product business follow-up (order / payment / invoice / customer / inventory /
  ledger) is never materialized as a P24 incident or runbook task -- it is out of scope
  for platform P24.
- A `source_unknown` signal alone (no incident closeout) is owned by P23-C, not P24; P24
  materializes a `source_unknown` task only when one is *linked into* a closeout as
  evidence, and even then the task type, dedup, and severity follow P23 unchanged.

### 5.5 Idempotency / dedup (extends P23, does not redefine it)

- P24 reuses the P23 `dedup_key_digest` discipline (SHA-256 over the canonical key;
  terminal tasks / steps exempt; no cross-tenant dedup; replays idempotent).
- A terminal closeout does not absorb a new event; a recurring incident re-opens as a
  new closeout (new id, same `correlation_id`).
- A terminal step does not absorb a new event; a recurring step re-opens as a new step.
- P24 changes no P23 dedup rule; it only supplies the canonical key inputs for the two
  task types it owns.

## 6. Data Model Plan (planning only -- not implemented in P24-A)

P24-A plans, but does not implement, three logical records. No table, migration, ORM
model, enum, or column is created in P24-A. The plan is the input to a future P24-B that
may implement an in-memory read model and, much later, a persisted store under separate
approval.

### 6.1 Logical record: `platform_incident_closeout`

```text
IncidentCloseout {
  closeout_id          : uuid        -- PK. required. Unique per closeout instance.
  state                : enum        -- required. Closed set (section 3.1).
  classification       : enum        -- nullable. P15 vocabulary: database | system |
                                     -- api | tenant_health | support_issue.
  severity             : enum        -- required. low | medium | high (mirrors P23).
  tenant_id            : uuid        -- nullable. Scoped id only; null for platform-wide.
                                     -- Never a business payload; never joinable to a
                                     -- product business table.
  actor_scope          : enum        -- required. platform | tenant_contextual.
  owner_role           : enum        -- nullable. Suggested owner role (presentation only;
                                     -- not authorization).
  owner_actor_id       : varchar     -- nullable. The operator who self-assigned, if any.
  correlation_id       : varchar     -- required. Threads P15 / P17 / P18 / P19 / P20 /
                                     -- P21 / P22 / P23 events into one closeout thread.
  flag_observed        : enum        -- required. observed_true | observed_false |
                                     -- observed_unknown. Mirrors P17 incident_active;
                                     -- P24 NEVER writes the flag.
  linked_incident_id   : uuid        -- nullable. -> P15 / P17 incident id.
  linked_triage_snapshot_ref : varchar -- nullable. -> P15 IncidentTriageSnapshot handle.
  linked_handoff_ref   : varchar     -- nullable. -> P15 IncidentHandoffSummary handle.
  summary_redacted     : text        -- required. One-line redacted summary. P10 allowlist
                                     -- applied. No secret, no raw payload, no DSN / host /
                                     -- port.
  reason_redacted      : text        -- nullable. Redacted closeout / triage reason.
  source_status        : enum        -- nullable. known | unknown | degraded. Mirrors the
                                     -- linked source; never fabricated healthy.
  dedup_key_digest     : char(64)    -- required. SHA-256 of the canonical dedup key
                                     -- (section 5). Drives collapse of repeat events.
  ttl_expires_at       : timestamptz -- nullable. When the closeout auto-expires.
  created_at           : timestamptz -- required. UTC ISO-8601.
  updated_at           : timestamptz -- required. UTC ISO-8601.
  redaction_applied    : bool        -- required. DEFAULT true.
}
```

Planned indexes / uniqueness (planning only): PK `closeout_id`; correlation index
`(correlation_id)`; source-link indexes `(linked_incident_id)`, `(tenant_id)`,
`(owner_actor_id)`; a dedup unique scoped to non-terminal states (Postgres partial-unique
discipline over active states, not a NULL column) so a recurring incident re-opens as a
new closeout.

### 6.2 Logical records: `platform_runbook` and `platform_runbook_step`

```text
Runbook {
  runbook_id           : uuid        -- PK. required.
  closeout_id          : uuid        -- required. -> IncidentCloseout.closeout_id.
  template_ref         : varchar     -- nullable. Doc-driven template key (by P15
                                     -- classification), if seeded from a template.
  correlation_id       : varchar     -- required. Echoes the closeout correlation_id.
  created_at           : timestamptz -- required. UTC ISO-8601.
  redaction_applied    : bool        -- required. DEFAULT true.
}

RunbookStep {
  step_id              : uuid        -- PK. required. Unique per step instance.
  runbook_id           : uuid        -- required. -> Runbook.runbook_id.
  closeout_id          : uuid        -- required. Echoed for direct closeout lookups.
  sequence_no          : int         -- required. Presentation order; not execution order.
  step_kind            : enum        -- required. observation | action_pointer |
                                     -- approval_pointer (section 4.1).
  step_state           : enum        -- required. owed | in_progress | done |
                                     -- not_applicable | blocked (section 4.2).
  tenant_id            : uuid        -- nullable. Scoped id only.
  correlation_id       : varchar     -- required. Echoes the closeout correlation_id.
  linked_action_id     : uuid        -- nullable. -> P18 action_id (action_pointer).
  linked_approval_id   : uuid        -- nullable. -> P21 durable_approval_id
                                     -- (approval_pointer).
  linked_execution_id  : uuid        -- nullable. -> P22 execution_request_id
                                     -- (action_pointer).
  linked_source_ref    : varchar     -- nullable. -> P17 backup / status source handle
                                     -- (observation / action_pointer).
  evidence_ref         : varchar     -- nullable. Pointer to evidence (audit event id,
                                     -- observation note id). Never raw payload.
  summary_redacted     : text        -- required. Redacted one-line summary.
  reason_redacted      : text        -- nullable. Redacted step reason / observation note.
  source_status        : enum        -- nullable. known | unknown | degraded. Mirrors the
                                     -- linked source; never fabricated healthy.
  dedup_key_digest     : char(64)    -- required. SHA-256 of the canonical step dedup key.
  created_at           : timestamptz -- required. UTC ISO-8601.
  updated_at           : timestamptz -- required. UTC ISO-8601.
  redaction_applied    : bool        -- required. DEFAULT true.
}
```

Planned indexes / uniqueness (planning only): PK `step_id`; per-runbook index
`(runbook_id, sequence_no)`; closeout index `(closeout_id)`; source-link indexes
`(linked_action_id)`, `(linked_approval_id)`, `(linked_execution_id)`; a dedup unique
scoped to non-terminal step states (partial-unique discipline) so a recurring step
re-opens as a new step.

### 6.3 Relationship to prior-phase ids

- `linked_incident_id` -> P15 / P17 incident id; `linked_triage_snapshot_ref` /
  `linked_handoff_ref` -> P15 snapshot / handoff handles (evidence pointers only).
- `flag_observed` mirrors P17 `incident_active`; it is an observation, not a write.
- `linked_action_id` -> P18 `action_id`; `linked_approval_id` -> P21
  `durable_approval_id`; `linked_execution_id` -> P22 `execution_request_id`;
  `linked_source_ref` -> P17 backup / status source handle.
- All links are **evidence pointers**. The closeout never stores the raw P18 request
  body, the raw P21 approval envelope, the raw P22 execution payload, the raw source
  artifact, the raw P15 snapshot, or any tenant business payload. Only redacted
  summaries and digests are stored (the P23 never-leaked list binds in full).

## 7. Audit / Event Model (planning only -- not implemented in P24-A)

Every closeout transition and every runbook step change is auditable. P24-A defines the
audit shapes and rules; a future phase records the events. The audit logs are
append-only; no UPDATE path; no single-row DELETE; only whole-record retention purge (P21
discipline), itself audited.

### 7.1 Closeout audit event (planning shape)

```text
IncidentCloseoutAuditEvent {
  event_id              : uuid        -- PK. required. Unique.
  closeout_id           : uuid        -- required. The closeout whose state changed.
  state                 : enum        -- required. Closed set (section 3.1).
  actor_id              : varchar     -- required. The operator (or SYSTEM for intake /
                                       -- TTL). Identity-only platform-operator.
  actor_role            : enum        -- required. super_admin | engineering_operator |
                                       -- support_operator | system.
  tenant_id             : uuid        -- nullable. Scoped id only.
  transition            : enum        -- required. e.g. detected->triaged,
                                       -- flagged_active->awaiting_closeout,
                                       -- awaiting_closeout->closed.
  previous_state        : enum        -- required. State before the transition.
  next_state            : enum        -- required. State after the transition.
  flag_observed         : enum        -- required. observed_true | observed_false |
                                       -- observed_unknown. Mirrors P17; never a write.
  reason_redacted       : text        -- nullable. Redacted reason / judgment note. P10
                                       -- allowlist applied. Never raw payload / secret.
  correlation_id        : varchar     -- required. Echoes the closeout correlation_id.
  linked_incident_id    : uuid        -- nullable. Echoed for traceability.
  linked_action_id      : uuid        -- nullable.
  linked_approval_id    : uuid        -- nullable.
  linked_execution_id   : uuid        -- nullable.
  redaction_applied     : bool        -- required. DEFAULT true.
  sequence_no           : bigint      -- required. Monotonic per-closeout sequence.
  created_at            : timestamptz -- required. UTC ISO-8601.
}
```

### 7.2 Runbook step audit event (planning shape)

```text
RunbookStepAuditEvent {
  event_id              : uuid        -- PK. required. Unique.
  step_id               : uuid        -- required. The step whose state changed.
  closeout_id           : uuid        -- required. Echoed.
  step_kind             : enum        -- required. observation | action_pointer |
                                       -- approval_pointer.
  step_transition       : enum        -- required. e.g. owed->in_progress,
                                       -- in_progress->done.
  previous_state        : enum        -- required. Step state before.
  next_state            : enum        -- required. Step state after.
  actor_id              : varchar     -- required. Operator or SYSTEM.
  actor_role            : enum        -- required.
  tenant_id             : uuid        -- nullable. Scoped id only.
  evidence_redacted     : text        -- nullable. Redacted observation / evidence note.
  correlation_id        : varchar     -- required. Echoes the closeout correlation_id.
  linked_action_id      : uuid        -- nullable. Echoed (action_pointer).
  linked_approval_id    : uuid        -- nullable. Echoed (approval_pointer).
  linked_execution_id   : uuid        -- nullable. Echoed (action_pointer).
  linked_source_ref     : varchar     -- nullable.
  redaction_applied     : bool        -- required. DEFAULT true.
  sequence_no           : bigint      -- required. Monotonic per-step sequence.
  created_at            : timestamptz -- required. UTC ISO-8601.
}
```

### 7.3 Audit rules

- One event per transition / step change; no batch transition hides intermediate states.
- `previous_state` and `next_state` are always recorded; a terminal-state exit attempt is
  audited as a denied transition.
- `flag_observed` is always an *observation*; no audit field ever records a P17 flag
  write performed by P24 (because P24 performs none).
- `reason_redacted`, `evidence_redacted`, and every echoed field pass through the P10
  allowlist; the P23 never-leaked list applies in full.
- `withdrawn` and `expired` are audited like any other transition; the underlying P15 /
  P17 / P18 / P19 / P20 / P21 / P22 / P23 audit trail is untouched.
- Denials (e.g. closing a closeout whose flag is still set, or marking an action step
  done whose execution is still at `dry_run_passed`) are audited.
- No audit field contains a secret, raw payload, DSN, host, port, token, cookie, auth
  header, stack trace, raw body, shell / SQL, or tenant business payload.

## 8. Security / RBAC Boundary

P24 reuses the existing auth / RBAC / session transport. It defines **no new auth, no new
token, no new session model, no new role**. Runtime authorization for *actions* remains
the P10 identity-only guard plus the P18 / P20 / P22 per-action boundary; P24-A only
plans *visibility* of closeouts, runbooks, and steps, and *intake* of recorded events.

### 8.1 Visibility by role (planning only; runtime left to a later gated slice)

- **`support_operator`**: sees closeouts within its P18 support-safe scope -- typically
  `support_issue` / `tenant_health` classifications, the `incident_followup_required`
  tasks, and the `observation` runbook steps within its scope. Never sees an
  `action_pointer` step as an executor (P22 executor is identity-only super_admin).
- **`engineering_operator`**: sees source / execution health closeouts within its scope
  -- `database` / `system` / `api` classifications, `action_pointer` steps whose linked
  actions are read-class (`provisioning.recheck`, `backup.check`), `observation` steps.
  Never an executor for write-class actions, never a checker.
- **`super_admin` (identity-only)**: sees the full platform-wide closeout view, may be
  checker / executor (through P22, never through P24), and may record closeout judgment.
  Tenant-contextual super_admin is bounded by its tenant context (no cross-tenant leak).
- **Tenant admin / tenant-scoped token**: never sees platform incident closeouts; the
  closeout view is a platform-operational surface, not a tenant surface.

### 8.2 Hard rules

1. **Identity-only platform-operator guard.** Every closeout / runbook / step read, every
   state-change endpoint, and the PUSH intake receiver are behind the P10 identity-only
   platform-operator guard. Tenant admin, tenant-scoped token, and unauthenticated
   callers are denied.
2. **No auth / RBAC rewrite in P24.** P24 consumes roles; it does not redefine them.
3. **Tenant scope is enforced at the read.** A closeout with `tenant_id == A` is
   invisible to an operator in tenant B's context unless the operator is on the
   identity-only platform-scope path (and that access is audited).
4. **Owner is not authorization.** `owner_role` / `owner_actor_id` are presentation and
   triage; they grant no new privilege. An operator may self-assign only closeouts
   already visible to them.
5. **No privilege escalation through the closeout.** Recording an `action_pointer` step
   as `done` does not make the recorder the P22 executor; running the linked action still
   requires the P22 identity-only super_admin executor and the full precondition set.
   Recording a closeout as `closed` does not clear the flag; the flag clears only through
   P22 `incident.flag_clear`.
6. **Intake actor comes from the token, not the body.** The PUSH intake receiver reads
   the actor from the P10 identity-only guard; the event body never names the actor.

## 9. API Plan (planning only -- not implemented in P24-A)

P24-A proposes -- does not implement -- the following closeout surface. Every endpoint
is behind the P10 identity-only platform-operator guard; **none executes a P22 action,
approves an approval, sets or clears the `incident_active` flag, or mutates a registry
field**.

- **POST /platform/p24/incident-closeouts/intake** -- PUSH intake of a recorded closeout
  event (section 5.1). Non-executing; advances the in-memory closeout / step view and
  upserts P23 tasks via the existing P23 seam. Actor from the token, not the body.
- **GET /platform/p24/incident-closeouts** -- list closeouts with filters (state,
  classification, severity, tenant, flag_observed, owner, correlation_id) and pagination.
  Read-only; audited as a read.
- **GET /platform/p24/incident-closeouts/{closeout_id}** -- read one closeout's redacted
  record, state, flag_observed, evidence links, and runbook summary. Read-only.
- **GET /platform/p24/incident-closeouts/{closeout_id}/runbook** -- read the ordered
  runbook steps (kind, state, linked ids, evidence).
- **POST /platform/p24/incident-closeouts/{closeout_id}/transition** -- record an
  operator closeout judgment (advance to `awaiting_closeout` / `closed` / `withdrawn`),
  subject to the transition rules (section 3.3). Rejects if the gate is still open (flag
  still set, owed tasks still non-terminal, source still unknown). Executes nothing; flips
  no flag.
- **POST /platform/p24/incident-closeouts/{closeout_id}/runbook/{step_id}/transition** --
  record a runbook step state change with a redacted evidence / observation note. Rejects
  a `done` on an `action_pointer` whose execution is not observed terminal, or on an
  `approval_pointer` whose approval is not observed resolved. Executes nothing.

Compatibility notes:

- No response field carries a secret, raw key, raw body, shell / SQL, host / port, or
  tenant payload.
- No endpoint returns a `closed` closeout whose flag is still observed set, or a `done`
  step whose linked gate is still open.
- No endpoint executes, approves, flags, or dispatches.
- A future backend preserves these shapes unless a new versioned contract is approved.

## 10. Acceptance Criteria

A future phase that implements this contract is accepted only when all of the following
hold:

1. **P24-A is docs and ledger only.** No runtime code, backend, frontend, migration,
   alembic change, table, test code, or dependency change ships in P24-A.
2. **An incident closeout is a view, not an executor.** No closeout transition --
   detect, triage, flag-observe, await, close, withdraw -- executes a P22 action,
   approves an approval, sets or clears the `incident_active` flag, or mutates a
   registry field.
3. **A runbook step is a pointer, not an execution.** No step state change runs an
   action, approves an approval, or flips a flag; an `action_pointer` `done` only records
   an observed terminal execution; an `approval_pointer` `done` only records an observed
   resolved approval.
4. **A follow-up task is a record, not a repair.** The `incident_followup_required` and
   `runbook_step_required` tasks materialized by P24 are presentation records that flow
   through the P23 triage machine; completing them executes nothing.
5. **The flag is mirrored, never owned.** A transition into `flagged_active` is permitted
   only when the flag is observed true; a transition into `closed` (where the flag was
   set) is permitted only when the flag is observed false via P22 `incident.flag_clear`.
   P24 writes no P17 `incident_active` field.
6. **`closed` requires honest completion.** Every linked `incident_followup_required` /
   `runbook_step_required` task is terminal, and (if the flag was set) the flag is
   observed cleared. A closeout whose linked source is `source_unknown` or whose linked
   execution is at `backup_check_warning` is not `closed` as healthy.
7. **`source_unknown` is never displayed or closed healthy;** a closeout / step whose
   linked source is `unknown` is labeled and ranked accordingly.
8. **`backup_check_warning` is never displayed or closed as success.**
9. **Approvals are not execution.** An `action_pointer` step is `done` only when the
   linked *execution* is observed `executed`, not when its approval alone is granted; an
   `approval_pointer` step and an `action_pointer` step are never conflated.
10. **No gate is bypassed.** Surfacing a step as `done` or a closeout as `closed` is a
    presentation label conditioned on observed prior-phase state; it grants no execution
    and no approval.
11. **`withdrawn` / `expired` do not delete audit history;** the underlying P15 / P17 /
    P18 / P19 / P20 / P21 / P22 / P23 audit trail is retained; only the active-closeout
    entry is removed.
12. **No tenant leak;** a closeout scoped to tenant A is invisible in tenant B's context;
    cross-tenant visibility is identity-only platform-scope and audited.
13. **No product business incident / task;** the closeout carries platform operational
    incidents only; no order / payment / invoice / customer / inventory / ledger incident
    or task exists.
14. **No tenant business mutation;** closing, withdrawing, or stepping changes closeout /
    step state only; no tenant business record is read or written.
15. **No auth / RBAC rewrite;** P24 reuses the P10 identity-only platform-operator guard
    and existing roles; runtime authorization is unchanged.
16. **Owner is not authorization;** `owner_role` / `owner_actor_id` grant no new
    privilege; self-assignment is bounded by existing visibility.
17. **Intake actor comes from the token, not the body;** the PUSH receiver reads the
    actor from the P10 identity-only guard.
18. **Redaction is total;** every closeout / runbook / step / audit / intake field scans
    clean against the P10 allowlist and the P23 never-leaked list;
    `redaction_applied == true` everywhere.
19. **No raw secrets / DSNs / hosts / ports / tokens / passwords / cookies / auth
    headers, raw bodies, shell / SQL, or tenant payload** appear in any closeout,
    runbook, step, intake event, response, or audit event.
20. **Every closeout transition and every step change is auditable;** one event per
    transition / step change, with `previous_state`, `next_state`, observed flag / linked
    ids, `reason_redacted` / `evidence_redacted`, and `correlation_id`; the logs are
    append-only.
21. **Dedup is correct and unchanged from P23;** many events sharing a
    `dedup_key_digest` collapse into one active closeout / step / task; terminal records
    are exempt; no dedup across tenants; replays write no duplicate.
22. **Materialization is honest;** `incident_followup_required` materializes only for an
    owed follow-up on an active-flagged closeout; `runbook_step_required` materializes
    only for an owed / in-progress / blocked step; nothing materializes for a closed /
    withdrawn / expired closeout or a terminal step (section 5.4).
23. **No AI agent execution / auto-approval / auto-close;** P24-A names a future AI
    Operator Copilot boundary only and grants no AI the power to execute, approve,
    auto-close, auto-withdraw, or auto-complete a closeout or step.
24. **The API is planning only;** no endpoint and no UI ship in P24-A; a future backend /
    frontend preserves the proposed shapes unless a new versioned contract is approved.

## 11. Counterexamples (must fail or be rejected)

1. **C1 -- a closeout transition runs an action.** A `transition` (or step change, or
   intake event) that executes the linked P22 action -- rejected; a closeout is a view,
   not an executor.
2. **C2 -- a closeout transition flips the flag.** A transition that sets or clears P17
   `incident_active` -- rejected; P24 mirrors the flag, it never writes it (the flag
   changes only through P22 `incident.flag_set` / `incident.flag_clear`).
3. **C3 -- closing with the flag still set.** A `* -> closed` transition where the flag
   was set and is not observed false -- rejected; closeout may not fabricate a flag
   clear.
4. **C4 -- closing with owed tasks non-terminal.** A `* -> closed` transition where a
   linked `incident_followup_required` / `runbook_step_required` task is still
   non-terminal -- rejected; closeout cannot fabricate follow-up completion.
5. **C5 -- `flagged_active` fabricated.** A `* -> flagged_active` transition where the
   flag is not observed true -- rejected; P24 may not fabricate an active flag.
6. **C6 -- an `action_pointer` step marked done on approval alone.** A step `done` where
   the linked approval is granted but the P22 execution is not observed `executed` --
   rejected; approvals are not execution.
7. **C7 -- an `action_pointer` step runs the action.** A step transition that executes
   the linked action or flips the P18 `executed` flag -- rejected; the step points, P22
   executes.
8. **C8 -- an `approval_pointer` step grants quorum.** A step `done` that also approves
   the linked approval, grants quorum, or waives maker-checker -- rejected; the step
   mirrors the approval, it never changes it.
9. **C9 -- `source_unknown` closed healthy.** A closeout / step whose linked source is
   `unknown`, displayed or closed as healthy / success -- rejected; unknown is never
   healthy.
10. **C10 -- `backup_check_warning` closed as success.** A closeout / step whose linked
    execution is at `backup_check_warning` (P22-G `completed_with_warning`), closed as
    success -- rejected; a warning is never a success.
11. **C11 -- `withdrawn` / `expired` deletes audit history.** A withdraw / expire that
    removes, overwrites, or truncates the underlying P15 / P17 / P18 / P19 / P20 / P21 /
    P22 / P23 audit trail -- rejected; the closeout is a view, not the system of record.
12. **C12 -- tenant closeout leaks across contexts.** A closeout with `tenant_id == A`
    visible to an operator in tenant B's context (without the identity-only platform-scope
    path) -- rejected (boundary violation).
13. **C13 -- a product business incident in the platform closeout.** An order / payment /
    invoice / customer / inventory / ledger follow-up materialized as a P24 closeout /
    step / task -- rejected; product business incidents are out of scope for platform
    P24.
14. **C14 -- a terminal closeout / step is reopened.** A transition out of `closed` /
    `withdrawn` / `expired`, or a step out of `done` / `not_applicable` -- rejected;
    reopening requires a new closeout / step.
15. **C15 -- a notification is delivered.** A closeout / step change that opens a socket,
    sends an email, or posts a webhook -- rejected; P24 delivers nothing (it may
    materialize a P23 notification EVENT, which is a record).
16. **C16 -- a raw secret in a closeout / step / intake field.** A summary, reason,
    evidence, observation, or intake field containing a credential, DSN, host, port,
    connection string, token, password, cookie, auth header, stack trace, raw body, or
    log line -- rejected (redaction violation).
17. **C17 -- a tenant business payload in a closeout / step.** A closeout / step carrying
    an order id / payment id / invoice id / customer record / inventory record / ledger
    entry as payload -- rejected; `tenant_id` is a scoped id only.
18. **C18 -- cross-tenant dedup.** Tenant-A and tenant-B closeouts / steps collapsed into
    one -- rejected; dedup is per-tenant.
19. **C19 -- a duplicate closeout / step / task on replay.** Re-emitting the same event
    for the same active closeout / step creating a duplicate -- rejected; replay is
    idempotent.
20. **C20 -- an unaudited transition / step change.** A state change that lands without
    exactly one audit event carrying `previous_state`, `next_state`, observed flag /
    linked ids, and `correlation_id` -- rejected (contract violation).
21. **C21 -- an AI agent auto-closing / auto-executing.** An AI copilot path that closes,
    withdraws, approves, executes, or marks a step done without a human operator --
    rejected (section 13).
22. **C22 -- intake actor from the body.** A PUSH intake event whose actor is read from
    the event body instead of the P10 identity-only token -- rejected (spoofing).
23. **C23 -- a migration or table added in P24-A.** Any backend, frontend, migration,
    alembic change, table, test, or dependency change added in P24-A -- rejected; P24-A
    is docs / ledger only.
24. **C24 -- a real closeout worker / intake receiver / scheduler in P24-A.** Any runtime
    drain loop, worker, scheduler, intake receiver, or notification sender added in
    P24-A -- rejected; P24-A defines the contract only.
25. **C25 -- a new auth transport in P24-A.** Any new token, session model, or role
    introduced in P24-A -- rejected; P24 reuses the existing guard.
26. **C26 -- owner grants privilege.** An operator self-assigning a closeout outside
    their visibility, or gaining executor / checker power by owning a closeout / step --
    rejected.

## 12. P24-B Entry Gate (future)

A future P24-B is permitted to implement **only a non-executing, non-sending backend
skeleton**: an in-memory (or existing-safe) closeout read model and runbook step model
that materialize from recorded PUSH intake events, the closeout / step state-management
endpoints (intake, list / read, transition) as pure state transitions, the materialization
of `incident_followup_required` and `runbook_step_required` tasks through the existing
P23-B upsert seam, the dedup / severity / correlation logic, and unit tests -- wired to
the P15 / P17 / P18 / P21 / P22 read paths and the P10 identity-only guard, able to
receive, mirror, close out, and audit an incident, but **not to execute any action, not
to approve any approval, not to set or clear the `incident_active` flag, and not to
deliver any notification**.

This gate is the counterpart to the P24-A-only non-goals (1.3.1): the runtime code,
backend handlers, in-memory closeout / step read model, intake receiver, and lifecycle
skeleton that are forbidden in P24-A are exactly the non-executing skeleton P24-B may
begin to implement. The all-P24 non-goals (1.3.2) bind P24-B equally; nothing in this
section relaxes them, and any P24-B migration (if a persisted store is proposed) requires
separate explicit approval in the P24-B contract review.

P24-B (and all of P24 before a separately approved delivery / persistence phase) **must
not**:

- execute any P22 action, approve any approval, set or clear the P17 `incident_active`
  flag, or mutate any registry field;
- deliver any notification (no in-app push, no email, no webhook); notification events
  stay at P23 `delivery_state == recorded`;
- add a real closeout worker, intake poller, drain loop, scheduler, or on-call /
  escalation engine, unless separately and explicitly approved outside this contract;
- add any migration, alembic change, table, or column unless explicitly approved in the
  P24-B contract review (an in-memory / existing-safe read model is preferred);
- implement any frontend (the Incident Closeout / Runbook page / drawer / checklist are a
  later, separately approved slice);
- carry any product business incident / task or tenant business payload;
- rewrite auth / RBAC / session / tenancy;
- delete or truncate audit history on withdraw / expire;
- display or close `source_unknown` as healthy, or `backup_check_warning` as success;
- mark an `action_pointer` step `done` on approval alone, or conflate an
  `approval_pointer` with an `action_pointer`;
- touch product-dev-recovered or any product business path.

**Real notification delivery, a persisted closeout / runbook store, and a real intake
pipeline are reserved for separately approved phases** and must remain behind the
never-leaked list and the identity-only platform-operator guard. P24-B must begin from
this contract and may not change the closeout lifecycle, the runbook step model, the
source boundaries, the materialization rules, the data-model fields, the audit fields,
the API shapes, the RBAC visibility rules, the dedup / severity / correlation rules, or
the never-leaked list without a new contract revision accepted by the CTO.

## 13. Future AI Operator Copilot Note

Any future AI Operator Copilot must operate **through** this closeout substrate and the
P23 task queue, never around them. The boundary:

- The AI may **read** closeouts, runbooks, steps, and the linked P15 / P17 / P22 evidence
  via approved, read-only tools.
- The AI may **propose** a closeout transition (await, close, withdraw) or a step
  transition (in_progress, done with drafted evidence), and may **draft** an observation
  note, but only as a proposal.
- The AI may **apply a transition only after explicit operator confirmation** -- a human
  identity-only platform-operator must own the action. The AI is never the owner of
  record for a `closed` closeout or a `done` `action_pointer` step, and never the
  executor.
- The AI **cannot execute actions, approve approvals, set or clear the flag, auto-close,
  auto-withdraw, or auto-complete steps.** There is no AI path to an executing state, no
  AI self-approval, no AI flag-flip, and no AI break-glass.
- **Every AI action must be audited** as a closeout / step audit event, with the AI
  proposal recorded as redacted metadata and `actor_role` set to the confirming
  operator's role.
- **AI tool calls must be linked** to the closeout, step, correlation, and underlying
  incident / action / approval / execution ids, so every AI proposal is traceable to a
  human-gated action.
- **Real delivery and real execution remain separately gated** behind future phases. The
  closeout substrate records AI-assisted triage; it does not run, deliver, or flag
  anything.

This section names a future boundary only. P24-A implements no AI copilot, grants no AI
closeout / execution / approval / flag power, and adds no AI-specific runtime code.

## 14. Docs-Only and Contract-Only Statement

P24-A is **docs-only and contract-only**. It ships:

- `docs/ai/PLATFORM_PRODUCT_P24_INCIDENT_RUNBOOK_CLOSEOUT_CONTRACT.md` -- this contract.
- `docs/ai/README.md` -- the P24 entry in the Platform Product Track read order.
- `ai-ledger/platform/2026-07-05_p24a_incident_runbook_closeout_contract.md` -- the
  ledger.

There is **no runtime code, no backend, no frontend, no migration, no alembic change, no
table, no test code, and no dependency change** in P24-A. P24-A defines the incident +
runbook closeout contract only; it does not execute, approve, flag, dispatch, queue,
schedule, deliver, migrate, or implement any closeout, runbook, step, task, action,
approval, or storage path. **An incident closeout is a view, not an executor. A runbook
step is a pointer, not an execution. A follow-up task is a record, not a repair.** Real
closeout materialization, the PUSH intake receiver, real notification delivery, and the
frontend are reserved for separately approved future phases. **P24-B is not started.**
