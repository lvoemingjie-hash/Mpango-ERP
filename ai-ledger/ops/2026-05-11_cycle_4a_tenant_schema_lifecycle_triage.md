# Cycle 4A — Tenant Schema Lifecycle Triage and Minimal Fix

> Date: 2026-05-11
> Branch: `ops/integration-rehearsal-clean-2026-05-08`
> Worktree: `product-dev-recovered-review`
> Status: **FIX_READY_FOR_CTO_REVIEW**

---

## 0. Executive Summary

**Root cause**: Architectural gap between two tenant schema management mechanisms — Alembic migrations (dynamic, one-shot) and `bootstrap_tenant_schema.py` (static, idempotent-but-incomplete). The two never reconciled, leaving tenants created after key migrations ran in a partially-initialised state.

**Why this surfaced**: Lubuntu Stage 4B exposed a tenant schema lifecycle blocker — `t_dev` was missing reporting views/matviews and could have been missing payment columns (retailer_id, transaction_id) if the tenant had been bootstrapped by an older version of the script.

**Fix**: 1 file changed (`bootstrap_tenant_schema.py`). Added idempotent reconciliation that mirrors migrations 012/013/021. Windows/local targeted tests pass (67 total). Zero business logic touched.

**Promotion**: **Still paused.** This code fix requires Docker image rebuild + Lubuntu Stage 4C verification before promotion can proceed.

---

## 1. Diagnostic Objective Results

### 1.1 Does docker-entrypoint.sh call bootstrap_tenant_schema.py?

**YES.** Confirmed at `backend/docker-entrypoint.sh:28`:

```sh
alembic upgrade head                              # line 24: public migrations
python scripts/bootstrap_tenant_schema.py "${TENANT}"  # line 28: tenant bootstrap
exec uvicorn main:app --host 0.0.0.0 --port 8000  # line 31: start server
```

Order matters: Alembic runs first (public schema), then bootstrap creates/reconciles tenant schema. This means Alembic's dynamic tenant-schema migrations (011-013) only discover tenants that existed *before* this container start. Tenants created by bootstrap *during this start* miss them.

### 1.2 Does bootstrap have schema reconcile capability?

**NO (prior to this fix).** The script used exclusively `CREATE TABLE IF NOT EXISTS`, which is a complete no-op when a table already exists — even if the table is missing columns that the DDL specifies. No ALTER TABLE, no column checks, no view/matview creation existed.

### 1.3 Where are reporting views/matviews created?

**By Alembic public migrations 012 and 013**, which dynamically discover tenant schemas at runtime:

| Migration | Creates | Mechanism |
|-----------|---------|-----------|
| 012_s6_1_read_models | `rpt_sales_daily`, `rpt_receivables_summary`, `rpt_cash_flow_daily` | `CREATE OR REPLACE VIEW` in each discovered `t_*` schema |
| 013_s6_2_materialize_sales | `mv_sales_daily` (replaces `rpt_sales_daily` view) | `CREATE MATERIALIZED VIEW` + `idx_mv_sales_daily_u1` |

**bootstrap_tenant_schema.py did NOT create any reporting objects.** This means any tenant created by bootstrap *after* migrations 012/013 ran would have tables but no reporting layer.

**Evidence from Docker DB (Windows local):**

| Schema | Tables | Views | Matviews |
|--------|--------|-------|----------|
| `t_a0000000000040008000000000000001` | (exists) | `rpt_receivables_summary`, `rpt_cash_flow_daily` | `mv_sales_daily` |
| `t_test` | (exists) | `rpt_receivables_summary`, `rpt_cash_flow_daily` | `mv_sales_daily` |
| **`t_dev`** | 12 tables | **NONE** | **NONE** |

`t_dev` was created by bootstrap *after* 012/013 had already executed for the earlier tenants. It has zero reporting objects. This confirms the lifecycle blocker that Lubuntu Stage 4B exposed.

### 1.4 Can migration 021 execute on tenant schema?

**Not through normal `alembic upgrade head`.** Migration 021 checks `search_path` at runtime:

```python
# 021 upgrade()
is_tenant = any(part.strip().startswith("t_") for part in search_path.split(","))
if not is_tenant:
    return  # no-op on public schema
```

`alembic upgrade head` runs with default `search_path` (public), so 021 is permanently a no-op during normal startup. It can only execute if manually invoked with tenant search_path.

**However**, this gap is now bridged by the bootstrap reconciliation, which mirrors 021's logic exactly (add columns first, then indexes).

### 1.5 Stage 4B Failure Classification

| Failure Type | Root Cause | Classification |
|-------------|-----------|----------------|
| t_dev missing reporting views/matviews | bootstrap doesn't create them; migrations 012/013 ran before t_dev existed | **Product schema lifecycle defect** |
| 021 can't reconcile existing tenants | tenant-only check + public-only alembic upgrade | **Product schema lifecycle defect** |
| alembic_version stuck at 017 | Cycle 3D wrong-worktree stamping | **Test environment issue** (from Cycle 3D, documented in correction ledger) |
| Old tenant schema missing payment columns | bootstrap used `CREATE TABLE IF NOT EXISTS` which is a no-op for existing tables | **Product schema lifecycle defect** |

---

## 2. Why This Is NOT a B5 Seed Problem

The issue is not about individual test data or B5 test fixtures. The problem is the *mechanism* that ensures tenant schemas are complete. Lubuntu Stage 4B exposed that bootstrap had no reconcile capability — any tenant bootstrapped by an older version of the script would remain permanently out-of-date regardless of how seed data was constructed.

---

## 3. Why This Is NOT a Simple Environment Variable Problem

The gap is architectural, not configurational:

1. Two independent mechanisms (Alembic + bootstrap) both modify tenant schemas
2. Neither mechanism knows about the other's work
3. Alembic can't re-run for new tenants (single alembic_version in public)
4. Bootstrap didn't know about reporting objects (no reconcile)
5. 021 was designed to fix old tenants but can't execute through normal upgrade

No environment variable can bridge this gap. Code change was required.

---

## 4. Code Changes

### 4.1 File: `backend/scripts/bootstrap_tenant_schema.py`

**What changed:**

1. **Removed** the static `payment_indexes` block from `bootstrap()` (was lines 326-334 in original). This block ran unconditionally with `CREATE INDEX IF NOT EXISTS` but had an ordering problem: it could attempt `uq_payments_transaction_id` before `transaction_id` column existed on old tenant schemas.

2. **Rewrote** `_reconcile_payments()` with two-phase ordering:
   - **Phase 1 (columns)**: Add `retailer_id` → backfill → fail-fast orphans → set NOT NULL. Then add `transaction_id`.
   - **Phase 2 (indexes)**: After both columns guaranteed to exist, ensure `ix_payments_order_id` and `uq_payments_transaction_id` via `CREATE INDEX IF NOT EXISTS` / `CREATE UNIQUE INDEX IF NOT EXISTS`.

3. **Rewrote** `_reconcile_reporting()` with hard requirements:
   - **Verifies `reporting_role` exists** (created by migration 011). Raises `RuntimeError` if absent — this is an incomplete migration state, not a tolerable condition.
   - **Grants `USAGE ON SCHEMA`** to `reporting_role` before granting object-level `SELECT`.
   - **Always runs `CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_sales_daily_u1`** — even if `mv_sales_daily` already existed (handles case where matview was created by migration 013 but index was somehow missed).

**Functions added/modified:**

| Function | Purpose | Mirrors |
|----------|---------|---------|
| `_column_exists(db, schema, table, column)` | information_schema check for column presence | Helper |
| `_reconcile_payments(db, ts)` | Phase 1: columns (retailer_id, transaction_id). Phase 2: indexes via `CREATE INDEX IF NOT EXISTS` | Migration 021 |
| `_reconcile_reporting(db, ts)` | Schema USAGE grant → views → matview → index → SELECT grants. Fail-fast if reporting_role missing. | Migrations 011 + 012 + 013 |

### 4.2 GitNexus Impact Analysis

```
Target: Function:bootstrap_tenant_schema.py:bootstrap
Direction: upstream
Risk: LOW
d=1: main() (same file, calls bootstrap)
d=2: bootstrap_tenant_schema.py (file module)
Affected processes: 1 (Tests)
```

Only direct caller is `main()` in the same file. No external callers affected. Change is self-contained.

### 4.3 Files NOT Changed

- Zero business API files touched
- Zero test files touched
- Zero Alembic migration files touched
- Zero Docker configuration files touched

---

## 5. Test Results (Windows / Local)

### 5.1 Schema Contract Tests

```
tests/test_payments_schema_contract.py: 14 passed, 1 warning
```

All static DDL checks (bootstrap source analysis) and live DB checks pass.

### 5.2 Payment Tests

```
tests/test_payments_api.py:        5 passed
tests/test_payment_atomicity.py:   2 passed
tests/test_phase5_order_payment.py: 46 passed, 1 xfailed
                                   (53 passed, 1 xfailed total)
```

Zero regressions. The xfailed test is pre-existing and unrelated.

### 5.3 Live Bootstrap Verification

The modified `bootstrap_tenant_schema.py` could not be run against the live Docker DB because:
- The Docker container's image contains the OLD version of the file
- Host-to-DB direct connection requires credentials not available outside Docker

**This is exactly why Lubuntu Stage 4C verification is required after Docker rebuild.**

---

## 6. Outstanding Issues

### 6.1 alembic_version at 017

`public.alembic_version` is currently `017_retailer_prices` (corrupted during Cycle 3D wrong-worktree stamping). The correct value should be `021_tenant_payments_retailer_id_transaction_id`.

**Recommendation**: CTO to decide remediation strategy. Options:
- A) Stamp alembic_version to 021 if migrations 018-021 are already reflected in the actual schema
- B) Run `alembic upgrade head` and let 018-021 execute (may need manual review for idempotency)

### 6.2 t_dev Missing Reporting Objects

`t_dev` currently has zero reporting views/matviews. This will be fixed when:
1. Docker image is rebuilt with the updated bootstrap script
2. Container restarts, running bootstrap with reconcile
3. Lubuntu Stage 4C verifies the reporting objects are present

---

## 7. Promotion Assessment

**Promotion remains paused.**

This fix enables bootstrap to reconcile old tenant schemas, but:
1. The updated `bootstrap_tenant_schema.py` is only in source — not in a rebuilt Docker image
2. Lubuntu Stage 4B exposed this blocker — Lubuntu Stage 4C must verify the fix
3. `alembic_version` 017 → 021 remediation is a separate concern requiring CTO decision

**Next steps:**
1. CTO review of the reconciliation code
2. Docker image rebuild
3. Lubuntu Stage 4C verification
4. Decision on alembic_version remediation

---

## 8. CTO/Subagent Review Addendum

After the initial Cycle 4A fix, CTO review with GitNexus and an independent
Subagent found three hardening gaps. The source has been updated accordingly:

1. Reporting permissions now mirror migration 011 more closely for tenants
   created after migration 011:
   - `GRANT USAGE ON SCHEMA "{ts}" TO reporting_role`
   - `GRANT SELECT ON ALL TABLES IN SCHEMA "{ts}" TO reporting_role`
   - `ALTER DEFAULT PRIVILEGES IN SCHEMA "{ts}" GRANT SELECT ON TABLES TO reporting_role`

2. `_reconcile_payments()` now repairs partial prior runs. If `retailer_id`
   already exists but is still nullable, bootstrap always backfills NULLs from
   `orders.retailer_id`, fails fast on unresolved orphan payments, and then
   enforces `NOT NULL`.

3. Index reconciliation now validates existing same-name index definitions
   instead of trusting `CREATE INDEX IF NOT EXISTS`. If an incompatible
   `uq_payments_transaction_id`, `ix_payments_order_id`, or
   `idx_mv_sales_daily_u1` already exists, bootstrap fails fast and requires
   manual review.

GitNexus was refreshed before this review. Impact remained LOW:
`main -> bootstrap -> _reconcile_payments/_reconcile_reporting`, all inside
`backend/scripts/bootstrap_tenant_schema.py`.

Promotion remains paused until Docker rebuild plus Lubuntu Stage 4C confirms
the updated bootstrap actually reconciles a live DB tenant schema.
