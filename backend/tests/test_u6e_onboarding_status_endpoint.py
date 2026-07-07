"""U6-E onboarding status endpoint tests."""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from api.app import app
from api.dependencies import get_db_session
from database.session import AsyncSessionLocal, async_engine
from models.tenant_onboarding import (
    EmailVerificationToken,
    OnboardingStatusToken,
    TenantRegistration,
)
from models.wholesaler import Wholesaler
from services.email_delivery import clear_dev_email_deliveries, get_dev_email_deliveries


pytestmark = pytest.mark.asyncio

VALID_PASSWORD = "ValidSignupCred123!"  # pragma: allowlist secret


@pytest.fixture(autouse=True)
async def _u6e_public_schema():
    await _ensure_onboarding_tables()
    await _clear_u6e_rows()
    clear_dev_email_deliveries()
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        await _clear_u6e_rows()
        clear_dev_email_deliveries()


async def _ensure_onboarding_tables() -> None:
    async with async_engine.begin() as connection:
        await connection.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await connection.run_sync(Wholesaler.__table__.create, checkfirst=True)
        await connection.run_sync(TenantRegistration.__table__.create, checkfirst=True)
        await connection.run_sync(EmailVerificationToken.__table__.create, checkfirst=True)
        await connection.run_sync(OnboardingStatusToken.__table__.create, checkfirst=True)


async def _clear_u6e_rows() -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        await session.execute(
            text(
                "DELETE FROM public.onboarding_status_tokens "
                "WHERE registration_id IN ("
                "SELECT id FROM public.tenant_registrations "
                "WHERE owner_email LIKE 'u6e_%@example.com')"
            )
        )
        await session.execute(
            text(
                "DELETE FROM public.email_verification_tokens "
                "WHERE registration_id IN ("
                "SELECT id FROM public.tenant_registrations "
                "WHERE owner_email LIKE 'u6e_%@example.com')"
            )
        )
        await session.execute(
            text("DELETE FROM public.tenant_registrations WHERE owner_email LIKE 'u6e_%@example.com'")
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
        "companyName": f"U6E Company {uuid.uuid4().hex[:8]}",
        "country": "KE",
        "email": email,
        "phone": "+254700000000",
        "businessType": "wholesale",
        "password": VALID_PASSWORD,
    }


async def _signup_and_status_token(email: str, *, headers: dict[str, str] | None = None) -> str:
    async with await _client() as client:
        response = await client.post(
            "/api/v1/auth/signup", json=_signup_payload(email), headers=headers
        )
    assert response.status_code == 202, response.text
    deliveries = get_dev_email_deliveries(email)
    assert len(deliveries) == 1
    return deliveries[0].token


async def _registration_row(email: str):
    async with AsyncSessionLocal() as session:
        return (
            await session.execute(
                text(
                    "SELECT id, owner_email, status, tenant_schema, wholesaler_id "
                    "FROM public.tenant_registrations WHERE owner_email = :email"
                ),
                {"email": email},
            )
        ).mappings().one_or_none()


async def _status_token_rows_for_email(email: str):
    async with AsyncSessionLocal() as session:
        return (
            await session.execute(
                text(
                    "SELECT ost.* FROM public.onboarding_status_tokens ost "
                    "JOIN public.tenant_registrations tr ON tr.id = ost.registration_id "
                    "WHERE tr.owner_email = :email ORDER BY ost.created_at"
                ),
                {"email": email},
            )
        ).mappings().all()


async def _active_status_token_rows_for_email(email: str):
    rows = await _status_token_rows_for_email(email)
    return [row for row in rows if row["revoked_at"] is None and row["is_deleted"] is False]


async def _set_status_token_expired(email: str) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        await session.execute(
            text(
                "UPDATE public.onboarding_status_tokens "
                "SET created_at = now() - interval '2 hours', "
                "expires_at = now() - interval '1 hour' "
                "WHERE registration_id IN ("
                "SELECT id FROM public.tenant_registrations WHERE owner_email = :email)"
            ),
            {"email": email},
        )
        await session.commit()


async def _set_status_token_revoked(email: str) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        await session.execute(
            text(
                "UPDATE public.onboarding_status_tokens "
                "SET revoked_at = now() "
                "WHERE registration_id IN ("
                "SELECT id FROM public.tenant_registrations WHERE owner_email = :email)"
            ),
            {"email": email},
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


def _assert_neutral_failure(response):
    assert response.status_code == 400, response.text
    body = response.json()
    assert body["detail"]["code"] == "INVALID_OR_EXPIRED_ONBOARDING_STATUS_TOKEN"
    lowered = str(body).lower()
    assert "registration" not in lowered
    assert "tenant" not in lowered
    assert "hash" not in lowered
    assert "password" not in lowered


async def test_signup_creates_one_active_status_token_hash_for_new_registration():
    email = f"u6e_{uuid.uuid4().hex}@example.com"
    raw_status_token = await _signup_and_status_token(email)

    rows = await _status_token_rows_for_email(email)
    assert len(rows) == 1
    assert len(await _active_status_token_rows_for_email(email)) == 1
    assert rows[0]["purpose"] == "onboarding_status"
    assert rows[0]["token_hash"]
    assert raw_status_token not in rows[0]["token_hash"]
    assert "token" not in set(rows[0].keys())
    assert "raw_token" not in set(rows[0].keys())
    assert "token_plaintext" not in set(rows[0].keys())


async def test_duplicate_live_email_neutral_signup_creates_no_new_status_token():
    local = f"u6e_{uuid.uuid4().hex}"
    first_email = f"{local}@example.com"
    duplicate_email = f"{local.upper()}@example.com"

    async with await _client() as client:
        first = await client.post("/api/v1/auth/signup", json=_signup_payload(first_email))
        duplicate = await client.post("/api/v1/auth/signup", json=_signup_payload(duplicate_email))

    assert first.status_code == 202, first.text
    assert duplicate.status_code == 202, duplicate.text
    assert first.json()["data"] == duplicate.json()["data"]
    assert len(await _active_status_token_rows_for_email(first_email)) == 1
    assert len(get_dev_email_deliveries(first_email)) == 1


async def test_idempotent_signup_retry_creates_no_duplicate_active_status_token():
    email = f"u6e_{uuid.uuid4().hex}@example.com"
    payload = _signup_payload(email)
    headers = {"Idempotency-Key": f"u6e-{uuid.uuid4().hex}"}

    async with await _client() as client:
        first = await client.post("/api/v1/auth/signup", json=payload, headers=headers)
        second = await client.post("/api/v1/auth/signup", json=payload, headers=headers)

    assert first.status_code == 202, first.text
    assert second.status_code == 202, second.text
    assert first.json()["data"] == second.json()["data"]
    assert len(await _active_status_token_rows_for_email(email)) == 1
    assert len(get_dev_email_deliveries(email)) == 1


async def test_valid_body_status_token_returns_pending_email_verification():
    email = f"u6e_{uuid.uuid4().hex}@example.com"
    raw_status_token = await _signup_and_status_token(email)

    async with await _client() as client:
        response = await client.post(
            "/api/v1/auth/onboarding/status", json={"statusToken": raw_status_token}
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["success"] is True
    assert body["data"] == {"status": "pending_email_verification"}
    assert raw_status_token not in response.text


async def test_after_verify_email_valid_status_token_returns_email_verified():
    email = f"u6e_{uuid.uuid4().hex}@example.com"
    raw_status_token = await _signup_and_status_token(email)

    async with await _client() as client:
        verify_response = await client.post("/api/v1/auth/verify-email", json={"token": raw_status_token})
        status_response = await client.post(
            "/api/v1/auth/onboarding/status",
            json={"statusToken": raw_status_token},
            headers={"X-Onboarding-Status-Token": raw_status_token},
        )

    assert verify_response.status_code == 200, verify_response.text
    assert status_response.status_code == 200, status_response.text
    assert status_response.json()["data"] == {"status": "email_verified"}


async def test_invalid_status_token_returns_neutral_failure_and_writes_nothing():
    email = f"u6e_{uuid.uuid4().hex}@example.com"
    await _signup_and_status_token(email)
    before_registration = await _registration_row(email)
    before_status_tokens = await _status_token_rows_for_email(email)

    async with await _client() as client:
        response = await client.post(
            "/api/v1/auth/onboarding/status", json={"statusToken": "not-a-real-token"}
        )

    _assert_neutral_failure(response)
    assert await _registration_row(email) == before_registration
    assert await _status_token_rows_for_email(email) == before_status_tokens


async def test_missing_status_token_returns_neutral_failure():
    async with await _client() as client:
        response = await client.post("/api/v1/auth/onboarding/status", json={})

    _assert_neutral_failure(response)


async def test_query_string_status_token_alone_fails_neutrally():
    email = f"u6e_{uuid.uuid4().hex}@example.com"
    raw_status_token = await _signup_and_status_token(email)
    before_status_tokens = await _status_token_rows_for_email(email)

    async with await _client() as client:
        response = await client.post(
            f"/api/v1/auth/onboarding/status?statusToken={raw_status_token}", json={}
        )

    _assert_neutral_failure(response)
    assert await _status_token_rows_for_email(email) == before_status_tokens


async def test_body_header_status_token_mismatch_fails_neutrally():
    email = f"u6e_{uuid.uuid4().hex}@example.com"
    raw_status_token = await _signup_and_status_token(email)

    async with await _client() as client:
        response = await client.post(
            "/api/v1/auth/onboarding/status",
            json={"statusToken": raw_status_token},
            headers={"X-Onboarding-Status-Token": "different-token"},
        )

    _assert_neutral_failure(response)


async def test_expired_or_revoked_status_token_fails_neutrally():
    expired_email = f"u6e_{uuid.uuid4().hex}@example.com"
    revoked_email = f"u6e_{uuid.uuid4().hex}@example.com"
    expired_token = await _signup_and_status_token(expired_email)
    revoked_token = await _signup_and_status_token(revoked_email)
    await _set_status_token_expired(expired_email)
    await _set_status_token_revoked(revoked_email)

    async with await _client() as client:
        expired_response = await client.post(
            "/api/v1/auth/onboarding/status", json={"statusToken": expired_token}
        )
        revoked_response = await client.post(
            "/api/v1/auth/onboarding/status", json={"statusToken": revoked_token}
        )

    _assert_neutral_failure(expired_response)
    _assert_neutral_failure(revoked_response)


async def test_status_response_never_exposes_sensitive_internal_details():
    email = f"u6e_{uuid.uuid4().hex}@example.com"
    raw_status_token = await _signup_and_status_token(email)
    registration = await _registration_row(email)

    async with await _client() as client:
        response = await client.post(
            "/api/v1/auth/onboarding/status", json={"statusToken": raw_status_token}
        )

    assert response.status_code == 200, response.text
    body_text = response.text.lower()
    assert str(registration["id"]).lower() not in body_text
    assert email not in body_text
    assert raw_status_token not in response.text
    assert "registration" not in body_text
    assert "tenant" not in body_text
    assert "schema" not in body_text
    assert "wholesaler" not in body_text
    assert "user" not in body_text
    assert "role" not in body_text
    assert "token" not in body_text
    assert "hash" not in body_text
    assert "password_hash" not in body_text


async def test_onboarding_status_has_no_tenant_schema_users_roles_or_rbac_side_effects():
    email = f"u6e_{uuid.uuid4().hex}@example.com"
    raw_status_token = await _signup_and_status_token(email)
    schemas_before = await _tenant_schema_names()
    rbac_before = await _rbac_table_inventory()

    async with await _client() as client:
        response = await client.post(
            "/api/v1/auth/onboarding/status", json={"statusToken": raw_status_token}
        )

    assert response.status_code == 200, response.text
    assert await _tenant_schema_names() == schemas_before
    assert await _rbac_table_inventory() == rbac_before
    registration = await _registration_row(email)
    assert registration["tenant_schema"] is None
    assert registration["wholesaler_id"] is None


async def test_onboarding_status_has_no_get_route():
    methods_by_path = {route.path: getattr(route, "methods", set()) for route in app.routes}

    assert "/api/v1/auth/onboarding/status" in methods_by_path
    assert "POST" in methods_by_path["/api/v1/auth/onboarding/status"]
    assert "GET" not in methods_by_path["/api/v1/auth/onboarding/status"]
