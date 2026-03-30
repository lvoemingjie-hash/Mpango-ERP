# 2026-03-06 — Fix: Dashboard & Orders 500 Errors Post-RC4

**Role:** Full-Stack AI
**Severity:** CRITICAL (all business endpoints returning 500)
**Commits:** `09b5893`, `885fffe`

---

## Symptom

After clean RC4 deployment + seed, Human Tester reported 500 Internal Server Error on:
- `/dashboards/kpi/summary`
- `/orders`
- `/inventory/stocks` (this one was actually working)

---

## Bug 1: Dashboard KPI — 500

### Error
```
asyncpg.exceptions.UndefinedTableError: relation "mv_sales_daily" does not exist
```

### Root Cause
`reporting_role` lacked `USAGE ON SCHEMA` for tenant schema `t_a0000000000040008000000000000001`.

Migration 011 grants `USAGE` + `SELECT ON ALL TABLES` to `reporting_role` for tenant schemas that exist at migration time. After `docker compose down -v` → `alembic upgrade head`, zero tenant schemas exist, so migration 011 grants nothing. The seed script creates the tenant schema **after** migrations, so `reporting_role` never receives schema-level access.

The previous `fix_views.py` hotfix granted `SELECT` on individual views but missed the critical `GRANT USAGE ON SCHEMA`. Without `USAGE`, PostgreSQL treats the schema as invisible — `SET search_path` is useless.

### Proof
```sql
SELECT nspname, has_schema_privilege('reporting_role', nspname, 'USAGE')
FROM pg_namespace WHERE nspname LIKE 't_%';

-- BEFORE fix:
-- t_a0000000000040008000000000000001 | f  ← FALSE

-- AFTER fix:
-- t_a0000000000040008000000000000001 | t  ← TRUE
```

### Fix
Updated `backend/scripts/fix_views.py` Step 4:
```python
# Grant schema USAGE + SELECT to reporting_role
await db.execute(text(f'GRANT USAGE ON SCHEMA "{schema}" TO reporting_role'))
await db.execute(text(f'GRANT SELECT ON ALL TABLES IN SCHEMA "{schema}" TO reporting_role'))
await db.execute(text(
    f'ALTER DEFAULT PRIVILEGES IN SCHEMA "{schema}" '
    f'GRANT SELECT ON TABLES TO reporting_role'
))
```

---

## Bug 2: Orders — 500

### Error
```
File "/app/api/v1/orders.py", line 52, in order_to_schema
    status=OrderStatus(order.status.value),
ValueError: 'fulfilled' is not a valid OrderStatus
```

### Root Cause
`schemas/order.py` `OrderStatus` enum was out of sync with `models/order.py`:

| models/order.py (8 values) | schemas/order.py (4 values) |
|---|---|
| draft ✅ | draft ✅ |
| confirmed ✅ | confirmed ✅ |
| partially_paid ✅ | ❌ missing |
| paid ✅ | ❌ missing |
| fulfilled ✅ | ❌ missing |
| cancelled ✅ | cancelled ✅ |
| voided ✅ | ❌ missing |
| returned ✅ | returned ✅ |

The seed script creates orders with `fulfilled`, `paid`, and `cancelled` statuses. When `order_to_schema()` tries to convert the model status to the schema enum, it fails on any value not in the schema.

### Fix
Added missing values to `backend/schemas/order.py`:
```python
class OrderStatus(str, Enum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    PARTIALLY_PAID = "partially_paid"  # added
    PAID = "paid"                      # added
    FULFILLED = "fulfilled"            # added
    CANCELLED = "cancelled"
    VOIDED = "voided"                  # added
    RETURNED = "returned"
```

---

## Deployment Steps

1. Updated `fix_views.py` → commit `09b5893` → pushed
2. VPS: `git pull` → re-ran `fix_views.py` (USAGE grants applied)
3. Fixed `schemas/order.py` → commit `885fffe` → pushed
4. VPS: `git pull` → `docker compose build --no-cache backend` → `docker compose up -d backend`

---

## Verification (curl from inside container)

| Endpoint | Status | Data |
|----------|--------|------|
| Login | ✅ 200 | Two-phase auth |
| Select Tenant | ✅ 200 | Contextual token |
| Dashboard KPI | ✅ 200 | Revenue: $17,600 · AR: $5,300 · Cash: $12,300 |
| Orders | ✅ 200 | 5 orders (draft, confirmed, paid, fulfilled, cancelled) |
| Inventory | ✅ 200 | 10 SKUs |

---

## Files Changed

| File | Change |
|------|--------|
| `backend/scripts/fix_views.py` | Added `GRANT USAGE ON SCHEMA` + `SELECT ON ALL TABLES` |
| `backend/schemas/order.py` | Synced `OrderStatus` enum with `models/order.py` (4 → 8 values) |

---

## Architectural Lesson

The migration-time pattern for schema-scoped grants (migrations 011/012/013) creates a **race condition** on clean deploys:

```
alembic upgrade head  → 0 tenant schemas → grants/views skipped
seed_demo_data.py     → creates tenant schema → no grants, no views
```

**Recommended fix:** Integrate view creation and reporting grants into `_bootstrap_tenant_schema()` in the seed script, or add a post-seed idempotent step that always runs `fix_views.py`.

---

## Status

**RESOLVED** — All business endpoints returning 200 with correct data.
