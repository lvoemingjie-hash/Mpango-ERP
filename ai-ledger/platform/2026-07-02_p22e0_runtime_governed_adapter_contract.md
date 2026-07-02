# P22-E0 Runtime Governed Action Adapter Seam Contract

**Phase:** P22-E0 Runtime Governed Action Adapter Seam Contract (docs-only architecture revision)
**Date:** 2026-07-02
**Branch:** `codex/platform-p22e0-runtime-governed-adapter-contract-2026-07-02`
**Base:** `f48e9fe` (`origin/platform-dev` -- "merge: P22-D controlled execution readiness lock")
**Contract:** `docs/ai/PLATFORM_PRODUCT_P22_RUNTIME_GOVERNED_ADAPTER_CONTRACT.md` (this slice)
**Revises:** P22-D section 3 gate G5 only
**Author:** Codex (Claude worker)
**Status:** Complete; docs-only; ready for CTO review

---

## 1. Summary

P22-E0 is a **docs-only** architecture revision contract. It does three things and nothing else:

1. Records why the attempted P22-E READ-FIRST execution slice (`backup.check`) correctly STOPPED at
   its discovery step (the E0 STOP retrospective).
2. Revises exactly one gate of the P22-D real-execution design lock: **G5**. OLD G5 ("real execution
   runs ONLY through the P16 Worktree Execution Harness ... no direct in-process execution") is
   replaced by NEW G5 ("real execution runs ONLY through a runtime governed action adapter seam").
   P16 is returned to its real role: a development-time / agent-worker file-change audit harness,
   NOT a runtime controlled-action executor.
3. Defines the runtime governed action adapter seam a future real-execution phase must build and run
   actions through, fixes the `backup.check` future path and its P17 data-source dependency, and
   gates a later P22-E1 backend-only NON-EXECUTING skeleton.

P22-E0 performs NO execution, dispatches NO worker, drains NO queue, invokes NO harness, runs NO
shell / SQL / script / subprocess, and mutates NO tenant / product / payment / billing / registry /
provisioning / backup data. It ships NO runtime code, NO backend, NO frontend, NO migration, NO
alembic change, NO table, NO test code, NO dependency change, and NO P16 code change. It grants no
execution power and starts no P22-E1 work.

> **Approval is not execution. A passed dry-run is not execution. A recorded request is not
> execution. The P16 worktree harness is not a runtime executor.** The runtime governed action
> adapter seam is the only boundary a future real execution may run through, and the seam, the
> adapter, the dry-run, the acknowledgement, and the durable approval are all preconditions, not
> execution itself.

## 2. Base / Branch / Commit Chain

- **Base SHA:** `f48e9fe` (`origin/platform-dev`, P22-D merge).
- **Worktree:** `MPANGO ERP/codex-platform-p22e0-runtime-governed-adapter-contract-2026-07-02`,
  created from `origin/platform-dev` via `git worktree add --no-track -b <branch> <path>
  origin/platform-dev`. Upstream is unset, so a bare `git push` cannot fast-forward `platform-dev`;
  the branch is published with the explicit refspec `git push -u origin <branch>:<branch>` (the
  worktree-push gotcha).
- **Commit chain (base..tip):** two commits on top of `f48e9fe`:
  - `f48e9fe` -- base (origin/platform-dev, P22-D merge)
  - `ab36017` -- `platform(p22e0): runtime governed action adapter seam contract (G5 revision)`
    (the contract doc + the README cumulative-state line + this ledger)
  - the R1 evidence-fix commit -- `platform(p22e0-r1): ledger GitNexus tip evidence + README G5
    conflict fix` (docs-only; corrects the ledger GitNexus status to read indexed/current == branch
    tip instead of base, and rewrites the README P22 paragraph's two old `P16 governed harness`
    clauses so the paragraph states unambiguously that P22-E0 supersedes P22-D G5). The R1 tip SHA is
    reported in the chat report, not self-referenced here (this ledger is part of the R1 commit); only
    `docs/ai/README.md` and this ledger changed in R1 -- no runtime code.

`platform-dev` was NOT merged and is NOT the push target. Only the isolated P22-E0 branch carries
these changes and is published to its own remote ref.

## 3. Modified / Added Files (exactly the three allowed)

| File | Status | Scope |
|---|---|---|
| `docs/ai/PLATFORM_PRODUCT_P22_RUNTIME_GOVERNED_ADAPTER_CONTRACT.md` | New | The contract: E0 STOP retrospective; G5 OLD -> NEW revision; corrected P16 role; runtime governed adapter seam definition (9 properties + planning adapter shape + seam-vs-P16 table); `backup.check` future path; P17 backup-source dependency; 18 acceptance criteria; 20 counterexamples; P22-E1 entry gate; relationship to P22-A / P22-D; docs-only statement |
| `docs/ai/README.md` | Modified (additive) | One cumulative-state sentence appended to the P22 read-order paragraph (ASCII-only) |
| `ai-ledger/platform/2026-07-02_p22e0_runtime_governed_adapter_contract.md` | New | This ledger |

No other paths were touched. `git diff --name-only origin/platform-dev..HEAD` returns exactly these
three paths. No `backend/`, no `frontend/`, no `migrations/`, no `alembic/env.py`, no
`scripts/platform_worktree_executor.py` or any other P16 asset, no `product-dev-recovered/`, no
product / payment / billing / order / invoice / customer / inventory / ledger path, no test file, no
`package.json` / lockfile, no CI / `.github` / `.claude` file, and no configured secrets baseline
file.

## 4. Why P22-E0 Exists (E0 STOP retrospective, summary)

The attempted P22-E READ-FIRST slice (`backup.check`) STOPPED at discovery because four as-built
facts on `origin/platform-dev` at `f48e9fe` combine to block any faithful implementation of G5 as
written in P22-D:

1. The only "P16 governed harness" is `scripts/platform_worktree_executor.py` -- a `subprocess`-based,
   file-change-auditing worktree mission runner for agent workers (verdict = changed-files vs
   expected-files + forbidden-path prefixes). It cannot host a bounded read adapter or return a
   backup-status result.
2. There is no in-process governed adapter seam in the platform runtime (a full `backend/` search
   found only unrelated Starlette `dispatch`, auth / reporting `.execute()`, and `core/governance/*`
   BI-asset URN governance).
3. `backup.check` has no data source: P17 records "Backup system source is not yet wired" and
   assembles `backup_status=None` everywhere.
4. The P22 source is AST-tested to forbid the very `execute` / `subprocess` / `p16` symbols a
   real-execution path needs.

Every implementation path violated a hard boundary (direct in-process adapter violates G5 + the AST
invariants; invoking the worktree executor violates the no-subprocess rule + AST invariants + is a
semantic mismatch; inventing a new seam without a contract is neither "the P16 harness" nor an
"existing platform harness contract"). The structural conclusion: G5 conflated the development-time
agent worktree harness with a runtime controlled-action executor. P22-E0 corrects that at the
contract layer. Full evidence is in section 2 of the contract doc.

## 5. G5 Revision (OLD -> NEW)

- **OLD G5 (P22-D):** "Real execution runs ONLY through the P16 Worktree Execution Harness. There is
  no direct in-process execution, no side channel, and no bypass. The harness is the single execution
  boundary."
- **NEW G5 (P22-E0):** "Real execution of a v0 action runs ONLY through the runtime governed action
  adapter seam. The seam is a per-action, bounded, typed, preflight-gated, before / after /
  failure-audited, idempotency-guarded, source-honest, no-tenant-business-mutation, fail-closed
  adapter boundary inside the platform runtime. There is no direct in-process bypass, no side
  channel, and no generic shell / SQL / script / subprocess executor. The P16 Worktree Execution
  Harness is a development-time / agent-worker file-change audit harness; it is NOT a runtime
  controlled-action executor and is never invoked at request time."

G1-G4, G6, and G7 are unchanged. The allowlist, the exclusion list, the preconditions, the dry-run /
request / result models, the audit contract, the idempotency rules, the safety rules, the
operator-separation policy, and the permanent hard stops are all unchanged. No P16 code, contract
term, or asset is changed.

## 6. Runtime Governed Action Adapter Seam (property summary)

The seam is the single runtime execution boundary. Its nine conjunctive properties: (1) per-action
adapter only, one named bounded adapter per allowlisted action; (2) no generic shell / SQL / script /
subprocess; (3) typed, echo-safe request / response; (4) preflight gate re-validating G1-G4 + source
status at execution time; (5) before / after / failure audit (`execution_started` /
`execution_succeeded` | `execution_failed` [+ compensation]); (6) digest-only idempotency guard
(replay vs conflict, no duplicate success); (7) source-status honesty (unknown never healthy;
degraded reads-only, changes no state); (8) no tenant business mutation; (9) fail closed. The seam
does not call P16 and P16 does not call the seam. Full definition and the planning adapter shape are
in sections 4.2-4.4 of the contract doc.

## 7. `backup.check` Path + P17 Dependency

`backup.check` stays READ-FIRST and remains the intended first candidate, but it may not begin until
(a) the seam is CTO-accepted and realized (at least as a non-executing skeleton) and (b) its data
source is explicitly identified. The P17 backup source is currently unwired (`backup_status=None`
with the documented reason); a future `backup.check` adapter must read a real platform backup /
status source or operate under an explicit degraded / unknown contract, and must never fabricate a
healthy status. "Unknown is never healthy" and "null is never zero" hold absolutely. P22-E0 wires no
source and changes no P17 code.

## 8. Validation Gates

| Gate | Result |
|---|---|
| `git diff --check origin/platform-dev..HEAD` | clean (exit 0; no whitespace errors) |
| Changed files | exactly the three allowed paths (section 3) |
| Non-ASCII scan on changed files | 0 non-ASCII bytes across all P22-E0 deliverables (contract 39,423 B; README + ledger re-scanned ASCII-clean in R1) |
| detect-secrets (configured baseline) | clean (pre-commit passed on the R0 commit; R1 re-verified with detect-secrets-hook against the configured baseline on the two changed files) |
| Forbidden path audit | clean (section 10) |
| `npx gitnexus analyze .` | indexed successfully (~18s); see section 9 |
| `npx gitnexus status` | up-to-date; indexed commit == current commit == branch tip, not base (docs-only adds no code-graph nodes) |
| Worktree clean (post-commit) | tracked tree clean (only gitignored `__pycache__` / `.gitnexus` artifacts, none committed) |

## 9. GitNexus

- `npx gitnexus analyze .` (re-index at the branch tip): repository indexed successfully in ~18s --
  **~8,373 nodes | 25,588 edges | ~533 clusters | 300 flows**. Edges (25,588) and flows (300) are
  stable; node and cluster counts vary +/-2-3 between fresh builds of the same tip (the P22-D rebuild
  at this base reported ~8,368-8,371 nodes / 25,587 edges / ~529-532 clusters / 300 flows; the R0 and
  R1 docs-only rebuilds reported 8,373 nodes / 25,588 edges / 533 clusters / 300 flows). Docs-only
  changes add no code-graph nodes; the counts reflect the `platform-dev` base after the P22-D merge.
  Documented as a band, not a point, to avoid amend loops.
- `npx gitnexus status`: index is **up-to-date** -- indexed commit == current commit == the branch
  tip, NOT the base `f48e9fe`. P22-E0 is docs-only, so the code graph is unchanged from the base, but
  the index tracks the branch tip (after both the R0 and R1 commits the index was re-built at the tip
  and reported up-to-date). The R1 tip SHA is reported in the chat report, not self-referenced here
  (this ledger is part of the R1 commit); the prior R0 tip was `ab36017`.

## 10. Forbidden Path Audit

`git diff --name-only origin/platform-dev..HEAD` returns exactly three paths, all under `docs/ai/`
and `ai-ledger/platform/`:

- `docs/ai/PLATFORM_PRODUCT_P22_RUNTIME_GOVERNED_ADAPTER_CONTRACT.md`
- `docs/ai/README.md`
- `ai-ledger/platform/2026-07-02_p22e0_runtime_governed_adapter_contract.md`

None matches any forbidden prefix or fragment:

- No `backend/`, no `frontend/`, no `migrations/`, no `alembic/env.py`.
- No `scripts/` change -- in particular no `scripts/platform_worktree_executor.py` or any other P16
  asset.
- No `product-dev-recovered/` or any product / business path (no orders, payments, billing, finance,
  inventory, client, customer, invoice, ledger).
- No auth / RBAC / session / tenancy rewrite.
- No `package.json`, no lockfiles, no dependency changes.
- No `.github/`, no `.claude/`, no configured secrets baseline file, no CI / deploy files.
- No real execution / worker / harness invocation / shell / SQL / script / subprocess.

## 11. Self-Review

- Did P22-E0 add execution power? No -- it is docs-only; no runtime code, no adapter, no execution
  path.
- Did it weaken any gate? No -- it revises only G5 to point at the correct boundary (a runtime seam)
  and tightens the description (P16 is explicitly not a runtime executor); G1-G4, G6, G7 and all hard
  stops are unchanged.
- Did it touch P16? No -- no P16 code, contract term, or asset is changed.
- Did it fabricate a backup source? No -- it explicitly records that the source is unwired and bars
  fabrication.
- Is it ASCII-clean and secrets-clean? Yes -- 0 non-ASCII bytes; detect-secrets (configured baseline)
  passed; only short SHAs are used and the baseline is referenced as "the configured baseline".
- Does it start P22-E1? No -- P22-E1 is gated behind CTO acceptance of E0.

## 12. Risk

**Low.** P22-E0 is docs-only and additive (the README change is a one-sentence append; the other two
files are new). It touches no runtime code, no migration, no tests, no dependencies, no auth / RBAC /
session / tenancy, no P16 code, and no product / payment / tenant business path. It changes one
contract gate (G5) to correct a semantic error and defines a seam; it grants no execution power.

## 13. Blockers

None.

## 14. Explicit Statements

- **No execution.** P22-E0 performs no execution, dispatches no worker, drains no queue, invokes no
  harness, and runs no shell / SQL / script / subprocess.
- **No runtime change.** No `backend/` or `frontend/` file is touched; no adapter is implemented.
- **No P16 change.** No `scripts/platform_worktree_executor.py` or any P16 code / contract / asset is
  touched; P16 remains the development-time / agent-worker file-change audit harness.
- **No migration / schema / storage change.** None.
- **No product / payment / tenant business mutation.** None.
- **No auth / RBAC / session rewrite.** None.
- **No package / lockfile / dependency change.** None.
- **No tests added or changed.** P22-E0 is docs-only.
- **platform-dev untouched.** `origin/platform-dev` was not merged and not pushed from P22-E0.
- **P22-E1 not started.** P22-E0 begins no backend runtime work. P22-E1 (a backend-only non-executing
  runtime seam skeleton) may begin only after CTO acceptance of E0, and still no real `backup.check`
  until a real backup / status source (or an explicit degraded / unknown contract) is proven.
