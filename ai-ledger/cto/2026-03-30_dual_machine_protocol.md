# AI Work Ledger

## AI Role
CTO AI - Codex

## Scope
Define parallel development rules for Windows product work and Lubuntu platform work, and document how shared memory works across two Codex installations.

## Inputs (Contracts Referenced)
- `docs/ai/CTO_COCKPIT.md`
- `docs/ai/CTO_CONTEXT.md`
- `docs/ai/PROJECT_MEMORY.md`
- `docs/ERP-Platform-Proposal-v3.2-APPROVED.md`
- `docs/mpango_erp_v0_3_development_master_plan.md`
- `decision-register/README.md`

## Outputs
- Added `docs/ai/DUAL_MACHINE_DEVELOPMENT_PROTOCOL.md`
- Added `docs/ai/SHARED_MEMORY_SYNC_PROTOCOL.md`

## Decisions Made
- Platform track is not yet implementation-primary and should begin in alignment mode
- Shared memory between machines must be git-tracked repository memory
- Important project memory documents should be committed like source code
- Platform proposals must not silently override the active tenancy model

## Known Risks / TODO
- Platform proposal appears to contain tenancy assumptions that may conflict with current repository direction and should be reconciled before implementation
- Current worktree is already dirty, so these docs are added without touching unrelated changes

## Validation
- Verified the referenced platform proposal exists in `docs/`
- Verified current repo already contains AI context, ledgers, contracts, and planning docs to support a dual-machine protocol
