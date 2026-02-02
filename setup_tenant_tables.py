#!/usr/bin/env python3
"""
Setup tenant tables for B6 verification.
Manually creates tables in tenant schemas.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "backend"))

from database.session import AsyncSessionLocal
from sqlalchemy import text

async def setup_tenant_tables(tenant_schema: str):
    """Create tables in the specified tenant schema."""
    async with AsyncSessionLocal() as db:
        print(f"Setting up tables in schema: {tenant_schema}")
        
        # Set search path to tenant schema
        await db.execute(text(f'SET LOCAL search_path TO "{tenant_schema}", public'))
        
        # Create users table
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS users (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                email VARCHAR(255) NOT NULL UNIQUE,
                password_hash VARCHAR(255) NOT NULL,
                full_name TEXT,
                is_active BOOLEAN NOT NULL DEFAULT true,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
                is_deleted BOOLEAN DEFAULT false,
                deleted_at TIMESTAMP WITH TIME ZONE,
                created_by UUID,
                updated_by UUID
            )
        """))
        
        # Create roles table
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS roles (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name VARCHAR(100) NOT NULL UNIQUE,
                description TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
                is_deleted BOOLEAN DEFAULT false,
                deleted_at TIMESTAMP WITH TIME ZONE,
                created_by UUID,
                updated_by UUID
            )
        """))
        
        # Create permissions table
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS permissions (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                code VARCHAR(100) NOT NULL UNIQUE,
                description TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
                is_deleted BOOLEAN DEFAULT false,
                deleted_at TIMESTAMP WITH TIME ZONE,
                created_by UUID,
                updated_by UUID
            )
        """))
        
        # Create user_roles M2M table
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS user_roles (
                user_id UUID NOT NULL,
                role_id UUID NOT NULL,
                PRIMARY KEY (user_id, role_id),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE
            )
        """))
        
        # Create role_permissions M2M table
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS role_permissions (
                role_id UUID NOT NULL,
                permission_id UUID NOT NULL,
                PRIMARY KEY (role_id, permission_id),
                FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE,
                FOREIGN KEY (permission_id) REFERENCES permissions(id) ON DELETE CASCADE
            )
        """))
        
        # Create order_status enum if not exists
        await db.execute(text("""
            DO $$ BEGIN
                CREATE TYPE order_status AS ENUM ('pending', 'confirmed', 'shipped', 'cancelled');
            EXCEPTION
                WHEN duplicate_object THEN null;
            END $$;
        """))
        
        # Create orders table
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS orders (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                retailer_id UUID NOT NULL,
                status order_status NOT NULL,
                total_amount NUMERIC(12, 2) NOT NULL,
                notes TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
                is_deleted BOOLEAN DEFAULT false,
                deleted_at TIMESTAMP WITH TIME ZONE,
                created_by UUID,
                updated_by UUID
            )
        """))
        
        # Create payments table (from B5 migration)
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS payments (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                order_id UUID NOT NULL,
                retailer_id UUID NOT NULL,
                transaction_id VARCHAR(255),
                amount NUMERIC(12, 2) NOT NULL,
                method VARCHAR(50) NOT NULL,
                status VARCHAR(50) NOT NULL DEFAULT 'pending',
                created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
                created_by UUID,
                CONSTRAINT uq_payments_transaction_id UNIQUE (transaction_id)
            )
        """))
        
        await db.commit()
        print(f"✓ Tables created in schema: {tenant_schema}")

async def main():
    """Setup tables for all tenant schemas."""
    tenant_schemas = [
        "t_550e8400e29b41d4a716446655440000",  # TEST001
        "t_f32148fea3b74353b1c9bb095a1a0e58"   # TEST_B
    ]
    
    for schema in tenant_schemas:
        await setup_tenant_tables(schema)
    
    print("\n✓ All tenant schemas setup complete!")

if __name__ == "__main__":
    asyncio.run(main())