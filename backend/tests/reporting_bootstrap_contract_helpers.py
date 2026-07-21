"""Focused helpers for reporting tests that need a real provisioned tenant."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import uuid

import pytest_asyncio
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from database.reporting_session import _build_reporting_url
from database.session import AsyncSessionLocal, async_engine
from models.tenant_onboarding import TenantRegistration
from services.tenant_provisioning_service import TenantProvisioningService


@dataclass(frozen=True)
class ReportingTenant:
    tenant_id: str
    tenant_schema: str


async def _insert_reporting_registration() -> uuid.UUID:
    now = datetime.now(timezone.utc)
    registration = TenantRegistration(
        company_name=f"DC11T4C Reporting {uuid.uuid4().hex[:8]}",
        country="KE",
        owner_email=f"dc11t4c_reporting_{uuid.uuid4().hex}@example.com",
        password_hash="hashed-registration-password",  # pragma: allowlist secret
        status="provisioning",
        email_verified_at=now,
        provisioning_started_at=now,
        expires_at=now + timedelta(hours=1),
    )
    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        session.add(registration)
        await session.commit()
        return registration.id


async def _provision_reporting_tenant() -> ReportingTenant:
    registration_id = await _insert_reporting_registration()
    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        result = await TenantProvisioningService(session).provision_wholesaler_and_schema(
            registration_id
        )
        await session.commit()

    assert result.action == "provisioned"
    assert result.wholesaler_id is not None
    assert result.tenant_schema is not None
    return ReportingTenant(
        tenant_id=str(result.wholesaler_id),
        tenant_schema=result.tenant_schema,
    )


async def _cleanup_reporting_tenant(reporting_tenant: ReportingTenant) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        await session.execute(
            text(
                "DELETE FROM public.tenant_registrations "
                "WHERE tenant_schema = :tenant_schema "
                "AND owner_email LIKE 'dc11t4c_reporting_%@example.com'"
            ),
            {"tenant_schema": reporting_tenant.tenant_schema},
        )
        await session.execute(
            text("DELETE FROM public.wholesalers WHERE id = :wholesaler_id"),
            {"wholesaler_id": uuid.UUID(reporting_tenant.tenant_id)},
        )
        assert reporting_tenant.tenant_schema.startswith("t_")
        assert reporting_tenant.tenant_schema.replace("_", "").isalnum()
        await session.execute(
            text(f'DROP SCHEMA IF EXISTS "{reporting_tenant.tenant_schema}" CASCADE')
        )
        await session.commit()
    await async_engine.dispose()


async def cleanup_reporting_tenant(reporting_tenant: ReportingTenant) -> None:
    await _cleanup_reporting_tenant(reporting_tenant)


async def provision_reporting_tenant_for_contract() -> ReportingTenant:
    return await _provision_reporting_tenant()


async def _set_tenant_search_path(session: AsyncSession, tenant_schema: str) -> None:
    await session.execute(text(f'SET LOCAL search_path TO "{tenant_schema}", public'))


@pytest_asyncio.fixture
async def provisioned_reporting_tenant() -> ReportingTenant:
    reporting_tenant = await _provision_reporting_tenant()
    try:
        yield reporting_tenant
    finally:
        await _cleanup_reporting_tenant(reporting_tenant)


@pytest_asyncio.fixture
async def reporting_tenant_session(
    provisioned_reporting_tenant: ReportingTenant,
) -> AsyncSession:
    async with AsyncSessionLocal() as session:
        session.info["tenant_id"] = provisioned_reporting_tenant.tenant_id
        session.info["tenant_schema"] = provisioned_reporting_tenant.tenant_schema
        await _set_tenant_search_path(session, provisioned_reporting_tenant.tenant_schema)

        sync_session = session.sync_session

        @event.listens_for(sync_session, "after_begin")
        def _after_begin(sess, transaction, connection):
            connection.execute(
                text(
                    f'SET LOCAL search_path TO '
                    f'"{provisioned_reporting_tenant.tenant_schema}", public'
                )
            )

        try:
            yield session
        finally:
            event.remove(sync_session, "after_begin", _after_begin)
            await session.rollback()
            await session.close()


@pytest_asyncio.fixture
async def reporting_user_tenant_session(
    ensure_reporting_user_password,
    provisioned_reporting_tenant: ReportingTenant,
) -> AsyncSession:
    engine = create_async_engine(_build_reporting_url(), pool_pre_ping=True)
    factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    async with factory() as session:
        session.info["tenant_id"] = provisioned_reporting_tenant.tenant_id
        session.info["tenant_schema"] = provisioned_reporting_tenant.tenant_schema
        await _set_tenant_search_path(session, provisioned_reporting_tenant.tenant_schema)
        try:
            yield session
        finally:
            await session.rollback()
            await session.close()
    await engine.dispose()


async def reporting_contract_snapshot(session: AsyncSession, tenant_schema: str) -> dict[str, object]:
    materialized_view_exists = (
        await session.execute(
            text(
                "SELECT EXISTS ("
                "SELECT 1 FROM pg_matviews "
                "WHERE schemaname = :schema AND matviewname = 'mv_sales_daily'"
                ")"
            ),
            {"schema": tenant_schema},
        )
    ).scalar_one()
    view_names = set(
        (
            await session.execute(
                text(
                    "SELECT table_name FROM information_schema.views "
                    "WHERE table_schema = :schema "
                    "AND table_name IN ('rpt_receivables_summary', 'rpt_cash_flow_daily')"
                ),
                {"schema": tenant_schema},
            )
        ).scalars()
    )
    index_definition = (
        await session.execute(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE schemaname = :schema AND tablename = 'mv_sales_daily' "
                "AND indexname = 'idx_mv_sales_daily_u1'"
            ),
            {"schema": tenant_schema},
        )
    ).scalar_one_or_none()
    grant_rows = (
        await session.execute(
            text(
                "SELECT relation_name, has_table_privilege("
                "'reporting_role', format('%I.%I', CAST(:schema AS text), relation_name), 'SELECT'"
                ") AS can_select "
                "FROM unnest(ARRAY["
                "'mv_sales_daily', 'rpt_receivables_summary', 'rpt_cash_flow_daily'"
                "]) AS relation_name"
            ),
            {"schema": tenant_schema},
        )
    ).mappings().all()
    return {
        "materialized_view_exists": materialized_view_exists,
        "view_names": view_names,
        "index_definition": index_definition,
        "grants": {row["relation_name"]: row["can_select"] for row in grant_rows},
    }


async def assert_supported_bootstrap_reporting_contract(
    session: AsyncSession,
    tenant_schema: str,
) -> None:
    snapshot = await reporting_contract_snapshot(session, tenant_schema)
    assert snapshot["materialized_view_exists"] is True
    assert snapshot["view_names"] == {"rpt_receivables_summary", "rpt_cash_flow_daily"}
    assert snapshot["index_definition"] is not None
    assert "UNIQUE INDEX" in str(snapshot["index_definition"]).upper()
    assert "transaction_date" in str(snapshot["index_definition"])
    assert "reporting_currency_code" in str(snapshot["index_definition"])
    assert snapshot["grants"] == {
        "mv_sales_daily": True,
        "rpt_receivables_summary": True,
        "rpt_cash_flow_daily": True,
    }


async def assert_public_alembic_does_not_create_schema(
    session: AsyncSession,
    tenant_schema: str,
) -> None:
    schema_exists = (
        await session.execute(
            text(
                "SELECT EXISTS ("
                "SELECT 1 FROM information_schema.schemata WHERE schema_name = :schema"
                ")"
            ),
            {"schema": tenant_schema},
        )
    ).scalar_one()
    assert schema_exists is False


async def reporting_tenant_teardown_snapshot(
    session: AsyncSession,
    reporting_tenant: ReportingTenant,
) -> dict[str, object]:
    schema_exists = (
        await session.execute(
            text(
                "SELECT EXISTS ("
                "SELECT 1 FROM information_schema.schemata WHERE schema_name = :schema"
                ")"
            ),
            {"schema": reporting_tenant.tenant_schema},
        )
    ).scalar_one()
    registration_count = (
        await session.execute(
            text(
                "SELECT COUNT(*) FROM public.tenant_registrations "
                "WHERE tenant_schema = :tenant_schema "
                "OR wholesaler_id = :wholesaler_id"
            ),
            {
                "tenant_schema": reporting_tenant.tenant_schema,
                "wholesaler_id": uuid.UUID(reporting_tenant.tenant_id),
            },
        )
    ).scalar_one()
    wholesaler_count = (
        await session.execute(
            text("SELECT COUNT(*) FROM public.wholesalers WHERE id = :wholesaler_id"),
            {"wholesaler_id": uuid.UUID(reporting_tenant.tenant_id)},
        )
    ).scalar_one()
    return {
        "schema_exists": schema_exists,
        "registration_count": registration_count,
        "wholesaler_count": wholesaler_count,
    }
