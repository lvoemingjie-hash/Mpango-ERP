---
name: mpango-platform-handoff
description: Use when a platform-track agent boots on the Mpango ERP platform-dev branch and needs to locate canonical docs, understand frozen zones, apply self-check gates, and operate within platform boundary rules without violating tenant isolation or product architecture
---

# Mpango Platform Handoff

## Overview

Orientation skill for platform-track agents working on the `platform-dev` branch of Mpango ERP. Provides the minimal boot sequence (sync → entry → governance → constraints), hard boundary rules, and canonical reference map so a new agent can become productive without violating multi-tenant isolation or product continuity.

**Core principle**: Platform work extends the SaaS layer without forcing the product core to adapt.

## P1 Harness Context

The GitHub self-hosted runner is now complete (CTO confirmed). Platform code
development may proceed in bounded slices under harness discipline.

### Runner Gate
Runner success is a prerequisite but not sufficient. Each platform slice must
additionally satisfy:
- Report artifact produced with all required fields
- Required fields not blank or placeholder
- Evidence traceable to concrete file changes

### Delegation Split
- **Goose**: Platform implementation on Machine B (Lubuntu) - code, tests, migrations
- **Opencode**: Governance, alignment, handoff, ledger - docs, skills, report artifacts

### Branch/Worktree Isolation
All platform work must occur in clean isolated worktrees on branches matching
`codex/platform-*`, derived from `origin/platform-dev`. No mixed worktrees.

### Final Status Report Fields
Every platform session must produce a terminal report containing:
- **Branch**: active branch name
- **Commit**: current HEAD hash
- **Modified files**: list of files changed
- **Tests/checks**: what was run and result
- **Report path**: path to report artifact
- **Risk**: LOW / MEDIUM / HIGH with brief justification

**Canonical entry point**: All agents must start from `docs/ai/README.md` and follow its read order. The boot sequence below is the platform-specific extension of that canonical path.

## Boot Sequence

### Phase 0 — Sync

```
git fetch origin
git pull origin platform-dev
```

Platform docs may have been updated on the other machine or by CTO remotely.
Always sync before reading to avoid stale context.

### Phase 1 — Canonical Entry Point

| Step | File | Purpose |
|------|------|---------|
| 1 | `docs/ai/README.md` | Canonical entry point; defines the read order for all AI agents |
| 2 | `docs/ai/PROJECT.md` | Canonical project log: branch map, accepted slices, blockers, next moves |
| 3 | `docs/ai/PROJECT_MEMORY.md` | Strategic intent, product boundary, delivery tradeoff principle |

### Phase 2 — Governance Documents

| Step | File | Purpose |
|------|------|---------|
| 4 | `docs/ai/CTO_COCKPIT.md` | Decision hierarchy, escalation triggers, alignment definition |
| 5 | `docs/ai/CTO_CONTEXT.md` | North star, non-negotiables, current risk areas |
| 6 | `docs/ai/AGENT_DELEGATION_PROTOCOL.md` | Delegation sequence, task brief template, output contract |
| 7 | `docs/ai/DUAL_MACHINE_DEVELOPMENT_PROTOCOL.md` | Two-machine rules, branch protocol, shared memory surfaces |

### Phase 3 — Platform-Specific Constraints

| Step | File | Purpose |
|------|------|---------|
| 8 | `docs/arch/platform-boundary-note.md` | Boundary mapping, frozen zones, approval gates |
| 9 | `docs/ai/PLATFORM_TRACK_STARTUP_CHECKLIST.md` | Phase-by-phase startup gate |
| 10 | `ai-ledger/platform/2026-04-09_permanent_operating_rules.md` | 6 permanent operating rules |
| 11 | `docs/PROJECT_HANDOFF.md` | Operational state: what's built, test counts, API surface |

Do NOT start coding until all 11 are read.

## Hard Boundary Rules

These rules are absolute. No violation without explicit CTO approval recorded in `decision-register/`.

### Frozen Zones — Never Touch

- Authentication model (JWT claims, login flow, token lifecycle)
- Schema-per-tenant isolation architecture (DR-001)
- Tenant provisioning workflow
- Product API endpoints (`/api/v1/auth`, `/api/v1/orders`, etc.)
- Tenant ORM guardrail interceptor
- Search-path routing mechanism

### Prohibited Without Approval

| Action | Why Blocked |
|--------|------------|
| Auth rewrite | Frozen zone — product stability |
| Tenancy rewrite | Frozen zone — DR-001 |
| Billing/subscription implementation | Needs CTO approval gate |
| Changes to tenant-schema tables | Tenant isolation boundary |
| Cross-tenant writes | Tenant isolation boundary |
| Migrations touching tenant schemas | Product ownership conflict |

### Proposal-First Discipline

All platform work follows proposal-first:

1. **Write a proposal** in `ai-ledger/platform/` describing scope, boundary impact, and migration plan
2. **Self-check** against the 8 gates below
3. **Present** ledger + diff to CTO for review
4. **Push only** after CTO approval

No push without CTO approval. Exception: CTO explicitly instructs immediate push.

## Platform Boundary Map

```
┌─────────────────────────────────────────────────────┐
│ public schema                                        │
│  ├─ wholesalers (existing — extend only, never break)│
│  ├─ platform_tenants (cross-tenant lifecycle)        │
│  ├─ platform_subscriptions (SaaS records)            │
│  ├─ platform_audit_logs (cross-tenant audit trail)   │
│  └─ platform_api_keys (platform credentials)         │
├─────────────────────────────────────────────────────┤
│ tenant schemas (t_xxx) — READ ONLY for platform      │
│  ├─ users, roles, permissions                         │
│  ├─ orders, order_items                               │
│  ├─ products, inventory                               │
│  ├─ payments                                          │
│  └─ retailers                                         │
└─────────────────────────────────────────────────────┘
```

**New public platform tables must:**
- Use `PublicBaseModel` (stored in public schema)
- Reference `wholesalers.id` as FK (never duplicate tenant identity)
- Never store tenant-scoped business data
- Be opt-in for tenants

**Platform MAY read tenant data** through guarded, read-only, documented access patterns. This is not a blanket ban on reading — it requires intentional, scoped, auditable access.

## 8 Self-Check Gates

Run before every commit. All must PASS.

| # | Gate | Check |
|---|------|-------|
| 1 | Scope | Only task-scoped files; no auth/tenancy/business-table changes |
| 2 | Architecture | Schema-per-tenant preserved; platform refs wholesalers.id; public schema only |
| 3 | API contract | No tuple-style responses; HTTPException/JSONResponse; read-only when required |
| 4 | Migration | FK in both ORM and migration; indexes match model; sane downgrade |
| 5 | Tests | All pass; request-level tests when API surface changes |
| 6 | Boot/import | Backend imports clean; no circular/missing imports; router registration valid |
| 7 | Diff hygiene | No debug prints; no temp scripts; canonical ledger path |
| 8 | CTO question | Honest self-assessment: would CTO flag this? |

## Canonical Reference Map

| Need | Location |
|------|----------|
| **Entry point (read first)** | `docs/ai/README.md` |
| Strategic memory | `docs/ai/PROJECT_MEMORY.md` |
| Canonical project log | `docs/ai/PROJECT.md` |
| Decision hierarchy | `docs/ai/CTO_COCKPIT.md` |
| Current priorities | `docs/ai/CTO_CONTEXT.md` |
| Delegation protocol | `docs/ai/AGENT_DELEGATION_PROTOCOL.md` |
| Dual-machine protocol | `docs/ai/DUAL_MACHINE_DEVELOPMENT_PROTOCOL.md` |
| Boundary rules | `docs/arch/platform-boundary-note.md` |
| Startup checklist | `docs/ai/PLATFORM_TRACK_STARTUP_CHECKLIST.md` |
| Platform proposal | `docs/ai/PLATFORM_PROPOSAL_CTO_REVIEW_2026-03-30.md` |
| Operational state | `docs/PROJECT_HANDOFF.md` |
| Tenancy architecture | `decision-register/DR-001_schema-per-tenant.md` |
| Tenancy spec | `docs/contracts/multi_tenancy_spec.md` |
| Permanent rules | `ai-ledger/platform/2026-04-09_permanent_operating_rules.md` |
| Session audit trail | `ai-ledger/platform/` |
| Decision records | `decision-register/` |
| Boot contract | `docs/contracts/Boot contract.md` |
| AI workrules | `docs/contracts/AI workrules.md` |

## Session Workflow

```
Phase 0: git fetch && git pull (isolated worktree on codex/platform-*)
Phase 1: Read README.md + PROJECT.md + PROJECT_MEMORY.md (canonical entry)
Phase 2: Read CTO_COCKPIT + CTO_CONTEXT + AGENT_DELEGATION + DUAL_MACHINE_PROTOCOL (governance)
Phase 3: Read platform-boundary-note + STARTUP_CHECKLIST + permanent_rules + PROJECT_HANDOFF (constraints)
  → Write proposal to ai-ledger/platform/
  → Implement bounded slice
  → Run 8 self-check gates
  → Run tests
  → Commit
  → Produce report artifact (branch, commit, files, tests, report path, risk)
  → Present ledger + hash + report to CTO
  → Await CTO review → Push after approval
```

## Output Contract

Every session must produce:

1. **Ledger entry** in `ai-ledger/platform/` with what changed, why, risks, validation, files touched
2. **Decision record** in `decision-register/` if a long-lived design choice was made
3. **PROJECT_MEMORY.md update** if strategic context became explicit
4. **Diff hygiene**: no debug prints, no temp scripts

## Red Flags — Stop Immediately

- Platform work requires changing tenancy architecture
- Platform work requires editing frozen product zones
- Platform work requires changing product auth model
- Migrations collide with active product work
- Assumptions exist only in chat, not in repo memory
- Product architecture must adapt to accommodate platform work

**Any of these → stop, document, escalate to CTO.**

## Platform-Specific Conventions

- Branch: `platform-dev` only
- Ledger path: `ai-ledger/platform/` (lowercase, no mixed-case variants)
- ORM base: `PublicBaseModel` for platform tables
- FK target: always `wholesalers.id`
- Migration ownership: explicitly assigned before creation
- Bootability: verify product bootability after every change
