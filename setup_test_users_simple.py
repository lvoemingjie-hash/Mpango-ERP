#!/usr/bin/env python3
"""
Setup test users for B6 verification using pre-hashed passwords.
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "backend"))

from database.session import AsyncSessionLocal
from sqlalchemy import text

async def setup_test_user(tenant_schema: str, email: str, password_hash: str, name: str):
    """Create a test user in the specified tenant schema."""
    async with AsyncSessionLocal() as db:
        print(f"Setting up user {email} in schema: {tenant_schema}")

        # Set search path to tenant schema
        await db.execute(text(f'SET LOCAL search_path TO "{tenant_schema}", public'))

        # Create user with pre-hashed password
        await db.execute(text("""
            INSERT INTO users (email, password_hash, full_name, is_active)
            VALUES (:email, :password_hash, :full_name, true)
            ON CONFLICT (email) DO NOTHING
        """), {
            "email": email,
            "password_hash": password_hash,
            "full_name": name
        })

        # Create admin role
        await db.execute(text("""
            INSERT INTO roles (name, description)
            VALUES ('admin', 'Administrator with full access')
            ON CONFLICT (name) DO NOTHING
        """))

        # Create permissions
        permissions = [
            ("users:read", "Read users"),
            ("users:create", "Create users"),
            ("orders:read", "Read orders"),
            ("orders:create", "Create orders"),
            ("payments:read", "Read payments"),
            ("payments:create", "Create payments"),
        ]

        for code, description in permissions:
            await db.execute(text("""
                INSERT INTO permissions (code, description)
                VALUES (:code, :description)
                ON CONFLICT (code) DO NOTHING
            """), {"code": code, "description": description})

        # Get user and role IDs
        user_result = await db.execute(text("""
            SELECT id FROM users WHERE email = :email
        """), {"email": email})
        user_id = user_result.scalar()

        role_result = await db.execute(text("""
            SELECT id FROM roles WHERE name = 'admin'
        """))
        role_id = role_result.scalar()

        # Assign role to user
        await db.execute(text("""
            INSERT INTO user_roles (user_id, role_id)
            VALUES (:user_id, :role_id)
            ON CONFLICT (user_id, role_id) DO NOTHING
        """), {"user_id": user_id, "role_id": role_id})

        # Assign all permissions to admin role
        perm_result = await db.execute(text("SELECT id FROM permissions"))
        permissions_ids = [row[0] for row in perm_result.fetchall()]

        for perm_id in permissions_ids:
            await db.execute(text("""
                INSERT INTO role_permissions (role_id, permission_id)
                VALUES (:role_id, :permission_id)
                ON CONFLICT (role_id, permission_id) DO NOTHING
            """), {"role_id": role_id, "permission_id": perm_id})

        await db.commit()
        print(f"✓ User {email} setup complete in schema: {tenant_schema}")

async def main():
    """Setup test users for verification."""

    # Pre-hashed passwords (bcrypt hashes for "testpassword" and "TestPass123")
    # These were generated with: python -c "from passlib.context import CryptContext; ctx = CryptContext(schemes=['bcrypt']); print(ctx.hash('testpassword'))"

    # Setup user for TEST001 tenant
    await setup_test_user(
        "t_550e8400e29b41d4a716446655440000",  # TEST001
        "admin@test.com",
        "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewdBPj3bp.gSUadG",  # "testpassword"
        "Test Admin A"
    )

    # Setup user for TEST_B tenant
    await setup_test_user(
        "t_f32148fea3b74353b1c9bb095a1a0e58",   # TEST_B
        "admin@tenant-b.com",
        "$2b$12$EixZxYyqSxjzpQByAHc1Puiuwr9OpOFndUKyp4/LGSLMZBEyPoeS6",  # "TestPass123"
        "Test Admin B"
    )

    print("\n✓ All test users setup complete!")

if __name__ == "__main__":
    asyncio.run(main())
