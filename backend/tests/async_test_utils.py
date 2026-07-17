"""Event-loop-safe helpers for synchronous tests that invoke async code."""

from __future__ import annotations

import asyncio
import os
import re
import warnings
from collections.abc import Awaitable, Callable
from contextlib import contextmanager
from typing import TypeVar
from urllib.parse import urlparse, urlunparse
from uuid import uuid4

from alembic import command
from alembic.config import Config


T = TypeVar("T")
_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
_TEST_DATABASE_NAME = re.compile(r"^(?:test|pytest|ci)[_-][a-z0-9_-]+$")
_TEMP_DATABASE_PREFIX = re.compile(r"^[a-z][a-z0-9_]{2,40}$")


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


def _connection_identity(url: str) -> tuple[object, ...]:
    parsed = urlparse(url.replace("postgresql+asyncpg://", "postgresql://", 1))
    return (
        parsed.scheme,
        parsed.username,
        parsed.password,
        (parsed.hostname or "").lower(),
        parsed.port or 5432,
        parsed.path,
        parsed.query,
    )


def _validate_temporary_database_source(source_url: str):
    """Require positive authorization before destructive database operations."""
    if os.environ.get("MPANGO_ENV") not in {"test", "testing"}:
        raise RuntimeError("temporary database creation requires a test environment")
    if os.environ.get("MPANGO_ALLOW_TEMP_DB_CREATE") != "1":
        raise RuntimeError("temporary database creation requires explicit opt-in")

    configured_url = os.environ.get("TEST_DATABASE_URL")
    if not configured_url:
        raise RuntimeError("temporary database creation requires TEST_DATABASE_URL")
    if _connection_identity(configured_url) != _connection_identity(source_url):
        raise RuntimeError("temporary database source must match TEST_DATABASE_URL")

    sync_url = source_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    parsed = urlparse(sync_url)
    if parsed.scheme != "postgresql":
        raise RuntimeError("temporary database source must use PostgreSQL")

    allowed_hosts = set(_LOOPBACK_HOSTS)
    allowed_hosts.update(
        host.strip().lower()
        for host in os.environ.get("MPANGO_TEMP_DB_ALLOWED_HOSTS", "").split(",")
        if host.strip()
    )
    if (parsed.hostname or "").lower() not in allowed_hosts:
        raise RuntimeError("temporary database source host is not explicitly allowed")

    port = parsed.port or 5432
    allowed_ports = {
        value.strip()
        for value in os.environ.get("MPANGO_TEMP_DB_ALLOWED_PORTS", "").split(",")
        if value.strip()
    }
    if str(port) not in allowed_ports:
        raise RuntimeError("temporary database source port is not explicitly allowed")

    source_database = parsed.path.lstrip("/").lower()
    if not _TEST_DATABASE_NAME.fullmatch(source_database):
        raise RuntimeError("temporary database source must have an explicit test name")
    username = (parsed.username or "").lower()
    if username == "mpango" or "prod" in username:
        raise RuntimeError("temporary database source user is not test-safe")
    return parsed


@contextmanager
def temporary_database_url(source_url: str, prefix: str):
    """Create and remove a disposable database on an explicit test server."""
    import psycopg2
    from psycopg2 import sql

    parsed = _validate_temporary_database_source(source_url)
    if not _TEMP_DATABASE_PREFIX.fullmatch(prefix):
        raise RuntimeError("temporary database prefix is invalid")

    database = f"test_{prefix}_{uuid4().hex[:12]}"
    admin_url = urlunparse(parsed._replace(path="/postgres"))
    admin = psycopg2.connect(admin_url)
    admin.autocommit = True
    created = False
    try:
        with admin.cursor() as cursor:
            cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
        created = True
        yield urlunparse(parsed._replace(path=f"/{database}"))
    finally:
        if created:
            with admin.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = %s AND pid <> pg_backend_pid()",
                    (database,),
                )
                cursor.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(database)))
        admin.close()
