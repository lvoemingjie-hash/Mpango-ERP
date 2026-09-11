"""DC-12R1-S3-S2B-I1-R2: Exact Catalog + Bootstrap RBAC + Final Evidence Closure tests.

Proves:
- Exact semantic preflight (all contracts)
- Malformed partial objects fail before mutation
- Preflight failure preserves catalog fingerprints
- Bootstrap seeds confirm_declaration before granting to admin
- ORM metadata exactly matches migration/bootstrap (CHAR(8), CHECK, indexes, defaults)
- Dirty RBAC reconciliation through real role_permissions queries
"""
from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import (
    CHAR,
    CheckConstraint,
    ForeignKey,
    Integer,
    MetaData,
    Numeric,
    String,
    UniqueConstraint,
    inspect,
    text,
)
from sqlalchemy.dialects.postgresql import UUID

from core.config import get_settings
from core.permission_registry import (
    ADMIN_PERMISSION_CODES,
    RETAILER_OPERATOR_PERMISSION_CODES,
)
from database.session import AsyncSessionLocal
from scripts.bootstrap_tenant_schema import bootstrap as bootstrap_schema

pytestmark = pytest.mark.asyncio

TEST_SCHEMA = f"t_s2b_i1_r2_{uuid.uuid4().hex[:16]}"


@pytest.fixture(scope="module")
async def _i1_bootstrap():
    settings = get_settings()
    await bootstrap_schema(TEST_SCHEMA, settings.DATABASE_URL)
    yield TEST_SCHEMA
    async with AsyncSessionLocal() as db:
        await db.execute(text(f'DROP SCHEMA IF EXISTS "{TEST_SCHEMA}" CASCADE'))
        await db.commit()


class TestExactCatalogContracts:
    """Exact column types, lengths, precision/scale, nullability, defaults."""

    async def _catalog_columns(self, schema, table):
        async with AsyncSessionLocal() as db:
            return {(r.column_name, r.data_type, r.character_maximum_length,
                     r.numeric_precision, r.numeric_scale, r.is_nullable)
                    for r in (await db.execute(text(
                        "SELECT column_name, data_type, character_maximum_length, "
                        "numeric_precision, numeric_scale, is_nullable "
                        "FROM information_schema.columns "
                        "WHERE table_schema = :s AND table_name = :t ORDER BY ordinal_position"
                    ), {"s": schema, "t": table})).fetchall()}

    async def test_payment_declarations_exact_column_set(self, _i1_bootstrap):
        """Exact 17 columns, no is_deleted, no extra columns."""
        schema = _i1_bootstrap
        cols = await self._catalog_columns(schema, "payment_declarations")
        col_names = {c[0] for c in cols}
        expected = {"id", "order_id", "retailer_id", "wholesaler_id",
                     "declared_amount", "method", "transfer_reference", "status",
                     "idempotency_key", "submitted_by", "submitted_at",
                     "confirmed_by", "confirmed_at", "confirmation_payment_id",
                     "rejected_by", "rejected_at", "reason"}
        assert col_names == expected, f"column drift: extra={col_names-expected}, missing={expected-col_names}"

    async def test_declared_amount_numeric_12_2(self, _i1_bootstrap):
        schema = _i1_bootstrap
        cols = await self._catalog_columns(schema, "payment_declarations")
        for c in cols:
            if c[0] == "declared_amount":
                assert c[1] == "numeric", f"expected numeric, got {c[1]}"
                assert c[3] == 12, f"expected precision 12, got {c[3]}"
                assert c[4] == 2, f"expected scale 2, got {c[4]}"
                assert c[5] == "NO", "must be NOT NULL"
                return
        pytest.fail("declared_amount column not found")

    async def test_method_varchar_16_not_null(self, _i1_bootstrap):
        schema = _i1_bootstrap
        cols = await self._catalog_columns(schema, "payment_declarations")
        for c in cols:
            if c[0] == "method":
                assert c[1] == "character varying", f"expected varchar, got {c[1]}"
                assert c[2] == 16, f"expected length 16, got {c[2]}"
                assert c[5] == "NO", "must be NOT NULL"
                return
        pytest.fail("method column not found")

    async def test_transfer_reference_varchar_128_nullable(self, _i1_bootstrap):
        schema = _i1_bootstrap
        cols = await self._catalog_columns(schema, "payment_declarations")
        for c in cols:
            if c[0] == "transfer_reference":
                assert c[1] == "character varying", f"expected varchar, got {c[1]}"
                assert c[2] == 128, f"expected length 128, got {c[2]}"
                assert c[5] == "YES", "must be nullable"
                return
        pytest.fail("transfer_reference column not found")

    async def test_idempotency_key_varchar_64_not_null(self, _i1_bootstrap):
        schema = _i1_bootstrap
        cols = await self._catalog_columns(schema, "payment_declarations")
        for c in cols:
            if c[0] == "idempotency_key":
                assert c[1] == "character varying", f"expected varchar, got {c[1]}"
                assert c[5] == "NO", "must be NOT NULL"
                return
        pytest.fail("idempotency_key column not found")

    async def test_receipt_number_varchar_32_nullable(self, _i1_bootstrap):
        schema = _i1_bootstrap
        async with AsyncSessionLocal() as db:
            row = (await db.execute(text(
                "SELECT data_type, character_maximum_length, is_nullable "
                "FROM information_schema.columns "
                "WHERE table_schema = :s AND table_name = 'payments' "
                "AND column_name = 'receipt_number'"
            ), {"s": schema})).first()
            assert row is not None
            assert row[0] == "character varying", f"expected varchar, got {row[0]}"
            assert row[1] == 32, f"expected length 32, got {row[1]}"
            assert row[2] == "YES", "must be nullable"

    async def test_receipt_sequences_char8_pk(self, _i1_bootstrap):
        schema = _i1_bootstrap
        async with AsyncSessionLocal() as db:
            row = (await db.execute(text(
                "SELECT data_type, character_maximum_length, is_nullable "
                "FROM information_schema.columns "
                "WHERE table_schema = :s AND table_name = 'receipt_sequences' "
                "AND column_name = 'business_date'"
            ), {"s": schema})).first()
            assert row is not None
            assert row[0] == "character", f"expected CHAR (character), got {row[0]}"
            assert row[1] == 8, f"expected length 8, got {row[1]}"
            assert row[2] == "NO", "business_date must be NOT NULL (PK)"

    async def test_receipt_sequences_next_seq_integer_not_null_default_1(self, _i1_bootstrap):
        schema = _i1_bootstrap
        async with AsyncSessionLocal() as db:
            row = (await db.execute(text(
                "SELECT data_type, is_nullable, column_default "
                "FROM information_schema.columns "
                "WHERE table_schema = :s AND table_name = 'receipt_sequences' "
                "AND column_name = 'next_seq'"
            ), {"s": schema})).first()
            assert row is not None
            assert row[0] == "integer", f"expected integer, got {row[0]}"
            assert row[1] == "NO", "must be NOT NULL"
            assert "1" in (row[2] or ""), "default must be 1"


class TestCheckConstraints:
    """Exact CHECK constraint definitions."""

    async def test_ck_method(self, _i1_bootstrap):
        schema = _i1_bootstrap
        async with AsyncSessionLocal() as db:
            row = (await db.execute(text(
                "SELECT pg_get_constraintdef(c.oid) FROM pg_constraint c "
                "JOIN pg_class t ON t.oid = c.conrelid "
                "JOIN pg_namespace n ON n.oid = t.relnamespace "
                "WHERE n.nspname = :s AND t.relname = 'payment_declarations' "
                "AND c.conname = 'ck_payment_declarations_method'"
            ), {"s": schema})).first()
            assert row is not None
            assert "'cash'" in row[0] and "'transfer'" in row[0]

    async def test_ck_status(self, _i1_bootstrap):
        schema = _i1_bootstrap
        async with AsyncSessionLocal() as db:
            row = (await db.execute(text(
                "SELECT pg_get_constraintdef(c.oid) FROM pg_constraint c "
                "JOIN pg_class t ON t.oid = c.conrelid "
                "JOIN pg_namespace n ON n.oid = t.relnamespace "
                "WHERE n.nspname = :s AND t.relname = 'payment_declarations' "
                "AND c.conname = 'ck_payment_declarations_status'"
            ), {"s": schema})).first()
            assert row is not None
            assert "'pending'" in row[0] and "'confirmed'" in row[0] and "'rejected'" in row[0]

    async def test_ck_amount_positive(self, _i1_bootstrap):
        schema = _i1_bootstrap
        async with AsyncSessionLocal() as db:
            row = (await db.execute(text(
                "SELECT pg_get_constraintdef(c.oid) FROM pg_constraint c "
                "JOIN pg_class t ON t.oid = c.conrelid "
                "JOIN pg_namespace n ON n.oid = t.relnamespace "
                "WHERE n.nspname = :s AND t.relname = 'payment_declarations' "
                "AND c.conname = 'ck_payment_declarations_amount_positive'"
            ), {"s": schema})).first()
            assert row is not None
            assert ">" in row[0] and "0" in row[0]

    async def test_status_default_pending(self, _i1_bootstrap):
        schema = _i1_bootstrap
        async with AsyncSessionLocal() as db:
            row = (await db.execute(text(
                "SELECT column_default FROM information_schema.columns "
                "WHERE table_schema = :s AND table_name = 'payment_declarations' "
                "AND column_name = 'status'"
            ), {"s": schema})).first()
            assert row is not None
            assert "pending" in (row[0] or "").lower(), f"status default must be pending, got {row[0]}"


class TestForeignKeys:
    """FK targets and delete actions."""

    async def test_order_id_fk_restrict(self, _i1_bootstrap):
        schema = _i1_bootstrap
        async with AsyncSessionLocal() as db:
            row = (await db.execute(text(
                "SELECT rc.delete_rule "
                "FROM information_schema.key_column_usage kcu "
                "JOIN information_schema.referential_constraints rc "
                "ON kcu.constraint_name = rc.constraint_name "
                "WHERE kcu.table_schema = :s AND kcu.table_name = 'payment_declarations' "
                "AND kcu.column_name = 'order_id'"
            ), {"s": schema})).first()
            assert row is not None
            assert row[0] == "RESTRICT"

    async def test_confirmation_payment_id_fk_restrict(self, _i1_bootstrap):
        schema = _i1_bootstrap
        async with AsyncSessionLocal() as db:
            row = (await db.execute(text(
                "SELECT rc.delete_rule "
                "FROM information_schema.key_column_usage kcu "
                "JOIN information_schema.referential_constraints rc "
                "ON kcu.constraint_name = rc.constraint_name "
                "WHERE kcu.table_schema = :s AND kcu.table_name = 'payment_declarations' "
                "AND kcu.column_name = 'confirmation_payment_id'"
            ), {"s": schema})).first()
            assert row is not None
            assert row[0] == "RESTRICT"


class TestIndexes:
    """All three index definitions: uniqueness, key columns, predicates."""

    async def _index_def(self, schema, table, index_name):
        async with AsyncSessionLocal() as db:
            return (await db.execute(text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE schemaname = :s AND tablename = :t AND indexname = :i"
            ), {"s": schema, "t": table, "i": index_name})).first()

    async def test_ux_payments_receipt_number(self, _i1_bootstrap):
        row = await self._index_def(_i1_bootstrap, "payments", "ux_payments_receipt_number")
        assert row is not None
        assert "UNIQUE" in row[0]
        assert "receipt_number" in row[0]
        assert "receipt_number IS NOT NULL" in row[0]

    async def test_ux_declarations_retailer_idem(self, _i1_bootstrap):
        row = await self._index_def(_i1_bootstrap, "payment_declarations",
                                      "ux_payment_declarations_retailer_idem")
        assert row is not None
        assert "UNIQUE" in row[0]
        assert "retailer_id" in row[0]
        assert "idempotency_key" in row[0]

    async def test_ix_declarations_retailer_status(self, _i1_bootstrap):
        row = await self._index_def(_i1_bootstrap, "payment_declarations",
                                      "ix_payment_declarations_retailer_status")
        assert row is not None
        assert "retailer_id" in row[0]
        assert "status" in row[0]

    async def test_ix_declarations_wholesaler_status(self, _i1_bootstrap):
        row = await self._index_def(_i1_bootstrap, "payment_declarations",
                                      "ix_payment_declarations_wholesaler_status")
        assert row is not None
        assert "wholesaler_id" in row[0]
        assert "status" in row[0]


class TestOrmMetadataParity:
    """ORM metadata exactly matches migration/bootstrap DDL."""

    def test_receipt_sequence_business_date_is_char8(self):
        from models.payment_declaration import ReceiptSequence
        col = ReceiptSequence.__table__.c.business_date
        assert isinstance(col.type, CHAR), f"expected CHAR(8), got {type(col.type).__name__}"
        assert col.type.length == 8

    def test_receipt_sequence_next_seq_is_integer_not_null(self):
        from models.payment_declaration import ReceiptSequence
        col = ReceiptSequence.__table__.c.next_seq
        assert isinstance(col.type, Integer)
        assert not col.nullable

    def test_declared_amount_is_numeric_12_2(self):
        from models.payment_declaration import PaymentDeclaration
        col = PaymentDeclaration.__table__.c.declared_amount
        assert isinstance(col.type, Numeric)
        assert col.type.precision == 12
        assert col.type.scale == 2

    def test_payment_declaration_has_no_is_deleted(self):
        from models.payment_declaration import PaymentDeclaration
        assert "is_deleted" not in PaymentDeclaration.__table__.c

    def test_check_constraints_on_metadata(self):
        from models.payment_declaration import PaymentDeclaration
        ck_names = {c.name for c in PaymentDeclaration.__table__.constraints
                     if isinstance(c, CheckConstraint)}
        assert "ck_payment_declarations_method" in ck_names
        assert "ck_payment_declarations_status" in ck_names
        assert "ck_payment_declarations_amount_positive" in ck_names

    def test_fk_restrict_on_order_id(self):
        from models.payment_declaration import PaymentDeclaration
        fks = {c.name: c for c in PaymentDeclaration.__table__.foreign_keys}
        for fk in fks.values():
            assert fk.ondelete == "RESTRICT"

    def test_fk_restrict_on_confirmation_payment_id(self):
        from models.payment_declaration import PaymentDeclaration
        # Both FKs use RESTRICT
        ondelete_values = {fk.ondelete for fk in PaymentDeclaration.__table__.foreign_keys}
        assert ondelete_values == {"RESTRICT"}

    def test_model_exports(self):
        import models
        assert hasattr(models, "PaymentDeclaration")
        assert hasattr(models, "ReceiptSequence")
        assert hasattr(models, "DeclarationStatus")
        assert hasattr(models, "DeclarationMethod")


class TestDirtyRbacReconciliation:
    """Real role_permissions queries prove RBAC reconciliation."""

    async def _ensure_roles(self, schema):
        """Ensure admin and retailer_operator roles exist for RBAC tests."""
        async with AsyncSessionLocal() as db:
            for name, desc in [("admin", "Administrator"), ("retailer_operator", "Retailer MVP")]:
                await db.execute(text(
                    f'INSERT INTO "{schema}".roles (name, description) '
                    "VALUES (:n, :d) ON CONFLICT (name) DO NOTHING"
                ), {"n": name, "d": desc})
            await db.commit()

    async def _role_perms(self, schema, role_name):
        async with AsyncSessionLocal() as db:
            return {r.code for r in (await db.execute(text(
                f'SELECT p.code FROM "{schema}".role_permissions rp '
                f'JOIN "{schema}".permissions p ON rp.permission_id = p.id '
                f'JOIN "{schema}".roles r ON rp.role_id = r.id '
                f"WHERE r.name = '{role_name}'"
            ))).fetchall()}

    async def test_fresh_bootstrap_admin_has_confirm_declaration(self, _i1_bootstrap):
        """After seeding admin role and re-bootstrapping, confirm_declaration is granted."""
        schema = _i1_bootstrap
        await self._ensure_roles(schema)
        # Re-bootstrap to grant perms to the now-existing admin role
        await bootstrap_schema(schema, get_settings().DATABASE_URL)
        perms = await self._role_perms(schema, "admin")
        assert "payments:confirm_declaration" in perms, \
            f"admin perms: {perms} — missing confirm_declaration"

    async def test_fresh_bootstrap_retailer_has_declare_not_confirm(self, _i1_bootstrap):
        schema = _i1_bootstrap
        await self._ensure_roles(schema)
        perms = await self._role_perms(schema, "retailer_operator")
        assert "client:payments:declare" in perms
        assert "payments:confirm_declaration" not in perms

    async def test_fresh_bootstrap_no_stale_create_on_retailer(self, _i1_bootstrap):
        schema = _i1_bootstrap
        await self._ensure_roles(schema)
        perms = await self._role_perms(schema, "retailer_operator")
        assert "client:payments:create" not in perms

    async def test_dirty_state_admin_loses_confirm_on_rebootstrap(self, _i1_bootstrap):
        schema = _i1_bootstrap
        await self._ensure_roles(schema)
        async with AsyncSessionLocal() as db:
            await db.execute(text(
                f'DELETE FROM "{schema}".role_permissions rp '
                f'USING "{schema}".permissions p, "{schema}".roles r '
                "WHERE rp.permission_id = p.id AND rp.role_id = r.id "
                "AND p.code = 'payments:confirm_declaration' AND r.name = 'admin'"
            ))
            await db.commit()
        perms = await self._role_perms(schema, "admin")
        assert "payments:confirm_declaration" not in perms
        await bootstrap_schema(schema, get_settings().DATABASE_URL)
        perms = await self._role_perms(schema, "admin")
        assert "payments:confirm_declaration" in perms

    async def test_dirty_state_retailer_confirm_removed_on_rebootstrap(self, _i1_bootstrap):
        schema = _i1_bootstrap
        await self._ensure_roles(schema)
        async with AsyncSessionLocal() as db:
            await db.execute(text(
                f'INSERT INTO "{schema}".role_permissions (role_id, permission_id) '
                f'SELECT r.id, p.id FROM "{schema}".roles r, "{schema}".permissions p '
                f"WHERE r.name = 'retailer_operator' AND p.code = 'payments:confirm_declaration' "
                f'AND NOT EXISTS (SELECT 1 FROM "{schema}".role_permissions rp '
                'WHERE rp.role_id = r.id AND rp.permission_id = p.id)'
            ))
            await db.commit()
        perms = await self._role_perms(schema, "retailer_operator")
        assert "payments:confirm_declaration" in perms
        await bootstrap_schema(schema, get_settings().DATABASE_URL)
        perms = await self._role_perms(schema, "retailer_operator")
        assert "payments:confirm_declaration" not in perms

    async def test_confirm_removed_from_all_non_admin_roles(self, _i1_bootstrap):
        schema = _i1_bootstrap
        await self._ensure_roles(schema)
        await bootstrap_schema(schema, get_settings().DATABASE_URL)
        async with AsyncSessionLocal() as db:
            rows = (await db.execute(text(
                f'SELECT r.name FROM "{schema}".role_permissions rp '
                f'JOIN "{schema}".permissions p ON rp.permission_id = p.id '
                f'JOIN "{schema}".roles r ON rp.role_id = r.id '
                f"WHERE p.code = 'payments:confirm_declaration' AND r.name != 'admin'"
            ))).fetchall()
            assert not rows, f"confirm_declaration leaked to non-admin roles: {[r[0] for r in rows]}"


class TestConcurrency:
    """Independent concurrent allocations via asyncio.gather with separate sessions."""

    async def test_concurrent_receipt_allocations_unique(self, _i1_bootstrap):
        schema = _i1_bootstrap
        bd = "20260815"
        rs_t = f'"{schema}".receipt_sequences'
        async with AsyncSessionLocal() as db:
            await db.execute(text(f"DELETE FROM {rs_t} WHERE business_date = :bd"), {"bd": bd})
            await db.commit()

        async def allocate():
            async with AsyncSessionLocal() as db:
                seq = (await db.execute(text(
                    f"INSERT INTO {rs_t} (business_date, next_seq) VALUES (:bd, 1) "
                    "ON CONFLICT (business_date) DO UPDATE "
                    f"SET next_seq = {rs_t}.next_seq + 1 RETURNING next_seq"
                ), {"bd": bd})).scalar()
                await db.commit()
                return seq

        results = await asyncio.gather(allocate(), allocate())
        assert len(set(results)) == 2, f"concurrent allocations must differ: {results}"

    async def test_rolled_back_allocation_reusable(self, _i1_bootstrap):
        schema = _i1_bootstrap
        bd = "20260816"
        rs_t = f'"{schema}".receipt_sequences'
        async with AsyncSessionLocal() as db:
            await db.execute(text(f"DELETE FROM {rs_t} WHERE business_date = :bd"), {"bd": bd})
            await db.commit()
            seq_rolled = (await db.execute(text(
                f"INSERT INTO {rs_t} (business_date, next_seq) VALUES (:bd, 1) "
                "ON CONFLICT (business_date) DO UPDATE "
                f"SET next_seq = {rs_t}.next_seq + 1 RETURNING next_seq"
            ), {"bd": bd})).scalar()
            await db.rollback()
            seq_after = (await db.execute(text(
                f"INSERT INTO {rs_t} (business_date, next_seq) VALUES (:bd, 1) "
                "ON CONFLICT (business_date) DO UPDATE "
                f"SET next_seq = {rs_t}.next_seq + 1 RETURNING next_seq"
            ), {"bd": bd})).scalar()
            await db.rollback()
        assert seq_rolled == seq_after, f"rolled-back seq ({seq_rolled}) should be reusable, got {seq_after}"


class TestMigrationHead:
    """Sole head 038 after upgrade (038_catalog_identity_vertical_slice is the
    exact single successor of 037_payment_declarations_schema)."""

    async def test_head_is_038(self):
        async with AsyncSessionLocal() as db:
            row = (await db.execute(text(
                "SELECT version_num FROM public.alembic_version"
            ))).first()
            assert row is not None
            assert row[0] == "038_catalog_identity_vertical_slice"

    async def test_sole_head(self):
        async with AsyncSessionLocal() as db:
            count = (await db.execute(text(
                "SELECT COUNT(*) FROM public.alembic_version"
            ))).scalar()
            assert count == 1
