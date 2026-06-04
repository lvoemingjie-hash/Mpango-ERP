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

P10 must start with a data-contract-only slice unless a later CTO decision explicitly broadens scope. Do not begin P10 with migrations, API handlers, frontend UI, auth/RBAC/tenancy/session changes, payment changes, or tenant business-data edits.

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
