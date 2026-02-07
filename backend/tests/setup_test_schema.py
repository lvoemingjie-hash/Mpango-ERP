"""
Setup test tenant schema for S5-A order state machine tests.

Creates t_test schema and runs migrations to create orders table.
"""
import asyncio
import sys
import os
from pathlib import Path

# Set test environment variables before importing
os.environ.setdefault("DATABASE_URL", "postgresql://mpango:MpangoDBV0.1.2@127.0.0.1:5432/mpango_erp")
os.environ.setdefault("SECRET_KEY", "kJ8mN2pQ5rT9vX3zA6bC4dF7gH1jK0lM")  # Strong key for testing
os.environ.setdefault("MPANGO_ENV", "test")

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from database.session import async_engine


async def setup_test_schema():
    """Create t_test schema and run migrations."""
    async with async_engine.begin() as conn:
        # Create t_test schema if it doesn't exist
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS t_test"))
        print("✓ Created t_test schema")
        
        # Set search path to t_test
        await conn.execute(text("SET search_path TO t_test, public"))
        
        # Create order_status enum (in t_test schema, but without schema prefix in type name)
        await conn.execute(text("""
            DO $$ BEGIN
                CREATE TYPE order_status AS ENUM (
                    'draft', 
                    'confirmed', 
                    'partially_paid', 
                    'paid', 
                    'fulfilled', 
                    'cancelled', 
                    'voided'
                );
            EXCEPTION
                WHEN duplicate_object THEN null;
            END $$;
        """))
        print("✓ Created order_status enum")
        
        # Create orders table (enum type will be found in search_path)
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS t_test.orders (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                wholesaler_id UUID NOT NULL,
                retailer_id UUID NOT NULL,
                status order_status NOT NULL DEFAULT 'draft',
                total_amount NUMERIC(12, 2) NOT NULL DEFAULT 0.00,
                notes TEXT,
                is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
                deleted_at TIMESTAMP WITH TIME ZONE,
                created_by UUID,
                updated_by UUID,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
        print("✓ Created orders table")
        
        # Create indexes
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_orders_wholesaler_id ON t_test.orders(wholesaler_id)
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_orders_retailer_id ON t_test.orders(retailer_id)
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_orders_status ON t_test.orders(status)
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_orders_created_at ON t_test.orders(created_at)
        """))
        print("✓ Created indexes")
        
        # Create order_items table
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS t_test.order_items (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                order_id UUID NOT NULL REFERENCES t_test.orders(id) ON DELETE CASCADE,
                product_name TEXT NOT NULL,
                sku_code VARCHAR(64) NOT NULL,
                quantity INTEGER NOT NULL,
                unit_price NUMERIC(12, 2) NOT NULL,
                subtotal NUMERIC(12, 2) NOT NULL,
                is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
                deleted_at TIMESTAMP WITH TIME ZONE,
                created_by UUID,
                updated_by UUID,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
        print("✓ Created order_items table")
        
        # Create order_items indexes
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_order_items_order_id ON t_test.order_items(order_id)
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_order_items_sku_code ON t_test.order_items(sku_code)
        """))
        print("✓ Created order_items indexes")
        
        # Create account_type enum for ledger
        await conn.execute(text("""
            DO $$ BEGIN
                CREATE TYPE account_type AS ENUM ('receivable', 'revenue', 'cash', 'liability');
            EXCEPTION
                WHEN duplicate_object THEN null;
            END $$;
        """))
        print("✓ Created account_type enum")
        
        # Create ledger_entries table (S5.5: Added entry_version and hash columns)
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS t_test.ledger_entries (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                transaction_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
                account_type account_type NOT NULL,
                amount NUMERIC(20, 4) NOT NULL,
                reference_type VARCHAR(50) NOT NULL,
                reference_id UUID NOT NULL,
                description TEXT,
                entry_version INTEGER NOT NULL DEFAULT 1,
                hash VARCHAR(64),
                is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
                deleted_at TIMESTAMP WITH TIME ZONE,
                created_by UUID,
                updated_by UUID,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
        print("✓ Created ledger_entries table")
        
        # S5.5: Create trigger function for ledger immutability
        await conn.execute(text("""
            CREATE OR REPLACE FUNCTION public.prevent_ledger_modification()
            RETURNS TRIGGER AS $$
            BEGIN
                IF TG_OP = 'UPDATE' THEN
                    RAISE EXCEPTION 'Ledger entries are immutable. UPDATE operations are not allowed.'
                        USING ERRCODE = 'integrity_constraint_violation',
                              HINT = 'Ledger entries cannot be modified after creation. Create a correction entry instead.';
                END IF;
                
                IF TG_OP = 'DELETE' THEN
                    RAISE EXCEPTION 'Ledger entries are immutable. DELETE operations are not allowed.'
                        USING ERRCODE = 'integrity_constraint_violation',
                              HINT = 'Ledger entries cannot be deleted. Create a reversal entry instead.';
                END IF;
                
                RETURN OLD;
            END;
            $$ LANGUAGE plpgsql;
        """))
        print("✓ Created prevent_ledger_modification() trigger function")
        
        # S5.5: Attach trigger to ledger_entries table
        await conn.execute(text("""
            DROP TRIGGER IF EXISTS prevent_ledger_modification_trigger ON t_test.ledger_entries
        """))
        await conn.execute(text("""
            CREATE TRIGGER prevent_ledger_modification_trigger
            BEFORE UPDATE OR DELETE ON t_test.ledger_entries
            FOR EACH ROW
            EXECUTE FUNCTION public.prevent_ledger_modification()
        """))
        print("✓ Attached immutability trigger to ledger_entries")
        
        # Create ledger_entries indexes
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_ledger_entries_reference ON t_test.ledger_entries(reference_type, reference_id)
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_ledger_entries_account_type ON t_test.ledger_entries(account_type)
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_ledger_entries_transaction_date ON t_test.ledger_entries(transaction_date)
        """))
        print("✓ Created ledger_entries indexes")
        
    print("\n✅ Test schema setup complete!")
    print("   Schema: t_test")
    print("   Tables: orders, order_items, ledger_entries")


if __name__ == "__main__":
    asyncio.run(setup_test_schema())
