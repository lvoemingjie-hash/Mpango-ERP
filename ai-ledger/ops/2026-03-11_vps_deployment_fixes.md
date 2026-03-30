# 2026-03-11 VPS Deployment Fixes

**Date**: 2026-03-11 16:56 (UTC+08:00)  
**Operator**: Cascade (OPS AI)  
**Target**: VPS 143.110.177.2  
**Version**: v0.2.3-r1

---

## Summary

Deployed v0.2.3-r1 to VPS with two operational fixes required:

1. **Alembic version mismatch** — Database state inconsistent with version marker
2. **Missing schema permissions** — `reporting_user` lacked USAGE on tenant schemas

---

## Issue 1: Alembic Version Mismatch

### Symptom

Backend container failed to start with error:
```
relation "sys_jobs" already exists
```

### Root Cause

During initial deployment, I incorrectly stamped `alembic_version` from `006` directly to `016`, skipping migrations `007-015`. However, the database already had tables from migrations `008-011` (`sys_jobs`, `sys_audit_logs`, `sys_reports`).

### Analysis

| Table | Exists | Migration |
|-------|--------|-----------|
| `sys_jobs` | ✅ | 008 |
| `sys_audit_logs` | ✅ | 009 |
| `sys_reports` | ✅ | 010 |
| `reporting_role` | ✅ | 011 |
| `rpt_sales_daily` | ❌ | 012 |
| `mv_sales_daily` | ❌ | 013 |

Actual database version: **011**

### Fix

1. Reset `alembic_version` to correct value (`011_s6_p_reporting_role`)
2. Run `alembic upgrade head` to execute migrations `012-016`
3. Verified `mv_sales_daily` materialized view created in both tenant schemas

```sql
-- Correct version
UPDATE alembic_version SET version_num = '011_s6_p_reporting_role';
```

```bash
alembic upgrade head
# Created rpt_sales_daily views (012)
# Created mv_sales_daily materialized views (013)
# Ran remaining migrations (014-016)
```

---

## Issue 2: Missing Schema Permissions

### Symptom

Dashboard API returned 500 error:
```
UndefinedTableError: relation "mv_sales_daily" does not exist
```

### Root Cause

`reporting_user` (used by Dashboard API for read-only BI queries) did not have `USAGE` privilege on tenant schemas (`t_a0000000000040008000000000000001`, `t_dev`).

Even though `mv_sales_daily` existed in tenant schemas, PostgreSQL could not find it because the user couldn't access the schema.

### Analysis

```sql
-- Before fix
SELECT has_schema_privilege('reporting_user', 't_a0000000000040008000000000000001', 'usage');
-- Result: f (false)

-- Materialized view existed
SELECT schemaname, matviewname FROM pg_matviews;
-- t_a0000000000040008000000000000001 | mv_sales_daily
-- t_dev                              | mv_sales_daily
```

### Fix

Granted `USAGE` on tenant schemas to `reporting_role`:

```sql
GRANT USAGE ON SCHEMA t_a0000000000040008000000000000001 TO reporting_role;
GRANT USAGE ON SCHEMA t_dev TO reporting_role;
```

### Verification

```sql
-- After fix
SELECT has_schema_privilege('reporting_user', 't_a0000000000040008000000000000001', 'usage');
-- Result: t (true)

-- Query succeeded
SET search_path TO t_a0000000000040008000000000000001, public;
SELECT * FROM mv_sales_daily LIMIT 1;
-- transaction_date | reporting_currency_code | daily_revenue | transaction_count
-- 2026-03-10       | USD                     |    17600.0000 |                 4
```

---

## Final Verification

### Service Status

```
NAME                   STATUS
mpango_prod_backend    Up (healthy)
mpango_prod_frontend   Up (healthy)
mpango_prod_gateway    Up (healthy)
mpango_prod_postgres   Up (healthy)
mpango_prod_redis      Up (healthy)
```

### API Tests

| Endpoint | Status | Result |
|----------|--------|--------|
| `/health` | 200 | `{"status":"healthy"}` |
| `/auth/login` | 200 | Identity JWT issued |
| `/auth/select-tenant` | 200 | Contextual JWT issued |
| `/api/v1/orders` | 200 | 2 orders returned |
| `/dashboards/kpi/summary` | 200 | KPI cards returned |

### KPI Data

```json
{
  "Total Revenue": 17600.00 USD,
  "Outstanding Receivables": 5300.00 USD,
  "Net Cash Position": 12300.00 USD
}
```

---

## Lessons Learned

1. **Alembic stamp vs upgrade**: Never skip migrations by stamping version. Always run `alembic upgrade head` to execute all pending migrations.

2. **Schema permissions for reporting**: When creating new tenant schemas, ensure `reporting_role` gets `USAGE` privilege. This should be added to the tenant bootstrap process.

3. **Database state verification**: Before stamping version, verify actual database state by checking for tables/views created by each migration.

---

## Access

- **URL**: http://143.110.177.2
- **Login**: `admin@mpango.demo` / `DemoAdmin2026!`
