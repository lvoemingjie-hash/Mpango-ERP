# Platform Product Contract Fixtures

**Phase**: P10-A-R1
**Date**: 2026-06-05
**Status**: Contract-only — reference fixtures for testing
**Source**: `PLATFORM_PRODUCT_CONTRACTS.md` (aligned to P9-R2 data source map)

---

## Purpose

This document provides concrete JSON fixtures that validate each contract's field rules, nullable/unknown behavior, and P10-A source status. Fixtures cover the 6 scenarios required by the P9-R2 acceptance criteria.

---

## Fixture 1: Healthy Tenant — TenantSummary

```json
{
  "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
  "tenant_name": "Acme Wholesale Ltd",
  "tenant_schema": "tenant_acme_wholesale",
  "status": "active",
  "tier": "professional",
  "created_at": "2026-01-15T09:30:00.000Z",
  "last_activity_at": "2026-06-05T08:12:00.000Z",
  "user_count": 24,
  "health_status": "healthy",
  "recent_error_count": 0,
  "support_mode_active": false
}
```

**Valid because**: All fields present, `health_status = "healthy"` (sources available), `support_mode_active = false`, `recent_error_count = 0`, `user_count >= 0`.

---

## Fixture 2: Healthy Tenant — TenantHealth

```json
{
  "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
  "tenant_schema": "tenant_acme_wholesale",
  "health_status": "healthy",
  "schema_status": "exists",
  "last_login_at": "2026-06-05T08:10:00.000Z",
  "activity_counters": {
    "orders": 42,
    "inventory_changes": 15,
    "invoices": 8,
    "payments": 3,
    "sync_jobs": 1
  },
  "recent_errors": [],
  "slow_routes": [],
  "failed_jobs": [],
  "last_health_check_at": "2026-06-05T08:15:00.000Z"
}
```

**Valid because**: `health_status = "healthy"`, `schema_status = "exists"`, no errors/slow routes/failed jobs, activity counters are counts only (no payment details).

---

## Fixture 3: Degraded Tenant — TenantSummary

```json
{
  "tenant_id": "660e8400-e29b-41d4-a716-446655440001",
  "tenant_name": "SlowCo Distributors",
  "tenant_schema": "tenant_slowco",
  "status": "active",
  "tier": "starter",
  "created_at": "2026-03-20T11:00:00.000Z",
  "last_activity_at": "2026-06-04T10:15:00.000Z",
  "user_count": 3,
  "health_status": "degraded",
  "recent_error_count": 7,
  "support_mode_active": false
}
```

**Valid because**: `health_status = "degraded"` (degradation detected), `recent_error_count > 0`, all source statuses are populated.

---

## Fixture 4: Degraded Tenant — TenantHealth

```json
{
  "tenant_id": "660e8400-e29b-41d4-a716-446655440001",
  "tenant_schema": "tenant_slowco",
  "health_status": "degraded",
  "schema_status": "exists",
  "last_login_at": "2026-06-04T10:00:00.000Z",
  "activity_counters": {
    "orders": 5,
    "inventory_changes": 1,
    "invoices": 0,
    "payments": 0,
    "sync_jobs": 0
  },
  "recent_errors": [
    {
      "error_class": "TimeoutError",
      "count": 5,
      "correlation_ids": ["corr-abc123", "corr-def456"]
    },
    {
      "error_class": "ConnectionRefused",
      "count": 2,
      "correlation_ids": ["corr-ghi789"]
    }
  ],
  "slow_routes": [
    {
      "route": "GET /api/orders",
      "latency_bucket_ms": 1200,
      "count": 3
    }
  ],
  "failed_jobs": [
    {
      "job_class": "OrderSyncJob",
      "count": 1
    }
  ],
  "last_health_check_at": "2026-06-05T08:15:00.000Z"
}
```

**Valid because**: `health_status = "degraded"`, errors have redacted class names and correlation IDs only (no raw payloads), slow routes have route name and latency bucket only, failed jobs have class name and count only.

---

## Fixture 5: Unknown Tenant (Unreachable DB) — TenantSummary

```json
{
  "tenant_id": "770e8400-e29b-41d4-a716-446655440002",
  "tenant_name": null,
  "tenant_schema": "tenant_phantom",
  "status": "unknown",
  "tier": null,
  "created_at": null,
  "last_activity_at": null,
  "user_count": null,
  "health_status": "unknown",
  "recent_error_count": null,
  "support_mode_active": false
}
```

**Valid because**: `health_status = "unknown"` (signals unavailable), nullable fields are `null`, `support_mode_active = false` (not yet implemented), `status = "unknown"` fallback.

---

## Fixture 6: Unknown Tenant — TenantHealth

```json
{
  "tenant_id": "770e8400-e29b-41d4-a716-446655440002",
  "tenant_schema": "tenant_phantom",
  "health_status": "unknown",
  "schema_status": "unreachable",
  "last_login_at": null,
  "activity_counters": null,
  "recent_errors": null,
  "slow_routes": null,
  "failed_jobs": null,
  "last_health_check_at": null
}
```

**Valid because**: `health_status = "unknown"`, `schema_status = "unreachable"`, all telemetry-backed fields are `null` (sources unavailable).

---

## Fixture 7: Degraded System — SystemHealth

```json
{
  "overall_status": "degraded",
  "api_status": "degraded",
  "database_status": "healthy",
  "database_connections": {
    "active": 8,
    "idle": 3,
    "max": 20,
    "saturation_pct": 40.0
  },
  "queue_status": "healthy",
  "cpu_status": null,
  "memory_status": null,
  "disk_status": null,
  "error_rate": 0.12,
  "slow_request_count": 3,
  "generated_at": "2026-06-05T09:00:00.000Z"
}
```

**Valid because**: `overall_status = "degraded"` (api_status is degraded), `cpu_status/memory_status/disk_status = null` (not instrumented in local/dev — per P9-R2), `error_rate` is time-windowed float.

---

## Fixture 8: Support Bundle Denied — Missing Reason — PlatformAuditEvent

A support operator requests a support bundle but does not provide a reason. Denied per P12 acceptance criteria.

```json
{
  "event_id": "880e8400-e29b-41d4-a716-446655440003",
  "actor_id": "operator-42",
  "actor_role": "support_operator",
  "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
  "scope": "support",
  "action": "support.bundle_generate",
  "reason": null,
  "result": "denied",
  "metadata_redacted": {
    "denial_code": "missing_reason",
    "requested_at": "2026-06-05T09:20:00.000Z"
  },
  "correlation_id": "corr-support-001",
  "created_at": "2026-06-05T09:20:01.000Z"
}
```

**Valid because**: `scope = "support"` with `reason = null` (denied because no reason provided), `result = "denied"`, `metadata_redacted` contains denial code but no raw payload.

---

## Fixture 9: Support Operator Denied — Unassigned Tenant — PlatformAuditEvent

A support operator attempts an action on a tenant they are not assigned to.

```json
{
  "event_id": "990e8400-e29b-41d4-a716-446655440004",
  "actor_id": "operator-99",
  "actor_role": "support_operator",
  "tenant_id": "660e8400-e29b-41d4-a716-446655440001",
  "scope": "support",
  "action": "support.tenant_view",
  "reason": "routine health check",
  "result": "denied",
  "metadata_redacted": {
    "denial_code": "unassigned_tenant",
    "operator_assignments": ["550e8400-e29b-41d4-a716-446655440000"],
    "message": "Operator not assigned to this tenant"
  },
  "correlation_id": "corr-support-002",
  "created_at": "2026-06-05T09:22:00.000Z"
}
```

**Valid because**: `scope = "support"` with `reason` provided, `result = "denied"` (unassigned), `metadata_redacted` has denial code and operator assignments but no sensitive data.

---

## Counterexample Fixtures (Rejected)

### C1: health_status = "healthy" when sources are unknown

```json
{
  "tenant_id": "770e8400-e29b-41d4-a716-446655440002",
  "tenant_name": null,
  "tenant_schema": "tenant_phantom",
  "status": "active",
  "tier": null,
  "created_at": null,
  "last_activity_at": null,
  "user_count": null,
  "health_status": "healthy",
  "recent_error_count": null,
  "support_mode_active": false
}
```

**Rejected because**: `health_status` cannot be `"healthy"` when all data sources are unavailable. Must be `"unknown"`.

### C2: support scope with null reason

```json
{
  "event_id": "aa0e8400-e29b-41d4-a716-446655440005",
  "actor_id": "operator-42",
  "actor_role": "support_operator",
  "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
  "scope": "support",
  "action": "support.tenant_view",
  "reason": null,
  "result": "allowed",
  "metadata_redacted": null,
  "correlation_id": null,
  "created_at": "2026-06-05T09:30:00.000Z"
}
```

**Rejected because**: `scope = "support"` with `result = "allowed"` but `reason = null`. Support scope requires reason, even for allowed actions.

### C3: overall_status = "healthy" with degraded component

```json
{
  "overall_status": "healthy",
  "api_status": "degraded",
  "database_status": "healthy",
  "database_connections": null,
  "queue_status": null,
  "cpu_status": null,
  "memory_status": null,
  "disk_status": null,
  "error_rate": null,
  "slow_request_count": null,
  "generated_at": "2026-06-05T09:00:00.000Z"
}
```

**Rejected because**: `overall_status = "healthy"` but `api_status = "degraded"`. Overall must be `"degraded"` when any component is degraded.

### C4: raw error payload in recent_errors

```json
{
  "tenant_id": "660e8400-e29b-41d4-a716-446655440001",
  "tenant_schema": "tenant_slowco",
  "health_status": "degraded",
  "schema_status": "exists",
  "last_login_at": null,
  "activity_counters": null,
  "recent_errors": [
    {
      "error_class": "ValueError",
      "count": 1,
      "correlation_ids": ["corr-001"],
      "raw_stack_trace": "Traceback (most recent call last): ..."
    }
  ],
  "slow_routes": null,
  "failed_jobs": null,
  "last_health_check_at": null
}
```

**Rejected because**: `raw_stack_trace` field in ErrorSummary — only `error_class`, `count`, and `correlation_ids` are allowed.

### C5: tenant scope without tenant_id

```json
{
  "event_id": "bb0e8400-e29b-41d4-a716-446655440006",
  "actor_id": null,
  "actor_role": "super_admin",
  "tenant_id": null,
  "scope": "tenant",
  "action": "tenant.status_change",
  "reason": "policy violation",
  "result": "allowed",
  "metadata_redacted": null,
  "correlation_id": null,
  "created_at": "2026-06-05T10:00:00.000Z"
}
```

**Rejected because**: `scope = "tenant"` requires a non-null `tenant_id`.

### C6: actor_role as "admin"

```json
{
  "event_id": "cc0e8400-e29b-41d4-a716-446655440007",
  "actor_id": "user-1",
  "actor_role": "admin",
  "tenant_id": null,
  "scope": "global",
  "action": "platform.config_change",
  "reason": null,
  "result": "completed",
  "metadata_redacted": null,
  "correlation_id": null,
  "created_at": "2026-06-05T10:05:00.000Z"
}
```

**Rejected because**: `actor_role = "admin"` is not a valid enum value. Use `"super_admin"`, `"support_operator"`, or `"engineering_operator"`.

---

## Fixture Index

| # | Fixture | Contract | Scenario |
|---|---------|----------|----------|
| 1 | Healthy Tenant Summary | TenantSummary | All fields populated, health_status = "healthy" |
| 2 | Healthy Tenant Health | TenantHealth | No errors, no slow routes, no failed jobs |
| 3 | Degraded Tenant Summary | TenantSummary | health_status = "degraded", recent_error_count > 0 |
| 4 | Degraded Tenant Health | TenantHealth | Errors, slow routes, failed jobs present |
| 5 | Unknown Tenant Summary | TenantSummary | health_status = "unknown", nullable fields null |
| 6 | Unknown Tenant Health | TenantHealth | schema_status = "unreachable", telemetry null |
| 7 | Degraded System | SystemHealth | api_status = "degraded", cpu/memory/disk null |
| 8 | Support Bundle Denied | PlatformAuditEvent | reason = null, result = "denied" |
| 9 | Support Operator Denied | PlatformAuditEvent | unassigned tenant, result = "denied" |
| C1 | healthy when unknown | TenantSummary | Rejected: unknown ≠ healthy |
| C2 | support without reason | PlatformAuditEvent | Rejected: support requires reason |
| C3 | healthy with degraded | SystemHealth | Rejected: contradicts component status |
| C4 | raw error payload | TenantHealth | Rejected: only redacted fields allowed |
| C5 | tenant scope no tenant_id | PlatformAuditEvent | Rejected: scope/tenant_id mismatch |
| C6 | actor_role = "admin" | PlatformAuditEvent | Rejected: invalid enum value |
