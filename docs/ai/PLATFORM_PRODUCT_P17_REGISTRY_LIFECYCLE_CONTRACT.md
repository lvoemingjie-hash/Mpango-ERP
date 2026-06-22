# Platform Product P17 -- Platform Registry & Tenant Lifecycle Contract

**Status:** Contract only (P17-A). No runtime code, no migrations, no frontend, no
backend handlers. Accepted by the CTO before any P17-B implementation may begin.
**Phase:** P17-A Platform Registry & Tenant Lifecycle Contract
**Date:** 2026-06-22
**Base:** `9e46a32` (origin/platform-dev -- P16 worktree execution harness closeout)
**Depends on:** P10 (TenantSummary, TenantHealth, SystemHealth, PlatformAuditEvent,
source-status vocabulary), P11 (Platform Admin Cockpit boundary), P12 (Support
Console diagnostics and bundle), P13/P14 (Operations Observability endpoints plus
`unavailable_reason` / `degraded_reason`), P15 (Incident Triage read-only contract),
P16 (Worktree Execution Harness).
**Author:** Codex (Claude worker)

---

## 1. P17 Goals

P17 defines the **platform-owned registry and tenant lifecycle contract** that
becomes the source of truth for SaaS platform operations: a single, audited,
read-consistent view of the identity, lifecycle state, operational flags,
provisioning status, and backup status of every tenant.

P17-A is **contract only**. It defines the data contracts and the lifecycle and
permission rules that later, separately approved phases will implement. P17-A
ships **no runtime code**.

In scope for P17-A (contract layer):

- Define `PlatformTenantRegistry` and its sub-contracts: `TenantLifecycleState`,
  `TenantOperationalFlags`, `TenantProvisioningStatus`, `TenantBackupStatus`, and
  `TenantRegistryAuditEvent`.
- Pin every field to a source zone with an explicit read behavior when the source
  is unavailable.
- Define the lifecycle state machine and the operational flag set.
- Define the permission matrix for who may read which fields.
- Define acceptance criteria and counterexamples.

Explicitly **out of scope** for ALL of P17 (not only P17-A):

- No runtime code, no backend handlers, no frontend UI, no migrations, no alembic
  changes.
- No auth / RBAC / session / tenancy / payment / business-data code.
- **No mutation of registry fields in P17.** P17 is read and contract only. Only
  future, separately approved controlled-action phases may mutate registry fields
  (lifecycle transitions, flag changes, provisioning re-runs, backup triggers).
- No direct push to `platform-dev` and no push to any product branch.

## 2. Relationship to Prior Phases

P17 consumes and extends the platform product track. It introduces **no new auth,
RBAC, session, observability, or data-source concepts**; it composes existing ones
and tightens the lifecycle vocabulary that earlier phases left partial.

| Prior phase | What P17 consumes / extends |
|---|---|
| **P10** TenantSummary / TenantHealth / SystemHealth / PlatformAuditEvent | `PlatformTenantRegistry` supersedes the partial `status` enum on `TenantSummary` with the full `TenantLifecycleState`. The `support_mode_active` boolean on `TenantSummary` becomes one bit inside `TenantOperationalFlags`. P17 reuses the P10 source-status vocabulary (`available_now`, `proposed_public_metadata`, `tenant_aggregate_required`, `telemetry_required`, `manual_or_unknown`, `deferred`) and the cross-contract rules: UUID v4/v7, UTC ISO-8601, `unknown != healthy`, and `null != zero`. `TenantRegistryAuditEvent` is a typed specialization of `PlatformAuditEvent`. |
| **P11** Cockpit | The Cockpit may **render** registry fields read-only, but P17 adds **no cockpit mutation controls**. Pause, resume, suspend, and re-provision buttons are explicitly absent in P17 and are deferred to future controlled-action phases. |
| **P12** Support Console | Support operators read a **support-safe subset** of registry fields: lifecycle state, the support-mode flag, and support-safe provisioning and backup summaries. Raw backup failure details and raw provisioning failure reasons are excluded from the support bundle; only redacted summaries are support-safe. |
| **P13 / P14** Operations Observability | Operational flags (`incident_active`, `writes_paused`, `login_paused`) and provisioning diagnostics (`schema_status`) are sourced from P13/P14 runtime signals and DB metadata, carrying forward `unavailable_reason` and `degraded_reason`. P17 creates no new observability infrastructure. |
| **P15** Incident Triage | When `incident_active` or `under_review` is set, the P15 `IncidentTriageSnapshot` may reference the registry lifecycle state for context. P17 supplies the lifecycle context that P15 triage reads; P17 itself remains read and contract only. |
| **P16** Worktree Execution Harness | Provisioning re-runs and future controlled actions will execute through the P16 harness. P17-A defines the contracts and the audit-event shape that those future runs will populate; P17-A does not invoke the harness. |

## 3. Personas / Roles (reused from the P10 permission matrix)

| Role | Registry access in P17 | Notes |
|---|---|---|
| **super_admin** (identity-only, global) | Full read of every registry contract. | The only role that may read the full registry including engineering diagnostics. Identity-only rule: a super admin who has selected a tenant context is denied, exactly as in P10/P13/P15. |
| **support_operator** | **Support-safe subset only**: lifecycle state, the support-mode flag, and support-safe provisioning and backup summaries. Raw failure details are excluded. | Strictly narrower than super_admin. Entitlement is enforced by existing P10/P12 guards. |
| **engineering_operator** | Read of operational flags, provisioning diagnostics, and backup diagnostics. | Read-only diagnostics for root-cause work. No mutation. |
| **tenant-contextual admin** | **DENIED.** Cannot access the platform registry at all. | Non-negotiable boundary, identical to P10/P13/P15. A tenant-scoped actor must never read cross-tenant platform registry data. |

P17 adds **no new roles** and **no new auth / RBAC / session concepts**. Role
enforcement is deferred to the existing P10 guard and permission matrix.

---

## 4. Data Contracts

All contracts are `extra="forbid"` on input. Nullable totals follow P10/P13/P14
source-status semantics: a field is `null` (or its documented fallback) when its
source is unavailable, and the reason is carried in a sibling reason field.
**`unknown` is never equivalent to `healthy` or `active`, and `null` is never
equivalent to `0`.** These contracts are defined here only; no runtime code exists
in P17-A.

### Visibility notation (used in every field table)

- **Req/Null** -- `required` (always present, uses a documented fallback when the
  source is down) or `nullable` (becomes `null` when the source is down).
- **Source zone** -- one of: `public platform metadata`, `tenant schema aggregate`,
  `runtime telemetry`, `backup system`, `manual/admin input`, `unknown/deferred`.
- **When unavailable** -- exact read behavior (fallback value or `null`, plus which
  reason field is set).
- **Cockpit** -- `yes` the field may be rendered in the Platform Admin Cockpit
  (read-only), or `no` it must not.
- **Operator visibility** -- what support_operator and engineering_operator may see:
  `support-yes; eng-yes`, `support-subset; eng-full`, `support-summary; eng-full`,
  `support-no; eng-full`, or `support-no; eng-no` (super_admin only).
- **Support bundle** -- `yes`, `yes (subset)`, `summary-only`, or `no`.

### 4.1 PlatformTenantRegistry

The root read-only registry record for one tenant. It composes the sub-contracts in
4.2 through 4.5.

```text
PlatformTenantRegistry {
  tenant_id              : uuid                     -- required
  tenant_name            : string                   -- nullable
  tenant_schema          : string                   -- nullable
  tier                   : string                   -- nullable
  created_at             : timestamp                -- nullable
  lifecycle_state        : TenantLifecycleState     -- required
  operational_flags      : TenantOperationalFlags   -- required
  provisioning_status    : TenantProvisioningStatus -- nullable
  backup_status          : TenantBackupStatus       -- nullable
  last_registry_update_at: timestamp                -- nullable
  registry_source_status : enum                     -- required
  unavailable_reason     : string                   -- nullable
}
```

| Field | Req/Null | Source zone | When unavailable | Cockpit | Operator visibility | Support bundle |
|---|---|---|---|---|---|---|
| `tenant_id` | required | public platform metadata | the whole record is `unknown` if the registry row is absent | yes | support-yes; eng-yes | yes |
| `tenant_name` | nullable | public platform metadata | `null` if not set | yes | support-yes; eng-yes | yes |
| `tenant_schema` | nullable | public platform metadata | `null` if provisioning metadata absent | yes | support-yes; eng-yes | yes |
| `tier` | nullable | public platform metadata | `null` until a subscription model exists | yes | support-yes; eng-yes | yes |
| `created_at` | nullable | public platform metadata | `null` if creation metadata absent | yes | support-yes; eng-yes | yes |
| `lifecycle_state` | required | public platform metadata (manual/admin input for transitions) | `state = unknown` fallback | yes | support-yes; eng-yes | yes (state only) |
| `operational_flags` | required | runtime telemetry + manual/admin input | object present; bits default `false`; `flags_unavailable_reason` set | yes | support-subset; eng-full | yes (subset) |
| `provisioning_status` | nullable | runtime telemetry / tenant schema aggregate | `null` + `unavailable_reason` if provisioning data absent | yes (summary) | support-summary; eng-full | summary-only |
| `backup_status` | nullable | backup system | `null` + `unavailable_reason` if the backup system is absent | yes (summary) | support-summary; eng-full | summary-only |
| `last_registry_update_at` | nullable | public platform metadata | `null` if never updated | yes | support-yes; eng-yes | yes |
| `registry_source_status` | required | derived | always present (`available` / `unavailable` / `unknown`) | yes | support-yes; eng-yes | yes |
| `unavailable_reason` | nullable | derived | set when any sub-source is unavailable or unknown | yes | support-yes; eng-yes | yes |

### 4.2 TenantLifecycleState

The lifecycle position of one tenant. Every transition is recorded as a
`TenantRegistryAuditEvent` (4.6); there is no transition without an actor, a
reason, and an audit event (see counterexample C5).

```text
TenantLifecycleState {
  state               : enum      -- required
  previous_state      : enum      -- nullable
  entered_at          : timestamp -- nullable
  last_actor_id       : string    -- nullable
  last_actor_role     : enum      -- nullable
  transition_reason   : string    -- nullable (required on every transition)
  last_audit_event_id : uuid      -- nullable
  state_source_status : enum      -- required
}
```

| Field | Req/Null | Source zone | When unavailable | Cockpit | Operator visibility | Support bundle |
|---|---|---|---|---|---|---|
| `state` | required | public platform metadata (manual/admin input for transitions) | `unknown` fallback | yes | support-yes; eng-yes | yes |
| `previous_state` | nullable | public platform metadata | `null` before the first transition | no | support-no; eng-yes | no |
| `entered_at` | nullable | public platform metadata | `null` if the entry time is unknown | yes | support-yes; eng-yes | yes |
| `last_actor_id` | nullable | manual/admin input (deferred until platform auth) | `null` until platform auth exists | no | support-no; eng-yes | no |
| `last_actor_role` | nullable | unknown/deferred | `null` until platform auth exists | no | support-no; eng-yes | no |
| `transition_reason` | nullable | manual/admin input | `null` only before the first transition; **required on every transition** | yes | support-yes; eng-yes | yes |
| `last_audit_event_id` | nullable | derived (audit) | `null` if no audit event exists yet | no | support-no; eng-yes | no |
| `state_source_status` | required | derived | always present (`available` / `unavailable` / `unknown`) | yes | support-yes; eng-yes | yes |

#### Lifecycle state enum

| Value | Meaning |
|---|---|
| `draft` | Tenant exists in the registry but is not yet operational; provisioning has not completed. |
| `provisioning` | Tenant resources (schema, seed, admin user, feature config) are being created. |
| `active` | Tenant is operational and reachable. |
| `under_review` | Tenant is being investigated (P15 triage context) but still operational. |
| `paused` | Tenant is temporarily paused by an operator or a billing event; logins and writes are halted. |
| `suspended` | Platform has suspended the tenant for abuse, policy, or non-payment. |
| `archived` | Tenant has been offboarded; the schema may be retained for audit. |
| `failed_provisioning` | Provisioning did not complete; the tenant is not operational. |
| `unknown` | The state cannot be determined. **Never equivalent to `active` or `healthy`.** |

### 4.3 TenantOperationalFlags

A required set of boolean operational flags. Every flag defaults to `false`. When
runtime telemetry is unavailable, every flag reads `false` and
`flags_unavailable_reason` is set so the operator can tell a real `false` from an
unknown one.

```text
TenantOperationalFlags {
  support_mode_active          : boolean   -- required
  incident_active              : boolean   -- required
  login_paused                 : boolean   -- required
  writes_paused                : boolean   -- required
  billing_hold                 : boolean   -- required
  backup_attention_required    : boolean   -- required
  migration_attention_required : boolean   -- required
  quota_attention_required     : boolean   -- required
  flags_source_status          : enum      -- required
  flags_updated_at             : timestamp -- nullable
  flags_unavailable_reason     : string    -- nullable
}
```

| Field | Req/Null | Source zone | When unavailable | Cockpit | Operator visibility | Support bundle |
|---|---|---|---|---|---|---|
| `support_mode_active` | required | runtime telemetry + manual/admin input | `false` + reason | yes | support-yes; eng-yes | yes |
| `incident_active` | required | runtime telemetry + manual/admin input | `false` + reason | yes | support-yes; eng-yes | yes |
| `login_paused` | required | runtime telemetry + manual/admin input | `false` + reason | yes | support-yes; eng-yes | yes |
| `writes_paused` | required | runtime telemetry + manual/admin input | `false` + reason | yes | support-yes; eng-yes | yes |
| `billing_hold` | required | runtime telemetry + manual/admin input | `false` + reason | yes | support-no; eng-yes | no |
| `backup_attention_required` | required | backup system + runtime telemetry | `false` + reason | yes | support-no; eng-yes | no |
| `migration_attention_required` | required | runtime telemetry + manual/admin input | `false` + reason | yes | support-no; eng-yes | no |
| `quota_attention_required` | required | runtime telemetry + manual/admin input | `false` + reason | yes | support-no; eng-yes | no |
| `flags_source_status` | required | derived | always present | yes | support-yes; eng-yes | yes |
| `flags_updated_at` | nullable | runtime telemetry | `null` if never set | yes | support-yes; eng-yes | yes |
| `flags_unavailable_reason` | nullable | derived | set when telemetry is unavailable | yes | support-yes; eng-yes | yes |

### 4.4 TenantProvisioningStatus

The provisioning state of tenant resources. Diagnostics are sourced from tenant
schema aggregate and runtime telemetry. `failure_reason_redacted` is always
redacted and never contains secrets, credentials, DSNs, or connection strings
(see counterexample C6).

```text
TenantProvisioningStatus {
  schema_status            : enum      -- nullable
  seed_status              : enum      -- nullable
  admin_user_status        : enum      -- nullable
  feature_config_status    : enum      -- nullable
  last_provisioning_check_at: timestamp -- nullable
  failure_reason_redacted  : string    -- nullable
  provisioning_source_status: enum     -- required
}
```

| Field | Req/Null | Source zone | When unavailable | Cockpit | Operator visibility | Support bundle |
|---|---|---|---|---|---|---|
| `schema_status` | nullable | tenant schema aggregate / runtime telemetry | `null` + reason if DB metadata is unavailable | yes (summary) | support-summary; eng-full | summary-only |
| `seed_status` | nullable | tenant schema aggregate | `null` + reason if unavailable | yes (summary) | support-summary; eng-full | summary-only |
| `admin_user_status` | nullable | tenant schema aggregate | `null` + reason if unavailable | yes (summary) | support-summary; eng-full | summary-only |
| `feature_config_status` | nullable | tenant schema aggregate / runtime telemetry | `null` + reason if unavailable | yes (summary) | support-summary; eng-full | summary-only |
| `last_provisioning_check_at` | nullable | runtime telemetry | `null` if never checked | yes | support-yes; eng-yes | yes |
| `failure_reason_redacted` | nullable | runtime telemetry (redacted) | `null` if there is no failure | no | support-no; eng-yes | no |
| `provisioning_source_status` | required | derived | always present | yes | support-yes; eng-yes | yes |

#### Provisioning status enums

`schema_status`: `exists` | `missing` | `unreachable` | `migration_misaligned` |
`unknown` (aligned to the P10 `TenantHealth.schema_status` enum).

`seed_status`: `seeded` | `partial` | `missing` | `unknown`.

`admin_user_status`: `created` | `missing` | `unknown`.

`feature_config_status`: `applied` | `partial` | `missing` | `unknown`.

`failure_reason_redacted` is a short, human-readable, allowlisted reason string
only (for example `schema_create_failed` or `admin_seed_failed`). It must not
contain the raw exception, stack trace, credential, DSN, host, port, or
connection string.

### 4.5 TenantBackupStatus

The backup and restore-test posture of one tenant. Sourced from the backup system.
A `last_backup_status` of `success` is valid only when `last_backup_at` is within
the freshness window; a stale timestamp downgrades the rendered status to `stale`
and must never read as `success` (see counterexample C4). Raw failure details are
never exposed; only `failure_reason_redacted` (see counterexample C2).

```text
TenantBackupStatus {
  last_backup_at        : timestamp -- nullable
  last_backup_status    : enum      -- nullable
  last_restore_test_at  : timestamp -- nullable
  restore_test_status   : enum      -- nullable
  export_available      : boolean   -- nullable
  retention_policy      : string    -- nullable
  failure_reason_redacted: string   -- nullable
  backup_source_status  : enum      -- required
  last_status_check_at  : timestamp -- nullable
}
```

| Field | Req/Null | Source zone | When unavailable | Cockpit | Operator visibility | Support bundle |
|---|---|---|---|---|---|---|
| `last_backup_at` | nullable | backup system | `null` if never backed up | yes (summary) | support-summary; eng-full | summary-only |
| `last_backup_status` | nullable | backup system | `null` + reason if the backup system is unavailable; `stale` if the timestamp is outside the freshness window | yes (summary) | support-summary; eng-full | summary-only |
| `last_restore_test_at` | nullable | backup system | `null` if never tested | yes | support-no; eng-yes | no |
| `restore_test_status` | nullable | backup system | `null` + reason if unavailable | yes | support-no; eng-yes | no |
| `export_available` | nullable | backup system | `null` + reason if unavailable | yes | support-yes; eng-yes | yes |
| `retention_policy` | nullable | backup system (manual/admin configured) | `null` if not configured | yes | support-no; eng-yes | no |
| `failure_reason_redacted` | nullable | backup system (redacted) | `null` if there is no failure | no | support-no; eng-yes | no |
| `backup_source_status` | required | derived | always present | yes | support-yes; eng-yes | yes |
| `last_status_check_at` | nullable | backup system | `null` if never checked | yes | support-yes; eng-yes | yes |

#### Backup status enums

`last_backup_status`: `success` | `partial` | `failed` | `in_progress` | `stale` |
`unknown`. `stale` means the last backup timestamp is outside the configured
freshness window.

`restore_test_status`: `passed` | `failed` | `stale` | `unknown`.

`failure_reason_redacted` is an allowlisted reason string only (for example
`backup_job_timeout` or `restore_checksum_mismatch`); it must not contain paths,
hostnames, credentials, or raw job output.

### 4.6 TenantRegistryAuditEvent

An **append-only** audit event for registry access and (in future phases) registry
mutation. It is a typed specialization of the P10 `PlatformAuditEvent`. In P17
(read and contract only) the only events emitted are reads and denied reads; the
write actions in the enum are reserved for future controlled-action phases and are
listed here so their audit shape is fixed in advance.

```text
TenantRegistryAuditEvent {
  event_id          : uuid      -- required
  actor_id          : string    -- nullable
  actor_role        : enum      -- nullable
  tenant_id         : uuid      -- nullable
  registry_action   : enum      -- required
  from_state        : enum      -- nullable
  to_state          : enum      -- nullable
  reason            : string    -- nullable (required on transitions and flag changes)
  result            : enum      -- required
  metadata_redacted : object    -- nullable
  correlation_id    : string    -- nullable
  created_at        : timestamp -- required
}
```

| Field | Req/Null | Source zone | When unavailable | Cockpit | Operator visibility | Support bundle |
|---|---|---|---|---|---|---|
| `event_id` | required | audit metadata | always generated (UUID v4/v7) | yes | support-no; eng-yes | no |
| `actor_id` | nullable | unknown/deferred | `null` until platform auth exists | yes | support-no; eng-yes | no |
| `actor_role` | nullable | unknown/deferred | `null` until platform auth exists | yes | support-no; eng-yes | no |
| `tenant_id` | nullable | public platform metadata | `null` for global-scope events | yes | support-no; eng-yes | no |
| `registry_action` | required | audit metadata | always required | yes | support-no; eng-yes | summary-only |
| `from_state` / `to_state` | nullable | public platform metadata | `null` for non-transition actions | yes | support-no; eng-yes | summary-only |
| `reason` | nullable | manual/admin input | `null` for actions that need none; **required on transitions and flag changes** | yes | support-no; eng-yes | summary-only |
| `result` | required | audit metadata | always required (`allowed` / `denied` / `failed` / `completed`) | yes | support-no; eng-yes | summary-only |
| `metadata_redacted` | nullable | audit metadata | `null` if none; never a raw sensitive payload | yes | support-no; eng-yes | summary-only |
| `correlation_id` | nullable | runtime telemetry | `null` if not yet correlated | yes | support-no; eng-yes | no |
| `created_at` | required | audit metadata | always required (UTC ISO-8601) | yes | support-no; eng-yes | summary-only |

`registry_action` enum: `registry_view` | `registry_view_denied` |
`lifecycle_transition` | `flag_change` | `provisioning_recheck` | `backup_trigger`.
In P17 only `registry_view` and `registry_view_denied` are emitted; the rest are
reserved for future controlled-action phases.

---

## 5. Lifecycle State Machine

The transitions below are **defined by P17** but **not executed by P17**. Only
future, separately approved controlled-action phases may perform them, and every
transition must emit a `TenantRegistryAuditEvent` with actor, reason, `from_state`,
and `to_state`.

| From | Allowed to | Notes |
|---|---|---|
| `draft` | `provisioning`, `archived`, `failed_provisioning` | Provisioning begins, or the draft is discarded. |
| `provisioning` | `active`, `failed_provisioning`, `draft` | Success, failure, or rollback to draft. |
| `active` | `under_review`, `paused`, `suspended`, `archived` | Operational transitions. |
| `under_review` | `active`, `paused`, `suspended` | Review concludes. |
| `paused` | `active`, `suspended`, `archived` | Resume, escalate, or offboard. |
| `suspended` | `active`, `archived` | Reinstate or offboard. |
| `failed_provisioning` | `provisioning`, `archived` | Retry or abandon. |
| `archived` | (terminal) | No outgoing transitions; the schema may be retained for audit. |
| `unknown` | (none automatic) | Requires manual diagnosis before any transition. |

Transition rules (non-negotiable):

1. No transition without an actor, a reason, and an audit event (counterexample C5).
2. Disallowed transitions are rejected and recorded as a `result = denied` audit
event with a reason.
3. `unknown` is never an automatic source of a transition to `active`.
4. P17 defines the graph; it does not implement or invoke it.

## 6. Permission Matrix

`yes` = may read; `no` = denied; `subset` = support-safe subset only; `summary` =
status-only summary (no raw failure detail); `future` = not in P17; reserved for a
separately approved controlled-action phase.

| Capability | super_admin | support_operator | engineering_operator | tenant-contextual admin |
|---|---|---|---|---|
| View full `PlatformTenantRegistry` | yes | no | no | no |
| View lifecycle state (support-safe) | yes | yes | yes | no |
| View operational flags, full set | yes | no | yes | no |
| View operational flags, support subset (`support_mode_active`, `incident_active`, `login_paused`, `writes_paused`) | yes | yes | yes | no |
| View provisioning diagnostics, full (incl. `failure_reason_redacted`) | yes | no | yes | no |
| View provisioning summary (status enums only) | yes | yes | yes | no |
| View backup diagnostics, full | yes | no | yes | no |
| View backup summary (`last_backup_status`, `export_available` only) | yes | yes | yes | no |
| View registry audit events | yes | own support events only | operational events only | no |
| Generate support bundle (registry subset, redacted) | yes (reason) | yes (assigned + reason) | yes (technical bundle + reason) | no |
| Mutate lifecycle state | future | no | no | no |
| Mutate operational flags | future | no | no | no |
| Trigger provisioning re-run | future | no | no | no |
| Trigger backup / restore test | future | no | no | no |

Explicit rules (required by the contract):

1. **tenant-contextual admin cannot access the platform registry.** A tenant-scoped
   actor is denied on every registry read (401/403), exactly as P10/P13/P15 enforce.
   This is the hardest boundary: registry data is cross-tenant and must never leak
   to a tenant-contextual identity.
2. **support_operator can view limited tenant lifecycle and support-safe status
   only.** Support reads the lifecycle state, the support subset of operational
   flags, and status-only summaries of provisioning and backup. Support must never
   see raw failure detail, full operational flags, full diagnostics, or audit
   payloads.
3. **engineering_operator can view operational, provisioning, and backup
   diagnostics** (full, including `failure_reason_redacted`) for root-cause work,
   read-only. Engineering cannot mutate.
4. **Only future controlled-action phases may mutate registry fields.** P17
   defines no write path. Any mutation (lifecycle transition, flag change,
   provisioning re-run, backup trigger) is reserved for a separately approved phase
   and must emit a `TenantRegistryAuditEvent`.
5. A super admin who has selected a tenant context is treated as
   tenant-contextual and is denied (identity-only enforcement).

---

## 7. Field Source Map (P17-B may only read these)

Registry fields must be sourced exclusively from existing read-only platform
sources. Anything without a real source is `null` or `unknown` with a reason --
never fabricated.

| Registry field | Allowed source | Fallback when missing |
|---|---|---|
| tenant identity, schema, tier, created_at, last_registry_update_at | public platform metadata (registry row) | `null` + `unavailable_reason`; the record is `unknown` if the row is absent |
| lifecycle `state`, `previous_state`, `entered_at` | public platform metadata | `state = unknown` + reason |
| `last_actor_id`, `last_actor_role`, audit actor fields | platform auth context (deferred) | `null` until platform auth exists |
| operational flags | runtime telemetry + manual/admin input | flag `false` + `flags_unavailable_reason` |
| `schema_status` | P13/P14 DB metadata / live probe | `null` + `unavailable_reason` from P13/P14 |
| seed / admin_user / feature_config status | tenant schema aggregate | `null` + reason |
| `last_provisioning_check_at` | runtime telemetry | `null` if never checked |
| `failure_reason_redacted` (provisioning) | runtime telemetry, allowlisted + redacted | `null` if no failure; never raw |
| `last_backup_at`, `last_backup_status`, restore-test fields | backup system | `null` + reason; `stale` if outside the freshness window |
| `export_available`, `retention_policy` | backup system (manual/admin configured) | `null` + reason |
| `failure_reason_redacted` (backup) | backup system, allowlisted + redacted | `null` if no failure; never raw |
| audit event fields | audit metadata + platform auth context | per P10 `PlatformAuditEvent` rules |

**Forbidden sources:** tenant business tables (orders, payments, invoices,
customers), raw request/response bodies, credentials, DSNs, host/port, connection
strings, migration history, and raw audit-log payloads.

---

## 8. Security Boundary

- **Identity-only super_admin** is required to read the full registry (P10 guard).
  A super admin who has selected a tenant context is denied.
- **tenant-contextual admin is denied on every registry read** (401/403). Registry
  data is cross-tenant and must never reach a tenant-scoped identity.
- **support_operator scope is strictly narrower** than super_admin: lifecycle
  state plus a support-safe subset only. Raw failure detail, full flags, full
  diagnostics, and audit payloads are excluded.
- **engineering_operator** reads operational, provisioning, and backup diagnostics
  read-only; no mutation.
- **No raw sensitive payloads.** The P10 `redact_metadata` allowlist applies to
  every registry field and every audit `metadata_redacted` object. `failure_reason_redacted`
  fields carry allowlisted reason codes only -- never the raw exception, stack
  trace, credential, DSN, host/port, or connection string.
- **No tenant business records** anywhere in the registry.
- **`unknown` is never `healthy` or `active`; `null` is never `0`.** A field whose
  source is down reads its fallback, never a fabricated passing value.
- **No mutation endpoints in P17.** P17 is read and contract only. Every mutation
  is reserved for a separately approved controlled-action phase and is audited.
- **No migrations**, no auth/RBAC/session/tenancy/payment changes, no product
  business-data scope.
- **Freshness is enforced.** A `last_backup_status` of `success` is invalid when
  `last_backup_at` is stale; it must read `stale`, never `success`.

---

## 9. P17-B Entry Gate (future)

A future P17-B is permitted to implement **only a read-only registry adapter**: the
data contracts in section 4, wired to the sources in section 7, behind the
identity-only guard in section 8, with redaction, graceful degradation, and the
permission matrix in section 6.

P17-B (and all of P17) **must not** implement:

- Any mutation of registry fields (lifecycle transition, flag change, provisioning
  re-run, backup trigger). Mutation is reserved for a separately approved
  controlled-action phase.
- Any tenant or user impersonation.
- Any tenant business-data query (orders, payments, invoices, customers).
- Any migration or alembic change.
- Any auth / RBAC / session / tenancy rewrite.
- Any write/mutation endpoint (POST/PUT/PATCH/DELETE) unless separately approved.
- Any new observability or backup infrastructure (reuse P13/P14 signals and the
  existing backup system only).
- Any cockpit mutation control (pause/resume/suspend/re-provision buttons).

---

## 10. Acceptance Criteria

P17-B (and any later phase that touches the registry) is accepted only when all of
the following hold:

1. **`unknown` is never `active` or `healthy`.** A registry field whose source is
   unavailable yields `unknown` or `null`, never a fabricated passing value.
2. **`null` is never `0`.** An unavailable count or a defaulted `false` flag is
   distinguishable from a real value via `*_source_status` and the reason field.
3. **Every unavailable field carries a visible reason** (`unavailable_reason`,
   `flags_unavailable_reason`, or the relevant `*_source_status`).
4. **tenant-contextual admin is denied** (401/403) on every registry read.
5. **Every lifecycle transition carries an actor, a reason, and an audit event.**
   No transition is accepted without all three.
6. **Disallowed transitions are rejected and recorded** as `result = denied` audit
   events with a reason.
7. **`failure_reason_redacted` contains only allowlisted reason codes** -- no
   secret, credential, DSN, host/port, connection string, stack trace, or raw
   exception.
8. **support_operator scope is strictly narrower** than super_admin: lifecycle
   state plus the support-safe subset only. Tests assert that support never sees
   raw failure detail, full operational flags, full diagnostics, or audit payloads.
9. **engineering_operator sees full operational, provisioning, and backup
   diagnostics read-only**, and has no mutation controls.
10. **`last_backup_status` never reads `success` when `last_backup_at` is stale.**
    It reads `stale` (or `unknown`), with the reason visible.
11. **No mutation endpoints or controls exist in P17.** Registry reads are
    GET-only / read-only; no pause, resume, suspend, or re-provision button or
    write endpoint exists.
12. **No migrations, no auth/RBAC/session/tenancy/payment changes, no product
    business scope, and no backend/frontend runtime code** in P17-A.
13. **No credential/DSN/host/port or tenant-business-data leak** in any registry
    response, audit payload, or support bundle (content scan).
14. **Freshness timestamps are UTC ISO-8601** and present whenever their source is
    available (`entered_at`, `flags_updated_at`, `last_provisioning_check_at`,
    `last_backup_at`, `last_status_check_at`, `created_at`).
15. **Audit is append-only** and two events never share an `event_id`.

## 11. Counterexamples (must fail or be rejected)

These implementations and behaviors must be rejected by P17-B tests or review.

1. **C1 -- tenant-contextual admin accessing the registry.** Any tenant-scoped
   identity successfully reading any registry field -- rejected (must 401/403).
2. **C2 -- support operator seeing backup failure raw details.** A support view or
   support bundle that includes the raw backup failure output, job log, path, or
   hostname -- rejected; only `failure_reason_redacted` (allowlisted reason code)
   is support-safe.
3. **C3 -- registry field reported healthy when the source is unknown.** A field
   whose source is unavailable returning `active` / `healthy` / `success` /
   `exists` -- rejected; it must return `unknown` or `null` with a reason.
4. **C4 -- backup status shown as success with a stale timestamp.** A
   `last_backup_status` of `success` while `last_backup_at` is outside the
   freshness window -- rejected; it must read `stale` (or `unknown`).
5. **C5 -- lifecycle transition without actor / reason / audit.** A transition
   that changes `state` with a missing actor, reason, or audit event -- rejected.
6. **C6 -- provisioning failure exposing raw secrets.** `failure_reason_redacted`
   (or any provisioning field) containing a credential, DSN, host/port, connection
   string, stack trace, or raw exception -- rejected.
7. **C7 -- platform UI offering pause/resume in P17.** Any cockpit control
   (button, endpoint, or link) that pauses, resumes, suspends, re-provisions, or
   otherwise mutates registry state in P17 -- rejected; mutation is reserved for a
   future controlled-action phase.
8. **C8 -- migration or backend code added in P17-A.** Any change under
   `backend/`, `frontend/`, `migrations/`, `alembic/`, `.github/`, `.claude/`, or
   `product-dev-recovered/`, or any auth/RBAC/session/tenancy/payment change in
   P17-A -- rejected; P17-A is docs and ledger only.
9. **C9 -- credential/DSN/host/port leak** in any registry response, audit
   payload, or bundle -- rejected.
10. **C10 -- `0` instead of `null`** when a count or status source is unavailable
    -- rejected.
11. **C11 -- a mutation endpoint on the registry in P17.** Any POST/PUT/PATCH/
    DELETE registry route in P17 -- rejected (read-only).
12. **C12 -- engineering_operator mutating a flag.** Any write capability granted
    to engineering_operator -- rejected; engineering is read-only.
13. **C13 -- an audit event missing a reason on a transition or flag change.** A
    `lifecycle_transition` or `flag_change` event with `reason = null` -- rejected.
14. **C14 -- tenant business records in a registry response or bundle** (orders,
    payments, invoices, customers) -- rejected.

---

## 12. Test Plan Estimate (P17-B / later)

Approximate scope (final counts set at implementation time):

- **Backend schema/contract tests** (~30-40): `*_source_status` consistency
  (`available` + value, `unavailable` + null/fallback, reject `unknown` +
  passing value), `extra="forbid"`, graceful-degraded shape, redaction allowlist,
  freshness/staleness (`stale` vs `success`), append-only audit + unique
  `event_id`.
- **Route guard tests** (~15-20): identity-only super_admin allowed;
  tenant-contextual denied; support subset; engineering full diagnostics;
  GET-only (POST/PUT/PATCH/DELETE -> 405); access-denied audit written.
- **Redaction tests** (~10-15): no secret/credential/DSN/host/port;
  `failure_reason_redacted` is an allowlisted reason code only; no tenant business
  records.
- **Permission-matrix tests** (~10-15): per-role field visibility; support-safe
  subset; engineering diagnostics; tenant-contextual denial on every field.
- **Lifecycle tests** (~10-15): allowed and disallowed transitions; every
  transition requires actor + reason + audit; `unknown` never auto-transitions.
- **Forbidden path tests** (~10): assert no `backend/`, `frontend/`, `migrations/`,
  `alembic/`, `.github/`, `.claude/`, `product-dev-recovered/`, auth/RBAC/session,
  payment, or tenancy paths are touched; no write endpoints.

Estimated total: ~85-115 tests, all read-only / scope / redaction / lifecycle
focused.

---

## Out of Scope Reminder

This is P17-A. It ships **docs + ledger only**. There is no runtime code, no
backend, no frontend, no migration, no test code, and no dependency change in this
phase. P17-B (a read-only registry adapter) begins only after this contract is
accepted, and any mutation is reserved for a separately approved controlled-action
phase.
