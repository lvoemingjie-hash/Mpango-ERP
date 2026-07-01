# P22-A Controlled Execution v0 Contract

Date: 2026-07-01
Phase: P22-A (contract-only design for controlled execution v0; the v0 execution allowlist
and exclusions, execution preconditions, dry-run model, execution request model, execution
result state machine, audit contract, idempotency, safety rules, operator separation
policy, API shape proposal, test plan, acceptance criteria, and counterexamples that bound
all later P22 implementation).
Branch: codex/platform-p22a-controlled-execution-v0-contract-2026-07-01
Base: origin/platform-dev = 41c003e (P21 durable approval store closeout: P21-A contract,
P21-B schema / migration plan, P21-C0/C1 migration readiness and public durable tables,
P21-D runtime adapter implementation and storage cutover, and P21-E runtime closeout all
merged; P21_DURABLE_APPROVAL_STORE_READY).
Scope: docs / ledger only. No new feature, no backend runtime code, no frontend runtime
code, no migration, no alembic change, no package or lockfile change, no test code.

This phase defines the controlled execution v0 contract only. It does not implement,
execute, dispatch, queue, schedule, migrate, or merge anything into platform-dev. It is an
isolated, docs-only branch. P22-B is not started.

## 1. Phase inventory

P22-A - controlled execution v0 contract (docs-only)
- Source branch: codex/platform-p22a-controlled-execution-v0-contract-2026-07-01
- Base: origin/platform-dev = 41c003e
- Report path: ai-ledger/platform/2026-07-01_p22a_controlled_execution_v0_contract.md
  (this file)
- Scope: docs-only contract for controlled execution v0 on top of P18 through P21 (v0
  allowlist and exclusions, execution preconditions, dry-run model, execution request
  model, execution result state machine, audit contract, idempotency, safety rules,
  operator separation policy, API shape proposal, future AI Operator Copilot boundary)
- Risk: LOW (docs-only, no runtime code, no migration, no execution, no storage switch)
- Status: contract on isolated branch; not merged to platform-dev

## 2. Capability statement

P22-A defines (contract only, no runtime code) the controlled execution v0 layer that P18
through P21 deliberately left open: P18 created action requests but did not execute them,
P19 approved / rejected but every approval resolved to execution_blocked, P20 added
maker-checker / quorum and capped approvals at approved_execution_blocked, and P21 made
approvals durable. P22 defines the bounded bridge from an approved durable approval to a
real platform action -- but P22-A defines the contract only; it performs no execution.
After P22-A is accepted, a future P22-B may implement -- under its own entry gate -- a
NON-EXECUTING execution skeleton (catalog read, dry-run validator, execution-request
recording, execution-result read) only; real execution of any v0 action is reserved for a
separately approved phase and must run through the P16 governed harness. P22-A fixes the
boundary for:

- v0 execution allowlist: exactly seven actions (support_mode.on, support_mode.off,
  incident.flag_set, incident.flag_clear, provisioning.recheck, backup.check,
  backup.restore_test_request) -- each read-only, reversible via a paired action, or a
  non-destructive restore test request; none mutates tenant business data. The v0 executor
  is always an identity-only super_admin.
- Explicit exclusion list (never executable in v0): tenant.pause, tenant.resume,
  lifecycle.transition, real restore, schema migration, data deletion, payment / billing,
  tenant business records, and arbitrary shell / SQL / script execution.
- Execution precondition contract: identity-only super_admin executor; matching durable
  approval id; approval at approved_execution_blocked with quorum_met; source available
  (degraded allowed for reads only); action in allowlist; idempotency key; passed dry-run
  (dry_run_ref); execution acknowledgement; no expired / superseded / cancelled / rejected
  approval; and maker / checker / executor separation.
- Dry-run model: a no-mutation validation gate returning executable (true | false), verdict
  (passed | blocked), block_reasons, expected audit shape (field names only), source
  status, and reversibility. Mandatory before any execution request.
- Execution request model: execution_request_id, durable_approval_id, action_type,
  tenant_id (scoped id only), requested_state, reason_redacted, idempotency_key_digest
  (digest only), payload_digest, actor_id, actor_role, identity_context (identity_only),
  execution_mode (sync | queued), dry_run_ref, execution_ack, correlation_id,
  metadata_redacted, result_state, redaction_applied, timestamps.
- Execution result model: a separate execution-record state machine (dry_run_passed,
  blocked, execution_queued, executing, executed, execution_failed,
  compensation_required, compensation_completed, cancelled) -- NOT a new approval state.
  Sync or queued, both audited identically; reversible writes have paired compensation.
- Audit contract: closed event set (execution_dry_run_requested, _passed, _blocked,
  execution_requested, _started, _succeeded, _failed, execution_compensation_recorded,
  execution_denied); never-logged list (raw secrets / DSNs / host:port / tokens / cookies /
  auth headers / raw idempotency key / raw request or response body / shell / SQL / tenant
  payload); append-only; one event per transition.
- Idempotency: digest-only; replay returns the original result with no new success event;
  same key + different payload is a conflict; failed execution retries require a new key
  and fresh dry-run; no duplicate audit success.
- Safety rules: allowlist only, dry-run first, fail closed, no silent fallback, no
  arbitrary tool / shell / SQL, no tenant business mutation, no product code path, no
  payment / billing, no raw secrets, unknown is never healthy, approval is not execution,
  durability is not execution, every execution audited, operator separation holds,
  reversible where possible.
- Operator separation policy: maker / checker / executor are distinct; no self-execution,
  no checker-execution; executor is always identity-only super_admin; three-distinct for
  write / write-request; read floor of one checker distinct from the maker. Fixed in
  P22-A, not deferred.
- API shape proposal (planning only): GET catalog, POST dry-run, POST requests, GET
  requests, GET requests/{id}; all behind the P10 identity-only super_admin guard; none
  implemented in P22-A.
- Test plan: 76 planned tests across contract / types, dry-run, preconditions, allowlist /
  exclusions, idempotency, audit, no-execution for blocked paths, no tenant business
  mutation, no raw leak, source unavailable, approval expired / rejected, and duplicate /
  retry.
- Future AI Operator Copilot boundary: the AI may read the catalog and execution state and
  propose dry-runs / execution requests, but may create a draft execution request only
  after explicit operator confirmation, can never execute directly, every AI action is
  audited, AI tool calls are linked to approval / execution records, and real execution
  stays separately gated.

## 3. Safety statement

- Approval is not execution, and durability is not execution. A durable, restart-safe,
  quorum-met approval at approved_execution_blocked is a precondition for v0 execution; it
  is not execution itself. P22-A defines the execution contract; it performs no execution.
- No real controlled action execution exists anywhere in P22-A (contract only). The v0
  allowlist defines what MIGHT eventually execute under a separately approved phase; P22-A
  executes nothing.
- No tenant business mutation: no order, payment, invoice, customer, inventory, or ledger
  record is read or written by any v0 action (contract forbids it for all future P22
  phases; tenant_id is a scoped identifier only, never a business payload and never
  joinable to business tables). v0 actions change platform operational flags (support_mode,
  incident_active) or refresh status only; backup.restore_test_request is test-only against
  an isolated environment.
- No destructive lifecycle execution: tenant.pause, tenant.resume, and lifecycle.transition
  are excluded from v0 and remain at approved_execution_blocked with no execution.
- No migration and no storage switch: no migrations, alembic changes, tables, or columns
  are introduced in P22-A. P22-A changes no P21 table, field, enum, or migration and adds
  no new durable approval state.
- No auth / RBAC rewrite: P22-A reuses the P10 identity-only guard conceptually; no new
  auth transport is defined or implemented.
- Raw idempotency key is digest-only by contract: only the SHA-256 digest is recorded; the
  raw key is hashed at the boundary and discarded, and never appears in any field,
  response, queue item, audit field, backup, or export.
- Redaction-before-record is total by contract: the P10 allowlist applies before any
  record, response, or audit; redaction_applied == true is required everywhere.
- Audit events store no raw request or response body, no shell / SQL, and no tenant
  payload: only redacted reason, digests, and status fields are recorded; the audit log is
  append-only.
- Operator separation is enforced: the executor is always an identity-only super_admin
  distinct from the maker and every checker; self-execution and checker-execution are
  denied.
- No arbitrary shell / SQL / script execution: no general code-execution surface exists or
  is introduced.
- No AI agent execution: P22-A names a future AI Operator Copilot boundary only; it grants
  no AI execution power and adds no AI-specific runtime code.

## 4. Verification (docs-only branch, all must pass)

Verified on this branch versus origin/platform-dev = 41c003e:

- git diff --check origin/platform-dev..HEAD : clean (no whitespace errors).
- Commit: branch tip (short SHA recorded in the session report; kept out of this file so
  the ledger stays non-self-referential; no 40-char SHA in this file).
- Changed files exactly equal three docs / ledger files:
  - docs/ai/PLATFORM_PRODUCT_P22_CONTROLLED_EXECUTION_V0_CONTRACT.md (new)
  - docs/ai/README.md (Platform Product Track read order updated; P22 entry + paragraph)
  - ai-ledger/platform/2026-07-01_p22a_controlled_execution_v0_contract.md (new, this
    file)
- Non-ASCII scan of the three files: 0 hits (pure ASCII; no section sign, box-drawing, em
  dash, middot, smart quotes, or arrows).
- detect-secrets (detect-secrets-hook against the configured secret baseline) on the three
  files: PASS, exit 0, no new secrets. The configured baseline file was not modified
  (working-tree status clean for it). No 40-char SHAs are present in any new file.
- Forbidden path audit (changed paths under backend/, frontend/, migrations/, alembic/,
  package or lock files, auth / RBAC / session, payment / billing, tenant business code,
  product-dev-recovered/, .github/, .claude/, or the configured secret baseline): 0 hits.
- npx gitnexus analyze : graph intact; no execution flow affected by a docs-only change.
- GitNexus detect_changes compare origin/platform-dev..HEAD : LOW risk, docs-only, 0
  affected processes (summary: changed_count 32, affected_count 0, changed_files 3,
  risk_level low; all 32 changed symbols are File / Section markdown nodes in the 3 docs /
  ledger files; affected_processes []).
- Working tree clean after commit.

## 5. GitNexus summary

- P22-A is docs-only: a contract markdown doc, a README read-order edit, and a ledger. No
  runtime symbols, no execution-flow impact.
- detect_changes compare origin/platform-dev..HEAD : LOW / docs-only / 0 affected processes
  (changed_count 32, affected_count 0, changed_files 3; affected_processes []). Verified on
  this branch. The change adds
  documentation only; no backend, frontend, migration, package, auth, payment, tenant, or
  product path is touched.

## 6. Forbidden audit summary

P22-A touches none of the following (all verified by the changed-path audit):

- No backend / runtime code path.
- No frontend code path.
- No migration or alembic change.
- No payment or billing change.
- No package.json, pnpm-lock, package-lock, or yarn.lock change.
- No product-dev-recovered path.
- No auth / RBAC / session rewrite.
- No .github / CI change.
- No .claude change.
- No change to the configured secret baseline.
- No real execution path (contract only; approved_execution_blocked is the ceiling, no new
  approval execution state, and no v0 action is executed in P22-A).
- No tenant mutation path (tenant_id is a scoped identifier only; v0 actions target
  platform operational flags or status refresh only).

## 7. Open risks / non-goals

The following are intentionally not done in P22-A and are NOT P22-A blockers. They are
deferred to P22-B (and later) under their own entry gates, contract-first:

- Non-executing execution skeleton (catalog read, dry-run validator, execution-request
  recording, execution-result read) -- P22-B only; no dispatch, no worker, no queue drain,
  no harness invocation.
- Real execution of any v0 action -- a separately approved future phase; must run through
  the P16 governed harness behind the full precondition set, a passed dry-run, operator
  separation, and total audit.
- Execution queue / worker / scheduler -- a separately approved future phase; not a hidden
  execution path.
- New durable approval execution state (for example execution_ready / approved_for_execution)
  -- a separate future contract change; P22-A adds none and anchors v0 on
  approved_execution_blocked.
- Lifting any v0 exclusion (tenant.pause / resume, lifecycle.transition, real restore,
  schema migration, data deletion, payment / billing, tenant business records, arbitrary
  shell / SQL / script) -- a new contract revision accepted by the CTO and a new phase.
- Frontend execution console / execute control -- separately gated and approved.
- Notification / escalation implementation (named as a future contract; no outbound
  channels, templates, or recipients in P22-A).
- AI Operator Copilot implementation (named as a future boundary only; no AI execution
  power, no AI-specific runtime code in P22-A).
- Emergency override (forbidden by default; any override requires a separately approved
  future contract).

## 8. P22-B entry gate

P22-B may implement ONLY a non-executing execution skeleton: the catalog read, the dry-run
validator (no mutation), execution-request recording (no execution), and execution-result
read, wired to the P21 durable approval store, the P18 request layer, and the P10
identity-only guard. P22-B must not execute any v0 action, dispatch any worker, drain any
queue, or invoke the P16 governed harness unless separately and explicitly approved; must
not add any migration, alembic change, table, or column unless explicitly approved in the
P22-B contract review; must not implement any frontend execution control; must not execute
any excluded action; must not mutate tenant business data or run arbitrary shell / SQL;
must not rewrite auth / RBAC / session; must not add a new approval-level execution state;
and must not touch product-dev-recovered. Real execution of any v0 action is reserved for a
separately approved phase and must run through the P16 governed harness. P22-B must begin
from this contract and may not change the allowlist, the exclusion list, the preconditions,
the dry-run model, the request / result models, the audit fields, the idempotency rules,
the safety rules, the separation policy, or the API shapes without a new contract revision
accepted by the CTO.

## 9. Final verdict

P22-A_CONTRACT_READY (docs-only, isolated branch, not merged to platform-dev).

P22-A defines the controlled execution v0 contract only. There is no runtime code, no
migration, no execution, no tenant mutation, no destructive lifecycle execution, no real
restore, no arbitrary shell / SQL / script, no payment / billing touch, no auth / RBAC
rewrite, no frontend, no backend, no AI agent execution, no notification implementation,
no new durable approval execution state, and no change to the configured secret baseline.
P22-B is not started. Approval is not execution, and durability is not execution.

## 10. R1 contract wording consistency fix (2026-07-01)

CTO review found one blocking wording conflict: section 1.3 was headed "Non-goals
(explicit, for ALL of P22, not only P22-A)" yet included "no runtime code, no backend
handlers, no ... test code" bullets. Read literally across all of P22, that would forbid
the non-executing execution skeleton that section 16 explicitly permits P22-B to
implement. R1 resolves the conflict without changing any contract semantics and without
touching runtime code.

Changes (docs-only):
- Section 1.3 is split into two buckets:
  - 1.3.1 P22-A-only non-goals -- no runtime code, no backend handlers, no frontend UI, no
    tests, no dependency changes, no migrations / alembic changes in P22-A, no real
    execution in P22-A, no execution scheduler / queue drain / automation runner in P22-A,
    and no notification implementation in P22-A. These are forbidden in P22-A but are the
    surface a future P22-B may implement as a non-executing skeleton under its gate.
  - 1.3.2 All-P22 non-goals -- no uncontrolled execution, no tenant business mutation, no
    destructive lifecycle execution, no real restore, no schema migration / data deletion
    as executable v0 actions, no arbitrary shell / SQL / script, no payment / billing, no
    product path, no auth / RBAC rewrite, no AI agent execution, no new durable approval
    execution state, and no merge / push of platform-dev. These bind every P22 phase unless
    a new contract revision is accepted.
- Section 16 (P22-B entry gate) gains an explicit cross-reference: the 1.3.1 P22-A-only
  non-goals are exactly the non-executing skeleton P22-B may begin to implement, the 1.3.2
  all-P22 non-goals bind P22-B equally, and any P22-B migration requires separate explicit
  approval. Section 16's substance (P22-B may implement only a non-executing skeleton) is
  unchanged.

No runtime code, backend, frontend, migration, alembic change, test code, or dependency
change was touched. Scope is still docs / ledger only. The v0 allowlist, exclusion list,
preconditions, dry-run model, request / result models, audit contract, idempotency, safety
rules, separation policy, API shapes, test plan, acceptance criteria, and counterexamples
are unchanged.

R1 re-validation on the same isolated branch (all PASS):
- git diff --check origin/platform-dev..HEAD : clean.
- Non-ASCII scan of the changed docs / ledger files : 0 hits.
- detect-secrets against the configured secret baseline : PASS (exit 0); baseline untouched.
- Forbidden path audit : 0 hits (only docs/ai and ai-ledger/platform markdown changed).
- npx gitnexus analyze : graph intact.
- GitNexus detect_changes compare origin/platform-dev..HEAD : LOW risk, docs-only, 0
  affected processes (re-verified after R1; exact summary counts in the R1 session report).
- platform-dev untouched; R1 is a new commit on top of the pushed P22-A commit on the same
  isolated branch.

P22-A_CONTRACT_READY (docs-only, isolated branch, R1 wording fix applied, not merged to
platform-dev). P22-B is not started.
