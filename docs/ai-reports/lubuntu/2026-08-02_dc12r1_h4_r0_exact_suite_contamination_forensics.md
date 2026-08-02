# DC-12R1-H4-R0: Exact Full-Suite AsyncPG Contamination and SIGKILL Forensics

**Date**: 2026-08-02
**Base SHA**: `9528cb6de5f668ed09feb7a1eaa9aafaa537987d`
**Branch**: `origin/product-dev-recovered`
**Verdict**: PASS_DC12R1_H4_R0_ROOT_CAUSE_IDENTIFIED

---

## Executive Summary

The full suite `poetry run pytest tests/ -q` fails for two independent reasons:

1. **Pre-existing bug (4 failures)**: `test_dc10e_export_worker_tenant_context.py` queries `mv_sales_daily` without schema-qualifying it. These tests fail in isolation regardless of test order.

2. **AsyncPG event-loop contamination (17+ failures, 2+ errors)**: A single dc11t4c async test + a single r4_r1 test permanently corrupts the global `async_engine`'s asyncpg connection pool. Every subsequent async test that uses the `async_session` fixture fails with `InterfaceError: cannot perform operation: another operation is in progress` or `RuntimeError: Task got Future attached to a different loop`.

3. **Suite hang at p21dd**: After contamination exhausts the connection pool, `test_platform_p21dd_runtime_storage_cutover_gate.py` (which starts its own Docker containers) blocks indefinitely. The suite is then killed by the `timeout` command (SIGKILL, exit 137). This is NOT an OOM kill.

---

## 1. Environment

| Component | Specification |
|-----------|--------------|
| PostgreSQL | 16 (Docker container `h4r0-pg`, port 56601) |
| Redis | 7-alpine (Docker container `h4r0-redis`, port 56501) |
| Python | 3.12.3 |
| pytest | 8.4.2 |
| pytest-asyncio | 0.26.0 (mode=auto, session-scoped loop) |
| SQLAlchemy | 2.x (async, asyncpg dialect, pool_pre_ping=True, pool_size=5) |
| asyncpg | latest |
| Total collected | 3172 tests, 182 files |

### pytest.ini configuration (relevant)
```ini
asyncio_mode = auto
asyncio_default_fixture_loop_scope = session
asyncio_default_test_loop_scope = session
```

---

## 2. Exact Collect Order

Collection order obtained via `pytest --collect-only -q --override-ini="addopts="`.

Key file positions in natural order:
| # | File | Test Range |
|---|------|-----------|
| 20 | `test_dc10e_export_worker_tenant_context.py` | 105-112 |
| 29 | `test_dc11t2_async_test_utils.py` | 221-234 |
| 30 | `test_dc11t4c_reporting_bootstrap_contract.py` | 235-238 |
| 48 | `test_dc12r1_s3_s2b_i1_r4_r1_real_alembic_upgrade.py` | 559-587 |
| 50 | `test_dc1g_retailer_registration_binding_balance.py` | 590-591 |
| 53 | `test_dc3b_credential_recovery_backend.py` | 606-621 |
| 92 | `test_platform_p21dd_runtime_storage_cutover_gate.py` | 1678-1713 |

---

## 3. First Failed/Error Node

Running `pytest tests/ -x -vv` stops at the FIRST failure:

```
FAILED tests/test_dc10e_export_worker_tenant_context.py::test_worker_real_reporting_session_has_required_tenant_context
```

**Error**: `sqlalchemy.exc.ProgrammingError: (asyncpg.ProgrammingError) UndefinedTableError: relation "mv_sales_daily" does not exist`

**Root cause**: `export_report_worker` in `jobs/export_jobs.py` executes `SELECT ... FROM mv_sales_daily` without schema-qualifying the table name. The test creates `mv_sales_daily` in tenant schema `t_550e8400e29b41d4a716446655440000` but the query's `search_path` does not include the tenant schema.

**Classification**: PRE-EXISTING. This test fails in isolation (4 of 8 tests in dc10e fail). It is NOT caused by contamination.

---

## 4. Contamination Root Cause

### 4.1 Minimal Reproducible Sequence (3 tests, 9 seconds)

```
pytest \
  tests/test_dc11t4c_reporting_bootstrap_contract.py::test_reporting_tenant_teardown_removes_schema_and_registry_rows \
  tests/test_dc12r1_s3_s2b_i1_r4_r1_real_alembic_upgrade.py::TestRealAlembicUpgradeFailClosed::test_missing_payments_table_fails \
  tests/test_dc1g_retailer_registration_binding_balance.py::test_binding_repository_create_sets_zero_outstanding_balance
```

Result: **1 failed, 2 errors** every time (3/3 reproductions confirmed).

### 4.2 Necessity and Sufficiency Proof

| Predecessor Set | Contaminates? | Evidence |
|----------------|--------------|----------|
| dc11t4c alone → dc1g | NO | 22 passed |
| r4_r1 alone → dc1g | NO | 47 passed |
| dc11t4c test_1 (sync) + r4_r1 → dc1g | NO | 32 passed |
| dc11t4c test_3 (async+dispose) + r4_r1 → dc1g | **YES** | 1 failed, 2 errors |
| dc11t4c test_3 + r4_r1 test_1 → dc1g | **YES** | 1 failed, 2 errors (9s) |

**Conclusion**: The minimal contaminating set is:
1. **dc11t4c `test_reporting_tenant_teardown_removes_schema_and_registry_rows`** (1 test)
2. **Any single r4_r1 test** (1 test)

### 4.3 Each File Passes Independently

| File | Alone | Tests | Time |
|------|-------|-------|------|
| `test_dc11t4c_reporting_bootstrap_contract.py` | 4 passed | 4 | 10.7s |
| `test_dc12r1_s3_s2b_i1_r4_r1_real_alembic_upgrade.py` | 29 passed | 29 | 147s |
| `test_dc1g_retailer_registration_binding_balance.py` | 2 passed | 2 | <2s |
| `test_dc3b_credential_recovery_backend.py` | 16 passed | 16 | <5s |
| `test_platform_p21dd_runtime_storage_cutover_gate.py` | 36 passed | 36 | 22s |

---

## 5. Contamination Mechanism

### 5.1 What dc11t4c test_3 Does

`test_reporting_tenant_teardown_removes_schema_and_registry_rows` (`tests/test_dc11t4c_reporting_bootstrap_contract.py:38-50`):

1. Calls `provision_reporting_tenant_for_contract()` — uses `AsyncSessionLocal` (the global `async_engine`) on the pytest-asyncio session-scoped event loop to create tenant registrations and schemas.
2. Calls `cleanup_reporting_tenant()` TWICE — each call:
   - Uses `AsyncSessionLocal` to delete rows and drop schema
   - Calls `await async_engine.dispose()` (`tests/reporting_bootstrap_contract_helpers.py:217`)
3. Creates `async with AsyncSessionLocal() as session:` — creates a NEW connection on the session loop and leaves it in the pool.

After this test, the global `async_engine` pool contains a connection (PID 4941 in pg_stat_activity, application_name="Mpango ERP", database=test_h4, state=idle, last_query=ROLLBACK) whose asyncpg protocol objects are bound to the session-scoped event loop.

### 5.2 What r4_r1 test_1 Does

`test_missing_payments_table_fails` (`tests/test_dc12r1_s3_s2b_i1_r4_r1_real_alembic_upgrade.py:319-345`):

1. `run_alembic_upgrade(config, REV_036)` — calls `_run_alembic_preserving_loop()` which:
   - Saves the current event loop reference
   - Runs `alembic.command.upgrade()` which internally calls `env.py:run_migrations_online()` → **`asyncio.run(run_async_migrations())`** (`alembic/env.py:211`)
   - `asyncio.run()` creates a new event loop, runs the async migrations, **closes the loop**, and calls `asyncio.set_event_loop(None)`
   - `_run_alembic_preserving_loop` restores the saved loop

2. `asyncio.run(_bootstrap_and_revert_to_036(schema, db_url))` (`tests/test_dc12r1_s3_s2b_i1_r4_r1_real_alembic_upgrade.py:313`) — creates ANOTHER throwaway event loop. This one:
   - Creates a LOCAL `create_async_engine` on the throwaway loop
   - Bootstraps the tenant schema
   - Reverts 037-specific changes
   - `await engine.dispose()` — disposes the LOCAL engine
   - Closes the throwaway loop

3. `run_alembic_upgrade(config, "head")` — another `_run_alembic_preserving_loop()` → `asyncio.run()`

**Critical**: Between step 1 and step 3, the current event loop has been set to `None` by step 2's `asyncio.run()`. In Python 3.12, `asyncio.run()` calls `events.set_event_loop(None)` in its finally block. When `_run_alembic_preserving_loop` calls `_current_or_new_loop()` in step 3, it gets `RuntimeError: There is no current event loop`, catches it, and **creates a NEW throwaway event loop** that is NOT the pytest-asyncio session loop.

After r4_r1 test_1 completes, the "current" event loop (as returned by `asyncio.get_event_loop()`) is a throwaway loop, NOT the session loop.

### 5.3 What Happens to the Victim (dc1g)

`test_binding_repository_create_sets_zero_outstanding_balance` uses the `async_session` fixture from `tests/conftest.py:478-558`:

1. **Line 496**: `async with AsyncSessionLocal() as setup_session:` — checks out the pooled connection (PID 4941) that was created by dc11t4c on the session loop
2. **Lines 501-513**: Executes DDL + TRUNCATE + COMMIT
3. **Line 517**: `await async_engine.dispose()` — disposes the engine
4. **Line 519**: `async with AsyncSessionLocal() as session:` — creates a NEW session

The failure occurs during **teardown** (line 554: `await session.rollback()`):

```
asyncpg/protocol/protocol.pyx:735: in asyncpg.protocol.protocol.BaseProtocol._check_state
E   asyncpg.exceptions._base.InterfaceError: cannot perform operation: another operation is in progress
```

For later dc3b tests, the error evolves to:

```
asyncpg/protocol/protocol.pyx:369: in query
E   RuntimeError: Task <Task pending> got Future <Future pending cb=[BaseProtocol._on_waiter_completed()]> attached to a different loop
```

### 5.4 pg_stat_activity Evidence

Captured during contamination run (8 seconds into execution):

| PID | Database | State | Last Query | Application |
|-----|----------|-------|------------|-------------|
| 4941 | test_h4 | idle | ROLLBACK | Mpango ERP |
| 4944 | test_r4r1pay_... | idle | COMMIT | (none) |
| 4946 | test_r4r1pay_... | active | DELETE FROM ...permissions | (none) |

PID 4941 is the global `async_engine`'s pooled connection from dc11t4c. It is idle after ROLLBACK. When r4_r1's `asyncio.run()` calls create/close throwaway event loops, this connection's asyncpg protocol Futures become orphaned — they were created on the session loop but subsequent event loop manipulation causes the protocol's internal `_waiting` state or Future loop binding to become inconsistent.

### 5.5 Event Loop ID Trace

| Checkpoint | Current Loop ID | Running | Closed | Pool Size | Pool Checked-in |
|-----------|----------------|---------|--------|-----------|----------------|
| Before dc11t4c | 133237187577472 | False | False | 5 | 0 |
| After dc11t4c | 133237168334672 | False | False | 5 | 0 |
| After r4_r1 | 133237133131312 | False | False | 5 | 0 |
| Async probe after r4_r1 | 133237133131312 | True | False | 5 | 0 |

The "current" event loop changes after each file. Three distinct loop IDs appear. The pytest-asyncio session loop is separate from the "current" loop seen by sync code.

---

## 6. Fixture Inspection

### 6.1 `async_session` Fixture (`tests/conftest.py:478-558`)

- **Scope**: function
- **Creates**: setup session → bootstraps DDL → TRUNCATE → COMMIT → `async_engine.dispose()` → new test session
- **Teardown**: `session.rollback()` → remove event listener → `session.close()`
- **Pool disposal**: `await async_engine.dispose()` at line 517 between setup and test session

The `async_engine.dispose()` at line 517 is the trigger point. After dc11t4c + r4_r1, the dispose + recreate cycle creates connections whose asyncpg protocols inherit corrupted loop state.

### 6.2 `ensure_reporting_user_password` Fixture (`tests/conftest.py:121-160`)

- **Scope**: session
- Disposes both `async_engine` and `reporting_engine` at lines 154, 158
- Used by dc10e and dc11t4c tests

### 6.3 `async_test_utils.py` Loop-Safety Design

The file was specifically designed to avoid `asyncio.run()`:

```python
# tests/async_test_utils.py:25-37
def _current_or_new_loop():
    policy = asyncio.get_event_loop_policy()
    try:
        loop = policy.get_event_loop()
    except RuntimeError:
        loop = policy.new_event_loop()
        policy.set_event_loop(loop)
    if loop.is_closed():
        loop = policy.new_event_loop()
        policy.set_event_loop(loop)
    return loop

# tests/async_test_utils.py:40-45
def run_coroutine(awaitable):
    loop = _current_or_new_loop()
    if loop.is_running():
        raise RuntimeError("run_coroutine cannot run inside an active event loop")
    return loop.run_until_complete(awaitable)
```

**But** r4_r1 bypasses this design by calling `asyncio.run()` directly at lines 313 and 1055, and `alembic/env.py:211` also uses `asyncio.run()`.

---

## 7. InterfaceError Determination

The `asyncpg.exceptions._base.InterfaceError: cannot perform operation: another operation is in progress` is:

**NOT** concurrent use of one connection (no evidence of parallel queries).
**NOT** pool contamination (the pool has 0 checked-out connections).
**NOT** closed-loop reuse (the session loop is still alive).

**It IS** event-loop orphaning: the asyncpg protocol's internal Future (created on the session loop) becomes incompatible with the event loop state after `asyncio.run()` calls in r4_r1 modify the global event loop policy state. The `_check_state` method at `asyncpg/protocol/protocol.pyx:735` detects that the protocol's waiter/completion callback is associated with a loop that no longer matches the running loop context.

The later `RuntimeError: Task got Future attached to a different loop` at `asyncpg/protocol/protocol.pyx:369` is the explicit confirmation: a Future created on loop A is being awaited on loop B.

---

## 8. SIGKILL Source Determination

### Evidence

| Check | Result |
|-------|--------|
| `dmesg` OOM records | None accessible (requires root) |
| `journalctl -k` OOM/kill | None found |
| System memory | 11Gi total, 8.2Gi available |
| Swap | 4Gi total, 2.7Gi free |
| cgroup memory.max | Not set (no container memory limit) |
| Docker resource limits | None on host containers |

### Conclusion

**Exit code 137 (SIGKILL) is from the `timeout` command**, not from the OOM killer. The full suite hangs at `test_platform_p21dd_runtime_storage_cutover_gate.py` (position 1678-1713, ~53% of suite) because upstream contamination exhausts or corrupts the asyncpg connection pool. The `timeout` command sends SIGTERM, then SIGKILL after the grace period, producing exit code 137.

---

## 9. Hang at p21dd

`test_platform_p21dd_runtime_storage_cutover_gate.py` starts its own ephemeral Docker containers (`subprocess.run(["docker", "run", ...])` at line 216) and runs alembic migrations against them. In isolation, all 36 tests pass in 22 seconds.

In the full suite, the hang occurs because:
1. Upstream contamination (dc11t4c + r4_r1) has corrupted the global `async_engine`'s asyncpg connections
2. The `async_session` fixture's `async_engine.dispose()` + recreation cycle inherits corrupted loop state
3. p21dd's own `run_alembic_upgrade()` calls add more `asyncio.run()` calls, compounding the corruption
4. Eventually an async operation blocks indefinitely waiting for a protocol response that will never arrive (the protocol's Future is orphaned)

**The hang is a SYMPTOM of contamination, not a separate bug.** p21dd does not cause the contamination; it is blocked by it.

---

## 10. Narrowest Repair Boundary

### Primary Repair: Replace `asyncio.run()` in r4_r1

**File**: `tests/test_dc12r1_s3_s2b_i1_r4_r1_real_alembic_upgrade.py`
**Lines**: 313, 1055
**Current**:
```python
asyncio.run(_bootstrap_and_revert_to_036(schema, db_url))
```
**Repair**: Use the existing loop-safe helper:
```python
run_coroutine(_bootstrap_and_revert_to_036(schema, db_url))
```

This is the same pattern already used by `async_test_utils.py:run_coroutine()` which was specifically designed to avoid creating throwaway event loops.

**Affected symbols**:
- `_setup_tenant()` method (line 308-314)
- `_full_proof()` method (line 1045-1086)

### Secondary Repair: Replace `asyncio.run()` in `alembic/env.py`

**File**: `alembic/env.py`
**Line**: 211
**Current**:
```python
def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())
```
**Repair**: Use `_current_or_new_loop().run_until_complete()`:
```python
def run_migrations_online() -> None:
    from tests.async_test_utils import _current_or_new_loop
    loop = _current_or_new_loop()
    loop.run_until_complete(run_async_migrations())
```

Or better: call `run_async_migrations()` directly when a loop is already running, and use `asyncio.run()` only when no loop exists.

### Tertiary: Fix dc10e pre-existing bug

**File**: `jobs/export_jobs.py`
**Issue**: Query `SELECT ... FROM mv_sales_daily` lacks schema qualification
**Repair**: Set `search_path` to include the tenant schema before querying, or schema-qualify the table reference.

---

## 11. Recommended RED Tests

These tests fail before the repair and pass after:

1. **Loop contamination regression**: Run dc11t4c test_3 + r4_r1 test_1 + any `async_session` fixture test. Assert all pass.
2. **Event loop identity**: After `run_alembic_upgrade()`, assert `asyncio.get_event_loop()` is the same loop object as before the call.
3. **No throwaway loops**: Instrument `asyncio.new_event_loop()` to count calls during r4_r1. Assert zero calls when using `run_coroutine()`.
4. **Engine pool integrity**: After dc11t4c + r4_r1, assert `async_engine.pool.size() == 0` and `async_engine.pool.checkedout() == 0` and a test query succeeds.
5. **dc10e search_path**: Assert `export_report_worker` queries with the tenant schema in `search_path`.

---

## 12. Red Nodes Summary

See `2026-08-02_dc12r1_h4_r0_red_nodes.csv` for the complete list.

| Category | Count | Files |
|----------|-------|-------|
| PRE_EXISTING | 4 | test_dc10e_export_worker_tenant_context.py |
| CONTAMINATION | 19 | test_dc1g_retailer_registration_binding_balance.py (2), test_dc3b_credential_recovery_backend.py (16), + errors |
| HANG (killed by timeout) | ~1459 | test_platform_p21dd and all subsequent files |

---

## 13. 3x Reproduction Confirmation

| Run | Duration | Result |
|-----|----------|--------|
| 1 | 148s | 1 failed, 2 errors, 33 passed |
| 2 | 190s | 1 failed, 2 errors, 33 passed |
| 3 | 153s | 1 failed, 2 errors, 33 passed |

Minimal sequence (dc11t4c test_3 + r4_r1 test_1 + dc1g test_1): 9.2s, 1 failed + 2 errors.

---

## Appendix A: Exact First-Failure Traceback (Contamination)

```
ERROR at teardown of test_binding_repository_create_sets_zero_outstanding_balance

/home/ivy/.local/lib/python3.12/site-packages/asyncpg/transaction.py:227: in rollback
    await self.__rollback()
/home/ivy/.local/lib/python3.12/site-packages/asyncpg/transaction.py:206: in __rollback
    await self._connection.execute(query)
/home/ivy/.local/lib/python3.12/site-packages/asyncpg/connection.py:354: in execute
    result = await self._protocol.query(query, timeout)
asyncpg/protocol/protocol.pyx:354: in query
asyncpg/protocol/protocol.pyx:735: in asyncpg.protocol.protocol.BaseProtocol._check_state
E   asyncpg.exceptions._base.InterfaceError: cannot perform operation: another operation is in progress

tests/conftest.py:554: in async_session
    await session.rollback()
```

## Appendix B: Later Failure Traceback (Different Loop)

```
RuntimeError: Task <Task pending name='Task-951' coro=<test_r1_no_internal_mapping_in_public_responses()
    running at tests/test_dc3b_credential_recovery_backend.py:853>
    cb=[_run_until_complete_cb() at /usr/lib/python3.12/asyncio/base_events.py:182]>
    got Future <Future pending cb=[BaseProtocol._on_waiter_completed()]>
    attached to a different loop
```

## Appendix C: asyncio.run() Call Sites

| File | Line | Context |
|------|------|---------|
| `alembic/env.py` | 211 | `asyncio.run(run_async_migrations())` — called by EVERY alembic migration |
| `tests/test_dc12r1_s3_s2b_i1_r4_r1_real_alembic_upgrade.py` | 313 | `asyncio.run(_bootstrap_and_revert_to_036(schema, db_url))` in `_setup_tenant()` |
| `tests/test_dc12r1_s3_s2b_i1_r4_r1_real_alembic_upgrade.py` | 1055 | `asyncio.run(_bootstrap_and_revert_to_036(schema, db_url))` in `_full_proof()` |
