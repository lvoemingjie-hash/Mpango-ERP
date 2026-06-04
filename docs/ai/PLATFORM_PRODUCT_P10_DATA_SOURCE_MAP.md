# Platform Product P10 Data Source Map

**Phase:** P9-R2 / P10-A input
**Status:** Implementation-ready planning draft
**Date:** 2026-06-04

## Purpose

This document maps the first platform product contracts to safe data sources before any runtime code is written.

P10-A is data-contract-only. It may define schemas, fixture examples, API response shapes, and test plans. It must not add migrations, API handlers, frontend UI, auth/RBAC/tenancy/session changes, payment changes, or tenant business-data edits.

## Source Zones

| Source zone | Meaning | P10-A usage |
| --- | --- | --- |
| `public` platform metadata | Cross-tenant metadata such as tenant registry, tenant status, tenant schema name, platform audit summaries, and support session metadata | Allowed as contract source. If an exact table does not exist, mark the field as proposed public metadata. |
| tenant schema | Tenant-owned ERP records such as users, orders, inventory, payments, invoices, jobs, and tenant-specific events | Aggregated counters only in early phases. Do not expose raw records in platform contracts. |
| application logs | Route errors, exception summaries, correlation ids, and request metadata | Allowed as redacted diagnostic summaries. Raw payloads are forbidden. |
| runtime metrics | CPU, memory, disk, process, DB connection, queue, error rate, and latency signals | Allowed as health summaries. P10-A may mark fields as unavailable if not yet instrumented. |
| derived platform snapshot | Periodic or on-demand summarized health record written to a platform-owned store | Allowed as proposed future source. Must not imply migration in P10-A. |

## Field Status Vocabulary

Every P10-A field must use one of these statuses:

- `available_now`: source exists and can be read safely.
- `proposed_public_metadata`: source should live in a platform-owned public table, but implementation is not approved yet.
- `tenant_aggregate_required`: source requires safe aggregation from tenant schema.
- `telemetry_required`: source requires logs, metrics, or traces instrumentation.
- `manual_or_unknown`: source is not currently available; contract may return `unknown`.
- `deferred`: field belongs after P10-A.

## TenantSummary Source Map

| Field | Source zone | Initial source decision | P10-A status | Notes |
| --- | --- | --- | --- | --- |
| `tenant_id` | `public` platform metadata | Existing tenant/wholesaler identifier or proposed tenant registry id | `proposed_public_metadata` | Must map to current product tenant identity before code. |
| `tenant_name` | `public` platform metadata | Existing wholesaler/company display name or proposed tenant registry name | `proposed_public_metadata` | Do not query tenant schema for display name unless approved. |
| `tenant_schema` | `public` platform metadata | Existing schema identity tied to tenant provisioning | `available_now` if current public metadata exposes it, otherwise `proposed_public_metadata` | Required by schema-per-tenant model. |
| `status` | `public` platform metadata | Proposed platform tenant status | `proposed_public_metadata` | Values: `draft`, `active`, `paused`, `suspended`, `archived`, `unknown`. |
| `tier` | `public` platform metadata | Proposed tier/stage metadata | `proposed_public_metadata` | May be `unknown` until subscription model exists. |
| `created_at` | `public` platform metadata | Tenant/wholesaler creation timestamp | `proposed_public_metadata` | Contract must allow `unknown`. |
| `last_activity_at` | tenant schema or logs | Max safe activity timestamp from login/API/business counters | `tenant_aggregate_required` or `telemetry_required` | Do not scan all tenant schemas synchronously for cockpit load. |
| `user_count` | tenant schema aggregate | Count of active tenant users | `tenant_aggregate_required` | Aggregate only; no user list in TenantSummary. |
| `health_status` | derived platform snapshot | Computed from health signals | `manual_or_unknown` for P10-A | Values: `healthy`, `degraded`, `unhealthy`, `unknown`. |
| `recent_error_count` | application logs | Count of recent redacted errors correlated to tenant | `telemetry_required` | Must be time-windowed. |
| `support_mode_active` | `public` platform metadata | Active support session metadata | `proposed_public_metadata` | Must be false/unknown until support mode exists. |

## TenantHealth Source Map

| Field | Source zone | Initial source decision | P10-A status | Notes |
| --- | --- | --- | --- | --- |
| `tenant_id` | `public` platform metadata | Tenant registry id | `proposed_public_metadata` | Required. |
| `tenant_schema` | `public` platform metadata | Tenant schema name | `available_now` or `proposed_public_metadata` | Required for routing and diagnostics. |
| `health_status` | derived platform snapshot | Health rollup | `manual_or_unknown` | Must distinguish unknown from healthy. |
| `schema_status` | DB metadata / provisioning | Schema exists, reachable, migration-aligned | `telemetry_required` | P10-A may define values only. No migration check implementation. |
| `last_login_at` | tenant schema aggregate or logs | Last successful login timestamp | `tenant_aggregate_required` or `telemetry_required` | No raw session view. |
| `activity_counters` | tenant schema aggregates | Orders, inventory changes, invoices, payments, sync jobs where safe | `tenant_aggregate_required` | Counts only, windowed. Payment counters must not expose payment details. |
| `recent_errors` | application logs | Redacted error classes and correlation ids | `telemetry_required` | No raw request/response body. |
| `slow_routes` | logs/metrics/traces | Slow route names and counts | `telemetry_required` | Route name and latency bucket only. |
| `failed_jobs` | queue/job telemetry | Failed background job class/count | `telemetry_required` | No payloads. |
| `last_health_check_at` | derived platform snapshot | Last generated health snapshot time | `proposed_public_metadata` | Future platform-owned snapshot source. |

## SystemHealth Source Map

| Field | Source zone | Initial source decision | P10-A status | Notes |
| --- | --- | --- | --- | --- |
| `overall_status` | derived platform snapshot | Computed from system health gates | `manual_or_unknown` | Contract defines status enum only. |
| `api_status` | runtime metrics/logs | API availability and error rate | `telemetry_required` | P10-A defines shape only. |
| `database_status` | runtime metrics | DB connectivity status | `telemetry_required` | No direct DB admin operation. |
| `database_connections` | runtime metrics | Connection count and pool saturation | `telemetry_required` | Summary only. |
| `queue_status` | runtime metrics | Queue depth/backlog status | `telemetry_required` | Optional if queue not present. |
| `cpu_status` | runtime metrics | CPU pressure summary | `telemetry_required` | Optional in local/dev environments. |
| `memory_status` | runtime metrics | Memory pressure summary | `telemetry_required` | Optional in local/dev environments. |
| `disk_status` | runtime metrics | Disk pressure summary | `telemetry_required` | Optional in local/dev environments. |
| `error_rate` | application logs/metrics | API error rate summary | `telemetry_required` | Time-windowed. |
| `slow_request_count` | logs/metrics/traces | Count of slow requests | `telemetry_required` | No payloads. |
| `generated_at` | platform runtime | Response generation timestamp | `available_now` | Safe contract field. |

## PlatformAuditEvent Source Map

| Field | Source zone | Initial source decision | P10-A status | Notes |
| --- | --- | --- | --- | --- |
| `event_id` | `public` platform metadata | Platform audit event id | `proposed_public_metadata` | P10-A defines contract only. |
| `actor_id` | platform auth context | Platform actor id | `deferred` | Depends on platform auth decision. |
| `actor_role` | platform auth context | Super Admin / Support Operator / Engineering Operator | `deferred` | P10-A may define enum only. |
| `tenant_id` | `public` platform metadata | Target tenant or null for global | `proposed_public_metadata` | Required for tenant-scoped actions. |
| `scope` | audit metadata | `global`, `tenant`, `system`, `support` | `proposed_public_metadata` | Contract enum. |
| `action` | audit metadata | Action string | `proposed_public_metadata` | No implementation in P10-A. |
| `reason` | audit metadata | Required for support/elevated views | `proposed_public_metadata` | Must be required in P12+. |
| `result` | audit metadata | `allowed`, `denied`, `failed`, `completed` | `proposed_public_metadata` | Contract enum. |
| `metadata_redacted` | audit metadata | Redacted metadata object | `proposed_public_metadata` | Never raw sensitive payload. |
| `correlation_id` | logs/traces | Correlates audit, logs, and support bundle | `telemetry_required` | Contract can require nullable string. |
| `created_at` | audit metadata | Event timestamp | `proposed_public_metadata` | Required. |

## P10-A Contract Output Expectations

P10-A may produce:

- JSON schema or typed contract docs for the four contracts above.
- Example fixture JSON files with `unknown` and degraded states.
- API shape documentation only, such as proposed `GET /platform/contracts/tenant-summary` response examples.
- Test plan proving no runtime path edits.

P10-A may not produce:

- database migrations
- backend API handlers
- frontend components
- auth/RBAC/session code
- tenancy routing changes
- payment or business data code
