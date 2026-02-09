"""S7-3: BI Access Audit Trail

Revision ID: 014_s7_3_audit_trail
Revises: 013_s6_2_materialize_sales
Create Date: 2026-02-09

Philosophy: "Every policy decision is a fact. Facts are immutable."

🔒 Constraint S7-3-C1: Table lives in public schema (Control Plane).
🔒 Constraint S7-3-C2: Append-only — no UPDATE/DELETE at application layer.
   DB-level REVOKE is a Phase 8 ops task.

Changes:
1. Create sys_audit_logs table in public schema
2. Add composite index (tenant_id, created_at) for compliance queries
3. Add individual indexes on actor_id, asset_urn, allowed
4. JSONB metadata column for extensibility

Partitioning Strategy (deferred):
    When sys_audit_logs > 10M rows → Ops must enable monthly
    range partitioning on created_at + retention policy.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


# revision identifiers, used by Alembic.
revision = '014_s7_3_audit_trail'
down_revision = '013_s6_2_materialize_sales'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'sys_audit_logs',
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
            'actor_id',
            sa.String(255),
            nullable=False,
            comment='user_id from PolicySubject',
        ),
        sa.Column(
            'tenant_id',
            sa.String(255),
            nullable=False,
            comment='tenant_id from PolicySubject',
        ),
        sa.Column(
            'action',
            sa.String(50),
            nullable=False,
            comment='BIAction value: view/interact/export/manage',
        ),
        sa.Column(
            'asset_urn',
            sa.String(512),
            nullable=False,
            comment='Full URN of the target BI asset',
        ),
        sa.Column(
            'allowed',
            sa.Boolean(),
            nullable=False,
            comment='True if policy allowed the action',
        ),
        sa.Column(
            'policy_name',
            sa.String(100),
            nullable=False,
            comment='Policy rule that produced the decision',
        ),
        sa.Column(
            'reason',
            sa.Text(),
            nullable=False,
            comment='Sanitized reason (no PII)',
        ),
        sa.Column(
            'metadata',
            JSONB(),
            nullable=True,
            comment='Extensible context: request_id, IP, user_agent, etc.',
        ),
        sa.PrimaryKeyConstraint('id'),
        comment='S7-3: Append-only BI access audit trail (public schema)',
    )

    # Composite index for compliance queries: "show me all decisions for tenant X in date range"
    op.create_index(
        'ix_sys_audit_logs_tenant_created',
        'sys_audit_logs',
        ['tenant_id', 'created_at'],
    )

    # Individual indexes for common query patterns
    op.create_index(
        'ix_sys_audit_logs_actor',
        'sys_audit_logs',
        ['actor_id'],
    )
    op.create_index(
        'ix_sys_audit_logs_asset_urn',
        'sys_audit_logs',
        ['asset_urn'],
    )
    op.create_index(
        'ix_sys_audit_logs_allowed',
        'sys_audit_logs',
        ['allowed'],
    )


def downgrade() -> None:
    op.drop_index('ix_sys_audit_logs_allowed', table_name='sys_audit_logs')
    op.drop_index('ix_sys_audit_logs_asset_urn', table_name='sys_audit_logs')
    op.drop_index('ix_sys_audit_logs_actor', table_name='sys_audit_logs')
    op.drop_index('ix_sys_audit_logs_tenant_created', table_name='sys_audit_logs')
    op.drop_table('sys_audit_logs')
