#!/usr/bin/env python3
"""
Simple script to create test tenants for B6 verification.
"""

import asyncio
import sys
import uuid
from pathlib import Path

# Add backend to path for imports
sys.path.insert(0, str(Path(__file__).parent / "backend"))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from database.session import AsyncSessionLocal
from models.wholesaler import Wholesaler
from models.user import User, Role, Permission
from core.security import hash_password


async def create_test_tenant(name: str, code: str, admin_email: str, admin_password: str):
    """Create a test tenant with admin user."""
    print(f"\nCreating tenant: {name} ({code})")
    
    async with AsyncSessionLocal() as db:
        # 1. Create wholesaler
        wholesaler = Wholesaler(name=name, code=code)
        db.add(wholesaler)
        await db.commit()
        await db.refresh(wholesaler)
        
        tenant_schema = wholesaler.get_tenant_schema()
        print(f"✓ Created wholesaler with schema: {tenant_schema}")
        
        # 2. Create tenant schema
        await db.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{tenant_schema}"'))
        await db.commit()
        print(f"✓ Created schema: {tenant_schema}")
        
        # 3. Set search path and create admin user
        await db.execute(text(f'SET LOCAL search_path TO "{tenant_schema}", public'))
        
        user = User(
            email=admin_email,
            hashed_password=hash_password(admin_password[:72]),  # Truncate to 72 bytes for bcrypt
            first_name="Admin",
            last_name="User",
            is_active=True,
            is_superuser=False
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        print(f"✓ Created admin user: {admin_email}")
        
        # 4. Create admin role
        admin_role = Role(name="admin", description="Administrator with full access")
        db.add(admin_role)
        await db.commit()
        await db.refresh(admin_role)
        
        # 5. Create permissions
        permissions_data = [
            ("users:read", "Read users"),
            ("users:create", "Create users"),
            ("orders:read", "Read orders"),
            ("orders:create", "Create orders"),
            ("payments:read", "Read payments"),
            ("payments:create", "Create payments"),
        ]
        
        for code, description in permissions_data:
            perm = Permission(code=code, description=description)
            db.add(perm)
        
        await db.commit()
        print(f"✓ Created permissions")
        
        # 6. Assign role to user and permissions to role
        await db.execute(
            text(f'INSERT INTO "{tenant_schema}".user_roles (user_id, role_id) VALUES (:user_id, :role_id)'),
            {"user_id": str(user.id), "role_id": str(admin_role.id)}
        )
        
        # Get all permissions and assign to admin role
        result = await db.execute(text(f'SELECT id FROM "{tenant_schema}".permissions'))
        permissions = result.fetchall()
        
        for (perm_id,) in permissions:
            await db.execute(
                text(f'INSERT INTO "{tenant_schema}".role_permissions (role_id, permission_id) VALUES (:role_id, :perm_id)'),
                {"role_id": str(admin_role.id), "perm_id": str(perm_id)}
            )
        
        await db.commit()
        print(f"✓ Assigned role and permissions")
        
        return wholesaler


async def main():
    """Create two test tenants."""
    print("Creating test tenants for B6 verification...")
    
    # Create Tenant A (use existing TEST001)
    print("Using existing TEST001 tenant as Tenant A")
    
    # Create Tenant B
    tenant_b = await create_test_tenant(
        "Test Tenant B", 
        "TEST_B", 
        "admin@tenant-b.com", 
        "TestPass123"  # Shorter password
    )
    
    print("\n" + "="*60)
    print("✓ Test tenants ready for verification!")
    print("="*60)
    print(f"Tenant A: TEST001 (existing)")
    print(f"  Login: admin@test.com / testpassword")
    print(f"Tenant B: {tenant_b.name} (schema: {tenant_b.get_tenant_schema()})")
    print(f"  Login: admin@tenant-b.com / TestPass123")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())