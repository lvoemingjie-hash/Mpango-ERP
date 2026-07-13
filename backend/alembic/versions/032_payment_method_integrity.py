"""DC-10F: constrain tenant payment methods.

Revision ID: 032_payment_method_integrity
Revises: 031_legacy_tenant_reconciliation
Create Date: 2026-07-13
"""
from __future__ import annotations

import re
from typing import Any

from alembic import context, op
import sqlalchemy as sa


revision = "032_payment_method_integrity"
down_revision = "031_legacy_tenant_reconciliation"
branch_labels = None
depends_on = None


CONSTRAINT_NAME = "ck_payments_method_canonical"
PAYMENTS = "payments"
TENANT_SCHEMA_RE = re.compile(r"^t_[0-9a-f]{32}$")
CANONICAL_METHODS = ("cash", "transfer", "credit")
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


class PaymentMethodPlan:
    def __init__(self, *, schema: str, action: str, legacy_constraint_name: str | None = None) -> None:
        self.schema = schema
        self.action = action
        self.legacy_constraint_name = legacy_constraint_name


def upgrade() -> None:
    bind = op.get_bind()
    plans = _preflight(bind)
    for plan in plans:
        _apply_plan(bind, plan)


def downgrade() -> None:
    bind = op.get_bind()
    for schema in _target_schemas(bind):
        if _constraint_exists(bind, schema, PAYMENTS, CONSTRAINT_NAME):
            bind.execute(sa.text(
                f"ALTER TABLE {_quote_ident(bind, schema)}.{_quote_ident(bind, PAYMENTS)} "
                f"DROP CONSTRAINT {_quote_ident(bind, CONSTRAINT_NAME)}"
            ))


def _preflight(bind) -> list[PaymentMethodPlan]:
    plans: list[PaymentMethodPlan] = []
    failures: list[str] = []
    for schema in _target_schemas(bind):
        try:
            plans.append(_plan_schema(bind, schema))
        except PreflightFailure as exc:
            failures.append(str(exc))
    if failures:
        raise PreflightFailure("DC-10F preflight failed: " + "; ".join(failures))
    return plans


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
               tr.status AS registration_status,
               w.id::text AS wholesaler_id,
               w.status AS wholesaler_status,
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
    missing = []
    for qualified_name in ("public.tenant_registrations", "public.wholesalers"):
        if _regclass_oid(bind, qualified_name) is None:
            missing.append(qualified_name)
    if missing:
        raise PreflightFailure("registry source unavailable: missing " + ", ".join(missing))


def _validate_registry_rows(bind, rows: list[dict[str, Any]]) -> None:
    failures: list[str] = []
    seen: dict[str, str] = {}
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
        else:
            seen[schema] = row["registration_id"]

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


def _plan_schema(bind, schema: str) -> PaymentMethodPlan:
    if not _table_exists(bind, schema, PAYMENTS):
        raise PreflightFailure(f"{schema}.{PAYMENTS}: table is missing")

    invalid_count = _invalid_method_count(bind, schema)
    if invalid_count > 0:
        raise PreflightFailure(
            f"{schema}.{PAYMENTS}.method contains {invalid_count} non-canonical or NULL rows"
        )

    rows = _payment_method_constraint_rows(bind, schema)
    canonical_rows = [row for row in rows if row["conname"] == CONSTRAINT_NAME]
    if len(canonical_rows) > 1:
        raise PreflightFailure(f"{schema}.{CONSTRAINT_NAME}: duplicate canonical constraints")
    if canonical_rows:
        row = canonical_rows[0]
        if not _is_equivalent_payment_method_constraint(row):
            raise PreflightFailure(f"{schema}.{CONSTRAINT_NAME}: check constraint is incompatible")
        return PaymentMethodPlan(schema=schema, action="none")

    equivalent_legacy = [row for row in rows if _is_equivalent_payment_method_constraint(row)]
    if equivalent_legacy:
        equivalent_legacy.sort(key=lambda row: row["conname"])
        return PaymentMethodPlan(
            schema=schema,
            action="rename",
            legacy_constraint_name=equivalent_legacy[0]["conname"],
        )

    return PaymentMethodPlan(schema=schema, action="add")


def _apply_plan(bind, plan: PaymentMethodPlan) -> None:
    qualified_table = f"{_quote_ident(bind, plan.schema)}.{_quote_ident(bind, PAYMENTS)}"
    if plan.action == "none":
        return
    if plan.action == "rename":
        bind.execute(sa.text(
            f"ALTER TABLE {qualified_table} "
            f"RENAME CONSTRAINT {_quote_ident(bind, plan.legacy_constraint_name)} "
            f"TO {_quote_ident(bind, CONSTRAINT_NAME)}"
        ))
        return
    if plan.action == "add":
        bind.execute(sa.text(
            f"ALTER TABLE {qualified_table} "
            f"ADD CONSTRAINT {_quote_ident(bind, CONSTRAINT_NAME)} "
            "CHECK (method IN ('cash', 'transfer', 'credit'))"
        ))
        return
    raise AssertionError(f"unknown payment method plan action: {plan.action}")


def _invalid_method_count(bind, schema: str) -> int:
    return int(bind.execute(
        sa.text(
            f"SELECT COUNT(*) FROM {_quote_ident(bind, schema)}.{_quote_ident(bind, PAYMENTS)} "
            "WHERE method IS NULL OR method NOT IN ('cash', 'transfer', 'credit')"
        )
    ).scalar() or 0)


def _payment_method_constraint_rows(bind, schema: str) -> list[dict[str, Any]]:
    rows = bind.execute(
        sa.text(
            """
            SELECT c.conname,
                   c.contype,
                   c.convalidated,
                   pg_get_constraintdef(c.oid, true) AS constraint_def
            FROM pg_constraint c
            JOIN pg_class t ON t.oid = c.conrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            WHERE n.nspname = :schema
              AND t.relname = :table_name
              AND c.contype = 'c'
            ORDER BY c.conname
            """
        ),
        {"schema": schema, "table_name": PAYMENTS},
    ).mappings()
    return [dict(row) for row in rows]


def _is_equivalent_payment_method_constraint(row: dict[str, Any]) -> bool:
    if _catalog_code(row["contype"]) != "c" or not bool(row["convalidated"]):
        return False
    constraint_def = _normalize_sql(str(row["constraint_def"] or ""))
    if "method" not in constraint_def:
        return False
    literal_values = set(re.findall(r"'([^']+)'", constraint_def))
    return literal_values == set(CANONICAL_METHODS)


def _constraint_exists(bind, schema: str, table_name: str, constraint_name: str) -> bool:
    return bool(bind.execute(
        sa.text(
            "SELECT 1 FROM pg_constraint c "
            "JOIN pg_class t ON t.oid = c.conrelid "
            "JOIN pg_namespace n ON n.oid = t.relnamespace "
            "WHERE n.nspname = :schema AND t.relname = :table_name "
            "AND c.conname = :constraint_name AND c.contype = 'c'"
        ),
        {"schema": schema, "table_name": table_name, "constraint_name": constraint_name},
    ).first())


def _table_exists(bind, schema: str, table_name: str) -> bool:
    return bool(bind.execute(
        sa.text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = :schema AND table_name = :table_name"
        ),
        {"schema": schema, "table_name": table_name},
    ).first())


def _schema_exists(bind, schema: str) -> bool:
    return bool(bind.execute(
        sa.text("SELECT 1 FROM pg_namespace WHERE nspname = :schema"),
        {"schema": schema},
    ).first())


def _regclass_oid(bind, qualified_name: str) -> int | None:
    return bind.execute(
        sa.text("SELECT to_regclass(:qualified_name)::oid"),
        {"qualified_name": qualified_name},
    ).scalar()


def _quote_ident(bind, identifier: str | None) -> str:
    if identifier is None:
        raise PreflightFailure("constraint identifier is missing")
    return bind.execute(
        sa.text("SELECT quote_ident(:identifier)"), {"identifier": identifier}
    ).scalar_one()


def _normalize_sql(sql: str) -> str:
    return "".join(sql.lower().split())


def _catalog_code(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, memoryview):
        value = value.tobytes()
    if isinstance(value, bytes):
        return value.decode()
    return str(value)
