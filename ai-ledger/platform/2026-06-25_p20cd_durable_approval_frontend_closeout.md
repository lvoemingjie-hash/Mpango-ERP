# P20-C / P20-D Durable Approval Frontend Console + Governance Closeout

Date: 2026-06-25
Phase: P20-C (read-only durable approval frontend console on top of the P20-B
backend skeleton) and P20-D (P20 master ledger, evidence, and operational
readiness / closeout). This is the closeout revision for the whole P20 track.
Branch: codex/platform-p20cd-durable-approval-frontend-closeout-2026-06-25
Base: origin/platform-dev = a62bcbe (merge: P20-B durable approval backend
skeleton; P20-A contract and P20-B skeleton already merged into platform-dev).
Scope: frontend console + typed API client + types + frontend tests + this
ledger + a docs/ai read-order accuracy edit. No backend code, no migration, no
alembic change, no real execution, no tenant mutation, no auth/RBAC/session
rewrite, no package or lockfile change, no change to the configured secret
baseline.

This phase adds a read-only durable approval console wired to the existing P20-B
read path, plus the P20 master closeout. It does not execute any controlled
action, does not mutate tenant data, does not add a migration or a real durable
backend, and does not merge anything into platform-dev. It is an isolated
branch, pending CTO review. P21 is not started.

## 1. Phase inventory

P20-A - durable approval governance contract (docs-only) - MERGED into
platform-dev.
- Ledger: ai-ledger/platform/2026-06-25_p20a_durable_approval_governance_contract.md
- Verdict recorded there: P20-A_CONTRACT_READY.

P20-B - durable approval backend skeleton (non-executing, in-memory) - MERGED
into platform-dev at a62bcbe (this branch's base).
- Ledger: ai-ledger/platform/2026-06-25_p20b_durable_approval_backend_skeleton.md
- Verdict recorded there: P20-B_SKELETON_READY (with P20-B-R1 identity binding
  + P20-B-R2 comment cleanup; maker/checker bound to the authenticated
  identity-only super_admin actor).

P20-C - durable approval frontend console (read-only, non-executing) - THIS
BRANCH.
- Source branch: codex/platform-p20cd-durable-approval-frontend-closeout-2026-06-25
- Base: origin/platform-dev = a62bcbe
- Code commit: 231cba1 (feat(platform): P20-C durable approval frontend console)
  - 6 files changed, 1612 insertions.
- Ledger commit: this file (docs/ledger only).
- Risk: detect_changes medium (a new frontend-only process is introduced -- the
  console's own page -> submitDecision -> unwrap flow); no backend symbol and no
  product business process affected.
- Status: on isolated branch; not merged to platform-dev.

P20-D - P20 master ledger, evidence, operational readiness, closeout - THIS
FILE (same branch, docs/ledger commit following 231cba1).

## 2. What each P20 slice did and did not do

P20-A (merged): defined the durable approval governance contract only. The
persistent approval store shape, digest-only idempotency, full reason/comment
redaction, retention/purge/export boundaries, dual-control policy
(maker-checker separation, quorum, tenant-contextual denied, emergency override
forbidden by default), execution readiness gate (approved_execution_blocked is
the ceiling; execution_allowed stays false), durable audit contract, and the
seven-state machine. No runtime code, no migration, no execution.

P20-B (merged at a62bcbe): implemented a NON-EXECUTING, IN-MEMORY durable
approval read/write skeleton under /api/v1/platform/p20/durable-approvals behind
the reused P10 identity-only guard. Open / list / read / checker-decision;
maker-checker dual-control with quorum (write / write_request floor 2, read
floor 1); reject final; approve accumulates to approved_execution_blocked;
digest-only idempotency (raw key never stored); full reason/metadata redaction;
durable append-only in-memory audit. 71 backend tests. P20-B-R1 bound maker and
checker to the authenticated identity-only super_admin actor (payload spoof
denied; no system/operator fallback; system path never counts toward quorum).
No migration, no database, no execution, no tenant mutation, no auth/RBAC
rewrite.

P20-C (this branch): added a read-only durable approval console on top of the
P20-B read path. Opens durable approval requests, lists the ephemeral queue,
reads a record, and records per-checker approve/reject DECISIONS only. Operator
visualization: maker-checker separation (the maker is offered NO decision
control on an approval they opened; a distinct identity-only super_admin checker
is required), quorum progress (approve checkers over quorum_required),
action-class badge, append-only checker decision log, and the
approved-vs-executed badge distinction (quorum_met is red, never green). 17 new
frontend tests. No backend code, no migration, no execution, no tenant mutation,
no auth/RBAC/session rewrite, no package/lockfile change.

P20-D (this file): the P20 master closeout. Cumulative capability, safety
statement, full verification evidence, GitNexus summary, forbidden audit, open
risks / non-goals, and the final verdict.

## 3. P20-C capability statement (the console)

After P20-C the platform operator (identity-only super_admin) can, from a
read-only console at /platform/durable-approvals:

- Open (record) a durable approval request at pending_review, with the maker
  bound to the authenticated actor and shown read-only as "maker (you)". The
  form carries action_id / action_type / tenant_id / reason / idempotency_key /
  expires_at / durable_retain_until / confirm (no raw value is echoed back).
- List the ephemeral durable approval queue with state / source / action-class /
  quorum-progress badges and the persistent executed=false /
  execution_allowed=false readout per item.
- Read a single record's read-only context: state, maker / maker_at, the
  checker decision log, quorum_required / quorum_met, action_class,
  validation_status, source_status, the one-way idempotency_key_digest and
  request_digest (truncated to 12 chars, never a raw key), execution_gate,
  execution_allowed, redaction_applied, retention_class, expires_at /
  durable_retain_until, audit_event_id, storage, executed.
- Record a checker approve / reject decision with an explicit confirmation
  token, but ONLY when the current operator is NOT the maker and has not yet
  decided on that approval (maker-checker separation; one decision per checker).
  An approve against an unknown / unavailable source or a non-valid
  validation_status is blocked at the UI (and denied by the backend); reject
  stays available.

The console never offers an execute / run / apply / dispatch / trigger control.
A quorum-met approval is shown as approved_execution_blocked (red, "execution
blocked" / "quorum met"), never as executed, applied, running, or done.

## 4. Safety statement (cumulative P20)

- Approval is not execution and durability is not execution. A quorum-met
  durable approval reaches approved_execution_blocked and leaves
  execution_allowed == false, execution_gate == "blocked", executed == false,
  and the P18 executed flag unchanged. No controlled action is ever run.
- No real controlled action execution exists anywhere in P20 (P20-A contract,
  P20-B non-executing skeleton, P20-C read-only console).
- No tenant mutation: no P17 registry, lifecycle, flag, provisioning, backup, or
  tenant business data is read or written from the P20 surface. The P20-B
  services source references no orders / payments / inventory / invoice /
  ledger symbols (enforced by a backend test); the P20-C console references no
  product-business symbols either.
- No migration: no migrations or alembic changes; no persistent store. The
  durable store is in-memory only (storage == "memory"); records, checker
  decisions, and audit events are ephemeral and do not survive a process
  restart.
- No auth/RBAC rewrite: P20-B reuses the P10 identity-only guard unchanged;
  P20-C reuses the existing PlatformRoute guard and the isIdentityPlatformOperator
  helper unchanged. The console route is a single additive element under the
  existing PlatformRoute; the nav link is a single additive entry inside the
  existing identity-gated sidebar block. No new auth transport.
- Raw idempotency key is digest-only: only the SHA-256 digest is stored; the raw
  key is hashed at the boundary and discarded. The console never displays a raw
  key -- only the one-way idempotency_key_digest and request_digest, truncated.
- Reason / comment / metadata redaction: the P18 allowlist redaction is reused;
  redaction_applied == true on every record and audit event; the console shows
  the already-redacted reason only.
- Maker-checker + quorum enforced on the authenticated actor (P20-B-R1): the
  maker and each checker bind to the authenticated identity-only super_admin
  actor; payload maker / approver_id spoof is denied; there is no system /
  operator fallback; the system path can never count toward quorum. The console
  mirrors this: the maker is offered NO decision control, and a checker who
  already decided sees no further control.
- Identity-only super_admin runtime: tenant-contextual super_admin, tenant
  admin, tenant-scoped tokens, and non-super_admin roles (support_operator /
  engineering_operator) are denied at the boundary by the identity-only guard
  and see no controls in the console (hidden, not merely disabled). The
  contract's support_operator / engineering_operator read-only GET allowance is
  NOT implemented in P20 and is deferred to a P20-RBAC slice.

## 5. Verification (this branch vs origin/platform-dev = a62bcbe; all pass)

- Frontend targeted tests (P20-C console, new): 17 passed.
- Frontend full suite: 29 files, 268 tests passed (the 17 new P20-C tests plus
  251 pre-existing; P19 approval console, sidebar, and guards regression intact).
- Backend P20 tests: 71 passed (unchanged; P20-C adds no backend code).
- Backend regression P19 + P18 + P18-D + P10: 244 passed; combined P20 +
  P19 + P18 + P18-D + P10: 315 passed, 0 failed. Pre-existing warnings
  (datetime.utcnow deprecation in core/security.py; pytest env_files config
  option) are non-blocking and were not introduced by P20-C.
- TypeScript (tsc --noEmit): 0 errors in any P20-C/D changed file. 41
  pre-existing errors remain in untouched files (P19 PlatformApprovalsPage.tsx,
  the P13 ops pages, and several pre-existing test files); P20-C/D adds zero
  new type errors.
- git diff --check origin/platform-dev..HEAD: clean (exit 0, no whitespace
  errors).
- Changed files: 6 (3 new frontend files + 3 modified frontend files).
- Non-ASCII scan of all changed files: 0 hits (pure ASCII; no section sign,
  box-drawing, em dash, middot, smart quotes, or arrows).
- detect-secrets (detect-secrets-hook against the repo's configured baseline) on
  all changed files: PASS, exit 0, no new secrets. The baseline file was not
  modified (working-tree status clean for it).
- npx gitnexus analyze (final branch tip): 7,645 nodes / 23,552 edges / 490
  clusters / 300 flows; graph intact (300 execution flows stable across
  re-indexes; node / edge counts grew slightly over the base because the new
  console symbols and the ledger markdown headings are parsed as graph nodes).
  For reference the base platform-dev index was 7,611 nodes / 23,493 edges.
- GitNexus detect_changes compare origin/platform-dev..HEAD: risk_level medium,
  changed_count 42, affected_count 1, changed_files 8 (6 frontend code files +
  this ledger and the docs/ai read-order edit). The changed_count above the 29
  code symbols is markdown-heading nodes from the two docs (no symbols, no
  flows). See section 6.
- Route / API impact: ZERO backend route changes. P20-C is frontend-only; the
  console calls the existing, already-merged P20-B durable-approval endpoints.
  The app.py wiring is unchanged on this branch.
- Working tree clean after each commit.

## 6. GitNexus detect_changes (medium -> a new frontend-only process)

detect_changes reports risk_level medium because the change introduces a new
frontend-only process (the console's own page -> submitDecision -> unwrap flow,
process_type intra_community, 3 steps). This is expected for a new console page
and is contained and acceptable because:

- The single affected process is "PlatformDurableApprovalsPage -> Unwrap"
  (proc_232_platformdurableappro), entirely within the new P20-C console source
  (PlatformDurableApprovalsPage.tsx). It is NOT a product business process.
- All 29 changed code symbols are under frontend/ (Sidebar.tsx, AppRouter.tsx,
  platformApi.ts, PlatformDurableApprovalsPage.tsx, platformDurableApprovals.ts).
  The remaining changed_count entries are markdown-heading nodes from this
  ledger and the docs/ai read-order edit (docs only, no symbols, no flows). Zero
  backend symbols changed.
- Product-business token scan across the affected process name and the changed
  symbols: 0 hits (no order / payment / invoice / inventory / ledger / customer
  / retail / wholesale / sku / finance / shipment / fulfillment / reservation /
  return / receivable / credit / collection / product).

No product business process is affected. The stop condition (GitNexus shows
product business processes affected) is NOT triggered. (Contrast: a backend
skeleton like P20-B reports CRITICAL because new routes are wired into
configure_app; a frontend console like P20-C reports medium because it adds a
new UI process. Neither touches product business.)

## 7. Forbidden audit summary

P20-C/D touches none of the following (all verified by the changed-path audit):

- No product-dev-recovered path.
- No tenant business page or code (no orders, payments, invoices, inventory,
  customers).
- No migration or alembic change.
- No payment or billing change.
- No package.json, pnpm-lock, package-lock, or yarn.lock change.
- No auth / RBAC / session rewrite (the PlatformRoute guard and
  isIdentityPlatformOperator helper are reused unchanged).
- No .github / CI change.
- No .claude change committed by this branch.
- No change to the configured secret baseline.
- No real execution path (the console has no execute / run / apply / dispatch /
  trigger control; approved_execution_blocked is the ceiling and
  execution_allowed stays false).
- No tenant mutation path.
- No P17 registry / lifecycle mutation, no P18 executed-flag mutation.

Two changed files are outside the strict P20-C "allowed to modify" positive list
but are NOT forbidden paths and are necessary additive wiring, each reusing the
existing identity-only guard unchanged: frontend/src/router/AppRouter.tsx (one
additive route element under the existing PlatformRoute; P19 precedent) and
frontend/src/components/layout/Sidebar.tsx (one additive nav link inside the
existing identity-gated platform-nav block). Neither is an auth/RBAC/session
change. The four remaining files (types, service, page, test) are squarely
within frontend/src/types, frontend/src/services, frontend/src/pages/platform,
and frontend platform tests.

## 8. Open risks / non-goals (carry-forward)

The following are intentionally not done in P20 and are NOT P20 blockers. They
are deferred to later phases under their own entry gates, contract-first:

- Real durable backend / migration (DEFAULT DENIED; requires separate explicit
  CTO approval in a contract revision). P20-B is in-memory only and P20-C wires
  to that read path.
- Real execution engine (P20 never executes; execution is a separately approved
  future execution contract that must run through the P16 governed harness).
- Real rollback / restore (backup.restore_test_request stays request-only).
- Notification / escalation implementation (named as a future contract; no
  outbound channels, templates, or recipients in P20).
- Role-granular runtime delegation (support_operator / engineering_operator
  read-only GET within scope) -- explicitly deferred to a P20-RBAC slice. The
  P20 runtime is identity-only super_admin; those roles are denied at the
  boundary and see no console controls today.
- Unimplemented durable state transitions (expired / cancelled / superseded /
  failed_validation) and TTL / supersession / retention purge / export -- the
  schema carries the full enum; transitions remain explicitly rejected in P20-B
  and the console offers no control for them.
- Emergency override (forbidden by default; any override requires a separately
  approved future contract).

Risk posture: the P20 change is runtime-additive (a new frontend console + the
already-merged non-executing backend skeleton), non-executing, and mitigated
(identity-only guard reused; maker-checker + quorum enforced on the
authenticated actor; digest-only idempotency; full redaction; approved stays
execution_blocked; defense in depth -- the backend P20-B service and P10 guard
are authoritative and deny maker self-approval, identity spoof, and
tenant-contextual access regardless of the console).

## 9. Final verdict

P20_DURABLE_APPROVAL_GOVERNANCE_READY (read-only frontend console + master
closeout, isolated branch, not merged to platform-dev; pending CTO review).

P20-C adds a read-only durable approval governance console (17 frontend tests,
maker-checker + quorum operator visualization, no execute control, identity-only
super_admin, no raw key / reason / metadata leak) wired to the P20-B non-executing
backend read path and the existing PlatformRoute guard. P20-D is this master
ledger and closeout. Across P20-A / P20-B / P20-C there is no real execution, no
migration, no real durable backend, no tenant mutation, no auth/RBAC/session
rewrite, no product business edit, no product-dev-recovered change, and no
change to the configured secret baseline. P21 is not started. Approval is not
execution, and durability is not execution.

## 10. Explicit non-goal statements (for the CTO review)

- No real execution: P20-C has no execute / run / apply / dispatch / trigger
  control; a quorum-met approval resolves to approved_execution_blocked and
  executed stays false.
- No migration: no migrations or alembic changes; the durable store is
  in-memory only.
- No tenant mutation: no P17 registry / lifecycle / flag / provisioning / backup
  / tenant business data is read or written.
- No auth/RBAC rewrite: the PlatformRoute guard and isIdentityPlatformOperator
  helper are reused unchanged; the route and nav link are additive.
- No product business edits: zero product-business symbols changed or affected
  (GitNexus 0 product tokens; 0 backend symbols).
- No product-dev-recovered: not touched.
- P21 not started.

---

## Merge Readiness Gate Evidence (P20-C/D -> platform-dev)

Gate executed: 2026-06-26. Branch tip at gate time: source 6d037f3; merge dc9b481.

### SHAs
- Target branch: platform-dev.
- Target before SHA: a62bcbe (origin/platform-dev == local platform-dev, confirmed after `git fetch --all --prune`).
- Source branch: codex/platform-p20cd-durable-approval-frontend-closeout-2026-06-25.
- Source commit SHA: 6d037f3 (origin == local, confirmed).
- Merge commit SHA: dc9b481 (--no-ff; parents a62bcbe + 6d037f3; subject "merge: P20-C/D durable approval frontend console and closeout").
- Target after SHA (local platform-dev): dc9b481 (a62bcbe -> dc9b481). origin/platform-dev: still a62bcbe (push pending, see Push status).

### Modified files (8, exactly the expected P20-C/D scope)
- A ai-ledger/platform/2026-06-25_p20cd_durable_approval_frontend_closeout.md
- M docs/ai/README.md
- M frontend/src/components/layout/Sidebar.tsx
- A frontend/src/pages/platform/PlatformDurableApprovalsPage.tsx
- A frontend/src/pages/platform/__tests__/PlatformDurableApprovalsPage.test.tsx
- M frontend/src/router/AppRouter.tsx
- M frontend/src/services/platformApi.ts
- A frontend/src/types/platformDurableApprovals.ts
8 files changed, 1926 insertions(+), 1 deletion(-). diff --name-status matches expected scope exactly; no extra files.

### Test results (run at source tip 6d037f3 and re-run at merge commit dc9b481; identical)
- Frontend targeted (PlatformDurableApprovalsPage.test.tsx): 17/17 passed.
- Frontend full suite: 268/268 passed (29 files).
- Backend P20 (test_platform_p20_durable_approval_governance.py): 71/71 passed.
- Backend regression P10 + P18 + P18-D + P19: 244/244 passed.
- Total failures: 0. vitest warnings (React Router v7 future flags; act() state-update notices) are pre-existing and benign. pytest warnings (Unknown config option: env_files; datetime.utcnow DeprecationWarning in core/security.py) are pre-existing and benign.

### GitNexus
- `npx gitnexus analyze` at merge commit dc9b481: 7,636 nodes | 23,541 edges | 492 clusters | 300 flows. (At source tip 6d037f3: 7,633 nodes | 23,541 edges | 489 clusters | 300 flows. Flow count is the stable metric at 300; node/edge/cluster counts are within the documented non-deterministic fluctuation.)
- `npx gitnexus status` at dc9b481: indexed commit dc9b481 == current commit dc9b481; Status: up-to-date.
- detect_changes compare origin/platform-dev..source (6d037f3): risk_level = medium, changed_count = 31, affected_count = 1, changed_files = 8. The single affected process is "PlatformDurableApprovalsPage -> Unwrap" (process_type intra_community, 3 steps) -- the new console's own render -> submitDecision -> unwrap flow. Product-business token scan over affected_processes[].name: 0 hits (the only "ledger" token is the ai-ledger doc filePath, not a process). No product business process affected.

### Forbidden path audit
- Path-based audit on the 8 changed files (pre-merge and post-merge HEAD~1..HEAD): PASS. No backend/, migrations/, alembic/, package/lockfile, auth/RBAC/session, product-dev-recovered, tenant business, payment/billing, or configured secret-detection baseline path.
- Content-level keyword scan of the diff: every hit (alembic, migrations, product-dev-recovered, rbac, permission, session, payment, billing) is a documentation safety statement asserting "no ... change" / "deferred to a P20-RBAC slice", or empty mock data (permissions: []). No actual backend logic, migration script, or auth/RBAC/session rewrite.

### Non-ASCII scan
- All 8 changed files: valid UTF-8, 0 non-ASCII / control characters. No mojibake.

### Whitespace
- `git diff --check origin/platform-dev..source`: clean (exit 0).
- `git diff --check HEAD~1..HEAD` (post-merge): clean (exit 0).

### Risk classification
- LOW. Frontend-only, read-only console plus governance closeout docs. No backend, no migration, no execution surface, no auth/RBAC/session change, no product business. detect_changes medium is the expected baseline for any new frontend console page (a new intra_community UI process appears) and is NOT a product-business signal.

### Explicit safety statement
- No execution. No migration. No real durable backend. No tenant mutation. No auth/RBAC/session rewrite. No product-dev-recovered. P21 not started.

### Push status
- PUSHED. Operator authorized the push on 2026-06-26. Merge commit dc9b481 pushed to origin/platform-dev (a62bcbe -> dc9b481); origin/platform-dev == local platform-dev == dc9b481. This evidence section was committed and pushed as the trailing docs commit on platform-dev. Post-merge gates (diff --check, forbidden-path audit, frontend 17/17 + 268/268, backend 71/71 + 244/244, gitnexus status up-to-date) all green before push.
