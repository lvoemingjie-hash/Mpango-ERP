# P12 Support Console Contract

**Phase:** P12-A
**Status:** Contract/design/test-plan only — no runtime code, no migrations, no API handlers, no frontend UI
**Date:** 2026-06-11
**Base:** `origin/platform-dev` at `12c2a30` (P11 merge)
**Branch:** `codex/platform-p12a-support-console-contract-2026-06-10`
**Author:** Platform product boundary analysis

---

## 1. Goal

The P12 Support Console allows platform operators to diagnose tenant issues safely through a structured, read-only, audit-trailed support workflow.

### Core Principles

- **Allow** super admin, support operator, and engineering operator to diagnose tenant issues through structured support sessions.
- **No impersonation.** The support console never logs in as a tenant user, assumes a tenant session, or bypasses tenant-auth boundaries.
- **No tenant business data mutation.** Support sessions are strictly read-only. The only writes are audit events and support session/bundle metadata.
- **No raw sensitive payloads by default.** Passwords, tokens, secrets, cookies, card numbers, payment identifiers, and raw business payloads are never exposed in support views or bundles.

### Alignment

- Inherits all constraints from `PLATFORM_PRODUCT_SECURITY_BOUNDARY.md`.
- Inherits all data contract shapes from `PLATFORM_PRODUCT_CONTRACTS.md` (P10-A-R1).
- Inherits permission model from `PLATFORM_PRODUCT_PERMISSION_MATRIX.md`.
- Inherits support workflow patterns from `PLATFORM_PRODUCT_ADMIN_WORKFLOWS.md` (Workflow 1–4).
- Inherits frontend boundary rules from `PLATFORM_PRODUCT_P11_FRONTEND_BOUNDARY.md`.
- Extends the P11 read-only cockpit with tenant-specific support diagnosis.

---

## 2. Personas

### Super Admin

- Full platform owner (Jeff or explicitly trusted operator).
- Can open support sessions for any tenant.
- Can generate support bundles for any tenant.
- Can view all audit events including other operators' support sessions.
- Must provide a reason for every support session.
- Authenticated via identity-only (global) `super_admin` Bearer token (established in P11-B0-R1).

### Support Operator

- Restricted platform role focused on tenant diagnosis.
- Can open support sessions only for assigned tenants.
- Can generate support bundles only for assigned tenants.
- Can view own support session audit events and assigned-tenant diagnostics.
- Cannot change tenant status, platform configuration, or view billing/payment secrets.
- Must provide a reason for every support session.
- **P12-A status:** contract only. Role assignment mechanism is deferred to implementation.

### Engineering Operator

- Restricted platform role focused on system health and incident response.
- Can open support sessions with a technical diagnostic focus.
- Can generate technical support bundles (metrics, errors, correlation IDs).
- Cannot access raw tenant business data by default.
- Cannot change tenant lifecycle state unless explicitly authorized.
- Must provide a reason for every support session.
- **P12-A status:** contract only. Role assignment mechanism is deferred to implementation.

### Explicitly Denied

- **Product Admin / Tenant-contextual admin:** Must not access the support console even if the tenant-contextual token carries a `super_admin` role. Only identity-only (global) `super_admin` tokens are accepted (per P11-B0-R1 resolution).
- **Tenant users:** No tenant user may access platform support features.

---

## 3. Support Workflow

The support console follows a structured workflow that must be enforced at the API and UI level.

### Step 1: Select Tenant

- Actor navigates to support tenant selector.
- Actor selects a tenant by ID, name, or schema from the tenant directory.
- System checks actor's role and assigned-tenant scope (if support_operator).
- System displays tenant summary from `TenantSummary` contract.

### Step 2: Provide Support Reason

- Actor must enter a support reason before any tenant-specific diagnostic data is loaded.
- Support reason is a **required** free-text field with minimum length of 10 characters.
- Support reason is recorded in the support session and audit event.
- **Counterexample:** Opening a support view without a reason must fail with `400 BAD REQUEST` and an audit event with `result: "denied"`.

### Step 3: Open Read-Only Support View

- System creates a `SupportSession` record with start timestamp, actor, tenant, and reason.
- System writes a `support_session_start` audit event.
- System loads tenant diagnostics from `TenantHealth` contract data.
- All diagnostic data is **read-only** — no edit forms, no mutation buttons, no inline changes.
- If a data source is unavailable, the system shows `unknown` or `null` — never fabricates `healthy` or `0`.

### Step 4: Inspect Redacted Diagnostics

- System displays tenant health, activity counters, recent errors, slow routes, and failed jobs.
- All diagnostics follow the `TenantHealth` contract shape from P10-A-R1.
- Redaction policy (Section 7) is applied to every field.
- Actor may navigate between diagnostic tabs/views within the support session.

### Step 5: Generate Support Bundle

- Actor requests a support bundle from within the active support session.
- System gathers redacted diagnostic items into a `SupportBundle`.
- System writes a `support_bundle_generated` audit event.
- Bundle excludes raw sensitive payloads per redaction policy (Section 7).
- Bundle includes correlation IDs, timestamps, and diagnostic summaries.

### Step 6: Close Support Session

- Actor closes the support session (or it expires after a defined timeout).
- System writes a `support_session_end` audit event.
- Session end timestamp is recorded.
- **Counterexample:** Support session without an end event is a gap — the system must auto-expire sessions and write the end event.

### Workflow Sequence Diagram (Conceptual)

```
Actor                  System                  Audit
  |                      |                      |
  |-- select tenant ---->|                      |
  |                      |-- check role/scope ->|
  |<-- tenant summary ---|                      |
  |                      |                      |
  |-- provide reason --->|                      |
  |                      |-- validate reason -->|
  |                      |                      |
  |-- open support ----->|                      |
  |                      |-- create session --->|
  |                      |                      |-- session_start event
  |<-- redacted diag ----|                      |
  |                      |                      |
  |-- generate bundle -->|                      |
  |                      |-- build bundle ----->|
  |                      |                      |-- bundle_generated event
  |<-- support bundle ---|                      |
  |                      |                      |
  |-- close session ---->|                      |
  |                      |-- close session ---->|
  |                      |                      |-- session_end event
```

---

## 4. Data Contracts

### 4.1 SupportReason

```
SupportReason {
  reason          : string    NOT NULL   -- free-text, minimum 10 characters
  category        : enum      NULLABLE   -- optional classification
  entered_at      : timestamp NOT NULL   -- UTC ISO-8601
}
```

#### Category Enum

| Value | Meaning |
|-------|---------|
| `login_issue` | Tenant login failure triage |
| `activity_anomaly` | Order or activity anomaly |
| `performance` | Slow response or high load |
| `data_integrity` | Suspected data inconsistency |
| `integration` | Sync or integration failure |
| `general` | General support request |
| `incident` | Active incident response |
| `other` | Uncategorized |

#### Counterexamples (Rejected)

1. `reason` shorter than 10 characters — must fail validation.
2. `reason` as `null` — must fail validation.
3. `reason` containing raw PII or credentials — must be sanitized before storage.

### 4.2 SupportSession

```
SupportSession {
  session_id        : uuid        NOT NULL   -- unique session identifier
  actor_id          : string      NOT NULL   -- platform operator identity
  actor_role        : enum        NOT NULL   -- super_admin | support_operator | engineering_operator
  tenant_id         : uuid        NOT NULL   -- target tenant
  reason            : string      NOT NULL   -- support reason text (min 10 chars)
  category          : enum        NULLABLE   -- optional classification
  correlation_id    : string      NOT NULL   -- session correlation ID
  status            : enum        NOT NULL   -- active | closed | expired
  started_at        : timestamp   NOT NULL   -- UTC ISO-8601
  closed_at         : timestamp   NULLABLE   -- UTC ISO-8601, null if active
  expires_at        : timestamp   NULLABLE   -- UTC ISO-8601, auto-expiry deadline
  bundle_count      : integer     NOT NULL   -- >= 0, number of bundles generated in this session
}
```

#### Session Status Enum

| Value | Meaning |
|-------|---------|
| `active` | Session is open and diagnostics are being viewed. |
| `closed` | Actor explicitly closed the session. |
| `expired` | Session timed out without explicit close. |

#### Counterexamples (Rejected)

1. `SupportSession` without `reason` — must fail creation.
2. `SupportSession` with `actor_role: "product_admin"` — must be denied.
3. Two `SupportSession` records with the same `session_id`.
4. `SupportSession` where `tenant_id` is outside actor's assigned scope (for support_operator).
5. `status` transitioning from `closed` back to `active` — sessions are one-shot.

### 4.3 SupportBundle

```
SupportBundle {
  bundle_id         : uuid                NOT NULL   -- unique bundle identifier
  session_id        : uuid                NOT NULL   -- parent support session
  actor_id          : string              NOT NULL   -- who requested the bundle
  tenant_id         : uuid                NOT NULL   -- target tenant
  correlation_id    : string              NOT NULL   -- inherited from session + bundle suffix
  generated_at      : timestamp           NOT NULL   -- UTC ISO-8601
  diagnostics       : SupportDiagnosticItem[] NOT NULL -- at least 1 item
  redaction_applied : boolean             NOT NULL   -- always true in P12
  bundle_type       : enum                NOT NULL   -- full | technical | summary
}
```

#### Bundle Type Enum

| Value | Meaning |
|-------|---------|
| `full` | Complete redacted diagnostics available to the actor's role scope. |
| `technical` | Technical-only diagnostics (errors, metrics, correlation IDs, job summaries). No business counters. |
| `summary` | High-level summary only (health status, schema status, top errors). |

#### Counterexamples (Rejected)

1. `SupportBundle` with empty `diagnostics` array — must have at least 1 item.
2. `SupportBundle` containing raw order payloads — redaction policy violation.
3. `SupportBundle` generated outside an active `SupportSession`.
4. `SupportBundle` with `bundle_type` exceeding actor's role scope (support_operator cannot request `full` if limited to `summary`).

### 4.4 SupportDiagnosticItem

```
SupportDiagnosticItem {
  item_id           : uuid        NOT NULL   -- unique item identifier
  bundle_id         : uuid        NOT NULL   -- parent bundle
  category          : enum        NOT NULL   -- what this item describes
  label             : string      NOT NULL   -- human-readable label
  value             : any         NOT NULL   -- the diagnostic value (redacted)
  source_status     : enum        NOT NULL   -- data source health
  collected_at      : timestamp   NOT NULL   -- UTC ISO-8601
}
```

#### Diagnostic Category Enum

| Value | Meaning | Example Content |
|-------|---------|-----------------|
| `tenant_metadata` | Tenant identity and status fields | tenant_id, schema, status, tier |
| `health_summary` | Overall health assessment | health_status, schema_status |
| `activity_counters` | Windowed business activity counts | orders, inventory changes, invoices (counts only) |
| `recent_errors` | Redacted error summaries | error_class, count, correlation_ids |
| `slow_routes` | Performance summaries | route name, latency bucket, count |
| `failed_jobs` | Job failure summaries | job_class, count |
| `system_snapshot` | System health at time of bundle | SystemHealth contract fields |
| `correlation_ids` | Related correlation IDs | for cross-referencing with logs |
| `schema_status` | Tenant schema reachability | exists, unreachable, missing, unknown |

#### Source Status Enum

| Value | Meaning |
|-------|---------|
| `available` | Data source returned valid data. |
| `degraded` | Data source returned partial data. |
| `unavailable` | Data source did not respond or is not instrumented. |
| `unknown` | Cannot determine source status. |

#### Counterexamples (Rejected)

1. `SupportDiagnosticItem` where `category = "tenant_metadata"` but `value` contains raw customer PII.
2. `SupportDiagnosticItem` where `source_status = "available"` but `value` is `null` — if value is null, source_status must be `"unavailable"` or `"unknown"`.
3. `SupportDiagnosticItem` with `category = "recent_errors"` containing raw request/response body.

### 4.5 SupportAuditEvent

Extends `PlatformAuditEvent` from P10-A-R1 with support-specific fields.

```
SupportAuditEvent extends PlatformAuditEvent {
  -- All fields from PlatformAuditEvent (event_id, actor_id, actor_role, tenant_id,
  --   scope, action, reason, result, metadata_redacted, correlation_id, created_at)
  -- scope is always "support" for support audit events

  -- Additional support-specific fields in metadata_redacted:
  session_id        : uuid        -- reference to SupportSession
  bundle_id         : uuid        -- reference to SupportBundle (if applicable)
  bundle_type       : enum        -- bundle type (if applicable)
}
```

#### Support Audit Action Enum

| Action | When | Scope |
|--------|------|-------|
| `support_session_start` | Actor opens a support session for a tenant. | `support` |
| `support_session_end` | Actor closes or session expires. | `support` |
| `support_bundle_generated` | Actor generates a support bundle. | `support` |
| `support_session_expired` | System auto-expires an idle session. | `support` |
| `support_view_diagnostic` | Actor views a specific diagnostic item. | `support` |
| `support_access_denied` | Actor denied access (wrong role, unassigned tenant, missing reason). | `support` |

#### Counterexamples (Rejected)

1. `support_session_start` with `reason = null` — must fail.
2. `support_bundle_generated` without a prior `support_session_start` event.
3. `SupportAuditEvent` with `scope = "tenant"` — support events must use `scope = "support"`.
4. Audit event for a tenant-contextual token accessing support features — must be `denied`.

---

## 5. Field Source Map

Every field in P12 data contracts maps to one or more data sources. This section defines the source, expected availability, and fallback behavior.

### Source Zones

| Zone | Description | P12-A Availability |
|------|-------------|-------------------|
| `public platform tables` | Tenant registry, status, tier in `public` schema or equivalent platform metadata surface | `proposed_public_metadata` — requires P10-B/P11 backend |
| `P10 platform contracts` | TenantSummary, TenantHealth, SystemHealth, PlatformAuditEvent as exposed by P10 read-only APIs | `available_now` — implemented in P10-B/P11 |
| `existing audit logs` | PlatformAuditEvent records from P10/P11 audit endpoints | `available_now` — implemented in P11-C |
| `runtime metrics/logs` | Application logs, metrics, traces, queue state, DB health | `telemetry_required` — not yet instrumented |
| `tenant schema aggregates` | Activity counters, login timestamps from tenant schemas | `tenant_aggregate_required` — requires safe aggregation path |

### SupportReason Source Map

| Field | Source | Availability | Fallback |
|-------|--------|-------------|----------|
| `reason` | Actor input | Always | N/A (required) |
| `category` | Actor selection or auto-classification | `proposed_public_metadata` | `null` |
| `entered_at` | System timestamp | Always | N/A (required) |

### SupportSession Source Map

| Field | Source | Availability | Fallback |
|-------|--------|-------------|----------|
| `session_id` | Generated UUID v4/v7 | Always | N/A |
| `actor_id` | Platform auth context | `deferred` until platform auth exists | Hardcoded in P10-B fixtures |
| `actor_role` | Platform auth context | `deferred` until platform auth exists | Hardcoded in P10-B fixtures |
| `tenant_id` | Tenant selector input | `proposed_public_metadata` | N/A (required) |
| `reason` | Actor input (SupportReason) | Always | N/A (required) |
| `category` | From SupportReason | `proposed_public_metadata` | `null` |
| `correlation_id` | Generated per session | Always | N/A |
| `status` | Session lifecycle | Always | N/A |
| `started_at` | System timestamp | Always | N/A |
| `closed_at` | System timestamp on close | Always when closed | `null` if active |
| `expires_at` | Configured timeout | Always | N/A |
| `bundle_count` | Derived from bundle count | Always | `0` |

### SupportDiagnosticItem Source Map

| Category | Source Zone | Availability | Unknown Behavior |
|----------|-------------|-------------|------------------|
| `tenant_metadata` | public platform tables | `proposed_public_metadata` | `source_status: "unavailable"`, value: minimal safe subset |
| `health_summary` | P10 platform contracts | `available_now` | `source_status: "unknown"`, value: `{ health_status: "unknown" }` |
| `activity_counters` | tenant schema aggregates | `tenant_aggregate_required` | `source_status: "unavailable"`, value: `null` |
| `recent_errors` | runtime metrics/logs | `telemetry_required` | `source_status: "unavailable"`, value: `null` |
| `slow_routes` | runtime metrics/logs | `telemetry_required` | `source_status: "unavailable"`, value: `null` |
| `failed_jobs` | runtime metrics/logs | `telemetry_required` | `source_status: "unavailable"`, value: `null` |
| `system_snapshot` | P10 platform contracts | `available_now` | `source_status: "unknown"`, value: `{ overall_status: "unknown" }` |
| `correlation_ids` | existing audit logs | `available_now` | `source_status: "unavailable"`, value: `[]` |
| `schema_status` | DB metadata / provisioning | `telemetry_required` | `source_status: "unknown"`, value: `{ schema_status: "unknown" }` |

### Degraded Fallback Behavior

When a data source is unavailable:

1. The corresponding `SupportDiagnosticItem` must still appear in the bundle with `source_status: "unavailable"` or `"unknown"`.
2. The `value` must be `null` or a minimal safe object with `"unknown"` status.
3. The UI must display this distinctly from `"healthy"` or `"0"` — use "Data unavailable" or "N/A" with a gray indicator.
4. **Counterexample:** An unavailable data source must NEVER produce `source_status: "available"` or `value: 0` or `value: { health_status: "healthy" }`.

---

## 6. Permission Matrix

### Role-Action Matrix for Support Console

| Action | super_admin (identity-only) | support_operator | engineering_operator | tenant-contextual admin |
|--------|-----------------------------|------------------|---------------------|------------------------|
| Select any tenant for support | **Allow** | Assigned only | Allow (technical focus) | **Deny** |
| Provide support reason | **Allow** (required) | **Allow** (required) | **Allow** (required) | **Deny** |
| Open support session | **Allow** with audit | **Allow** for assigned + audit | **Allow** with audit | **Deny** |
| View redacted diagnostics | **Allow** | **Allow** for assigned | **Allow** (technical items only) | **Deny** |
| Generate full support bundle | **Allow** with reason + audit | **Allow** for assigned + reason + audit | **Deny** (technical only) | **Deny** |
| Generate technical support bundle | **Allow** with reason + audit | **Deny** | **Allow** with reason + audit | **Deny** |
| Generate summary support bundle | **Allow** with reason + audit | **Allow** for assigned + reason + audit | **Allow** with reason + audit | **Deny** |
| View own support audit events | **Allow** | **Allow** | **Allow** | **Deny** |
| View all support audit events | **Allow** | **Deny** | **Deny** | **Deny** |
| Close support session | **Allow** | **Allow** (own sessions) | **Allow** (own sessions) | **Deny** |
| Access support console at all | **Allow** | **Allow** | **Allow** | **Deny** |

### Identity-Only Enforcement

Per P11-B0-R1 resolution:

- **Only identity-only (global) `super_admin` Bearer tokens** are accepted for platform support console access.
- A **tenant-contextual token** with `super_admin` role is **NOT sufficient** — must be **denied**.
- This applies to all support console operations: session creation, diagnostic viewing, bundle generation, audit review.
- The `X-Platform-Operator` header remains available for server/operator contexts but is not used in the browser.

### Counterexamples (Rejected)

1. Support operator accessing diagnostics for an unassigned tenant — must deny with audit event.
2. Engineering operator requesting `full` bundle type — must deny, only `technical` and `summary` allowed.
3. Any actor opening a support session without a reason — must reject with `400 BAD REQUEST`.
4. Tenant-contextual admin token accessing any support endpoint — must deny with `403 FORBIDDEN`.
5. Support operator changing tenant status from support console — no write operations allowed.
6. Support operator viewing billing/payment secrets in diagnostics — must deny.

---

## 7. Redaction Policy

### 7.1 Always Redacted (Removed Before Display/Storage in Bundles)

These fields are **never** included in support views, diagnostic items, or support bundles:

| Category | Examples |
|----------|---------|
| Passwords | `password`, `password_hash`, `password_reset_token` |
| Tokens | `jwt`, `bearer_token`, `api_key`, `secret_key`, `access_token`, `refresh_token` |
| Secrets | `private_key`, `client_secret`, `webhook_secret`, `encryption_key` |
| Cookies | `session_cookie`, `auth_cookie` |
| Card/Payment identifiers | `card_number`, `cvv`, `bank_account_number`, `routing_number` |
| Raw auth payloads | `authorization_header`, `cookie_header` |

### 7.2 Summarized (Counts/Status Only, Not Raw Payloads)

These fields are included only as **aggregated counts or status indicators**, never as raw payloads:

| Category | Allowed Form | Forbidden Form |
|----------|-------------|----------------|
| Orders | `orders: 42` (count) | Raw order objects, line items, customer details |
| Inventory changes | `inventory_changes: 15` (count) | Raw inventory records, SKU details, quantities |
| Invoices | `invoices: 8` (count) | Raw invoice objects, amounts, customer details |
| Payments | `payments: 3` (count) | Payment amounts, card numbers, bank details, transaction IDs |
| Sync jobs | `sync_jobs: 1` (count) | Raw sync payloads, mapped data |
| Errors | `error_class + count + correlation_ids` | Raw request/response body, stack trace with tenant data |
| Slow routes | `route + latency_bucket + count` | Full URL with query params, request body |
| Failed jobs | `job_class + count` | Job payload, job arguments |

### 7.3 Safe to Include (No Redaction Needed)

| Category | Examples |
|----------|---------|
| Tenant metadata | `tenant_id`, `tenant_name`, `tenant_schema`, `status`, `tier` |
| Health statuses | `health_status`, `schema_status`, component statuses |
| Timestamps | `created_at`, `last_activity_at`, `last_login_at`, `started_at` |
| Correlation IDs | UUIDs for cross-referencing logs |
| Error class names | Class name only (e.g., `"ValidationError"`, `"ConnectionError"`) |
| Route names | Route path only (e.g., `"/api/v1/orders"`) |
| Job class names | Class name only (e.g., `"InventorySyncJob"`) |
| System health | `overall_status`, component statuses, connection counts |

### 7.4 Bundle Exclusion Rules

Support bundles must additionally exclude:

1. Raw customer/order/payment/inventory payloads — only counts allowed.
2. Any field from Section 7.1 (Always Redacted).
3. Tenant business data from a **different tenant** than the session target.
4. Raw `metadata_redacted` payloads from audit events — only structured fields.
5. Internal system secrets, environment variables, or deployment configuration.

### 7.5 Redaction Enforcement

- Redaction must be applied at the **data gathering layer** — not at the presentation layer.
- Every `SupportDiagnosticItem` must pass through the redaction filter before being added to a bundle.
- The `redaction_applied: true` flag on `SupportBundle` indicates the filter was applied.
- **Counterexample:** A `SupportBundle` with `redaction_applied: false` must be rejected by the API.

---

## 8. Audit Requirements

### 8.1 Required Audit Event Fields

Every support console audit event must include:

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `event_id` | uuid | YES | Unique event identifier (UUID v4/v7) |
| `actor_id` | string | YES | Platform operator identity |
| `actor_role` | enum | YES | `super_admin`, `support_operator`, or `engineering_operator` |
| `tenant_id` | uuid | YES | Target tenant |
| `reason` | string | YES for session start and bundle generation | Support reason text |
| `action` | string | YES | From support audit action enum (Section 4.5) |
| `result` | enum | YES | `allowed`, `denied`, `failed`, or `completed` |
| `timestamp` | timestamp | YES | UTC ISO-8601 |
| `correlation_id` | string | YES | Session correlation ID |
| `scope` | enum | YES | Always `"support"` for support console events |

### 8.2 Audit Event Scenarios

| Scenario | Action | Result | Audit Written |
|----------|--------|--------|---------------|
| Actor opens support session | `support_session_start` | `allowed` | YES |
| Actor denied — wrong role | `support_access_denied` | `denied` | YES |
| Actor denied — missing reason | `support_access_denied` | `denied` | YES |
| Actor denied — unassigned tenant | `support_access_denied` | `denied` | YES |
| Actor denied — tenant-contextual token | `support_access_denied` | `denied` | YES |
| Actor generates bundle | `support_bundle_generated` | `completed` | YES |
| Actor closes session | `support_session_end` | `completed` | YES |
| Session auto-expires | `support_session_expired` | `completed` | YES |
| Actor views diagnostic item | `support_view_diagnostic` | `allowed` | YES (sampled in later implementation) |
| Bundle generation fails | `support_bundle_generated` | `failed` | YES |

### 8.3 Audit Immutability

- Support audit events are **append-only**.
- No actor may delete or rewrite a support audit event.
- Audit events must be queryable by: actor, tenant, action, time window, result, correlation_id.

---

## 9. P12-B Implementation Gate

P12-B (support console API implementation) may only begin after P12-A is accepted and merged. The following gates must be satisfied before P12-B implementation starts:

### 9.1 API Constraints

- The P12 API must be **read-only** except for:
  - `SupportSession` creation (support_session_start).
  - `SupportSession` closure (support_session_end / support_session_expired).
  - `SupportBundle` generation (support_bundle_generated).
  - `SupportAuditEvent` creation for all support operations.
- No mutations to tenant business data, auth, RBAC, session, tenancy, or payment state.

### 9.2 Mandatory Audit

- Every support view must write a `support_session_start` audit event.
- Every support bundle generation must write a `support_bundle_generated` audit event.
- Every denied access attempt must write a `support_access_denied` audit event.
- Session close/expiry must write a `support_session_end` or `support_session_expired` audit event.

### 9.3 No Migrations Unless Separately Approved

- P12-B must not add database migrations unless a dedicated CTO gate approves a platform-owned metadata store.
- P12 support session/bundle data may use existing platform tables or in-memory structures pending CTO decision.

### 9.4 No Frontend Until P12-B API Contract Tests Pass

- P12-C (frontend support UI) may not begin until:
  - P12-B API endpoints are implemented.
  - Contract tests prove all data shapes match this document.
  - Permission tests prove identity-only enforcement.
  - Redaction tests prove sensitive fields are removed.
  - Audit tests prove every operation writes an audit event.

### 9.5 P12-B Entry Checklist

Before P12-B implementation begins:

- [ ] P12-A contract document accepted by CTO/product owner.
- [ ] P12-A ledger recorded and merged to `platform-dev`.
- [ ] P12 data contracts reviewed against P10-A contracts for consistency.
- [ ] Redaction policy reviewed against security boundary.
- [ ] Permission matrix reviewed against P11-B0-R1 identity-only enforcement.
- [ ] No runtime code changes in P12-A (docs/ledger only).
- [ ] P11 batch fully merged and stable on `platform-dev`.

---

## 10. Acceptance Criteria and Counterexamples

### 10.1 Acceptance Criteria

| # | Criterion | Validation |
|---|-----------|------------|
| AC-01 | Missing support reason fails session creation | API returns 400, audit event with `result: "denied"` |
| AC-02 | Tenant-contextual token is denied for all support operations | API returns 403, audit event with `result: "denied"` |
| AC-03 | Support bundle redacts sensitive keys (passwords, tokens, secrets, cookies, cards) | Bundle scan finds zero sensitive keys |
| AC-04 | Raw business payload cannot appear in support bundle | Bundle scan finds no raw order/inventory/payment/invoice objects |
| AC-05 | Unknown metrics render as `unknown`, not `healthy` or `0` | UI displays gray indicator, not green or zero |
| AC-06 | Every support session generates start and end audit events | Audit log contains both events |
| AC-07 | Every support bundle generation generates audit event | Audit log contains bundle_generated event |
| AC-08 | Support operator cannot access unassigned tenant | API returns 403, audit event with `result: "denied"` |
| AC-09 | Engineering operator cannot generate `full` bundle type | API returns 403 for `full`, allows `technical` |
| AC-10 | Support session auto-expires after timeout | Session status transitions to `expired`, audit event written |
| AC-11 | No runtime code changes in P12-A | Only docs/ai/ and ai-ledger/ files modified |
| AC-12 | No migrations in P12-A | Zero migration files in diff |
| AC-13 | No frontend support UI in P12-A | Zero frontend files in diff |
| AC-14 | No auth/RBAC/session/tenancy/payment changes | Zero auth/payment/session files in diff |

### 10.2 Counterexamples (Must Be Rejected)

| # | Counterexample | Expected Rejection |
|---|---------------|-------------------|
| CE-01 | Support session created with empty reason | 400 BAD REQUEST, audit event with `result: "denied"` |
| CE-02 | Support session created with reason `"bug"` (9 chars) | 400 BAD REQUEST, reason too short |
| CE-03 | Tenant-contextual `super_admin` token accessing support endpoints | 403 FORBIDDEN, audit event with `result: "denied"` |
| CE-04 | Support bundle containing `"password": "..."` | Rejected by redaction filter |
| CE-05 | Support bundle containing raw order objects `[{"id": 1, "items": [...]}]` | Rejected by redaction filter |
| CE-06 | Support diagnostic item with `source_status: "available"` but `value: null` | Inconsistent — must be `"unavailable"` or `"unknown"` |
| CE-07 | Unknown health status rendered as green badge | Must render as gray "Data unavailable" |
| CE-08 | `user_count: null` displayed as `"0"` | Must display as `"N/A"` or `"--"` |
| CE-09 | Support operator accessing tenant outside assigned scope | 403 FORBIDDEN, audit event with `result: "denied"` |
| CE-10 | Engineering operator requesting `full` bundle | 403 FORBIDDEN |
| CE-11 | Support session transitioned from `closed` back to `active` | Invalid state transition |
| CE-12 | Support audit event with `scope: "tenant"` instead of `"support"` | Invalid scope for support events |
| CE-13 | Bundle generated outside an active support session | 400 BAD REQUEST |
| CE-14 | Support console API performing a write to tenant business data | Architecture violation — stop and escalate |
| CE-15 | P12-A branch containing runtime code changes | Rejected at merge gate |

### 10.3 Test Plan (P12-B Implementation)

| Category | Count (est.) | Description |
|----------|-------------|-------------|
| Session lifecycle | 8 | Create with reason, create without reason (fail), close, expire, status transitions |
| Permission enforcement | 10 | super_admin allow, support_operator assigned/unassigned, engineering_operator scope, tenant-contextual deny |
| Bundle generation | 8 | Full/technical/summary types, redaction enforcement, bundle outside session (fail) |
| Redaction verification | 6 | Sensitive key removal, business payload summarization, redaction_applied flag |
| Audit events | 8 | Session start/end, bundle generated, access denied, expired, required fields |
| Unknown state | 4 | Unknown ≠ healthy, null ≠ 0, unavailable source status |
| Counterexample validation | 10 | All 15 counterexamples covered in test fixtures |
| **Total estimate** | **~54** | |

---

## Scope Boundaries

This document does NOT:

- Implement API endpoints, HTTP methods, or URL patterns for support console.
- Define database migration schemas for support session/bundle storage.
- Modify auth/RBAC/session/tenancy/payment flows.
- Implement frontend support UI components.
- Require any code changes to `backend/`, `frontend/`, or `product-dev-recovered/`.
- Change the `schema-per-tenant` isolation architecture.
- Introduce impersonation capabilities.
- Expose raw tenant business data.

---

## References

- `PLATFORM_PRODUCT_PRD.md` — P11/P12 feature definitions
- `PLATFORM_PRODUCT_SECURITY_BOUNDARY.md` — Support mode rules, data redaction rules
- `PLATFORM_PRODUCT_CONTRACTS.md` — P10-A-R1 data contract shapes
- `PLATFORM_PRODUCT_PERMISSION_MATRIX.md` — Role-action permission matrix
- `PLATFORM_PRODUCT_ADMIN_WORKFLOWS.md` — Workflow 1–4 (support bundle generation)
- `PLATFORM_PRODUCT_P11_FRONTEND_BOUNDARY.md` — Frontend boundary and identity-only enforcement
- `ai-ledger/platform/2026-06-10_p11b0_c0_b1_c_d_batch_ledger.md` — P11 merge evidence
