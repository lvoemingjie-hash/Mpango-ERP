"""U6-I6 end-to-end backend closeout gate for owner onboarding."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import select, text

from api.app import app
from api.dependencies import get_db_session
from core.config import get_settings
from core.permission_registry import (
    RETAILER_OPERATOR_PERMISSION_CODES,
    RETAILER_OPERATOR_ROLE,
)
from core.security import verify_password
from database.session import AsyncSessionLocal, async_engine
from models.tenant_onboarding import (
    EmailVerificationToken,
    OnboardingStatusToken,
    OwnerCredentialSetupToken,
    TenantRegistration,
)
from models.wholesaler import Wholesaler
from services.email_delivery import clear_dev_email_deliveries, get_dev_email_deliveries
from services.onboarding_service import hash_token
from services.owner_credential_service import (
    OWNER_ADMIN_PERMISSION_REGISTRY,
    OwnerCredentialSetupService,
)
from services.tenant_provisioning_service import TenantProvisioningService


pytestmark = pytest.mark.asyncio

SIGNUP_URL = "/api/v1/auth/signup"
VERIFY_EMAIL_URL = "/api/v1/auth/verify-email"
ONBOARDING_STATUS_URL = "/api/v1/auth/onboarding/status"
SETUP_CREDENTIAL_URL = "/api/v1/auth/onboarding/setup-credential"
SIGNUP_PASSWORD = "U6I6SignupCred_01!"  # pragma: allowlist secret
OWNER_PASSWORD = "U6I6OwnerCred_01!"  # pragma: allowlist secret
REPLAY_PASSWORD = "U6I6ReplayCred_01!"  # pragma: allowlist secret
QUERY_PASSWORD = "U6I6QueryCred_01!"  # pragma: allowlist secret
CANONICAL_ADMIN_PERMISSION_CODES = {code for code, _description in OWNER_ADMIN_PERMISSION_REGISTRY}
CANONICAL_TENANT_PERMISSION_CODES = CANONICAL_ADMIN_PERMISSION_CODES | set(
    RETAILER_OPERATOR_PERMISSION_CODES
)
FORBIDDEN_TOKEN_COLUMNS = {"raw_token", "token_plaintext", "plaintext_token"}
FORBIDDEN_PUBLIC_FIELD_NAMES = (
    "token_hash",
    "password_hash",
    "tenant_schema",
    "user_id",
    "role_id",
    "permission_id",
    "permission_ids",
)


@pytest.fixture(autouse=True)
async def _u6i6_backend_gate():
    await _ensure_tables()
    await _clear_u6i6_rows_and_schemas()
    clear_dev_email_deliveries()
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        await _clear_u6i6_rows_and_schemas()
        clear_dev_email_deliveries()


async def _ensure_tables() -> None:
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


async def _clear_u6i6_rows_and_schemas() -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        rows = (
            await session.execute(
                text(
                    "SELECT wholesaler_id, tenant_schema FROM public.tenant_registrations "
                    "WHERE owner_email LIKE 'u6i6_%@example.com'"
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
                "WHERE owner_email LIKE 'u6i6_%@example.com')"
            )
        )
        await session.execute(
            text("DELETE FROM public.tenant_registrations WHERE owner_email LIKE 'u6i6_%@example.com'")
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
        "companyName": f"U6I6 Company {uuid.uuid4().hex[:8]}",
        "country": "KE",
        "email": email,
        "phone": "+254700000000",
        "businessType": "wholesale",
        "password": SIGNUP_PASSWORD,
    }


def _dev_token(email: str) -> str:
    deliveries = get_dev_email_deliveries(email)
    assert len(deliveries) == 1
    return deliveries[0].token


def _dev_setup_token(email: str) -> str:
    deliveries = [
        delivery
        for delivery in get_dev_email_deliveries(email)
        if delivery.purpose == "owner_setup"
    ]
    assert len(deliveries) == 1
    return deliveries[0].token


async def _registration_row(email: str):
    async with AsyncSessionLocal() as session:
        return (
            await session.execute(
                text(
                    "SELECT id, company_name, owner_email, password_hash, status, "
                    "email_verified_at, provisioning_started_at, provisioning_completed_at, "
                    "password_hash_cleared_at, password_hash_cleanup_reason, "
                    "wholesaler_id, tenant_schema FROM public.tenant_registrations "
                    "WHERE owner_email = :email"
                ),
                {"email": email},
            )
        ).mappings().one()


async def _verification_token_rows(registration_id: uuid.UUID):
    async with AsyncSessionLocal() as session:
        return (
            await session.execute(
                select(EmailVerificationToken)
                .where(EmailVerificationToken.registration_id == registration_id)
                .order_by(EmailVerificationToken.created_at.asc())
                .execution_options(ignore_tenant=True)
            )
        ).scalars().all()


async def _setup_token_rows(registration_id: uuid.UUID):
    async with AsyncSessionLocal() as session:
        return (
            await session.execute(
                select(OwnerCredentialSetupToken)
                .where(OwnerCredentialSetupToken.registration_id == registration_id)
                .order_by(OwnerCredentialSetupToken.created_at.asc())
                .execution_options(ignore_tenant=True)
            )
        ).scalars().all()


async def _wholesaler_row(wholesaler_id: uuid.UUID):
    async with AsyncSessionLocal() as session:
        return (
            await session.execute(
                text(
                    "SELECT id, code, name, contact, status, provisioned_at "
                    "FROM public.wholesalers WHERE id = :wholesaler_id"
                ),
                {"wholesaler_id": wholesaler_id},
            )
        ).mappings().one()


async def _table_count(schema: str, table: str) -> int:
    async with AsyncSessionLocal() as session:
        return int(await session.scalar(text(f'SELECT count(*) FROM "{schema}"."{table}"')))


async def _tenant_tables(schema: str) -> set[str]:
    async with AsyncSessionLocal() as session:
        return set(
            (
                await session.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = :schema"
                    ),
                    {"schema": schema},
                )
            ).scalars()
        )


async def _owner_admin_row(schema: str, owner_email: str):
    async with AsyncSessionLocal() as session:
        return (
            await session.execute(
                text(
                    f'SELECT u.id AS user_id, u.email, u.password_hash, u.is_active, '
                    f'r.id AS role_id, r.name AS role_name, r.is_deleted AS role_deleted '
                    f'FROM "{schema}".users u '
                    f'JOIN "{schema}".user_roles ur ON ur.user_id = u.id '
                    f'JOIN "{schema}".roles r ON r.id = ur.role_id '
                    "WHERE u.email = :email AND r.name = 'admin'"
                ),
                {"email": owner_email},
            )
        ).mappings().one()


async def _admin_permission_rows(schema: str):
    async with AsyncSessionLocal() as session:
        return (
            await session.execute(
                text(
                    f'SELECT p.id, p.code FROM "{schema}".permissions p '
                    f'JOIN "{schema}".role_permissions rp ON rp.permission_id = p.id '
                    f'JOIN "{schema}".roles r ON r.id = rp.role_id '
                    "WHERE r.name = 'admin' ORDER BY p.code"
                )
            )
        ).mappings().all()


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


async def _setup_response(
    setup_token: str,
    password: str,
    *,
    query: str = "",
) -> Response:
    async with await _client() as client:
        return await client.post(
            SETUP_CREDENTIAL_URL + query,
            json={"setup_token": setup_token, "password": password},
        )


def _assert_public_response_safe(
    response: Response,
    *,
    raw_values: tuple[str | None, ...] = (),
    identifiers: tuple[Any, ...] = (),
) -> None:
    body = response.text
    body_lower = body.lower()
    for raw_value in raw_values:
        if raw_value:
            assert raw_value not in body
    for field_name in FORBIDDEN_PUBLIC_FIELD_NAMES:
        assert field_name not in body_lower
    for identifier in identifiers:
        if identifier is not None:
            assert str(identifier).lower() not in body_lower


async def test_full_owner_onboarding_backend_chain_proves_hash_only_tokens_and_admin_rbac():
    email = f"u6i6_{uuid.uuid4().hex}@example.com"
    public_responses: list[Response] = []

    async with await _client() as client:
        signup = await client.post(SIGNUP_URL, json=_signup_payload(email))
    public_responses.append(signup)

    assert signup.status_code == 202, signup.text
    assert signup.json()["data"]["registrationId"] is None
    assert signup.json()["data"]["status"] == "pending_email_verification"
    raw_status_and_verify_token = _dev_token(email)
    _assert_public_response_safe(
        signup,
        raw_values=(raw_status_and_verify_token, SIGNUP_PASSWORD),
    )

    pending = await _registration_row(email)
    registration_id = pending["id"]
    assert pending["status"] == "pending_email_verification"
    assert pending["owner_email"] == email
    assert pending["password_hash"] is not None
    assert pending["password_hash"] != SIGNUP_PASSWORD
    assert pending["tenant_schema"] is None
    assert pending["wholesaler_id"] is None

    verification_tokens = await _verification_token_rows(registration_id)
    assert len(verification_tokens) == 1
    assert verification_tokens[0].token_hash == hash_token(raw_status_and_verify_token)
    assert verification_tokens[0].token_hash != raw_status_and_verify_token
    assert verification_tokens[0].used_at is None
    assert FORBIDDEN_TOKEN_COLUMNS.isdisjoint(EmailVerificationToken.__table__.columns.keys())
    assert FORBIDDEN_TOKEN_COLUMNS.isdisjoint(OnboardingStatusToken.__table__.columns.keys())
    assert await _setup_token_rows(registration_id) == []

    async with await _client() as client:
        verify = await client.post(VERIFY_EMAIL_URL, json={"token": raw_status_and_verify_token})
        status_after_verify = await client.post(
            ONBOARDING_STATUS_URL,
            json={"statusToken": raw_status_and_verify_token},
        )
    public_responses.extend([verify, status_after_verify])

    assert verify.status_code == 200, verify.text
    active = await _registration_row(email)
    assert active["status"] == "active"
    assert active["email_verified_at"] is not None
    used_verification_token = (await _verification_token_rows(registration_id))[0]
    assert used_verification_token.used_at is not None
    assert status_after_verify.status_code == 200, status_after_verify.text
    assert status_after_verify.json()["data"] == {"status": "active"}

    tenant_schema = active["tenant_schema"]
    wholesaler_id = active["wholesaler_id"]
    assert active["provisioning_started_at"] is not None
    assert active["provisioning_completed_at"] is not None
    assert active["password_hash"] is None
    assert active["password_hash_cleared_at"] is not None
    assert active["password_hash_cleanup_reason"] == "provisioned"  # pragma: allowlist secret
    wholesaler = await _wholesaler_row(wholesaler_id)
    assert wholesaler["status"] == "active"
    assert wholesaler["provisioned_at"] is not None
    assert wholesaler["contact"] == email
    assert tenant_schema == f"t_{str(wholesaler_id).replace('-', '')}"
    assert {"users", "roles", "permissions", "user_roles", "role_permissions"} <= await _tenant_tables(tenant_schema)

    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        existing = await TenantProvisioningService(
            session,
            database_url=get_settings().DATABASE_URL,
        ).provision_wholesaler_and_schema(registration_id)
        await session.commit()
    assert existing.action == "existing"
    assert existing.tenant_schema == tenant_schema
    assert existing.wholesaler_id == wholesaler_id

    setup_token = _dev_setup_token(email)
    setup_tokens = await _setup_token_rows(registration_id)
    assert len(setup_tokens) == 1
    assert setup_tokens[0].token_hash == hash_token(setup_token)
    assert setup_tokens[0].token_hash != setup_token
    assert setup_tokens[0].used_at is None
    assert FORBIDDEN_TOKEN_COLUMNS.isdisjoint(OwnerCredentialSetupToken.__table__.columns.keys())

    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        duplicate_issue = await OwnerCredentialSetupService(session).issue_setup_token(registration_id)
        await session.commit()
    assert duplicate_issue.action == "existing"
    assert duplicate_issue.raw_token is None
    assert len(await _setup_token_rows(registration_id)) == 1

    setup_response = await _setup_response(setup_token, OWNER_PASSWORD)
    public_responses.append(setup_response)
    assert setup_response.status_code == 200, setup_response.text
    assert setup_response.json()["data"] == {}

    owner_admin = await _owner_admin_row(tenant_schema, email)
    admin_permissions = await _admin_permission_rows(tenant_schema)
    permission_ids = tuple(row["id"] for row in admin_permissions)
    assert owner_admin["email"] == email
    assert owner_admin["is_active"] is True
    assert owner_admin["role_name"] == "admin"
    assert owner_admin["role_deleted"] is False
    assert verify_password(OWNER_PASSWORD, owner_admin["password_hash"])
    assert OWNER_PASSWORD not in owner_admin["password_hash"]
    assert {row["code"] for row in admin_permissions} == CANONICAL_ADMIN_PERMISSION_CODES
    assert not {row["code"] for row in admin_permissions if row["code"].startswith("client:")}
    assert await _role_permission_codes(tenant_schema, RETAILER_OPERATOR_ROLE) == set(
        RETAILER_OPERATOR_PERMISSION_CODES
    )
    assert await _table_count(tenant_schema, "users") == 1
    assert await _table_count(tenant_schema, "roles") == 2
    assert await _table_count(tenant_schema, "permissions") == len(CANONICAL_TENANT_PERMISSION_CODES)
    assert await _table_count(tenant_schema, "user_roles") == 1
    assert await _table_count(tenant_schema, "role_permissions") == (
        len(CANONICAL_ADMIN_PERMISSION_CODES) + len(RETAILER_OPERATOR_PERMISSION_CODES)
    )

    password_hash_after_setup = owner_admin["password_hash"]
    replay = await _setup_response(setup_token, REPLAY_PASSWORD)
    public_responses.append(replay)
    assert replay.status_code == 401, replay.text
    owner_after_replay = await _owner_admin_row(tenant_schema, email)
    assert owner_after_replay["password_hash"] == password_hash_after_setup
    assert not verify_password(REPLAY_PASSWORD, owner_after_replay["password_hash"])

    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        query_path_issue = await OwnerCredentialSetupService(session).issue_setup_token(registration_id)
        await session.commit()
    assert query_path_issue.action == "issued"
    assert query_path_issue.raw_token is not None
    query_path_token = query_path_issue.raw_token

    async with await _client() as client:
        get_query = await client.get(
            SETUP_CREDENTIAL_URL + f"?setup_token={query_path_token}&password={QUERY_PASSWORD}"
        )
    public_responses.append(get_query)
    assert get_query.status_code == 405

    post_query = await _setup_response(
        query_path_token,
        QUERY_PASSWORD,
        query=f"?setup_token={query_path_token}",
    )
    public_responses.append(post_query)
    assert post_query.status_code == 401, post_query.text
    query_path_hash = hash_token(query_path_token)
    query_path_row = next(
        row
        for row in await _setup_token_rows(registration_id)
        if row.token_hash == query_path_hash
    )
    assert query_path_row.token_hash == query_path_hash
    assert query_path_row.used_at is None
    assert (await _owner_admin_row(tenant_schema, email))["password_hash"] == password_hash_after_setup

    identifiers = (
        registration_id,
        wholesaler_id,
        tenant_schema,
        owner_admin["user_id"],
        owner_admin["role_id"],
        *permission_ids,
    )
    raw_values = (
        raw_status_and_verify_token,
        setup_token,
        query_path_token,
        SIGNUP_PASSWORD,
        OWNER_PASSWORD,
        REPLAY_PASSWORD,
        QUERY_PASSWORD,
        setup_tokens[0].token_hash,
        query_path_row.token_hash,
        password_hash_after_setup,
    )
    for response in public_responses:
        _assert_public_response_safe(response, raw_values=raw_values, identifiers=identifiers)
