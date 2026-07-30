#!/usr/bin/env python3
"""
Bootstrap script to create the first tenant (wholesaler) and admin user.

Usage:
    python scripts/create_wholesaler.py \
        --name "Mpango Demo" \
        --code mpango_demo \
        --admin-email admin@mpango.com \
        --admin-password "ChangeMe123!@#"

This script:
1. Creates the tenant schema in the database
2. Creates the wholesaler record in public schema
3. Creates the admin user in the tenant schema
4. Assigns admin role with all permissions
"""

import asyncio
import argparse
import sys
import uuid
from pathlib import Path

# Add backend to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from database.session import get_tenant_db, AsyncSessionLocal
from models.wholesaler import Wholesaler
from models.user import User, Role, Permission
from models.associations import user_roles, role_permissions
from core.security import hash_password
from core.permission_registry import (
    ADMIN_PERMISSION_CODES,
    ADMIN_PERMISSIONS,
    ADMIN_ROLE,
    RETAILER_OPERATOR_PERMISSIONS,
)
from db.sql_safety import validate_identifier as _validate_identifier


async def create_wholesaler(
    db: AsyncSession,
    name: str,
    code: str
) -> Wholesaler:
    """Create a new wholesaler in the public schema."""
    # Generate tenant schema name
    tenant_id = uuid.uuid4().hex
    tenant_schema = f"t_{tenant_id}"

    wholesaler = Wholesaler(
        name=name,
        code=code
    )

    db.add(wholesaler)
    await db.commit()
    await db.refresh(wholesaler)

    print(f"✓ Created wholesaler: {name} (schema: {tenant_schema})")
    return wholesaler


async def create_tenant_schema(db: AsyncSession, tenant_schema: str):
    """Create the tenant schema if it doesn't exist."""
    _validate_identifier(tenant_schema, "tenant_schema")
    await db.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{tenant_schema}"'))
    await db.commit()
    print(f"✓ Created tenant schema: {tenant_schema}")


async def create_admin_user(
    db: AsyncSession,
    tenant_schema: str,
    email: str,
    password: str,
    first_name: str = "Admin",
    last_name: str = "User"
) -> User:
    """Create an admin user in the tenant schema."""
    # S8-SEC: Validate schema name before SQL interpolation
    _validate_identifier(tenant_schema, "tenant_schema")

    # Set search path to tenant schema
    await db.execute(text(f'SET LOCAL search_path TO "{tenant_schema}", public'))

    # Check if user already exists (uses search_path, no schema prefix needed)
    result = await db.execute(
        text('SELECT * FROM users WHERE email = :email'),
        {"email": email}
    )
    existing = result.fetchone()

    if existing:
        print(f"⚠ User {email} already exists, skipping creation")
        return None

    user = User(
        email=email,
        hashed_password=hash_password(password),
        first_name=first_name,
        last_name=last_name,
        is_active=True,
        is_superuser=False  # We'll use role-based access instead
    )

    db.add(user)
    await db.commit()
    await db.refresh(user)

    print(f"✓ Created admin user: {email} in schema {tenant_schema}")
    return user


async def create_admin_role(
    db: AsyncSession,
    tenant_schema: str,
    user_id: uuid.UUID
) -> Role:
    """Create admin role and assign to user."""
    # S8-SEC: Validate schema name before SQL interpolation
    _validate_identifier(tenant_schema, "tenant_schema")

    # Set search path
    await db.execute(text(f'SET LOCAL search_path TO "{tenant_schema}", public'))

    # Check if admin role exists (uses search_path, no schema prefix needed)
    result = await db.execute(
        text('SELECT * FROM roles WHERE name = :name'),
        {"name": ADMIN_ROLE}
    )
    existing_role = result.fetchone()

    if existing_role:
        print(f"⚠ Admin role already exists, skipping creation")
        return None

    # Create admin role
    admin_role = Role(
        name=ADMIN_ROLE,
        description="Administrator with full access"
    )
    db.add(admin_role)
    await db.commit()
    await db.refresh(admin_role)

    # Assign role to user (uses search_path, no schema prefix needed)
    await db.execute(
        text('INSERT INTO user_roles (user_id, role_id) VALUES (:user_id, :role_id)'),
        {"user_id": str(user_id), "role_id": str(admin_role.id)}
    )
    await db.commit()

    print(f"✓ Created admin role and assigned to user")
    return admin_role


async def create_permissions(db: AsyncSession, tenant_schema: str):
    """Create canonical admin permissions for the system."""
    # S8-SEC: Validate schema name before SQL interpolation
    _validate_identifier(tenant_schema, "tenant_schema")

    # Set search path
    await db.execute(text(f'SET LOCAL search_path TO "{tenant_schema}", public'))

    for code, description in ADMIN_PERMISSIONS + RETAILER_OPERATOR_PERMISSIONS:
        result = await db.execute(
            text('SELECT * FROM permissions WHERE code = :code'),
            {"code": code}
        )
        if not result.fetchone():
            perm = Permission(code=code, description=description)
            db.add(perm)
            print(f"??Created permission: {code}")

    await db.commit()


async def assign_all_permissions_to_admin(db: AsyncSession, tenant_schema: str):
    """Assign only canonical admin permissions to the admin role."""
    # S8-SEC: Validate schema name before SQL interpolation
    _validate_identifier(tenant_schema, "tenant_schema")

    # Set search path
    await db.execute(text(f'SET LOCAL search_path TO "{tenant_schema}", public'))

    # Get admin role (uses search_path, no schema prefix needed)
    result = await db.execute(
        text('SELECT id FROM roles WHERE name = :name'),
        {"name": ADMIN_ROLE}
    )
    role = result.fetchone()

    if not role:
        print("??Admin role not found, skipping permission assignment")
        return

    role_id = role[0]

    resolved_permissions: list[tuple[str, str]] = []
    missing_permissions: list[str] = []
    for code in sorted(ADMIN_PERMISSION_CODES):
        result = await db.execute(
            text('SELECT id FROM permissions WHERE code = :code'),
            {"code": code},
        )
        perm_id = result.scalar()
        if perm_id is None:
            missing_permissions.append(code)
        else:
            resolved_permissions.append((code, str(perm_id)))

    if missing_permissions:
        raise RuntimeError(
            f"Missing canonical admin permission(s): {sorted(missing_permissions)}"
        )

    # Assign only canonical admin permissions, never client:* permissions.
    # R3: reconcile — remove stale grants before re-seeding canonical admin set
    await db.execute(text(
        'DELETE FROM role_permissions WHERE role_id = :role_id'
    ), {"role_id": str(role_id)})

    for _code, perm_id in resolved_permissions:
        # Check if already assigned
        check = await db.execute(
            text('SELECT * FROM role_permissions WHERE role_id = :role_id AND permission_id = :perm_id'),
            {"role_id": str(role_id), "perm_id": str(perm_id)}
        )
        if not check.fetchone():
            await db.execute(
                text('INSERT INTO role_permissions (role_id, permission_id) VALUES (:role_id, :perm_id)'),
                {"role_id": str(role_id), "perm_id": str(perm_id)}
            )
            print(f"??Assigned permission to admin role")

    await db.commit()


async def bootstrap_tenant(
    name: str,
    code: str,
    admin_email: str,
    admin_password: str,
    admin_first_name: str = "Admin",
    admin_last_name: str = "User"
):
    """Main bootstrap function."""
    print("\n" + "="*60)
    print("Mpango ERP Tenant Bootstrap")
    print("="*60 + "\n")

    # Connect to public schema
    async with AsyncSessionLocal() as db:
        # Step 1: Create wholesaler (tenant record)
        print("\n[1/5] Creating wholesaler...")
        wholesaler = await create_wholesaler(db, name, code)

        # Step 2: Create tenant schema
        print("\n[2/5] Creating tenant schema...")
        await create_tenant_schema(db, wholesaler.tenant_schema)

        # Step 3: Create admin user
        print("\n[3/5] Creating admin user...")
        user = await create_admin_user(
            db,
            wholesaler.tenant_schema,
            admin_email,
            admin_password,
            admin_first_name,
            admin_last_name
        )

        if user:
            # Step 4: Create admin role
            print("\n[4/5] Creating admin role...")
            await create_admin_role(db, wholesaler.tenant_schema, user.id)

            # Step 5: Create permissions and assign to admin
            print("\n[5/5] Creating permissions and assigning to admin...")
            await create_permissions(db, wholesaler.tenant_schema)
            await assign_all_permissions_to_admin(db, wholesaler.tenant_schema)

    print("\n" + "="*60)
    print("✓ Bootstrap completed successfully!")
    print("="*60)
    print(f"\nTenant Information:")
    print(f"  Name: {name}")
    print(f"  Code: {code}")
    print(f"  Schema: {wholesaler.tenant_schema}")
    print(f"\nAdmin User:")
    print(f"  Email: {admin_email}")
    print(f"  Password: {admin_password}")
    print("\nYou can now log in to the ERP system with these credentials.")
    print("="*60 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Bootstrap Mpango ERP tenant"
    )
    parser.add_argument(
        "--name",
        required=True,
        help="Wholesaler/tenant name"
    )
    parser.add_argument(
        "--code",
        required=True,
        help="Unique wholesaler code (used in tenant schema name)"
    )
    parser.add_argument(
        "--admin-email",
        required=True,
        help="Admin user email"
    )
    parser.add_argument(
        "--admin-password",
        required=True,
        help="Admin user password"
    )
    parser.add_argument(
        "--admin-first-name",
        default="Admin",
        help="Admin first name (default: Admin)"
    )
    parser.add_argument(
        "--admin-last-name",
        default="User",
        help="Admin last name (default: User)"
    )

    args = parser.parse_args()

    # Validate password strength
    if len(args.admin_password) < 8:
        print("⚠ Warning: Password is less than 8 characters")

    asyncio.run(bootstrap_tenant(
        name=args.name,
        code=args.code,
        admin_email=args.admin_email,
        admin_password=args.admin_password,
        admin_first_name=args.admin_first_name,
        admin_last_name=args.admin_last_name
    ))


if __name__ == "__main__":
    main()
