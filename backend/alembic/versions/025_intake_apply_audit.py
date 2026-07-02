"""025: Intake apply audit contract

Revision ID: 025_intake_apply_audit
Revises: 024_intake_skeleton
Create Date: 2026-07-02

U4-I-B1: add tenant-schema intake apply lifecycle/audit columns only. This
migration does not write SKUs and is a no-op on public schema.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "025_intake_apply_audit"
down_revision = "024_intake_skeleton"
branch_labels = None
depends_on = None


WORKSPACE_APPLY_STATUSES = ("not_applied", "applying", "applied", "failed")
ROW_APPLY_STATUSES = ("not_applied", "applied", "failed", "skipped")


def upgrade() -> None:
    conn = op.get_bind()
    search_path = conn.execute(sa.text("SHOW search_path")).scalar() or ""

    is_tenant = any(part.strip().startswith("t_") for part in search_path.split(","))
    if not is_tenant:
        return

    if not _table_exists(conn, "intake_workspaces") or not _table_exists(conn, "intake_product_rows"):
        return

    _add_column_if_missing(
        conn,
        "intake_workspaces",
        "apply_status",
        sa.Column("apply_status", sa.String(length=32), nullable=False, server_default=sa.text("'not_applied'")),
    )
    _add_column_if_missing(
        conn,
        "intake_workspaces",
        "applied_at",
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
    )
    _add_column_if_missing(
        conn,
        "intake_workspaces",
        "applied_by",
        sa.Column("applied_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    _add_column_if_missing(
        conn,
        "intake_workspaces",
        "apply_result",
        sa.Column("apply_result", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )

    _add_column_if_missing(
        conn,
        "intake_product_rows",
        "target_sku_id",
        sa.Column("target_sku_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    _add_column_if_missing(
        conn,
        "intake_product_rows",
        "apply_status",
        sa.Column("apply_status", sa.String(length=32), nullable=False, server_default=sa.text("'not_applied'")),
    )
    _add_column_if_missing(
        conn,
        "intake_product_rows",
        "apply_error_code",
        sa.Column("apply_error_code", sa.String(length=64), nullable=True),
    )
    _add_column_if_missing(
        conn,
        "intake_product_rows",
        "apply_error_message",
        sa.Column("apply_error_message", sa.Text(), nullable=True),
    )

    _add_check_constraint_if_missing(
        conn,
        "intake_workspaces",
        "ck_intake_workspaces_apply_status",
        "apply_status IN ('not_applied', 'applying', 'applied', 'failed')",
    )
    _add_check_constraint_if_missing(
        conn,
        "intake_product_rows",
        "ck_intake_product_rows_apply_status",
        "apply_status IN ('not_applied', 'applied', 'failed', 'skipped')",
    )

    _create_indexes(conn)


def downgrade() -> None:
    conn = op.get_bind()
    search_path = conn.execute(sa.text("SHOW search_path")).scalar() or ""

    is_tenant = any(part.strip().startswith("t_") for part in search_path.split(","))
    if not is_tenant:
        return

    if _index_exists(conn, "ix_intake_product_rows_target_sku_id"):
        op.drop_index("ix_intake_product_rows_target_sku_id", table_name="intake_product_rows")
    if _index_exists(conn, "ix_intake_workspaces_apply_status"):
        op.drop_index("ix_intake_workspaces_apply_status", table_name="intake_workspaces")
    _drop_constraint_if_exists(conn, "intake_product_rows", "ck_intake_product_rows_apply_status")
    _drop_constraint_if_exists(conn, "intake_workspaces", "ck_intake_workspaces_apply_status")
    for table_name, column_name in (
        ("intake_product_rows", "apply_error_message"),
        ("intake_product_rows", "apply_error_code"),
        ("intake_product_rows", "apply_status"),
        ("intake_product_rows", "target_sku_id"),
        ("intake_workspaces", "apply_result"),
        ("intake_workspaces", "applied_by"),
        ("intake_workspaces", "applied_at"),
        ("intake_workspaces", "apply_status"),
    ):
        if _column_exists(conn, table_name, column_name):
            op.drop_column(table_name, column_name)


def _create_indexes(conn) -> None:
    indexes = [
        ("ix_intake_workspaces_apply_status", "intake_workspaces", ["apply_status"]),
        ("ix_intake_product_rows_target_sku_id", "intake_product_rows", ["target_sku_id"]),
    ]
    for index_name, table_name, columns in indexes:
        if not _index_exists(conn, index_name):
            op.create_index(index_name, table_name, columns)


def _add_column_if_missing(conn, table_name: str, column_name: str, column: sa.Column) -> None:
    if not _column_exists(conn, table_name, column_name):
        op.add_column(table_name, column)


def _add_check_constraint_if_missing(conn, table_name: str, constraint_name: str, sql_text: str) -> None:
    if not _constraint_exists(conn, table_name, constraint_name):
        op.create_check_constraint(constraint_name, table_name, sa.text(sql_text))


def _drop_constraint_if_exists(conn, table_name: str, constraint_name: str) -> None:
    if _constraint_exists(conn, table_name, constraint_name):
        op.drop_constraint(constraint_name, table_name, type_="check")


def _table_exists(conn, table_name: str) -> bool:
    res = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = current_schema() AND table_name = :table_name"
        ),
        {"table_name": table_name},
    )
    return res.first() is not None


def _column_exists(conn, table_name: str, column_name: str) -> bool:
    res = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = :table_name "
            "AND column_name = :column_name"
        ),
        {"table_name": table_name, "column_name": column_name},
    )
    return res.first() is not None


def _index_exists(conn, index_name: str) -> bool:
    res = conn.execute(
        sa.text(
            "SELECT 1 FROM pg_indexes "
            "WHERE schemaname = current_schema() AND indexname = :index_name"
        ),
        {"index_name": index_name},
    )
    return res.first() is not None


def _constraint_exists(conn, table_name: str, constraint_name: str) -> bool:
    res = conn.execute(
        sa.text(
            "SELECT 1 FROM pg_constraint c "
            "JOIN pg_class t ON t.oid = c.conrelid "
            "JOIN pg_namespace n ON n.oid = c.connamespace "
            "WHERE n.nspname = current_schema() "
            "AND t.relname = :table_name "
            "AND c.conname = :constraint_name "
            "AND c.contype = 'c'"
        ),
        {"table_name": table_name, "constraint_name": constraint_name},
    )
    return res.first() is not None
