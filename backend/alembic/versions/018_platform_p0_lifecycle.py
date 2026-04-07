"""018: Platform P0 - Tenant lifecycle fields and platform_tenants table

Revision ID: 018_platform_p0_lifecycle
Revises: 017_retailer_prices
Create Date: 2026-04-07

Platform Track P0 first implementation slice.
- Adds backward-compatible columns to public.wholesalers (status, provisioned_at, suspended_at, suspension_reason)
- Creates public.platform_tenants table (platform-level provisioning journal)

No tenant-schema changes. No auth changes. No billing logic.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '018_platform_p0_lifecycle'
down_revision = '017_retailer_prices'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add backward-compatible columns to public.wholesalers
    op.add_column('wholesalers', sa.Column(
        'status', sa.String(20), nullable=False,
        server_default='active',
        comment='Platform-facing tenant state: active, suspended, provisioning, deactivated'
    ))
    op.add_column('wholesalers', sa.Column(
        'provisioned_at', sa.DateTime(timezone=True), nullable=True,
        comment='When tenant schema provisioning completed'
    ))
    op.add_column('wholesalers', sa.Column(
        'suspended_at', sa.DateTime(timezone=True), nullable=True,
        comment='When tenant was suspended'
    ))
    op.add_column('wholesalers', sa.Column(
        'suspension_reason', sa.Text, nullable=True,
        comment='Human-readable reason for suspension'
    ))

    # 2. Create public.platform_tenants
    op.create_table(
        'platform_tenants',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('wholesaler_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('provisioning_status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('provisioning_log', postgresql.JSONB, nullable=True, server_default='{}'),
        sa.Column('activated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('deactivated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('deactivation_reason', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        schema='public'
    )
    op.create_index('ix_platform_tenants_wholesaler_id', 'platform_tenants', ['wholesaler_id'], unique=True, schema='public')


def downgrade() -> None:
    op.drop_table('platform_tenants', schema='public')
    op.drop_column('wholesalers', 'suspension_reason')
    op.drop_column('wholesalers', 'suspended_at')
    op.drop_column('wholesalers', 'provisioned_at')
    op.drop_column('wholesalers', 'status')
