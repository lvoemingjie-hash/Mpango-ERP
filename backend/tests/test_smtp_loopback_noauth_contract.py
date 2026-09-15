"""Database-backed public provisioning SMTP contract tests.

Authorization: CTO-AUTH-SKU-PUBLIC-PROVISIONING-SMTP-KIMI-V1-2026-09-15,
successor rounds R1 and R2 (CTO-AUTH-SKU-PUBLIC-PROVISIONING-SMTP-KIMI-R1).

Companion module ``test_smtp_auth_mode_guard_config.py`` holds the pure
config/guard tests and requires no database. THIS module is the only one that
touches a database, and it enforces, before its first write:

- the task database URL must be supplied explicitly through
  ``KIMI_SMTP_TASK_DATABASE_URL`` (loopback host, ``kimi_smtp_`` database
  name) -- no fallback to ``DATABASE_URL``, defaults, or any other name;
- the task cluster must be declared explicitly through
  ``KIMI_SMTP_TASK_CLUSTER_ID`` and must equal the live server's immutable
  ``pg_control_system().system_identifier`` -- a matching database *name*
  never authorizes a cluster;
- the ACTUAL ``AsyncSessionLocal``/engine identity is proven with
  ``SELECT current_database()``, the live server address/port and a URL
  comparison against the task URL before any row write.

R2: this suite performs **zero DDL**. It never creates or alters roles,
extensions, databases, tables or schemas; the task database is prepared by
the environment owner (migrated to head ``038_catalog_identity_vertical_slice``,
which is what creates ``reporting_role``). A read-only preparation check
refuses to run against an unprepared database instead of creating objects.

Cleanup is targeted: only rows belonging to the exact emails created by this
module's tests are removed (exact-match ``= ANY(:emails)``, never a prefix
``LIKE``), and only tenant schemas recorded on those registrations are
dropped. The names of created registration ids, wholesaler ids and schemas are
re-derived from the database at cleanup time and verified to be gone.

Covered required paths (V1 items 1-5):

1. complete valid non-test SMTP configuration sends exactly one verification
   message to a loopback capture sink;
2. the message carries a usable opaque continuation link and the public signup
   response exposes no raw registration ID;
3. incomplete configuration, unsupported TLS/auth combination and failed SMTP
   connection remain fail-closed with the established 503 category, with
   zero-connection assertions for every pre-transport guard rejection;
4. no-auth mode is rejected for a non-loopback host at both layers and is
   never inferred from a label, empty credentials, or a connection failure;
5. public email verification continues into the owner/setup lifecycle without
   direct SQL identity or RBAC seeding.
"""

from __future__ import annotations

import base64
import email as email_lib
import os
import socket
import threading
import uuid
from types import SimpleNamespace
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from api.app import app
from api.dependencies import get_db_session
from core.config import Settings
from database.session import AsyncSessionLocal, async_engine
from services import email_delivery, onboarding_service
from services.email_delivery import clear_dev_email_deliveries, get_dev_email_deliveries


pytestmark = pytest.mark.asyncio

SIGNUP_URL = "/api/v1/auth/signup"
VERIFY_EMAIL_URL = "/api/v1/auth/verify-email"
SETUP_CREDENTIAL_URL = "/api/v1/auth/onboarding/setup-credential"

TASK_DATABASE_ENV = "KIMI_SMTP_TASK_DATABASE_URL"
TASK_CLUSTER_ENV = "KIMI_SMTP_TASK_CLUSTER_ID"
TASK_DATABASE_PREFIX = "kimi_smtp_"
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
EXPECTED_MIGRATION_HEAD = "038_catalog_identity_vertical_slice"
REQUIRED_TABLES = (
    "tenant_registrations",
    "email_verification_tokens",
    "onboarding_status_tokens",
    "owner_credential_setup_tokens",
    "wholesalers",
)
REQUIRED_ROLE = "reporting_role"  # created by migration 011_s6_p_reporting_role

EMAIL_PREFIX = "kimi_smtp_"
VALID_PASSWORD = "ValidSignupCred123!"  # pragma: allowlist secret
OWNER_PASSWORD = "KimiSmtpOwnerCred_01!"  # pragma: allowlist secret
SMTP_PASSWORD_VALUE = "smtp-provider-app-password"  # pragma: allowlist secret
TEST_SECRET_KEY = "Z9vLk8mN4pQ7rS2tU5wX8yB3cD6fG0hJ"  # pragma: allowlist secret
LOOPBACK_NOAUTH_PUBLIC_ORIGIN = "https://kimi-smtp-links.invalid"


# ---------------------------------------------------------------------------
# Cluster + task-database identity guard (must run before ANY write)
#
# A matching database *name* does not authorize a cluster: this suite performs
# ZERO cluster-level or database-level DDL (no CREATE/ALTER/DROP ROLE, no
# CREATE/DROP EXTENSION, no CREATE/DROP DATABASE, no CREATE TABLE). It only
# reads the cluster identity and refuses to touch anything unless the live
# server's immutable cluster identifier (pg_control_system().system_identifier)
# matches the task-declared value, on top of loopback host, exact database
# name, and engine/session identity agreement.
# ---------------------------------------------------------------------------


def _normalized(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


def _task_cluster_id() -> str:
    """Declared cluster identity (pg_control_system().system_identifier)."""
    raw = (os.environ.get(TASK_CLUSTER_ENV) or "").strip()
    if not raw:
        raise RuntimeError(
            f"{TASK_CLUSTER_ENV} must be set explicitly to the task-owned "
            "cluster's system_identifier; this suite refuses to infer cluster "
            "ownership from a database name and will not run without it."
        )
    return raw


def _task_database_url() -> str:
    """Resolve the task-owned database URL. Fallbacks are prohibited."""
    raw = (os.environ.get(TASK_DATABASE_ENV) or "").strip()
    if not raw:
        raise RuntimeError(
            f"{TASK_DATABASE_ENV} must be set explicitly to the task-owned "
            "database URL; this suite refuses to fall back to DATABASE_URL, "
            "test defaults, or any other database."
        )
    parsed = urlparse(_normalized(raw))
    if parsed.hostname not in LOOPBACK_HOSTS:
        raise RuntimeError(
            f"{TASK_DATABASE_ENV} must be a loopback URL, got host "
            f"{parsed.hostname!r}; refusing to run against a non-loopback database."
        )
    database = (parsed.path or "").lstrip("/")
    if not database.startswith(TASK_DATABASE_PREFIX):
        raise RuntimeError(
            f"{TASK_DATABASE_ENV} must name the task-owned database "
            f"(prefix {TASK_DATABASE_PREFIX!r}), got {database!r}."
        )
    return raw


async def _assert_engine_is_task_database() -> dict[str, Any]:
    """Prove the live engine/session identity is the task database."""
    task_url = urlparse(_normalized(_task_database_url()))
    engine_url = async_engine.url
    engine_database = engine_url.database or ""
    engine_host = engine_url.host or ""

    assert engine_host in LOOPBACK_HOSTS, f"engine host {engine_host!r} is not loopback"
    assert engine_database == (task_url.path or "").lstrip("/"), (
        f"engine database {engine_database!r} != task database "
        f"{(task_url.path or '').lstrip('/')!r}"
    )
    assert engine_url.port == (task_url.port or 5432)

    declared_cluster = _task_cluster_id()
    async with async_engine.connect() as connection:
        connected_database = await connection.scalar(text("SELECT current_database()"))
        connected_user = await connection.scalar(text("SELECT current_user"))
        server_addr = await connection.scalar(
            text("SELECT coalesce(inet_server_addr()::text, 'unix-socket')")
        )
        server_port = await connection.scalar(text("SELECT inet_server_port()"))
        server_version = await connection.scalar(text("SELECT version()"))
        cluster_identifier = await connection.scalar(
            text("SELECT system_identifier::text FROM pg_control_system()")
        )

    async with AsyncSessionLocal() as session:
        session_database = await session.scalar(text("SELECT current_database()"))

    assert connected_database == engine_database, (
        f"server reports {connected_database!r}, engine claims {engine_database!r}"
    )
    assert session_database == engine_database
    # Cluster ownership: a matching database NAME never authorizes a cluster.
    assert cluster_identifier == declared_cluster, (
        f"cluster mismatch: live system_identifier {cluster_identifier!r} != "
        f"declared {TASK_CLUSTER_ENV} {declared_cluster!r}; refusing before any write"
    )
    assert server_port == engine_url.port, (
        f"live server port {server_port!r} != engine port {engine_url.port!r}"
    )
    return {
        "database": connected_database,
        "engine_database": engine_database,
        "engine_host": engine_host,
        "engine_port": engine_url.port,
        "user": connected_user,
        "cluster_identifier": cluster_identifier,
        "declared_cluster_identifier": declared_cluster,
        "server_addr": server_addr,
        "server_port": server_port,
        "server_version": (server_version or "").split(",")[0],
    }


async def _assert_task_database_prepared() -> dict[str, Any]:
    """Read-only preparation check: the suite performs ZERO DDL itself.

    The task database must already be migrated to the expected head, with the
    tables and the ``reporting_role`` that migration 011 creates. If anything
    is missing the suite refuses to run instead of creating cluster-level or
    database-level objects.
    """
    async with async_engine.connect() as connection:
        has_version_table = bool(
            await connection.scalar(
                text("SELECT to_regclass('public.alembic_version') IS NOT NULL")
            )
        )
        head = (
            await connection.scalar(text("SELECT version_num FROM public.alembic_version"))
            if has_version_table
            else None
        )
        missing_tables = [
            table
            for table in REQUIRED_TABLES
            if not await connection.scalar(
                text("SELECT to_regclass(:qualified) IS NOT NULL"),
                {"qualified": f"public.{table}"},
            )
        ]
        role_exists = bool(
            await connection.scalar(
                text("SELECT 1 FROM pg_roles WHERE rolname = :role"), {"role": REQUIRED_ROLE}
            )
        )
    if not has_version_table:
        raise RuntimeError(
            "task database has no public.alembic_version; it is not prepared. "
            "This suite performs no DDL - migrate the database to "
            f"{EXPECTED_MIGRATION_HEAD!r} first."
        )
    if head != EXPECTED_MIGRATION_HEAD:
        raise RuntimeError(
            f"task database is not migrated to {EXPECTED_MIGRATION_HEAD!r} (found "
            f"{head!r}); this suite performs no DDL - prepare the database first."
        )
    if missing_tables:
        raise RuntimeError(
            f"task database is missing tables {missing_tables!r}; this suite "
            "performs no DDL - prepare the database first."
        )
    if not role_exists:
        raise RuntimeError(
            f"task database is missing role {REQUIRED_ROLE!r} (created by "
            "migration 011_s6_p_reporting_role); this suite performs no DDL - "
            "prepare the database first."
        )
    return {
        "migration_head": head,
        "checked_tables": list(REQUIRED_TABLES),
        "checked_role": REQUIRED_ROLE,
    }


@pytest.fixture(scope="module", autouse=True)
async def task_database_identity_guard():
    """Fail closed unless the live cluster + engine/session are the task's own."""
    identity = await _assert_engine_is_task_database()
    identity["preparation"] = await _assert_task_database_prepared()
    yield identity


# ---------------------------------------------------------------------------
# Task-owned loopback SMTP capture sink (real socket, real SMTP conversation)
# ---------------------------------------------------------------------------


class LoopbackCaptureSink:
    """Real SMTP server bound to 127.0.0.1 for capture and negative paths.

    ``auth_mode="none"`` advertises neither AUTH nor STARTTLS (unauthenticated
    plaintext task-owned sink). ``auth_mode="login"`` advertises AUTH LOGIN and
    completes the exchange so the authenticated default path can be proven
    against a real server. STARTTLS is never advertised: the task-owned sink is
    plaintext, which is why the runbook disables SMTP_STARTTLS explicitly.
    """

    def __init__(self, *, auth_mode: str = "none") -> None:
        assert auth_mode in {"none", "login"}
        self.auth_mode = auth_mode
        self.messages: list[email_lib.message.EmailMessage] = []
        self.auth_attempts: list[tuple[str, str]] = []
        self.connections = 0
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(4)
        self.port = self._sock.getsockname()[1]
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._accept_loop, daemon=True)

    def __enter__(self) -> "LoopbackCaptureSink":
        self._thread.start()
        return self

    def __exit__(self, *_exc_info) -> bool:
        self.close()
        return False

    def close(self) -> None:
        self._stop.set()
        try:
            self._sock.close()
        except OSError:
            pass
        self._thread.join(timeout=5)

    def _accept_loop(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _ = self._sock.accept()
            except OSError:
                return
            self.connections += 1
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _ehlo_reply(self) -> bytes:
        lines = [b"250-task-sink"]
        if self.auth_mode == "login":
            lines.append(b"250-AUTH LOGIN")
        lines.append(b"250 8BITMIME")
        return b"\r\n".join(lines) + b"\r\n"

    def _handle(self, conn: socket.socket) -> None:
        reader = conn.makefile("rwb")
        reader.write(b"220 task-sink ESMTP\r\n")
        reader.flush()
        try:
            while True:
                line = reader.readline()
                if not line:
                    break
                command = line.decode("utf-8", "replace").strip()
                upper = command.upper()
                if upper.startswith(("EHLO", "HELO")):
                    reader.write(self._ehlo_reply())
                elif upper.startswith("AUTH LOGIN"):
                    self._handle_auth_login(reader, command)
                elif upper.startswith("MAIL FROM:") or upper.startswith("RCPT TO:"):
                    reader.write(b"250 OK\r\n")
                elif upper == "DATA":
                    reader.write(b"354 End data with <CR><LF>.<CR><LF>\r\n")
                    reader.flush()
                    raw = b""
                    while True:
                        data_line = reader.readline()
                        if data_line in (b".\r\n", b".\n", b""):
                            break
                        raw += data_line
                    self.messages.append(
                        email_lib.message_from_string(
                            raw.decode("utf-8", "replace"),
                            policy=email_lib.policy.default,
                        )
                    )
                    reader.write(b"250 OK queued\r\n")
                elif upper == "RSET" or upper == "NOOP":
                    reader.write(b"250 OK\r\n")
                elif upper == "QUIT":
                    reader.write(b"221 Bye\r\n")
                    reader.flush()
                    break
                else:
                    reader.write(b"502 Command not implemented\r\n")
                reader.flush()
        except OSError:
            pass
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def _handle_auth_login(self, reader, command: str) -> None:
        """AUTH LOGIN handshake, tolerating smtplib's initial-response form."""
        parts = command.split()
        try:
            if len(parts) == 3:
                decoded = base64.b64decode(parts[2]).decode()
                if "\x00" in decoded:
                    _empty, username, password = (decoded + "\x00\x00").split("\x00")[:3]
                else:
                    username = decoded
                    reader.write(b"334 UGFzc3dvcmQ6\r\n")
                    reader.flush()
                    password = base64.b64decode(reader.readline().strip()).decode()
            else:
                reader.write(b"334 VXNlcm5hbWU6\r\n")
                reader.flush()
                username = base64.b64decode(reader.readline().strip()).decode()
                reader.write(b"334 UGFzc3dvcmQ6\r\n")
                reader.flush()
                password = base64.b64decode(reader.readline().strip()).decode()
            self.auth_attempts.append((username, password))
            reader.write(b"235 2.7.0 Authentication successful\r\n")
        except Exception:
            reader.write(b"535 5.7.8 Authentication failed\r\n")


class SmtpSslTripwire:
    """Spy for the implicit-TLS client: construction is recorded, never used."""

    constructed: list[tuple] = []

    def __init__(self, *args, **kwargs):  # noqa: D107
        type(self).constructed.append((args, kwargs))
        raise AssertionError("SMTP_SSL transport must not be constructed")

    @classmethod
    def reset(cls) -> None:
        cls.constructed = []


def _closed_loopback_port() -> int:
    """Return a loopback port with no listener (connection refused)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


# ---------------------------------------------------------------------------
# Settings, targeted cleanup, and HTTP client
# ---------------------------------------------------------------------------


def _active_test_database_url() -> str:
    """Task database URL for service settings; explicit, no fallback."""
    return _task_database_url()


_CREATED_EMAILS: list[str] = []


def _record_email(email: str) -> str:
    """Record the exact address a test is about to create rows for."""
    normalized = email.strip().lower()
    if normalized not in _CREATED_EMAILS:
        _CREATED_EMAILS.append(normalized)
    return email


def test_cleanup_registry_starts_empty():
    """Sanity: the targeted cleanup registry is per-run, not module residue."""
    assert isinstance(_CREATED_EMAILS, list)


async def _cleanup_recorded_rows() -> dict[str, int]:
    """Delete exactly the rows recorded by this run (never a prefix LIKE)."""
    emails = list(_CREATED_EMAILS)
    summary = {"registrations": 0, "schemas_dropped": 0, "wholesalers": 0, "tokens": 0}
    if not emails:
        return summary
    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        rows = (
            await session.execute(
                text(
                    "SELECT id, wholesaler_id, tenant_schema FROM public.tenant_registrations "
                    "WHERE owner_email = ANY(:emails)"
                ),
                {"emails": emails},
            )
        ).mappings().all()
        registration_ids = [row["id"] for row in rows]
        wholesaler_ids = [row["wholesaler_id"] for row in rows if row["wholesaler_id"] is not None]
        schemas = [row["tenant_schema"] for row in rows if row["tenant_schema"] is not None]
        for schema in schemas:
            if schema.startswith("t_") and schema[2:].isalnum():
                await session.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
                summary["schemas_dropped"] += 1
        if registration_ids:
            for table in (
                "public.owner_credential_setup_tokens",
                "public.onboarding_status_tokens",
                "public.email_verification_tokens",
            ):
                result = await session.execute(
                    text(f"DELETE FROM {table} WHERE registration_id = ANY(:ids)"),
                    {"ids": registration_ids},
                )
                summary["tokens"] += result.rowcount or 0
            result = await session.execute(
                text("DELETE FROM public.tenant_registrations WHERE id = ANY(:ids)"),
                {"ids": registration_ids},
            )
            summary["registrations"] = result.rowcount or 0
        if wholesaler_ids:
            result = await session.execute(
                text("DELETE FROM public.wholesalers WHERE id = ANY(:ids)"),
                {"ids": wholesaler_ids},
            )
            summary["wholesalers"] = result.rowcount or 0
        await session.commit()

    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        remaining = await session.scalar(
            text(
                "SELECT count(*) FROM public.tenant_registrations "
                "WHERE owner_email = ANY(:emails)"
            ),
            {"emails": emails},
        )
    assert remaining == 0, f"targeted cleanup left {remaining} registration(s) for {emails}"
    return summary


@pytest.fixture(autouse=True)
async def _kimi_smtp_rows(task_database_identity_guard):
    """Per-test setup/teardown; runs only after the identity + prep guard passed.

    No DDL: the task database is prepared (migrated to head) by the environment
    owner, and this fixture only clears in-process sinks and the per-run
    cleanup registry.
    """
    clear_dev_email_deliveries()
    _CREATED_EMAILS.clear()
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        clear_dev_email_deliveries()
        await _cleanup_recorded_rows()
        _CREATED_EMAILS.clear()


@pytest.fixture(autouse=True)
def _allow_rate_limiter():
    from unittest.mock import AsyncMock, Mock, patch

    limiter = Mock()
    limiter.check_rate_limit = AsyncMock(return_value=(True, 1, 100))
    with patch("api.middleware.rate_limiting.get_rate_limiter", return_value=limiter):
        yield limiter


async def _client() -> AsyncClient:
    async def _override_public_db():
        async with AsyncSessionLocal() as session:
            await session.execute(text("SET search_path TO public"))
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db_session] = _override_public_db
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    return AsyncClient(transport=transport, base_url="http://testserver")


# ---------------------------------------------------------------------------
# Settings factories
# ---------------------------------------------------------------------------


def _production_settings(**overrides: Any) -> Settings:
    """Real Settings instance in production mode (no test-env fallback).

    SECRET_KEY comes from the active test environment so independently
    resolving consumers (e.g. the setup-credential endpoint, which calls
    core.config.get_settings directly) hash and verify opaque tokens with the
    same key material as the flows under test.
    """
    values: dict[str, Any] = {
        "MPANGO_ENV": "production",
        "SECRET_KEY": os.environ.get("SECRET_KEY") or TEST_SECRET_KEY,
        "DATABASE_URL": _active_test_database_url(),
        "REDIS_URL": "redis://127.0.0.1:6379/15",
        "PUBLIC_FRONTEND_URL": LOOPBACK_NOAUTH_PUBLIC_ORIGIN,
        "EMAIL_PROVIDER": "smtp",
        "EMAIL_DELIVERY_MODE": "smtp",
        "SMTP_HOST": "127.0.0.1",
        "SMTP_PORT": 2525,
        "SMTP_USER": "mailer@example.invalid",
        "SMTP_PASSWORD": SMTP_PASSWORD_VALUE,
        "EMAIL_FROM": "no-reply@example.invalid",
        "SMTP_USE_TLS": False,
        "SMTP_STARTTLS": False,
        "SMTP_AUTH_MODE": "login",
    }
    values.update(overrides)
    return Settings(**values)


def _loopback_noauth_settings(sink: LoopbackCaptureSink, **overrides: Any) -> Settings:
    """Complete valid non-test SMTP config for the unauthenticated sink.

    SMTP_USER / SMTP_PASSWORD are deliberately absent: the unauthenticated
    transport must not require credentials that it will never use.
    """
    values: dict[str, Any] = {
        "SMTP_PORT": sink.port,
        "SMTP_USER": None,
        "SMTP_PASSWORD": None,
        "SMTP_AUTH_MODE": "none",
    }
    values.update(overrides)
    return _production_settings(**values)


def _loose_settings(**overrides: Any) -> SimpleNamespace:
    """Loosely constructed settings object (bypasses Settings validation)."""
    values: dict[str, Any] = {
        "MPANGO_ENV": "production",
        "SECRET_KEY": os.environ.get("SECRET_KEY") or TEST_SECRET_KEY,
        "DATABASE_URL": _active_test_database_url(),
        "PUBLIC_FRONTEND_URL": LOOPBACK_NOAUTH_PUBLIC_ORIGIN,
        "EMAIL_PROVIDER": "smtp",
        "EMAIL_DELIVERY_MODE": "smtp",
        "SMTP_HOST": "127.0.0.1",
        "SMTP_PORT": 2525,
        "SMTP_USER": "mailer@example.invalid",
        "SMTP_PASSWORD": SMTP_PASSWORD_VALUE,
        "EMAIL_FROM": "no-reply@example.invalid",
        "SMTP_USE_TLS": False,
        "SMTP_STARTTLS": False,
        "SMTP_AUTH_MODE": "login",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _signup_payload(email: str) -> dict[str, str]:
    return {
        "companyName": f"Kimi SMTP Company {uuid.uuid4().hex[:8]}",
        "country": "KE",
        "email": email,
        "phone": "+254700000000",
        "businessType": "wholesale",
        "password": VALID_PASSWORD,
    }


def _new_email() -> str:
    return _record_email(f"{EMAIL_PREFIX}{uuid.uuid4().hex}@example.com")


async def _signup_with_settings(monkeypatch, settings, email: str):
    monkeypatch.setattr(onboarding_service, "get_settings", lambda: settings)
    async with await _client() as client:
        return await client.post(SIGNUP_URL, json=_signup_payload(email))


async def _verify_with_settings(monkeypatch, settings, raw_token: str):
    monkeypatch.setattr(onboarding_service, "get_settings", lambda: settings)
    async with await _client() as client:
        return await client.post(VERIFY_EMAIL_URL, json={"token": raw_token})


async def _registration_row(email: str):
    async with AsyncSessionLocal() as session:
        return (
            await session.execute(
                text(
                    "SELECT id, owner_email, status, email_verified_at, wholesaler_id, tenant_schema, "
                    "provisioning_completed_at, password_hash FROM public.tenant_registrations "
                    "WHERE owner_email = :email ORDER BY created_at"
                ),
                {"email": email},
            )
        ).mappings().all()


async def _setup_token_rows(registration_id: uuid.UUID):
    async with AsyncSessionLocal() as session:
        return (
            await session.execute(
                text(
                    "SELECT * FROM public.owner_credential_setup_tokens "
                    "WHERE registration_id = :registration_id ORDER BY created_at"
                ),
                {"registration_id": registration_id},
            )
        ).mappings().all()


async def _table_count(schema: str, table: str) -> int:
    async with AsyncSessionLocal() as session:
        return int(await session.scalar(text(f'SELECT count(*) FROM "{schema}"."{table}"')))


async def _admin_role_count(schema: str, owner_email: str) -> int:
    async with AsyncSessionLocal() as session:
        return int(
            await session.scalar(
                text(
                    f'SELECT count(*) FROM "{schema}".user_roles ur '
                    f'JOIN "{schema}".users u ON u.id = ur.user_id '
                    f'JOIN "{schema}".roles r ON r.id = ur.role_id '
                    "WHERE u.email = :email AND r.name = 'admin'"
                ),
                {"email": owner_email},
            )
        )


def _verification_link_from_message(message: email_lib.message.EmailMessage) -> str:
    body = message.get_content()
    link_lines = [line for line in body.splitlines() if "/verify-email#token=" in line]
    assert len(link_lines) == 1, body
    return link_lines[0].strip()


def _setup_link_from_message(message: email_lib.message.EmailMessage) -> str:
    body = message.get_content()
    link_lines = [line for line in body.splitlines() if "/setup-credential#setupToken=" in line]
    assert len(link_lines) == 1, body
    return link_lines[0].strip()


def _fragment_token(link: str, key: str) -> str:
    parsed = urlparse(link)
    fragment_params = parse_qs(parsed.fragment)
    assert key in fragment_params, f"{key} not in fragment of {parsed}"
    return fragment_params[key][0]


def _assert_signup_response_is_neutral_about_identity(response, *, registration_id, forbidden=()) -> None:
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["success"] is True
    assert body["data"]["registrationId"] is None
    assert body["data"]["status"] == "pending_email_verification"
    response_text = response.text
    assert VALID_PASSWORD not in response_text
    for term in ("token_hash", "password_hash", "tenant_schema", "setup_token", "setuptoken"):
        assert term not in response_text
    if registration_id is not None:
        assert str(registration_id) not in response_text
    for value in forbidden:
        assert str(value) not in response_text


def _assert_503_fail_closed(response) -> None:
    assert response.status_code == 503, response.text
    assert response.json()["detail"]["code"] == "EMAIL_DELIVERY_NOT_CONFIGURED"


# ---------------------------------------------------------------------------
# 1 + 2: complete config, exactly one message, opaque continuation link
# ---------------------------------------------------------------------------


async def test_complete_non_test_smtp_config_sends_exactly_one_verification_message(monkeypatch):
    email = _new_email()
    with LoopbackCaptureSink(auth_mode="none") as sink:
        settings = _loopback_noauth_settings(sink)
        assert settings.MPANGO_ENV == "production"
        assert settings.SMTP_AUTH_MODE == "none"
        assert settings.SMTP_USER is None and settings.SMTP_PASSWORD is None
        assert email_delivery.is_verification_email_delivery_configured(settings=settings) is True

        response = await _signup_with_settings(monkeypatch, settings, email)

    rows = await _registration_row(email)
    assert len(rows) == 1
    assert len(sink.messages) == 1
    message = sink.messages[0]
    assert str(message["To"]).strip() == email
    assert str(message["From"]).strip() == "no-reply@example.invalid"
    assert "Verify your Mpango ERP email" == str(message["Subject"])
    assert sink.auth_attempts == []
    assert sink.connections == 1
    assert get_dev_email_deliveries(email) == []
    _assert_signup_response_is_neutral_about_identity(response, registration_id=rows[0]["id"])


async def test_verification_message_carries_usable_opaque_link_with_new_registration(monkeypatch):
    email = _new_email()
    with LoopbackCaptureSink(auth_mode="none") as sink:
        settings = _loopback_noauth_settings(sink)
        response = await _signup_with_settings(monkeypatch, settings, email)

        rows = await _registration_row(email)
        registration_id = rows[0]["id"]
        assert len(sink.messages) == 1

        link = _verification_link_from_message(sink.messages[0])
        assert link.startswith(f"{LOOPBACK_NOAUTH_PUBLIC_ORIGIN}/verify-email#token=")
        token = _fragment_token(link, "token")

        # Opaque material only: not the registration UUID, high-entropy, and the
        # public response never carried it or a hash of it.
        assert token != str(registration_id)
        assert len(token) >= 32
        assert token not in response.text
        assert registration_id and str(registration_id) not in response.text
        assert "registrationId" in response.text  # field present, value neutral (None)

        # Usable continuation: the emailed token drives the public verify API.
        verify_response = await _verify_with_settings(monkeypatch, settings, token)
        assert verify_response.status_code == 200, verify_response.text


# ---------------------------------------------------------------------------
# 3: fail-closed matrix (503 category preserved)
# ---------------------------------------------------------------------------


async def test_pre_transport_guard_rejections_remain_503_with_zero_connections(monkeypatch):
    """Guard rejections fail closed BEFORE any SMTP/SMTP_SSL construction."""
    email = _new_email()
    with LoopbackCaptureSink(auth_mode="none") as sink:
        sink_connections_before = sink.connections
        cases = {
            "missing_host": {"SMTP_HOST": None},
            "missing_login_credentials": {"SMTP_AUTH_MODE": "login", "SMTP_USER": None},
            "unknown_auth_mode_value": {"SMTP_AUTH_MODE": "bogus"},
            "none_off_loopback": {"SMTP_HOST": "mail.internal.invalid", "SMTP_AUTH_MODE": "none"},
        }
        for label, overrides in cases.items():
            settings = _loose_settings(**overrides)
            SmtpSslTripwire.reset()
            monkeypatch.setattr(email_delivery.smtplib, "SMTP_SSL", SmtpSslTripwire)
            case_email = _new_email()
            response = await _signup_with_settings(monkeypatch, settings, case_email)
            _assert_503_fail_closed(response)
            assert await _registration_row(case_email) == [], label
            assert get_dev_email_deliveries(case_email) == [], label
        assert sink.messages == []
        assert sink.connections == sink_connections_before
    assert SmtpSslTripwire.constructed == []


async def test_transport_failures_remain_503_and_never_silently_fall_back(monkeypatch):
    """Unsupported TLS/auth combinations and a refused connection stay 503."""
    with LoopbackCaptureSink(auth_mode="none") as sink:
        cases = {
            "unsupported_tls_starttls_against_plaintext_sink": {"SMTP_STARTTLS": True},
            "unsupported_auth_login_against_unauthenticated_sink": {"SMTP_AUTH_MODE": "login"},
        }
        for label, overrides in cases.items():
            settings = _loose_settings(SMTP_PORT=sink.port, **overrides)
            case_email = _new_email()
            response = await _signup_with_settings(monkeypatch, settings, case_email)
            _assert_503_fail_closed(response)
            assert await _registration_row(case_email) == [], label
            assert get_dev_email_deliveries(case_email) == [], label
        # Both cases reached the transport (real TCP connections) and failed
        # there; nothing was captured and nothing fell back to the dev sink.
        assert sink.connections >= len(cases)
        assert sink.messages == []

    refused_settings = _loose_settings(SMTP_HOST="127.0.0.1", SMTP_PORT=_closed_loopback_port())
    refused_email = _new_email()
    refused_response = await _signup_with_settings(monkeypatch, refused_settings, refused_email)
    _assert_503_fail_closed(refused_response)
    assert await _registration_row(refused_email) == []
    assert get_dev_email_deliveries(refused_email) == []


# ---------------------------------------------------------------------------
# 4: no-auth policy guard (rejected off-loopback, never inferred, not default)
# ---------------------------------------------------------------------------


async def test_default_login_mode_still_authenticates_against_a_real_sink(monkeypatch):
    email = _new_email()
    with LoopbackCaptureSink(auth_mode="login") as sink:
        settings = _production_settings(SMTP_PORT=sink.port, SMTP_AUTH_MODE="login")
        response = await _signup_with_settings(monkeypatch, settings, email)

    rows = await _registration_row(email)
    assert len(rows) == 1
    assert len(sink.messages) == 1
    assert sink.auth_attempts == [("mailer@example.invalid", SMTP_PASSWORD_VALUE)]
    _assert_signup_response_is_neutral_about_identity(response, registration_id=rows[0]["id"])


async def test_noauth_mode_is_not_inferred_from_env_label_or_empty_credentials(monkeypatch):
    """A staging label, empty credentials, or a refused connection never enable no-auth."""
    with LoopbackCaptureSink(auth_mode="none") as sink:
        staging_without_auth_mode = _loose_settings(
            MPANGO_ENV="staging",
            SMTP_USER=None,
            SMTP_PASSWORD=None,
        )
        assert email_delivery._smtp_auth_mode(staging_without_auth_mode) == "login"
        # Empty credentials under login mode are incomplete, not a no-auth switch.
        assert email_delivery._smtp_config_complete(staging_without_auth_mode) is False

        # A refused connection never flips the mode at runtime either: login
        # stays demanded and the delivery fails closed with the 503 category.
        refused = _loose_settings(
            SMTP_HOST="127.0.0.1",
            SMTP_PORT=_closed_loopback_port(),
            SMTP_AUTH_MODE="login",
        )
        email = _new_email()
        response = await _signup_with_settings(monkeypatch, refused, email)
        _assert_503_fail_closed(response)
        assert await _registration_row(email) == []
        assert email_delivery._smtp_auth_mode(refused) == "login"
        assert sink.auth_attempts == []
        assert sink.messages == []


# ---------------------------------------------------------------------------
# 5: public lifecycle continuation without SQL identity/RBAC seeding
# ---------------------------------------------------------------------------


async def test_public_verification_continues_into_owner_setup_lifecycle_over_smtp(monkeypatch):
    email = _new_email()
    with LoopbackCaptureSink(auth_mode="none") as sink:
        settings = _loopback_noauth_settings(sink)
        signup_response = await _signup_with_settings(monkeypatch, settings, email)
        assert signup_response.status_code == 202, signup_response.text

        assert len(sink.messages) == 1
        verification_link = _verification_link_from_message(sink.messages[0])
        verification_token = _fragment_token(verification_link, "token")

        # Public API continuation only: no direct SQL identity or RBAC seeding.
        verify_response = await _verify_with_settings(monkeypatch, settings, verification_token)
        assert verify_response.status_code == 200, verify_response.text

        assert len(sink.messages) == 2
        setup_message = sink.messages[1]
        assert "Set up your Mpango ERP owner account" == str(setup_message["Subject"])
        setup_link = _setup_link_from_message(setup_message)
        setup_token = _fragment_token(setup_link, "setupToken")

    rows = await _registration_row(email)
    assert len(rows) == 1
    registration = rows[0]
    assert registration["status"] == "active"
    assert registration["email_verified_at"] is not None
    assert registration["wholesaler_id"] is not None
    assert registration["tenant_schema"] is not None
    assert registration["provisioning_completed_at"] is not None
    assert registration["password_hash"] is None

    setup_tokens = await _setup_token_rows(registration["id"])
    assert len(setup_tokens) == 1
    assert setup_tokens[0]["token_hash"] != setup_token
    assert setup_token not in setup_tokens[0]["token_hash"]
    assert "token" not in set(setup_tokens[0].keys())

    # Continue into the owner credential step through the public API; the
    # owner identity and RBAC rows are created by the application, not seeded.
    monkeypatch.setattr(onboarding_service, "get_settings", lambda: settings)
    async with await _client() as client:
        setup_response = await client.post(
            SETUP_CREDENTIAL_URL,
            json={"setup_token": setup_token, "password": OWNER_PASSWORD},
        )
    assert setup_response.status_code == 200, setup_response.text
    schema = registration["tenant_schema"]
    assert await _table_count(schema, "users") == 1
    assert await _admin_role_count(schema, email) == 1

    # Public responses never disclose tokens, schema, or internal identifiers.
    for response, values in (
        (signup_response, (verification_token, setup_token, str(registration["id"]))),
        (verify_response, (verification_token, setup_token, schema)),
        (setup_response, (setup_token, schema)),
    ):
        body = response.text
        for value in values:
            if value is not None:
                assert value not in body
        for term in ("password_hash", "token_hash"):
            assert term not in body
