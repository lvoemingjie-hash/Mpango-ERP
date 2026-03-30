# AI Context Entry

This folder is the canonical starting point for Codex and other AI coding agents working on Mpango ERP.

## Read Order

1. `docs/ai/CTO_COCKPIT.md`
2. `docs/ai/CTO_CONTEXT.md`
3. `docs/ai/PROJECT_MEMORY.md`
4. `docs/ai/AGENT_DELEGATION_PROTOCOL.md`
5. `docs/contracts/Boot contract.md`
6. `docs/contracts/AI workrules.md`
7. `docs/mpango_erp_v0_3_development_master_plan.md`
8. `decision-register/README.md`

## Purpose

- Keep long-lived project context inside the repository
- Reduce dependence on transient chat history
- Align multiple AI agents on the same roadmap and constraints
- Give Codex a repeatable CTO operating surface for planning and delegation

## Update Rules

- Strategic or cross-module decisions must also be recorded in `decision-register/`
- Each meaningful AI implementation session should leave a ledger entry in `ai-ledger/`
- When priorities change, update `CTO_CONTEXT.md` first
- When hidden assumptions from old chats are recovered, add them to `PROJECT_MEMORY.md`
- When team operating rules for AI agents change, update `AGENT_DELEGATION_PROTOCOL.md`
