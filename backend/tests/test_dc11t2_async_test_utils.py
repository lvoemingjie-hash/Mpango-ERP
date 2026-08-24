import asyncio
import os
import secrets
import threading
import time
import uuid
import warnings
from urllib.parse import urlparse

import psycopg2
import pytest
from psycopg2 import sql

from tests import async_test_utils
from tests.async_test_utils import TemporaryDatabaseTeardownError


TEST_SOURCE_URL = "postgresql://test_runner@127.0.0.1:55448/test_dc11t2_source"


def _authorize_temp_db(monkeypatch, source_url=TEST_SOURCE_URL):
    monkeypatch.setenv("MPANGO_ENV", "test")
    monkeypatch.setenv("MPANGO_ALLOW_TEMP_DB_CREATE", "1")
    monkeypatch.setenv("MPANGO_TEMP_DB_ALLOWED_PORTS", "55448")
    monkeypatch.setenv("TEST_DATABASE_URL", source_url)
    monkeypatch.delenv("MPANGO_TEMP_DB_ALLOWED_HOSTS", raising=False)


@pytest.fixture()
def isolated_event_loop():
    policy = asyncio.get_event_loop_policy()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        try:
            previous = policy.get_event_loop()
        except RuntimeError:
            previous = None
    loop = policy.new_event_loop()
    policy.set_event_loop(loop)
    try:
        yield loop
    finally:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            try:
                current = policy.get_event_loop()
            except RuntimeError:
                current = None
        if current is not None and current is not previous and not current.is_closed():
            current.close()
        if previous is not None and not previous.is_closed():
            policy.set_event_loop(previous)
        else:
            policy.set_event_loop(policy.new_event_loop())


def test_run_coroutine_reuses_current_loop(isolated_event_loop):
    assert async_test_utils.run_coroutine(asyncio.sleep(0, result="ok")) == "ok"
    assert asyncio.get_event_loop() is isolated_event_loop
    assert not isolated_event_loop.is_closed()


def test_run_coroutine_replaces_closed_loop(isolated_event_loop):
    isolated_event_loop.close()
    assert async_test_utils.run_coroutine(asyncio.sleep(0, result=7)) == 7
    replacement = asyncio.get_event_loop()
    assert replacement is not isolated_event_loop
    assert not replacement.is_closed()


def test_alembic_upgrade_restores_current_loop(monkeypatch, isolated_event_loop):
    def clobber_current_loop(config, revision):
        asyncio.set_event_loop(None)

    monkeypatch.setattr(async_test_utils.command, "upgrade", clobber_current_loop)
    async_test_utils.run_alembic_upgrade(object(), "head")
    assert asyncio.get_event_loop() is isolated_event_loop


def test_alembic_downgrade_restores_current_loop(monkeypatch, isolated_event_loop):
    def clobber_current_loop(config, revision):
        asyncio.set_event_loop(None)

    monkeypatch.setattr(async_test_utils.command, "downgrade", clobber_current_loop)
    async_test_utils.run_alembic_downgrade(object(), "base")
    assert asyncio.get_event_loop() is isolated_event_loop


def test_temp_db_guard_accepts_explicit_loopback_test_source(monkeypatch):
    _authorize_temp_db(monkeypatch)

    parsed = async_test_utils._validate_temporary_database_source(TEST_SOURCE_URL)

    assert parsed.hostname == "127.0.0.1"
    assert parsed.port == 55448
    assert parsed.path == "/test_dc11t2_source"


@pytest.mark.parametrize(
    ("env_name", "env_value", "expected"),
    [
        ("MPANGO_ENV", "production", "test environment"),
        ("MPANGO_ALLOW_TEMP_DB_CREATE", "0", "explicit opt-in"),
        ("MPANGO_TEMP_DB_ALLOWED_PORTS", "55449", "port is not explicitly allowed"),
    ],
)
def test_temp_db_guard_rejects_missing_positive_authorization(
    monkeypatch, env_name, env_value, expected
):
    _authorize_temp_db(monkeypatch)
    monkeypatch.setenv(env_name, env_value)

    with pytest.raises(RuntimeError, match=expected):
        async_test_utils._validate_temporary_database_source(TEST_SOURCE_URL)


def test_temp_db_guard_rejects_source_not_matching_test_database_url(monkeypatch):
    _authorize_temp_db(monkeypatch)
    monkeypatch.setenv(
        "TEST_DATABASE_URL",
        "postgresql://test_runner@127.0.0.1:55448/test_other_source",
    )

    with pytest.raises(RuntimeError, match="must match TEST_DATABASE_URL"):
        async_test_utils._validate_temporary_database_source(TEST_SOURCE_URL)


def test_temp_db_guard_rejects_nonlocal_host(monkeypatch):
    source_url = "postgresql://test_runner@db.example.invalid:55448/test_dc11t2_source"
    _authorize_temp_db(monkeypatch, source_url)

    with pytest.raises(RuntimeError, match="host is not explicitly allowed"):
        async_test_utils._validate_temporary_database_source(source_url)


def test_temp_db_guard_rejects_unmarked_database_name(monkeypatch):
    source_url = "postgresql://test_runner@127.0.0.1:55448/customer_data"
    _authorize_temp_db(monkeypatch, source_url)

    with pytest.raises(RuntimeError, match="explicit test name"):
        async_test_utils._validate_temporary_database_source(source_url)


def test_temp_db_guard_rejects_production_user(monkeypatch):
    source_url = "postgresql://mpango@127.0.0.1:55448/test_dc11t2_source"
    _authorize_temp_db(monkeypatch, source_url)

    with pytest.raises(RuntimeError, match="user is not test-safe"):
        async_test_utils._validate_temporary_database_source(source_url)


def test_temporary_database_context_refuses_without_positive_guard(monkeypatch):
    monkeypatch.setenv("MPANGO_ENV", "test")
    monkeypatch.delenv("MPANGO_ALLOW_TEMP_DB_CREATE", raising=False)
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="explicit opt-in"):
        with async_test_utils.temporary_database_url(TEST_SOURCE_URL, "dc11t2"):
            pytest.fail("an unauthorized temporary database was created")


def test_temporary_database_context_rejects_untrusted_prefix(monkeypatch):
    _authorize_temp_db(monkeypatch)

    with pytest.raises(RuntimeError, match="prefix is invalid"):
        with async_test_utils.temporary_database_url(TEST_SOURCE_URL, "../unsafe"):
            pytest.fail("a temporary database with an unsafe prefix was created")


# ---------------------------------------------------------------------------
# R2-R4 (DC-12R1-MVP-L1-J1-H2-B): session-aware temporary-database teardown.
# These tests exercise the real PostgreSQL teardown contract: own-role sessions
# are terminated, sessions owned by other roles are waited out within a fixed
# bound, a persistent non-terminable session fails closed with a sanitized
# deterministic error, original test-body exceptions are preserved exactly,
# and a body failure plus cleanup failure produces one BaseExceptionGroup with
# both exact exception objects. Foreign sessions are created through a login
# role owned by the test role (no SUPERUSER and no pg_signal_backend is ever
# granted; no task credentials appear in any assertion output).
# ---------------------------------------------------------------------------

# R1 (DC-12R1-MVP-L1-J1-H2-B-R2-R4-R1): the foreign-session login role is now
# EPHEMERAL — its name and login value are randomly generated for every test
# run, created with quoted identifiers and a bound parameter (never string
# concatenation), torn down NOLOGIN-first with bounded fail-closed retries,
# and independently proven absent from pg_roles over a fresh connection.
# Error messages never contain role names, login values, URLs, hosts, or
# usernames. No SUPERUSER and no pg_signal_backend is ever granted.
_EPHEMERAL_ROLE_PREFIX = "dc11t2fr_"
_EPHEMERAL_ROLE_WAIT_SECONDS = 5.0
_EPHEMERAL_ROLE_POLL_SECONDS = 0.05
_ROLE_DROP_RETRYABLE = (
    psycopg2.errors.DependentObjectsStillExist,
    psycopg2.errors.ObjectInUse,
)


def _create_ephemeral_role(admin) -> tuple[str, str]:
    role = f"{_EPHEMERAL_ROLE_PREFIX}{uuid.uuid4().hex[:10]}"
    login_value = secrets.token_hex(16)
    with admin.cursor() as cursor:
        cursor.execute(
            sql.SQL("CREATE ROLE {} LOGIN PASSWORD %s").format(sql.Identifier(role)),
            (login_value,),
        )
    return role, login_value


def _drop_ephemeral_role(admin_connection_factory, role: str) -> None:
    """NOLOGIN first, then bounded DROP retries that fail closed, then a
    fresh-connection zero-residue proof over pg_roles."""
    admin = admin_connection_factory()
    try:
        with admin.cursor() as cursor:
            cursor.execute(
                sql.SQL("ALTER ROLE {} NOLOGIN").format(sql.Identifier(role))
            )
    finally:
        admin.close()
    deadline = time.monotonic() + _EPHEMERAL_ROLE_WAIT_SECONDS
    while True:
        admin = admin_connection_factory()
        try:
            with admin.cursor() as cursor:
                cursor.execute(
                    sql.SQL("DROP ROLE {}").format(sql.Identifier(role))
                )
            break
        except _ROLE_DROP_RETRYABLE:
            admin.rollback()
        finally:
            admin.close()
        if time.monotonic() >= deadline:
            raise AssertionError(
                "ephemeral test role teardown deadline exceeded: role could "
                "not be removed after bounded retries"
            )
        time.sleep(_EPHEMERAL_ROLE_POLL_SECONDS)
    proof = admin_connection_factory()
    try:
        with proof.cursor() as cursor:
            cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,))
            if cursor.fetchone() is not None:
                raise AssertionError(
                    "ephemeral test role teardown verification failed: role "
                    "still present in pg_roles"
                )
    finally:
        proof.close()


def _real_source_url() -> str:
    url = os.environ["TEST_DATABASE_URL"]
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


def _authorize_real_temp_db(monkeypatch) -> str:
    url = _real_source_url()
    parsed = urlparse(url)
    monkeypatch.setenv("MPANGO_ENV", "test")
    monkeypatch.setenv("MPANGO_ALLOW_TEMP_DB_CREATE", "1")
    monkeypatch.setenv("MPANGO_TEMP_DB_ALLOWED_HOSTS", parsed.hostname or "127.0.0.1")
    monkeypatch.setenv("MPANGO_TEMP_DB_ALLOWED_PORTS", str(parsed.port or 5432))
    monkeypatch.setenv("TEST_DATABASE_URL", url)
    return url


def _admin_connection() -> psycopg2.extensions.connection:
    parsed = urlparse(_real_source_url())
    admin = psycopg2.connect(
        f"postgresql://{parsed.username}:{parsed.password}@"
        f"{parsed.hostname}:{parsed.port or 5432}/postgres"
    )
    admin.autocommit = True
    return admin


def _database_exists(admin, database: str) -> bool:
    with admin.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (database,))
        return cursor.fetchone() is not None


def _database_of(url: str) -> str:
    return urlparse(url).path.lstrip("/")


def _wait_until_gone_then_drop(admin, database: str) -> None:
    for _ in range(100):
        with admin.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (database,),
            )
            (remaining,) = cursor.fetchone()
        if not remaining:
            break
        time.sleep(0.1)
    with admin.cursor() as cursor:
        cursor.execute(f'DROP DATABASE IF EXISTS "{database}"')


@pytest.fixture()
def admin_conn():
    admin = _admin_connection()
    yield admin
    admin.close()


@pytest.fixture(autouse=True, scope="module")
def _prove_no_ephemeral_role_residue():
    """Module-level zero-residue proof over a fresh connection (fail-closed)."""
    yield
    proof = _admin_connection()
    try:
        with proof.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM pg_roles WHERE rolname LIKE %s",
                (_EPHEMERAL_ROLE_PREFIX + "%",),
            )
            (remaining,) = cursor.fetchone()
    finally:
        proof.close()
    assert remaining == 0, "ephemeral test roles remain in pg_roles after the module"


@pytest.fixture()
def foreign_role(admin_conn):
    role, login_value = _create_ephemeral_role(admin_conn)
    yield role, login_value
    _drop_ephemeral_role(_admin_connection, role)


def _open_foreign_session(real_url: str, database: str, role: str, login_value: str):
    parsed = urlparse(real_url)
    return psycopg2.connect(
        f"postgresql://{role}:{login_value}@{parsed.hostname}:{parsed.port or 5432}/{database}"
    )


def test_temp_db_creates_and_drops_exact_database(monkeypatch, admin_conn):
    real_url = _authorize_real_temp_db(monkeypatch)

    with async_test_utils.temporary_database_url(real_url, "dc11t2ok") as temp_url:
        database = _database_of(temp_url)
        suffix = database.rsplit("_", 1)[1]
        assert database == f"test_dc11t2ok_{suffix}"
        assert len(suffix) == 12
        assert all(c in "0123456789abcdef" for c in suffix)
        assert _database_exists(admin_conn, database)

    assert not _database_exists(admin_conn, database)


def test_temp_db_terminates_own_role_session_and_drops(monkeypatch, admin_conn):
    real_url = _authorize_real_temp_db(monkeypatch)

    with async_test_utils.temporary_database_url(real_url, "dc11t2own") as temp_url:
        holder = psycopg2.connect(temp_url)
        holder_cursor = holder.cursor()
        holder_cursor.execute("SELECT 1")
        database = _database_of(temp_url)

    assert not _database_exists(admin_conn, database)
    with pytest.raises(psycopg2.Error):
        holder_cursor.execute("SELECT 1")
        holder.commit()
    holder.close()


def test_temp_db_waits_out_transient_foreign_session(monkeypatch, admin_conn, foreign_role):
    real_url = _authorize_real_temp_db(monkeypatch)
    role, login_value = foreign_role
    connected = threading.Event()

    def hold_transient(database):
        session = _open_foreign_session(real_url, database, role, login_value)
        cursor = session.cursor()
        cursor.execute("SELECT 1")
        connected.set()
        time.sleep(1.5)
        session.close()

    with async_test_utils.temporary_database_url(real_url, "dc11t2tr") as temp_url:
        database = _database_of(temp_url)
        worker = threading.Thread(target=hold_transient, args=(database,))
        worker.start()
        assert connected.wait(5)

    assert not _database_exists(admin_conn, database)
    worker.join(10)


def test_temp_db_persistent_foreign_session_fails_closed_sanitized(
    monkeypatch, admin_conn, foreign_role
):
    real_url = _authorize_real_temp_db(monkeypatch)
    role, login_value = foreign_role
    parsed = urlparse(real_url)
    secret_markers = (
        parsed.password or "",
        parsed.username or "",
        parsed.hostname or "",
        role,
        login_value,
    )

    with pytest.raises(TemporaryDatabaseTeardownError) as excinfo:
        with async_test_utils.temporary_database_url(real_url, "dc11t2ps") as temp_url:
            database = _database_of(temp_url)
            session = _open_foreign_session(real_url, database, role, login_value)
            cursor = session.cursor()
            cursor.execute("SELECT 1")

    session.close()
    message = str(excinfo.value)
    assert "sessions owned by other roles" in message
    for marker in secret_markers:
        if marker:
            assert marker not in message
    assert "postgresql://" not in message
    assert _database_exists(admin_conn, database), (
        "fail-closed teardown must not falsely report the database as cleaned"
    )
    _wait_until_gone_then_drop(admin_conn, database)


def test_temp_db_original_exception_preserved_by_identity(monkeypatch):
    real_url = _authorize_real_temp_db(monkeypatch)
    sentinel = ValueError("dc11t2 original body failure marker")

    with pytest.raises(ValueError) as excinfo:
        with async_test_utils.temporary_database_url(real_url, "dc11t2ex"):
            raise sentinel

    assert excinfo.value is sentinel


def test_temp_db_body_and_cleanup_failure_raise_exception_group(
    monkeypatch, admin_conn, foreign_role
):
    real_url = _authorize_real_temp_db(monkeypatch)
    role, login_value = foreign_role
    sentinel = ValueError("dc11t2 grouped body failure marker")

    with pytest.raises(BaseExceptionGroup) as excinfo:
        with async_test_utils.temporary_database_url(real_url, "dc11t2gr") as temp_url:
            database = _database_of(temp_url)
            session = _open_foreign_session(real_url, database, role, login_value)
            cursor = session.cursor()
            cursor.execute("SELECT 1")
            raise sentinel

    session.close()
    group = excinfo.value
    assert group.exceptions[0] is sentinel
    assert isinstance(group.exceptions[1], TemporaryDatabaseTeardownError)
    assert not isinstance(group.exceptions[1], ValueError)
    _wait_until_gone_then_drop(admin_conn, database)


# ---------------------------------------------------------------------------
# Scripted-admin contract tests (no live server): fail-closed presence proof
# and bounded deadline. These pin the internal contract deterministically:
# teardown must prove the database absent after DROP and must raise the
# sanitized deadline error when a non-terminable session persists.
# ---------------------------------------------------------------------------


class _ScriptedCursor:
    def __init__(self, script):
        self._script = script
        self._result = None
        self.polls = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, statement, params=None):
        text = statement if isinstance(statement, str) else str(statement)
        self._result = self._script(text, params, self)

    def fetchone(self):
        return self._result

    def fetchall(self):
        return self._result


class _ScriptedAdmin:
    def __init__(self, script):
        self._script = script
        self.closed = False
        self.rollbacks = 0

    def cursor(self):
        return _ScriptedCursor(self._script)

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


def test_teardown_fails_closed_when_database_remains_after_drop():
    def script(text, params, cursor):
        if text.startswith("SELECT current_user"):
            return ("h2btester",)
        if "pg_stat_activity" in text and "pid, usename" in text:
            return []
        if "DROP DATABASE" in text:
            return None
        if text.startswith("SELECT 1 FROM pg_database"):
            return (1,)
        raise AssertionError(f"unexpected statement: {text}")

    with pytest.raises(
        TemporaryDatabaseTeardownError, match="still exists after drop"
    ):
        async_test_utils._teardown_temporary_database(
            _ScriptedAdmin(script), "test_dc11t2fake"
        )


def test_teardown_times_out_on_persistent_foreign_sessions(monkeypatch):
    monkeypatch.setattr(async_test_utils, "_TEMP_DB_SESSION_WAIT_SECONDS", 0.3)
    monkeypatch.setattr(async_test_utils, "_TEMP_DB_SESSION_POLL_SECONDS", 0.02)

    def script(text, params, cursor):
        if text.startswith("SELECT current_user"):
            return ("h2btester",)
        if "pg_stat_activity" in text and "pid, usename" in text:
            cursor.polls += 1
            if cursor.polls > 500:
                raise RuntimeError("scripted poll budget exhausted")
            return [(4242, "postgres")]
        raise AssertionError(f"unexpected statement: {text}")

    with pytest.raises(
        TemporaryDatabaseTeardownError, match="sessions owned by other roles"
    ):
        async_test_utils._teardown_temporary_database(
            _ScriptedAdmin(script), "test_dc11t2fake"
        )


# ---------------------------------------------------------------------------
# R1 scripted contract tests: the exact DROP is attempted INSIDE the single
# bounded deadline loop; only ObjectInUse retries (re-enumerating the exact
# database sessions); any other DROP error fails closed immediately; the
# exact drop never masks an unexpected absence (no IF EXISTS).
# ---------------------------------------------------------------------------


def test_teardown_retries_drop_object_in_use_then_succeeds():
    attempts = {"n": 0}

    def script(text, params, cursor):
        if text.startswith("SELECT current_user"):
            return ("h2btester",)
        if "pg_stat_activity" in text and "pid, usename" in text:
            return []
        if "DROP DATABASE" in text:
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise psycopg2.errors.ObjectInUse(
                    "database is being accessed by other users"
                )
            return None
        if text.startswith("SELECT 1 FROM pg_database"):
            return None
        raise AssertionError(f"unexpected statement: {text}")

    admin = _ScriptedAdmin(script)
    async_test_utils._teardown_temporary_database(admin, "test_dc11t2fake")
    assert attempts["n"] == 2
    assert admin.rollbacks == 1


def test_teardown_persistent_object_in_use_fails_closed_at_deadline(monkeypatch):
    monkeypatch.setattr(async_test_utils, "_TEMP_DB_SESSION_WAIT_SECONDS", 0.3)
    monkeypatch.setattr(async_test_utils, "_TEMP_DB_SESSION_POLL_SECONDS", 0.02)

    def script(text, params, cursor):
        if text.startswith("SELECT current_user"):
            return ("h2btester",)
        if "pg_stat_activity" in text and "pid, usename" in text:
            cursor.polls += 1
            if cursor.polls > 500:
                raise RuntimeError("scripted poll budget exhausted")
            return []
        if "DROP DATABASE" in text:
            raise psycopg2.errors.ObjectInUse(
                "database is being accessed by other users"
            )
        raise AssertionError(f"unexpected statement: {text}")

    with pytest.raises(
        TemporaryDatabaseTeardownError, match="deadline exceeded"
    ):
        async_test_utils._teardown_temporary_database(
            _ScriptedAdmin(script), "test_dc11t2fake"
        )


def test_teardown_non_object_in_use_drop_error_propagates_immediately():
    def script(text, params, cursor):
        if text.startswith("SELECT current_user"):
            return ("h2btester",)
        if "pg_stat_activity" in text and "pid, usename" in text:
            return []
        if "DROP DATABASE" in text:
            raise psycopg2.errors.InvalidCatalogName("database does not exist")
        raise AssertionError(f"unexpected statement: {text}")

    with pytest.raises(psycopg2.errors.InvalidCatalogName):
        async_test_utils._teardown_temporary_database(
            _ScriptedAdmin(script), "test_dc11t2fake"
        )


# ---------------------------------------------------------------------------
# R1 ephemeral-role contract tests (scripted): persistent role-drop failure
# must fail closed (never silently end), and the fresh-connection zero-residue
# proof must catch a role that survives its own successful drop statement.
# ---------------------------------------------------------------------------


def test_role_drop_persistent_failure_raises_not_silent(monkeypatch):
    monkeypatch.setattr(
        f"{__name__}._EPHEMERAL_ROLE_WAIT_SECONDS", 0.3, raising=False
    )
    monkeypatch.setattr(
        f"{__name__}._EPHEMERAL_ROLE_POLL_SECONDS", 0.02, raising=False
    )
    attempts = {"n": 0}

    def factory():
        def script(text, params, cursor):
            if "ALTER ROLE" in text and "NOLOGIN" in text:
                return None
            if "DROP ROLE" in text:
                attempts["n"] += 1
                if attempts["n"] > 100:
                    raise RuntimeError("scripted role-drop budget exhausted")
                raise psycopg2.errors.DependentObjectsStillExist(
                    "role cannot be dropped because some objects depend on it"
                )
            raise AssertionError(f"unexpected statement: {text}")

        return _ScriptedAdmin(script)

    with pytest.raises(AssertionError, match="deadline exceeded"):
        _drop_ephemeral_role(factory, "dc11t2fr_fake")
    assert attempts["n"] > 1


def test_role_drop_zero_residue_proof_fails_closed():
    def factory():
        def script(text, params, cursor):
            if "ALTER ROLE" in text and "NOLOGIN" in text:
                return None
            if "DROP ROLE" in text:
                return None
            if "FROM pg_roles" in text:
                return (1,)
            raise AssertionError(f"unexpected statement: {text}")

        return _ScriptedAdmin(script)

    with pytest.raises(AssertionError, match="still present in pg_roles"):
        _drop_ephemeral_role(factory, "dc11t2fr_fake")
