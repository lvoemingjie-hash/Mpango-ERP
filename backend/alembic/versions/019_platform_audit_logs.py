"""019: Platform P0 - Audit log table (append-only)

Revision ID: 019_platform_audit_logs
Revises: 018_platform_p0_lifecycle
Create Date: 2026-04-09

Platform Track P0 audit boundary.
Creates public.platform_audit_logs — append-only table for platform admin actions.
wholesaler_id is nullable FK to public.wholesalers.id (NULL for global actions).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '019_platform_audit_logs'
down_revision = '018_platform_p0_lifecycle'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'platform_audit_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('actor_type', sa.String(20), nullable=False, comment='Who acted: system, admin, api'),
        sa.Column('actor_id', postgresql.UUID(as_uuid=True), nullable=True, comment='UUID of the actor'),
        sa.Column('wholesaler_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('public.wholesalers.id'), nullable=True, comment='Affected tenant (NULL for global actions)'),
        sa.Column('action', sa.String(100), nullable=False, comment='Action performed'),
        sa.Column('resource', sa.String(255), nullable=False, comment='Resource affected'),
        sa.Column('audit_metadata', postgresql.JSONB, nullable=True, server_default='{}', comment='Action details'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        schema='public'
    )
    op.create_index('ix_platform_audit_logs_wholesaler_id', 'platform_audit_logs', ['wholesaler_id'], schema='public')
    op.create_index('ix_platform_audit_logs_action', 'platform_audit_logs', ['action'], schema='public')
    op.create_index('ix_platform_audit_logs_created_at', 'platform_audit_logs', ['created_at'], schema='public')


def downgrade() -> None:
    op.drop_table('platform_audit_logs', schema='public')
