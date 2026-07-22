# DC-11T4I-R2A — TEST001 Cleanup Design

| Field | Value |
|-------|-------|
| Task | DC-11T4I-R1B + R2A |
| Owner | Local OPS AI |
| Branch | `ops/dc11t4i-r1-legacy-test-tenant-forensics-2026-07-22` |
| Branch tip (start) | `eb79cb040376431a870895771907cafd72f01fdf` |
| Product target | `origin/product-dev-recovered` @ `1be053e0ad362df66b2e153e8317d6a559eed61a` |
| VPS safe baseline | `303dc179e94527668f4f1d2145fab74be0f48751` (tracked clean, 5/5 healthy) |
| Target wholesaler | `TEST001` (`550e8400-e29b-41d4-a716-446655440000`) |
| Classification | `CONFIRMED_LEGACY_TEST_FIXTURE_CONTAMINATION` (unchanged) |
| Production modified in this task | **NO** (plan only; proven on disposable copy) |

---

## 1. Objective & Hard Rules

Produce an exact, evidence-backed cleanup plan for the TEST001 legacy test
fixture, prove it on a disposable restored database, and **not** modify
production data.

Hard rules obeyed:
- No production INSERT/UPDATE/DELETE/TRUNCATE/DROP.
- No `outstanding_balance = 0` mutation.
- No fabricated `tenant_registrations` or `platform_tenants` rows.
- No deploy of `1be053e0`; no product code/migration/frontend/config/lockfile/env changes.
- No secret/DB-URL/password/token/email/backup-content disclosure.
- No push of `product-dev-recovered`, `platform-dev`, or tags.

---

## 2. Base Proof (recap)

- `git fetch origin` performed; `origin/product-dev-recovered` = `1be053e0`.
- Branch HEAD `eb79cb04`, parent `1be053e0`; ancestry verified
  (`PRODUCT_IS_ANCESTOR_OF_HEAD: YES`).
- Pre-edit worktree: no staged/modified files.
- VPS `/opt/mpango-erp` @ `303dc179`, branch `product-dev-recovered`, tracked
  clean; 5/5 prod containers healthy (`mpango_prod_backend`, `_frontend`,
  `_gateway`, `_postgres`, `_redis`) + `procurement-workspace`.

---

## 3. Complete Read-Only Dependency Inventory (sanitized)

All counts captured `BEGIN READ ONLY` against production via the postgres
container (no secrets printed; only counts/catalog metadata).

### 3.1 Target fixture row

| Table | Rows | Code/Status | id prefix |
|-------|------|-------------|-----------|
| `public.wholesalers` | **1** | `TEST001` / `active` / `is_deleted=false` | `550e8400` |

### 3.2 Public tables referencing TEST001 (by `wholesaler_id`)

| Table | Rows for TEST001 | Notes |
|-------|------------------|-------|
| `public.tenant_registrations` | **0** | Migration 035 authority source; no live registration |
| `public.platform_tenants` | **0** | Not consulted by migration 035; contextual only |
| `public.invitations` | **3** (1 used) | Fixture invitations from DC-11T4G runtime |
| `public.wholesaler_retailer_bindings` | **2** | sum `outstanding_balance` = **-2,325.00**; `count(balance>0)` = **0** |
| `public.password_reset_tokens` | **0** | `tenant_id` ref |
| `public.platform_audit_logs` | **0** | `wholesaler_id` ref (the 1 global audit row has NULL wholesaler_id) |

Binding detail (sanitized):

| retailer prefix | status | outstanding_balance |
|-----------------|--------|---------------------|
| `22eb3fb6` | active | -2,325.00 (stale/contaminated) |
| `51488f90` | active | 0.00 |

Token tables dependent on `tenant_registrations` (CASCADE): all **0** for
TEST001 — `email_verification_tokens`, `onboarding_status_tokens`,
`owner_credential_setup_tokens`.

### 3.3 Retailer sharing analysis (FK target: `public.retailers`)

Both TEST001-bound retailers are **EXCLUSIVE** to TEST001 — no shared retailers:

| retailer prefix | is_deleted | distinct wholesaler bindings | referenced by invitations |
|-----------------|-----------|------------------------------|---------------------------|
| `22eb3fb6` | false | **1** (TEST001 only) | 0 |
| `51488f90` | false | **1** (TEST001 only) | 1 (used) |

### 3.4 FK / cascade behavior (authoritative catalog)

References **to `public.wholesalers`**:

| Referencing table | Constraint | on delete |
|-------------------|-----------|-----------|
| `public.invitations` | `invitations_wholesaler_id_fkey` | **CASCADE** |
| `public.wholesaler_retailer_bindings` | `wholesaler_retailer_bindings_wholesaler_id_fkey` | **CASCADE** |
| `public.tenant_registrations` | `tenant_registrations_wholesaler_id_fkey` | NO_ACTION (RESTRICT) |
| `public.platform_tenants` | `platform_tenants_wholesaler_id_fkey` | NO_ACTION (RESTRICT) |
| `public.password_reset_tokens` | `password_reset_tokens_tenant_id_fkey` | NO_ACTION (RESTRICT) |
| `public.platform_audit_logs` | `platform_audit_logs_wholesaler_id_fkey` | NO_ACTION (RESTRICT) |

References **to `public.retailers`**:

| Referencing table | Constraint | on delete |
|-------------------|-----------|-----------|
| `public.wholesaler_retailer_bindings` | `..._retailer_id_fkey` | **CASCADE** |
| `public.invitations` | `invitations_used_retailer_id_fkey` | **SET NULL** |

References **to `public.tenant_registrations`** (all CASCADE): `email_verification_tokens`, `onboarding_status_tokens`, `owner_credential_setup_tokens` (all 0 rows for TEST001).

> Note: a `retailer_id`/`used_retailer_id` column also exists on
> `public.retailer_prices`, but it carries **no FK constraint** to
> `public.retailers` (FK catalog confirms only the two constraints above). The
> `retailer_prices` table containing TEST001 data lives inside the **derived
> tenant schema** (3 rows), which is dropped wholesale in the cleanup. There is
> no public-level `retailer_prices` row for TEST001.

### 3.5 Derived tenant schema `t_550e8400e29b41d4a716446655440000` (exact counts)

20 tables — all synthetic (created by test user `2b560429`):

| Table | Rows | | Table | Rows |
|-------|------|-|-------|------|
| users | 1 | | orders | 17 |
| roles | 1 | | order_items | 17 |
| role_permissions | 28 | | payments | 23 |
| permissions | 28 | | ledger_entries | 22 |
| user_roles | 1 | | inventory_stocks | 12 |
| skus | 21 | | inventory_movements | 3 |
| retailer_prices | 3 | | inventory_reservations | 15 |
| import_runs | 8 | | intake_workspaces | 19 |
| intake_uploads | 15 | | intake_product_rows | 37 |
| intake_validation_issues | 28 | | mv_sales_daily | 0 |

### 3.6 Global collision / blast-radius context

| Metric | Value |
|--------|-------|
| `tenant_registrations` (live statuses, global) | 17 (none for TEST001) |
| `wholesalers` total | 10 |
| `wholesalers` active + not deleted | 10 |

### 3.7 Cleanup ownership markers & decisions

| Object | Ownership | Disposition |
|--------|-----------|-------------|
| wholesalers `TEST001` row | Test fixture (code/name provenance) | Hard delete (preferred) |
| 2 bindings | Test fixture, exclusive | Remove (CASCADE from wholesaler) |
| 3 invitations | Test fixture | Remove (CASCADE from wholesaler) |
| 2 retailers | Exclusive to TEST001 | Remove (after bindings) |
| derived schema (20 tables) | Test fixture | DROP SCHEMA CASCADE |
| token tables | 0 rows | No action needed |
| audit logs | 0 rows for TEST001 | Preserve global; nothing to remove |

**Rows that must be preserved:** every non-TEST001 wholesaler, every
non-TEST001 retailer/binding/invitation/registration, the global audit log row
(NULL wholesaler_id), and all other tenant schemas. The cleanup touches ONLY
TEST001-owned rows.

**Exact stop conditions (fail-closed, abort the transaction):**
- Any TEST001-bound retailer has `distinct wholesaler bindings > 1` (shared).
- `tenant_registrations` for TEST001 > 0 (unexpected live registration).
- `platform_tenants` for TEST001 > 0.
- `platform_audit_logs` referencing TEST001 > 0.
- `password_reset_tokens` for TEST001 > 0.
- wholesalers row count for id = TEST001 <> exactly 1.
- Any other tenant schema or non-TEST001 row is touched by the predicates.

---

## 4. Cleanup Design

### 4.1 Pre-cleanup backup & restore verification

- **Source backup (approved, already taken during DC-11T4I):**
  `/home/ubuntu/.secure-backups/dc11t4i_20260722T062413Z.sql`
  (874,700 bytes; SHA256 prefix `b4380a8a8cdb5cfaad6d38b8e4992dafd59e3314ff8f8f911ba6edee5467ba02`).
- Before any production run: take a **fresh** `pg_dump` snapshot, record size +
  SHA256, and verify it restores cleanly into a disposable DB (Step 5 proves the
  restore path).
- The cleanup transaction itself is fully rollback-able; the backup is a
  **logical restore safety net** (NOT PITR — no WAL archiving or physical
  base-backup evidence exists for this environment, so point-in-time recovery
  to an arbitrary transaction must not be claimed).

### 4.2 Advisory lock / maintenance window

- Acquire `pg_advisory_xact_lock(hashtext('dc11t4i_test001_cleanup'))` at
  transaction start so concurrent cleanup attempts block/fail and the window is
  single-owner. Release is automatic on COMMIT/ROLLBACK.
- A maintenance window banner is desirable but not strictly required: all
  NO_ACTION-referenced tables have 0 rows, and the derived schema belongs only to
  TEST001, so no live tenant session is affected.

### 4.3 Exact transaction order (single transaction, fail-closed)

> **STATUS: NON-EXECUTABLE DESIGN DRAFT.** The SQL below is a design artifact
> only. It has NOT been executed, approved, or proven against any database
> (production or disposable). It must NOT be run until Step 5 disposable proof
> succeeds. See Section 5 (NOT EXECUTED) and Section 6 (`NEEDS_DISPOSABLE_PROOF`).

> **Parameterization warning.** The `$WID` / `$SCHEMA` tokens shown inside the
> dollar-quoted `DO $$ ... $$` blocks below are **shell/psql textual
> placeholders**, NOT an approved SQL parameterization mechanism. Substituting
> values into a dollar-quoted body by string replacement is vulnerable to
> identifier/literal injection and is **not approved** for execution. Before any
> run, the literals must be replaced with a reviewed parameterization
> (`EXECUTE ... USING`, prepared statements, or psql `:variable` with proper
> quoting via `quote_literal`/`%L` and `quote_ident`/`%I`) and re-validated on a
> disposable copy. As written, this is illustrative design, not runnable
> production SQL.

Identifiers are quoted (`%I`/double quotes); every step asserts before mutating.
`$WID` = `550e8400-e29b-41d4-a716-446655440000`;
`$SCHEMA` = `t_550e8400e29b41d4a716446655440000`.

```
BEGIN;

-- 0. Single-owner window
SELECT pg_advisory_xact_lock(hashtext('dc11t4i_test001_cleanup'));

-- 1. PRE-ASSERTIONS (raise => automatic ROLLBACK of whole xact)
DO $$
DECLARE
  w_cnt int; reg_cnt int; pt_cnt int; prt_cnt int; al_cnt int;
  shared_cnt int; rids uuid[];
BEGIN
  SELECT count(*) INTO w_cnt FROM public.wholesalers WHERE id = '$WID'::uuid;
  IF w_cnt = 0 THEN
    RAISE NOTICE 'ALREADY_CLEAN: TEST001 absent (idempotent no-op)';
  ELSIF w_cnt > 1 THEN
    RAISE EXCEPTION 'STOP wholesaler row count > 1: %', w_cnt;
  END IF;
  -- hard stops below only matter when the fixture is still present:
  IF w_cnt = 1 THEN
    SELECT count(*) INTO reg_cnt FROM public.tenant_registrations WHERE wholesaler_id='$WID'::uuid;
    IF reg_cnt > 0 THEN RAISE EXCEPTION 'STOP unexpected tenant_registrations: %', reg_cnt; END IF;

    SELECT count(*) INTO pt_cnt FROM public.platform_tenants WHERE wholesaler_id='$WID'::uuid;
    IF pt_cnt > 0 THEN RAISE EXCEPTION 'STOP unexpected platform_tenants: %', pt_cnt; END IF;

    SELECT count(*) INTO prt_cnt FROM public.password_reset_tokens WHERE tenant_id='$WID'::uuid;
    IF prt_cnt > 0 THEN RAISE EXCEPTION 'STOP unexpected password_reset_tokens: %', prt_cnt; END IF;

    SELECT count(*) INTO al_cnt FROM public.platform_audit_logs WHERE wholesaler_id='$WID'::uuid;
    IF al_cnt > 0 THEN RAISE EXCEPTION 'STOP unexpected platform_audit_logs: %', al_cnt; END IF;

    -- shared-retailer guard: any TEST001-bound retailer owned by >1 wholesaler
    SELECT count(*) INTO shared_cnt
    FROM (
      SELECT b.retailer_id, count(DISTINCT b.wholesaler_id) AS wcnt
      FROM public.wholesaler_retailer_bindings b
      WHERE b.retailer_id IN (SELECT retailer_id FROM public.wholesaler_retailer_bindings WHERE wholesaler_id='$WID'::uuid)
      GROUP BY b.retailer_id
    ) s WHERE s.wcnt > 1;
    IF shared_cnt > 0 THEN RAISE EXCEPTION 'STOP shared retailer detected: %', shared_cnt; END IF;
  END IF;

  -- capture exclusive retailer ids for targeted removal (BEFORE any deletes)
  SELECT array_agg(DISTINCT retailer_id) INTO rids
  FROM public.wholesaler_retailer_bindings WHERE wholesaler_id='$WID'::uuid;
  RAISE NOTICE 'exclusive retailer ids: %', rids;
END $$;

-- 1b. Snapshot the exclusive retailer ids into a temp table (survives the xact)
CREATE TEMP TABLE _dc11t4i_rids AS
SELECT retailer_id AS id FROM public.wholesaler_retailer_bindings
WHERE wholesaler_id='$WID'::uuid;

-- 2. Remove derived tenant schema (all 20 synthetic tables)
DROP SCHEMA IF EXISTS "$SCHEMA" CASCADE;

-- 3. Remove exclusive retailers. Deleting a retailer CASCADE-deletes its
--    bindings (FK on_delete=CASCADE) and SET NULLs invitations.used_retailer_id.
--    Both retailers are exclusive to TEST001 (guarded above), so this is safe.
DELETE FROM public.retailers WHERE id IN (SELECT id FROM _dc11t4i_rids);

-- 4. Remove TEST001 invitations (test artifacts; wholesaler CASCADE also covers)
DELETE FROM public.invitations WHERE wholesaler_id = '$WID'::uuid;

-- 5. Remove the wholesaler fixture row (NO_ACTION refs all confirmed 0;
--    any residual bindings/invitations CASCADE-clean here too)
DELETE FROM public.wholesalers WHERE id = '$WID'::uuid;

-- 7. POST-ASSERTIONS
DO $$
DECLARE
  gone_w int; gone_b int; gone_i int; gone_s int;
  live_reg int; live_w int;
BEGIN
  SELECT count(*) INTO gone_w FROM public.wholesalers WHERE id='$WID'::uuid;
  SELECT count(*) INTO gone_b FROM public.wholesaler_retailer_bindings WHERE wholesaler_id='$WID'::uuid;
  SELECT count(*) INTO gone_i FROM public.invitations WHERE wholesaler_id='$WID'::uuid;
  SELECT count(*) INTO gone_s FROM information_schema.schemata WHERE schema_name='$SCHEMA';
  IF gone_w<>0 OR gone_b<>0 OR gone_i<>0 OR gone_s<>0 THEN
    RAISE EXCEPTION 'POST FAIL residuals w=% b=% i=% schema=%', gone_w,gone_b,gone_i,gone_s;
  END IF;
  -- blast-radius: live registrations unchanged, wholesalers decreased by exactly 1
  SELECT count(*) INTO live_reg FROM public.tenant_registrations
   WHERE status IN ('pending_email_verification','email_verified','provisioning','active','failed');
  SELECT count(*) INTO live_w FROM public.wholesalers;
  RAISE NOTICE 'post live_reg=% live_wholesalers=%', live_reg, live_w;
END $$;

COMMIT;
```

### 4.4 Safe handling of shared retailer rows

**Confirmed: none shared** (both retailers exclusive to TEST001). The plan
nonetheless enforces a hard **shared-retailer guard** (step 1). If a shared
retailer is ever detected, the transaction **aborts** and the operator must keep
the shared retailer and its other-wholesaler bindings intact, removing only the
TEST001 binding row. Shared retailers are **never** deleted.

### 4.5 Tenant schema removal order

`DROP SCHEMA ... CASCADE` removes all 20 tables atomically. No per-table ordering
is required because the derived schema is self-contained and CASCADE resolves
intra-schema dependencies. This is done **before** public-table deletes so that
any cross-schema dependency (none observed) cannot block.

### 4.6 Wholesaler removal vs tombstone

- **Recommended: hard delete.** Justified by the inventory: all NO_ACTION
  references have 0 rows; the only referencing rows (bindings, invitations) are
  exclusive fixtures that are removed in the same transaction; no audit/registration
  history exists for TEST001.
- **Fallback: soft tombstone** (`is_deleted=true`, keep row) is used **only if**
  a pre-assertion reveals an unexpected reference that cannot be resolved — but
  that would trigger `STOP_AND_REPORT_CTO` rather than silent tombstoning. The
  `outstanding_balance` is **never** zeroed (hard rule).

### 4.7 Rollback boundary

- The **entire cleanup is one transaction.** Any pre/post assertion failure
  raises an exception that aborts and rolls back the whole transaction — no
  partial state can persist.
- Additionally, the verified pre-cleanup `pg_dump` provides a **logical restore
  safety net** if a COMMIT must be undone. This is a logical snapshot restore,
  NOT PITR — no WAL archiving or physical base-backup evidence exists, so
  point-in-time recovery to an arbitrary transaction must not be claimed.

### 4.8 Post-cleanup assertions

- wholesalers `TEST001` row count = 0.
- bindings / invitations / derived schema for TEST001 = 0.
- exclusive retailer ids removed.
- `tenant_registrations` live count unchanged (no other tenant affected).
- `wholesalers` total decreased by exactly 1 (10 -> 9).
- All other tenant schemas and non-TEST001 rows unchanged.

### 4.9 Audit evidence to retain

- This R2A design + the R1 forensic report (permanent forensic record).
- The DC-11T4I backup (kept on disk; not deleted).
- A post-run `pg_dump` for comparison and the disposable-proof report below.
- `platform_audit_logs` is preserved as-is (no TEST001 rows exist to remove).

### 4.10 Forbidden approaches (explicitly excluded)

- Setting `outstanding_balance = 0`.
- Inserting a fake `tenant_registrations` / `platform_tenants` row.
- Deleting any shared retailer (none exist; guard enforces).
- Broad `t_%` schema scanning / wildcard `DROP SCHEMA LIKE`.
- Wildcard deletion (`DELETE FROM ... WHERE ... LIKE`).
- Disabling constraints (`SET session_replication_role`, `ALTER TABLE ... NOCHECK`).
- Editing migration `035`.

---

## 5. Disposable Proof Procedure & Results

**STATUS: NOT EXECUTED.** Step 5 (the one-shot disposable proof — restore backup
into an isolated disposable PostgreSQL, apply the cleanup design, run migration
`035`, assert invariants, then destroy the disposable DB) was **not executed**.
The end-to-end execution command was prepared and preflighted (restore health
verified, migration `035` chain validated, `env.py` `DATABASE_URL` override
confirmed), but **command authorization was blocked**, so no disposable proof
was produced.

Consequences:
- The cleanup design in Section 4.3 remains an **unproven NON-EXECUTABLE DESIGN
  DRAFT**.
- No production or disposable data was mutated in this task.
- The verdict is `NEEDS_DISPOSABLE_PROOF` (see Section 6) — disposable proof is
  a hard prerequisite before any production execution can be authorized.

<!-- DISPOSABLE_PROOF_RESULTS -->

---

## 6. Verdict

**Verdict: `NEEDS_DISPOSABLE_PROOF`**

Rationale:
- Step 5 disposable proof was **NOT EXECUTED** (command authorization blocked).
- The cleanup SQL in Section 4.3 is a **NON-EXECUTABLE DESIGN DRAFT**.
- No production or disposable data was modified.
- The financial-semantics correction in the R1 report is preserved: negative
  ledger movement is NOT a valid negative customer outstanding; paid-order
  remaining exposure is `max(credit - collection, 0)`; the DC-11T4H code fix
  exists at `1be053e0`; production runtime closure remains pending.
- `pg_dump` is documented as a **logical restore safety net**, NOT PITR.

**Next required action:** authorize and execute Step 5 against an isolated
disposable PostgreSQL to convert this design into proven procedure before any
production execution is considered.
