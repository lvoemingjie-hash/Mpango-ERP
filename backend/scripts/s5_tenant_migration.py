"""S5 Tenant Migration Script - Apply ledger_entries to all tenant schemas.

This script directly applies the S5-B DDL (ledger_entries table, account_type enum,
indexes) to all tenant schemas that are missing the table.

Safe to run multiple times (idempotent).
"""
import asyncio
import os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# S8-SEC: Never hardcode credentials — read from environment
DB_URL = os.environ.get("DATABASE_URL", "").replace("postgresql://", "postgresql+asyncpg://")
if not DB_URL:
    raise RuntimeError("DATABASE_URL environment variable must be set")


async def apply_tenant_migration():
    engine = create_async_engine(DB_URL)

    async with engine.begin() as conn:
        # Find all tenant schemas
        result = await conn.execute(text(
            "SELECT schema_name FROM information_schema.schemata "
            "WHERE schema_name LIKE 't_%' ORDER BY schema_name"
        ))
        schemas = [r[0] for r in result.fetchall()]
        print(f"Found {len(schemas)} tenant schemas: {schemas}")

        for schema in schemas:
            # Check if ledger_entries already exists
            result = await conn.execute(text(
                "SELECT table_name FROM information_schema.tables "
                f"WHERE table_schema = :schema AND table_name = 'ledger_entries'"
            ), {"schema": schema})
            if result.fetchone():
                print(f"  ✅ {schema}.ledger_entries already exists — skipping")
                continue

            print(f"  🔧 Applying S5-B migration to {schema}...")

            # Set search_path
            await conn.execute(text(f'SET LOCAL search_path TO "{schema}", public'))

            # Create account_type enum (idempotent)
            await conn.execute(text("""
                DO $$ BEGIN
                    CREATE TYPE account_type AS ENUM ('receivable', 'revenue', 'cash', 'liability');
                EXCEPTION
                    WHEN duplicate_object THEN null;
                END $$;
            """))

            # Create ledger_entries table
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS ledger_entries (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    transaction_date TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    account_type account_type NOT NULL,
                    amount NUMERIC(20, 4) NOT NULL,
                    reference_type VARCHAR(50) NOT NULL,
                    reference_id UUID NOT NULL,
                    description TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    is_deleted BOOLEAN NOT NULL DEFAULT false,
                    deleted_at TIMESTAMPTZ,
                    created_by UUID,
                    updated_by UUID
                )
            """))

            # Create indexes
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_ledger_entries_reference "
                "ON ledger_entries (reference_type, reference_id)"
            ))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_ledger_entries_account_type "
                "ON ledger_entries (account_type)"
            ))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_ledger_entries_transaction_date "
                "ON ledger_entries (transaction_date)"
            ))

            print(f"  ✅ {schema}.ledger_entries CREATED with indexes")

            # Reset search_path
            await conn.execute(text("SET LOCAL search_path TO public"))

    await engine.dispose()
    print("\n✅ All tenant schemas migrated")


asyncio.run(apply_tenant_migration())
