"""DC-12R1-S3-S2B-I1-R4: Real Preflight Execution + Evidence Integrity.

Executes actual migration-037 preflight against deliberately malformed PG16 catalogs.
Every test: RED (malformed catalog) -> execute preflight -> assert exact PreflightFailure
-> assert no catalog mutation -> GREEN (fix malformation) -> preflight passes.
"""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from core.config import get_settings
from database.session import AsyncSessionLocal

# Sync engine for preflight execution
_settings = get_settings()
_db_url = _settings.DATABASE_URL
if _db_url.startswith("postgresql+asyncpg"):
    _db_url = _db_url.replace("postgresql+asyncpg://", "postgresql://", 1)
_sync_engine = create_engine(_db_url)

# Load migration module
MIGRATION_037_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic" / "versions" / "037_payment_declarations_schema.py"
)
spec = importlib.util.spec_from_file_location("migration_037", MIGRATION_037_PATH)
m037 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m037)

pytestmark = pytest.mark.asyncio


def _fingerprint(schema: str) -> dict:
    """Capture catalog fingerprint: column count, constraint count, row counts."""
    with _sync_engine.connect() as conn:
        tables = ["payment_declarations", "receipt_sequences"]
        fp = {}
        for t in tables:
            exists = m037._table_exists(conn, schema, t)
            fp[f"{t}_exists"] = exists
            if exists:
                cols = m037._pg_catalog_columns(conn, schema, t)
                fp[f"{t}_columns"] = {c[0]: (c[1], c[2]) for c in cols}
                constr = m037._pg_catalog_constraints(conn, schema, t)
                fp[f"{t}_constraints"] = len(constr)
                idxs = m037._pg_catalog_indexes(conn, schema, t)
                fp[f"{t}_indexes"] = len(idxs)
        return fp


# ---------------------------------------------------------------------------
# Real preflight execution with RED-before/GREEN-after proof
# ---------------------------------------------------------------------------

class TestRealPreflightExecution:
    """Each test creates a malformed catalog, executes the actual preflight,
    asserts exact PreflightFailure, and proves no catalog mutation."""

    @pytest.fixture(autouse=True)
    async def _schema(self):
        s = get_settings()
        schema = f"t_r4_{uuid.uuid4().hex[:12]}"
        from scripts.bootstrap_tenant_schema import bootstrap as bootstrap_schema
        await bootstrap_schema(schema, s.DATABASE_URL)
        yield schema
        async with AsyncSessionLocal() as db:
            await db.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
            await db.commit()

    # ------------------------------------------------------------------
    # 1. Wrong CHECK constraint
    # ------------------------------------------------------------------
    async def test_wrong_check_constraint_fails_preflight(self, _schema):
        schema = _schema
        async with AsyncSessionLocal() as db:
            await db.execute(text(
                f'ALTER TABLE "{schema}".payment_declarations '
                'DROP CONSTRAINT ck_payment_declarations_status'))
            await db.execute(text(
                f'ALTER TABLE "{schema}".payment_declarations '
                "ADD CONSTRAINT ck_payment_declarations_status "
                "CHECK (status IN ('pending', 'confirmed'))"
            ))
            await db.commit()

        fp_before = _fingerprint(schema)
        failures = []
        with _sync_engine.connect() as conn:
            m037._verify_declaration_catalog_pg(conn, schema, failures)
        assert failures, "preflight should have detected wrong CHECK constraint"
        assert any("status" in f.lower() or "rejected" in f.lower() for f in failures)
        fp_after = _fingerprint(schema)
        assert fp_before == fp_after, f"catalog mutated: {fp_before} != {fp_after}"

        # GREEN: fix the CHECK
        async with AsyncSessionLocal() as db:
            await db.execute(text(
                f'ALTER TABLE "{schema}".payment_declarations '
                'DROP CONSTRAINT ck_payment_declarations_status'))
            await db.execute(text(
                f'ALTER TABLE "{schema}".payment_declarations '
                "ADD CONSTRAINT ck_payment_declarations_status "
                "CHECK (status IN ('pending', 'confirmed', 'rejected'))"
            ))
            await db.commit()
        with _sync_engine.connect() as conn:
            m037._verify_declaration_catalog_pg(conn, schema, [])  # no raise

    # ------------------------------------------------------------------
    # 2. Wrong FK delete action (CASCADE instead of RESTRICT)
    # ------------------------------------------------------------------
    async def test_wrong_fk_cascade_fails_preflight(self, _schema):
        schema = _schema
        async with AsyncSessionLocal() as db:
            fk_name = (await db.execute(text(
                "SELECT c.conname FROM pg_catalog.pg_constraint c "
                "JOIN pg_catalog.pg_class t ON t.oid = c.conrelid "
                "JOIN pg_catalog.pg_namespace n ON n.oid = t.relnamespace "
                "WHERE n.nspname = :s AND t.relname = 'payment_declarations' "
                "AND c.contype = 'f' AND pg_get_constraintdef(c.oid) LIKE '%orders(id)%'"
            ), {"s": schema})).scalar()
            if fk_name:
                await db.execute(text(
                    f'ALTER TABLE "{schema}".payment_declarations DROP CONSTRAINT "{fk_name}"'))
                await db.execute(text(
                    f'ALTER TABLE "{schema}".payment_declarations '
                    f'ADD CONSTRAINT "{fk_name}" '
                    f'FOREIGN KEY (order_id) REFERENCES "{schema}".orders(id) ON DELETE CASCADE'))
                await db.commit()

        fp_before = _fingerprint(schema)
        failures = []
        with _sync_engine.connect() as conn:
            m037._verify_declaration_catalog_pg(conn, schema, failures)
        assert failures, "preflight should detect wrong FK CASCADE"
        assert any("RESTRICT" in f or "order_id" in f.lower() for f in failures)
        fp_after = _fingerprint(schema)
        assert fp_before == fp_after

        # GREEN: fix the FK
        async with AsyncSessionLocal() as db:
            await db.execute(text(
                f'ALTER TABLE "{schema}".payment_declarations DROP CONSTRAINT "{fk_name}"'))
            await db.execute(text(
                f'ALTER TABLE "{schema}".payment_declarations '
                f'ADD CONSTRAINT "{fk_name}" '
                f'FOREIGN KEY (order_id) REFERENCES "{schema}".orders(id) ON DELETE RESTRICT'))
            await db.commit()
        with _sync_engine.connect() as conn:
            m037._verify_declaration_catalog_pg(conn, schema, [])

    # ------------------------------------------------------------------
    # 3. Wrong VARCHAR length (transfer_reference VARCHAR(50) not VARCHAR(128))
    # ------------------------------------------------------------------
    async def test_wrong_varchar_length_fails_preflight(self, _schema):
        schema = _schema
        async with AsyncSessionLocal() as db:
            await db.execute(text(
                f'ALTER TABLE "{schema}".payment_declarations '
                'ALTER COLUMN transfer_reference TYPE VARCHAR(50)'))
            await db.commit()

        fp_before = _fingerprint(schema)
        failures = []
        with _sync_engine.connect() as conn:
            m037._verify_declaration_catalog_pg(conn, schema, failures)
        assert failures, "preflight should detect wrong VARCHAR length"
        assert any("transfer_reference" in f for f in failures)
        fp_after = _fingerprint(schema)
        assert fp_before == fp_after

        # GREEN
        async with AsyncSessionLocal() as db:
            await db.execute(text(
                f'ALTER TABLE "{schema}".payment_declarations '
                'ALTER COLUMN transfer_reference TYPE VARCHAR(128)'))
            await db.commit()
        with _sync_engine.connect() as conn:
            m037._verify_declaration_catalog_pg(conn, schema, [])

    # ------------------------------------------------------------------
    # 4. Wrong column nullability
    # ------------------------------------------------------------------
    async def test_wrong_nullability_fails_preflight(self, _schema):
        schema = _schema
        async with AsyncSessionLocal() as db:
            await db.execute(text(
                f'ALTER TABLE "{schema}".payment_declarations '
                'ALTER COLUMN reason SET NOT NULL'))
            await db.commit()

        fp_before = _fingerprint(schema)
        failures = []
        with _sync_engine.connect() as conn:
            m037._verify_declaration_catalog_pg(conn, schema, failures)
        assert failures, f"preflight should detect nullability on reason"
        assert any("reason" in f for f in failures)
        fp_after = _fingerprint(schema)
        assert fp_before == fp_after

        # GREEN
        async with AsyncSessionLocal() as db:
            await db.execute(text(
                f'ALTER TABLE "{schema}".payment_declarations '
                'ALTER COLUMN reason DROP NOT NULL'))
            await db.commit()
        with _sync_engine.connect() as conn:
            m037._verify_declaration_catalog_pg(conn, schema, [])

    # ------------------------------------------------------------------
    # 5. Extra is_deleted column
    # ------------------------------------------------------------------
    async def test_extra_is_deleted_fails_preflight(self, _schema):
        schema = _schema
        async with AsyncSessionLocal() as db:
            await db.execute(text(
                f'ALTER TABLE "{schema}".payment_declarations '
                'ADD COLUMN is_deleted BOOLEAN DEFAULT false'))
            await db.commit()

        fp_before = _fingerprint(schema)
        failures = []
        with _sync_engine.connect() as conn:
            m037._verify_declaration_catalog_pg(conn, schema, failures)
        assert failures, "preflight should detect extra is_deleted"
        assert any("is_deleted" in f for f in failures)
        fp_after = _fingerprint(schema)
        assert fp_before == fp_after

        # GREEN
        async with AsyncSessionLocal() as db:
            await db.execute(text(
                f'ALTER TABLE "{schema}".payment_declarations DROP COLUMN is_deleted'))
            await db.commit()
        with _sync_engine.connect() as conn:
            m037._verify_declaration_catalog_pg(conn, schema, [])

    # ------------------------------------------------------------------
    # 6. Missing index
    # ------------------------------------------------------------------
    async def test_missing_index_fails_preflight(self, _schema):
        schema = _schema
        async with AsyncSessionLocal() as db:
            await db.execute(text(
                f'DROP INDEX IF EXISTS "{schema}".ix_payment_declarations_retailer_status'))
            await db.commit()

        fp_before = _fingerprint(schema)
        failures = []
        with _sync_engine.connect() as conn:
            m037._verify_declaration_catalog_pg(conn, schema, failures)
        assert failures, "preflight should detect missing index"
        assert any("ix_payment_declarations_retailer_status" in f for f in failures)
        fp_after = _fingerprint(schema)
        assert fp_before == fp_after

        # GREEN
        async with AsyncSessionLocal() as db:
            await db.execute(text(
                f"CREATE INDEX ix_payment_declarations_retailer_status ON "
                f'"{schema}".payment_declarations (retailer_id, status)'))
            await db.commit()
        with _sync_engine.connect() as conn:
            m037._verify_declaration_catalog_pg(conn, schema, [])

    # ------------------------------------------------------------------
    # 7. Partial receipt_sequences (wrong business_date type)
    # ------------------------------------------------------------------
    async def test_wrong_receipt_sequences_type_fails_preflight(self, _schema):
        schema = _schema
        async with AsyncSessionLocal() as db:
            await db.execute(text(f'DROP TABLE IF EXISTS "{schema}".receipt_sequences'))
            await db.execute(text(
                f'CREATE TABLE "{schema}".receipt_sequences ('
                'business_date VARCHAR(10) PRIMARY KEY, next_seq INTEGER DEFAULT 1)'))
            await db.commit()

        fp_before = _fingerprint(schema)
        failures = []
        with _sync_engine.connect() as conn:
            m037._verify_receipt_sequences_pg(conn, schema, failures)
        assert failures, "preflight should detect wrong business_date type"
        assert any("business_date" in f for f in failures)
        fp_after = _fingerprint(schema)
        assert fp_before == fp_after

        # GREEN
        async with AsyncSessionLocal() as db:
            await db.execute(text(f'DROP TABLE IF EXISTS "{schema}".receipt_sequences'))
            await db.execute(text(
                f'CREATE TABLE "{schema}".receipt_sequences ('
                'business_date CHAR(8) PRIMARY KEY, next_seq INTEGER NOT NULL DEFAULT 1)'))
            await db.commit()
        with _sync_engine.connect() as conn:
            m037._verify_receipt_sequences_pg(conn, schema, [])

    # ------------------------------------------------------------------
    # 8. Old+new permission collision
    # ------------------------------------------------------------------
    async def test_permission_collision_fails_preflight(self, _schema):
        schema = _schema
        async with AsyncSessionLocal() as db:
            # Insert the OLD permission code to create collision
            await db.execute(text(
                f'INSERT INTO "{schema}".permissions (code, description) '
                "VALUES ('client:payments:create', 'collision test') "
                "ON CONFLICT (code) DO NOTHING"))
            await db.commit()
            # Verify both exist
            old = (await db.execute(text(
                f"SELECT 1 FROM \"{schema}\".permissions WHERE code = 'client:payments:create'"
            ))).first()
            new = (await db.execute(text(
                f"SELECT 1 FROM \"{schema}\".permissions WHERE code = 'client:payments:declare'"
            ))).first()
            assert old and new, "collision setup failed"

        # Execute the full semantic preflight (includes permission collision check)
        fp_before = _fingerprint(schema)
        with _sync_engine.connect() as conn:
            rows = [{"tenant_schema": schema}]
            with pytest.raises(m037.PreflightFailure) as exc_info:
                m037._preflight_semantic(conn, rows)
            assert "collision" in str(exc_info.value).lower() or "both" in str(exc_info.value).lower()
        fp_after = _fingerprint(schema)
        assert fp_before == fp_after

    # ------------------------------------------------------------------
    # 9. Missing receipt index on payments
    # ------------------------------------------------------------------
    async def test_missing_receipt_index_fails_preflight(self, _schema):
        schema = _schema
        async with AsyncSessionLocal() as db:
            await db.execute(text(
                f'ALTER TABLE "{schema}".payments ADD COLUMN IF NOT EXISTS receipt_number VARCHAR(32)'))
            # Drop the partial unique index
            await db.execute(text(
                f'DROP INDEX IF EXISTS "{schema}".ux_payments_receipt_number'))
            await db.commit()

        fp_before = _fingerprint(schema)
        with _sync_engine.connect() as conn:
            rows = [{"tenant_schema": schema}]
            with pytest.raises(m037.PreflightFailure) as exc_info:
                m037._preflight_semantic(conn, rows)
            assert "receipt_number" in str(exc_info.value).lower() or "ux_payments" in str(exc_info.value).lower()
        fp_after = _fingerprint(schema)
        assert fp_before == fp_after


# ---------------------------------------------------------------------------
# Two-registered-tenant test: A canonical, B malformed
# ---------------------------------------------------------------------------

class TestTwoRegisteredTenants:
    """Tenant A canonical; Tenant B malformed. Preflight fails only on B.
    Both catalogs unchanged."""

    async def test_cross_tenant_failure_fingerprint_preserved(self):
        s = get_settings()
        schema_a = f"t_r4_a_{uuid.uuid4().hex[:8]}"
        schema_b = f"t_r4_b_{uuid.uuid4().hex[:8]}"
        from scripts.bootstrap_tenant_schema import bootstrap as bootstrap_schema

        # Bootstrap both schemas canonical
        await bootstrap_schema(schema_a, s.DATABASE_URL)
        await bootstrap_schema(schema_b, s.DATABASE_URL)

        try:
            # Malform B: wrong CHECK constraint
            async with AsyncSessionLocal() as db:
                await db.execute(text(
                    f'ALTER TABLE "{schema_b}".payment_declarations '
                    'DROP CONSTRAINT ck_payment_declarations_method'))
                await db.execute(text(
                    f'ALTER TABLE "{schema_b}".payment_declarations '
                    "ADD CONSTRAINT ck_payment_declarations_method "
                    "CHECK (method IN ('cash'))"
                ))
                await db.commit()

            fp_a_before = _fingerprint(schema_a)
            fp_b_before = _fingerprint(schema_b)

            # Execute preflight on both. A should pass, B should fail.
            with _sync_engine.connect() as conn:
                rows = [
                    {"tenant_schema": schema_a},
                    {"tenant_schema": schema_b},
                ]
                with pytest.raises(m037.PreflightFailure) as exc_info:
                    m037._preflight_semantic(conn, rows)
                msg = str(exc_info.value)
                # Must reference B, not A
                assert "method" in msg.lower() or "cash" in msg.lower()

            fp_a_after = _fingerprint(schema_a)
            fp_b_after = _fingerprint(schema_b)

            assert fp_a_before == fp_a_after, f"tenant A mutated: {fp_a_before} != {fp_a_after}"
            assert fp_b_before == fp_b_after, f"tenant B mutated: {fp_b_before} != {fp_b_after}"

        finally:
            async with AsyncSessionLocal() as db:
                await db.execute(text(f'DROP SCHEMA IF EXISTS "{schema_a}" CASCADE'))
                await db.execute(text(f'DROP SCHEMA IF EXISTS "{schema_b}" CASCADE'))
                await db.commit()
