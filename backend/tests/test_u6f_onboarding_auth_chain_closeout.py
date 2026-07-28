"""U6-F closeout gate for the signup, verify-email, and status auth chain."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
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
from tests.test_route_authorization_policy import ALL_CLASSIFICATIONS, PUBLIC_ALLOWLIST


pytestmark = pytest.mark.asyncio

VALID_PASSWORD = "ValidSignupCred123!"  # pragma: allowlist secret
LIVE_STATUSES = {
    "pending_email_verification",
    "email_verified",
    "provisioning",
    "active",
    "failed",
}
EXPECTED_PUBLIC_ALLOWLIST = {
    "/api/v1/auth/login",
    "/api/v1/auth/signup",
    "/api/v1/auth/verify-email",
    "/api/v1/auth/onboarding/status",
    "/api/v1/auth/onboarding/setup-credential",
    "/api/v1/auth/forgot-password",
    "/api/v1/auth/reset-password",
    "/api/v1/auth/refresh",
    "/api/v1/invitations/{code}",
    "/api/v1/retailers/register",
    "/api/v1/retailers/setup-credential",
    "/api/v1/client/auth/forgot-password",
    "/api/v1/client/auth/reset-password",
    "/api/v1/client/auth/login",
    "/api/v1/invitations/lookup",
}
SENSITIVE_RESPONSE_TERMS = (
    "tenant",
    "schema",
    "wholesaler",
    "user",
    "role",
    "token",
    "hash",
    "password_hash",
)
SIDE_EFFECT_TABLES = {
    "users",
    "roles",
    "permissions",
    "user_roles",
    "role_permissions",
    "inventory_stock",
    "inventory_reservations",
    "orders",
    "order_items",
    "payments",
    "ledger_entries",
    "intake_workspaces",
    "intake_uploads",
}


@pytest.fixture(autouse=True)
async def _u6f_public_schema():
    await _ensure_onboarding_tables()
    await _clear_u6f_rows()
    clear_dev_email_deliveries()
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        await _clear_u6f_rows()
        clear_dev_email_deliveries()


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


async def _clear_u6f_rows() -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        rows = (
            await session.execute(
                text(
                    "SELECT wholesaler_id, tenant_schema FROM public.tenant_registrations "
                    "WHERE owner_email LIKE 'u6f_%@example.com'"
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
                "WHERE owner_email LIKE 'u6f_%@example.com')"
            )
        )
        await session.execute(
            text(
                "DELETE FROM public.onboarding_status_tokens "
                "WHERE registration_id IN ("
                "SELECT id FROM public.tenant_registrations "
                "WHERE owner_email LIKE 'u6f_%@example.com')"
            )
        )
        await session.execute(
            text(
                "DELETE FROM public.email_verification_tokens "
                "WHERE registration_id IN ("
                "SELECT id FROM public.tenant_registrations "
                "WHERE owner_email LIKE 'u6f_%@example.com')"
            )
        )
        await session.execute(
            text("DELETE FROM public.tenant_registrations WHERE owner_email LIKE 'u6f_%@example.com'")
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


def _signup_payload(email: str, *, company_name: str | None = None) -> dict[str, str]:
    return {
        "companyName": company_name or f"U6F Company {uuid.uuid4().hex[:8]}",
        "country": "KE",
        "email": email,
        "phone": "+254700000000",
        "businessType": "wholesale",
        "password": VALID_PASSWORD,
    }


async def _registration_rows(email: str):
    async with AsyncSessionLocal() as session:
        return (
            await session.execute(
                text(
                    "SELECT id, owner_email, status, password_hash, tenant_schema, wholesaler_id, "
                    "idempotency_key_hash, request_fingerprint_hash "
                    "FROM public.tenant_registrations WHERE owner_email = :email ORDER BY created_at"
                ),
                {"email": email},
            )
        ).mappings().all()


async def _registration_by_email(email: str):
    rows = await _registration_rows(email)
    assert len(rows) == 1
    return rows[0]


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


async def _status_token_rows(email: str):
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


async def _active_status_token_rows(email: str):
    rows = await _status_token_rows(email)
    return [row for row in rows if row["revoked_at"] is None and row["is_deleted"] is False]


async def _active_verification_token_rows(email: str):
    rows = await _verification_token_rows(email)
    return [row for row in rows if row["used_at"] is None and row["revoked_at"] is None]


async def _set_verification_token_expired(email: str) -> None:
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


async def _tenant_schema_names() -> set[str]:
    async with AsyncSessionLocal() as session:
        return set(
            (
                await session.execute(
                    text("SELECT nspname FROM pg_namespace WHERE nspname LIKE 't_%'")
                )
            ).scalars()
        )


async def _side_effect_table_inventory() -> set[tuple[str, str]]:
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT n.nspname, c.relname FROM pg_class c "
                    "JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE c.relkind = 'r'"
                )
            )
        ).all()
        return {(schema, table) for schema, table in rows if table in SIDE_EFFECT_TABLES}


async def _setup_token_rows(email: str):
    async with AsyncSessionLocal() as session:
        return (
            await session.execute(
                text(
                    "SELECT oct.* FROM public.owner_credential_setup_tokens oct "
                    "JOIN public.tenant_registrations tr ON tr.id = oct.registration_id "
                    "WHERE tr.owner_email = :email ORDER BY oct.created_at"
                ),
                {"email": email},
            )
        ).mappings().all()


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
                await session.execute(
                    text(f'SELECT code FROM "{schema}".permissions')
                )
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


async def _assert_current_bootstrap_rbac(schema: str) -> None:
    assert await _table_count(schema, "users") == 0
    assert await _table_count(schema, "user_roles") == 0
    assert await _role_permission_codes(schema, RETAILER_OPERATOR_ROLE) == set(
        RETAILER_OPERATOR_PERMISSION_CODES
    )
    assert ADMIN_MANAGEMENT_PERMISSION_CODES <= await _permission_codes(schema)
    assert not await _role_exists(schema, ADMIN_ROLE)


async def _signup(email: str, *, payload: dict[str, str] | None = None, headers=None):
    async with await _client() as client:
        return await client.post(
            "/api/v1/auth/signup", json=payload or _signup_payload(email), headers=headers
        )


def _dev_token(email: str) -> str:
    deliveries = [
        delivery
        for delivery in get_dev_email_deliveries(email)
        if delivery.purpose == "email_verification"
    ]
    assert len(deliveries) == 1
    return deliveries[0].token


def _owner_setup_token(email: str) -> str:
    deliveries = [
        delivery for delivery in get_dev_email_deliveries(email) if delivery.purpose == "owner_setup"
    ]
    assert len(deliveries) == 1
    return deliveries[0].token


def _assert_public_response_safe(response, *, email: str, raw_token: str | None = None) -> None:
    body = response.text.lower()
    assert email not in body
    if raw_token is not None:
        assert raw_token not in response.text
    for term in SENSITIVE_RESPONSE_TERMS:
        assert term not in body


def _assert_neutral_failure(response, expected_code: str) -> None:
    assert response.status_code == 400, response.text
    assert response.json()["detail"]["code"] == expected_code
    body = response.text.lower()
    for term in ("registration", "tenant", "hash", "password"):
        assert term not in body


def _assert_hash_only_rows(rows) -> None:
    for row in rows:
        keys = set(row.keys())
        assert "token_hash" in keys
        assert "token" not in keys
        assert "raw_token" not in keys
        assert "token_plaintext" not in keys
        assert row["token_hash"]


async def test_end_to_end_signup_verify_status_happy_path_is_neutral_and_provisions_without_admin():
    email = f"u6f_{uuid.uuid4().hex}@example.com"
    schemas_before = await _tenant_schema_names()
    side_effect_tables_before = await _side_effect_table_inventory()

    async with await _client() as client:
        signup = await client.post("/api/v1/auth/signup", json=_signup_payload(email))

    assert signup.status_code == 202, signup.text
    raw_token = _dev_token(email)
    _assert_public_response_safe(signup, email=email, raw_token=raw_token)

    async with await _client() as client:
        pending = await client.post(
            "/api/v1/auth/onboarding/status", json={"statusToken": raw_token}
        )
        verify = await client.post("/api/v1/auth/verify-email", json={"token": raw_token})
        verified = await client.post(
            "/api/v1/auth/onboarding/status", json={"statusToken": raw_token}
        )

    assert pending.status_code == 200, pending.text
    assert pending.json()["data"] == {"status": "pending_email_verification"}
    assert verify.status_code == 200, verify.text
    assert verified.status_code == 200, verified.text
    assert verified.json()["data"] == {"status": "active"}
    owner_setup_token = _owner_setup_token(email)

    for response in (pending, verify, verified):
        _assert_public_response_safe(response, email=email, raw_token=raw_token)
        _assert_public_response_safe(response, email=email, raw_token=owner_setup_token)

    registration = await _registration_by_email(email)
    assert registration["status"] == "active"
    for response in (signup, pending, verify, verified):
        assert str(registration["id"]).lower() not in response.text.lower()
        assert str(registration["tenant_schema"]).lower() not in response.text.lower()
        assert str(registration["wholesaler_id"]).lower() not in response.text.lower()
    assert registration["tenant_schema"] is not None
    assert registration["wholesaler_id"] is not None
    assert registration["tenant_schema"] in ((await _tenant_schema_names()) - schemas_before)
    assert len(await _setup_token_rows(email)) == 1
    assert await _side_effect_table_inventory() != side_effect_tables_before
    await _assert_current_bootstrap_rbac(registration["tenant_schema"])


async def test_duplicate_email_neutrality_creates_no_second_live_registration_or_status_token():
    local = f"u6f_{uuid.uuid4().hex}"
    email = f"{local}@example.com"
    duplicate = f"{local.upper()}@example.com"

    first = await _signup(email)
    duplicate_response = await _signup(duplicate)

    assert first.status_code == 202, first.text
    assert duplicate_response.status_code == 202, duplicate_response.text
    assert first.json()["data"] == duplicate_response.json()["data"]
    assert first.json()["data"]["registrationId"] is None
    assert duplicate_response.json()["data"]["registrationId"] is None

    rows = await _registration_rows(email)
    live_rows = [row for row in rows if row["status"] in LIVE_STATUSES]
    assert len(rows) == 1
    assert len(live_rows) == 1
    assert len(await _verification_token_rows(email)) == 1
    assert len(await _active_status_token_rows(email)) == 1
    assert len(get_dev_email_deliveries(email)) == 1


async def test_idempotency_retry_and_conflict_do_not_create_duplicate_rows():
    email = f"u6f_{uuid.uuid4().hex}@example.com"
    payload = _signup_payload(email)
    conflict_payload = dict(payload)
    conflict_payload["companyName"] = f"U6F Changed {uuid.uuid4().hex[:8]}"
    headers = {"Idempotency-Key": f"u6f-{uuid.uuid4().hex}"}

    first = await _signup(email, payload=payload, headers=headers)
    retry = await _signup(email, payload=payload, headers=headers)
    conflict = await _signup(email, payload=conflict_payload, headers=headers)

    assert first.status_code == 202, first.text
    assert retry.status_code == 202, retry.text
    assert retry.json()["data"] == first.json()["data"]
    assert conflict.status_code == 409, conflict.text
    assert conflict.json()["detail"]["code"] == "IDEMPOTENCY_CONFLICT"

    rows = await _registration_rows(email)
    assert len(rows) == 1
    assert rows[0]["idempotency_key_hash"] is not None
    assert rows[0]["request_fingerprint_hash"] is not None
    assert len(await _verification_token_rows(email)) == 1
    assert len(await _active_status_token_rows(email)) == 1
    assert len(get_dev_email_deliveries(email)) == 1


async def test_token_transport_and_invalid_missing_expired_reused_fail_neutrally():
    email = f"u6f_{uuid.uuid4().hex}@example.com"
    expired_verify_email = f"u6f_{uuid.uuid4().hex}@example.com"
    expired_status_email = f"u6f_{uuid.uuid4().hex}@example.com"
    await _signup(email)
    await _signup(expired_verify_email)
    await _signup(expired_status_email)
    token = _dev_token(email)
    expired_verify_token = _dev_token(expired_verify_email)
    expired_status_token = _dev_token(expired_status_email)
    await _set_verification_token_expired(expired_verify_email)
    await _set_status_token_expired(expired_status_email)

    async with await _client() as client:
        verify_query = await client.post(f"/api/v1/auth/verify-email?token={token}", json={})
        status_query = await client.post(
            f"/api/v1/auth/onboarding/status?statusToken={token}", json={}
        )
        verify_missing = await client.post("/api/v1/auth/verify-email", json={})
        status_missing = await client.post("/api/v1/auth/onboarding/status", json={})
        verify_invalid = await client.post("/api/v1/auth/verify-email", json={"token": "bad"})
        status_invalid = await client.post(
            "/api/v1/auth/onboarding/status", json={"statusToken": "bad"}
        )
        verify_expired = await client.post(
            "/api/v1/auth/verify-email", json={"token": expired_verify_token}
        )
        status_expired = await client.post(
            "/api/v1/auth/onboarding/status", json={"statusToken": expired_status_token}
        )
        verify_first = await client.post("/api/v1/auth/verify-email", json={"token": token})
        verify_reused = await client.post("/api/v1/auth/verify-email", json={"token": token})

    for response in (verify_query, verify_missing, verify_invalid, verify_expired, verify_reused):
        _assert_neutral_failure(response, "INVALID_OR_EXPIRED_VERIFICATION_TOKEN")
    for response in (status_query, status_missing, status_invalid, status_expired):
        _assert_neutral_failure(response, "INVALID_OR_EXPIRED_ONBOARDING_STATUS_TOKEN")
    assert verify_first.status_code == 200, verify_first.text


async def test_closeout_provisions_tenant_but_defers_admin_rbac_until_setup_credential():
    email = f"u6f_{uuid.uuid4().hex}@example.com"
    schemas_before = await _tenant_schema_names()

    signup = await _signup(email)
    raw_token = _dev_token(email)
    async with await _client() as client:
        verify = await client.post("/api/v1/auth/verify-email", json={"token": raw_token})
        status_response = await client.post(
            "/api/v1/auth/onboarding/status", json={"statusToken": raw_token}
        )

    assert signup.status_code == 202, signup.text
    assert verify.status_code == 200, verify.text
    assert status_response.status_code == 200, status_response.text
    assert status_response.json()["data"] == {"status": "active"}

    registration = await _registration_by_email(email)
    assert registration["status"] == "active"
    assert registration["tenant_schema"] is not None
    assert registration["wholesaler_id"] is not None
    assert registration["tenant_schema"] in ((await _tenant_schema_names()) - schemas_before)
    assert len(await _setup_token_rows(email)) == 1
    await _assert_current_bootstrap_rbac(registration["tenant_schema"])


async def test_route_policy_keeps_current_onboarding_and_recovery_routes_public():
    assert PUBLIC_ALLOWLIST == EXPECTED_PUBLIC_ALLOWLIST

    public_by_path = {c.path: c.policy for c in ALL_CLASSIFICATIONS if c.path in PUBLIC_ALLOWLIST}
    assert public_by_path["/api/v1/auth/signup"] == "public"
    assert public_by_path["/api/v1/auth/verify-email"] == "public"
    assert public_by_path["/api/v1/auth/onboarding/status"] == "public"
    assert public_by_path["/api/v1/auth/onboarding/setup-credential"] == "public"
    assert public_by_path["/api/v1/auth/forgot-password"] == "public"  # pragma: allowlist secret
    assert public_by_path["/api/v1/auth/reset-password"] == "public"  # pragma: allowlist secret
    assert public_by_path["/api/v1/retailers/setup-credential"] == "public"
    assert public_by_path["/api/v1/client/auth/forgot-password"] == "public"  # pragma: allowlist secret
    assert public_by_path["/api/v1/client/auth/reset-password"] == "public"  # pragma: allowlist secret
    assert public_by_path["/api/v1/invitations/lookup"] == "public"
    assert not (PUBLIC_ALLOWLIST - EXPECTED_PUBLIC_ALLOWLIST)


async def test_migration_schema_sanity_uses_current_single_head():
    backend_dir = Path(__file__).resolve().parents[1]
    alembic_cfg = Config(str(backend_dir / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    script = ScriptDirectory.from_config(alembic_cfg)
    assert script.get_heads() == ["036_retailer_mvp_identity"]
    assert script.get_current_head() == "036_retailer_mvp_identity"

    assert TenantRegistration.__tablename__ == "tenant_registrations"
    assert EmailVerificationToken.__tablename__ == "email_verification_tokens"
    assert OnboardingStatusToken.__tablename__ == "onboarding_status_tokens"
    assert {"tenant_registrations", "email_verification_tokens", "onboarding_status_tokens"} == {
        TenantRegistration.__tablename__,
        EmailVerificationToken.__tablename__,
        OnboardingStatusToken.__tablename__,
    }

    assert "token_hash" in {column.name for column in EmailVerificationToken.__table__.columns}
    assert "token_hash" in {column.name for column in OnboardingStatusToken.__table__.columns}
    _assert_hash_only_rows([
        {column.name: "placeholder" for column in EmailVerificationToken.__table__.columns},
        {column.name: "placeholder" for column in OnboardingStatusToken.__table__.columns},
    ])
