# ZCode-W R1 — Tenant bootstrap DB authority: runtime no longer owns or replaces the public ledger guard

- DATE=2026-09-16
- AUTHORIZATION_ID=CTO-AUTH-TENANT-BOOTSTRAP-DB-AUTHORITY-R1-2026-09-16
- BASE=2665f0ee019302291bfca1d3f579cf852bc633ff (kimi/public-provisioning-smtp-source-closure-2026-09-15 tip)
- EXECUTOR=ZCode-W
- VERIFICATION_TIER=V3_DATA_INTEGRITY_AND_PROVISIONING_AUTHORITY
- CLAIM_CEILING=TENANT_BOOTSTRAP_DB_AUTHORITY_ONLY
- NEXT_GATE=`KILO_TENANT_BOOTSTRAP_DB_AUTHORITY_SOURCE_AND_REAL_PG16_REVIEW`

## What changed

1. `backend/scripts/bootstrap_tenant_schema.py` — REMOVED the runtime
   `CREATE OR REPLACE FUNCTION public.prevent_ledger_modification()`; ADDED
   `_assert_ledger_guard_function_authority()` + `LedgerGuardAuthorityError`:
   an exact existence / signature (public, zero args, RETURNS trigger,
   plpgsql) / ownership (`MPANGO_MIGRATION_AUTHORITY_ROLE`, defaulting to the
   connected role for single-role deployments) / EXECUTE precondition run as
   the FIRST bootstrap statement, before `CREATE SCHEMA`, so a refusal leaves
   zero partial tenant objects. The tenant trigger still only REFERENCES the
   migration-owned function.
2. `backend/scripts/provision_runtime_db_roles.py` (NEW) — the only sanctioned
   minimum-grant declaration: `mpango_migrate` (NOSUPERUSER NOCREATEDB
   CREATEROLE — needed by migration 011) / `mpango_app` (NOSUPERUSER
   NOCREATEDB NOCREATEROLE), database owned by the authority, CONNECT+CREATE
   on the database, USAGE on public, DML+default privileges on public tables,
   EXECUTE on the guard function only. Every statement is checked against
   `FORBIDDEN_SQL_FRAGMENTS` (alter schema / owner to / grant all / alter
   function / admin/grant option / alter database); `--verify` re-checks the
   live cluster and probes that runtime cannot replace the guard.
3. NO changes to alembic migrations, deployment topology, docker-entrypoint,
   SKU/SMTP/order/payment behavior or frontend. Product diff = exactly the
   bootstrap script modified plus the new files below.

## V3 evidence (fresh PG16, machine-generated)

`ai-ledger/product-ai/evidence/2026-09-16_zcode_tenant_bootstrap_db_authority_r1/`
(README with reproduction; `harness_report.json`; per-scenario pytest logs;
per-DB tool `--verify` JSON).

- Fresh `postgres:16.15` container (cluster id 7685856202415009836);
  migrations run AS `mpango_migrate` to head `038_catalog_identity_vertical_slice`
  in 5 scenario databases; minimum grants applied AS the authority.
- v3_ok: full public lifecycle AS the runtime role `mpango_app`
  (signup 202 → verification mail → verify 200 (provisioning bootstrap runs
  as runtime) → setup 200 → login 200 → select-tenant 200 → /auth/me 200);
  tenant has all required tables, both reporting views (SELECT granted to
  reporting_role), `mv_sales_daily` + unique index `idx_mv_sales_daily_u1`;
  guard function OID + `pg_get_functiondef` sha256 + owner preserved across
  tenant creation; ledger INSERT allowed, UPDATE/DELETE refused with the
  migration-owned message; runtime refusal probes (CREATE OR REPLACE guard /
  ALTER FUNCTION OWNER / ALTER SCHEMA public OWNER / CREATE ROLE / CREATE
  DATABASE) all refused.
- Negatives (missing function / bad signature / runtime-owned function /
  revoked EXECUTE): verify-email fails closed at 503, registration never
  activated, zero wholesalers, zero partial schemas; direct `bootstrap()`
  raises `LedgerGuardAuthorityError`.
- Mutations: M1 (runtime CREATE OR REPLACE reintroduced) → named RED ×2;
  M2 (ownership precondition removed) → named RED ×3; both restored
  byte-identically (sha256 `a3ef3a4fd485f409658434784120aa1789ff35d55bc727d4ac2be6810d55fa3a`);
  post-restore v3_ok run GREEN.
- Regression: per-node pytest outcomes IDENTICAL to BASE across 7
  bootstrap-heavy suites (99 nodeids) on a migrated PG16 database.

## Notes for the reviewer

- `tests/conftest.py` and `tests/setup_test_schema.py` keep their own
  test-fixture DDL for the guard function (test-harness preparation under the
  test DB owner, outside the tenant-bootstrap claim ceiling; byte-untouched).
- PG16 facts: schema `public` is owned by `pg_database_owner`; `ALTER ...
  OWNER TO` requires SET ROLE membership (the wrongown state is induced by
  the cluster admin in the harness); `CREATE OR REPLACE FUNCTION` cannot
  change a return type.
- GitNexus impact before editing: `bootstrap` upstream CRITICAL
  (118 symbols; 50 direct) — production caller is the dynamic import from
  `services/tenant_provisioning_service.py` during verify-email provisioning;
  signature and idempotency contract unchanged.
