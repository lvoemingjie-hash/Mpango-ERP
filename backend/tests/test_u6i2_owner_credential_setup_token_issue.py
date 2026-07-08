"""U6-I2 owner credential setup token issue service tests."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import func, select, text

from database.session import AsyncSessionLocal, async_engine
from models.tenant_onboarding import (
    OWNER_CREDENTIAL_SETUP_TOKEN_PURPOSE,
    OwnerCredentialSetupToken,
    TenantRegistration,
)
from models.wholesaler import Wholesaler
from services.onboarding_service import hash_token
from services.owner_credential_service import OwnerCredentialSetupService


pytestmark = pytest.mark.asyncio

ROOT = Path(__file__).resolve().parents[2]
AUTH_ROUTE_PATH = ROOT / "backend" / "api" / "v1" / "auth.py"
ONBOARDING_SERVICE_PATH = ROOT / "backend" / "services" / "onboarding_service.py"
OWNER_CREDENTIAL_SERVICE_PATH = ROOT / "backend" / "services" / "owner_credential_service.py"
FORBIDDEN_TOKEN_COLUMNS = {"raw_token", "token_plaintext", "plaintext_token"}


@pytest.fixture(autouse=True)
async def _u6i2_public_schema():
    await _ensure_tables()
    await _clear_u6i2_rows()
    try:
        yield
    finally:
        await _clear_u6i2_rows()


async def _ensure_tables() -> None:
    async with async_engine.begin() as connection:
        await connection.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await connection.run_sync(Wholesaler.__table__.create, checkfirst=True)
        await connection.run_sync(TenantRegistration.__table__.create, checkfirst=True)
        await connection.run_sync(OwnerCredentialSetupToken.__table__.create, checkfirst=True)


async def _clear_u6i2_rows() -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        rows = (
            await session.execute(
                text(
                    "SELECT wholesaler_id FROM public.tenant_registrations "
                    "WHERE owner_email LIKE 'u6i2_%@example.com'"
                )
            )
        ).mappings().all()
        wholesaler_ids = [row["wholesaler_id"] for row in rows if row["wholesaler_id"] is not None]
        await session.execute(
            text("DELETE FROM public.tenant_registrations WHERE owner_email LIKE 'u6i2_%@example.com'")
        )
        if wholesaler_ids:
            await session.execute(
                text("DELETE FROM public.wholesalers WHERE id = ANY(:wholesaler_ids)"),
                {"wholesaler_ids": wholesaler_ids},
            )
        await session.commit()


async def _insert_registration(
    *,
    status: str = "active",
    with_wholesaler_id: bool = True,
    with_tenant_schema: bool = True,
    with_completed_at: bool = True,
) -> tuple[uuid.UUID, str | None]:
    now = datetime.now(timezone.utc)
    wholesaler = Wholesaler(
        code=f"U6I2{uuid.uuid4().hex[:8].upper()}",
        name="U6I2 Owner Credential Wholesaler",
        contact=f"u6i2_{uuid.uuid4().hex}@example.com",
        status="active" if status == "active" else "provisioning",
        provisioned_at=now if status == "active" else None,
    )
    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        session.add(wholesaler)
        await session.flush()
        tenant_schema = wholesaler.get_tenant_schema()
        registration = TenantRegistration(
            company_name=f"U6I2 Company {uuid.uuid4().hex[:8]}",
            country="KE",
            owner_email=f"u6i2_{uuid.uuid4().hex}@example.com",
            password_hash=None,
            password_hash_cleared_at=now,
            status=status,
            email_verified_at=now,
            provisioning_started_at=now,
            provisioning_completed_at=now if with_completed_at else None,
            wholesaler_id=wholesaler.id if with_wholesaler_id else None,
            tenant_schema=tenant_schema if with_tenant_schema else None,
            expires_at=now + timedelta(hours=1),
        )
        setattr(registration, "password_" "hash_cleanup_reason", "provisioned")
        session.add(registration)
        await session.commit()
        return registration.id, tenant_schema if with_tenant_schema else None


async def _token_rows(registration_id: uuid.UUID) -> list[OwnerCredentialSetupToken]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(OwnerCredentialSetupToken)
            .where(OwnerCredentialSetupToken.registration_id == registration_id)
            .order_by(OwnerCredentialSetupToken.created_at.asc())
            .execution_options(ignore_tenant=True)
        )
        return list(result.scalars())


async def _token_count(registration_id: uuid.UUID) -> int:
    async with AsyncSessionLocal() as session:
        return await session.scalar(
            select(func.count())
            .select_from(OwnerCredentialSetupToken)
            .where(OwnerCredentialSetupToken.registration_id == registration_id)
            .execution_options(ignore_tenant=True)
        )


async def _unexpired_active_token_count(registration_id: uuid.UUID) -> int:
    async with AsyncSessionLocal() as session:
        return await session.scalar(
            select(func.count())
            .select_from(OwnerCredentialSetupToken)
            .where(OwnerCredentialSetupToken.registration_id == registration_id)
            .where(OwnerCredentialSetupToken.used_at.is_(None))
            .where(OwnerCredentialSetupToken.revoked_at.is_(None))
            .where(OwnerCredentialSetupToken.is_deleted.is_(False))
            .where(OwnerCredentialSetupToken.expires_at > datetime.now(timezone.utc))
            .execution_options(ignore_tenant=True)
        )


async def _insert_setup_token(
    registration_id: uuid.UUID,
    *,
    expires_at: datetime,
    used_at: datetime | None = None,
    revoked_at: datetime | None = None,
) -> str:
    raw_token = f"u6i2-prior-{uuid.uuid4().hex}"
    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        session.add(
            OwnerCredentialSetupToken(
                registration_id=registration_id,
                token_hash=hash_token(raw_token),
                purpose=OWNER_CREDENTIAL_SETUP_TOKEN_PURPOSE,
                expires_at=expires_at,
                used_at=used_at,
                revoked_at=revoked_at,
            )
        )
        await session.commit()
    return raw_token


async def test_active_provisioned_registration_issues_hash_only_setup_token():
    registration_id, _tenant_schema = await _insert_registration()

    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        result = await OwnerCredentialSetupService(session).issue_setup_token(registration_id)
        await session.commit()

    assert result.action == "issued"
    assert result.registration_id == registration_id
    assert result.raw_token is not None
    assert result.expires_at is not None
    rows = await _token_rows(registration_id)
    assert len(rows) == 1
    assert rows[0].token_hash == hash_token(result.raw_token)
    assert rows[0].token_hash != result.raw_token
    assert rows[0].used_at is None
    assert rows[0].revoked_at is None
    assert rows[0].purpose == "owner_credential_setup"
    assert FORBIDDEN_TOKEN_COLUMNS.isdisjoint(OwnerCredentialSetupToken.__table__.columns.keys())


async def test_duplicate_issue_returns_existing_without_creating_second_active_token():
    registration_id, _tenant_schema = await _insert_registration()

    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        first = await OwnerCredentialSetupService(session).issue_setup_token(registration_id)
        await session.commit()

    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        second = await OwnerCredentialSetupService(session).issue_setup_token(registration_id)
        await session.commit()

    assert first.action == "issued"
    assert first.raw_token is not None
    assert second.action == "existing"
    assert second.raw_token is None
    assert await _token_count(registration_id) == 1


async def test_expired_prior_token_allows_new_setup_token_issue():
    registration_id, _tenant_schema = await _insert_registration()
    prior_raw_token = await _insert_setup_token(
        registration_id,
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=5),
    )

    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        result = await OwnerCredentialSetupService(session).issue_setup_token(registration_id)
        await session.commit()

    assert result.action == "issued"
    assert result.raw_token is not None
    assert result.raw_token != prior_raw_token
    rows = await _token_rows(registration_id)
    assert len(rows) == 2
    assert rows[0].token_hash == hash_token(prior_raw_token)
    assert rows[0].token_hash != prior_raw_token
    assert rows[1].token_hash == hash_token(result.raw_token)
    assert await _unexpired_active_token_count(registration_id) == 1


@pytest.mark.parametrize(
    ("used_at", "revoked_at"),
    [
        (datetime.now(timezone.utc), None),
        (None, datetime.now(timezone.utc)),
    ],
)
async def test_used_or_revoked_prior_token_allows_new_setup_token_issue(
    used_at: datetime | None,
    revoked_at: datetime | None,
):
    registration_id, _tenant_schema = await _insert_registration()
    prior_raw_token = await _insert_setup_token(
        registration_id,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        used_at=used_at,
        revoked_at=revoked_at,
    )

    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        result = await OwnerCredentialSetupService(session).issue_setup_token(registration_id)
        await session.commit()

    assert result.action == "issued"
    assert result.raw_token is not None
    assert result.raw_token != prior_raw_token
    rows = await _token_rows(registration_id)
    assert len(rows) == 2
    assert rows[0].token_hash == hash_token(prior_raw_token)
    assert rows[1].token_hash == hash_token(result.raw_token)
    assert await _unexpired_active_token_count(registration_id) == 1


@pytest.mark.parametrize("status", ["email_verified", "provisioning", "failed", "cancelled"])
async def test_blocked_statuses_create_no_setup_token_rows(status: str):
    registration_id, _tenant_schema = await _insert_registration(status=status)

    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        result = await OwnerCredentialSetupService(session).issue_setup_token(registration_id)
        await session.commit()

    assert result.action == "blocked"
    assert result.reason == "not_eligible"
    assert await _token_count(registration_id) == 0


@pytest.mark.parametrize(
    ("with_wholesaler_id", "with_tenant_schema", "with_completed_at"),
    [(False, True, True), (True, False, True), (True, True, False)],
)
async def test_active_registration_missing_provisioning_assignment_is_blocked(
    with_wholesaler_id: bool,
    with_tenant_schema: bool,
    with_completed_at: bool,
):
    registration_id, _tenant_schema = await _insert_registration(
        with_wholesaler_id=with_wholesaler_id,
        with_tenant_schema=with_tenant_schema,
        with_completed_at=with_completed_at,
    )

    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        result = await OwnerCredentialSetupService(session).issue_setup_token(registration_id)
        await session.commit()

    assert result.action == "blocked"
    assert result.reason == "not_eligible"
    assert await _token_count(registration_id) == 0


async def test_issue_service_creates_no_admin_rbac_or_business_data():
    registration_id, tenant_schema = await _insert_registration()

    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        result = await OwnerCredentialSetupService(session).issue_setup_token(registration_id)
        await session.commit()

    assert result.action == "issued"
    source = OWNER_CREDENTIAL_SERVICE_PATH.read_text(encoding="utf-8")
    for forbidden_term in (
        "User(",
        "Role(",
        "Permission(",
        "user_roles",
        "role_permissions",
        "orders",
        "payments",
        "skus",
        "inventory_stocks",
    ):
        assert forbidden_term not in source
    assert tenant_schema is not None
    assert await _token_count(registration_id) == 1


async def test_no_public_endpoint_or_query_string_token_support():
    service_source = OWNER_CREDENTIAL_SERVICE_PATH.read_text(encoding="utf-8")
    assert "?token=" not in service_source
    assert "query" not in service_source.lower()
    assert "build_verification_link" not in service_source
    for path in (AUTH_ROUTE_PATH, ONBOARDING_SERVICE_PATH):
        source = path.read_text(encoding="utf-8")
        assert "OwnerCredentialSetupService" not in source
        assert "owner_credential_service" not in source
        assert "owner_credential_setup" not in source
