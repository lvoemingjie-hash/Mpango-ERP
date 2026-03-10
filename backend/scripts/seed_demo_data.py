#!/usr/bin/env python3
"""
Track E2: Staging Demo Data Seeder

Seeds a complete demo environment using backend Service methods so that
the Track E1 tenant guardrails are exercised during seeding.

Usage:
    python scripts/seed_demo_data.py                # from repo root
    python scripts/seed_demo_data.py --allow-production  # skip safety

Idempotent: safe to run multiple times.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid
from decimal import Decimal
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEMO_WHOLESALER_ID = uuid.UUID("a0000000-0000-4000-8000-000000000001")
DEMO_WHOLESALER_CODE = "DEMO001"
DEMO_WHOLESALER_NAME = "Mpango Demo Wholesaler"

DEMO_RETAILER_ID = uuid.UUID("b0000000-0000-4000-8000-000000000001")
DEMO_RETAILER_PHONE = "+254700000001"
DEMO_RETAILER_NAME = "Nairobi Central Duka"

ADMIN_EMAIL = "admin@mpango.demo"
ADMIN_PASSWORD = "DemoAdmin2026!"  # pragma: allowlist secret (demo credential)
ADMIN_FULL_NAME = "Demo Administrator"

PERMISSION_CODES = [
    ("users:read", "Read users"), ("users:create", "Create users"),
    ("users:update", "Update users"), ("users:delete", "Delete users"),
    ("orders:read", "Read orders"), ("orders:create", "Create orders"),
    ("orders:write", "Write/update orders"), ("orders:delete", "Delete orders"),
    ("payments:read", "Read payments"), ("payments:create", "Create payments"),
    ("skus:read", "Read SKUs"), ("skus:create", "Create SKUs"),
    ("skus:update", "Update SKUs"), ("inventory:read", "Read inventory"),
    ("inventory:update", "Update inventory"), ("reports:read", "Read reports"),
    ("dashboards:read", "Read dashboard KPIs and charts"),
    ("reports:analyze", "Execute ad-hoc semantic analysis queries"),
]

ROLES = [
    ("admin", "Administrator with full access"),
    ("sales", "Sales team member"),
    ("warehouse", "Warehouse operator"),
    ("finance", "Finance team member"),
]

DEMO_SKUS = [
    ("SKU-FLOUR-001", "Pembe Wheat Flour 2kg", "Premium wheat flour", "bag", "Flour & Grains"),
    ("SKU-FLOUR-002", "Jogoo Maize Flour 2kg", "Sifted maize flour", "bag", "Flour & Grains"),
    ("SKU-SUGAR-001", "Mumias Sugar 1kg", "White granulated sugar", "pack", "Sugar & Sweeteners"),
    ("SKU-SUGAR-002", "Kabras Brown Sugar 500g", "Natural brown sugar", "pack", "Sugar & Sweeteners"),
    ("SKU-OIL-001", "Elianto Cooking Oil 1L", "Pure sunflower oil", "bottle", "Cooking Oil"),
    ("SKU-OIL-002", "Rina Vegetable Oil 2L", "Blended vegetable oil", "bottle", "Cooking Oil"),
    ("SKU-RICE-001", "Daawat Basmati Rice 1kg", "Long grain basmati", "pack", "Rice & Pasta"),
    ("SKU-TEA-001", "Kericho Gold Tea 100s", "Premium Kenyan tea bags", "box", "Beverages"),
    ("SKU-SOAP-001", "Menengai Bar Soap 200g", "Multi-purpose bar soap", "piece", "Household"),
    ("SKU-SALT-001", "Kensalt Iodized Salt 1kg", "Iodized table salt", "pack", "Condiments"),
]

DEMO_ORDERS = [
    {
        "notes": "Weekly restock - pending confirmation",
        "total_amount": Decimal("4500.00"),
        "items": [
            ("SKU-FLOUR-001", "Pembe Wheat Flour 2kg", 20, Decimal("150.00")),
            ("SKU-SUGAR-001", "Mumias Sugar 1kg", 15, Decimal("100.00")),
        ],
        "transitions": [],
    },
    {
        "notes": "Confirmed order awaiting payment",
        "total_amount": Decimal("3200.00"),
        "items": [
            ("SKU-OIL-001", "Elianto Cooking Oil 1L", 10, Decimal("220.00")),
            ("SKU-RICE-001", "Daawat Basmati Rice 1kg", 5, Decimal("200.00")),
        ],
        "transitions": ["confirmed"],
    },
    {
        "notes": "Fully paid order ready for dispatch",
        "total_amount": Decimal("6800.00"),
        "items": [
            ("SKU-TEA-001", "Kericho Gold Tea 100s", 30, Decimal("180.00")),
            ("SKU-SALT-001", "Kensalt Iodized Salt 1kg", 20, Decimal("70.00")),
        ],
        "transitions": ["confirmed", "paid"],
    },
    {
        "notes": "Delivered to Nairobi Central Duka",
        "total_amount": Decimal("5500.00"),
        "items": [
            ("SKU-FLOUR-002", "Jogoo Maize Flour 2kg", 25, Decimal("120.00")),
            ("SKU-SOAP-001", "Menengai Bar Soap 200g", 50, Decimal("50.00")),
        ],
        "transitions": ["confirmed", "paid", "fulfilled"],
    },
    {
        "notes": "Cancelled by retailer before payment",
        "total_amount": Decimal("2100.00"),
        "items": [
            ("SKU-SUGAR-002", "Kabras Brown Sugar 500g", 10, Decimal("130.00")),
            ("SKU-OIL-002", "Rina Vegetable Oil 2L", 4, Decimal("200.00")),
        ],
        "transitions": ["confirmed", "cancelled"],
    },
]


def _add_backend_to_path() -> None:
    backend_dir = Path(__file__).resolve().parents[1] / "backend"
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))


def _require_safe_environment(*, allow_production: bool) -> None:
    mpango_env = os.getenv("MPANGO_ENV", "production").strip().lower()
    if mpango_env not in {"test", "dev", "staging"} and not allow_production:
        raise SystemExit(
            "Refusing to seed outside MPANGO_ENV in {test,dev,staging}. "
            "Pass --allow-production to override."
        )


async def _seed_system_data(db) -> str:
    """Seed wholesaler + retailer in public schema. Returns tenant_schema."""
    from sqlalchemy import text
    from db.tenant_filter import mark_session_as_system
    from models.wholesaler import Wholesaler

    mark_session_as_system(db, reason="seed_demo_data:system_bootstrap")

    row = (await db.execute(
        text("SELECT id FROM public.wholesalers WHERE code = :code"),
        {"code": DEMO_WHOLESALER_CODE},
    )).scalar()
    if row is None:
        await db.execute(text(
            "INSERT INTO public.wholesalers (id, code, name, contact, plan_type) "
            "VALUES (:id, :code, :name, :contact, :plan)"
        ), {
            "id": DEMO_WHOLESALER_ID, "code": DEMO_WHOLESALER_CODE,
            "name": DEMO_WHOLESALER_NAME, "contact": "+254700000000",
            "plan": "enterprise",
        })
        print("  + Wholesaler DEMO001 created")
    else:
        print("  . Wholesaler DEMO001 exists")

    row_r = (await db.execute(
        text("SELECT id FROM public.retailers WHERE phone = :phone"),
        {"phone": DEMO_RETAILER_PHONE},
    )).scalar()
    if row_r is None:
        await db.execute(text(
            "INSERT INTO public.retailers (id, phone, name, email, address) "
            "VALUES (:id, :phone, :name, :email, :addr)"
        ), {
            "id": DEMO_RETAILER_ID, "phone": DEMO_RETAILER_PHONE,
            "name": DEMO_RETAILER_NAME, "email": "duka@example.co.ke",
            "addr": "Tom Mboya St, Nairobi CBD",
        })
        print("  + Retailer created")
    else:
        print("  . Retailer exists")

    await db.commit()
    return Wholesaler.derive_schema_from_id(str(DEMO_WHOLESALER_ID))


async def _bootstrap_tenant_schema(db, ts: str) -> None:
    """Create tenant schema and tables via DDL (idempotent)."""
    from sqlalchemy import text

    await db.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{ts}"'))
    await db.execute(text(f'SET LOCAL search_path TO "{ts}", public'))

    for enum_ddl in [
        "DO $$ BEGIN CREATE TYPE order_status AS ENUM "
        "('draft','confirmed','partially_paid','paid','fulfilled','cancelled','voided'); "
        "EXCEPTION WHEN duplicate_object THEN null; END $$",
        "DO $$ BEGIN CREATE TYPE account_type AS ENUM "
        "('receivable','revenue','cash','liability'); "
        "EXCEPTION WHEN duplicate_object THEN null; END $$",
    ]:
        await db.execute(text(enum_ddl))

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
    print(f"  + Tenant schema {ts} bootstrapped")


async def _seed_rbac(db, ts: str) -> None:
    """Seed admin user, roles, permissions, and wire them together."""
    from sqlalchemy import text
    import bcrypt

    await db.execute(text(f'SET LOCAL search_path TO "{ts}", public'))

    pw_hash = bcrypt.hashpw(ADMIN_PASSWORD[:72].encode(), bcrypt.gensalt()).decode()
    await db.execute(text(
        "INSERT INTO users (email, password_hash, full_name, is_active) "
        "VALUES (:e, :p, :n, true) "
        "ON CONFLICT (email) DO UPDATE SET password_hash=EXCLUDED.password_hash, "
        "full_name=EXCLUDED.full_name, is_active=true"
    ), {"e": ADMIN_EMAIL, "p": pw_hash, "n": ADMIN_FULL_NAME})

    for rname, rdesc in ROLES:
        await db.execute(text(
            "INSERT INTO roles (name, description) VALUES (:n, :d) "
            "ON CONFLICT (name) DO UPDATE SET description=EXCLUDED.description"
        ), {"n": rname, "d": rdesc})

    for pcode, pdesc in PERMISSION_CODES:
        await db.execute(text(
            "INSERT INTO permissions (code, description) VALUES (:c, :d) "
            "ON CONFLICT (code) DO UPDATE SET description=EXCLUDED.description"
        ), {"c": pcode, "d": pdesc})

    uid = (await db.execute(
        text("SELECT id FROM users WHERE email = :e"), {"e": ADMIN_EMAIL}
    )).scalar()
    rid = (await db.execute(
        text("SELECT id FROM roles WHERE name = 'admin'")
    )).scalar()

    await db.execute(text(
        "INSERT INTO user_roles (user_id, role_id) VALUES (:u, :r) "
        "ON CONFLICT DO NOTHING"
    ), {"u": uid, "r": rid})

    perms = (await db.execute(text("SELECT id FROM permissions"))).fetchall()
    for (pid,) in perms:
        await db.execute(text(
            "INSERT INTO role_permissions (role_id, permission_id) "
            "VALUES (:r, :p) ON CONFLICT DO NOTHING"
        ), {"r": rid, "p": pid})

    await db.commit()
    print(f"  + RBAC seeded: admin user + {len(ROLES)} roles + {len(PERMISSION_CODES)} perms")


async def _seed_skus(db, ts: str) -> None:
    """Seed SKUs using SKUService (exercises tenant guardrail)."""
    from sqlalchemy import text
    from db.tenant_filter import clear_session_system_scope
    from services.sku_service import SKUService

    clear_session_system_scope(db)
    db.info["tenant_schema"] = ts
    db.info["tenant_id"] = str(DEMO_WHOLESALER_ID)
    await db.execute(text(f'SET LOCAL search_path TO "{ts}", public'))

    svc = SKUService()
    created = 0
    for sku_code, name, desc, unit, category in DEMO_SKUS:
        try:
            await svc.create_sku(
                db, sku_code=sku_code, name=name, description=desc,
                unit=unit, category=category, is_active=True, created_by=None,
            )
            created += 1
        except Exception:
            pass  # already exists (409)

    await db.commit()
    print(f"  + SKUs: {created} created, {len(DEMO_SKUS) - created} already existed")


async def _seed_inventory(db, ts: str) -> None:
    """Seed inventory stocks for all SKUs (100 units each)."""
    from sqlalchemy import text

    db.info["tenant_schema"] = ts
    db.info["tenant_id"] = str(DEMO_WHOLESALER_ID)
    await db.execute(text(f'SET LOCAL search_path TO "{ts}", public'))

    # Get all SKU IDs
    sku_rows = (await db.execute(
        text("SELECT id FROM skus WHERE is_deleted = false")
    )).fetchall()

    created = 0
    for (sku_id,) in sku_rows:
        # Insert inventory stock record with 100 units on hand
        result = await db.execute(text(
            "INSERT INTO inventory_stocks (sku_id, quantity_on_hand, quantity_reserved) "
            "VALUES (:sku_id, 100, 0) "
            "ON CONFLICT (sku_id) DO UPDATE SET quantity_on_hand = 100 "
            "WHERE inventory_stocks.quantity_on_hand = 0"
        ), {"sku_id": sku_id})
        if result.rowcount > 0:
            created += 1

    await db.commit()
    print(f"  + Inventory: {created} stocks seeded with 100 units each")


async def _seed_orders(db, ts: str) -> None:
    """Seed orders using ORM + OrderService.transition (exercises guardrail)."""
    from sqlalchemy import text, select
    from models.order import Order, OrderItem, OrderStatus
    from services.order_service import OrderService
    from core.domain.order_state import OrderState

    db.info["tenant_schema"] = ts
    db.info["tenant_id"] = str(DEMO_WHOLESALER_ID)
    await db.execute(text(f'SET LOCAL search_path TO "{ts}", public'))

    existing_count = (await db.execute(
        select(Order).where(Order.is_deleted == False)
    )).scalars().all()
    if len(existing_count) >= len(DEMO_ORDERS):
        print(f"  . Orders already seeded ({len(existing_count)} found)")
        return

    svc = OrderService(db)
    state_map = {
        "confirmed": OrderState.CONFIRMED,
        "paid": OrderState.PAID,
        "fulfilled": OrderState.FULFILLED,
        "cancelled": OrderState.CANCELLED,
    }

    for i, spec in enumerate(DEMO_ORDERS, 1):
        order = Order(
            wholesaler_id=DEMO_WHOLESALER_ID,
            retailer_id=DEMO_RETAILER_ID,
            status=OrderStatus.DRAFT,
            total_amount=spec["total_amount"],
            notes=spec["notes"],
        )
        db.add(order)
        await db.flush()

        for sku_code, prod_name, qty, unit_price in spec["items"]:
            item = OrderItem(
                order_id=order.id,
                product_name=prod_name,
                sku_code=sku_code,
                quantity=qty,
                unit_price=unit_price,
                subtotal=qty * unit_price,
            )
            db.add(item)
        await db.flush()

        for tname in spec["transitions"]:
            target = state_map[tname]
            order = await svc.transition(
                order_id=order.id, target_state=target,
                reason=f"Demo seed: {tname}",
            )

        await db.commit()
        await db.execute(text(f'SET LOCAL search_path TO "{ts}", public'))
        label = spec["transitions"][-1] if spec["transitions"] else "draft"
        print(f"  + Order {i}/{len(DEMO_ORDERS)}: {label}")

    print(f"  + {len(DEMO_ORDERS)} demo orders seeded with ledger entries")


async def seed(*, allow_production: bool) -> None:
    _require_safe_environment(allow_production=allow_production)
    _add_backend_to_path()

    os.environ.setdefault("MPANGO_ENV", "staging")
    import hashlib
    _fallback_key = hashlib.sha256(b"mpango-staging-seed-key").hexdigest()
    os.environ.setdefault("SECRET_KEY", _fallback_key)
    os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:6379/0")

    from database.session import AsyncSessionLocal

    print("\n=== Mpango ERP Demo Seeder (Track E2) ===\n")

    print("[1/5] System data (public schema)...")
    async with AsyncSessionLocal() as db:
        db.info["tenant_schema"] = "public"
        ts = await _seed_system_data(db)

    print(f"[2/5] Tenant schema bootstrap ({ts})...")
    async with AsyncSessionLocal() as db:
        db.info["tenant_schema"] = "public"
        await _bootstrap_tenant_schema(db, ts)

    print("[3/5] RBAC (admin + roles + permissions)...")
    async with AsyncSessionLocal() as db:
        db.info["tenant_schema"] = ts
        db.info["tenant_id"] = str(DEMO_WHOLESALER_ID)
        await _seed_rbac(db, ts)

    print("[4/5] SKUs (10 products via SKUService)...")
    async with AsyncSessionLocal() as db:
        await _seed_skus(db, ts)

    print("[4.5/5] Inventory (100 units per SKU)...")
    async with AsyncSessionLocal() as db:
        await _seed_inventory(db, ts)

    print("[5/5] Orders (5 orders via OrderService)...")
    async with AsyncSessionLocal() as db:
        await _seed_orders(db, ts)

    print("\n=== Seed Complete ===")
    print(f"  Tenant code : {DEMO_WHOLESALER_CODE}")
    print(f"  Tenant ID   : {DEMO_WHOLESALER_ID}")
    print(f"  Schema      : {ts}")
    print(f"  Admin login : {ADMIN_EMAIL} / {ADMIN_PASSWORD}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed Mpango staging demo data")
    parser.add_argument("--allow-production", action="store_true",
                        help="Allow running outside test/dev/staging env")
    args = parser.parse_args()
    asyncio.run(seed(allow_production=args.allow_production))


if __name__ == "__main__":
    main()
