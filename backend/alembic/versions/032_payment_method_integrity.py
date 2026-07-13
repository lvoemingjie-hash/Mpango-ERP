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

    equivalent_rows = [row for row in rows if _is_equivalent_payment_method_constraint(row)]
    incompatible_rows = [
        row
        for row in rows
        if not _is_equivalent_payment_method_constraint(row)
        and _is_payment_method_constraint_candidate(row)
    ]

    if canonical_rows:
        row = canonical_rows[0]
        if not _is_equivalent_payment_method_constraint(row):
            raise PreflightFailure(f"{schema}.{CONSTRAINT_NAME}: check constraint is incompatible")
        duplicate_equivalent = [row for row in equivalent_rows if row["conname"] != CONSTRAINT_NAME]
        if duplicate_equivalent:
            raise PreflightFailure(
                f"{schema}.{CONSTRAINT_NAME}: duplicate equivalent payment method constraints"
            )
        if incompatible_rows:
            names = ", ".join(row["conname"] for row in incompatible_rows)
            raise PreflightFailure(f"{schema}.{PAYMENTS}: incompatible method check constraints: {names}")
        return PaymentMethodPlan(schema=schema, action="none")

    if incompatible_rows:
        names = ", ".join(row["conname"] for row in incompatible_rows)
        raise PreflightFailure(f"{schema}.{PAYMENTS}: incompatible method check constraints: {names}")

    if len(equivalent_rows) > 1:
        raise PreflightFailure(f"{schema}.{PAYMENTS}: multiple equivalent payment method constraints")

    if equivalent_rows:
        return PaymentMethodPlan(
            schema=schema,
            action="rename",
            legacy_constraint_name=equivalent_rows[0]["conname"],
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
                   pg_get_constraintdef(c.oid, true) AS constraint_def,
                   pg_get_expr(c.conbin, c.conrelid, true) AS check_expr,
                   COALESCE(array_agg(a.attname ORDER BY cols.ordinality)
                       FILTER (WHERE a.attname IS NOT NULL), ARRAY[]::name[]) AS column_names
            FROM pg_constraint c
            JOIN pg_class t ON t.oid = c.conrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            LEFT JOIN LATERAL unnest(c.conkey) WITH ORDINALITY AS cols(attnum, ordinality)
                ON true
            LEFT JOIN pg_attribute a
                ON a.attrelid = c.conrelid AND a.attnum = cols.attnum
            WHERE n.nspname = :schema
              AND t.relname = :table_name
              AND c.contype = 'c'
            GROUP BY c.oid, c.conname, c.contype, c.convalidated, c.conbin, c.conrelid
            ORDER BY c.conname
            """
        ),
        {"schema": schema, "table_name": PAYMENTS},
    ).mappings()
    return [dict(row) for row in rows]


def _is_equivalent_payment_method_constraint(row: dict[str, Any]) -> bool:
    if _catalog_code(row["contype"]) != "c" or not bool(row["convalidated"]):
        return False
    if _catalog_column_names(row.get("column_names")) != ["method"]:
        return False

    expression = str(row.get("check_expr") or row.get("constraint_def") or "")
    normalized = _normalize_expression(expression)
    compact = _compact_sql(expression)
    if _has_forbidden_boolean_or_negative_semantics(normalized, compact):
        return False
    members = _positive_method_members(normalized)
    return members is not None and len(members) == len(CANONICAL_METHODS) and set(members) == set(CANONICAL_METHODS)


def _is_payment_method_constraint_candidate(row: dict[str, Any]) -> bool:
    columns = _catalog_column_names(row.get("column_names"))
    literal_values = set(re.findall(r"'([^']+)'", str(row.get("check_expr") or row.get("constraint_def") or "")))
    return "method" in columns or literal_values == set(CANONICAL_METHODS)


def _has_forbidden_boolean_or_negative_semantics(normalized: str, compact: str) -> bool:
    return bool(
        re.search(r"\bor\b|\band\b|\bnot\b", normalized)
        or re.search(r"\bcurrent_user\b|\bcurrent_role\b", normalized)
        or "<>" in normalized
        or "!=" in normalized
        or "||" in normalized
        or "<>all" in compact
        or "notin" in compact
        or "isdistinctfrom" in compact
    )


def _positive_method_members(normalized: str) -> list[str] | None:
    method_lhs = r"\(?method\)?(?:::[a-z_][a-z0-9_.]*(?:\s+[a-z_][a-z0-9_]*)?)?"
    in_match = re.fullmatch(method_lhs + r"\s+in\s*\((?P<members>.*)\)", normalized)
    if in_match:
        return _direct_string_literal_members(in_match.group("members"))

    any_match = re.fullmatch(
        method_lhs
        + r"\s*=\s*any\s*\(\s*array\[(?P<members>.*?)\]"
        + r"(?:::[a-z_][a-z0-9_.]*(?:\s+[a-z_][a-z0-9_]*)?\[\])?\s*\)",
        normalized,
    )
    if any_match:
        return _direct_string_literal_members(any_match.group("members"))

    return None


def _direct_string_literal_members(member_sql: str) -> list[str] | None:
    values: list[str] = []
    for member in _split_top_level_sql_members(member_sql):
        match = re.fullmatch(
            r"'([^']+)'(?:::[a-z_][a-z0-9_.]*(?:\s+[a-z_][a-z0-9_]*)?)?",
            member.strip(),
        )
        if not match:
            return None
        values.append(match.group(1))
    return values


def _split_top_level_sql_members(member_sql: str) -> list[str]:
    members: list[str] = []
    start = 0
    depth = 0
    in_quote = False
    index = 0
    while index < len(member_sql):
        char = member_sql[index]
        if char == "'":
            in_quote = not in_quote
        elif not in_quote:
            if char in "([":
                depth += 1
            elif char in ")]" and depth > 0:
                depth -= 1
            elif char == "," and depth == 0:
                members.append(member_sql[start:index].strip())
                start = index + 1
        index += 1
    members.append(member_sql[start:].strip())
    return members


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


def _normalize_expression(sql: str) -> str:
    return " ".join(sql.lower().split())


def _compact_sql(sql: str) -> str:
    return "".join(sql.lower().split())


def _catalog_column_names(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        stripped = value.strip("{}")
        return [part.strip().strip('"') for part in stripped.split(",") if part]
    return [str(part) for part in value]


def _catalog_code(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, memoryview):
        value = value.tobytes()
    if isinstance(value, bytes):
        return value.decode()
    return str(value)
