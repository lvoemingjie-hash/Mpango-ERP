"""DC-2M2: Reconcile legacy registered tenant schemas.

Revision ID: 031_legacy_tenant_reconciliation
Revises: 030_platform_backup_status_source
Create Date: 2026-07-12

Forward-only repair for registered/live tenant schemas whose
retailer_prices/reporting objects were created before the current canonical
tenant contract. Rollback is application-version rollback plus restore from a
verified pre-migration database backup/snapshot; this migration does not offer
an automatic downgrade that can safely reverse tenant-specific legacy drift.
"""
from __future__ import annotations

import re
from typing import Any

from alembic import op
import sqlalchemy as sa

from models.tenant_onboarding import LIVE_REGISTRATION_STATUSES


# revision identifiers, used by Alembic.
revision = "031_legacy_tenant_reconciliation"
down_revision = "030_platform_backup_status_source"
branch_labels = None
depends_on = None


ADVISORY_LOCK_KEY = 20260712031
LOCK_TIMEOUT = "5s"
STATEMENT_TIMEOUT = "60s"
TENANT_SCHEMA_RE = re.compile(r"^t_[0-9a-f]{32}$")
WHOLESALER_ACTIVE_STATUSES = ("active", "provisioning")

RETAILER_PRICES = "retailer_prices"
UQ_RETAILER_PRICES = "uq_retailer_prices_retailer_sku"
CK_RETAILER_PRICES = "ck_retailer_prices_positive_price"
IX_RETAILER_PRICES_RETAILER = "ix_retailer_prices_retailer_id"
IX_RETAILER_PRICES_SKU = "ix_retailer_prices_sku_id"
LEDGER_ENTRIES = "ledger_entries"
RPT_SALES_DAILY = "rpt_sales_daily"
MV_SALES_DAILY = "mv_sales_daily"
IX_MV_SALES_DAILY = "idx_mv_sales_daily_u1"
REPORTING_ROLE = "reporting_role"

RELKIND_LABELS = {
    "r": "table",
    "p": "partitioned table",
    "v": "view",
    "m": "materialized view",
    "i": "index",
    "I": "partitioned index",
    "S": "sequence",
    "f": "foreign table",
}

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

MV_SALES_DAILY_COLUMNS = {
    "transaction_date": "date",
    "reporting_currency_code": "character(3)",
    "daily_revenue": "numeric(20,4)",
    "transaction_count": "integer",
}

class QuotedNames:
    def __init__(
        self,
        *,
        schema: str,
        retailer_prices: str,
        ledger_entries: str,
        rpt_sales_daily: str,
        mv_sales_daily: str,
        reporting_role: str,
        uq_retailer_prices: str,
        ck_retailer_prices: str,
        ix_retailer_prices_retailer: str,
        ix_retailer_prices_sku: str,
        ix_mv_sales_daily: str,
    ) -> None:
        self.schema = schema
        self.retailer_prices = retailer_prices
        self.ledger_entries = ledger_entries
        self.rpt_sales_daily = rpt_sales_daily
        self.mv_sales_daily = mv_sales_daily
        self.reporting_role = reporting_role
        self.uq_retailer_prices = uq_retailer_prices
        self.ck_retailer_prices = ck_retailer_prices
        self.ix_retailer_prices_retailer = ix_retailer_prices_retailer
        self.ix_retailer_prices_sku = ix_retailer_prices_sku
        self.ix_mv_sales_daily = ix_mv_sales_daily

    def qualified(self, attr: str) -> str:
        return f"{self.schema}.{getattr(self, attr)}"


class RetailerPricesPlan:
    def __init__(
        self,
        unique_action: str = "none",
        legacy_constraint_name: str | None = None,
        add_check_constraint: bool = False,
        create_indexes: list[str] | None = None,
    ) -> None:
        self.unique_action = unique_action
        self.legacy_constraint_name = legacy_constraint_name
        self.add_check_constraint = add_check_constraint
        self.create_indexes = create_indexes or []


class ReportingPlan:
    def __init__(
        self,
        drop_rpt_sales_daily: bool = False,
        create_mv_sales_daily: bool = False,
        create_unique_index: bool = False,
        grant_reporting_role: bool = True,
    ) -> None:
        self.drop_rpt_sales_daily = drop_rpt_sales_daily
        self.create_mv_sales_daily = create_mv_sales_daily
        self.create_unique_index = create_unique_index
        self.grant_reporting_role = grant_reporting_role


class TenantPlan:
    def __init__(
        self,
        *,
        schema: str,
        quoted: QuotedNames,
        retailer_prices: RetailerPricesPlan,
        reporting: ReportingPlan,
    ) -> None:
        self.schema = schema
        self.quoted = quoted
        self.retailer_prices = retailer_prices
        self.reporting = reporting

    def actions(self) -> list[str]:
        actions: list[str] = []
        if self.retailer_prices.unique_action == "rename":
            actions.append("rename legacy retailer_prices unique constraint")
        elif self.retailer_prices.unique_action == "add":
            actions.append("add canonical retailer_prices unique constraint")
        if self.retailer_prices.add_check_constraint:
            actions.append("add retailer_prices positive price check")
        actions.extend(f"create {index_name}" for index_name in self.retailer_prices.create_indexes)
        if self.reporting.drop_rpt_sales_daily:
            actions.append("drop legacy rpt_sales_daily view")
        if self.reporting.create_mv_sales_daily:
            actions.append("create mv_sales_daily")
        if self.reporting.create_unique_index:
            actions.append("create idx_mv_sales_daily_u1")
        if self.reporting.grant_reporting_role:
            actions.append("grant reporting_role access")
        return actions or ["no-op"]


class PreflightFailure(RuntimeError):
    pass


def _scalar(bind, sql: str, params: dict[str, Any] | None = None) -> Any:
    return bind.execute(sa.text(sql), params or {}).scalar()


def _quote_ident(bind, identifier: str) -> str:
    return bind.execute(
        sa.text("SELECT quote_ident(:identifier)"), {"identifier": identifier}
    ).scalar_one()


def _quoted_names(bind, schema: str) -> QuotedNames:
    return QuotedNames(
        schema=_quote_ident(bind, schema),
        retailer_prices=_quote_ident(bind, RETAILER_PRICES),
        ledger_entries=_quote_ident(bind, LEDGER_ENTRIES),
        rpt_sales_daily=_quote_ident(bind, RPT_SALES_DAILY),
        mv_sales_daily=_quote_ident(bind, MV_SALES_DAILY),
        reporting_role=_quote_ident(bind, REPORTING_ROLE),
        uq_retailer_prices=_quote_ident(bind, UQ_RETAILER_PRICES),
        ck_retailer_prices=_quote_ident(bind, CK_RETAILER_PRICES),
        ix_retailer_prices_retailer=_quote_ident(bind, IX_RETAILER_PRICES_RETAILER),
        ix_retailer_prices_sku=_quote_ident(bind, IX_RETAILER_PRICES_SKU),
        ix_mv_sales_daily=_quote_ident(bind, IX_MV_SALES_DAILY),
    )


def _qualified_name(q: QuotedNames, attr: str) -> str:
    return q.qualified(attr)


def _regclass_oid(bind, qualified_name: str) -> int | None:
    return _scalar(bind, "SELECT to_regclass(:qualified_name)::oid", {"qualified_name": qualified_name})


def _normalize_type(type_name: str) -> str:
    return "".join(type_name.lower().split())


def _normalize_sql(sql: str) -> str:
    return "".join(sql.lower().split())


def _label_relkind(relkind: str | None) -> str:
    return RELKIND_LABELS.get(relkind or "", relkind or "missing")


def _relation_kind(bind, schema: str, object_name: str) -> str | None:
    return _scalar(
        bind,
        """
        SELECT c.relkind
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = :schema AND c.relname = :object_name
        """,
        {"schema": schema, "object_name": object_name},
    )


def _columns_for_relation(bind, relation_oid: int) -> dict[str, dict[str, Any]]:
    rows = bind.execute(
        sa.text(
            """
            SELECT a.attname, format_type(a.atttypid, a.atttypmod) AS formatted_type,
                   a.attnotnull
            FROM pg_attribute a
            WHERE a.attrelid = :relation_oid
              AND a.attnum > 0
              AND NOT a.attisdropped
            """
        ),
        {"relation_oid": relation_oid},
    ).mappings()
    return {row["attname"]: dict(row) for row in rows}


def _validate_tenant_schema_name(schema: str | None, evidence_name: str) -> None:
    if schema is None or schema.strip() == "":
        raise PreflightFailure(f"{evidence_name}: tenant_schema is missing")
    if len(schema) > 63 or not TENANT_SCHEMA_RE.fullmatch(schema):
        raise PreflightFailure(
            f"{schema}: tenant_schema is not a valid derived tenant identifier"
        )


def _ensure_registry_tables_exist(bind) -> None:
    missing = []
    for qualified_name in ("public.tenant_registrations", "public.wholesalers"):
        if _regclass_oid(bind, qualified_name) is None:
            missing.append(qualified_name)
    if missing:
        raise PreflightFailure(
            "registry source unavailable: missing " + ", ".join(missing)
        )


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

        derived_schema = row["derived_schema"]
        if schema != derived_schema:
            failures.append(
                f"{schema}: tenant_schema does not match wholesaler-derived schema"
            )

        schema_exists = bool(
            _scalar(
                bind,
                "SELECT 1 FROM pg_namespace WHERE nspname = :schema",
                {"schema": schema},
            )
        )
        if not schema_exists:
            failures.append(f"{schema}: registered tenant schema is missing")

    if failures:
        raise PreflightFailure("; ".join(failures))


def _validate_retailer_price_columns(bind, schema: str, table_oid: int) -> None:
    columns = _columns_for_relation(bind, table_oid)
    violations: list[str] = []
    for column_name, (expected_type, expected_not_null) in RETAILER_PRICE_COLUMNS.items():
        column = columns.get(column_name)
        if column is None:
            violations.append(f"missing column {column_name}")
            continue
        actual_type = _normalize_type(column["formatted_type"])
        if actual_type != _normalize_type(expected_type):
            violations.append(
                f"column {column_name} has type {column['formatted_type']}, expected {expected_type}"
            )
        if expected_not_null and not column["attnotnull"]:
            violations.append(f"column {column_name} is nullable")
    if violations:
        raise PreflightFailure(f"{schema}.{RETAILER_PRICES}: " + "; ".join(violations))


def _constraint_rows(bind, table_oid: int) -> list[dict[str, Any]]:
    rows = bind.execute(
        sa.text(
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
    ).mappings()
    return [dict(row) for row in rows]


def _is_equivalent_unique_constraint(row: dict[str, Any]) -> bool:
    return (
        row["contype"] == "u"
        and bool(row["convalidated"])
        and bool(row["indisunique"])
        and bool(row["indisvalid"])
        and not bool(row["has_predicate"])
        and list(row["column_names"] or []) == ["retailer_id", "sku_id"]
    )


def _canonical_name_is_free(bind, schema: str, table_oid: int) -> bool:
    canonical_constraint = bind.execute(
        sa.text(
            """
            SELECT 1
            FROM pg_constraint
            WHERE conrelid = :table_oid AND conname = :constraint_name
            """
        ),
        {"table_oid": table_oid, "constraint_name": UQ_RETAILER_PRICES},
    ).first()
    if canonical_constraint is not None:
        return False
    return _relation_kind(bind, schema, UQ_RETAILER_PRICES) is None


def _has_duplicate_retailer_prices(bind, q: QuotedNames) -> bool:
    return bool(
        _scalar(
            bind,
            f"""
            SELECT 1
            FROM {_qualified_name(q, 'retailer_prices')}
            GROUP BY retailer_id, sku_id
            HAVING COUNT(*) > 1
            LIMIT 1
            """,
        )
    )


def _has_price_violations(bind, q: QuotedNames) -> bool:
    return bool(
        _scalar(
            bind,
            f"""
            SELECT 1
            FROM {_qualified_name(q, 'retailer_prices')}
            WHERE price IS NULL OR price <= 0
            LIMIT 1
            """,
        )
    )


def _check_constraint_is_canonical(row: dict[str, Any]) -> bool:
    definition = _normalize_sql(row["constraint_def"] or "")
    return (
        row["contype"] == "c"
        and bool(row["convalidated"])
        and (
            "check((price>(0)::numeric))" in definition
            or "check((price>0))" in definition
            or "check(price>0)" in definition
        )
    )


def _index_rows(bind, schema: str, index_name: str) -> list[dict[str, Any]]:
    rows = bind.execute(
        sa.text(
            """
            SELECT idx.oid AS index_oid,
                   idx.relname AS index_name,
                   idx.relkind,
                   tbl.oid AS table_oid,
                   tbl.relname AS table_name,
                   i.indisunique,
                   i.indisvalid,
                   i.indpred IS NOT NULL AS has_predicate,
                   COALESCE(array_agg(a.attname ORDER BY keys.ordinality)
                       FILTER (WHERE a.attname IS NOT NULL), ARRAY[]::name[]) AS column_names,
                   EXISTS (
                       SELECT 1 FROM pg_constraint c WHERE c.conindid = idx.oid
                   ) AS is_constraint_backed
            FROM pg_class idx
            JOIN pg_namespace n ON n.oid = idx.relnamespace
            LEFT JOIN pg_index i ON i.indexrelid = idx.oid
            LEFT JOIN pg_class tbl ON tbl.oid = i.indrelid
            LEFT JOIN LATERAL unnest(i.indkey) WITH ORDINALITY AS keys(attnum, ordinality)
                ON true
            LEFT JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = keys.attnum
            WHERE n.nspname = :schema AND idx.relname = :index_name
            GROUP BY idx.oid, idx.relname, idx.relkind, tbl.oid, tbl.relname,
                     i.indisunique, i.indisvalid, i.indpred
            """
        ),
        {"schema": schema, "index_name": index_name},
    ).mappings()
    return [dict(row) for row in rows]


def _validate_or_plan_index(
    bind,
    schema: str,
    table_oid: int,
    table_name: str,
    index_name: str,
    expected_columns: list[str],
    unique: bool,
) -> bool:
    rows = _index_rows(bind, schema, index_name)
    if not rows:
        return True
    if len(rows) > 1:
        raise PreflightFailure(f"{schema}.{index_name}: duplicate index-name objects")
    row = rows[0]
    if row["relkind"] not in ("i", "I"):
        raise PreflightFailure(
            f"{schema}.{index_name}: name is occupied by {_label_relkind(row['relkind'])}"
        )
    if row["table_oid"] != table_oid or row["table_name"] != table_name:
        raise PreflightFailure(f"{schema}.{index_name}: index targets the wrong relation")
    if bool(row["indisunique"]) != unique:
        expected = "unique" if unique else "non-unique"
        raise PreflightFailure(f"{schema}.{index_name}: index is not {expected}")
    if not bool(row["indisvalid"]):
        raise PreflightFailure(f"{schema}.{index_name}: index is invalid")
    if bool(row["has_predicate"]):
        raise PreflightFailure(f"{schema}.{index_name}: partial indexes are incompatible")
    if list(row["column_names"] or []) != expected_columns:
        raise PreflightFailure(f"{schema}.{index_name}: index columns are incompatible")
    return False


def _detect_unique_index_only_equivalents(bind, schema: str, table_oid: int) -> None:
    rows = bind.execute(
        sa.text(
            """
            SELECT idx.relname AS index_name,
                   i.indisunique,
                   i.indisvalid,
                   i.indpred IS NOT NULL AS has_predicate,
                   COALESCE(array_agg(a.attname ORDER BY keys.ordinality)
                       FILTER (WHERE a.attname IS NOT NULL), ARRAY[]::name[]) AS column_names
            FROM pg_index i
            JOIN pg_class idx ON idx.oid = i.indexrelid
            LEFT JOIN LATERAL unnest(i.indkey) WITH ORDINALITY AS keys(attnum, ordinality)
                ON true
            LEFT JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = keys.attnum
            WHERE i.indrelid = :table_oid
              AND NOT EXISTS (SELECT 1 FROM pg_constraint c WHERE c.conindid = i.indexrelid)
            GROUP BY idx.relname, i.indisunique, i.indisvalid, i.indpred
            """
        ),
        {"table_oid": table_oid},
    ).mappings()
    for row in rows:
        if bool(row["indisunique"]) and list(row["column_names"] or []) == ["retailer_id", "sku_id"]:
            raise PreflightFailure(
                f"{schema}.{row['index_name']}: unique-index-only retailer_prices equivalent "
                "is not a constraint"
            )


def _preflight_retailer_prices(bind, schema: str, q: QuotedNames) -> RetailerPricesPlan:
    table_oid = _regclass_oid(bind, _qualified_name(q, "retailer_prices"))
    if table_oid is None:
        raise PreflightFailure(f"{schema}.{RETAILER_PRICES}: table is missing")

    _validate_retailer_price_columns(bind, schema, table_oid)
    if _has_duplicate_retailer_prices(bind, q):
        raise PreflightFailure(f"{schema}.{RETAILER_PRICES}: duplicate (retailer_id, sku_id) rows")
    if _has_price_violations(bind, q):
        raise PreflightFailure(f"{schema}.{RETAILER_PRICES}: price check violations exist")
    _detect_unique_index_only_equivalents(bind, schema, table_oid)

    plan = RetailerPricesPlan()
    constraints = _constraint_rows(bind, table_oid)
    canonical_rows = [row for row in constraints if row["conname"] == UQ_RETAILER_PRICES]
    if len(canonical_rows) > 1:
        raise PreflightFailure(f"{schema}.{UQ_RETAILER_PRICES}: duplicate canonical constraints")
    if canonical_rows:
        if not _is_equivalent_unique_constraint(canonical_rows[0]):
            raise PreflightFailure(
                f"{schema}.{UQ_RETAILER_PRICES}: canonical name is incompatible"
            )
    else:
        if _relation_kind(bind, schema, UQ_RETAILER_PRICES) is not None:
            raise PreflightFailure(
                f"{schema}.{UQ_RETAILER_PRICES}: canonical name is occupied by a non-constraint object"
            )
        equivalent_constraints = [
            row
            for row in constraints
            if row["conname"] != UQ_RETAILER_PRICES and _is_equivalent_unique_constraint(row)
        ]
        if len(equivalent_constraints) > 1:
            raise PreflightFailure(
                f"{schema}.{RETAILER_PRICES}: ambiguous equivalent unique constraints"
            )
        if len(equivalent_constraints) == 1:
            if not _canonical_name_is_free(bind, schema, table_oid):
                raise PreflightFailure(
                    f"{schema}.{UQ_RETAILER_PRICES}: canonical name is not free for rename"
                )
            plan.unique_action = "rename"
            plan.legacy_constraint_name = equivalent_constraints[0]["conname"]
        else:
            plan.unique_action = "add"

    check_rows = [row for row in constraints if row["conname"] == CK_RETAILER_PRICES]
    if len(check_rows) > 1:
        raise PreflightFailure(f"{schema}.{CK_RETAILER_PRICES}: duplicate check constraints")
    if check_rows:
        if not _check_constraint_is_canonical(check_rows[0]):
            raise PreflightFailure(f"{schema}.{CK_RETAILER_PRICES}: check constraint is incompatible")
    else:
        plan.add_check_constraint = True

    if _validate_or_plan_index(
        bind,
        schema,
        table_oid,
        RETAILER_PRICES,
        IX_RETAILER_PRICES_RETAILER,
        ["retailer_id"],
        unique=False,
    ):
        plan.create_indexes.append(IX_RETAILER_PRICES_RETAILER)
    if _validate_or_plan_index(
        bind,
        schema,
        table_oid,
        RETAILER_PRICES,
        IX_RETAILER_PRICES_SKU,
        ["sku_id"],
        unique=False,
    ):
        plan.create_indexes.append(IX_RETAILER_PRICES_SKU)

    return plan


def _validate_mv_columns(bind, schema: str, mv_oid: int) -> None:
    columns = _columns_for_relation(bind, mv_oid)
    violations: list[str] = []
    for column_name, expected_type in MV_SALES_DAILY_COLUMNS.items():
        column = columns.get(column_name)
        if column is None:
            violations.append(f"missing column {column_name}")
            continue
        if _normalize_type(column["formatted_type"]) != _normalize_type(expected_type):
            violations.append(
                f"column {column_name} has type {column['formatted_type']}, expected {expected_type}"
            )
    if violations:
        raise PreflightFailure(f"{schema}.{MV_SALES_DAILY}: " + "; ".join(violations))


def _preflight_reporting(bind, schema: str, q: QuotedNames) -> ReportingPlan:
    if _regclass_oid(bind, _qualified_name(q, "ledger_entries")) is None:
        raise PreflightFailure(f"{schema}.{LEDGER_ENTRIES}: table is missing")

    if not bool(_scalar(bind, "SELECT 1 FROM pg_roles WHERE rolname = :role", {"role": REPORTING_ROLE})):
        raise PreflightFailure(f"{schema}: reporting_role is missing")

    plan = ReportingPlan()
    mv_kind = _relation_kind(bind, schema, MV_SALES_DAILY)
    if mv_kind is None:
        plan.create_mv_sales_daily = True
        rpt_kind = _relation_kind(bind, schema, RPT_SALES_DAILY)
        if rpt_kind is not None:
            if rpt_kind != "v":
                raise PreflightFailure(
                    f"{schema}.{RPT_SALES_DAILY}: expected legacy view, found {_label_relkind(rpt_kind)}"
                )
            plan.drop_rpt_sales_daily = True
    elif mv_kind != "m":
        raise PreflightFailure(
            f"{schema}.{MV_SALES_DAILY}: expected materialized view, found {_label_relkind(mv_kind)}"
        )
    else:
        mv_oid = _regclass_oid(bind, _qualified_name(q, "mv_sales_daily"))
        if mv_oid is None:
            raise PreflightFailure(f"{schema}.{MV_SALES_DAILY}: materialized view is unresolved")
        _validate_mv_columns(bind, schema, mv_oid)

    mv_oid_for_index = _regclass_oid(bind, _qualified_name(q, "mv_sales_daily"))
    if mv_oid_for_index is None:
        existing_idx = _index_rows(bind, schema, IX_MV_SALES_DAILY)
        if existing_idx:
            raise PreflightFailure(
                f"{schema}.{IX_MV_SALES_DAILY}: index exists without canonical materialized view"
            )
        plan.create_unique_index = True
    elif _validate_or_plan_index(
        bind,
        schema,
        mv_oid_for_index,
        MV_SALES_DAILY,
        IX_MV_SALES_DAILY,
        ["transaction_date", "reporting_currency_code"],
        unique=True,
    ):
        plan.create_unique_index = True

    return plan


def _preflight(bind) -> list[TenantPlan]:
    rows = _registered_tenants(bind)
    _validate_registry_rows(bind, rows)

    plans: list[TenantPlan] = []
    failures: list[str] = []
    for row in rows:
        schema = row["tenant_schema"]
        try:
            q = _quoted_names(bind, schema)
            retailer_prices_plan = _preflight_retailer_prices(bind, schema, q)
            reporting_plan = _preflight_reporting(bind, schema, q)
            plans.append(
                TenantPlan(
                    schema=schema,
                    quoted=q,
                    retailer_prices=retailer_prices_plan,
                    reporting=reporting_plan,
                )
            )
        except PreflightFailure as exc:
            failures.append(str(exc))

    if failures:
        raise PreflightFailure("DC-2M2 preflight failed: " + "; ".join(failures))

    return plans


def _create_mv_sales_daily_sql(q: QuotedNames) -> str:
    return f"""
    CREATE MATERIALIZED VIEW {_qualified_name(q, 'mv_sales_daily')} AS
    SELECT
        transaction_date::DATE                          AS transaction_date,
        'USD'::CHAR(3)                                  AS reporting_currency_code,
        ABS(SUM(amount))::NUMERIC(20, 4)                AS daily_revenue,
        COUNT(*)::INTEGER                               AS transaction_count
    FROM {_qualified_name(q, 'ledger_entries')}
    WHERE account_type = 'revenue'
      AND is_deleted = false
    GROUP BY transaction_date::DATE
    ORDER BY transaction_date::DATE
    WITH DATA
    """


def _execute_retailer_prices_plan(bind, tenant_plan: TenantPlan) -> None:
    q = tenant_plan.quoted
    retailer_plan = tenant_plan.retailer_prices
    if retailer_plan.unique_action == "rename":
        if retailer_plan.legacy_constraint_name is None:
            raise RuntimeError(f"{tenant_plan.schema}: missing legacy constraint rename target")
        legacy_constraint = _quote_ident(bind, retailer_plan.legacy_constraint_name)
        bind.execute(
            sa.text(
                f"""
                ALTER TABLE {_qualified_name(q, 'retailer_prices')}
                RENAME CONSTRAINT {legacy_constraint} TO {q.uq_retailer_prices}
                """
            )
        )
    elif retailer_plan.unique_action == "add":
        bind.execute(
            sa.text(
                f"""
                ALTER TABLE {_qualified_name(q, 'retailer_prices')}
                ADD CONSTRAINT {q.uq_retailer_prices} UNIQUE (retailer_id, sku_id)
                """
            )
        )

    if retailer_plan.add_check_constraint:
        bind.execute(
            sa.text(
                f"""
                ALTER TABLE {_qualified_name(q, 'retailer_prices')}
                ADD CONSTRAINT {q.ck_retailer_prices} CHECK (price > 0)
                """
            )
        )

    if IX_RETAILER_PRICES_RETAILER in retailer_plan.create_indexes:
        bind.execute(
            sa.text(
                f"""
                CREATE INDEX {q.ix_retailer_prices_retailer}
                ON {_qualified_name(q, 'retailer_prices')} (retailer_id)
                """
            )
        )
    if IX_RETAILER_PRICES_SKU in retailer_plan.create_indexes:
        bind.execute(
            sa.text(
                f"""
                CREATE INDEX {q.ix_retailer_prices_sku}
                ON {_qualified_name(q, 'retailer_prices')} (sku_id)
                """
            )
        )


def _execute_reporting_plan(bind, tenant_plan: TenantPlan) -> None:
    q = tenant_plan.quoted
    reporting_plan = tenant_plan.reporting
    bind.execute(sa.text(f"GRANT USAGE ON SCHEMA {q.schema} TO {q.reporting_role}"))
    if reporting_plan.drop_rpt_sales_daily:
        bind.execute(sa.text(f"DROP VIEW {_qualified_name(q, 'rpt_sales_daily')}"))
    if reporting_plan.create_mv_sales_daily:
        bind.execute(sa.text(_create_mv_sales_daily_sql(q)))
    if reporting_plan.create_unique_index:
        bind.execute(
            sa.text(
                f"""
                CREATE UNIQUE INDEX {q.ix_mv_sales_daily}
                ON {_qualified_name(q, 'mv_sales_daily')} (transaction_date, reporting_currency_code)
                """
            )
        )
    bind.execute(
        sa.text(f"GRANT SELECT ON {_qualified_name(q, 'mv_sales_daily')} TO {q.reporting_role}")
    )


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": ADVISORY_LOCK_KEY})
    bind.execute(sa.text(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'"))
    bind.execute(sa.text(f"SET LOCAL statement_timeout = '{STATEMENT_TIMEOUT}'"))

    plans = _preflight(bind)
    print(f"DC-2M2 preflight OK: {len(plans)} registered tenant schema(s)")
    for plan in plans:
        print(f"DC-2M2 plan {plan.schema}: {', '.join(plan.actions())}")

    for plan in plans:
        bind.execute(sa.text(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'"))
        bind.execute(sa.text(f"SET LOCAL statement_timeout = '{STATEMENT_TIMEOUT}'"))
        _execute_retailer_prices_plan(bind, plan)
        _execute_reporting_plan(bind, plan)


def downgrade() -> None:
    raise RuntimeError(
        "031_legacy_tenant_reconciliation is forward-only. Roll back the application "
        "version and restore from a verified pre-migration database backup/snapshot."
    )
