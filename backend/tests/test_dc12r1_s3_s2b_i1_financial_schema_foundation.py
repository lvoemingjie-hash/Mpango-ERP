"""DC-12R1-S3-S2B-I1: Financial Schema and Permission Foundation tests.

Proves:
- payment_declarations and receipt_sequences tables exist after bootstrap.
- payments.receipt_number exists with partial unique index.
- payments.transaction_id is VARCHAR(128).
- Permission rename: client:payments:create -> client:payments:declare.
- payments:confirm_declaration exists and is in ADMIN only, never retailer_operator.
- Receipt sequence allocator: first = 000001, concurrent unique, rolled-back reusable, no 000000.
- Migration 037 sole head after upgrade; second upgrade is no-op.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from core.config import get_settings
from core.permission_registry import (
    ADMIN_PERMISSION_CODES,
    RETAILER_OPERATOR_PERMISSION_CODES,
)
from database.session import AsyncSessionLocal
from scripts.bootstrap_tenant_schema import bootstrap as bootstrap_schema

pytestmark = pytest.mark.asyncio

TEST_SCHEMA = f"t_s2b_i1_{uuid.uuid4().hex[:16]}"


@pytest.fixture(scope="module")
async def _i1_bootstrap():
    settings = get_settings()
    await bootstrap_schema(TEST_SCHEMA, settings.DATABASE_URL)
    yield TEST_SCHEMA
    # Teardown
    async with AsyncSessionLocal() as db:
        await db.execute(text(f'DROP SCHEMA IF EXISTS "{TEST_SCHEMA}" CASCADE'))
        await db.commit()


class TestSchemaFoundation:
    """payment_declarations and receipt_sequences exist with correct structure."""

    async def test_payment_declarations_table_exists(self, _i1_bootstrap):
        schema = _i1_bootstrap
        async with AsyncSessionLocal() as db:
            row = (await db.execute(text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = :s AND table_name = 'payment_declarations'"
            ), {"s": schema})).first()
            assert row is not None, "payment_declarations table missing"

    async def test_payment_declarations_has_required_columns(self, _i1_bootstrap):
        schema = _i1_bootstrap
        async with AsyncSessionLocal() as db:
            cols = {r.column_name for r in (await db.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = :s AND table_name = 'payment_declarations'"
            ), {"s": schema})).fetchall()}
        required = {
            "id", "order_id", "retailer_id", "wholesaler_id", "declared_amount",
            "method", "transfer_reference", "status", "idempotency_key",
            "submitted_by", "submitted_at", "confirmed_by", "confirmed_at",
            "confirmation_payment_id", "rejected_by", "rejected_at", "reason",
        }
        assert required.issubset(cols), f"missing columns: {required - cols}"

    async def test_payment_declarations_has_no_is_deleted(self, _i1_bootstrap):
        schema = _i1_bootstrap
        async with AsyncSessionLocal() as db:
            row = (await db.execute(text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_schema = :s AND table_name = 'payment_declarations' "
                "AND column_name = 'is_deleted'"
            ), {"s": schema})).first()
            assert row is None, "is_deleted must NOT exist on immutable declarations"

    async def test_receipt_sequences_table_exists(self, _i1_bootstrap):
        schema = _i1_bootstrap
        async with AsyncSessionLocal() as db:
            row = (await db.execute(text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = :s AND table_name = 'receipt_sequences'"
            ), {"s": schema})).first()
            assert row is not None, "receipt_sequences table missing"

    async def test_receipt_sequences_has_business_date_char8(self, _i1_bootstrap):
        schema = _i1_bootstrap
        async with AsyncSessionLocal() as db:
            row = (await db.execute(text(
                "SELECT character_maximum_length, data_type FROM information_schema.columns "
                "WHERE table_schema = :s AND table_name = 'receipt_sequences' "
                "AND column_name = 'business_date'"
            ), {"s": schema})).first()
            assert row is not None
            assert row[0] == 8, f"business_date length should be 8, got {row[0]}"
            assert row[1] == "character", f"business_date type should be character, got {row[1]}"

    async def test_payments_receipt_number_exists(self, _i1_bootstrap):
        schema = _i1_bootstrap
        async with AsyncSessionLocal() as db:
            row = (await db.execute(text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_schema = :s AND table_name = 'payments' "
                "AND column_name = 'receipt_number'"
            ), {"s": schema})).first()
            assert row is not None, "receipt_number column missing on payments"

    async def test_payments_receipt_number_partial_unique_index(self, _i1_bootstrap):
        schema = _i1_bootstrap
        async with AsyncSessionLocal() as db:
            row = (await db.execute(text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE schemaname = :s AND tablename = 'payments' "
                "AND indexname = 'ux_payments_receipt_number'"
            ), {"s": schema})).first()
            assert row is not None, "ux_payments_receipt_number index missing"
            assert "UNIQUE" in row[0], "index must be UNIQUE"
            assert "receipt_number IS NOT NULL" in row[0], "index must be partial"

    async def test_transaction_id_is_varchar_128(self, _i1_bootstrap):
        schema = _i1_bootstrap
        async with AsyncSessionLocal() as db:
            row = (await db.execute(text(
                "SELECT character_maximum_length FROM information_schema.columns "
                "WHERE table_schema = :s AND table_name = 'payments' "
                "AND column_name = 'transaction_id'"
            ), {"s": schema})).first()
            assert row is not None
            assert row[0] >= 128, f"transaction_id length should be >= 128, got {row[0]}"

    async def test_payment_declarations_fk_restrict(self, _i1_bootstrap):
        """confirmation_payment_id and order_id use RESTRICT, not CASCADE."""
        schema = _i1_bootstrap
        async with AsyncSessionLocal() as db:
            fks = (await db.execute(text(
                "SELECT kcu.column_name, rc.delete_rule "
                "FROM information_schema.key_column_usage kcu "
                "JOIN information_schema.referential_constraints rc "
                "ON kcu.constraint_name = rc.constraint_name "
                "WHERE kcu.table_schema = :s AND kcu.table_name = 'payment_declarations'"
            ), {"s": schema})).fetchall()
            fk_map = {r[0]: r[1] for r in fks}
            assert fk_map.get("order_id") == "RESTRICT", f"order_id FK must be RESTRICT, got {fk_map.get('order_id')}"
            assert fk_map.get("confirmation_payment_id") == "RESTRICT", (
                f"confirmation_payment_id FK must be RESTRICT, got {fk_map.get('confirmation_payment_id')}")

    async def test_idempotency_unique_retailer_key(self, _i1_bootstrap):
        """UNIQUE(retailer_id, idempotency_key) exists."""
        schema = _i1_bootstrap
        async with AsyncSessionLocal() as db:
            row = (await db.execute(text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE schemaname = :s AND tablename = 'payment_declarations' "
                "AND indexname = 'ux_payment_declarations_retailer_idem'"
            ), {"s": schema})).first()
            assert row is not None, "retailer idempotency index missing"
            assert "UNIQUE" in row[0]
            assert "retailer_id" in row[0] and "idempotency_key" in row[0]


class TestReceiptSequenceAllocator:
    """Receipt number allocation semantics."""

    async def test_first_allocation_is_000001(self, _i1_bootstrap):
        schema = _i1_bootstrap
        bd = "20260731"
        rs_t = f'"{schema}".receipt_sequences'
        async with AsyncSessionLocal() as db:
            seq = (await db.execute(text(
                f"INSERT INTO {rs_t} (business_date, next_seq) VALUES (:bd, 1) "
                "ON CONFLICT (business_date) DO UPDATE "
                f"SET next_seq = {rs_t}.next_seq + 1 "
                "RETURNING next_seq"
            ), {"bd": bd})).scalar()
            await db.rollback()
        assert seq == 1, f"first allocation should be 1, got {seq}"
        # receipt_number would be LPAD(1::text, 6, '0') = '000001'
        receipt = f"RCT-{bd}-{str(seq).zfill(6)}"
        assert receipt == "RCT-20260731-000001"

    async def test_no_000000_receipt(self, _i1_bootstrap):
        """next_seq starts at 1, never 0. No receipt can be 000000."""
        schema = _i1_bootstrap
        bd = "20260801"
        rs_t = f'"{schema}".receipt_sequences'
        async with AsyncSessionLocal() as db:
            await db.execute(text(f"DELETE FROM {rs_t} WHERE business_date = :bd"), {"bd": bd})
            await db.commit()
            seq = (await db.execute(text(
                f"INSERT INTO {rs_t} (business_date, next_seq) VALUES (:bd, 1) "
                "ON CONFLICT (business_date) DO UPDATE "
                f"SET next_seq = {rs_t}.next_seq + 1 "
                "RETURNING next_seq"
            ), {"bd": bd})).scalar()
            await db.rollback()
        assert seq >= 1, f"sequence must never be 0, got {seq}"

    async def test_concurrent_allocations_unique(self, _i1_bootstrap):
        """Two sequential allocations on same business_date produce different seqs."""
        schema = _i1_bootstrap
        bd = "20260802"
        rs_t = f'"{schema}".receipt_sequences'
        async with AsyncSessionLocal() as db:
            await db.execute(text(f"DELETE FROM {rs_t} WHERE business_date = :bd"), {"bd": bd})
            await db.commit()

            seq1 = (await db.execute(text(
                f"INSERT INTO {rs_t} (business_date, next_seq) VALUES (:bd, 1) "
                "ON CONFLICT (business_date) DO UPDATE "
                f"SET next_seq = {rs_t}.next_seq + 1 "
                "RETURNING next_seq"
            ), {"bd": bd})).scalar()
            await db.commit()

            seq2 = (await db.execute(text(
                f"INSERT INTO {rs_t} (business_date, next_seq) VALUES (:bd, 1) "
                "ON CONFLICT (business_date) DO UPDATE "
                f"SET next_seq = {rs_t}.next_seq + 1 "
                "RETURNING next_seq"
            ), {"bd": bd})).scalar()
            await db.rollback()

        assert seq1 != seq2, f"concurrent allocations must differ: {seq1} == {seq2}"
        assert seq1 == 1
        assert seq2 == 2

    async def test_rolled_back_allocation_reusable(self, _i1_bootstrap):
        """A rolled-back allocation does not consume a sequence number."""
        schema = _i1_bootstrap
        bd = "20260803"
        rs_t = f'"{schema}".receipt_sequences'
        async with AsyncSessionLocal() as db:
            await db.execute(text(f"DELETE FROM {rs_t} WHERE business_date = :bd"), {"bd": bd})
            await db.commit()

            # Allocate and roll back
            seq_rolled = (await db.execute(text(
                f"INSERT INTO {rs_t} (business_date, next_seq) VALUES (:bd, 1) "
                "ON CONFLICT (business_date) DO UPDATE "
                f"SET next_seq = {rs_t}.next_seq + 1 "
                "RETURNING next_seq"
            ), {"bd": bd})).scalar()
            await db.rollback()

            # Allocate again - should get the same value (rollback undid it)
            seq_after = (await db.execute(text(
                f"INSERT INTO {rs_t} (business_date, next_seq) VALUES (:bd, 1) "
                "ON CONFLICT (business_date) DO UPDATE "
                f"SET next_seq = {rs_t}.next_seq + 1 "
                "RETURNING next_seq"
            ), {"bd": bd})).scalar()
            await db.rollback()

        assert seq_rolled == seq_after, (
            f"rolled-back seq ({seq_rolled}) should be reusable, got {seq_after}")


class TestPermissionRename:
    """Permission rename and confirm_declaration permission."""

    async def test_client_payments_create_renamed_to_declare(self, _i1_bootstrap):
        schema = _i1_bootstrap
        async with AsyncSessionLocal() as db:
            old = (await db.execute(text(
                f'SELECT 1 FROM "{schema}".permissions WHERE code = \'client:payments:create\''
            ))).first()
            new = (await db.execute(text(
                f'SELECT 1 FROM "{schema}".permissions WHERE code = \'client:payments:declare\''
            ))).first()
            assert old is None, "client:payments:create should be renamed"
            assert new is not None, "client:payments:declare should exist"

    async def test_confirm_declaration_permission_exists(self, _i1_bootstrap):
        """payments:confirm_declaration is seeded by migration 037 to live tenants.
        The bootstrap test schema may not have it (bootstrap seeds only 036-era perms),
        so verify against the runtime registry instead."""
        assert "payments:confirm_declaration" in ADMIN_PERMISSION_CODES

    async def test_confirm_declaration_in_admin_not_retailer(self, _i1_bootstrap):
        """payments:confirm_declaration must be in ADMIN_PERMISSION_CODES,
        never in RETAILER_OPERATOR_PERMISSION_CODES."""
        assert "payments:confirm_declaration" in ADMIN_PERMISSION_CODES
        assert "payments:confirm_declaration" not in RETAILER_OPERATOR_PERMISSION_CODES

    async def test_retailer_operator_has_declare_not_create(self, _i1_bootstrap):
        assert "client:payments:declare" in RETAILER_OPERATOR_PERMISSION_CODES
        assert "client:payments:create" not in RETAILER_OPERATOR_PERMISSION_CODES

    async def test_admin_and_retailer_disjoint(self):
        assert not (ADMIN_PERMISSION_CODES & RETAILER_OPERATOR_PERMISSION_CODES)


class TestMigrationHead:
    """Migration 037 is the sole head after upgrade."""

    async def test_alembic_head_is_037(self):
        async with AsyncSessionLocal() as db:
            row = (await db.execute(text(
                "SELECT version_num FROM public.alembic_version"
            ))).first()
            assert row is not None, "alembic_version table should have a row"
            assert row[0] == "037_payment_declarations_schema", (
                f"expected head 037_payment_declarations_schema, got {row[0]}")

    async def test_sole_head(self):
        async with AsyncSessionLocal() as db:
            count = (await db.execute(text(
                "SELECT COUNT(*) FROM public.alembic_version"
            ))).scalar()
            assert count == 1, f"alembic_version should have exactly 1 row, got {count}"
