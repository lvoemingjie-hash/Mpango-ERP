"""022: Create import_runs table for agent-operable import contract

Revision ID: 022_import_runs
Revises: 021_tenant_payments_retailer_id_transaction_id
Create Date: 2026-06-12

U3-B1 Contract Foundation: tenant-schema table for tracking the 3-phase
import contract (preview → validate → apply). Each row represents one
import session with stable import_id, phase status, field mapping,
validation results, apply results, and audit metadata.

This migration is tenant-only (no-op on public schema).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "022_import_runs"
down_revision = "021_tenant_payments_retailer_id_transaction_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    result = conn.execute(sa.text("SHOW search_path"))
    search_path = result.scalar() or ""

    # Only run on tenant schemas (t_*), not public
    is_tenant = any(part.strip().startswith("t_") for part in search_path.split(","))
    if not is_tenant:
        return

    if _table_exists(conn, "import_runs"):
        return

    op.create_table(
        "import_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("import_id", sa.String(length=64), nullable=False, unique=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False,
                  server_default=sa.text("'previewed'")),
        sa.Column("source_filename", sa.String(length=255), nullable=True),
        sa.Column("source_encoding", sa.String(length=32), nullable=True),
        sa.Column("total_rows", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("valid_rows", sa.Integer(), nullable=True),
        sa.Column("error_rows", sa.Integer(), nullable=True),
        sa.Column("warning_rows", sa.Integer(), nullable=True),
        sa.Column("mapping", postgresql.JSONB(), nullable=True),
        sa.Column("validation_result", postgresql.JSONB(), nullable=True),
        sa.Column("apply_result", postgresql.JSONB(), nullable=True),
        sa.Column("created_rows", sa.Integer(), nullable=True, server_default=sa.text("0")),
        sa.Column("skipped_rows", sa.Integer(), nullable=True, server_default=sa.text("0")),
        sa.Column("updated_rows", sa.Integer(), nullable=True, server_default=sa.text("0")),
        sa.Column("applied_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("is_deleted", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index("ix_import_runs_import_id", "import_runs", ["import_id"], unique=True)
    op.create_index("ix_import_runs_status", "import_runs", ["status"])
    op.create_index("ix_import_runs_tenant_id", "import_runs", ["tenant_id"])
    op.create_index("ix_import_runs_created_at", "import_runs", ["created_at"])


def downgrade() -> None:
    conn = op.get_bind()
    result = conn.execute(sa.text("SHOW search_path"))
    search_path = result.scalar() or ""

    is_tenant = any(part.strip().startswith("t_") for part in search_path.split(","))
    if not is_tenant:
        return

    if _table_exists(conn, "import_runs"):
        op.drop_table("import_runs")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _table_exists(conn, table_name: str) -> bool:
    res = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = current_schema() AND table_name = :table_name"
        ),
        {"table_name": table_name},
    )
    return res.first() is not None
