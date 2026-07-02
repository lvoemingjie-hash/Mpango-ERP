"""U4-I-B1 intake apply audit schema contract tests."""
from __future__ import annotations

import importlib.util
import os
import uuid
from pathlib import Path

from alembic import op
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


BACKEND_DIR = Path(__file__).resolve().parents[1]
TEST_TENANT_SCHEMA = os.environ.get("TEST_TENANT_SCHEMA", "t_test")

WORKSPACE_COLUMNS = {
    "apply_status": {"nullable": False, "default_fragment": "not_applied"},
    "applied_at": {"nullable": True, "default_fragment": None},
    "applied_by": {"nullable": True, "default_fragment": None},
    "apply_result": {"nullable": False, "default_fragment": "{}"},
}

ROW_COLUMNS = {
    "target_sku_id": {"nullable": True, "default_fragment": None},
    "apply_status": {"nullable": False, "default_fragment": "not_applied"},
    "apply_error_code": {"nullable": True, "default_fragment": None},
    "apply_error_message": {"nullable": True, "default_fragment": None},
}

APPLY_AUDIT_INDEXES = {
    "ix_intake_workspaces_apply_status",
    "ix_intake_product_rows_target_sku_id",
}

APPLY_AUDIT_CONSTRAINTS = {
    "ck_intake_workspaces_apply_status": "not_applied applying applied failed",
    "ck_intake_product_rows_apply_status": "not_applied applied failed skipped",
}


async def _run_intake_migrations(session: AsyncSession, schema: str, *, include_025: bool = True) -> None:
    await session.execute(text(f'SET search_path TO "{schema}", public'))
    await session.commit()

    revisions = ["024_intake_skeleton"]
    if include_025:
        revisions.append("025_intake_apply_audit")

    for revision in revisions:
        migration_file = BACKEND_DIR / "alembic" / "versions" / f"{revision}.py"
        spec = importlib.util.spec_from_file_location(f"migration_{revision}_u4ib1", migration_file)
        migration_mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(migration_mod)

        def _run_upgrade_sync(sync_conn, migration_mod=migration_mod):
            sync_conn.execute(text(f'SET search_path TO "{schema}", public'))
            migration_context = MigrationContext.configure(sync_conn)
            operations = Operations(migration_context)
            patched_names = (
                "add_column",
                "create_check_constraint",
                "create_index",
                "create_table",
                "drop_column",
                "drop_constraint",
                "drop_index",
                "drop_table",
                "get_bind",
            )
            saved = {name: getattr(op, name, None) for name in patched_names}
            op.get_bind = lambda: sync_conn
            op.add_column = operations.add_column
            op.create_check_constraint = operations.create_check_constraint
            op.create_index = operations.create_index
            op.create_table = operations.create_table
            op.drop_column = operations.drop_column
            op.drop_constraint = operations.drop_constraint
            op.drop_index = operations.drop_index
            op.drop_table = operations.drop_table
            try:
                migration_mod.upgrade()
            finally:
                for name, original in saved.items():
                    if original is not None:
                        setattr(op, name, original)

        async_conn = await session.connection()
        await async_conn.run_sync(_run_upgrade_sync)
        await session.commit()


async def _drop_intake_tables(session: AsyncSession, schema: str) -> None:
    for table in (
        "intake_validation_issues",
        "intake_product_rows",
        "intake_uploads",
        "intake_workspaces",
    ):
        await session.execute(text(f'DROP TABLE IF EXISTS "{schema}".{table} CASCADE'))
    await session.commit()


async def _column_contract(session: AsyncSession, schema: str, table: str, column: str) -> dict[str, str | None]:
    result = await session.execute(
        text(
            "SELECT is_nullable, column_default FROM information_schema.columns "
            "WHERE table_schema = :schema AND table_name = :table AND column_name = :column"
        ),
        {"schema": schema, "table": table, "column": column},
    )
    row = result.mappings().first()
    assert row is not None, f"Missing {schema}.{table}.{column}"
    return {"is_nullable": row["is_nullable"], "column_default": row["column_default"]}


async def _index_exists(session: AsyncSession, schema: str, index_name: str) -> bool:
    result = await session.execute(
        text("SELECT 1 FROM pg_indexes WHERE schemaname = :schema AND indexname = :index_name"),
        {"schema": schema, "index_name": index_name},
    )
    return result.first() is not None


async def _constraint_definition(session: AsyncSession, schema: str, constraint_name: str) -> str | None:
    result = await session.execute(
        text(
            "SELECT pg_get_constraintdef(c.oid) "
            "FROM pg_constraint c "
            "JOIN pg_namespace n ON n.oid = c.connamespace "
            "WHERE n.nspname = :schema AND c.conname = :constraint_name"
        ),
        {"schema": schema, "constraint_name": constraint_name},
    )
    return result.scalar()


async def _assert_apply_audit_contract(session: AsyncSession, schema: str) -> None:
    for column, expected in WORKSPACE_COLUMNS.items():
        contract = await _column_contract(session, schema, "intake_workspaces", column)
        assert (contract["is_nullable"] == "YES") == expected["nullable"]
        if expected["default_fragment"]:
            assert expected["default_fragment"] in str(contract["column_default"])

    for column, expected in ROW_COLUMNS.items():
        contract = await _column_contract(session, schema, "intake_product_rows", column)
        assert (contract["is_nullable"] == "YES") == expected["nullable"]
        if expected["default_fragment"]:
            assert expected["default_fragment"] in str(contract["column_default"])

    for index_name in APPLY_AUDIT_INDEXES:
        assert await _index_exists(session, schema, index_name), f"Missing index {index_name}"

    for constraint_name, expected_fragments in APPLY_AUDIT_CONSTRAINTS.items():
        constraint = await _constraint_definition(session, schema, constraint_name)
        assert constraint is not None, f"Missing constraint {constraint_name}"
        for fragment in expected_fragments.split():
            assert fragment in constraint


@pytest.mark.asyncio
async def test_025_migration_adds_apply_audit_columns_defaults_indexes_and_constraints(async_session):
    await _drop_intake_tables(async_session, TEST_TENANT_SCHEMA)

    await _run_intake_migrations(async_session, TEST_TENANT_SCHEMA)

    await _assert_apply_audit_contract(async_session, TEST_TENANT_SCHEMA)


@pytest.mark.asyncio
async def test_bootstrap_fresh_tenant_has_apply_audit_columns(async_session):
    from scripts.bootstrap_tenant_schema import bootstrap

    schema = f"t_u4ib1_fresh_{uuid.uuid4().hex[:8]}"
    database_url = os.environ["DATABASE_URL"]

    await async_session.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
    await async_session.commit()

    try:
        await bootstrap(schema, database_url)

        await _assert_apply_audit_contract(async_session, schema)
    finally:
        await async_session.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await async_session.commit()


@pytest.mark.asyncio
async def test_bootstrap_reconciles_existing_tenant_missing_apply_audit_columns(async_session):
    from scripts.bootstrap_tenant_schema import bootstrap

    schema = f"t_u4ib1_existing_{uuid.uuid4().hex[:8]}"
    database_url = os.environ["DATABASE_URL"]

    await async_session.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
    await async_session.execute(text(f'CREATE SCHEMA "{schema}"'))
    await async_session.commit()

    try:
        await _run_intake_migrations(async_session, schema, include_025=False)

        assert (await _column_contract(async_session, schema, "intake_workspaces", "status"))["is_nullable"] == "NO"
        missing_before = await async_session.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.columns "
                "WHERE table_schema = :schema "
                "AND table_name IN ('intake_workspaces', 'intake_product_rows') "
                "AND column_name IN ('apply_status', 'applied_at', 'applied_by', 'apply_result', "
                "'target_sku_id', 'apply_error_code', 'apply_error_message')"
            ),
            {"schema": schema},
        )
        assert missing_before.scalar_one() == 0

        await bootstrap(schema, database_url)

        await _assert_apply_audit_contract(async_session, schema)
    finally:
        await async_session.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await async_session.commit()


def test_u4_intake_routes_still_have_no_sku_write_surface():
    source = (BACKEND_DIR / "api" / "v1" / "intake.py").read_text(encoding="utf-8")

    forbidden = [
        "SKU(",
        "from models.sku",
        "import SKU",
        "ImportService",
        "apply_import",
        "sku_import",
        "skus/import",
        "intake_public",
        "public_token",
    ]
    for value in forbidden:
        assert value not in source, f"U4-I-B1 must not add SKU write/apply surface: {value}"
