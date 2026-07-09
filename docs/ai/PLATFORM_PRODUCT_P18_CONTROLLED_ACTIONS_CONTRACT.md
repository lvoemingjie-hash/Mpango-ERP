# Platform Product P18 -- Controlled Platform Actions Contract

**Status:** Contract only (P18-A). No runtime code, no backend handlers, no frontend
UI, no migrations, no tests, and no dependency changes. Accepted by the CTO before any
P18-B implementation may begin.
**Phase:** P18-A Controlled Platform Actions Contract
**Date:** 2026-06-23
**Base:** `40fed88` (origin/platform-dev -- P17-B/C registry adapter cockpit)
**Depends on:** P10 (identity-only super_admin guard, PlatformAuditEvent, source-status
vocabulary, redact_metadata allowlist), P11 (Platform Admin Cockpit boundary), P12
(Support Console support-safe subset and diagnostics bundle), P13/P14 (Operations
Observability endpoints plus unavailable_reason / degraded_reason), P15 (Incident
Triage read-only contract), P16 (Worktree Execution Harness), P17 (Platform Registry
and Tenant Lifecycle Contract).
**Author:** Codex (Claude worker)

---

## 1. Goal and Non-Goals

### 1.1 Goal

P17 delivered the platform registry and tenant lifecycle as a **read and contract
only** layer, and explicitly deferred every registry mutation to a future, separately
approved controlled-action phase. P18 is that phase boundary.

P18 defines the **controlled platform actions contract**: the safe, audited,
idempotent, permission-bounded shape for the small set of write and write-request
operations that may, in a later phase, act on the P17 registry and tenant lifecycle.
P18-A fixes four things before any execution code is written:

1. The **action catalog** and the per-action rules (who may request it, what it
   requires, when it is denied, and how it degrades).
2. The **permission matrix** across the four platform roles.
3. The **safety rules** that every controlled action must satisfy.
4. The **audit event contract** that records every request, including denied and
   duplicate requests.

P18-A is **contract only**. It ships **no runtime code**.

### 1.2 In scope (contract layer)

- Define the controlled action catalog with, for every action: action name, read/write
  classification, allowed actor role, required reason, required confirmation,
  idempotency key requirement, preconditions, denied states, audit event requirement,
  and expected degraded behavior.
- Define the permission matrix for identity-only super_admin, support_operator,
  engineering_operator, and the denied tenant-contextual admin.
- Define the safety rules (no impersonation, no tenant business mutation, no raw
  secrets/logs/DSNs/host/port, no action without reason, no action without audit, no
  action without an idempotency key, and no action when the registry source is unknown
  unless the contract explicitly allows a degraded request).
- Define the ControlledActionAuditEvent contract and its result and action_type enums.
- Define the degraded behavior for every action.
- Define acceptance criteria and counterexamples.

### 1.3 Non-goals (explicit, for ALL of P18, not only P18-A)

- No runtime code, no backend handlers, no frontend UI, no migrations, no alembic
  changes, no test code, and no dependency changes.
- No auth / RBAC / session / tenancy / payment / business-data code or rewrite.
- **No direct execution of any controlled action.** P18-A defines the contract only.
  Even P18-B is restricted to a read-model and action-request skeleton and must not
  execute destructive actions unless separately approved.
- No new observability, backup, or provisioning infrastructure. Controlled actions
  reuse P13/P14 signals, the existing backup system, and the P17 registry as their
  sources of truth.
- No product business code, no touch of product-dev-recovered, no push to any product
  branch, and no merge or push of platform-dev.

## 2. Relationship to Prior Phases (P10 through P17)

P18 introduces **no new auth, RBAC, session, observability, or data-source concepts**.
It composes the existing platform product track and is the controlled-action layer that
P17 explicitly left unimplemented.

| Prior phase | What P18 consumes / extends |
|---|---|
| **P10** identity-only guard, PlatformAuditEvent, source-status vocabulary, redact_metadata allowlist | Every controlled action runs behind the P10 identity-only super_admin guard. ControlledActionAuditEvent is a typed specialization of PlatformAuditEvent. The P10 redact_metadata allowlist applies to every action reason and metadata_redacted payload. The source-status rules (unknown is never healthy, null is never zero) govern degraded behavior. |
| **P11** Cockpit | The Cockpit may, in a future approved phase, render action-request controls. P18-A adds no cockpit controls and no mutation buttons. |
| **P12** Support Console | The support_operator controlled action (support_mode on/off) flows through the support-safe path. No raw failure detail, no raw payload, and no tenant business data may appear in any support-side action request or response. |
| **P13 / P14** Operations Observability | Controlled actions carry unavailable_reason and degraded_reason from P13/P14 when a source is down. P18 creates no new observability infrastructure. |
| **P15** Incident Triage | incident.flag_set and incident.flag_clear are the write complement to the P15 read-only triage snapshot. Setting incident_active links the action to the P15 IncidentTriageSnapshot context; P18 itself remains contract only. |
| **P16** Worktree Execution Harness | Any future execution of a destructive controlled action must run through the P16 governed harness. P18-A defines the request and audit shape; it does not invoke the harness. |
| **P17** Registry and Tenant Lifecycle | P18 is the controlled-action layer that P17 deferred. Every P18 action targets a P17 PlatformTenantRegistry field or lifecycle transition. ControlledActionAuditEvent specializes the P17 TenantRegistryAuditEvent. The P17 lifecycle state machine (section 5 of the P17 contract) is the authority for lifecycle.transition, tenant.pause, and tenant.resume. |

## 3. Controlled Action Catalog

Every controlled action is a single, named, audited operation against one tenant (or a
global flag for incident.flag_set/clear when tenant_id is null). The catalog is fixed
and closed: an action not listed here is not a controlled action and has no contract.

For every action the following ten fields are defined below: action name, read/write
classification, allowed actor role, required reason, required confirmation, idempotency
key requirement, preconditions, denied states, audit event required, and expected
degraded behavior.

Notation:

- **Classification:** read (recompute or refresh a cached status; no tenant state
  change), write (mutate a P17 registry field or lifecycle state), or write-request
  (trigger non-destructive work in platform infrastructure without mutating tenant
  business data).
- **Confirmation:** a typed, explicit confirmation token supplied by the actor at
  request time. Required for every write and write-request action; not required for
  pure reads.
- **Idempotency key:** client-supplied, unique within (actor_id, tenant_id,
  action_type) for the dedup window. A repeat key with an identical request returns the
  prior result and records result = duplicate; a repeat key with a different request is
  rejected and recorded as result = denied (idempotency conflict).
- **Degraded:** behavior when the P17 registry source for the affected field is
  unavailable or unknown.

### 3.0 Master summary

| Action type | Classification | Allowed actor | Confirmation |
|---|---|---|---|
| support_mode.on | write | super_admin; support_operator | yes |
| support_mode.off | write | super_admin; support_operator | yes |
| tenant.pause | write | super_admin | yes |
| tenant.resume | write | super_admin | yes |
| incident.flag_set | write | super_admin | yes |
| incident.flag_clear | write | super_admin | yes |
| provisioning.recheck | read | super_admin; engineering_operator | no |
| backup.check | read | super_admin; engineering_operator | no |
| backup.restore_test_request | write-request | super_admin | yes |
| lifecycle.transition | write | super_admin | yes |

### 3.1 support_mode.on

- **Action name / action_type:** `support_mode.on`
- **Read/write classification:** write (sets P17 TenantOperationalFlags.support_mode_active to true)
- **Allowed actor role:** super_admin (identity-only) or support_operator
- **Required reason:** yes (non-empty, redacted via the P10 allowlist before audit)
- **Required confirmation:** yes
- **Idempotency key requirement:** required
- **Preconditions:** tenant exists; tenant is not archived; registry source for operational flags is known
- **Denied states:** archived, unknown
- **Audit event required:** yes (result recorded; denied requests are audited too)
- **Expected degraded behavior:** denied with reason registry_source_unknown when the operational-flags source is unavailable; no silent flag change

### 3.2 support_mode.off

- **Action name / action_type:** `support_mode.off`
- **Read/write classification:** write (clears P17 TenantOperationalFlags.support_mode_active to false)
- **Allowed actor role:** super_admin (identity-only) or support_operator
- **Required reason:** yes
- **Required confirmation:** yes
- **Idempotency key requirement:** required
- **Preconditions:** tenant exists; tenant is not archived; registry source for operational flags is known; completing when already false is no-op-safe and records result = completed with no state change
- **Denied states:** archived, unknown
- **Audit event required:** yes
- **Expected degraded behavior:** denied with reason registry_source_unknown when the operational-flags source is unavailable; no silent flag change

### 3.3 tenant.pause

- **Action name / action_type:** `tenant.pause`
- **Read/write classification:** write (lifecycle transition to paused; implies login_paused and writes_paused per P17 semantics)
- **Allowed actor role:** super_admin (identity-only)
- **Required reason:** yes
- **Required confirmation:** yes
- **Idempotency key requirement:** required
- **Preconditions:** current lifecycle state is active or under_review
- **Denied states:** paused, suspended, archived, failed_provisioning, draft, provisioning, unknown
- **Audit event required:** yes
- **Expected degraded behavior:** denied with reason registry_source_unknown when the lifecycle source is unavailable

### 3.4 tenant.resume

- **Action name / action_type:** `tenant.resume`
- **Read/write classification:** write (lifecycle transition out of paused or suspended toward active)
- **Allowed actor role:** super_admin (identity-only)
- **Required reason:** yes
- **Required confirmation:** yes
- **Idempotency key requirement:** required
- **Preconditions:** current lifecycle state is paused or suspended
- **Denied states:** active, under_review, archived, failed_provisioning, draft, provisioning, unknown
- **Audit event required:** yes
- **Expected degraded behavior:** denied with reason registry_source_unknown when the lifecycle source is unavailable

### 3.5 incident.flag_set

- **Action name / action_type:** `incident.flag_set`
- **Read/write classification:** write (sets P17 TenantOperationalFlags.incident_active to true)
- **Allowed actor role:** super_admin (identity-only)
- **Required reason:** yes
- **Required confirmation:** yes
- **Idempotency key requirement:** required
- **Preconditions:** tenant exists (or tenant_id is null for a platform-wide incident); registry operational-flags source is known
- **Denied states:** archived (per-tenant), unknown
- **Audit event required:** yes (links to the P15 IncidentTriageSnapshot when one exists)
- **Expected degraded behavior:** denied with reason registry_source_unknown when the operational-flags source is unavailable

### 3.6 incident.flag_clear

- **Action name / action_type:** `incident.flag_clear`
- **Read/write classification:** write (clears P17 TenantOperationalFlags.incident_active to false)
- **Allowed actor role:** super_admin (identity-only)
- **Required reason:** yes (must reference the resolution)
- **Required confirmation:** yes (stronger: requires an explicit resolve acknowledgement)
- **Idempotency key requirement:** required
- **Preconditions:** incident_active is currently true; if a P15 IncidentTriageSnapshot exists, it must be in a resolvable state
- **Denied states:** unknown
- **Audit event required:** yes
- **Expected degraded behavior:** denied with reason registry_source_unknown when the operational-flags source is unavailable

### 3.7 provisioning.recheck

- **Action name / action_type:** `provisioning.recheck`
- **Read/write classification:** read (recompute and refresh cached TenantProvisioningStatus; no tenant state change)
- **Allowed actor role:** super_admin (identity-only) or engineering_operator
- **Required reason:** yes
- **Required confirmation:** no
- **Idempotency key requirement:** required
- **Preconditions:** tenant exists
- **Denied states:** none beyond tenant-contextual denial (the read is allowed even in a degraded source state)
- **Audit event required:** yes
- **Expected degraded behavior:** **degraded request explicitly allowed.** When the provisioning source is unavailable, the action returns result = degraded with degraded_reason and changes no state. This is one of only two actions where a degraded request is permitted.

### 3.8 backup.check

- **Action name / action_type:** `backup.check`
- **Read/write classification:** read (refresh cached TenantBackupStatus; no tenant state change)
- **Allowed actor role:** super_admin (identity-only) or engineering_operator
- **Required reason:** yes
- **Required confirmation:** no
- **Idempotency key requirement:** required
- **Preconditions:** tenant exists
- **Denied states:** none beyond tenant-contextual denial (the read is allowed even in a degraded source state)
- **Audit event required:** yes
- **Expected degraded behavior:** **degraded request explicitly allowed.** When the backup system is unavailable, the action returns result = degraded with degraded_reason and changes no state.

### 3.9 backup.restore_test_request

- **Action name / action_type:** `backup.restore_test_request`
- **Read/write classification:** write-request (trigger a restore test against a backup snapshot in an isolated environment; does not mutate tenant business data)
- **Allowed actor role:** super_admin (identity-only)
- **Required reason:** yes
- **Required confirmation:** yes
- **Idempotency key requirement:** required
- **Preconditions:** tenant exists; a usable backup snapshot exists (backup_source_status available and last_backup_status not failed or missing)
- **Denied states:** unknown; denied when no usable snapshot exists
- **Audit event required:** yes
- **Expected degraded behavior:** denied with reason backup_source_unknown when the backup system is unavailable (a restore test cannot run against an unreadable source). No degraded execution is permitted.

### 3.10 lifecycle.transition

- **Action name / action_type:** `lifecycle.transition`
- **Read/write classification:** write (a generic lifecycle transition request validated against the P17 state machine)
- **Allowed actor role:** super_admin (identity-only)
- **Required reason:** yes
- **Required confirmation:** yes
- **Idempotency key requirement:** required
- **Preconditions:** the requested transition is permitted by the P17 state machine (section 5 of the P17 contract); previous_state and requested_state are both known
- **Denied states:** any transition not permitted by the P17 state machine; unknown previous_state; archived as a source state
- **Audit event required:** yes (records previous_state and requested_state)
- **Expected degraded behavior:** denied with reason registry_source_unknown when the lifecycle source is unavailable

## 4. Permission Matrix

`yes` = may request the action; `no` = denied; `n/a` = not applicable.
tenant-contextual admin is denied on every action.

| Capability | super_admin (identity-only) | support_operator | engineering_operator | tenant-contextual admin |
|---|---|---|---|---|
| support_mode.on / off | yes | yes | no | no |
| tenant.pause / resume | yes | no | no | no |
| incident.flag_set / clear | yes | no | no | no |
| provisioning.recheck | yes | no | yes | no |
| backup.check | yes | no | yes | no |
| backup.restore_test_request | yes | no | no | no |
| lifecycle.transition | yes | no | no | no |
| Submit a read or write-request without executing it (P18-B skeleton) | yes | support-safe reads only | diagnostic reads only | no |
| View controlled-action audit events | yes | own support events only | operational events only | no |

Explicit rules (required by the contract):

1. **tenant-contextual admin is denied on every controlled action.** A tenant-scoped
   actor must never change platform registry state, even for its own tenant. The
   platform registry and its mutations are cross-tenant and identity-only.
2. **A super_admin who has selected a tenant context is treated as tenant-contextual
   and is denied** (identity-only enforcement, identical to P10/P13/P15/P17).
3. **support_operator may toggle support_mode only.** Support cannot pause or resume a
   tenant, set or clear incident flags, request provisioning or backup checks, request
   restore tests, or drive lifecycle transitions.
4. **engineering_operator may request the two read actions only** (provisioning.recheck
   and backup.check). Engineering cannot mutate any registry field or lifecycle state
   and cannot request a restore test.
5. **Only super_admin may perform every action.** Lifecycle transitions, incident
   flags, tenant pause/resume, and restore-test requests are super_admin only.
6. **No role may execute a destructive action in P18-A.** P18-A is contract only.
   Execution is reserved for a separately approved phase and must run through the P16
   governed harness.

## 5. Safety Rules

Every controlled action, in every phase that implements this contract, must satisfy all
of the following. A violation rejects the action and records a result = denied audit
event.

1. **No impersonation.** An action is recorded under the real, authenticated
   identity-only actor. No actor may act as another user, as a tenant admin, or as a
   tenant-scoped identity. There is no act-as, on-behalf-of, or sudo path for
   controlled actions.
2. **No tenant business mutation.** A controlled action changes P17 registry fields or
   lifecycle state only. It must never read, write, create, update, or delete tenant
   business records (orders, payments, invoices, customers, inventory, ledgers).
3. **No raw secrets, logs, DSNs, host, or port.** The reason field and the
   metadata_redacted payload are passed through the P10 redact_metadata allowlist
   before audit. No credential, secret, DSN, connection string, hostname, port, stack
   trace, raw exception, or raw log line may appear in any action request, response, or
   audit event.
4. **No action without a reason.** Every request carries a non-empty reason. A request
   with an empty or missing reason is rejected and audited as denied.
5. **No action without an audit event.** Every request, including denied, duplicate,
   degraded, and failed requests, emits exactly one ControlledActionAuditEvent. There
   is no unaudited action and no unaudited denial.
6. **No action without an idempotency key.** Every request carries a client-supplied
   idempotency key. A request without one is rejected and audited as denied. A repeat
   key with an identical request returns the prior result (duplicate); a repeat key
   with a different request is rejected (idempotency conflict).
7. **No action when the registry source is unknown, unless the contract explicitly
   allows a degraded request.** A write action against an unknown source is denied.
   Only provisioning.recheck and backup.check (the two read actions) explicitly allow a
   degraded request, which returns result = degraded and changes no state.

Derived hard rules (consequences of the above):

- No action may proceed without the identity-only super_admin guard (or the narrowed
  support_operator / engineering_operator scope for the two delegated actions).
- No controlled action may run outside the audit boundary; an implementation that can
  apply a state change without emitting an audit event is a contract violation.
- No controlled action may fabricate a passing state when its source is down (unknown
  is never active or healthy).

## 6. Audit Event Contract

Every controlled action emits exactly one ControlledActionAuditEvent. It is a typed
specialization of the P10 PlatformAuditEvent and of the P17 TenantRegistryAuditEvent.
It is append-only; two events never share an action_id. Denied, duplicate, degraded,
and failed requests are audited with the same shape as completed requests.

```text
ControlledActionAuditEvent {
  action_id        : uuid      -- required
  actor_id         : string    -- nullable
  actor_role       : enum      -- nullable
  tenant_id        : uuid      -- nullable
  action_type      : enum      -- required
  requested_state  : enum      -- nullable
  previous_state   : enum      -- nullable
  reason           : string    -- required (redacted via P10 allowlist)
  idempotency_key  : string    -- required
  correlation_id   : string    -- nullable
  result           : enum      -- required
  metadata_redacted: object    -- nullable
  created_at       : timestamp -- required
}
```

| Field | Req/Null | Source zone | When unavailable | Cockpit | Operator visibility | Support bundle |
|---|---|---|---|---|---|---|
| action_id | required | audit metadata | always generated (UUID v4/v7) | yes | support-no; eng-yes | no |
| actor_id | nullable | platform auth context (deferred) | null until platform auth exists | yes | support-no; eng-yes | no |
| actor_role | nullable | platform auth context (deferred) | null until platform auth exists | yes | support-no; eng-yes | no |
| tenant_id | nullable | public platform metadata | null for platform-wide (global) actions such as incident.flag_set without a tenant | yes | support-no; eng-yes | summary-only |
| action_type | required | audit metadata | always required | yes | support-no; eng-yes | summary-only |
| requested_state | nullable | manual/admin input | null for actions with no target state (for example backup.check) | yes | support-no; eng-yes | summary-only |
| previous_state | nullable | public platform metadata | null before the first transition or for non-transition actions | yes | support-no; eng-yes | summary-only |
| reason | required | manual/admin input (redacted) | always required on every request, including denied and duplicate | yes | support-no; eng-yes | summary-only |
| idempotency_key | required | manual/admin input (client-supplied) | always required | yes | support-no; eng-yes | no |
| correlation_id | nullable | runtime telemetry | null if not yet correlated | yes | support-no; eng-yes | no |
| result | required | audit metadata | always required | yes | support-no; eng-yes | summary-only |
| metadata_redacted | nullable | audit metadata (redacted) | null if none; never a raw sensitive payload | yes | support-no; eng-yes | summary-only |
| created_at | required | audit metadata | always required (UTC ISO-8601) | yes | support-no; eng-yes | summary-only |

action_type enum: `support_mode.on` | `support_mode.off` | `tenant.pause` |
`tenant.resume` | `incident.flag_set` | `incident.flag_clear` | `provisioning.recheck`
| `backup.check` | `backup.restore_test_request` | `lifecycle.transition`. These map to
the P17 registry_action families `flag_change`, `lifecycle_transition`,
`provisioning_recheck`, and `backup_trigger`.

result enum:

- `completed` -- the action was applied and the requested state change landed.
- `denied` -- the request was rejected (permission, precondition, denied-state,
  idempotency conflict, or unknown source for a write).
- `degraded` -- a read action took the degraded path because its source was
  unavailable; no state changed.
- `failed` -- the request was accepted but execution errored; no state landed.
- `duplicate` -- the idempotency key was already seen with an identical request; the
  prior result is returned and no new state change occurs.

The reason and metadata_redacted fields are redacted via the P10 redact_metadata
allowlist before the event is written. No credential, DSN, host, port, connection
string, stack trace, raw exception, or raw log line may appear in any field.

## 7. Acceptance Criteria

A future phase that implements this contract is accepted only when all of the
following hold:

1. **Every controlled action is audited.** Each request, including denied, duplicate,
   degraded, and failed, emits exactly one ControlledActionAuditEvent with a unique
   action_id.
2. **No action without a reason.** A request with an empty or missing reason is
   rejected and recorded as result = denied.
3. **No action without an idempotency key.** A request without a key is rejected and
   recorded as denied; a repeat key with an identical request returns the prior result
   (duplicate) with no new state change.
4. **A repeat idempotency key with a different request is rejected** as an idempotency
   conflict and recorded as denied.
5. **tenant-contextual admin is denied on every action** (401/403) and the denial is
   audited.
6. **A super_admin with a selected tenant context is denied** (identity-only
   enforcement) and the denial is audited.
7. **support_operator may toggle support_mode only.** Any attempt by support_operator
   to perform tenant.pause/resume, incident flag set/clear, provisioning.recheck,
   backup.check, backup.restore_test_request, or lifecycle.transition is denied and
   audited.
8. **engineering_operator may run provisioning.recheck and backup.check only.** Any
   attempt by engineering_operator to perform a write or write-request action is denied
   and audited.
9. **Write actions against an unknown registry source are denied** with reason
   registry_source_unknown and audited; no silent state change occurs.
10. **provisioning.recheck and backup.check may take the degraded path.** When their
    source is unavailable they return result = degraded with degraded_reason and change
    no state.
11. **backup.restore_test_request is denied when the backup source is unavailable or no
    usable snapshot exists.** No degraded restore-test execution is permitted.
12. **tenant.pause is rejected from a non-pausable state** (paused, suspended,
    archived, failed_provisioning, draft, provisioning, unknown) and recorded as
    denied; tenant.resume is rejected from a non-resumable state and recorded as
    denied.
13. **lifecycle.transition obeys the P17 state machine.** A transition not permitted by
    the P17 state machine is rejected and recorded as denied; unknown is never an
    automatic source of a transition to active.
14. **No raw secrets, logs, DSNs, host, or port** appear in any reason,
    metadata_redacted, or other audit field (content scan against the P10 allowlist).
15. **No tenant business mutation.** A controlled action changes P17 registry fields or
    lifecycle state only; no order, payment, invoice, customer, inventory, or ledger
    record is read or written by any controlled action.
16. **No impersonation.** Every action is recorded under the real identity-only actor;
    there is no act-as, on-behalf-of, or sudo path.
17. **No runtime code, migrations, frontend, tests, or dependency changes** ship in
    P18-A; P18-A is docs and ledger only.

## 8. Counterexamples (must fail or be rejected)

1. **C1 -- tenant-contextual admin performing any controlled action.** Any
   tenant-scoped identity successfully pausing, resuming, toggling support_mode, or
   setting an incident flag -- rejected (must 401/403) and audited as denied.
2. **C2 -- a controlled action without a reason.** A request with an empty or missing
   reason that proceeds -- rejected and audited as denied.
3. **C3 -- a controlled action without an idempotency key.** A request with no
   idempotency key that proceeds -- rejected and audited as denied.
4. **C4 -- a duplicate idempotency key with a different request that proceeds.** A
   second request reusing a key with different parameters that applies a second state
   change -- rejected and audited as denied (idempotency conflict).
5. **C5 -- an unaudited action.** A state change that lands without a
   ControlledActionAuditEvent -- rejected (contract violation).
6. **C6 -- support_operator pausing a tenant.** A support_operator successfully running
   tenant.pause -- rejected and audited as denied.
7. **C7 -- engineering_operator clearing an incident flag.** An engineering_operator
   successfully running incident.flag_clear -- rejected and audited as denied.
8. **C8 -- a write action against an unknown source that proceeds.** tenant.pause or
   incident.flag_set applying a state change while the registry source is unknown --
   rejected and audited as denied.
9. **C9 -- provisioning.recheck fabricating a passing status when the source is down.**
   provisioning.recheck returning completed with a healthy status while the
   provisioning source is unavailable -- rejected; it must return degraded with a
   reason.
10. **C10 -- backup.restore_test_request running against an unreadable source.** A
    restore-test request that proceeds while the backup system is unavailable --
    rejected and audited as denied.
11. **C11 -- a lifecycle transition not permitted by the P17 state machine.** A
    transition from archived to active, or from unknown to active, that proceeds --
    rejected and audited as denied.
12. **C12 -- a raw secret in an audit field.** A reason or metadata_redacted value that
    contains a credential, DSN, host, port, connection string, stack trace, or raw
    exception -- rejected (redaction allowlist violation).
13. **C13 -- a controlled action mutating tenant business data.** An action that reads
    or writes an order, payment, invoice, customer, inventory, or ledger record --
    rejected (boundary violation).
14. **C14 -- an impersonated action.** A request recorded under an identity that is not
    the real authenticated identity-only actor, or any act-as / on-behalf-of / sudo
    path -- rejected.
15. **C15 -- a controlled action executing in P18-A.** Any backend handler, frontend
    control, migration, alembic change, test, or dependency change added in P18-A --
    rejected; P18-A is docs and ledger only.
16. **C16 -- a new action added outside the catalog.** An action type not in the
    action_type enum that is accepted as a controlled action -- rejected; the catalog
    is closed.

## 9. P18-B Entry Gate (future)

A future P18-B is permitted to implement **only a read-model and action-request
skeleton**: the action catalog and audit event contract defined here, wired to the P17
registry read model and the P10 identity-only guard, able to receive, validate, deny,
deduplicate, and audit a request, but **not to execute destructive actions**.

P18-B (and all of P18) **must not**:

- Execute any destructive action (tenant.pause/resume that lands, incident flag change
  that lands, lifecycle.transition that lands, backup.restore_test_request that runs)
  unless separately approved outside this contract.
- Add any migration or alembic change unless explicitly approved in the P18-B contract
  review.
- Rewrite auth, RBAC, session, or tenancy.
- Add any product business code or touch product-dev-recovered.
- Implement impersonation, act-as, on-behalf-of, or sudo.
- Add cockpit mutation controls or write endpoints beyond the action-request skeleton.
- Bypass the audit boundary for any request, including denied and duplicate requests.

P18-B must begin from this contract and may not change the action catalog, the
permission matrix, the safety rules, or the audit event fields without a new contract
revision accepted by the CTO.

## 10. Docs-Only and Contract-Only Statement

P18-A is **docs-only and contract-only**. It ships:

- `docs/ai/PLATFORM_PRODUCT_P18_CONTROLLED_ACTIONS_CONTRACT.md` -- this contract.
- `docs/ai/README.md` -- the P18 entry in the Platform Product Track read order.
- `ai-ledger/platform/2026-06-23_p18a_controlled_actions_contract.md` -- the ledger.

There is **no runtime code, no backend, no frontend, no migration, no alembic change,
no test code, and no dependency change** in P18-A. P18-A defines the contract only; it
does not execute, invoke, or implement any controlled action. Execution is reserved for
a separately approved phase and must run through the P16 governed harness.
