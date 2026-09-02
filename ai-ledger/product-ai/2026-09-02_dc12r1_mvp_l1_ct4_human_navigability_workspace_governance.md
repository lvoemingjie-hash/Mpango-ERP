# DC-12R1-MVP-L1-CT4 - Human Navigability and Workspace Governance

- Date: 2026-09-02 (+08:00)
- Executor: Codex acting as CTO
- Base: `origin/product-dev-recovered@24a28d76d6d9483d8101f8e0f537c148dc262859`
- Branch: `codex/dc12r1-mvp-l1-ct4-human-navigability-workspace-governance-2026-09-02`
- Change class: `DOCS_AND_READ_ONLY_NAVIGATION_TOOLING`
- Verification tier: `V1_SOURCE`
- Claim ceiling: `HUMAN_AND_AI_NAVIGABILITY_CANDIDATE_ONLY`

## Problem statement

The project had strong evidence governance but no canonical one-page entry. SHA
history was difficult to navigate, current-state documents could lag the live
protected tip, and the local Git registry contained hundreds of historical
worktrees across canonical, legacy, tool-managed and temporary paths.

## Read-only inventory truth

After `git fetch --all --prune`:

- protected product tip: `24a28d76d6d9483d8101f8e0f537c148dc262859`;
- remote refs: 623;
- local branches: 642;
- registered worktrees: 507;
- canonical `MPANGO ERP/worktrees/`: 60;
- Codex-managed: 7;
- legacy directly under `MPANGO ERP/`: 433;
- temporary legacy: 5;
- other: 2.

No legacy directory, worktree, branch, evidence file or temporary path was
moved, deleted, pruned or rewritten in this task.

## Delivered navigation layer

1. Root `START-HERE.md` with current truth, architecture, first-ten-minute
   onboarding, evidence vocabulary and navigation hierarchy.
2. Machine-readable and human-readable current state.
3. Baseline architecture, data ownership and core-flow documentation.
4. Incident, observability, rollback and recovery runbook with honest gaps.
5. Evidence policy including mandatory `TEST_COVERAGE_DELTA` reporting.
6. Active-work index and workspace hygiene/retention policy.
7. Read-only `scripts/project-context.ps1` for live ref, status, worktree and
   navigation checks.
8. A root README entry link so humans and agents reach the canonical page
   before scanning branches. Local tool-generated `AGENTS.md` remains ignored.

## Current-truth boundaries

- H2-C candidate `e16f39ca` and Kilo report `446a42a9` are unmerged; Kilo PASS
  is reported but remains subject to CTO acceptance and a later Lubuntu runtime gate.
- SKU candidate `1bd71055` is an unmerged post-defect fix line awaiting
  independent review.
- Migration `038`, the three-layer catalog, PRICING-R0 and order-price/reorder
  work are not part of the protected baseline.
- Prometheus scraping exists, but alert rules/Alertmanager and customer-facing
  incident drills are not proven.

## Test coverage delta

`TEST_DELTA=NOT_APPLICABLE`: product and test code are unchanged. The new
PowerShell navigation script is verified by syntax, JSON output, text output and
stale-baseline behavior checks in this task's quality gate.

## Verification gates

- PowerShell parse, text output, JSON output and 507-worktree inventory: PASS;
- stale-baseline negative control: mismatch detected, then `state.json` restored
  to byte-identical SHA-256;
- 11-document relative-link scan: PASS, including correction of the existing
  broken `docs/CHANGELOG_v0.2.0.md` README link;
- state schema/2 parse and four referenced Git commits: PASS;
- read-only detect-secrets hook: zero findings, baseline SHA-256 unchanged;
- staged-blob encoding: 13/13 strict UTF-8, no BOM/NUL/CR/U+FFFD, LF ending;
- `git diff --cached --check`: PASS;
- GitNexus staged detection: 13 files, zero affected execution flows, LOW risk.
  Its symbol list over-associated same-named README nodes in other directories;
  the exact Git staged inventory remained the authority for file scope.

## Stop boundary

This task does not authorize workspace cleanup, branch deletion, product work,
runtime tests, merge, deployment or customer release. The next step is an
independent docs/tooling review followed by a separate controlled docs merge.
