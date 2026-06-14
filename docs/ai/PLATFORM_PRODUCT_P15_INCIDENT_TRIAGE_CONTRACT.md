# Platform Product P15 -- Incident Triage Contract

**Status:** Contract only (P15-A). No runtime code, no migrations, no frontend, no
backend handlers. Accepted by CTO before P15-B may begin.
**Phase:** P15-A Incident Triage Contract
**Date:** 2026-06-14
**Base:** `6b9efa8` (origin/platform-dev -- P14 real-signals merge)
**Depends on:** P10 (platform product contracts, tenant/system health), P12 (support
console diagnostics/bundle concepts), P13 (operations observability endpoints),
P14 (real DB live probe + `unavailable_reason` fields).
**Author:** Codex (Claude worker)

---

## 1. P15 Goals

P15 gives platform **super admin** and **support operator** a single **read-only
triage path** when an anomaly is suspected, so the operator can detect, classify,
inspect, explain, hand off, and record a conclusion -- **without** touching tenant
business data or executing any repair.

In scope for P15 (contract layer, P15-A):
- Define the incident triage workflow and the data contracts P15-B/P15-C will
  implement as read-only adapters.
- Pin every field to an existing P10/P12/P13/P14 read-only source, or mark it
  `unavailable`/`unknown` with a reason.

Explicitly **out of scope** for all of P15:
- No automated or manual repair actions.
- No restart, redeploy, or scaling actions.
- No tenant business data viewing (orders, payments, invoices, customers).
- No tenant or user impersonation.
- No mutation / write endpoints.
- No migrations.
- No new observability infrastructure (reuse P13/P14 signals only).

P15 is a **read-only triage surface** layered on existing signals, not a control
plane.

---

## 2. Personas / Roles

| Role | Access in P15 | Notes |
|------|---------------|-------|
| **Super Admin** (identity-only, global) | Full read-only triage: all P13 ops signals, P10 tenant/system summaries, P14 DB live probe, P12 diagnostic concepts. | The only role permitted to enter the platform admin incident-triage surface for cross-cutting signals. |
| **Support Operator** | Narrower read-only set: support-bundle/handoff concepts and tenant health summaries they are entitled to. Must NOT see raw ops internals (DB pool, noisy-neighbor) beyond what P12 already grants. | Strictly narrower than Super Admin. Entitlement enforced by existing P10/P12 guards. |
| **Engineering Operator** | Read-only ops internals (P13 ops signals, P14 DB probe) for root-cause handoff. | Read-only; no mutation. |

**Boundary rule (non-negotiable):** **tenant-contextual admin is NOT permitted to
enter the P15 incident-triage surface.** Only identity-only (global) platform
operators may triage. A super admin who has selected a tenant context must be
denied, exactly as P10/P13 enforce. This prevents a tenant-scoped actor from
reading cross-tenant platform signals.

Role semantics are deferred to the existing P10 guard / permission matrix; P15
adds no new auth, RBAC, or session concepts.

---

## 3. Incident Triage Workflow

The triage workflow is a **read-only state machine**. Every step is observational;
no step executes a side effect beyond the existing best-effort ops audit event
already written by P13.

1. **Detect** -- An operator observes a platform anomaly signal (e.g. P13 DB
   status `degraded`/`unhealthy`, an `ops_access_denied` spike, or a P10 tenant
   health summary showing `unknown`/`unhealthy`). P15 surfaces these existing
   signals; it does not generate new ones.
2. **Classify** -- The operator (aided by a runbook hint) labels the incident as
   one of: `database`, `system`, `api`, `tenant_health`, or `support_issue`. The
   classification is a **suggestion/label stored in the snapshot metadata**, never
   an automated action.
3. **Inspect** -- The operator opens a read-only `IncidentTriageSnapshot` that
   aggregates the relevant P10/P13/P14 read-only sources for the moment of
   triage. No tenant business records.
4. **Explain** -- The snapshot and UI must display `unavailable_reason` and
   `degraded_reason` wherever a source is missing or degraded (carrying forward
   the P13/P14 reason fields). The operator must always be able to tell *why* a
   field is empty.
5. **Handoff** -- The operator generates an `IncidentHandoffSummary` (redacted,
   counts/paths/statuses only) to pass to support or engineering. No credentials,
   no payloads, no tenant business data.
6. **Close** -- The operator records a **suggested conclusion** (free-text note,
   classification, suggested owner). Closing performs **no repair action**; it is
   a labeled observation. Any write required for persistence is deferred to a
   separate, separately-approved phase.

---

## 4. Data Contracts (for P15-B implementation)

These are the contract shapes P15-B will implement as read-only adapters. All are
`extra="forbid"` on input, all nullable-totals follow P13/P14 source-status
semantics. Defined here only; no runtime code in P15-A.

### 4.1 IncidentSignal

A single observed anomaly signal drawn from an existing source.

| Field | Type | Source | Notes |
|-------|------|--------|-------|
| `signal_id` | str | derived (ephemeral) | Stable within one snapshot; not persisted. |
| `kind` | Literal `database|system|api|tenant_health|support_issue` | classification hint | Suggested category. |
| `severity` | Literal `info|warning|degraded|unhealthy|unknown` | mapped from P13/P14 status | `unknown != healthy`. |
| `source_ref` | str | P13/P14/P10 endpoint or field name | e.g. `p13.ops.resources.database`. |
| `observed_value` | Optional[str/int] | the live value or `null` | `null` when source unavailable. |
| `source_status` | OpsSourceStatus | from P13/P14 | `available|unavailable|unknown`. |
| `unavailable_reason` | Optional[str] | from P13/P14 reason fields | Visible to operator. |
| `degraded_reason` | Optional[str] | derived when status is `degraded`/`unhealthy` | Visible to operator. |
| `observed_at` | datetime | from source `generated_at` | UTC ISO-8601 freshness. |

### 4.2 IncidentClassification

The operator-assigned label. Suggestion only.

| Field | Type | Notes |
|-------|------|-------|
| `category` | Literal `database|system|api|tenant_health|support_issue` | Required. |
| `confidence` | Literal `low|medium|high` | Operator's confidence. |
| `suggested_owner` | Literal `support|engineering|dba|platform` | Handoff target hint. |
| `notes` | Optional[str] | Free text, redacted before any handoff. |

### 4.3 IncidentRunbookHint

A static, doc-driven hint mapping a signal/category to a triage checklist.

| Field | Type | Notes |
|-------|------|-------|
| `category` | Literal (as above) | Key. |
| `checklist` | list[str] | Read-only observation steps. **No action steps.** |
| `do_not` | list[str] | Explicit prohibitions (no repair, no impersonation, no business query). |
| `handoff_to` | Literal `support|engineering|dba|platform` | Suggested owner. |

Runbook hints are authored in docs/config, not generated from tenant data.

### 4.4 IncidentTriageSnapshot

The aggregated read-only view at triage time.

| Field | Type | Source |
|-------|------|--------|
| `snapshot_id` | str | ephemeral |
| `generated_at` | datetime | UTC ISO-8601 |
| `overall_status` | Literal `healthy|degraded|unhealthy|unknown` | derived from signals; `unknown != healthy` |
| `signals` | list[IncidentSignal] | aggregated P10/P13/P14 |
| `database_probe` | Optional[DatabaseHealth] | P14 live DB probe (latency/pool/status) |
| `system_health` | Optional[SystemHealth] | P10 (stub today) |
| `tenant_health_samples` | Optional[list[TenantSummary]] | P10, **counts/status only, no business records** |
| `degraded_reason` | Optional[str] | why overall is degraded, if so |
| `unavailable_reason` | Optional[str] | why a primary source is missing |
| `graceful_degraded` | bool | true when snapshot was assembled despite a source failure |

On any source failure the snapshot must still return (`graceful_degraded=true`)
with the failing component marked `unknown`/`unavailable` and a reason -- never a
500 with no explanation, and never a fabricated `healthy`/`0`.

### 4.5 IncidentHandoffSummary

The redacted package handed to support/engineering.

| Field | Type | Notes |
|-------|------|-------|
| `summary_id` | str | ephemeral |
| `created_at` | datetime | UTC ISO-8601 |
| `classification` | IncidentClassification | operator label |
| `signals` | list[IncidentSignal] | redacted (counts/paths/statuses) |
| `runbook_hint` | Optional[IncidentRunbookHint] | doc-driven checklist |
| `redacted` | bool | always true in P15; metadata is allowlisted |
| `sensitive_keys_dropped` | int | count of redacted keys (diagnostic only) |

No raw payloads, credentials, DSN, host/port, or tenant business records.

---

## 5. Field Source Map (P15-B may only read these)

P15 fields must be sourced exclusively from existing **read-only** platform
endpoints/helpers. Anything without a real source is `unavailable`/`unknown` with
a reason -- never fabricated.

| P15 field | Allowed source | Fallback when missing |
|-----------|----------------|------------------------|
| DB latency/pool/status | P14 `_database_health` (live `SELECT 1` + engine pool) | `status=unhealthy`, latency/pool `null`, reason set |
| Error-rate / slow-route signals | P13 `/ops/errors`, `/ops/slow-routes` | `source_status=unavailable`, `unavailable_reason` from P13 |
| Noisy-neighbor signals | P13 `/ops/noisy-neighbors` | empty list + `unavailable_reason` |
| Resource (queue/cpu/mem/disk) | P13 `/ops/resources` (queue/cpu/mem/disk still `null`) | component `null` ("Not instrumented") |
| System health | P10 `get_system_health` (stub today) | `overall_status=unknown`, reason set |
| Tenant summaries/health | P10 tenant summary/health (status/counts only) | `null`/`unknown`; **no business records ever** |
| Support diagnostic concepts | P12 support console diagnostics/bundle (read-only) | narrower for support operator |

**Forbidden sources:** tenant business tables (orders, payments, invoices,
customers), raw request/response bodies, credentials, connection strings,
migration history, audit-log raw payloads.

---

## 6. Security Boundary

- **Identity-only super_admin** required to enter the platform incident-triage
  surface (P10 guard). Tenant-contextual admin denied.
- **Support operator** read scope is **strictly narrower** than super admin
  (P12 entitlements); support operators must not see raw DB pool / noisy-neighbor
  internals beyond what P12 already grants.
- **No raw sensitive payloads.** Redaction allowlist (P10 `redact_metadata`
  pattern) applies to all snapshot/handoff metadata.
- **No tenant business records** anywhere in P15.
- **No credentials, DSN, host/port, or connection-string exposure.** The P14
  `pool.status()` raw string is parsed server-side and never serialized (same
  rule as P14).
- **No write endpoints** in P15-B unless granted by a separate later approval.
- **No migrations** in P15-B.
- All P15 endpoints are **GET-only** (read-only) in P15-B.

---

## 7. P15-B Entry Gate

P15-B is permitted to implement **only a read-only API skeleton + snapshot
adapter**: the data contracts in section 4, wired to the sources in section 5,
behind the identity-only guard in section 6, with redaction and graceful
degradation.

P15-B **must not** implement:
- Any repair / restart / redeploy / scaling action.
- Any tenant or user impersonation.
- Any tenant business-data query (orders, payments, invoices, customers).
- Any migration or alembic change.
- Any auth / RBAC / session rewrite.
- Any write/mutation endpoint (POST/PUT/PATCH/DELETE) unless separately approved.
- Any new dependency on product/business modules.

P15-B must reuse P10/P12/P13/P14 read-only helpers; it must not create new
observability infrastructure or new data sources.

---

## 8. Acceptance Criteria

P15-B/P15-C are accepted only when all of the following hold (12+):

1. `unknown != healthy`: an unknown source yields `unknown`, never `healthy`.
2. `null != zero`: an unavailable count is `null`, never `0`.
3. Every `unavailable` field carries a visible `unavailable_reason`.
4. Every `degraded`/`unhealthy` field carries a visible `degraded_reason` (or maps
   from the underlying status).
5. Tenant-contextual admin is denied entry (401/403) on every P15 endpoint.
6. Support operator scope is strictly narrower than super admin (asserted in
   tests).
7. Handoff summary contains **no** sensitive keys (redaction allowlist enforced).
8. Handoff summary contains **no** tenant business records.
9. Snapshot assembly is **graceful-degraded**: a source failure yields
   `graceful_degraded=true` with reasons, not a bare 500 or fabricated data.
10. No mutation controls exist anywhere in P15 UI/API (GET-only; no action
    buttons).
11. No new migrations, no auth/RBAC/session changes, no payment/billing, no
    tenancy changes, no product business scope.
12. No credentials/DSN/host/port leak in any P15 response (content scan).
13. Freshness (`observed_at`/`generated_at`) is present on every signal/snapshot.
14. Runbook hints contain **observation steps only**; every `do_not` entry is
    honored (no repair/impersonation/business-query capability exists).

---

## 9. Counterexamples (must fail or be rejected)

These implementations/behaviors must be rejected by P15-B/C tests or review:

1. A P15 endpoint that performs a write (POST/PUT/PATCH/DELETE) -- rejected
   (405/forbidden).
2. A snapshot that fabricates `overall_status="healthy"` when a source is
   unknown/unavailable -- rejected.
3. A field that returns `0` instead of `null` when its source is unavailable --
   rejected.
4. A handoff summary that includes a tenant order/payment/invoice/customer record
   -- rejected.
5. A response that exposes DB host, port, DSN, or credentials -- rejected.
6. A `pool.status()` raw string serialized to the client -- rejected (must be
   parsed to counts only).
7. A tenant-contextual super admin successfully entering the triage surface --
   rejected (must 401/403).
8. A support operator reading DB pool/noisy-neighbor internals beyond P12 scope --
   rejected.
9. A "repair"/"restart"/"impersonate" action endpoint or button -- rejected.
10. A migration or alembic revision introduced by P15-B -- rejected.
11. An auth/RBAC/session rewrite introduced by P15-B -- rejected.
12. A snapshot that 500s with no `graceful_degraded`/reason on a single source
    failure -- rejected.
13. A runbook hint that contains a concrete repair/action step -- rejected
   (observation only).
14. A P15 field sourced from tenant business tables or raw audit payloads --
   rejected.

---

## 10. Test Plan Estimate (P15-B / P15-C)

Approximate scope (final counts set at P15-B/C):

- **Backend schema/contract tests** (~25-35): source_status consistency
  (`available`+int, `unavailable`+null, reject `unknown`+int), `extra="forbid"`,
  graceful-degraded shape, redaction allowlist, freshness presence.
- **Route guard tests** (~15-20): identity-only super admin allowed; tenant-
  contextual denied; support operator narrower scope; GET-only (POST/PUT/DELETE
  -> 405); access-denied audit written.
- **Redaction tests** (~10-15): no sensitive keys (host/port/DSN/credentials),
  no raw `pool.status()`, no tenant business records, handoff `redacted=true`.
- **Frontend render tests** (~15-25): unknown != healthy (gray), null != 0 (N/A),
  unavailable reason visible, degraded reason visible, no mutation controls, no
  business fields, graceful-degraded rendering, snapshot loading/error states.
- **Forbidden path tests** (~10): assert no backend product/tenant/migration/
  payment/auth paths touched; no write endpoints; lockfile/migration absent.

Estimated total: ~75-105 tests across P15-B/C, all read-only/scope/redaction
focused.

---

## Out of Scope Reminder

This is P15-A. It ships **docs + ledger only**. There is no runtime code, no
backend, no frontend, no migration, no test code, and no dependency change in
this phase. P15-B begins only after this contract is accepted.
