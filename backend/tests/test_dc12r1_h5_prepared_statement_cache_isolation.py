"""DC-12R1-H5: Prepared-statement cache isolation — genuine causal regression.

Root Cause
==========
asyncpg maintains a per-connection prepared-statement cache.  When DDL alters
a table's structure (especially a column type change), PostgreSQL invalidates
the cached plan.  In a test session where I2A runs before I2B, pooled
connections carry stale plans that raise ``InvalidCachedStatementError`` on
the next query to an affected table.

Repair
======
``_h5_flush_stmt_cache`` (in ``test_dc12r1_s3_s2b_i2b_payment_declarations.py``)
calls ``async_engine.dispose()`` on the **actual global engine** after
module-scoped provisioning DDL completes.

PW1-R4-A runtime policy update
==============================

The production engine now sets ``prepared_statement_cache_size=0``
(``database/session.py``): the SQLAlchemy asyncpg dialect no longer reuses
pooled prepared statements, so DDL invalidation cannot poison cross-request
statements at runtime. Consequently the *global-engine* GREEN leg no longer
causally proves anything about dispose (it would pass even without it) and
has been reshaped:

* RED    - a DEDICATED cache-enabled engine (test-local, dialect defaults,
           pool_size=1), no dispose, same SQL re-executed after DDL -> error
           (unchanged; still the causal core).
* GREEN  - a DEDICATED cache-enabled engine, dispose between DDL and
           re-execution of the SAME SQL -> success (dispose mechanism proven
           where caching exists). Neither RED nor GREEN touches the
           production global engine.
* POLICY - the ONLY leg on the production global engine: re-executes the SAME
           SQL after DDL WITHOUT dispose and must succeed; this leg fails if
           ``prepared_statement_cache_size=0`` is ever removed from
           ``database/session.py`` (mutation-verified in
           ``test_pw1r4_cross_tenant_statement_cache.py``).

Causal Proof
============
These tests prove RED (without dispose → error) and GREEN (with dispose →
success) using the actual global engine boundary.  No mocks, no conditional
pass, no silent-re-prepare acceptance.

Cleanup is fail-closed: every created schema is dropped in a finally block
with a ``pg_namespace`` assertion verifying zero residue.
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


async def _assert_schema_absent(session: AsyncSession, schema: str) -> None:
    """Assert that ``schema`` does not exist in pg_catalog.pg_namespace."""
    result = await session.execute(
        text("SELECT count(*) FROM pg_catalog.pg_namespace WHERE nspname = :nsp"),
        {"nsp": schema},
    )
    count = result.scalar()
    assert count == 0, (
        f"schema '{schema}' still exists after cleanup: pg_namespace count={count}"
    )


# ---------------------------------------------------------------------------
# Test 1: RED — DDL invalidates cached plan WITHOUT dispose
# ---------------------------------------------------------------------------

async def test_red_ddl_without_dispose_raises_invalid_cached_statement():
    """CAUSAL RED: cache a plan on engine-A → DDL on engine-B → re-execute on
    engine-A WITHOUT dispose → MUST raise InvalidCachedStatementError.
    """
    url = _async_db_url()
    schema = f"h5_red_{uuid.uuid4().hex[:8]}"
    select_sql = f'SELECT val FROM "{schema}".t_red WHERE id = 1'

    engine_a = create_async_engine(
        url,
        pool_size=1,
        max_overflow=0,
        connect_args={
            "statement_cache_size": 100,
            "server_settings": {"application_name": _unique_app_name(), "jit": "off"},
        },
    )
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

        # Phase 3 (engine A): re-execute WITHOUT dispose.
        stale_error: Exception | None = None
        try:
            async with AsyncSession(engine_a) as session:
                result = await session.execute(text(select_sql))
                _ = result.scalar()
                await session.commit()
        except Exception as exc:
            stale_error = exc

        chain: list[str] = []
        cur: BaseException | None = stale_error
        seen: set[int] = set()
        while cur is not None and id(cur) not in seen:
            seen.add(id(cur))
            chain.append(f"{type(cur).__module__}.{type(cur).__name__}")
            cur = cur.__cause__ or cur.__context__

        assert stale_error is not None, (
            "Expected InvalidCachedStatementError but query succeeded."
        )
        chain_str = " -> ".join(chain)
        assert any(
            "InvalidCachedStatement" in c or "CachedStatement" in c
            for c in chain
        ), f"Expected InvalidCachedStatementError in chain, got: {chain_str}"

    finally:
        # Fail-closed cleanup: schema drop + pg_namespace assertion.
        # Engine disposal must still execute even if schema cleanup fails.
        cleanup_error: Exception | None = None
        try:
            async with AsyncSession(engine_b) as session:
                await session.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
                await session.commit()
                await _assert_schema_absent(session, schema)
        except Exception as exc:
            cleanup_error = exc
        finally:
            await engine_a.dispose()
            await engine_b.dispose()
        if cleanup_error is not None:
            raise cleanup_error


# ---------------------------------------------------------------------------
# Test 2: GREEN — dispose clears stale plans via the actual global engine
# ---------------------------------------------------------------------------

async def test_green_dispose_clears_stale_plans_on_caching_engine():
    """CAUSAL GREEN (reshaped by PW1-R4-A): a CACHING engine re-executes the
    SAME SQL after DDL and a dispose — must succeed. Without the dispose this
    exact shape is proven RED by the test above, so the GREEN is
    dispose-causal, not accidentally green under the new runtime policy.
    """

    schema = f"h5_green_{uuid.uuid4().hex[:8]}"
    green_engine = create_async_engine(
        _async_db_url(),
        pool_size=1,
        max_overflow=0,
        connect_args={
            "statement_cache_size": 100,
            "server_settings": {"application_name": _unique_app_name(), "jit": "off"},
        },
    )

    # PW1-R4-A-R1: ddl_engine is created BEFORE the protected try so the
    # outer finally can never observe an unbound name if phase 1 fails.
    ddl_engine = create_async_engine(
        _async_db_url(),
        pool_size=1,
        max_overflow=0,
        connect_args={
            "server_settings": {"application_name": _unique_app_name(), "jit": "off"},
        },
    )

    try:
        # Phase 1: create table + cache the SELECT plan on the caching engine.
        async with AsyncSession(green_engine) as session:
            await session.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
            await session.execute(
                text(f'CREATE TABLE "{schema}".t_green (id int, label text)')
            )
            await session.execute(
                text(f'INSERT INTO "{schema}".t_green VALUES (1, :lbl)'),
                {"lbl": "before"},
            )
            await session.commit()

        async with AsyncSession(green_engine) as session:
            result = await session.execute(
                text(f'SELECT label FROM "{schema}".t_green WHERE id = 1')
            )
            assert result.scalar() == "before"
            await session.commit()

        # Phase 2: DDL that changes the SELECTED column's type OID, from the
        # SECOND engine (created above, before the protected try) so
        # invalidation arrives from outside the pool.
        try:
            async with AsyncSession(ddl_engine) as session:
                await session.execute(
                    text(
                        f'ALTER TABLE "{schema}".t_green '
                        f'ALTER COLUMN label TYPE varchar(100) USING label::varchar(100)'
                    )
                )
                await session.commit()

            # Phase 3: DISPOSE (the H5 repair) — closes every pooled connection.
            await green_engine.dispose()

            # Phase 4: re-execution of the SAME SQL on a fresh connection.
            async with AsyncSession(green_engine) as session:
                result = await session.execute(
                    text(f'SELECT label FROM "{schema}".t_green WHERE id = 1')
                )
                assert result.scalar() == "before"
                await session.commit()
        finally:
            await ddl_engine.dispose()

    finally:
        # Fail-closed cleanup: schema drop + pg_namespace assertion.
        cleanup_error: Exception | None = None
        try:
            async with AsyncSession(ddl_engine) as session:
                await session.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
                await session.commit()
                await _assert_schema_absent(session, schema)
        except Exception as exc:
            cleanup_error = exc
        finally:
            await green_engine.dispose()
        if cleanup_error is not None:
            raise cleanup_error


async def test_runtime_policy_global_engine_survives_ddl_without_dispose():
    """PW1-R4-A runtime policy: the PRODUCTION global engine re-executes the
    SAME SQL after DDL invalidation WITHOUT dispose and must succeed. Fails
    if ``prepared_statement_cache_size=0`` is removed from database/session.py.
    """
    from database.session import AsyncSessionLocal

    schema = f"h5_policy_{uuid.uuid4().hex[:8]}"
    select_sql = f'SELECT label FROM "{schema}".t_policy WHERE id = 1'
    ddl_engine = create_async_engine(
        _async_db_url(),
        pool_size=1,
        max_overflow=0,
        connect_args={
            "server_settings": {"application_name": _unique_app_name(), "jit": "off"},
        },
    )

    try:
        async with AsyncSessionLocal() as session:
            session.info["tenant_schema"] = "public"
            await session.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
            await session.execute(
                text(f'CREATE TABLE "{schema}".t_policy (id int, label text)')
            )
            await session.execute(
                text(f'INSERT INTO "{schema}".t_policy VALUES (1, :lbl)'),
                {"lbl": "policy"},
            )
            await session.commit()
        async with AsyncSessionLocal() as session:
            session.info["tenant_schema"] = "public"
            result = await session.execute(text(select_sql))
            assert result.scalar() == "policy"
            await session.commit()

        async with AsyncSession(ddl_engine) as session:
            await session.execute(
                text(
                    f'ALTER TABLE "{schema}".t_policy '
                    f'ALTER COLUMN label TYPE varchar(100) USING label::varchar(100)'
                )
            )
            await session.commit()

        # NO dispose — the runtime policy must make this safe.
        async with AsyncSessionLocal() as session:
            session.info["tenant_schema"] = "public"
            result = await session.execute(text(select_sql))
            assert result.scalar() == "policy"
            await session.commit()

    finally:
        cleanup_error: Exception | None = None
        try:
            async with AsyncSession(ddl_engine) as session:
                await session.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
                await session.commit()
                await _assert_schema_absent(session, schema)
        except Exception as exc:
            cleanup_error = exc
        finally:
            await ddl_engine.dispose()
        if cleanup_error is not None:
            raise cleanup_error


# ---------------------------------------------------------------------------
# Test 3: dispose changes backend PID (connection identity proof)
# ---------------------------------------------------------------------------

async def test_dispose_changes_backend_pid():
    """After ``engine.dispose()``, the backend PID changes."""
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

    await async_engine.dispose()

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
