"""DC-2M2 legacy tenant reconciliation forward migration tests."""

from __future__ import annotations

import asyncio
import importlib.util
import os
from pathlib import Path
import uuid

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, text

from models.tenant_onboarding import TenantRegistration
from models.wholesaler import Wholesaler


BACKEND_DIR = Path(__file__).resolve().parents[1]
MIGRATION_031 = BACKEND_DIR / "alembic" / "versions" / "031_legacy_tenant_reconciliation.py"


def _database_url() -> str:
    return os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://", 1)


def _engine():
    return create_engine(_database_url(), future=True)


def _schema_name() -> str:
    return f"t_{uuid.uuid4().hex}"


def _qualified(schema: str, relation: str) -> str:
    return f'"{schema}".{relation}'


def _load_migration_031():
    spec = importlib.util.spec_from_file_location("dc2m2_migration_031", MIGRATION_031)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_migration_031(connection) -> None:
    module = _load_migration_031()
    migration_context = MigrationContext.configure(connection)
    operations = Operations(migration_context)
    original_op = module.op
    module.op = operations
    try:
        module.upgrade()
    finally:
        module.op = original_op


def _ensure_public_prerequisites(connection) -> None:
    connection.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
    connection.execute(
        text(
            "DO $$ BEGIN "
            "IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'reporting_role') "
            "THEN CREATE ROLE reporting_role NOLOGIN; END IF; "
            "END $$"
        )
    )
    Wholesaler.__table__.create(connection, checkfirst=True)
    TenantRegistration.__table__.create(connection, checkfirst=True)


def _cleanup(connection, schemas: list[str]) -> None:
    connection.execute(
        text("DELETE FROM public.tenant_registrations WHERE owner_email LIKE 'dc2m2_%@example.com'")
    )
    connection.execute(text("DELETE FROM public.wholesalers WHERE code LIKE 'DC2M2%'"))
    for schema in schemas:
        assert schema.startswith("t_") and schema.replace("_", "").isalnum()
        connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))


def _register_tenant(connection, schema: str, registration_status: str = "provisioning") -> uuid.UUID:
    wholesaler_id = uuid.UUID(schema.removeprefix("t_"))
    connection.execute(
        text(
            "INSERT INTO public.wholesalers (id, code, name, status) "
            "VALUES (:id, :code, :name, 'active')"
        ),
        {
            "id": wholesaler_id,
            "code": f"DC2M2{uuid.uuid4().hex[:8].upper()}",
            "name": "DC2M2 Test Wholesaler",
        },
    )
    registration_id = uuid.uuid4()
    connection.execute(
        text(
            "INSERT INTO public.tenant_registrations ("
            "id, company_name, country, owner_email, status, email_verified_at, "
            "provisioning_started_at, password_hash_cleared_at, wholesaler_id, "
            "tenant_schema, expires_at"
            ") VALUES ("
            ":id, :company_name, 'KE', :owner_email, :status, now(), now(), now(), "
            ":wholesaler_id, :tenant_schema, now() + interval '1 hour'"
            ")"
        ),
        {
            "id": registration_id,
            "company_name": "DC2M2 Company",
            "owner_email": f"dc2m2_{uuid.uuid4().hex}@example.com",
            "status": registration_status,
            "wholesaler_id": wholesaler_id,
            "tenant_schema": schema,
        },
    )
    return wholesaler_id


def _create_legacy_tenant_schema(
    connection,
    schema: str,
    *,
    unique_mode: str = "legacy_constraint",
    duplicate_prices: bool = False,
) -> tuple[uuid.UUID, uuid.UUID]:
    retailer_id = uuid.uuid4()
    sku_id = uuid.uuid4()
    connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    unique_clause = ""
    if unique_mode == "legacy_constraint":
        unique_clause = ", CONSTRAINT legacy_retailer_sku_unique UNIQUE (retailer_id, sku_id)"
    connection.execute(
        text(
            f"""
            CREATE TABLE {_qualified(schema, 'retailer_prices')} (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                retailer_id UUID NOT NULL,
                sku_id UUID NOT NULL,
                price NUMERIC(12,2) NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                is_deleted BOOLEAN NOT NULL DEFAULT false,
                deleted_at TIMESTAMPTZ,
                created_by UUID,
                updated_by UUID,
                CONSTRAINT ck_retailer_prices_positive_price CHECK (price > 0)
                {unique_clause}
            )
            """
        )
    )
    if unique_mode == "canonical_bad_index":
        connection.execute(
            text(
                f"CREATE INDEX uq_retailer_prices_retailer_sku "
                f"ON {_qualified(schema, 'retailer_prices')} (price)"
            )
        )
    elif unique_mode == "partial_unique_index_only":
        connection.execute(
            text(
                f"CREATE UNIQUE INDEX legacy_partial_unique_idx "
                f"ON {_qualified(schema, 'retailer_prices')} (retailer_id, sku_id) "
                "WHERE price > 0"
            )
        )

    connection.execute(
        text(
            f"INSERT INTO {_qualified(schema, 'retailer_prices')} (retailer_id, sku_id, price) "
            "VALUES (:retailer_id, :sku_id, 10.00)"
        ),
        {"retailer_id": retailer_id, "sku_id": sku_id},
    )
    if duplicate_prices:
        connection.execute(
            text(
                f"INSERT INTO {_qualified(schema, 'retailer_prices')} (retailer_id, sku_id, price) "
                "VALUES (:retailer_id, :sku_id, 11.00)"
            ),
            {"retailer_id": retailer_id, "sku_id": sku_id},
        )

    connection.execute(
        text(
            f"""
            CREATE TABLE {_qualified(schema, 'ledger_entries')} (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                transaction_date TIMESTAMPTZ NOT NULL DEFAULT now(),
                account_type TEXT NOT NULL,
                amount NUMERIC(20,4) NOT NULL,
                reference_type VARCHAR(50) NOT NULL,
                reference_id UUID NOT NULL,
                is_deleted BOOLEAN NOT NULL DEFAULT false
            )
            """
        )
    )
    connection.execute(
        text(
            f"INSERT INTO {_qualified(schema, 'ledger_entries')} "
            "(account_type, amount, reference_type, reference_id) "
            "VALUES ('revenue', -25.00, 'order', gen_random_uuid())"
        )
    )
    return retailer_id, sku_id


def _constraint_names(connection, schema: str, table_name: str) -> list[str]:
    return list(
        connection.execute(
            text(
                "SELECT c.conname FROM pg_constraint c "
                "WHERE c.conrelid = to_regclass(:qualified_table) ORDER BY c.conname"
            ),
            {"qualified_table": _qualified(schema, table_name)},
        ).scalars()
    )


def _unique_constraint_count(connection, schema: str) -> int:
    return int(
        connection.execute(
            text(
                "SELECT COUNT(*) FROM pg_constraint "
                "WHERE conrelid = to_regclass(:qualified_table) "
                "AND contype = 'u' "
                "AND conkey = ARRAY["
                "(SELECT attnum FROM pg_attribute WHERE attrelid = to_regclass(:qualified_table) "
                "AND attname = 'retailer_id'), "
                "(SELECT attnum FROM pg_attribute WHERE attrelid = to_regclass(:qualified_table) "
                "AND attname = 'sku_id')]::smallint[]"
            ),
            {"qualified_table": _qualified(schema, "retailer_prices")},
        ).scalar_one()
    )


def _index_names(connection, schema: str, table_name: str) -> list[str]:
    return list(
        connection.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE schemaname = :schema AND tablename = :table_name ORDER BY indexname"
            ),
            {"schema": schema, "table_name": table_name},
        ).scalars()
    )


def _row_count(connection, schema: str, table_name: str) -> int:
    return int(connection.execute(text(f"SELECT COUNT(*) FROM {_qualified(schema, table_name)}")).scalar_one())


def _assert_reporting_contract(connection, schema: str) -> None:
    assert connection.execute(
        text("SELECT 1 FROM pg_matviews WHERE schemaname = :schema AND matviewname = 'mv_sales_daily'"),
        {"schema": schema},
    ).first()
    indexdef = connection.execute(
        text(
            "SELECT indexdef FROM pg_indexes "
            "WHERE schemaname = :schema AND indexname = 'idx_mv_sales_daily_u1'"
        ),
        {"schema": schema},
    ).scalar_one()
    assert "UNIQUE INDEX" in indexdef.upper()
    assert "transaction_date" in indexdef
    assert "reporting_currency_code" in indexdef
    assert connection.execute(
        text("SELECT has_table_privilege('reporting_role', :qualified_table, 'SELECT')"),
        {"qualified_table": _qualified(schema, "mv_sales_daily")},
    ).scalar_one()


def _assert_retailer_prices_canonical(connection, schema: str) -> None:
    constraints = _constraint_names(connection, schema, "retailer_prices")
    assert "uq_retailer_prices_retailer_sku" in constraints
    assert "legacy_retailer_sku_unique" not in constraints
    assert _unique_constraint_count(connection, schema) == 1
    indexes = _index_names(connection, schema, "retailer_prices")
    assert "ix_retailer_prices_retailer_id" in indexes
    assert "ix_retailer_prices_sku_id" in indexes


def test_fresh_bootstrap_creates_canonical_retailer_prices_and_reporting():
    from scripts.bootstrap_tenant_schema import bootstrap

    schema = _schema_name()
    engine = _engine()
    try:
        with engine.begin() as connection:
            _ensure_public_prerequisites(connection)
            _cleanup(connection, [schema])

        asyncio.run(bootstrap(schema, os.environ["DATABASE_URL"]))

        with engine.begin() as connection:
            _assert_retailer_prices_canonical(connection, schema)
            _assert_reporting_contract(connection, schema)
    finally:
        with engine.begin() as connection:
            _cleanup(connection, [schema])
        engine.dispose()


def test_migration_renames_legacy_unique_and_creates_reporting_idempotently():
    schema = _schema_name()
    engine = _engine()
    try:
        with engine.begin() as connection:
            _ensure_public_prerequisites(connection)
            _cleanup(connection, [schema])
            _register_tenant(connection, schema)
            retailer_id, sku_id = _create_legacy_tenant_schema(connection, schema)
            before_rows = _row_count(connection, schema, "retailer_prices")

            _run_migration_031(connection)
            _assert_retailer_prices_canonical(connection, schema)
            _assert_reporting_contract(connection, schema)
            assert _row_count(connection, schema, "retailer_prices") == before_rows
            assert connection.execute(
                text(
                    f"SELECT price FROM {_qualified(schema, 'retailer_prices')} "
                    "WHERE retailer_id = :retailer_id AND sku_id = :sku_id"
                ),
                {"retailer_id": retailer_id, "sku_id": sku_id},
            ).scalar_one() == 10

            _run_migration_031(connection)
            _assert_retailer_prices_canonical(connection, schema)
            _assert_reporting_contract(connection, schema)
            assert _row_count(connection, schema, "retailer_prices") == before_rows
    finally:
        with engine.begin() as connection:
            _cleanup(connection, [schema])
        engine.dispose()


def test_migration_fails_closed_before_mutation_for_duplicate_rows():
    schema = _schema_name()
    engine = _engine()
    try:
        with engine.begin() as connection:
            _ensure_public_prerequisites(connection)
            _cleanup(connection, [schema])
            _register_tenant(connection, schema)
            _create_legacy_tenant_schema(connection, schema, unique_mode="none", duplicate_prices=True)

            with pytest.raises(RuntimeError, match="duplicate .*retailer_id, sku_id"):
                _run_migration_031(connection)

            assert "uq_retailer_prices_retailer_sku" not in _constraint_names(
                connection, schema, "retailer_prices"
            )
            assert connection.execute(
                text("SELECT 1 FROM pg_matviews WHERE schemaname = :schema AND matviewname = 'mv_sales_daily'"),
                {"schema": schema},
            ).first() is None
    finally:
        with engine.begin() as connection:
            _cleanup(connection, [schema])
        engine.dispose()


@pytest.mark.parametrize(
    ("unique_mode", "match_text"),
    [
        ("canonical_bad_index", "canonical name is occupied"),
        ("partial_unique_index_only", "unique-index-only"),
    ],
)
def test_migration_fails_closed_for_incompatible_unique_objects(unique_mode: str, match_text: str):
    schema = _schema_name()
    engine = _engine()
    try:
        with engine.begin() as connection:
            _ensure_public_prerequisites(connection)
            _cleanup(connection, [schema])
            _register_tenant(connection, schema)
            _create_legacy_tenant_schema(connection, schema, unique_mode=unique_mode)

            with pytest.raises(RuntimeError, match=match_text):
                _run_migration_031(connection)

            assert "uq_retailer_prices_retailer_sku" not in _constraint_names(
                connection, schema, "retailer_prices"
            )
            assert connection.execute(
                text("SELECT 1 FROM pg_matviews WHERE schemaname = :schema AND matviewname = 'mv_sales_daily'"),
                {"schema": schema},
            ).first() is None
    finally:
        with engine.begin() as connection:
            _cleanup(connection, [schema])
        engine.dispose()


def test_migration_uses_registry_gate_and_ignores_inactive_and_unregistered_schemas():
    active_schema = _schema_name()
    cancelled_schema = _schema_name()
    unregistered_schema = _schema_name()
    schemas = [active_schema, cancelled_schema, unregistered_schema]
    engine = _engine()
    try:
        with engine.begin() as connection:
            _ensure_public_prerequisites(connection)
            _cleanup(connection, schemas)
            _register_tenant(connection, active_schema)
            _register_tenant(connection, cancelled_schema, registration_status="cancelled")
            _create_legacy_tenant_schema(connection, active_schema)
            _create_legacy_tenant_schema(connection, cancelled_schema)
            _create_legacy_tenant_schema(connection, unregistered_schema)

            _run_migration_031(connection)

            _assert_retailer_prices_canonical(connection, active_schema)
            assert "legacy_retailer_sku_unique" in _constraint_names(
                connection, cancelled_schema, "retailer_prices"
            )
            assert "uq_retailer_prices_retailer_sku" not in _constraint_names(
                connection, cancelled_schema, "retailer_prices"
            )
            assert "legacy_retailer_sku_unique" in _constraint_names(
                connection, unregistered_schema, "retailer_prices"
            )
            assert "uq_retailer_prices_retailer_sku" not in _constraint_names(
                connection, unregistered_schema, "retailer_prices"
            )
    finally:
        with engine.begin() as connection:
            _cleanup(connection, schemas)
        engine.dispose()
