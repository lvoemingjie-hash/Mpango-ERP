# S5 Environment Stabilization & Deployment

**Date**: 2026-02-06  
**Track**: S5 - Order State Machine & Ledger  
**Task**: Test Infrastructure Fix + CI Gate  
**Status**: ✅ COMPLETE

---

## Executive Summary

Backend AI completed Track S5 (Order State Machine & Financial Ledger). The test suite was experiencing infrastructure failures (`Event loop closed`, `search_path` issues) due to increased complexity from async transactions and row locking. This Ops Ledger documents the root cause analysis and fixes applied.

---

## Problem Statement

### Symptom 1: "Event loop is closed"

**Where**: `tests/test_s5_order_state_machine.py`, `tests/test_s5_ledger.py`

**Root Cause**: `pytest-asyncio` creates a new event loop per test function by default. SQLAlchemy's async engine maintains a connection pool that is bound to the loop it was created on. When the loop is destroyed between tests, the engine's pool tries to use a closed loop, raising `RuntimeError: Event loop is closed`.

This was not visible in simpler tests because they didn't exercise the connection pool heavily. S5 tests use `SELECT FOR UPDATE` (row locking), multi-step transactions, and `session.commit()` mid-test — all of which increase pool pressure.

### Symptom 2: "relation does not exist" / search_path lost

**Where**: Tests that call `session.commit()` mid-test (e.g., `test_invariant_violation_confirm_zero_total`, `test_void_vs_cancel_rules`)

**Root Cause**: The original `conftest.py` used `SET LOCAL search_path TO "t_test", public` which only persists for the duration of the **current transaction**. When a test calls `session.commit()`, PostgreSQL starts a new implicit transaction and the `search_path` reverts to `"$user", public`. Subsequent queries then fail because `orders`, `ledger_entries`, etc. don't exist in the public schema.

---

## Fixes Applied

### Fix 1: Session-Scoped Event Loop

**File**: `backend/tests/conftest.py`

**Change**: Added a `session`-scoped `event_loop` fixture that creates a single event loop for the entire test run.

```python
@pytest.fixture(scope="session")
def event_loop():
    """Create a session-scoped event loop for all async tests."""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()
```

**Why**: A single loop means the async engine's connection pool is always valid. No more "Event loop is closed" errors.

**Trade-off**: Tests are no longer fully isolated at the event-loop level. This is acceptable because test isolation is enforced by the `async_session` fixture (rollback after each test).

### Fix 2: Automatic search_path Re-set via after_begin Listener

**File**: `backend/tests/conftest.py`

**Change**: Replaced the one-shot `SET LOCAL search_path` with a SQLAlchemy `after_begin` event listener that automatically re-sets the search_path whenever a new transaction begins.

```python
sync_session = session.sync_session

@event.listens_for(sync_session, "after_begin")
def _after_begin(sess, transaction, connection):
    connection.execute(
        text(f'SET LOCAL search_path TO "{tenant_schema}", public')
    )
```

**Why**: Every `session.commit()` starts a new transaction. The listener fires on every new transaction, ensuring `search_path` is always set to `t_test, public`.

**Cleanup**: The listener is removed in the `finally` block to prevent leaking across tests.

### Fix 3: Schema Creation in Fixture

**File**: `backend/tests/conftest.py`

**Change**: Added `CREATE SCHEMA IF NOT EXISTS "t_test"` at the start of the fixture.

**Why**: Ensures the `t_test` schema exists before any test runs, even on a fresh CI database.

---

## Migration Review

### 009_s5_b_financial_ledger.py

**Status**: ✅ SAFE

**Safety Checks Present**:
1. `SHOW search_path` — inspects current search_path
2. `is_tenant_migration` guard — only runs if a `t_` schema is in the path
3. Both `upgrade()` and `downgrade()` have the guard

**Tables Created** (in tenant schema only):
- `ledger_entries` — immutable financial ledger
- `account_type` enum — receivable, revenue, cash, liability
- Indexes: reference, account_type, transaction_date

**No S5-A migration needed**: The order state machine changes are in the model layer (`OrderStatus` enum extended with new values). The existing `orders` table already uses a string-backed enum, so no DDL migration is required.

---

## CI/CD Pipeline

### New Workflow: `.github/workflows/s5-ci-gate.yml`

**Gates**:

| Gate | Description | Must Pass |
|------|-------------|-----------|
| S5-A Order State Machine | 10 tests: transitions, invariants, locking, audit | ✅ Yes |
| S5-B Financial Ledger | 7 tests: entries, balances, immutability, lifecycle | ✅ Yes |
| Migration Safety | Verifies search_path guards in migration files | ✅ Yes |

**Services**: PostgreSQL 15 + Redis 7 (sidecars)

**Environment**: All S2-1 mandatory env vars set in global `env` block

---

## Test Matrix

### S5-A: Order State Machine (10 tests)

| # | Test | Type |
|---|------|------|
| 1 | State transition matrix validation | Unit |
| 2 | Get valid transitions | Unit |
| 3 | Terminal state detection | Unit |
| 4 | Happy path: DRAFT → CONFIRMED → PAID → FULFILLED | Integration |
| 5 | Illegal transition: DRAFT → FULFILLED | Integration |
| 6 | Invariant: Confirm zero-total order | Integration |
| 7 | Terminal state: No transitions from FULFILLED | Integration |
| 8 | VOID vs CANCEL rules | Integration |
| 9 | Partial payment flow | Integration |
| 10 | Concurrent transition with row locking | Integration |

### S5-B: Financial Ledger (7 tests)

| # | Test | Type |
|---|------|------|
| 1 | Post single ledger entry | Integration |
| 2 | Post balanced transaction | Integration |
| 3 | Reject unbalanced transaction | Integration |
| 4 | Calculate account balance | Integration |
| 5 | Order confirmation creates ledger entries | Integration |
| 6 | Payment received updates ledger | Integration |
| 7 | Full order lifecycle accounting | Integration |

---

## Files Changed

| File | Change |
|------|--------|
| `backend/tests/conftest.py` | Session-scoped event loop, after_begin listener, schema creation |
| `.github/workflows/s5-ci-gate.yml` | New CI gate for S5 tests |
| `ai-ledger/ops/2026-02-06_s5_environment_stabilization.md` | This ledger |

---

## Verification

To verify the fixes locally:

```bash
cd backend

# Run S5-A tests
poetry run pytest tests/test_s5_order_state_machine.py -v

# Run S5-B tests
poetry run pytest tests/test_s5_ledger.py -v

# Run both together (tests session-scoped loop)
poetry run pytest tests/test_s5_order_state_machine.py tests/test_s5_ledger.py -v
```

**Expected**: All tests pass green with no `Event loop closed` or `relation does not exist` errors.

---

## Troubleshooting

### "Event loop is closed" still appears
- Verify `conftest.py` has the `event_loop` fixture with `scope="session"`
- Verify `pytest.ini` has `asyncio_mode = auto`
- Check no other conftest overrides the event_loop fixture

### "relation 'orders' does not exist"
- Verify `t_test` schema exists: `SELECT schema_name FROM information_schema.schemata WHERE schema_name = 't_test';`
- Verify tables exist in t_test: `SET search_path TO t_test; \dt`
- Run migrations with tenant context if tables are missing

### Tests pass individually but fail together
- This usually means test isolation is broken (missing rollback)
- Check that the `async_session` fixture's `finally` block runs `session.close()`
- Check that the `after_begin` listener is removed in `finally`

---

---

## S5 Release Deployment

**Date**: 2026-02-06  
**Status**: ✅ DEPLOYED & VERIFIED

### 1. Database Migration Verification

**Alembic State Before**: `008_s4_b_job_persistence`  
**Alembic State After**: `009_s5_b_financial_ledger`

**Public Schema**:
```
✅ public.sys_jobs EXISTS (S4-B)
   Indexes: sys_jobs_pkey, ix_sys_jobs_job_name, ix_sys_jobs_status,
            ix_sys_jobs_created_at, ix_sys_jobs_status_attempts
```

**Tenant Schemas** (6 total):
```
✅ t_550e8400e29b41d4a716446655440000.ledger_entries CREATED
✅ t_7465a81cc3f94fb3b0e6674cbc22c829.ledger_entries CREATED
✅ t_b6_verify.ledger_entries CREATED
✅ t_dev.ledger_entries CREATED
✅ t_f32148fea3b74353b1c9bb095a1a0e58.ledger_entries CREATED
✅ t_test.ledger_entries EXISTS (created by conftest)
```

**Note**: Alembic's shared version table means `upgrade head` only runs once.
Tenant-schema DDL was applied via `scripts/s5_tenant_migration.py` (idempotent).

### 2. Bugs Found & Fixed During Deployment

#### Bug 1: `/readyz` route returning 404

**Root Cause**: Health router mounted at prefix `/health`. Endpoint path `"y"` resolved to `/healthy`, not `/readyz`. Kubernetes expects `/readyz`.

**Fix**: Registered top-level routes directly on the FastAPI app in `api/app.py`:
```python
app.get("/healthz", ...)(health.liveness_probe)
app.get("/readyz", ...)(health.readiness_probe)
```

**File**: `backend/api/app.py`

#### Bug 2: `KeyError: "Attempt to overwrite 'message' in LogRecord"`

**Root Cause**: `error_codes.py:189` passed `"message"` as a key in the `extra` dict of `logger.warning()`. Python's `logging.LogRecord` reserves `message` as an attribute.

**Fix**: Renamed `"message"` → `"error_message"` in the extra dict.

**File**: `backend/core/error_codes.py`

#### Bug 3: `alembic.ini` pointing to Docker hostname

**Root Cause**: `sqlalchemy.url` in `alembic.ini` used `postgres:5432` (Docker service name), which fails when running locally.

**Fix**: Updated to `127.0.0.1:5432` for local/staging execution.

**File**: `backend/alembic.ini`

### 3. Deployment & Startup Log

```
✅ Configuration validated successfully
   Environment: test
   Database: 127.0.0.1:5432/mpango_erp
   Redis: configured
   Secret Key: ******************************** (length: 32)

{"level": "INFO", "message": "Structured logging initialized"}
{"level": "INFO", "message": "Job queue started"}
{"level": "INFO", "message": "Worker 0 started"}
{"level": "INFO", "message": "Worker 1 started"}
{"level": "INFO", "message": "Worker 2 started"}
{"level": "INFO", "message": "Worker 3 started"}
{"level": "INFO", "message": "Worker 4 started"}
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

**Verified**:
- ✅ `Job queue started` (S4 component alive)
- ✅ Redis connected (5 workers started)
- ✅ No Alembic version mismatches
- ✅ Structured JSON logging active

### 4. Smoke Test Results

```
✅ GET /healthz → 200 OK
   {"status":"healthy","service":"mpango-erp-backend","version":"0.1.0"}

✅ GET /readyz  → 200 OK
   {"status":"healthy","checks":{
     "database":{"status":"healthy","latency_ms":10.7},
     "redis":{"status":"healthy","latency_ms":3.25,"response":"PONG"}
   }}

✅ GET /metrics → 200 OK
   (Prometheus format)
```

### 5. Files Changed During Deployment

| File | Change | Reason |
|------|--------|--------|
| `backend/api/app.py` | Added top-level `/healthz` and `/readyz` routes | Route prefix mismatch fix |
| `backend/core/error_codes.py` | Renamed `"message"` → `"error_message"` in extra dict | LogRecord key collision |
| `backend/alembic.ini` | Changed host from `postgres` to `127.0.0.1` | Local execution support |
| `backend/scripts/s5_tenant_migration.py` | New: applies S5-B DDL to all tenant schemas | Tenant migration tool |
| `backend/scripts/s5_verify_deployment.py` | New: verifies migration state across schemas | Deployment verification |

---

**Document Author**: Ops AI  
**Track**: S5 - Order State Machine & Ledger  
**Status**: ✅ DEPLOYED & VERIFIED  
**Last Updated**: 2026-02-06
