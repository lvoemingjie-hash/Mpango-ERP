"""H4 regression: event-loop/pool isolation after run_coroutine migration.

DC-12R1-H4-R1: Verifies that replacing ``asyncio.run()`` with
``run_coroutine()`` in the R4-R1 real Alembic upgrade test file preserves
event-loop identity and does not contaminate the global ``async_engine``'s
asyncpg connection pool.

Root cause recap (DC-12R1-H4-R0):
    ``asyncio.run()`` creates a new event loop, runs the coroutine, then
    **closes** the loop and sets the current loop to ``None``.  When this
    happens between tests that share a session-scoped pytest-asyncio loop,
    asyncpg protocol Futures created on the original loop become orphaned,
    producing ``InterfaceError: another operation in progress`` or
    ``RuntimeError: Task got Future attached to a different loop``.

    ``run_coroutine()`` uses ``loop.run_until_complete()`` on the existing
    loop (or a new persistent one), avoiding throwaway loop creation.
"""
from __future__ import annotations

import asyncio
import os
import warnings

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from database.session import AsyncSessionLocal, async_engine
from tests.async_test_utils import run_coroutine


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _async_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


def _get_current_loop() -> asyncio.AbstractEventLoop:
    policy = asyncio.get_event_loop_policy()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        return policy.get_event_loop()


async def _local_engine_lifecycle() -> None:
    """Simulate the _bootstrap_and_revert_to_036 pattern.

    Creates a **local** async engine, runs a query, and disposes it -- the
    same lifecycle that ``_bootstrap_and_revert_to_036`` performs in the
    R4-R1 test file.
    """
    url = _async_url(os.environ["DATABASE_URL"])
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    finally:
        await engine.dispose()


async def _select_one_via_global() -> int:
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("SELECT 1"))
        return result.scalar()


async def _select_one_after_dispose() -> int:
    await async_engine.dispose()
    return await _select_one_via_global()


async def _rollback_via_global() -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(text("SELECT 1"))
        await session.rollback()


async def _count_idle_mpango_connections() -> int:
    await async_engine.dispose()
    url = _async_url(os.environ["DATABASE_URL"])
    check_engine = create_async_engine(url)
    try:
        async with check_engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE application_name = 'Mpango ERP' "
                    "AND state = 'idle'"
                )
            )
            return result.scalar()
    finally:
        await check_engine.dispose()


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------

class TestRunCoroutinePreservesEventLoop:
    """run_coroutine must not create/close throwaway event loops."""

    def test_loop_identity_unchanged(self):
        loop_before = _get_current_loop()
        run_coroutine(_local_engine_lifecycle())
        loop_after = _get_current_loop()
        assert loop_before is loop_after, (
            f"Event loop changed: {id(loop_before)} -> {id(loop_after)}"
        )

    def test_loop_still_open(self):
        run_coroutine(_local_engine_lifecycle())
        loop = _get_current_loop()
        assert not loop.is_closed(), "Event loop was closed"

    def test_loop_not_none_after_run_coroutine(self):
        run_coroutine(_local_engine_lifecycle())
        loop = _get_current_loop()
        assert loop is not None, "Current event loop is None after run_coroutine"


class TestGlobalEngineNotContaminated:
    """The global async_engine pool must work after run_coroutine calls."""

    def test_select_one_via_global_engine(self):
        run_coroutine(_local_engine_lifecycle())
        assert run_coroutine(_select_one_via_global()) == 1

    def test_select_one_after_engine_dispose(self):
        """Simulate the async_session fixture's dispose+recreate cycle."""
        run_coroutine(_local_engine_lifecycle())
        assert run_coroutine(_select_one_after_dispose()) == 1

    def test_no_interface_error_on_rollback(self):
        """The InterfaceError 'another operation in progress' must not occur."""
        run_coroutine(_local_engine_lifecycle())
        run_coroutine(_rollback_via_global())


class TestNoLeakedConnections:
    """No idle/rollback connections should remain after run_coroutine."""

    def test_no_idle_mpango_connections_after_local_dispose(self):
        run_coroutine(_local_engine_lifecycle())
        leaked = run_coroutine(_count_idle_mpango_connections())
        assert leaked == 0, f"{leaked} leaked idle 'Mpango ERP' connections"
