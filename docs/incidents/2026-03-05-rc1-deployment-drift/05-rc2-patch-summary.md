# RC2 Patch Summary

**To:** CTO
**From:** Backend AI
**Date:** 2026-03-05
**Tag:** `v0.2.1-rc2`
**Commit:** `b715518`

---

## Issue A — Login Endpoint Contract Violation

### Root Cause

The file `backend/api/v1/auth.py` was rewritten locally during Track H-Fix-01 to implement two-phase auth, but was **never staged or committed** to git. The original commit `69ecf32` (v0.2.1-rc1) included schema changes (`schemas/auth.py` — `LoginRequest` without `tenant_code`) and CRUD changes (`crud/user.py` — `find_user_across_tenants`), but missed the endpoint file itself.

When OPS deployed to staging, the VPS pulled from git and received:
- ✅ `LoginRequest` schema with only `email` + `password`
- ✅ `find_user_across_tenants` CRUD function
- ❌ **Old** `auth.py` endpoint still calling `request.tenant_code`

Result: `AttributeError: 'LoginRequest' object has no attribute 'tenant_code'`

### Fix Applied

Committed the correct `backend/api/v1/auth.py` (222 insertions, 97 deletions). The login endpoint now:

1. Accepts `email` + `password` only (no `tenant_code`)
2. Calls `find_user_across_tenants()` to scan all active tenant schemas
3. Returns `IdentityLoginResponse` with identity JWT + `available_tenants[]`

Tenant context is handled exclusively by `POST /auth/select-tenant`.

### Files Changed

| File | Change |
|------|--------|
| `backend/api/v1/auth.py` | Full two-phase auth rewrite (was missing from git) |

---

## Issue B — Migration 016 Enum Dependency

### Root Cause

Migration `016_add_returned_status` assumed the `order_status` enum type already existed (created by migration `003_phase_b3_orders_minimal_closed_loop`). On the staging DB, the enum was created inside tenant schemas, not in the public schema. The `ALTER TYPE` statement failed because it looked for the type in the wrong schema context.

### Fix Applied

Made migration 016 **idempotent and environment-safe**:

```python
from sqlalchemy import text

def upgrade() -> None:
    conn = op.get_bind()
    result = conn.execute(
        text("SELECT 1 FROM pg_type WHERE typname = 'order_status'")
    ).fetchone()

    if result is None:
        # Enum doesn't exist — create with all values
        op.execute(text(
            "CREATE TYPE order_status AS ENUM "
            "('pending', 'confirmed', 'processing', 'shipped', "
            "'delivered', 'cancelled', 'returned')"
        ))
    else:
        # Enum exists — add 'returned' if missing
        op.execute(text(
            "ALTER TYPE order_status ADD VALUE IF NOT EXISTS 'returned'"
        ))
```

Changes from OPS's emergency patch:
- Replaced `__import__('sqlalchemy').text()` hack with proper `from sqlalchemy import text`
- All `op.execute()` calls now use `text()` for explicit SQL handling

### Files Changed

| File | Change |
|------|--------|
| `backend/alembic/versions/016_add_returned_status.py` | Idempotent enum creation + proper imports |

---

## Verification

### Local Verification

```
git log v0.2.1-rc2 -1 --oneline
b715518 (tag: v0.2.1-rc2) fix(auth): remove tenant_code dependency from login flow

git branch --contains v0.2.1-rc2
* main
```

### Deployment Instructions for OPS

OPS should execute a **clean rebuild** from the `v0.2.1-rc2` tag:

```bash
cd /root/mpango-erp
git fetch --tags
git checkout v0.2.1-rc2
docker compose -f docker-compose.prod.yml build --no-cache
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml exec backend alembic upgrade head
```

### Acceptance Criteria

| Check | Expected |
|-------|----------|
| `POST /auth/login {"email":"..","password":".."}` | 200 or 401 (not 500) |
| `POST /auth/select-tenant {"tenant_id":".."}` | 200 with contextual JWT |
| `alembic upgrade head` on empty DB | No errors |
| Migration 016 on DB with existing enum | No errors |
| Migration 016 on DB without enum | Creates enum, no errors |

---

## Governance Note

This incident exposed a gap in the commit workflow:

**Root cause of the incident was not a code bug — it was a staging failure.** The code was correct locally but never committed. The `git add` command in the original v0.2.1-rc1 workflow explicitly listed files but missed `backend/api/v1/auth.py`.

**Recommendation:** Future releases should use `git diff --cached --stat` to verify all modified files are staged before committing.

---

*RC2 is ready for OPS deployment. Awaiting CTO approval.*
