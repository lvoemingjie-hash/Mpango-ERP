"""DC-11T4H receivable collection integrity.

Revision ID: 035_receivable_collection_integrity
Revises: 034_platform_operators
Create Date: 2026-07-22
"""
from __future__ import annotations

import re
from typing import Any

from alembic import op
import sqlalchemy as sa


revision = "035_receivable_collection_integrity"
down_revision = "034_platform_operators"
branch_labels = None
depends_on = None


PUBLIC_SCHEMA = "public"
BINDINGS = "wholesaler_retailer_bindings"
ORDERS = "orders"
PAYMENTS = "payments"
CONSTRAINT_NAME = "ck_wrb_outstanding_balance_non_negative"
TENANT_SCHEMA_RE = re.compile(r"^t_[0-9a-f]{32}$")
LIVE_REGISTRATION_STATUSES = (
    "pending_email_verification",
    "email_verified",
    "provisioning",
    "active",
    "failed",
)
WHOLESALER_ACTIVE_STATUSES = ("active", "provisioning")
PAYMENT_METHODS = ("cash", "transfer", "credit")


class PreflightFailure(RuntimeError):
    pass


def upgrade() -> None:
    bind = op.get_bind()
    _ensure_public_contract(bind)
    rows = _registered_tenants(bind)
    _validate_registry_rows(bind, rows)
    _validate_nonzero_bindings_are_reconstructable(bind, rows)
    for row in rows:
        _validate_payment_history(bind, row)
        _reconstruct_binding_balances(bind, row)
    _validate_no_negative_bindings_remain(bind)
    _ensure_non_negative_constraint(bind)


def downgrade() -> None:
    bind = op.get_bind()
    if _constraint_exists(bind, PUBLIC_SCHEMA, BINDINGS, CONSTRAINT_NAME):
        bind.execute(sa.text(
            f"ALTER TABLE {_qualified(bind, PUBLIC_SCHEMA, BINDINGS)} "
            f"DROP CONSTRAINT {_quote_ident(bind, CONSTRAINT_NAME)}"
        ))


def _ensure_public_contract(bind) -> None:
    missing = []
    for qualified_name in (
        "public.wholesaler_retailer_bindings",
        "public.tenant_registrations",
        "public.wholesalers",
    ):
        if _regclass_oid(bind, qualified_name) is None:
            missing.append(qualified_name)
    if missing:
        raise PreflightFailure("registry source unavailable: missing " + ", ".join(missing))
    if not _column_exists(bind, PUBLIC_SCHEMA, BINDINGS, "outstanding_balance"):
        raise PreflightFailure("public.wholesaler_retailer_bindings.outstanding_balance is missing")


def _registered_tenants(bind) -> list[dict[str, Any]]:
    stmt = sa.text(
        """
        SELECT tr.id::text AS registration_id,
               tr.tenant_schema AS tenant_schema,
               tr.status AS registration_status,
               tr.wholesaler_id::text AS registration_wholesaler_id,
               tr.owner_email AS owner_email,
               w.id::text AS wholesaler_id,
               w.status AS wholesaler_status,
               ('t_' || replace(w.id::text, '-', '')) AS derived_schema
        FROM public.tenant_registrations tr
        JOIN public.wholesalers w ON w.id = tr.wholesaler_id
        WHERE tr.is_deleted IS FALSE
          AND tr.status IN :registration_statuses
          AND w.is_deleted IS FALSE
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


def _validate_registry_rows(bind, rows: list[dict[str, Any]]) -> None:
    failures: list[str] = []
    seen_schemas: dict[str, str] = {}
    seen_wholesalers: dict[str, str] = {}
    for row in rows:
        schema = row["tenant_schema"]
        registration_id = row["registration_id"]
        evidence_name = schema or f"registration {registration_id}"
        try:
            _validate_tenant_schema_name(schema, evidence_name)
        except PreflightFailure as exc:
            failures.append(str(exc))
            continue

        if schema in seen_schemas:
            failures.append(f"{schema}: duplicate live tenant registry rows")
        seen_schemas[schema] = registration_id

        wholesaler_id = row["wholesaler_id"]
        if wholesaler_id in seen_wholesalers:
            failures.append(f"{wholesaler_id}: duplicate live wholesaler registry rows")
        seen_wholesalers[wholesaler_id] = registration_id

        if row["registration_wholesaler_id"] != wholesaler_id:
            failures.append(f"{schema}: registration wholesaler does not match joined wholesaler")
        if schema != row["derived_schema"]:
            failures.append(f"{schema}: tenant_schema does not match wholesaler-derived schema")
        if not _schema_exists(bind, schema):
            failures.append(f"{schema}: registered tenant schema is missing")
            continue
        for table_name in (ORDERS, PAYMENTS):
            if not _table_exists(bind, schema, table_name):
                failures.append(f"{schema}.{table_name}: table is missing")

    if failures:
        raise PreflightFailure("DC-11T4H preflight failed: " + "; ".join(failures))


def _validate_tenant_schema_name(schema: str | None, evidence_name: str) -> None:
    if schema is None or schema.strip() == "":
        raise PreflightFailure(f"{evidence_name}: tenant_schema is missing")
    if len(schema) > 63 or not TENANT_SCHEMA_RE.fullmatch(schema):
        raise PreflightFailure(f"{evidence_name}: tenant_schema is not a valid derived tenant identifier")


def _validate_nonzero_bindings_are_reconstructable(bind, rows: list[dict[str, Any]]) -> None:
    registered_wholesalers = {row["wholesaler_id"] for row in rows}
    stmt = sa.text(
        """
        SELECT wrb.wholesaler_id::text AS wholesaler_id,
               COUNT(*) AS binding_count
        FROM public.wholesaler_retailer_bindings wrb
        JOIN public.wholesalers w ON w.id = wrb.wholesaler_id
        WHERE wrb.is_deleted IS FALSE
          AND wrb.outstanding_balance <> 0
          AND w.is_deleted IS FALSE
          AND w.status IN :wholesaler_statuses
        GROUP BY wrb.wholesaler_id
        ORDER BY wrb.wholesaler_id
        """
    ).bindparams(sa.bindparam("wholesaler_statuses", expanding=True))
    rows_with_balances = bind.execute(
        stmt,
        {"wholesaler_statuses": list(WHOLESALER_ACTIVE_STATUSES)},
    ).mappings()
    unknown = [
        f"{row['wholesaler_id']}({row['binding_count']})"
        for row in rows_with_balances
        if row["wholesaler_id"] not in registered_wholesalers
    ]
    if unknown:
        raise PreflightFailure(
            "nonzero binding balances lack live tenant registration: " + ", ".join(unknown)
        )


def _validate_payment_history(bind, row: dict[str, Any]) -> None:
    schema = row["tenant_schema"]
    wholesaler_id = row["wholesaler_id"]
    q_orders = _qualified(bind, schema, ORDERS)
    q_payments = _qualified(bind, schema, PAYMENTS)
    method_values = ", ".join(_quote_literal(bind, value) for value in PAYMENT_METHODS)

    invalid_orders = int(bind.execute(
        sa.text(
            f"SELECT COUNT(*) FROM {q_orders} "
            "WHERE is_deleted IS FALSE AND wholesaler_id <> :wholesaler_id"
        ),
        {"wholesaler_id": wholesaler_id},
    ).scalar() or 0)
    if invalid_orders:
        raise PreflightFailure(f"{schema}.orders contains {invalid_orders} rows for another wholesaler")

    invalid_payments = int(bind.execute(
        sa.text(
            f"""
            SELECT COUNT(*)
            FROM {q_payments} p
            LEFT JOIN {q_orders} o ON o.id = p.order_id
            WHERE p.is_deleted IS FALSE
              AND (
                  p.amount IS NULL
                  OR p.amount < 0
                  OR p.method IS NULL
                  OR p.method NOT IN ({method_values})
                  OR o.id IS NULL
                  OR o.is_deleted IS TRUE
                  OR o.wholesaler_id <> :wholesaler_id
                  OR p.retailer_id IS DISTINCT FROM o.retailer_id
              )
            """
        ),
        {"wholesaler_id": wholesaler_id},
    ).scalar() or 0)
    if invalid_payments:
        raise PreflightFailure(f"{schema}.payments contains {invalid_payments} invalid history rows")

    duplicate_credit_orders = int(bind.execute(
        sa.text(
            f"""
            SELECT COUNT(*)
            FROM (
                SELECT order_id
                FROM {q_payments}
                WHERE is_deleted IS FALSE AND method = 'credit'
                GROUP BY order_id
                HAVING COUNT(*) > 1
            ) duplicate_credit
            """
        )
    ).scalar() or 0)
    if duplicate_credit_orders:
        raise PreflightFailure(
            f"{schema}.payments contains {duplicate_credit_orders} orders with duplicate credit sales"
        )

    invalid_settlement_orders = int(bind.execute(
        sa.text(
            f"""
            WITH totals AS (
                SELECT o.id,
                       o.total_amount,
                       o.status,
                       COALESCE(SUM(p.amount) FILTER (WHERE p.method = 'credit'), 0) AS credit_total,
                       COALESCE(SUM(p.amount) FILTER (WHERE p.method IN ('cash', 'transfer')), 0) AS collection_total
                FROM {q_orders} o
                LEFT JOIN {q_payments} p
                  ON p.order_id = o.id AND p.is_deleted IS FALSE
                WHERE o.is_deleted IS FALSE
                  AND o.wholesaler_id = :wholesaler_id
                GROUP BY o.id, o.total_amount, o.status
            )
            SELECT COUNT(*)
            FROM totals
            WHERE (
                    credit_total > 0
                    AND (credit_total <> total_amount OR status::text <> 'paid')
                  )
               OR (
                    credit_total = 0
                    AND collection_total > total_amount
                  )
            """
        ),
        {"wholesaler_id": wholesaler_id},
    ).scalar() or 0)
    if invalid_settlement_orders:
        raise PreflightFailure(
            f"{schema}.payments contains {invalid_settlement_orders} invalid order settlement histories"
        )

    over_collected_credit_orders = int(bind.execute(
        sa.text(
            f"""
            WITH totals AS (
                SELECT o.id,
                       COALESCE(SUM(p.amount) FILTER (WHERE p.method = 'credit'), 0) AS credit_total,
                       COALESCE(SUM(p.amount) FILTER (WHERE p.method IN ('cash', 'transfer')), 0) AS collection_total
                FROM {q_orders} o
                LEFT JOIN {q_payments} p
                  ON p.order_id = o.id AND p.is_deleted IS FALSE
                WHERE o.is_deleted IS FALSE
                  AND o.wholesaler_id = :wholesaler_id
                GROUP BY o.id
            )
            SELECT COUNT(*)
            FROM totals
            WHERE credit_total > 0
              AND collection_total > credit_total
            """
        ),
        {"wholesaler_id": wholesaler_id},
    ).scalar() or 0)
    if over_collected_credit_orders:
        raise PreflightFailure(
            f"{schema}.payments contains {over_collected_credit_orders} over-collected credit orders"
        )


def _reconstruct_binding_balances(bind, row: dict[str, Any]) -> None:
    schema = row["tenant_schema"]
    wholesaler_id = row["wholesaler_id"]
    q_orders = _qualified(bind, schema, ORDERS)
    q_payments = _qualified(bind, schema, PAYMENTS)
    q_bindings = _qualified(bind, PUBLIC_SCHEMA, BINDINGS)

    bind.execute(
        sa.text(
            f"""
            WITH payment_totals AS (
                SELECT o.id AS order_id,
                       o.retailer_id,
                       COALESCE(SUM(p.amount) FILTER (WHERE p.method = 'credit'), 0) AS credit_total,
                       COALESCE(SUM(p.amount) FILTER (WHERE p.method IN ('cash', 'transfer')), 0) AS collection_total
                FROM {q_orders} o
                LEFT JOIN {q_payments} p
                  ON p.order_id = o.id AND p.is_deleted IS FALSE
                WHERE o.is_deleted IS FALSE
                  AND o.wholesaler_id = :wholesaler_id
                GROUP BY o.id, o.retailer_id
            ),
            retailer_exposure AS (
                SELECT retailer_id,
                       SUM(
                           CASE
                               WHEN credit_total > 0
                               THEN GREATEST(credit_total - collection_total, 0)
                               ELSE 0
                           END
                       )::NUMERIC(12, 2) AS reconstructed_balance
                FROM payment_totals
                GROUP BY retailer_id
            ),
            binding_targets AS (
                SELECT wrb.id AS binding_id,
                       COALESCE(re.reconstructed_balance, 0)::NUMERIC(12, 2) AS reconstructed_balance
                FROM {q_bindings} wrb
                LEFT JOIN retailer_exposure re ON re.retailer_id = wrb.retailer_id
                WHERE wrb.wholesaler_id = :wholesaler_id
                  AND wrb.is_deleted IS FALSE
            )
            UPDATE {q_bindings} wrb
            SET outstanding_balance = binding_targets.reconstructed_balance,
                updated_at = now()
            FROM binding_targets
            WHERE wrb.id = binding_targets.binding_id
            """
        ),
        {"wholesaler_id": wholesaler_id},
    )


def _validate_no_negative_bindings_remain(bind) -> None:
    count = int(bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM public.wholesaler_retailer_bindings "
            "WHERE outstanding_balance < 0"
        )
    ).scalar() or 0)
    if count:
        raise PreflightFailure(
            f"public.wholesaler_retailer_bindings has {count} unreconciled negative balances"
        )


def _ensure_non_negative_constraint(bind) -> None:
    rows = _binding_check_constraint_rows(bind)
    canonical_rows = [row for row in rows if row["conname"] == CONSTRAINT_NAME]
    if len(canonical_rows) > 1:
        raise PreflightFailure(f"{CONSTRAINT_NAME}: duplicate canonical constraints")
    if canonical_rows:
        if not _is_non_negative_outstanding_constraint(canonical_rows[0]):
            raise PreflightFailure(f"{CONSTRAINT_NAME}: check constraint is incompatible")
        return

    equivalent_rows = [row for row in rows if _is_non_negative_outstanding_constraint(row)]
    incompatible_rows = [
        row
        for row in rows
        if _is_outstanding_constraint_candidate(row)
        and not _is_non_negative_outstanding_constraint(row)
    ]
    if incompatible_rows:
        names = ", ".join(row["conname"] for row in incompatible_rows)
        raise PreflightFailure(f"{BINDINGS}: incompatible outstanding balance constraints: {names}")
    if len(equivalent_rows) > 1:
        raise PreflightFailure(f"{BINDINGS}: multiple equivalent outstanding balance constraints")

    q_bindings = _qualified(bind, PUBLIC_SCHEMA, BINDINGS)
    if equivalent_rows:
        bind.execute(sa.text(
            f"ALTER TABLE {q_bindings} "
            f"RENAME CONSTRAINT {_quote_ident(bind, equivalent_rows[0]['conname'])} "
            f"TO {_quote_ident(bind, CONSTRAINT_NAME)}"
        ))
        return

    bind.execute(sa.text(
        f"ALTER TABLE {q_bindings} "
        f"ADD CONSTRAINT {_quote_ident(bind, CONSTRAINT_NAME)} "
        "CHECK (outstanding_balance >= 0)"
    ))


def _binding_check_constraint_rows(bind) -> list[dict[str, Any]]:
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
        {"schema": PUBLIC_SCHEMA, "table_name": BINDINGS},
    ).mappings()
    return [dict(row) for row in rows]


def _is_non_negative_outstanding_constraint(row: dict[str, Any]) -> bool:
    if _catalog_code(row["contype"]) != "c" or not bool(row["convalidated"]):
        return False
    if _catalog_column_names(row.get("column_names")) != ["outstanding_balance"]:
        return False
    expression = _compact_sql(
        str(row.get("check_expr") or row.get("constraint_def") or "")
    ).replace("(0)::numeric", "0").replace("0::numeric", "0")
    return expression in {
        "outstanding_balance>=0",
        "(outstanding_balance>=0)",
        "check(outstanding_balance>=0)",
        "check((outstanding_balance>=0))",
    }


def _is_outstanding_constraint_candidate(row: dict[str, Any]) -> bool:
    columns = _catalog_column_names(row.get("column_names"))
    expression = str(row.get("check_expr") or row.get("constraint_def") or "")
    return "outstanding_balance" in columns or "outstanding_balance" in expression


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


def _column_exists(bind, schema: str, table_name: str, column_name: str) -> bool:
    return bool(bind.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = :schema AND table_name = :table_name "
            "AND column_name = :column_name"
        ),
        {"schema": schema, "table_name": table_name, "column_name": column_name},
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


def _qualified(bind, schema: str, table_name: str) -> str:
    return f"{_quote_ident(bind, schema)}.{_quote_ident(bind, table_name)}"


def _quote_ident(bind, identifier: str | None) -> str:
    if identifier is None:
        raise PreflightFailure("identifier is missing")
    return bind.execute(
        sa.text("SELECT quote_ident(:identifier)"), {"identifier": identifier}
    ).scalar_one()


def _quote_literal(bind, value: str) -> str:
    return bind.execute(
        sa.text("SELECT quote_literal(:value)"), {"value": value}
    ).scalar_one()


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
