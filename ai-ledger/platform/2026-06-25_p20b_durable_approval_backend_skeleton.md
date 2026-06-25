# P20-B Durable Approval Backend Skeleton

Date: 2026-06-25
Phase: P20-B (non-executing, in-memory backend skeleton implementing the P20-A
durable approval governance contract; maker-checker dual-control with quorum).
Branch: codex/platform-p20b-durable-approval-backend-skeleton-2026-06-25
Base: origin/platform-dev = 670e9a3 (merge: P20-A durable approval governance
contract)
Scope: backend skeleton + tests + ledger only. No frontend, no migration, no
alembic change, no database, no real execution, no tenant mutation, no
auth/RBAC rewrite, no package or lockfile change.

This phase implements a non-executing durable approval read/write skeleton under
/api/v1/platform/p20/durable-approvals. It does not execute any controlled
action, does not mutate tenant data, and does not merge anything into
platform-dev. It is an isolated branch. P20-C is not started.

## 1. Phase inventory

P20-B - durable approval backend skeleton (non-executing, in-memory)
- Source branch: codex/platform-p20b-durable-approval-backend-skeleton-2026-06-25
- Base: origin/platform-dev = 670e9a3
- Code commit: a5522f3 (feat(platform): P20-B durable approval governance
  backend skeleton) -- 6 files (4 new p20 modules + app.py additive include +
  test file).
- Ledger commit: this file (docs/ledger only).
- Report path: ai-ledger/platform/2026-06-25_p20b_durable_approval_backend_skeleton.md
  (this file)
- Risk: detect_changes CRITICAL (platform-runtime additive) / phase risk
  contained to the P20 platform surface; no product business process affected.
- Status: on isolated branch; not merged to platform-dev.

## 2. Capability statement

P20-B implements (non-executing backend skeleton) the durable approval
governance layer defined by the P20-A contract. After P20-B the platform can:

- Open (record) a durable approval request at pending_review, with the P18
  action class resolved and the action-class quorum floor set (write /
  write_request = 2; read = 1). Carries request_digest and the SHA-256
  idempotency_key_digest (raw key never stored).
- List durable approvals with status / action_type / tenant_id filters, and read
  a single record by approval_id.
- Record per-checker approve / reject decisions under maker-checker
  dual-control: the maker can never be a checker (self-approval forbidden);
  each checker records at most one decision (duplicate idempotent, flip is a
  conflict); reject is final/terminal; approve accumulates until the quorum
  floor of distinct checkers is met, then resolves to approved_execution_blocked.
- Emit a durable, append-only in-memory audit event for every open / decision /
  quorum_met / reject / denial, carrying the P20-A required fields (event_id,
  approval_id, action_id, actor_id, actor_role, identity_context, decision,
  previous_status, next_status, reason_redacted, created_at, request_digest,
  redaction_applied).

The durable store is in-memory only (storage = "memory"); record / decision /
audit are modeled separately. There is no database, no migration, no execution
path, and no tenant mutation.

## 3. Endpoints

All behind the identity-only P10 platform guard
(require_platform_operator, reused unchanged):

- POST /api/v1/platform/p20/durable-approvals -- open a durable approval.
- GET  /api/v1/platform/p20/durable-approvals -- list (status / action_type /
  tenant_id filters; limit / offset).
- GET  /api/v1/platform/p20/durable-approvals/{approval_id} -- read one.
- POST /api/v1/platform/p20/durable-approvals/{approval_id}/decisions -- record
  one checker's approve / reject.

No PUT / PATCH / DELETE verbs are registered (no mutation-by-effect verbs).

## 4. Safety statement

- Approval is not execution and durability is not execution. A quorum-met
  approval reaches approved_execution_blocked and leaves execution_allowed ==
  false, execution_gate == "blocked", executed == false, and the P18 executed
  flag unchanged. No controlled action is ever run.
- No real controlled action execution exists anywhere in P20-B.
- No tenant mutation: no P17 registry, lifecycle, flag, provisioning, backup, or
  tenant business data is read or written from this surface. The services source
  references no orders / payments / inventory / invoice / ledger symbols
  (enforced by a test).
- No migration: no migrations or alembic changes; no persistent store introduced.
- In-memory store only: durable records, checker decisions, and audit events are
  ephemeral and do not survive a process restart.
- No auth/RBAC rewrite: the existing P10 identity-only guard is reused
  unchanged; no new auth transport.
- Raw idempotency key is digest-only: only the SHA-256 digest of the create
  idempotency key is stored (idempotency_key_digest); the raw key is never
  stored, echoed, or audited.
- Reason / comment / metadata redaction: the P18 allowlist redaction is reused;
  redaction_applied == true on every record and audit event.
- Maker-checker enforced at the service layer (payload identities); reject is
  final; quorum required for write / write_request.
- Tenant-contextual super_admin, tenant admin, tenant-scoped tokens, and
  non-super_admin roles (support_operator / engineering_operator) are denied at
  the boundary by the identity-only guard (strictly stronger than the contract's
  read-only allowance; finer role delegation deferred).

## 5. State machine

P20-B implements only pending_review -> approved_execution_blocked | rejected.
The full seven-state enum (pending_review, approved_execution_blocked,
rejected, expired, cancelled, superseded, failed_validation) is defined in the
schema; transitions to expired / cancelled / superseded / failed_validation are
NOT implemented and are explicitly rejected by the service layer with a shaped
denial. reject is final/terminal.

## 6. Tests summary

Run via the shared repo venv with PYTHONPATH=backend (conftest forces the test
SECRET_KEY).

- P20-B backend (new): 63 passed (>= 45 required). Coverage: create / list
  (status / action_type / tenant_id filters) / read / decision; action class +
  quorum floor; identity-only guard; tenant-contextual / tenant-admin /
  support_operator / engineering_operator denied; maker cannot self-approve
  (approve or reject); quorum not met -> pending_review (quorum_pending);
  quorum met -> approved_execution_blocked; read-action quorum one;
  write_request quorum two (backup.restore_test_request); reject is terminal;
  rejected cannot be approved after; duplicate idempotent / flip conflict;
  approve never executes; execution_allowed / executed false on every response;
  execution_gate blocked; digest-only idempotency (raw never stored / echoed);
  reason / metadata / decision redaction; unknown / not-found P18 source
  handling; available never fabricated; audit required fields + quorum_met /
  rejected / denial events; no-migration / no-mutation / route-registration
  scope.
- Regression P19 + P18 + P18-D + P10: 244 passed, 0 failed.

Pre-existing warnings (datetime.utcnow deprecation in core/security.py; pytest
env_files config option) are non-blocking and were not introduced by P20-B.

## 7. Verification (docs + code branch, all must pass)

Verified on this branch versus origin/platform-dev = 670e9a3:

- git diff --check origin/platform-dev..HEAD : clean (exit 0, no whitespace
  errors).
- Changed files: 7 (6 code/test/app + this ledger). Forbidden-path audit: 0
  hits (no frontend/, migrations/, alembic/, package or lock files,
  product-dev-recovered/, .github/, .claude/, or the configured secret
  baseline).
- Non-ASCII scan of all changed source files: 0 hits (pure ASCII).
- detect-secrets (detect-secrets-hook against the configured secret baseline)
  on all changed files: PASS, exit 0, no new secrets. The baseline file was not
  modified.
- npx gitnexus analyze : 7,593 nodes / 23,373 edges / 488 clusters / 300 flows;
  indexed at the branch HEAD; graph intact.
- GitNexus detect_changes compare origin/platform-dev..HEAD : risk_level
  CRITICAL, changed_count 75, affected_count 18, changed_files 7. See section 8.
- Route / API impact review: 3 new routes (POST/GET durable-approvals; GET
  durable-approvals/{id}; POST durable-approvals/{id}/decisions) under
  /api/v1/platform/p20, additive, platform-only; app.py change is a single
  additive include_router in configure_app.
- Working tree clean after commit.

## 8. GitNexus detect_changes (CRITICAL -> additive platform-only)

detect_changes reports risk_level CRITICAL because the change is
platform-runtime additive: new P20 routes wired into configure_app plus new
platform symbols. This is expected for a backend skeleton (P20-B gate #7). The
CRITICAL is contained and acceptable because:

- All 18 affected processes are within the P20 platform surface. They are
  require_platform_operator_with_p20_audit and the create / list / read /
  submit_decision durable-approval routes, flowing only to platform
  infrastructure (PlatformAuditLog, _http_exc, Commit) and P20 schema types
  (DurableApprovalRecord, CheckerDecisionSummary, DurableApprovalQueue).
- Product-business token scan across the 18 affected process names: 0 hits (no
  order / payment / invoice / inventory / ledger / customer / retail /
  wholesale / sku / finance / shipment / fulfillment / reservation / return /
  receivable / credit / collection / product).
- Changed-symbol scope audit: every changed symbol is under platform/p20/, the
  app.py additive include_router, or the P20 test file. No symbol outside the
  P20 platform surface changed.

No product business process is affected. The stop condition (GitNexus shows
product business processes affected) is NOT triggered.

## 9. Open risks / non-goals

The following are intentionally not done in P20-B and are NOT P20-B blockers.
They are deferred to P20-C (and later) under their own entry gates:

- Durable approval frontend console (P20-C candidate; not started).
- Real durable backend / migration (DEFAULT DENIED; requires separate explicit
  CTO approval in a contract revision). P20-B is in-memory only.
- Role-granular runtime delegation (support_operator / engineering_operator
  read-only within scope) -- deferred; the identity-only guard denies these
  roles at the boundary today, which is stricter than read-only.
- Unimplemented state transitions (expired / cancelled / superseded /
  failed_validation) and TTL / supersession / retention purge / export -- the
  schema carries the full enum; transitions are explicitly rejected in P20-B.
- Real execution engine (P20 never executes; execution is a separately approved
  future execution contract via the P16 governed harness).
- Real rollback / restore (backup.restore_test_request stays request-only).
- Notification / escalation implementation (named as a future contract).

## 10. P20-C entry gate

P20-C may implement ONLY the durable approval frontend console (read-only
request context, maker / checker columns, quorum progress, approve / reject with
explicit confirmation, no execute button, approved-vs-executed badge
distinction), wired to the P20-B backend read path and the existing PlatformRoute
guard / isIdentityPlatformOperator identity-only check. P20-C must not execute,
must not mutate tenant state, must not add a migration or real durable backend,
and must not rewrite auth / RBAC / session. Any migration or real durable
backend remains DEFAULT DENIED (separate CTO approval). P20-C must not change
the P20-B lifecycle states, dual-control rules, data contracts, required fields,
safety rules, execution gate, or audit fields without a new contract revision
accepted by the CTO.

## 11. Final verdict

P20-B_SKELETON_READY (non-executing backend skeleton, isolated branch, not
merged to platform-dev).

P20-B implements a non-executing, in-memory durable approval backend skeleton
with maker-checker dual-control and quorum, 63 passing tests, and 244 passing
regression tests. There is no frontend, no migration, no real execution, no
tenant mutation, and no auth/RBAC rewrite, and no change to the configured
secret baseline. P20-C is not started. Approval is not execution, and durability
is not execution.
