"""S4-G migration infrastructure hardening tests."""

from __future__ import annotations

import importlib.util
import os
import uuid
from contextlib import contextmanager
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text

from tests.async_test_utils import run_alembic_upgrade, temporary_database_url


BACKEND_DIR = Path(__file__).resolve().parents[1]
MIGRATION_017 = BACKEND_DIR / "alembic" / "versions" / "017_retailer_prices.py"
ALEMBIC_DIR = BACKEND_DIR / "alembic"
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"


def _sync_url(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


def _async_url(url: str) -> str:
    return url.replace("postgresql://", "postgresql+asyncpg://", 1)


def _engine(database_url: str):
    return create_engine(_sync_url(database_url), future=True)


def _source_test_database_url() -> str:
    return os.environ["TEST_DATABASE_URL"]


def _alembic_config(database_url: str) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(ALEMBIC_DIR))
    config.set_main_option("sqlalchemy.url", _async_url(database_url))
    return config


@contextmanager
def _database_url_env(url: str):
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


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


def _run_alembic_upgrade_head(database_url: str) -> None:
    config = _alembic_config(database_url)
    with _database_url_env(database_url):
        run_alembic_upgrade(config, "head")


def _current_alembic_head() -> str:
    return ScriptDirectory(str(ALEMBIC_DIR)).get_current_head()


def _version_table_state(database_url: str) -> tuple[int, set[str]]:
    engine = _engine(database_url)
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
    with temporary_database_url(_source_test_database_url(), "s4gver") as database_url:
        _run_alembic_upgrade_head(database_url)
        version_length, versions = _version_table_state(database_url)
        assert version_length >= 128
        assert _current_alembic_head() in versions


@pytest.mark.integration
def test_alembic_upgrade_head_widens_existing_varchar32_version_table():
    with temporary_database_url(_source_test_database_url(), "s4gwide") as database_url:
        engine = _engine(database_url)
        with engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE public.alembic_version ("
                    "version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
                )
            )
        engine.dispose()

        _run_alembic_upgrade_head(database_url)
        version_length, versions = _version_table_state(database_url)

        assert version_length >= 128
        assert _current_alembic_head() in versions


def test_migration_017_creates_retailer_prices_on_fresh_tenant_schema():
    schema = _schema_name()
    with temporary_database_url(_source_test_database_url(), "s4g017a") as database_url:
        engine = _engine(database_url)
        with engine.begin() as connection:
            _create_schema(connection, schema)
            _run_migration_017(connection)
            _assert_retailer_prices_contract(connection, schema)
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()


def test_migration_017_reconciles_compatible_preexisting_retailer_prices():
    schema = _schema_name()
    retailer_id = uuid.uuid4()
    sku_id = uuid.uuid4()
    with temporary_database_url(_source_test_database_url(), "s4g017b") as database_url:
        engine = _engine(database_url)
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
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()


def test_migration_017_fails_closed_for_incompatible_retailer_prices():
    schema = _schema_name()
    with temporary_database_url(_source_test_database_url(), "s4g017c") as database_url:
        engine = _engine(database_url)
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
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()
