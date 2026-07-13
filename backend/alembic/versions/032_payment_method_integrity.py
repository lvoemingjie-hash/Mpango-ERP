"""DC-10F: constrain tenant payment methods.

Revision ID: 032_payment_method_integrity
Revises: 031_legacy_tenant_reconciliation
Create Date: 2026-07-13
"""
from __future__ import annotations

import re

from alembic import context, op
import sqlalchemy as sa


revision = "032_payment_method_integrity"
down_revision = "031_legacy_tenant_reconciliation"
branch_labels = None
depends_on = None


CONSTRAINT_NAME = "ck_payments_method_canonical"
TENANT_SCHEMA_RE = re.compile(r"^t_[A-Za-z0-9_]+$")


def upgrade() -> None:
    conn = op.get_bind()
    for schema in _target_schemas(conn):
        invalid_count = conn.execute(
            sa.text(
                f"SELECT COUNT(*) FROM {_quote_ident(schema)}.payments "
                "WHERE method NOT IN ('cash', 'transfer', 'credit')"
            )
        ).scalar()
        if invalid_count and int(invalid_count) > 0:
            raise RuntimeError(
                f"Migration 032: {schema}.payments.method contains "
                f"{invalid_count} non-canonical values. Resolve rows before "
                "applying ck_payments_method_canonical."
            )

        if not _constraint_exists(conn, schema, "payments", CONSTRAINT_NAME):
            conn.execute(sa.text(
                f"ALTER TABLE {_quote_ident(schema)}.payments "
                f"ADD CONSTRAINT {CONSTRAINT_NAME} "
                "CHECK (method IN ('cash', 'transfer', 'credit'))"
            ))


def downgrade() -> None:
    conn = op.get_bind()
    for schema in _target_schemas(conn):
        if _constraint_exists(conn, schema, "payments", CONSTRAINT_NAME):
            conn.execute(sa.text(
                f"ALTER TABLE {_quote_ident(schema)}.payments "
                f"DROP CONSTRAINT {CONSTRAINT_NAME}"
            ))


def _target_schemas(conn) -> list[str]:
    tenant_schema = context.get_x_argument(as_dictionary=True).get("tenant_schema")
    if tenant_schema:
        if not TENANT_SCHEMA_RE.fullmatch(tenant_schema):
            return []
        return [tenant_schema] if _table_exists(conn, tenant_schema, "payments") else []

    rows = conn.execute(
        sa.text(
            "SELECT table_schema FROM information_schema.tables "
            "WHERE table_name = 'payments' AND table_schema LIKE 't\\_%' ESCAPE '\\' "
            "ORDER BY table_schema"
        )
    ).scalars().all()
    return [schema for schema in rows if TENANT_SCHEMA_RE.fullmatch(schema)]


def _table_exists(conn, schema: str, table_name: str) -> bool:
    res = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = :schema AND table_name = :table_name"
        ),
        {"schema": schema, "table_name": table_name},
    )
    return res.first() is not None


def _constraint_exists(conn, schema: str, table_name: str, constraint_name: str) -> bool:
    res = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.table_constraints "
            "WHERE table_schema = :schema "
            "AND table_name = :table_name "
            "AND constraint_name = :constraint_name"
        ),
        {"schema": schema, "table_name": table_name, "constraint_name": constraint_name},
    )
    return res.first() is not None


def _quote_ident(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'
