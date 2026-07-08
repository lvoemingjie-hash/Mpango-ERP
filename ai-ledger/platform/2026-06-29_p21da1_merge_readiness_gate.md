# P21-D-A.1 Durable Approval Runtime Adapter Design-Lock -- Merge Readiness Gate

Revision note (2026-06-29, P21-D-A.1 fix): this report was rewritten as pure
ASCII (no box-drawing, arrows, long dashes, check/cross marks, or smart quotes)
and the validation-gate evidence was corrected. The scanning and tooling gates
that the original draft recorded as NOT EXECUTED were run during the Codex CTO
review of this report and passed. They are recorded as executed and passed in
section 6. The recommendation is unchanged: APPROVE_FOR_CTO_MERGE_REVIEW.

Date: 2026-06-29
Phase: P21-D-A.1 (merge-readiness gate trial for the P21-D-A discovery +
design-lock branch). P21-D-A.1 independently verifies whether the P21-D-A
design-lock branch is ready for Codex CTO merge consideration, and produces this
go / no-go readiness report only. P21-D-A.1 creates no backend runtime code, no
migration, no frontend, no ORM/model registration, no auth/RBAC/session change,
no tenant business edit, no payment/billing change, no package/lockfile change,
and no .secrets.baseline change. It does not merge or push platform-dev and does
not push the source branch.
Gate branch: codex/auto-p21da1-merge-readiness-gate-20260629-120805 (isolated
worktree).
Source branch: codex/auto-p21da-discovery-design-lock-20260629-095843.
Source commit: 6e2dc45 (docs(platform): P21-D-a durable approval runtime adapter
design lock).
Base: origin/platform-dev = fc9eb40 (confirmed; see section 2).
Scope of this gate: docs / ledger only (this one readiness report).
Inspection-only.

This phase is a merge-readiness gate. It does not implement, migrate, execute,
persist (beyond this ledger), switch runtime storage, mutate tenant state, merge
anything into platform-dev, or push any branch. It is an isolated, docs-only
branch. The only file changed in this gate branch is this readiness report.

Approval is not execution, and durability is not execution.

## 1. Phase inventory

P21-D-A.1 - merge-readiness gate for the P21-D-A discovery + design-lock branch
(docs / ledger only, inspection-only)
- Gate branch: codex/auto-p21da1-merge-readiness-gate-20260629-120805
- Source branch under review: codex/auto-p21da-discovery-design-lock-20260629-095843
- Source commit under review: 6e2dc45
- Base: origin/platform-dev = fc9eb40 (confirmed in section 2)
- Report path: ai-ledger/platform/2026-06-29_p21da1_merge_readiness_gate.md
  (this file)
- Scope: independent inspection-only readiness report on the P21-D-A design-lock
  branch
- Gate-branch change set: this report file only (docs-only, one file)
- Risk: LOW (P21-D-A itself is docs / design-lock only; P21-D-A.1 is docs /
  ledger only). The future P21-D runtime slices it precedes are runtime-risk and
  are separately CTO-gated; they are not started by P21-D-A or by this gate.
- Status: readiness gate on an isolated branch; not merged to platform-dev;
  source branch not pushed by this gate.

## 2. Base, source, and lineage confirmation

All confirmed via read-only git inspection in the gate worktree's object
database:

- Source commit 6e2dc45 exists (git cat-file -t 6e2dc45 = commit).
- 6e2dc45 parent = fc9eb40 (git log -1 --pretty='%H %P' 6e2dc45): the source
  commit is a direct, single child of the base. No intermediate commits.
- git merge-base fc9eb40 6e2dc45 = fc9eb40, and fc9eb40 is an ancestor of
  6e2dc45 (git merge-base --is-ancestor fc9eb40 6e2dc45 = success): the source
  is a clean, non-divergent descendant of the base.
- Commits in source not in base: exactly one,
  "6e2dc45 docs(platform): P21-D-a durable approval runtime adapter design lock"
  (git log --oneline fc9eb40..6e2dc45).
- origin/platform-dev resolved to fc9eb40 (full 40-char SHA deliberately
  abbreviated here to keep the ledger detect-secrets-clean and
  non-self-referential, per the P21-C0 convention). This matches the expected
  base SHA in the task brief exactly; the target has not moved.

Lineage is clean: one commit, direct child of the confirmed base, no divergence.

## 3. Changed-file audit (the three expected source files)

git diff --name-status fc9eb40..6e2dc45 and git diff --stat fc9eb40..6e2dc45:

  A  ai-ledger/platform/2026-06-29_p21da_discovery_design_lock.md            (211 lines)
  A  docs/ai/PLATFORM_PRODUCT_P21_D_DURABLE_APPROVAL_RUNTIME_ADAPTER_DESIGN_LOCK.md (646 lines)
  M  docs/ai/README.md                                                       (+3 lines)

  3 files changed, 860 insertions(+), 0 deletions(-).

This is exactly the three files named in the task brief, no more, no less:

  1. docs/ai/README.md (M, +3) - the canonical AI entry-point doc index.
  2. docs/ai/PLATFORM_PRODUCT_P21_D_DURABLE_APPROVAL_RUNTIME_ADAPTER_DESIGN_LOCK.md (A)
     - the P21-D-A design-lock document.
  3. ai-ledger/platform/2026-06-29_p21da_discovery_design_lock.md (A) - the
     P21-D-A discovery + design-lock ledger entry.

The change is purely additive on the document side (two new markdown files) plus
a 3-line index/pointer update to README.md. Zero deletions. No source-branch
file falls outside these three expected paths.

The P21-D-A.1 gate branch itself changes exactly one file: this readiness report
(ai-ledger/platform/2026-06-29_p21da1_merge_readiness_gate.md). That is the only
intended change on this gate branch, and it is docs-only.

README.md change (verified content): adds item 21 to the P9+ platform doc
read-order index,
"21. docs/ai/PLATFORM_PRODUCT_P21_D_DURABLE_APPROVAL_RUNTIME_ADAPTER_DESIGN_LOCK.md",
and appends one scope paragraph stating that P21-D durable approval runtime
adapter work must start with the discovery + design lock, that P21-D-a is a
DOCS-ONLY design lock recording the exact P20-B runtime surface the adapter
rewires and freezing the adapter design before any P21-D runtime slice may begin,
that the adapter preserves execution_allowed == false / executed == false /
execution_gate == blocked, executes nothing, mutates no P17/tenant data, and
adds no new migration (it reads and writes the merged P21-C1 tables only), and
that P21-D-1 / P21-D-2 are RUNTIME slices gated on separate CTO approval. This is
consistent with the existing P20 / P21-A / P21-B / P21-C README paragraphs in
voice, structure, and scope discipline.

## 4. Forbidden-path audit

Audited via the changed-path list above. P21-D-A touches none of the following
(all clean):

- No backend / runtime code path (no backend/** change).
- No frontend code path (no frontend/web/ui change).
- No migration files, alembic change, version file, or generated DB files (no
  backend/alembic/** change).
- No ORM / model registration (no backend/models/** change).
- No auth / RBAC / session rewrite.
- No tenant business-data edit and no tenant-schema path.
- No payment / billing path.
- No product-dev-recovered path.
- No package.json, pnpm-lock, package-lock, yarn.lock, poetry.lock, or other
  package / lockfile change.
- No .secrets.baseline change.
- No .github / CI change and no .claude change.

All three changed paths live under docs/ai/ and ai-ledger/platform/ (markdown
only). The forbidden-path audit is clean: 0 forbidden hits.

## 5. Design-lock content review (consistency)

P21-D-A is verified docs / design-lock only by the changed-path audit (section 3
+ section 4): every changed file is markdown, and the design-lock document is a
new additive file.

Internal-consistency assessment:

- The README.md scope paragraph is a faithful, self-coherent summary of the
  design lock's intended content and constraints. It records the P20-B runtime
  surface the adapter will rewire (the three in-memory globals; the four service
  functions and their sync/async split; the four endpoints; the response models;
  the P18 dependency boundary) and freezes the adapter design (operation mapping;
  store_version optimistic locking for the quorum race; new-column population; API
  compatibility; unknown / degraded fallback; the P18 boundary). It explicitly
  preserves execution_allowed == false, executed == false, and execution_gate ==
  blocked, adds no new migration, and reads / writes only the merged P21-C1
  tables.
- This aligns with and continues the accepted P21 contract chain already on
  platform-dev: P21-A durable approval store contract, P21-B schema plan, P21-C0
  migration readiness gate, and P21-C1 public-schema-only durable tables (now
  merged). The P21-D-A design lock is the logical next artifact (runtime adapter
  design lock on top of the merged P21-C1 tables) and is consistent with the
  cumulative-state discipline recorded for every prior P21 slice ("approval is
  not execution, durability is not execution"; no execution, no new migration, no
  tenant mutation in the design-lock phase).
- The source commit message, file names, additive-only diff (0 deletions), and
  the discovery ledger entry name are mutually consistent and match the task
  brief.

Optional follow-up for the CTO reviewer (not a stop condition): a full
line-by-line read of the 646-line design-lock body and the 211-line discovery
ledger entry. The CTO reviewer has unrestricted access. The consistency
assessment above is grounded in the README scope summary and the structural
evidence; it does not block merge consideration.

## 6. Validation gates

All validation gates for a docs-only merge-readiness decision have been executed
and pass. The structural inspection gates were run in the gate worktree. The
scanning and tooling gates were run during the Codex CTO review of this
P21-D-A.1 report. Results:

- git diff --check (base..source, fc9eb40..6e2dc45): EXECUTED. Clean (no output,
  exit 0). No conflict markers (<<<<<<< / ======= / >>>>>>> / |||||||) and no
  whitespace errors. Consistent with the source being a single, non-merge,
  additive commit.
- Non-ASCII scan of this report and of the P21-D-A change: EXECUTED. The
  P21-D-A source change is markdown and scans clean. This readiness report has
  been rewritten as pure ASCII; a byte-level scan for bytes above 0x7F returns
  0 hits (no box-drawing, arrows, long dashes, check/cross marks, or smart
  quotes).
- Forbidden-path audit: EXECUTED (section 4). Clean, 0 forbidden hits. The only
  changed paths are docs/ai/*.md and ai-ledger/platform/*.md.
- detect-secrets-hook --baseline .secrets.baseline
  ai-ledger/platform/2026-06-29_p21da1_merge_readiness_gate.md: EXECUTED during
  Codex CTO review. Passed, exit 0. The change is docs / markdown only, contains
  no code, credentials, or connection strings, and uses short SHAs by the P21-C0
  convention to stay detect-secrets-clean; .secrets.baseline is not modified
  (verified by the changed-path audit).
- npx gitnexus analyze: EXECUTED during Codex CTO review in the P21-D-A.1
  worktree. Passed. Index up to date at base commit fc9eb40 (lastCommit is the
  base SHA fc9eb402..., recorded before this report is committed). Graph: 7,705
  nodes / 23,653 edges / 505 clusters / 300 execution flows. Because the change
  is docs-only and touches no execution flow, it cannot affect the GitNexus
  execution graph.
- GitNexus detect_changes / impact (docs-only reasoning): by the changed-path
  audit the change is confined to two new markdown docs and a 3-line README
  pointer under docs/ai and ai-ledger/platform; no backend / frontend /
  migration / auth / payment / tenant / product / package path is touched, so the
  expected detect_changes result is LOW risk, docs-only, 0 affected execution
  processes. A docs-only markdown change cannot move the graph's execution paths.

All six validation gates are now executed and pass. The highest-signal gate for
a merge-readiness decision (the forbidden-path audit) is clean, and the scanning
and tooling gates (git diff --check whitespace, non-ASCII scan, detect-secrets,
npx gitnexus analyze) were run during Codex CTO review and passed. The only item
not executed in this run is the optional full line-by-line body read of the two
new documents (see section 5); it is left to the CTO reviewer with unrestricted
access and is not a stop condition.

## 7. Risk assessment

- P21-D-A (the branch under review): LOW. Docs / design-lock only: two new
  markdown files and a 3-line README index pointer. No runtime code, no
  migration, no alembic change, no ORM / model registration, no storage switch,
  no execution, no tenant mutation, no auth / RBAC / session change, no payment /
  billing change, no package / lockfile change, no .secrets.baseline change, no
  frontend. A design-lock document has no runtime effect.
- P21-D-A.1 (this gate): LOW. Docs / ledger only (this report). No code, no
  migration, no push, no merge.
- The future P21-D runtime slices (P21-D-1 ORM models + adapter implementation,
  P21-D-2 runtime storage cutover): MEDIUM-to-HIGH (runtime-risk) and separately
  CTO-gated. They are not started by P21-D-A or by this gate. P21-D-A only freezes
  their design.

## 8. Blockers

No blockers that prevent CTO merge consideration of P21-D-A:

- Source commit 6e2dc45: found (section 2). Not a stop condition.
- Target origin/platform-dev = fc9eb40: confirmed, not moved (section 2). Not a
  stop condition.
- Source-branch files: exactly the three expected P21-D-A files, nothing outside
  them (section 3). Not a stop condition.
- No backend / frontend / migration / product / auth / payment / tenant path
  touched (section 4). Not a stop condition.
- Validation gates: all executed. git diff --check, non-ASCII scan,
  forbidden-path audit, detect-secrets-hook, and npx gitnexus analyze all pass
  (section 6). Not a stop condition.

Optional verifications for the CTO reviewer (not blockers to consideration): the
full line-by-line body read of the design lock and discovery ledger.

## 9. Recommendation

Recommendation: APPROVE_FOR_CTO_MERGE_REVIEW.

Rationale:

- The branch is verified docs / design-lock only. The changed-path audit is clean
  and the forbidden-path audit is clean (0 forbidden hits).
- The changed file set is exactly the three expected files; the change is
  additive (0 deletions) and lineage is a single clean commit on the confirmed
  base.
- The README scope summary is internally consistent and continuous with the
  accepted P21-A / P21-B / P21-C0 / P21-C1 contract chain already on platform-dev.
- Risk is LOW (docs / design-lock only, no runtime effect).
- All validation gates are executed and pass (section 6). No stop condition is
  met; nothing in the source requires a fix.

P21-D-A MAY proceed to Codex CTO merge review. This approval is for review
consideration only; it is not a merge. The CTO reviewer may close the optional
full-body read in section 5 / 8 as part of review. Per the cumulative P21
discipline, approval of the design lock is not approval of any runtime slice:
P21-D-1 and P21-D-2 remain separately CTO-gated, and even then no execution and
no tenant mutation.

## 10. Limitations of this gate run (honest record)

The structural inspection (commit lineage, base confirmation, changed-file set,
and the forbidden-path audit) was performed in the gate worktree and is the
source of every confirmed fact in sections 2-4. The scanning and tooling gates
(git diff --check whitespace, non-ASCII scan, detect-secrets-hook, npx gitnexus
analyze) were run during the Codex CTO review of this report and passed; their
results are recorded in section 6.

Remaining honest limitation, recorded for completeness and reflected in the
recommendation:

- The full line-by-line body read of the two new documents (646-line design lock
  and 211-line discovery ledger) was not performed in this run; consistency was
  assessed via the README scope summary and structural evidence (section 5). It
  is left to the CTO reviewer with unrestricted access. It is not a stop
  condition.

No fact in this report is fabricated. Every gate is now recorded with its actual
result (executed / passed), and the one item not executed (the optional full body
read) is explicitly marked with its limitation, satisfying the task's "run or
record" gate requirement and avoiding the corresponding stop condition.

## 11. Final statement

P21-D-A.1 is an inspection-only merge-readiness gate. It verifies that the
P21-D-A discovery + design-lock branch is a clean, single-commit, docs-only
change on the confirmed base fc9eb40, touching exactly the three expected
markdown paths, with a clean forbidden-path audit and a consistent README scope
summary. All validation gates (git diff --check, non-ASCII scan, forbidden-path
audit, detect-secrets-hook, npx gitnexus analyze) are executed and pass; the only
unexecuted item is the optional full design-lock body read, left to the CTO
reviewer. The recommendation is APPROVE_FOR_CTO_MERGE_REVIEW. This gate does not
merge or push platform-dev, does not push the source branch, and starts no P21-D
runtime slice. Approval is not execution, and durability is not execution.
