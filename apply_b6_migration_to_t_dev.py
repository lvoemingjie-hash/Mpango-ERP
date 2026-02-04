#!/usr/bin/env python3
"""
Apply B6 migration to t_dev tenant schema.

This script manually applies the idempotency_key column and index to the t_dev schema.
"""

import asyncio
import asyncpg
import os

async def apply_migration():
    # Connect to database
    conn = await asyncpg.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        user=os.getenv("POSTGRES_USER", "mpango"),
        password=os.getenv("POSTGRES_PASSWORD", "mpango_dev_pass"),
        database=os.getenv("POSTGRES_DB", "mpango_erp")
    )

    try:
        # Set search_path to t_dev
        await conn.execute('SET search_path TO t_dev, public')

        # Check if payments table exists
        table_exists = await conn.fetchval(
            """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 't_dev' AND table_name = 'payments'
            )
            """
        )

        if not table_exists:
            print("❌ Payments table does not exist in t_dev schema")
            return False

        print("✅ Payments table exists in t_dev schema")

        # Check if idempotency_key column exists
        column_exists = await conn.fetchval(
            """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 't_dev'
                AND table_name = 'payments'
                AND column_name = 'idempotency_key'
            )
            """
        )

        if not column_exists:
            print("Adding idempotency_key column...")
            await conn.execute(
                """
                ALTER TABLE t_dev.payments
                ADD COLUMN idempotency_key VARCHAR(64)
                """
            )
            print("✅ Added idempotency_key column")
        else:
            print("✅ idempotency_key column already exists")

        # Check if index exists
        index_exists = await conn.fetchval(
            """
            SELECT EXISTS (
                SELECT 1 FROM pg_indexes
                WHERE schemaname = 't_dev'
                AND indexname = 'uq_payments_idempotency_key'
            )
            """
        )

        if not index_exists:
            print("Creating unique index on idempotency_key...")
            await conn.execute(
                """
                CREATE UNIQUE INDEX uq_payments_idempotency_key
                ON t_dev.payments (idempotency_key)
                WHERE idempotency_key IS NOT NULL
                """
            )
            print("✅ Created unique index uq_payments_idempotency_key")
        else:
            print("✅ Index uq_payments_idempotency_key already exists")

        # Verify the changes
        columns = await conn.fetch(
            """
            SELECT column_name, data_type, character_maximum_length
            FROM information_schema.columns
            WHERE table_schema = 't_dev'
            AND table_name = 'payments'
            ORDER BY ordinal_position
            """
        )

        print("\n✅ B6 migration applied successfully to t_dev schema")
        print("\nPayments table columns:")
        for col in columns:
            print(f"  - {col['column_name']}: {col['data_type']}", end="")
            if col['character_maximum_length']:
                print(f"({col['character_maximum_length']})")
            else:
                print()

        return True

    finally:
        await conn.close()

if __name__ == "__main__":
    result = asyncio.run(apply_migration())
    exit(0 if result else 1)
