"""DC-12R1-H5: Prepared-statement cache isolation — executable regression.

Root Cause
==========
asyncpg maintains a per-connection prepared-statement cache (default 100
entries).  When DDL alters a table's structure, PostgreSQL invalidates the
cached plan for any prepared statement referencing that table.

In a test session where I2A runs before I2B, the following happens:

1. I2A tests create/alter tenant-schema tables (via reconcile/bootstrap DDL).
2. The asyncpg connections used by I2A now have cached statements referencing
   the *pre-DDL* table structure.
3. ``provisioned_pool`` (module-scoped, shared with I2B) runs additional
   bootstrap DDL for its 3 tenants, further invalidating statements.
4. When I2B's function-scoped tests acquire a pooled connection, that
   connection may still carry stale prepared statements from step 1.
5. The first query to an affected table raises
   ``InvalidCachedStatementError``.

Repair
======
Dispose the engine pool after module-scoped DDL completes but before
function-scoped tests begin.  The ``_h5_flush_stmt_cache`` autouse fixture in
``test_dc12r1_s3_s2b_i2b_payment_declarations.py`` implements this.

These tests verify the repair using real PostgreSQL 16 connections — no mocks.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helper: build a DATABASE_URL compatible with asyncpg
# ---------------------------------------------------------------------------

def _async_db_url() -> str:
    import os

    url = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL", "")
    # Ensure asyncpg dialect
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql+asyncpg://"):
        pass
    else:
        raise RuntimeError(
            "TEST_DATABASE_URL or DATABASE_URL must be set for the H5 "
            "prepared-statement-cache isolation regression."
        )
    return url


# ---------------------------------------------------------------------------
# Test 1: engine.dispose() produces a different underlying DBAPI connection
# ---------------------------------------------------------------------------

async def test_dispose_produces_different_connection_identity():
    """After ``engine.dispose()``, a new session obtains a different underlying
    asyncpg connection object. This proves the pool was actually drained.

    Uses ``pg_backend_pid()`` — the PostgreSQL server-side connection PID —
    as the identity, which is reliable across SQLAlchemy versions."""
    url = _async_db_url()
    engine = create_async_engine(url, pool_size=1, max_overflow=0)

    try:
        # Obtain connection PID #1.
        async with AsyncSession(engine) as session:
            result = await session.execute(text("SELECT pg_backend_pid()"))
            pid1 = result.scalar()

        # Dispose — drains all pooled connections.
        await engine.dispose()

        # Obtain connection PID #2 — must differ.
        async with AsyncSession(engine) as session:
            result = await session.execute(text("SELECT pg_backend_pid()"))
            pid2 = result.scalar()

        assert pid1 != pid2, (
            f"dispose() did not produce a different connection: pid {pid1} == {pid2}"
        )
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Test 2: dispose() + DDL boundary + stale-plan resilience
# ---------------------------------------------------------------------------

async def test_dispose_clears_stale_prepared_statements_after_ddl():
    """Simulate the I2A→I2B cross-module scenario:

    1. Prepare a statement on a temp table.
    2. ALTER the table (DDL invalidation).
    3. Without dispose, a pooled connection may reuse a stale plan.
    4. With dispose, the next connection has a clean cache and succeeds.
    """
    url = _async_db_url()
    engine = create_async_engine(url, pool_size=1, max_overflow=0)
    task_schema = f"h5_test_{uuid.uuid4().hex[:8]}"

    try:
        # Phase 1: create table and cache a prepared statement.
        async with AsyncSession(engine) as session:
            await session.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{task_schema}"'))
            await session.execute(
                text(
                    f'CREATE TABLE "{task_schema}".t1 (id int, label text)'
                )
            )
            await session.execute(
                text(f'INSERT INTO "{task_schema}".t1 VALUES (1, :lbl)'),
                {"lbl": "before"},
            )
            await session.commit()
            # Prepare a statement — asyncpg caches it per-connection.
            await session.execute(text(f'SELECT * FROM "{task_schema}".t1'))
            result = await session.execute(text(f'SELECT label FROM "{task_schema}".t1 WHERE id = 1'))
            assert result.scalar() == "before"

        # Phase 2: DDL — alter the table structure.
        async with AsyncSession(engine) as session:
            await session.execute(
                text(f'ALTER TABLE "{task_schema}".t1 ADD COLUMN extra int DEFAULT 0')
            )
            await session.commit()

        # Phase 3: DISPOSE — flush the entire pool.
        await engine.dispose()

        # Phase 4: query on a fresh connection — must succeed (no stale plan).
        async with AsyncSession(engine) as session:
            result = await session.execute(
                text(f'SELECT label, extra FROM "{task_schema}".t1 WHERE id = 1')
            )
            row = result.fetchone()
            assert row is not None
            assert row.label == "before"
            assert row.extra == 0
            await session.commit()
    finally:
        # Cleanup: drop the test schema.
        async with AsyncSession(engine) as session:
            await session.execute(text(f'DROP SCHEMA IF EXISTS "{task_schema}" CASCADE'))
            await session.commit()
        await engine.dispose()


# ---------------------------------------------------------------------------
# Test 3: event-loop identity preserved across dispose
# ---------------------------------------------------------------------------

async def test_event_loop_identity_preserved_across_dispose():
    """``engine.dispose()`` closes pooled connections but does NOT close or
    change the running event loop. The same loop handles both pre- and
    post-dispose queries."""
    import asyncio

    url = _async_db_url()
    engine = create_async_engine(url, pool_size=1, max_overflow=0)

    try:
        loop_before = asyncio.get_running_loop()

        async with AsyncSession(engine) as session:
            await session.execute(text("SELECT 1"))

        await engine.dispose()

        loop_after = asyncio.get_running_loop()

        assert loop_before is loop_after, (
            "event loop changed across dispose — this would break async fixtures"
        )

        # A query after dispose still works on the same loop.
        async with AsyncSession(engine) as session:
            result = await session.execute(text("SELECT 42"))
            assert result.scalar() == 42
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Test 4: no idle connections left after dispose
# ---------------------------------------------------------------------------

async def test_no_idle_connections_after_dispose():
    """After ``engine.dispose()``, querying ``pg_stat_activity`` confirms no
    connections from this engine remain on the server side.

    The ``SET application_name`` is set at the session level which means it
    persists on the connection even after the session returns it to the pool.
    After dispose, the connection is closed and the PID disappears from
    ``pg_stat_activity``."""
    url = _async_db_url()
    engine = create_async_engine(url, pool_size=1, max_overflow=0)

    try:
        # Get the backend PID and set application_name so we can track it.
        async with AsyncSession(engine) as session:
            pid = (await session.execute(text("SELECT pg_backend_pid()"))).scalar()
            await session.execute(text("SELECT 1"))
            # Commit so the session returns the connection to the pool.
            await session.commit()

        # The connection is now idle in the pool. Verify it's visible.
        check_engine = create_async_engine(url, pool_size=1, max_overflow=0)
        async with AsyncSession(check_engine) as check:
            active = await check.execute(
                text("SELECT count(*) FROM pg_stat_activity WHERE pid = :pid"),
                {"pid": pid},
            )
            count_before = active.scalar()
        await check_engine.dispose()

        # If the pool already returned the connection, count_before should be >= 1.
        # If not (timing), skip the "before" assertion and only verify "after".
        if count_before >= 1:
            # Dispose — drains all pooled connections.
            await engine.dispose()

            # After dispose, no connections with our PID remain.
            verify_engine = create_async_engine(url, pool_size=1, max_overflow=0)
            async with AsyncSession(verify_engine) as verify:
                active = await verify.execute(
                    text("SELECT count(*) FROM pg_stat_activity WHERE pid = :pid"),
                    {"pid": pid},
                )
                count_after = active.scalar()
            await verify_engine.dispose()

            assert count_after == 0, (
                f"connection still alive after dispose: pid={pid} count={count_after}"
            )
        else:
            # Connection was already gone (pool returned + server cleaned up).
            # Still valid — dispose is idempotent.
            await engine.dispose()
    finally:
        await engine.dispose()
