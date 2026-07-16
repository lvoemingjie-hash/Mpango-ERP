"""Event-loop-safe helpers for synchronous tests that invoke async code."""

from __future__ import annotations

import asyncio
import warnings
from collections.abc import Awaitable, Callable
from contextlib import contextmanager
from typing import TypeVar
from urllib.parse import urlparse, urlunparse
from uuid import uuid4

from alembic import command
from alembic.config import Config


T = TypeVar("T")


def _current_or_new_loop() -> asyncio.AbstractEventLoop:
    policy = asyncio.get_event_loop_policy()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            loop = policy.get_event_loop()
    except RuntimeError:
        loop = policy.new_event_loop()
        policy.set_event_loop(loop)
    if loop.is_closed():
        loop = policy.new_event_loop()
        policy.set_event_loop(loop)
    return loop


def run_coroutine(awaitable: Awaitable[T]) -> T:
    """Run an awaitable without creating and closing a throwaway event loop."""
    loop = _current_or_new_loop()
    if loop.is_running():
        raise RuntimeError("run_coroutine cannot run inside an active event loop")
    return loop.run_until_complete(awaitable)


def _run_alembic_preserving_loop(operation: Callable[[], None]) -> None:
    """Restore pytest's current loop after Alembic's async env completes."""
    loop = _current_or_new_loop()
    try:
        operation()
    finally:
        if not loop.is_closed():
            asyncio.set_event_loop(loop)


def run_alembic_upgrade(config: Config, revision: str = "head") -> None:
    _run_alembic_preserving_loop(lambda: command.upgrade(config, revision))


def run_alembic_downgrade(config: Config, revision: str) -> None:
    _run_alembic_preserving_loop(lambda: command.downgrade(config, revision))


@contextmanager
def temporary_database_url(source_url: str, prefix: str):
    """Create and remove a disposable database on an explicit test server."""
    import psycopg2
    from psycopg2 import sql

    sync_url = source_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    parsed = urlparse(sync_url)
    source_database = parsed.path.lstrip("/").lower()
    if source_database in {"mpango_erp", "postgres"}:
        raise RuntimeError("temporary database source must be a non-production test database")

    database = f"{prefix}_{uuid4().hex[:12]}"
    admin_url = urlunparse(parsed._replace(path="/postgres"))
    admin = psycopg2.connect(admin_url)
    admin.autocommit = True
    try:
        with admin.cursor() as cursor:
            cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
        yield urlunparse(parsed._replace(path=f"/{database}"))
    finally:
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (database,),
            )
            cursor.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(database)))
        admin.close()
