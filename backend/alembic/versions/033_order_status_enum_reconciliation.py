"""DC-10L: reconcile tenant order status enums.

Revision ID: 033_order_status_enum_reconciliation
Revises: 032_payment_method_integrity
Create Date: 2026-07-14
"""
from __future__ import annotations

import re
from typing import Any

from alembic import context, op
import sqlalchemy as sa


revision = "033_order_status_enum_reconciliation"
down_revision = "032_payment_method_integrity"
branch_labels = None
depends_on = None


ORDERS = "orders"
ORDER_STATUS = "order_status"
TENANT_SCHEMA_RE = re.compile(r"^t_[0-9a-f]{32}$")
CANONICAL_ORDER_STATUSES = (
    "draft",
    "confirmed",
    "partially_paid",
    "paid",
    "fulfilled",
    "cancelled",
    "voided",
    "returned",
)
LIVE_REGISTRATION_STATUSES = (
    "pending_email_verification",
    "email_verified",
    "provisioning",
    "active",
    "failed",
)
WHOLESALER_ACTIVE_STATUSES = ("active", "provisioning")


class PreflightFailure(RuntimeError):
    pass


class OrderStatusPlan:
    def __init__(self, *, schema: str, missing_values: tuple[str, ...]) -> None:
        self.schema = schema
        self.missing_values = missing_values


def upgrade() -> None:
    bind = op.get_bind()
    for plan in _preflight(bind):
        _apply_plan(bind, plan)


def downgrade() -> None:
    # PostgreSQL enum values cannot be removed safely in place. Rollback uses
    # the release backup and application rollback runbook.
    pass


def _preflight(bind) -> list[OrderStatusPlan]:
    plans: list[OrderStatusPlan] = []
    failures: list[str] = []
    for schema in _target_schemas(bind):
        try:
            plans.append(_plan_schema(bind, schema))
        except PreflightFailure as exc:
            failures.append(str(exc))
    if failures:
        raise PreflightFailure("DC-10L preflight failed: " + "; ".join(failures))
    return plans


def _plan_schema(bind, schema: str) -> OrderStatusPlan:
    if not _table_exists(bind, schema, ORDERS):
        raise PreflightFailure(f"{schema}.{ORDERS}: table is missing")

    metadata = _status_column_metadata(bind, schema)
    if metadata is None:
        raise PreflightFailure(f"{schema}.{ORDERS}.status: column is missing")
    if metadata["type_schema"] != schema or metadata["type_name"] != ORDER_STATUS:
        raise PreflightFailure(
            f"{schema}.{ORDERS}.status: expected schema-local {ORDER_STATUS} enum"
        )
    if _catalog_code(metadata["type_kind"]) != "e":
        raise PreflightFailure(f"{schema}.{ORDER_STATUS}: type is not an enum")

    invalid_count = _noncanonical_row_count(bind, schema)
    if invalid_count:
        raise PreflightFailure(
            f"{schema}.{ORDERS}.status contains {invalid_count} non-canonical rows"
        )

    existing = set(_enum_labels(bind, schema))
    missing = tuple(value for value in CANONICAL_ORDER_STATUSES if value not in existing)
    return OrderStatusPlan(schema=schema, missing_values=missing)


def _apply_plan(bind, plan: OrderStatusPlan) -> None:
    qualified_type = (
        f"{_quote_ident(bind, plan.schema)}.{_quote_ident(bind, ORDER_STATUS)}"
    )
    for value in plan.missing_values:
        bind.execute(
            sa.text(
                f"ALTER TYPE {qualified_type} ADD VALUE IF NOT EXISTS "
                f"{_quote_literal(bind, value)}"
            )
        )


def _status_column_metadata(bind, schema: str) -> dict[str, Any] | None:
    row = bind.execute(
        sa.text(
            """
            SELECT type_ns.nspname AS type_schema,
                   typ.typname AS type_name,
                   typ.typtype AS type_kind
            FROM pg_attribute attr
            JOIN pg_class rel ON rel.oid = attr.attrelid
            JOIN pg_namespace rel_ns ON rel_ns.oid = rel.relnamespace
            JOIN pg_type typ ON typ.oid = attr.atttypid
            JOIN pg_namespace type_ns ON type_ns.oid = typ.typnamespace
            WHERE rel_ns.nspname = :schema
              AND rel.relname = :table
              AND attr.attname = 'status'
              AND attr.attnum > 0
              AND NOT attr.attisdropped
            """
        ),
        {"schema": schema, "table": ORDERS},
    ).mappings().one_or_none()
    return dict(row) if row is not None else None


def _enum_labels(bind, schema: str) -> list[str]:
    rows = bind.execute(
        sa.text(
            """
            SELECT enum.enumlabel
            FROM pg_enum enum
            JOIN pg_type typ ON typ.oid = enum.enumtypid
            JOIN pg_namespace ns ON ns.oid = typ.typnamespace
            WHERE ns.nspname = :schema
              AND typ.typname = :type_name
            ORDER BY enum.enumsortorder
            """
        ),
        {"schema": schema, "type_name": ORDER_STATUS},
    ).scalars()
    return [_catalog_code(value) for value in rows]


def _noncanonical_row_count(bind, schema: str) -> int:
    values = ", ".join(_quote_literal(bind, value) for value in CANONICAL_ORDER_STATUSES)
    return int(
        bind.execute(
            sa.text(
                f"SELECT COUNT(*) FROM {_quote_ident(bind, schema)}.{_quote_ident(bind, ORDERS)} "
                f"WHERE status IS NULL OR status::text NOT IN ({values})"
            )
        ).scalar()
        or 0
    )


def _target_schemas(bind) -> list[str]:
    tenant_schema = _tenant_schema_argument()
    if tenant_schema is not None:
        _validate_tenant_schema_name(tenant_schema, "tenant_schema argument")

    rows = _registered_tenants(bind)
    _validate_registry_rows(bind, rows)
    if tenant_schema is None:
        return [row["tenant_schema"] for row in rows]
    if not any(row["tenant_schema"] == tenant_schema for row in rows):
        raise PreflightFailure("tenant_schema argument is not a live registered tenant")
    return [tenant_schema]


def _tenant_schema_argument() -> str | None:
    try:
        value = context.get_x_argument(as_dictionary=True).get("tenant_schema")
    except Exception:
        value = None
    if value is None or str(value).strip() == "":
        return None
    return str(value)


def _registered_tenants(bind) -> list[dict[str, Any]]:
    _ensure_registry_tables_exist(bind)
    stmt = sa.text(
        """
        SELECT tr.id::text AS registration_id,
               tr.tenant_schema AS tenant_schema,
               w.id::text AS wholesaler_id,
               ('t_' || replace(w.id::text, '-', '')) AS derived_schema
        FROM public.tenant_registrations tr
        JOIN public.wholesalers w ON w.id = tr.wholesaler_id
        WHERE tr.status IN :registration_statuses
          AND w.status IN :wholesaler_statuses
        ORDER BY tr.tenant_schema, tr.id
        """
    ).bindparams(
        sa.bindparam("registration_statuses", expanding=True),
        sa.bindparam("wholesaler_statuses", expanding=True),
    )
    rows = bind.execute(
        stmt,
        {
            "registration_statuses": list(LIVE_REGISTRATION_STATUSES),
            "wholesaler_statuses": list(WHOLESALER_ACTIVE_STATUSES),
        },
    ).mappings()
    return [dict(row) for row in rows]


def _ensure_registry_tables_exist(bind) -> None:
    missing = [
        name
        for name in ("public.tenant_registrations", "public.wholesalers")
        if _regclass_oid(bind, name) is None
    ]
    if missing:
        raise PreflightFailure("registry source unavailable: missing " + ", ".join(missing))


def _validate_registry_rows(bind, rows: list[dict[str, Any]]) -> None:
    failures: list[str] = []
    seen: set[str] = set()
    for row in rows:
        schema = row["tenant_schema"]
        evidence_name = schema or f"registration {row['registration_id']}"
        try:
            _validate_tenant_schema_name(schema, evidence_name)
        except PreflightFailure as exc:
            failures.append(str(exc))
            continue
        if schema in seen:
            failures.append(f"{schema}: duplicate live tenant registry rows")
        seen.add(schema)
        if schema != row["derived_schema"]:
            failures.append(f"{schema}: tenant_schema does not match wholesaler-derived schema")
        if not _schema_exists(bind, schema):
            failures.append(f"{schema}: registered tenant schema is missing")
    if failures:
        raise PreflightFailure("; ".join(failures))


def _validate_tenant_schema_name(schema: str | None, evidence_name: str) -> None:
    if schema is None or schema.strip() == "":
        raise PreflightFailure(f"{evidence_name}: tenant_schema is missing")
    if len(schema) > 63 or not TENANT_SCHEMA_RE.fullmatch(schema):
        raise PreflightFailure(f"{evidence_name}: tenant_schema is not a valid derived tenant identifier")


def _table_exists(bind, schema: str, table: str) -> bool:
    return _regclass_oid(bind, f"{_quote_ident(bind, schema)}.{_quote_ident(bind, table)}") is not None


def _schema_exists(bind, schema: str) -> bool:
    return bind.execute(
        sa.text("SELECT 1 FROM pg_namespace WHERE nspname = :schema"),
        {"schema": schema},
    ).first() is not None


def _regclass_oid(bind, qualified_name: str) -> int | None:
    return bind.execute(
        sa.text("SELECT to_regclass(:qualified_name)::oid"),
        {"qualified_name": qualified_name},
    ).scalar()


def _quote_ident(bind, value: str) -> str:
    return str(
        bind.execute(sa.text("SELECT quote_ident(:value)"), {"value": value}).scalar_one()
    )


def _quote_literal(bind, value: str) -> str:
    return str(
        bind.execute(sa.text("SELECT quote_literal(:value)"), {"value": value}).scalar_one()
    )


def _catalog_code(value: Any) -> str:
    if isinstance(value, memoryview):
        value = value.tobytes()
    if isinstance(value, bytes):
        return value.decode("ascii")
    return str(value)
