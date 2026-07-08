# P21-A Durable Approval Store Contract

Date: 2026-06-26
Phase: P21-A (contract-only design for the durable approval store; the persisted tables /
logical storage records, restart-safe consistency, digest-only idempotency,
redaction-before-persistence, durable append-only audit, retention / purge / export,
migration boundary, and API compatibility that bound all later P21 implementation).
Branch: codex/platform-p21a-durable-approval-store-contract-2026-06-26
Base: origin/platform-dev = 82ee1c1 (P20 durable approval governance closeout: P20-A
contract, P20-B in-memory non-executing backend skeleton, P20-C read-only frontend
console, and P20-D master closeout all merged; P20_DURABLE_APPROVAL_GOVERNANCE_READY).
Scope: docs / ledger only. No new feature, no backend runtime code, no frontend runtime
code, no migration, no alembic change, no package or lockfile change, no test code.

This phase defines the durable approval store contract only. It does not implement,
execute, persist (beyond defining the contract), migrate, switch runtime storage, or
merge anything into platform-dev. It is an isolated, docs-only branch. P21-B is not
started.

## 1. Phase inventory

P21-A - durable approval store contract (docs-only)
- Source branch: codex/platform-p21a-durable-approval-store-contract-2026-06-26
- Base: origin/platform-dev = 82ee1c1
- Report path: ai-ledger/platform/2026-06-26_p21a_durable_approval_store_contract.md
  (this file)
- Scope: docs-only contract for the durable storage substrate on top of P20 (persisted
  tables / logical storage records, restart-safe consistency, digest-only idempotency,
  redaction-before-persistence, durable append-only audit, retention / purge / export,
  migration boundary, API compatibility, future AI Operator Copilot boundary)
- Risk: LOW (docs-only, no runtime code, no migration, no storage switch)
- Status: contract on isolated branch; not merged to platform-dev

## 2. Capability statement

P21-A defines (contract only, no runtime code) the durable approval store that P20
deliberately left open: P20-B is an in-memory / existing-safe, non-executing backend
skeleton with no migration and no database, so a process restart loses every pending
review, partial quorum, and in-flight decision. After P21-A is accepted, a future P21-B
may define -- under its own entry gate -- the schema / migration plan and tests only;
P21-C is the earliest phase that may implement the migration, and only after explicit
CTO approval. P21-A fixes the boundary for:

- Durable storage model contract: five logical tables / records
  (durable_approval_requests, durable_approval_decisions,
  durable_approval_audit_events, durable_approval_idempotency_keys,
  durable_approval_retention_jobs) with required fields, nullable rules, enum values,
  indexes, uniqueness constraints, and foreign-key-like relationships; restart-safe
  consistency rules (every state, decision, audit event, and idempotency row survives a
  restart; every transition commits atomically with a store_version bump; unknown is
  never healthy).
- Security and redaction contract: the raw idempotency key is never stored (SHA-256
  digest only); reason / comment / metadata are redacted via the P10 allowlist before
  persistence; no raw secret, DSN, host, port, host:port, token, password, cookie, auth
  header, or tenant business payload is ever persisted; tenant_id is a scoped identifier
  only and never a foreign key into product business tables; audit events store no raw
  request or response body.
- Maker-checker / quorum consistency contract: maker and checker are both bound to an
  authenticated identity-only super_admin actor; the maker cannot approve or reject its
  own request; checkers are distinct identities only (unique approval_id + checker_id);
  quorum count is transactionally consistent (write and write_request floor of two
  distinct checkers excluding the maker; read floor of one); duplicate decisions are
  idempotent only on payload-digest match; conflicting decisions are rejected and
  serialized by the store_version optimistic lock (no split-brain quorum).
- State machine contract: the seven P20 states (pending_review,
  approved_execution_blocked, rejected, expired, cancelled, superseded,
  failed_validation) with restart-safe persistence, explicit allowed and forbidden
  transitions, and the rule that no transition executes the underlying P18 action.
- Retention / purge / export contract: retention_class (standard | long | legal_hold);
  durable_retain_until; legal_hold suspends automated purge; purge is automated retention
  expiry via a SYSTEM actor only (never an operator); whole-record purge; export-safe and
  never-exported field lists; every purge emits an approval_purged audit event.
- Migration boundary: P21-A creates nothing now; a future P21-C migration may create the
  durable tables only if additive, reversible (rollback plan), dry-run / schema-
  inspection gated, platform / public schema only, no existing product or tenant schema
  change, and CTO-approved.
- API compatibility contract: the future durable backend preserves P20 API response
  shapes for POST create, GET list, GET by id, and POST decision unless a new versioned
  contract is approved; execution_allowed stays false; the existing P20-C frontend needs
  no semantic change.
- Test plan: schema contract, migration, restart persistence, idempotency digest,
  redaction persistence, maker-checker transaction, quorum race, retention / purge /
  export, no-execution, no-tenant-mutation, and GitNexus scope tests.
- Future AI Operator Copilot boundary: the AI may read platform state via approved tools
  and propose controlled actions, but may create draft action requests only after
  explicit operator confirmation, can never execute directly, every AI action is audited,
  AI tool calls are linked to approval records, and real execution stays separately
  gated.

## 3. Safety statement

- Approval is not execution, and durability is not execution. A quorum-met durable
  approval reaches approved_execution_blocked and leaves execution_allowed == false,
  execution_gate == blocked, and the P18 executed flag == false. No controlled action is
  ever run. A durable, restart-safe, retention-aware store is still not an execution
  path.
- No real controlled action execution exists anywhere in P21-A (contract only).
- No tenant mutation: no P17 registry, lifecycle, flag, provisioning, backup, or tenant
  business data is read or written from this surface (and the contract forbids it for all
  future P21 phases; tenant_id is a scoped identifier only, never a business payload and
  never joinable to business tables).
- No migration and no storage switch: no migrations, alembic changes, tables, or columns
  are introduced in P21-A or P21-B; the durable store is a contract, not an
  implementation, in P21-A. Runtime storage is not switched away from the P20-B
  in-memory / existing-safe skeleton.
- No auth / RBAC rewrite: P21-A reuses the P10 identity-only guard conceptually; no new
  auth transport is defined or implemented.
- Raw idempotency key is digest-only by contract: only the SHA-256 digest is stored; the
  raw key is hashed at the boundary and discarded, and never appears in any persisted
  column, response, queue item, audit field, backup, or export.
- Redaction-before-persistence is total by contract: the P10 allowlist applies before
  storage, response, or audit; redaction_applied == true is required everywhere.
- Audit events store no raw request or response body: only redacted reason, digests, and
  status fields are persisted; the audit log is append-only.
- Maker-checker separation and quorum are enforced in the same transaction as the
  decision; a self-decision is never persisted; conflicting decisions are rejected.
- No AI agent execution: P21-A names a future AI Operator Copilot boundary only; it
  grants no AI execution power and adds no AI-specific runtime code.

## 4. Verification (docs-only branch, all must pass)

Verified on this branch versus origin/platform-dev = 82ee1c1:

- git diff --check origin/platform-dev..HEAD : clean (no whitespace errors).
- Commit: branch tip (short SHA recorded in the session report; kept out of this file so the ledger stays non-self-referential; no 40-char SHA in this file).
- Changed files exactly equal three docs / ledger files:
  - docs/ai/PLATFORM_PRODUCT_P21_DURABLE_APPROVAL_STORE_CONTRACT.md (new)
  - docs/ai/README.md (Platform Product Track read order updated; P21 entry + paragraph)
  - ai-ledger/platform/2026-06-26_p21a_durable_approval_store_contract.md (new, this
    file)
- Non-ASCII scan of the three files: 0 hits (pure ASCII; no section sign, box-drawing,
  em dash, middot, smart quotes, or arrows).
- detect-secrets (detect-secrets-hook against the configured secret baseline) on the
  three files: PASS, exit 0, no new secrets. The configured baseline file was not
  modified (working-tree status clean for it). No 40-char SHAs are present in any new
  file.
- Forbidden path audit (changed paths under backend/, frontend/, migrations/, alembic/,
  package or lock files, auth / RBAC / session, payment / billing, tenant business code,
  product-dev-recovered/, .github/, .claude/, or the configured secret baseline): 0 hits.
- npx gitnexus analyze : graph intact; no execution flow affected by a docs-only change.
- GitNexus detect_changes compare origin/platform-dev..HEAD : LOW risk, docs-only, 0 affected processes (summary: changed_count 32, affected_count 0, changed_files 3, risk_level low; all 32 changed symbols are File / Section markdown nodes in the 3 docs / ledger files; affected_processes []).
- Working tree clean after commit.

## 5. GitNexus summary

- P21-A is docs-only: a contract markdown doc, a README read-order edit, and a ledger. No
  runtime symbols, no execution-flow impact.
- detect_changes compare origin/platform-dev..HEAD : LOW / docs-only / 0 affected processes (changed_count 32, affected_count 0, changed_files 3; affected_processes []). Verified
  on this branch. The change adds documentation only; no backend, frontend, migration,
  package, auth, payment, tenant, or product path is touched.

## 6. Forbidden audit summary

P21-A touches none of the following (all verified by the changed-path audit):

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
- No real execution path (contract only; approved_execution_blocked is the ceiling and
  execution_allowed stays false by contract).
- No tenant mutation path (tenant_id is a scoped identifier only).

## 7. Open risks / non-goals

The following are intentionally not done in P21-A and are NOT P21-A blockers. They are
deferred to P21-B (and later) under their own entry gates, contract-first:

- Schema / migration plan and tests (P21-B only; no production migration, no storage
  switch).
- Real durable backend / migration (P21-C at the earliest; requires separate explicit
  CTO approval and all migration gates in the contract).
- Runtime storage cutover from the P20-B in-memory / existing-safe store to a durable
  backend (a further separately approved step, not before P21-C).
- Real execution engine (P21 never executes; execution is a separately approved future
  execution contract that must run through the P16 governed harness).
- Real rollback / restore (backup.restore_test_request stays request-only).
- Notification / escalation implementation (named as a future contract; no outbound
  channels, templates, or recipients in P21-A).
- AI Operator Copilot implementation (named as a future boundary only; no AI execution
  power, no AI-specific runtime code in P21-A).
- Emergency override (forbidden by default; any override requires a separately approved
  future contract).

## 8. P21-B entry gate

P21-B may define ONLY a schema / migration plan for the durable tables (DDL sketch,
indexes, constraints, rollback plan, dry-run procedure) and tests for that plan (schema
contract tests, migration / reversibility tests, dry-run / schema-inspection tests), run
only against ephemeral test databases. P21-B must not run any production migration or
alembic change, must not switch runtime storage, must not execute any action, must not
mutate tenant state, must not implement a real rollback / restore, must not implement
notification, must not implement an AI copilot, and must not rewrite auth / RBAC /
session. P21-C is the earliest phase that may implement the migration, and only after
explicit CTO approval and only under all migration gates. P21-B must begin from this
contract and may not change the tables, fields, enums, constraints, state machine,
security rules, retention rules, API compatibility, or audit fields without a new
contract revision accepted by the CTO.

## 9. Final verdict

P21-A_CONTRACT_READY (docs-only, isolated branch, not merged to platform-dev).

P21-A defines the durable approval store contract only. There is no runtime code, no
migration, no execution, no tenant mutation, no auth / RBAC rewrite, no frontend, no
backend, no AI agent execution, no notification implementation, and no change to the
configured secret baseline. P21-B is not started. Approval is not execution, and
durability is not execution.

## 10. Merge evidence (P21-A.1 merge readiness gate, 2026-06-26)

P21-A.1 merged the P21-A contract-only branch into platform-dev after all readiness
gates passed. (Evidence appended at merge time; the original sections 1-9 above describe
the contract branch as it stood before the merge.)

- Gate: P21-A.1 merge readiness gate (contract-only, docs-only).
- Date: 2026-06-26.
- Source branch: codex/platform-p21a-durable-approval-store-contract-2026-06-26.
- Source commit: 843aa70 (short SHA; full SHA not pinned here).
- Merge target before: origin/platform-dev = 82ee1c1 (local platform-dev == origin ==
  82ee1c1, confirmed before merge).
- Merge commit (--no-ff, NOT a squash, NOT a fast-forward): 5442853 (short SHA); parents
  82ee1c1 (platform-dev before) + 843aa70 (source); subject "merge: P21-A durable
  approval store contract".
- Tip after this evidence commit: branch tip (this evidence commit; short SHA recorded in
  the session report; kept out of this file so the ledger stays non-self-referential).
- Pre-merge gates (all PASS): git fetch --all --prune; source HEAD == 843aa70 and
  origin/platform-dev == 82ee1c1; worktree clean; changed files == exactly the 3 P21-A
  docs / ledger files; git diff --check origin/platform-dev..source clean; non-ASCII scan
  0 hits; detect-secrets against the configured baseline PASS (exit 0); forbidden path
  audit 0 hits; npx gitnexus analyze up-to-date; GitNexus detect_changes source vs
  origin/platform-dev = LOW / docs-only / 0 affected processes (changed_count 32,
  affected_count 0, changed_files 3; affected_processes []).
- Post-merge gates on the merge commit (all PASS): git diff --check HEAD~1..HEAD clean;
  forbidden path audit on the merge commit 0 hits (only the 3 docs / ledger files);
  non-ASCII scan 0 hits; detect-secrets PASS (exit 0).
- Pushed to: origin/platform-dev (single push carrying the merge commit plus this
  evidence commit).
- Risk: LOW (docs-only merge; no runtime code, no migration, no execution, no tenant
  mutation, no auth / RBAC rewrite, no frontend, no backend).

Status after P21-A.1: P21-A is MERGED into platform-dev. There is no runtime code, no
migration, no execution, no tenant mutation, no auth / RBAC rewrite, no frontend, no
backend, and no AI agent execution. P21-B is not started. Approval is not execution, and
durability is not execution.
