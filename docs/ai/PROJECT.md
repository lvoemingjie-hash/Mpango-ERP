# Project Log

This file is the fast handoff document for new AI threads and newly activated agents.

It is not a full audit trail.
It is not a substitute for `ai-ledger/`.
It is not a strategy archive like `PROJECT_MEMORY.md`.

Its job is to answer, quickly:

- What have we already completed?
- What branch should work happen on?
- What is currently blocked?
- What should the next agent preserve?

## How To Use

Read this after:

1. `docs/ai/CTO_COCKPIT.md`
2. `docs/ai/CTO_CONTEXT.md`

Then use this file to orient yourself before opening detailed ledgers or code.

## Document Roles

- `docs/ai/PROJECT.md`
  Current project status, active branches, accepted slices, blockers, next moves.
- `docs/ai/PROJECT_MEMORY.md`
  Durable strategic truth, long-lived decisions, product philosophy.
- `ai-ledger/`
  Detailed implementation/session audit trail.

## Current Strategic Frame

- Product first, platform second.
- Primary customer is the wholesaler.
- Retailer workflows exist to improve wholesaler throughput and retention.
- Platform work must support the ERP product line and must not force architecture drift.
- `schema-per-tenant` remains the primary tenancy model.

## Current Branch Map

- `origin/product-dev`
  Last stable remote product baseline before recovered Phase 5 work.
- `product-dev-recovered`
  Current product recovery branch and active candidate for the new product mainline.
- `product-dev-backup`
  Historical backup branch; keep for recovery/reference, do not use as active mainline.
- `platform-dev`
  Active platform branch.

## Product Line Status

### Accepted Before Recovery

- Phase 3 pricing MVP: accepted.
- Phase 4 pricing-safe wholesaler order creation: accepted and previously pushed.

### Phase 5 Goal

- Close the wholesaler money loop:
  - structured payment recording
  - outstanding balance correctness
  - safe order lifecycle closure

### Phase 5 Recovered State

The recovered branch has progressed through three recovery checkpoints:

1. Auth regressions restored
   - `select-tenant` repaired
   - identity-only `/auth/me` repaired
2. Payment runtime repaired
   - nested transaction conflict removed from payment creation path
3. Runtime closeout evidence added for:
   - `draft -> confirm -> pay`
   - payment record creation
   - outstanding balance update

### Current Product-Line Truth

- `product-dev-recovered` is the candidate mainline.
- `product-dev-backup` remains preserved and must not be deleted yet.
- The latest closeout evidence is promising, but branch hygiene and final review discipline still matter.
- If runtime evidence depends on uncommitted code or unpushed docs, the branch is not yet operationally closed.

## Platform Line Status

Platform line is active and progressing in controlled slices.

Accepted slices so far include:

- platform routing scaffold
- platform tenant lifecycle scaffold
- platform audit log boundary
- platform operational reporting stats
- audit time-range filtering and activity summary enhancement
- GitHub self-hosted runner completed by CTO (confirmed)

### P1 Harness Kickoff - 2026-05-19

- GitHub self-hosted runner confirmed complete by CTO
- Platform P1 development proceeds in bounded code slices under harness discipline
- Active branch: `codex/platform-p1-harness-aligned-dev-2026-05-19` (isolated worktree)
- Each slice requires: proposal -> implementation -> 8 gates -> report artifact -> CTO review
- No auth rewrite, no tenancy rewrite, no billing engine implementation

Platform remains proposal-first and incremental.

## Current Priority Order

1. Finish clean product-line closeout on `product-dev-recovered`
2. Ensure accepted product-line state is pushed and visible to all machines
3. Only after closeout and visibility are stable, decide whether to re-promote recovered branch as the canonical product line
4. Keep platform line moving in controlled proposal/implementation slices with synchronized repo memory

## Current Non-Negotiables

- Do not delete `product-dev-backup` until recovered branch is fully accepted and stabilized.
- Do not treat `product-dev-backup` as the active product mainline.
- Do not change `schema-per-tenant`.
- Do not let platform work drive product architecture.
- Do not claim route-level validation that was not actually achieved.
- Do not push mixed or dirty worktrees.
- Do not let `PROJECT.md` drift behind the actual accepted branch/blocker state.
- Do not start platform or product tasks from stale local docs when a newer remote state exists.

## What A New Agent Should Preserve

- Product line priority and wholesaler-first hierarchy
- Accepted Phase 3 and Phase 4 baselines
- Recovery status of Phase 5 and its repaired auth/payment chain
- Platform branch boundaries and proposal-first discipline
- AI team operating rules in `docs/ai/AI_TEAM_OPERATING_RULES.md`
- The rule that repo memory must be both updated and made remotely visible when another machine depends on it

## Next Expected Action

For the product line:

- complete final closeout / cleanliness / promotion decision for `product-dev-recovered`

For the platform line:

- continue with the next approved proposal-first slice
- keep platform handoff skill and repo-memory sync aligned with the actual remote branch state

## Update Rule

Update this file when any of the following changes:

- active branch strategy
- accepted phase/slice status
- current blocker list
- project-wide next action
- recovered vs stable branch ownership

Keep entries concise.
Do not turn this into a raw transcript or a duplicate of `ai-ledger/`.
