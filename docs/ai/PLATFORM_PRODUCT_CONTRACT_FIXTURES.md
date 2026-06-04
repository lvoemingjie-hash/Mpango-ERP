# Platform Product Contract Fixtures

**Phase**: P10-A
**Date**: 2026-06-04
**Status**: Contract-only — reference fixtures for testing
**Source**: `PLATFORM_PRODUCT_CONTRACTS.md`

---

## Purpose

This document provides concrete JSON fixtures that validate each contract's field rules, nullable behavior, source zone semantics, and counterexample rejection. Fixtures are organized by contract and by scenario.

---

## Fixture 1: Healthy Tenant — TenantSummary

```json
{
  "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
  "tenant_name": "Acme Wholesale Ltd",
  "schema_name": "tenant_acme_wholesale",
  "status": "active",
  "plan": "professional",
  "retailer_count": 12,
  "created_at": "2026-01-15T09:30:00.000Z",
  "last_activity_at": "2026-06-04T14:22:00.000Z",
  "source_zone": "tenant"
}
```

**Valid because**: All required fields present, `retailer_count >= 0`, `status` is valid enum, timestamps are UTC ISO-8601.

---

## Fixture 2: Healthy Tenant — TenantHealth

```json
{
  "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
  "healthy": true,
  "checks": [
    {
      "name": "db_connectivity",
      "status": "pass",
      "message": "Tenant schema reachable",
      "latency_ms": 23
    },
    {
      "name": "schema_integrity",
      "status": "pass",
      "message": "All expected tables present",
      "latency_ms": 145
    }
  ],
  "assessed_at": "2026-06-04T14:25:00.000Z",
  "source_zone": "tenant"
}
```

**Valid because**: `healthy = true` matches all checks being `"pass"`, at least 1 check, correct enum values.

---

## Fixture 3: Degraded Tenant — TenantSummary

```json
{
  "tenant_id": "660e8400-e29b-41d4-a716-446655440001",
  "tenant_name": "SlowCo Distributors",
  "schema_name": "tenant_slowco",
  "status": "active",
  "plan": "starter",
  "retailer_count": 3,
  "created_at": "2026-03-20T11:00:00.000Z",
  "last_activity_at": "2026-06-04T10:15:00.000Z",
  "source_zone": "tenant"
}
```

**Valid because**: Summary shape is correct even though the tenant is degraded (degradation is a health property, not a summary property).

---

## Fixture 4: Degraded Tenant — TenantHealth

```json
{
  "tenant_id": "660e8400-e29b-41d4-a716-446655440001",
  "healthy": false,
  "checks": [
    {
      "name": "db_connectivity",
      "status": "pass",
      "message": "Connected",
      "latency_ms": 18
    },
    {
      "name": "query_performance",
      "status": "degraded",
      "message": "Average query time 1200ms exceeds 500ms threshold",
      "latency_ms": 1237
    }
  ],
  "assessed_at": "2026-06-04T14:25:00.000Z",
  "source_zone": "tenant"
}
```

**Valid because**: `healthy = false` (one check is `"degraded"`), `"degraded"` is a valid enum, `latency_ms` is positive.

---

## Fixture 5: Unknown Tenant (Unreachable DB) — TenantSummary

```json
{
  "tenant_id": "770e8400-e29b-41d4-a716-446655440002",
  "tenant_name": "Phantom Retail",
  "schema_name": "tenant_phantom",
  "status": "active",
  "plan": null,
  "retailer_count": -1,
  "created_at": "2026-02-10T08:00:00.000Z",
  "last_activity_at": null,
  "source_zone": "unknown"
}
```

**Valid because**: `source_zone = "unknown"`, `retailer_count = -1` (unreachable sentinel), `plan = null` (nullable), `last_activity_at = null` (nullable).

---

## Fixture 6: Unknown Tenant — TenantHealth

```json
{
  "tenant_id": "770e8400-e29b-41d4-a716-446655440002",
  "healthy": false,
  "checks": [
    {
      "name": "db_connectivity",
      "status": "unknown",
      "message": "Connection refused after 5000ms timeout",
      "latency_ms": null
    }
  ],
  "assessed_at": "2026-06-04T14:25:00.000Z",
  "source_zone": "unknown"
}
```

**Valid because**: All checks `"unknown"` → `healthy = false`, `source_zone = "unknown"`, `latency_ms = null` (not measurable).

---

## Fixture 7: Degraded System — SystemHealth

```json
{
  "status": "degraded",
  "tenant_total": 5,
  "tenant_healthy": 3,
  "tenant_degraded": 1,
  "tenant_unreachable": 1,
  "platform_checks": [
    {
      "name": "platform_db",
      "status": "pass",
      "message": "Platform database reachable",
      "latency_ms": 12
    },
    {
      "name": "redis",
      "status": "pass",
      "message": "Redis connected",
      "latency_ms": 3
    }
  ],
  "assessed_at": "2026-06-04T14:30:00.000Z",
  "source_zone": "platform"
}
```

**Valid because**: `status = "degraded"` (1 degraded + 1 unreachable tenant, but no platform check fails), counts consistent: `3 + 1 + 1 = 5 <= tenant_total`.

---

## Fixture 8: Support Bundle Denied — Missing Reason — PlatformAuditEvent

A support operator requests a support bundle for a tenant, but the bundle creation is denied because no reason was provided.

```json
{
  "event_id": "880e8400-e29b-41d4-a716-446655440003",
  "event_type": "support.bundle_denied",
  "actor_type": "operator",
  "actor_id": "operator-42",
  "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
  "payload": {
    "reason": null,
    "denial_code": "missing_reason",
    "requested_at": "2026-06-04T14:20:00.000Z"
  },
  "occurred_at": "2026-06-04T14:20:01.000Z",
  "source_zone": "platform",
  "source_status": "live"
}
```

**Valid because**: `payload.reason = null` (the denial reason is that no reason was provided — the denial itself is recorded), `event_type` is namespaced, `actor_type` is valid enum.

---

## Fixture 9: Support Operator Denied — Unassigned Tenant — PlatformAuditEvent

A support operator attempts an action on a tenant they are not assigned to.

```json
{
  "event_id": "990e8400-e29b-41d4-a716-446655440004",
  "event_type": "support.access_denied",
  "actor_type": "operator",
  "actor_id": "operator-99",
  "tenant_id": "660e8400-e29b-41d4-a716-446655440001",
  "payload": {
    "action": "support_bundle_create",
    "denial_code": "unassigned_tenant",
    "operator_assignments": ["550e8400-e29b-41d4-a716-446655440000"],
    "message": "Operator is not assigned to this tenant"
  },
  "occurred_at": "2026-06-04T14:22:00.000Z",
  "source_zone": "platform",
  "source_status": "live"
}
```

**Valid because**: `payload` is a JSON object (not a string), `event_type` is namespaced under `support.*`, `actor_type = "operator"` is valid, `tenant_id` references the denied tenant.

---

## Counterexample Fixtures (Rejected)

These fixtures MUST be rejected by any contract validator:

### C1: tenant_id as string

```json
{
  "tenant_id": "not-a-uuid",
  "tenant_name": "Bad Co",
  "schema_name": "tenant_bad",
  "status": "active",
  "plan": null,
  "retailer_count": 0,
  "created_at": "2026-01-01T00:00:00.000Z",
  "last_activity_at": null,
  "source_zone": "platform"
}
```

**Rejected because**: `tenant_id` must be UUID, not a freeform string.

### C2: status as "deleted"

```json
{
  "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
  "tenant_name": "Ghost Co",
  "schema_name": "tenant_ghost",
  "status": "deleted",
  "plan": "starter",
  "retailer_count": 0,
  "created_at": "2026-01-01T00:00:00.000Z",
  "last_activity_at": null,
  "source_zone": "platform"
}
```

**Rejected because**: `"deleted"` is not a valid status enum value. Use `"decommissioned"`.

### C3: healthy = true with failing check

```json
{
  "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
  "healthy": true,
  "checks": [
    {
      "name": "db_connectivity",
      "status": "fail",
      "message": "Connection refused",
      "latency_ms": null
    }
  ],
  "assessed_at": "2026-06-04T14:25:00.000Z",
  "source_zone": "tenant"
}
```

**Rejected because**: `healthy` must be `false` when any check has `status = "fail"`.

### C4: payload as string

```json
{
  "event_id": "aa0e8400-e29b-41d4-a716-446655440005",
  "event_type": "tenant.suspended",
  "actor_type": "system",
  "actor_id": null,
  "tenant_id": "550e8400-e29b-41d4-a716-446655440000",
  "payload": "tenant suspended for billing",
  "occurred_at": "2026-06-04T15:00:00.000Z",
  "source_zone": "platform",
  "source_status": "live"
}
```

**Rejected because**: `payload` must be a JSON object or `null`, not a string.

### C5: event_type without namespace dot

```json
{
  "event_id": "bb0e8400-e29b-41d4-a716-446655440006",
  "event_type": "something_happened",
  "actor_type": "system",
  "actor_id": null,
  "tenant_id": null,
  "payload": null,
  "occurred_at": "2026-06-04T15:00:00.000Z",
  "source_zone": "platform",
  "source_status": "live"
}
```

**Rejected because**: `event_type` must be namespaced with a dot separator (e.g., `"platform.something_happened"`).

### C6: tenant_healthy > tenant_total

```json
{
  "status": "healthy",
  "tenant_total": 3,
  "tenant_healthy": 5,
  "tenant_degraded": 0,
  "tenant_unreachable": 0,
  "platform_checks": [
    {
      "name": "platform_db",
      "status": "pass",
      "message": "OK",
      "latency_ms": 10
    }
  ],
  "assessed_at": "2026-06-04T14:30:00.000Z",
  "source_zone": "platform"
}
```

**Rejected because**: `tenant_healthy` (5) cannot exceed `tenant_total` (3).

---

## Fixture Index

| # | Fixture | Contract | Scenario |
|---|---------|----------|----------|
| 1 | Healthy Tenant Summary | TenantSummary | All fields populated, source_zone = "tenant" |
| 2 | Healthy Tenant Health | TenantHealth | All checks pass, healthy = true |
| 3 | Degraded Tenant Summary | TenantSummary | Normal summary shape for a degraded tenant |
| 4 | Degraded Tenant Health | TenantHealth | One check degraded, healthy = false |
| 5 | Unknown Tenant Summary | TenantSummary | DB unreachable, source_zone = "unknown", retailer_count = -1 |
| 6 | Unknown Tenant Health | TenantHealth | All checks unknown, healthy = false |
| 7 | Degraded System | SystemHealth | 1 degraded + 1 unreachable tenant, platform checks pass |
| 8 | Support Bundle Denied (Missing Reason) | PlatformAuditEvent | Denied due to null reason field |
| 9 | Support Operator Denied (Unassigned) | PlatformAuditEvent | Denied due to operator not assigned to tenant |
| C1 | tenant_id as string | TenantSummary | Rejected: not UUID |
| C2 | status as "deleted" | TenantSummary | Rejected: invalid enum |
| C3 | healthy=true with fail | TenantHealth | Rejected: contradicts check result |
| C4 | payload as string | PlatformAuditEvent | Rejected: must be object or null |
| C5 | event_type without dot | PlatformAuditEvent | Rejected: missing namespace |
| C6 | tenant_healthy > total | SystemHealth | Rejected: count invariant violation |
