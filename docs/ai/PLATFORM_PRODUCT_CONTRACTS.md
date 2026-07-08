# Platform Product Data Contracts

**Phase**: P10-A-R1
**Date**: 2026-06-05
**Status**: Contract-only — no backend/frontend/migration/API code
**Source map**: `PLATFORM_PRODUCT_P10_DATA_SOURCE_MAP.md` (P9-R2)

---

## 1. Purpose

These contracts define the **shape and semantics** of data that the platform layer exposes to operators, dashboards, and audit consumers. They are aligned field-by-field with the P9-R2 data source map. Every field carries its P10-A source status.

These contracts are NOT implemented yet. They exist so that:

1. Front-end and back-end teams can code against a stable interface definition.
2. Test fixtures can validate conformance without running a live system.
3. Counterexamples can be rejected mechanically.

---

## 2. Contract: TenantSummary

A **read-only** summary of a tenant's operational state for platform operator dashboards. Aligned to `PLATFORM_PRODUCT_P10_DATA_SOURCE_MAP.md` TenantSummary section.

```
TenantSummary {
  tenant_id             : uuid        NULLABLE   -- proposed_public_metadata
  tenant_name           : string      NULLABLE   -- proposed_public_metadata
  tenant_schema         : string      NULLABLE   -- available_now or proposed_public_metadata
  status                : enum        NOT NULL   -- proposed_public_metadata
  tier                  : string      NULLABLE   -- proposed_public_metadata
  created_at            : timestamp   NULLABLE   -- proposed_public_metadata
  last_activity_at      : timestamp   NULLABLE   -- tenant_aggregate_required
  user_count            : integer     NULLABLE   -- tenant_aggregate_required
  health_status         : enum        NOT NULL   -- manual_or_unknown
  recent_error_count    : integer     NULLABLE   -- telemetry_required
  support_mode_active   : boolean     NOT NULL   -- proposed_public_metadata
}
```

### Field Details

| Field | Type | Nullable | Unknown Behavior | Source Zone | P10-A Status |
|-------|------|----------|-----------------|-------------|--------------|
| `tenant_id` | uuid | Yes | `null` if platform registry not yet created | public platform metadata | `proposed_public_metadata` |
| `tenant_name` | string | Yes | `null` if platform registry not yet created | public platform metadata | `proposed_public_metadata` |
| `tenant_schema` | string | Yes | `null` if provisioning metadata not available | public platform metadata | `available_now` or `proposed_public_metadata` |
| `status` | enum | No | `"unknown"` as fallback | public platform metadata | `proposed_public_metadata` |
| `tier` | string | Yes | `null` until subscription model exists | public platform metadata | `proposed_public_metadata` |
| `created_at` | timestamp | Yes | `null` if creation metadata unavailable | public platform metadata | `proposed_public_metadata` |
| `last_activity_at` | timestamp | Yes | `null` if tenant aggregate not available | tenant schema or logs | `tenant_aggregate_required` |
| `user_count` | integer | Yes | `null` if tenant aggregate not available | tenant schema aggregate | `tenant_aggregate_required` |
| `health_status` | enum | No | `"unknown"` if health signals unavailable | derived platform snapshot | `manual_or_unknown` |
| `recent_error_count` | integer | Yes | `null` if telemetry not instrumented | application logs | `telemetry_required` |
| `support_mode_active` | boolean | No | `false` if support mode not yet implemented | public platform metadata | `proposed_public_metadata` |

### Status Enum

| Value | Meaning |
|-------|---------|
| `draft` | Tenant exists in registry but is not yet operational. |
| `active` | Tenant is operational and reachable. |
| `paused` | Tenant is temporarily paused (billing, maintenance). |
| `suspended` | Platform has suspended the tenant (abuse, policy). |
| `archived` | Tenant has been offboarded. Schema may exist for audit. |
| `unknown` | Status cannot be determined. |

### Health Status Enum

| Value | Meaning |
|-------|---------|
| `healthy` | All health signals normal. |
| `degraded` | Partial degradation detected. |
| `unhealthy` | Significant failure detected. |
| `unknown` | Health signals unavailable. |

### Counterexamples (Rejected)

1. `status` as `"deleted"` — use `"archived"`.
2. `status` as `"active"` when `health_status` is `"unknown"` — `status` and `health_status` are independent fields; this is valid. But `health_status = "healthy"` when data sources are unavailable is rejected — must be `"unknown"`.
3. `user_count` as negative integer — must be `>= 0` or `null`.
4. `recent_error_count` as negative — must be `>= 0` or `null`.
5. `support_mode_active` as `null` — must be `true` or `false`.

---

## 3. Contract: TenantHealth

A **read-only** health assessment for a single tenant. Aligned to P9-R2 TenantHealth source map.

```
TenantHealth {
  tenant_id             : uuid        NULLABLE   -- proposed_public_metadata
  tenant_schema         : string      NULLABLE   -- available_now or proposed_public_metadata
  health_status         : enum        NOT NULL   -- manual_or_unknown
  schema_status         : enum        NULLABLE   -- telemetry_required
  last_login_at         : timestamp   NULLABLE   -- tenant_aggregate_required
  activity_counters     : object      NULLABLE   -- tenant_aggregate_required
  recent_errors         : ErrorSummary[] NULLABLE -- telemetry_required
  slow_routes           : SlowRoute[] NULLABLE   -- telemetry_required
  failed_jobs           : FailedJob[] NULLABLE   -- telemetry_required
  last_health_check_at  : timestamp   NULLABLE   -- proposed_public_metadata
}

ErrorSummary {
  error_class           : string      NOT NULL   -- redacted error class name
  count                 : integer     NOT NULL   -- >= 1
  correlation_ids       : string[]    NOT NULL   -- at least 1 entry, redacted
}

SlowRoute {
  route                 : string      NOT NULL   -- route name only
  latency_bucket_ms     : integer     NOT NULL   -- >= 0
  count                 : integer     NOT NULL   -- >= 1
}

FailedJob {
  job_class             : string      NOT NULL   -- class name only
  count                 : integer     NOT NULL   -- >= 1
}
```

### Field Details

| Field | Type | Nullable | Unknown Behavior | Source Zone | P10-A Status |
|-------|------|----------|-----------------|-------------|--------------|
| `tenant_id` | uuid | Yes | `null` if registry unavailable | public platform metadata | `proposed_public_metadata` |
| `tenant_schema` | string | Yes | `null` if provisioning data unavailable | public platform metadata | `available_now` or `proposed_public_metadata` |
| `health_status` | enum | No | `"unknown"` as fallback | derived platform snapshot | `manual_or_unknown` |
| `schema_status` | enum | Yes | `null` if DB metadata unavailable | DB metadata / provisioning | `telemetry_required` |
| `last_login_at` | timestamp | Yes | `null` if aggregate unavailable | tenant schema or logs | `tenant_aggregate_required` |
| `activity_counters` | object | Yes | `null` if aggregation unavailable | tenant schema aggregates | `tenant_aggregate_required` |
| `recent_errors` | ErrorSummary[] | Yes | `null` if logs unavailable | application logs | `telemetry_required` |
| `slow_routes` | SlowRoute[] | Yes | `null` if metrics unavailable | logs/metrics/traces | `telemetry_required` |
| `failed_jobs` | FailedJob[] | Yes | `null` if job telemetry unavailable | queue/job telemetry | `telemetry_required` |
| `last_health_check_at` | timestamp | Yes | `null` if no snapshot generated | derived platform snapshot | `proposed_public_metadata` |

### Schema Status Enum

| Value | Meaning |
|-------|---------|
| `exists` | Schema exists and is reachable. |
| `unreachable` | Schema exists but DB is unreachable. |
| `migration_misaligned` | Schema migration version does not match expected. |
| `missing` | Schema does not exist. |
| `unknown` | Cannot determine status. |

### activity_counters Object Shape

```json
{
  "orders": 42,
  "inventory_changes": 15,
  "invoices": 8,
  "payments": 3,
  "sync_jobs": 1
}
```

All values are windowed counts only. Payment counts must not expose payment details. `null` object if aggregation unavailable.

### Counterexamples (Rejected)

1. `recent_errors` with raw request/response body in any field.
2. `slow_routes` with full URL including query parameters — route name only.
3. `failed_jobs` with job payload — class name and count only.
4. `health_status = "healthy"` when data sources are explicitly unavailable — must be `"unknown"`.

---

## 4. Contract: SystemHealth

A **read-only** aggregate health of the entire platform. Aligned to P9-R2 SystemHealth source map.

```
SystemHealth {
  overall_status        : enum        NOT NULL   -- manual_or_unknown
  api_status            : enum        NULLABLE   -- telemetry_required
  database_status       : enum        NULLABLE   -- telemetry_required
  database_connections  : object      NULLABLE   -- telemetry_required
  queue_status          : enum        NULLABLE   -- telemetry_required
  cpu_status            : enum        NULLABLE   -- telemetry_required
  memory_status         : enum        NULLABLE   -- telemetry_required
  disk_status           : enum        NULLABLE   -- telemetry_required
  error_rate            : number      NULLABLE   -- telemetry_required
  slow_request_count    : integer     NULLABLE   -- telemetry_required
  generated_at          : timestamp   NOT NULL   -- available_now
}
```

### Field Details

| Field | Type | Nullable | Unknown Behavior | Source Zone | P10-A Status |
|-------|------|----------|-----------------|-------------|--------------|
| `overall_status` | enum | No | `"unknown"` as fallback | derived platform snapshot | `manual_or_unknown` |
| `api_status` | enum | Yes | `null` if not instrumented | runtime metrics/logs | `telemetry_required` |
| `database_status` | enum | Yes | `null` if not instrumented | runtime metrics | `telemetry_required` |
| `database_connections` | object | Yes | `null` if not instrumented | runtime metrics | `telemetry_required` |
| `queue_status` | enum | Yes | `null` if no queue present | runtime metrics | `telemetry_required` |
| `cpu_status` | enum | Yes | `null` if not instrumented (local/dev) | runtime metrics | `telemetry_required` |
| `memory_status` | enum | Yes | `null` if not instrumented (local/dev) | runtime metrics | `telemetry_required` |
| `disk_status` | enum | Yes | `null` if not instrumented (local/dev) | runtime metrics | `telemetry_required` |
| `error_rate` | number | Yes | `null` if not instrumented | application logs/metrics | `telemetry_required` |
| `slow_request_count` | integer | Yes | `null` if not instrumented | logs/metrics/traces | `telemetry_required` |
| `generated_at` | timestamp | No | Always available | platform runtime | `available_now` |

### Component Status Enum

Applies to `api_status`, `database_status`, `queue_status`, `cpu_status`, `memory_status`, `disk_status`:

| Value | Meaning |
|-------|---------|
| `healthy` | Component operating normally. |
| `degraded` | Partial degradation (slow but functional). |
| `down` | Component unavailable. |
| `unknown` | Cannot determine status. |

### Overall Status Enum

| Value | Meaning |
|-------|---------|
| `healthy` | All instrumented components report `healthy`. |
| `degraded` | At least one component reports `degraded`, none `down`. |
| `down` | At least one component reports `down`. |
| `unknown` | Status cannot be determined. |

### database_connections Object Shape

```json
{
  "active": 12,
  "idle": 5,
  "max": 20,
  "saturation_pct": 60.0
}
```

`null` object if not instrumented.

### Counterexamples (Rejected)

1. `overall_status = "healthy"` when any component is `"down"`.
2. `error_rate` as negative number.
3. `slow_request_count` as negative number.
4. `overall_status = "ok"` or `"green"` — must use enum values.
5. `generated_at` as local time — must be UTC ISO-8601.

---

## 5. Contract: PlatformAuditEvent

An **append-only** audit event for platform-level operations. Aligned to P9-R2 PlatformAuditEvent source map.

```
PlatformAuditEvent {
  event_id              : uuid        NOT NULL   -- proposed_public_metadata
  actor_id              : string      NULLABLE   -- deferred
  actor_role            : enum        NULLABLE   -- deferred
  tenant_id             : uuid        NULLABLE   -- proposed_public_metadata
  scope                 : enum        NOT NULL   -- proposed_public_metadata
  action                : string      NOT NULL   -- proposed_public_metadata
  reason                : string      NULLABLE   -- proposed_public_metadata
  result                : enum        NOT NULL   -- proposed_public_metadata
  metadata_redacted     : object      NULLABLE   -- proposed_public_metadata
  correlation_id        : string      NULLABLE   -- telemetry_required
  created_at            : timestamp   NOT NULL   -- proposed_public_metadata
}
```

### Field Details

| Field | Type | Nullable | Unknown Behavior | Source Zone | P10-A Status |
|-------|------|----------|-----------------|-------------|--------------|
| `event_id` | uuid | No | Always generated | public platform metadata | `proposed_public_metadata` |
| `actor_id` | string | Yes | `null` until platform auth exists | platform auth context | `deferred` |
| `actor_role` | enum | Yes | `null` until platform auth exists | platform auth context | `deferred` |
| `tenant_id` | uuid | Yes | `null` for global-scope events | public platform metadata | `proposed_public_metadata` |
| `scope` | enum | No | Always required | audit metadata | `proposed_public_metadata` |
| `action` | string | No | Always required | audit metadata | `proposed_public_metadata` |
| `reason` | string | Yes | `null` for actions not requiring reason; **required** for support/elevated views per acceptance criteria | audit metadata | `proposed_public_metadata` |
| `result` | enum | No | Always required | audit metadata | `proposed_public_metadata` |
| `metadata_redacted` | object | Yes | `null` if no metadata; never raw sensitive payload | audit metadata | `proposed_public_metadata` |
| `correlation_id` | string | Yes | `null` if not yet correlated | logs/traces | `telemetry_required` |
| `created_at` | timestamp | No | Always required | audit metadata | `proposed_public_metadata` |

### Actor Role Enum

| Value | Meaning |
|-------|---------|
| `super_admin` | Platform super administrator. |
| `support_operator` | Support operator with assigned tenants. |
| `engineering_operator` | Engineering operator for diagnostics/incident response. |

### Scope Enum

| Value | Meaning |
|-------|---------|
| `global` | Platform-wide event (no tenant context). |
| `tenant` | Tenant-scoped event. |
| `system` | System infrastructure event. |
| `support` | Support-mode event. |

### Result Enum

| Value | Meaning |
|-------|---------|
| `allowed` | Action was permitted and completed. |
| `denied` | Action was denied (authorization, policy). |
| `failed` | Action was attempted but failed (error). |
| `completed` | Action completed successfully. |

### Counterexamples (Rejected)

1. `metadata_redacted` containing raw request body or payment details.
2. `scope = "tenant"` with `tenant_id = null` — tenant scope requires tenant_id.
3. `result` as `"success"` — use `"completed"` or `"allowed"`.
4. `reason = null` for `scope = "support"` — support scope requires reason.
5. Two events with the same `event_id`.
6. `actor_role` as `"admin"` — use `"super_admin"` or `"support_operator"`.

---

## 6. Cross-Contract Rules

1. All UUIDs must be version 4 or 7. No version 1 (leaks MAC) or nil UUIDs.
2. All timestamps must be UTC ISO-8601 (`YYYY-MM-DDTHH:MM:SS.sssZ`). No timezone offsets, no local time.
3. Nullable fields return `null` when data sources are unavailable. Non-nullable enum fields use documented fallback values (typically `"unknown"` or `false`).
4. `unknown` is not equivalent to `healthy`. Unknown means "cannot determine" and must never be treated as passing.
5. Platform data MUST NOT contain tenant business data (raw orders, payments, products, customer PII).
6. Tenant references are by UUID only, never by name or schema in identity fields.
7. Enum fields use lowercase snake_case string values.
8. Every field has a P10-A source status from the P9-R2 vocabulary: `available_now`, `proposed_public_metadata`, `tenant_aggregate_required`, `telemetry_required`, `manual_or_unknown`, `deferred`.

---

## 7. Scope Boundaries

This document does NOT:

- Define API endpoints, HTTP methods, or URL patterns.
- Define database migration schemas or assert where platform data is stored.
- Define authentication or authorization rules.
- Define billing, subscription, or quota enforcement.
- Modify tenant schema structure or business data.
- Require any code changes to `backend/`, `frontend/`, or `product-dev-recovered/`.
- Assert storage location (e.g., "public schema with platform_ prefix") — that is an implementation decision requiring separate approval.
