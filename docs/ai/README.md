# AI Context Entry

This folder is the canonical starting point for Codex and other AI coding agents working on Mpango ERP.

## Read Order

1. `docs/ai/CTO_CURRENT_OPS.md`
2. `docs/ai/CTO_COCKPIT.md`
3. `docs/ai/CTO_CONTEXT.md`
4. `docs/ai/PROJECT.md`
5. `docs/ai/PROJECT_MEMORY.md`
6. `docs/ai/AI_TEAM_OPERATING_RULES.md`
7. `docs/ai/AGENT_DELEGATION_PROTOCOL.md`
8. `docs/contracts/Boot contract.md`
9. `docs/contracts/AI workrules.md`
10. `docs/mpango_erp_v0_3_development_master_plan.md`
11. `decision-register/README.md`

## Platform Product Track Entry

For P9+ SaaS platform product work, read these after the general context above and before writing any platform product code:

1. `docs/ai/PLATFORM_PRODUCT_PRD.md`
2. `docs/ai/PLATFORM_PRODUCT_SECURITY_BOUNDARY.md`
3. `docs/ai/PLATFORM_PRODUCT_ROADMAP.md`
4. `docs/ai/PLATFORM_PRODUCT_P10_DATA_SOURCE_MAP.md`
5. `docs/ai/PLATFORM_PRODUCT_ADMIN_WORKFLOWS.md`
6. `docs/ai/PLATFORM_PRODUCT_PERMISSION_MATRIX.md`
7. `docs/ai/PLATFORM_PRODUCT_ACCEPTANCE_CRITERIA.md`
8. `docs/ai/PLATFORM_PRODUCT_CONTRACTS.md`
9. `docs/ai/PLATFORM_PRODUCT_CONTRACT_FIXTURES.md`
10. `docs/ai/PLATFORM_PRODUCT_P10A_TEST_PLAN.md`
11. `docs/ai/PLATFORM_PRODUCT_P11_FRONTEND_BOUNDARY.md`
12. `docs/ai/PLATFORM_PRODUCT_P12_SUPPORT_CONSOLE_CONTRACT.md`
13. `docs/ai/PLATFORM_PRODUCT_P13_OPERATIONS_COCKPIT_CONTRACT.md`
14. `docs/ai/PLATFORM_PRODUCT_P15_INCIDENT_TRIAGE_CONTRACT.md`
15. `docs/ai/PLATFORM_PRODUCT_P17_REGISTRY_LIFECYCLE_CONTRACT.md`
16. `docs/ai/PLATFORM_PRODUCT_P18_CONTROLLED_ACTIONS_CONTRACT.md`
17. `docs/ai/PLATFORM_PRODUCT_P19_APPROVAL_WORKFLOW_CONTRACT.md`
18. `docs/ai/PLATFORM_PRODUCT_P20_DURABLE_APPROVAL_GOVERNANCE_CONTRACT.md`

P10 must start with a data-contract-only slice unless a later CTO decision explicitly broadens scope. Do not begin P10 with migrations, API handlers, frontend UI, auth/RBAC/tenancy/session changes, payment changes, or tenant business-data edits.

P11 frontend work must start with the boundary map (`PLATFORM_PRODUCT_P11_FRONTEND_BOUNDARY.md`) and must not begin P11-B until the platform auth transport question is resolved.

P12 support console work must start with the contract (`PLATFORM_PRODUCT_P12_SUPPORT_CONSOLE_CONTRACT.md`) and must not begin P12-B (API implementation) until the contract is accepted. P12-B must not begin P12-C (frontend support UI) until API contract tests pass. No runtime code, migrations, or frontend UI in P12-A.

P13 operations observability work must start with the contract (`PLATFORM_PRODUCT_P13_OPERATIONS_COCKPIT_CONTRACT.md`) and must not begin P13-B (API implementation) until the contract is accepted. P13-B must not introduce new observability infrastructure -- it consumes existing logs, DB metadata, and runtime signals. No runtime code, migrations, or frontend UI in P13-A.

P15 incident triage work must start with the contract (`PLATFORM_PRODUCT_P15_INCIDENT_TRIAGE_CONTRACT.md`) and must not begin P15-B (read-only snapshot API adapter) until the contract is accepted. P15 is read-only triage only: no repair, no impersonation, no tenant business data, no mutation endpoints, no migrations. No runtime code, migrations, or frontend UI in P15-A.

P17 platform registry and tenant lifecycle work must start with the contract (`PLATFORM_PRODUCT_P17_REGISTRY_LIFECYCLE_CONTRACT.md`). P17 is read and contract only: no mutation of registry fields, no runtime code, no migrations, no frontend UI, and no auth/RBAC/session/tenancy/payment changes. Only future, separately approved controlled-action phases may mutate registry fields. No runtime code, migrations, or frontend UI in P17-A.

P18 controlled platform actions work must start with the contract (`PLATFORM_PRODUCT_P18_CONTROLLED_ACTIONS_CONTRACT.md`). P18 is contract only: no execution of any controlled action, no runtime code, no migrations, no frontend UI, and no auth/RBAC/session/tenancy/payment changes. Only a separately approved future phase may implement the action-request skeleton, and even then destructive actions remain blocked unless separately approved. No runtime code, migrations, or frontend UI in P18-A.

P19 controlled action approval workflow work must start with the contract (`PLATFORM_PRODUCT_P19_APPROVAL_WORKFLOW_CONTRACT.md`). P19 is the approval boundary on top of the P18 request layer: approve and reject change approval state only, they never execute any action, and every approved approval resolves to execution_blocked with execution_allowed == false. P19 is contract only: no execution, no runtime code, no migrations, no frontend UI, no automation runner, and no auth/RBAC/session/tenancy/payment changes. Only a separately approved future phase may implement the backend approval read/write skeleton, and even then no execution, no tenant mutation, and no persistent storage unless separately gated and approved. No runtime code, migrations, or frontend UI in P19-A.

P20 durable approval governance work must start with the contract (`docs/ai/PLATFORM_PRODUCT_P20_DURABLE_APPROVAL_GOVERNANCE_CONTRACT.md`). P20 is the durable governance layer on top of P19: a persistent approval store contract (digest-only idempotency, full reason/comment redaction, retention/purge/export, unknown/degraded/read-only fallback), a dual-control policy contract (maker-checker separation, quorum, tenant-contextual identity denied, emergency override forbidden by default), and an execution readiness gate contract. Approval is not execution and durability is not execution: an approved durable approval stays at approved_execution_blocked with execution_allowed == false, every destructive or tenant-mutating action stops, and backup.restore_test_request is request-only. Cumulative state: P20-A is the docs-only contract; P20-B is a NON-EXECUTING, IN-MEMORY backend read/write skeleton (maker-checker + quorum; no migration; no database); P20-C is a READ-ONLY frontend console on top of the P20-B read path (maker-checker operator visualization, no execute control, identity-only super_admin); P20-D is the master closeout. Across all P20 slices there is no execution, no migration, no real durable backend, no tenant mutation, no notification implementation, and no auth/RBAC/session/tenancy/payment changes. Only a separately approved future phase may implement a real durable backend or a migration, and even then no execution, no tenant mutation, and no real durable backend unless separately gated and approved by the CTO. No runtime code, migrations, or frontend UI in P20-A; P20-B adds non-executing backend skeleton only; P20-C adds read-only frontend console only.

## Purpose

- Keep long-lived project context inside the repository
- Reduce dependence on transient chat history
- Align multiple AI agents on the same roadmap and constraints
- Give Codex a repeatable CTO operating surface for planning and delegation
- Give agents a short current operating picture before they enter detailed ledgers

## Update Rules

- Strategic or cross-module decisions must also be recorded in `decision-register/`
- Each meaningful AI implementation session should leave a ledger entry in `ai-ledger/`
- After each active sprint, baseline, validation gate, or agent-role change, update `CTO_CURRENT_OPS.md`
- After each meaningful phase or branch-state change, update `PROJECT.md`
- When priorities change, update `CTO_CONTEXT.md` first
- When hidden assumptions from old chats are recovered, add them to `PROJECT_MEMORY.md`
- When team operating rules for AI agents change, update `AI_TEAM_OPERATING_RULES.md`

## Multi-Agent Sync Rules

- Before starting a new task, fetch/pull the latest branch state and reread:
  - `docs/ai/README.md`
  - `docs/ai/PROJECT.md`
  - `docs/ai/PROJECT_MEMORY.md`
- If a task changes branch ownership, accepted status, current blockers, or next action, update `PROJECT.md` in the same work cycle.
- Distinguish clearly between:
  - visibility push: push so another machine / CTO can inspect the work
  - approval push: push after CTO has approved the slice for continuation or merge
- Do not assume local chat memory is shared memory. If a fact matters to another agent, it must land in repo docs or a ledger.
