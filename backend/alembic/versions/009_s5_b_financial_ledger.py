"""S5-B Financial Ledger (tenant schema)

Revision ID: 009_s5_b_financial_ledger
Revises: 008_s4_b_job_persistence
Create Date: 2026-02-06

Tenant-schema migration:
- Create account_type enum
- Create ledger_entries table
- Add indexes for efficient querying
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "009_s5_b_financial_ledger"
down_revision: Union[str, None] = "008_s4_b_job_persistence"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    result = conn.execute(sa.text("SHOW search_path"))
    search_path = result.scalar() or ""

    is_tenant_migration = any(part.strip().startswith("t_") for part in search_path.split(","))
    if not is_tenant_migration:
        return

    # 1) Create account_type enum
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE account_type AS ENUM ('receivable', 'revenue', 'cash', 'liability');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)

    # 2) Create ledger_entries table
    op.create_table(
        'ledger_entries',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('transaction_date', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('account_type', sa.Enum('receivable', 'revenue', 'cash', 'liability', name='account_type'), nullable=False),
        sa.Column('amount', sa.Numeric(precision=20, scale=4), nullable=False),
        sa.Column('reference_type', sa.String(length=50), nullable=False),
        sa.Column('reference_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        # BaseModel columns
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('updated_by', postgresql.UUID(as_uuid=True), nullable=True),
    )

    # 3) Create indexes
    op.create_index('ix_ledger_entries_reference', 'ledger_entries', ['reference_type', 'reference_id'])
    op.create_index('ix_ledger_entries_account_type', 'ledger_entries', ['account_type'])
    op.create_index('ix_ledger_entries_transaction_date', 'ledger_entries', ['transaction_date'])


def downgrade() -> None:
    conn = op.get_bind()
    result = conn.execute(sa.text("SHOW search_path"))
    search_path = result.scalar() or ""

    is_tenant_migration = any(part.strip().startswith("t_") for part in search_path.split(","))
    if not is_tenant_migration:
        return

    # Drop indexes
    op.drop_index('ix_ledger_entries_transaction_date', table_name='ledger_entries')
    op.drop_index('ix_ledger_entries_account_type', table_name='ledger_entries')
    op.drop_index('ix_ledger_entries_reference', table_name='ledger_entries')

    # Drop table
    op.drop_table('ledger_entries')

    # Drop enum
    op.execute('DROP TYPE IF EXISTS account_type')
