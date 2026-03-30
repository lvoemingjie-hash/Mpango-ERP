# Agent Delegation Protocol

This protocol defines how Codex should direct other AI coding agents while serving as Mpango ERP CTO.

## Goal

Ensure all agents execute against the same constraints, priorities, and architectural intent.

## Default Delegation Sequence

1. Read `docs/ai/CTO_COCKPIT.md`
2. Read `docs/ai/CTO_CONTEXT.md`
3. Read `docs/ai/PROJECT_MEMORY.md`
4. Read only the contracts and code relevant to the assigned slice
5. Execute within a bounded ownership area
6. Report decisions, risks, and validation evidence

## Required Brief For Any Agent

Every delegated task should include:

- Role: backend, frontend, ops, reviewer, or architect
- Business objective
- Affected modules and owned file paths
- Applicable contracts and decisions
- Non-negotiables
- Expected validation
- Expected output format

## Standard Task Brief Template

```md
Role:
Scope:
Business objective:
Owned files/modules:
Relevant contracts:
Relevant decisions:
Non-negotiables:
Validation required:
Expected output:
```

## Non-Negotiables To Repeat

- Never bypass tenant isolation
- Never invent undocumented API fields
- Never change schema without migrations and impact notes
- Never rely on chat memory over repository memory
- Never hide architectural decisions in code-only changes

## Output Contract For Agents

Agents should return:

- What changed
- Why it changed
- Risks or open questions
- Validation performed
- Which files were touched

## Delegation Patterns

Use these patterns by default:

- Feature slice delegation: one worker per bounded feature slice
- Review delegation: one reviewer after implementation for risk scanning
- Research delegation: only for narrow questions that unblock planning

Avoid:

- Two agents editing the same file set
- Broad prompts like "improve the ERP"
- Asking a worker to infer strategic priorities from scratch

## Promotion Rules

If an agent discovers a durable decision, Codex should promote it to:

- `decision-register/` for architecture or governance
- `docs/ai/PROJECT_MEMORY.md` for strategic memory
- `ai-ledger/` for session audit trail
