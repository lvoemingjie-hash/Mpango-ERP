"""Phase B5 - Payments minimal loop (tenant + public)

Revision ID: 005_phase_b5_payments_minimal_loop
Revises: 004_phase_b4_sku_inventory_mvp
Create Date: 2026-01-28

Implements Phase B5 minimal loop:
- Tenant schema: create payments table with unique transaction_id
- Public schema: add outstanding_balance to wholesaler_retailer_bindings
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "005_phase_b5_payments_minimal_loop"
down_revision: Union[str, None] = "004_phase_b4_sku_inventory_mvp"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    result = conn.execute(sa.text("SHOW search_path"))
    search_path = result.scalar() or ""

    is_tenant_migration = any(part.strip().startswith("t_") for part in search_path.split(","))

    if is_tenant_migration:
        _upgrade_tenant(conn)
    else:
        _upgrade_public(conn)


def downgrade() -> None:
    conn = op.get_bind()
    result = conn.execute(sa.text("SHOW search_path"))
    search_path = result.scalar() or ""

    is_tenant_migration = any(part.strip().startswith("t_") for part in search_path.split(","))

    if is_tenant_migration:
        _downgrade_tenant(conn)
    else:
        _downgrade_public(conn)


def _upgrade_public(conn) -> None:
    if not _column_exists(conn, "wholesaler_retailer_bindings", "outstanding_balance", schema="public"):
        op.add_column(
            "wholesaler_retailer_bindings",
            sa.Column(
                "outstanding_balance",
                sa.Numeric(precision=12, scale=2),
                nullable=False,
                server_default=sa.text("0"),
                comment="Outstanding balance / credit exposure cache (MVP)",
            ),
            schema="public",
        )
        op.alter_column(
            "wholesaler_retailer_bindings",
            "outstanding_balance",
            schema="public",
            server_default=None,
        )


def _downgrade_public(conn) -> None:
    if _column_exists(conn, "wholesaler_retailer_bindings", "outstanding_balance", schema="public"):
        op.drop_column("wholesaler_retailer_bindings", "outstanding_balance", schema="public")


def _upgrade_tenant(conn) -> None:
    if _table_exists(conn, "payments"):
        return

    op.create_table(
        "payments",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "order_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "retailer_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("transaction_id", sa.String(length=64), nullable=True),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("method", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_payments_order_id", "payments", ["order_id"], unique=False)
    op.create_index(
        "uq_payments_transaction_id",
        "payments",
        ["transaction_id"],
        unique=True,
        postgresql_where=sa.text("transaction_id IS NOT NULL"),
    )


def _downgrade_tenant(conn) -> None:
    if _table_exists(conn, "payments"):
        op.drop_index("uq_payments_transaction_id", table_name="payments")
        op.drop_index("ix_payments_order_id", table_name="payments")
        op.drop_table("payments")


def _table_exists(conn, table_name: str) -> bool:
    res = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = current_schema() AND table_name = :table_name"
        ),
        {"table_name": table_name},
    )
    return res.first() is not None


def _column_exists(conn, table_name: str, column_name: str, *, schema: str) -> bool:
    res = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = :schema AND table_name = :table_name AND column_name = :column_name"
        ),
        {"schema": schema, "table_name": table_name, "column_name": column_name},
    )
    return res.first() is not None
