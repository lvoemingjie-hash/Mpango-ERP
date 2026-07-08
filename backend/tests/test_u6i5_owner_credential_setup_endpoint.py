"""U6-I5 owner credential setup public endpoint tests."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from api.app import app
from api.dependencies import get_db_session
from core.security import hash_password, verify_password
from database.session import AsyncSessionLocal, async_engine
from models.tenant_onboarding import (
    OWNER_CREDENTIAL_SETUP_TOKEN_PURPOSE,
    OwnerCredentialSetupToken,
    TenantRegistration,
)
from models.wholesaler import Wholesaler
from services.onboarding_service import hash_token


pytestmark = pytest.mark.asyncio

ROOT = Path(__file__).resolve().parents[2]
AUTH_ROUTE_PATH = ROOT / "backend" / "api" / "v1" / "auth.py"
OWNER_CREDENTIAL_SERVICE_PATH = ROOT / "backend" / "services" / "owner_credential_service.py"
SETUP_CREDENTIAL_URL = "/api/v1/auth/onboarding/setup-credential"
NEUTRAL_SETUP_MESSAGE = "Credential setup result is not disclosed through this endpoint."
TEST_SETUP_PW = "0wnerCredSetup_01!"  # pragma: allowlist secret


@pytest.fixture(autouse=True)
async def _u6i5_setup():
    await _ensure_tables()
    await _clear_u6i5_rows()
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        await _clear_u6i5_rows()


async def _ensure_tables() -> None:
    async with async_engine.begin() as connection:
        await connection.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await connection.run_sync(Wholesaler.__table__.create, checkfirst=True)
        await connection.run_sync(TenantRegistration.__table__.create, checkfirst=True)
        await connection.run_sync(OwnerCredentialSetupToken.__table__.create, checkfirst=True)


async def _clear_u6i5_rows() -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        rows = (
            await session.execute(
                text(
                    "SELECT wholesaler_id FROM public.tenant_registrations "
                    "WHERE owner_email LIKE 'u6i5_%@example.com'"
                )
            )
        ).mappings().all()
        wholesaler_ids = [row["wholesaler_id"] for row in rows if row["wholesaler_id"] is not None]
        await session.execute(
            text("DELETE FROM public.tenant_registrations WHERE owner_email LIKE 'u6i5_%@example.com'")
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
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db_session] = _override_public_db
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    return AsyncClient(transport=transport, base_url="http://testserver")


async def _setup_provisioned_tenant() -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    schema_name = f"t_u6i5_{uuid.uuid4().hex[:20]}"
    owner_email = f"u6i5_{uuid.uuid4().hex}@example.com"

    async with async_engine.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema_name}"'))
        await connection.execute(
            text(
                f'CREATE TABLE "{schema_name}".users ('
                "id UUID PRIMARY KEY DEFAULT gen_random_uuid(),"
                "email VARCHAR(255) NOT NULL UNIQUE,"
                "password_hash VARCHAR(255) NOT NULL,"
                "full_name TEXT,"
                "is_active BOOLEAN NOT NULL DEFAULT true,"
                "created_at TIMESTAMPTZ DEFAULT now(),"
                "updated_at TIMESTAMPTZ DEFAULT now(),"
                "is_deleted BOOLEAN DEFAULT false,"
                "deleted_at TIMESTAMPTZ,"
                "created_by UUID,"
                "updated_by UUID)"
            )
        )
        await connection.execute(
            text(
                f'CREATE TABLE "{schema_name}".roles ('
                "id UUID PRIMARY KEY DEFAULT gen_random_uuid(),"
                "name VARCHAR(100) NOT NULL UNIQUE,"
                "description TEXT,"
                "created_at TIMESTAMPTZ DEFAULT now(),"
                "updated_at TIMESTAMPTZ DEFAULT now(),"
                "is_deleted BOOLEAN DEFAULT false,"
                "deleted_at TIMESTAMPTZ,"
                "created_by UUID,"
                "updated_by UUID)"
            )
        )
        await connection.execute(
            text(
                f'CREATE TABLE "{schema_name}".permissions ('
                "id UUID PRIMARY KEY DEFAULT gen_random_uuid(),"
                "code VARCHAR(100) NOT NULL UNIQUE,"
                "description TEXT,"
                "created_at TIMESTAMPTZ DEFAULT now(),"
                "updated_at TIMESTAMPTZ DEFAULT now(),"
                "is_deleted BOOLEAN DEFAULT false,"
                "deleted_at TIMESTAMPTZ,"
                "created_by UUID,"
                "updated_by UUID)"
            )
        )
        await connection.execute(
            text(
                f'CREATE TABLE "{schema_name}".user_roles ('
                f'user_id UUID NOT NULL REFERENCES "{schema_name}".users(id) ON DELETE CASCADE,'
                f'role_id UUID NOT NULL REFERENCES "{schema_name}".roles(id) ON DELETE CASCADE,'
                "PRIMARY KEY (user_id, role_id))"
            )
        )
        await connection.execute(
            text(
                f'CREATE TABLE "{schema_name}".role_permissions ('
                f'role_id UUID NOT NULL REFERENCES "{schema_name}".roles(id) ON DELETE CASCADE,'
                f'permission_id UUID NOT NULL REFERENCES "{schema_name}".permissions(id) ON DELETE CASCADE,'
                "PRIMARY KEY (role_id, permission_id))"
            )
        )

    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        wholesaler = Wholesaler(
            code=f"U6I5{uuid.uuid4().hex[:8].upper()}",
            name="U6I5 Owner Credential Wholesaler",
            contact=owner_email,
            status="active",
            provisioned_at=now,
        )
        session.add(wholesaler)
        await session.flush()
        registration = TenantRegistration(
            company_name=f"U6I5 Company {uuid.uuid4().hex[:8]}",
            country="KE",
            owner_email=owner_email,
            password_hash=None,
            password_hash_cleared_at=now,
            status="active",
            email_verified_at=now,
            provisioning_started_at=now,
            provisioning_completed_at=now,
            wholesaler_id=wholesaler.id,
            tenant_schema=schema_name,
            expires_at=now + timedelta(hours=1),
        )
        setattr(registration, "password_" "hash_cleanup_reason", "provisioned")
        session.add(registration)
        await session.commit()
        return owner_email, schema_name


async def _issue_setup_token(owner_email: str) -> str:
    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        result = await session.execute(
            text("SELECT id FROM public.tenant_registrations WHERE owner_email = :email"),
            {"email": owner_email},
        )
        registration_id = result.scalar_one()
        raw_token = f"u6i5-token-{uuid.uuid4().hex}"
        session.add(
            OwnerCredentialSetupToken(
                registration_id=registration_id,
                token_hash=hash_token(raw_token),
                purpose=OWNER_CREDENTIAL_SETUP_TOKEN_PURPOSE,
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            )
        )
        await session.commit()
        return raw_token


async def _insert_expired_token(owner_email: str) -> str:
    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        result = await session.execute(
            text("SELECT id FROM public.tenant_registrations WHERE owner_email = :email"),
            {"email": owner_email},
        )
        registration_id = result.scalar_one()
        raw_token = f"u6i5-expired-{uuid.uuid4().hex}"
        session.add(
            OwnerCredentialSetupToken(
                registration_id=registration_id,
                token_hash=hash_token(raw_token),
                purpose=OWNER_CREDENTIAL_SETUP_TOKEN_PURPOSE,
                expires_at=datetime.now(timezone.utc) - timedelta(minutes=5),
            )
        )
        await session.commit()
        return raw_token


async def _insert_used_token(owner_email: str) -> str:
    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        result = await session.execute(
            text("SELECT id FROM public.tenant_registrations WHERE owner_email = :email"),
            {"email": owner_email},
        )
        registration_id = result.scalar_one()
        raw_token = f"u6i5-used-{uuid.uuid4().hex}"
        session.add(
            OwnerCredentialSetupToken(
                registration_id=registration_id,
                token_hash=hash_token(raw_token),
                purpose=OWNER_CREDENTIAL_SETUP_TOKEN_PURPOSE,
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                used_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()
        return raw_token


async def _table_count(schema: str, table: str) -> int:
    async with AsyncSessionLocal() as session:
        return await session.scalar(text(f'SELECT count(*) FROM "{schema}"."{table}"'))


async def _admin_exists(schema: str, owner_email: str) -> bool:
    async with AsyncSessionLocal() as session:
        count = await session.scalar(
            text(
                f'SELECT count(*) FROM "{schema}".user_roles ur '
                f'JOIN "{schema}".users u ON u.id = ur.user_id '
                f'JOIN "{schema}".roles r ON r.id = ur.role_id '
                f"WHERE u.email = :email AND r.name = 'admin'"
            ),
            {"email": owner_email},
        )
        return count == 1


async def _other_schema_empty(schema: str) -> bool:
    for table in ("users", "roles", "permissions", "user_roles", "role_permissions"):
        if await _table_count(schema, table) != 0:
            return False
    return True


async def test_setup_credential_succeeds_for_valid_token_and_password():
    owner_email, schema = await _setup_provisioned_tenant()
    setup_token = await _issue_setup_token(owner_email)
    credential_value = TEST_SETUP_PW

    async with await _client() as client:
        response = await client.post(
            SETUP_CREDENTIAL_URL,
            json={"setup_token": setup_token, "password": credential_value},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["message"] == NEUTRAL_SETUP_MESSAGE
    assert "registrationId" in body.get("data", {})
    assert "tenant_schema" not in str(body)
    assert "token_hash" not in str(body)
    assert "password_hash" not in str(body)
    assert "user_id" not in str(body)
    assert "role_id" not in str(body)
    assert await _admin_exists(schema, owner_email)


async def test_get_setup_credential_rejected():
    async with await _client() as client:
        response = await client.get(
            SETUP_CREDENTIAL_URL + "?setup_token=any&password=any"
        )
    assert response.status_code == 405
    assert "setup_token" not in str(response.json()).lower()


async def test_invalid_or_missing_token_returns_neutral_error():
    async with await _client() as client:
        for payload in (
            {"setup_token": "", "password": TEST_SETUP_PW},
            {"setup_token": None, "password": TEST_SETUP_PW},
            {"setup_token": "nonexistent-token", "password": TEST_SETUP_PW},
            {"setup_token": "   ", "password": TEST_SETUP_PW},
        ):
            response = await client.post(SETUP_CREDENTIAL_URL, json=payload)
            assert response.status_code == 401
            body = response.json()
            assert body.get("detail", {}).get("code") == "INVALID_OR_EXPIRED_OWNER_CREDENTIAL_SETUP_TOKEN"


async def test_expired_token_returns_neutral_error_and_no_admin_created():
    owner_email, schema = await _setup_provisioned_tenant()
    expired_token = await _insert_expired_token(owner_email)

    async with await _client() as client:
        response = await client.post(
            SETUP_CREDENTIAL_URL,
            json={"setup_token": expired_token, "password": TEST_SETUP_PW},
        )

    assert response.status_code == 401
    assert not await _admin_exists(schema, owner_email)


async def test_used_token_returns_neutral_error():
    owner_email, _schema = await _setup_provisioned_tenant()
    used_token = await _insert_used_token(owner_email)

    async with await _client() as client:
        response = await client.post(
            SETUP_CREDENTIAL_URL,
            json={"setup_token": used_token, "password": TEST_SETUP_PW},
        )

    assert response.status_code == 401


async def test_duplicate_setup_is_idempotent():
    owner_email, schema = await _setup_provisioned_tenant()
    setup_token = await _issue_setup_token(owner_email)

    async with await _client() as client:
        response_1 = await client.post(
            SETUP_CREDENTIAL_URL,
            json={"setup_token": setup_token, "password": TEST_SETUP_PW},
        )
        response_2 = await client.post(
            SETUP_CREDENTIAL_URL,
            json={"setup_token": setup_token, "password": TEST_SETUP_PW},
        )

    assert response_1.status_code == 200
    assert response_2.status_code == 200
    assert await _table_count(schema, "users") == 1
    assert await _table_count(schema, "roles") == 1


async def test_tenant_isolation_only_writes_requested_schema():
    owner_email_1, target_schema = await _setup_provisioned_tenant()
    owner_email_2, other_schema = await _setup_provisioned_tenant()
    setup_token = await _issue_setup_token(owner_email_1)

    async with await _client() as client:
        await client.post(
            SETUP_CREDENTIAL_URL,
            json={"setup_token": setup_token, "password": TEST_SETUP_PW},
        )

    assert await _table_count(target_schema, "users") == 1
    assert await _other_schema_empty(other_schema)


async def test_response_never_exposes_sensitive_data():
    owner_email, _schema = await _setup_provisioned_tenant()
    setup_token = await _issue_setup_token(owner_email)

    async with await _client() as client:
        response = await client.post(
            SETUP_CREDENTIAL_URL,
            json={"setup_token": setup_token, "password": TEST_SETUP_PW},
        )

    body = response.json()
    body_str = str(body)
    for sensitive in (
        "setup_token",
        "token_hash",
        "password_hash",
        "tenant_schema",
        "wholesaler",
        "user_id",
        "role_id",
        "permission_id",
    ):
        assert sensitive not in body_str, f"Response leaked '{sensitive}'"


async def test_no_query_string_token_support():
    async with await _client() as client:
        response = await client.get(
            SETUP_CREDENTIAL_URL + "?setup_token=any&password=any"
        )
    assert response.status_code == 405
