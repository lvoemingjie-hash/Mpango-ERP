"""U6-H1 tenant provisioning service skeleton tests."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import func, select, text

from database.session import AsyncSessionLocal, async_engine
from models.tenant_onboarding import TenantRegistration
from models.wholesaler import Wholesaler
from services.tenant_provisioning_service import TenantProvisioningService


pytestmark = pytest.mark.asyncio

ROOT = Path(__file__).resolve().parents[2]
AUTH_ROUTE_PATH = ROOT / "backend" / "api" / "v1" / "auth.py"
ONBOARDING_SERVICE_PATH = ROOT / "backend" / "services" / "onboarding_service.py"
PROVISIONING_SERVICE_PATH = ROOT / "backend" / "services" / "tenant_provisioning_service.py"
SENSITIVE_PLACEHOLDER = "hashed-registration-password"  # pragma: allowlist secret
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
async def _u6h1_public_schema():
    await _ensure_tables()
    await _clear_u6h1_rows()
    try:
        yield
    finally:
        await _clear_u6h1_rows()


async def _ensure_tables() -> None:
    async with async_engine.begin() as connection:
        await connection.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await connection.run_sync(Wholesaler.__table__.create, checkfirst=True)
        await connection.run_sync(TenantRegistration.__table__.create, checkfirst=True)


async def _clear_u6h1_rows() -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        await session.execute(
            text("DELETE FROM public.tenant_registrations WHERE owner_email LIKE 'u6h1_%@example.com'")
        )
        await session.execute(text("DELETE FROM public.wholesalers WHERE code LIKE 'U6H1%SKELETON'"))
        await session.commit()


async def _insert_registration(
    *,
    status: str,
    owner_email: str | None = None,
    wholesaler_id: uuid.UUID | None = None,
    tenant_schema: str | None = None,
    provisioning_completed_at: datetime | None = None,
    retry_allowed_until: datetime | None = None,
) -> uuid.UUID:
    now = datetime.now(timezone.utc)
    terminal = status in {"active", "cancelled", "expired"}
    failed_without_retry = status == "failed" and retry_allowed_until is None
    registration = TenantRegistration(
        company_name=f"U6H1 Company {uuid.uuid4().hex[:8]}",
        country="KE",
        owner_email=owner_email or f"u6h1_{uuid.uuid4().hex}@example.com",
        password_hash=None if terminal or failed_without_retry else SENSITIVE_PLACEHOLDER,
        password_hash_cleared_at=now if terminal or failed_without_retry else None,
        password_hash_cleanup_reason="test_cleanup" if terminal or failed_without_retry else None,  # pragma: allowlist secret
        status=status,
        email_verified_at=now if status in {"email_verified", "provisioning", "active"} else None,
        provisioning_completed_at=provisioning_completed_at,
        failed_at=now if status == "failed" else None,
        retry_allowed_until=retry_allowed_until,
        wholesaler_id=wholesaler_id,
        tenant_schema=tenant_schema,
        expires_at=now + timedelta(hours=1),
    )
    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        session.add(registration)
        await session.commit()
        return registration.id


async def _insert_wholesaler() -> Wholesaler:
    wholesaler = Wholesaler(
        code=f"U6H1{uuid.uuid4().hex[:8].upper()}SKELETON",
        name="U6H1 Existing Wholesaler",
        status="active",
        provisioned_at=datetime.now(timezone.utc),
    )
    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        session.add(wholesaler)
        await session.commit()
        return wholesaler


async def _registration_snapshot(registration_id: uuid.UUID) -> dict[str, object]:
    async with AsyncSessionLocal() as session:
        row = (
            await session.execute(
                select(
                    TenantRegistration.status,
                    TenantRegistration.provisioning_started_at,
                    TenantRegistration.provisioning_completed_at,
                    TenantRegistration.wholesaler_id,
                    TenantRegistration.tenant_schema,
                    TenantRegistration.failed_at,
                    TenantRegistration.failure_code,
                    TenantRegistration.failure_message,
                    TenantRegistration.retry_allowed_until,
                )
                .where(TenantRegistration.id == registration_id)
                .execution_options(ignore_tenant=True)
            )
        ).mappings().one()
        return dict(row)


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


async def _wholesaler_count() -> int:
    async with AsyncSessionLocal() as session:
        return await session.scalar(
            select(func.count()).select_from(Wholesaler).execution_options(ignore_tenant=True)
        )


async def test_email_verified_registration_can_be_claimed_and_becomes_provisioning():
    registration_id = await _insert_registration(status="email_verified")

    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        result = await TenantProvisioningService(session).claim_registration_for_provisioning(
            registration_id
        )
        await session.commit()

    assert result.action == "claimed"
    assert result.registration_id == registration_id
    assert result.status == "provisioning"
    assert result.provisioning_started_at is not None
    assert result.wholesaler_id is None
    assert result.tenant_schema is None
    assert result.provisioning_completed_at is None

    snapshot = await _registration_snapshot(registration_id)
    assert snapshot["status"] == "provisioning"
    assert snapshot["provisioning_started_at"] is not None
    assert snapshot["wholesaler_id"] is None
    assert snapshot["tenant_schema"] is None
    assert snapshot["provisioning_completed_at"] is None


@pytest.mark.parametrize(
    "status",
    ["pending_email_verification", "expired", "cancelled", "failed"],
)
async def test_blocked_statuses_do_not_mutate(status: str):
    registration_id = await _insert_registration(status=status)
    before = await _registration_snapshot(registration_id)

    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        result = await TenantProvisioningService(session).claim_registration_for_provisioning(
            registration_id
        )
        await session.commit()

    assert result.action == "blocked"
    assert result.status == status
    assert await _registration_snapshot(registration_id) == before


async def test_active_registration_with_assignment_returns_idempotent_existing_result():
    wholesaler = await _insert_wholesaler()
    tenant_schema = wholesaler.get_tenant_schema()
    completed_at = datetime.now(timezone.utc)
    registration_id = await _insert_registration(
        status="active",
        wholesaler_id=wholesaler.id,
        tenant_schema=tenant_schema,
        provisioning_completed_at=completed_at,
    )
    before = await _registration_snapshot(registration_id)

    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        result = await TenantProvisioningService(session).claim_registration_for_provisioning(
            registration_id
        )
        await session.commit()

    assert result.action == "existing"
    assert result.status == "active"
    assert result.wholesaler_id == wholesaler.id
    assert result.tenant_schema == tenant_schema
    assert result.provisioning_completed_at == completed_at
    assert await _registration_snapshot(registration_id) == before


async def test_rollback_leaves_claimed_registration_state_unchanged():
    registration_id = await _insert_registration(status="email_verified")

    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        result = await TenantProvisioningService(session).claim_registration_for_provisioning(
            registration_id
        )
        assert result.action == "claimed"
        assert result.status == "provisioning"
        await session.rollback()

    snapshot = await _registration_snapshot(registration_id)
    assert snapshot["status"] == "email_verified"
    assert snapshot["provisioning_started_at"] is None
    assert snapshot["wholesaler_id"] is None
    assert snapshot["tenant_schema"] is None


async def test_public_auth_routes_do_not_call_tenant_provisioning():
    for path in (AUTH_ROUTE_PATH, ONBOARDING_SERVICE_PATH):
        source = path.read_text(encoding="utf-8")
        assert "TenantProvisioningService" not in source
        assert "tenant_provisioning_service" not in source
        assert "claim_registration_for_provisioning" not in source


async def test_claim_has_no_schema_user_role_rbac_or_wholesaler_side_effects():
    registration_id = await _insert_registration(status="email_verified")
    schemas_before = await _tenant_schema_names()
    side_effect_tables_before = await _side_effect_table_inventory()
    wholesaler_count_before = await _wholesaler_count()

    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        result = await TenantProvisioningService(session).claim_registration_for_provisioning(
            registration_id
        )
        await session.commit()

    assert result.action == "claimed"
    assert await _tenant_schema_names() == schemas_before
    assert await _side_effect_table_inventory() == side_effect_tables_before
    assert await _wholesaler_count() == wholesaler_count_before

    source = PROVISIONING_SERVICE_PATH.read_text(encoding="utf-8")
    forbidden_terms = (
        "Wholesaler(",
        "bootstrap_tenant_schema",
        "CREATE SCHEMA",
        "User(",
        "Role(",
        "Permission(",
        "user_roles",
        "role_permissions",
    )
    for term in forbidden_terms:
        assert term not in source


async def test_service_uses_row_level_lock_and_does_not_log_sensitive_material():
    source = PROVISIONING_SERVICE_PATH.read_text(encoding="utf-8")

    assert ".with_for_update()" in source
    assert "ignore_tenant=True" in source
    assert "logging" not in source
    assert "logger" not in source
    for sensitive_term in ("token", "raw_password", "password_hash", "SECRET_KEY"):
        assert sensitive_term not in source
