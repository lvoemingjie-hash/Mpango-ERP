"""024: Data intake backend schema skeleton

Revision ID: 024_intake_skeleton
Revises: 023_inventory_reservations
Create Date: 2026-07-01

U4-C: tenant-schema intake staging foundation. This migration creates only the
four CTO-approved intake tables and is a no-op on public schema.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "024_intake_skeleton"
down_revision = "023_inventory_reservations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    search_path = conn.execute(sa.text("SHOW search_path")).scalar() or ""

    is_tenant = any(part.strip().startswith("t_") for part in search_path.split(","))
    if not is_tenant:
        return

    if not _table_exists(conn, "intake_workspaces"):
        op.create_table(
            "intake_workspaces",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("name", sa.String(length=160), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("source_type", sa.String(length=32), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'OPEN'")),
            sa.Column("approved_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        )

    if not _table_exists(conn, "intake_uploads"):
        op.create_table(
            "intake_uploads",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("filename", sa.String(length=255), nullable=False),
            sa.Column("content_type", sa.String(length=128), nullable=True),
            sa.Column("file_ext", sa.String(length=16), nullable=False),
            sa.Column("file_size_bytes", sa.Integer(), nullable=False),
            sa.Column("sha256", sa.CHAR(length=64), nullable=False),
            sa.Column("storage_key", sa.String(length=512), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'RECEIVED'")),
            sa.Column("row_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("column_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("headers_raw", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("headers_normalized", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("parse_summary", postgresql.JSONB(), nullable=True),
            sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["workspace_id"], ["intake_workspaces.id"], ondelete="CASCADE"),
        )

    if not _table_exists(conn, "intake_product_rows"):
        op.create_table(
            "intake_product_rows",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("upload_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("source_row_number", sa.Integer(), nullable=False),
            sa.Column("row_index", sa.Integer(), nullable=False),
            sa.Column("raw_values", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("normalized_values", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("mapping_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
            sa.Column("sku_code", sa.String(length=64), nullable=True),
            sa.Column("name", sa.String(length=255), nullable=True),
            sa.Column("unit", sa.String(length=32), nullable=True),
            sa.Column("category", sa.String(length=64), nullable=True),
            sa.Column("unit_price", sa.Numeric(precision=12, scale=2), nullable=True),
            sa.Column("barcode", sa.String(length=128), nullable=True),
            sa.Column("image_asset_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("review_status", sa.String(length=32), nullable=False, server_default=sa.text("'UNREVIEWED'")),
            sa.Column("dedupe_key", sa.String(length=160), nullable=True),
            sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["workspace_id"], ["intake_workspaces.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["upload_id"], ["intake_uploads.id"], ondelete="CASCADE"),
        )

    if not _table_exists(conn, "intake_validation_issues"):
        op.create_table(
            "intake_validation_issues",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("upload_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("row_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("source_row_number", sa.Integer(), nullable=True),
            sa.Column("severity", sa.String(length=16), nullable=False),
            sa.Column("code", sa.String(length=64), nullable=False),
            sa.Column("field", sa.String(length=128), nullable=True),
            sa.Column("source_header", sa.String(length=255), nullable=True),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("is_blocking", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("resolved_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["workspace_id"], ["intake_workspaces.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["upload_id"], ["intake_uploads.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["row_id"], ["intake_product_rows.id"], ondelete="CASCADE"),
        )

    _create_indexes(conn)


def downgrade() -> None:
    conn = op.get_bind()
    search_path = conn.execute(sa.text("SHOW search_path")).scalar() or ""

    is_tenant = any(part.strip().startswith("t_") for part in search_path.split(","))
    if not is_tenant:
        return

    for table in (
        "intake_validation_issues",
        "intake_product_rows",
        "intake_uploads",
        "intake_workspaces",
    ):
        if _table_exists(conn, table):
            op.drop_table(table)


def _create_indexes(conn) -> None:
    indexes = [
        ("ix_intake_workspaces_tenant_id", "intake_workspaces", ["tenant_id"]),
        ("ix_intake_workspaces_status", "intake_workspaces", ["status"]),
        ("ix_intake_workspaces_created_at", "intake_workspaces", ["created_at"]),
        ("ix_intake_uploads_workspace_id", "intake_uploads", ["workspace_id"]),
        ("ix_intake_uploads_tenant_id", "intake_uploads", ["tenant_id"]),
        ("ix_intake_product_rows_workspace_id", "intake_product_rows", ["workspace_id"]),
        ("ix_intake_product_rows_upload_order", "intake_product_rows", ["upload_id", "row_index"]),
        ("ix_intake_product_rows_review_status", "intake_product_rows", ["review_status"]),
        ("ix_intake_validation_issues_workspace_id", "intake_validation_issues", ["workspace_id"]),
        ("ix_intake_validation_issues_row_id", "intake_validation_issues", ["row_id"]),
        ("ix_intake_validation_issues_severity", "intake_validation_issues", ["severity"]),
    ]
    for index_name, table_name, columns in indexes:
        if not _index_exists(conn, index_name):
            op.create_index(index_name, table_name, columns)


def _index_exists(conn, index_name: str) -> bool:
    res = conn.execute(
        sa.text(
            "SELECT 1 FROM pg_indexes "
            "WHERE schemaname = current_schema() AND indexname = :index_name"
        ),
        {"index_name": index_name},
    )
    return res.first() is not None


def _table_exists(conn, table_name: str) -> bool:
    res = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = current_schema() AND table_name = :table_name"
        ),
        {"table_name": table_name},
    )
    return res.first() is not None
