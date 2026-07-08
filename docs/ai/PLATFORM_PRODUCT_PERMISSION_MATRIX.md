# Platform Product Permission Matrix

**Phase:** P9-R2 / P10-A input
**Status:** Implementation-ready planning draft
**Date:** 2026-06-04

## Purpose

This matrix defines the initial platform roles and allowed operations before implementation begins.

P10-A may document this matrix and create test-plan expectations only. It must not implement authorization code.

## Roles

| Role | Description |
| --- | --- |
| Super Admin | Full platform owner role for Jeff or explicitly trusted platform operators. Can view platform-wide diagnostics and later perform controlled actions. |
| Support Operator | Restricted support role. Can view assigned tenant diagnostics and generate support bundles with reason. Cannot change tenant state or platform configuration. |
| Engineering Operator | Restricted operations role. Can view system health, logs/metrics/traces summaries, and incident diagnostics. Cannot access raw tenant business data by default. |
| Product Admin | Tenant/product-side role. Not a platform operator. Must not access platform cockpit unless separately granted a platform role. |

## Page/View Permissions

| Page/View | Super Admin | Support Operator | Engineering Operator | Product Admin | Notes |
| --- | --- | --- | --- | --- | --- |
| Platform overview dashboard | View | View limited | View system-focused | No | Support sees tenant support queue only when assigned. |
| Tenant directory | View all | View assigned only | View metadata only | No | Assigned-only support scope must be explicit. |
| Tenant health profile | View all with audit | View assigned with reason/audit | View technical summaries with reason/audit | No | Raw business records excluded. |
| System health | View | View limited status | View | No | Engineering role sees most operational diagnostics. |
| Audit log | View all | View own/assigned support events | View operational events | No | Audit log access itself should be audited in later phases. |
| Support bundle preview | View/generate with reason | Generate assigned with reason | Generate technical bundle with reason | No | Bundles are redacted by default. |
| Controlled actions page | Future | No | Future limited | No | Not in P10-A/P10-B/P11/P12. |

## Action Permissions

| Action | Super Admin | Support Operator | Engineering Operator | Product Admin | P10-A status |
| --- | --- | --- | --- | --- | --- |
| View platform summary | Allow | Limited | Allow system-focused | Deny | Contract/test-plan only |
| View tenant summary | Allow | Assigned only | Metadata only | Deny | Contract/test-plan only |
| View tenant health | Allow with audit | Assigned + reason + audit | Technical summary + reason + audit | Deny | Contract/test-plan only |
| Generate support bundle | Allow with reason | Assigned + reason | Technical bundle + reason | Deny | Contract/test-plan only |
| Trigger read-only health check | Future P13 | No | Future P13 | No | Deferred |
| Pause tenant login | Future P14 | No | No | No | Deferred |
| Resume tenant login | Future P14 | No | No | No | Deferred |
| Change feature flags | Future P14 | No | No | No | Deferred |
| Change quota/tier | Future P14/P15 | No | No | No | Deferred |
| Impersonate tenant user | Deny by default | Deny | Deny | Deny | Out of scope |
| Edit tenant business data | Deny | Deny | Deny | Product-side only by normal product permissions | Out of scope |
| View raw payment details/secrets | Deny by default | Deny | Deny | Product-side only if already permitted | Out of scope / HIGH gate |
| Modify auth/RBAC/session behavior | Deny in platform product flow | Deny | Deny | Deny | HIGH gate |
| Run migrations | Deny in platform product flow | Deny | Deny unless separate ops gate | Deny | HIGH gate |

## Audit Requirements by Action

| Action category | Audit required | Reason required | Correlation id required |
| --- | --- | --- | --- |
| Platform overview view | Yes, aggregate or sampled in later implementation | No | Yes when available |
| Tenant directory view | Yes | No | Yes when available |
| Tenant health view | Yes | Yes for support/elevated view | Yes |
| Support bundle generation | Yes | Yes | Yes |
| System health view | Yes in later implementation | No | Yes when available |
| Denied operation | Yes | Optional | Yes when available |
| Controlled action | Yes | Yes | Yes |

## P10-A Test Plan Expectations

P10-A should define tests that prove the contract rejects:

- Product Admin access to platform contracts.
- Support Operator access to unassigned tenant summaries.
- Support Operator support bundle without reason.
- Engineering Operator request for raw business payloads.
- Any role attempting impersonation.
- Any role attempting tenant business-data edit through platform contracts.
- Any P10-A deliverable that introduces migration/API handler/UI code.

## Open Decisions

- How assigned support scope is represented.
- Whether platform roles are separate from product roles or mapped from an existing auth model later.
- Whether platform audit events are stored in a new public table or another platform-owned store.
- How audit access itself is audited.
