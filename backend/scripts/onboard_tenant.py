#!/usr/bin/env python3
"""
Tenant Onboarding Script — Full lifecycle tenant provisioning.

Usage:
    # Interactive mode (guided wizard):
    python scripts/onboard_tenant.py

    # Non-interactive mode:
    python scripts/onboard_tenant.py \
        --name "Acme Wholesale" \
        --code acme_wholesale \
        --admin-email admin@acme.com \
        --admin-password "SecureP@ss123!" \
        --seed-demo

This script orchestrates the complete tenant onboarding flow:
1. Creates the wholesaler record in public schema
2. Creates the isolated tenant schema
3. Runs Alembic migrations on the tenant schema
4. Creates admin user with full permissions
5. (Optional) Seeds demo data: retailers, SKUs, inventory, orders
6. Validates the tenant is functional

Why this exists:
    The original create_wholesaler.py handles schema+user creation but does NOT:
    - Run Alembic migrations (tables must already exist)
    - Seed demo/sample data
    - Validate the tenant is functional after creation
    This script fills those gaps.
"""

import asyncio
import argparse
import sys
import uuid
import re
from pathlib import Path
from decimal import Decimal

# Add backend to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from database.session import AsyncSessionLocal
from models.wholesaler import Wholesaler
from models.user import User, Role, Permission
from core.security import hash_password
from db.sql_safety import validate_identifier as _validate_identifier


# ==============================================================================
# Step 1: Tenant Creation
# ==============================================================================

async def create_tenant(db: AsyncSession, name: str, code: str) -> Wholesaler:
    """Create wholesaler record in public schema."""
    # Check for duplicate code
    result = await db.execute(
        text('SELECT id FROM wholesalers WHERE code = :code'),
        {"code": code}
    )
    if result.fetchone():
        raise ValueError(f"Tenant code '{code}' already exists. Choose a different code.")

    wholesaler = Wholesaler(name=name, code=code)
    db.add(wholesaler)
    await db.commit()
    await db.refresh(wholesaler)

    print(f"  ✓ Created wholesaler: {name} (id: {wholesaler.id})")
    return wholesaler


# ==============================================================================
# Step 2: Schema Creation + Migrations
# ==============================================================================

async def create_schema(db: AsyncSession, tenant_schema: str):
    """Create tenant schema and run migrations."""
    _validate_identifier(tenant_schema, "tenant_schema")

    await db.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{tenant_schema}"'))
    await db.commit()
    print(f"  ✓ Created schema: {tenant_schema}")


async def run_migrations(tenant_schema: str):
    """
    Run Alembic migrations against the tenant schema.

    This stamps the schema with the current head revision and creates
    all tables in the tenant schema.
    """
    import subprocess

    backend_dir = Path(__file__).parent.parent

    # Run alembic upgrade head on the tenant schema
    # The Alembic env.py should support schema-aware migrations
    result = subprocess.run(
        [
            sys.executable, "-m", "alembic", "upgrade", "head",
        ],
        cwd=str(backend_dir),
        capture_output=True,
        text=True,
        env={
            **__import__("os").environ,
            "TENANT_SCHEMA": tenant_schema,
        }
    )

    if result.returncode == 0:
        print(f"  ✓ Alembic migrations applied to {tenant_schema}")
    else:
        # Migrations might not target tenant schemas — fall back to SQLAlchemy create_all
        print(f"  ⚠ Alembic returned code {result.returncode}, falling back to metadata.create_all")
        print(f"    stderr: {result.stderr[:200] if result.stderr else 'none'}")
        await _fallback_create_tables(tenant_schema)


async def _fallback_create_tables(tenant_schema: str):
    """Fallback: create tables using SQLAlchemy metadata (no Alembic)."""
    _validate_identifier(tenant_schema, "tenant_schema")

    # Import all models to ensure metadata is populated
    from models import base  # noqa: F401
    from models.user import User  # noqa: F401
    from models.order import Order, OrderItem  # noqa: F401
    from models.inventory_stock import InventoryStock  # noqa: F401
    from models.sku import SKU  # noqa: F401
    from models.ledger import LedgerEntry  # noqa: F401

    from database.session import engine
    from sqlalchemy import event

    async with engine.begin() as conn:
        # Set search path so tables are created in tenant schema
        await conn.execute(text(f'SET search_path TO "{tenant_schema}", public'))

        from models.base import BaseModel
        await conn.run_sync(BaseModel.metadata.create_all)

    print(f"  ✓ Tables created via metadata.create_all in {tenant_schema}")


# ==============================================================================
# Step 3: Admin User + Role + Permissions
# ==============================================================================

async def setup_admin(
    db: AsyncSession,
    tenant_schema: str,
    email: str,
    password: str,
    first_name: str = "Admin",
    last_name: str = "User"
) -> User:
    """Create admin user, role, and all permissions."""
    _validate_identifier(tenant_schema, "tenant_schema")
    await db.execute(text(f'SET LOCAL search_path TO "{tenant_schema}", public'))

    # --- Create permissions ---
    # U1: Complete permission list covering all API-enforced RequirePermission checks.
    # Every permission here is required by at least one API endpoint.
    # Admin role receives ALL permissions during onboarding.
    permissions_data = [
        # ── User management ──
        ("users:read", "Read users"),
        ("users:create", "Create users"),
        ("users:update", "Update users"),
        ("users:deactivate", "Deactivate users"),
        # ── Wholesaler ──
        ("wholesalers:read", "Read wholesalers"),
        ("wholesalers:write", "Create/update/delete wholesalers"),
        # ── Role management ──
        ("roles:read", "Read roles"),
        ("roles:create", "Create roles"),
        ("roles:update", "Update roles"),
        ("roles:delete", "Delete roles"),
        ("roles:assign", "Assign roles to users"),
        # ── Order management ──
        ("orders:read", "Read orders"),
        ("orders:create", "Create orders"),
        ("orders:update", "Update orders"),
        ("orders:confirm", "Confirm orders"),
        ("orders:ship", "Ship orders"),
        ("orders:cancel", "Cancel orders"),
        # ── SKU / Product management ──
        ("skus:read", "Read SKUs"),
        ("skus:create", "Create SKUs"),
        ("skus:update", "Update SKUs"),
        ("skus:import", "Import SKUs via preview/validate/apply contract"),
        # -- Data Intake (U4-A foundation: permissions only, no routes yet) --
        ("intake:read", "Read data intake batches"),
        ("intake:create", "Create data intake batches"),
        ("intake:update", "Update data intake batches"),
        ("intake:approve", "Approve data intake batches for ERP import"),
        ("intake:export", "Export data intake batches"),
        ("intake:import_to_erp", "Import approved data intake into ERP"),
        # ── Inventory management ──
        ("inventory:read", "Read inventory"),
        ("inventory:write", "Write inventory (legacy alias)"),
        ("inventory:update", "Update inventory (adjustments)"),
        # ── Payment management ──
        ("payments:read", "Read payments"),
        ("payments:create", "Create payments"),
        # ── Retailer management ──
        ("retailers:read", "Read retailers"),
        # ── Invitations ──
        ("invitations:create", "Create invitations"),
        # ── Pricing ──
        ("pricing:read", "Read pricing"),
        ("pricing:write", "Write pricing"),
        # ── Finance ──
        ("finance:read", "View invoices, receivables, financial summary"),
        # ── Dashboards & Reports ──
        ("dashboards:read", "View dashboard KPIs and charts"),
        ("reports:read", "Read reports"),
        ("reports:analyze", "Analyze reports"),
        # ── Exports ──
        ("exports:create", "Request data exports"),
        # ── System ──
        ("system:admin", "Full system administration (job queues, debug endpoints)"),
        ("metrics:admin", "Reset application metrics"),
    ]

    perm_ids = []
    for code, description in permissions_data:
        result = await db.execute(
            text('SELECT id FROM permissions WHERE code = :code'),
            {"code": code}
        )
        row = result.fetchone()
        if not row:
            perm = Permission(code=code, description=description)
            db.add(perm)
            await db.flush()
            perm_ids.append(perm.id)
        else:
            perm_ids.append(row[0])

    print(f"  ✓ {len(perm_ids)} permissions ensured")

    # --- Create admin role ---
    result = await db.execute(
        text('SELECT id FROM roles WHERE name = :name'),
        {"name": "admin"}
    )
    role_row = result.fetchone()
    if role_row:
        role_id = role_row[0]
    else:
        admin_role = Role(name="admin", description="Administrator with full access")
        db.add(admin_role)
        await db.flush()
        role_id = admin_role.id

    print(f"  ✓ Admin role ensured")

    # --- Assign all permissions to admin role ---
    for perm_id in perm_ids:
        check = await db.execute(
            text('SELECT 1 FROM role_permissions WHERE role_id = :rid AND permission_id = :pid'),
            {"rid": str(role_id), "pid": str(perm_id)}
        )
        if not check.fetchone():
            await db.execute(
                text('INSERT INTO role_permissions (role_id, permission_id) VALUES (:rid, :pid)'),
                {"rid": str(role_id), "pid": str(perm_id)}
            )

    # --- Create admin user ---
    result = await db.execute(
        text('SELECT id FROM users WHERE email = :email'),
        {"email": email}
    )
    existing = result.fetchone()
    if existing:
        print(f"  ⚠ User {email} already exists, skipping user creation")
        await db.commit()
        return None

    user = User(
        email=email,
        hashed_password=hash_password(password),
        first_name=first_name,
        last_name=last_name,
        is_active=True,
        is_superuser=False,
    )
    db.add(user)
    await db.flush()

    # Assign admin role to user
    await db.execute(
        text('INSERT INTO user_roles (user_id, role_id) VALUES (:uid, :rid)'),
        {"uid": str(user.id), "rid": str(role_id)}
    )
    await db.commit()

    print(f"  ✓ Admin user created: {email}")
    return user


# ==============================================================================
# Step 4: Demo Data Seeding (optional)
# ==============================================================================

async def seed_demo_data(db: AsyncSession, tenant_schema: str, wholesaler_id: uuid.UUID):
    """Seed sample retailers, SKUs, inventory, and orders for demo."""
    _validate_identifier(tenant_schema, "tenant_schema")
    await db.execute(text(f'SET LOCAL search_path TO "{tenant_schema}", public'))

    # --- Retailers ---
    retailer_ids = []
    retailers = [
        {"name": "Downtown Kiosk", "phone": "+254712000001", "location": "Nairobi CBD"},
        {"name": "Eastlands Duka", "phone": "+254712000002", "location": "Eastlands, Nairobi"},
        {"name": "Mombasa Mart", "phone": "+254722000003", "location": "Mombasa Road"},
    ]
    for r in retailers:
        rid = uuid.uuid4()
        retailer_ids.append(rid)
        await db.execute(
            text("""
                INSERT INTO retailers (id, name, phone, location, is_deleted)
                VALUES (:id, :name, :phone, :location, false)
                ON CONFLICT DO NOTHING
            """),
            {"id": str(rid), "name": r["name"], "phone": r["phone"], "location": r["location"]}
        )
    print(f"  ✓ {len(retailers)} demo retailers created")

    # --- SKUs ---
    skus = [
        {"code": "UNGA-2KG", "name": "Unga Maize Flour 2kg", "price": Decimal("180.00")},
        {"code": "SUGAR-1KG", "name": "Mumias Sugar 1kg", "price": Decimal("150.00")},
        {"code": "MILK-500ML", "name": "Brookside Full Cream 500ml", "price": Decimal("65.00")},
        {"code": "RICE-5KG", "name": "Pishori Rice 5kg", "price": Decimal("750.00")},
        {"code": "OIL-1L", "name": "Golden Fry Cooking Oil 1L", "price": Decimal("320.00")},
    ]
    sku_ids = []
    for s in skus:
        sid = uuid.uuid4()
        sku_ids.append(sid)
        await db.execute(
            text("""
                INSERT INTO skus (id, sku_code, name, unit_price, is_active, is_deleted)
                VALUES (:id, :code, :name, :price, true, false)
                ON CONFLICT DO NOTHING
            """),
            {"id": str(sid), "code": s["code"], "name": s["name"], "price": float(s["price"])}
        )
    print(f"  ✓ {len(skus)} demo SKUs created")

    # --- Inventory Stock ---
    for sid in sku_ids:
        await db.execute(
            text("""
                INSERT INTO inventory_stock (id, sku_id, on_hand, reserved, is_deleted)
                VALUES (:id, :sku_id, 100, 0, false)
                ON CONFLICT DO NOTHING
            """),
            {"id": str(uuid.uuid4()), "sku_id": str(sid)}
        )
    print(f"  ✓ Inventory stock initialized (100 units each)")

    # --- Sample Orders ---
    from models.order import OrderStatus
    order_scenarios = [
        {"retailer_idx": 0, "status": OrderStatus.DRAFT, "sku_idx": 0, "qty": 10},
        {"retailer_idx": 1, "status": OrderStatus.CONFIRMED, "sku_idx": 1, "qty": 5},
        {"retailer_idx": 2, "status": OrderStatus.FULFILLED, "sku_idx": 2, "qty": 20},
    ]
    for scenario in order_scenarios:
        sku = skus[scenario["sku_idx"]]
        qty = scenario["qty"]
        subtotal = sku["price"] * qty
        order_id = uuid.uuid4()
        item_id = uuid.uuid4()

        await db.execute(
            text("""
                INSERT INTO orders (id, wholesaler_id, retailer_id, status, total_amount, is_deleted)
                VALUES (:id, :wid, :rid, :status, :total, false)
            """),
            {
                "id": str(order_id),
                "wid": str(wholesaler_id),
                "rid": str(retailer_ids[scenario["retailer_idx"]]),
                "status": scenario["status"].value,
                "total": float(subtotal),
            }
        )
        await db.execute(
            text("""
                INSERT INTO order_items (id, order_id, product_name, sku_code, quantity, unit_price, subtotal, is_deleted)
                VALUES (:id, :oid, :pname, :sku, :qty, :price, :sub, false)
            """),
            {
                "id": str(item_id),
                "oid": str(order_id),
                "pname": sku["name"],
                "sku": sku["code"],
                "qty": qty,
                "price": float(sku["price"]),
                "sub": float(subtotal),
            }
        )
    print(f"  ✓ {len(order_scenarios)} demo orders created (draft/confirmed/fulfilled)")

    await db.commit()


# ==============================================================================
# Step 5: Validation
# ==============================================================================

async def validate_tenant(db: AsyncSession, tenant_schema: str) -> bool:
    """Quick validation: ensure tables exist and are accessible."""
    _validate_identifier(tenant_schema, "tenant_schema")

    checks = [
        ("users", "SELECT count(*) FROM users"),
        ("roles", "SELECT count(*) FROM roles"),
        ("permissions", "SELECT count(*) FROM permissions"),
        ("orders", "SELECT count(*) FROM orders"),
        ("skus", "SELECT count(*) FROM skus"),
    ]

    await db.execute(text(f'SET LOCAL search_path TO "{tenant_schema}", public'))

    all_ok = True
    for table_name, query in checks:
        try:
            result = await db.execute(text(query))
            count = result.scalar()
            print(f"  ✓ {table_name}: {count} rows")
        except Exception as e:
            print(f"  ✗ {table_name}: FAILED — {e}")
            all_ok = False

    return all_ok


# ==============================================================================
# Main Orchestrator
# ==============================================================================

async def onboard_tenant(
    name: str,
    code: str,
    admin_email: str,
    admin_password: str,
    admin_first_name: str = "Admin",
    admin_last_name: str = "User",
    seed_demo: bool = False,
):
    """Full tenant onboarding pipeline."""
    print()
    print("╔" + "═" * 58 + "╗")
    print("║  Mpango ERP — Tenant Onboarding                        ║")
    print("╚" + "═" * 58 + "╝")

    async with AsyncSessionLocal() as db:
        # Step 1
        print(f"\n[1/5] Creating tenant record...")
        wholesaler = await create_tenant(db, name, code)

        # Step 2
        print(f"\n[2/5] Creating tenant schema...")
        await create_schema(db, wholesaler.tenant_schema)

        # Step 3 (migrations / table creation)
        print(f"\n[3/5] Running migrations...")
        try:
            await run_migrations(wholesaler.tenant_schema)
        except Exception as e:
            print(f"  ⚠ Migration error (non-fatal): {e}")
            await _fallback_create_tables(wholesaler.tenant_schema)

        # Step 4
        print(f"\n[4/5] Setting up admin user & RBAC...")
        await setup_admin(
            db,
            wholesaler.tenant_schema,
            admin_email,
            admin_password,
            admin_first_name,
            admin_last_name,
        )

        # Step 5 (optional)
        if seed_demo:
            print(f"\n[5/5] Seeding demo data...")
            await seed_demo_data(db, wholesaler.tenant_schema, wholesaler.id)
        else:
            print(f"\n[5/5] Skipping demo data (use --seed-demo to populate)")

        # Validation
        print(f"\n[✓] Validating tenant...")
        ok = await validate_tenant(db, wholesaler.tenant_schema)

    # Summary
    print()
    print("╔" + "═" * 58 + "╗")
    if ok:
        print("║  ✓ Onboarding complete!                                 ║")
    else:
        print("║  ⚠ Onboarding complete with warnings                    ║")
    print("╚" + "═" * 58 + "╝")
    print(f"""
  Tenant:    {name}
  Code:      {code}
  Schema:    {wholesaler.tenant_schema}
  Admin:     {admin_email}
  Demo data: {"Yes" if seed_demo else "No"}

  Login URL: http://localhost:5173/login
  API Base:  http://localhost:8000/api/v1
""")


# ==============================================================================
# CLI
# ==============================================================================

def interactive_wizard() -> dict:
    """Guided wizard for interactive mode."""
    print()
    print("╔" + "═" * 58 + "╗")
    print("║  Mpango ERP — New Tenant Wizard                         ║")
    print("╚" + "═" * 58 + "╝")
    print()

    name = input("  Business name: ").strip()
    if not name:
        print("  ✗ Business name is required")
        sys.exit(1)

    # Auto-generate code from name
    suggested_code = re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')
    code = input(f"  Tenant code [{suggested_code}]: ").strip() or suggested_code

    email = input("  Admin email: ").strip()
    if not email or "@" not in email:
        print("  ✗ Valid email is required")
        sys.exit(1)

    password = input("  Admin password (min 8 chars): ").strip()
    if len(password) < 8:
        print("  ✗ Password must be at least 8 characters")
        sys.exit(1)

    first_name = input("  Admin first name [Admin]: ").strip() or "Admin"
    last_name = input("  Admin last name [User]: ").strip() or "User"

    seed = input("  Seed demo data? (y/N): ").strip().lower()

    return {
        "name": name,
        "code": code,
        "admin_email": email,
        "admin_password": password,
        "admin_first_name": first_name,
        "admin_last_name": last_name,
        "seed_demo": seed in ("y", "yes"),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Mpango ERP — Full Tenant Onboarding",
        epilog="Run without arguments for interactive wizard mode.",
    )
    parser.add_argument("--name", help="Business / tenant name")
    parser.add_argument("--code", help="Unique tenant code (lowercase, underscores)")
    parser.add_argument("--admin-email", help="Admin user email")
    parser.add_argument("--admin-password", help="Admin user password")
    parser.add_argument("--admin-first-name", default="Admin", help="Admin first name")
    parser.add_argument("--admin-last-name", default="User", help="Admin last name")
    parser.add_argument("--seed-demo", action="store_true", help="Seed sample data for demo")

    args = parser.parse_args()

    # Detect interactive vs non-interactive
    if args.name and args.code and args.admin_email and args.admin_password:
        # Non-interactive
        config = {
            "name": args.name,
            "code": args.code,
            "admin_email": args.admin_email,
            "admin_password": args.admin_password,
            "admin_first_name": args.admin_first_name,
            "admin_last_name": args.admin_last_name,
            "seed_demo": args.seed_demo,
        }
    else:
        # Interactive wizard
        config = interactive_wizard()

    # Validate password
    if len(config["admin_password"]) < 8:
        print("⚠ Warning: Password is less than 8 characters")

    # Run
    asyncio.run(onboard_tenant(**config))


if __name__ == "__main__":
    main()
