# Platform Handoff Skill — Creation Ledger

**Date**: 2026-04-27
**Agent**: OpenCode (CTO directive)
**Branch**: platform-dev
**Status**: Skill created, awaiting CTO review

---

## What Changed

Created `.claude/skills/generated/mpango-platform-handoff/SKILL.md` — a platform-specific handoff skill derived from the general `mpango-handoff` skill with platform-track hardening.

## Why

The general handoff skill provides project orientation. Platform agents need additional constraints:

1. Frozen zones that must never be touched
2. Proposal-first discipline with CTO approval gates
3. 8 self-check gates from permanent operating rules
4. Platform boundary map distinguishing public schema from tenant schemas
5. Explicit prohibitions (no auth rewrite, no tenancy rewrite, no billing without approval)

## Sources

Skill content synthesized from:

- `docs/ai/CTO_COCKPIT.md` — decision hierarchy, escalation triggers
- `docs/ai/CTO_CONTEXT.md` — north star, non-negotiables
- `docs/ai/PROJECT_MEMORY.md` — strategic intent, delivery tradeoff principle
- `docs/ai/AGENT_DELEGATION_PROTOCOL.md` — delegation patterns, output contract
- `docs/arch/platform-boundary-note.md` — boundary map, frozen zones, approval gates
- `docs/ai/PLATFORM_TRACK_STARTUP_CHECKLIST.md` — startup phases, stop conditions
- `ai-ledger/platform/2026-04-09_permanent_operating_rules.md` — 6 permanent rules

Files not found (listed in task but absent from repo):

- `docs/ai/PROJECT.md` — does not exist; PROJECT_MEMORY.md used instead
- `docs/ai/AI_TEAM_OPERATING_RULES.md` — does not exist; permanent_operating_rules.md used instead
- `.claude/skills/generated/mpango-handoff/SKILL.md` — does not exist; no general handoff skill to diff against

## Platform-Specific Adjustments (vs. general handoff)

| Area | General Handoff | Platform Handoff |
|------|----------------|-----------------|
| Branch | Any | `platform-dev` only |
| Boot sequence | Read project docs | Read 7 docs in fixed order, no coding until complete |
| Boundary | None specified | Public schema vs tenant schemas map |
| Frozen zones | Not mentioned | 6 explicitly frozen areas |
| Approval flow | Not specified | Proposal-first → self-check → CTO review → push |
| Self-check gates | None | 8 mandatory gates before every commit |
| Prohibitions | General non-negotiables | Explicit table: auth/tenancy/billing/tenant-schema blocked |
| Cross-tenant access | "Never bypass" | Guarded read-only access is permitted with documentation |
| Ledger path | `ai-ledger/` | `ai-ledger/platform/` (lowercase enforced) |
| ORM base | Not specified | `PublicBaseModel` for all platform tables |

## Files Touched

- Created: `.claude/skills/generated/mpango-platform-handoff/SKILL.md`
- Created: `ai-ledger/platform/20260427-platform-handoff-skill.md` (this file)

## Risks

- Skill references files that don't exist yet (PROJECT.md, AI_TEAM_OPERATING_RULES.md, general mpango-handoff) — will need updates if those are created
- Skill is untested against actual platform agents — should be validated in next session

## Validation

- Skill covers all 5 platform-specific rules from the task brief (platform-dev only, proposal-first, public schema only, no auth/tenancy/billing rewrite, platform must not force product to adapt)
- All referenced files verified to exist in repo (except the 3 noted above)
- Self-check gates match permanent operating rules
- Boundary map matches platform-boundary-note.md
