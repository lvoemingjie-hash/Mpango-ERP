"""S4-G migration infrastructure hardening tests."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import uuid
from pathlib import Path
from urllib.parse import quote_plus

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, text


BACKEND_DIR = Path(__file__).resolve().parents[1]
MIGRATION_017 = BACKEND_DIR / "alembic" / "versions" / "017_retailer_prices.py"


def _database_url(database: str) -> str:
    user = os.environ["POSTGRES_USER"]
    password = os.environ["POSTGRES_PASSWORD"]
    host = os.environ.get("POSTGRES_HOST", "127.0.0.1")
    port = os.environ.get("POSTGRES_PORT", "5432")
    return (
        f"postgresql://{quote_plus(user)}:{quote_plus(password)}@"
        f"{host}:{port}/{database}"
    )


def _engine(database: str):
    return create_engine(_database_url(database), future=True)


def _create_database(database: str) -> None:
    admin_database = os.environ["POSTGRES_DB"]
    engine = create_engine(
        _database_url(admin_database), future=True, isolation_level="AUTOCOMMIT"
    )
    with engine.connect() as connection:
        connection.execute(
            text(
                "SELECT pg_terminate_backend(pid) "
                "FROM pg_stat_activity WHERE datname = :database"
            ),
            {"database": database},
        )
        connection.execute(text(f'DROP DATABASE IF EXISTS "{database}"'))
        connection.execute(text(f'CREATE DATABASE "{database}"'))
    engine.dispose()


def _drop_database(database: str) -> None:
    admin_database = os.environ["POSTGRES_DB"]
    engine = create_engine(
        _database_url(admin_database), future=True, isolation_level="AUTOCOMMIT"
    )
    with engine.connect() as connection:
        connection.execute(
            text(
                "SELECT pg_terminate_backend(pid) "
                "FROM pg_stat_activity WHERE datname = :database"
            ),
            {"database": database},
        )
        connection.execute(text(f'DROP DATABASE IF EXISTS "{database}"'))
    engine.dispose()


def _load_migration_017():
    spec = importlib.util.spec_from_file_location("s4g_migration_017", MIGRATION_017)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_migration_017(connection) -> None:
    module = _load_migration_017()
    migration_context = MigrationContext.configure(connection)
    operations = Operations(migration_context)
    original_op = module.op
    module.op = operations
    try:
        module.upgrade()
    finally:
        module.op = original_op


def _run_alembic_upgrade_head(database: str) -> None:
    env = os.environ.copy()
    env["DATABASE_URL"] = _database_url(database)
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stderr + result.stdout


def _version_table_state(database: str) -> tuple[int, set[str]]:
    engine = _engine(database)
    with engine.connect() as connection:
        version_length = connection.execute(
            text(
                "SELECT character_maximum_length "
                "FROM information_schema.columns "
                "WHERE table_schema = 'public' "
                "AND table_name = 'alembic_version' "
                "AND column_name = 'version_num'"
            )
        ).scalar_one()
        versions = set(
            connection.execute(text("SELECT version_num FROM public.alembic_version"))
            .scalars()
            .all()
        )
    engine.dispose()
    return version_length, versions


def _schema_name() -> str:
    return f"t_s4g_{uuid.uuid4().hex[:12]}"


def _create_schema(connection, schema: str) -> None:
    connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    connection.execute(text(f'SET LOCAL search_path TO "{schema}", public'))


def _retailer_prices_contract(connection, schema: str) -> dict[str, set[str]]:
    columns = set(
        connection.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = :schema AND table_name = 'retailer_prices'"
            ),
            {"schema": schema},
        ).scalars()
    )
    constraints = set(
        connection.execute(
            text(
                "SELECT conname FROM pg_constraint c "
                "JOIN pg_namespace n ON n.oid = c.connamespace "
                "WHERE n.nspname = :schema "
                "AND c.conrelid = to_regclass(:qualified_table)"
            ),
            {"schema": schema, "qualified_table": f'"{schema}".retailer_prices'},
        ).scalars()
    )
    indexes = set(
        connection.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE schemaname = :schema AND tablename = 'retailer_prices'"
            ),
            {"schema": schema},
        ).scalars()
    )
    return {"columns": columns, "constraints": constraints, "indexes": indexes}


def _assert_retailer_prices_contract(connection, schema: str) -> None:
    contract = _retailer_prices_contract(connection, schema)
    assert {
        "id",
        "retailer_id",
        "sku_id",
        "price",
        "created_at",
        "updated_at",
        "is_deleted",
        "deleted_at",
        "created_by",
        "updated_by",
    }.issubset(contract["columns"])
    assert "uq_retailer_prices_retailer_sku" in contract["constraints"]
    assert "ck_retailer_prices_positive_price" in contract["constraints"]
    assert "ix_retailer_prices_retailer_id" in contract["indexes"]
    assert "ix_retailer_prices_sku_id" in contract["indexes"]


@pytest.mark.integration
def test_alembic_upgrade_head_creates_wide_version_table_on_fresh_database():
    database = f"s4g_version_{uuid.uuid4().hex[:12]}"
    _create_database(database)
    try:
        _run_alembic_upgrade_head(database)
        version_length, versions = _version_table_state(database)

        assert version_length >= 128
        assert "023_inventory_reservations" in versions
    finally:
        _drop_database(database)


@pytest.mark.integration
def test_alembic_upgrade_head_widens_existing_varchar32_version_table():
    database = f"s4g_existing_{uuid.uuid4().hex[:12]}"
    _create_database(database)
    try:
        engine = _engine(database)
        with engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE public.alembic_version ("
                    "version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
                )
            )
        engine.dispose()

        _run_alembic_upgrade_head(database)
        version_length, versions = _version_table_state(database)

        assert version_length >= 128
        assert "023_inventory_reservations" in versions
    finally:
        _drop_database(database)


def test_migration_017_creates_retailer_prices_on_fresh_tenant_schema():
    schema = _schema_name()
    engine = _engine(os.environ["POSTGRES_DB"])
    try:
        with engine.begin() as connection:
            _create_schema(connection, schema)
            _run_migration_017(connection)
            _assert_retailer_prices_contract(connection, schema)
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()


def test_migration_017_reconciles_compatible_preexisting_retailer_prices():
    schema = _schema_name()
    retailer_id = uuid.uuid4()
    sku_id = uuid.uuid4()
    engine = _engine(os.environ["POSTGRES_DB"])
    try:
        with engine.begin() as connection:
            _create_schema(connection, schema)
            connection.execute(
                text(
                    f'''
                    CREATE TABLE "{schema}".retailer_prices (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        retailer_id UUID NOT NULL,
                        sku_id UUID NOT NULL,
                        price NUMERIC(12, 2) NOT NULL CHECK (price > 0),
                        created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
                        updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
                        is_deleted BOOLEAN NOT NULL DEFAULT false,
                        deleted_at TIMESTAMP WITH TIME ZONE,
                        created_by UUID,
                        updated_by UUID,
                        UNIQUE (retailer_id, sku_id)
                    )
                    '''
                )
            )
            connection.execute(
                text(
                    f'INSERT INTO "{schema}".retailer_prices '
                    "(retailer_id, sku_id, price) VALUES (:retailer_id, :sku_id, 10.00)"
                ),
                {"retailer_id": retailer_id, "sku_id": sku_id},
            )

            _run_migration_017(connection)

            _assert_retailer_prices_contract(connection, schema)
            row_count = connection.execute(
                text(f'SELECT count(*) FROM "{schema}".retailer_prices')
            ).scalar_one()
            assert row_count == 1
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()


def test_migration_017_fails_closed_for_incompatible_retailer_prices():
    schema = _schema_name()
    engine = _engine(os.environ["POSTGRES_DB"])
    try:
        with engine.begin() as connection:
            _create_schema(connection, schema)
            connection.execute(
                text(
                    f'''
                    CREATE TABLE "{schema}".retailer_prices (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        retailer_id UUID NOT NULL,
                        sku_id UUID NOT NULL
                    )
                    '''
                )
            )

            with pytest.raises(RuntimeError, match="missing column 'price'"):
                _run_migration_017(connection)
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()
