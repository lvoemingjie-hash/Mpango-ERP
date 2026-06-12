"""U3-B2.2 Live DB Validation -- preview + validate against real PostgreSQL.

Tests that U3-B1/U3-B2 import preview/validate works against a real database,
using the ACTUAL 022_import_runs migration (not a hand-crafted helper table).

Environment requirements:
- Docker PostgreSQL running on localhost:5432
- POSTGRES_HOST=127.0.0.1 (or set TEST_DATABASE_URL)
- t_test schema must exist (conftest bootstraps it)

If environment is unavailable, all tests report BLOCKED_ENVIRONMENT.
"""
from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import AsyncSession

# -- Environment gate --------------------------------------------------------
os.environ.setdefault("MPANGO_ENV", "test")


# =====================================================================
# Helpers
# =====================================================================

TEST_TENANT_SCHEMA = os.environ.get("TEST_TENANT_SCHEMA", "t_test")
TEST_TENANT_ID = os.environ.get("TEST_TENANT_ID", "11111111-1111-1111-1111-111111111111")


async def _run_022_upgrade(session: AsyncSession, schema: str) -> None:
    """Execute the real 022_import_runs migration upgrade against the DB.

    Sets search_path to the tenant schema, then executes the migration's
    upgrade() within SQLAlchemy's run_sync context (required because
    Alembic's op API is synchronous but our engine uses asyncpg).
    """
    import importlib.util
    from pathlib import Path
    from alembic import op
    from alembic.runtime.migration import MigrationContext
    from alembic.operations import Operations

    # Set search_path to tenant schema so the migration's tenant guard passes
    await session.execute(
        text(f'SET search_path TO "{schema}", public')
    )
    await session.commit()

    # Load migration module from file
    backend_dir = Path(__file__).resolve().parent.parent
    migration_file = backend_dir / "alembic" / "versions" / "022_import_runs.py"
    spec = importlib.util.spec_from_file_location("migration_022", migration_file)
    migration_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration_mod)

    def _run_upgrade_sync(sync_conn):
        """Sync callback that runs the migration's upgrade()."""
        migration_context = MigrationContext.configure(sync_conn)
        operations = Operations(migration_context)

        # Patch op module so the migration's op calls work
        _saved = {}
        for name in ('create_table', 'create_index', 'drop_table', 'get_bind'):
            _saved[name] = getattr(op, name, None)

        op.get_bind = lambda: sync_conn
        op.create_table = operations.create_table
        op.create_index = operations.create_index
        op.drop_table = operations.drop_table

        try:
            migration_mod.upgrade()
        finally:
            for name, orig in _saved.items():
                if orig is not None:
                    setattr(op, name, orig)

    # Execute the sync migration function via SQLAlchemy's run_sync
    async_conn = await session.connection()
    await async_conn.run_sync(_run_upgrade_sync)
    await session.commit()


async def _count_table(session: AsyncSession, schema: str, table: str) -> int:
    """Count rows in a table within a schema."""
    result = await session.execute(
        text(f'SELECT COUNT(*) FROM "{schema}".{table}')
    )
    return result.scalar()


async def _table_exists(session: AsyncSession, schema: str, table: str) -> bool:
    """Check if table exists in schema."""
    result = await session.execute(text(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = :schema AND table_name = :table"
    ), {"schema": schema, "table": table})
    return result.first() is not None


async def _column_exists(session: AsyncSession, schema: str, table: str, column: str) -> bool:
    """Check if column exists in table."""
    result = await session.execute(text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_schema = :schema AND table_name = :table AND column_name = :col"
    ), {"schema": schema, "table": table, "col": column})
    return result.first() is not None


# =====================================================================
# 1. Migration Smoke: real 022 migration creates import_runs
# =====================================================================

class TestMigrationSmoke:
    """Verify real 022_import_runs migration creates correct table."""

    @pytest.mark.asyncio
    async def test_022_migration_creates_import_runs(self, async_session):
        """Running 022 upgrade must create import_runs in t_test schema."""
        # Ensure clean state
        await async_session.execute(text(
            f'DROP TABLE IF EXISTS "{TEST_TENANT_SCHEMA}".import_runs CASCADE'
        ))
        await async_session.commit()

        await _run_022_upgrade(async_session, TEST_TENANT_SCHEMA)

        assert await _table_exists(async_session, TEST_TENANT_SCHEMA, "import_runs"), (
            "022 migration must create import_runs table in t_test schema"
        )

    @pytest.mark.asyncio
    async def test_022_migration_includes_audit_columns(self, async_session):
        """022 migration must include is_deleted and deleted_at (AuditMixin)."""
        await _run_022_upgrade(async_session, TEST_TENANT_SCHEMA)

        assert await _column_exists(
            async_session, TEST_TENANT_SCHEMA, "import_runs", "is_deleted"
        ), "is_deleted column missing from migration-created import_runs"
        assert await _column_exists(
            async_session, TEST_TENANT_SCHEMA, "import_runs", "deleted_at"
        ), "deleted_at column missing from migration-created import_runs"

    @pytest.mark.asyncio
    async def test_022_migration_all_orm_columns_present(self, async_session):
        """All ImportRun ORM columns must exist after 022 migration runs."""
        await _run_022_upgrade(async_session, TEST_TENANT_SCHEMA)

        expected = [
            "id", "import_id", "tenant_id", "status",
            "source_filename", "source_encoding", "total_rows",
            "valid_rows", "error_rows", "warning_rows",
            "mapping", "validation_result", "apply_result",
            "created_rows", "skipped_rows", "updated_rows",
            "applied_by", "applied_at", "created_at", "updated_at",
            "is_deleted", "deleted_at",
        ]
        for col in expected:
            assert await _column_exists(
                async_session, TEST_TENANT_SCHEMA, "import_runs", col
            ), f"Column '{col}' missing from migration-created import_runs"

    @pytest.mark.asyncio
    async def test_import_runs_not_in_public_schema(self, async_session):
        """public schema must NOT have import_runs (tenant-only table)."""
        has_it = await _table_exists(async_session, "public", "import_runs")
        assert not has_it, "import_runs must NOT exist in public schema"


# =====================================================================
# 2. Preview Live DB Smoke
# =====================================================================

class TestPreviewLiveDB:
    """Verify ImportService.preview writes to migration-created import_runs."""

    @pytest.mark.asyncio
    async def test_preview_creates_import_run(self, async_session):
        """preview() must INSERT one row into migration-created import_runs."""
        await _run_022_upgrade(async_session, TEST_TENANT_SCHEMA)
        from services.import_service import ImportService

        csv_bytes = b"sku_code,name,unit\nSKU-001,Widget,pcs\nSKU-002,Gadget,pcs\n"
        tenant_uuid = uuid.UUID(TEST_TENANT_ID)

        result = await ImportService().preview(
            async_session,
            tenant_id=tenant_uuid,
            filename="test_preview.csv",
            file_bytes=csv_bytes,
        )
        await async_session.commit()

        # Verify DB state
        db_result = await async_session.execute(
            text(f'SELECT import_id, status, total_rows, mapping '
                 f'FROM "{TEST_TENANT_SCHEMA}".import_runs '
                 f'WHERE import_id = :iid'),
            {"iid": result.import_id},
        )
        row = db_result.first()
        assert row is not None, "import_runs row must exist after preview"
        assert row[1] == "previewed", f"Expected status=previewed, got {row[1]}"
        assert row[2] == 2, f"Expected total_rows=2, got {row[2]}"
        assert "rows" in row[3], "mapping must contain 'rows' key"
        assert len(row[3]["rows"]) == 2
        assert result.import_id.startswith("imp_")

    @pytest.mark.asyncio
    async def test_preview_utf8_sig_bom_live(self, async_session):
        """preview with UTF-8-sig BOM must succeed against real DB."""
        await _run_022_upgrade(async_session, TEST_TENANT_SCHEMA)
        from services.import_service import ImportService

        csv_bytes = b"\xef\xbb\xbfsku_code,name\nBOM-001,TestItem\n"
        result = await ImportService().preview(
            async_session,
            tenant_id=uuid.UUID(TEST_TENANT_ID),
            filename="bom_test.csv",
            file_bytes=csv_bytes,
        )
        await async_session.commit()

        db_result = await async_session.execute(
            text(f'SELECT mapping FROM "{TEST_TENANT_SCHEMA}".import_runs '
                 f'WHERE import_id = :iid'),
            {"iid": result.import_id},
        )
        mapping = db_result.scalar()
        assert mapping["rows"][0]["sku_code"] == "BOM-001"

    @pytest.mark.asyncio
    async def test_preview_response_sample_rows_only_5(self, async_session):
        """preview response must return only 5 sample_rows even with 7 rows."""
        await _run_022_upgrade(async_session, TEST_TENANT_SCHEMA)
        from services.import_service import ImportService

        csv_bytes = b"sku_code,name\n" + b"\n".join(
            f"SKU-{i:03d},Item {i}".encode() for i in range(1, 8)
        )
        result = await ImportService().preview(
            async_session,
            tenant_id=uuid.UUID(TEST_TENANT_ID),
            filename="7rows.csv",
            file_bytes=csv_bytes,
        )
        await async_session.commit()

        assert len(result.sample_rows) == 5, "Response must have 5 sample_rows"
        assert result.source.row_count == 7, "row_count must be 7"

        # DB mapping must have full 7 rows
        db_result = await async_session.execute(
            text(f'SELECT mapping FROM "{TEST_TENANT_SCHEMA}".import_runs '
                 f'WHERE import_id = :iid'),
            {"iid": result.import_id},
        )
        mapping = db_result.scalar()
        assert len(mapping["rows"]) == 7, "DB mapping.rows must have all 7 rows"


# =====================================================================
# 3. Validate Live DB Smoke
# =====================================================================

class TestValidateLiveDB:
    """Verify ImportService.validate updates migration-created import_runs."""

    @pytest.mark.asyncio
    async def test_validate_updates_import_run_status(self, async_session):
        """validate() must update import_runs status to validated."""
        await _run_022_upgrade(async_session, TEST_TENANT_SCHEMA)
        from services.import_service import ImportService

        csv_bytes = b"sku_code,name\nSKU-001,Widget\nSKU-002,Gadget\n"
        preview_result = await ImportService().preview(
            async_session,
            tenant_id=uuid.UUID(TEST_TENANT_ID),
            filename="val_test.csv",
            file_bytes=csv_bytes,
        )
        await async_session.commit()

        validate_result = await ImportService().validate(
            async_session,
            import_id=preview_result.import_id,
            mapping={"sku_code": "sku_code", "name": "name"},
        )
        await async_session.commit()

        assert validate_result.status in ("validated", "needs_review")
        assert validate_result.valid_rows == 2
        assert validate_result.error_rows == 0

        # Verify DB state
        db_result = await async_session.execute(
            text(f'SELECT status, valid_rows, error_rows, validation_result '
                 f'FROM "{TEST_TENANT_SCHEMA}".import_runs '
                 f'WHERE import_id = :iid'),
            {"iid": preview_result.import_id},
        )
        row = db_result.first()
        assert row[0] == "validated"
        assert row[1] == 2
        assert row[2] == 0
        assert row[3] is not None

    @pytest.mark.asyncio
    async def test_validate_6_row_csv_catches_row_6_error(self, async_session):
        """6-row CSV with row 6 missing required field -- validate must catch it."""
        await _run_022_upgrade(async_session, TEST_TENANT_SCHEMA)
        from services.import_service import ImportService

        rows_csv = b"sku_code,name\n" + b"\n".join(
            f"SKU-{i:03d},Item {i}".encode() for i in range(1, 6)
        ) + b"\n,Empty Name\n"

        preview_result = await ImportService().preview(
            async_session,
            tenant_id=uuid.UUID(TEST_TENANT_ID),
            filename="6rows_err.csv",
            file_bytes=rows_csv,
        )
        await async_session.commit()

        validate_result = await ImportService().validate(
            async_session,
            import_id=preview_result.import_id,
            mapping={"sku_code": "sku_code", "name": "name"},
        )
        await async_session.commit()

        assert validate_result.status == "needs_review"
        assert validate_result.error_rows == 1
        assert validate_result.valid_rows == 5
        row6_errors = [e for e in validate_result.errors if e.row == 6]
        assert len(row6_errors) >= 1, "Row 6 must have error"

    @pytest.mark.asyncio
    async def test_validate_duplicate_sku_detected_live(self, async_session):
        """Intra-file duplicate sku_code must be detected against real DB."""
        await _run_022_upgrade(async_session, TEST_TENANT_SCHEMA)
        from services.import_service import ImportService

        csv_bytes = b"sku_code,name\nSKU-DUP,First\nSKU-DUP,Second\nSKU-UNIQ,Third\n"
        preview_result = await ImportService().preview(
            async_session,
            tenant_id=uuid.UUID(TEST_TENANT_ID),
            filename="dup_test.csv",
            file_bytes=csv_bytes,
        )
        await async_session.commit()

        validate_result = await ImportService().validate(
            async_session,
            import_id=preview_result.import_id,
            mapping={"sku_code": "sku_code", "name": "name"},
        )
        await async_session.commit()

        assert validate_result.status == "needs_review"
        assert any("Duplicate" in e.message for e in validate_result.errors)


# =====================================================================
# 4. No SKU Writes Verification
# =====================================================================

class TestNoSkuWrites:
    """Verify preview/validate never write to skus/inventory/pricing."""

    @pytest.mark.asyncio
    async def test_preview_does_not_write_skus(self, async_session):
        """SKU count must be unchanged after preview."""
        await _run_022_upgrade(async_session, TEST_TENANT_SCHEMA)

        sku_count_before = await _count_table(async_session, TEST_TENANT_SCHEMA, "skus")

        from services.import_service import ImportService
        csv_bytes = b"sku_code,name\nNEW-001,NewItem\nNEW-002,AnotherItem\n"
        await ImportService().preview(
            async_session,
            tenant_id=uuid.UUID(TEST_TENANT_ID),
            filename="no_write.csv",
            file_bytes=csv_bytes,
        )
        await async_session.commit()

        sku_count_after = await _count_table(async_session, TEST_TENANT_SCHEMA, "skus")
        assert sku_count_after == sku_count_before, (
            f"SKU count changed: {sku_count_before} -> {sku_count_after}"
        )

    @pytest.mark.asyncio
    async def test_validate_does_not_write_skus(self, async_session):
        """SKU count must be unchanged after validate."""
        await _run_022_upgrade(async_session, TEST_TENANT_SCHEMA)

        from services.import_service import ImportService
        csv_bytes = b"sku_code,name\nV-001,ValItem\n"
        preview_result = await ImportService().preview(
            async_session,
            tenant_id=uuid.UUID(TEST_TENANT_ID),
            filename="val_no_write.csv",
            file_bytes=csv_bytes,
        )
        await async_session.commit()

        sku_count_before = await _count_table(async_session, TEST_TENANT_SCHEMA, "skus")

        await ImportService().validate(
            async_session,
            import_id=preview_result.import_id,
            mapping={"sku_code": "sku_code", "name": "name"},
        )
        await async_session.commit()

        sku_count_after = await _count_table(async_session, TEST_TENANT_SCHEMA, "skus")
        assert sku_count_after == sku_count_before

    @pytest.mark.asyncio
    async def test_inventory_and_pricing_unchanged(self, async_session):
        """inventory_stocks and retailer_prices counts unchanged."""
        await _run_022_upgrade(async_session, TEST_TENANT_SCHEMA)

        inv_before = await _count_table(async_session, TEST_TENANT_SCHEMA, "inventory_stocks")
        price_before = await _count_table(async_session, TEST_TENANT_SCHEMA, "retailer_prices")

        from services.import_service import ImportService
        csv_bytes = b"sku_code,name\nIP-001,TestItem\n"
        preview_result = await ImportService().preview(
            async_session,
            tenant_id=uuid.UUID(TEST_TENANT_ID),
            filename="inv_check.csv",
            file_bytes=csv_bytes,
        )
        await async_session.commit()

        await ImportService().validate(
            async_session,
            import_id=preview_result.import_id,
            mapping={"sku_code": "sku_code", "name": "name"},
        )
        await async_session.commit()

        inv_after = await _count_table(async_session, TEST_TENANT_SCHEMA, "inventory_stocks")
        price_after = await _count_table(async_session, TEST_TENANT_SCHEMA, "retailer_prices")
        assert inv_after == inv_before, f"inventory count changed: {inv_before} -> {inv_after}"
        assert price_after == price_before, f"pricing count changed: {price_before} -> {price_after}"


# =====================================================================
# 5. Full Roundtrip (preview -> validate -> DB check)
# =====================================================================

class TestFullRoundtrip:
    """End-to-end preview + validate with full DB verification."""

    @pytest.mark.asyncio
    async def test_complete_import_pipeline(self, async_session):
        """Full preview->validate pipeline with 6-row CSV, verify all DB state."""
        await _run_022_upgrade(async_session, TEST_TENANT_SCHEMA)
        from services.import_service import ImportService

        # 6 rows: rows 1-5 valid, row 6 has duplicate sku_code of row 1 AND empty name
        csv_bytes = (
            b"sku_code,name\n"
            b"SKU-001,Item 1\n"
            b"SKU-002,Item 2\n"
            b"SKU-003,Item 3\n"
            b"SKU-004,Item 4\n"
            b"SKU-005,Item 5\n"
            b"SKU-001,\n"  # row 6: duplicate + empty name
        )

        # Phase 1: Preview
        preview_result = await ImportService().preview(
            async_session,
            tenant_id=uuid.UUID(TEST_TENANT_ID),
            filename="roundtrip.csv",
            file_bytes=csv_bytes,
        )
        await async_session.commit()

        import_id = preview_result.import_id
        assert preview_result.source.row_count == 6
        assert len(preview_result.sample_rows) == 5

        # Verify preview DB state
        db_row = await async_session.execute(
            text(f'SELECT status, total_rows, mapping '
                 f'FROM "{TEST_TENANT_SCHEMA}".import_runs WHERE import_id = :iid'),
            {"iid": import_id},
        )
        row = db_row.first()
        assert row[0] == "previewed"
        assert row[1] == 6
        assert len(row[2]["rows"]) == 6

        # Phase 2: Validate
        validate_result = await ImportService().validate(
            async_session,
            import_id=import_id,
            mapping={"sku_code": "sku_code", "name": "name"},
        )
        await async_session.commit()

        # Row 6 has: empty name (error) + duplicate sku_code (error) = 1 error_row
        assert validate_result.status == "needs_review"
        assert validate_result.error_rows == 1, (
            f"Expected error_rows=1, got {validate_result.error_rows}"
        )
        assert validate_result.valid_rows == 5

        # Verify validate DB state
        db_row2 = await async_session.execute(
            text(f'SELECT status, valid_rows, error_rows, validation_result '
                 f'FROM "{TEST_TENANT_SCHEMA}".import_runs WHERE import_id = :iid'),
            {"iid": import_id},
        )
        row2 = db_row2.first()
        assert row2[0] == "needs_review"
        assert row2[1] == 5
        assert row2[2] == 1
        val_result = row2[3]
        assert "errors" in val_result
        assert "warnings" in val_result

        # Row 6 must have 2 error details (missing name + duplicate sku)
        row6_errors = [e for e in validate_result.errors if e.row == 6]
        assert len(row6_errors) == 2, (
            f"Row 6 should have 2 error details, got {len(row6_errors)}"
        )
