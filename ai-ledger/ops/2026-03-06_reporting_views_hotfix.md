# 2026-03-06 — Reporting Views Hotfix Deployment

**Role:** OPS AI
**Context:** Dashboard 500 errors post-RC4 clean deployment

---

## Symptom

After clean RC4 deployment (`docker compose down -v` → `alembic upgrade head` → `seed_demo_data.py`):

```
asyncpg.exceptions.UndefinedTableError: relation "mv_sales_daily" does not exist
```

---

## Root Cause

Migrations 012/013 create views only in tenant schemas that exist at migration time. After `down -v`, zero tenant schemas exist → views never created. Seed script creates tenant schema AFTER migrations.

---

## Deployment Steps

### 1. Git Sync (Already Done)
```bash
git commit -m "fix(backend): add fix_views.py to recreate reporting views post-seed"
git push origin main
# Commit: 27bda96
```

### 2. VPS Pull
```bash
ssh root@143.110.177.2
cd /root/mpango-erp
git pull origin main
```

### 3. Execute Hotfix
```bash
docker compose -f docker-compose.prod.yml exec -T -e PYTHONPATH=/app backend python /app/scripts/fix_views.py
```

---

## Execution Output

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
  Views created: rpt_receivables_summary, rpt_cash_flow_daily
  Materialized:  mv_sales_daily (WITH DATA)
```

---

## Verification

```sql
SELECT schemaname, viewname FROM pg_views WHERE schemaname LIKE 't_%';
-- t_a0000000000040008000000000000001 | rpt_receivables_summary  ✅
-- t_a0000000000040008000000000000001 | rpt_cash_flow_daily      ✅

SELECT schemaname, matviewname FROM pg_matviews WHERE schemaname LIKE 't_%';
-- t_a0000000000040008000000000000001 | mv_sales_daily           ✅
```

---

## Status

**RESOLVED** — Dashboard endpoints should now return 200 instead of 500.
