# Mpango Platform Product Roadmap

**Phase:** P9 onward
**Status:** Draft roadmap for platform product layer
**Date:** 2026-06-04

## Track Separation

Mpango now has two platform-related tracks:

### Track A - Platform Engineering Control Plane

Purpose: make AI agents, runner validation, evidence, and merge governance safe.

Status:

- P1-P8 delivered the harness engineering foundation.
- P8 introduced a governed worker orchestrator with mission validation, worker execution, artifact writing, final diff audit, and evidence outputs.
- This track remains important for safe implementation, but it is not the SaaS platform product itself.

### Track B - SaaS Platform Product Layer

Purpose: give the Mpango platform team a super admin cockpit for tenant-aware operations, support, audit, and system health.

Status:

- Starts with P9 PRD and safety boundary.
- P10 begins the first product implementation slice.

## Completed Foundation Summary

### P1-P8 Harness Foundation

Outcome:

- Shared AI operating rules were synchronized.
- Platform preflight, runner gate, directive gate, mission gate, worker bridge, batch readiness, diff auditor, health check, and merge readiness tooling were established.
- The branch and evidence discipline required for worker-driven development is now in place.
- The platform team can delegate bounded work while preserving expected-file, forbidden-path, test, secret, GitNexus, and ledger gates.

Effect:

- Claude/opencode/Codex can work under a governed harness.
- CTO review can focus on evidence and counterexamples.
- Platform product work can now start without abandoning safety gates.

### Why P9 Exists

P1-P8 created the production line. P9 defines what the platform product should be.

Without P9, implementation would risk mixing:

- AI engineering control plane features
- SaaS super admin features
- product ERP business features
- deployment/operations tooling

P9 separates these concerns before P10 code starts.

## Roadmap

### P9 - Platform Product PRD & Super Admin Operating Model

Goal:

- Define the platform product scope, safety boundary, and development plan.

Deliverables:

- `docs/ai/PLATFORM_PRODUCT_PRD.md`
- `docs/ai/PLATFORM_PRODUCT_SECURITY_BOUNDARY.md`
- `docs/ai/PLATFORM_PRODUCT_ROADMAP.md`
- `docs/ai/PLATFORM_PRODUCT_P10_DATA_SOURCE_MAP.md`
- `docs/ai/PLATFORM_PRODUCT_ADMIN_WORKFLOWS.md`
- `docs/ai/PLATFORM_PRODUCT_PERMISSION_MATRIX.md`
- `docs/ai/PLATFORM_PRODUCT_ACCEPTANCE_CRITERIA.md`
- P9 ledger

Exit criteria:

- CTO/product owner accepts PRD.
- Platform product layer is clearly separated from harness engineering.
- P10-A scope is data-contract-only and bounded.

### P10-A - Platform Data Contracts Only

Goal:

- Define platform data contracts, source mapping, examples, and test plan before any runtime code is written.

Allowed deliverables:

- TenantSummary contract
- TenantHealth contract
- SystemHealth contract
- PlatformAuditEvent contract
- per-field source map
- example fixtures for healthy, degraded, and unknown states
- permission and workflow-driven test plan
- explicit no-runtime-code evidence

Implementation posture:

- documentation and contract artifacts only
- no migrations
- no backend API handlers
- no frontend UI
- no auth/RBAC/tenancy/session/payment changes
- no tenant business-data edits

### P10-B - Read-Only API Skeleton

Goal:

- Implement read-only API skeletons only after P10-A contracts are accepted.

Likely deliverables:

- read-only platform API skeleton
- fixture-backed or explicitly safe responses where real sources are unavailable
- tests for degraded and unknown states
- tests proving no product/runtime mutation

Implementation posture:

- backend first, contract-driven
- no frontend production UI yet
- no controlled write actions except audit/diagnostic records if explicitly approved
- no migrations unless a dedicated CTO gate approves a platform-owned metadata store

### P11 - Super Admin Cockpit Foundation

Goal:

- Build the first read-only platform admin UI backed by P10 contracts.

Likely deliverables:

- platform overview dashboard
- tenant directory
- basic health indicators
- recent audit events

Implementation posture:

- frontend consumes read-only APIs
- no impersonation
- no business data editing
- UI must show unknown/degraded states clearly

### P12 - Tenant Health & Support Console

Goal:

- Provide tenant-specific support diagnosis without unsafe raw data access.

Likely deliverables:

- tenant health detail page
- support reason capture
- support bundle generation design or implementation
- audit events for support views

Implementation posture:

- read-only
- redacted by default
- all support views audited

### P13 - Operations Observability

Goal:

- Add system health and tenant-aware operational insight.

Likely deliverables:

- system health endpoint/page
- error rate and slow route summaries
- queue/DB/resource health summaries
- noisy-neighbor signals

Implementation posture:

- use metrics/logs/traces concepts
- avoid building heavy observability infrastructure before the current deployment needs it

### P14 - Controlled Admin Actions

Goal:

- Introduce narrow write operations with strict audit and rollback rules.

Likely deliverables:

- pause/resume tenant login
- mark tenant under review
- trigger read-only health check
- feature flag or quota change scaffolding

Implementation posture:

- every action requires actor, reason, audit event, and tests
- no direct business data mutation

### P15 - Tenant Lifecycle Foundation

Goal:

- Prepare tenant provisioning and lifecycle management.

Likely deliverables:

- tenant lifecycle state machine
- tenant creation checklist
- schema provisioning status visibility
- backup/export status visibility

Implementation posture:

- only after P10-P14 prove read-only and controlled action paths

## Development Order

The approved order for SaaS platform product work is:

1. PRD and safety boundary
2. data source map, workflows, permission matrix, and acceptance criteria
3. P10-A data-contract-only
4. P10-B read-only backend API skeleton
5. frontend cockpit
6. tenant support console
7. operations observability
8. controlled admin actions
9. tenant lifecycle management

This differs from a normal product feature because the super admin surface has higher blast radius. The team must define what is legal and auditable before exposing powerful UI affordances.

## Governance Rules

- Every P10+ slice uses an isolated branch.
- Every slice has mission/result/events/ledger where applicable.
- Product runtime, tenancy, auth, RBAC, session, migration, and payment paths remain HIGH gate.
- Forbidden path audit remains mandatory.
- GitNexus detect_changes remains mandatory before merge.
- Shared docs changes must be kept synchronized across platform/product lines when accepted.
