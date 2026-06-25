# P20-A Durable Approval Governance Contract

Date: 2026-06-25
Phase: P20-A (contract-only design for durable approval governance; the persistent approval
store, dual-control policy, execution readiness gate, durable audit, and state machine that
bound all later P20 implementation).
Branch: codex/platform-p20a-durable-approval-governance-contract-2026-06-25
Base: origin/platform-dev = e831da0 (P19-D approval workflow closeout,
P19_APPROVAL_WORKFLOW_READY)
Scope: docs / ledger only. No new feature, no backend runtime code, no frontend runtime
code, no migration, no alembic change, no package or lockfile change, no test code.

This phase defines the durable approval governance contract only. It does not implement,
execute, persist (beyond defining the contract), or merge anything into platform-dev. It is
an isolated, docs-only branch. P20-B is not started.

## 1. Phase inventory

P20-A - durable approval governance contract (docs-only)
- Source branch: codex/platform-p20a-durable-approval-governance-contract-2026-06-25
- Base: origin/platform-dev = e831da0
- Report path: ai-ledger/platform/2026-06-25_p20a_durable_approval_governance_contract.md
  (this file)
- Scope: docs-only contract for the durable governance layer on top of P19 (persistent
  approval store, dual-control policy, execution readiness gate, durable audit, state
  machine)
- Risk: LOW (docs-only, no runtime code, no migration)
- Status: contract on isolated branch; not merged to platform-dev

## 2. Capability statement

P20-A defines (contract only, no runtime code) the durable approval governance layer that
P19 deliberately left open. After P20-A is accepted, a future P20-B may implement -- under
its own entry gate -- a non-executing durable approval read/write skeleton or a storage
abstraction skeleton. P20-A fixes the boundary for:

- Persistent approval store contract: durable ApprovalRecord and ApprovalDecision shapes;
  digest-only idempotency (SHA-256 of the key only, raw key never stored / logged /
  returned); full reason / comment / metadata redaction via the P10 allowlist; retention /
  purge / export boundaries (purge is automated retention expiry only, never an operator
  action; export is redacted and audited); unknown / degraded / read-only fallback (unknown
  is never healthy; source_unknown write -> failed_validation; read-only denies writes but
  still audits them).
- Dual-control policy contract: identity-only super_admin as the only checker role;
  support_operator and engineering_operator may open within their P18 scope only; maker /
  checker separation (the maker can never be a checker; self-approval forbidden, tightening
  P19); quorum (write and write_request floor of two distinct checkers excluding the maker;
  read floor of one); tenant admin, tenant-contextual super_admin, and tenant-scoped token
  denied on every operation; emergency override explicitly forbidden by default.
- Execution readiness gate contract: approval is not execution and durability is not
  execution; execution_allowed defaults to and stays false; execution_gate stays blocked;
  approved_execution_blocked is the ceiling; every destructive or tenant-mutating action
  stops (tenant.pause / resume, incident.flag_set / clear, lifecycle.transition,
  backup.restore_test_request); backup.restore_test_request is request-only and requires a
  known backup source.
- Audit contract: every state change emits exactly one durable, append-only audit event
  with the required fields (event_id, approval_id, action_id, actor_id, actor_role,
  identity_context, decision, previous_status, next_status, reason_redacted, created_at,
  request_digest, redaction_applied); no raw secret, DSN, host:port, token, password,
  operator secret, or tenant payload is ever recorded.
- State machine: pending_review, approved_execution_blocked, rejected, expired, cancelled,
  superseded, failed_validation; terminals and transitions explicit; reject is final;
  superseded and failed_validation are terminal.

## 3. Safety statement

- Approval is not execution, and durability is not execution. A quorum-met durable approval
  reaches approved_execution_blocked and leaves execution_allowed == false,
  execution_gate == blocked, and the P18 executed flag == false. No controlled action is
  ever run.
- No real controlled action execution exists anywhere in P20-A (contract only).
- No tenant mutation: no P17 registry, lifecycle, flag, provisioning, backup, or tenant
  business data is read or written from this surface (and the contract forbids it for all
  future P20 phases).
- No migration: no migrations or alembic changes; no persistent store introduced; the
  durable store is a contract, not an implementation, in P20-A.
- No auth / RBAC rewrite: P20-A reuses the P10 identity-only guard conceptually; no new
  auth transport is defined or implemented.
- Raw idempotency key is digest-only by contract: only the SHA-256 digest is stored; the
  raw key is hashed at the boundary and discarded.
- Reason / comment / metadata redaction is total by contract: the P10 allowlist applies
  before storage, response, or audit; redaction_applied == true is required everywhere.
- Emergency override is forbidden by default; no role, quorum, or urgency bypasses
  maker-checker separation or sets execution_allowed == true.
- Tenant-contextual identities are denied on every durable governance operation; the
  surface is identity-only and cross-tenant.

## 4. Verification (docs-only branch, all must pass)

Verified on this branch versus origin/platform-dev = e831da0:

- git diff --check origin/platform-dev..HEAD : clean (no whitespace errors).
- Changed files exactly equal three docs / ledger files:
  - docs/ai/PLATFORM_PRODUCT_P20_DURABLE_APPROVAL_GOVERNANCE_CONTRACT.md (new)
  - docs/ai/README.md (Platform Product Track read order updated; P20 entry + paragraph)
  - ai-ledger/platform/2026-06-25_p20a_durable_approval_governance_contract.md (new, this
    file)
- Non-ASCII scan of the three files: 0 hits (pure ASCII; no section sign, box-drawing,
  em dash, middot, smart quotes, or arrows).
- detect-secrets (detect-secrets-hook against the configured secret baseline) on the three
  files: PASS, exit 0, no new secrets. The baseline file was not modified (working-tree
  status clean for it).
- Forbidden path audit (changed paths under backend/, frontend/, migrations/, alembic/,
  package or lock files, auth / RBAC / session, payment / billing, tenant business code,
  product-dev-recovered/, .github/, .claude/, or the secret baseline): 0 hits.
- npx gitnexus analyze : graph intact; no execution flow affected by a docs-only change.
- GitNexus detect_changes compare origin/platform-dev..HEAD : LOW risk, docs-only, 0
  affected processes (only markdown docs and a ledger are added; no code symbols and no
  execution-flow impact).
- Working tree clean after commit.

## 5. GitNexus summary

- P20-A is docs-only: a contract markdown doc, a README read-order edit, and a ledger. No
  runtime symbols, no execution-flow impact.
- detect_changes compare origin/platform-dev..HEAD : LOW / docs-only / 0 affected processes.
  Verified on this branch. The change adds documentation only; no backend, frontend,
  migration, package, auth, payment, tenant, or product path is touched.

## 6. Forbidden audit summary

P20-A touches none of the following (all verified by the changed-path audit):

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
- No tenant mutation path.

## 7. Open risks / non-goals

The following are intentionally not done in P20-A and are NOT P20-A blockers. They are
deferred to P20-B (and later) under their own entry gates, contract-first:

- Durable approval backend read / write skeleton (P20-B candidate; non-executing; in-memory
  or existing-safe storage only unless separately gated).
- Storage abstraction skeleton (P20-B candidate; interface / adapter, no real durable
  backend).
- Real durable backend / migration (DEFAULT DENIED in P20-B; requires separate explicit CTO
  approval in a contract revision).
- Real execution engine (P20 never executes; execution is a separately approved future
  execution contract that must run through the P16 governed harness).
- Real rollback / restore (backup.restore_test_request stays request-only).
- Notification / escalation implementation (named as a future contract; no outbound
  channels, templates, or recipients in P20-A).
- Emergency override (forbidden by default; any override requires a separately approved
  future contract).

## 8. P20-B entry gate

P20-B may implement ONLY a backend durable approval read / write skeleton OR a storage
abstraction skeleton. It must not execute any action, must not mutate tenant state, must
not implement a real rollback / restore, must not implement notification, and must not
rewrite auth / RBAC / session. Any migration, alembic change, new persistent table, or real
durable backend is DEFAULT DENIED and requires separate explicit CTO approval in a contract
revision. P20-B must begin from this contract and may not change the lifecycle states,
actors, permission matrix, dual-control rules, data contracts, required fields, safety
rules, execution gate, or audit fields without a new contract revision accepted by the CTO.

## 9. Final verdict

P20-A_CONTRACT_READY (docs-only, isolated branch, not merged to platform-dev).

P20-A defines the durable approval governance contract only. There is no runtime code, no
migration, no execution, no tenant mutation, no auth / RBAC rewrite, and no change to the
configured secret baseline. P20-B is not started. Approval is not execution, and durability
is not execution.
