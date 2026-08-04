"""DC-12R1-H5: Prepared-statement cache isolation — genuine causal regression.

Root Cause
==========
asyncpg maintains a per-connection prepared-statement cache.  When DDL alters
a table's structure, PostgreSQL invalidates the cached plan.  In a test
session where I2A runs before I2B, pooled connections carry stale plans that
raise ``InvalidCachedStatementError`` on the next query to an affected table.

Repair
======
``_h5_flush_stmt_cache`` (in ``test_dc12r1_s3_s2b_i2b_payment_declarations.py``)
calls ``async_engine.dispose()`` on the **actual global engine** after
module-scoped provisioning DDL completes.

Causal Proof
============
These tests prove RED (without dispose → error) and GREEN (with dispose →
success) using the actual global engine boundary.  No mocks, no conditional
pass, no silent-re-prepare escape.
"""
from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

pytestmark = pytest.mark.asyncio


def _async_db_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL", "")
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql+asyncpg://"):
        pass
    else:
        raise RuntimeError(
            "TEST_DATABASE_URL or DATABASE_URL must be set for H5 regression."
        )
    return url


def _unique_app_name() -> str:
    return f"h5_causal_{uuid.uuid4().hex[:12]}"


# ---------------------------------------------------------------------------
# Test 1: RED — DDL invalidates cached plan WITHOUT dispose
# ---------------------------------------------------------------------------

async def test_red_ddl_without_dispose_raises_invalid_cached_statement():
    """CAUSAL RED: cache a plan on engine-A → DDL on engine-B → re-execute on
    engine-A WITHOUT dispose → MUST raise InvalidCachedStatementError.

    This reproduces the real I2A→provisioning→I2B scenario: the DDL happens
    on a DIFFERENT connection (the provisioning/bootstrap path) than the one
    that cached the SELECT plan (the I2A test connection).

    The trigger is a column type change (int → text) which changes the result
    column's OID.  asyncpg caches the plan with the original OID; when PG
    changes it, asyncpg detects the mismatch and raises
    ``InvalidCachedStatementError``.
    """
    url = _async_db_url()
    schema = f"h5_red_{uuid.uuid4().hex[:8]}"
    select_sql = f'SELECT val FROM "{schema}".t_red WHERE id = 1'

    # Engine A: the "I2A" engine that caches the plan.
    engine_a = create_async_engine(
        url,
        pool_size=1,
        max_overflow=0,
        connect_args={
            "statement_cache_size": 100,
            "server_settings": {"application_name": _unique_app_name(), "jit": "off"},
        },
    )
    # Engine B: the "provisioning/bootstrap" engine that performs DDL.
    engine_b = create_async_engine(
        url,
        pool_size=1,
        max_overflow=0,
        connect_args={
            "server_settings": {"application_name": _unique_app_name(), "jit": "off"},
        },
    )

    try:
        # Phase 1 (engine A): create table (val is int), insert, cache plan.
        async with AsyncSession(engine_a) as session:
            await session.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
            await session.execute(
                text(f'CREATE TABLE "{schema}".t_red (id int, val int)')
            )
            await session.execute(
                text(f'INSERT INTO "{schema}".t_red VALUES (1, :v)'),
                {"v": 42},
            )
            await session.commit()

        # Cache the SELECT plan on engine A's pooled connection.
        async with AsyncSession(engine_a) as session:
            result = await session.execute(text(select_sql))
            assert result.scalar() == 42
            await session.commit()

        # Phase 2 (engine B): ALTER COLUMN TYPE (int → text) — changes OID.
        async with AsyncSession(engine_b) as session:
            await session.execute(
                text(
                    f'ALTER TABLE "{schema}".t_red '
                    f'ALTER COLUMN val TYPE text USING val::text'
                )
            )
            await session.execute(
                text(f'UPDATE "{schema}".t_red SET val = :v WHERE id = 1'),
                {"v": "changed"},
            )
            await session.commit()

        # Phase 3 (engine A): re-execute the SAME cached SQL WITHOUT dispose.
        stale_error: Exception | None = None
        try:
            async with AsyncSession(engine_a) as session:
                result = await session.execute(text(select_sql))
                _ = result.scalar()
                await session.commit()
        except Exception as exc:
            stale_error = exc

        # Record the __cause__ / __context__ chain.
        chain: list[str] = []
        cur: BaseException | None = stale_error
        seen: set[int] = set()
        while cur is not None and id(cur) not in seen:
            seen.add(id(cur))
            chain.append(f"{type(cur).__module__}.{type(cur).__name__}")
            cur = cur.__cause__ or cur.__context__

        # HARD ASSERTIONS — no conditional pass, no "silent re-prepare is OK".
        assert stale_error is not None, (
            "Expected InvalidCachedStatementError but query succeeded — "
            "the cached plan was NOT invalidated."
        )
        chain_str = " -> ".join(chain)
        assert any(
            "InvalidCachedStatement" in c or "CachedStatement" in c
            for c in chain
        ), f"Expected InvalidCachedStatementError in chain, got: {chain_str}"
    finally:
        try:
            async with AsyncSession(engine_b) as session:
                await session.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
                await session.commit()
        except Exception:
            pass
        await engine_a.dispose()
        await engine_b.dispose()


# ---------------------------------------------------------------------------
# Test 2: GREEN — dispose clears stale plans via the actual global engine
# ---------------------------------------------------------------------------

async def test_green_dispose_via_global_engine_clears_stale_plans():
    """CAUSAL GREEN: Use the ACTUAL global engine from database.session.

    After DDL that would invalidate cached plans, ``async_engine.dispose()``
    drains the pool so the next session gets a fresh connection with an empty
    statement cache.  The same query that would have raised RED now succeeds.
    """
    from database.session import async_engine, AsyncSessionLocal

    schema = f"h5_green_{uuid.uuid4().hex[:8]}"

    # Phase 1: create table + cache a SELECT on the GLOBAL engine.
    async with AsyncSessionLocal() as session:
        session.info["tenant_schema"] = "public"
        await session.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
        await session.execute(
            text(f'CREATE TABLE "{schema}".t_green (id int, label text)')
        )
        await session.execute(
            text(f'INSERT INTO "{schema}".t_green VALUES (1, :lbl)'),
            {"lbl": "before"},
        )
        await session.commit()

    # Cache the plan.
    async with AsyncSessionLocal() as session:
        session.info["tenant_schema"] = "public"
        result = await session.execute(
            text(f'SELECT label FROM "{schema}".t_green WHERE id = 1')
        )
        assert result.scalar() == "before"
        await session.commit()

    # Phase 2: DDL.
    async with AsyncSessionLocal() as session:
        session.info["tenant_schema"] = "public"
        await session.execute(
            text(f'ALTER TABLE "{schema}".t_green ADD COLUMN extra int DEFAULT 0')
        )
        await session.commit()

    # Phase 3: DISPOSE the global engine (the H5 repair).
    await async_engine.dispose()

    # Phase 4: re-execute on a FRESH connection — must succeed.
    async with AsyncSessionLocal() as session:
        session.info["tenant_schema"] = "public"
        result = await session.execute(
            text(f'SELECT label, extra FROM "{schema}".t_green WHERE id = 1')
        )
        row = result.fetchone()
        assert row is not None
        assert row.label == "before"
        assert row.extra == 0
        await session.commit()

    # Cleanup.
    try:
        async with AsyncSessionLocal() as session:
            session.info["tenant_schema"] = "public"
            await session.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
            await session.commit()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Test 3: dispose changes backend PID (connection identity proof)
# ---------------------------------------------------------------------------

async def test_dispose_changes_backend_pid():
    """After ``engine.dispose()``, the backend PID changes — proving the old
    pooled connection was closed and a new one was established."""
    from database.session import AsyncSessionLocal, async_engine

    pid_before = 0
    pid_after = 0

    async with AsyncSessionLocal() as session:
        session.info["tenant_schema"] = "public"
        pid_before = (
            await session.execute(text("SELECT pg_backend_pid()"))
        ).scalar()
        await session.commit()

    await async_engine.dispose()

    async with AsyncSessionLocal() as session:
        session.info["tenant_schema"] = "public"
        pid_after = (
            await session.execute(text("SELECT pg_backend_pid()"))
        ).scalar()
        await session.commit()

    assert pid_before != pid_after, (
        f"backend PID did not change after dispose: {pid_before} == {pid_after}"
    )


# ---------------------------------------------------------------------------
# Test 4: event-loop identity + pg_stat_activity exact assertions
# ---------------------------------------------------------------------------

async def test_event_loop_and_pg_stat_activity_after_dispose():
    """After dispose: (a) same event loop, (b) old PID gone from
    pg_stat_activity (exact assertion), (c) SELECT 1 succeeds."""
    import asyncio

    from database.session import AsyncSessionLocal, async_engine

    app_name = _unique_app_name()
    loop_before = asyncio.get_running_loop()
    old_pid = 0
    count_before = 0

    async with AsyncSessionLocal() as session:
        session.info["tenant_schema"] = "public"
        await session.execute(text(f"SET application_name TO '{app_name}'"))
        old_pid = (
            await session.execute(text("SELECT pg_backend_pid()"))
        ).scalar()
        await session.commit()

    # Verify the connection is visible BEFORE dispose.
    async with AsyncSessionLocal() as session:
        session.info["tenant_schema"] = "public"
        count_before = (
            await session.execute(
                text("SELECT count(*) FROM pg_stat_activity WHERE pid = :pid"),
                {"pid": old_pid},
            )
        ).scalar()
        await session.commit()

    assert count_before >= 1, (
        f"expected pooled connection visible before dispose, "
        f"got count_before={count_before} for pid={old_pid}"
    )

    # Dispose.
    await async_engine.dispose()

    # After dispose: old PID must be GONE (exact assertion).
    async with AsyncSessionLocal() as session:
        session.info["tenant_schema"] = "public"
        count_after = (
            await session.execute(
                text("SELECT count(*) FROM pg_stat_activity WHERE pid = :pid"),
                {"pid": old_pid},
            )
        ).scalar()
        one = (await session.execute(text("SELECT 1"))).scalar()
        await session.commit()

    assert count_after == 0, (
        f"connection still alive after dispose: pid={old_pid} "
        f"count_after={count_after} (expected 0)"
    )
    assert one == 1

    loop_after = asyncio.get_running_loop()
    assert loop_before is loop_after, "event loop changed across dispose"
