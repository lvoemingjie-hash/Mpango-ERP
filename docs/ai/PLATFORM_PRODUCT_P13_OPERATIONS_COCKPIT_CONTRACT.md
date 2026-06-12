# P13 Operations Observability Cockpit Contract

**Phase:** P13-A-R1
**Status:** Contract/design/test-plan only -- no runtime code, no migrations, no API handlers, no frontend UI
**Date:** 2026-06-12
**Base:** `origin/platform-dev` at `51cfb41` (P12-D merge)
**Branch:** `codex/platform-p13a-operations-cockpit-contract-2026-06-12`
**Author:** Platform product boundary analysis

---

## 1. Goal

The P13 Operations Observability Cockpit extends the P11 read-only platform cockpit with system-wide and tenant-aware operational insight. It surfaces error rates, slow routes, queue/DB/resource health, and noisy-neighbor signals so that platform operators can detect, triage, and correlate operational issues without leaving the cockpit.

### Core Principles

- **Read-only by default.** All P13 endpoints return diagnostic data. The only writes are audit events.
- **No new observability infrastructure.** P13 consumes data already produced by the application (logs, DB metadata, connection pools, queue state). It does not introduce a metrics pipeline, tracing backend, or time-series database.
- **No raw sensitive payloads.** Passwords, tokens, secrets, cookies, card numbers, and raw business payloads are never exposed in operational views.
- **No tenant business data mutation.** Operational views are strictly diagnostic.
- **Unknown is not healthy.** When a data source is unavailable, P13 surfaces `unknown` distinctly -- never fabricates `healthy` or `0`.
- **Tenant-aware but not tenant-bypassing.** P13 can show tenant-scoped operational signals (e.g., error rates per tenant) but never impersonates or enters a tenant session.

### Alignment

- Inherits all constraints from `PLATFORM_PRODUCT_SECURITY_BOUNDARY.md`.
- Inherits all data contract shapes from `PLATFORM_PRODUCT_CONTRACTS.md` (P10-A-R1).
- Inherits permission model from `PLATFORM_PRODUCT_PERMISSION_MATRIX.md`.
- Inherits frontend boundary rules from `PLATFORM_PRODUCT_P11_FRONTEND_BOUNDARY.md`.
- Extends P11 read-only cockpit and P12 support console with system-level observability.
- Follows the P13 roadmap entry in `PLATFORM_PRODUCT_ROADMAP.md`.

---

## 2. Personas

### Super Admin

- Full platform owner (Jeff or explicitly trusted operator).
- Can view system health, error rates, slow routes, resource summaries, and tenant-scoped operational signals.
- Can view noisy-neighbor analysis (which tenants consume disproportionate resources).
- Must authenticate via identity-only (global) `super_admin` Bearer token (P11-B0-R1).
- All views generate audit events.

### Engineering Operator

- Restricted platform role focused on system health and incident response.
- Can view system health, error rates, slow routes, and resource summaries.
- Can view tenant-scoped error rates but cannot see raw tenant business data.
- Cannot change tenant lifecycle state, platform configuration, or billing.
- **P13-A status:** contract only. Role assignment mechanism is deferred to implementation.

### Support Operator

- Can view system health as context for support sessions.
- Cannot view noisy-neighbor analysis or cross-tenant resource breakdowns.
- **P13-A status:** contract only. Scoped to system-level read-only views only.

### Explicitly Denied

- **Product Admin / Tenant-contextual admin:** Must not access P13 operational endpoints even if the tenant-contextual token carries `super_admin` role.
- **Tenant users:** No tenant user may access platform operational features.

---

## 3. Operational Workflows

### Workflow 1: System Health Overview

1. Actor navigates to `/platform/ops/health`.
2. System displays `SystemHealth` (already defined in P10-A-R1) enriched with P13 extensions.
3. P13 adds: error rate breakdown, slow request count, resource pressure indicators, and a tenant-impact summary.
4. System writes a `ops_health_view` audit event.

### Workflow 2: Error Rate Analysis

1. Actor navigates to `/platform/ops/errors`.
2. System displays `ErrorRateSummary` -- aggregated error counts by class, route, and tenant over configurable time windows.
3. Errors are redacted: only error class, count, route name, and correlation IDs are shown.
4. No raw request/response bodies, stack traces with tenant data, or PII.
5. System writes an `ops_error_analysis_view` audit event.

### Workflow 3: Slow Route Analysis

1. Actor navigates to `/platform/ops/slow-routes`.
2. System displays `SlowRouteSummary` -- routes with latency exceeding thresholds, grouped by route and latency bucket.
3. No full URLs with query params, no request bodies, no tenant-specific business context.
4. System writes an `ops_slow_route_view` audit event.

### Workflow 4: Resource Health Summary

1. Actor navigates to `/platform/ops/resources`.
2. System displays `ResourceHealthSummary` -- DB connection pools, queue depth, memory/CPU pressure, and disk status.
3. All values are summaries or statuses, never raw internals.
4. System writes an `ops_resource_view` audit event.

### Workflow 5: Noisy-Neighbor Detection

1. Actor navigates to `/platform/ops/noisy-neighbors`.
2. System displays `NoisyNeighborSummary` -- tenants with disproportionate error rates, slow routes, or resource consumption.
3. Only super_admin and engineering_operator may access this view.
4. Data is aggregated: tenant ID + error count + slow route count. No raw business payloads.
5. System writes an `ops_noisy_neighbor_view` audit event.

### Workflow 6: Tenant-Scoped Operational View

1. Actor selects a tenant from the operational dashboard.
2. System displays tenant-scoped error rates, slow routes affecting that tenant, and resource indicators.
3. Follows the same redaction and audit rules as system-level views.
4. System writes an `ops_tenant_view` audit event with `tenant_id` set.

---

## 4. Data Contracts

### 4.1 ErrorRateSummary

```
ErrorRateSummary {
  window_minutes       : integer     NOT NULL   -- aggregation window (e.g., 5, 15, 60)
  total_errors         : integer     NOT NULL   -- >= 0
  error_classes        : ErrorClassBreakdown[] NOT NULL
  top_routes           : RouteErrorBreakdown[] NOT NULL
  top_tenants          : TenantErrorBreakdown[] NULLABLE   -- null if actor lacks cross-tenant scope
  generated_at         : timestamp   NOT NULL   -- UTC ISO-8601
}
```

#### ErrorClassBreakdown

```
ErrorClassBreakdown {
  error_class          : string      NOT NULL   -- e.g., "ValidationError", "ConnectionError"
  count                : integer     NOT NULL   -- >= 0
  percentage           : float       NOT NULL   -- 0.0 to 100.0
  sample_correlation_ids : string[]  NOT NULL   -- up to 5 correlation IDs for drill-down
}
```

#### RouteErrorBreakdown

```
RouteErrorBreakdown {
  route                : string      NOT NULL   -- e.g., "/api/v1/orders", NOT full URL with query params
  error_count          : integer     NOT NULL   -- >= 0
  latency_bucket_ms    : integer     NULLABLE   -- p95 latency for this route, null if unavailable
  sample_correlation_ids : string[]  NOT NULL   -- up to 5
}
```

#### TenantErrorBreakdown

```
TenantErrorBreakdown {
  tenant_id            : uuid        NOT NULL   -- tenant identifier
  tenant_name          : string      NULLABLE   -- display name if available
  error_count          : integer     NOT NULL   -- >= 0
  top_error_class      : string      NULLABLE   -- most frequent error class for this tenant
}
```

#### Counterexamples (Rejected)

1. `ErrorRateSummary` containing raw request body or stack trace -- redaction violation.
2. `ErrorClassBreakdown` with more than 5 `sample_correlation_ids` -- must cap at 5.
3. `TenantErrorBreakdown` accessible to support_operator -- cross-tenant scope denied.
4. `ErrorRateSummary` with `window_minutes: 0` -- invalid window.

### 4.2 SlowRouteSummary

```
SlowRouteSummary {
  window_minutes       : integer     NOT NULL   -- aggregation window
  threshold_ms         : integer     NOT NULL   -- what counts as "slow" (e.g., 1000)
  total_slow_requests  : integer     NOT NULL   -- >= 0
  routes               : SlowRouteEntry[] NOT NULL
  generated_at         : timestamp   NOT NULL   -- UTC ISO-8601
}
```

#### SlowRouteEntry

```
SlowRouteEntry {
  route                : string      NOT NULL   -- route path only
  request_count        : integer     NOT NULL   -- >= 0
  p50_ms               : integer     NULLABLE   -- null if unavailable
  p95_ms               : integer     NULLABLE   -- null if unavailable
  p99_ms               : integer     NULLABLE   -- null if unavailable
  sample_correlation_ids : string[]  NOT NULL   -- up to 5
}
```

#### Counterexamples (Rejected)

1. `SlowRouteEntry` with full URL including query parameters -- must strip query params.
2. `SlowRouteEntry` containing request body or response body -- redaction violation.
3. `SlowRouteSummary` with `threshold_ms: 0` -- invalid threshold.

### 4.3 ResourceHealthSummary

```
ResourceHealthSummary {
  database             : DatabaseHealth    NOT NULL
  queue                : QueueHealth       NULLABLE   -- null if no queue configured
  memory               : ComponentHealth   NULLABLE   -- null if not instrumented
  cpu                  : ComponentHealth   NULLABLE   -- null if not instrumented
  disk                 : ComponentHealth   NULLABLE   -- null if not instrumented
  generated_at         : timestamp         NOT NULL   -- UTC ISO-8601
}
```

#### DatabaseHealth

```
DatabaseHealth {
  status               : enum        NOT NULL   -- healthy | degraded | unhealthy | unknown
  connection_pool_active : integer    NULLABLE   -- active connections, null if unavailable
  connection_pool_max  : integer     NULLABLE   -- pool max, null if unavailable
  connection_pool_idle : integer     NULLABLE   -- idle connections, null if unavailable
  latency_ms           : integer     NULLABLE   -- average query latency, null if unavailable
}
```

#### QueueHealth

```
QueueHealth {
  status               : enum        NOT NULL   -- healthy | degraded | unhealthy | unknown
  depth                : integer     NULLABLE   -- current queue depth, null if unavailable
  worker_count         : integer     NULLABLE   -- active workers, null if unavailable
  oldest_pending_age_s : integer     NULLABLE   -- age of oldest pending job in seconds, null if unavailable
}
```

#### ComponentHealth

```
ComponentHealth {
  status               : enum        NOT NULL   -- healthy | degraded | unhealthy | unknown
  usage_percent        : float       NULLABLE   -- 0.0 to 100.0, null if unavailable
  detail               : string      NULLABLE   -- human-readable note (e.g., "Memory usage within normal range")
}
```

#### Counterexamples (Rejected)

1. `DatabaseHealth` with `status: "healthy"` but `connection_pool_active: null` -- inconsistent. If metrics unavailable, status must be `"unknown"`.
2. `ResourceHealthSummary` exposing database host, port, or credentials -- security violation.
3. `ComponentHealth.usage_percent` > 100.0 -- invalid range.

### 4.4 NoisyNeighborSummary

```
NoisyNeighborSummary {
  window_minutes       : integer                NOT NULL
  tenants              : NoisyNeighborEntry[]   NOT NULL   -- sorted by impact descending
  generated_at         : timestamp              NOT NULL   -- UTC ISO-8601
}
```

#### NoisyNeighborEntry

```
NoisyNeighborEntry {
  tenant_id            : uuid        NOT NULL
  tenant_name          : string      NULLABLE
  error_count          : integer     NOT NULL   -- >= 0
  slow_route_count     : integer     NOT NULL   -- >= 0
  impact_score         : float       NOT NULL   -- 0.0 to 1.0, derived from error rate + slow routes
  top_error_class      : string      NULLABLE
  top_slow_route       : string      NULLABLE
}
```

#### Counterexamples (Rejected)

1. `NoisyNeighborEntry` containing raw tenant business data -- only counts and route names allowed.
2. `NoisyNeighborSummary` accessible to support_operator -- restricted to super_admin and engineering_operator.
3. `NoisyNeighborEntry` with `impact_score` > 1.0 or < 0.0 -- invalid range.
4. `NoisyNeighborEntry` listing other tenants' raw order or payment counts -- only error/slow-route counts.

### 4.5 OpsAuditEvent

Extends `PlatformAuditEvent` from P10-A-R1 with P13-specific fields.

```
OpsAuditEvent extends PlatformAuditEvent {
  -- All fields from PlatformAuditEvent (event_id, actor_id, actor_role, tenant_id,
  --   scope, action, reason, result, metadata_redacted, correlation_id, created_at)
  -- scope is always "operations" for P13 audit events

  -- Additional ops-specific fields in metadata_redacted:
  view_type           : string      -- "health" | "errors" | "slow_routes" | "resources" | "noisy_neighbors" | "tenant"
  target_tenant_id    : uuid        -- only when view_type = "tenant"
  window_minutes      : integer     -- aggregation window viewed
}
```

#### Ops Audit Action Enum

| Action | When | Scope |
|--------|------|-------|
| `ops_health_view` | Actor views system health dashboard. | `operations` |
| `ops_error_analysis_view` | Actor views error rate analysis. | `operations` |
| `ops_slow_route_view` | Actor views slow route analysis. | `operations` |
| `ops_resource_view` | Actor views resource health summary. | `operations` |
| `ops_noisy_neighbor_view` | Actor views noisy-neighbor analysis. | `operations` |
| `ops_tenant_view` | Actor views tenant-scoped operational data. | `operations` |
| `ops_access_denied` | Actor denied access (wrong role, unassigned tenant). | `operations` |

#### Counterexamples (Rejected)

1. `ops_health_view` with `scope: "tenant"` -- ops events must use `scope: "operations"`.
2. `OpsAuditEvent` for a tenant-contextual token accessing ops endpoints -- must be `denied`.
3. `ops_noisy_neighbor_view` by support_operator -- must be denied.

---

## 5. Source Map

### Source Zones (P13-specific)

| Zone | Description | P13-A Availability |
|------|-------------|-------------------|
| `P10 platform contracts` | SystemHealth as exposed by P10 read-only APIs | `available_now` |
| `P12 support diagnostics` | Error/slow-route/job summaries from P12 diagnostic categories | `available_now` |
| `application logs` | Error logs, route timing, correlation IDs | `telemetry_required` -- partially available via P12 diagnostic sources |
| `runtime metrics` | DB connections, queue depth, CPU, memory, disk | `telemetry_required` -- not yet instrumented |
| `derived operational snapshot` | Aggregated error rates, slow route summaries, noisy-neighbor scores | `manual_or_unknown` -- must be computed |

### ErrorRateSummary Source Map

| Field | Source | Availability | Fallback |
|-------|--------|-------------|----------|
| `window_minutes` | Configuration | Always | N/A |
| `total_errors` | Application log aggregation | `telemetry_required` | `0` with `source_status: "unavailable"` |
| `error_classes` | Log error class extraction | `telemetry_required` | Empty array with status note |
| `top_routes` | Route + error correlation | `telemetry_required` | Empty array with status note |
| `top_tenants` | Tenant + error correlation | `telemetry_required` | `null` (requires cross-tenant scope) |
| `generated_at` | System timestamp | Always | N/A |

### SlowRouteSummary Source Map

| Field | Source | Availability | Fallback |
|-------|--------|-------------|----------|
| `window_minutes` | Configuration | Always | N/A |
| `threshold_ms` | Configuration | Always | N/A |
| `total_slow_requests` | Latency log aggregation | `telemetry_required` | `0` with status note |
| `routes` | Route latency extraction | `telemetry_required` | Empty array with status note |
| `generated_at` | System timestamp | Always | N/A |

### ResourceHealthSummary Source Map

| Field | Source | Availability | Fallback |
|-------|--------|-------------|----------|
| `database` | SQLAlchemy pool stats + DB connectivity | `available_now` (pool stats) / `telemetry_required` (latency) | `status: "unknown"`, null counts |
| `queue` | Celery/Redis queue inspection | `telemetry_required` | `null` (no queue configured) |
| `memory` | Runtime metrics | `telemetry_required` | `null` (not instrumented) |
| `cpu` | Runtime metrics | `telemetry_required` | `null` (not instrumented) |
| `disk` | Runtime metrics | `telemetry_required` | `null` (not instrumented) |
| `generated_at` | System timestamp | Always | N/A |

### NoisyNeighborSummary Source Map

| Field | Source | Availability | Fallback |
|-------|--------|-------------|----------|
| `window_minutes` | Configuration | Always | N/A |
| `tenants` | Cross-tenant error + latency aggregation | `telemetry_required` | Empty array with status note |
| `generated_at` | System timestamp | Always | N/A |

### Degraded/Unknown Behavior

When a data source is unavailable:

1. The corresponding field must be `null` or the parent object must have `status: "unknown"`.
2. `total_errors: 0` is NOT the same as "no data available." If the source is uninstrumented, the response must indicate `unavailable`, not `0`.
3. UI must display uninstrumented sources distinctly: gray indicator + "Data unavailable" or "Not instrumented."
4. **Counterexample:** An unavailable data source must NEVER produce `status: "healthy"`, `total_errors: 0` (when unknown), or `usage_percent: 0.0` (when unknown).

---

## 6. Permission Matrix

### Role-Action Matrix for Operations Cockpit

| Action | super_admin (identity-only) | engineering_operator | support_operator | tenant-contextual admin |
|--------|-----------------------------|---------------------|-----------------|------------------------|
| View system health overview | **Allow** + audit | **Allow** + audit | **Allow** + audit | **Deny** |
| View error rate analysis | **Allow** + audit | **Allow** + audit | **Deny** | **Deny** |
| View slow route analysis | **Allow** + audit | **Allow** + audit | **Deny** | **Deny** |
| View resource health summary | **Allow** + audit | **Allow** + audit | **Deny** | **Deny** |
| View noisy-neighbor analysis | **Allow** + audit | **Allow** + audit | **Deny** | **Deny** |
| View tenant-scoped operational data | **Allow** + audit | **Allow** + audit | **Deny** | **Deny** |
| Access ops cockpit at all | **Allow** | **Allow** | **Allow** (health only) | **Deny** |

### Identity-Only Enforcement

Per P11-B0-R1 resolution:

- **Only identity-only (global) `super_admin` Bearer tokens** are accepted for P13 operational cockpit access.
- A **tenant-contextual token** with `super_admin` role is **NOT sufficient** -- must be **denied**.
- The `X-Platform-Operator` header remains available for server/operator contexts but is not used in the browser.

### Counterexamples (Rejected)

1. Support operator viewing error rate analysis -- must deny with audit event.
2. Tenant-contextual admin accessing any ops endpoint -- must deny with 403.
3. Engineering operator viewing raw tenant business data through ops views -- not possible; ops views only expose counts and statuses.
4. Any actor modifying system state through the ops cockpit -- no write operations allowed.

---

## 7. Redaction Policy

### 7.1 Always Redacted (Same as P12 Section 7.1)

Passwords, tokens, secrets, cookies, card/payment identifiers, raw auth payloads -- never included.

### 7.2 Operational Data Redaction Rules

| Category | Allowed Form | Forbidden Form |
|----------|-------------|----------------|
| Error details | Error class name + count + correlation IDs | Raw request/response body, stack trace with tenant data |
| Route details | Route path (e.g., `/api/v1/orders`) | Full URL with query params, request body |
| Tenant breakdown | Tenant ID + error/slow-route counts | Raw order/invoice/payment records, user details |
| Resource metrics | Status + pool counts + percentages | DB host/port/credentials, internal connection strings |
| Queue details | Depth + worker count + oldest age | Job payloads, job arguments, retry details |
| Latency | p50/p95/p99 in milliseconds | Individual request/response pairs |

### 7.3 Safe to Include

| Category | Examples |
|----------|---------|
| Error class names | `"ValidationError"`, `"ConnectionError"`, `"TimeoutError"` |
| Route paths | `"/api/v1/orders"`, `"/api/v1/inventory"` |
| Health statuses | `"healthy"`, `"degraded"`, `"unhealthy"`, `"unknown"` |
| Timestamps | All UTC ISO-8601 timestamps |
| Correlation IDs | UUIDs for cross-referencing |
| Counts and percentages | Error counts, request counts, pool utilization % |

---

## 8. Audit Requirements

### 8.1 Required Audit Event Fields

Every P13 audit event must include:

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `event_id` | uuid | YES | Unique event identifier |
| `actor_id` | string | YES | Platform operator identity |
| `actor_role` | enum | YES | `super_admin` or `engineering_operator` |
| `tenant_id` | uuid | YES for tenant-scoped views, `null` for system views | Target tenant or null |
| `action` | string | YES | From ops audit action enum (Section 4.5) |
| `result` | enum | YES | `allowed` or `denied` |
| `scope` | enum | YES | Always `"operations"` for P13 events |
| `timestamp` | timestamp | YES | UTC ISO-8601 |
| `view_type` | string | YES | From view type enum |
| `window_minutes` | integer | YES | Aggregation window viewed |

### 8.2 Audit Event Scenarios

| Scenario | Action | Result | Audit Written |
|----------|--------|--------|---------------|
| Actor views system health | `ops_health_view` | `allowed` | YES |
| Actor views error analysis | `ops_error_analysis_view` | `allowed` | YES |
| Actor views slow routes | `ops_slow_route_view` | `allowed` | YES |
| Actor views resources | `ops_resource_view` | `allowed` | YES |
| Actor views noisy neighbors | `ops_noisy_neighbor_view` | `allowed` | YES |
| Actor views tenant ops data | `ops_tenant_view` | `allowed` | YES |
| Support operator views errors | `ops_access_denied` | `denied` | YES |
| Tenant-contextual token accesses ops | `ops_access_denied` | `denied` | YES |

---

## 9. P13-B Implementation Gate

P13-B (operations cockpit API implementation) may only begin after P13-A is accepted and merged.

### 9.1 API Constraints

- The API may read operational data from existing P10/P12 sources.
- The API may create `OpsAuditEvent` records (audit event creation is the only allowed write).
- No mutations to tenant business data, auth, RBAC, session, tenancy, or payment state.
- No database migrations unless a dedicated CTO gate approves.
- No new observability infrastructure -- use existing logs, DB metadata, and runtime signals.

### 9.2 Frontend Route Proposal

| Route | Component | Description |
|-------|-----------|-------------|
| `/platform/ops/health` | `OpsHealthPage` | System health with P13 extensions |
| `/platform/ops/errors` | `OpsErrorPage` | Error rate analysis |
| `/platform/ops/slow-routes` | `OpsSlowRoutesPage` | Slow route analysis |
| `/platform/ops/resources` | `OpsResourcesPage` | Resource health summary |
| `/platform/ops/noisy-neighbors` | `OpsNoisyNeighborsPage` | Noisy-neighbor detection |

### 9.3 P13-B Entry Checklist

Before P13-B implementation begins:

- [ ] P13-A contract document accepted by CTO/product owner.
- [ ] P13-A ledger recorded and merged to `platform-dev`.
- [ ] P13 data contracts reviewed against P10-A and P12 contracts for consistency.
- [ ] Redaction policy reviewed against security boundary.
- [ ] Permission matrix reviewed against P11-B0-R1 identity-only enforcement.
- [ ] No runtime code changes in P13-A (docs/ledger only).
- [ ] P12 batch fully merged and stable on `platform-dev`.
- [ ] Data source availability assessed (what can be read now vs. needs instrumentation).

### 9.4 P13-C Frontend Gate

P13-C (frontend ops UI) may not begin until:

- P13-B API endpoints are implemented.
- Contract tests prove all data shapes match this document.
- Permission tests prove identity-only enforcement.
- Redaction tests prove sensitive fields are removed.
- Audit tests prove every view writes an audit event.
- Unknown/degraded state tests prove correct rendering.

---

## 10. Acceptance Criteria and Counterexamples

### 10.1 Acceptance Criteria

| # | Criterion | Validation |
|---|-----------|------------|
| AC-01 | Tenant-contextual token denied for all P13 ops endpoints | API returns 403, audit event with `result: "denied"` |
| AC-02 | Error rate summary redacts raw request/response bodies | Summary scan finds zero raw payloads |
| AC-03 | Slow route entries show route path only, no query params | Entry scan finds no `?` or `&` in route field |
| AC-04 | Resource health shows `unknown` distinctly from `healthy` | UI displays gray indicator for unknown |
| AC-05 | Noisy-neighbor view denied for support_operator | API returns 403, audit event written |
| AC-06 | Every ops view generates an audit event | Audit log contains corresponding event |
| AC-07 | `total_errors: 0` only when data is confirmed zero, not when source is unavailable | Unavailable sources show `null` or status note |
| AC-08 | No runtime code changes in P13-A | Only docs/ai/ and ai-ledger/ files modified |
| AC-09 | No migrations in P13-A | Zero migration files in diff |
| AC-10 | No frontend UI in P13-A | Zero frontend files in diff |
| AC-11 | No auth/RBAC/session/tenancy/payment changes | Zero auth/payment/session files in diff |

### 10.2 Counterexamples (Must Be Rejected)

| # | Counterexample | Expected Rejection |
|---|---------------|-------------------|
| CE-01 | Tenant-contextual `super_admin` token accessing ops endpoints | 403 FORBIDDEN, audit event |
| CE-02 | Error summary containing raw request body `{"order_id": 123}` | Rejected by redaction filter |
| CE-03 | Slow route entry with full URL `/api/v1/orders?tenant_id=x&status=active` | Must strip to `/api/v1/orders` |
| CE-04 | `ResourceHealthSummary.database.status: "healthy"` with all null metrics | Inconsistent -- must be `"unknown"` |
| CE-05 | `ErrorRateSummary.total_errors: 0` when telemetry is uninstrumented | Must be `null` or flagged unavailable |
| CE-06 | Noisy-neighbor entry listing raw order counts per tenant | Only error/slow-route counts allowed |
| CE-07 | Support operator viewing error rate analysis | 403 FORBIDDEN |
| CE-08 | Ops audit event with `scope: "tenant"` instead of `"operations"` | Invalid scope for P13 events |
| CE-09 | P13-A branch containing runtime code changes | Rejected at merge gate |
| CE-10 | `ComponentHealth.usage_percent: 150.0` | Invalid range -- must be 0.0-100.0 or null |
| CE-11 | Queue health exposing job payloads or arguments | Redaction violation |
| CE-12 | Database health exposing host, port, or credentials | Security violation |
| CE-13 | `NoisyNeighborEntry.impact_score: 2.5` | Invalid range -- must be 0.0-1.0 |
| CE-14 | Ops cockpit providing any write/mutation capability | Architecture violation |
| CE-15 | Introducing a metrics pipeline or time-series DB in P13 | Out of scope -- use existing sources only |

### 10.3 Test Plan (P13-B Implementation)

| Category | Count (est.) | Description |
|----------|-------------|-------------|
| Error rate summary | 8 | Shape validation, redaction, empty/unavailable, window validation |
| Slow route summary | 8 | Shape validation, URL stripping, latency buckets, threshold validation |
| Resource health | 10 | DB/queue/CPU/memory/disk status, unknown behavior, null handling |
| Noisy-neighbor | 8 | Permission (super_admin only), aggregation, impact score range, redaction |
| Permission enforcement | 10 | super_admin allow, engineering_operator scope, support_operator deny, tenant-contextual deny |
| Audit events | 8 | All view types, access denied events, required fields |
| Unknown state | 6 | Unknown != healthy, null != 0, unavailable status |
| Counterexample validation | 10 | All 15 counterexamples covered in test fixtures |
| **Total estimate** | **~68** | |

---

## Scope Boundaries

This document does NOT:

- Implement API endpoints, HTTP methods, or URL patterns for operations cockpit.
- Define database migration schemas for operational data storage.
- Modify auth/RBAC/session/tenancy/payment flows.
- Implement frontend operational UI components.
- Require any code changes to `backend/`, `frontend/`, or `product-dev-recovered/`.
- Introduce a metrics pipeline, tracing backend, or time-series database.
- Change the `schema-per-tenant` isolation architecture.
- Expose raw tenant business data, credentials, or internal system details.

---

## References

- `PLATFORM_PRODUCT_PRD.md` -- P13 feature definitions
- `PLATFORM_PRODUCT_SECURITY_BOUNDARY.md` -- Operational mode rules, data redaction
- `PLATFORM_PRODUCT_CONTRACTS.md` -- P10-A-R1 data contract shapes (SystemHealth, PlatformAuditEvent)
- `PLATFORM_PRODUCT_P10_DATA_SOURCE_MAP.md` -- Source zone definitions
- `PLATFORM_PRODUCT_PERMISSION_MATRIX.md` -- Role-action permission matrix
- `PLATFORM_PRODUCT_P11_FRONTEND_BOUNDARY.md` -- Frontend boundary and identity-only enforcement
- `PLATFORM_PRODUCT_P12_SUPPORT_CONSOLE_CONTRACT.md` -- P12 diagnostic categories (error, slow routes, jobs)
- `PLATFORM_PRODUCT_ROADMAP.md` -- P13 roadmap entry
