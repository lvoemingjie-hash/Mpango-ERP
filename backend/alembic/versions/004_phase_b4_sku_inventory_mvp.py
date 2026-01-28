"""Phase B4 - Inventory MVP (tenant schema)

Revision ID: 004_phase_b4_sku_inventory_mvp
Revises: 003_phase_b3_orders_minimal_closed_loop
Create Date: 2026-01-27

Tenant-schema migration:
- Create skus table (SKU master)
- Create inventory_stocks table (per-SKU stock view)

This migration intentionally does NOT implement stock movement journals,
reservations workflows, or any logistics/warehouse concepts.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "004_phase_b4_sku_inventory_mvp"
down_revision: Union[str, None] = "003_phase_b3_orders_minimal_closed_loop"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    result = conn.execute(sa.text("SHOW search_path"))
    search_path = result.scalar() or ""

    is_tenant_migration = any(part.strip().startswith("t_") for part in search_path.split(","))
    if not is_tenant_migration:
        return

    op.create_table(
        "skus",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("sku_code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("unit", sa.String(length=32), nullable=False, server_default=sa.text("'unit'")),
        sa.Column("category", sa.String(length=64), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ux_skus_sku_code", "skus", ["sku_code"], unique=True)
    op.create_index("ix_skus_is_active", "skus", ["is_active"], unique=False)
    op.create_index("ix_skus_created_at", "skus", ["created_at"], unique=False)

    op.create_table(
        "inventory_stocks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("sku_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("quantity_on_hand", sa.Numeric(precision=12, scale=2), nullable=False, server_default=sa.text("0")),
        sa.Column("quantity_reserved", sa.Numeric(precision=12, scale=2), nullable=False, server_default=sa.text("0")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["sku_id"], ["skus.id"], ondelete="CASCADE"),
    )
    op.create_index("ux_inventory_stocks_sku_id", "inventory_stocks", ["sku_id"], unique=True)


def downgrade() -> None:
    conn = op.get_bind()
    result = conn.execute(sa.text("SHOW search_path"))
    search_path = result.scalar() or ""

    is_tenant_migration = any(part.strip().startswith("t_") for part in search_path.split(","))
    if not is_tenant_migration:
        return

    op.drop_index("ux_inventory_stocks_sku_id", table_name="inventory_stocks")
    op.drop_table("inventory_stocks")

    op.drop_index("ix_skus_created_at", table_name="skus")
    op.drop_index("ix_skus_is_active", table_name="skus")
    op.drop_index("ux_skus_sku_code", table_name="skus")
    op.drop_table("skus")
