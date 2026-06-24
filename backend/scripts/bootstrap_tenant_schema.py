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
import sys
from pathlib import Path


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


def _normalize_sql(sql: str) -> str:
    return " ".join(sql.lower().split())


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



async def _reconcile_payments(db, ts: str) -> None:
    """Idempotent reconciliation of payments table to match 021 contract.

    Order matters: columns must exist before indexes that reference them.
    1. Add retailer_id (nullable) if missing
    2. Backfill from orders.retailer_id
    3. Fail fast if orphan payments exist (no matching order)
    4. Set retailer_id NOT NULL
    5. Add transaction_id if missing
    6. Create ix_payments_order_id if missing
    7. Create uq_payments_transaction_id partial unique if missing
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
    """Structural validation and index reconciliation for retailer_prices.

    Mirrors Alembic migration 017 contract exactly.  Two-phase approach:

    Phase 1 - if the table does not exist at all, return (the CREATE TABLE IF
    NOT EXISTS in the tables list above will create it fresh with full DDL).

    Phase 2 - if the table *does* exist, validate every column, constraint,
    and index against the migration 017 contract.  Any structural mismatch
    triggers an immediate RuntimeError with a precise description of what is
    wrong.  No silent patching, no guessing.
    """
    from sqlalchemy import text

    # Phase 1: missing table -> nothing to reconcile (CREATE TABLE handles it)
    if not await _table_exists(db, ts, "retailer_prices"):
        return

    # Phase 2: table exists - full structural contract check
    violations: list[str] = []

    # --- Required NOT NULL columns ---
    required_not_null = {
        "retailer_id": "UUID",
        "sku_id": "UUID",
        "price": "NUMERIC(12,2)",
        "created_at": "TIMESTAMPTZ",
        "updated_at": "TIMESTAMPTZ",
        "is_deleted": "BOOLEAN",
    }

    for col_name, expected_type in required_not_null.items():
        if not await _column_exists(db, ts, "retailer_prices", col_name):
            violations.append(f"missing column '{col_name}'")
            continue
        if await _column_is_nullable(db, ts, "retailer_prices", col_name):
            violations.append(f"column '{col_name}' is nullable, expected NOT NULL")

    # --- Unique constraint: uq_retailer_prices_retailer_sku ---
    # Check via pg_constraint (covers both table constraints and unique indexes)
    uq_result = await db.execute(text(
        "SELECT 1 FROM pg_constraint "
        "WHERE connamespace = (SELECT oid FROM pg_namespace WHERE nspname = :schema) "
        "AND conname = 'uq_retailer_prices_retailer_sku' "
        "AND contype = 'u'"
    ), {"schema": ts})
    uq_constraint_exists = uq_result.first() is not None
    # Also accept if a unique *index* with the same name provides the guarantee
    uq_idx_result = await db.execute(text(
        "SELECT 1 FROM pg_indexes "
        "WHERE schemaname = :schema AND indexname = 'uq_retailer_prices_retailer_sku' "
        "AND indexdef LIKE '%UNIQUE%'"
    ), {"schema": ts})
    uq_index_exists = uq_idx_result.first() is not None
    if not uq_constraint_exists and not uq_index_exists:
        violations.append(
            "missing unique constraint 'uq_retailer_prices_retailer_sku' "
            "on (retailer_id, sku_id)"
        )

    # --- Check constraint: ck_retailer_prices_positive_price ---
    ck_result = await db.execute(text(
        "SELECT 1 FROM pg_constraint "
        "WHERE connamespace = (SELECT oid FROM pg_namespace WHERE nspname = :schema) "
        "AND conname = 'ck_retailer_prices_positive_price' "
        "AND contype = 'c'"
    ), {"schema": ts})
    if ck_result.first() is None:
        violations.append(
            "missing check constraint 'ck_retailer_prices_positive_price'"
        )

    # --- Indexes ---
    await _ensure_index(
        db,
        ts,
        "ix_retailer_prices_retailer_id",
        f'CREATE INDEX IF NOT EXISTS ix_retailer_prices_retailer_id '
        f'ON "{ts}".retailer_prices (retailer_id)',
        ("retailer_prices", "(retailer_id)"),
    )

    await _ensure_index(
        db,
        ts,
        "ix_retailer_prices_sku_id",
        f'CREATE INDEX IF NOT EXISTS ix_retailer_prices_sku_id '
        f'ON "{ts}".retailer_prices (sku_id)',
        ("retailer_prices", "(sku_id)"),
    )

    # --- Fail fast if any violations ---
    if violations:
        violation_list = "\n  - ".join(violations)
        raise RuntimeError(
            f"Bootstrap reconcile: {ts}.retailer_prices exists but does NOT match "
            f"migration 017 contract. Violations:\n  - {violation_list}\n"
            "Manual schema correction is required before continuing."
        )

    print(f"[reconcile] {ts}.retailer_prices: contract validated, indexes ensured")


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
    # Drop the old standard view first (migration 013 did this)
    await db.execute(text(
        f'DROP VIEW IF EXISTS "{ts}".rpt_sales_daily'
    ))
    # Create materialized view if it does not already exist
    mv_exists = await db.execute(text(
        "SELECT 1 FROM pg_matviews WHERE schemaname = :schema AND matviewname = 'mv_sales_daily'"
    ), {"schema": ts})
    if mv_exists.first() is None:
        await db.execute(text(f"""
            CREATE MATERIALIZED VIEW "{ts}".mv_sales_daily AS
            SELECT
                transaction_date::DATE                          AS transaction_date,
                'USD'::CHAR(3)                                  AS reporting_currency_code,
                ABS(SUM(amount))::NUMERIC(20, 4)                AS daily_revenue,
                COUNT(*)::INTEGER                               AS transaction_count
            FROM "{ts}".ledger_entries
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
        "idx_mv_sales_daily_u1",
        f'CREATE UNIQUE INDEX idx_mv_sales_daily_u1 '
        f'ON "{ts}".mv_sales_daily (transaction_date, reporting_currency_code)',
        ("unique index", "mv_sales_daily", "(transaction_date, reporting_currency_code)"),
    )
    print(f"[reconcile] {ts}: ensured idx_mv_sales_daily_u1")

    await db.execute(text(
        f'GRANT SELECT ON "{ts}".mv_sales_daily TO reporting_role'
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
        await db.execute(text("ALTER TYPE order_status ADD VALUE IF NOT EXISTS 'returned'"))

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
            "created_by UUID, updated_by UUID)",

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

        # --- retailer_prices: reconcile indexes (mirrors 017) ---
        await _reconcile_retailer_prices(db, ts)

        # --- reporting views / matviews (mirrors 012 + 013) ---
        await _reconcile_reporting(db, ts)

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
