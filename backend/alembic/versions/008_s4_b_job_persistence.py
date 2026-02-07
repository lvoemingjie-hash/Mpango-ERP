"""S4-B: Job Persistence - Add sys_jobs table for job tracking

Revision ID: 008_s4_b_job_persistence
Revises: 007_s3_b_index_hygiene
Create Date: 2026-02-06

S4-B: Job Persistence & Retry
Philosophy: "Jobs are not fire-and-forget, they are tracked and retryable."

This migration creates the public.sys_jobs table for persistent job tracking.
Jobs are stored in public schema as they may cross tenants.

Table: public.sys_jobs
- id: UUID primary key
- job_name: Name of the job handler
- payload: JSONB job parameters
- status: pending, running, completed, failed
- attempts: Number of execution attempts
- max_retries: Maximum retry attempts (default: 3)
- last_error: Error message from last failure
- Timestamps: created_at, updated_at, started_at, completed_at
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '008_s4_b_job_persistence'
down_revision: Union[str, None] = '007_s3_b_index_hygiene'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    S4-B: Create sys_jobs table for job persistence.
    
    Features:
    - UUID primary key
    - JSONB payload for flexible job parameters
    - Status tracking (pending, running, completed, failed)
    - Retry tracking (attempts, max_retries)
    - Error logging (last_error)
    - Comprehensive timestamps
    """
    
    # Create sys_jobs table in public schema
    op.create_table(
        'sys_jobs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('job_name', sa.String(length=255), nullable=False),
        sa.Column('payload', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('max_retries', sa.Integer(), nullable=False),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        schema='public'
    )
    
    # Create indexes for common queries
    # - job_name: Filter by job type
    op.create_index('ix_sys_jobs_job_name', 'sys_jobs', ['job_name'], unique=False, schema='public')
    
    # - status: Filter by job status (pending, running, completed, failed)
    op.create_index('ix_sys_jobs_status', 'sys_jobs', ['status'], unique=False, schema='public')
    
    # - created_at: Sort by creation time
    op.create_index('ix_sys_jobs_created_at', 'sys_jobs', ['created_at'], unique=False, schema='public')
    
    # - Composite index for retry queries: status + attempts
    # Used to find failed jobs that can be retried
    op.create_index(
        'ix_sys_jobs_status_attempts',
        'sys_jobs',
        ['status', 'attempts'],
        unique=False,
        schema='public'
    )


def downgrade() -> None:
    """Remove sys_jobs table and indexes."""
    
    # Drop indexes
    op.drop_index('ix_sys_jobs_status_attempts', table_name='sys_jobs', schema='public')
    op.drop_index('ix_sys_jobs_created_at', table_name='sys_jobs', schema='public')
    op.drop_index('ix_sys_jobs_status', table_name='sys_jobs', schema='public')
    op.drop_index('ix_sys_jobs_job_name', table_name='sys_jobs', schema='public')
    
    # Drop table
    op.drop_table('sys_jobs', schema='public')
