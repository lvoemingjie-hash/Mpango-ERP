# P21-D-C Durable Approval Adapter Implementation (no cutover)

Date: 2026-06-30
Phase: P21-D-C (the concrete durable approval store adapter: DB read/write
implementation of the P21-D-B frozen surface against the five merged P21-C1
public durable approval tables, behind an injected async SQLAlchemy session).
P21-D-C implements the adapter but does NOT switch the live P20 runtime store.
The running durable approval store stays the in-memory P20-B skeleton. No P20
route or service is rewired. No migration, no alembic change, no table
alteration. No controlled action is executed. No tenant / P17 registry data is
mutated. No auth / RBAC / session rewrite. No frontend. No product path and no
touch of product-dev-recovered.
Branch: codex/platform-p21dc-durable-approval-adapter-implementation-2026-06-30
Base: origin/platform-dev = 5c4534a (the P21-D-B durable approval adapter
skeleton merge). HEAD pre-commit == base; all P21-D-C work is the uncommitted
change set produced by this run plus the worker commit at the end.

Approval is not execution, and durability is not execution. execution_allowed
stays False, executed stays False, execution_gate stays "blocked", and no P18
controlled action is ever run.

Relationship to the P21-D slice map (design lock section 8):
  - P21-D-a: discovery + design lock (docs only, already merged).
  - P21-D-B: ORM models + NON-EXECUTING adapter skeleton (already merged). Its
    frozen DurableApprovalStore still raises StoreNotImplementedError on every
    method and is left byte-for-byte intact by this slice.
  - P21-D-C (this slice): concrete adapter implementation. Adds
    DurableApprovalStoreAdapter, which realizes create / read / list / decide
    against the durable tables through an injected session. NOT the live store.
  - P21-D-D (storage cutover / feature flag): NOT STARTED. Wiring the adapter
    into the running P20 services / routes is the separately CTO-gated cutover
    and is explicitly forbidden by the P21-D-C directive.

## 1. Phase inventory

- Branch: codex/platform-p21dc-durable-approval-adapter-implementation-2026-06-30
- Base: origin/platform-dev = 5c4534a (confirmed in section 2).
- Scope (four files: two modified platform modules, one new test, this ledger):
  1. backend/api/v1/platform/p21/adapter.py (MODIFIED, additive) -- adds the
     concrete DurableApprovalStoreAdapter class plus pure helpers and module
     constants. The frozen P21-D-B skeleton DurableApprovalStore and every
     pre-existing constant / mapping are unchanged.
  2. backend/api/v1/platform/p21/models.py (MODIFIED, additive) -- supplies the
     closed enum symbols to the ORM _enum helper so rows decode on read. No
     column, type, nullability, server_default, FK, or DDL change; create_type
     stays False; no migration is touched.
  3. backend/tests/test_platform_p21_durable_approval_adapter_implementation.py
     (NEW) -- focused, ephemeral-DB tests for the concrete adapter (23 tests).
  4. ai-ledger/platform/2026-06-30_p21dc_durable_approval_adapter_implementation.md
     (this file).
- Risk: LOW. The change is confined to the new p21 concrete adapter and its
  tests. The adapter is not imported by any P20 route / service / app / models
  registry / alembic path (verified in section 7 and by GitNexus
  affected_count = 0 in section 8). No runtime storage cutover.

## 2. Base and lineage confirmation

Confirmed via read-only git inspection in the worktree:
- origin/platform-dev resolves to 5c4534a (the P21-D-B skeleton merge head).
- The worktree branch was created from origin/platform-dev at 5c4534a.
- The five public durable tables and their fifteen enum types (migration
  020_durable_approval_store) exist on the base; the adapter reads / writes them
  through ORM models and runs the same migration against an ephemeral DB in tests.

## 3. Changed-file audit

git status --short (pre-commit):
  M backend/api/v1/platform/p21/adapter.py
  M backend/api/v1/platform/p21/models.py
  ?? backend/tests/test_platform_p21_durable_approval_adapter_implementation.py
  + ai-ledger/platform/2026-06-30_p21dc_durable_approval_adapter_implementation.md

All four paths fall inside the three allowed roots (backend/api/v1/platform/p21,
backend/tests, ai-ledger/platform). No migration, alembic, env.py, models
registry, p20 routes/services/schemas, auth, RBAC, session, frontend, product, or
product-dev-recovered path is modified. No package, lockfile, dependency, or
configured secrets baseline file is modified.

## 4. What was implemented

### 4.1 Concrete adapter (backend/api/v1/platform/p21/adapter.py)

A new class DurableApprovalStoreAdapter realizes the frozen surface against the
durable tables through an injected async SQLAlchemy session. It mirrors the P20-B
in-memory service logic EXACTLY (P20-B-R1 identity binding, maker-checker,
distinct-checker, reject-final, quorum, source-honesty, redaction, digest-only
idempotency) and persists every operation as a single atomic, restart-safe
transaction.

Methods implemented (IMPLEMENTED_METHODS): create_request, get_request,
list_requests, submit_decision, find_by_idempotency_digest, append_audit_event.
Retention / export (expire_due_requests, purge_eligible_records, export_record)
remain deferred to the separately CTO-gated P21-D-future slice and raise
StoreNotImplementedError.

Key design points (each locked to the P21-D design lock, section 4):
- create (open): one transaction inserts the durable_approval_requests row at
  pending_review (execution_allowed = false, executed = false, execution_gate =
  blocked, redaction_applied = true, storage_class = durable, store_version = 1),
  the approval_opened audit event (sequence_no = 1, audit_result = success), and
  the open idempotency row. Create idempotency: a matching payload_digest returns
  the prior record (duplicate); a mismatch is a decision_conflict. All P20-B
  create-time denials (no authenticated actor, identity spoof, missing reason /
  key / confirm, past expires_at, unresolvable P18 reference) remain denials,
  persist no request row, and emit an approval_denied audit event.
- decide (approve / reject): one transaction enforces maker-checker /
  distinct-checker / reject-final / source-honesty, inserts the
  durable_approval_decisions row (confirm, idempotency_key_digest,
  decision_digest, redacted reason / metadata, linked audit_event_id), inserts
  the decide idempotency row, recomputes quorum_met from the committed distinct
  approve set, and on a state transition bumps store_version by 1 with
  optimistic locking (UPDATE ... WHERE approval_id = ? AND store_version = ?),
  sets previous_state, updates state / decision / last_audit_event_id /
  updated_at, and appends approval_decision_recorded plus approval_quorum_met or
  approval_rejected. The decision audit sequence_no is the prior max + 1 for that
  approval_id. A deny / duplicate / conflict emits approval_denied (or no row for
  a pure idempotent no-op) and commits no decision row.
- read: get_request selects the request + decisions + audit, maps to
  DurableApprovalRecord, and emits approval_read (sequence_no = max + 1). Not
  found -> not_found error.
- list: read-only filtered query over T1 (state / action_type / tenant_id,
  limit / offset), mapped to DurableApprovalQueue. No audit write.

Concurrency / atomicity (design lock 4.3): every create and every decide is a
single transaction; the request mutation, decision row, idempotency row(s), and
audit event(s) commit atomically or roll back together. The decide transition
uses store_version optimistic locking; a stale write (zero rows updated) rolls
back and returns stale_write. The P21-C1 unique constraints
(uq_decisions_approval_checker, uq_decisions_approval_idem, uq_idem_scope) and
IntegrityError handling backstop distinct-checker and per-key decide idempotency.

New-column population (design lock 4.4): store_version = 1 at create, +1 per
transition; sequence_no = per-approval max + 1 inside the transaction;
storage_class = durable; audit_result via derive_audit_result(event_type,
outcome); confirm persisted verbatim; metadata_redacted = P10/P18-redacted
metadata (raw metadata never persisted).

API compatibility (design lock 4.5): the four DurableApproval* response models
are unchanged. The adapter returns DurableApprovalRecord / DurableApprovalQueue
instances with storage = "durable" (additive) and source_status mapped back to
the P20 vocabulary. execution_allowed / executed stay False; execution_gate
stays "blocked". restart_safe rides on the StoreResult wrapper (not a new field
on the response model).

Identity / redaction / digest-only: the adapter consumes the P18 helpers
unchanged (_redact_reason, _sanitize_text, redact_metadata) and binds the maker /
checker to the authenticated identity-only super_admin actor exactly as P20-B.
The raw idempotency key is hashed at the boundary (_digest); only the SHA-256
digest is stored / compared. The create fingerprint is computed from REDACTED
values so the raw reason is never hashed or persisted.

### 4.2 ORM enum decode (backend/api/v1/platform/p21/models.py)

postgresql.ENUM created with create_type = False and no symbols cannot decode
rows on read (LookupError at row-load). The _enum helper now passes the closed
symbol tuple from a new _ENUM_VALUE_MAP so SQLAlchemy can decode. This is a
Python-side decode detail only: create_type stays False, no DDL is ever emitted,
and no column / type / nullability / FK / migration changes. The P21-D-B model
test (which asserts create_type is False and the enum type name) still passes
unchanged (section 8.2).

### 4.3 Tests (backend/tests/test_platform_p21_durable_approval_adapter_implementation.py)

23 focused tests, pytest.mark.integration, self-contained. A module fixture
starts its OWN throwaway postgres:15 container (never the developer mpango_erp
database, never a shared DB), bootstraps the test-only prerequisites (pgcrypto,
widened public.alembic_version, t_dev), runs the already-merged migration
020_durable_approval_store, builds an async engine, and tears the container down
on finish. Each test gets an isolated session and the durable tables are
truncated before every test.

Coverage (the directive's required surface, all green):
- create persists request + audit + idempotency, transactionally consistent;
- create idempotent replay (duplicate) and key-mismatch conflict;
- create denials persist no request row;
- decision persists checker row + audit + decide idempotency;
- duplicate decision (same checker, same decision) is idempotent;
- conflict (same checker flips) is rejected;
- maker-checker (self-decision denied, never persisted);
- reject is final (terminal; later approve denied);
- source-honesty (approve against an unknown source denied; the unknown source
  is stored verbatim, never fabricated available);
- quorum met -> approved_execution_blocked (two distinct approvers), still no
  execution, store_version 1 -> 2;
- no-execution invariant across the full lifecycle (every record AND every
  StoreResult: execution_allowed False, executed False, execution_gate blocked);
- restart-safety: a NEW adapter instance on a NEW session reads the persisted
  state back unchanged; per-approval audit sequence_no is preserved;
- read not-found; list filters + pagination;
- raw idempotency key never persisted (digest-only, scanned across all four
  tables);
- raw secret reason redacted before persistence;
- P20 services remain the in-memory store and P20 routes / api.app do not wire
  the durable adapter (no cutover).

## 5. No-cutover / no-execution design

- DurableApprovalStoreAdapter.is_live_store is False. The module-level
  IS_LIVE_STORE stays False. The frozen P21-D-B DurableApprovalStore stays
  non-executing (StoreNotImplementedError on every method) and unchanged.
- The adapter is NOT imported by api.v1.platform.p20 (services / routes) or by
  api.app (verified by source scan in section 7 and by GitNexus
  affected_count = 0 in section 8). The running store stays in-memory.
- The session is marked system-scope (db.tenant_filter mark_session_as_system)
  because the durable tables are public-schema / system-scope platform data
  (design lock: tenant_id is a scoped identifier only, never a business FK). This
  mirrors how the adapter must run once a future P21-D-D cutover wires it live.
- execution_allowed / executed stay False and execution_gate stays "blocked" on
  every persisted row and every response (verified by test and by source scan:
  no "execution_allowed = True" / "executed = True" / "execution_allowed=True" /
  "executed=True" substring exists in adapter.py).

## 6. Static verification

- The frozen skeleton surface is byte-intact: the P21-D-B skeleton + model unit
  suite (58 tests) passes unchanged (section 8.2), which asserts
  DurableApprovalStore raises StoreNotImplementedError, IS_LIVE_STORE is False,
  ADAPTER_PHASE is "P21-D-B-skeleton", the no-execution invariants, the closed
  mappings, and the no-cutover source scans.
- adapter.py contains no substring that sets execution_allowed or executed True
  (the skeleton test test_store_has_no_execution_unlocking_surface covers this and
  still passes).

## 7. No-cutover / forbidden-path audit (executed, clean)

Verified by source scan (Grep) against the actual files on the base + this slice.
All clean (0 forbidden hits):
- backend/api/v1/platform/p20/services.py: still uses the in-memory globals
  (_STORE, _STORE_BY_CREATE_KEY, _AUDIT_LOG) and storage = "memory"; does not
  import or call the p21 adapter / models.
- backend/api/v1/platform/p20/routes.py: no p21 / DurableApprovalStoreAdapter
  reference.
- backend/api/v1/platform/p20/schemas.py: no p21 import.
- backend/api/app.py: no platform.p21 / DurableApprovalStoreAdapter reference.
- backend/models/__init__.py: no durable / p21 / DurableApproval reference (the
  durable models are NOT registered in the shared metadata).
- backend/alembic/env.py: no p21 / durable reference.
- Alembic chain: 020_durable_approval_store is still the head; nothing descends
  from it. No new migration is added by this slice.
- No backend / frontend / migration / auth / RBAC / session / tenant / payment /
  product / package / lockfile / configured-baseline path is modified. The change
  is confined to the p21 package (adapter.py, models.py), one new test file, and
  this ledger.

The durable adapter DOES import api.v1.platform.p18 (redaction helpers) and
api.v1.platform.p20.schemas (response shapes), one-way. This is by design
(design lock 4.5 / 4.7) and is the opposite direction from the forbidden cutover;
the no-cutover source scans guard p20 -> p21, which remains clean.

## 8. Validation gates (all executed in this run)

8.1 P21-D-C focused adapter implementation tests:
  Command (from backend/, shared venv, PYTHONPATH = worktree backend):
    python -m pytest
      tests/test_platform_p21_durable_approval_adapter_implementation.py -v
  Status: 23 passed, 0 failed (against an ephemeral postgres:15 container that
  the fixture starts, bootstraps, migrates to head, and tears down per module).

8.2 P21-D-B model / skeleton tests (must stay green / unchanged):
  Command: python -m pytest
    tests/test_platform_p21_durable_approval_adapter_skeleton.py
    tests/test_platform_p21_durable_approval_models.py -v
  Status: 58 passed, 0 failed. The models.py enum-decode change is non-breaking
  (create_type stays False; the model test does not assert enum symbol presence).

8.3 P20 durable approval governance regression:
  tests/test_platform_p20_durable_approval_governance.py -- included in 8.4.

8.4 P10 + P18 + P18-D + P19 regression (with P20 governance):
  Command: python -m pytest
    tests/test_platform_p20_durable_approval_governance.py
    tests/test_platform_p10_contracts.py
    tests/test_platform_p18_controlled_actions.py
    tests/test_platform_p18d_real_registry.py
    tests/test_platform_p19_approval_workflow.py -q
  Status: 315 passed, 0 failed, 5 pre-existing datetime.utc() deprecation
  warnings (unchanged from the base).

8.5 git diff --check:
  Status: clean. `git diff --check` (unstaged) and `git diff --cached --check`
  both exit 0 (no whitespace errors, no conflict markers).

8.6 Non-ASCII scan on the changed files:
  Status: EXECUTED (ripgrep pattern [^\x00-\x7F] over adapter.py, models.py, and
  the new test file). 0 hits. Pure ASCII (no box-drawing, arrows, long dashes,
  section sign, middot, check / cross marks, or smart quotes).

8.7 Forbidden path audit:
  Status: EXECUTED (section 7). Clean, 0 forbidden hits.

8.8 detect-secrets-hook --baseline <configured baseline> on changed files:
  Command: detect-secrets-hook --baseline <the configured secrets baseline file>
    backend/api/v1/platform/p21/adapter.py
    backend/api/v1/platform/p21/models.py
    backend/tests/test_platform_p21_durable_approval_adapter_implementation.py
  Status: passed, exit code 0. Three test fixtures are marked
  "# pragma: allowlist secret": two throwaway local-container DB URLs
  (postgres:p21dc@127.0.0.1, never the developer DB) and one deliberate
  secret-bearing reason string used to prove redaction-before-persistence. The
  configured baseline file is not modified.

8.9 npx gitnexus analyze:
  Status: passed. 7,926 nodes / 24,276 edges / 515 clusters / 300 flows (forced
  re-index after the working-tree change). Up from the base 7,858 nodes /
  23,989 edges.

8.10 GitNexus detect_changes (MCP, driven over stdio JSON-RPC):
  Status: passed.
  Result: changed_count = 40, affected_count = 0, changed_files = 2,
  risk_level = low. Both changed paths are inside backend/api/v1/platform/p21/
  (adapter.py, models.py). 0 affected processes. No HIGH / CRITICAL risk, and
  nothing outside the P21 durable approval surface.

8.11 Clean worktree after commit:
  Status: confirmed post-commit (single worker commit containing exactly the
  four paths in section 3 and nothing else staged or modified).

## 9. Risk assessment

- P21-D-C (this slice): LOW. A new concrete adapter class + a decode-only models
  tweak + self-contained ephemeral-DB tests, confined to the p21 package that no
  live path imports (GitNexus affected_count = 0). No database I/O outside the
  adapter's own tests, no state mutation in production, no router, no migration,
  no storage switch, no execution, no tenant mutation, no auth / RBAC / session
  change, no payment change, no package / lockfile change, no configured-baseline
  change, no frontend.
- P21-D-D (runtime storage cutover): NOT STARTED, separately CTO-gated. Even
  then, approval is not execution and durability is not execution.

## 10. Blockers

None. No stop condition was hit. No migration or schema change was required (the
adapter reads / writes the already-merged P21-C1 tables). The tests are
self-contained against an ephemeral throwaway container (no manual / shared DB).
The no-execution invariant is proven by test and by source scan. No raw secret,
raw reason, raw metadata, or raw idempotency key is persisted or echoed (the
adapter hashes keys at the boundary, redacts reason / metadata before
persistence, and the tests scan every persisted table for the raw values).

## 11. Final statements

- No execution: no controlled action was run; execution_allowed stays False,
  executed stays False, execution_gate stays "blocked" on every row and response.
- No storage cutover: the running P20-B store stays in-memory; the durable
  adapter is not imported by any P20 route / service or by api.app.
- No migration: no new migration, no existing migration / env.py / table altered.
- No tenant mutation: no P17 registry field, lifecycle, flag, or tenant business
  record read or written; tenant_id is a scoped identifier only.
- No auth / RBAC rewrite: the P10 identity-only guard and P20-B-R1 actor binding
  are reused unchanged.
- No frontend: no frontend path touched.
- No product-dev-recovered: no product or product-dev-recovered path touched.
- P21-D-D not started: the runtime storage cutover is not performed or authorized
  by this slice.

## 12. Recommendation

Recommendation: APPROVE_FOR_CODEX_REVIEW.

Rationale:
- The branch is a clean change set on the confirmed base 5c4534a, touching
  exactly the four intended paths (section 3), with a clean forbidden-path audit
  (section 7).
- The concrete adapter implements the frozen P21-D-B surface against the durable
  tables, mirroring P20-B exactly and preserving the no-execution / no-cutover /
  digest-only / redaction-before-persistence invariants. Correctness is proven by
  23 focused ephemeral-DB tests plus 315 regression tests, all green.
- The frozen P21-D-B skeleton suite (58 tests) passes unchanged.
- Risk is LOW (confined to the new, unimported p21 adapter + tests; GitNexus
  affected_count = 0).

Mandatory reviewer actions before any merge: re-execute the focused P21-D-C
tests (8.1), the P21-D-B skeleton / model suite (8.2), the P10 / P18 / P18-D /
P19 / P20 regression suite (8.4), detect-secrets-hook against the configured
baseline on the changed files (8.8), and npx gitnexus analyze / detect_changes
(8.9 / 8.10); confirm git diff --check origin/platform-dev..HEAD (8.5) and the
clean post-commit worktree (8.11). Do not merge until those pass.

Approval is for review consideration only; it is not a merge. Per the cumulative
P21 discipline, approval of the concrete adapter implementation is not approval
of any cutover: P21-D-D remains separately CTO-gated, and even then no execution
and no tenant mutation.

Approval is not execution, and durability is not execution. P21-D-D is not
started.
