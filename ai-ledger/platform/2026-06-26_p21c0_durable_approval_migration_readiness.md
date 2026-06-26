# P21-C0 Durable Approval Migration Readiness Gate

Date: 2026-06-26
Phase: P21-C0 (inspection-only readiness gate for the future CTO-approved P21-C1
additive durable approval migration). P21-C0 inspects the existing migration / schema
system and the accepted P21-A durable approval store contract and P21-B schema plan, and
produces a go / no-go readiness report. P21-C0 creates no migration files, no tables, no
alembic change, no generated DB files, no backend runtime code, no frontend, no test code,
no storage switch, no execution, no tenant mutation, and starts no P21-C1.
Branch: codex/platform-p21c0-durable-approval-migration-readiness-2026-06-26
Base: origin/platform-dev = e873422 (P21-A durable approval store contract merged via
P21-A.1; P21-B durable approval schema plan + test plan merged via P21-B.1).
Scope: docs / ledger only (one readiness ledger file). Inspection-only. No migration files,
no runtime code, no frontend, no storage switch, no execution, no P21-C1.

This phase is a readiness gate. It does not implement, migrate, execute, persist (beyond
this ledger), switch runtime storage, mutate tenant state, or merge anything into
platform-dev. It is an isolated, docs-only branch. P21-C1 is not started.

Approval is not execution, and durability is not execution.

## 1. Phase inventory

P21-C0 - durable approval migration readiness gate (docs / ledger only, inspection-only)
- Source branch: codex/platform-p21c0-durable-approval-migration-readiness-2026-06-26
- Base: origin/platform-dev = e873422 (confirmed: git fetch --all --prune; HEAD == merge-base
  HEAD origin/platform-dev == e873422; worktree clean at base)
- Report path: ai-ledger/platform/2026-06-26_p21c0_durable_approval_migration_readiness.md
  (this file)
- Scope: inspection-only readiness report grounded in the accepted P21-A contract and P21-B
  plan and the existing migration / schema system
- Risk: LOW (P21-C0 itself is docs / ledger only, no runtime code, no migration files, no
  tables, no storage switch). The future P21-C1 it gates is schema-risk and is separately
  classified in section 9.
- Status: readiness gate on isolated branch; not merged to platform-dev

## 2. Base and branch confirmation

- git fetch --all --prune: run. origin/platform-dev resolved to e873422 (short SHA; full
  40-char SHA deliberately not pinned in this file so the ledger stays detect-secrets-clean
  and non-self-referential).
- origin/platform-dev == e873422: confirmed (matches the expected base in the task
  brief).
- Isolated branch codex/platform-p21c0-durable-approval-migration-readiness-2026-06-26
  created from origin/platform-dev via an isolated worktree.
- HEAD == e873422 at branch creation; git merge-base HEAD origin/platform-dev == e873422
  (no divergence from base).
- Branch upstream deliberately unset after creation so a bare git push can never fast-forward
  origin/platform-dev; the isolated branch is pushed only via the BR:BR refspec. origin /
  platform-dev is not merged and is not pushed by this phase.
- Worktree clean at base and after the readiness ledger is written.

## 3. Migration system findings (inspection)

Inspected (read-only, no edits):

- backend/alembic.ini
- backend/alembic/env.py
- backend/alembic/versions/ (all 19 version files: revision / down_revision chain, upgrade
  and downgrade presence, schema scoping)
- backend/alembic/versions/018_platform_p0_lifecycle.py (platform table migration template)
- backend/alembic/versions/019_platform_audit_logs.py (platform table migration template;
  current head)
- backend/models/__init__.py and backend/models/base.py (Base / metadata / mixins / model
  registration pattern)
- backend/models/platform_tenant.py and backend/models/platform_audit_log.py (platform ORM
  models paired with the 018 / 019 migrations)
- backend/tests/test_alembic_migrations.py (migration structure and reversibility test
  harness)
- backend/tests/test_platform_p20_durable_approval_governance.py (existing P20 durable
  approval governance test, for test conventions)
- backend/pytest.ini (test markers: integration, unit, property; asyncio_mode = auto)
- docs/ai/PLATFORM_PRODUCT_P21_DURABLE_APPROVAL_SCHEMA_PLAN.md (accepted P21-B plan, the
  authoritative source for the future migration scope)
- docs/ai/PLATFORM_PRODUCT_P21_DURABLE_APPROVAL_STORE_CONTRACT.md and the P21-A / P21-B
  ledger reports (accepted contract terms)

Findings:

- Alembic configuration (backend/alembic.ini): single-database config; script_location =
  alembic; version_path_separator = os; the default sqlalchemy.url is a local asyncpg DSN
  and is overridden at runtime by DATABASE_URL inside env.py (postgresql:// is rewritten to
  postgresql+asyncpg://). This is config-only; P21-C0 changes none of it.
- Alembic environment (backend/alembic/env.py): multi-tenant aware. It imports
  `from models import Base` and sets `target_metadata = Base.metadata` so autogenerate sees
  every registered model. It sets `version_table_schema = "public"` and `include_schemas =
  True` always. Public-schema migrations run with `alembic upgrade head` (no extra arg); a
  specific tenant is migrated with `alembic upgrade head -x tenant_schema=t_abc123`, which
  CREATEs the tenant schema IF NOT EXISTS and SET LOCAL search_path to that tenant then
  public. The version table always lives in public.
- Version layout and chain: 19 files under backend/alembic/versions/. Naming convention is a
  monotonic zero-padded numeric prefix plus a slug: 001_initial_schema.py ... through
  019_platform_audit_logs.py. The revision id equals the filename stem and down_revision is
  the previous stem, forming a single linear chain 010 -> 011 -> ... -> 019. Current head is
  019_platform_audit_logs. (Files 001-009 use the same numeric convention; the chain is
  linear and unbranched to head.)
- Reversibility: every one of the 19 version files defines both upgrade() and downgrade()
  (verified). The platform migrations downgrade by dropping only the objects they created
  (op.drop_table / op.drop_index / op.drop_column, schema = public), leaving all prior data
  intact. This is the rollback convention a future P21-C1 migration must follow.
- Platform table migration template (018, 019): create platform tables with explicit
  schema = 'public', UUID primary key with server_default gen_random_uuid(), JSONB columns,
  FK references to public.wholesalers.id, created_at / updated_at with server_default
  func.now(), column comments, and explicit op.create_index(..., schema = 'public'). The
  downgrade drops the table(s) and any added columns. tenant_id / wholesaler_id are stored as
  nullable scoped identifiers with an FK only to the public wholesalers tenant table, never
  to a product business table.
- Tenant-schema model: tenant schemas are dynamic, not hardcoded. Version files never embed a
  tenant schema name; where per-tenant objects are needed (for example the reporting role and
  materialized views in 011 and 013) the migration enumerates existing tenant schemas from
  the catalog at runtime and loops over them. No version file is scoped to a literal tenant
  schema. Platform tables (018, 019) use explicit schema = 'public' and so are created only
  in public regardless of search_path.
- Model registration: backend/models/__init__.py explicitly imports every ORM model and the
  shared Base / mixins from backend/models/base.py. Base is a SQLAlchemy 2.0 DeclarativeBase;
  PublicBaseModel provides a UUID id (gen_random_uuid()), created_at, updated_at, is_deleted,
  deleted_at for public-schema tables; BaseModel adds user tracking for tenant-scoped tables.
  The 018 / 019 platform tables already have paired ORM models (platform_tenant.py,
  platform_audit_log.py). Autogenerate therefore sees the platform tables; a future durable
  approval ORM model set would be registered the same way when it is added (P21-D adapter
  wiring), so that Base.metadata and the migrated schema stay consistent.
- Migration test harness: backend/tests/test_alembic_migrations.py checks the initial
  migration exists, has upgrade() / downgrade() / revision / down_revision identifiers, and
  includes (skipped) integration property tests asserting public migrations do not create
  tenant tables and tenant migrations do not affect public.wholesalers. pytest markers are
  integration / unit / property, and asyncio_mode = auto. The existing
  test_platform_p20_durable_approval_governance.py establishes the durable approval test
  conventions P21-C1 / P21-D tests will extend.

## 4. Target schema boundary recommendation

Recommendation: the future durable approval governance tables must live in the public schema
only, with explicit schema = 'public' on every CREATE TABLE / CREATE INDEX, exactly matching
the 018 / 019 platform table pattern. The tenant schema is explicitly rejected for the
durable approval tables unless separately, explicitly approved.

Evidence supporting the public-schema boundary:

- The accepted P21-A contract and P21-B plan both fix the durable tables to platform / public
  schema only (P21-A migration boundary; P21-B section 8 target schema) and forbid touching
  tenant schema without separate approval.
- Durable approval is platform governance, not tenant business data. The closest existing
  analogues (platform_tenants, platform_audit_logs) are public-schema tables that reference
  public.wholesalers.id as a scoped tenant identifier and are created only in public.
- env.py sets version_table_schema = public and the platform tables pin schema = 'public', so
  explicit-public tables are never created in a tenant schema. IMPORTANT CAVEAT (P21-C0-R1):
  this does NOT remove env.py's tenant-schema creation side effect. do_run_migrations still
  executes CREATE SCHEMA IF NOT EXISTS for the supplied tenant whenever -x tenant_schema is
  passed. So the durable tables staying in public does not, by itself, prove no tenant-schema
  change; tenant mode must simply not be invoked for P21-C1 (see sections 6 and 8).
- The contract requires tenant_id to be a scoped identifier only, never a foreign key into a
  product business table (C-R4). A public-schema table with tenant_id as a plain nullable
  value (no business FK) satisfies this; a tenant-schema table would not.

Metadata / session conventions the future P21-C1 migration must use:

- Hand-written op.create_table / op.create_index / op.create_unique_constraint with explicit
  schema = 'public' (do not rely on autogenerate; follow the 018 / 019 style). Use
  postgresql.UUID(as_uuid=True) with server_default gen_random_uuid() for UUID keys, char(64)
  for SHA-256 digests, JSONB for metadata, DateTime(timezone=True) with server_default
  func.now() for timestamps, and column comments.
- revision / down_revision / branch_labels = None / depends_on = None header matching the
  existing files, and a docstring with Revision ID / Revises / Create Date.
- No tenant_schema logic, no CREATE SCHEMA, no per-tenant loop, and no reference to any
  product business table.
- The future migration must not switch runtime P20 storage (P20-B stays in-memory /
  existing-safe); runtime adapter wiring is P21-D.

## 5. Future P21-C1 migration scope (defined, not created)

P21-C0 creates nothing. The following is the exact scope a future CTO-approved P21-C1
migration must have, taken from the accepted P21-B plan (section 3 schema, section 4 enums,
section 5 constraints, section 8 migration plan) and reconciled with the repo's actual
conventions.

- Purpose: create ONLY the five durable approval governance tables from P21-B, additive-only,
  public-schema-only, reversible, dry-run-gated, no storage switch, no execution. No ALTER /
  DROP / RENAME of any existing object, no tenant-schema migration, no product business path.
- File: one new version file under backend/alembic/versions/. Because the repo uses a
  monotonic numeric prefix (current head 019_platform_audit_logs), the next file is 020_*
  (for example 020_durable_approval_store.py), with revision = '020_...' and down_revision =
  '019_platform_audit_logs'. NOTE: the P21-B plan's illustrative name
  YYYYMMDDHHMM_p21c_durable_approval_store.py is the alembic default timestamp form; the
  repo's established convention is the numeric-prefix form, and P21-C1 must use the numeric
  form to stay consistent with 001-019. This naming reconciliation is a P21-C0 finding, not a
  contract change.
- Tables (all schema = 'public'):
  - durable_approval_requests (T1) - approval_id PK, action_id, tenant_id (scoped id only,
    no business FK), action_type, action_class, state, maker_actor_id, maker_at,
    quorum_required, quorum_met (default false), decision, reason_redacted,
    metadata_redacted, request_digest (char 64), idempotency_key_digest (char 64),
    source_status, validation_status, execution_allowed (default false), execution_gate
    (default blocked), executed (default false), redaction_applied (default true),
    storage_class, retention_class, expires_at, durable_retain_until, superseded_by,
    previous_state, last_audit_event_id, correlation_id, store_version (default 1),
    created_at, updated_at.
  - durable_approval_decisions (T2) - decision_id PK, approval_id, checker_actor_id,
    decision, reason_redacted, metadata_redacted, idempotency_key_digest, decision_digest,
    confirm, audit_event_id, correlation_id, created_at.
  - durable_approval_audit_events (T3) - event_id PK, approval_id, action_id, actor_id,
    actor_role, identity_context, event_type, decision, audit_result, previous_status,
    next_status, reason_redacted, metadata_redacted, request_digest, redaction_applied
    (default true), tenant_id (scoped id only), quorum_required, quorum_met, source_status,
    validation_status, correlation_id, sequence_no, created_at.
  - durable_approval_idempotency_keys (T4) - idempotency_id PK, scope_key, scope_id,
    idempotency_key_digest (char 64), payload_digest (char 64), result_ref, first_seen_at,
    last_seen_at, created_at.
  - durable_approval_retention_jobs (T5) - job_id PK, job_type, target_approval_id,
    retention_class, eligible_at, locked_by, locked_at, status (default pending),
    audit_event_id, attempts (default 0), created_at, updated_at.
- Indexes / constraints to verify after migration (from P21-B section 3): PK on each table;
  T1 uq_requests_active_digest (partial, request_digest where state active),
  uq_requests_open_action_maker (partial, action_id + maker_actor_id where not terminal),
  ix_requests_state, ix_requests_tenant_state, ix_requests_purge_scan, ix_requests_expire_scan
  (partial, expires_at where pending_review), ix_requests_source_val, ix_requests_action;
  T2 uq_decisions_approval_checker (approval_id + checker_actor_id),
  uq_decisions_approval_idem (approval_id + idempotency_key_digest), ix_decisions_approval,
  ix_decisions_checker; T3 uq_audit_approval_seq (approval_id + sequence_no),
  ix_audit_approval_time, ix_audit_event_type, ix_audit_actor, ix_audit_time; T4
  uq_idem_scope (scope_key + scope_id + idempotency_key_digest), ix_idem_digest; T5
  uq_jobs_active_target_type (partial, target_approval_id + job_type where pending / running),
  ix_jobs_dequeue (status + eligible_at), ix_jobs_retention. FK-like references stay logical
  (action_id -> P18 request, last_audit_event_id / audit_event_id -> T3, superseded_by ->
  approval_id self-ref); no FK to any product business table.
- Enums (closed value sets from P21-B section 4): approval states (no executing / executed /
  queued / ready value), action classes, execution gate (only blocked reachable in P21),
  source status, validation status, retention class, decision type, audit event type, audit
  result, plus actor_role / identity_context / storage_class / scope_key / job_type /
  job status. Created as native enums or varchar-with-CHECK per the engine; value sets closed
  and validated at the boundary.
- Defaults that must be false: execution_allowed (default false), executed (default false),
  execution_gate (default blocked); redaction_applied (default true). A permanent DB
  CHECK(false) on execution_allowed / executed is intentionally NOT added (it would block a
  future separately-approved execution phase); the column defaults plus adapter invariant
  plus G11 tests hold the line in P21.

## 6. Rollback and dry-run requirements (for P21-C1)

- Downgrade expectation: downgrade() DROPs only the five new tables and their enums / indexes
  / unique constraints, in dependency-safe order, with explicit schema = 'public', leaving
  every pre-existing object and all existing data intact. Rollback must not touch any
  pre-existing object (matching the 018 / 019 downgrade style). A documented restore path
  (re-run upgrade) is required.
- Dry-run / schema-inspection command: run the migration only against an ephemeral test
  database first. Inspect the DDL preview (for example alembic upgrade --sql or an
  information_schema diff) to confirm only new objects appear; no data change. The diff must
  show additions only.
- Pre-migration safety checks: confirm the target DB is at the expected base (current head
  019_platform_audit_logs); confirm no durable_approval_* objects pre-exist; confirm the
  additive-only DDL preview; confirm execution_allowed / executed / execution_gate defaults
  are false / blocked; confirm no tenant-schema migration is present.
- Post-migration validation: confirm the five tables exist with the exact columns, types,
  nullability, defaults, enums, indexes, and unique constraints from section 5; confirm no
  existing table was altered (schema diff is additions-only); confirm the downgrade removes
  only the five tables and re-applies cleanly; pass G1 schema tests against the real schema.
- Tenant mode is out of scope and must not be invoked (P21-C0-R1 correction). The P21-C1
  migration invocation is public-schema-only: deployment and test commands MUST NOT pass
  -x tenant_schema. backend/alembic/env.py (do_run_migrations) executes CREATE SCHEMA IF NOT
  EXISTS for the supplied tenant whenever -x tenant_schema is given, so running the migration
  in tenant mode would itself create a tenant schema. Therefore the absence of tenant-schema
  change is NOT proven by running the migration with and without -x tenant_schema; it is
  enforced by never invoking tenant mode for P21-C1 and by verifying, via catalog inspection
  (information_schema) rather than tenant-mode execution, that no durable_approval_* object
  exists in any tenant schema.
- Operational preflight for P21-C1 (public mode only):
  - Before upgrade, confirm the public migration head is 019_platform_audit_logs.
  - Execute the new 020 migration in public mode only (alembic upgrade head, with NO
    -x tenant_schema). No tenant-mode upgrade or downgrade is run for P21-C1.
  - Before any later tenant-mode operations, confirm the public alembic revision is the new
    020 revision, so a subsequent tenant-mode run does not carry the durable migration through
    the tenant search_path.
- Prove no product table changed: schema diff of public before vs after is additions-only;
  wholesalers, orders, payments, invoices, inventory, ledgers, and all tenant business tables
  are unchanged. No durable column references any product business table (C-R4).

## 7. Test readiness (for P21-C1 / P21-D)

Planned test artifacts (from the accepted P21-B plan section 9, G1-G14; P21-C0 writes no
tests). P21-C1 specifically must deliver at least G1 and G2 to satisfy its entry gate; the
rest land across P21-C1 / P21-D.

- G1 schema tests (>= 12): exact columns / types / nullability / defaults / enums, extra =
  forbid discipline, unique and index objects present, execution_allowed / executed default
  false. Likely home: backend/tests/test_platform_p21_durable_approval_schema.py (new).
- G2 migration dry-run tests (>= 6): additive-only DDL preview, downgrade removes only the
  five tables, no existing table altered (additions-only diff), base-DB precondition,
  idempotent apply, rollback restore path. Likely home:
  backend/tests/test_platform_p21_durable_approval_migration.py (new), extending the existing
  backend/tests/test_alembic_migrations.py structure / reversibility pattern.
- G4 restart persistence (>= 5), G5 idempotency digest (>= 6), G6 redaction persistence
  (>= 6), G7 maker-checker (>= 8), G8 quorum race (>= 5), G9 state transition (>= 9),
  G10 retention / purge / export (>= 8), G11 no-execution (>= 5), G12 no-tenant-mutation
  (>= 5), G13 API compatibility (>= 6): adapter / transaction tests for P21-D, extending
  test_platform_p20_durable_approval_governance.py conventions.
- G14 GitNexus scope tests (>= 2): detect_changes for the durable store change is scoped to
  the platform durable-approval storage surface; no product / tenant / payment / auth / RBAC
  process is affected.
- Public / platform schema boundary tests, no-tenant-mutation tests, no-product-mutation
  tests, and no-execution / no-storage-switch tests are all covered by the G1, G2, G11, G12,
  G13 groups above. No execution and no storage switch is asserted in P21-C1. The tenant-scope
  proof is by public-mode catalog inspection (no durable_approval_* object appears in any
  tenant schema), never by invoking tenant-mode migration; P21-C1 test commands MUST NOT pass
  -x tenant_schema (see section 6).

## 8. P21-C1 entry gate (readiness conditions)

P21-C1 may implement the migration only, and only after explicit CTO approval. It must:
- remain additive and public / platform schema only (CREATE TABLE / INDEX / TYPE /
  CONSTRAINT for T1-T5; no ALTER / DROP / RENAME of any existing object);
- perform no tenant schema migration and touch no product business paths; in particular P21-C1
  is public-schema-only and its deployment / test commands MUST NOT pass -x tenant_schema
  (tenant-mode migration is out of scope for P21-C1);
- not switch runtime P20 storage (P20-B stays in-memory / existing-safe; cutover is P21-D);
- satisfy every gate in section 6 (rollback, dry-run, pre / post validation) and pass G1 and
  G2 against a real ephemeral-test schema;
- not execute any action, not mutate tenant state, and not set execution_allowed / executed
  true;
- begin from the accepted P21-A contract and P21-B plan and not change tables, columns,
  types, enums, constraints, state machine, security rules, retention rules, API
  compatibility, or audit fields without a new contract / plan revision accepted by the CTO.

## 9. Risk assessment

- P21-C0 itself: LOW. Docs / ledger only, inspection-only. No runtime code, no migration
  files, no tables, no alembic change, no generated DB files, no storage switch, no execution,
  no tenant mutation, no auth / RBAC change, no frontend, no package / lockfile change.
- The future P21-C1 it gates: MEDIUM-to-HIGH (schema-risk). Even though P21-C1 is additive and
  public-schema-only, any migration that creates tables and indexes in a shared database
  carries schema risk and must be gated. P21-C1 is therefore blocked behind explicit CTO
  approval and the full entry gate (section 8) plus the rollback / dry-run / pre / post
  validation (section 6) and the G1 + G2 tests (section 7). The durable store is governance
  only; approval is not execution and durability is not execution.

## 10. Go / no-go verdict for P21-C1

Verdict: P21-C1_READY_TO_IMPLEMENT_MIGRATION (conditional). The verdict is conditional in
particular on the public-only invocation rule (P21-C0-R1): P21-C1 must never be run with
-x tenant_schema; tenant-mode migration is out of scope for P21-C1.

The migration system is ready: a single linear chain with current head 019_platform_audit_logs
and a clear next slot (020_*); a documented public-schema, additive-only, fully reversible
platform-table migration template (018 / 019); explicit-schema-public conventions that place
the durable tables in public only (with the explicit caveat that this does not remove env.py's
tenant-schema creation side effect, so public-only invocation -- never -x tenant_schema -- is
what actually excludes tenant mode); an accepted
implementation-ready schema plan (P21-B) and contract (P21-A) with exact tables, columns,
enums, constraints, indexes, a rollback plan, a dry-run procedure, and a G1-G14 test plan; and
an existing migration test harness to extend.

Conditions (blockers that must be cleared before P21-C1 actually runs, all expected and none
caused by a defect):
1. Explicit CTO approval for P21-C1 (required by both the P21-A contract and the P21-B entry
   gate).
2. P21-C1 begins from the accepted P21-A contract + P21-B plan and changes none of their
   terms without a new accepted revision.
3. P21-C1 uses the repo's numeric-prefix naming (020_*) with down_revision =
   019_platform_audit_logs, not the plan's illustrative timestamp name.
4. P21-C1 runs public-mode only: deployment and test commands MUST NOT pass -x tenant_schema
   (tenant-mode migration is out of scope). It passes the full entry gate (section 8), the
   rollback / dry-run / pre / post validation (section 6), and the G1 + G2 tests (section 7)
   against a real ephemeral-test schema; it verifies by public-mode catalog inspection that no
   durable_approval_* object exists in any tenant schema; and it proves no product table
   changed.
5. P21-C1 performs no storage switch (P20-B stays in-memory / existing-safe; cutover is
   P21-D), no execution, and no tenant mutation.

No contract / plan revision is required: the accepted P21-A contract and P21-B plan already
make the migration implementation-ready, and the only reconciliation (numeric-prefix file
naming) is a repo-convention finding, not a contract change.

## 11. Verification (docs-only branch, all must pass)

Run on this branch versus origin/platform-dev = e873422:

- git diff --check origin/platform-dev..HEAD: clean (no whitespace errors).
- Non-ASCII scan of the changed file: 0 hits (pure ASCII; no section sign, box-drawing,
  em dash, middot, smart quotes, or arrows).
- detect-secrets (detect-secrets-hook against the configured secret baseline) on the changed
  file: PASS, exit 0, no new secrets. The configured baseline file is not modified.
- Forbidden path audit: 0 hits. The only changed file is this readiness ledger.
- npx gitnexus analyze: success (graph intact; a docs-only change affects no execution flow).
  Node / cluster counts fluctuate slightly across re-indexes (clustering is non-deterministic);
  the stable metric is 300 flows (observed on the order of ~7,650 nodes / ~23,560 edges / ~490
  clusters). Re-indexed and re-verified at the P21-C0-R1 tip.
- GitNexus detect_changes compare origin/platform-dev..HEAD: LOW risk, docs-only, 0 affected
  processes (changed_count 15, affected_count 0, changed_files 1, risk_level low; all 15
  changed symbols are File / Section markdown nodes in the one ledger file;
  affected_processes []).
- Working tree clean after commit.
- Isolated branch pushed only via the BR:BR refspec; origin / platform-dev untouched at
  e873422 (not merged, not pushed).

## 12. Forbidden audit summary

P21-C0 touches none of the following (all verified by the changed-path audit):

- No backend / runtime code path.
- No frontend code path.
- No migration files, alembic change, version file, or generated DB files.
- No new tables created and no production migration run.
- No payment or billing change.
- No package.json, pnpm-lock, package-lock, yarn.lock, or poetry.lock change.
- No product-dev-recovered path.
- No auth / RBAC / session rewrite.
- No .github / CI change.
- No .claude change.
- No change to the configured secret baseline.
- No real execution path (readiness gate only; approved_execution_blocked is the ceiling and
  execution_allowed / executed stay false by plan).
- No tenant mutation path (tenant_id is a scoped identifier only).
- No runtime storage switch (P20-B stays in-memory / existing-safe; that is P21-D).
- No P21-C1 started.

## 13. Final statement

P21-C0 is inspection-only. There is no migration file, no table, no alembic change, no
generated DB file, no runtime backend code, no frontend, no test code, no storage switch, no
execution, no tenant mutation, no auth / RBAC rewrite, no product table change, and no P21-C1
in this phase. P21-C1 remains CTO-gated and must satisfy the full entry gate before it may
implement the additive, public-schema-only, reversible durable approval migration. Approval is
not execution, and durability is not execution.
