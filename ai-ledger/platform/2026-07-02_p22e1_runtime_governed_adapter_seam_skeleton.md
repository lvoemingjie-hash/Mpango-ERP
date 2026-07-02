# P22-E1 Runtime Governed Action Adapter Seam Skeleton

**Phase:** P22-E1 Runtime Governed Action Adapter Seam Skeleton (backend-only, NON-EXECUTING)
**Date:** 2026-07-02
**Branch:** `codex/platform-p22e1-runtime-governed-adapter-seam-skeleton-2026-07-02`
**Base:** `317c407` (`origin/platform-dev` -- the P22-E0 merge; the runtime governed adapter
seam contract / G5 revision is on the books)
**Author:** Codex (Claude worker)
**Status:** Complete; backend-only non-executing skeleton; ready for CTO review

---

## 1. Summary

P22-E1 is the gated backend-only, NON-EXECUTING realization of the runtime governed action
adapter seam defined by P22-E0 (docs/ai/PLATFORM_PRODUCT_P22_RUNTIME_GOVERNED_ADAPTER_
CONTRACT.md, section 9). It builds the SEAM SHAPE only and runs nothing.

It adds exactly four files and modifies none of the existing P22-A/P22-B/P22-C/P22-D surface:

1. `backend/api/v1/platform/p22/adapters.py` -- the per-action NON-EXECUTING adapter registry.
   One named, bounded, not_implemented descriptor per allowlisted v0 action; allowlist-only
   resolution; no generic dispatcher; no fallback adapter.
2. `backend/api/v1/platform/p22/seam.py` -- the seam skeleton: per-action adapter resolution,
   the preflight gate (REUSES the P22-B precondition evaluator), the before / after / failure /
   denial audit-shape templates (field names only), and the digest-only idempotency classify.
3. `backend/tests/test_platform_p22e1_runtime_governed_adapter_seam.py` -- 29 targeted tests
   (registry, non-executing adapters, backup.check honesty, preflight fail-closed, idempotency,
   audit-shape redaction, and AST / text scans proving no forbidden symbol).
4. `ai-ledger/platform/2026-07-02_p22e1_runtime_governed_adapter_seam_skeleton.md` -- this ledger.

P22-E1 performs NO execution: it dispatches NO worker, drains NO queue, invokes NO development-
time worktree harness, runs no shell / SQL / script / external process, reads / writes NO tenant
business data, and writes NO real execution_succeeded audit event. Every adapter is
not_implemented and realizes_execution / realized_execution / executed are always False. The seam
is import-tested only; it is not wired into any HTTP route and adds no public execution entry
point. backup.check is an honest source_unknown / not_implemented slot; it never fabricates a
healthy read.

> **Approval is not execution. A passed dry-run is not execution. A recorded request is not
> execution. A passed preflight is not execution.** The seam is a PRECONDITION boundary, not an
> executor. Real execution of any v0 action remains reserved for a separately CTO-approved phase
> that runs through this seam behind revised G5 + G1-G4 + G6-G7.

## 2. Base / Branch / Commit Chain

- **Base SHA:** `317c407` (`origin/platform-dev`, the P22-E0 merge that revised G5).
- **Worktree:** `MPANGO ERP/codex-platform-p22e1-runtime-governed-adapter-seam-skeleton-2026-07-02`,
  created from `317c407` via `git worktree add --no-track -b <branch> <path> 317c407`. Upstream is
  unset, so a bare `git push` cannot fast-forward `platform-dev`; the branch is published with the
  explicit refspec `git push -u origin <branch>:<branch>` (the worktree-push gotcha).
- **Commit chain (base..tip):** the base `317c407`, then the P22-E1 R0 commit (the two seam modules
  + the test file + this ledger), then the P22-E1-R1 evidence-fix commit (this ledger only --
  corrects the GitNexus numbers to the branch tip and records the actual detect_changes result).
  The exact tip SHA is reported in the chat report, not self-referenced here (this ledger is part
  of the R1 commit); the chain is `317c407` -> R0 -> R1 tip.

`platform-dev` is NOT merged and is NOT the push target. Only the isolated P22-E1 branch carries
these changes and is published to its own remote ref.

## 3. Added Files (exactly the four allowed)

| File | Status | Scope |
|---|---|---|
| `backend/api/v1/platform/p22/adapters.py` | New | NON-EXECUTING adapter registry: AdapterDescriptor; ADAPTER_REALIZES_EXECUTION=False; allowlist-only resolve / inventory / is_registered_action; non_executing_adapter_result; backup.check is source_unknown (P17 source not wired) |
| `backend/api/v1/platform/p22/seam.py` | New | Seam skeleton: SeamAdapterRequest (typed, digest-only); PreflightVerdict (realized_execution / executed always False); expected_seam_audit_shape (before/after/failure/denial templates, field names only); classify_idempotency (digest-only new/replay/conflict); evaluate_preflight_gate (reuses P22-B evaluator, fail-closed) |
| `backend/tests/test_platform_p22e1_runtime_governed_adapter_seam.py` | New | 29 tests (see section 6) |
| `ai-ledger/platform/2026-07-02_p22e1_runtime_governed_adapter_seam_skeleton.md` | New | This ledger |

No existing file is modified. `git diff --name-only origin/platform-dev..HEAD` returns exactly the
three code/test/ledger paths above (the ledger is part of this commit). No `frontend/`, no
`migrations/`, no `alembic/env.py`, no `scripts/platform_worktree_executor.py` or any P16 asset, no
`product-dev-recovered/`, no product / payment / billing / order / invoice / customer / inventory /
ledger path, no `package.json` / lockfile, no CI / `.github` / `.claude` file, no auth / RBAC /
session / tenancy file, and no configured secrets baseline file.

## 4. What the Seam Skeleton IS (shape only)

- **Per-action adapter resolution (P22-E0 4.2.1).** An allowlisted action_type resolves to its ONE
  NON-EXECUTING adapter descriptor; every other value (excluded action, unknown string, None,
  empty) resolves to None. There is no generic dispatcher and no fallback adapter.
- **Preflight gate (P22-E0 4.2.4).** `evaluate_preflight_gate` re-validates the full precondition
  set at execution time by REUSING the P22-B precondition evaluator (`_executor_block_reason`,
  `_classify_action`, `_resolve_approval`, `_check_approval_preconditions`, the in-memory dry-run
  store): executor is identity-only super_admin; idempotency digest present; explicit
  acknowledgement present; action allowlisted; the bound dry-run still matches approval / action /
  tenant / requested_state / executor and is not expired; the durable approval is at
  approved_execution_blocked with quorum, matching action / target, honest source, and operator
  separation; and the digest-only idempotency is not a conflict. Any failed precondition blocks
  (fail closed).
- **Audit shape (P22-E0 4.2.5).** `expected_seam_audit_shape` returns the before
  (execution_started) / after (execution_succeeded) / failure (execution_failed) / compensation
  (execution_compensation_recorded) templates for a passed verdict, and the denial
  (execution_denied) template for a blocked verdict. FIELD NAMES ONLY -- never a value, secret,
  digest-as-value, or executed=True. The skeleton writes NO real audit event.
- **Idempotency guard (P22-E0 4.2.6).** `classify_idempotency` is a digest-only, read-only
  new / replay / conflict classification against the recorded request store. The raw key is never
  accepted or stored; only its one-way digest is.

## 5. What the Seam Skeleton is NOT

- It performs NO execution. It dispatches NO worker, drains NO queue, invokes NO development-time
  worktree harness, runs no shell / SQL / script / external process, and writes NO real
  execution_succeeded audit event.
- Every adapter is not_implemented. `ADAPTER_REALIZES_EXECUTION`, `SEAM_REALIZES_EXECUTION`,
  `PreflightVerdict.realized_execution`, and `PreflightVerdict.executed` are always False.
- backup.check is an honest source_unknown / not_implemented slot. It never fabricates a healthy /
  known read and reads no unverified source (the P17 backup source is not yet wired).
- It is NOT wired into any HTTP route and adds no public execution entry point. It reuses the
  existing P22 routes (catalog / dry-run / requests); the seam is import-tested only.
- It changes NO existing P22-A / P22-B / P22-C / P22-D code, NO P16 code, NO migration, NO schema,
  NO auth / RBAC / session / tenancy, NO frontend, and NO dependency.

## 6. Tests

`backend/tests/test_platform_p22e1_runtime_governed_adapter_seam.py` -- **29 passed** (shared venv
pytest, PYTHONPATH=backend, PYTHONUTF8=1). Coverage:

- Registry is allowlist-only: exactly the seven v0 actions in order; resolution of an excluded /
  unknown / None / empty action is None; no generic dispatcher; no fallback.
- Every descriptor is non_executing / not_implemented; the non-executing result never carries
  executed=True; an arbitrary action is not_registered.
- backup.check is source_unknown / not_implemented and never fabricates a healthy source; no
  adapter reports a known source in the skeleton.
- Preflight is fail-closed and reuses the P22-B evaluator: a fully valid binding passes (but
  realizes no execution); a missing acknowledgement, a non-super_admin executor, an unknown
  action, a missing / invalid dry-run, a missing idempotency digest, an expired approval, a target
  mismatch, and an idempotency conflict each block. A passed verdict still has executed=False.
  backup.check passes preflight only as a not_implemented slot (no fabricated read).
- Idempotency is digest-only: new / replay / conflict classify correctly; SeamAdapterRequest
  carries a digest, never a raw key.
- Audit shape is field-name templates only: no boolean value, no executed=true, no request value
  leaks.
- No-execution invariants: an AST scan of EVERY p22 source file (seam + adapters included) proves
  no subprocess / os.system / os.popen / os.execv / os.execve / shell=True / eval / exec / harness
  / action-execution call token, and no p16 / subprocess / product / order / payment / invoice /
  customer / inventory / ledger / billing import; a raw-text scan of the new modules proves no
  invocation token; and the seam / adapters public API exposes no generic executor name
  (execute / run / dispatch / invoke / start_worker). A test also confirms the preflight gate
  reuses the P22-B evaluator symbols rather than re-implementing execution semantics.

## 7. Validation Gates

| Gate | Result |
|---|---|
| `git diff --check origin/platform-dev..HEAD` | clean (exit 0; no whitespace errors) |
| Changed files | exactly the four allowed paths (section 3) |
| Non-ASCII scan on new files | 0 non-ASCII bytes across all three code/test files (Python byte scan) |
| detect-secrets (configured baseline) | clean on all changed files (pre-commit detect-secrets-hook against the configured baseline) |
| Forbidden path audit | clean (section 9) |
| P22-B regression (`test_platform_p22_controlled_execution.py`) | 56 passed (the non-executing baseline is unbroken) |
| P22-E1 targeted tests | 29 passed |
| `npx gitnexus analyze .` | indexed successfully (~16s); see section 8 |
| `npx gitnexus status` | up-to-date at the branch tip (re-indexed after commit; indexed commit == current commit == tip) |
| detect_changes (compare vs origin/platform-dev) | changed_count 75, changed_files 4, affected_count 0, risk_level low, affected_processes []; see section 8 |
| Worktree clean (post-commit) | tracked tree clean |

## 8. GitNexus

- `npx gitnexus analyze .` at the branch tip: repository indexed successfully in ~16s --
  **~8,456 nodes | 25,846 edges | ~536 clusters | 300 flows**. Edges (25,846) and flows (300) are
  stable; node and cluster counts vary slightly between fresh builds of the same tip (a pre-commit
  working-tree scan reported ~8,438 nodes / 25,831 edges / ~533 clusters / 300 flows; the post-
  commit tip adds this ledger's markdown heading nodes and the test module nodes). Documented as a
  band, not a point, to avoid amend loops.
- `npx gitnexus status`: re-indexed at the branch tip after commit -- indexed commit == current
  commit == the branch tip, status up-to-date. The exact tip SHA is reported in the chat report,
  not self-referenced here.
- detect_changes (compare vs `origin/platform-dev`), run at the branch tip via the GitNexus MCP
  detect_changes tool (scope=compare, base_ref=origin/platform-dev): **changed_count 75,
  affected_count 0, changed_files 4, risk_level low, affected_processes []**. Because the seam is
  import-tested and not wired into any route or service flow, NO process is affected -- not a
  platform process and not a product business process. The 75 changed symbols are the new adapter /
  seam / test symbols plus this ledger's markdown heading nodes (gitnexus parses markdown headings
  as graph nodes). The product-token grep over affected_processes and changed_symbols file paths
  (order, payment, invoice, customer, inventor, ledger, billing, finance, product) returns 0
  product business tokens; every changed symbol file path is under backend/api/v1/platform/p22/,
  backend/tests/, or ai-ledger/platform/. The stop-condition gate ("affected flows must all be
  platform P22 internal; 0 product business flow") holds decisively: affected_count is 0.

## 9. Forbidden Path Audit

The change set is exactly four paths, all under `backend/api/v1/platform/p22/`,
`backend/tests/`, and `ai-ledger/platform/`:

- `backend/api/v1/platform/p22/adapters.py`
- `backend/api/v1/platform/p22/seam.py`
- `backend/tests/test_platform_p22e1_runtime_governed_adapter_seam.py`
- `ai-ledger/platform/2026-07-02_p22e1_runtime_governed_adapter_seam_skeleton.md`

None matches any forbidden prefix or fragment:

- No existing file modified; no `frontend/`, no `migrations/`, no `alembic/env.py`.
- No `scripts/` change -- in particular no `scripts/platform_worktree_executor.py` or any P16 asset.
- No `product-dev-recovered/` or any product / business path.
- No auth / RBAC / session / tenancy rewrite.
- No `package.json`, no lockfiles, no dependency changes.
- No `.github/`, no `.claude/`, no configured secrets baseline file, no CI / deploy files.
- No real execution / worker / harness invocation / shell / SQL / script / external process.

## 10. Self-Review

- Did P22-E1 add execution power? No -- every adapter is not_implemented; realized_execution and
  executed are always False; no adapter body runs; no audit success is written.
- Did it weaken any gate? No -- it reuses the P22-B precondition evaluator unchanged and adds a
  fail-closed preflight; G1-G7 and all hard stops stand.
- Did it touch P16? No -- no P16 code, contract term, or asset is changed; the seam never calls the
  worktree harness.
- Did it fabricate a backup source? No -- backup.check is source_unknown / not_implemented; the P17
  source is still unwired and is never synthesized as healthy.
- Did it break the non-executing baseline? No -- the P22-B regression passes 56/56 unchanged.
- Is it ASCII-clean and secrets-clean? Yes -- 0 non-ASCII bytes; detect-secrets (configured baseline)
  passed; only short SHAs are used and the baseline is referenced as "the configured baseline".
- Did it wire a new public execution entry point? No -- the seam is import-tested only; no route is
  added and no existing route is changed.

## 11. Risk

**Low.** P22-E1 is backend-only and additive (four new files; no existing file modified). It
touches no migration, no schema, no auth / RBAC / session / tenancy, no P16 code, no frontend, no
dependency, and no product / payment / tenant business path. GitNexus detect_changes at the branch
tip reports risk_level low with affected_count 0 (the seam is import-tested and not wired into any
route or service flow, so no process -- platform or product -- is affected). The seam is
non-executing: it runs no adapter, writes no success audit, and a passed preflight is not execution.

## 12. Blockers

None.

## 13. Explicit Statements

- **No real execution.** P22-E1 runs no adapter, dispatches no worker, drains no queue, invokes no
  development-time worktree harness, and runs no shell / SQL / script / external process.
- **No tenant / business mutation.** No order, payment, invoice, customer, inventory, or ledger
  record is read or written; tenant_id is a scoped identifier only.
- **No migration / schema / storage change.** None (in-memory, process-local, like P22-B).
- **No P16 change.** No `scripts/platform_worktree_executor.py` or any P16 code / contract / asset
  is touched; P16 remains the development-time / agent-worker file-change audit harness.
- **No frontend.** None.
- **No auth / RBAC / session rewrite.** None (the executor identity is supplied to the seam by the
  caller; in a live wiring it would come from the existing P10 identity-only guard).
- **No new public execution entry point.** The seam is import-tested only; existing P22 routes are
  reused unchanged.
- **P22-E2 not started.** P22-E1 lands the non-executing seam skeleton only. The first real adapter
  execution (earliest, a proven backup.check) is a separately CTO-approved phase that must satisfy
  revised G5 + G1-G4 + G6-G7 in full and run only through this seam; no real backup.check begins
  until its data source is explicitly identified.
