# DC-2M1 Legacy Tenant Reconciliation Forward-Migration Design Gate

Date: 2026-07-12
Branch: `opencode/dc2m1-legacy-tenant-reconciliation-design-2026-07-12`
Baseline: `origin/product-dev-recovered @ 458c0219ddea27fef9754e67521402d145743161`
Status: `DESIGN_READY_FOR_CTO_REVIEW` (revised by DC-2M1-R1; see the "DC-2M1-R1 CTO Design Corrections" section)

## Scope

This gate is design and test planning only. It does not modify production code, Alembic migrations, tenant bootstrap code, frontend code, configuration, lockfiles, deployed infrastructure, or VPS state.

The confirmed gap is in legacy tenant reconciliation: a tenant schema can already have `retailer_prices` with the correct business uniqueness on `(retailer_id, sku_id)` but under a noncanonical legacy name. Current reconciliation requires the canonical name `uq_retailer_prices_retailer_sku`; when that name is absent, G1 fails and the same reconcile run never reaches the reporting reconciliation that should ensure `mv_sales_daily` and `idx_mv_sales_daily_u1` exist.

## Non-Negotiable Decision

Historical migration `017_retailer_prices.py` must not be modified.

Reasons:

- It is already part of the historical Alembic chain and may have run in existing environments.
- Rewriting history would make database state depend on when an environment first migrated.
- The safe repair is a new forward migration plus matching reconciliation/test coverage.

## Current Contract Summary

`backend/alembic/versions/017_retailer_prices.py` defines the tenant table contract:

- Table: `retailer_prices`
- Required columns include `id`, `retailer_id`, `sku_id`, `price`, audit columns, and soft-delete columns.
- Required unique constraint name: `uq_retailer_prices_retailer_sku`
- Required check constraint name: `ck_retailer_prices_positive_price`
- Required indexes: `ix_retailer_prices_retailer_id`, `ix_retailer_prices_sku_id`

`backend/alembic/versions/013_s6_2_materialize_sales.py` defines the sales materialized view contract:

- Materialized view: `mv_sales_daily`
- Unique index: `idx_mv_sales_daily_u1` on `(transaction_date, reporting_currency_code)`
- The unique index is required for `REFRESH MATERIALIZED VIEW CONCURRENTLY`.

`backend/scripts/bootstrap_tenant_schema.py` currently runs reconciliation in this order:

1. `_reconcile_payments`
2. `_reconcile_retailer_prices`
3. `_reconcile_reporting`
4. `_reconcile_import_runs`
5. `_reconcile_intake_tables`

Therefore, G1 must not stop on a compatible legacy unique name, or G2 is blocked in the same run.

## Forward-Migration Design

Create a new forward migration after the current head:

- File: `backend/alembic/versions/031_legacy_tenant_reconciliation.py`
- Revision: `031_legacy_tenant_reconciliation`
- Down revision: `030_platform_backup_status_source`
- Mode: public Alembic run that discovers tenant schemas; do not run with `-x tenant_schema`.

The migration must iterate tenant schemas that are eligible for reconciliation. Eligibility should be conservative:

- Include schemas matching the tenant schema convention, such as `t_%`.
- For G1, operate only when `retailer_prices` exists.
- For G2, operate only when `ledger_entries` exists, because the materialized view depends on it.
- If a schema has neither object, skip it as not relevant to this repair.

### G1: Legacy `retailer_prices` Unique Name Compatibility

The migration must validate the existing `retailer_prices` table before changing it.

Required validation:

- Required columns exist.
- Column types are compatible with migration `017` expectations.
- Required non-null columns are non-nullable.
- `price` is `numeric(12,2)`.
- Existing canonical constraints, if present, match the expected definition.
- Existing same-name indexes, if present, match the expected definition.
- Existing data has no duplicate `(retailer_id, sku_id)` pairs.
- Existing data has no rows violating `price > 0` before adding or validating the check constraint.

Repair behavior:

- If `uq_retailer_prices_retailer_sku` exists and is exactly a unique constraint over `(retailer_id, sku_id)`, leave it untouched.
- If the canonical unique constraint is absent but the table shape and data are compatible, add the canonical unique constraint with `ALTER TABLE ... ADD CONSTRAINT uq_retailer_prices_retailer_sku UNIQUE (retailer_id, sku_id)`.
- Do not drop or rename legacy noncanonical unique constraints in this slice. Keeping the legacy constraint preserves rollback simplicity and avoids destructive assumptions.
- If a compatible noncanonical unique constraint already exists, the canonical constraint may duplicate the same guarantee. That is acceptable for this repair because it preserves all rows and creates the canonical contract required by code/tests.
- If the canonical name is already used for an incompatible object, fail closed.
- If duplicate data prevents adding the canonical unique constraint, fail closed and report the schema/table needing manual data resolution.

This approach is forward-compatible with old unique names because it does not require knowing every old name. It validates the table and data, then establishes the canonical named guarantee additively.

### G2: Continue To Reporting Reconciliation In The Same Flow

After G1 succeeds for a schema, the same migration flow must continue to reporting reconciliation for that schema.

Required G2 behavior:

- If `ledger_entries` exists and `mv_sales_daily` is missing, create `mv_sales_daily` with the same SQL shape as migration `013`.
- If legacy `rpt_sales_daily` exists and `mv_sales_daily` is missing, drop only the old view before creating the materialized view, matching migration `013` behavior.
- Always ensure `idx_mv_sales_daily_u1` exists and is a unique index over `(transaction_date, reporting_currency_code)`.
- If an index named `idx_mv_sales_daily_u1` exists with any incompatible definition, fail closed.
- Grant `SELECT` on `mv_sales_daily` to `reporting_role` after the object exists.
- If `reporting_role` is missing, fail closed because migration `011` should have created it.

The implementation test must prove that a legacy tenant with a noncanonical `retailer_prices` unique name and no `mv_sales_daily` is repaired in one run: the canonical unique constraint is present, `mv_sales_daily` is present, and `idx_mv_sales_daily_u1` is present.

## Idempotency And Data Preservation

The migration and bootstrap reconciliation changes must be repeatable.

Idempotency requirements:

- Running the migration twice must be a no-op after the first successful run.
- Running bootstrap reconciliation twice on the same tenant must be a no-op after the first successful run.
- Existing business rows in `retailer_prices`, `ledger_entries`, and all other tenant tables must remain intact.
- The migration must not delete, truncate, rewrite, or deduplicate business rows.

Data preservation rules:

- Never resolve duplicates automatically.
- Never coerce unknown column types automatically.
- Never silently replace incompatible constraints or indexes.
- Fail with a schema-qualified error message instead.

## Fail-Closed Rules

The implementation must raise and stop on unknown or incompatible structures, including:

- Missing required `retailer_prices` columns on an existing table.
- Nullable required columns.
- Incompatible `retailer_id`, `sku_id`, `price`, or audit column types.
- `price` precision/scale that is not `numeric(12,2)`.
- Duplicate `(retailer_id, sku_id)` pairs.
- `price <= 0` rows before check constraint enforcement.
- Canonical constraint name present with wrong columns or wrong constraint type.
- Canonical index name present with wrong uniqueness, columns, predicate, expression, or target relation.
- `mv_sales_daily` present as a non-materialized relation when a materialized view is required.
- `idx_mv_sales_daily_u1` present but not a unique index on `(transaction_date, reporting_currency_code)`.
- Missing `reporting_role` when reporting objects need grants.

Failure must happen before destructive changes. Error messages must identify the tenant schema and object.

## New-Tenant Bootstrap Behavior

New tenant bootstrap behavior must not change.

The existing `CREATE TABLE IF NOT EXISTS` path for a missing `retailer_prices` table already creates the canonical `uq_retailer_prices_retailer_sku` constraint. The next implementation slice must not change:

- Tenant schema naming.
- Onboarding claim/provisioning state transitions.
- RBAC seeding behavior.
- New tenant table list.
- Public `wholesalers` or `tenant_registrations` behavior.
- Frontend onboarding behavior.

Only the reconciliation branch for already-existing tenant objects should be changed.

## Next Implementation Slice Boundaries

Allowed files for the next implementation slice:

- `backend/alembic/versions/031_legacy_tenant_reconciliation.py`
- `backend/scripts/bootstrap_tenant_schema.py`
- `backend/tests/test_dc2m2_legacy_tenant_reconciliation_forward_migration.py`
- `backend/tests/test_u6h3_tenant_provisioning_reconcile_cleanup.py` only if existing reconcile tests need a new targeted case
- `backend/tests/test_payments_schema_contract.py` only if static contract coverage must be extended
- `ai-ledger/product-ai/2026-07-12_dc2m2_legacy_tenant_reconciliation_implementation.md`

Forbidden files for the next implementation slice:

- `backend/alembic/versions/017_retailer_prices.py`
- Any already-applied historical migration before `031`
- Frontend files
- Production compose/config/env files
- Lockfiles
- Onboarding API/service files unless CTO explicitly expands scope
- Auth, RBAC, pricing API, reporting API, or dashboard runtime logic unless CTO explicitly expands scope

Migration numbering strategy:

- Use exactly one new revision after the current head: `031_legacy_tenant_reconciliation`.
- Do not branch the Alembic graph.
- Do not edit old revisions.
- The migration should be additive and schema-repair oriented.

Rollback boundary:

- Downgrade may drop only objects introduced by `031` when safe, primarily the canonical duplicate `uq_retailer_prices_retailer_sku` added by the migration and `idx_mv_sales_daily_u1` / `mv_sales_daily` only when they were created by this migration.
- Downgrade must not drop or alter legacy noncanonical constraints.
- Downgrade must not delete business rows.
- Downgrade must not attempt to restore broken legacy drift.
- Operational rollback for a failed deploy is application rollback plus database restore/snapshot if the migration already committed in production.

## Test Matrix For Next Slice

Static tests:

- Verify migration `031` exists and has `down_revision = '030_platform_backup_status_source'`.
- Verify migration `017_retailer_prices.py` is unchanged from baseline.
- Verify forbidden files are not changed.
- Verify bootstrap source still creates new `retailer_prices` with canonical `uq_retailer_prices_retailer_sku`.
- Verify migration source contains no row-deleting operations for tenant business tables.

Unit-style helper tests:

- Existing canonical unique constraint: pass and remain idempotent.
- Legacy noncanonical unique constraint over `(retailer_id, sku_id)`: add canonical constraint and preserve rows.
- Missing unique constraint with no duplicates: add canonical constraint and preserve rows.
- Missing unique constraint with duplicates: fail closed before changes.
- Canonical unique name with wrong definition: fail closed.
- Unknown or incompatible column type: fail closed.
- Existing compatible check constraint: pass.
- Missing check constraint with all positive prices: add or validate canonical check.
- Missing check constraint with nonpositive rows: fail closed.

Integration tests with PostgreSQL:

- Create a tenant schema with legacy `retailer_prices` using an unnamed or noncanonical unique constraint, existing business rows, `ledger_entries`, no `mv_sales_daily`, and no `idx_mv_sales_daily_u1`. Run the migration. Assert canonical unique constraint exists, row count is unchanged, `mv_sales_daily` exists, and `idx_mv_sales_daily_u1` is unique.
- Run the migration a second time. Assert no errors and no row changes.
- Create a tenant schema where `idx_mv_sales_daily_u1` exists with an incompatible definition. Assert migration fails closed.
- Create a tenant schema where `mv_sales_daily` exists as a standard view or table. Assert migration fails closed unless the implementation explicitly handles that case safely.
- Bootstrap reconciliation test: create a partial failed tenant schema with noncanonical `retailer_prices` uniqueness and missing reporting objects, then run `bootstrap`. Assert the same run reaches both G1 and G2.

New-tenant regression tests:

- Fresh bootstrap still creates all expected tenant tables.
- Fresh bootstrap still creates canonical `retailer_prices` constraint directly.
- Fresh bootstrap still creates `mv_sales_daily` and `idx_mv_sales_daily_u1`.
- Tenant provisioning reconcile still does not seed RBAC/admin rows unexpectedly.
- Complete schema provisioning still does not rerun bootstrap unnecessarily.

Validation commands for next slice:

- `poetry run pytest tests/test_dc2m2_legacy_tenant_reconciliation_forward_migration.py -q`
- `poetry run pytest tests/test_payments_schema_contract.py -q --tb=short`
- `poetry run pytest tests/test_u6h3_tenant_provisioning_reconcile_cleanup.py -q --tb=short`
- `poetry run pytest tests/test_u1r1_bootstrap_completeness.py -q --tb=short`
- `git diff --check`
- ASCII and mojibake scan on changed files and added diff lines
- `pre-commit run --files <changed files>`
- `npx gitnexus analyze`
- `npx gitnexus status`

## Risk Assessment

Risk: Medium.

Reasons:

- The change touches tenant schema reconciliation and database DDL.
- It must run against potentially drifted legacy schemas.
- It is data-preserving and additive, but database DDL failures can stop deployment if incompatible drift exists.

Risk controls:

- Fail closed on unknown/incompatible structures.
- Preserve all business rows.
- Keep historical migration `017` immutable.
- Use a new forward migration only.
- Test both migration and bootstrap reconciliation paths.
- Keep new-tenant bootstrap behavior unchanged.

## DC-2M1-R1 CTO Design Corrections

Date: 2026-07-12 (revision R1)
Branch: `opencode/dc2m1-legacy-tenant-reconciliation-design-2026-07-12`
Revises: commit `c9714c1bdfc10daf17c9c4581a14bd1250c19ec1`
Baseline: `origin/product-dev-recovered @ 458c0219ddea27fef9754e67521402d145743161` (unchanged; verified no drift)
Scope of this revision: design text only. No production code, migration, bootstrap, test,
frontend, config, or lockfile is modified. This revision tightens and, where noted,
overrides the original design above. Where the original text and this section disagree,
THIS SECTION GOVERNS for DC-2M2 implementation.

The four corrections below are mandatory for DC-2M2.

### Correction 1. Authoritative Tenant Schema Enumeration and Safe Identifiers

The original design said eligibility "should be conservative" and gave `t_%` as an example.
That is rejected. The DC-2M2 implementation MUST NOT discover tenants by scanning schemas.

1.1 Sole authoritative source of tenant schemas.

- The single authoritative source is the public registry, read from `public.tenant_registrations`
  joined to `public.wholesalers`. A schema is "registered/active" only when BOTH hold:
  (a) a `tenant_registrations` row with `status IN (LIVE_REGISTRATION_STATUSES)` AND a
      non-null `tenant_schema` (the partial unique index `ux_tenant_registrations_tenant_schema`
      guarantees at most one registration per schema); AND
  (b) a matching `wholesalers` row whose derived tenant schema equals that value and whose
      `wholesalers.status` indicates an active/provisioned tenant.
- `LIVE_REGISTRATION_STATUSES` / `TENANT_REGISTRATION_STATUSES` (defined in
  `backend/models/tenant_onboarding.py`) are the only acceptable status filters. The
  implementation must read these constants from the model, not hardcode a copy.

1.2 Explicit exclusions (mandatory).

- MUST NOT enumerate schemas via `LIKE 't_%'`, `information_schema.schemata`, `pg_namespace`,
  or any directory-style scan.
- MUST exclude test schemas (`t_test`, `t_dev`, `t_u1r1_test`, and any schema not present in
  the registry result).
- MUST exclude deleted / cancelled / expired / never-completed registrations
  (`status` not in the live set), and any registration whose `tenant_schema` is NULL or empty.
- MUST exclude any `tenant_schema` value that is not a valid, single PostgreSQL identifier
  matching the system's tenant-schema naming rule (the same derivation used by
  `wholesalers.get_tenant_schema()`).

1.3 Safe identifiers (mandatory; no exceptions).

- Every dynamic schema, table, index, constraint, and role identifier used in generated SQL
  MUST be produced through a database-side quote-ident mechanism, never by Python string
  interpolation/concatenation.
- Acceptable mechanisms: `quote_ident(<name>)` executed server-side, or
  `format('%I', <name>)` executed server-side, with the rendered SQL parameterized for all
  values. Identifiers must be quoted even when they appear "safe".
- Tenant-table and tenant-object names that are fixed by the contract (e.g.
  `retailer_prices`, `mv_sales_daily`, `idx_mv_sales_daily_u1`,
  `uq_retailer_prices_retailer_sku`, `reporting_role`) are constants and are also passed
  through the same quote-ident path for uniformity, but they are never data-derived.

1.4 Fail-closed for identifier problems.

- If a registered `tenant_schema` is illegal (not a valid identifier), duplicated across two
  registrations, missing from `pg_namespace` (registered but the schema object is absent),
  or otherwise unresolvable, the migration MUST fail closed for that tenant with a
  schema-named, non-sensitive error, and MUST NOT execute any DDL in that schema.
- A tenant schema that exists in the registry but whose schema object is missing is itself a
  fail-closed condition: the migration must not silently create or assume the schema.

### Correction 2. G1 Constraint Compatibility Policy

The original design allowed adding a second, duplicate canonical unique constraint alongside
a compatible legacy one. That is rejected as sloppy. The DC-2M2 G1 logic MUST first attempt a
safe rename of an exactly-equivalent legacy constraint to the canonical name, and only add a
new constraint when no equivalent exists.

2.1 Exact definition of "business-equivalent legacy unique constraint".

A legacy object on `retailer_prices` qualifies as business-equivalent to the canonical
`uq_retailer_prices_retailer_sku` if and only if ALL of the following are true, verified from
catalog evidence (`pg_constraint` / `pg_index`), not from name guessing:

- The containing relation is exactly `retailer_prices` in this tenant schema.
- The object is a UNIQUE CONSTRAINT (`pg_constraint.contype = 'u'`), not a unique index
  without a constraint, not a primary key, not an exclusion constraint.
- The constraint's column set is EXACTLY `(retailer_id, sku_id)` in that order, resolved by
  `pg_constraint.conkey` -> `pg_attribute.attname` (compare by name, not by attnum).
- It is NOT a partial unique constraint: `pg_constraint.conpredid IS NULL` and there is no
  predicate / WHERE clause.
- The constraint is valid: `pg_constraint.convalidated = true` (for a `u` constraint this is
  the expected state).
- Column types are compatible with migration `017`: `retailer_id` and `sku_id` are
  `uuid` (non-nullable); `price` is `numeric(12,2)`.

Any deviation (extra columns, wrong columns, wrong order, partial predicate, invalidated,
wrong type, or a same-named object of the wrong kind) means NOT equivalent.

2.2 Repair decision tree (in order, per tenant schema).

- (a) If `uq_retailer_prices_retailer_sku` already exists and satisfies 2.1 exactly: no-op
      (canonical already present). G1 succeeds for this schema.
- (b) Else if exactly one legacy constraint satisfies 2.1 (business-equivalent) AND the
      canonical name is free (no object of any kind named
      `uq_retailer_prices_retailer_sku`): rename that legacy constraint to the canonical
      name via `ALTER TABLE ... RENAME CONSTRAINT <legacy> TO uq_retailer_prices_retailer_sku`.
      This is the preferred path: it avoids creating a second index for the same guarantee.
- (c) Else if NO legacy constraint satisfies 2.1 AND the canonical name is free AND the data
      has no duplicate `(retailer_id, sku_id)` pairs: add the canonical unique constraint with
      `ALTER TABLE ... ADD CONSTRAINT uq_retailer_prices_retailer_sku UNIQUE (retailer_id, sku_id)`.
- (d) Else: fail closed (see 2.3).

2.3 Mandatory fail-closed conditions for G1 (do not auto-fix, do not skip).

The migration MUST fail closed and stop (no partial success) when, for a tenant schema:

- The canonical name `uq_retailer_prices_retailer_sku` is occupied by an INCOMPATIBLE object
  (wrong columns/order/type, non-unique, partial, invalidated, or wrong object kind).
- More than one legacy constraint satisfies the 2.1 equivalence test (ambiguous; the rename
  target is undefined).
- A legacy constraint satisfies 2.1 but the canonical name is occupied by a different object,
  so the rename cannot proceed.
- The `retailer_prices` table is missing required columns, has wrong column types, or has
  nullable required columns.
- Duplicate `(retailer_id, sku_id)` business rows exist (the canonical uniqueness cannot be
  established without changing business data).
- Any row has `price <= 0` / NULL where the `ck_retailer_prices_positive_price` check would
  be violated.
- The `ck_retailer_prices_positive_price` check exists with an incompatible definition.

On any fail-closed the migration must: report the tenant schema name and a non-sensitive
reason (e.g. "duplicate (retailer_id, sku_id) rows", "canonical name occupied by
non-unique index"), and MUST NOT rewrite, deduplicate, delete, or type-coerce any business
data, and MUST NOT drop or alter the legacy constraint.

2.4 Catalog evidence strategy (required; no information_schema short-cuts).

- Columns/types/nullability: `pg_attribute` + `pg_type` + `pg_attrdef` (NOT
  `information_schema.columns`, which can misreport on tenant schemas).
- Constraints: `pg_constraint` (contype, conkey, convalidated, conpredid).
- Indexes: `pg_index` (indisunique, indisvalid, indkey, indpredicate) cross-referenced to
  `pg_constraint.conindid` so that a constraint-backed unique index is attributed to its
  constraint, not double-counted.
- Data duplicates: `SELECT retailer_id, sku_id, COUNT(*) ... GROUP BY ... HAVING COUNT(*) > 1`.
- Price violations: `SELECT COUNT(*) FROM ... WHERE price IS NULL OR price <= 0`.
- All data-count queries are read-only and run in the preflight (see Correction 3).

### Correction 3. DDL Locks, Execution Model, and Failure Handling

3.1 Transaction and timeout strategy.

- The migration runs each tenant schema's G1+G2 work inside its own transaction with explicit:
  - `lock_timeout` (short, e.g. 3-5s) so a contended table cannot hang the run;
  - `statement_timeout` (bounded, e.g. 30-60s) so a slow scan cannot hang the run.
- Both are set per-transaction via `SET LOCAL` so they do not leak beyond the migration.
- A cluster-wide advisory lock (e.g. `pg_advisory_xact_lock(<hashed app:key>))`) serializes
  the whole migration so two concurrent runs (e.g. two boots) cannot interleave DDL on the
  same tenant objects.

3.2 Read-only preflight BEFORE any DDL.

- Before writing anything, run a single read-only preflight across ALL registered tenant
  schemas that classifies each as: OK / INCOMPATIBLE / NEEDS_REPAIR, and for NEEDS_REPAIR
  records the planned action (rename legacy / add canonical / create MV+index / grant).
- The preflight MUST output a desensitized report: tenant schema names + non-sensitive
  classifications + planned action only. No business values, prices, row contents, emails,
  or tokens.
- If ANY registered schema is INCOMPATIBLE (Correction 2.3 / 3.4 conditions), the migration
  MUST stop and fail closed; it MUST NOT silently skip an incompatible schema, MUST NOT mark
  a partial run as successful, and MUST NOT proceed to DDL on other schemas in the same run
  unless the CTO explicitly authorizes a "continue past incompatible" mode (not the default).

3.3 Single-tenant incompatibility handling.

- Incompatibility is detected in preflight; no DDL is issued for an incompatible schema.
- The error surface is: schema name + non-sensitive reason + the catalog fact that triggered
  it (e.g. "retailer_prices.uq_retailer_prices_retailer_sku is a non-unique index").
- The migration does not attempt automatic repair of incompatible structures.

3.4 Production execution window, backup, recovery ownership.

- Execution window: a maintenance window with no onboarding/signup traffic (signup path may
  trigger provisioning/reconcile). Coordinate so no concurrent `bootstrap_tenant_schema` runs.
- Backup precondition: a verified DB backup/snapshot MUST exist before running `031` in
  production (the DC-1C runbook pattern). Record backup path/size/SHA256 prefix only.
- Recovery ownership: rollback is application-version rollback plus DB restore/snapshot
  restore (see Correction 4). The migration itself is forward-only.

3.5 G1 -> G2 continuation in the same flow (per schema).

- Within a single tenant schema, after G1 succeeds (canonical unique constraint present and
  valid), the same migration transaction continues to G2 for that schema:
  - Ensure `mv_sales_daily` exists as a MATERIALIZED VIEW with the migration-013 SQL shape.
    If a legacy `rpt_sales_daily` view exists and `mv_sales_daily` is absent, drop only that
    legacy view then create the materialized view (matches migration 013).
  - Ensure `idx_mv_sales_daily_u1` exists as a UNIQUE index over
    `(transaction_date, reporting_currency_code)`.
  - Grant `SELECT` on `mv_sales_daily` to `reporting_role`.
- G2 fail-closed conditions (stop, no partial success): `mv_sales_daily` exists as a
  non-materialized relation (table/standard view); `idx_mv_sales_daily_u1` exists with a
  non-unique / wrong-column / partial definition; `reporting_role` does not exist
  (migration 011 should have created it); `ledger_entries` is missing so the MV cannot be
  defined. Any of these fails the schema closed and the migration stops per 3.2.
- G1 and G2 for one schema run in one transaction; if G2 fails after G1 succeeded, the
  transaction rolls back so the schema is not left half-reconciled.

### Correction 4. Rollback and Test Boundaries

4.1 Forward-only repair; no promised automatic downgrade.

- This legacy-tenant DDL reconcile is a FORWARD-ONLY repair. The DC-2M2 migration MUST NOT
  promise a reliable automatic `downgrade()`. A best-effort downgrade may drop only objects
  this migration created (the canonical constraint it added, the MV/index it created), and
  only when it can prove it created them; it MUST NOT attempt to reverse a safe rename
  (renaming back to the original legacy name is not reliable and is forbidden), MUST NOT
  drop legacy noncanonical constraints, and MUST NOT delete business rows.

4.2 Real rollback strategy.

- The only supported rollback is: application-version rollback (deploy the previous app
  build) PLUS restore from a verified pre-migration database backup/snapshot. This must be
  stated in the migration docstring and the implementation ledger.

4.3 down_revision is fixed.

- The new migration's `down_revision` MUST be the current single head
  `030_platform_backup_status_source`. Historical migration `017_retailer_prices.py` is
  immutable and is NOT the down_revision. The new revision id is `031_legacy_tenant_reconciliation`
  (or the next legal number if `031` is taken by a merged change at implementation time; in
  that case STOP_AND_REPORT_CTO).

4.4 DC-2M2 mandatory test coverage (must all pass before the slice can be merged).

The implementation tests MUST prove each of the following; any missing case is a blocker:

- Fresh bootstrap is unchanged: a brand-new tenant still gets all canonical objects
  (`retailer_prices` + `uq_retailer_prices_retailer_sku` + check + indexes; `mv_sales_daily`
  + `idx_mv_sales_daily_u1`; `reporting_role` SELECT).
- One-shot legacy DDL repair: a tenant with a legacy noncanonical unique constraint on
  `(retailer_id, sku_id)`, real business rows, and no reporting objects is fully repaired in
  a single run (canonical constraint via safe rename per 2.2(b), MV + unique index + grant).
- Idempotent second run: a second run on the same repaired tenant is a no-op (no errors, no
  row changes, no duplicate objects).
- Canonical already present: when `uq_retailer_prices_retailer_sku` already satisfies 2.1,
  G1 is a no-op and G2 still proceeds.
- Legacy equivalent constraint is safely normalized: per 2.2(b) the legacy constraint is
  RENAMED (not duplicated); assert no second unique index is created.
- Fail-closed cases (each must raise and stop, no DDL, no data change):
  - duplicate `(retailer_id, sku_id)` business data;
  - wrong column type (e.g. `retailer_id` as text);
  - canonical name occupied by an incompatible object (e.g. a non-unique index);
  - `mv_sales_daily` exists as a standard view/table (G2 incompatible);
  - `idx_mv_sales_daily_u1` exists with a non-unique/wrong definition (G2 incompatible).
- Business-row preservation: `retailer_prices` and `ledger_entries` row counts and content
  hashes are identical before and after a successful run.
- G1 -> G2 same-flow success: after G1 repair, G2 completes in the same run for the same
  schema (MV + index + grant present).
- Tenant isolation: a schema that is NOT in the public registry (e.g. an orphan `t_%`
  schema, or a test schema) is never touched, even if it contains a `retailer_prices` table.
- Registry-gated enumeration: a registration whose `status` is not live, or whose
  `tenant_schema` is NULL, is never enumerated.

### Correction 5. DC-2M2 Slice Boundaries (definitive)

Allowed files for DC-2M2 (this list replaces the original "Next Implementation Slice
Boundaries"):

- `backend/alembic/versions/031_legacy_tenant_reconciliation.py` (new migration).
- `backend/scripts/bootstrap_tenant_schema.py` (reconcile branch only; new-tenant path unchanged).
- `backend/tests/test_dc2m2_legacy_tenant_reconciliation_forward_migration.py` (new).
- `backend/tests/test_u6h3_tenant_provisioning_reconcile_cleanup.py` (only if a new targeted reconcile case is required).
- `backend/tests/test_payments_schema_contract.py` (only if static contract coverage must be extended).
- `ai-ledger/product-ai/2026-07-12_dc2m2_legacy_tenant_reconciliation_implementation.md` (new ledger).

Forbidden files for DC-2M2:

- `backend/alembic/versions/017_retailer_prices.py` and every historical migration `< 031`.
- Frontend, production compose/config/env, lockfiles.
- Onboarding API/service, auth, RBAC, pricing API, reporting API, dashboard runtime logic
  (unless CTO explicitly expands scope in writing).
- The authoritative status constants in `backend/models/tenant_onboarding.py` must be READ,
  not redefined or moved.

Migration numbering strategy: exactly one new revision `031_legacy_tenant_reconciliation`
chained on the single current head `030_platform_backup_status_source`; do not branch the
Alembic graph; do not edit old revisions. If `031` is already taken at implementation time,
STOP_AND_REPORT_CTO.

Risk (revised): Medium, unchanged in level but tightened in controls — registry-gated
enumeration (no `t_%` scan), safe quote-ident, read-only preflight, per-tenant fail-closed,
prefer-rename-over-duplicate, forward-only with backup-restore rollback.

Stop conditions for DC-2M2: (1) baseline `458c0219` has drifted; (2) head is no longer a
single head at `030_platform_backup_status_source`; (3) `031` is taken by another merged
change; (4) any required test case in 4.4 cannot be made to pass without touching a
forbidden file; (5) a registered tenant schema in production preflight is incompatible and
the CTO has not authorized continued execution.

## Evidence For This Design Gate

- `git diff --check`: passed.
- ASCII scan: passed; no non-ASCII matches in the report.
- Mojibake scan: passed; no mojibake matches in the report.
- `poetry run detect-secrets scan ..\ai-ledger\product-ai\2026-07-12_dc2m1_legacy_tenant_reconciliation_forward_migration_design.md`: passed with empty `results`.
- `poetry run pre-commit run --config ..\.pre-commit-config.yaml --files ..\ai-ledger\product-ai\2026-07-12_dc2m1_legacy_tenant_reconciliation_forward_migration_design.md`: passed, including `Detect secrets`.
- `npx gitnexus analyze`: repository indexed successfully; `12,444 nodes`, `37,590 edges`, `797 clusters`, `300 flows`.
- `npx gitnexus status`: indexed commit `458c021`, current commit `458c021`, status up to date.

## Verdict

DC-2M1-R1 final verdict: `PASS_FOR_CTO_DC2M2_IMPLEMENTATION`

The original `PASS_FOR_IMPLEMENTATION_PLANNING_REVIEW` is superseded. The four CTO
corrections (registry-gated enumeration with safe identifiers; exact G1 equivalence with
prefer-rename-over-duplicate and mandatory fail-closed; preflight + per-tenant DDL locks and
same-flow G1->G2; forward-only rollback with the DC-2M2 test matrix) are now captured and
govern DC-2M2. No remaining design decision requires CTO input before implementation begins;
the stop conditions in Correction 5 are the only valid reasons to escalate.
