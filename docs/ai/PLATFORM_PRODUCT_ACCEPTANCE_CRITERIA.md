# Platform Product Acceptance Criteria

**Phase:** P9-R2 / P10-A input
**Status:** Implementation-ready planning draft
**Date:** 2026-06-04

## Purpose

This document defines acceptance criteria for the first SaaS platform product phases.

P10-A is accepted only when it produces contracts and test plans. It is not accepted if it writes runtime code.

## P9 Completion Criteria

P9 is complete when:

- Platform product PRD exists.
- Security boundary exists.
- Roadmap separates harness control plane from SaaS platform product layer.
- Data source map exists for P10 contracts.
- Super admin workflows exist.
- Permission matrix exists.
- Acceptance criteria exist.
- README startup index includes the platform product track.
- Ledger records that P10 starts with data-contract-only.
- No runtime code is changed.

## P10-A Data-Contract-Only Acceptance Criteria

P10-A must produce:

- Contract definitions for:
  - `TenantSummary`
  - `TenantHealth`
  - `SystemHealth`
  - `PlatformAuditEvent`
- Per-field source mapping using the statuses in `PLATFORM_PRODUCT_P10_DATA_SOURCE_MAP.md`.
- Example fixtures for:
  - healthy tenant
  - degraded tenant
  - unknown tenant health
  - system degraded
  - support bundle denied because reason is missing
  - support operator denied for unassigned tenant
- Test plan that proves:
  - no migrations were added
  - no API handlers were added
  - no frontend UI was added
  - no auth/RBAC/tenancy/session/payment/business data files were touched
  - contracts distinguish `unknown` from `healthy`
  - support/elevated views require reason and audit contract fields

P10-A must not produce:

- database migrations
- backend API handlers
- frontend components
- auth/RBAC/session changes
- tenancy routing changes
- payment changes
- tenant business-data mutation logic

## P10-B Read-Only API Skeleton Acceptance Criteria

P10-B may begin only after P10-A is accepted.

P10-B must:

- Implement read-only API skeletons only after contract acceptance.
- Return fixture-backed or explicitly safe read-only responses where real sources are unavailable.
- Use `unknown` for unavailable telemetry.
- Include tests for degraded/unknown responses.
- Include forbidden path audit and GitNexus detect_changes evidence.
- Avoid migrations unless a separate CTO gate approves a platform-owned metadata store.

## P11 Cockpit Acceptance Criteria

The first read-only cockpit must answer these first-screen questions:

1. How many tenants exist?
2. How many tenants are active?
3. Which tenants are unhealthy or unknown?
4. Is system health healthy, degraded, unhealthy, or unknown?
5. Are there recent platform admin/support actions?
6. Are there tenants with recent errors?

The cockpit must:

- show `unknown` distinctly from `healthy`
- degrade gracefully if one diagnostic source is unavailable
- never show raw tenant business records on the overview
- never offer write/destructive buttons in P11
- link to tenant detail only through audited support/diagnostic path in later phases

Allowed unknown behavior:

- P11 may show unknown for telemetry-backed fields if instrumentation is unavailable.
- P11 may show unknown for tier/status if platform registry metadata is unavailable.
- P11 must not treat unknown as pass/healthy.

## P12 Support Console Acceptance Criteria

P12 must:

- require a support reason before elevated tenant diagnostics
- generate or preview redacted support bundle only
- record audit contract fields for support mode and bundle generation
- show activity counters as summaries only
- exclude raw order, payment, customer, token, or session payloads

## P13 Observability Acceptance Criteria

P13 must:

- show system health with degraded/unknown states
- include API, DB, queue, CPU, memory, disk, error rate, and slow request summaries where available
- avoid heavy observability infrastructure unless current deployment needs it
- avoid automatic remediation or autoscaling actions

## General Platform Acceptance Gates

Every P10+ slice must report:

- branch
- commit
- modified files
- tests
- report path
- risk
- forbidden path audit
- GitNexus detect_changes result
- counterexamples rejected

Stop and escalate if any slice touches:

- auth
- RBAC
- tenancy routing
- sessions
- migrations
- payments
- tenant business data mutation
- production infrastructure
