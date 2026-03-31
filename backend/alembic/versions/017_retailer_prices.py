"""017: Add retailer_prices table for MVP retailer-specific pricing

Revision ID: 017_retailer_prices
Revises: 016_add_returned_status
Create Date: 2026-03-31

Phase 3 P0: Without pricing, retailer orders are financially meaningless.
This migration adds a simple retailer_id + sku_id → price lookup table
in the tenant schema.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '017_retailer_prices'
down_revision = '016_add_returned_status'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'retailer_prices',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('retailer_id', postgresql.UUID(as_uuid=True), nullable=False, comment='FK to public.retailers.id'),
        sa.Column('sku_id', postgresql.UUID(as_uuid=True), nullable=False, comment='FK to skus.id'),
        sa.Column('price', sa.Numeric(precision=12, scale=2), nullable=False, comment='Sell price'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('is_deleted', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('updated_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('retailer_id', 'sku_id', name='uq_retailer_prices_retailer_sku'),
        sa.CheckConstraint('price > 0', name='ck_retailer_prices_positive_price'),
    )
    op.create_index('ix_retailer_prices_retailer_id', 'retailer_prices', ['retailer_id'])
    op.create_index('ix_retailer_prices_sku_id', 'retailer_prices', ['sku_id'])


def downgrade() -> None:
    op.drop_index('ix_retailer_prices_sku_id', table_name='retailer_prices')
    op.drop_index('ix_retailer_prices_retailer_id', table_name='retailer_prices')
    op.drop_table('retailer_prices')
