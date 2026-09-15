# MPANGO_TENANT_BOOTSTRAP_DB_AUTHORITY_R1 — V3 Data-Integrity Evidence Pack

- **Authorization:** CTO-AUTH-TENANT-BOOTSTRAP-DB-AUTHORITY-R1-2026-09-16
- **Executor:** ZCode-W
- **Base:** `2665f0ee019302291bfca1d3f579cf852bc633ff`
  (branch `zcode/tenant-bootstrap-db-authority-r1-2026-09-16`)
- **Verification tier:** V3_DATA_INTEGRITY_AND_PROVISIONING_AUTHORITY
- **Machine:** Windows 10.0.26200 x64, Docker 29.1.3, fresh
  `postgres:16.15` container per run (cluster
  `system_identifier` recorded in `harness_report.json`)

## What changed (product, bytes)

1. `backend/scripts/bootstrap_tenant_schema.py`
   - REMOVED the runtime `CREATE OR REPLACE FUNCTION
     public.prevent_ledger_modification()` DDL (the bootstrap no longer
     replaces or re-owns the migration-owned shared guard function; frozen
     decision 2).
   - ADDED `_assert_ledger_guard_function_authority(db)` +
     `LedgerGuardAuthorityError`: an exact existence / signature / ownership /
     EXECUTE precondition executed as the FIRST statement of every bootstrap,
     BEFORE `CREATE SCHEMA`, so a refusal leaves zero partial tenant objects
     (frozen decisions 4/5 and fail-closed clause).
     - existence: `to_regprocedure('public.prevent_ledger_modification()')`
     - exact signature: schema `public`, zero identity arguments,
       `RETURNS trigger`, `LANGUAGE plpgsql`
     - ownership: owner equals `MPANGO_MIGRATION_AUTHORITY_ROLE` when declared
       (two-role topology), else the connected role itself (single-role
       `docker-entrypoint` topology); any other owner — including a runtime
       role under a declared authority — is refused
     - privilege: `has_function_privilege(current_user, <oid>, 'EXECUTE')`
   - The tenant trigger still REFERENCES the migration-owned function
     (`EXECUTE FUNCTION public.prevent_ledger_modification()`), which is
     allowed by frozen decision 4 (tenant-owned trigger objects).
2. `backend/scripts/provision_runtime_db_roles.py` (NEW): the only sanctioned
   declaration of runtime grants.  Declarative statement vocabulary
   (`MINIMUM_GRANT_STATEMENTS`, `DATABASE_SCOPE_GRANT_TEMPLATES`,
   `RUNTIME_ROLE_DDL_TEMPLATE`), every statement checked against
   `FORBIDDEN_SQL_FRAGMENTS` (`alter schema`, `owner to`, `grant all`,
   `alter function`, `with admin/grant option`, `alter database`) before
   execution.  Creates `mpango_migrate` (NOSUPERUSER NOCREATEDB CREATEROLE —
   CREATEROLE is required by migration 011 which creates reporting_role) and
   `mpango_app` (NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION),
   application database OWNED BY the migration authority (on PG15+ this makes
   the authority own schema `public`; PG16 reports the owner as the pseudo
   role `pg_database_owner`), and applies exactly these minimum grants:
   `CONNECT` + `CREATE` on the database (the ONLY schema-level authority: it
   lets signup provisioning create tenant schemas), `USAGE` on `public`,
   DML on all public tables (+ default privileges), `USAGE/SELECT` on
   sequences, and `EXECUTE` on `public.prevent_ledger_modification()`.
   `--verify` re-checks the live cluster and probes that the runtime role
   cannot replace the guard.
3. NO changes to `alembic/versions/*`, deployment topology, docker-entrypoint,
   SKU/SMTP/order/payment behavior, or frontend.  `git diff --stat` for the
   product: exactly `backend/scripts/bootstrap_tenant_schema.py` modified plus
   the new scripts/tests listed below.

## New verification artifacts

- `backend/tests/test_tenant_bootstrap_db_authority.py` — V3 suite
  (static invariants always run; database scenarios run only when
  `MPANGO_DB_AUTHORITY_MANIFEST` + `MPANGO_DB_AUTHORITY_SCENARIO` are set, so
  ordinary suite runs are unaffected).  Zero-DDL doctrine: the suite creates
  no roles/databases/schemas itself; the harness prepares everything and the
  tenant schema is created by the PRODUCT's own verify-email provisioning
  path under test.
- `backend/scripts/v3_tenant_bootstrap_db_authority_harness.py` — the full
  pipeline (provision → migrate AS AUTHORITY → grants → breakage → suite × 5
  scenarios → mutations → byte-identical restore proof).

## Machine results (regenerate with the harness command below)

See `harness_report.json` for the authoritative run record and
`pytest_*.txt` for full per-scenario output.  Reproduce from zero:

```
cd backend
<venv-python> scripts/v3_tenant_bootstrap_db_authority_harness.py \
    --evidence-dir <this directory>
```

Recorded run: cluster `system_identifier` 7685856202415009836,
`postgres:16.15` (server_version_num 160015), alembic head
`038_catalog_identity_vertical_slice` in all five scenario databases,
`bootstrap_tenant_schema.py` sha256 (grouped 8-char form)
`a3ef3a4f d485f409 65843478 4120aa17 89ff35d5 5bc727d4 ac2be681 0d55fa3a`
(= the committed bytes = the post-mutation restored bytes).

| phase | result |
| --- | --- |
| fresh PG16 container | `postgres:16.15`, server_version_num 160015 |
| migrations as `mpango_migrate` | head `038_catalog_identity_vertical_slice` in all 5 scenario databases |
| runtime-role lifecycle (v3_ok) | signup 202 → verification mail captured → verify 200 (bootstrap executes AS `mpango_app`) → setup 200 → login 200 → select-tenant 200 → /auth/me 200; registration + wholesaler `active` |
| tenant content | 22 tables incl. all required; views `rpt_receivables_summary` + `rpt_cash_flow_daily` (`relkind v`, SELECT granted to `reporting_role`); `mv_sales_daily` (`relkind m`) + unique index `idx_mv_sales_daily_u1` |
| guard identity preserved | same pg_proc OID, same `pg_get_functiondef` sha256, owner `mpango_migrate` before/after tenant creation |
| ledger immutability | INSERT allowed; UPDATE and DELETE refused with the MIGRATION-owned function's message "Ledger entries are immutable" |
| runtime refusal probes | `CREATE OR REPLACE` guard, `ALTER FUNCTION ... OWNER`, `ALTER SCHEMA public OWNER`, `CREATE ROLE`, `CREATE DATABASE` all refused as `mpango_app` |
| negative scenarios | v3_nofunc / v3_badsig / v3_wrongown / v3_nopriv all fail closed (5/5 scenario suites rc=0): verify-email → 503, registration NOT active, zero wholesalers, zero partial schemas, direct `bootstrap()` raises `LedgerGuardAuthorityError` |
| mutation M1 | runtime `CREATE OR REPLACE` reintroduced → RED with 2 named nodeids (`test_r1_public_lifecycle_activates_tenant_as_runtime_role`, `test_mutation_m1_sentinel_reintroducing_runtime_replace_is_refused`), then byte-identical restore (sha256 equal) |
| mutation M2 | ownership precondition removed → RED with 3 named nodeids (`test_n3_runtime_owned_guard_function_fails_closed_zero_partial_tenant`, `test_mutation_m2_sentinel_ownership_precondition_is_load_bearing`, `test_bootstrap_script_never_replaces_or_reowns_public_guard`), then byte-identical restore (sha256 equal) |
| post-restore | unmuted v3_ok run GREEN again (rc=0) |

## Regression proof (bootstrap-heavy existing suites)

The change removes DDL the old bootstrap performed; existing suites that
bootstrap tenants could only be affected through the new precondition.
Measured on a disposable PG16 database (per-node outcome comparison,
7 bootstrap-heavy test files, 99 nodeids):

- virgin database: candidate totals identical to BASE
  (27 failed / 6 passed / 66 errors both) — these files were already
  not virgin-DB-self-sufficient on BASE (missing migrations/reporting_user);
- migrated database (alembic head as the same role — the docker-entrypoint
  topology): per-node outcomes IDENTICAL between BASE and candidate
  (every PASSED/FAILED/ERROR/XFAIL nodeid matched exactly).

## Scope discipline

- `tests/conftest.py` and `tests/setup_test_schema.py` keep their own test
  fixture DDL for the shared guard function: they are test-harness
  preparation executed under the TEST database's own owner role (which is
  also the alembic role there), not the runtime provisioning path.  They are
  outside the tenant-bootstrap claim ceiling and were left byte-untouched.
- PG16 facts worth recording: `pg_database_owner` pseudo-role owns schema
  `public`; `ALTER ... OWNER TO` requires SET ROLE membership (the wrongown
  state is therefore induced by the cluster administrator in the harness —
  exactly the state a deployment that ran migrations as the wrong role
  produces); `CREATE OR REPLACE FUNCTION` cannot change a return type.
