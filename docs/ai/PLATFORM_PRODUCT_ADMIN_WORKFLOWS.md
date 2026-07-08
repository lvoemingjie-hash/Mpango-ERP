# Platform Product Super Admin Workflows

**Phase:** P9-R2 / P10-A input
**Status:** Implementation-ready planning draft
**Date:** 2026-06-04

## Purpose

This document captures the first real super administrator workflows that the SaaS platform product must eventually support.

P10-A remains data-contract-only. These workflows guide contract design; they do not authorize implementation code.

## Workflow 1 - Tenant Login Failure Triage

User story:

> A tenant reports that staff cannot log in. The platform super administrator needs to determine whether the issue is tenant-specific, system-wide, configuration-related, or an auth/session incident.

Steps:

1. Open Platform Overview Dashboard.
2. Check `SystemHealth.api_status`, `database_status`, and `error_rate`.
3. Open Tenant Directory and search the tenant by name, id, or schema.
4. Open Tenant Health Profile.
5. Review:
   - `schema_status`
   - `last_login_at`
   - recent auth/login error summaries, redacted
   - recent API error count
   - support mode active state
6. If tenant-specific diagnostics are needed, start support mode with reason: "tenant login failure triage".
7. Generate or preview support bundle with correlation ids and redacted errors.
8. Record triage outcome:
   - system-wide issue
   - tenant schema unreachable
   - tenant configuration issue
   - auth/session product issue requiring product CTO gate
   - insufficient telemetry

Contract implications:

- `TenantSummary` needs `health_status`, `recent_error_count`, and `last_activity_at`.
- `TenantHealth` needs `last_login_at`, `recent_errors`, and `schema_status`.
- `PlatformAuditEvent` needs support view and support bundle events.
- `SystemHealth` needs system-wide API/DB status to distinguish tenant-specific vs global failure.

Stop conditions:

- Do not inspect raw passwords, tokens, sessions, or private auth payloads.
- Do not modify auth/RBAC/session code as part of P10-A.
- If diagnosis requires auth/session changes, stop and open a HIGH gate.

## Workflow 2 - Tenant Order Activity Anomaly

User story:

> A wholesaler says orders look wrong or stopped flowing. The super administrator needs to see whether this is a tenant activity issue, a background job issue, or a product workflow bug.

Steps:

1. Search tenant in Tenant Directory.
2. Open Tenant Health Profile.
3. Review safe activity counters:
   - orders count by time window
   - inventory changes count by time window
   - invoice/payment counters where safe
   - failed jobs count
4. Compare counters with recent errors and slow routes.
5. Start support mode with reason: "tenant order anomaly triage" if deeper diagnostic bundle is needed.
6. Generate support bundle containing:
   - aggregate activity counters
   - redacted route errors
   - failed job classes/counts
   - correlation ids
   - no raw order payloads
7. Decide outcome:
   - tenant inactivity
   - failed background job
   - product workflow bug
   - data inconsistency requiring product-side investigation
   - insufficient telemetry

Contract implications:

- `TenantHealth.activity_counters` must support windowed counts.
- `TenantHealth.failed_jobs` must be a redacted summary.
- Support bundle contract must exclude raw tenant business records by default.

Stop conditions:

- Do not edit order, inventory, invoice, or payment data from platform console.
- Do not expose raw order payloads in platform summary.
- Payment-related details remain HIGH gate.

## Workflow 3 - High Load / Noisy Tenant Investigation

User story:

> The system is slow. The platform team needs to know whether the issue is global, infrastructure-related, or driven by a high-activity tenant.

Steps:

1. Open Platform Overview Dashboard.
2. Review `SystemHealth`:
   - API status
   - database status
   - database connection pressure
   - queue status
   - CPU/memory/disk pressure
   - error rate
   - slow request count
3. Review high-activity tenant list from Tenant Directory or future Operations Observability.
4. Identify tenants with:
   - high recent activity
   - high error count
   - high slow route count
5. For a suspect tenant, open Tenant Health Profile.
6. Generate a redacted support/ops bundle if needed.
7. Decide outcome:
   - platform infrastructure pressure
   - DB connection saturation
   - queue backlog
   - tenant activity spike
   - unknown due to missing telemetry

Contract implications:

- `SystemHealth` must expose degraded/unknown states.
- `TenantSummary` must support recent activity and error summaries.
- Telemetry missing should produce `unknown`, not `healthy`.

Stop conditions:

- P10-A does not implement autoscaling.
- P10-A does not modify deployment or production infrastructure.
- Any runtime remediation remains outside P10-A.

## Workflow 4 - Safe Support Bundle Generation

User story:

> Support needs a portable diagnostic package to hand to engineering without leaking sensitive tenant payloads.

Steps:

1. Actor opens Tenant Health Profile.
2. Actor enters support reason.
3. Platform validates actor role and support scope.
4. Platform records support mode start audit event.
5. Platform gathers safe diagnostic summaries:
   - tenant metadata
   - health summary
   - redacted recent errors
   - correlation ids
   - windowed activity counters
   - failed job summaries
6. Platform writes support bundle metadata and audit event.
7. Platform records support mode end or expiry.

Contract implications:

- `PlatformAuditEvent` must include action, reason, result, scope, and correlation id.
- Support bundle contract must classify every field as safe summary, redacted diagnostic, or forbidden.

Stop conditions:

- No raw request/response bodies.
- No passwords, tokens, keys, payment secrets, or private customer data.
- No tenant business-data mutation.

## Workflow 5 - Platform Admin Reviews Audit Trail

User story:

> Jeff wants to verify who accessed tenant support context and why.

Steps:

1. Open Audit & Access Log.
2. Filter by tenant, actor, action, time window, or result.
3. Review support mode events and bundle generation events.
4. Verify each elevated access has a reason.
5. Escalate missing reason or denied access attempts.

Contract implications:

- `PlatformAuditEvent` must be queryable by actor, tenant, action, and time window.
- P10-A must define the event shape before audit storage implementation.

Stop conditions:

- Audit logs are append-only in design.
- No actor may silently delete or rewrite audit events without a future dedicated governance decision.
