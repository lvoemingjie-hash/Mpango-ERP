"""016: Add 'returned' value to order_status enum

Revision ID: 016_add_returned_status
Revises: 015_s7_4_sys_reports
Create Date: 2026-02-16

Adds the RETURNED status to the PostgreSQL order_status enum for the
returns feature. This is a non-destructive change — existing data is untouched.
"""
from alembic import op
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision = '016_add_returned_status'
down_revision = '015_s7_4_sys_reports'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add 'returned' value to the order_status PostgreSQL enum."""
    conn = op.get_bind()
    result = conn.execute(
        text("SELECT 1 FROM pg_type WHERE typname = 'order_status'")
    ).fetchone()

    if result is None:
        op.execute(
            text("CREATE TYPE order_status AS ENUM "
                 "('pending', 'confirmed', 'processing', 'shipped', "
                 "'delivered', 'cancelled', 'returned')")
        )
    else:
        op.execute(
            text("ALTER TYPE order_status ADD VALUE IF NOT EXISTS 'returned'")
        )


def downgrade() -> None:
    """
    PostgreSQL does not support removing values from an enum type.
    To truly downgrade, you would need to:
    1. Create a new enum without 'returned'
    2. Alter the column to use the new enum
    3. Drop the old enum
    This is rarely needed, so we leave it as a no-op.
    """
    pass
