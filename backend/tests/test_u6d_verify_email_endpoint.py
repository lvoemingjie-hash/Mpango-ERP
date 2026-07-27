"""U6-D verify-email endpoint skeleton tests."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, Mock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from api.app import app
from api.dependencies import get_db_session
from core.permission_registry import (
    ADMIN_MANAGEMENT_PERMISSION_CODES,
    ADMIN_ROLE,
    RETAILER_OPERATOR_PERMISSION_CODES,
    RETAILER_OPERATOR_ROLE,
)
from database.session import AsyncSessionLocal, async_engine
from models.tenant_onboarding import (
    EmailVerificationToken,
    OnboardingStatusToken,
    OwnerCredentialSetupToken,
    TenantRegistration,
)
from models.wholesaler import Wholesaler
from services.email_delivery import clear_dev_email_deliveries, get_dev_email_deliveries


pytestmark = pytest.mark.asyncio

VALID_PASSWORD = "ValidSignupCred123!"  # pragma: allowlist secret


@pytest.fixture(autouse=True)
async def _u6d_public_schema():
    await _ensure_onboarding_tables()
    await _clear_u6d_rows()
    clear_dev_email_deliveries()
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        await _clear_u6d_rows()
        clear_dev_email_deliveries()


@pytest.fixture(autouse=True)
def _allow_rate_limiter():
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


async def _clear_u6d_rows() -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        rows = (
            await session.execute(
                text(
                    "SELECT wholesaler_id, tenant_schema FROM public.tenant_registrations "
                    "WHERE owner_email LIKE 'u6d_%@example.com'"
                )
            )
        ).mappings().all()
        wholesaler_ids = [row["wholesaler_id"] for row in rows if row["wholesaler_id"] is not None]
        for schema in {row["tenant_schema"] for row in rows if row["tenant_schema"] is not None}:
            if schema.startswith("t_") and schema.replace("_", "").isalnum():
                await session.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await session.execute(
            text(
                "DELETE FROM public.owner_credential_setup_tokens "
                "WHERE registration_id IN ("
                "SELECT id FROM public.tenant_registrations "
                "WHERE owner_email LIKE 'u6d_%@example.com')"
            )
        )
        await session.execute(
            text(
                "DELETE FROM public.email_verification_tokens "
                "WHERE registration_id IN ("
                "SELECT id FROM public.tenant_registrations "
                "WHERE owner_email LIKE 'u6d_%@example.com')"
            )
        )
        await session.execute(
            text("DELETE FROM public.tenant_registrations WHERE owner_email LIKE 'u6d_%@example.com'")
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


def _signup_payload(email: str) -> dict[str, str]:
    return {
        "companyName": f"U6D Company {uuid.uuid4().hex[:8]}",
        "country": "KE",
        "email": email,
        "phone": "+254700000000",
        "businessType": "wholesale",
        "password": VALID_PASSWORD,
    }


async def _signup_and_token(email: str) -> str:
    async with await _client() as client:
        response = await client.post("/api/v1/auth/signup", json=_signup_payload(email))
    assert response.status_code == 202, response.text
    deliveries = get_dev_email_deliveries(email)
    assert len(deliveries) == 1
    return deliveries[0].token


async def _registration_row(email: str):
    async with AsyncSessionLocal() as session:
        return (
            await session.execute(
                text(
                    "SELECT id, owner_email, status, email_verified_at, tenant_schema, "
                    "wholesaler_id FROM public.tenant_registrations "
                    "WHERE owner_email = :email"
                ),
                {"email": email},
            )
        ).mappings().one_or_none()


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


async def _set_token_expired(email: str) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        await session.execute(
            text(
                "UPDATE public.email_verification_tokens "
                "SET expires_at = now() - interval '1 hour' "
                "WHERE registration_id IN ("
                "SELECT id FROM public.tenant_registrations WHERE owner_email = :email)"
            ),
            {"email": email},
        )
        await session.commit()


async def _set_registration_status(email: str, status: str) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        await session.execute(
            text(
                "UPDATE public.tenant_registrations "
                "SET status = :status, email_verified_at = now() "
                "WHERE owner_email = :email"
            ),
            {"email": email, "status": status},
        )
        await session.commit()


async def _tenant_schema_names() -> set[str]:
    async with AsyncSessionLocal() as session:
        return set(
            (
                await session.execute(
                    text("SELECT nspname FROM pg_namespace WHERE nspname LIKE 't_%'")
                )
            ).scalars()
        )


async def _rbac_table_inventory() -> set[tuple[str, str]]:
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT n.nspname, c.relname FROM pg_class c "
                    "JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE c.relkind = 'r' "
                    "AND c.relname IN ('users', 'roles', 'permissions', 'user_roles', 'role_permissions')"
                )
            )
        ).all()
        return {(schema, table) for schema, table in rows}


async def _table_count(schema: str, table: str) -> int:
    async with AsyncSessionLocal() as session:
        return int(await session.scalar(text(f'SELECT count(*) FROM "{schema}"."{table}"')))


async def _role_exists(schema: str, role_name: str) -> bool:
    async with AsyncSessionLocal() as session:
        row = await session.execute(
            text(f'SELECT 1 FROM "{schema}".roles WHERE name = :role_name'),
            {"role_name": role_name},
        )
        return row.first() is not None


async def _permission_codes(schema: str) -> set[str]:
    async with AsyncSessionLocal() as session:
        return set(
            (
                await session.execute(text(f'SELECT code FROM "{schema}".permissions'))
            ).scalars()
        )


async def _role_permission_codes(schema: str, role_name: str) -> set[str]:
    async with AsyncSessionLocal() as session:
        return set(
            (
                await session.execute(
                    text(
                        f'SELECT p.code FROM "{schema}".permissions p '
                        f'JOIN "{schema}".role_permissions rp ON rp.permission_id = p.id '
                        f'JOIN "{schema}".roles r ON r.id = rp.role_id '
                        "WHERE r.name = :role_name"
                    ),
                    {"role_name": role_name},
                )
            ).scalars()
        )


def _assert_neutral_failure(response):
    assert response.status_code == 400, response.text
    body = response.json()
    assert body["detail"]["code"] == "INVALID_OR_EXPIRED_VERIFICATION_TOKEN"
    assert "hash" not in str(body).lower()
    assert "registration" not in str(body).lower()
    assert "tenant" not in str(body).lower()


async def test_valid_token_verifies_registration_and_marks_token_used():
    email = f"u6d_{uuid.uuid4().hex}@example.com"
    raw_token = await _signup_and_token(email)

    async with await _client() as client:
        response = await client.post("/api/v1/auth/verify-email", json={"token": raw_token})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["success"] is True
    assert "token" not in str(body).lower()
    assert "hash" not in str(body).lower()
    assert "registration" not in str(body).lower()
    assert "tenant" not in str(body).lower()

    registration = await _registration_row(email)
    assert registration["status"] == "active"
    assert registration["email_verified_at"] is not None
    assert registration["tenant_schema"] is not None
    assert registration["wholesaler_id"] is not None

    token_rows = await _token_rows_for_email(email)
    assert len(token_rows) == 1
    assert token_rows[0]["used_at"] is not None


async def test_invalid_token_returns_neutral_failure_and_writes_nothing():
    email = f"u6d_{uuid.uuid4().hex}@example.com"
    await _signup_and_token(email)
    before_registration = await _registration_row(email)
    before_tokens = await _token_rows_for_email(email)

    async with await _client() as client:
        response = await client.post("/api/v1/auth/verify-email", json={"token": "not-a-real-token"})

    _assert_neutral_failure(response)
    assert await _registration_row(email) == before_registration
    assert await _token_rows_for_email(email) == before_tokens


async def test_missing_or_query_string_token_returns_neutral_failure_and_writes_nothing():
    email = f"u6d_{uuid.uuid4().hex}@example.com"
    raw_token = await _signup_and_token(email)
    before_registration = await _registration_row(email)
    before_tokens = await _token_rows_for_email(email)

    async with await _client() as client:
        missing = await client.post("/api/v1/auth/verify-email", json={})
        query_only = await client.post(f"/api/v1/auth/verify-email?token={raw_token}", json={})

    _assert_neutral_failure(missing)
    _assert_neutral_failure(query_only)
    assert await _registration_row(email) == before_registration
    assert await _token_rows_for_email(email) == before_tokens


async def test_verify_email_has_no_get_query_token_route():
    methods_by_path = {route.path: getattr(route, "methods", set()) for route in app.routes}

    assert "/api/v1/auth/verify-email" in methods_by_path
    assert "POST" in methods_by_path["/api/v1/auth/verify-email"]
    assert "GET" not in methods_by_path["/api/v1/auth/verify-email"]


async def test_expired_token_returns_neutral_failure_and_writes_nothing():
    email = f"u6d_{uuid.uuid4().hex}@example.com"
    raw_token = await _signup_and_token(email)
    await _set_token_expired(email)
    before_registration = await _registration_row(email)
    before_tokens = await _token_rows_for_email(email)

    async with await _client() as client:
        response = await client.post("/api/v1/auth/verify-email", json={"token": raw_token})

    _assert_neutral_failure(response)
    assert await _registration_row(email) == before_registration
    assert await _token_rows_for_email(email) == before_tokens


async def test_reused_token_cannot_verify_twice():
    email = f"u6d_{uuid.uuid4().hex}@example.com"
    raw_token = await _signup_and_token(email)

    async with await _client() as client:
        first = await client.post("/api/v1/auth/verify-email", json={"token": raw_token})
        second = await client.post("/api/v1/auth/verify-email", json={"token": raw_token})

    assert first.status_code == 200, first.text
    _assert_neutral_failure(second)
    registration = await _registration_row(email)
    assert registration["status"] == "active"
    token_rows = await _token_rows_for_email(email)
    assert len(token_rows) == 1
    assert token_rows[0]["used_at"] is not None


async def test_token_for_non_pending_registration_does_not_regress_state():
    email = f"u6d_{uuid.uuid4().hex}@example.com"
    raw_token = await _signup_and_token(email)
    await _set_registration_status(email, "email_verified")
    before_registration = await _registration_row(email)
    before_tokens = await _token_rows_for_email(email)

    async with await _client() as client:
        response = await client.post("/api/v1/auth/verify-email", json={"token": raw_token})

    _assert_neutral_failure(response)
    assert await _registration_row(email) == before_registration
    assert await _token_rows_for_email(email) == before_tokens


async def test_verify_email_provisions_tenant_schema_without_admin_rbac_side_effects():
    email = f"u6d_{uuid.uuid4().hex}@example.com"
    raw_token = await _signup_and_token(email)
    schemas_before = await _tenant_schema_names()

    async with await _client() as client:
        response = await client.post("/api/v1/auth/verify-email", json={"token": raw_token})

    assert response.status_code == 200, response.text
    registration = await _registration_row(email)
    assert await _tenant_schema_names() == schemas_before | {registration["tenant_schema"]}
    assert registration["tenant_schema"] is not None
    assert registration["wholesaler_id"] is not None
    assert await _table_count(registration["tenant_schema"], "users") == 0
    assert await _table_count(registration["tenant_schema"], "user_roles") == 0
    assert await _role_permission_codes(registration["tenant_schema"], RETAILER_OPERATOR_ROLE) == set(
        RETAILER_OPERATOR_PERMISSION_CODES
    )
    assert ADMIN_MANAGEMENT_PERMISSION_CODES <= await _permission_codes(
        registration["tenant_schema"]
    )
    assert not await _role_exists(registration["tenant_schema"], ADMIN_ROLE)
