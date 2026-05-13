"""020: Add audit columns to public.sys_jobs + server_default on id

Revision ID: 020_sys_jobs_audit_columns
Revises: 019_platform_audit_logs
Create Date: 2026-05-09

Brings public.sys_jobs into compliance with database_contract.md audit-column contract.
Job is a mutable infrastructure model (status transitions, retry logic), not append-only,
so soft-delete semantics are appropriate.

Changes:
- id: SET DEFAULT gen_random_uuid() (model already had default=uuid.uuid4 but no server_default)
- is_deleted: BOOLEAN NOT NULL DEFAULT false
- deleted_at: TIMESTAMPTZ nullable
"""
from alembic import op
import sqlalchemy as sa

revision = '020_sys_jobs_audit_columns'
down_revision = '019_platform_audit_logs'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add server_default for id (gen_random_uuid)
    op.alter_column(
        'sys_jobs', 'id',
        server_default=sa.text('gen_random_uuid()'),
        schema='public'
    )
    # Audit columns
    op.add_column(
        'sys_jobs',
        sa.Column('is_deleted', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        schema='public'
    )
    op.add_column(
        'sys_jobs',
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        schema='public'
    )


def downgrade() -> None:
    op.drop_column('sys_jobs', 'deleted_at', schema='public')
    op.drop_column('sys_jobs', 'is_deleted', schema='public')
    op.alter_column(
        'sys_jobs', 'id',
        server_default=None,
        schema='public'
    )
