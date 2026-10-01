"""Event-loop-safe helpers for synchronous tests that invoke async code."""

from __future__ import annotations

import asyncio
import os
import re
import time
import warnings
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from typing import TypeVar
from urllib.parse import urlparse, urlunparse
from uuid import uuid4

from alembic import command
from alembic.config import Config


T = TypeVar("T")
_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
_TEST_DATABASE_NAME = re.compile(r"^(?:test|pytest|ci)[_-][a-z0-9_-]+$")
_TEMP_DATABASE_PREFIX = re.compile(r"^[a-z][a-z0-9_]{2,40}$")
_TEMP_DB_SESSION_WAIT_SECONDS = 5.0
_TEMP_DB_SESSION_POLL_SECONDS = 0.05

# Three-identity test topology (CTO-AUTH-MPANGO-PROMOTION-A180050-G1-R2C-
# TEST-CONTRACT-20260925):
#   TEST_DATABASE_URL           runtime app identity (never gains CREATEDB/
#                               CREATEROLE/public CREATE)
#   TEST_MIGRATION_DATABASE_URL migration authority (database owner; Alembic
#                               and migration DDL run under this identity)
#   TEST_OPERATOR_DATABASE_URL  one-shot operator for precise create/drop of
#                               disposable databases and task role supply
#   TEST_ADMIN_DATABASE_URL     optional task cluster admin for product
#                               provisioner scenarios that contractually
#                               require a real administrator; never a test
#                               data source
# All keys must share one task endpoint, one test_-marked source database
# and pairwise-distinct users; a missing required key, a wrong endpoint or a
# wrong identity is rejected by name BEFORE any write.
_MIGRATION_URL_ENV = "TEST_MIGRATION_DATABASE_URL"
_OPERATOR_URL_ENV = "TEST_OPERATOR_DATABASE_URL"
_ADMIN_URL_ENV = "TEST_ADMIN_DATABASE_URL"
_shared_test_pool = None


def record_shared_test_pool(engine, loop) -> None:
    """Track the loop at actual asyncpg allocation, not the current-loop slot."""
    global _shared_test_pool
    _shared_test_pool = (engine, loop)


def _release_shared_test_pool() -> None:
    global _shared_test_pool
    if _shared_test_pool is None:
        return
    engine, owner = _shared_test_pool
    pool = engine.pool
    if pool.checkedout():
        raise RuntimeError("TEST_POOL_BOUNDARY_REFUSED_CHECKED_OUT_CONNECTION")
    if pool.checkedin():
        if owner.is_closed() or owner.is_running():
            raise RuntimeError("TEST_POOL_BOUNDARY_REFUSED_UNAVAILABLE_OWNER_LOOP")
        owner.run_until_complete(engine.dispose())
    _shared_test_pool = None


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
    try:
        _release_shared_test_pool()
    except BaseException:
        if hasattr(awaitable, "close"):
            awaitable.close()
        raise
    try:
        return loop.run_until_complete(awaitable)
    finally:
        # A synchronous test loop cannot lend asyncpg connections to the
        # later pytest session loop. Pooling remains enabled within the call.
        _release_shared_test_pool()


def _current_loop_slot() -> asyncio.AbstractEventLoop | None:
    """Read the thread's current-loop slot without requiring a loop to exist.

    Returns None when the policy raises (slot explicitly cleared). On the
    very first call in a thread the policy auto-creates a loop and installs
    it; that loop is returned and save/restore then faithfully preserves it.
    """
    policy = asyncio.get_event_loop_policy()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            return policy.get_event_loop()
    except RuntimeError:
        return None


def _run_alembic_preserving_loop(operation: Callable[[], None]) -> None:
    """Run one in-process Alembic env execution without leaking its loop.

    env.py's online path calls asyncio.run(), whose Runner cleanup closes its
    private loop AND clears the thread's current-loop slot
    (set_event_loop(None)). Under a pytest-asyncio session-scoped loop this
    poisons every later async node: asyncio.get_event_loop() then raises
    "There is no current event loop". Save the caller's exact slot (which may
    legitimately be None) before the operation and restore it afterwards; a
    saved loop that the operation somehow closed is never re-installed.
    """
    loop = _current_loop_slot()
    try:
        operation()
    finally:
        if loop is None or not loop.is_closed():
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


def _per_url_shape_checks(parsed, label: str, *, require_test_name: bool = True) -> str:
    """Apply the per-URL safety shape rules to one sanctioned identity URL."""
    allowed_hosts = set(_LOOPBACK_HOSTS)
    allowed_hosts.update(
        host.strip().lower()
        for host in os.environ.get("MPANGO_TEMP_DB_ALLOWED_HOSTS", "").split(",")
        if host.strip()
    )
    if (parsed.hostname or "").lower() not in allowed_hosts:
        raise RuntimeError(f"{label} host is not explicitly allowed")

    port = parsed.port or 5432
    allowed_ports = {
        value.strip()
        for value in os.environ.get("MPANGO_TEMP_DB_ALLOWED_PORTS", "").split(",")
        if value.strip()
    }
    if str(port) not in allowed_ports:
        raise RuntimeError(f"{label} port is not explicitly allowed")

    source_database = parsed.path.lstrip("/").lower()
    if require_test_name and not _TEST_DATABASE_NAME.fullmatch(source_database):
        raise RuntimeError(f"{label} must have an explicit test name")
    username = (parsed.username or "").lower()
    if username == "mpango" or "prod" in username:
        raise RuntimeError(f"{label} user is not test-safe")
    return username


def _sanctioned_test_identities() -> dict[str, tuple[object, str]]:
    """Resolve and cross-check the sanctioned test identities.

    Returns {"app": (parsed, raw), "migration": ..., "operator": ...[, "admin"]:
    ...} where parsed is the sync-style urlparse of each key.  Every failure
    mode is a named refusal raised BEFORE any write.
    """
    raws = {
        "app": os.environ.get("TEST_DATABASE_URL"),
        "migration": os.environ.get(_MIGRATION_URL_ENV),
        "operator": os.environ.get(_OPERATOR_URL_ENV),
        "admin": os.environ.get(_ADMIN_URL_ENV),
    }
    required = ("app", "migration", "operator")
    for label in required:
        if not raws[label]:
            raise RuntimeError(
                "temporary database topology requires TEST_DATABASE_URL, "
                f"{_MIGRATION_URL_ENV} and {_OPERATOR_URL_ENV} to be set "
                f"(missing: the {label} identity)"
            )
    raws = {label: raw for label, raw in raws.items() if raw}

    identities: dict[str, tuple[object, str]] = {}
    for label, raw in raws.items():
        sync_url = raw.replace("postgresql+asyncpg://", "postgresql://", 1)
        parsed = urlparse(sync_url)
        if parsed.scheme != "postgresql":
            raise RuntimeError(f"{label} identity must use PostgreSQL")
        if label == "admin":
            # The cluster admin targets the maintenance database; it is
            # never a test data source, so the test-name rule does not
            # apply, but an explicit maintenance target is mandatory.
            if parsed.path.lstrip("/") != "postgres":
                raise RuntimeError(
                    "admin identity must target the /postgres maintenance "
                    "database"
                )
            _per_url_shape_checks(
                parsed, f"{label} identity", require_test_name=False)
        else:
            _per_url_shape_checks(parsed, f"{label} identity")
        identities[label] = (parsed, raw)

    endpoints = {
        label: ((parsed.hostname or "").lower(), parsed.port or 5432)
        for label, (parsed, _) in identities.items()
    }
    if len(set(endpoints.values())) != 1:
        raise RuntimeError(
            "temporary database topology requires one task endpoint: the "
            "app, migration and operator identities disagree on host/port"
        )
    databases = {
        parsed.path.lstrip("/").lower()
        for label, (parsed, _) in identities.items()
        if label != "admin"
    }
    if len(databases) != 1:
        raise RuntimeError(
            "temporary database topology requires one test source database: "
            "the app, migration and operator identities name different "
            "databases"
        )
    users = {
        label: (parsed.username or "").lower()
        for label, (parsed, _) in identities.items()
    }
    if len(set(users.values())) != len(users):
        raise RuntimeError(
            "temporary database topology requires pairwise-distinct users: "
            "app, migration authority, operator and cluster admin must be "
            "different roles"
        )
    return identities


@dataclass(frozen=True)
class MigrationPrepIdentity:
    url: str = field(repr=False)
    user: str
    database: str


def migration_prep_identity() -> MigrationPrepIdentity:
    """Freeze approved topology before connecting; never echo URL values."""
    if os.environ.get("MPANGO_ENV") not in {"test", "testing"}:
        raise RuntimeError("PUBLIC_PREP_REFUSED_NOT_TEST_ENVIRONMENT")
    identities = _sanctioned_test_identities()
    parsed, raw = identities["migration"]
    return MigrationPrepIdentity(raw, parsed.username, parsed.path.lstrip("/"))


def assert_migration_public_connection(connection, identity, objects=()) -> None:
    """Read-only proof on the actual write connection, including absent objects."""
    from sqlalchemy import text

    def rows(statement):
        if hasattr(connection, "cursor"):
            with connection.cursor() as cursor:
                cursor.execute(statement)
                return cursor.fetchall()
        return connection.execute(text(statement)).all()

    user, database = rows("SELECT current_user, current_database()")[0]
    if (user, database) != (identity.user, identity.database):
        raise RuntimeError("PUBLIC_PREP_REFUSED_ACTUAL_IDENTITY_MISMATCH")
    # CREATEROLE is the existing migration-011 reporting-role contract;
    # CREATEDB identifies the operator, and is never a preparation role.
    role = rows("SELECT rolsuper, rolcreatedb, rolreplication, "
                "rolbypassrls FROM pg_roles WHERE rolname = current_user")[0]
    if any(role):
        raise RuntimeError("PUBLIC_PREP_REFUSED_PRIVILEGED_ROLE")
    owner = rows("SELECT pg_get_userbyid(datdba) FROM pg_database "
                 "WHERE datname = current_database()")[0][0]
    if owner != user:
        raise RuntimeError("PUBLIC_PREP_REFUSED_DATABASE_OWNER")
    schema = rows("SELECT pg_get_userbyid(nspowner), "
                  "has_schema_privilege(current_user, oid, 'CREATE') "
                  "FROM pg_namespace WHERE nspname = 'public'")
    if not schema or schema[0][0] not in (user, "pg_database_owner") or not schema[0][1]:
        raise RuntimeError("PUBLIC_PREP_REFUSED_SCHEMA_OWNER")
    owners = dict(rows("SELECT c.relname, pg_get_userbyid(c.relowner) "
                       "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                       "WHERE n.nspname='public'"))
    if any(name in owners and owners[name] != user for name in objects):
        raise RuntimeError("PUBLIC_PREP_REFUSED_OBJECT_OWNER")


@asynccontextmanager
async def migration_public_prep(objects):
    """Own a short migration connection; business sessions keep app identity."""
    from sqlalchemy.ext.asyncio import create_async_engine

    identity = migration_prep_identity()
    engine = create_async_engine(identity.url.replace(
        "postgresql://", "postgresql+asyncpg://", 1))
    try:
        async with engine.begin() as connection:
            await connection.run_sync(
                lambda sync: assert_migration_public_connection(sync, identity, objects))
            yield connection
    finally:
        await engine.dispose()


def _validate_temporary_database_source(source_url: str):
    """Require positive authorization before destructive database operations."""
    if os.environ.get("MPANGO_ENV") not in {"test", "testing"}:
        raise RuntimeError("temporary database creation requires a test environment")
    if os.environ.get("MPANGO_ALLOW_TEMP_DB_CREATE") != "1":
        raise RuntimeError("temporary database creation requires explicit opt-in")

    identities = _sanctioned_test_identities()

    admin_raw = os.environ.get(_ADMIN_URL_ENV)
    if admin_raw and _connection_identity(source_url) == _connection_identity(
        admin_raw
    ):
        raise RuntimeError(
            "temporary database source must not be the cluster-admin "
            "identity: the admin serves product provisioner scenarios, it "
            "is never a test data source"
        )
    if _connection_identity(source_url) == _connection_identity(
        os.environ[_OPERATOR_URL_ENV]
    ):
        raise RuntimeError(
            "temporary database source must not be the operator identity: "
            "the operator creates and drops databases, it is never a test "
            "data source"
        )
    sanctioned_sources = {
        _connection_identity(os.environ["TEST_DATABASE_URL"]),
        _connection_identity(os.environ[_MIGRATION_URL_ENV]),
    }
    if _connection_identity(source_url) not in sanctioned_sources:
        raise RuntimeError(
            "temporary database source must match TEST_DATABASE_URL or "
            f"{_MIGRATION_URL_ENV}"
        )

    parsed = urlparse(source_url.replace("postgresql+asyncpg://", "postgresql://", 1))
    if parsed.scheme != "postgresql":
        raise RuntimeError("temporary database source must use PostgreSQL")
    return identities, parsed


class TemporaryDatabaseTeardownError(RuntimeError):
    """Fail-closed, sanitized temporary-database teardown failure.

    Messages are static and contain no source/admin URLs, hosts, users, or
    credentials.
    """


def _teardown_temporary_database(admin, database: str) -> None:
    """Session-aware teardown of exactly one generated temporary database.

    Within ONE bounded monotonic deadline the loop enumerates the sessions
    attached to the exact generated database name, terminates only sessions
    owned by the current (non-superuser) test role, and attempts the exact
    DROP. ObjectInUse is the only retryable DROP error (a session attached to
    the database or raced in between enumeration and drop); every other DROP
    or privilege error fails closed immediately. A DROP that stays ObjectInUse
    until the deadline raises a sanitized deterministic error instead of
    attempting privilege escalation. The exact drop uses no IF EXISTS, so an
    unexpected absence is never masked, and absence is independently proved
    after a successful drop. InsufficientPrivilege, ObjectInUse, DROP
    failures, and timeouts are never silently suppressed.
    """
    import psycopg2
    from psycopg2 import sql

    deadline = time.monotonic() + _TEMP_DB_SESSION_WAIT_SECONDS
    with admin.cursor() as cursor:
        cursor.execute("SELECT current_user")
        (current_user,) = cursor.fetchone()
        while True:
            cursor.execute(
                "SELECT pid, usename FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid() ORDER BY pid",
                (database,),
            )
            sessions = cursor.fetchall()
            for pid, usename in sessions:
                if usename == current_user:
                    cursor.execute("SELECT pg_terminate_backend(%s)", (pid,))
            if not sessions:
                try:
                    cursor.execute(
                        sql.SQL("DROP DATABASE {}").format(sql.Identifier(database))
                    )
                    break
                except psycopg2.errors.ObjectInUse:
                    admin.rollback()
            if time.monotonic() >= deadline:
                raise TemporaryDatabaseTeardownError(
                    "temporary database teardown deadline exceeded: sessions "
                    "owned by other roles are still attached to the generated "
                    "test database"
                )
            time.sleep(_TEMP_DB_SESSION_POLL_SECONDS)
        cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (database,))
        if cursor.fetchone() is not None:
            raise TemporaryDatabaseTeardownError(
                "temporary database teardown verification failed: generated "
                "test database still exists after drop"
            )


class TemporaryDatabaseURL(str):
    """Migration-authority URL of a disposable, migration-owned database.

    The ``str`` value carries the MIGRATION identity (the database owner) so
    existing consumers that run Alembic / migration DDL on the yielded URL
    keep working unchanged.  ``app_url`` carries the runtime app identity
    (asyncpg scheme) on the same database for bootstrap/runtime consumers.
    """

    app_url: str

    def __new__(cls, migration_url: str, app_url: str) -> "TemporaryDatabaseURL":
        self = super().__new__(cls, migration_url)
        self.app_url = app_url
        return self


@contextmanager
def temporary_database_url(source_url: str, prefix: str):
    """Create and remove a disposable migration-owned database.

    The one-shot operator creates the database with ``OWNER <migration
    authority>``; the yielded URL is the migration identity on that database
    (``.app_url`` is the runtime identity).  Teardown runs as the migration
    authority — the database owner — so DROP DATABASE needs no privilege
    escalation.  If the test body raises and cleanup also fails, both exact
    exception objects are delivered in one BaseExceptionGroup so the original
    test failure is never masked.  The admin connections always close.
    """
    import psycopg2
    from psycopg2 import sql

    identities, parsed = _validate_temporary_database_source(source_url)
    if not _TEMP_DATABASE_PREFIX.fullmatch(prefix):
        raise RuntimeError("temporary database prefix is invalid")

    migration_parsed = identities["migration"][0]
    app_parsed = identities["app"][0]
    migration_user = (migration_parsed.username or "").lower()

    database = f"test_{prefix}_{uuid4().hex[:12]}"
    operator_admin_url = urlunparse(identities["operator"][0]._replace(path="/postgres"))
    migration_admin_url = urlunparse(migration_parsed._replace(path="/postgres"))

    operator = psycopg2.connect(operator_admin_url)
    operator.autocommit = True
    created = False
    try:
        with operator.cursor() as cursor:
            cursor.execute(
                sql.SQL("CREATE DATABASE {} OWNER {}").format(
                    sql.Identifier(database), sql.Identifier(migration_user)
                )
            )
        created = True
        migration_url = urlunparse(migration_parsed._replace(path=f"/{database}"))
        app_url = urlunparse(
            app_parsed._replace(
                scheme="postgresql+asyncpg", path=f"/{database}"
            )
        )
        body_exc: BaseException | None = None
        try:
            yield TemporaryDatabaseURL(migration_url, app_url)
        except BaseException as exc:
            body_exc = exc
        cleanup_exc: BaseException | None = None
        try:
            if created:
                owner = psycopg2.connect(migration_admin_url)
                owner.autocommit = True
                try:
                    _teardown_temporary_database(owner, database)
                finally:
                    owner.close()
        except BaseException as exc:
            cleanup_exc = exc
        if body_exc is not None and cleanup_exc is not None:
            raise BaseExceptionGroup(
                "temporary database cleanup failed after test body failure",
                [body_exc, cleanup_exc],
            )
        if body_exc is not None:
            raise body_exc
        if cleanup_exc is not None:
            raise cleanup_exc
    finally:
        operator.close()
