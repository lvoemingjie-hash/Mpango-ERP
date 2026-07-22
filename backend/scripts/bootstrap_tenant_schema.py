#!/usr/bin/env python3
"""
Bootstrap a tenant schema with all required tables (idempotent).

This script creates the tenant schema and all business tables using raw DDL.
It is called by docker-entrypoint.sh before Uvicorn starts to ensure the
default tenant schema (used by MockAuthStrategy in MPANGO_ENV=test) is ready.

Alembic migrations cannot be used for this purpose because the project uses
a single shared alembic_version table in public schema - running
`alembic upgrade head -x tenant_schema=t_dev` is a no-op when public
migrations are already at HEAD.

Usage:
    python scripts/bootstrap_tenant_schema.py t_dev
    python scripts/bootstrap_tenant_schema.py t_dev --database-url postgresql://...
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from pathlib import Path


RETAILER_PRICES = "retailer_prices"
UQ_RETAILER_PRICES = "uq_retailer_prices_retailer_sku"
CK_RETAILER_PRICES = "ck_retailer_prices_positive_price"
IX_RETAILER_PRICES_RETAILER = "ix_retailer_prices_retailer_id"
IX_RETAILER_PRICES_SKU = "ix_retailer_prices_sku_id"
MV_SALES_DAILY = "mv_sales_daily"
IX_MV_SALES_DAILY = "idx_mv_sales_daily_u1"
REPORTING_ROLE = "reporting_role"
CK_PAYMENTS_METHOD = "ck_payments_method_canonical"
PUBLIC_BINDINGS = "wholesaler_retailer_bindings"
CK_BINDINGS_OUTSTANDING_NON_NEGATIVE = (
    "ck_wrb_outstanding_balance_non_negative"
)
CANONICAL_PAYMENT_METHODS = ("cash", "transfer", "credit")
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

RETAILER_PRICE_COLUMNS = {
    "id": ("uuid", True),
    "retailer_id": ("uuid", True),
    "sku_id": ("uuid", True),
    "price": ("numeric(12,2)", True),
    "created_at": ("timestamp with time zone", True),
    "updated_at": ("timestamp with time zone", True),
    "is_deleted": ("boolean", True),
    "deleted_at": ("timestamp with time zone", False),
    "created_by": ("uuid", False),
    "updated_by": ("uuid", False),
}


def _add_backend_to_path() -> None:
    backend_dir = Path(__file__).resolve().parents[1]
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))


async def _column_exists(db, schema: str, table: str, column: str) -> bool:
    from sqlalchemy import text
    result = await db.execute(text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_schema = :schema AND table_name = :table AND column_name = :column"
    ), {"schema": schema, "table": table, "column": column})
    return result.first() is not None


async def _table_exists(db, schema: str, table: str) -> bool:
    """Check whether a table exists in the given schema."""
    from sqlalchemy import text
    result = await db.execute(text(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = :schema AND table_name = :table"
    ), {"schema": schema, "table": table})
    return result.first() is not None


async def _column_is_nullable(db, schema: str, table: str, column: str) -> bool | None:
    from sqlalchemy import text
    result = await db.execute(text(
        "SELECT is_nullable FROM information_schema.columns "
        "WHERE table_schema = :schema AND table_name = :table AND column_name = :column"
    ), {"schema": schema, "table": table, "column": column})
    value = result.scalar()
    if value is None:
        return None
    return value == "YES"


async def _index_definition(db, schema: str, index_name: str) -> str | None:
    from sqlalchemy import text
    result = await db.execute(text(
        "SELECT indexdef FROM pg_indexes "
        "WHERE schemaname = :schema AND indexname = :index_name"
    ), {"schema": schema, "index_name": index_name})
    return result.scalar()


async def _constraint_exists(db, schema: str, table: str, constraint_name: str) -> bool:
    from sqlalchemy import text
    result = await db.execute(text(
        "SELECT 1 FROM pg_constraint c "
        "JOIN pg_class t ON t.oid = c.conrelid "
        "JOIN pg_namespace n ON n.oid = c.connamespace "
        "WHERE n.nspname = :schema AND t.relname = :table "
        "AND c.conname = :constraint_name AND c.contype = 'c'"
    ), {"schema": schema, "table": table, "constraint_name": constraint_name})
    return result.first() is not None


async def _check_constraint_rows(db, schema: str, table: str) -> list[dict]:
    from sqlalchemy import text

    rows = (await db.execute(
        text(
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
              AND t.relname = :table
              AND c.contype = 'c'
            GROUP BY c.oid, c.conname, c.contype, c.convalidated, c.conbin, c.conrelid
            ORDER BY c.conname
            """
        ),
        {"schema": schema, "table": table},
    )).mappings()
    return [dict(row) for row in rows]


def _is_equivalent_payment_method_constraint(row: dict) -> bool:
    if _catalog_code(row.get("contype")) != "c" or not bool(row.get("convalidated")):
        return False
    if _catalog_column_names(row.get("column_names")) != ["method"]:
        return False
    expression = str(row.get("check_expr") or row.get("constraint_def") or "")
    normalized = _normalize_expression(expression)
    compact = _compact_sql(expression)
    if _has_forbidden_payment_method_semantics(normalized, compact):
        return False
    members = _positive_payment_method_members(normalized)
    return (
        members is not None
        and len(members) == len(CANONICAL_PAYMENT_METHODS)
        and set(members) == set(CANONICAL_PAYMENT_METHODS)
    )


def _is_payment_method_constraint_candidate(row: dict) -> bool:
    columns = _catalog_column_names(row.get("column_names"))
    expression = str(row.get("check_expr") or row.get("constraint_def") or "")
    literal_values = set(re.findall(r"'([^']+)'", expression))
    return "method" in columns or literal_values == set(CANONICAL_PAYMENT_METHODS)


def _is_outstanding_balance_non_negative_constraint(row: dict) -> bool:
    if _catalog_code(row.get("contype")) != "c" or not bool(row.get("convalidated")):
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


def _is_outstanding_balance_constraint_candidate(row: dict) -> bool:
    columns = _catalog_column_names(row.get("column_names"))
    expression = str(row.get("check_expr") or row.get("constraint_def") or "")
    return "outstanding_balance" in columns or "outstanding_balance" in expression


def _has_forbidden_payment_method_semantics(normalized: str, compact: str) -> bool:
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


def _positive_payment_method_members(normalized: str) -> list[str] | None:
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


def _normalize_sql(sql: str) -> str:
    return " ".join(sql.lower().split())


def _normalize_expression(sql: str) -> str:
    return " ".join(sql.lower().split())


def _compact_sql(sql: str) -> str:
    return "".join(sql.lower().split())


async def _ensure_index(
    db,
    schema: str,
    index_name: str,
    create_sql: str,
    required_fragments: tuple[str, ...],
) -> None:
    """Create an index or fail fast if an incompatible same-name index exists."""
    from sqlalchemy import text

    indexdef = await _index_definition(db, schema, index_name)
    if indexdef is not None:
        normalized = _normalize_sql(indexdef)
        missing = [
            fragment
            for fragment in required_fragments
            if _normalize_sql(fragment) not in normalized
        ]
        if missing:
            raise RuntimeError(
                f"Bootstrap reconcile: existing index {schema}.{index_name} "
                f"does not match expected contract. Missing fragments: {missing}. "
                "Manual review is required before continuing."
            )
        return

    await db.execute(text(create_sql))


async def _ensure_public_binding_balance_constraint(db) -> None:
    from sqlalchemy import text

    if not await _table_exists(db, "public", PUBLIC_BINDINGS):
        return
    if not await _column_exists(db, "public", PUBLIC_BINDINGS, "outstanding_balance"):
        raise RuntimeError(
            "Bootstrap reconcile: public.wholesaler_retailer_bindings is missing "
            "outstanding_balance"
        )

    rows = await _check_constraint_rows(db, "public", PUBLIC_BINDINGS)
    canonical_rows = [
        row for row in rows
        if row["conname"] == CK_BINDINGS_OUTSTANDING_NON_NEGATIVE
    ]
    if len(canonical_rows) > 1:
        raise RuntimeError(
            "Bootstrap reconcile: duplicate public binding outstanding balance constraints"
        )
    if canonical_rows:
        if not _is_outstanding_balance_non_negative_constraint(canonical_rows[0]):
            raise RuntimeError(
                "Bootstrap reconcile: public binding outstanding balance check "
                "constraint is incompatible"
            )
        return

    equivalent_rows = [
        row for row in rows if _is_outstanding_balance_non_negative_constraint(row)
    ]
    incompatible_rows = [
        row
        for row in rows
        if _is_outstanding_balance_constraint_candidate(row)
        and not _is_outstanding_balance_non_negative_constraint(row)
    ]
    if incompatible_rows:
        names = ", ".join(row["conname"] for row in incompatible_rows)
        raise RuntimeError(
            "Bootstrap reconcile: incompatible public binding outstanding balance "
            f"constraints: {names}"
        )
    if len(equivalent_rows) > 1:
        raise RuntimeError(
            "Bootstrap reconcile: multiple equivalent public binding outstanding "
            "balance constraints"
        )

    qualified_table = await _qualified_identifier(db, "public", PUBLIC_BINDINGS)
    quoted_constraint = await _quote_ident(db, CK_BINDINGS_OUTSTANDING_NON_NEGATIVE)
    if equivalent_rows:
        legacy_name = await _quote_ident(db, equivalent_rows[0]["conname"])
        await db.execute(text(
            f"ALTER TABLE {qualified_table} RENAME CONSTRAINT {legacy_name} "
            f"TO {quoted_constraint}"
        ))
        return

    await db.execute(text(
        f"ALTER TABLE {qualified_table} ADD CONSTRAINT {quoted_constraint} "
        "CHECK (outstanding_balance >= 0)"
    ))


async def _quote_ident(db, identifier: str) -> str:
    from sqlalchemy import text

    return (await db.execute(
        text("SELECT quote_ident(:identifier)"), {"identifier": identifier}
    )).scalar_one()


async def _qualified_identifier(db, schema: str, object_name: str) -> str:
    quoted_schema = await _quote_ident(db, schema)
    quoted_object = await _quote_ident(db, object_name)
    return f"{quoted_schema}.{quoted_object}"


async def _reconcile_order_status(db, schema: str) -> None:
    """Add missing canonical enum labels and reject non-canonical live rows."""
    from sqlalchemy import text

    qualified_orders = await _qualified_identifier(db, schema, "orders")
    metadata = (await db.execute(
        text(
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
              AND rel.relname = 'orders'
              AND attr.attname = 'status'
              AND attr.attnum > 0
              AND NOT attr.attisdropped
            """
        ),
        {"schema": schema},
    )).mappings().one_or_none()
    if metadata is None:
        raise RuntimeError(f"{schema}.orders.status column is missing")
    if (
        _catalog_code(metadata["type_schema"]) != schema
        or _catalog_code(metadata["type_name"]) != "order_status"
        or _catalog_code(metadata["type_kind"]) != "e"
    ):
        raise RuntimeError(
            f"{schema}.orders.status must use the schema-local order_status enum"
        )

    members = ", ".join(f"'{value}'" for value in CANONICAL_ORDER_STATUSES)
    invalid_count = int((await db.execute(text(
        f"SELECT COUNT(*) FROM {qualified_orders} "
        f"WHERE status IS NULL OR status::text NOT IN ({members})"
    ))).scalar() or 0)
    if invalid_count:
        raise RuntimeError(
            f"{schema}.orders.status contains {invalid_count} non-canonical rows"
        )

    qualified_type = await _qualified_identifier(db, schema, "order_status")
    for value in CANONICAL_ORDER_STATUSES:
        await db.execute(text(
            f"ALTER TYPE {qualified_type} ADD VALUE IF NOT EXISTS '{value}'"
        ))


def _normalize_type(type_name: str) -> str:
    return "".join(type_name.lower().split())


def _catalog_code(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, memoryview):
        value = value.tobytes()
    if isinstance(value, bytes):
        return value.decode()
    return str(value)


async def _regclass_oid(db, qualified_name: str) -> int | None:
    from sqlalchemy import text

    return (await db.execute(
        text("SELECT to_regclass(:qualified_name)::oid"),
        {"qualified_name": qualified_name},
    )).scalar()


async def _relation_kind(db, schema: str, object_name: str) -> str | None:
    from sqlalchemy import text

    return _catalog_code(
        (await db.execute(
            text(
                "SELECT c.relkind FROM pg_class c "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = :schema AND c.relname = :object_name"
            ),
            {"schema": schema, "object_name": object_name},
        )).scalar()
    )


async def _relation_columns(db, relation_oid: int) -> dict[str, dict]:
    from sqlalchemy import text

    rows = (await db.execute(
        text(
            "SELECT a.attname, format_type(a.atttypid, a.atttypmod) AS formatted_type, "
            "a.attnotnull "
            "FROM pg_attribute a "
            "WHERE a.attrelid = :relation_oid AND a.attnum > 0 AND NOT a.attisdropped"
        ),
        {"relation_oid": relation_oid},
    )).mappings()
    return {row["attname"]: dict(row) for row in rows}


async def _retailer_price_constraint_rows(db, table_oid: int) -> list[dict]:
    from sqlalchemy import text

    rows = (await db.execute(
        text(
            """
            SELECT c.oid AS constraint_oid,
                   c.conname,
                   c.contype,
                   c.convalidated,
                   c.conindid,
                   pg_get_constraintdef(c.oid, true) AS constraint_def,
                   i.indisunique,
                   i.indisvalid,
                   i.indpred IS NOT NULL AS has_predicate,
                   COALESCE(array_agg(a.attname ORDER BY cols.ordinality)
                       FILTER (WHERE a.attname IS NOT NULL), ARRAY[]::name[]) AS column_names
            FROM pg_constraint c
            LEFT JOIN pg_index i ON i.indexrelid = c.conindid
            LEFT JOIN LATERAL unnest(c.conkey) WITH ORDINALITY AS cols(attnum, ordinality)
                ON true
            LEFT JOIN pg_attribute a
                ON a.attrelid = c.conrelid AND a.attnum = cols.attnum
            WHERE c.conrelid = :table_oid
            GROUP BY c.oid, c.conname, c.contype, c.convalidated, c.conindid,
                     i.indisunique, i.indisvalid, i.indpred
            ORDER BY c.conname
            """
        ),
        {"table_oid": table_oid},
    )).mappings()
    return [dict(row) for row in rows]


def _catalog_column_names(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        stripped = value.strip("{}")
        return [part.strip().strip('"') for part in stripped.split(",") if part]
    return [str(part) for part in value]


def _constraint_type(value) -> str:
    normalized = _catalog_code(value)
    return normalized or ""


def _is_equivalent_retailer_unique(row: dict) -> bool:
    return (
        _constraint_type(row["contype"]) == "u"
        and bool(row["convalidated"])
        and row["indisunique"] is not False
        and row["indisvalid"] is not False
        and not bool(row["has_predicate"])
        and _catalog_column_names(row["column_names"]) == ["retailer_id", "sku_id"]
    )


def _check_constraint_is_canonical(row: dict) -> bool:
    definition = _normalize_sql(row["constraint_def"] or "")
    expression = (
        definition.replace("check", "")
        .replace("(", "")
        .replace(")", "")
        .replace("::numeric", "")
    )
    expression = "".join(expression.split())
    return (
        _constraint_type(row["contype"]) == "c"
        and bool(row["convalidated"])
        and expression == "price>0"
    )


async def _validate_retailer_price_columns(db, ts: str, table_oid: int) -> list[str]:
    columns = await _relation_columns(db, table_oid)
    violations: list[str] = []
    for column_name, (expected_type, expected_not_null) in RETAILER_PRICE_COLUMNS.items():
        column = columns.get(column_name)
        if column is None:
            violations.append(f"missing column '{column_name}'")
            continue
        actual_type = _normalize_type(column["formatted_type"])
        if actual_type != _normalize_type(expected_type):
            violations.append(
                f"column '{column_name}' has type {column['formatted_type']}, "
                f"expected {expected_type}"
            )
        if expected_not_null and not column["attnotnull"]:
            violations.append(f"column '{column_name}' is nullable, expected NOT NULL")
    return violations


async def _retailer_price_duplicate_count(db, qualified_table: str) -> int:
    from sqlalchemy import text

    return int((await db.execute(text(f"""
        SELECT COUNT(*) FROM (
            SELECT retailer_id, sku_id
            FROM {qualified_table}
            GROUP BY retailer_id, sku_id
            HAVING COUNT(*) > 1
        ) duplicates
    """))).scalar() or 0)


async def _retailer_price_violation_count(db, qualified_table: str) -> int:
    from sqlalchemy import text

    return int((await db.execute(text(
        f"SELECT COUNT(*) FROM {qualified_table} WHERE price IS NULL OR price <= 0"
    ))).scalar() or 0)


async def _has_unique_index_only_retailer_equivalent(db, table_oid: int) -> str | None:
    from sqlalchemy import text

    rows = (await db.execute(
        text(
            """
            SELECT idx.relname AS index_name,
                   i.indisunique,
                   COALESCE(array_agg(a.attname ORDER BY keys.ordinality)
                       FILTER (WHERE a.attname IS NOT NULL), ARRAY[]::name[]) AS column_names
            FROM pg_index i
            JOIN pg_class idx ON idx.oid = i.indexrelid
            LEFT JOIN LATERAL unnest(i.indkey) WITH ORDINALITY AS keys(attnum, ordinality)
                ON true
            LEFT JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = keys.attnum
            WHERE i.indrelid = :table_oid
              AND NOT EXISTS (SELECT 1 FROM pg_constraint c WHERE c.conindid = i.indexrelid)
            GROUP BY idx.relname, i.indisunique
            """
        ),
        {"table_oid": table_oid},
    )).mappings()
    for row in rows:
        if bool(row["indisunique"]) and _catalog_column_names(row["column_names"]) == ["retailer_id", "sku_id"]:
            return row["index_name"]
    return None



async def _reconcile_payments(db, ts: str) -> None:
    """Idempotent reconciliation of payments table to match 021 contract.

    Order matters: columns must exist before indexes that reference them.
    1. Add retailer_id (nullable) if missing
    2. Backfill from orders.retailer_id
    3. Fail fast if orphan payments exist (no matching order)
    4. Set retailer_id NOT NULL
    5. Add transaction_id if missing
    6. Create ix_payments_order_id if missing
    7. Ensure canonical payments.method check constraint
    8. Create uq_payments_transaction_id partial unique if missing
    """
    from sqlalchemy import text

    payments_exists = await _column_exists(db, ts, "payments", "id")
    if not payments_exists:
        return

    # --- Phase 1: columns (must complete before indexes) ---

    if not await _column_exists(db, ts, "payments", "retailer_id"):
        await db.execute(text(
            f'ALTER TABLE "{ts}".payments ADD COLUMN retailer_id UUID'
        ))

    # Always backfill/enforce retailer_id. A previous partial run may have
    # added the column but failed before NOT NULL was applied.
    await db.execute(text(
        f'UPDATE "{ts}".payments p SET retailer_id = o.retailer_id '
        f'FROM "{ts}".orders o WHERE p.order_id = o.id AND p.retailer_id IS NULL'
    ))
    orphan_count = (await db.execute(text(
        f'SELECT COUNT(*) FROM "{ts}".payments WHERE retailer_id IS NULL'
    ))).scalar()
    if orphan_count and int(orphan_count) > 0:
        raise RuntimeError(
            f"Bootstrap reconcile: {orphan_count} payments rows have NULL "
            "retailer_id after backfill from orders. Orphan payments require "
            "manual data resolution."
        )
    if await _column_is_nullable(db, ts, "payments", "retailer_id"):
        await db.execute(text(
            f'ALTER TABLE "{ts}".payments ALTER COLUMN retailer_id SET NOT NULL'
        ))
        print(f"[reconcile] {ts}.payments: added retailer_id (NOT NULL)")

    # --- transaction_id ---
    if not await _column_exists(db, ts, "payments", "transaction_id"):
        await db.execute(text(
            f'ALTER TABLE "{ts}".payments ADD COLUMN transaction_id VARCHAR(64)'
        ))
        print(f"[reconcile] {ts}.payments: added transaction_id (nullable)")

    invalid_method_count = (await db.execute(text(
        f'SELECT COUNT(*) FROM "{ts}".payments '
        "WHERE method IS NULL OR method NOT IN ('cash', 'transfer', 'credit')"
    ))).scalar()
    if invalid_method_count and int(invalid_method_count) > 0:
        raise RuntimeError(
            f"Bootstrap reconcile: {invalid_method_count} payments rows have "
            "non-canonical or NULL method values. Manual data resolution is required."
        )

    constraints = await _check_constraint_rows(db, ts, "payments")
    canonical_rows = [row for row in constraints if row["conname"] == CK_PAYMENTS_METHOD]
    if len(canonical_rows) > 1:
        raise RuntimeError(f"Bootstrap reconcile: duplicate {ts}.{CK_PAYMENTS_METHOD} constraints")

    equivalent_rows = [row for row in constraints if _is_equivalent_payment_method_constraint(row)]
    incompatible_rows = [
        row
        for row in constraints
        if not _is_equivalent_payment_method_constraint(row)
        and _is_payment_method_constraint_candidate(row)
    ]

    if canonical_rows:
        if not _is_equivalent_payment_method_constraint(canonical_rows[0]):
            raise RuntimeError(
                f"Bootstrap reconcile: existing {ts}.{CK_PAYMENTS_METHOD} "
                "does not match expected payment method contract."
            )
        duplicate_equivalent = [row for row in equivalent_rows if row["conname"] != CK_PAYMENTS_METHOD]
        if duplicate_equivalent:
            raise RuntimeError(
                f"Bootstrap reconcile: duplicate equivalent {ts}.payments method constraints"
            )
        if incompatible_rows:
            names = ", ".join(row["conname"] for row in incompatible_rows)
            raise RuntimeError(
                f"Bootstrap reconcile: incompatible {ts}.payments method constraints: {names}"
            )
    else:
        if incompatible_rows:
            names = ", ".join(row["conname"] for row in incompatible_rows)
            raise RuntimeError(
                f"Bootstrap reconcile: incompatible {ts}.payments method constraints: {names}"
            )
        if len(equivalent_rows) > 1:
            raise RuntimeError(
                f"Bootstrap reconcile: multiple equivalent {ts}.payments method constraints"
            )
        if equivalent_rows:
            legacy_name = equivalent_rows[0]["conname"]
            quoted_legacy_name = await _quote_ident(db, legacy_name)
            quoted_constraint_name = await _quote_ident(db, CK_PAYMENTS_METHOD)
            await db.execute(text(
                f'ALTER TABLE "{ts}".payments '
                f'RENAME CONSTRAINT {quoted_legacy_name} TO {quoted_constraint_name}'
            ))
        else:
            await db.execute(text(
                f'ALTER TABLE "{ts}".payments '
                f'ADD CONSTRAINT {CK_PAYMENTS_METHOD} '
                "CHECK (method IN ('cash', 'transfer', 'credit'))"
            ))
        print(f"[reconcile] {ts}.payments: ensured {CK_PAYMENTS_METHOD}")

    # --- Phase 2: indexes (require both columns to exist) ---

    await _ensure_index(
        db,
        ts,
        "ix_payments_order_id",
        f'CREATE INDEX ix_payments_order_id ON "{ts}".payments (order_id)',
        ("payments", "(order_id)"),
    )
    print(f"[reconcile] {ts}.payments: ensured ix_payments_order_id")

    await _ensure_index(
        db,
        ts,
        "uq_payments_transaction_id",
        f'CREATE UNIQUE INDEX IF NOT EXISTS uq_payments_transaction_id '
        f'ON "{ts}".payments (transaction_id) '
        f"WHERE transaction_id IS NOT NULL",
        ("unique index", "payments", "(transaction_id)", "transaction_id is not null"),
    )
    print(f"[reconcile] {ts}.payments: ensured uq_payments_transaction_id")


async def _reconcile_retailer_prices(db, ts: str) -> None:
    """Structural reconciliation for retailer_prices.

    Mirrors migration 017 plus DC-2M2 legacy compatibility: a single
    business-equivalent legacy UNIQUE CONSTRAINT on (retailer_id, sku_id) is
    renamed to the canonical name; unique-index-only equivalents and ambiguous
    structures fail closed.
    """
    from sqlalchemy import text

    if not await _table_exists(db, ts, RETAILER_PRICES):
        return

    violations: list[str] = []
    qualified_table = await _qualified_identifier(db, ts, RETAILER_PRICES)
    table_oid = await _regclass_oid(db, qualified_table)
    if table_oid is None:
        raise RuntimeError(f"Bootstrap reconcile: {ts}.{RETAILER_PRICES} is unresolved")

    violations.extend(await _validate_retailer_price_columns(db, ts, table_oid))
    duplicate_count = await _retailer_price_duplicate_count(db, qualified_table)
    if duplicate_count > 0:
        violations.append("duplicate (retailer_id, sku_id) rows")
    price_violation_count = await _retailer_price_violation_count(db, qualified_table)
    if price_violation_count > 0:
        violations.append("rows violate price > 0")
    index_only_equivalent = await _has_unique_index_only_retailer_equivalent(db, table_oid)
    if index_only_equivalent:
        violations.append(
            f"unique-index-only equivalent '{index_only_equivalent}' is not a constraint"
        )

    constraints = await _retailer_price_constraint_rows(db, table_oid)
    canonical_rows = [row for row in constraints if row["conname"] == UQ_RETAILER_PRICES]
    equivalent_legacy = [
        row
        for row in constraints
        if row["conname"] != UQ_RETAILER_PRICES and _is_equivalent_retailer_unique(row)
    ]
    unique_action: tuple[str, str | None] = ("none", None)

    if len(canonical_rows) > 1:
        violations.append(f"duplicate canonical constraint '{UQ_RETAILER_PRICES}'")
    elif canonical_rows:
        if not _is_equivalent_retailer_unique(canonical_rows[0]):
            violations.append(f"canonical constraint '{UQ_RETAILER_PRICES}' is incompatible")
    else:
        canonical_kind = await _relation_kind(db, ts, UQ_RETAILER_PRICES)
        if canonical_kind is not None:
            violations.append(
                f"canonical name '{UQ_RETAILER_PRICES}' is occupied by a non-constraint object"
            )
        elif len(equivalent_legacy) > 1:
            violations.append("ambiguous equivalent legacy unique constraints")
        elif len(equivalent_legacy) == 1:
            unique_action = ("rename", equivalent_legacy[0]["conname"])
        else:
            unique_action = ("add", None)

    check_rows = [row for row in constraints if row["conname"] == CK_RETAILER_PRICES]
    add_check_constraint = False
    if len(check_rows) > 1:
        violations.append(f"duplicate check constraint '{CK_RETAILER_PRICES}'")
    elif check_rows:
        if not _check_constraint_is_canonical(check_rows[0]):
            violations.append(f"check constraint '{CK_RETAILER_PRICES}' is incompatible")
    else:
        add_check_constraint = True

    if violations:
        violation_list = "\n  - ".join(violations)
        raise RuntimeError(
            f"Bootstrap reconcile: {ts}.{RETAILER_PRICES} exists but does NOT match "
            f"migration 017/DC-2M2 contract. Violations:\n  - {violation_list}\n"
            "Manual schema correction is required before continuing."
        )

    quoted_uq = await _quote_ident(db, UQ_RETAILER_PRICES)
    quoted_ck = await _quote_ident(db, CK_RETAILER_PRICES)
    if unique_action[0] == "rename":
        quoted_legacy = await _quote_ident(db, unique_action[1] or "")
        await db.execute(text(
            f"ALTER TABLE {qualified_table} RENAME CONSTRAINT {quoted_legacy} TO {quoted_uq}"
        ))
        print(
            f"[reconcile] {ts}.{RETAILER_PRICES}: renamed legacy unique constraint "
            f"to {UQ_RETAILER_PRICES}"
        )
    elif unique_action[0] == "add":
        await db.execute(text(
            f"ALTER TABLE {qualified_table} "
            f"ADD CONSTRAINT {quoted_uq} UNIQUE (retailer_id, sku_id)"
        ))
        print(f"[reconcile] {ts}.{RETAILER_PRICES}: added {UQ_RETAILER_PRICES}")

    if add_check_constraint:
        await db.execute(text(
            f"ALTER TABLE {qualified_table} ADD CONSTRAINT {quoted_ck} CHECK (price > 0)"
        ))
        print(f"[reconcile] {ts}.{RETAILER_PRICES}: added {CK_RETAILER_PRICES}")

    # --- Indexes ---
    await _ensure_index(
        db,
        ts,
        IX_RETAILER_PRICES_RETAILER,
        f'CREATE INDEX IF NOT EXISTS {IX_RETAILER_PRICES_RETAILER} '
        f'ON {qualified_table} (retailer_id)',
        (RETAILER_PRICES, "(retailer_id)"),
    )

    await _ensure_index(
        db,
        ts,
        IX_RETAILER_PRICES_SKU,
        f'CREATE INDEX IF NOT EXISTS {IX_RETAILER_PRICES_SKU} '
        f'ON {qualified_table} (sku_id)',
        (RETAILER_PRICES, "(sku_id)"),
    )

    print(f"[reconcile] {ts}.{RETAILER_PRICES}: contract validated, indexes ensured")


async def _reconcile_reporting(db, ts: str) -> None:
    """Idempotent reconciliation of reporting views and materialized views.

    Mirrors Alembic migrations 012 (read models) and 013 (materialize sales).
    These migrations discover tenant schemas dynamically at runtime; tenants
    created *after* those migrations ran (e.g. via bootstrap) would miss them.

    Requires reporting_role to exist (created by migration 011).
    Raises RuntimeError if reporting_role is absent - this indicates an
    incomplete migration state, not a tolerable condition.
    """
    from sqlalchemy import text

    # Check if ledger_entries exists (prerequisite for all reporting objects)
    le_exists = await _column_exists(db, ts, "ledger_entries", "id")
    if not le_exists:
        return

    # Verify reporting_role exists (migration 011 must have run)
    role_result = await db.execute(text(
        "SELECT 1 FROM pg_roles WHERE rolname = 'reporting_role'"
    ))
    if role_result.first() is None:
        raise RuntimeError(
            "Bootstrap reconcile: reporting_role does not exist. "
            "Migration 011_s6_p_reporting_role must run first. "
            "Cannot grant reporting permissions without this role."
        )

    # Grant schema-level USAGE so reporting_role can access the tenant schema
    await db.execute(text(
        f'GRANT USAGE ON SCHEMA "{ts}" TO reporting_role'
    ))
    print(f"[reconcile] {ts}: granted schema USAGE to reporting_role")

    # --- rpt_receivables_summary (from 012) ---
    await db.execute(text(f"""
        CREATE OR REPLACE VIEW "{ts}".rpt_receivables_summary AS
        SELECT
            reference_id                                    AS entity_id,
            reference_type                                  AS entity_type,
            'USD'::CHAR(3)                                  AS reporting_currency_code,
            SUM(amount)::NUMERIC(20, 4)                     AS outstanding_balance,
            COUNT(*)                                        AS entry_count,
            MIN(transaction_date)                           AS earliest_transaction,
            MAX(transaction_date)                           AS latest_transaction
        FROM "{ts}".ledger_entries
        WHERE account_type = 'receivable'
          AND is_deleted = false
        GROUP BY reference_id, reference_type
        ORDER BY outstanding_balance DESC
    """))
    await db.execute(text(
        f'GRANT SELECT ON "{ts}".rpt_receivables_summary TO reporting_role'
    ))

    # --- rpt_cash_flow_daily (from 012) ---
    await db.execute(text(f"""
        CREATE OR REPLACE VIEW "{ts}".rpt_cash_flow_daily AS
        SELECT
            transaction_date::DATE                          AS transaction_date,
            'USD'::CHAR(3)                                  AS reporting_currency_code,
            SUM(amount)::NUMERIC(20, 4)                     AS net_change,
            COUNT(*)                                        AS transaction_count,
            SUM(SUM(amount)) OVER (
                ORDER BY transaction_date::DATE
            )::NUMERIC(20, 4)                               AS running_balance
        FROM "{ts}".ledger_entries
        WHERE account_type = 'cash'
          AND is_deleted = false
        GROUP BY transaction_date::DATE
        ORDER BY transaction_date::DATE
    """))
    await db.execute(text(
        f'GRANT SELECT ON "{ts}".rpt_cash_flow_daily TO reporting_role'
    ))

    # --- mv_sales_daily (from 013, replaces rpt_sales_daily view) ---
    qualified_ledger_entries = await _qualified_identifier(db, ts, "ledger_entries")
    qualified_rpt_sales_daily = await _qualified_identifier(db, ts, "rpt_sales_daily")
    qualified_mv_sales_daily = await _qualified_identifier(db, ts, MV_SALES_DAILY)

    mv_kind = await _relation_kind(db, ts, MV_SALES_DAILY)
    if mv_kind is not None and mv_kind != "m":
        raise RuntimeError(
            f"Bootstrap reconcile: {ts}.{MV_SALES_DAILY} exists but is not a "
            "materialized view. Manual schema correction is required before continuing."
        )

    if mv_kind is None:
        rpt_kind = await _relation_kind(db, ts, "rpt_sales_daily")
        if rpt_kind is not None and rpt_kind != "v":
            raise RuntimeError(
                f"Bootstrap reconcile: {ts}.rpt_sales_daily exists but is not a view. "
                "Manual schema correction is required before continuing."
            )
        if rpt_kind == "v":
            await db.execute(text(f"DROP VIEW {qualified_rpt_sales_daily}"))
        await db.execute(text(f"""
            CREATE MATERIALIZED VIEW {qualified_mv_sales_daily} AS
            SELECT
                transaction_date::DATE                          AS transaction_date,
                'USD'::CHAR(3)                                  AS reporting_currency_code,
                ABS(SUM(amount))::NUMERIC(20, 4)                AS daily_revenue,
                COUNT(*)::INTEGER                               AS transaction_count
            FROM {qualified_ledger_entries}
            WHERE account_type = 'revenue'
              AND is_deleted = false
            GROUP BY transaction_date::DATE
            ORDER BY transaction_date::DATE
            WITH DATA
        """))
        print(f"[reconcile] {ts}: created mv_sales_daily")

    # Always ensure the unique index exists (even if mv was already present)
    await _ensure_index(
        db,
        ts,
        IX_MV_SALES_DAILY,
        f'CREATE UNIQUE INDEX {IX_MV_SALES_DAILY} '
        f'ON {qualified_mv_sales_daily} (transaction_date, reporting_currency_code)',
        ("unique index", MV_SALES_DAILY, "(transaction_date, reporting_currency_code)"),
    )
    print(f"[reconcile] {ts}: ensured {IX_MV_SALES_DAILY}")

    await db.execute(text(
        f'GRANT SELECT ON {qualified_mv_sales_daily} TO {REPORTING_ROLE}'
    ))

    # Mirror migration 011's reporting contract for tenants created after 011.
    await db.execute(text(
        f'GRANT SELECT ON ALL TABLES IN SCHEMA "{ts}" TO reporting_role'
    ))
    await db.execute(text(
        f'ALTER DEFAULT PRIVILEGES IN SCHEMA "{ts}" '
        f'GRANT SELECT ON TABLES TO reporting_role'
    ))
    print(f"[reconcile] {ts}: ensured reporting_role table privileges")


async def _reconcile_import_runs(db, ts: str) -> None:
    """Idempotent reconciliation of import_runs indexes (mirrors migration 022).

    If the table does not exist, CREATE TABLE IF NOT EXISTS above handles it.
    If the table exists, ensure all 4 indexes match the migration 022 contract.
    """
    if not await _table_exists(db, ts, "import_runs"):
        return

    # ix_import_runs_import_id -- UNIQUE index on import_id
    await _ensure_index(
        db,
        ts,
        "ix_import_runs_import_id",
        f'CREATE UNIQUE INDEX IF NOT EXISTS ix_import_runs_import_id '
        f'ON "{ts}".import_runs (import_id)',
        ("unique index", "import_runs", "(import_id)"),
    )

    # ix_import_runs_status
    await _ensure_index(
        db,
        ts,
        "ix_import_runs_status",
        f'CREATE INDEX IF NOT EXISTS ix_import_runs_status '
        f'ON "{ts}".import_runs (status)',
        ("import_runs", "(status)"),
    )

    # ix_import_runs_tenant_id
    await _ensure_index(
        db,
        ts,
        "ix_import_runs_tenant_id",
        f'CREATE INDEX IF NOT EXISTS ix_import_runs_tenant_id '
        f'ON "{ts}".import_runs (tenant_id)',
        ("import_runs", "(tenant_id)"),
    )

    # ix_import_runs_created_at
    await _ensure_index(
        db,
        ts,
        "ix_import_runs_created_at",
        f'CREATE INDEX IF NOT EXISTS ix_import_runs_created_at '
        f'ON "{ts}".import_runs (created_at)',
        ("import_runs", "(created_at)"),
    )

    print(f"[reconcile] {ts}.import_runs: ensured indexes")


async def _reconcile_intake_tables(db, ts: str) -> None:
    """Idempotent reconciliation of U4 intake tables and indexes."""
    from sqlalchemy import text

    intake_indexes = [
        (
            "ix_intake_workspaces_tenant_id",
            f'CREATE INDEX IF NOT EXISTS ix_intake_workspaces_tenant_id '
            f'ON "{ts}".intake_workspaces (tenant_id)',
            ("intake_workspaces", "(tenant_id)"),
        ),
        (
            "ix_intake_workspaces_status",
            f'CREATE INDEX IF NOT EXISTS ix_intake_workspaces_status '
            f'ON "{ts}".intake_workspaces (status)',
            ("intake_workspaces", "(status)"),
        ),
        (
            "ix_intake_workspaces_created_at",
            f'CREATE INDEX IF NOT EXISTS ix_intake_workspaces_created_at '
            f'ON "{ts}".intake_workspaces (created_at)',
            ("intake_workspaces", "(created_at)"),
        ),
        (
            "ix_intake_workspaces_apply_status",
            f'CREATE INDEX IF NOT EXISTS ix_intake_workspaces_apply_status '
            f'ON "{ts}".intake_workspaces (apply_status)',
            ("intake_workspaces", "(apply_status)"),
        ),
        (
            "ix_intake_uploads_workspace_id",
            f'CREATE INDEX IF NOT EXISTS ix_intake_uploads_workspace_id '
            f'ON "{ts}".intake_uploads (workspace_id)',
            ("intake_uploads", "(workspace_id)"),
        ),
        (
            "ix_intake_uploads_tenant_id",
            f'CREATE INDEX IF NOT EXISTS ix_intake_uploads_tenant_id '
            f'ON "{ts}".intake_uploads (tenant_id)',
            ("intake_uploads", "(tenant_id)"),
        ),
        (
            "ix_intake_product_rows_workspace_id",
            f'CREATE INDEX IF NOT EXISTS ix_intake_product_rows_workspace_id '
            f'ON "{ts}".intake_product_rows (workspace_id)',
            ("intake_product_rows", "(workspace_id)"),
        ),
        (
            "ix_intake_product_rows_upload_order",
            f'CREATE INDEX IF NOT EXISTS ix_intake_product_rows_upload_order '
            f'ON "{ts}".intake_product_rows (upload_id, row_index)',
            ("intake_product_rows", "(upload_id, row_index)"),
        ),
        (
            "ix_intake_product_rows_review_status",
            f'CREATE INDEX IF NOT EXISTS ix_intake_product_rows_review_status '
            f'ON "{ts}".intake_product_rows (review_status)',
            ("intake_product_rows", "(review_status)"),
        ),
        (
            "ix_intake_product_rows_target_sku_id",
            f'CREATE INDEX IF NOT EXISTS ix_intake_product_rows_target_sku_id '
            f'ON "{ts}".intake_product_rows (target_sku_id)',
            ("intake_product_rows", "(target_sku_id)"),
        ),
        (
            "ix_intake_validation_issues_workspace_id",
            f'CREATE INDEX IF NOT EXISTS ix_intake_validation_issues_workspace_id '
            f'ON "{ts}".intake_validation_issues (workspace_id)',
            ("intake_validation_issues", "(workspace_id)"),
        ),
        (
            "ix_intake_validation_issues_row_id",
            f'CREATE INDEX IF NOT EXISTS ix_intake_validation_issues_row_id '
            f'ON "{ts}".intake_validation_issues (row_id)',
            ("intake_validation_issues", "(row_id)"),
        ),
        (
            "ix_intake_validation_issues_severity",
            f'CREATE INDEX IF NOT EXISTS ix_intake_validation_issues_severity '
            f'ON "{ts}".intake_validation_issues (severity)',
            ("intake_validation_issues", "(severity)"),
        ),
    ]

    for table_name in (
        "intake_workspaces",
        "intake_uploads",
        "intake_product_rows",
        "intake_validation_issues",
    ):
        if not await _table_exists(db, ts, table_name):
            return

    workspace_columns = [
        ("apply_status", "VARCHAR(32) NOT NULL DEFAULT 'not_applied'"),
        ("applied_at", "TIMESTAMPTZ"),
        ("applied_by", "UUID"),
        ("apply_result", "JSONB NOT NULL DEFAULT '{}'::jsonb"),
    ]
    for column_name, ddl in workspace_columns:
        if not await _column_exists(db, ts, "intake_workspaces", column_name):
            await db.execute(text(f'ALTER TABLE "{ts}".intake_workspaces ADD COLUMN {column_name} {ddl}'))

    row_columns = [
        ("target_sku_id", "UUID"),
        ("apply_status", "VARCHAR(32) NOT NULL DEFAULT 'not_applied'"),
        ("apply_error_code", "VARCHAR(64)"),
        ("apply_error_message", "TEXT"),
    ]
    for column_name, ddl in row_columns:
        if not await _column_exists(db, ts, "intake_product_rows", column_name):
            await db.execute(text(f'ALTER TABLE "{ts}".intake_product_rows ADD COLUMN {column_name} {ddl}'))

    if not await _constraint_exists(db, ts, "intake_workspaces", "ck_intake_workspaces_apply_status"):
        await db.execute(text(
            f'ALTER TABLE "{ts}".intake_workspaces '
            "ADD CONSTRAINT ck_intake_workspaces_apply_status "
            "CHECK (apply_status IN ('not_applied', 'applying', 'applied', 'failed'))"
        ))

    if not await _constraint_exists(db, ts, "intake_product_rows", "ck_intake_product_rows_apply_status"):
        await db.execute(text(
            f'ALTER TABLE "{ts}".intake_product_rows '
            "ADD CONSTRAINT ck_intake_product_rows_apply_status "
            "CHECK (apply_status IN ('not_applied', 'applied', 'failed', 'skipped'))"
        ))

    for index_name, create_sql, fragments in intake_indexes:
        await _ensure_index(db, ts, index_name, create_sql, fragments)

    print(f"[reconcile] {ts}: ensured U4 intake apply audit contract")


async def bootstrap(tenant_schema: str, database_url: str) -> None:
    """Create tenant schema and all required tables."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker

    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    engine = create_async_engine(database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    ts = tenant_schema

    async with async_session() as db:
        await db.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{ts}"'))
        await db.execute(text(f'SET LOCAL search_path TO "{ts}", public'))
        await _ensure_public_binding_balance_constraint(db)

        # Enums (idempotent)
        for enum_ddl in [
            "DO $$ BEGIN CREATE TYPE order_status AS ENUM "
            "('draft','confirmed','partially_paid','paid','fulfilled','cancelled','voided','returned'); "
            "EXCEPTION WHEN duplicate_object THEN null; END $$",
            "DO $$ BEGIN CREATE TYPE account_type AS ENUM "
            "('receivable','revenue','cash','liability'); "
            "EXCEPTION WHEN duplicate_object THEN null; END $$",
        ]:
            await db.execute(text(enum_ddl))

        # Core business tables (idempotent via CREATE TABLE IF NOT EXISTS)
        tables = [
            f'CREATE TABLE IF NOT EXISTS "{ts}".users ('
            "id UUID PRIMARY KEY DEFAULT gen_random_uuid(),"
            "email VARCHAR(255) NOT NULL UNIQUE, password_hash VARCHAR(255) NOT NULL,"
            "full_name TEXT, is_active BOOLEAN NOT NULL DEFAULT true,"
            "created_at TIMESTAMPTZ DEFAULT now(), updated_at TIMESTAMPTZ DEFAULT now(),"
            "is_deleted BOOLEAN DEFAULT false, deleted_at TIMESTAMPTZ,"
            "created_by UUID, updated_by UUID)",

            f'CREATE TABLE IF NOT EXISTS "{ts}".roles ('
            "id UUID PRIMARY KEY DEFAULT gen_random_uuid(),"
            "name VARCHAR(100) NOT NULL UNIQUE, description TEXT,"
            "created_at TIMESTAMPTZ DEFAULT now(), updated_at TIMESTAMPTZ DEFAULT now(),"
            "is_deleted BOOLEAN DEFAULT false, deleted_at TIMESTAMPTZ,"
            "created_by UUID, updated_by UUID)",

            f'CREATE TABLE IF NOT EXISTS "{ts}".permissions ('
            "id UUID PRIMARY KEY DEFAULT gen_random_uuid(),"
            "code VARCHAR(100) NOT NULL UNIQUE, description TEXT,"
            "created_at TIMESTAMPTZ DEFAULT now(), updated_at TIMESTAMPTZ DEFAULT now(),"
            "is_deleted BOOLEAN DEFAULT false, deleted_at TIMESTAMPTZ,"
            "created_by UUID, updated_by UUID)",

            f'CREATE TABLE IF NOT EXISTS "{ts}".user_roles ('
            f'user_id UUID NOT NULL REFERENCES "{ts}".users(id) ON DELETE CASCADE,'
            f'role_id UUID NOT NULL REFERENCES "{ts}".roles(id) ON DELETE CASCADE,'
            "PRIMARY KEY (user_id, role_id))",

            f'CREATE TABLE IF NOT EXISTS "{ts}".role_permissions ('
            f'role_id UUID NOT NULL REFERENCES "{ts}".roles(id) ON DELETE CASCADE,'
            f'permission_id UUID NOT NULL REFERENCES "{ts}".permissions(id) ON DELETE CASCADE,'
            "PRIMARY KEY (role_id, permission_id))",

            f'CREATE TABLE IF NOT EXISTS "{ts}".skus ('
            "id UUID PRIMARY KEY DEFAULT gen_random_uuid(),"
            "sku_code VARCHAR(64) NOT NULL UNIQUE, name VARCHAR(255) NOT NULL,"
            "description TEXT, unit VARCHAR(32) NOT NULL DEFAULT 'unit',"
            "category VARCHAR(64), is_active BOOLEAN NOT NULL DEFAULT true,"
            "created_at TIMESTAMPTZ DEFAULT now(), updated_at TIMESTAMPTZ DEFAULT now(),"
            "is_deleted BOOLEAN DEFAULT false, deleted_at TIMESTAMPTZ,"
            "created_by UUID, updated_by UUID)",

            f'CREATE TABLE IF NOT EXISTS "{ts}".inventory_stocks ('
            "id UUID PRIMARY KEY DEFAULT gen_random_uuid(),"
            f'sku_id UUID NOT NULL UNIQUE REFERENCES "{ts}".skus(id) ON DELETE CASCADE,'
            "quantity_on_hand NUMERIC(12,2) NOT NULL DEFAULT 0,"
            "quantity_reserved NUMERIC(12,2) NOT NULL DEFAULT 0,"
            "created_at TIMESTAMPTZ DEFAULT now(), updated_at TIMESTAMPTZ DEFAULT now(),"
            "is_deleted BOOLEAN DEFAULT false, deleted_at TIMESTAMPTZ,"
            "created_by UUID, updated_by UUID)",

            f'CREATE TABLE IF NOT EXISTS "{ts}".inventory_movements ('
            "id UUID PRIMARY KEY DEFAULT gen_random_uuid(),"
            f'sku_id UUID NOT NULL REFERENCES "{ts}".skus(id) ON DELETE CASCADE,'
            "movement_type VARCHAR(32) NOT NULL,"
            "quantity NUMERIC(12,2) NOT NULL,"
            "quantity_before NUMERIC(12,2) NOT NULL,"
            "quantity_after NUMERIC(12,2) NOT NULL,"
            "reason TEXT,"
            "reference_type VARCHAR(50),"
            "reference_id UUID,"
            "created_at TIMESTAMPTZ DEFAULT now(), updated_at TIMESTAMPTZ DEFAULT now(),"
            "is_deleted BOOLEAN DEFAULT false, deleted_at TIMESTAMPTZ,"
            "created_by UUID, updated_by UUID)",

            f'CREATE TABLE IF NOT EXISTS "{ts}".orders ('
            "id UUID PRIMARY KEY DEFAULT gen_random_uuid(),"
            "wholesaler_id UUID NOT NULL, retailer_id UUID NOT NULL,"
            "status order_status NOT NULL DEFAULT 'draft',"
            "total_amount NUMERIC(12,2) NOT NULL DEFAULT 0, notes TEXT,"
            "created_at TIMESTAMPTZ DEFAULT now(), updated_at TIMESTAMPTZ DEFAULT now(),"
            "is_deleted BOOLEAN DEFAULT false, deleted_at TIMESTAMPTZ,"
            "created_by UUID, updated_by UUID)",

            f'CREATE TABLE IF NOT EXISTS "{ts}".order_items ('
            "id UUID PRIMARY KEY DEFAULT gen_random_uuid(),"
            f'order_id UUID NOT NULL REFERENCES "{ts}".orders(id) ON DELETE CASCADE,'
            "product_name TEXT NOT NULL, sku_code VARCHAR(64) NOT NULL,"
            "quantity INTEGER NOT NULL, unit_price NUMERIC(12,2) NOT NULL,"
            "subtotal NUMERIC(12,2) NOT NULL,"
            "created_at TIMESTAMPTZ DEFAULT now(), updated_at TIMESTAMPTZ DEFAULT now(),"
            "is_deleted BOOLEAN DEFAULT false, deleted_at TIMESTAMPTZ,"
            "created_by UUID, updated_by UUID)",

            f'CREATE TABLE IF NOT EXISTS "{ts}".inventory_reservations ('
            "id UUID PRIMARY KEY DEFAULT gen_random_uuid(),"
            f'order_id UUID NOT NULL REFERENCES "{ts}".orders(id) ON DELETE CASCADE,'
            f'order_item_id UUID NOT NULL REFERENCES "{ts}".order_items(id) ON DELETE CASCADE,'
            f'sku_id UUID NOT NULL REFERENCES "{ts}".skus(id) ON DELETE CASCADE,'
            "sku_code VARCHAR(64) NOT NULL,"
            "quantity NUMERIC(12,2) NOT NULL,"
            "status VARCHAR(32) NOT NULL DEFAULT 'reserved',"
            "reserved_at TIMESTAMPTZ NOT NULL DEFAULT now(),"
            "consumed_at TIMESTAMPTZ,"
            "released_at TIMESTAMPTZ,"
            "reference_type VARCHAR(50) NOT NULL DEFAULT 'order',"
            "reference_id UUID NOT NULL,"
            "created_at TIMESTAMPTZ DEFAULT now(), updated_at TIMESTAMPTZ DEFAULT now(),"
            "is_deleted BOOLEAN DEFAULT false, deleted_at TIMESTAMPTZ,"
            "created_by UUID, updated_by UUID,"
            "CONSTRAINT ck_inventory_reservations_quantity_positive CHECK (quantity > 0),"
            "CONSTRAINT ck_inventory_reservations_status "
            "CHECK (status IN ('reserved', 'consumed', 'released')))",

            f'CREATE TABLE IF NOT EXISTS "{ts}".payments ('
            "id UUID PRIMARY KEY DEFAULT gen_random_uuid(),"
            f'order_id UUID NOT NULL REFERENCES "{ts}".orders(id) ON DELETE CASCADE,'
            "retailer_id UUID NOT NULL,"
            "transaction_id VARCHAR(64),"
            "amount NUMERIC(12,2) NOT NULL,"
            "method VARCHAR(50) NOT NULL DEFAULT 'cash',"
            "status VARCHAR(50) NOT NULL DEFAULT 'completed',"
            "reference_number VARCHAR(100),"
            "idempotency_key VARCHAR(64) UNIQUE,"
            "created_at TIMESTAMPTZ DEFAULT now(), updated_at TIMESTAMPTZ DEFAULT now(),"
            "is_deleted BOOLEAN DEFAULT false, deleted_at TIMESTAMPTZ,"
            "created_by UUID, updated_by UUID,"
            "CONSTRAINT ck_payments_method_canonical "
            "CHECK (method IN ('cash', 'transfer', 'credit')))",

            f'CREATE TABLE IF NOT EXISTS "{ts}".ledger_entries ('
            "id UUID PRIMARY KEY DEFAULT gen_random_uuid(),"
            "transaction_date TIMESTAMPTZ NOT NULL DEFAULT now(),"
            "account_type account_type NOT NULL,"
            "amount NUMERIC(20,4) NOT NULL,"
            "reference_type VARCHAR(50) NOT NULL, reference_id UUID NOT NULL,"
            "description TEXT, entry_version INTEGER NOT NULL DEFAULT 1,"
            "hash VARCHAR(64),"
            "created_at TIMESTAMPTZ DEFAULT now(), updated_at TIMESTAMPTZ DEFAULT now(),"
            "is_deleted BOOLEAN DEFAULT false, deleted_at TIMESTAMPTZ,"
            "created_by UUID, updated_by UUID)",

            # retailer_prices - mirrors migration 017 contract exactly
            # Audit fields: NOT NULL (matching AuditMixin / migration 017,
            # unlike legacy tables where bootstrap omitted NOT NULL)
            f'CREATE TABLE IF NOT EXISTS "{ts}".retailer_prices ('
            "id UUID PRIMARY KEY DEFAULT gen_random_uuid(),"
            "retailer_id UUID NOT NULL,"
            "sku_id UUID NOT NULL,"
            "price NUMERIC(12,2) NOT NULL,"
            "created_at TIMESTAMPTZ NOT NULL DEFAULT now(),"
            "updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),"
            "is_deleted BOOLEAN NOT NULL DEFAULT false,"
            "deleted_at TIMESTAMPTZ,"
            "created_by UUID, updated_by UUID,"
            "CONSTRAINT uq_retailer_prices_retailer_sku UNIQUE (retailer_id, sku_id),"
            "CONSTRAINT ck_retailer_prices_positive_price CHECK (price > 0))",

            # import_runs - mirrors migration 022 contract exactly
            # U3-B1: 3-phase import contract table (preview -> validate -> apply)
            f'CREATE TABLE IF NOT EXISTS "{ts}".import_runs ('
            "id UUID PRIMARY KEY DEFAULT gen_random_uuid(),"
            "import_id VARCHAR(64) NOT NULL UNIQUE,"
            "tenant_id UUID NOT NULL,"
            "status VARCHAR(32) NOT NULL DEFAULT 'previewed',"
            "source_filename VARCHAR(255),"
            "source_encoding VARCHAR(32),"
            "total_rows INTEGER NOT NULL DEFAULT 0,"
            "valid_rows INTEGER,"
            "error_rows INTEGER,"
            "warning_rows INTEGER,"
            "mapping JSONB,"
            "validation_result JSONB,"
            "apply_result JSONB,"
            "created_rows INTEGER DEFAULT 0,"
            "skipped_rows INTEGER DEFAULT 0,"
            "updated_rows INTEGER DEFAULT 0,"
            "applied_by UUID,"
            "applied_at TIMESTAMPTZ,"
            "created_at TIMESTAMPTZ NOT NULL DEFAULT now(),"
            "updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),"
            "is_deleted BOOLEAN NOT NULL DEFAULT false,"
            "deleted_at TIMESTAMPTZ)",

            # intake_workspaces - U4-C tenant-scoped intake skeleton
            f'CREATE TABLE IF NOT EXISTS "{ts}".intake_workspaces ('
            "id UUID PRIMARY KEY DEFAULT gen_random_uuid(),"
            "tenant_id UUID NOT NULL,"
            "name VARCHAR(160) NOT NULL,"
            "description TEXT,"
            "source_type VARCHAR(32) NOT NULL,"
            "status VARCHAR(32) NOT NULL DEFAULT 'OPEN',"
            "apply_status VARCHAR(32) NOT NULL DEFAULT 'not_applied',"
            "applied_at TIMESTAMPTZ,"
            "applied_by UUID,"
            "apply_result JSONB NOT NULL DEFAULT '{}'::jsonb,"
            "approved_by UUID,"
            "approved_at TIMESTAMPTZ,"
            "metadata JSONB NOT NULL DEFAULT '{}'::jsonb,"
            "created_by UUID, updated_by UUID,"
            "created_at TIMESTAMPTZ NOT NULL DEFAULT now(),"
            "updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),"
            "is_deleted BOOLEAN NOT NULL DEFAULT false,"
            "deleted_at TIMESTAMPTZ,"
            "CONSTRAINT ck_intake_workspaces_apply_status "
            "CHECK (apply_status IN ('not_applied', 'applying', 'applied', 'failed')))",

            # intake_uploads - source metadata only; no file handling in U4-C
            f'CREATE TABLE IF NOT EXISTS "{ts}".intake_uploads ('
            "id UUID PRIMARY KEY DEFAULT gen_random_uuid(),"
            "tenant_id UUID NOT NULL,"
            f'workspace_id UUID NOT NULL REFERENCES "{ts}".intake_workspaces(id) ON DELETE CASCADE,'
            "filename VARCHAR(255) NOT NULL,"
            "content_type VARCHAR(128),"
            "file_ext VARCHAR(16) NOT NULL,"
            "file_size_bytes INTEGER NOT NULL,"
            "sha256 CHAR(64) NOT NULL,"
            "storage_key VARCHAR(512),"
            "status VARCHAR(32) NOT NULL DEFAULT 'RECEIVED',"
            "row_count INTEGER NOT NULL DEFAULT 0,"
            "column_count INTEGER NOT NULL DEFAULT 0,"
            "headers_raw JSONB NOT NULL DEFAULT '[]'::jsonb,"
            "headers_normalized JSONB NOT NULL DEFAULT '{}'::jsonb,"
            "parse_summary JSONB,"
            "created_by UUID, updated_by UUID,"
            "created_at TIMESTAMPTZ NOT NULL DEFAULT now(),"
            "updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),"
            "is_deleted BOOLEAN NOT NULL DEFAULT false,"
            "deleted_at TIMESTAMPTZ)",

            # intake_product_rows - staged rows only; no direct SKU writes
            f'CREATE TABLE IF NOT EXISTS "{ts}".intake_product_rows ('
            "id UUID PRIMARY KEY DEFAULT gen_random_uuid(),"
            "tenant_id UUID NOT NULL,"
            f'workspace_id UUID NOT NULL REFERENCES "{ts}".intake_workspaces(id) ON DELETE CASCADE,'
            f'upload_id UUID NOT NULL REFERENCES "{ts}".intake_uploads(id) ON DELETE CASCADE,'
            "source_row_number INTEGER NOT NULL,"
            "row_index INTEGER NOT NULL,"
            "raw_values JSONB NOT NULL DEFAULT '{}'::jsonb,"
            "normalized_values JSONB NOT NULL DEFAULT '{}'::jsonb,"
            "mapping_version INTEGER NOT NULL DEFAULT 1,"
            "sku_code VARCHAR(64),"
            "name VARCHAR(255),"
            "unit VARCHAR(32),"
            "category VARCHAR(64),"
            "unit_price NUMERIC(12,2),"
            "barcode VARCHAR(128),"
            "image_asset_id UUID,"
            "target_sku_id UUID,"
            "review_status VARCHAR(32) NOT NULL DEFAULT 'UNREVIEWED',"
            "apply_status VARCHAR(32) NOT NULL DEFAULT 'not_applied',"
            "apply_error_code VARCHAR(64),"
            "apply_error_message TEXT,"
            "dedupe_key VARCHAR(160),"
            "created_by UUID, updated_by UUID,"
            "created_at TIMESTAMPTZ NOT NULL DEFAULT now(),"
            "updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),"
            "is_deleted BOOLEAN NOT NULL DEFAULT false,"
            "deleted_at TIMESTAMPTZ,"
            "CONSTRAINT ck_intake_product_rows_apply_status "
            "CHECK (apply_status IN ('not_applied', 'applied', 'failed', 'skipped')))",

            # intake_validation_issues - staged validation findings
            f'CREATE TABLE IF NOT EXISTS "{ts}".intake_validation_issues ('
            "id UUID PRIMARY KEY DEFAULT gen_random_uuid(),"
            "tenant_id UUID NOT NULL,"
            f'workspace_id UUID NOT NULL REFERENCES "{ts}".intake_workspaces(id) ON DELETE CASCADE,'
            f'upload_id UUID REFERENCES "{ts}".intake_uploads(id) ON DELETE CASCADE,'
            f'row_id UUID REFERENCES "{ts}".intake_product_rows(id) ON DELETE CASCADE,'
            "source_row_number INTEGER,"
            "severity VARCHAR(16) NOT NULL,"
            "code VARCHAR(64) NOT NULL,"
            "field VARCHAR(128),"
            "source_header VARCHAR(255),"
            "message TEXT NOT NULL,"
            "is_blocking BOOLEAN NOT NULL DEFAULT false,"
            "resolved_at TIMESTAMPTZ,"
            "resolved_by UUID,"
            "created_by UUID, updated_by UUID,"
            "created_at TIMESTAMPTZ NOT NULL DEFAULT now(),"
            "updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),"
            "is_deleted BOOLEAN NOT NULL DEFAULT false,"
            "deleted_at TIMESTAMPTZ)",
        ]
        for ddl in tables:
            await db.execute(text(ddl))

        await db.execute(text(
            f'CREATE INDEX IF NOT EXISTS ix_inventory_reservations_order_id '
            f'ON "{ts}".inventory_reservations(order_id)'
        ))
        await db.execute(text(
            f'CREATE INDEX IF NOT EXISTS ix_inventory_reservations_sku_id '
            f'ON "{ts}".inventory_reservations(sku_id)'
        ))
        await db.execute(text(
            f'CREATE INDEX IF NOT EXISTS ix_inventory_reservations_status '
            f'ON "{ts}".inventory_reservations(status)'
        ))
        await db.execute(text(
            f'CREATE UNIQUE INDEX IF NOT EXISTS ux_inventory_reservations_active_order_item '
            f'ON "{ts}".inventory_reservations(order_item_id) WHERE status = \'reserved\''
        ))

        # Ledger immutability trigger
        await db.execute(text(
            "CREATE OR REPLACE FUNCTION public.prevent_ledger_modification() "
            "RETURNS TRIGGER AS $$ BEGIN "
            "IF TG_OP = 'UPDATE' THEN RAISE EXCEPTION 'Ledger immutable' "
            "USING ERRCODE = 'integrity_constraint_violation'; END IF; "
            "IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'Ledger immutable' "
            "USING ERRCODE = 'integrity_constraint_violation'; END IF; "
            "RETURN OLD; END; $$ LANGUAGE plpgsql"
        ))
        await db.execute(text(
            f'DROP TRIGGER IF EXISTS prevent_ledger_mod ON "{ts}".ledger_entries'
        ))
        await db.execute(text(
            f'CREATE TRIGGER prevent_ledger_mod '
            f'BEFORE UPDATE OR DELETE ON "{ts}".ledger_entries '
            f'FOR EACH ROW EXECUTE FUNCTION public.prevent_ledger_modification()'
        ))

        # --- Schema reconciliation ---
        # CREATE TABLE IF NOT EXISTS is a no-op for existing tables, even if
        # their column definitions diverge from the DDL above.  The blocks
        # below bridge the gap for tenant schemas that were bootstrapped by
        # an older version of this script (e.g. missing retailer_id on
        # payments, missing reporting views / matviews).

        # --- payments: reconcile retailer_id / transaction_id (mirrors 021) ---
        await _reconcile_payments(db, ts)

        # --- orders: reconcile canonical order_status enum values ---
        await _reconcile_order_status(db, ts)

        # --- retailer_prices: reconcile indexes (mirrors 017) ---
        await _reconcile_retailer_prices(db, ts)

        # --- reporting views / matviews (mirrors 012 + 013) ---
        await _reconcile_reporting(db, ts)

        # --- import_runs: reconcile indexes (mirrors 022) ---
        await _reconcile_import_runs(db, ts)

        # --- U4-C intake skeleton: reconcile indexes (mirrors 024) ---
        await _reconcile_intake_tables(db, ts)

        await db.commit()

    await engine.dispose()
    print(f"[bootstrap] Tenant schema '{ts}' ready ({len(tables)} tables, reconciled).")


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap a tenant schema")
    parser.add_argument("tenant_schema", help="Tenant schema name (e.g. t_dev)")
    parser.add_argument("--database-url", default=None,
                        help="Database URL (default: DATABASE_URL env var)")
    args = parser.parse_args()

    _add_backend_to_path()

    db_url = args.database_url or os.environ.get("DATABASE_URL", "")
    if not db_url:
        print("ERROR: DATABASE_URL not set and --database-url not provided", file=sys.stderr)
        sys.exit(1)

    asyncio.run(bootstrap(args.tenant_schema, db_url))


if __name__ == "__main__":
    main()
