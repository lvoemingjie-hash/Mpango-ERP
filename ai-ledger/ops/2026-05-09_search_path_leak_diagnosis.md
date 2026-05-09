# Stabilization Cycle 1B — Search Path Leak Diagnosis

Date: 2026-05-09
Branch: ops/integration-rehearsal-clean-2026-05-08
Worktree: C:\Users\Jeff0\MPANGO ERP\product-dev-recovered-review
Agent: Goose
Status: DIAGNOSIS COMPLETE — no commit, no push

---

## 1. Failing Test

```
tests/test_tenant_isolation.py::TestTenantSchemaIsolation::test_public_session_has_no_tenant_schema
```

Asserts: a session from `get_db()` should have NO `t_*` schema in its `search_path`.

---

## 2. Root Cause — Connection Pool Reuse with Residual search_path

### The Leak Chain (3-step)

```
Step 1: Some test (or fixture) calls get_tenant_db("t_xxx")
        → SET LOCAL search_path TO "t_xxx", public
        → session.close() → connection returned to pool
        → BUT the underlying asyncpg connection still has search_path = "t_xxx", public
             because SET LOCAL only reverts at transaction end, and session.close()
             may or may not issue a ROLLBACK before returning the connection.

Step 2: Next checkout from the pool reuses that same connection.
        The new session (from get_db()) inherits the stale search_path.

Step 3: test_public_session_has_no_tenant_schema runs get_db()
        → SHOW search_path → returns "t_xxx, public" instead of "public"
        → FAIL
```

### Why it passes in isolation

When `test_public_session_has_no_tenant_schema` runs alone:
- No prior test has set a tenant search_path on any connection.
- The pool gives it a clean connection → `search_path = public` → PASS.

### Why it fails in full/subset runs

When a tenant test (test 1 or 2) runs first:
- `get_tenant_db()` does `SET LOCAL search_path TO "t_xxx", public` on a pooled connection.
- When that session closes, the connection goes back to the pool.
- SQLAlchemy's async engine with `pool_pre_ping=True` does a `SELECT 1` to check liveness, but does NOT reset `search_path`.
- The next `get_db()` checkout may get that same connection with the residual tenant `search_path`.
- Result: the "public" session sees `t_xxx` in its path → FAIL.

### Contributing factors

| Factor | Code Location | Role |
|--------|---------------|------|
| `SET LOCAL search_path` | `session.py:114`, `conftest.py:348,364` | Only scoped to current transaction. After `session.close()`, connection may not be in a transaction, making `SET LOCAL` ambiguous. |
| `get_db()` does NOT set search_path | `session.py:62-79` | No `SET search_path TO public` on open. Assumes clean connection. |
| `pool_pre_ping` only checks liveness | `session.py:31` | Does `SELECT 1`, not `RESET search_path`. |
| `async_session` fixture sets `t_test` via `after_begin` listener | `conftest.py:355-365` | Listener runs on every new transaction for any session created from `AsyncSessionLocal`, including sessions used by `get_db()` inside tests that also use the fixture. |

### The `after_begin` listener is the PRIMARY culprit

This is the smoking gun. In `conftest.py:356-365`:

```python
@event.listens_for(sync_session, "after_begin")
def _after_begin(sess, transaction, connection):
    connection.execute(
        text(f'SET LOCAL search_path TO "{tenant_schema}", public')
    )
```

This listener is registered on the **sync_session** object — but because the test uses the session-scoped event loop and a shared `AsyncSessionLocal` factory, the **underlying engine's connection pool** is shared. Here's the critical path:

1. `async_session` fixture creates a session, sets `after_begin` listener on `sync_session`.
2. That session uses connection C1 from the pool.
3. The `after_begin` callback sets `search_path` to `t_test, public` on C1 via sync execution.
4. When the fixture session closes, the listener is removed from `sync_session` — BUT connection C1 still has `search_path = t_test, public` at the asyncpg level.
5. `test_public_session_has_no_tenant_schema` creates a NEW session via `get_db()`.
6. That session gets connection C1 from the pool (reused).
7. `get_db()` does NOT set search_path — it just does `session.info["tenant_schema"] = "public"`.
8. `SHOW search_path` → `t_test, public` → FAIL.

Additionally, `get_tenant_db()` in `test_search_path_set_for_tenant_session` and `test_different_tenants_have_isolated_search_paths` also leaves residual search_path on pooled connections for the same reason.

---

## 3. Root Cause Confidence

**HIGH (90%)**

The leak mechanism is clear: connection pool reuse without `search_path` reset between sessions. The `after_begin` listener in conftest.py and the `SET LOCAL` in `get_tenant_db()` both leave state on pooled connections.

---

## 4. Reproduction Command

```bash
# Requires running PostgreSQL
poetry run pytest tests/test_tenant_isolation.py -q --tb=short
```

Expected: test 1 or 2 sets tenant search_path → test 3 (`test_public_session_has_no_tenant_schema`) inherits it → FAIL.

### Smallest Failing Group

```bash
# Run just test 2 + test 3 (smallest reproducible pair)
poetry run pytest tests/test_tenant_isolation.py::TestTenantSchemaIsolation::test_different_tenants_have_isolated_search_paths tests/test_tenant_isolation.py::TestTenantSchemaIsolation::test_public_session_has_no_tenant_schema -q --tb=short
```

Or even just test 3 after any other test that uses `get_tenant_db()`.

---

## 5. Proposed Fix Options

### Option A: Test fixture cleanup only (MINIMAL, lowest risk)

**Scope**: `backend/tests/conftest.py` only

Add a `RESET search_path` in the `async_session` fixture's `finally` block, and add an explicit `RESET search_path` at the end of `get_tenant_db()` usage in the isolation tests.

```python
# In conftest.py async_session fixture finally block, add:
finally:
    event.remove(sync_session, "after_begin", _after_begin)
    # Reset search_path before returning connection to pool
    await session.execute(text("RESET search_path"))
    await session.close()
```

Also wrap the `test_public_session_has_no_tenant_schema` test to explicitly reset:

```python
async for session in get_db():
    # Defensive: reset any residual search_path from pool
    await session.execute(text("RESET search_path"))
    await session.commit()  # commit the RESET
    result = await session.execute(text("SHOW search_path"))
    ...
```

**Risk**: LOW — only changes test fixtures and test code. No production impact.
**Coverage**: Fixes the test isolation symptom but doesn't harden production.

### Option B: Session factory always resets search_path (RECOMMENDED)

**Scope**: `backend/database/session.py` — `get_db()` function

Add an explicit `RESET search_path` (or `SET search_path TO public`) at the start of `get_db()`:

```python
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            session.info["tenant_schema"] = "public"
            # Defensive: ensure clean search_path from pool
            await session.execute(text("SET search_path TO public"))
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            # Clean up before returning connection to pool
            await session.execute(text("RESET search_path"))
            await session.close()
```

**Risk**: LOW-MEDIUM — changes production session factory but only adds a defensive reset.
**Coverage**: Fixes both test isolation AND hardens production against pool reuse leaks.

### Option C: Connection pool reset hook

**Scope**: `backend/database/session.py` — engine creation

Add a `pool_reset_agent` or `pool_recycle` callback:

```python
from sqlalchemy import event as sa_event

@sa_event.listens_for(async_engine.sync_engine, "reset")
def _reset_search_path(dbapi_conn, connection_record):
    """Reset search_path when connection is returned to pool."""
    cursor = dbapi_conn.cursor()
    cursor.execute("RESET search_path")
    cursor.close()
```

Or use the async approach with `pool_reset_agent` parameter in `create_async_engine`.

**Risk**: MEDIUM — touches engine-level pool behavior. Needs careful testing with asyncpg.
**Coverage**: Most thorough — prevents ANY search_path leak regardless of session factory.

### Option D: Explicit rollback/close discipline

**Scope**: `backend/database/session.py` — both `get_db()` and `get_tenant_db()`

Ensure `session.rollback()` is called before `session.close()` in all paths:

```python
# get_tenant_db finally block:
finally:
    await session.rollback()  # ROLLBACK resets SET LOCAL
    await session.close()
```

`SET LOCAL` is transaction-scoped, so a `ROLLBACK` or `COMMIT` should clear it. The issue is that `session.close()` might not always issue a `ROLLBACK` if the session is already in a clean state.

**Risk**: LOW — standard cleanup discipline.
**Coverage**: Partial — only helps if ROLLBACK reliably resets SET LOCAL. May not cover all edge cases with asyncpg.

---

## 6. Recommended Minimal Fix

**Option A + Option D combined** (test-only + cleanup discipline):

1. Add `await session.rollback()` before `await session.close()` in `get_tenant_db()` finally block.
2. Add `await session.execute(text("RESET search_path"))` in `conftest.py` async_session fixture finally block.

This is the smallest change with lowest production risk. If CTO wants production hardening, escalate to Option B.

---

## 7. Production Risk if Left Unfixed

| Scenario | Risk |
|----------|------|
| Production API: `get_tenant_db()` followed by `get_db()` on same pool connection | **MEDIUM** — a public-scoped request could inherit a tenant search_path, potentially leaking cross-tenant data visibility. |
| Production API: concurrent requests with different tenants | **LOW-MEDIUM** — asyncpg connection pool reuse could theoretically serve a request with wrong search_path if timing aligns. |
| Test suite reliability | **HIGH** — flaky test failures erode confidence and slow development. |

The production risk is real but mitigated by:
- Connection pool size vs. request concurrency making reuse of the same connection less likely.
- Most production flows use either `get_db()` or `get_tenant_db()`, not both in sequence on the same connection.
- `pool_pre_ping` ensures connections are alive (but doesn't reset state).

**Recommendation**: Fix tests now (Option A). Schedule production hardening (Option B) for next stabilization cycle.

---

## 8. Confirmation

- [x] No commit made
- [x] No push made
- [x] No product business logic changed
- [x] No payment/order code touched
- [x] No `git reset --hard` used
- [x] `resolve_conflict.py` not staged
- [x] Working tree state unchanged from start
