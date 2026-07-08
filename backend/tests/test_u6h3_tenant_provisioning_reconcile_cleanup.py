"""U6-H3 tenant provisioning reconcile and cleanup safety tests."""

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
BOOTSTRAP_BASELINE_TABLES = {
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
async def _u6h3_public_schema():
    await _ensure_tables()
    await _clear_u6h3_rows_and_schemas()
    try:
        yield
    finally:
        await _clear_u6h3_rows_and_schemas()


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


async def _clear_u6h3_rows_and_schemas() -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        rows = (
            await session.execute(
                text(
                    "SELECT wholesaler_id, tenant_schema FROM public.tenant_registrations "
                    "WHERE owner_email LIKE 'u6h3_%@example.com'"
                )
            )
        ).mappings().all()
        wholesaler_ids = [row["wholesaler_id"] for row in rows if row["wholesaler_id"] is not None]
        for schema in {row["tenant_schema"] for row in rows if row["tenant_schema"] is not None}:
            if schema.startswith("t_") and schema.replace("_", "").isalnum():
                await session.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await session.execute(
            text("DELETE FROM public.tenant_registrations WHERE owner_email LIKE 'u6h3_%@example.com'")
        )
        if wholesaler_ids:
            await session.execute(
                text("DELETE FROM public.wholesalers WHERE id = ANY(:wholesaler_ids)"),
                {"wholesaler_ids": wholesaler_ids},
            )
        await session.commit()


async def _insert_wholesaler() -> Wholesaler:
    wholesaler = Wholesaler(
        code=f"U6H3{uuid.uuid4().hex[:8].upper()}",
        name="U6H3 Reconcile Wholesaler",
        status="provisioning",
    )
    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        session.add(wholesaler)
        await session.commit()
        return wholesaler


async def _insert_registration(
    *,
    wholesaler_id: uuid.UUID | None,
    tenant_schema: str | None,
    failure_code: str | None = None,
    failure_message: str | None = None,
) -> uuid.UUID:
    now = datetime.now(timezone.utc)
    registration = TenantRegistration(
        company_name=f"U6H3 Company {uuid.uuid4().hex[:8]}",
        country="KE",
        owner_email=f"u6h3_{uuid.uuid4().hex}@example.com",
        password_hash=SENSITIVE_PLACEHOLDER,
        status="provisioning",
        email_verified_at=now,
        provisioning_started_at=now,
        failed_at=now if failure_code else None,
        failure_code=failure_code,
        failure_message=failure_message,
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
                    TenantRegistration.provisioning_completed_at,
                    TenantRegistration.wholesaler_id,
                    TenantRegistration.tenant_schema,
                    TenantRegistration.failed_at,
                    TenantRegistration.failure_code,
                    TenantRegistration.failure_message,
                    TenantRegistration.password_hash,
                )
                .where(TenantRegistration.id == registration_id)
                .execution_options(ignore_tenant=True)
            )
        ).mappings().one()
        return dict(row)


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


async def _create_partial_schema(schema: str) -> None:
    assert schema.startswith("t_")
    async with AsyncSessionLocal() as session:
        await session.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
        await session.execute(text(f'CREATE TABLE IF NOT EXISTS "{schema}".users (id UUID PRIMARY KEY)'))
        await session.commit()


async def _create_bootstrap_baseline_tables(schema: str) -> None:
    assert schema.startswith("t_")
    async with AsyncSessionLocal() as session:
        await session.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
        for table_name in BOOTSTRAP_BASELINE_TABLES:
            await session.execute(
                text(f'CREATE TABLE IF NOT EXISTS "{schema}".{table_name} (id UUID PRIMARY KEY)')
            )
        await session.commit()


async def _drop_schema_if_exists(schema: str) -> None:
    assert schema.startswith("t_")
    async with AsyncSessionLocal() as session:
        await session.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await session.commit()


async def _bootstrap_schema(schema: str) -> None:
    from scripts.bootstrap_tenant_schema import bootstrap

    await bootstrap(schema, get_settings().DATABASE_URL)


async def _wholesaler_count(wholesaler_id: uuid.UUID) -> int:
    async with AsyncSessionLocal() as session:
        return await session.scalar(
            select(func.count())
            .select_from(Wholesaler)
            .where(Wholesaler.id == wholesaler_id)
            .execution_options(ignore_tenant=True)
        )


async def _wholesaler_ids_for_registration(registration_id: uuid.UUID) -> list[uuid.UUID]:
    code = f"TR{registration_id.hex[:30]}".upper()
    async with AsyncSessionLocal() as session:
        return list(
            (
                await session.execute(
                    select(Wholesaler.id)
                    .where(Wholesaler.code == code)
                    .order_by(Wholesaler.id)
                    .execution_options(ignore_tenant=True)
                )
            ).scalars()
        )


async def test_first_attempt_partial_schema_failure_persists_retry_anchor_and_reconciles():
    registration_id = await _insert_registration(
        wholesaler_id=None,
        tenant_schema=None,
    )
    created_schemas: list[str] = []

    async def _create_partial_then_fail(schema: str, _database_url: str) -> None:
        created_schemas.append(schema)
        async with AsyncSessionLocal() as session:
            await session.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
            await session.execute(
                text(f'CREATE TABLE IF NOT EXISTS "{schema}".first_attempt_marker (id UUID)')
            )
            await session.commit()
        raise RuntimeError("first attempt bootstrap failed after partial schema")

    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SET search_path TO public"))
            failed = await TenantProvisioningService(
                session,
                bootstrap_func=_create_partial_then_fail,
                database_url=get_settings().DATABASE_URL,
            ).provision_wholesaler_and_schema(registration_id)
            await session.commit()

        assert failed.action == "failed"
        assert len(created_schemas) == 1
        first_schema = created_schemas[0]
        snapshot_after_failure = await _registration_snapshot(registration_id)
        first_wholesaler_id = snapshot_after_failure["wholesaler_id"]
        assert first_wholesaler_id is not None
        assert snapshot_after_failure["tenant_schema"] == first_schema
        assert snapshot_after_failure["failure_code"] == "BOOTSTRAP_FAILED"
        assert snapshot_after_failure["failure_message"] == "RuntimeError: bootstrap failed"
        assert await _wholesaler_ids_for_registration(registration_id) == [first_wholesaler_id]
        assert "first_attempt_marker" in await _tenant_tables(first_schema)

        retry_schemas: list[str] = []

        async def _complete_bootstrap(schema: str, _database_url: str) -> None:
            retry_schemas.append(schema)
            await _create_bootstrap_baseline_tables(schema)

        async with AsyncSessionLocal() as session:
            await session.execute(text("SET search_path TO public"))
            retried = await TenantProvisioningService(
                session,
                bootstrap_func=_complete_bootstrap,
                database_url=get_settings().DATABASE_URL,
            ).provision_wholesaler_and_schema(registration_id)
            await session.commit()

        assert retried.action == "reconciled"
        assert retried.status == "active"
        assert retried.wholesaler_id == first_wholesaler_id
        assert retried.tenant_schema == first_schema
        assert retry_schemas == [first_schema]
        assert await _wholesaler_ids_for_registration(registration_id) == [first_wholesaler_id]
        assert BOOTSTRAP_BASELINE_TABLES <= await _tenant_tables(first_schema)

        snapshot_after_retry = await _registration_snapshot(registration_id)
        assert snapshot_after_retry["status"] == "active"
        assert snapshot_after_retry["wholesaler_id"] == first_wholesaler_id
        assert snapshot_after_retry["tenant_schema"] == first_schema
        assert snapshot_after_retry["failure_code"] is None
        assert snapshot_after_retry["failure_message"] is None
        assert snapshot_after_retry["password_hash"] is None
    finally:
        for schema in created_schemas:
            await _drop_schema_if_exists(schema)


async def test_partial_schema_after_failure_reconciles_to_active_without_duplicate_wholesaler():
    wholesaler = await _insert_wholesaler()
    tenant_schema = wholesaler.get_tenant_schema()
    await _create_partial_schema(tenant_schema)
    registration_id = await _insert_registration(
        wholesaler_id=wholesaler.id,
        tenant_schema=tenant_schema,
        failure_code="BOOTSTRAP_FAILED",
        failure_message="RuntimeError: bootstrap failed",
    )

    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        result = await TenantProvisioningService(session).provision_wholesaler_and_schema(
            registration_id
        )
        await session.commit()

    assert result.action == "reconciled"
    assert result.status == "active"
    assert result.wholesaler_id == wholesaler.id
    assert result.tenant_schema == tenant_schema
    assert await _wholesaler_count(wholesaler.id) == 1
    assert BOOTSTRAP_BASELINE_TABLES <= await _tenant_tables(tenant_schema)

    snapshot = await _registration_snapshot(registration_id)
    assert snapshot["status"] == "active"
    assert snapshot["provisioning_completed_at"] is not None
    assert snapshot["failure_code"] is None
    assert snapshot["failure_message"] is None
    assert snapshot["failed_at"] is None
    assert snapshot["password_hash"] is None


async def test_complete_schema_for_provisioning_registration_completes_without_bootstrap_rerun():
    wholesaler = await _insert_wholesaler()
    tenant_schema = wholesaler.get_tenant_schema()
    await _bootstrap_schema(tenant_schema)
    registration_id = await _insert_registration(
        wholesaler_id=wholesaler.id,
        tenant_schema=tenant_schema,
    )

    async def _fail_if_called(_schema: str, _database_url: str) -> None:
        raise AssertionError("complete schema should not require bootstrap rerun")

    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        result = await TenantProvisioningService(
            session,
            bootstrap_func=_fail_if_called,
            database_url=get_settings().DATABASE_URL,
        ).provision_wholesaler_and_schema(registration_id)
        await session.commit()

    assert result.action == "reconciled"
    assert result.status == "active"
    assert await _wholesaler_count(wholesaler.id) == 1


async def test_partial_schema_bootstrap_rerun_failure_stays_not_active_and_sanitized():
    wholesaler = await _insert_wholesaler()
    tenant_schema = wholesaler.get_tenant_schema()
    await _create_partial_schema(tenant_schema)
    registration_id = await _insert_registration(
        wholesaler_id=wholesaler.id,
        tenant_schema=tenant_schema,
    )
    fake_password = "FakePartialSchemaPass123!"  # pragma: allowlist secret
    fake_dsn = f"postgresql://u:{fake_password}@db.example.invalid:5432/app"

    async def _fail_bootstrap(_schema: str, _database_url: str) -> None:
        raise RuntimeError(f"bootstrap failed for {fake_dsn} token abc123")

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
    assert snapshot["wholesaler_id"] == wholesaler.id
    assert snapshot["tenant_schema"] == tenant_schema
    assert snapshot["failure_code"] == "BOOTSTRAP_FAILED"
    assert snapshot["failure_message"] == "RuntimeError: bootstrap failed"
    assert fake_password not in snapshot["failure_message"]
    assert fake_dsn not in snapshot["failure_message"]
    assert "postgresql://" not in snapshot["failure_message"]
    assert "token abc123" not in snapshot["failure_message"]
    assert await _wholesaler_count(wholesaler.id) == 1


async def test_active_existing_remains_idempotent_after_reconcile():
    wholesaler = await _insert_wholesaler()
    tenant_schema = wholesaler.get_tenant_schema()
    await _create_partial_schema(tenant_schema)
    registration_id = await _insert_registration(
        wholesaler_id=wholesaler.id,
        tenant_schema=tenant_schema,
    )

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

    assert first.action == "reconciled"
    assert second.action == "existing"
    assert second.status == "active"
    assert await _wholesaler_count(wholesaler.id) == 1


async def test_reconcile_seeds_no_user_role_rbac_or_admin_rows():
    wholesaler = await _insert_wholesaler()
    tenant_schema = wholesaler.get_tenant_schema()
    await _create_partial_schema(tenant_schema)
    registration_id = await _insert_registration(
        wholesaler_id=wholesaler.id,
        tenant_schema=tenant_schema,
    )

    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        result = await TenantProvisioningService(session).provision_wholesaler_and_schema(
            registration_id
        )
        await session.commit()

    assert result.action == "reconciled"
    for table in EMPTY_RBAC_TABLES:
        assert await _table_count(tenant_schema, table) == 0


async def test_public_auth_routes_do_not_call_tenant_provisioning_service():
    for path in (AUTH_ROUTE_PATH, ONBOARDING_SERVICE_PATH):
        source = path.read_text(encoding="utf-8")
        assert "TenantProvisioningService" not in source
        assert "tenant_provisioning_service" not in source
        assert "provision_wholesaler_and_schema" not in source


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
