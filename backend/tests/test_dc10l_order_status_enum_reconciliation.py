"""DC-10L legacy order status enum reconciliation tests."""

from __future__ import annotations

import sys, os; sys.path.insert(0, os.path.dirname(__file__)); from conftest import run_coroutine
import asyncio
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
import uuid

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from models.tenant_onboarding import TenantRegistration
from models.wholesaler import Wholesaler
from services.receivables_service import ReceivablesService


BACKEND_DIR = Path(__file__).resolve().parents[1]
MIGRATION_033 = (
    BACKEND_DIR
    / "alembic"
    / "versions"
    / "033_order_status_enum_reconciliation.py"
)
CANONICAL_ORDER_STATUSES = (
    "draft",
    "confirmed",
    "partially_paid",
    "paid",
    "fulfilled",
    "cancelled",
    "voided",
    "returned",
)
LEGACY_ORDER_STATUSES = (
    "draft",
    "confirmed",
    "partially_paid",
    "cancelled",
    "returned",
)


def _database_url() -> str:
    return os.environ["DATABASE_URL"].replace(
        "postgresql+asyncpg://", "postgresql://", 1
    )


def _async_database_url() -> str:
    return os.environ["DATABASE_URL"].replace(
        "postgresql://", "postgresql+asyncpg://", 1
    )


def _engine():
    return create_engine(_database_url(), future=True)


def _schema_name() -> str:
    return f"t_{uuid.uuid4().hex}"


def _qualified(schema: str, relation: str) -> str:
    return f'"{schema}"."{relation}"'


def _load_migration_033():
    spec = importlib.util.spec_from_file_location("dc10l_migration_033", MIGRATION_033)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_migration_033(connection, *, tenant_schema: str | None = None) -> None:
    module = _load_migration_033()
    migration_context = MigrationContext.configure(connection)
    operations = Operations(migration_context)
    original_op = module.op
    original_context = module.context
    module.op = operations
    module.context = SimpleNamespace(
        get_x_argument=lambda as_dictionary=True: (
            {"tenant_schema": tenant_schema}
            if as_dictionary and tenant_schema is not None
            else {}
        )
    )
    try:
        module.upgrade()
    finally:
        module.op = original_op
        module.context = original_context


def _ensure_public_prerequisites(connection) -> None:
    connection.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
    Wholesaler.__table__.create(connection, checkfirst=True)
    TenantRegistration.__table__.create(connection, checkfirst=True)


def _cleanup(connection, schemas: list[str]) -> None:
    for schema in schemas:
        wholesaler_id = uuid.UUID(schema.removeprefix("t_"))
        connection.execute(
            text(
                "DELETE FROM public.tenant_registrations "
                "WHERE tenant_schema = :schema OR wholesaler_id = :wholesaler_id"
            ),
            {"schema": schema, "wholesaler_id": wholesaler_id},
        )
        connection.execute(
            text("DELETE FROM public.wholesalers WHERE id = :wholesaler_id"),
            {"wholesaler_id": wholesaler_id},
        )
        connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))


def _register_tenant(
    connection,
    schema: str,
    *,
    registration_status: str = "provisioning",
    wholesaler_status: str = "active",
) -> uuid.UUID:
    wholesaler_id = uuid.UUID(schema.removeprefix("t_"))
    connection.execute(
        text(
            "INSERT INTO public.wholesalers (id, code, name, status) "
            "VALUES (:id, :code, 'DC-10L Test Wholesaler', :status)"
        ),
        {
            "id": wholesaler_id,
            "code": f"DC10L{uuid.uuid4().hex[:10].upper()}",
            "status": wholesaler_status,
        },
    )
    connection.execute(
        text(
            "INSERT INTO public.tenant_registrations ("
            "id, company_name, country, owner_email, status, email_verified_at, "
            "provisioning_started_at, password_hash_cleared_at, wholesaler_id, "
            "tenant_schema, expires_at"
            ") VALUES ("
            ":id, 'DC-10L Company', 'KE', :owner_email, :status, now(), now(), "
            "now(), :wholesaler_id, :tenant_schema, now() + interval '1 hour'"
            ")"
        ),
        {
            "id": uuid.uuid4(),
            "owner_email": f"dc10l_{uuid.uuid4().hex}@example.com",
            "status": registration_status,
            "wholesaler_id": wholesaler_id,
            "tenant_schema": schema,
        },
    )
    return wholesaler_id


def _create_orders_table(
    connection,
    schema: str,
    *,
    statuses: tuple[str, ...] = LEGACY_ORDER_STATUSES,
    row_status: str | None = None,
) -> None:
    connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    enum_members = ", ".join(f"'{value}'" for value in statuses)
    connection.execute(
        text(
            f"CREATE TYPE {_qualified(schema, 'order_status')} "
            f"AS ENUM ({enum_members})"
        )
    )
    connection.execute(
        text(
            f"""
            CREATE TABLE {_qualified(schema, 'orders')} (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                wholesaler_id UUID NOT NULL,
                retailer_id UUID NOT NULL,
                status {_qualified(schema, 'order_status')} NOT NULL DEFAULT 'draft',
                total_amount NUMERIC(12, 2) NOT NULL DEFAULT 0,
                notes TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                is_deleted BOOLEAN NOT NULL DEFAULT false,
                deleted_at TIMESTAMPTZ,
                created_by UUID,
                updated_by UUID
            )
            """
        )
    )
    if row_status is not None:
        connection.execute(
            text(
                f"INSERT INTO {_qualified(schema, 'orders')} "
                "(wholesaler_id, retailer_id, status) "
                "VALUES (:wholesaler_id, :retailer_id, :status)"
            ),
            {
                "wholesaler_id": uuid.UUID(schema.removeprefix("t_")),
                "retailer_id": uuid.uuid4(),
                "status": row_status,
            },
        )


def _enum_labels(connection, schema: str) -> tuple[str, ...]:
    return tuple(
        connection.execute(
            text(
                "SELECT enum.enumlabel FROM pg_enum enum "
                "JOIN pg_type typ ON typ.oid = enum.enumtypid "
                "JOIN pg_namespace ns ON ns.oid = typ.typnamespace "
                "WHERE ns.nspname = :schema AND typ.typname = 'order_status' "
                "ORDER BY enum.enumsortorder"
            ),
            {"schema": schema},
        ).scalars()
    )


def _list_receivable_orders(schema: str, wholesaler_id: uuid.UUID):
    async def _run():
        engine = create_async_engine(_async_database_url(), future=True)
        try:
            async with AsyncSession(engine) as session:
                session.info["tenant_id"] = str(wholesaler_id)
                session.info["tenant_schema"] = schema
                await session.execute(
                    text(f'SET LOCAL search_path TO "{schema}", public')
                )
                return await ReceivablesService().list_receivable_orders(
                    tenant_db=session,
                    wholesaler_id=wholesaler_id,
                    page=1,
                    size=20,
                )
        finally:
            await engine.dispose()

    return run_coroutine(_run())


def test_migration_is_self_contained_and_normalizes_catalog_bytes():
    source = MIGRATION_033.read_text(encoding="utf-8")
    assert "from models" not in source
    assert "import models" not in source

    module = _load_migration_033()
    assert module._catalog_code(b"e") == "e"
    assert module._catalog_code(memoryview(b"paid")) == "paid"


def test_migration_closes_real_finance_enum_coercion_failure_and_is_idempotent():
    schema = _schema_name()
    engine = _engine()
    try:
        with engine.begin() as connection:
            _ensure_public_prerequisites(connection)
            _cleanup(connection, [schema])
            wholesaler_id = _register_tenant(connection, schema)
            _create_orders_table(connection, schema)

        with pytest.raises(DBAPIError, match='invalid input value for enum order_status: "paid"'):
            _list_receivable_orders(schema, wholesaler_id)

        with engine.begin() as connection:
            _run_migration_033(connection)
            assert set(_enum_labels(connection, schema)) == set(CANONICAL_ORDER_STATUSES)

        result = _list_receivable_orders(schema, wholesaler_id)
        assert result == {
            "items": [],
            "pagination": {"page": 1, "size": 20, "total": 0, "pages": 0},
        }

        with engine.begin() as connection:
            before = _enum_labels(connection, schema)
            _run_migration_033(connection)
            assert _enum_labels(connection, schema) == before
    finally:
        with engine.begin() as connection:
            _cleanup(connection, [schema])
        engine.dispose()


def test_preflight_failure_prevents_partial_enum_mutation_across_tenants():
    good_schema = _schema_name()
    bad_schema = _schema_name()
    engine = _engine()
    try:
        with engine.begin() as connection:
            _ensure_public_prerequisites(connection)
            _cleanup(connection, [good_schema, bad_schema])
            _register_tenant(connection, good_schema)
            _create_orders_table(connection, good_schema)
            _register_tenant(connection, bad_schema)
            _create_orders_table(
                connection,
                bad_schema,
                statuses=LEGACY_ORDER_STATUSES + ("pending",),
                row_status="pending",
            )
            before = _enum_labels(connection, good_schema)

            with pytest.raises(RuntimeError, match="non-canonical rows"):
                _run_migration_033(connection)

            assert _enum_labels(connection, good_schema) == before
    finally:
        with engine.begin() as connection:
            _cleanup(connection, [good_schema, bad_schema])
        engine.dispose()


def test_unregistered_and_inactive_tenant_schemas_are_not_mutated():
    registered_schema = _schema_name()
    inactive_schema = _schema_name()
    rogue_schema = _schema_name()
    schemas = [registered_schema, inactive_schema, rogue_schema]
    engine = _engine()
    try:
        with engine.begin() as connection:
            _ensure_public_prerequisites(connection)
            _cleanup(connection, schemas)
            _register_tenant(connection, registered_schema)
            _create_orders_table(connection, registered_schema)
            _register_tenant(
                connection,
                inactive_schema,
                wholesaler_status="suspended",
            )
            _create_orders_table(connection, inactive_schema)
            _create_orders_table(connection, rogue_schema)

            _run_migration_033(connection)

            assert set(_enum_labels(connection, registered_schema)) == set(
                CANONICAL_ORDER_STATUSES
            )
            assert _enum_labels(connection, inactive_schema) == LEGACY_ORDER_STATUSES
            assert _enum_labels(connection, rogue_schema) == LEGACY_ORDER_STATUSES
    finally:
        with engine.begin() as connection:
            _cleanup(connection, schemas)
        engine.dispose()


def test_wrong_order_status_column_type_fails_closed():
    schema = _schema_name()
    engine = _engine()
    try:
        with engine.begin() as connection:
            _ensure_public_prerequisites(connection)
            _cleanup(connection, [schema])
            _register_tenant(connection, schema)
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(
                text(
                    f"CREATE TABLE {_qualified(schema, 'orders')} ("
                    "id UUID PRIMARY KEY DEFAULT gen_random_uuid(), "
                    "status VARCHAR(32) NOT NULL DEFAULT 'draft')"
                )
            )

            with pytest.raises(RuntimeError, match="schema-local order_status enum"):
                _run_migration_033(connection)

            assert _enum_labels(connection, schema) == ()
    finally:
        with engine.begin() as connection:
            _cleanup(connection, [schema])
        engine.dispose()


def test_fresh_bootstrap_creates_complete_order_status_enum():
    from scripts.bootstrap_tenant_schema import bootstrap

    schema = _schema_name()
    engine = _engine()
    try:
        with engine.begin() as connection:
            _ensure_public_prerequisites(connection)
            _cleanup(connection, [schema])

        run_coroutine(bootstrap(schema, os.environ["DATABASE_URL"]))

        with engine.begin() as connection:
            assert set(_enum_labels(connection, schema)) == set(
                CANONICAL_ORDER_STATUSES
            )
    finally:
        with engine.begin() as connection:
            _cleanup(connection, [schema])
        engine.dispose()


def test_bootstrap_reconciles_existing_legacy_order_status_enum():
    from scripts.bootstrap_tenant_schema import bootstrap

    schema = _schema_name()
    engine = _engine()
    try:
        with engine.begin() as connection:
            _ensure_public_prerequisites(connection)
            _cleanup(connection, [schema])
            _create_orders_table(connection, schema)

        run_coroutine(bootstrap(schema, os.environ["DATABASE_URL"]))

        with engine.begin() as connection:
            assert set(_enum_labels(connection, schema)) == set(
                CANONICAL_ORDER_STATUSES
            )
    finally:
        with engine.begin() as connection:
            _cleanup(connection, [schema])
        engine.dispose()


def test_bootstrap_rejects_wrong_order_status_type_without_creating_enum():
    from scripts.bootstrap_tenant_schema import bootstrap

    schema = _schema_name()
    engine = _engine()
    try:
        with engine.begin() as connection:
            _ensure_public_prerequisites(connection)
            _cleanup(connection, [schema])
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.execute(
                text(
                    f"""
                    CREATE TABLE {_qualified(schema, 'orders')} (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        wholesaler_id UUID NOT NULL,
                        retailer_id UUID NOT NULL,
                        status VARCHAR(32) NOT NULL DEFAULT 'draft',
                        total_amount NUMERIC(12, 2) NOT NULL DEFAULT 0,
                        notes TEXT,
                        created_at TIMESTAMPTZ DEFAULT now(),
                        updated_at TIMESTAMPTZ DEFAULT now(),
                        is_deleted BOOLEAN DEFAULT false,
                        deleted_at TIMESTAMPTZ,
                        created_by UUID,
                        updated_by UUID
                    )
                    """
                )
            )

        with pytest.raises(RuntimeError, match="schema-local order_status enum"):
            run_coroutine(bootstrap(schema, os.environ["DATABASE_URL"]))

        with engine.begin() as connection:
            assert _enum_labels(connection, schema) == ()
    finally:
        with engine.begin() as connection:
            _cleanup(connection, [schema])
        engine.dispose()
