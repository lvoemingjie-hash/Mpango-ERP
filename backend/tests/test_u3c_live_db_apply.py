"""U3-C-R1 DB-capable Apply Tests -- real tenant-schema apply path.

Tests that require a real PostgreSQL database (pytest --run-db).
Covers: success, skip duplicate, fail duplicate rollback, second apply
rejected, and no inventory/pricing writes.

Uses the async_session fixture from conftest.py (t_test schema).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Dict, List

import os

import pytest
import pytest_asyncio
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.import_run import ImportRun
from models.sku import SKU
from services.import_service import ImportService

TEST_TENANT_SCHEMA = os.environ.get("TEST_TENANT_SCHEMA", "t_test")
TEST_TENANT_ID = os.environ.get("TEST_TENANT_ID", "11111111-1111-1111-1111-111111111111")

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _valid_rows() -> List[Dict]:
    return [
        {"sku_code": "U3C-R1-001", "name": "DB Test Alpha"},
        {"sku_code": "U3C-R1-002", "name": "DB Test Beta"},
    ]


def _valid_mapping() -> Dict[str, str]:
    return {"sku_code": "sku_code", "name": "name"}


async def _create_validated_import_run(
    db: AsyncSession,
    import_id: str,
    rows: List[Dict] = None,
    field_mapping: Dict[str, str] = None,
) -> ImportRun:
    """Insert a validated ImportRun row directly into the DB."""
    if rows is None:
        rows = _valid_rows()
    if field_mapping is None:
        field_mapping = _valid_mapping()

    run = ImportRun(
        import_id=import_id,
        tenant_id=uuid.UUID(TEST_TENANT_ID),
        status="validated",
        source_filename="test.csv",
        source_encoding="utf-8",
        total_rows=len(rows),
        valid_rows=len(rows),
        error_rows=0,
        warning_rows=0,
        mapping={
            "columns": list(field_mapping.keys()),
            "rows": rows,
            "sample_rows": rows[:5],
            "field_mapping": field_mapping,
        },
    )
    db.add(run)
    await db.flush()
    return run


async def _count_skus(db: AsyncSession) -> int:
    """Count non-deleted SKUs in t_test schema."""
    result = await db.execute(
        select(SKU).where(SKU.is_deleted.is_(False))
    )
    return len(result.scalars().all())


async def _count_table(db: AsyncSession, table: str) -> int:
    """Count rows in a table via information_schema."""
    result = await db.execute(
        text(
            f"SELECT COUNT(*) FROM information_schema.tables "
            f"WHERE table_schema = '{TEST_TENANT_SCHEMA}' "
            f"AND table_name = '{table}'"
        )
    )
    return result.scalar()


async def _table_row_count(db: AsyncSession, table: str) -> int:
    """Count rows in a tenant-schema table."""
    result = await db.execute(
        text(f'SELECT COUNT(*) FROM "{TEST_TENANT_SCHEMA}"."{table}"')
    )
    return result.scalar()


# ---------------------------------------------------------------------------
# Fixture: ensure import_runs table exists (Alembic migration 022)
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(scope="function")
async def import_runs_table(async_session: AsyncSession):
    """Ensure import_runs table exists via Alembic migration 022."""
    # Run migration 022 inside t_test schema
    import importlib.util
    import os

    migrations_dir = os.path.join(
        os.path.dirname(__file__), "..", "alembic", "versions"
    )
    migration_path = os.path.join(migrations_dir, "022_import_runs.py")

    if os.path.exists(migration_path):
        spec = importlib.util.spec_from_file_location(
            "migration_022", migration_path
        )
        module = importlib.util.module_from_spec(spec)

        # Patch alembic.op for run_sync execution
        import alembic.op as _op

        class _FakeOp:
            @staticmethod
            def create_table(*args, **kwargs):
                pass

            @staticmethod
            def create_index(*args, **kwargs):
                pass

            @staticmethod
            def f(name):
                return name

        # Use a sync connection to run the migration
        conn = await async_session.connection()
        sync_conn = await conn.get_raw_connection()
        # Actually just check if table exists, create if not
        table_result = await async_session.execute(
            text(
                f"SELECT EXISTS (SELECT FROM information_schema.tables "
                f"WHERE table_schema = '{TEST_TENANT_SCHEMA}' "
                f"AND table_name = 'import_runs')"
            )
        )
        exists = table_result.scalar()

        if not exists:
            await async_session.execute(text(f"""
                CREATE TABLE "{TEST_TENANT_SCHEMA}".import_runs (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    import_id VARCHAR(64) NOT NULL UNIQUE,
                    tenant_id UUID NOT NULL,
                    status VARCHAR(32) NOT NULL DEFAULT 'previewed',
                    source_filename VARCHAR(255),
                    source_encoding VARCHAR(32),
                    total_rows INTEGER NOT NULL DEFAULT 0,
                    valid_rows INTEGER,
                    error_rows INTEGER,
                    warning_rows INTEGER,
                    mapping JSONB,
                    validation_result JSONB,
                    apply_result JSONB,
                    created_rows INTEGER DEFAULT 0,
                    skipped_rows INTEGER DEFAULT 0,
                    updated_rows INTEGER DEFAULT 0,
                    applied_by UUID,
                    applied_at TIMESTAMP WITH TIME ZONE,
                    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
                    deleted_at TIMESTAMP WITH TIME ZONE,
                    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """))
            await async_session.execute(text(f"""
                CREATE UNIQUE INDEX IF NOT EXISTS ux_import_runs_import_id
                ON "{TEST_TENANT_SCHEMA}".import_runs (import_id)
            """))
            await async_session.execute(text(f"""
                CREATE INDEX IF NOT EXISTS ix_import_runs_status
                ON "{TEST_TENANT_SCHEMA}".import_runs (status)
            """))
            await async_session.flush()

    yield

    # Cleanup
    await async_session.execute(
        text(f'DELETE FROM "{TEST_TENANT_SCHEMA}".import_runs')
    )
    await async_session.flush()


@pytest_asyncio.fixture(scope="function")
async def clean_skus(async_session: AsyncSession):
    """Ensure no pre-existing SKUs interfere with tests."""
    await async_session.execute(
        text(f'DELETE FROM "{TEST_TENANT_SCHEMA}".skus')
    )
    await async_session.flush()


# ====================================================================
# 1. Success path
# ====================================================================

class TestApplySuccess:
    """Happy path: apply validated import_run -> SKUs created in DB."""

    @pytest.mark.asyncio
    async def test_apply_creates_skus_in_db(
        self, async_session: AsyncSession, import_runs_table, clean_skus
    ):
        """Apply creates SKU rows in the tenant schema."""
        import_id = f"imp_{uuid.uuid4().hex[:20]}"
        rows = _valid_rows()
        await _create_validated_import_run(async_session, import_id, rows)

        svc = ImportService()
        result = await svc.apply(
            async_session,
            import_id=import_id,
            on_conflict="skip",
            applied_by=uuid.UUID(TEST_TENANT_ID),
        )
        await async_session.commit()

        assert result.status == "completed"
        assert result.created == 2
        assert result.skipped == 0
        assert result.errors == []

        # Verify SKU rows exist in DB
        stmt = select(SKU).where(SKU.is_deleted.is_(False))
        sku_res = await async_session.execute(stmt)
        skus = sku_res.scalars().all()
        sku_codes = {s.sku_code for s in skus}
        assert "U3C-R1-001" in sku_codes
        assert "U3C-R1-002" in sku_codes

        # Verify import_run status updated
        run_res = await async_session.execute(
            select(ImportRun).where(ImportRun.import_id == import_id)
        )
        run = run_res.scalar_one()
        assert run.status == "applied"
        assert run.created_rows == 2

    @pytest.mark.asyncio
    async def test_apply_single_sku(
        self, async_session: AsyncSession, import_runs_table, clean_skus
    ):
        """Apply with one row creates exactly one SKU."""
        import_id = f"imp_{uuid.uuid4().hex[:20]}"
        rows = [{"sku_code": "SINGLE-001", "name": "Solo"}]
        await _create_validated_import_run(async_session, import_id, rows)

        svc = ImportService()
        result = await svc.apply(
            async_session,
            import_id=import_id,
            on_conflict="skip",
            applied_by=uuid.UUID(TEST_TENANT_ID),
        )
        await async_session.commit()

        assert result.created == 1
        assert result.status == "completed"
        sku_count = await _count_skus(async_session)
        assert sku_count >= 1


# ====================================================================
# 2. Skip duplicate
# ====================================================================

class TestSkipDuplicate:
    """skip strategy: existing SKU code -> row skipped, no error."""

    @pytest.mark.asyncio
    async def test_skip_existing_sku_code(
        self, async_session: AsyncSession, import_runs_table, clean_skus
    ):
        """Pre-existing SKU is skipped, new SKU still created."""
        # Create a SKU directly
        existing = SKU(
            sku_code="EXIST-DB-001",
            name="Already Exists",
            unit="unit",
            is_active=True,
        )
        async_session.add(existing)
        await async_session.flush()

        import_id = f"imp_{uuid.uuid4().hex[:20]}"
        rows = [
            {"sku_code": "EXIST-DB-001", "name": "Duplicate"},
            {"sku_code": "NEW-DB-001", "name": "New One"},
        ]
        await _create_validated_import_run(async_session, import_id, rows)

        svc = ImportService()
        result = await svc.apply(
            async_session,
            import_id=import_id,
            on_conflict="skip",
            applied_by=uuid.UUID(TEST_TENANT_ID),
        )
        await async_session.commit()

        assert result.status == "completed"
        assert result.created == 1
        assert result.skipped == 1
        assert result.errors == []

        # Only NEW-DB-001 should exist in DB (EXIST-DB-001 was pre-existing)
        stmt = select(SKU.sku_code).where(SKU.is_deleted.is_(False))
        sku_res = await async_session.execute(stmt)
        codes = set(sku_res.scalars().all())
        assert "EXIST-DB-001" in codes
        assert "NEW-DB-001" in codes


# ====================================================================
# 3. Fail duplicate rollback
# ====================================================================

class TestFailDuplicate:
    """fail strategy: existing SKU code -> 409, no writes committed."""

    @pytest.mark.asyncio
    async def test_fail_on_existing_sku_rolls_back(
        self, async_session: AsyncSession, import_runs_table, clean_skus
    ):
        """Pre-existing SKU with on_conflict=fail -> 409, zero new SKUs."""
        existing = SKU(
            sku_code="EXIST-FAIL-001",
            name="Already There",
            unit="unit",
            is_active=True,
        )
        async_session.add(existing)
        await async_session.flush()

        import_id = f"imp_{uuid.uuid4().hex[:20]}"
        rows = [
            {"sku_code": "NEW-FAIL-001", "name": "Should Fail"},
            {"sku_code": "EXIST-FAIL-001", "name": "Conflict!"},
        ]
        await _create_validated_import_run(async_session, import_id, rows)

        # Count SKUs before
        skus_before = await _count_skus(async_session)

        svc = ImportService()
        with pytest.raises(Exception) as exc_info:
            await svc.apply(
                async_session,
                import_id=import_id,
                on_conflict="fail",
                applied_by=uuid.UUID(TEST_TENANT_ID),
            )
        err = str(exc_info.value).upper()
        assert "CONFLICT" in err

        # Rollback
        await async_session.rollback()

        # Verify no SKUs were added (count unchanged)
        # Need a fresh query
        stmt = select(SKU).where(SKU.is_deleted.is_(False))
        fresh_res = await async_session.execute(stmt)
        skus_after = len(fresh_res.scalars().all())
        assert skus_after == skus_before

        # import_run should NOT be applied
        run_res = await async_session.execute(
            select(ImportRun).where(ImportRun.import_id == import_id)
        )
        run = run_res.scalar_one()
        assert run.status != "applied"


# ====================================================================
# 4. Second apply rejected (duplicate apply)
# ====================================================================

class TestSecondApplyRejected:
    """After a successful apply, the second attempt is rejected (409)."""

    @pytest.mark.asyncio
    async def test_second_apply_returns_409(
        self, async_session: AsyncSession, import_runs_table, clean_skus
    ):
        """First apply succeeds, second apply on same import_id -> 409."""
        import_id = f"imp_{uuid.uuid4().hex[:20]}"
        rows = _valid_rows()
        await _create_validated_import_run(async_session, import_id, rows)

        svc = ImportService()
        # First apply
        result1 = await svc.apply(
            async_session,
            import_id=import_id,
            on_conflict="skip",
            applied_by=uuid.UUID(TEST_TENANT_ID),
        )
        await async_session.commit()
        assert result1.status == "completed"
        assert result1.created == 2

        # Second apply -- should be rejected
        with pytest.raises(Exception) as exc_info:
            await svc.apply(
                async_session,
                import_id=import_id,
                on_conflict="skip",
                applied_by=uuid.UUID(TEST_TENANT_ID),
            )
        err = str(exc_info.value).upper()
        assert "INVALID_STATUS" in err

        # Rollback the failed attempt
        await async_session.rollback()


# ====================================================================
# 5. No inventory/pricing writes
# ====================================================================

class TestNoSideEffectWrites:
    """Apply must not touch inventory_stocks or retailer_prices tables."""

    @pytest.mark.asyncio
    async def test_apply_does_not_write_inventory(
        self, async_session: AsyncSession, import_runs_table, clean_skus
    ):
        """After apply, inventory_stocks should have no new rows from import."""
        # Get baseline inventory count
        inv_before = await _table_row_count(async_session, "inventory_stocks")

        import_id = f"imp_{uuid.uuid4().hex[:20]}"
        await _create_validated_import_run(async_session, import_id, _valid_rows())

        svc = ImportService()
        result = await svc.apply(
            async_session,
            import_id=import_id,
            on_conflict="skip",
            applied_by=uuid.UUID(TEST_TENANT_ID),
        )
        await async_session.commit()
        assert result.created == 2

        inv_after = await _table_row_count(async_session, "inventory_stocks")
        assert inv_after == inv_before, (
            f"inventory_stocks changed: {inv_before} -> {inv_after}"
        )

    @pytest.mark.asyncio
    async def test_apply_does_not_write_pricing(
        self, async_session: AsyncSession, import_runs_table, clean_skus
    ):
        """After apply, retailer_prices should have no new rows from import."""
        price_before = await _table_row_count(async_session, "retailer_prices")

        import_id = f"imp_{uuid.uuid4().hex[:20]}"
        await _create_validated_import_run(async_session, import_id, _valid_rows())

        svc = ImportService()
        result = await svc.apply(
            async_session,
            import_id=import_id,
            on_conflict="skip",
            applied_by=uuid.UUID(TEST_TENANT_ID),
        )
        await async_session.commit()
        assert result.created == 2

        price_after = await _table_row_count(async_session, "retailer_prices")
        assert price_after == price_before, (
            f"retailer_prices changed: {price_before} -> {price_after}"
        )

    @pytest.mark.asyncio
    async def test_apply_no_cross_table_contamination(
        self, async_session: AsyncSession, import_runs_table, clean_skus
    ):
        """Apply only creates SKU rows; no other table is touched."""
        inv_before = await _table_row_count(async_session, "inventory_stocks")
        price_before = await _table_row_count(async_session, "retailer_prices")
        skus_before = await _count_skus(async_session)

        import_id = f"imp_{uuid.uuid4().hex[:20]}"
        await _create_validated_import_run(async_session, import_id, _valid_rows())

        svc = ImportService()
        result = await svc.apply(
            async_session,
            import_id=import_id,
            on_conflict="skip",
            applied_by=uuid.UUID(TEST_TENANT_ID),
        )
        await async_session.commit()
        assert result.created == 2

        inv_after = await _table_row_count(async_session, "inventory_stocks")
        price_after = await _table_row_count(async_session, "retailer_prices")
        skus_after = await _count_skus(async_session)

        assert inv_after == inv_before
        assert price_after == price_before
        assert skus_after == skus_before + 2, (
            f"Expected {skus_before + 2} SKUs, got {skus_after}"
        )
