# MPANGO_TENANT_BOOTSTRAP_DB_AUTHORITY_R1_R2 — V3 Merge-Critical Evidence Pack

- **Authorization:** CTO-AUTH-TENANT-BOOTSTRAP-DB-AUTHORITY-R1-R2-2026-09-16
- **Executor:** ZCode-W
- **Base:** `5ee42a982a9d6132b4557fe4cd9f945334a608f6` (R1-R1 manifest commit)
- **Verification tier:** V3_MERGE_CRITICAL_DATA_INTEGRITY_SECURITY
- **Claim ceiling:** CORRECTED_SOURCE_CANDIDATE_ONLY
- **Machine:** Windows 10.0.26200 x64, Docker 29.1.3, TWO fresh
  `postgres:16.15` clusters per run (cluster ids in `harness_report.json`)

## Required fixes → implementation map

1. **Frozen endpoint binding before ANY first-deployment write.**
   `_assert_cluster_binding` Layer 1 now compares host:port of ALL THREE
   URLs (admin, migrate, app) — not just migrate vs app. A first-deploy
   mis-wiring (admin on cluster A, migrate/app on cluster B) is refused at
   the URL layer before a single connection is made to B.
2. **Deferred connection only on catalog-proven valid state.** When
   migrate/app endpoints are not connectable, the admin catalog must prove
   exactly one of two shapes before any write:
   - (a) fully fresh first deployment: target database AND both roles
     absent → deferred allowed, roles+database created on the admin
     endpoint, full live binding re-asserted immediately after creation;
   - (b) established deployment adding a database: BOTH roles exist and
     only the database is absent → the credentials are verified FIRST by a
     live authentication probe of each role against the maintenance
     database (bound current_user checked); only then is the database
     created.
   Refused shapes (zero writes): exactly one role exists (partial role
   set), the target database already exists while URLs are unconnectable,
   or the credential probe fails.
3. **True first-deploy cross-cluster counterexample:**
   `test_first_deploy_cross_cluster_refused_zero_writes` — admin URL on the
   second (virgin) cluster, migrate/app URLs on the main cluster: refused
   with `frozen endpoint` and ZERO additions on BOTH clusters.
4. **Partial-exists and wrong-password counterexamples:**
   - `test_partial_exists_first_deploy_refused_zero_writes`: only the
     migration role pre-exists (run-unique role names so the persistent
     second cluster never collides) → refused `is not fresh (partial role
     set ...)`, zero writes;
   - `test_wrong_password_provision_refused_zero_writes`: existing roles +
     database with a wrong migrate password → refused `is not fresh (target
     database ... already exists)`, zero writes (no database recreated, no
     half-finished state).
5. **Credential hygiene with synthetic-secret proof.** All diagnostics now
   render host:port and role names only — the netloc rendering is deleted.
   The harness embeds a random synthetic secret token in EVERY password
   (admin/migrate/app/reporting/second-admin), runs everything, then scans
   all 18 evidence files for the token: `synthetic_secret_scan =
   files_containing_secret: 0` (recorded in `harness_report.json`). Suite
   assertions (`_assert_no_credentials_leaked`) additionally prove per-
   counterexample that neither the password, a DSN (`postgresql://`), nor
   `@` (netloc/userinfo) appears in any CLI output. Mutation-run logs mask
   the token in place (`***SYNTHETIC-SECRET-REDACTED***`) while keeping the
   leak location visible.
6. **Runtime no-CREATE-on-public in the PRODUCT bootstrap.**
   `_assert_ledger_guard_function_authority` now also checks
   `has_schema_privilege(current_user, 'public', 'CREATE')` and refuses —
   before CREATE SCHEMA, with zero tenant objects — when the runtime can
   create/replace objects in the migration-owned public schema.
   `test_runtime_with_public_create_refused_zero_tenant` grants CREATE as
   the authority, expects the refusal, and proves the exact attempted
   tenant schema is absent (finally-revoked).
7. **Three new semantic mutations** (all named-RED, byte-identical restore;
   MM1–MM4 from R1-R1 retained):
   - **MM5 binding refusal matrix deleted** (`deferral_allowed = True`,
     `if False:`) → RED `test_wrong_password_provision_refused_zero_writes`
     (its `is not fresh` semantic assertion fires);
   - **MM6 netloc leak restored** → RED
     `test_cluster_binding_mismatch_zero_writes` +
     `test_first_deploy_cross_cluster_refused_zero_writes` (their
     credential-hygiene assertions fire);
   - **MM7 public-CREATE check deleted** → RED
     `test_runtime_with_public_create_refused_zero_tenant` +
     `test_bootstrap_script_keeps_fail_closed_precondition_semantics`.
   Mutation runs are now ISOLATED (previous mutation restored before the
   next is applied) and after ALL mutations both scripts are proven
   byte-identical (sha256 recorded, grouped form) with a green post-restore
   v3_ok run.
8. **Full rerun:** six scenario suites GREEN on fresh PG16 (full public
   lifecycle as the runtime role, four original negatives, the R1-R1
   verify counterexample, the new R1-R2 counterexamples), tool `--verify`
   rc=0 / rc=2, and the BASE-vs-candidate bootstrap-heavy regression in an
   identical two-role topology: **104/104 per-node outcomes, deltas=0**.
9. **Scope:** only the two scripts, the V3 suite, the harness and
   ledger/evidence changed. No migrations, SKU, SMTP, order, payment or
   frontend changes.
10. **Successor commit:** normal commit from BASE, no amend/rebase/force;
    pushed with local==remote proof recorded in the journal.

## Review-blocker closure (three blockers)

| Blocker | Closure |
| --- | --- |
| P0 first-provision wrote before refusing | Layer-1 frozen endpoint binding (all three URLs) refuses pre-connection; deferred writes only after catalog-proven shape (a)/(b); counterexamples 3+4 prove zero writes |
| P1 credentials in diagnostics | netloc rendering deleted; synthetic-secret scan 0/18 files; per-test leak assertions; MM6 proves the assertion load-bearing |
| P1 product bootstrap missed public-CREATE | precondition check added before CREATE SCHEMA with zero-tenant counterexample; MM7 proves load-bearing |

## Reproduce from zero

```
cd backend
<venv-python> scripts/v3_tenant_bootstrap_db_authority_harness.py \
    --evidence-dir <this directory>
```
