"""S7-4-T3: Tenant-Scoped Reports — sys_reports table

Revision ID: 015_s7_4_sys_reports
Revises: 014_s7_3_audit_trail
Create Date: 2026-02-09

This migration creates the sys_reports table in the TENANT schema.
Unlike sys_audit_logs (public schema), sys_reports lives in each
tenant's schema because reports are tenant-scoped assets.

🔒 S7-4-C1: URN is auto-generated as urn:bi:report:<domain>:<id>.
    tenant_id is NOT embedded in the URN.
🔒 S7-4-C4: CRUD API must call invalidate_asset(urn) after mutations.

Note: This migration runs per-tenant via Alembic's tenant schema
migration strategy. The table inherits BaseModel columns:
id, created_at, updated_at, is_deleted, deleted_at, created_by, updated_by.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


# revision identifiers, used by Alembic.
revision = '015_s7_4_sys_reports'
down_revision = '014_s7_3_audit_trail'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'sys_reports',
        # BaseModel columns
        sa.Column(
            'id',
            UUID(as_uuid=True),
            server_default=sa.text('gen_random_uuid()'),
            nullable=False,
        ),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            'is_deleted',
            sa.Boolean(),
            server_default=sa.text('false'),
            nullable=False,
        ),
        sa.Column(
            'deleted_at',
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            'created_by',
            UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            'updated_by',
            UUID(as_uuid=True),
            nullable=True,
        ),
        # SysReport-specific columns
        sa.Column(
            'title',
            sa.String(256),
            nullable=False,
            comment='Human-readable report name',
        ),
        sa.Column(
            'description',
            sa.Text(),
            nullable=True,
            comment='Business-level description of the report',
        ),
        sa.Column(
            'domain',
            sa.String(50),
            nullable=False,
            server_default='custom',
            comment='BI domain for URN generation (e.g., sales, finance, custom)',
        ),
        sa.Column(
            'config',
            JSONB(),
            nullable=False,
            comment='Report configuration: layout, widgets, data sources',
        ),
        sa.Column(
            'owner_id',
            UUID(as_uuid=True),
            nullable=False,
            comment='UUID of the creating user (forced server-side)',
        ),
        sa.Column(
            'acl',
            JSONB(),
            nullable=False,
            server_default='[]',
            comment='ACL entries: user:<id>, role:<name>, tenant:*',
        ),
        sa.PrimaryKeyConstraint('id'),
        comment='S7-4: Tenant-scoped user-created BI reports',
    )

    op.create_index(
        'ix_sys_reports_owner_id',
        'sys_reports',
        ['owner_id'],
    )
    op.create_index(
        'ix_sys_reports_domain',
        'sys_reports',
        ['domain'],
    )


def downgrade() -> None:
    op.drop_index('ix_sys_reports_domain', table_name='sys_reports')
    op.drop_index('ix_sys_reports_owner_id', table_name='sys_reports')
    op.drop_table('sys_reports')
