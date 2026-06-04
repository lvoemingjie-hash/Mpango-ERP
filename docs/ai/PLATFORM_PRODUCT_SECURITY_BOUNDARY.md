# Mpango Platform Product Security Boundary

**Phase:** P9 - Platform Product PRD & Super Admin Operating Model
**Status:** Draft boundary for platform product development
**Date:** 2026-06-04

## Purpose

This document defines what the Mpango platform super administrator may see and do, and what must remain protected by tenant isolation, authorization, and audit controls.

The platform admin surface is powerful by design. That power must be constrained before implementation starts.

## Non-Negotiable Architecture Constraints

- `schema-per-tenant` remains the primary isolation architecture.
- JWT carries `tenant_id` and `tenant_schema` for tenant-scoped product flows.
- Search-path routing remains authoritative for tenant DB access.
- Tenant-key filtering is defense in depth, not a replacement for schema routing.
- Platform product work must not rewrite product auth, RBAC, tenancy, session, migration, or payment flows without explicit CTO gate.

## Platform Data Zones

### Public Platform Zone

Expected location: `public` schema or equivalent platform-owned metadata surface.

Allowed platform-owned records:

- tenant registry metadata
- tenant status
- tenant tier or stage
- platform audit events
- support session metadata
- health check summaries
- feature flag and quota metadata

These records can reference tenant identity and schema names. They should not duplicate raw tenant business data.

### Tenant Schema Zone

Expected location: per-tenant schemas.

Protected tenant-owned records:

- orders
- inventory records
- payments
- invoices
- customer or retailer records
- user-generated business content
- tenant-specific operational transactions

The platform admin surface may show aggregated counters and diagnostics from this zone only through approved read-only contracts.

### Infrastructure/Runtime Zone

Operational sources:

- logs
- metrics
- traces
- queue state
- database health
- process health
- runner or deployment status

These sources must be correlated with tenant context where safe, but should not leak sensitive payloads.

## Access Model

### Super Administrator

Allowed:

- view platform overview
- view tenant directory
- view tenant health summaries
- generate support bundles
- view platform audit logs
- trigger read-only health checks
- perform approved controlled actions after P13

Not allowed by default:

- edit tenant business data
- bypass product-level business rules
- impersonate a tenant user
- view sensitive raw payloads without reason and audit
- perform destructive operations without a dedicated gate

### Support Operator

Allowed:

- view assigned tenant health
- generate support bundle with reason
- view recent platform diagnostics

Not allowed:

- change tenant status
- change platform configuration
- view billing/payment secrets
- edit business data

### Engineering Operator

Allowed:

- view system health
- inspect logs/metrics/traces with redaction
- run read-only diagnostics
- participate in incident response

Not allowed:

- perform product data edits
- change tenant lifecycle state unless explicitly authorized

## Support Mode Rules

Support mode is any state where a platform actor is viewing tenant-specific diagnostics beyond the global overview.

Requirements:

- actor identity is required
- tenant identity is required
- reason is required
- correlation id is required
- start and end timestamps are recorded
- every generated diagnostic artifact is logged
- sensitive fields are redacted by default

Support mode must be visible in the platform audit trail.

## Audit Requirements

The following actions must create audit events:

- platform admin login
- tenant directory view
- tenant detail view
- support mode start
- support mode end
- support bundle generation
- read-only health check trigger
- tenant status change
- feature flag change
- quota change
- failed authorization attempt
- rejected unsafe operation

Audit events must include:

- actor id
- actor role
- tenant id or global scope
- action
- reason where applicable
- result
- timestamp
- correlation id
- redacted metadata

## Read-Only First Rule

P10-P12 must be read-only except for audit writes and generated diagnostic artifacts.

Read-only means:

- no tenant business data mutation
- no tenant lifecycle mutation
- no product auth/session mutation
- no migration changes
- no payment state changes

Allowed writes in P10-P12:

- platform audit events
- support session metadata
- generated support bundle metadata
- health check snapshots, if explicitly scoped as platform-owned summaries

## Controlled Action Gate

Before any write action enters P13 or later, it must define:

- exact actor role allowed
- exact target scope
- required reason
- expected state transition
- audit event shape
- rollback or reversal path
- failure behavior
- tests for unauthorized access
- tests for tenant boundary violations

## Data Redaction Rules

Default platform views may show:

- counts
- statuses
- timestamps
- route names
- error classes
- correlation ids
- tenant schema names
- tenant metadata

Default platform views must not show:

- payment secrets
- raw tokens
- passwords
- private keys
- sensitive customer personal data
- full raw order payloads
- raw request/response bodies
- tenant data from a different tenant context

## Stop Conditions

Stop implementation and escalate if a platform task requires:

- changing the tenancy model
- broad auth or RBAC rewrite
- direct edits to product business data
- cross-tenant data joins that expose raw tenant records
- migrations that alter active product tables
- session or impersonation logic
- payment state changes
- production infrastructure changes

## P10 Entry Gate

P10 may begin only after:

- PRD is accepted by CTO/product owner
- this security boundary is accepted
- data contracts are drafted
- first implementation slice is read-only
- expected files are bounded
- tests and ledger expectations are defined
