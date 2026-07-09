"""U6-L email-verified onboarding orchestration tests."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse
from types import SimpleNamespace
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from api.app import app
from api.dependencies import get_db_session
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
from services.onboarding_service import complete_email_verified_onboarding, hash_token
from services.owner_credential_service import OWNER_ADMIN_PERMISSION_REGISTRY


pytestmark = pytest.mark.asyncio

SIGNUP_URL = "/api/v1/auth/signup"
VERIFY_EMAIL_URL = "/api/v1/auth/verify-email"
STATUS_URL = "/api/v1/auth/onboarding/status"
SETUP_CREDENTIAL_URL = "/api/v1/auth/onboarding/setup-credential"
VALID_PASSWORD = "ValidSignupCred123!"  # pragma: allowlist secret
OWNER_PASSWORD = "U6LOwnerSetupCred_01!"  # pragma: allowlist secret
SMTP_PASSWORD_VALUE = "smtp-provider-app-password"  # pragma: allowlist secret
TEST_SECRET_KEY = "Z9vLk8mN4pQ7rS2tU5wX8yB3cD6fG0hJ"  # pragma: allowlist secret
CANONICAL_ADMIN_PERMISSION_CODES = {code for code, _description in OWNER_ADMIN_PERMISSION_REGISTRY}


@pytest.fixture(autouse=True)
async def _u6l_public_schema():
    await _ensure_onboarding_tables()
    await _clear_u6l_rows_and_schemas()
    clear_dev_email_deliveries()
    FakeSMTP.reset()
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        await _clear_u6l_rows_and_schemas()
        clear_dev_email_deliveries()
        FakeSMTP.reset()


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


async def _clear_u6l_rows_and_schemas() -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        rows = (
            await session.execute(
                text(
                    "SELECT wholesaler_id, tenant_schema FROM public.tenant_registrations "
                    "WHERE owner_email LIKE 'u6l_%@example.com'"
                )
            )
        ).mappings().all()
        wholesaler_ids = [row["wholesaler_id"] for row in rows if row["wholesaler_id"] is not None]
        for schema in {row["tenant_schema"] for row in rows if row["tenant_schema"] is not None}:
            if schema.startswith("t_") and schema.replace("_", "").isalnum():
                await session.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await session.execute(
            text(
                "DELETE FROM public.owner_credential_setup_tokens WHERE registration_id IN ("
                "SELECT id FROM public.tenant_registrations "
                "WHERE owner_email LIKE 'u6l_%@example.com')"
            )
        )
        await session.execute(
            text("DELETE FROM public.tenant_registrations WHERE owner_email LIKE 'u6l_%@example.com'")
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


class FakeSMTP:
    sent_messages: list[Any] = []
    login_calls: list[tuple[str, str]] = []
    fail_send = False

    def __init__(self, *_args, **_kwargs) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_exc_info):
        return False

    def starttls(self, *, context) -> None:
        assert context is not None

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
        cls.fail_send = False


def _signup_payload(email: str) -> dict[str, str]:
    return {
        "companyName": f"U6L Company {uuid.uuid4().hex[:8]}",
        "country": "KE",
        "email": email,
        "phone": "+254700000000",
        "businessType": "wholesale",
        "password": VALID_PASSWORD,
    }


def _production_settings(**overrides: Any):
    values = {
        "MPANGO_ENV": "production",
        "SECRET_KEY": onboarding_service.get_settings().SECRET_KEY,
        "DATABASE_URL": "postgresql://postgres@127.0.0.1:55440/mpango_erp",
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


async def _signup(email: str) -> str:
    async with await _client() as client:
        response = await client.post(SIGNUP_URL, json=_signup_payload(email))
    assert response.status_code == 202, response.text
    verification_delivery = _delivery(email, "email_verification")
    return verification_delivery.token


def _delivery(email: str, purpose: str):
    matches = [delivery for delivery in get_dev_email_deliveries(email) if delivery.purpose == purpose]
    assert len(matches) == 1
    return matches[0]


async def _verify(raw_token: str):
    async with await _client() as client:
        return await client.post(VERIFY_EMAIL_URL, json={"token": raw_token})


async def _registration_row(email: str):
    async with AsyncSessionLocal() as session:
        return (
            await session.execute(
                text(
                    "SELECT id, owner_email, status, email_verified_at, wholesaler_id, tenant_schema, "
                    "provisioning_completed_at, password_hash FROM public.tenant_registrations "
                    "WHERE owner_email = :email"
                ),
                {"email": email},
            )
        ).mappings().one_or_none()


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


async def _verification_token_rows(email: str):
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


async def _wholesaler_count(wholesaler_id: uuid.UUID) -> int:
    async with AsyncSessionLocal() as session:
        return int(
            await session.scalar(
                text("SELECT count(*) FROM public.wholesalers WHERE id = :wholesaler_id"),
                {"wholesaler_id": wholesaler_id},
            )
        )


async def _table_count(schema: str, table: str) -> int:
    async with AsyncSessionLocal() as session:
        return int(await session.scalar(text(f'SELECT count(*) FROM "{schema}"."{table}"')))


async def _owner_role_count(schema: str, owner_email: str) -> int:
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


async def _admin_permission_codes(schema: str) -> set[str]:
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                text(
                    f'SELECT p.code FROM "{schema}".permissions p '
                    f'JOIN "{schema}".role_permissions rp ON rp.permission_id = p.id '
                    f'JOIN "{schema}".roles r ON r.id = rp.role_id '
                    "WHERE r.name = 'admin'"
                )
            )
        ).scalars().all()
        return set(rows)


def _assert_public_response_safe(response, *, forbidden_values: tuple[Any, ...] = ()) -> None:
    body = response.text.lower()
    for term in (
        "registrationid",
        "registration_id",
        "tenant_schema",
        "token_hash",
        "setup_token",
        "setuptoken",
        "password_hash",
        "user_id",
        "role_id",
        "permission_id",
    ):
        assert term not in body
    for value in forbidden_values:
        if value is not None:
            assert str(value).lower() not in body


def _setup_token_from_smtp_message(message) -> str:
    body = message.get_content()
    setup_line = next(line for line in body.splitlines() if "setupToken=" in line)
    query = parse_qs(urlparse(setup_line).query)
    assert "setupToken" in query
    return query["setupToken"][0]


async def test_verify_email_provisions_tenant_issues_setup_token_and_sends_owner_email():
    email = f"u6l_{uuid.uuid4().hex}@example.com"
    verification_token = await _signup(email)

    response = await _verify(verification_token)

    assert response.status_code == 200, response.text
    registration = await _registration_row(email)
    setup_delivery = _delivery(email, "owner_setup")
    setup_tokens = await _setup_token_rows(registration["id"])
    assert registration["status"] == "active"
    assert registration["email_verified_at"] is not None
    assert registration["wholesaler_id"] is not None
    assert registration["tenant_schema"] is not None
    assert registration["provisioning_completed_at"] is not None
    assert registration["password_hash"] is None
    assert len(setup_tokens) == 1
    assert setup_tokens[0]["token_hash"] == hash_token(setup_delivery.token)
    assert setup_tokens[0]["token_hash"] != setup_delivery.token
    assert setup_delivery.token in setup_delivery.verification_link
    _assert_public_response_safe(
        response,
        forbidden_values=(
            verification_token,
            setup_delivery.token,
            setup_tokens[0]["token_hash"],
            registration["tenant_schema"],
            registration["wholesaler_id"],
            registration["id"],
        ),
    )


async def test_emailed_setup_token_can_create_first_admin_rbac_and_status_is_public_active():
    email = f"u6l_{uuid.uuid4().hex}@example.com"
    verification_token = await _signup(email)
    verify_response = await _verify(verification_token)
    assert verify_response.status_code == 200, verify_response.text
    setup_token = _delivery(email, "owner_setup").token
    registration = await _registration_row(email)

    async with await _client() as client:
        status_response = await client.post(STATUS_URL, json={"statusToken": verification_token})
        setup_response = await client.post(
            SETUP_CREDENTIAL_URL,
            json={"setup_token": setup_token, "password": OWNER_PASSWORD},
        )

    assert status_response.status_code == 200, status_response.text
    assert status_response.json()["data"] == {"status": "active"}
    _assert_public_response_safe(
        status_response,
        forbidden_values=(verification_token, setup_token, registration["tenant_schema"]),
    )
    assert setup_response.status_code == 200, setup_response.text
    _assert_public_response_safe(setup_response, forbidden_values=(setup_token, registration["tenant_schema"]))
    assert await _table_count(registration["tenant_schema"], "users") == 1
    assert await _table_count(registration["tenant_schema"], "roles") == 1
    assert await _owner_role_count(registration["tenant_schema"], email) == 1
    assert await _admin_permission_codes(registration["tenant_schema"]) == CANONICAL_ADMIN_PERMISSION_CODES


async def test_repeated_internal_orchestration_does_not_duplicate_tenant_token_or_admin_rows():
    email = f"u6l_{uuid.uuid4().hex}@example.com"
    verification_token = await _signup(email)
    response = await _verify(verification_token)
    assert response.status_code == 200, response.text
    registration = await _registration_row(email)

    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        await complete_email_verified_onboarding(db=session, registration_id=registration["id"])
        await complete_email_verified_onboarding(db=session, registration_id=registration["id"])
        await session.commit()

    assert await _wholesaler_count(registration["wholesaler_id"]) == 1
    assert len(await _setup_token_rows(registration["id"])) == 1
    assert len([d for d in get_dev_email_deliveries(email) if d.purpose == "owner_setup"]) == 1

    setup_token = _delivery(email, "owner_setup").token
    async with await _client() as client:
        first_setup = await client.post(
            SETUP_CREDENTIAL_URL,
            json={"setup_token": setup_token, "password": OWNER_PASSWORD},
        )
        replay_setup = await client.post(
            SETUP_CREDENTIAL_URL,
            json={"setup_token": setup_token, "password": "U6LReplayCred_01!"},  # pragma: allowlist secret
        )
    assert first_setup.status_code == 200, first_setup.text
    assert replay_setup.status_code == 401, replay_setup.text
    assert await _table_count(registration["tenant_schema"], "users") == 1
    assert await _table_count(registration["tenant_schema"], "roles") == 1
    assert await _owner_role_count(registration["tenant_schema"], email) == 1


async def test_reused_verification_token_remains_neutral_and_does_not_duplicate_orchestration():
    email = f"u6l_{uuid.uuid4().hex}@example.com"
    verification_token = await _signup(email)
    first = await _verify(verification_token)
    reused = await _verify(verification_token)
    registration = await _registration_row(email)

    assert first.status_code == 200, first.text
    assert reused.status_code == 400, reused.text
    assert reused.json()["detail"]["code"] == "INVALID_OR_EXPIRED_VERIFICATION_TOKEN"
    assert await _wholesaler_count(registration["wholesaler_id"]) == 1
    assert len(await _setup_token_rows(registration["id"])) == 1
    assert len([d for d in get_dev_email_deliveries(email) if d.purpose == "owner_setup"]) == 1
    _assert_public_response_safe(reused, forbidden_values=(verification_token, registration["tenant_schema"]))


async def test_production_missing_owner_setup_smtp_config_fails_closed(monkeypatch):
    email = f"u6l_{uuid.uuid4().hex}@example.com"
    verification_token = await _signup(email)
    settings = _production_settings(SMTP_HOST=None)
    monkeypatch.setattr(onboarding_service, "get_settings", lambda: settings)
    monkeypatch.setattr(onboarding_service, "TenantProvisioningService", FakeProvisioningService)

    response = await _verify(verification_token)

    assert response.status_code == 503, response.text
    assert response.json()["detail"]["code"] == "EMAIL_DELIVERY_NOT_CONFIGURED"
    registration = await _registration_row(email)
    verification_row = (await _verification_token_rows(email))[0]
    assert registration["status"] == "pending_email_verification"
    assert registration["tenant_schema"] is None
    assert verification_row["used_at"] is None
    assert await _setup_token_rows(registration["id"]) == []
    assert [d for d in get_dev_email_deliveries(email) if d.purpose == "owner_setup"] == []
    _assert_public_response_safe(response, forbidden_values=(verification_token,))


async def test_production_owner_setup_smtp_failure_fails_closed_with_retry_anchor(monkeypatch):
    email = f"u6l_{uuid.uuid4().hex}@example.com"
    verification_token = await _signup(email)
    settings = _production_settings()
    FakeSMTP.fail_send = True
    monkeypatch.setattr(onboarding_service, "get_settings", lambda: settings)
    monkeypatch.setattr(onboarding_service, "TenantProvisioningService", FakeProvisioningService)
    monkeypatch.setattr(email_delivery.smtplib, "SMTP", FakeSMTP)

    response = await _verify(verification_token)

    assert response.status_code == 503, response.text
    assert response.json()["detail"]["code"] == "EMAIL_DELIVERY_NOT_CONFIGURED"
    registration = await _registration_row(email)
    verification_row = (await _verification_token_rows(email))[0]
    assert registration["status"] == "active"
    assert registration["tenant_schema"] is not None
    assert registration["wholesaler_id"] is not None
    assert verification_row["used_at"] is None
    assert await _setup_token_rows(registration["id"]) == []
    assert FakeSMTP.sent_messages == []
    _assert_public_response_safe(
        response,
        forbidden_values=(
            verification_token,
            registration["id"],
            registration["wholesaler_id"],
            registration["tenant_schema"],
        ),
    )


async def test_real_bootstrap_owner_setup_smtp_failure_persists_anchor_and_retry_reconciles(monkeypatch):
    email = f"u6l_{uuid.uuid4().hex}@example.com"
    verification_token = await _signup(email)
    settings = _production_settings()
    FakeSMTP.fail_send = True
    monkeypatch.setattr(onboarding_service, "get_settings", lambda: settings)
    monkeypatch.setattr(email_delivery.smtplib, "SMTP", FakeSMTP)

    first = await _verify(verification_token)

    assert first.status_code == 503, first.text
    assert first.json()["detail"]["code"] == "EMAIL_DELIVERY_NOT_CONFIGURED"
    registration_after_failure = await _registration_row(email)
    verification_row = (await _verification_token_rows(email))[0]
    assert registration_after_failure["status"] == "active"
    assert registration_after_failure["wholesaler_id"] is not None
    assert registration_after_failure["tenant_schema"] is not None
    assert registration_after_failure["provisioning_completed_at"] is not None
    assert registration_after_failure["password_hash"] is None
    assert verification_row["used_at"] is None
    assert await _setup_token_rows(registration_after_failure["id"]) == []
    assert FakeSMTP.sent_messages == []
    _assert_public_response_safe(
        first,
        forbidden_values=(
            verification_token,
            registration_after_failure["id"],
            registration_after_failure["wholesaler_id"],
            registration_after_failure["tenant_schema"],
        ),
    )

    FakeSMTP.fail_send = False
    retry = await _verify(verification_token)

    assert retry.status_code == 200, retry.text
    registration_after_retry = await _registration_row(email)
    setup_rows = await _setup_token_rows(registration_after_retry["id"])
    assert registration_after_retry["wholesaler_id"] == registration_after_failure["wholesaler_id"]
    assert registration_after_retry["tenant_schema"] == registration_after_failure["tenant_schema"]
    assert await _wholesaler_count(registration_after_retry["wholesaler_id"]) == 1
    assert len(setup_rows) == 1
    assert len(FakeSMTP.sent_messages) == 1
    setup_token = _setup_token_from_smtp_message(FakeSMTP.sent_messages[0])
    assert setup_rows[0]["token_hash"] == hash_token(setup_token)
    assert setup_rows[0]["token_hash"] != setup_token
    verification_row_after_retry = (await _verification_token_rows(email))[0]
    assert verification_row_after_retry["used_at"] is not None
    _assert_public_response_safe(
        retry,
        forbidden_values=(
            verification_token,
            setup_token,
            setup_rows[0]["token_hash"],
            registration_after_retry["id"],
            registration_after_retry["wholesaler_id"],
            registration_after_retry["tenant_schema"],
        ),
    )


class FakeProvisioningService:
    def __init__(self, db, **_kwargs) -> None:
        self.db = db

    async def claim_registration_for_provisioning(self, registration_id):
        registration = await self.db.get(TenantRegistration, registration_id)
        registration.status = "provisioning"
        registration.provisioning_started_at = datetime.now(timezone.utc)
        await self.db.flush()
        return SimpleNamespace(action="claimed", registration_id=registration_id, status="provisioning")

    async def provision_wholesaler_and_schema(self, registration_id):
        registration = await self.db.get(TenantRegistration, registration_id)
        wholesaler = Wholesaler(
            code=f"U6L{uuid.uuid4().hex[:8].upper()}",
            name="U6L Fake Provisioning Wholesaler",
            status="active",
            provisioned_at=datetime.now(timezone.utc),
        )
        self.db.add(wholesaler)
        await self.db.flush()
        tenant_schema = wholesaler.get_tenant_schema()
        registration.status = "active"
        registration.wholesaler_id = wholesaler.id
        registration.tenant_schema = tenant_schema
        registration.provisioning_completed_at = datetime.now(timezone.utc)
        registration.password_hash = None
        registration.password_hash_cleared_at = datetime.now(timezone.utc)
        registration.password_hash_cleanup_reason = "provisioned"  # pragma: allowlist secret
        await self.db.flush()
        return SimpleNamespace(
            action="provisioned",
            registration_id=registration_id,
            status="active",
            wholesaler_id=wholesaler.id,
            tenant_schema=tenant_schema,
        )
