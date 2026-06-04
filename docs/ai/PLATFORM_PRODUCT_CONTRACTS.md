# Platform Product Data Contracts

**Phase**: P10-A
**Date**: 2026-06-04
**Status**: Contract-only — no backend/frontend/migration/API code
**Scope**: Define the structural contracts for platform observability and tenant-management data surfaces.

---

## 1. Purpose

These contracts define the **shape and semantics** of data that the platform layer exposes to operators, dashboards, and audit consumers. They are NOT implemented yet. They exist so that:

1. Front-end and back-end teams can code against a stable interface definition.
2. Test fixtures can validate conformance without running a live system.
3. Counterexamples can be rejected mechanically.

All platform data lives in the `public` schema with `platform_` prefix. Platform references `wholesalers.id` for tenant identity — it must not duplicate tenant identity.

---

## 2. Contract: TenantSummary

A **read-only** summary of a tenant's operational state, intended for platform operator dashboards.

```
TenantSummary {
  tenant_id           : uuid        NOT NULL   -- references wholesalers.id
  tenant_name         : string      NOT NULL   -- human-readable name
  schema_name         : string      NOT NULL   -- e.g. "tenant_abc123"
  status              : enum        NOT NULL   -- active | suspended | provisioning | decommissioned
  plan                : string      NULLABLE   -- plan identifier (e.g. "starter", "professional")
  retailer_count      : integer     NOT NULL   -- >= 0, count of invited retailers
  created_at          : timestamp   NOT NULL   -- UTC, ISO-8601
  last_activity_at    : timestamp   NULLABLE   -- UTC, ISO-8601; null if no activity
  source_zone         : string      NOT NULL   -- "platform" | "tenant" | "unknown"
}
```

### Field Semantics

| Field | Nullable | Source Zone | Notes |
|-------|----------|-------------|-------|
| `tenant_id` | No | platform | Immutable after creation. FK to `wholesalers.id`. |
| `tenant_name` | No | tenant | Sourced from tenant schema. May lag if tenant DB unreachable. |
| `schema_name` | No | platform | Derived from provisioning. Format: `tenant_{suffix}`. |
| `status` | No | platform | Platform-managed lifecycle state. |
| `plan` | Yes | platform | NULL if not yet assigned a plan. |
| `retailer_count` | No | tenant | Queried from tenant schema. `-1` if tenant DB unreachable. |
| `created_at` | No | platform | Set at provisioning time. |
| `last_activity_at` | Yes | tenant | NULL if no recorded activity. Not updated if tenant DB unreachable. |
| `source_zone` | No | platform | Indicates whether data was sourced from platform tables, tenant schema, or is unknown (unreachable). |

### Source Status Per Field

Each field carries an implicit source status:

- **`live`**: Value was read from a live database within the last sync window.
- **`cached`**: Value was read from a previously cached snapshot because the live source was unavailable.
- **`unknown`**: No value is available (source unreachable, no cache). Nullable fields become `null`; non-nullable fields use documented defaults (e.g., `retailer_count = -1`, `status = "unknown"` if no data at all).

The `source_zone` field disambiguates where the data came from. When `source_zone = "unknown"`, consumers should treat nullable fields as `null` and non-nullable defaults as stale.

### Status Enum Values

| Value | Meaning |
|-------|---------|
| `active` | Tenant schema exists, DB is reachable, tenant is operational. |
| `suspended` | Platform has suspended the tenant (billing, abuse, etc.). |
| `provisioning` | Tenant schema is being created or migrated. |
| `decommissioned` | Tenant has been offboarded. Schema may still exist for audit. |

### Counterexamples (Rejected)

These shapes MUST NOT appear and MUST be rejected by any contract validator:

1. `tenant_id` as a string (must be UUID).
2. `status` as "deleted" (the status is `decommissioned`, not `deleted`).
3. `retailer_count` as `null` (must be `>= 0` or `-1` for unreachable).
4. `schema_name` without `tenant_` prefix.
5. `tenant_id` that does not exist in `wholesalers.id`.
6. `created_at` in local time (must be UTC ISO-8601).

---

## 3. Contract: TenantHealth

A **read-only** health assessment for a single tenant, intended for operational monitoring and alerting.

```
TenantHealth {
  tenant_id           : uuid        NOT NULL
  healthy             : boolean     NOT NULL
  checks              : CheckResult[]  NOT NULL  -- at least 1 entry
  assessed_at         : timestamp   NOT NULL   -- UTC, ISO-8601
  source_zone         : string      NOT NULL   -- "platform" | "tenant" | "unknown"
}

CheckResult {
  name                : string      NOT NULL   -- e.g. "db_connectivity", "schema_integrity"
  status              : enum        NOT NULL   -- pass | fail | degraded | unknown
  message             : string      NULLABLE   -- human-readable detail
  latency_ms          : integer     NULLABLE   -- check latency, NULL if not measurable
}
```

### Field Semantics

| Field | Nullable | Source Zone | Notes |
|-------|----------|-------------|-------|
| `tenant_id` | No | platform | Identifies the tenant. |
| `healthy` | No | platform | `true` only if ALL checks have `status = "pass"`. |
| `checks` | No | mixed | Array of at least 1 `CheckResult`. May mix platform and tenant sources. |
| `assessed_at` | No | platform | When this health assessment was performed. |
| `source_zone` | No | platform | "unknown" if the tenant DB was unreachable for all checks. |

### Check Status Enum

| Value | Meaning |
|-------|---------|
| `pass` | Check succeeded. |
| `fail` | Check failed — actionable. |
| `degraded` | Partial success — e.g., slow but functional. |
| `unknown` | Could not assess (DB unreachable, timeout). |

### Derived Rules

- `healthy = true` if and only if every `CheckResult.status = "pass"`.
- `healthy = false` if any `CheckResult.status` is `"fail"`.
- If all checks are `"unknown"`, `healthy = false` and `source_zone = "unknown"`.

### Counterexamples (Rejected)

1. `healthy = true` when any check has `status = "fail"`.
2. Empty `checks` array (must have at least 1).
3. `checks` with `status = "ok"` (the enum value is `"pass"`, not `"ok"`).
4. `latency_ms` as a negative integer.
5. `assessed_at` in the future.

---

## 4. Contract: SystemHealth

A **read-only** aggregate health of the entire platform, intended for the platform operator cockpit.

```
SystemHealth {
  status              : enum        NOT NULL   -- healthy | degraded | down | unknown
  tenant_total        : integer     NOT NULL   -- >= 0
  tenant_healthy      : integer     NOT NULL   -- >= 0, <= tenant_total
  tenant_degraded     : integer     NOT NULL   -- >= 0
  tenant_unreachable  : integer     NOT NULL   -- >= 0
  platform_checks     : CheckResult[]  NOT NULL  -- at least 1 entry
  assessed_at         : timestamp   NOT NULL   -- UTC, ISO-8601
  source_zone         : string      NOT NULL   -- always "platform"
}
```

### Field Semantics

| Field | Nullable | Source Zone | Notes |
|-------|----------|-------------|-------|
| `status` | No | platform | Derived from tenant counts and platform checks. |
| `tenant_total` | No | platform | Count of all known tenants regardless of status. |
| `tenant_healthy` | No | platform | Count where `TenantHealth.healthy = true`. |
| `tenant_degraded` | No | platform | Count where any check is `"degraded"` but none is `"fail"`. |
| `tenant_unreachable` | No | platform | Count where `source_zone = "unknown"` for the tenant. |
| `platform_checks` | No | platform | Infrastructure-level checks (DB, Redis, storage, etc.). |
| `assessed_at` | No | platform | When this assessment was performed. |
| `source_zone` | No | platform | Always `"platform"` for system-level health. |

### Derived Rules

- `status = "healthy"` if `tenant_degraded = 0` AND `tenant_unreachable = 0` AND all `platform_checks` pass.
- `status = "degraded"` if any tenant is degraded or unreachable, but no platform check fails.
- `status = "down"` if any `platform_check.status = "fail"`.
- `status = "unknown"` if assessment could not be performed.
- `tenant_total = tenant_healthy + tenant_degraded + tenant_unreachable + tenant_failed`.
- Where `tenant_failed = tenant_total - tenant_healthy - tenant_degraded - tenant_unreachable` (count of tenants with at least one `"fail"` check).

### Counterexamples (Rejected)

1. `tenant_healthy > tenant_total`.
2. `status = "healthy"` when any `platform_checks` entry has `status = "fail"`.
3. `status` as "ok" or "green" (must use enum values).
4. Negative counts for any tenant metric.
5. `source_zone` as anything other than `"platform"`.

---

## 5. Contract: PlatformAuditEvent

An **append-only** audit event recording platform-level operations. Intended for compliance, debugging, and operational review.

```
PlatformAuditEvent {
  event_id            : uuid        NOT NULL   -- unique per event
  event_type          : string      NOT NULL   -- e.g. "tenant.provisioned", "tenant.suspended"
  actor_type          : enum        NOT NULL   -- system | operator | tenant_admin | unknown
  actor_id            : string      NULLABLE   -- identifier of the actor (user ID, system component)
  tenant_id           : uuid        NULLABLE   -- affected tenant, NULL if platform-wide event
  payload             : object      NULLABLE   -- event-specific detail, schema varies by event_type
  occurred_at         : timestamp   NOT NULL   -- UTC, ISO-8601
  source_zone         : string      NOT NULL   -- "platform" | "tenant" | "unknown"
  source_status       : string      NOT NULL   -- "live" | "cached" | "unknown"
}
```

### Field Semantics

| Field | Nullable | Source Zone | Notes |
|-------|----------|-------------|-------|
| `event_id` | No | platform | UUIDv7 recommended (time-ordered). Immutable after creation. |
| `event_type` | No | mixed | Namespaced as `{domain}.{action}`. |
| `actor_type` | No | platform | Who or what triggered the event. |
| `actor_id` | Yes | platform | NULL for anonymous or system-initiated events. |
| `tenant_id` | Yes | platform | NULL for platform-wide events (e.g., infrastructure alerts). |
| `payload` | Yes | mixed | Event-type-specific data. Must be a JSON object, not a string. |
| `occurred_at` | No | mixed | When the event actually happened (not when it was recorded). |
| `source_zone` | No | platform | Where the event was generated. |
| `source_status` | No | platform | Quality of the data source at time of recording. |

### Event Type Namespace

| Prefix | Domain |
|--------|--------|
| `tenant.*` | Tenant lifecycle (provisioned, suspended, decommissioned, etc.) |
| `platform.*` | Platform infrastructure (health_check, config_change, etc.) |
| `audit.*` | Audit subsystem events (export_requested, access_denied, etc.) |
| `support.*` | Support operations (bundle_created, bundle_denied, etc.) |

### Actor Type Enum

| Value | Meaning |
|-------|---------|
| `system` | Automated platform process. |
| `operator` | Platform operator with admin access. |
| `tenant_admin` | Tenant-side administrator. |
| `unknown` | Actor could not be determined. |

### Counterexamples (Rejected)

1. `event_id` as an integer (must be UUID).
2. `event_type` without a dot separator (must be namespaced).
3. `payload` as a string (must be a JSON object or null).
4. `occurred_at` after the recording timestamp (cannot be in the future relative to ingestion).
5. `actor_type` as "admin" (must use enum: `operator` or `tenant_admin`).
6. Two events with the same `event_id`.

---

## 6. Cross-Contract Rules

1. All UUIDs must be version 4 or 7. No version 1 (leaks MAC) or nil UUIDs.
2. All timestamps must be UTC ISO-8601 (`YYYY-MM-DDTHH:MM:SS.sssZ`). No timezone offsets, no local time.
3. `source_zone` is always one of: `"platform"`, `"tenant"`, `"unknown"`.
4. `source_status` is always one of: `"live"`, `"cached"`, `"unknown"`.
5. Platform data MUST NOT contain tenant business data (orders, payments, products).
6. Tenant references are always by `wholesalers.id` UUID, never by name or schema.
7. Enum fields use lowercase snake_case string values.
8. Array fields must not be empty where `NOT NULL` is specified with a minimum count.

---

## 7. Implementation Notes (Non-Binding)

These contracts define structure only. Implementation considerations for future phases:

- **Storage**: Platform tables in `public` schema with `platform_` prefix.
- **Sync**: Tenant-sourced fields may lag. The `source_zone` and `source_status` fields make lag explicit.
- **Immutability**: `PlatformAuditEvent` records are append-only. No updates, no deletes.
- **Pagination**: List endpoints should support `limit`/`offset` with a default of 50.
- **Filtering**: `SystemHealth` should support filtering by tenant status.
- **Versioning**: Contracts may evolve. Use a `contract_version` field when serialization format changes.

---

## 8. Scope Boundaries

This document does NOT:

- Define API endpoints, HTTP methods, or URL patterns.
- Define database migration schemas.
- Define authentication or authorization rules.
- Define billing, subscription, or quota enforcement.
- Modify tenant schema structure or business data.
- Require any code changes to `backend/`, `frontend/`, or `product-dev-recovered/`.
