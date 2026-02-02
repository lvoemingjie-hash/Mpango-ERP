"""Phase B6 - Payments idempotency key (tenant)

Revision ID: 006_phase_b6_payments_idempotency_key
Revises: 005_phase_b5_payments_minimal_loop
Create Date: 2026-01-31

Hardening:
- Tenant schema: add payments.idempotency_key and unique index on it.

Notes:
- Multi-tenancy is schema-per-tenant via search_path. Uniqueness inside tenant schema is equivalent to (tenant_id, key).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "006_phase_b6_payments_idempotency_key"
down_revision: Union[str, None] = "005_phase_b5_payments_minimal_loop"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    result = conn.execute(sa.text("SHOW search_path"))
    search_path = result.scalar() or ""

    is_tenant_migration = any(part.strip().startswith("t_") for part in search_path.split(","))
    if not is_tenant_migration:
        return

    if not _table_exists(conn, "payments"):
        return

    if not _column_exists(conn, "payments", "idempotency_key"):
        op.add_column(
            "payments",
            sa.Column("idempotency_key", sa.String(length=64), nullable=True),
        )

    if not _index_exists(conn, "uq_payments_idempotency_key"):
        op.create_index(
            "uq_payments_idempotency_key",
            "payments",
            ["idempotency_key"],
            unique=True,
            postgresql_where=sa.text("idempotency_key IS NOT NULL"),
        )


def downgrade() -> None:
    conn = op.get_bind()
    result = conn.execute(sa.text("SHOW search_path"))
    search_path = result.scalar() or ""

    is_tenant_migration = any(part.strip().startswith("t_") for part in search_path.split(","))
    if not is_tenant_migration:
        return

    if _table_exists(conn, "payments"):
        if _index_exists(conn, "uq_payments_idempotency_key"):
            op.drop_index("uq_payments_idempotency_key", table_name="payments")
        if _column_exists(conn, "payments", "idempotency_key"):
            op.drop_column("payments", "idempotency_key")


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
            "WHERE table_schema = current_schema() AND table_name = :table_name AND column_name = :column_name"
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
