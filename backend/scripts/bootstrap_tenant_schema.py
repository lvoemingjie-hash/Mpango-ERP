#!/usr/bin/env python3
"""
Bootstrap a tenant schema with all required tables (idempotent).

This script creates the tenant schema and all business tables using raw DDL.
It is called by docker-entrypoint.sh before Uvicorn starts to ensure the
default tenant schema (used by MockAuthStrategy in MPANGO_ENV=test) is ready.

Alembic migrations cannot be used for this purpose because the project uses
a single shared alembic_version table in public schema — running
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
            "('draft','confirmed','partially_paid','paid','fulfilled','cancelled','voided'); "
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
        ]
        for ddl in tables:
            await db.execute(text(ddl))

        # Indexes for payments table (idempotent via CREATE INDEX IF NOT EXISTS)
        payment_indexes = [
            f'CREATE INDEX IF NOT EXISTS ix_payments_order_id ON "{ts}".payments (order_id)',
            f'CREATE UNIQUE INDEX IF NOT EXISTS uq_payments_transaction_id '
            f'ON "{ts}".payments (transaction_id) '
            f"WHERE transaction_id IS NOT NULL",
        ]
        for idx_ddl in payment_indexes:
            await db.execute(text(idx_ddl))

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

        await db.commit()

    await engine.dispose()
    print(f"[bootstrap] Tenant schema '{ts}' ready ({len(tables)} tables).")


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
