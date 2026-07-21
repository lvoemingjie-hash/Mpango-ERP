"""Focused helpers for reporting tests that need a real provisioned tenant."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import re
import uuid

from alembic.config import Config
import pytest_asyncio
from sqlalchemy import create_engine, event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from database.reporting_session import _build_reporting_url
from database.session import AsyncSessionLocal, async_engine
from db.sql_safety import validate_identifier
from models.tenant_onboarding import TenantRegistration
from services.tenant_provisioning_service import TenantProvisioningService
from tests.async_test_utils import run_alembic_upgrade, temporary_database_url


BACKEND_DIR = Path(__file__).resolve().parents[1]
OWNER_EMAIL_PREFIX = "dc11t4c_reporting_"
OWNER_EMAIL_DOMAIN = "@example.com"
TENANT_SCHEMA_RE = re.compile(r"^t_[0-9a-f]{32}$")


@dataclass(frozen=True)
class ReportingTenant:
    registration_id: uuid.UUID
    tenant_id: str
    tenant_schema: str
    owner_email: str


def _expected_tenant_schema(tenant_id: str) -> str:
    return f"t_{uuid.UUID(tenant_id).hex}"


def _validate_owned_tenant_schema(reporting_tenant: ReportingTenant) -> str:
    expected_schema = _expected_tenant_schema(reporting_tenant.tenant_id)
    if reporting_tenant.tenant_schema != expected_schema:
        raise AssertionError(
            "reporting tenant schema does not match derived wholesaler UUID schema"
        )
    if TENANT_SCHEMA_RE.fullmatch(reporting_tenant.tenant_schema) is None:
        raise AssertionError("reporting tenant schema does not match expected t_<uuid> format")
    return validate_identifier(reporting_tenant.tenant_schema, "tenant_schema")


def _is_helper_owner_email(owner_email: str) -> bool:
    return owner_email.startswith(OWNER_EMAIL_PREFIX) and owner_email.endswith(OWNER_EMAIL_DOMAIN)


async def _insert_reporting_registration() -> tuple[uuid.UUID, str]:
    now = datetime.now(timezone.utc)
    owner_email = f"{OWNER_EMAIL_PREFIX}{uuid.uuid4().hex}{OWNER_EMAIL_DOMAIN}"
    registration = TenantRegistration(
        company_name=f"DC11T4C Reporting {uuid.uuid4().hex[:8]}",
        country="KE",
        owner_email=owner_email,
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
        return registration.id, owner_email


async def _provision_reporting_tenant() -> ReportingTenant:
    registration_id, owner_email = await _insert_reporting_registration()
    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        result = await TenantProvisioningService(session).provision_wholesaler_and_schema(
            registration_id
        )
        await session.commit()

    assert result.action == "provisioned"
    assert result.wholesaler_id is not None
    assert result.tenant_schema is not None
    reporting_tenant = ReportingTenant(
        registration_id=registration_id,
        tenant_id=str(result.wholesaler_id),
        tenant_schema=result.tenant_schema,
        owner_email=owner_email,
    )
    _validate_owned_tenant_schema(reporting_tenant)
    return reporting_tenant


async def _tenant_schema_exists(session: AsyncSession, tenant_schema: str) -> bool:
    return (
        await session.execute(
            text(
                "SELECT EXISTS ("
                "SELECT 1 FROM information_schema.schemata WHERE schema_name = :schema"
                ")"
            ),
            {"schema": tenant_schema},
        )
    ).scalar_one()


async def _owned_registration_count(
    session: AsyncSession,
    reporting_tenant: ReportingTenant,
) -> int:
    return (
        await session.execute(
            text(
                "SELECT COUNT(*) FROM public.tenant_registrations "
                "WHERE id = :registration_id "
                "OR tenant_schema = :tenant_schema "
                "OR wholesaler_id = :wholesaler_id "
                "OR owner_email = :owner_email"
            ),
            {
                "registration_id": reporting_tenant.registration_id,
                "tenant_schema": reporting_tenant.tenant_schema,
                "wholesaler_id": uuid.UUID(reporting_tenant.tenant_id),
                "owner_email": reporting_tenant.owner_email,
            },
        )
    ).scalar_one()


async def _owned_wholesaler_count(
    session: AsyncSession,
    reporting_tenant: ReportingTenant,
) -> int:
    return (
        await session.execute(
            text("SELECT COUNT(*) FROM public.wholesalers WHERE id = :wholesaler_id"),
            {"wholesaler_id": uuid.UUID(reporting_tenant.tenant_id)},
        )
    ).scalar_one()


async def reporting_tenant_teardown_snapshot(
    session: AsyncSession,
    reporting_tenant: ReportingTenant,
) -> dict[str, object]:
    return {
        "schema_exists": await _tenant_schema_exists(session, reporting_tenant.tenant_schema),
        "registration_count": await _owned_registration_count(session, reporting_tenant),
        "wholesaler_count": await _owned_wholesaler_count(session, reporting_tenant),
    }


async def _owned_artifacts_absent(
    session: AsyncSession,
    reporting_tenant: ReportingTenant,
) -> bool:
    return await reporting_tenant_teardown_snapshot(session, reporting_tenant) == {
        "schema_exists": False,
        "registration_count": 0,
        "wholesaler_count": 0,
    }


async def _assert_cleanup_ownership(
    session: AsyncSession,
    reporting_tenant: ReportingTenant,
) -> str | None:
    tenant_schema = _validate_owned_tenant_schema(reporting_tenant)
    row = (
        await session.execute(
            text(
                "SELECT id, owner_email, wholesaler_id, tenant_schema "
                "FROM public.tenant_registrations "
                "WHERE id = :registration_id"
            ),
            {"registration_id": reporting_tenant.registration_id},
        )
    ).mappings().one_or_none()

    if row is None:
        if await _owned_artifacts_absent(session, reporting_tenant):
            return None
        raise AssertionError("owned reporting tenant cleanup evidence is missing")

    assert row["id"] == reporting_tenant.registration_id
    assert row["owner_email"] == reporting_tenant.owner_email
    assert _is_helper_owner_email(row["owner_email"])
    assert row["wholesaler_id"] == uuid.UUID(reporting_tenant.tenant_id)
    assert row["tenant_schema"] == reporting_tenant.tenant_schema
    return tenant_schema


async def _cleanup_reporting_tenant(reporting_tenant: ReportingTenant) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(text("SET search_path TO public"))
        tenant_schema = await _assert_cleanup_ownership(session, reporting_tenant)
        if tenant_schema is None:
            await session.rollback()
            return

        await session.execute(
            text("DELETE FROM public.tenant_registrations WHERE id = :registration_id"),
            {"registration_id": reporting_tenant.registration_id},
        )
        await session.execute(
            text("DELETE FROM public.wholesalers WHERE id = :wholesaler_id"),
            {"wholesaler_id": uuid.UUID(reporting_tenant.tenant_id)},
        )
        await session.execute(text(f'DROP SCHEMA IF EXISTS "{tenant_schema}" CASCADE'))
        await session.commit()
    await async_engine.dispose()


async def cleanup_reporting_tenant(reporting_tenant: ReportingTenant) -> None:
    await _cleanup_reporting_tenant(reporting_tenant)


async def provision_reporting_tenant_for_contract() -> ReportingTenant:
    return await _provision_reporting_tenant()


def _tenant_schema_set(database_url: str) -> set[str]:
    engine = create_engine(database_url, future=True)
    try:
        with engine.connect() as connection:
            return set(
                connection.execute(
                    text(
                        "SELECT schema_name FROM information_schema.schemata "
                        "WHERE schema_name ~ '^t_[0-9a-f]{32}$' "
                        "ORDER BY schema_name"
                    )
                ).scalars()
            )
    finally:
        engine.dispose()


def assert_public_alembic_upgrade_preserves_tenant_schema_set() -> None:
    source_url = os.environ["TEST_DATABASE_URL"]
    with temporary_database_url(source_url, "dc11t4cpublic") as database_url:
        before = _tenant_schema_set(database_url)

        previous_database_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = database_url
        try:
            config = Config(str(BACKEND_DIR / "alembic.ini"))
            run_alembic_upgrade(config, "head")
        finally:
            if previous_database_url is None:
                os.environ.pop("DATABASE_URL", None)
            else:
                os.environ["DATABASE_URL"] = previous_database_url

        after = _tenant_schema_set(database_url)

    assert before == after


async def _set_tenant_search_path(session: AsyncSession, tenant_schema: str) -> None:
    tenant_schema = validate_identifier(tenant_schema, "tenant_schema")
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
            tenant_schema = validate_identifier(
                provisioned_reporting_tenant.tenant_schema,
                "tenant_schema",
            )
            connection.execute(text(f'SET LOCAL search_path TO "{tenant_schema}", public'))

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
