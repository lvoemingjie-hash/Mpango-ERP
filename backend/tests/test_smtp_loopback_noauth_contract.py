"""Kimi V1 public provisioning SMTP transport contract tests.

Authorization: CTO-AUTH-SKU-PUBLIC-PROVISIONING-SMTP-KIMI-V1-2026-09-15
(frozen base candidate 1ee75d9faaa00cdcadfe9f46d1e0ac960efc632e).

These tests exercise the REAL application modules end to end:

- ``core.config.Settings`` (SMTP_AUTH_MODE guard, loopback-only no-auth policy);
- ``services.email_delivery`` over a REAL socket against a task-owned,
  loopback-bound SMTP capture sink -- never a copied SMTP implementation;
- the public signup / verify-email / setup-credential HTTP API through
  ``api.app``.

Covered required paths:

1. complete valid non-test SMTP configuration sends exactly one verification
   message to a loopback capture sink;
2. the message carries a usable opaque continuation link and the public signup
   response exposes no raw registration ID;
3. incomplete configuration, unsupported TLS/auth combination and failed SMTP
   connection remain fail-closed with the established 503 category;
4. no-auth mode is rejected for a non-loopback host, is never inferred, and is
   not the default (login stays the default and still authenticates);
5. public email verification continues into the existing owner/setup lifecycle
   without direct SQL identity or RBAC seeding.
"""

from __future__ import annotations

import base64
import email as email_lib
import os
import re
import socket
import threading
import uuid
from types import SimpleNamespace
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import text

from api.app import app
from api.dependencies import get_db_session
from core.config import Settings
from database.session import AsyncSessionLocal, async_engine
from models.tenant_onboarding import (
    EmailVerificationToken,
    OnboardingStatusToken,
    OwnerCredentialSetupToken,
    TenantRegistration,
)
from models.wholesaler import Wholesaler
from services import email_delivery, onboarding_service
from services.email_delivery import clear_dev_email_deliveries, get_dev_email_deliveries


pytestmark = pytest.mark.asyncio

SIGNUP_URL = "/api/v1/auth/signup"
VERIFY_EMAIL_URL = "/api/v1/auth/verify-email"
SETUP_CREDENTIAL_URL = "/api/v1/auth/onboarding/setup-credential"

EMAIL_PREFIX = "kimi_smtp_"
VALID_PASSWORD = "ValidSignupCred123!"  # pragma: allowlist secret
OWNER_PASSWORD = "KimiSmtpOwnerCred_01!"  # pragma: allowlist secret
SMTP_PASSWORD_VALUE = "smtp-provider-app-password"  # pragma: allowlist secret
TEST_SECRET_KEY = "Z9vLk8mN4pQ7rS2tU5wX8yB3cD6fG0hJ"  # pragma: allowlist secret
LOOPBACK_NOAUTH_PUBLIC_ORIGIN = "https://kimi-smtp-links.invalid"


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
        mail_from: str | None = None
        rcpt_to: str | None = None
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
                elif upper.startswith("MAIL FROM:"):
                    mail_from = command[10:].strip()
                    reader.write(b"250 OK\r\n")
                elif upper.startswith("RCPT TO:"):
                    rcpt_to = command[8:].strip()
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
                elif upper == "RSET":
                    mail_from = rcpt_to = None
                    reader.write(b"250 OK\r\n")
                elif upper == "NOOP":
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


def _closed_loopback_port() -> int:
    """Return a loopback port with no listener (connection refused)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


# ---------------------------------------------------------------------------
# Settings + DB fixtures
# ---------------------------------------------------------------------------


def _active_test_database_url() -> str:
    return (
        os.environ.get("TEST_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
        or onboarding_service.get_settings().DATABASE_URL
    )


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
        "SECRET_KEY": TEST_SECRET_KEY,
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


@pytest.fixture(autouse=True)
async def _kimi_smtp_public_schema():
    await _ensure_onboarding_tables()
    await _clear_kimi_smtp_rows_and_schemas()
    clear_dev_email_deliveries()
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        await _clear_kimi_smtp_rows_and_schemas()
        clear_dev_email_deliveries()


@pytest.fixture(autouse=True)
def _allow_rate_limiter():
    from unittest.mock import AsyncMock, Mock, patch

    limiter = Mock()
    limiter.check_rate_limit = AsyncMock(return_value=(True, 1, 100))
    with patch("api.middleware.rate_limiting.get_rate_limiter", return_value=limiter):
        yield limiter


async def _ensure_onboarding_tables() -> None:
    async with async_engine.begin() as connection:
        await connection.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await connection.execute(
            text(
                "DO $$ BEGIN "
                "IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'reporting_role') "
                "THEN CREATE ROLE reporting_role NOLOGIN; END IF; "
                "END $$"
            )
        )
        await connection.run_sync(Wholesaler.__table__.create, checkfirst=True)
        await connection.run_sync(TenantRegistration.__table__.create, checkfirst=True)
        await connection.run_sync(EmailVerificationToken.__table__.create, checkfirst=True)
        await connection.run_sync(OnboardingStatusToken.__table__.create, checkfirst=True)
        await connection.run_sync(OwnerCredentialSetupToken.__table__.create, checkfirst=True)


async def _clear_kimi_smtp_rows_and_schemas() -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        rows = (
            await session.execute(
                text(
                    "SELECT wholesaler_id, tenant_schema FROM public.tenant_registrations "
                    "WHERE owner_email LIKE :prefix"
                ),
                {"prefix": f"{EMAIL_PREFIX}%@example.com"},
            )
        ).mappings().all()
        wholesaler_ids = [row["wholesaler_id"] for row in rows if row["wholesaler_id"] is not None]
        for schema in {row["tenant_schema"] for row in rows if row["tenant_schema"] is not None}:
            if schema.startswith("t_") and schema.replace("_", "").isalnum():
                await session.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await session.execute(
            text(
                "DELETE FROM public.owner_credential_setup_tokens WHERE registration_id IN ("
                "SELECT id FROM public.tenant_registrations WHERE owner_email LIKE :prefix)"
            ),
            {"prefix": f"{EMAIL_PREFIX}%@example.com"},
        )
        await session.execute(
            text(
                "DELETE FROM public.onboarding_status_tokens WHERE registration_id IN ("
                "SELECT id FROM public.tenant_registrations WHERE owner_email LIKE :prefix)"
            ),
            {"prefix": f"{EMAIL_PREFIX}%@example.com"},
        )
        await session.execute(
            text(
                "DELETE FROM public.email_verification_tokens WHERE registration_id IN ("
                "SELECT id FROM public.tenant_registrations WHERE owner_email LIKE :prefix)"
            ),
            {"prefix": f"{EMAIL_PREFIX}%@example.com"},
        )
        await session.execute(
            text("DELETE FROM public.tenant_registrations WHERE owner_email LIKE :prefix"),
            {"prefix": f"{EMAIL_PREFIX}%@example.com"},
        )
        if wholesaler_ids:
            await session.execute(
                text("DELETE FROM public.wholesalers WHERE id = ANY(:wholesaler_ids)"),
                {"wholesaler_ids": wholesaler_ids},
            )
        await session.commit()


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
    email = f"{EMAIL_PREFIX}{uuid.uuid4().hex}@example.com"
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
    assert get_dev_email_deliveries(email) == []
    _assert_signup_response_is_neutral_about_identity(response, registration_id=rows[0]["id"])


async def test_verification_message_carries_usable_opaque_link_with_new_registration(monkeypatch):
    email = f"{EMAIL_PREFIX}{uuid.uuid4().hex}@example.com"
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


async def test_incomplete_or_unsupported_transport_remains_fail_closed_503(monkeypatch):
    email = f"{EMAIL_PREFIX}{uuid.uuid4().hex}@example.com"

    with LoopbackCaptureSink(auth_mode="none") as sink:
        cases = {
            "missing_host": (lambda: _loose_settings(SMTP_HOST=None), sink),
            "missing_login_credentials": (
                lambda: _loose_settings(SMTP_AUTH_MODE="login", SMTP_USER=None),
                sink,
            ),
            "unsupported_tls_starttls_against_plaintext_sink": (
                lambda: _loose_settings(SMTP_STARTTLS=True),
                sink,
            ),
            "unsupported_auth_login_against_unauthenticated_sink": (
                lambda: _loose_settings(SMTP_AUTH_MODE="login"),
                sink,
            ),
            "unknown_auth_mode_value": (
                lambda: _loose_settings(SMTP_AUTH_MODE="bogus"),
                sink,
            ),
            "connection_refused": (
                lambda: _loose_settings(SMTP_HOST="127.0.0.1", SMTP_PORT=_closed_loopback_port()),
                None,
            ),
        }
        for label, (factory, active_sink) in cases.items():
            settings = factory()
            case_email = f"{EMAIL_PREFIX}{uuid.uuid4().hex}@example.com"
            response = await _signup_with_settings(monkeypatch, settings, case_email)
            _assert_503_fail_closed(response)
            assert await _registration_row(case_email) == [], label
            assert get_dev_email_deliveries(case_email) == [], label
        assert sink.messages == []
    assert list(sink.messages) == []


async def test_unsupported_auth_mode_raises_without_touching_the_socket(monkeypatch):
    """Delivery-layer guard: unknown auth mode fails before any connection."""
    settings = _loose_settings(SMTP_AUTH_MODE="bogus")
    assert email_delivery._smtp_config_complete(settings) is False
    with pytest.raises(email_delivery.EmailDeliveryNotConfiguredError):
        email_delivery._send_smtp_email(
            settings=settings,
            to_email="owner@example.invalid",
            subject="subject",
            body="body",
        )


class _TransportTripwire:
    """Tripwire: records construction attempts of the real SMTP client.

    Used only as a negative-path detector -- it performs no SMTP protocol
    work. Any recorded attempt proves the guard under test let the code
    reach the network layer it must never reach.
    """

    constructed: list[tuple] = []

    def __init__(self, host, port, *args, **kwargs):  # noqa: D107
        type(self).constructed.append((host, port, args, kwargs))
        raise AssertionError("SMTP transport must not be reached")


async def test_delivery_layer_guard_blocks_offloopback_noauth_before_transport(monkeypatch):
    """Defense in depth: no-auth off-loopback fails closed before any socket opens."""
    settings = _loose_settings(SMTP_HOST="mail.internal.invalid", SMTP_AUTH_MODE="none")
    _TransportTripwire.constructed = []
    monkeypatch.setattr(email_delivery.smtplib, "SMTP", _TransportTripwire)

    with pytest.raises(email_delivery.EmailDeliveryNotConfiguredError):
        email_delivery._send_smtp_email(
            settings=settings,
            to_email="owner@example.invalid",
            subject="subject",
            body="body",
        )
    assert _TransportTripwire.constructed == []


# ---------------------------------------------------------------------------
# 4: no-auth policy guard (rejected off-loopback, never inferred, not default)
# ---------------------------------------------------------------------------


async def test_noauth_mode_is_rejected_for_non_loopback_host():
    for host in ("smtp.example.invalid", "127.0.0.1.evil.invalid", "10.0.0.5", "0.0.0.0", "::ffff:8.8.8.8"):
        with pytest.raises(ValidationError):
            _production_settings(SMTP_AUTH_MODE="none", SMTP_HOST=host)


async def test_noauth_mode_is_accepted_only_for_literal_loopback_hosts():
    for host in ("127.0.0.1", "127.9.9.9", "localhost", "::1", "[::1]", "LOCALHOST"):
        settings = _production_settings(SMTP_AUTH_MODE="none", SMTP_HOST=host)
        assert settings.SMTP_AUTH_MODE == "none"


async def test_login_remains_the_default_auth_mode():
    settings = _production_settings()
    assert settings.SMTP_AUTH_MODE == "login"
    assert getattr(Settings.model_fields["SMTP_AUTH_MODE"], "default", None) == "login"


async def test_default_login_mode_still_authenticates_against_a_real_sink(monkeypatch):
    email = f"{EMAIL_PREFIX}{uuid.uuid4().hex}@example.com"
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
        # A staging label alone never resolves to unauthenticated delivery.
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
        email = f"{EMAIL_PREFIX}{uuid.uuid4().hex}@example.com"
        response = await _signup_with_settings(monkeypatch, refused, email)
        _assert_503_fail_closed(response)
        assert await _registration_row(email) == []
        assert email_delivery._smtp_auth_mode(refused) == "login"
        assert sink.auth_attempts == []

        # Explicitly demanded no-auth still refuses to leave loopback: both the
        # config gate and the delivery layer reject it, and nothing is captured.
        off_loopback = _loose_settings(SMTP_HOST="mail.internal.invalid", SMTP_AUTH_MODE="none")
        assert email_delivery.is_verification_email_delivery_configured(settings=off_loopback) is False
        with pytest.raises(email_delivery.EmailDeliveryNotConfiguredError):
            email_delivery.record_verification_email(
                settings=off_loopback,
                registration_id=uuid.uuid4(),
                to_email="owner@example.invalid",
                token="opaque-token",
                verification_link="https://links.invalid/verify-email#token=opaque-token",
            )
    assert sink.messages == []
    assert sink.auth_attempts == []


# ---------------------------------------------------------------------------
# 5: public lifecycle continuation without SQL identity/RBAC seeding
# ---------------------------------------------------------------------------


async def test_public_verification_continues_into_owner_setup_lifecycle_over_smtp(monkeypatch):
    email = f"{EMAIL_PREFIX}{uuid.uuid4().hex}@example.com"
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
