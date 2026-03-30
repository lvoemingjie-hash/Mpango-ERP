# 2026-03-06 — Fix: Reporting Views Missing After Clean Deployment

**Role:** Backend Architect AI
**Severity:** CRITICAL (500 on all dashboard endpoints)
**Tag:** Post v0.2.1-rc4 hotfix

---

## Symptom

After a clean RC4 deployment (`docker compose down -v` → `alembic upgrade head` → `seed_demo_data.py`), all dashboard endpoints returned **500 Internal Server Error**:

```
asyncpg.exceptions.UndefinedTableError: relation "mv_sales_daily" does not exist
```

Affected endpoints:
- `/dashboards/kpi/summary`
- `/orders`
- `/inventory/stocks`

---

## Root Cause

Migrations **012** (`rpt_*` views) and **013** (`mv_sales_daily` materialized view) create views **only in tenant schemas that already exist at migration time**.

Deployment sequence was:

```
1. docker compose down -v          → DB wiped (zero tenant schemas)
2. alembic upgrade head            → migrations 012/013 find 0 schemas → skip view creation
3. seed_demo_data.py               → creates tenant schema t_a000...0001
                                      BUT does NOT create reporting views
```

Result: tenant schema has `ledger_entries` with data, but **no views/materialized views**.

---

## Fix Applied

Created hotfix script: `backend/scripts/fix_views.py`

### What It Does

1. Discovers all tenant schemas with `ledger_entries`
2. Creates `rpt_receivables_summary` (regular view)
3. Creates `rpt_cash_flow_daily` (regular view)
4. Drops `rpt_sales_daily` (if leftover) + creates `mv_sales_daily` (materialized view)
5. Creates unique index `idx_mv_sales_daily_u1` for `REFRESH CONCURRENTLY`
6. Grants `SELECT` to `reporting_role`

### Execution

```bash
docker compose -f docker-compose.prod.yml cp backend/scripts/fix_views.py backend:/app/scripts/fix_views.py
docker compose -f docker-compose.prod.yml exec -T -e PYTHONPATH=/app backend python /app/scripts/fix_views.py
```

### Output

```
=== Mpango ERP: Fix Reporting Views ===

  Found 1 tenant schema(s): ['t_a0000000000040008000000000000001']

  Processing schema: t_a0000000000040008000000000000001
    + rpt_receivables_summary (view)
    + rpt_cash_flow_daily (view)
    + mv_sales_daily (materialized view + unique index)
    + GRANT SELECT to reporting_role
  Done: t_a0000000000040008000000000000001

=== Fix Complete ===
```

---

## Verification

```sql
SELECT schemaname, viewname FROM pg_views WHERE schemaname LIKE 't_%';
--  t_a0000000000040008000000000000001 | rpt_receivables_summary  ✅
--  t_a0000000000040008000000000000001 | rpt_cash_flow_daily      ✅

SELECT schemaname, matviewname FROM pg_matviews WHERE schemaname LIKE 't_%';
--  t_a0000000000040008000000000000001 | mv_sales_daily           ✅
```

---

## Files Changed

| File | Action |
|------|--------|
| `backend/scripts/fix_views.py` | **Created** — one-off hotfix script |
| `backend/scripts/check_views.sh` | **Created** — DB verification helper |

---

## SQL Definitions (from migrations 012 + 013)

| View | Type | Source | Filter |
|------|------|--------|--------|
| `rpt_receivables_summary` | VIEW | `ledger_entries` | `account_type = 'receivable'` |
| `rpt_cash_flow_daily` | VIEW | `ledger_entries` | `account_type = 'cash'` |
| `mv_sales_daily` | MATERIALIZED VIEW | `ledger_entries` | `account_type = 'revenue'` |

---

## Long-Term Recommendation

The `seed_demo_data.py` script should invoke `fix_views.py` logic at the end, or the tenant schema bootstrap function should create reporting views. The current migration-time approach is a **race condition**: views depend on tenant schemas that don't exist yet during `alembic upgrade head`.

**Correct future deployment order:**

```
1. alembic upgrade head          → schema DDL only
2. seed_demo_data.py             → creates tenant + data
3. fix_views.py                  → creates views in populated schemas
```

Or better: integrate view creation into `_bootstrap_tenant_schema()`.

---

## Status

**RESOLVED** — Dashboard endpoints should now return data instead of 500.
