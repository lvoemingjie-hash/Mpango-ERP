# Fix Outdated GAP in Platform Handoff Skill

**Date**: 2026-04-28
**Agent**: OpenCode (CTO directive)
**Branch**: platform-dev
**Status**: Closed

---

## What Changed

1. **Created `docs/ai/PROJECT.md`** — minimal project overview document with architecture, development tracks, constraints, and current phase status.

2. **Updated `docs/ai/README.md`** — added PROJECT.md as Step 1 in the canonical read order.

3. **Fixed `.claude/skills/generated/mpango-platform-handoff/SKILL.md`**:
   - Removed outdated GAP description claiming PROJECT.md does not exist
   - Added PROJECT.md as mandatory Step 2 in boot Phase 1
   - Renumbered all steps (1–11 instead of 1–10)
   - Updated canonical reference map to show PROJECT.md as active (not GAP)
   - Updated session workflow to include PROJECT.md in Phase 1

4. **Updated `docs/PROJECT_HANDOFF.md`** — step reference updated from Step 10 to Step 11.

5. **Updated this ledger entry** (`ai-ledger/platform/20260427-platform-handoff-skill.md`) — marked PROJECT.md GAP as resolved.

## Why

The platform handoff skill contained an outdated GAP note claiming `docs/ai/PROJECT.md` did not exist. This was true when the skill was created (2026-04-27) but created a misleading signal: future platform agents would see "does not exist yet" and potentially skip reading PROJECT.md, treating it as optional or future work.

PROJECT.md is now a real, mandatory boot document. Every platform agent must read it as Step 2 before proceeding to governance or constraint documents.

## Key Decision

Platform agents must `git fetch && git pull` (Phase 0) **before** reading any docs. This ensures they always see the latest version of PROJECT.md and other canonical documents.

## Files Touched

- Created: `docs/ai/PROJECT.md`
- Modified: `docs/ai/README.md`
- Modified: `.claude/skills/generated/mpango-platform-handoff/SKILL.md`
- Modified: `docs/PROJECT_HANDOFF.md`
- Modified: `ai-ledger/platform/20260427-platform-handoff-skill.md`
- Created: `ai-ledger/platform/20260428-fix-project-md-gap.md` (this file)

## Risks

- PROJECT.md content is minimal — may need enrichment as the project evolves
- README.md read order change affects all AI agents, not just platform track

## Validation

- [x] `docs/ai/PROJECT.md` exists and contains project overview
- [x] SKILL.md contains no GAP references to PROJECT.md
- [x] SKILL.md Phase 1 includes PROJECT.md as mandatory Step 2
- [x] Canonical reference map shows PROJECT.md as active document
- [x] Session workflow includes PROJECT.md
- [x] Step numbering is consistent (1–11)
- [x] PROJECT_HANDOFF.md defers to canonical docs/ai/* paths
- [x] No product code changes
- [x] No new platform slice implementations
