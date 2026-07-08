# P24-A Incident + Runbook Closeout Contract

Date: 2026-07-05
Phase: P24-A (contract-only design for the incident + runbook closeout layer; the
incident closeout lifecycle, the runbook step model, the PUSH source boundary, the
materialization rules for the incident_followup_required and runbook_step_required P23
task types, the data-model plan, the audit / event model, the API plan, the RBAC
visibility boundary, the acceptance criteria, and the counterexamples that bound all
later P24 implementation).
Branch: codex/platform-p24a-incident-runbook-closeout-contract-2026-07-05
Base: origin/platform-dev = cf3464db (P23 operator task / notification queue: P23-A
contract, P23-B non-executing / non-sending backend skeleton, P23-C read-only source
materialization bridge, P23-D frontend console, and P23-E closeout all merged;
P23_OPERATOR_TASK_QUEUE_READY).
Scope: docs / ledger only. No new feature, no backend runtime code, no frontend runtime
code, no migration, no alembic change, no package or lockfile change, no test code.

This phase defines the incident + runbook closeout contract only. It does not implement,
execute, approve, flag, dispatch, queue, schedule, deliver, migrate, or merge anything
into platform-dev. It is an isolated, docs-only branch. P24-B is not started.

## 1. Phase inventory

P24-A - incident + runbook closeout contract (docs-only)
- Source branch: codex/platform-p24a-incident-runbook-closeout-contract-2026-07-05
- Base: origin/platform-dev = cf3464db
- Report path: ai-ledger/platform/2026-07-05_p24a_incident_runbook_closeout_contract.md
  (this file)
- Scope: docs-only contract for the incident + runbook closeout layer on top of P15
  through P23 (incident closeout lifecycle + runbook step model + PUSH source boundary +
  materialization rules for incident_followup_required / runbook_step_required +
  data-model plan + audit / event model + API plan + RBAC visibility + future AI
  Operator Copilot boundary)
- Risk: LOW (docs-only, no runtime code, no migration, no execution, no flag mutation,
  no approval, no notification delivery, no storage switch)
- Status: contract on isolated branch; not merged to platform-dev

## 2. Capability statement

P24-A defines (contract only, no runtime code) the incident + runbook closeout layer
that connects P15 read-only incident triage, the P17 incident_active flag, the P18
incident.flag_set / incident.flag_clear action requests, the P19 / P20 / P21 durable
approval envelope, the P22 governed execution outcomes, and the P23 operator task
queue into one non-executing incident lifecycle. P15 triages an incident read-only; P18
creates the flag-set / flag-clear requests; P19 / P20 / P21 gather and durably store the
approvals; P22 governs execution (and may set / clear the flag); P23 aggregates all of
it into a task queue -- but two of the ten P23 task types
(incident_followup_required, runbook_step_required) were deliberately left as PUSH
intake in P23-C, and the connective tissue that closes an incident out was missing. P24
is that contract. After P24-A is accepted, a future P24-B may implement -- under its
own entry gate -- a NON-EXECUTING, NON-SENDING backend skeleton (an in-memory closeout /
runbook read model, a PUSH intake receiver, lifecycle / step state endpoints as pure
state transitions, materialization of the two P23 task types via the existing P23-B
upsert seam, dedup / severity / correlation logic, and tests); a real persisted
closeout / runbook store, a real intake pipeline, real notification delivery, and the
Incident Closeout / Runbook frontend are each reserved for separately approved phases.
P24-A fixes the boundary for:

- Incident closeout lifecycle: eight states (detected, triaged, flagged_active,
  in_remediation, awaiting_closeout, closed, withdrawn, expired) with allowed / forbidden
  transitions; terminal states accept no exit; `closed` requires owed-task completion and
  (if the flag was set) an observed flag clear through P22 incident.flag_clear; NO
  transition executes a controlled action, approves an approval, sets or clears the
  incident_active flag, or mutates a registry field. The lifecycle mirrors the P17 flag
  (observed_true / observed_false / observed_unknown); it never owns it. The lifecycle is
  a presentation / closeout state machine, entirely separate from the P15 triage
  workflow, the P22 execution-record machine, and the P23 task triage machine.
- Runbook step model: three step kinds (observation = read-only P15 runbook-hint style;
  action_pointer = pointer to a P18 action request resolved through P22 execution;
  approval_pointer = pointer to a P19 / P20 / P21 durable approval) and five step states
  (owed, in_progress, done, not_applicable, blocked); a step is a pointer and a record,
  never an execution; an action_pointer step is done only when the linked P22 execution
  is observed executed (approvals are not execution), an approval_pointer step is done
  only when the linked approval is observed resolved, an observation step is done with a
  redacted evidence note; ordering is presentation, not execution order.
- Source boundary: PUSH intake only (not PULL); the closed set of recorded intake events
  (incident_detected, incident_classified, incident_flag_observed, runbook_step_*,
  closeout_transition); intake is record-only, non-executing, actor from the token not
  the body; P23-C remains the read-only PULL bridge for its four task types; the two
  P24-owned types arrive via intake PUSH.
- Materialization rules: incident_followup_required materializes only for an owed
  follow-up on an active-flagged (incident_active observed true) non-terminal closeout
  (dedup over (incident_followup_required, closeout_id, tenant_id, follow-up variant));
  runbook_step_required materializes per owed / in_progress / blocked step (dedup over
  (runbook_step_required, step_id, closeout_id, tenant_id)); both flow through the P23
  triage machine unchanged; nothing materializes for a closed / withdrawn / expired
  closeout, a terminal step, a detection with no flag and no owed steps, or any product
  business follow-up.
- Data-model plan (planning only): logical platform_incident_closeout (closeout_id,
  state, classification, severity, tenant_id scoped id only, actor_scope, owner_role /
  owner_actor_id, correlation_id, flag_observed mirrored enum, linked_incident_id /
  linked_triage_snapshot_ref / linked_handoff_ref, summary_redacted, reason_redacted,
  source_status, dedup_key_digest, ttl_expires_at, redaction_applied, timestamps),
  logical platform_runbook (runbook_id, closeout_id, template_ref, correlation_id,
  timestamps, redaction_applied), and logical platform_runbook_step (step_id, runbook_id,
  closeout_id, sequence_no, step_kind, step_state, tenant_id, correlation_id,
  linked_action_id / linked_approval_id / linked_execution_id / linked_source_ref,
  evidence_ref, summary_redacted, reason_redacted, source_status, dedup_key_digest,
  timestamps, redaction_applied); indexes, dedup uniques scoped to non-terminal states
  (Postgres partial-unique discipline over active states, not a NULL column),
  source-link indexes, and the relationship to P15 / P17 / P18 / P19 / P20 / P21 / P22
  ids as evidence pointers only. P24-A creates NO table, NO migration, NO ORM model, NO
  enum column.
- Audit / event model (planning only): IncidentCloseoutAuditEvent (event_id, closeout_id,
  state, actor_id / actor_role, tenant_id, transition, previous_state, next_state,
  flag_observed mirrored, reason_redacted, correlation_id, linked ids, redaction_applied,
  sequence_no, created_at) and RunbookStepAuditEvent (event_id, step_id, closeout_id,
  step_kind, step_transition, previous_state, next_state, actor_id / actor_role,
  tenant_id, evidence_redacted, correlation_id, linked ids, redaction_applied,
  sequence_no, created_at); one event per transition / step change; append-only; the P23
  never-leaked list applies in full; flag_observed is always an observation, never a
  write.
- API plan (planning only): POST intake (PUSH, non-executing, actor from token), GET
  closeouts, GET closeout detail, GET runbook, POST closeout transition (rejects if the
  flag is still set, owed tasks still non-terminal, or source still unknown), POST step
  transition (rejects an action_pointer done on approval alone); all behind the P10
  identity-only platform-operator guard; none executes, approves, flags, or mutates.
- Security / RBAC boundary: identity-only platform-operator visibility
  (support_operator, engineering_operator, super_admin) reusing the existing auth / RBAC
  / session transport; no auth rewrite; tenant scope enforced at the read; owner is
  presentation, not authorization; intake actor from the token not the body; runtime
  authorization left to the existing P10 / P18 / P20 / P22 per-action boundary.
- Future AI Operator Copilot boundary: the AI may read closeouts / steps / evidence and
  propose transitions / draft evidence, may apply a transition only after explicit
  operator confirmation, can never execute / approve / flag / auto-close / auto-withdraw /
  auto-complete, every AI action is audited, AI tool calls are linked to the closeout and
  underlying ids, and real delivery / execution / flag change stay separately gated.

## 3. Safety statement

- An incident closeout is a view, not an executor, a runbook step is a pointer, not an
  execution, and a follow-up task is a record, not a repair. No closeout transition or
  step change executes a P22 action, approves a P19 / P20 / P21 approval, sets or clears
  the incident_active flag, bypasses a checker, or mutates a registry field. P24-A
  defines the closeout contract; it performs no execution, no flag mutation, no approval,
  and no delivery.
- The incident_active flag is owned by P17 and changed only by P22 governed execution of
  incident.flag_set / incident.flag_clear. P24 mirrors the observed flag state into the
  closeout lifecycle (flagged_active when observed true; closed / awaiting_closeout
  reflect an observed clear); P24 NEVER sets or clears the flag. A transition into
  flagged_active only records that the flag was observed true; a transition into closed
  only records that the flag was observed false (if it was ever set). The P24 transition
  flips no P17 field.
- No real controlled action execution, no flag mutation, no approval, and no notification
  delivery exists anywhere in P24-A (contract only). The closeout aggregates, mirrors, and
  presents; it never short-circuits a gate that P15 / P17 / P18 / P19 / P20 / P21 / P22 /
  P23 put in place.
- Approvals are not execution: an action_pointer runbook step is done only when the
  linked P22 execution is observed executed, not when its approval alone is granted; an
  approval_pointer step and an action_pointer step are never conflated.
- No tenant business mutation: no order, payment, invoice, customer, inventory, or ledger
  record is read or written by any closeout, runbook, step, or intake event (contract
  forbids it for all future P24 phases; tenant_id is a scoped identifier only, never a
  business payload and never joinable to business tables).
- No product business incident / task: the closeout carries platform operational incidents
  only; an order / payment / invoice / customer / inventory / ledger follow-up is a
  product concern, not a platform P24 incident or task.
- No migration and no storage switch: no migrations, alembic changes, tables, or columns
  are introduced in P24-A. P24-A changes no P15 / P17 / P18 / P19 / P20 / P21 / P22 / P23
  table, field, enum, or migration.
- No auth / RBAC rewrite: P24-A reuses the P10 identity-only platform-operator guard and
  the existing operator roles conceptually; no new auth transport, token, session, or
  role is defined or implemented.
- Redaction-before-record is total by contract: the P10 allowlist applies before any
  record, response, audit, intake, or evidence field; redaction_applied == true is
  required everywhere; the P23 never-leaked list (raw secrets / DSNs / host:port / tokens
  / cookies / auth headers / raw idempotency key / raw request or response body / shell /
  SQL / tenant payload / log lines) binds every closeout, runbook, step, intake event,
  response, and audit event.
- Audit history is never deleted: withdrawn and expired remove a closeout from the active
  view only; the underlying P15 / P17 / P18 / P19 / P20 / P21 / P22 / P23 audit trail is
  retained; the closeout is a view, not the system of record.
- Unknown is never healthy and a warning is never a success: a closeout / step whose
  linked source is source_unknown is never displayed or closed healthy; a
  backup_check_warning (P22-G completed_with_warning) linked into a closeout is never
  displayed or closed as success (P10 / P17 / P22 / P23 rule, carried into P24).
- No tenant data leak across contexts: a closeout scoped to tenant A is never visible to
  an operator in tenant B's context; cross-tenant visibility requires the identity-only
  platform-scope path and is audited.
- No AI agent execution / flag-flip / auto-approval / auto-close: P24-A names a future AI
  Operator Copilot boundary only; it grants no AI the power to execute, approve, set or
  clear the flag, auto-close, auto-withdraw, or auto-complete a closeout or step.

## 4. Verification (docs-only branch, all must pass)

Verified on this branch versus origin/platform-dev = cf3464db:

- git diff --check origin/platform-dev..HEAD : clean (no whitespace errors).
- Commit: branch tip (short SHA recorded in the session report; kept out of this file so
  the ledger stays non-self-referential; no 40-char SHA in this file).
- Changed files exactly equal three docs / ledger files:
  - docs/ai/PLATFORM_PRODUCT_P24_INCIDENT_RUNBOOK_CLOSEOUT_CONTRACT.md (new)
  - docs/ai/README.md (Platform Product Track read order updated; P24 entry + paragraph)
  - ai-ledger/platform/2026-07-05_p24a_incident_runbook_closeout_contract.md (new, this
    file)
- Non-ASCII scan of the three files: 0 hits (pure ASCII; no section sign, box-drawing, em
  dash, middot, smart quotes, or arrows).
- detect-secrets (detect-secrets-hook against the configured secret baseline) on the
  three files: PASS, exit 0, no new secrets. The configured baseline file was not
  modified (working-tree status clean for it). No 40-char SHAs are present in any new
  file.
- Forbidden path audit (changed paths under backend/, frontend/, migrations/, alembic/,
  package or lock files, auth / RBAC / session, payment / billing, tenant business code,
  product-dev-recovered/, .github/, .claude/, or the configured secret baseline): 0 hits.
- npx gitnexus analyze : graph intact; no execution / approval / flag / delivery flow
  affected by a docs-only change.
- GitNexus detect_changes corroborator: the docs-only diff (one contract markdown, one
  README read-order edit, one ledger) touches no code symbols, so the changed-code-symbol
  set and the affected-runtime-flow set are both empty -- the cleanest possible docs-only
  result. (The detect_changes tool is MCP-only; where the MCP stdio server is
  unresponsive in this environment, `git diff --name-only origin/platform-dev..HEAD` is
  the corroborator: only docs/ai/*.md and ai-ledger/platform/*.md paths appear, so zero
  code symbols and zero runtime flows are affected.)
- Working tree clean after commit.

## 5. GitNexus summary

- P24-A is docs-only: a contract markdown doc, a README read-order edit, and a ledger.
  No runtime symbols, no execution-flow impact, no approval-flow impact, no flag-mutation
  impact, no notification-delivery impact.
- The change adds documentation only; no backend, frontend, migration, package, auth,
  payment, tenant, product, intake, or notification-sender path is touched. The node /
  edge / cluster counts reported by `npx gitnexus analyze` are documented as a band (the
  graph is unchanged from base cf3464db because markdown is not a code symbol), not a
  point, to avoid amend loops on the known small analyze-count wobble.

## 6. Forbidden audit summary

P24-A touches none of the following (all verified by the changed-path audit):

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
- No execution path (contract only; a closeout is a view, not an executor; no v0 action,
  no approval, no flag mutation, and no notification delivery is performed in P24-A).
- No tenant mutation path (tenant_id is a scoped identifier only; closeouts target
  platform incidents / runbook steps / follow-ups only).
- No flag-mutation path (the P17 incident_active flag is mirrored as flag_observed, never
  written by P24; flag changes flow through P22 incident.flag_set / incident.flag_clear
  only).
- No intake-receiver path (PUSH intake is planned only; no receiver is wired in P24-A).
- No notification-sender path (a closeout / step change may materialize a P23
  notification EVENT, which is a record; delivery_state stays recorded; no channel is
  wired).

## 7. Open risks / non-goals

The following are intentionally not done in P24-A and are NOT P24-A blockers. They are
deferred to P24-B (and later) under their own entry gates, contract-first:

- Non-executing, non-sending backend skeleton (in-memory closeout / runbook read model,
  PUSH intake receiver, lifecycle / step state endpoints as pure state transitions,
  materialization of the two P23 task types via the existing P23-B upsert seam, dedup /
  severity / correlation logic, tests) -- P24-B only; no execution, no flag mutation, no
  approval, no delivery, no worker, no scheduler.
- Real persisted closeout / runbook store / worker / scheduler / drain loop / intake
  pipeline -- a separately approved future phase; not a hidden execution, flag, or
  delivery path.
- Real notification delivery (in-app push, email, webhook) for closeout events -- a
  separately approved future phase; bound by the never-leaked list and the identity-only
  platform-operator guard.
- Incident Closeout / Runbook frontend (page, drawer, step checklist, badge) -- a
  separately approved future slice.
- Materialization from live prior-phase event streams / webhooks / polling / a real
  incident detector -- P24-B (or later) decides the source-of-truth intake path; P24-A
  only plans the PUSH intake contract and the logical read model.
- Lifting any P24 exclusion (product business incident / task, tenant payload, synthetic
  execution, flag mutation, auto-close / auto-approval, cross-tenant broadcast, channel
  delivery) -- a new contract revision accepted by the CTO and a new phase.
- AI Operator Copilot implementation (named as a future boundary only; no AI execution /
  approval / flag / auto-close power, no AI-specific runtime code in P24-A).
- Emergency override / auto-close / auto-withdraw (forbidden by default; any override
  requires a separately approved future contract).

## 8. P24-B entry gate

P24-B may implement ONLY a non-executing, non-sending backend skeleton: an in-memory (or
existing-safe) closeout / runbook read model that mirrors recorded PUSH intake events,
the closeout / step state-management endpoints (intake, list / read, transition) as pure
state transitions, the materialization of incident_followup_required and
runbook_step_required tasks through the existing P23-B upsert seam, the dedup / severity
/ correlation logic, and unit tests, wired to the P15 / P17 / P18 / P21 / P22 read paths
and the P10 identity-only guard. P24-B must not execute any P22 action, approve any
approval, set or clear the P17 incident_active flag, mutate any registry field, or
deliver any notification (no in-app push, no email, no webhook); must not add a real
closeout worker, intake poller, drain loop, scheduler, or escalation engine unless
separately and explicitly approved; must not add any migration, alembic change, table, or
column unless explicitly approved in the P24-B contract review (an in-memory /
existing-safe read model is preferred); must not implement any frontend; must not carry
any product business incident / task or tenant business payload; must not rewrite auth /
RBAC / session; must not delete or truncate audit history on withdraw / expire; must not
display or close source_unknown as healthy or backup_check_warning as success; must not
mark an action_pointer step done on approval alone; and must not touch
product-dev-recovered. Real notification delivery, a persisted closeout / runbook store,
and a real intake pipeline are reserved for separately approved phases and must stay
behind the never-leaked list and the identity-only platform-operator guard. P24-B must
begin from this contract and may not change the closeout lifecycle, the runbook step
model, the source boundaries, the materialization rules, the data-model fields, the
audit fields, the API shapes, the RBAC visibility rules, the dedup / severity /
correlation rules, or the never-leaked list without a new contract revision accepted by
the CTO.

## 9. Final verdict

P24-A_CONTRACT_READY (docs-only, isolated branch, not merged to platform-dev).

P24-A defines the incident + runbook closeout contract only. There is no runtime code,
no migration, no execution, no flag mutation, no approval, no notification delivery, no
tenant mutation, no product business incident / task, no tenant data leak across
contexts, no auth / RBAC rewrite, no frontend, no backend, no AI agent execution /
flag-flip / auto-approval / auto-close, no deletion of audit history on withdraw /
expire, no source_unknown displayed or closed healthy, no backup_check_warning displayed
or closed as success, and no change to the configured secret baseline. P24-B is not
started. An incident closeout is a view, not an executor, a runbook step is a pointer,
not an execution, and a follow-up task is a record, not a repair.
