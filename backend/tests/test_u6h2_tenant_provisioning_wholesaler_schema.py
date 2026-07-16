"""U6-H2 tenant provisioning wholesaler and schema bootstrap tests."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import func, select, text

from core.config import get_settings
from database.session import AsyncSessionLocal, async_engine
from models.tenant_onboarding import TenantRegistration
from models.wholesaler import Wholesaler
from services.tenant_provisioning_service import TenantProvisioningService


pytestmark = pytest.mark.asyncio

ROOT = Path(__file__).resolve().parents[2]
AUTH_ROUTE_PATH = ROOT / "backend" / "api" / "v1" / "auth.py"
ONBOARDING_SERVICE_PATH = ROOT / "backend" / "services" / "onboarding_service.py"
BASE_REF = "origin/product-dev-recovered"
FORBIDDEN_EDIT_PATHS = {
    "backend/models/wholesaler.py",
    "backend/api/v1/wholesalers.py",
    "backend/crud/wholesaler.py",
    "backend/repositories/wholesaler_repository.py",
    "backend/api/v1/platform/tenants.py",
    "backend/api/v1/platform/stats.py",
    "backend/scripts/bootstrap_tenant_schema.py",
}
SENSITIVE_PLACEHOLDER = "hashed-registration-password"  # pragma: allowlist secret
EXPECTED_BASELINE_TABLES = {
    "users",
    "roles",
    "permissions",
    "user_roles",
    "role_permissions",
    "skus",
    "inventory_stocks",
    "inventory_movements",
    "orders",
    "order_items",
    "payments",
    "ledger_entries",
    "import_runs",
    "intake_workspaces",
    "intake_uploads",
    "intake_product_rows",
    "intake_validation_issues",
}
EMPTY_RBAC_TABLES = ("users", "roles", "permissions", "user_roles", "role_permissions")


@pytest.fixture(autouse=True)
async def _u6h2_public_schema():
    await _ensure_tables()
    await _clear_u6h2_rows_and_schemas()
    try:
        yield
    finally:
        await _clear_u6h2_rows_and_schemas()


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


async def _clear_u6h2_rows_and_schemas() -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        rows = (
            await session.execute(
                text(
                    "SELECT wholesaler_id, tenant_schema FROM public.tenant_registrations "
                    "WHERE owner_email LIKE 'u6h2_%@example.com' "
                )
            )
        ).mappings().all()
        wholesaler_ids = [row["wholesaler_id"] for row in rows if row["wholesaler_id"] is not None]
        for schema in {row["tenant_schema"] for row in rows if row["tenant_schema"] is not None}:
            if schema.startswith("t_") and schema.replace("_", "").isalnum():
                await session.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await session.execute(
            text("DELETE FROM public.tenant_registrations WHERE owner_email LIKE 'u6h2_%@example.com'")
        )
        if wholesaler_ids:
            await session.execute(
                text("DELETE FROM public.wholesalers WHERE id = ANY(:wholesaler_ids)"),
                {"wholesaler_ids": wholesaler_ids},
            )
        await session.commit()


async def _insert_registration(
    *,
    status: str,
    owner_email: str | None = None,
    wholesaler_id: uuid.UUID | None = None,
    tenant_schema: str | None = None,
    provisioning_completed_at: datetime | None = None,
) -> uuid.UUID:
    now = datetime.now(timezone.utc)
    terminal = status in {"active", "cancelled", "expired"}
    failed_without_retry = status == "failed"
    registration = TenantRegistration(
        company_name=f"U6H2 Company {uuid.uuid4().hex[:8]}",
        country="KE",
        owner_email=owner_email or f"u6h2_{uuid.uuid4().hex}@example.com",
        password_hash=None if terminal or failed_without_retry else SENSITIVE_PLACEHOLDER,
        password_hash_cleared_at=now if terminal or failed_without_retry else None,
        password_hash_cleanup_reason="test_cleanup" if terminal or failed_without_retry else None,  # pragma: allowlist secret
        status=status,
        email_verified_at=now if status in {"email_verified", "provisioning", "active"} else None,
        provisioning_started_at=now if status in {"provisioning", "active"} else None,
        provisioning_completed_at=provisioning_completed_at,
        failed_at=now if status == "failed" else None,
        wholesaler_id=wholesaler_id,
        tenant_schema=tenant_schema,
        expires_at=now + timedelta(hours=1),
    )
    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        session.add(registration)
        await session.commit()
        return registration.id


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
                )
                .where(TenantRegistration.id == registration_id)
                .execution_options(ignore_tenant=True)
            )
        ).mappings().one()
        return dict(row)


async def _wholesaler_count_for_registration(registration_id: uuid.UUID) -> int:
    code = f"TR{registration_id.hex[:30]}".upper()
    async with AsyncSessionLocal() as session:
        return await session.scalar(
            select(func.count())
            .select_from(Wholesaler)
            .where(Wholesaler.code == code)
            .execution_options(ignore_tenant=True)
        )


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


async def _table_count(schema: str, table: str) -> int:
    async with AsyncSessionLocal() as session:
        return int((await session.execute(text(f'SELECT COUNT(*) FROM "{schema}".{table}'))).scalar())


async def _drop_schema(schema: str) -> None:
    assert schema.startswith("t_")
    async with AsyncSessionLocal() as session:
        await session.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await session.commit()


async def test_provisioning_registration_creates_one_wholesaler_and_bootstrapped_schema():
    registration_id = await _insert_registration(status="provisioning")

    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        result = await TenantProvisioningService(session).provision_wholesaler_and_schema(
            registration_id
        )
        await session.commit()

    assert result.action == "provisioned"
    assert result.status == "active"
    assert result.wholesaler_id is not None
    assert result.tenant_schema is not None
    assert result.provisioning_completed_at is not None
    assert await _wholesaler_count_for_registration(registration_id) == 1

    snapshot = await _registration_snapshot(registration_id)
    assert snapshot["status"] == "active"
    assert snapshot["wholesaler_id"] == result.wholesaler_id
    assert snapshot["tenant_schema"] == result.tenant_schema
    assert snapshot["provisioning_completed_at"] is not None

    tables = await _tenant_tables(result.tenant_schema)
    assert EXPECTED_BASELINE_TABLES <= tables


async def test_active_existing_registration_returns_idempotent_result():
    registration_id = await _insert_registration(status="provisioning")

    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        first = await TenantProvisioningService(session).provision_wholesaler_and_schema(
            registration_id
        )
        await session.commit()

    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        second = await TenantProvisioningService(session).provision_wholesaler_and_schema(
            registration_id
        )
        await session.commit()

    assert first.action == "provisioned"
    assert second.action == "existing"
    assert second.status == "active"
    assert second.wholesaler_id == first.wholesaler_id
    assert second.tenant_schema == first.tenant_schema
    assert await _wholesaler_count_for_registration(registration_id) == 1


async def test_duplicate_retry_creates_no_duplicate_wholesaler_or_schema_corruption():
    registration_id = await _insert_registration(status="provisioning")

    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        first = await TenantProvisioningService(session).provision_wholesaler_and_schema(
            registration_id
        )
        await session.commit()

    tables_before = await _tenant_tables(first.tenant_schema)
    for _ in range(2):
        async with AsyncSessionLocal() as session:
            await session.execute(text("SET search_path TO public"))
            retry = await TenantProvisioningService(session).provision_wholesaler_and_schema(
                registration_id
            )
            await session.commit()
        assert retry.action == "existing"

    assert await _wholesaler_count_for_registration(registration_id) == 1
    assert await _tenant_tables(first.tenant_schema) == tables_before


@pytest.mark.parametrize(
    "status",
    ["pending_email_verification", "email_verified", "cancelled", "expired", "failed"],
)
async def test_non_provisioning_statuses_are_blocked_without_mutation(status: str):
    registration_id = await _insert_registration(status=status)
    before = await _registration_snapshot(registration_id)

    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        result = await TenantProvisioningService(session).provision_wholesaler_and_schema(
            registration_id
        )
        await session.commit()

    assert result.action == "blocked"
    assert result.status == status
    assert await _registration_snapshot(registration_id) == before
    assert await _wholesaler_count_for_registration(registration_id) == 0


async def test_bootstrap_failure_does_not_mark_active_or_completed():
    registration_id = await _insert_registration(status="provisioning")

    async def _fail_bootstrap(_schema: str, _database_url: str) -> None:
        raise RuntimeError("u6h2 simulated bootstrap failure")

    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        result = await TenantProvisioningService(
            session,
            bootstrap_func=_fail_bootstrap,
            database_url=get_settings().DATABASE_URL,
        ).provision_wholesaler_and_schema(registration_id)
        await session.commit()

    assert result.action == "failed"
    snapshot = await _registration_snapshot(registration_id)
    assert snapshot["status"] == "provisioning"
    assert snapshot["provisioning_completed_at"] is None
    assert snapshot["wholesaler_id"] is None
    assert snapshot["tenant_schema"] is None
    assert snapshot["failure_code"] == "BOOTSTRAP_FAILED"
    assert snapshot["failure_message"] == "RuntimeError: bootstrap failed"
    assert await _wholesaler_count_for_registration(registration_id) == 0


async def test_bootstrap_failure_message_does_not_persist_dsn_or_fake_password():
    registration_id = await _insert_registration(status="provisioning")
    fake_password = "FakeLeakPass123!"  # pragma: allowlist secret
    fake_dsn = f"postgresql+asyncpg://user:{fake_password}@db.example.invalid:5432/app"

    async def _fail_with_sensitive_message(_schema: str, _database_url: str) -> None:
        raise RuntimeError(f"could not connect to {fake_dsn} using token abc123")

    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        result = await TenantProvisioningService(
            session,
            bootstrap_func=_fail_with_sensitive_message,
            database_url=get_settings().DATABASE_URL,
        ).provision_wholesaler_and_schema(registration_id)
        await session.commit()

    assert result.action == "failed"
    snapshot = await _registration_snapshot(registration_id)
    assert snapshot["failure_code"] == "BOOTSTRAP_FAILED"
    assert snapshot["failure_message"] == "RuntimeError: bootstrap failed"
    assert fake_password not in snapshot["failure_message"]
    assert fake_dsn not in snapshot["failure_message"]
    assert "postgresql://" not in snapshot["failure_message"]
    assert "postgresql+asyncpg://" not in snapshot["failure_message"]
    assert "user:" not in snapshot["failure_message"]
    assert "token abc123" not in snapshot["failure_message"]


async def test_no_user_role_rbac_or_admin_rows_are_seeded_by_slice():
    registration_id = await _insert_registration(status="provisioning")

    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        result = await TenantProvisioningService(session).provision_wholesaler_and_schema(
            registration_id
        )
        await session.commit()

    assert result.action == "provisioned"
    for table in EMPTY_RBAC_TABLES:
        assert await _table_count(result.tenant_schema, table) == 0


async def test_public_auth_routes_delegate_tenant_provisioning_to_onboarding_service():
    auth_source = AUTH_ROUTE_PATH.read_text(encoding="utf-8")
    onboarding_source = ONBOARDING_SERVICE_PATH.read_text(encoding="utf-8")

    assert "TenantProvisioningService" not in auth_source
    assert "tenant_provisioning_service" not in auth_source
    assert "TenantProvisioningService" in onboarding_source
    assert "provision_wholesaler_and_schema" in onboarding_source


async def test_active_existing_with_missing_schema_is_not_treated_as_idempotent():
    registration_id = await _insert_registration(status="provisioning")
    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        provisioned = await TenantProvisioningService(session).provision_wholesaler_and_schema(
            registration_id
        )
        await session.commit()

    await _drop_schema(provisioned.tenant_schema)

    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        result = await TenantProvisioningService(session).provision_wholesaler_and_schema(
            registration_id
        )
        await session.commit()

    assert result.action == "blocked"
    assert result.reason == "schema_not_bootstrapped"


async def test_forbidden_wholesaler_api_crud_repository_and_bootstrap_files_are_untouched():
    import subprocess

    completed = subprocess.run(
        ["git", "diff", "--name-only", BASE_REF, "--"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    changed = set(completed.stdout.splitlines())
    assert changed.isdisjoint(FORBIDDEN_EDIT_PATHS)
