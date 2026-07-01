"""U4-C Data Intake backend schema skeleton contract tests.

These tests keep U4-C scoped to the CTO-approved four tenant tables only:
intake_workspaces, intake_uploads, intake_product_rows, and
intake_validation_issues.
"""
from __future__ import annotations

import importlib.util
import os
import uuid
from pathlib import Path

import pytest
from alembic import op
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


TEST_TENANT_SCHEMA = "t_test"

INTAKE_TABLES = {
    "intake_workspaces",
    "intake_uploads",
    "intake_product_rows",
    "intake_validation_issues",
}

FORBIDDEN_U4C_TABLES = {"intake_assets", "intake_exports", "intake_public_tokens"}
INTAKE_INDEXES = {
    "ix_intake_workspaces_tenant_id",
    "ix_intake_workspaces_status",
    "ix_intake_workspaces_created_at",
    "ix_intake_uploads_workspace_id",
    "ix_intake_uploads_tenant_id",
    "ix_intake_product_rows_workspace_id",
    "ix_intake_product_rows_upload_order",
    "ix_intake_product_rows_review_status",
    "ix_intake_validation_issues_workspace_id",
    "ix_intake_validation_issues_row_id",
    "ix_intake_validation_issues_severity",
}


async def _drop_intake_tables(session: AsyncSession, schema: str) -> None:
    for table in sorted(INTAKE_TABLES | FORBIDDEN_U4C_TABLES):
        await session.execute(text(f'DROP TABLE IF EXISTS "{schema}".{table} CASCADE'))
    await session.execute(text('DROP TABLE IF EXISTS public.intake_public_tokens CASCADE'))
    await session.commit()


async def _run_024_upgrade(session: AsyncSession, schema: str) -> None:
    await session.execute(text(f'SET search_path TO "{schema}", public'))
    await session.commit()

    backend_dir = Path(__file__).resolve().parent.parent
    migration_file = backend_dir / "alembic" / "versions" / "024_intake_skeleton.py"
    spec = importlib.util.spec_from_file_location("migration_024", migration_file)
    migration_mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(migration_mod)

    def _run_upgrade_sync(sync_conn):
        migration_context = MigrationContext.configure(sync_conn)
        operations = Operations(migration_context)
        saved = {name: getattr(op, name, None) for name in ("create_table", "create_index", "drop_table", "get_bind")}
        op.get_bind = lambda: sync_conn
        op.create_table = operations.create_table
        op.create_index = operations.create_index
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


async def _table_exists(session: AsyncSession, schema: str, table: str) -> bool:
    result = await session.execute(
        text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = :schema AND table_name = :table"
        ),
        {"schema": schema, "table": table},
    )
    return result.first() is not None


async def _column_exists(session: AsyncSession, schema: str, table: str, column: str) -> bool:
    result = await session.execute(
        text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = :schema AND table_name = :table AND column_name = :column"
        ),
        {"schema": schema, "table": table, "column": column},
    )
    return result.first() is not None


async def _intake_tables(session: AsyncSession, schema: str) -> set[str]:
    result = await session.execute(
        text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = :schema AND table_name LIKE 'intake_%'"
        ),
        {"schema": schema},
    )
    return set(result.scalars().all())


async def _index_exists(session: AsyncSession, schema: str, index_name: str) -> bool:
    result = await session.execute(
        text("SELECT 1 FROM pg_indexes WHERE schemaname = :schema AND indexname = :index_name"),
        {"schema": schema, "index_name": index_name},
    )
    return result.first() is not None


@pytest.mark.asyncio
async def test_024_migration_creates_exact_four_intake_tables(async_session):
    await _drop_intake_tables(async_session, TEST_TENANT_SCHEMA)

    await _run_024_upgrade(async_session, TEST_TENANT_SCHEMA)

    for table in INTAKE_TABLES:
        assert await _table_exists(async_session, TEST_TENANT_SCHEMA, table), f"Missing {table}"
    for table in FORBIDDEN_U4C_TABLES:
        assert not await _table_exists(async_session, TEST_TENANT_SCHEMA, table), f"Forbidden U4-C table exists: {table}"
    assert not await _table_exists(async_session, "public", "intake_public_tokens")


@pytest.mark.asyncio
async def test_024_migration_tables_include_tenant_and_audit_columns(async_session):
    await _run_024_upgrade(async_session, TEST_TENANT_SCHEMA)

    for table in INTAKE_TABLES:
        for column in ("id", "tenant_id", "created_at", "updated_at", "is_deleted", "deleted_at"):
            assert await _column_exists(async_session, TEST_TENANT_SCHEMA, table, column), (
                f"{table}.{column} missing"
            )


@pytest.mark.asyncio
async def test_024_migration_does_not_create_public_intake_tables(async_session):
    await _run_024_upgrade(async_session, TEST_TENANT_SCHEMA)

    for table in INTAKE_TABLES | FORBIDDEN_U4C_TABLES:
        assert not await _table_exists(async_session, "public", table), f"public.{table} must not exist"


def test_intake_models_export_exact_four_classes():
    from models import IntakeProductRow, IntakeUpload, IntakeValidationIssue, IntakeWorkspace

    assert IntakeWorkspace.__tablename__ == "intake_workspaces"
    assert IntakeUpload.__tablename__ == "intake_uploads"
    assert IntakeProductRow.__tablename__ == "intake_product_rows"
    assert IntakeValidationIssue.__tablename__ == "intake_validation_issues"


def test_bootstrap_mentions_only_u4c_intake_tables():
    source = (Path(__file__).resolve().parents[1] / "scripts" / "bootstrap_tenant_schema.py").read_text(
        encoding="utf-8"
    )

    for table in INTAKE_TABLES:
        assert table in source
    for table in FORBIDDEN_U4C_TABLES:
        assert table not in source


@pytest.mark.asyncio
async def test_bootstrap_reconciles_missing_intake_tables_and_indexes(async_session):
    from scripts.bootstrap_tenant_schema import bootstrap

    schema = f"t_u4c_r1_{uuid.uuid4().hex[:8]}"
    database_url = os.environ["DATABASE_URL"]

    await async_session.execute(text(f'CREATE SCHEMA "{schema}"'))
    for table in sorted(INTAKE_TABLES | FORBIDDEN_U4C_TABLES):
        await async_session.execute(text(f'DROP TABLE IF EXISTS "{schema}".{table} CASCADE'))
    await async_session.execute(text('DROP TABLE IF EXISTS public.intake_public_tokens CASCADE'))
    await async_session.commit()

    try:
        assert await _intake_tables(async_session, schema) == set()

        await bootstrap(schema, database_url)

        assert await _intake_tables(async_session, schema) == INTAKE_TABLES
        for table in INTAKE_TABLES:
            assert await _table_exists(async_session, schema, table), f"Missing bootstrapped table {table}"
        for table in FORBIDDEN_U4C_TABLES:
            assert not await _table_exists(async_session, schema, table), f"Forbidden table exists: {table}"
        assert not await _table_exists(async_session, "public", "intake_public_tokens")
        for index_name in INTAKE_INDEXES:
            assert await _index_exists(async_session, schema, index_name), f"Missing bootstrapped index {index_name}"
    finally:
        await async_session.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await async_session.commit()
