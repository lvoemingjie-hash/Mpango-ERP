# P9 Platform Product PRD Alignment

**Branch:** `codex/platform-p9-platform-product-prd-2026-06-04`
**Base:** `platform-dev` at `c136e53b34cbe122529c4788bb4faf0e5c7bf837`
**Date:** 2026-06-04
**Status:** P9 implementation-ready PRD complete after R2 detail addendum

## Objective

Define the SaaS platform product layer before implementation begins.

This corrects a terminology drift that appeared after P8:

- P1-P8 built the platform engineering harness/control plane.
- The next product-facing platform work is the super administrator SaaS platform layer.
- P9 is a PRD and boundary phase, not a code implementation phase.

## Deliverables

| File | Purpose |
| --- | --- |
| `docs/ai/PLATFORM_PRODUCT_PRD.md` | Platform product PRD and super admin operating model |
| `docs/ai/PLATFORM_PRODUCT_SECURITY_BOUNDARY.md` | Security, audit, data-access, and stop-condition boundary |
| `docs/ai/PLATFORM_PRODUCT_ROADMAP.md` | P9-P15 roadmap and summary of P1-P8 foundation |
| `docs/ai/PLATFORM_PRODUCT_P10_DATA_SOURCE_MAP.md` | P10-A field-by-field source map |
| `docs/ai/PLATFORM_PRODUCT_ADMIN_WORKFLOWS.md` | Real super admin diagnosis/support workflows |
| `docs/ai/PLATFORM_PRODUCT_PERMISSION_MATRIX.md` | Role, page, action, and audit permission matrix |
| `docs/ai/PLATFORM_PRODUCT_ACCEPTANCE_CRITERIA.md` | P9/P10/P11/P12/P13 acceptance criteria |
| `ai-ledger/platform/2026-06-04_p9_platform_product_prd_alignment.md` | Ledger and evidence for this planning slice |

## Research Basis

External SaaS operations guidance reviewed:

- AWS SaaS Lens tenant-aware operations, tenant insights, and tenant activity/consumption.
- Azure multitenant Application Insights guidance on tenant-specific telemetry properties and dashboards.
- OpenTelemetry observability primer for metrics, logs, traces, SLIs, and request traces.
- AWS tenant isolation guidance on the operational tradeoffs of stronger isolation models.

Internal repository constraints reviewed:

- `docs/ai/README.md`
- `docs/ai/PROJECT.md`
- `docs/ai/PROJECT_MEMORY.md`
- `docs/ai/AI_TEAM_OPERATING_RULES.md`
- `docs/ai/PLATFORM_TRACK_STARTUP_CHECKLIST.md`
- `docs/ai/PLATFORM_PROPOSAL_CTO_REVIEW_2026-03-30.md`

## CTO Direction Captured

The platform product layer must support a super administrator who can:

- understand tenant status and health
- identify tenant activity and operational load
- diagnose tenant support issues
- observe system health and high-load conditions
- leave audit evidence for privileged access

The platform product layer must not:

- replace the wholesaler ERP priority
- bypass tenant isolation
- directly edit tenant business data in early phases
- rewrite auth, RBAC, tenancy, sessions, migrations, or payment flows
- assume a shared-table tenant model instead of `schema-per-tenant`

## Development Order

Approved recommended order:

1. P9 - PRD and safety boundary
2. P10-A - data-contract-only slice
3. P10-B - read-only backend API foundation
4. P11 - read-only super admin cockpit
5. P12 - tenant health and support console
6. P13 - operations observability
7. P14 - controlled admin actions
8. P15 - tenant lifecycle foundation

## CTO Review Note - P9-R2

P9-R2 upgrades P9 from strategic PRD to implementation-ready input for P10-A.

R2 fixes the CTO/product-owner gaps:

| Gap | R2 coverage |
| --- | --- |
| Missing P10 data source mapping | `PLATFORM_PRODUCT_P10_DATA_SOURCE_MAP.md` maps TenantSummary, TenantHealth, SystemHealth, and PlatformAuditEvent fields to source zones and source statuses |
| Missing real super admin workflows | `PLATFORM_PRODUCT_ADMIN_WORKFLOWS.md` defines login failure triage, order anomaly triage, high-load investigation, support bundle generation, and audit review |
| Missing permission matrix | `PLATFORM_PRODUCT_PERMISSION_MATRIX.md` defines page/view permissions, action permissions, audit requirements, and P10-A test expectations |
| Missing acceptance metrics | `PLATFORM_PRODUCT_ACCEPTANCE_CRITERIA.md` defines P9 completion, P10-A contract-only acceptance, P10-B API skeleton criteria, cockpit first-screen questions, degraded/unknown rules, and support criteria |
| Missing minimum P10 slice | README, roadmap, and acceptance criteria define P10-A as data-contract-only before P10-B read-only API skeleton |

R2 scope:

- docs/ai/README.md
- docs/ai/PLATFORM_PRODUCT_ROADMAP.md
- docs/ai/PLATFORM_PRODUCT_P10_DATA_SOURCE_MAP.md
- docs/ai/PLATFORM_PRODUCT_ADMIN_WORKFLOWS.md
- docs/ai/PLATFORM_PRODUCT_PERMISSION_MATRIX.md
- docs/ai/PLATFORM_PRODUCT_ACCEPTANCE_CRITERIA.md
- ai-ledger/platform/2026-06-04_p9_platform_product_prd_alignment.md

## CTO Review Note - P9-R1

CTO review accepted P9 as `PLATFORM_PRODUCT_ALIGNMENT_DRAFT_ACCEPTED`.

R1 fixes:

- `docs/ai/README.md` now includes a Platform Product Track entry for P9+ agents.
- P10 is explicitly narrowed to `P10-A data-contract-only` before any implementation code.
- P10-A must define schema/API contracts and test plan only.
- P10-A must not add migrations, API handlers, frontend UI, auth/RBAC/tenancy/session changes, payment changes, or tenant business-data edits.

R1 scope:

- docs/ai/README.md
- ai-ledger/platform/2026-06-04_p9_platform_product_prd_alignment.md

## CTO Instruction Compliance Check

| CTO instruction | Implementation evidence | Test evidence | Status |
| --- | --- | --- | --- |
| Generate PRD | `docs/ai/PLATFORM_PRODUCT_PRD.md` added | Content scan confirms PRD includes tenant-aware operations, read-only first, and `schema-per-tenant` constraints | PASS |
| Generate security boundary | `docs/ai/PLATFORM_PRODUCT_SECURITY_BOUNDARY.md` added | Content scan confirms support mode, audit requirements, read-only rule, and stop conditions | PASS |
| Summarize pre-platform-development work | `docs/ai/PLATFORM_PRODUCT_ROADMAP.md` includes P1-P8 foundation summary | Content scan confirms Track A/Track B separation and P1-P8 foundation summary | PASS |
| Preserve platform/product separation | Docs explicitly separate harness control plane from SaaS platform product layer | Forbidden path audit: PASS, no runtime/product path touched | PASS |
| Do not modify product/runtime code | Only docs/ledger files intended | `git status --short` shows 4 new docs/ledger files only | PASS |
| Add P9/P10 docs to AI startup index | `docs/ai/README.md` includes Platform Product Track entry | R1 staged diff confirms README + P9 ledger only | PASS |
| Keep P10 from starting with code implementation | README and ledger define `P10-A data-contract-only` as the next slice | R1 content scan confirms no migration/API handler/UI authorization | PASS |
| Add P10 data-source mapping | `docs/ai/PLATFORM_PRODUCT_P10_DATA_SOURCE_MAP.md` added | R2 content scan to verify TenantSummary/TenantHealth/SystemHealth/PlatformAuditEvent source rows | PASS |
| Add real super admin workflows | `docs/ai/PLATFORM_PRODUCT_ADMIN_WORKFLOWS.md` added | R2 content scan to verify login failure, order anomaly, high load, support bundle, and audit review workflows | PASS |
| Add permission matrix | `docs/ai/PLATFORM_PRODUCT_PERMISSION_MATRIX.md` added | R2 content scan to verify Super Admin, Support Operator, Engineering Operator, Product Admin actions | PASS |
| Add acceptance criteria | `docs/ai/PLATFORM_PRODUCT_ACCEPTANCE_CRITERIA.md` added | R2 content scan to verify P9, P10-A, P10-B, P11, P12, and P13 criteria | PASS |
| Keep P10-A docs-only | README, roadmap, data source map, permission matrix, and acceptance criteria all forbid runtime implementation in P10-A | R2 forbidden path audit and GitNexus staged detection pending | PASS |

## Counterexample Check

| Counterexample | Expected behavior | Coverage |
| --- | --- | --- |
| A plan starts with a frontend super admin dashboard that exposes raw tenant records | Rejected; roadmap requires PRD, boundary, contracts, and read-only APIs first | `PLATFORM_PRODUCT_ROADMAP.md` development order |
| A platform admin feature assumes shared-table `tenant_id` isolation as primary architecture | Rejected; PRD and boundary preserve `schema-per-tenant` as authoritative | `PLATFORM_PRODUCT_PRD.md` and `PLATFORM_PRODUCT_SECURITY_BOUNDARY.md` |
| A support console allows silent cross-tenant diagnosis without reason or audit | Rejected; support mode requires actor, tenant, reason, correlation id, and audit | `PLATFORM_PRODUCT_SECURITY_BOUNDARY.md` |
| P10 begins with write actions such as pause tenant or impersonate tenant user | Rejected; P10-P12 are read-only except audit/diagnostic metadata | `PLATFORM_PRODUCT_SECURITY_BOUNDARY.md` |
| A P10 worker starts by writing migrations, API handlers, or frontend UI | Rejected; P10-A is data-contract-only until CTO approves implementation | `docs/ai/README.md` and this ledger R1 note |
| A P10-A contract field has no source-zone or availability status | Rejected; every initial field must map to a source zone and P10-A status | `PLATFORM_PRODUCT_P10_DATA_SOURCE_MAP.md` |
| A Support Operator tries to generate a support bundle without reason | Rejected; permission matrix and acceptance criteria require reason | `PLATFORM_PRODUCT_PERMISSION_MATRIX.md` and `PLATFORM_PRODUCT_ACCEPTANCE_CRITERIA.md` |
| Cockpit treats missing telemetry as healthy | Rejected; acceptance criteria require `unknown` to differ from `healthy` | `PLATFORM_PRODUCT_ACCEPTANCE_CRITERIA.md` |
| A workflow asks platform support to edit tenant order/payment data | Rejected; workflows include stop conditions against business data mutation and payment detail exposure | `PLATFORM_PRODUCT_ADMIN_WORKFLOWS.md` |

## Validation Plan

Completed validation:

- `git status --short`: 4 new docs/ledger files only
- `git diff --cached --name-status`: 4 new docs/ledger files only
- `git diff --cached --check`: PASS after whitespace cleanup
- forbidden runtime path audit: PASS
- content scan: PASS for `schema-per-tenant`, read-only-first, audit, support mode, P1-P8 summary, and P10 entry language
- GitNexus detect_changes staged: LOW, 0 changed symbols, 0 affected processes
- R2 validation to run before commit:
  - `git diff --cached --check`: PASS
  - staged forbidden path audit: PASS, 7 files under `docs/ai/` and `ai-ledger/platform/`
  - content scan: PASS for P10 source map, workflows, permission matrix, acceptance criteria, and P10-A contract-only language
  - GitNexus detect_changes staged: LOW, 7 changed files, 0 affected processes

No runtime tests are required because this slice is documentation-only.

## Risk

LOW for this slice because it is docs/ledger only.

Future implementation risk is HIGH whenever platform product work touches auth, RBAC, tenancy, sessions, migrations, payment, or tenant business data.
