# Mpango Platform Product PRD

**Phase:** P9 - Platform Product PRD & Super Admin Operating Model
**Status:** Draft for CTO/product-owner alignment
**Date:** 2026-06-04
**Owner:** Jeff, Platform CTO Governance

## Executive Summary

Mpango needs a SaaS platform administration layer for a super administrator to observe, diagnose, support, and operate a multi-tenant ERP safely. This platform product is not a replacement for the wholesaler ERP product and must not drift the tenancy model. It is a control and support surface for the platform team.

The first platform product milestone must prioritize read-only visibility, tenant-aware diagnosis, and auditability. Write operations come later, after access policy, support justification, and rollback behavior are explicit.

## Strategic Fit

Mpango's product truth remains:

- Product first, platform second.
- Primary customer is the wholesaler.
- Retailer workflows support wholesaler throughput and retention.
- Multi-tenant safety is a hard constraint.
- `schema-per-tenant` is the primary isolation model.

The platform product exists to keep the SaaS operation healthy as tenants grow. It should help the platform team answer:

- Which tenants are active, unhealthy, or at risk?
- Which tenants are creating load, errors, or operational tickets?
- What changed recently across tenant activity, system health, and admin actions?
- Can support diagnose a tenant issue without bypassing isolation or silently viewing sensitive business data?

## External Research Basis

This PRD is shaped by current SaaS operations guidance:

- AWS SaaS Lens emphasizes tenant-aware operational views, tenant activity, consumption, tenant tiers, and tenant insights.
- Azure multitenant monitoring guidance recommends tenant identifiers or similar custom properties on telemetry so operations teams can filter, alert, and report per tenant.
- OpenTelemetry frames observability as metrics, logs, and traces, with service/user-facing indicators and trace context for debugging distributed or hard-to-reproduce behavior.
- AWS tenant isolation guidance shows that stronger isolation improves clarity and control, but increases operational complexity and automation needs.

Reference URLs:

- https://docs.aws.amazon.com/wellarchitected/latest/saas-lens/tenant-aware-operations.html
- https://docs.aws.amazon.com/wellarchitected/latest/saas-lens/tenant-insights.html
- https://docs.aws.amazon.com/wellarchitected/latest/saas-lens/tenant-activity-and-consumption.html
- https://learn.microsoft.com/en-us/azure/architecture/guide/multitenant/service/application-insights
- https://opentelemetry.io/docs/concepts/observability-primer/
- https://docs.aws.amazon.com/whitepapers/latest/saas-tenant-isolation-strategies/full-stack-isolation.html

## Personas

### Platform Super Administrator

Jeff or an authorized platform operator responsible for tenant support, platform health, incident response, and controlled operational changes.

Primary needs:

- See the platform health at a glance.
- Identify tenant-level issues quickly.
- Diagnose support tickets without unsafe cross-tenant access.
- Understand system load, error trends, and operational risk.
- Leave an audit trail for every privileged action.

### Support Operator

A future restricted platform role that can view tenant health and generate support bundles, but cannot change tenant business data or platform configuration.

### Engineering Operator

A future role focused on system health, migrations, runner validation, logs, metrics, queue health, and incident response.

## Product Principles

1. **Tenant-aware, not tenant-invasive.**
   The platform should show operational summaries and diagnostics first, not raw business records by default.

2. **Read-only before write.**
   P10-P12 should focus on observation and diagnosis. Controlled actions start only after audit and authorization are in place.

3. **Every privileged action is auditable.**
   Viewing tenant support context, exporting diagnostics, changing status, or triggering an operational action must create an audit event.

4. **Schema-per-tenant remains authoritative.**
   Platform features must map cleanly to tenant schemas and `public` platform records. No feature may assume a shared-table tenant model unless a future decision record changes architecture.

5. **Operational clarity beats feature breadth.**
   The first cockpit should answer a few critical questions reliably instead of becoming a broad admin panel with weak controls.

## Functional Scope

### P10 - Super Admin Cockpit Foundation

Goal: give the platform team a read-only home page.

Features:

- Platform overview cards:
  - total tenants
  - active tenants
  - unhealthy tenants
  - tenants with recent errors
  - system health summary
  - recent platform admin actions
- Tenant directory:
  - tenant id
  - tenant name
  - tenant schema
  - status
  - tier or stage
  - user count summary
  - recent activity timestamp
  - health status
- No tenant impersonation.
- No tenant business data editing.
- No destructive operation.

### P11 - Tenant Health & Support Console

Goal: let support diagnose one tenant safely.

Features:

- Tenant health profile:
  - login activity summary
  - recent API or route error summary
  - key ERP activity counters, such as orders, inventory changes, payments, invoices, and sync jobs where available
  - slow request and failed job summary
  - tenant schema status
- Support bundle:
  - generated read-only diagnostic package
  - includes request correlation ids, recent errors, health checks, and relevant platform metadata
  - excludes sensitive raw business payloads by default
- Required support reason before elevated support view.
- Audit event for each support view and bundle generation.

### P12 - Operations Observability

Goal: help the platform team respond to high load and incidents.

Features:

- System health:
  - API availability
  - database connectivity
  - DB connection count
  - queue depth or background task backlog when available
  - CPU, memory, disk, and process health where available
  - slow query or slow route summary
  - error rate by route and tenant where safe
- Tenant-aware operational view:
  - high-activity tenants
  - high-error tenants
  - noisy-neighbor signals
  - per-tenant activity and consumption trends
- Alert readiness:
  - define alert thresholds
  - do not build pager automation until metrics are reliable

### P13 - Audit & Controlled Admin Actions

Goal: add a narrow set of safe platform actions.

Features:

- Platform audit event model and viewer.
- Controlled actions:
  - mark tenant under review
  - pause tenant login
  - resume tenant login
  - trigger read-only health check
  - generate support bundle
- Required fields:
  - actor id
  - role
  - tenant id or global scope
  - reason
  - action
  - result
  - timestamp
  - correlation id
- No direct business data mutation.

### P14 - Tenant Lifecycle Foundation

Goal: prepare for safe tenant administration.

Features:

- Tenant creation readiness checklist.
- Tenant status transitions:
  - draft
  - active
  - paused
  - suspended
  - archived
- Tier, feature flag, and quota definitions.
- Backup/export status visibility.
- Provisioning and schema lifecycle integration design.

## Data Contracts

The first implementation should define contracts before UI.

### TenantSummary

- `tenant_id`
- `tenant_name`
- `tenant_schema`
- `status`
- `tier`
- `created_at`
- `last_activity_at`
- `user_count`
- `health_status`
- `recent_error_count`
- `support_mode_active`

### TenantHealth

- `tenant_id`
- `tenant_schema`
- `health_status`
- `schema_status`
- `last_login_at`
- `activity_counters`
- `recent_errors`
- `slow_routes`
- `failed_jobs`
- `last_health_check_at`

### SystemHealth

- `overall_status`
- `api_status`
- `database_status`
- `database_connections`
- `queue_status`
- `cpu_status`
- `memory_status`
- `disk_status`
- `error_rate`
- `slow_request_count`
- `generated_at`

### PlatformAuditEvent

- `event_id`
- `actor_id`
- `actor_role`
- `tenant_id`
- `scope`
- `action`
- `reason`
- `result`
- `metadata_redacted`
- `correlation_id`
- `created_at`

## Non-Functional Requirements

- Platform pages must load with degraded data if one diagnostic source is unavailable.
- Tenant summaries must never require opening every tenant schema synchronously on every page load.
- Health endpoints must be read-only until P13.
- Platform APIs must use explicit platform-only authorization.
- All cross-tenant support views must be audited.
- Sensitive payloads must be redacted by default.
- The UI must distinguish "unknown" from "healthy".

## Out of Scope for P10-P12

- Direct cross-tenant business data editing.
- Tenant impersonation.
- Payment, auth, RBAC, tenancy, migration, or session rewrites.
- Billing automation.
- Public customer-facing marketplace capabilities.
- Infrastructure auto-scaling automation.
- Production deployment changes.

## Open Decisions

- Which existing product roles can ever become platform roles?
- Whether platform tables live only in `public` and how they reference `public.wholesalers`.
- Which tenant activity counters can be safely aggregated without privacy risk.
- What minimum server metrics are available in the current deployment environment.
- Whether support bundle generation should be async from day one.

## Acceptance Criteria for P9

- PRD exists in repo shared memory.
- Platform safety boundary exists in repo shared memory.
- Roadmap separates platform product work from AI harness work.
- P10 starts from data contracts and read-only backend APIs, not from a speculative UI.
- No runtime code changes are made in P9.
