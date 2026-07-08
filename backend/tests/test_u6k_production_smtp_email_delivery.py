"""U6-K production SMTP email delivery tests."""

from __future__ import annotations

import re
import uuid
from types import SimpleNamespace
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from api.app import app
from api.dependencies import get_db_session
from database.session import AsyncSessionLocal, async_engine
from models.tenant_onboarding import EmailVerificationToken, OnboardingStatusToken, TenantRegistration
from models.wholesaler import Wholesaler
from services import email_delivery, onboarding_service
from services.email_delivery import clear_dev_email_deliveries, get_dev_email_deliveries


pytestmark = pytest.mark.asyncio

VALID_PASSWORD = "ValidSignupCred123!"  # pragma: allowlist secret
SMTP_PASSWORD_VALUE = "smtp-provider-app-password"  # pragma: allowlist secret
TEST_SECRET_KEY = "Z9vLk8mN4pQ7rS2tU5wX8yB3cD6fG0hJ"  # pragma: allowlist secret


@pytest.fixture(autouse=True)
async def _u6k_public_schema():
    await _ensure_onboarding_tables()
    await _clear_u6k_rows()
    clear_dev_email_deliveries()
    FakeSMTP.reset()
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        await _clear_u6k_rows()
        clear_dev_email_deliveries()
        FakeSMTP.reset()


async def _ensure_onboarding_tables() -> None:
    async with async_engine.begin() as connection:
        await connection.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await connection.run_sync(Wholesaler.__table__.create, checkfirst=True)
        await connection.run_sync(TenantRegistration.__table__.create, checkfirst=True)
        await connection.run_sync(EmailVerificationToken.__table__.create, checkfirst=True)
        await connection.run_sync(OnboardingStatusToken.__table__.create, checkfirst=True)


async def _clear_u6k_rows() -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        await session.execute(
            text(
                "DELETE FROM public.onboarding_status_tokens "
                "WHERE registration_id IN ("
                "SELECT id FROM public.tenant_registrations "
                "WHERE owner_email LIKE 'u6k_%@example.com')"
            )
        )
        await session.execute(
            text(
                "DELETE FROM public.email_verification_tokens "
                "WHERE registration_id IN ("
                "SELECT id FROM public.tenant_registrations "
                "WHERE owner_email LIKE 'u6k_%@example.com')"
            )
        )
        await session.execute(
            text("DELETE FROM public.tenant_registrations WHERE owner_email LIKE 'u6k_%@example.com'")
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


class FakeSMTP:
    sent_messages: list[Any] = []
    login_calls: list[tuple[str, str]] = []
    starttls_calls = 0
    fail_send = False

    def __init__(self, host: str, port: int, timeout: int = 15, **_kwargs: Any) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout

    def __enter__(self):
        return self

    def __exit__(self, *_exc_info):
        return False

    def starttls(self, *, context) -> None:
        assert context is not None
        self.__class__.starttls_calls += 1

    def login(self, username: str, password: str) -> None:
        self.__class__.login_calls.append((username, password))

    def send_message(self, message) -> None:
        if self.__class__.fail_send:
            raise OSError("SMTP send failed")
        self.__class__.sent_messages.append(message)

    @classmethod
    def reset(cls) -> None:
        cls.sent_messages = []
        cls.login_calls = []
        cls.starttls_calls = 0
        cls.fail_send = False


def _signup_payload(email: str) -> dict[str, str]:
    return {
        "companyName": f"U6K Company {uuid.uuid4().hex[:8]}",
        "country": "KE",
        "email": email,
        "phone": "+254700000000",
        "businessType": "wholesale",
        "password": VALID_PASSWORD,
    }


def _production_settings(**overrides: Any):
    values = {
        "MPANGO_ENV": "production",
        "SECRET_KEY": TEST_SECRET_KEY,
        "EMAIL_PROVIDER": "smtp",
        "EMAIL_DELIVERY_MODE": "smtp",
        "SMTP_HOST": "smtp.example.invalid",
        "SMTP_PORT": 587,
        "SMTP_USER": "mailer@example.invalid",
        "SMTP_PASSWORD": SMTP_PASSWORD_VALUE,
        "EMAIL_FROM": "no-reply@example.invalid",
        "SMTP_STARTTLS": True,
        "SMTP_USE_TLS": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _test_settings():
    return SimpleNamespace(
        MPANGO_ENV="test",
        SECRET_KEY=TEST_SECRET_KEY,
        EMAIL_PROVIDER="dev_sink",
        EMAIL_DELIVERY_MODE="dev_sink",
    )


async def _registration_rows(email: str):
    async with AsyncSessionLocal() as session:
        return (
            await session.execute(
                text(
                    "SELECT id, owner_email, password_hash, status FROM public.tenant_registrations "
                    "WHERE owner_email = :email ORDER BY created_at"
                ),
                {"email": email},
            )
        ).mappings().all()


async def _token_rows_for_email(email: str):
    async with AsyncSessionLocal() as session:
        return (
            await session.execute(
                text(
                    "SELECT evt.* FROM public.email_verification_tokens evt "
                    "JOIN public.tenant_registrations tr ON tr.id = evt.registration_id "
                    "WHERE tr.owner_email = :email ORDER BY evt.created_at"
                ),
                {"email": email},
            )
        ).mappings().all()


async def _signup_with_settings(monkeypatch, settings, email: str):
    monkeypatch.setattr(onboarding_service, "get_settings", lambda: settings)
    async with await _client() as client:
        return await client.post("/api/v1/auth/signup", json=_signup_payload(email))


def _raw_token_from_smtp_message() -> str:
    assert len(FakeSMTP.sent_messages) == 1
    body = FakeSMTP.sent_messages[0].get_content()
    match = re.search(r"token=([^\s]+)", body)
    assert match is not None
    return match.group(1)


def _assert_neutral_signup_response(response, *, raw_token: str | None = None, token_hash: str | None = None) -> None:
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["success"] is True
    assert body["data"]["registrationId"] is None
    assert body["data"]["status"] == "pending_email_verification"
    response_text = response.text
    assert VALID_PASSWORD not in response_text
    assert "token_hash" not in response_text
    assert "password_hash" not in response_text
    if raw_token is not None:
        assert raw_token not in response_text
    if token_hash is not None:
        assert token_hash not in response_text


async def test_production_missing_smtp_config_returns_503_and_writes_no_rows(monkeypatch):
    email = f"u6k_{uuid.uuid4().hex}@example.com"
    settings = _production_settings(SMTP_HOST=None)

    response = await _signup_with_settings(monkeypatch, settings, email)

    assert response.status_code == 503, response.text
    assert response.json()["detail"]["code"] == "EMAIL_DELIVERY_NOT_CONFIGURED"
    assert await _registration_rows(email) == []
    assert await _token_rows_for_email(email) == []
    assert get_dev_email_deliveries(email) == []
    assert FakeSMTP.sent_messages == []


async def test_production_smtp_success_creates_hash_only_registration_and_token(monkeypatch):
    email = f"u6k_{uuid.uuid4().hex}@example.com"
    monkeypatch.setattr(email_delivery.smtplib, "SMTP", FakeSMTP)

    response = await _signup_with_settings(monkeypatch, _production_settings(), email)

    rows = await _registration_rows(email)
    assert len(rows) == 1
    registration = rows[0]
    assert registration["status"] == "pending_email_verification"
    assert registration["password_hash"] != VALID_PASSWORD
    tokens = await _token_rows_for_email(email)
    assert len(tokens) == 1
    raw_token = _raw_token_from_smtp_message()
    assert tokens[0]["token_hash"] != raw_token
    assert raw_token not in tokens[0]["token_hash"]
    assert "token" not in set(tokens[0].keys())
    assert "raw_token" not in set(tokens[0].keys())
    assert "token_plaintext" not in set(tokens[0].keys())
    assert FakeSMTP.login_calls == [("mailer@example.invalid", SMTP_PASSWORD_VALUE)]
    assert FakeSMTP.starttls_calls == 1
    assert get_dev_email_deliveries(email) == []
    _assert_neutral_signup_response(response, raw_token=raw_token, token_hash=tokens[0]["token_hash"])


async def test_production_smtp_send_failure_rolls_back_registration_and_token(monkeypatch):
    email = f"u6k_{uuid.uuid4().hex}@example.com"
    FakeSMTP.fail_send = True
    monkeypatch.setattr(email_delivery.smtplib, "SMTP", FakeSMTP)

    response = await _signup_with_settings(monkeypatch, _production_settings(), email)

    assert response.status_code == 503, response.text
    assert response.json()["detail"]["code"] == "EMAIL_DELIVERY_NOT_CONFIGURED"
    assert await _registration_rows(email) == []
    assert await _token_rows_for_email(email) == []
    assert get_dev_email_deliveries(email) == []


async def test_test_environment_still_uses_dev_sink_without_smtp(monkeypatch):
    email = f"u6k_{uuid.uuid4().hex}@example.com"
    monkeypatch.setattr(email_delivery.smtplib, "SMTP", FakeSMTP)

    response = await _signup_with_settings(monkeypatch, _test_settings(), email)

    deliveries = get_dev_email_deliveries(email)
    assert len(deliveries) == 1
    assert FakeSMTP.sent_messages == []
    assert await _token_rows_for_email(email) != []
    _assert_neutral_signup_response(response, raw_token=deliveries[0].token)


async def test_duplicate_live_email_in_production_is_neutral_and_sends_no_extra_smtp(monkeypatch):
    email = f"u6k_{uuid.uuid4().hex}@example.com"
    monkeypatch.setattr(email_delivery.smtplib, "SMTP", FakeSMTP)
    settings = _production_settings()

    first = await _signup_with_settings(monkeypatch, settings, email)
    first_raw_token = _raw_token_from_smtp_message()
    duplicate = await _signup_with_settings(monkeypatch, settings, email.upper())

    assert len(FakeSMTP.sent_messages) == 1
    assert len(await _registration_rows(email)) == 1
    assert len(await _token_rows_for_email(email)) == 1
    _assert_neutral_signup_response(first, raw_token=first_raw_token)
    _assert_neutral_signup_response(duplicate, raw_token=first_raw_token)
    assert duplicate.json()["data"] == first.json()["data"]
