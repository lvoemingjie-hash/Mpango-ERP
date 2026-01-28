"""Phase B3 - Orders minimal closed loop (tenant schema)

Revision ID: 003_phase_b3_orders_minimal_closed_loop
Revises: 002_phase_b2_invitation_binding
Create Date: 2026-01-27

Tenant-schema migration:
- Update order_status enum to (draft, confirmed, cancelled)
- Add orders.wholesaler_id
- Update order_items to store product snapshots (product_name, sku_code)
- Remove order shipping state and product_id dependency
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "003_phase_b3_orders_minimal_closed_loop"
down_revision: Union[str, None] = "002_phase_b2_invitation_binding"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    result = conn.execute(sa.text("SHOW search_path"))
    search_path = result.scalar() or ""

    is_tenant_migration = any(part.strip().startswith("t_") for part in search_path.split(","))
    if not is_tenant_migration:
        return

    # 1) Evolve enum: order_status -> draft/confirmed/cancelled
    # Create a new enum type, migrate column, then replace old type.
    op.execute("CREATE TYPE order_status_v3 AS ENUM ('draft', 'confirmed', 'cancelled')")

    op.execute(
        "UPDATE orders SET status = 'draft' WHERE status = 'pending'"
    )
    op.execute(
        "UPDATE orders SET status = 'confirmed' WHERE status = 'shipped'"
    )

    op.execute(
        "ALTER TABLE orders ALTER COLUMN status TYPE order_status_v3 USING status::text::order_status_v3"
    )

    op.execute("DROP TYPE order_status")
    op.execute("ALTER TYPE order_status_v3 RENAME TO order_status")

    # 2) Add orders.wholesaler_id
    op.add_column(
        "orders",
        sa.Column("wholesaler_id", postgresql.UUID(as_uuid=True), nullable=False),
    )
    op.create_index("ix_orders_wholesaler_id", "orders", ["wholesaler_id"], unique=False)

    # 3) Update order_items to snapshot product fields
    # Add new columns with defaults to avoid failing if there is existing data.
    op.add_column(
        "order_items",
        sa.Column("product_name", sa.Text(), server_default=sa.text("''"), nullable=False),
    )
    op.add_column(
        "order_items",
        sa.Column("sku_code", sa.String(length=64), server_default=sa.text("''"), nullable=False),
    )
    op.create_index("ix_order_items_sku_code", "order_items", ["sku_code"], unique=False)

    op.alter_column("order_items", "product_name", server_default=None)
    op.alter_column("order_items", "sku_code", server_default=None)

    if _column_exists(conn, "order_items", "product_id"):
        op.drop_index("ix_order_items_product_id", table_name="order_items")
        op.drop_column("order_items", "product_id")


def downgrade() -> None:
    conn = op.get_bind()
    result = conn.execute(sa.text("SHOW search_path"))
    search_path = result.scalar() or ""

    is_tenant_migration = any(part.strip().startswith("t_") for part in search_path.split(","))
    if not is_tenant_migration:
        return

    # Re-add product_id
    op.add_column(
        "order_items",
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
    )
    op.create_index("ix_order_items_product_id", "order_items", ["product_id"], unique=False)

    # Remove snapshot fields
    op.drop_index("ix_order_items_sku_code", table_name="order_items")
    op.drop_column("order_items", "sku_code")
    op.drop_column("order_items", "product_name")

    # Remove wholesaler_id
    op.drop_index("ix_orders_wholesaler_id", table_name="orders")
    op.drop_column("orders", "wholesaler_id")

    # Revert enum back to old values
    op.execute("CREATE TYPE order_status_v2 AS ENUM ('pending', 'confirmed', 'shipped', 'cancelled')")

    op.execute(
        "ALTER TABLE orders ALTER COLUMN status TYPE order_status_v2 USING status::text::order_status_v2"
    )

    op.execute("DROP TYPE order_status")
    op.execute("ALTER TYPE order_status_v2 RENAME TO order_status")


def _column_exists(conn, table_name: str, column_name: str) -> bool:
    res = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = current_schema() "
            "AND table_name = :table_name "
            "AND column_name = :column_name"
        ),
        {"table_name": table_name, "column_name": column_name},
    )
    return res.first() is not None
