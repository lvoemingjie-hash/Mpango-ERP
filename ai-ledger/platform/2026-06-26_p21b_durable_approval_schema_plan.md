# P21-B Durable Approval Store Schema Plan + Test Plan

Date: 2026-06-26
Phase: P21-B (planning-only schema / migration plan, storage-adapter interface contract,
constraint and transaction plan, and test plan that convert the accepted P21-A durable
approval store contract into an implementation-ready artifact set for P21-C / P21-D).
Branch: codex/platform-p21b-durable-approval-schema-plan-2026-06-26
Base: origin/platform-dev = df92bb0 (P21-A durable approval store contract merged;
P21-A_CONTRACT_MERGED).
Scope: docs / ledger only. No migration files, no tables, no generated DB files, no new
feature, no backend runtime code, no frontend runtime code, no alembic change, no storage
switch, no package or lockfile change, no test code.

This phase converts the P21-A contract into an implementation-ready plan only. It does
not create migration files, does not create tables, does not implement, execute, persist
(beyond the plan), switch runtime storage, or merge anything into platform-dev. It is an
isolated, docs-only branch. P21-C is not started.

## 1. Phase inventory

P21-B - durable approval store schema plan + test plan (docs-only)
- Source branch: codex/platform-p21b-durable-approval-schema-plan-2026-06-26
- Base: origin/platform-dev = df92bb0
- Report path: ai-ledger/platform/2026-06-26_p21b_durable_approval_schema_plan.md
  (this file)
- Scope: docs-only implementation-ready plan on top of the merged P21-A contract (exact
  schema / columns / types / nullability / defaults / indexes / uniqueness / FK-like
  relationships for the five durable tables; enum plan; constraint plan; transaction plan
  with race handling; storage-adapter interface contract as planning-only pseudocode;
  P21-C migration plan; test plan G1-G14; acceptance criteria; counterexamples; P21-C
  entry gate; future AI Operator Copilot trace; full P21-A traceability)
- Risk: LOW (docs-only, no runtime code, no migration files, no tables, no storage switch)
- Status: plan on isolated branch; not merged to platform-dev

## 2. Capability statement

P21-B defines (planning only, no runtime code, no migration files, no tables) the
implementation-ready artifact set that a future CTO-approved P21-C may migrate and P21-D
may wire. P21-B fixes the boundary for:

- Schema plan: the five durable tables (durable_approval_requests, _decisions,
  _audit_events, _idempotency_keys, _retention_jobs) with exact columns, types,
  nullability, defaults, indexes, uniqueness constraints, and FK-like relationships,
  including the task-required columns (approval_id, action_id, tenant_id, action_type,
  action_class, state, maker_actor_id, maker_at, quorum_required, quorum_met,
  execution_allowed, execution_gate, executed, request_digest, idempotency_key_digest,
  reason_redacted, metadata_redacted, source_status, validation_status, retention_class,
  expires_at, durable_retain_until, superseded_by, previous_state, created_at,
  updated_at). Two refinements over P21-A's logical model are explicit: maker_actor_id
  (P21-A's `maker`) and executed (a local always-false column materializing the P18 flag).
- Enum plan: closed value sets for approval states, action classes, execution gate,
  source status, validation status, retention class, decision type, audit event type, and
  audit result.
- Constraint plan: C-R1..C-R5 (redaction / security), C-Q1..C-Q7 (maker-checker /
  quorum), C-T1..C-T6 (state machine), C-L1..C-L2 (approved-state / legal_hold), and
  C-X1 (no-execution invariant).
- Transaction plan: create_request, submit_decision (which folds quorum_transition and
  reject_transition), expire, cancel, supersede, and purge/export job boundaries, with
  race handling via store_version optimistic locking, SELECT FOR UPDATE, unique-constraint
  backstops, and idempotency dedup (no split-brain quorum).
- Storage-adapter interface contract: create_request, list_requests, get_request,
  submit_decision, append_audit_event, find_by_idempotency_digest, expire_due_requests,
  purge_eligible_records, export_record -- planning-only pseudocode with return shapes,
  StoreError codes, idempotency behavior, and the no-execution invariant. No backend
  files.
- Migration plan for P21-C: additive-only, platform-schema-only naming / rollback /
  dry-run / pre+post validation; P21-B creates no migration files.
- Test plan: G1-G14 with expected counts (schema, migration dry-run, adapter unit,
  restart persistence, idempotency digest, redaction persistence, maker-checker, quorum
  race, state transition, retention/purge/export, no-execution, no-tenant-mutation, API
  compatibility, GitNexus scope); >= 101 planned tests (floors).
- Traceability: every major P21-A requirement tagged (P21A-S/R/Q/T/L/M/A) and mapped to a
  planned schema artifact and test artifact.

## 3. Safety statement

- Approval is not execution, and durability is not execution. The plan preserves
  execution_allowed == false, execution_gate == blocked, and executed == false on every
  record, decision, audit event, and job. No controlled action is ever run.
- No real controlled action execution exists anywhere in P21-B (planning only).
- No migration and no tables: P21-B creates no migration files, no tables, no alembic
  changes, and no generated DB files; runtime storage is not switched (P20 stays
  in-memory / existing-safe).
- No tenant mutation: tenant_id is a scoped identifier only, never a business payload and
  never an FK into a product business table; the plan forbids it for all future P21
  phases.
- No auth / RBAC rewrite: P21-B reuses the P10 identity-only guard conceptually; no new
  auth transport is defined or implemented.
- Raw idempotency key is digest-only by plan: only SHA-256 digests are stored; the raw key
  is hashed at the boundary and discarded.
- Redaction-before-persistence is total by plan: reason_redacted / metadata_redacted
  columns and redaction_applied == true on every record and audit event.
- Maker-checker separation and quorum are transactional by plan; a self-decision is never
  persisted; conflicting decisions are rejected; the only approved state is
  approved_execution_blocked.
- No AI agent execution: P21-B names a future AI Operator Copilot trace only; it grants no
  AI execution power and adds no AI-specific runtime or schema artifact.

## 4. Verification (docs-only branch, all must pass)

Verified on this branch versus origin/platform-dev = df92bb0:

- git diff --check origin/platform-dev..HEAD : clean (no whitespace errors).
- Commit: branch tip (short SHA recorded in the session report; kept out of this file so
  the ledger stays non-self-referential; no 40-char SHA in this file).
- Changed files exactly equal three docs / ledger files:
  - docs/ai/PLATFORM_PRODUCT_P21_DURABLE_APPROVAL_SCHEMA_PLAN.md (new)
  - docs/ai/README.md (Platform Product Track read order updated; P21-B entry + paragraph)
  - ai-ledger/platform/2026-06-26_p21b_durable_approval_schema_plan.md (new, this file)
- Non-ASCII scan of the three files: 0 hits (pure ASCII; no section sign, box-drawing,
  em dash, middot, smart quotes, or arrows).
- detect-secrets (detect-secrets-hook against the configured secret baseline) on the
  three files: PASS, exit 0, no new secrets. The configured baseline file was not
  modified. No 40-char SHAs are present in any new file.
- Forbidden path audit (changed paths under backend/, frontend/, migrations/, alembic/,
  generated DB files, package or lock files, auth / RBAC / session, payment / billing,
  tenant business code, product-dev-recovered/, .github/, .claude/, or the configured
  secret baseline): 0 hits.
- npx gitnexus analyze : graph intact; no execution flow affected by a docs-only change.
- GitNexus detect_changes compare origin/platform-dev..HEAD : LOW risk, docs-only, 0 affected processes (summary: changed_count 32, affected_count 0, changed_files 3, risk_level low; all 32 changed symbols are File / Section markdown nodes in the 3 docs / ledger files; affected_processes []).
- Working tree clean after commit.

## 5. GitNexus summary

- P21-B is docs-only: a schema-plan markdown doc, a README read-order edit, and a ledger.
  No runtime symbols, no execution-flow impact.
- detect_changes compare origin/platform-dev..HEAD : LOW / docs-only / 0 affected processes (changed_count 32, affected_count 0, changed_files 3; affected_processes []). Verified
  on this branch. The change adds documentation only; no backend, frontend, migration,
  package, auth, payment, tenant, or product path is touched.

## 6. Forbidden audit summary

P21-B touches none of the following (all verified by the changed-path audit):

- No backend / runtime code path.
- No frontend code path.
- No migration files, alembic change, or generated DB files.
- No payment or billing change.
- No package.json, pnpm-lock, package-lock, or yarn.lock change.
- No product-dev-recovered path.
- No auth / RBAC / session rewrite.
- No .github / CI change.
- No .claude change.
- No change to the configured secret baseline.
- No real execution path (planning only; approved_execution_blocked is the ceiling and
  execution_allowed / executed stay false by plan).
- No tenant mutation path (tenant_id is a scoped identifier only).

## 7. Open risks / non-goals

The following are intentionally not done in P21-B and are NOT P21-B blockers. They are
deferred to P21-C / P21-D under their own entry gates:

- Migration implementation (P21-C; additive, platform-schema-only, CTO-gated; creates the
  five tables; no storage switch).
- Runtime storage adapter wiring / cutover from the P20-B in-memory / existing-safe store
  to a durable backend (P21-D; separately gated).
- Real execution engine (P21 never executes; execution is a separately approved future
  execution contract that must run through the P16 governed harness).
- Real rollback / restore (backup.restore_test_request stays request-only).
- Notification / escalation implementation (named as a future contract; no outbound
  channels, templates, or recipients in P21-B).
- AI Operator Copilot implementation (named as a future trace only; no AI execution power
  in P21-B).
- Emergency override (forbidden by default; any override requires a separately approved
  future contract).

## 8. P21-C entry gate

P21-C may implement ONLY the migration, and only after explicit CTO approval. It must
remain additive and public / platform-schema-only, must perform no tenant schema
migration, must touch no product business paths, must not switch runtime P20 storage
(separately gated; that is P21-D), and must satisfy every gate in the plan (rollback,
dry-run, pre / post validation; pass G1 and G2 against a real ephemeral-test schema).
P21-D is the earliest possible runtime adapter wiring phase. P21-C must begin from this
plan and the P21-A contract and may not change the tables, columns, types, enums,
constraints, state machine, security rules, retention rules, API compatibility, or audit
fields without a new plan / contract revision accepted by the CTO.

## 9. Final verdict

P21-B_PLAN_READY (docs-only, isolated branch, not merged to platform-dev).

P21-B defines the implementation-ready schema / migration / adapter / test plan only.
There is no runtime code, no migration file, no table, no execution, no tenant mutation,
no auth / RBAC rewrite, no frontend, no backend, no AI agent execution, no notification
implementation, and no change to the configured secret baseline. P21-C is not started.
Approval is not execution, and durability is not execution.

## 10. Evidence completion (P21-B evidence request, 2026-06-26)

This section consolidates the required evidence for the P21-B evidence-completion
request. It records facts already established in sections 1-9 and adds the commit, push,
and analyze specifics so the ledger is self-contained.

- Branch: codex/platform-p21b-durable-approval-schema-plan-2026-06-26 (pushed).
- Base: origin/platform-dev = df92bb0 (confirmed before work).
- Commit (substantive P21-B plan, pushed): 863cd4f (short SHA; full SHA not pinned
  here). The evidence-completion tip (this commit) is recorded in the session report; the
  ledger stays non-self-referential.
- Exact modified files (exactly three):
  - docs/ai/PLATFORM_PRODUCT_P21_DURABLE_APPROVAL_SCHEMA_PLAN.md
  - docs/ai/README.md
  - ai-ledger/platform/2026-06-26_p21b_durable_approval_schema_plan.md (this file)
- Ledger path: ai-ledger/platform/2026-06-26_p21b_durable_approval_schema_plan.md.
- git diff --check origin/platform-dev..HEAD : clean (exit 0).
- Non-ASCII scan on the three files: 0 hits.
- detect-secrets (detect-secrets-hook against the configured baseline): PASS, exit 0, no
  new secrets; configured baseline unchanged.
- Forbidden path audit: 0 hits (only the three allowed docs / ledger files; no backend,
  frontend, migrations, alembic, generated DB files, package / lockfile, auth / RBAC /
  session, payment / billing, tenant business code, product-dev-recovered, .github,
  .claude, or the configured baseline).
- npx gitnexus analyze : success; indexed at the P21-B plan commit; 7,677 nodes /
  23,578 edges / 496 clusters / 300 flows; status up-to-date.
- GitNexus detect_changes compare vs origin/platform-dev : LOW / docs-only / 0 affected
  processes (changed_count 32, affected_count 0, changed_files 3; affected_processes [];
  all changed symbols are File / Section markdown nodes in the three docs / ledger files).
- Working tree: clean after commit.
- Push status: isolated branch pushed via the BR:BR refspec;
  origin/codex/platform-p21b-durable-approval-schema-plan-2026-06-26 created; platform-dev
  untouched at df92bb0 (not merged).
- Risk: LOW (docs-only).
- Explicit statement: docs-only, no runtime code, no migration, no execution, no tenant
  mutation, no auth / RBAC rewrite, no frontend, no backend, no P21-C.

Plan document contents (confirmed present in
docs/ai/PLATFORM_PRODUCT_P21_DURABLE_APPROVAL_SCHEMA_PLAN.md): schema plan (section 3),
enum plan (section 4), constraint plan (section 5), transaction plan (section 6), storage
adapter interface contract (section 7), P21-C migration plan (section 8), P21-C / P21-D
test plan (section 9), acceptance criteria (section 10), counterexamples (section 11),
P21-C entry gate (section 12), future AI Operator Copilot trace (section 13).
