# Platform P1 Shared-Memory Reconciliation Proposal

**Date:** 2026-05-19
**Author:** Opencode proposal, reviewed by Codex Platform CTO
**Branch:** `codex/platform-p1-harness-aligned-dev-2026-05-19`
**Base:** `origin/platform-dev`
**Status:** PROPOSAL ONLY - no runtime code changes, no merge into `platform-dev`

## Executive Summary

`origin/platform-dev` shared-memory docs are stale relative to `origin/product-dev-recovered`.
The highest-risk gap is that `docs/ai/AI_TEAM_OPERATING_RULES.md` is absent on
`origin/platform-dev`, while product governance now uses it to define the CTO
Instruction Compliance Check, validation discipline, escalation rules, and
completion standard.

This proposal does not sync the files. It identifies the exact reconciliation
set and classifies the risk so the main CTO can approve a later docs-only sync.

## Branch And Push State

- Current isolated branch: `codex/platform-p1-harness-aligned-dev-2026-05-19`
- Current commit at proposal time: `0ddd4f0aee1d194e8007b3fc08e3ff43036c7ea2`
- Visibility push performed for the pre-existing P1 harness alignment commit.
- No merge into `platform-dev`.
- No direct push to `platform-dev`.
- No product branch push.

## Diff Evidence

Commands run:

```bash
git ls-tree -r --name-only origin/platform-dev docs/ai
git ls-tree -r --name-only origin/product-dev-recovered docs/ai
git diff --name-status origin/platform-dev..origin/product-dev-recovered -- docs/ai
git diff --stat origin/platform-dev..origin/product-dev-recovered -- docs/ai
```

`origin/platform-dev` has 12 `docs/ai` files. `origin/product-dev-recovered`
has those 12 plus:

- `docs/ai/AI_TEAM_OPERATING_RULES.md`
- `docs/ai/CTO_CURRENT_OPS.md`
- `docs/ai/PHASE4_FRONTEND_CONTRACT.md`

Name-status drift:

```text
A       docs/ai/AI_TEAM_OPERATING_RULES.md
A       docs/ai/CTO_CURRENT_OPS.md
M       docs/ai/DUAL_MACHINE_DEVELOPMENT_PROTOCOL.md
A       docs/ai/PHASE4_FRONTEND_CONTRACT.md
M       docs/ai/PROJECT.md
M       docs/ai/README.md
```

Stat drift:

```text
docs/ai/AI_TEAM_OPERATING_RULES.md           | 102 ++++++++
docs/ai/CTO_CURRENT_OPS.md                   | 338 ++++++++++++++++++++++++++
docs/ai/DUAL_MACHINE_DEVELOPMENT_PROTOCOL.md |  55 +++++
docs/ai/PHASE4_FRONTEND_CONTRACT.md          | 170 ++++++++++++++
docs/ai/PROJECT.md                           | 339 ++++++++++++++++++++-------
docs/ai/README.md                            |  24 +-
6 files changed, 927 insertions(+), 101 deletions(-)
```

## File Findings

### Missing On Platform-Dev

| File | Source branch | Finding | Platform risk |
|------|---------------|---------|---------------|
| `docs/ai/AI_TEAM_OPERATING_RULES.md` | `origin/product-dev-recovered` | Defines mandatory CTO Instruction Compliance Check, branch discipline, validation discipline, escalation triggers, and completion standard. | HIGH |
| `docs/ai/CTO_CURRENT_OPS.md` | `origin/product-dev-recovered` | Current-state capsule for baseline, active work, memory model, agent roles, validation commands, and known risks. | HIGH |
| `docs/ai/PHASE4_FRONTEND_CONTRACT.md` | `origin/product-dev-recovered` | Product/frontend contract reference. Useful context, but not required for pure platform infra work. | LOW-MEDIUM |

### Stale On Platform-Dev

| File | Source branch | Finding | Platform risk |
|------|---------------|---------|---------------|
| `docs/ai/README.md` | `origin/product-dev-recovered` | Product branch read order now includes `CTO_CURRENT_OPS.md` and `AI_TEAM_OPERATING_RULES.md`; platform branch read order does not. | HIGH |
| `docs/ai/PROJECT.md` | `origin/product-dev-recovered` | Branch map, current priorities, validation snapshot, and risk sections have materially changed after product recovery and promotion work. | HIGH |
| `docs/ai/DUAL_MACHINE_DEVELOPMENT_PROTOCOL.md` | `origin/product-dev-recovered` | Product branch has newer start-of-task sync gate, visibility push rule, `PROJECT.md` update gate, and CTO review handshake. | HIGH |

## Proposed Reconciliation Groups

### Group 1 - Must Sync Before Platform Code Development

These files should be copied from `origin/product-dev-recovered` into a clean
platform reconciliation branch, then reviewed as a docs-only change:

| File | Source branch | Reason |
|------|---------------|--------|
| `docs/ai/AI_TEAM_OPERATING_RULES.md` | `origin/product-dev-recovered` | Required for CTO compliance checks and completion claims. |
| `docs/ai/CTO_CURRENT_OPS.md` | `origin/product-dev-recovered` | Required current-state capsule before new platform work. |
| `docs/ai/README.md` | `origin/product-dev-recovered` | Required canonical read order. |
| `docs/ai/PROJECT.md` | `origin/product-dev-recovered` | Required branch map and current priority alignment. |
| `docs/ai/DUAL_MACHINE_DEVELOPMENT_PROTOCOL.md` | `origin/product-dev-recovered` | Required two-machine visibility and review gates. |

### Group 2 - Sync After CTO Review / Product-Track Specific

| File | Source branch | Reason |
|------|---------------|--------|
| `docs/ai/PHASE4_FRONTEND_CONTRACT.md` | `origin/product-dev-recovered` | Product-track contract. Sync only if CTO wants platform agents to carry this product API boundary reference. |

### Group 3 - Do Not Sync Automatically

| File | Source branch | Reason |
|------|---------------|--------|
| `.claude/skills/generated/mpango-platform-handoff/SKILL.md` | Current platform branch | Platform-specific skill. It should be manually reconciled after Group 1 docs sync so its boot sequence includes `CTO_CURRENT_OPS.md` and `AI_TEAM_OPERATING_RULES.md`. Do not copy from product branch. |

## Recommended Follow-Up Slice

After CTO approval, create a new isolated branch from `origin/platform-dev`:

```bash
git fetch origin
git switch --create codex/platform-shared-memory-sync-2026-05-19 origin/platform-dev
git checkout origin/product-dev-recovered -- docs/ai/AI_TEAM_OPERATING_RULES.md
git checkout origin/product-dev-recovered -- docs/ai/CTO_CURRENT_OPS.md
git checkout origin/product-dev-recovered -- docs/ai/README.md
git checkout origin/product-dev-recovered -- docs/ai/PROJECT.md
git checkout origin/product-dev-recovered -- docs/ai/DUAL_MACHINE_DEVELOPMENT_PROTOCOL.md
```

Then review manually:

```bash
git diff -- docs/ai
git diff --check
```

Only after that, reconcile the platform handoff skill in a separate commit or
clearly separated hunk.

## Changed File List For This Proposal

- `ai-ledger/platform/2026-05-19_shared_memory_reconciliation_proposal.md`

No `docs/ai` files were changed in this proposal-only task.

## Validation Evidence

- `git fetch --all --prune`: completed before analysis.
- Visibility push of `codex/platform-p1-harness-aligned-dev-2026-05-19`: completed before proposal work.
- `opencode run`: completed bounded proposal draft.
- `git diff --name-status origin/platform-dev..origin/product-dev-recovered -- docs/ai`: identified 6 drift files.
- `git diff --stat origin/platform-dev..origin/product-dev-recovered -- docs/ai`: measured 927 insertions and 101 deletions.
- `git diff --check`: PASS.
- Forbidden path audit: PASS; only this platform ledger proposal changed.
- GitNexus unstaged/all detection before staging returned no indexed symbol changes because the proposal file was untracked.
- GitNexus `detect_changes(scope=staged)`: LOW risk; changed files: 1; affected processes: none.

## Risk Classification

| Risk | Level | Notes |
|------|-------|-------|
| Shared-memory drift risk | HIGH | Platform agents do not see current compliance rules, current ops, read order, or dual-machine gates. |
| Runtime code risk from this proposal | LOW | This task adds only a platform ledger proposal. |
| Product branch risk | LOW | No product branch push and no product code edits. |
| Merge risk | LOW | No merge into `platform-dev`; branch remains isolated. |

## CTO Instruction Compliance Check

| CTO instruction | Implementation evidence | Test evidence | Status |
|----------------|-------------------------|---------------|--------|
| Push current isolated branch only if CTO approves | Codex Platform CTO approved visibility push for the existing isolated branch only | `git push -u origin codex/platform-p1-harness-aligned-dev-2026-05-19` completed | PASS |
| Do not merge into `platform-dev` | No merge performed | Branch remains isolated | PASS |
| Identify missing/stale shared docs | File findings list 3 missing and 3 stale docs | Diff evidence commands recorded | PASS |
| Call out `AI_TEAM_OPERATING_RULES.md` absence | Explicit high-risk finding in Missing On Platform-Dev table | Name-status drift shows file added on product branch | PASS |
| Compare against product-dev-recovered governance state | Comparison uses `origin/platform-dev..origin/product-dev-recovered` | `git diff --name-status` and `git diff --stat` evidence recorded | PASS |
| Propose exact files to sync with no runtime code changes | Groups 1-3 list exact files and source branches | Changed file list contains only this ledger proposal | PASS |
| No backend/frontend edits | No runtime paths are part of this proposal | Forbidden audit before commit passed | PASS |
| No auth/RBAC/tenancy/migration edits | No such paths are part of this proposal | Forbidden audit before commit passed | PASS |
| No product branch push | No product branch push performed | Git operation scope remained current isolated branch | PASS |
| No `platform-dev` direct push | No direct push to `platform-dev` performed | Git operation scope remained current isolated branch | PASS |

## Counterexample Check

| Counterexample | Expected behavior | Coverage |
|----------------|-------------------|----------|
| Blindly copy all 6 drift files into platform-dev | Reject until CTO reviews product-specific `PHASE4_FRONTEND_CONTRACT.md` and platform skill implications | Group 2 and Group 3 separate optional/product-specific and manual-reconcile items |
| Treat existence of `PROJECT.md` and `README.md` as sufficient | Reject because existing files can be stale | Stale file table identifies modified docs and risk |
| Use this proposal as approval to merge into platform-dev | Reject | Status and branch rules say proposal-only, no merge |
| Claim runner success means docs are current | Reject | Risk table treats shared-memory drift as independent from runner completion |

## Completion Claim

**COMPLETE for proposal-only analysis.** No runtime code changed. No `docs/ai`
sync was performed. The next step requires CTO approval of the proposed Group 1
sync set.
