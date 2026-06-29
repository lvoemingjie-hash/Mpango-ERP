# P21-C1 Public Durable Approval Store Migration

Date: 2026-06-26
Phase: P21-C1 (implements the additive, reversible, public-schema-only durable approval
migration from the accepted P21-A contract and P21-B plan, plus the real ephemeral-Postgres
G1 schema and G2 migration tests). P21-C1 creates the five durable approval governance
tables and their enum types / indexes / uniqueness constraints in the public schema only.
It does not switch runtime P20 storage (P20-B stays in-memory / existing-safe; that is
P21-D), does not execute any controlled action, does not mutate tenant data, and does not
register ORM models.
Branch: codex/platform-p21c1-public-durable-approval-migration-2026-06-26
Base: origin/platform-dev = b06b773 (P21-C0 readiness gate merged).
Scope: four files only:
  - backend/alembic/versions/020_durable_approval_store.py (new migration)
  - backend/tests/test_platform_p21_durable_approval_schema.py (new, G1)
  - backend/tests/test_platform_p21_durable_approval_migration.py (new, G2)
  - ai-ledger/platform/2026-06-26_p21c1_public_durable_approval_migration.md (this ledger)

Approval is not execution, and durability is not execution. No controlled action is ever
run. The durable store is governance only.

## 1. Migration object summary

revision = 020_durable_approval_store; down_revision = 019_platform_audit_logs; the next
monotonic numeric slot after the prior head. All objects are created in schema = 'public'.

Tables (five, public):
  - durable_approval_requests (T1): approval_id (uuid PK, gen_random_uuid), action_id,
    tenant_id (scoped id, no business FK), action_type (varchar(255), P18 vocabulary),
    action_class, state, maker_actor_id, maker_at, quorum_required, quorum_met (default
    false), decision, reason_redacted, metadata_redacted, request_digest (char 64),
    idempotency_key_digest (char 64), source_status, validation_status, execution_allowed
    (default false), execution_gate (default 'blocked'), executed (default false),
    redaction_applied (default true), storage_class, retention_class, expires_at,
    durable_retain_until, superseded_by, previous_state, last_audit_event_id, correlation_id,
    store_version (default 1), created_at, updated_at.
  - durable_approval_decisions (T2): decision_id (uuid PK), approval_id (FK -> T1 ondelete
    RESTRICT), checker_actor_id, decision, reason_redacted, metadata_redacted,
    idempotency_key_digest (char 64), decision_digest (char 64), confirm, audit_event_id
    (FK -> T3), correlation_id, created_at.
  - durable_approval_audit_events (T3, append-only): event_id (uuid PK), approval_id,
    action_id, actor_id, actor_role, identity_context, event_type, decision, audit_result,
    previous_status, next_status, reason_redacted, metadata_redacted, request_digest (char
    64), redaction_applied (default true), tenant_id, quorum_required, quorum_met,
    source_status, validation_status, correlation_id, sequence_no (bigint), created_at.
  - durable_approval_idempotency_keys (T4, digest-only): idempotency_id (uuid PK), scope_key,
    scope_id, idempotency_key_digest (char 64), payload_digest (char 64), result_ref,
    first_seen_at, last_seen_at, created_at. The raw idempotency key is never stored.
  - durable_approval_retention_jobs (T5): job_id (uuid PK), job_type, target_approval_id
    (FK -> T1), retention_class, eligible_at, locked_by, locked_at, status (default
    'pending'), audit_event_id (FK -> T3), attempts (default 0), created_at, updated_at.

Enum types (fifteen, public): durable_approval_state, _action_class, _execution_gate,
_source_status, _validation_status, _retention_class, _decision, _actor_role,
_identity_context, _event_type, _audit_result, _storage_class, _scope_key, _job_type,
_job_status. Each is a native Postgres enum created explicitly in public and dropped
explicitly in the downgrade.

Indexes / uniqueness (public):
  - T1: uq_requests_active_digest (unique partial), uq_requests_open_action_maker (unique
    partial), ix_requests_state, ix_requests_tenant_state, ix_requests_purge_scan,
    ix_requests_expire_scan (partial), ix_requests_source_val, ix_requests_action.
  - T2: uq_decisions_approval_checker (unique), uq_decisions_approval_idem (unique),
    ix_decisions_approval, ix_decisions_checker.
  - T3: uq_audit_approval_seq (unique), ix_audit_approval_time, ix_audit_event_type,
    ix_audit_actor, ix_audit_time.
  - T4: uq_idem_scope (unique), ix_idem_digest.
  - T5: uq_jobs_active_target_type (unique partial), ix_jobs_dequeue, ix_jobs_retention.

Foreign keys (real, public): T2.approval_id -> T1 (RESTRICT); T2.audit_event_id -> T3;
T5.target_approval_id -> T1; T5.audit_event_id -> T3. FK-like logical references kept as
plain columns (no constraint): T1.action_id (-> P18), T1.last_audit_event_id (-> T3),
T1.superseded_by (self), T3.approval_id / action_id.

Defaults that hold the line (no permanent DB CHECK is added, so a future separately
approved execution phase is not blocked): execution_allowed = false, executed = false,
execution_gate = 'blocked', redaction_applied = true, store_version = 1, quorum_met =
false, status = 'pending', attempts = 0.

Downgrade (dependency-safe): drops only P21-C1 objects in reverse dependency order
(retention_jobs, decisions, idempotency_keys, audit_events, requests) then drops the
fifteen enum types. No pre-existing object is touched.

## 2. Test commands and results (real ephemeral PostgreSQL)

The G1 / G2 tests run only against an explicit ephemeral database and refuse to run against
the developer mpango_erp database. They were run against a throwaway postgres:15-alpine
container (NEVER against shared / production / developer databases). Public mode only: no
alembic or pytest command passed -x tenant_schema.

Setup (throwaway ephemeral DB) -- self-contained as of P21-C1-R1 (no manual SQL):
  - docker run --rm postgres:15-alpine with a dedicated ephemeral database / user / password
    on an isolated port (not 5432, not mpango_erp). No SQL is applied by hand.
  - A session bootstrap fixture (_boot / _bootstrap_ephemeral in each test file) applies the
    test-only prerequisites to the explicit ephemeral DB, idempotently, mirroring
    database/init.sql: CREATE EXTENSION IF NOT EXISTS pgcrypto; ensure
    public.alembic_version.version_num is varchar(128) (create the table if absent, else
    ALTER the column wider if it is shorter than 128); CREATE SCHEMA IF NOT EXISTS t_dev.
    This runs only against the explicit ephemeral URL and never against a shared / dev / prod
    DB.
  - env set by the runner: TEST_DATABASE_URL -> ephemeral DSN; PYTHONIOENCODING=utf-8
    (existing migrations 010 / 011 / 013 print a checkmark the GBK console cannot encode);
    REPORTING_USER_PASSWORD (existing migration 011 requires it; the fixture also setdefaults
    it so the tests are self-contained from the URL alone for that variable).

Command (from backend/):
  python -m pytest tests/test_platform_p21_durable_approval_schema.py \
                   tests/test_platform_p21_durable_approval_migration.py -v

Result: 37 passed, 0 failed (31 G1 schema tests + 6 G2 migration tests).

G1 (test_platform_p21_durable_approval_schema.py, 31 tests): each of the five tables has
exactly its declared columns (extra = forbid); key types correct; the no-execution and
redaction defaults verified (execution_allowed = false, executed = false, execution_gate =
'blocked', redaction_applied = true); all planned indexes / unique constraints present in
public; decisions and jobs foreign keys present; every durable enum type exists in public
with its exact closed value set.

G2 (test_platform_p21_durable_approval_migration.py, 6 tests): additions-only upgrade from
019 to head adds only the five durable tables / their indexes / constraints / the fifteen
enum types and creates no schema; downgrade drops only P21-C1 objects and leaves every base
object intact; re-upgrade recreates the five tables; catalog proof that no durable_approval_*
table or type exists outside public; the public-mode upgrade does not create any tenant
schema; preflight that the public head is 019 before the upgrade.

## 3. Public-only evidence

  - Public-mode invocation only: every alembic upgrade / downgrade and every pytest run was
    executed WITHOUT -x tenant_schema. No command in this phase passes -x tenant_schema
    (the P21-C0-R1 public-mode rule).
  - Preflight: the public alembic head is confirmed at 019_platform_audit_logs before the
    020 upgrade (G2 test_base_revision_is_019_before_upgrade).
  - The 020 migration is applied in public mode (alembic upgrade head) and the public head
    becomes 020_durable_approval_store.
  - The upgrade does not create any tenant schema (G2 test_upgrade_does_not_create_tenant_schema:
    the schema set is identical before and after the public-mode upgrade), confirming
    env.py's tenant-schema creation side effect is never triggered.

## 4. Downgrade proof

  - G2 test_downgrade_drops_only_p21_objects: downgrade -1 from head removes all five tables,
    all durable indexes / constraints, and all fifteen enum types; the base inventory (11
    public tables and all base indexes / constraints / enums) is byte-for-byte identical
    before and after; schemas unchanged.
  - G2 test_reupgrade_recreates_tables: after downgrade, re-running upgrade recreates all
    five durable tables cleanly.
  - Manual confirmation: at head there are 16 public tables (11 base + 5 durable); after
    downgrade there are 11; after re-upgrade, 16 again and current = 020_durable_approval_store.

## 5. Catalog proof (no tenant-schema mutation)

  - G2 test_no_durable_objects_in_tenant_schemas: no durable_approval_* table and no
    durable_approval_* enum type exists in any schema other than public.
  - G2 test_upgrade_does_not_create_tenant_schema: the set of schemas is unchanged by the
    public-mode upgrade (no tenant schema is created).
  - Every table, index, constraint, and enum type was created with explicit schema =
    'public', so durable objects can never land in a tenant schema.

## 6. GitNexus result

  - npx gitnexus analyze: success (graph intact; new migration + tests indexed).
  - detect_changes on the staged code change: risk_level low, changed_count 32,
    affected_count 0, changed_files 3, affected_processes []. All 32 changed symbols are in
    the three new files (the migration and the two test files). No product, tenant, payment,
    auth, or RBAC execution flow is affected. (Final detect_changes vs origin/platform-dev
    for the whole branch is recorded in the verification section below.)
  - Impact analysis: no existing symbol is modified by this phase (the migration and both
    test files are brand-new; no runtime code, model, API, service, env.py, or frontend file
    is touched), so there is no upstream blast radius to analyze.

## 7. Forbidden-path audit

The change touches only the four allowed files and nothing else (verified by changed-path
audit): no backend runtime code (the migration and tests are additive, not runtime), no
env.py change, no model registration, no API / service / frontend change, no auth / RBAC /
session change, no new migration infrastructure, no tenant business path, no payment path,
no package.json / lockfile, no product-dev-recovered path, no .github / .claude change, and
no change to the configured secret baseline. No file outside the allowed list was created or
modified.

## 8. Risk

  - P21-C1 is schema work, so it carries inherent schema risk (MEDIUM by nature). The
    realized blast radius is LOW: the change is additive, public-schema-only, fully
    reversible (downgrade drops only P21-C1 objects), touches no existing object, registers
    no ORM model, switches no runtime storage, and shows 0 affected processes in GitNexus.
  - Verified end-to-end on a real ephemeral PostgreSQL database: the full base chain
    (001..019) plus the new 020 upgrade cleanly; downgrade clean; re-upgrade clean; exact
    schema / defaults / indexes / constraints / enums; no tenant-schema mutation.

## 9. Stop conditions

None triggered:
  - An ephemeral PostgreSQL-backed migration test COULD be run (docker postgres:15-alpine);
    all 37 G1 / G2 tests passed.
  - The design required no file outside the allowed list.
  - No product table or tenant schema is altered (additive, public-only; catalog-proven).
  - The migration needs no -x tenant_schema to validate (public-mode only).

## 10. Verification (all PASS at branch tip)

  - Preflight public head = 019 before upgrade (G2 test).
  - Upgrade runs in public mode only (no -x tenant_schema); public head = 020 after.
  - G1 / G2 tests: 37 passed, 0 failed.
  - git diff --check origin/platform-dev..HEAD: clean.
  - Non-ASCII scan of the four files: 0 hits (pure ASCII).
  - detect-secrets against the configured baseline: PASS (exit 0); baseline unchanged.
  - Forbidden-path audit: only the four allowed files.
  - npx gitnexus analyze: success.
  - detect_changes compare origin/platform-dev..HEAD: LOW, docs+schema-only, 0 affected
    processes (changed_count 51, affected_count 0, changed_files 4, risk_level low,
    affected_processes []; all 51 changed symbols are in the four allowed files).
  - Worktree clean after commit; isolated branch pushed only via the BR:BR refspec;
    origin/platform-dev untouched at b06b773 (not merged, not pushed).

## 11. P21-C1-R1 reproducibility fix (CTO finding)

CTO finding (P21-C1-R1): the original G1 / G2 tests depended on hidden, out-of-band manual
database preconditions (the pgcrypto extension, a widened public.alembic_version, and the
t_dev schema) that were applied by hand to the ephemeral container before pytest ran. A
clean throwaway Postgres given only TEST_DATABASE_URL would therefore fail to reproduce,
because those prerequisites were not part of the tests themselves.

Fix: a session bootstrap fixture (_boot / _bootstrap_ephemeral, added to each of the two
test files) now applies those test-only prerequisites to the explicit ephemeral DB
idempotently: CREATE EXTENSION IF NOT EXISTS pgcrypto; create-or-widen
public.alembic_version.version_num to varchar(128) (create the table if absent, else ALTER
the column wider when it is shorter than 128); CREATE SCHEMA IF NOT EXISTS t_dev. The safety
guards are unchanged: skip when TEST_DATABASE_URL / DATABASE_URL is unset and refuse any URL
containing mpango_erp; the fixture never touches a shared / dev / prod DB. No migration,
env.py, conftest.py, runtime, model, API, service, frontend, package, lockfile, or baseline
file is changed -- only the two test files and this ledger.

Repro proof (P21-C1-R1): a fresh throwaway postgres:15-alpine container was started with NO
manual SQL applied; only TEST_DATABASE_URL, REPORTING_USER_PASSWORD, and
PYTHONIOENCODING=utf-8 were set. Running the two P21-C1 test files produced 37 passed,
0 failed -- the fixture bootstrapped the DB and the full base chain (001..019) plus the 020
migration applied cleanly. The tests are now self-contained and reproducible from a clean
container.

Risk (unchanged): MEDIUM by nature (schema work), mitigated to LOW realized blast radius
(additive, public-schema-only, reversible, 0 affected processes, self-contained ephemeral
verification).

## 12. Final statement

P21-C1 implements the additive, reversible, public-schema-only durable approval migration
and its real ephemeral-Postgres G1 / G2 tests. There is no runtime storage switch (P20-B
stays in-memory / existing-safe; runtime adapter wiring is P21-D), no execution of any
controlled action, no tenant mutation, no auth / RBAC rewrite, no model registration, no
frontend, no package / lockfile change, and no change to the configured secret baseline.
Approval is not execution, and durability is not execution. P21-D is not started.

## 13. P21-C1.1 merge readiness gate (2026-06-29)

P21-C1.1 merged the P21-C1 + P21-C1-R1 source branch into platform-dev after every
readiness gate passed. This section records that merge evidence.

- Gate: P21-C1.1 merge readiness gate (schema migration merge).
- Date: 2026-06-29.
- Source branch: codex/platform-p21c1-public-durable-approval-migration-2026-06-26.
- Source tip: 2149ef8 (short SHA; full SHA not pinned here so the ledger stays
  detect-secrets-clean).
- Target before: origin/platform-dev = b06b773 (local platform-dev == origin == b06b773,
  confirmed before merge; git fetch --all --prune run).
- Merge commit (--no-ff, NOT a squash, NOT a fast-forward): cfa0ea0 (short SHA); parents
  b06b773 (platform-dev before) + 2149ef8 (source tip); subject "merge: P21-C1 public
  durable approval migration".
- Target after: cfa0ea0 (merge), then this evidence commit (short SHA recorded in the
  session report; kept out of this file so the ledger stays non-self-referential).
- Changed files on the merge: exactly the four allowed files
  (020_durable_approval_store.py, the two G1 / G2 test files, and this ledger); 1314
  insertions, no deletions of pre-existing content.

Pre-merge gates (all PASS):
- git fetch --all --prune; origin/platform-dev == b06b773 (target had not moved); source
  HEAD == 2149ef8; merge-base(source, origin/platform-dev) == b06b773.
- Source diff vs origin/platform-dev == exactly the four allowed files.
- git diff --check origin/platform-dev..source: clean (exit 0).
- Non-ASCII scan of the four files: 0 hits.
- detect-secrets (detect-secrets-hook against the configured baseline) on the four files:
  PASS (exit 0); configured baseline unchanged.
- Forbidden path audit: 0 hits (no env.py, no runtime backend API / service / model, no
  frontend, no auth / RBAC / session, no package / lockfile, no configured baseline, no
  product-dev-recovered).

37-test throwaway-DB proof (self-contained, no manual SQL):
- A fresh throwaway postgres:15-alpine container was started; NO SQL was applied by hand.
  Only TEST_DATABASE_URL / DATABASE_URL, REPORTING_USER_PASSWORD, and PYTHONIOENCODING=utf-8
  were set. The session bootstrap fixture applied the test-only prerequisites (pgcrypto,
  widened public.alembic_version, t_dev) to the explicit ephemeral DB.
- Command (from backend/): pytest tests/test_platform_p21_durable_approval_schema.py
  tests/test_platform_p21_durable_approval_migration.py -q
- Result: 37 passed, 0 failed.
- The throwaway container was torn down; the developer databases mpango_postgres and
  mpango_prod_postgres were untouched, and no shared / production database was contacted.

Public-only and reversibility proof (carried from the source):
- Public-mode only: no alembic or pytest command passed -x tenant_schema.
- G2 test_upgrade_does_not_create_tenant_schema: the schema set is unchanged by the
  public-mode upgrade; G2 test_no_durable_objects_in_tenant_schemas: no durable_approval_*
  object exists outside public.
- G2 test_downgrade_drops_only_p21_objects + test_reupgrade_recreates_tables: downgrade
  removes only the five tables + fifteen enum types and leaves the base inventory intact;
  re-upgrade recreates the five tables.

Post-merge gates on the merge commit (all PASS):
- git diff --check HEAD~1..HEAD: clean (exit 0).
- Forbidden path audit on HEAD~1..HEAD: 0 hits (only the four allowed files).
- Non-ASCII scan on the merged files: 0 hits.
- detect-secrets (detect-secrets-hook against the configured baseline): PASS (exit 0).
- npx gitnexus analyze: success (7,709 nodes / 23,659 edges / 503 clusters / 300 flows;
  node / cluster counts fluctuate slightly across re-indexes; the stable metric is 300
  flows).
- GitNexus detect_changes compare vs origin/platform-dev (the pre-merge target): LOW risk,
  docs+schema-only, 0 affected processes (changed_count 38, affected_count 0, changed_files
  4, risk_level low; affected_processes []). No product / tenant / auth / payment execution
  flow is affected.

Pushed to: origin/platform-dev (single push carrying the merge commit plus this evidence
commit).

Risk: MEDIUM by nature (schema work), mitigated to LOW realized blast radius (additive,
public-schema-only, fully reversible, 0 affected processes, self-contained ephemeral-DB
verification with 37 passing tests).

Status after P21-C1.1: the durable approval migration is MERGED into platform-dev. There is
no runtime storage switch (P20-B stays in-memory / existing-safe; runtime adapter wiring is
P21-D), no execution of any controlled action, no tenant mutation, no auth / RBAC rewrite,
no frontend, no model registration, and no AI agent execution. P21-D is not started.
Approval is not execution, and durability is not execution.
