"""023: Inventory reservation ownership contract

Revision ID: 023_inventory_reservations
Revises: 022_import_runs
Create Date: 2026-06-23

S4-E3: tenant-schema reservation ownership table. The table records which
order item owns reserved stock. `inventory_stocks.quantity_reserved` remains
the aggregate fast-read projection.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "023_inventory_reservations"
down_revision = "022_import_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    result = conn.execute(sa.text("SHOW search_path"))
    search_path = result.scalar() or ""

    is_tenant = any(part.strip().startswith("t_") for part in search_path.split(","))
    if not is_tenant:
        return

    if _table_exists(conn, "inventory_reservations"):
        return

    op.create_table(
        "inventory_reservations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("order_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sku_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sku_code", sa.String(length=64), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'reserved'")),
        sa.Column("reserved_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reference_type", sa.String(length=50), nullable=False, server_default=sa.text("'order'")),
        sa.Column("reference_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["order_item_id"], ["order_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sku_id"], ["skus.id"], ondelete="CASCADE"),
        sa.CheckConstraint("quantity > 0", name="ck_inventory_reservations_quantity_positive"),
        sa.CheckConstraint(
            "status IN ('reserved', 'consumed', 'released')",
            name="ck_inventory_reservations_status",
        ),
    )

    op.create_index("ix_inventory_reservations_order_id", "inventory_reservations", ["order_id"])
    op.create_index("ix_inventory_reservations_sku_id", "inventory_reservations", ["sku_id"])
    op.create_index("ix_inventory_reservations_status", "inventory_reservations", ["status"])
    op.create_index(
        "ux_inventory_reservations_active_order_item",
        "inventory_reservations",
        ["order_item_id"],
        unique=True,
        postgresql_where=sa.text("status = 'reserved'"),
    )


def downgrade() -> None:
    conn = op.get_bind()
    result = conn.execute(sa.text("SHOW search_path"))
    search_path = result.scalar() or ""

    is_tenant = any(part.strip().startswith("t_") for part in search_path.split(","))
    if not is_tenant:
        return

    if _table_exists(conn, "inventory_reservations"):
        op.drop_index("ux_inventory_reservations_active_order_item", table_name="inventory_reservations")
        op.drop_index("ix_inventory_reservations_status", table_name="inventory_reservations")
        op.drop_index("ix_inventory_reservations_sku_id", table_name="inventory_reservations")
        op.drop_index("ix_inventory_reservations_order_id", table_name="inventory_reservations")
        op.drop_table("inventory_reservations")


def _table_exists(conn, table_name: str) -> bool:
    res = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = current_schema() AND table_name = :table_name"
        ),
        {"table_name": table_name},
    )
    return res.first() is not None
