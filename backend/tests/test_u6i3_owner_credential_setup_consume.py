"""U6-I3 owner credential setup token consume service tests."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import func, select, text

from core.security import verify_password
from database.session import AsyncSessionLocal, async_engine
from models.tenant_onboarding import (
    OWNER_CREDENTIAL_SETUP_TOKEN_PURPOSE,
    OwnerCredentialSetupToken,
    TenantRegistration,
)
from models.wholesaler import Wholesaler
from services.onboarding_service import hash_token
from services.owner_credential_service import (
    INVALID_OR_EXPIRED_OWNER_CREDENTIAL_SETUP_TOKEN,
    OwnerCredentialSetupService,
    OwnerCredentialSetupTokenInvalidError,
)


pytestmark = pytest.mark.asyncio

ROOT = Path(__file__).resolve().parents[2]
AUTH_ROUTE_PATH = ROOT / "backend" / "api" / "v1" / "auth.py"
OWNER_CREDENTIAL_SERVICE_PATH = ROOT / "backend" / "services" / "owner_credential_service.py"
FORBIDDEN_TOKEN_COLUMNS = {"raw_token", "token_plaintext", "plaintext_token"}
TENANT_AUTH_TABLES = ("users", "roles", "permissions", "user_roles", "role_permissions")


@pytest.fixture(autouse=True)
async def _u6i3_public_schema():
    await _ensure_tables()
    await _clear_u6i3_rows()
    try:
        yield
    finally:
        await _clear_u6i3_rows()


async def _ensure_tables() -> None:
    async with async_engine.begin() as connection:
        await connection.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await connection.run_sync(Wholesaler.__table__.create, checkfirst=True)
        await connection.run_sync(TenantRegistration.__table__.create, checkfirst=True)
        await connection.run_sync(OwnerCredentialSetupToken.__table__.create, checkfirst=True)


async def _clear_u6i3_rows() -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        rows = (
            await session.execute(
                text(
                    "SELECT wholesaler_id FROM public.tenant_registrations "
                    "WHERE owner_email LIKE 'u6i3_%@example.com'"
                )
            )
        ).mappings().all()
        wholesaler_ids = [row["wholesaler_id"] for row in rows if row["wholesaler_id"] is not None]
        await session.execute(
            text("DELETE FROM public.tenant_registrations WHERE owner_email LIKE 'u6i3_%@example.com'")
        )
        if wholesaler_ids:
            await session.execute(
                text("DELETE FROM public.wholesalers WHERE id = ANY(:wholesaler_ids)"),
                {"wholesaler_ids": wholesaler_ids},
            )
        await session.commit()


async def _insert_registration() -> tuple[uuid.UUID, str, str]:
    now = datetime.now(timezone.utc)
    owner_email = f"u6i3_{uuid.uuid4().hex}@example.com"
    wholesaler = Wholesaler(
        code=f"U6I3{uuid.uuid4().hex[:8].upper()}",
        name="U6I3 Owner Credential Wholesaler",
        contact=owner_email,
        status="active",
        provisioned_at=now,
    )
    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        session.add(wholesaler)
        await session.flush()
        tenant_schema = wholesaler.get_tenant_schema()
        registration = TenantRegistration(
            company_name=f"U6I3 Company {uuid.uuid4().hex[:8]}",
            country="KE",
            owner_email=owner_email,
            password_hash=None,
            password_hash_cleared_at=now,
            status="active",
            email_verified_at=now,
            provisioning_started_at=now,
            provisioning_completed_at=now,
            wholesaler_id=wholesaler.id,
            tenant_schema=tenant_schema,
            expires_at=now + timedelta(hours=1),
        )
        setattr(registration, "password_" "hash_cleanup_reason", "provisioned")
        session.add(registration)
        await session.commit()
        return registration.id, tenant_schema, owner_email


async def _insert_setup_token(
    registration_id: uuid.UUID,
    raw_token: str,
    *,
    purpose: str = OWNER_CREDENTIAL_SETUP_TOKEN_PURPOSE,
    expires_at: datetime | None = None,
    used_at: datetime | None = None,
    revoked_at: datetime | None = None,
    is_deleted: bool = False,
) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        session.add(
            OwnerCredentialSetupToken(
                registration_id=registration_id,
                token_hash=hash_token(raw_token),
                purpose=purpose,
                expires_at=expires_at or datetime.now(timezone.utc) + timedelta(hours=1),
                used_at=used_at,
                revoked_at=revoked_at,
                is_deleted=is_deleted,
            )
        )
        await session.commit()


async def _token_row(raw_token: str) -> OwnerCredentialSetupToken | None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(OwnerCredentialSetupToken)
            .where(OwnerCredentialSetupToken.token_hash == hash_token(raw_token))
            .execution_options(ignore_tenant=True)
        )
        return result.scalar_one_or_none()


async def _registration_row(registration_id: uuid.UUID) -> TenantRegistration:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(TenantRegistration)
            .where(TenantRegistration.id == registration_id)
            .execution_options(ignore_tenant=True)
        )
        return result.scalar_one()


async def _setup_token_count(registration_id: uuid.UUID) -> int:
    async with AsyncSessionLocal() as session:
        return await session.scalar(
            select(func.count())
            .select_from(OwnerCredentialSetupToken)
            .where(OwnerCredentialSetupToken.registration_id == registration_id)
            .execution_options(ignore_tenant=True)
        )


async def _tenant_auth_tables_absent_or_empty(tenant_schema: str) -> bool:
    async with AsyncSessionLocal() as session:
        for table_name in TENANT_AUTH_TABLES:
            qualified_name = f"{tenant_schema}.{table_name}"
            exists = await session.scalar(text("SELECT to_regclass(:qualified_name)"), {"qualified_name": qualified_name})
            if exists is not None:
                count = await session.scalar(
                    text(f'SELECT count(*) FROM "{tenant_schema}"."{table_name}"')
                )
                if count != 0:
                    return False
        return True


async def _drop_owner_setup_purpose_constraint() -> None:
    async with async_engine.begin() as connection:
        await connection.execute(
            text(
                "ALTER TABLE public.owner_credential_setup_tokens "
                "DROP CONSTRAINT IF EXISTS ck_owner_credential_setup_tokens_purpose"
            )
        )


async def _restore_owner_setup_purpose_constraint() -> None:
    async with async_engine.begin() as connection:
        await connection.execute(
            text(
                "DO $$ BEGIN "
                "IF NOT EXISTS ("
                "SELECT 1 FROM pg_constraint WHERE conname = 'ck_owner_credential_setup_tokens_purpose'"
                ") THEN "
                "ALTER TABLE public.owner_credential_setup_tokens "
                "ADD CONSTRAINT ck_owner_credential_setup_tokens_purpose "
                "CHECK (purpose = 'owner_credential_setup'); "
                "END IF; END $$"
            )
        )


async def _assert_neutral_failure(raw_token: str | None, password: str = "OwnerSetup123!") -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        with pytest.raises(OwnerCredentialSetupTokenInvalidError) as exc_info:
            await OwnerCredentialSetupService(session).consume_setup_token(raw_token, password)
        await session.rollback()
    assert str(exc_info.value) == INVALID_OR_EXPIRED_OWNER_CREDENTIAL_SETUP_TOKEN


async def test_consume_valid_owner_setup_token_returns_admin_creation_inputs_without_persisting_password():
    registration_id, tenant_schema, owner_email = await _insert_registration()
    raw_token = f"u6i3-valid-{uuid.uuid4().hex}"
    credential_value = "OwnerSetup123!"
    await _insert_setup_token(registration_id, raw_token)

    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        result = await OwnerCredentialSetupService(session).consume_setup_token(raw_token, credential_value)
        await session.commit()

    assert result.registration_id == registration_id
    assert result.tenant_schema == tenant_schema
    assert result.owner_email == owner_email
    assert verify_password(credential_value, result.password_hash)
    assert credential_value not in result.password_hash
    token = await _token_row(raw_token)
    assert token is not None
    assert token.used_at is not None
    assert token.token_hash == hash_token(raw_token)
    assert token.token_hash != raw_token
    registration = await _registration_row(registration_id)
    assert registration.password_hash is None
    assert FORBIDDEN_TOKEN_COLUMNS.isdisjoint(OwnerCredentialSetupToken.__table__.columns.keys())
    assert await _tenant_auth_tables_absent_or_empty(tenant_schema)


@pytest.mark.parametrize(
    "raw_token",
    # Stable literal: a random uuid4 here made the parametrized node ID
    # volatile per collection, which breaks frozen manifest binding.
    [None, "", "   ", "u6i3-missing-0f1e2d3c4b5a69788796a5b4c3d2e1f0"],
)
async def test_invalid_or_missing_raw_token_fails_neutrally(raw_token: str | None):
    await _assert_neutral_failure(raw_token)


@pytest.mark.parametrize(
    "token_state",
    ["expired", "revoked", "used", "deleted"],
)
async def test_non_actionable_token_states_fail_neutrally(token_state: str):
    registration_id, _tenant_schema, _owner_email = await _insert_registration()
    raw_token = f"u6i3-{token_state}-{uuid.uuid4().hex}"
    now = datetime.now(timezone.utc)
    await _insert_setup_token(
        registration_id,
        raw_token,
        expires_at=now - timedelta(minutes=1) if token_state == "expired" else now + timedelta(hours=1),
        used_at=now if token_state == "used" else None,
        revoked_at=now if token_state == "revoked" else None,
        is_deleted=token_state == "deleted",
    )

    await _assert_neutral_failure(raw_token)
    assert await _setup_token_count(registration_id) == 1


async def test_wrong_purpose_token_fails_neutrally():
    registration_id, _tenant_schema, _owner_email = await _insert_registration()
    raw_token = f"u6i3-wrong-purpose-{uuid.uuid4().hex}"
    await _drop_owner_setup_purpose_constraint()
    try:
        await _insert_setup_token(
            registration_id,
            raw_token,
            purpose="not_owner_credential_setup",
        )
        await _assert_neutral_failure(raw_token)
        async with AsyncSessionLocal() as session:
            await session.execute(
                text("DELETE FROM public.owner_credential_setup_tokens WHERE token_hash = :token_hash"),
                {"token_hash": hash_token(raw_token)},
            )
            await session.commit()
    finally:
        await _restore_owner_setup_purpose_constraint()


async def test_consuming_used_token_twice_fails_neutrally_after_first_success():
    registration_id, _tenant_schema, _owner_email = await _insert_registration()
    raw_token = f"u6i3-once-{uuid.uuid4().hex}"
    await _insert_setup_token(registration_id, raw_token)

    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        result = await OwnerCredentialSetupService(session).consume_setup_token(
            raw_token,
            "OwnerSetup123!",
        )
        await session.commit()

    assert result.registration_id == registration_id
    await _assert_neutral_failure(raw_token, "OwnerSetup456!")
    assert await _setup_token_count(registration_id) == 1


async def test_consume_service_has_no_endpoint_query_string_or_admin_creation_boundary():
    service_source = OWNER_CREDENTIAL_SERVICE_PATH.read_text(encoding="utf-8")
    assert "?token=" not in service_source
    assert "query" not in service_source.lower()
    for forbidden_term in (
        "User(",
        "Role(",
        "Permission(",
        "user_roles",
        "role_permissions",
        "registration.password_hash",
        "TenantRegistration.password_hash",
    ):
        assert forbidden_term not in service_source
