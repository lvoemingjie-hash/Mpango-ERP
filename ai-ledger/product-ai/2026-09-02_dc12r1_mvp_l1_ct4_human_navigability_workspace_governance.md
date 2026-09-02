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
- SKU candidate `adfcfc82` is the live unmerged fix/test tip. It linearly
  succeeds `1bd71055` with a router-oracle test correction and still awaits
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

## R1 contract graph closure

The first publication exposed a navigation defect: the new summary layer did
not link the existing `docs/contracts/` library, so valid contracts could become
invisible without being deleted. R1 closes that defect by:

- adding `docs/contracts/README.md` as the authority/lifecycle index;
- linking `START-HERE`, architecture overview, data map and current state back
  to the contract library;
- adding mandatory `DOCUMENTATION_LINKAGE_DELTA` evidence;
- reconciling the canonical RBAC contract with the executable permission
  registry at the frozen baseline;
- classifying `docs/RBAC_MATRIX_v0.2.0.md` as a retained historical snapshot,
  not deleting or moving it;
- making the read-only project-context script require the contract index.
- binding active candidates/reviews to both remote ref names and expected SHAs,
  after fetch exposed that the SKU branch had advanced beyond the recorded tip.

GitNexus does not index the Markdown contract or the PowerShell script as code
symbols, so no synthetic impact rating was claimed. Exact Git scope, references,
permission parity and link integrity are verified directly.

### Documentation linkage delta

- `DOCUMENTATION_FILES_ADDED_OR_CHANGED=12`;
- `PREDECESSOR_DOCUMENTS_REVIEWED=docs/contracts/rbac_matrix.md,docs/RBAC_MATRIX_v0.2.0.md`;
- `CONTRACT_INDEX_LINKS_ADDED_OR_CHANGED=README,START-HERE,OVERVIEW,DATA-MAP,STATE`;
- `SUPERSEDED_DOCUMENTS_AND_REASON=docs/RBAC_MATRIX_v0.2.0.md:historical_permission_and_role_snapshot`;
- `BROKEN_LINK_SCAN_RESULT=PASS`;
- `UNLINKED_RELEVANT_CONTRACTS=0` for the architecture, data ownership, RBAC,
  operations and governance topics changed in CT4/R1.

Deletion or physical archival of the superseded RBAC snapshot remains outside
scope because current and historical ledgers still reference its path.

## R2 Windows path gate and H2-C evidence acceptance

The Windows user-profile inventory found 48 top-level names that heuristically
look like project, review, evidence, runtime or worktree material. Twenty expose
a top-level Git marker and only two are registered worktrees. This is a triage
signal only: system/tool state, unrelated projects and Mpango ERP artifacts are
not interchangeable, so no path was moved or deleted.

R2 adds a read-only path creation gate for worktree, evidence, handoff, scratch,
archive and desktop-managed worktree purposes. Positive, user-root negative and
prefix-lookalike negative controls are required before publication. Existing
legacy cleanup remains a separate manifest/reference-safe task.

Kilo report `446a42a988aeae645c93af5310f41eb6cbc82284` was independently reconciled:
its parent is candidate `e16f39cab7613a32bced21d1f8a5c6be6a54fe18`, its delta is exactly the review
and findings files, and it records independently executed detect-secrets,
static, R1-R40 and M1-M5 evidence. CTO accepts the bounded source/test/contract/
mutation authenticity result. Browser authority remains `NOT_EXECUTED`; the
next gate is one Lubuntu single-stack, single-preflight, single-browser run.

### R2 boundaries

- `WORKSPACE_MOVE_COUNT=0`;
- `WORKSPACE_DELETE_COUNT=0`;
- `KILO_SOURCE_TEST_AUTHENTICITY=CTO_ACCEPTED`;
- `BROWSER_AUTHORITY=NOT_EXECUTED`;
- `H2_C_MERGED=false`;
- `NEXT_GATE=LUBUNTU_SINGLE_STACK_SINGLE_PREFLIGHT_SINGLE_BROWSER_AUTHORITY`.
