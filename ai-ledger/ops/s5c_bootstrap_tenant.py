#!/usr/bin/env python3
"""S5-C: Bootstrap a complete tenant with admin user for browser smoke testing.

Runs inside the backend Docker container. Uses raw DDL to bypass ORM tenant filter.

Usage (inside container):
    python /app/../ai-ledger/ops/s5c_bootstrap_tenant.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

# Add backend to path (container has backend at /app)
backend_dir = Path("/app")
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import asyncpg
from core.security import hash_password

# Config
DB_URL = os.environ.get("DATABASE_URL", "postgresql://mpango:MpangoDBV0.1.4@postgres:5432/mpango_erp")  # pragma: allowlist secret

TENANT_NAME = "S5C Smoke Test"
TENANT_CODE = "s5c_test"
ADMIN_EMAIL = "admin@s5c.test"
ADMIN_PASSWORD = "S5cP@ss1!"  # pragma: allowlist secret
ADMIN_FULL_NAME = "S5C Admin"


async def main():
    conn = await asyncpg.connect(DB_URL)
    try:
        # Step 1: Clean up broken s5c_test
        print("[1/6] Cleaning up existing s5c_test...")
        existing = await conn.fetchrow(
            "SELECT id FROM wholesalers WHERE code = $1 AND is_deleted = false",
            TENANT_CODE,
        )
        if existing:
            wid = existing["id"]
            # Delete platform_tenant first
            await conn.execute("DELETE FROM platform_tenants WHERE wholesaler_id = $1", wid)
            # Delete wholesaler
            await conn.execute("DELETE FROM wholesalers WHERE id = $1", wid)
            print(f"  Deleted existing wholesaler {wid}")
        else:
            print("  No existing record to clean")

        # Step 2: Create wholesaler
        print("[2/6] Creating wholesaler record...")
        wholesaler_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO wholesalers (id, code, name, status) VALUES ($1, $2, $3, 'active')",
            str(wholesaler_id), TENANT_CODE, TENANT_NAME,
        )
        print(f"  Created wholesaler: {wholesaler_id}")

        # Step 3: Create platform_tenant
        print("[3/6] Creating platform_tenant...")
        await conn.execute(
            "INSERT INTO platform_tenants (wholesaler_id, provisioning_status) VALUES ($1, 'active')",
            str(wholesaler_id),
        )
        print("  Created platform_tenant entry")

        # Step 4: Bootstrap tenant schema
        print("[4/6] Bootstrapping tenant schema...")
        from scripts.bootstrap_tenant_schema import bootstrap
        engine_db_url = DB_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
        bootstrap_schema = f"t_{TENANT_CODE}"
        await bootstrap(bootstrap_schema, engine_db_url)
        print(f"  Bootstrapped schema: {bootstrap_schema}")

        # Step 5: Create RBAC
        print("[5/6] Creating RBAC (permissions + admin role)...")
        permissions = [
            ("users:read", "Read users"),
            ("users:create", "Create users"),
            ("users:update", "Update users"),
            ("users:deactivate", "Deactivate users"),
            ("wholesalers:read", "Read wholesalers"),
            ("wholesalers:write", "Create/update/delete wholesalers"),
            ("roles:read", "Read roles"),
            ("roles:create", "Create roles"),
            ("roles:update", "Update roles"),
            ("roles:delete", "Delete roles"),
            ("roles:assign", "Assign roles to users"),
            ("orders:read", "Read orders"),
            ("orders:create", "Create orders"),
            ("orders:update", "Update orders"),
            ("orders:confirm", "Confirm orders"),
            ("orders:ship", "Ship orders"),
            ("orders:cancel", "Cancel orders"),
            ("skus:read", "Read SKUs"),
            ("skus:create", "Create SKUs"),
            ("skus:update", "Update SKUs"),
            ("skus:import", "Import SKUs"),
            ("inventory:read", "Read inventory"),
            ("inventory:write", "Write inventory"),
            ("inventory:update", "Update inventory"),
            ("payments:read", "Read payments"),
            ("payments:create", "Create payments"),
            ("retailers:read", "Read retailers"),
            ("invitations:create", "Create invitations"),
            ("pricing:read", "Read pricing"),
            ("pricing:write", "Write pricing"),
            ("finance:read", "View finance"),
            ("dashboards:read", "View dashboard"),
            ("reports:read", "Read reports"),
            ("reports:analyze", "Analyze reports"),
            ("exports:create", "Request exports"),
            ("system:admin", "System admin"),
            ("metrics:admin", "Reset metrics"),
        ]

        perm_ids = []
        for code, desc in permissions:
            await conn.execute(
                f"INSERT INTO {bootstrap_schema}.permissions (id, code, description) "
                "VALUES ($1, $2, $3) ON CONFLICT (code) DO UPDATE SET description = $3",
                str(uuid.uuid4()), code, desc,
            )
            row = await conn.fetchrow(
                f"SELECT id FROM {bootstrap_schema}.permissions WHERE code = $1", code
            )
            perm_ids.append(row["id"])

        print(f"  Created {len(perm_ids)} permissions")

        # Create admin role
        role_id = uuid.uuid4()
        await conn.execute(
            f"INSERT INTO {bootstrap_schema}.roles (id, name, description) "
            "VALUES ($1, 'admin', 'Administrator with full access') "
            "ON CONFLICT DO NOTHING",
            str(role_id),
        )
        row = await conn.fetchrow(
            f"SELECT id FROM {bootstrap_schema}.roles WHERE name = 'admin'"
        )
        role_id = row["id"]
        print(f"  Admin role: {role_id}")

        # Assign permissions to admin role
        for pid in perm_ids:
            await conn.execute(
                f"INSERT INTO {bootstrap_schema}.role_permissions (role_id, permission_id) "
                "VALUES ($1, $2) ON CONFLICT DO NOTHING",
                str(role_id), str(pid),
            )
        print(f"  Assigned {len(perm_ids)} permissions to admin role")

        # Step 6: Create admin user
        print("[6/6] Creating admin user...")
        user_id = uuid.uuid4()
        password_hash = hash_password(ADMIN_PASSWORD)
        await conn.execute(
            f"INSERT INTO {bootstrap_schema}.users (id, email, password_hash, full_name, is_active) "
            "VALUES ($1, $2, $3, $4, true) ON CONFLICT (email) DO NOTHING",
            str(user_id), ADMIN_EMAIL, password_hash, ADMIN_FULL_NAME,
        )
        row = await conn.fetchrow(
            f"SELECT id FROM {bootstrap_schema}.users WHERE email = $1", ADMIN_EMAIL
        )
        user_id = row["id"]

        # Assign admin role to user
        await conn.execute(
            f"INSERT INTO {bootstrap_schema}.user_roles (user_id, role_id) "
            "VALUES ($1, $2) ON CONFLICT DO NOTHING",
            str(user_id), str(role_id),
        )

        print(f"  Admin user created: {ADMIN_EMAIL}")

        # Summary
        print()
        print("=" * 60)
        print("S5-C Tenant Bootstrap Complete!")
        print("=" * 60)
        print(f"  Tenant:    {TENANT_NAME}")
        print(f"  Code:      {TENANT_CODE}")
        print(f"  Schema:    {bootstrap_schema}")
        print(f"  Admin:     {ADMIN_EMAIL}")
        print(f"  Password:  {ADMIN_PASSWORD}")
        print(f"  Login:     http://localhost:8080/login")
        print("=" * 60)

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
