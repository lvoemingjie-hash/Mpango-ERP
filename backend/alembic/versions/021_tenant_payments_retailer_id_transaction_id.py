"""021: Add retailer_id and transaction_id to tenant payments

Revision ID: 021_tenant_payments_retailer_id_transaction_id
Revises: 020_sys_jobs_audit_columns
Create Date: 2026-05-09

Aligns bootstrapped tenant payments schema with PaymentRepository contract.
The bootstrap script previously created payments without retailer_id and
transaction_id, while payment_repository.py queries and inserts both columns.

This migration is tenant-only (no-op on public schema).

Strategy:
- If payments table exists but lacks retailer_id:
  1. Add nullable retailer_id
  2. Backfill from orders.retailer_id
  3. If any NULLs remain after backfill, FAIL with explicit error
     (data integrity issue that requires manual resolution)
  4. Set NOT NULL constraint
- If payments table exists but lacks transaction_id:
  1. Add nullable transaction_id
- Create order_id index if missing
- Create partial unique index on transaction_id if missing
"""
from alembic import op
import sqlalchemy as sa


revision = "021_tenant_payments_retailer_id_transaction_id"
down_revision = "020_sys_jobs_audit_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    result = conn.execute(sa.text("SHOW search_path"))
    search_path = result.scalar() or ""

    # Only run on tenant schemas (t_*), not public
    is_tenant = any(part.strip().startswith("t_") for part in search_path.split(","))
    if not is_tenant:
        return

    if not _table_exists(conn, "payments"):
        return

    # --- retailer_id ---
    if not _column_exists(conn, "payments", "retailer_id"):
        op.add_column(
            "payments",
            sa.Column("retailer_id", sa.UUID(as_uuid=True), nullable=True),
        )

        # Backfill from orders.retailer_id
        conn.execute(sa.text(
            "UPDATE payments p "
            "SET retailer_id = o.retailer_id "
            "FROM orders o "
            "WHERE p.order_id = o.id AND p.retailer_id IS NULL"
        ))

        # Verify no NULLs remain — fail explicitly if data issue exists
        null_count = conn.execute(sa.text(
            "SELECT COUNT(*) FROM payments WHERE retailer_id IS NULL"
        )).scalar()

        if null_count and int(null_count) > 0:
            raise RuntimeError(
                f"Migration 021: {null_count} payment rows have NULL retailer_id "
                "after backfill from orders. These are orphaned payments with no "
                "matching order. Resolve data integrity issue before retrying."
            )

        op.alter_column("payments", "retailer_id", nullable=False)

    # --- transaction_id ---
    if not _column_exists(conn, "payments", "transaction_id"):
        op.add_column(
            "payments",
            sa.Column("transaction_id", sa.String(length=64), nullable=True),
        )

    # --- order_id index ---
    if not _index_exists(conn, "ix_payments_order_id"):
        op.create_index("ix_payments_order_id", "payments", ["order_id"])

    # --- transaction_id partial unique index ---
    if not _index_exists(conn, "uq_payments_transaction_id"):
        op.create_index(
            "uq_payments_transaction_id",
            "payments",
            ["transaction_id"],
            unique=True,
            postgresql_where=sa.text("transaction_id IS NOT NULL"),
        )


def downgrade() -> None:
    conn = op.get_bind()
    result = conn.execute(sa.text("SHOW search_path"))
    search_path = result.scalar() or ""

    is_tenant = any(part.strip().startswith("t_") for part in search_path.split(","))
    if not is_tenant:
        return

    if not _table_exists(conn, "payments"):
        return

    if _index_exists(conn, "uq_payments_transaction_id"):
        op.drop_index("uq_payments_transaction_id", table_name="payments")
    if _index_exists(conn, "ix_payments_order_id"):
        op.drop_index("ix_payments_order_id", table_name="payments")
    if _column_exists(conn, "payments", "transaction_id"):
        op.drop_column("payments", "transaction_id")
    if _column_exists(conn, "payments", "retailer_id"):
        op.drop_column("payments", "retailer_id")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _table_exists(conn, table_name: str) -> bool:
    res = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = current_schema() AND table_name = :table_name"
        ),
        {"table_name": table_name},
    )
    return res.first() is not None


def _column_exists(conn, table_name: str, column_name: str) -> bool:
    res = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = current_schema() "
            "AND table_name = :table_name AND column_name = :column_name"
        ),
        {"table_name": table_name, "column_name": column_name},
    )
    return res.first() is not None


def _index_exists(conn, index_name: str) -> bool:
    res = conn.execute(
        sa.text(
            "SELECT 1 FROM pg_indexes "
            "WHERE schemaname = current_schema() AND indexname = :index_name"
        ),
        {"index_name": index_name},
    )
    return res.first() is not None
