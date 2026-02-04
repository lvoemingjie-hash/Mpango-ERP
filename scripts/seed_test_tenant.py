#!/usr/bin/env python3
"""Seed the gold-standard test tenant and admin user.

This script is intended for MPANGO_ENV=test or local development.
It is idempotent and safe to run multiple times.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
import uuid
from pathlib import Path


def _add_backend_to_path() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    backend_dir = repo_root / "backend"
    sys.path.insert(0, str(backend_dir))


def _looks_like_production_db(database_url: str) -> bool:
    url = database_url.lower()

    if any(token in url for token in ("prod", "production")):
        return True

    # allow common local dev patterns
    if "localhost" in url or "127.0.0.1" in url:
        return False

    # if it's not obviously local, treat as suspicious
    return True


def _require_safe_environment(*, allow_production: bool) -> None:
    mpango_env = os.getenv("MPANGO_ENV", "production").strip().lower()

    if mpango_env not in {"test", "dev"} and not allow_production:
        raise SystemExit(
            "Refusing to seed tenant outside MPANGO_ENV in {test,dev}. "
            "Set MPANGO_ENV=test (recommended) or pass --allow-production to override."
        )


async def _ensure_tenant_tables(db, tenant_schema: str) -> None:
    from sqlalchemy import text

    await db.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{tenant_schema}"'))
    await db.execute(text(f'SET LOCAL search_path TO "{tenant_schema}", public'))

    await db.execute(
        text(
            """
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
            """
        )
    )

    await db.execute(
        text(
            """
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
            """
        )
    )

    await db.execute(
        text(
            """
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
            """
        )
    )

    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS user_roles (
                user_id UUID NOT NULL,
                role_id UUID NOT NULL,
                PRIMARY KEY (user_id, role_id),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE
            )
            """
        )
    )

    await db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS role_permissions (
                role_id UUID NOT NULL,
                permission_id UUID NOT NULL,
                PRIMARY KEY (role_id, permission_id),
                FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE,
                FOREIGN KEY (permission_id) REFERENCES permissions(id) ON DELETE CASCADE
            )
            """
        )
    )


async def _seed_admin_rbac(
    db,
    *,
    tenant_schema: str,
    admin_email: str,
    admin_password: str,
    admin_full_name: str,
    permission_codes: list[tuple[str, str]],
) -> None:
    from sqlalchemy import text

    from core.security import hash_password

    await db.execute(text(f'SET LOCAL search_path TO "{tenant_schema}", public'))

    password_hash = hash_password(admin_password[:72])

    await db.execute(
        text(
            """
            INSERT INTO users (email, password_hash, full_name, is_active)
            VALUES (:email, :password_hash, :full_name, true)
            ON CONFLICT (email) DO UPDATE
            SET password_hash = EXCLUDED.password_hash,
                full_name = EXCLUDED.full_name,
                is_active = true
            """
        ),
        {"email": admin_email, "password_hash": password_hash, "full_name": admin_full_name},
    )

    await db.execute(
        text(
            """
            INSERT INTO roles (name, description)
            VALUES ('admin', 'Administrator with full access')
            ON CONFLICT (name) DO UPDATE
            SET description = EXCLUDED.description
            """
        )
    )

    for code, description in permission_codes:
        await db.execute(
            text(
                """
                INSERT INTO permissions (code, description)
                VALUES (:code, :description)
                ON CONFLICT (code) DO UPDATE
                SET description = EXCLUDED.description
                """
            ),
            {"code": code, "description": description},
        )

    user_id = (
        await db.execute(text("SELECT id FROM users WHERE email = :email"), {"email": admin_email})
    ).scalar()
    role_id = (await db.execute(text("SELECT id FROM roles WHERE name = 'admin'"))).scalar()

    await db.execute(
        text(
            """
            INSERT INTO user_roles (user_id, role_id)
            VALUES (:user_id, :role_id)
            ON CONFLICT (user_id, role_id) DO NOTHING
            """
        ),
        {"user_id": user_id, "role_id": role_id},
    )

    perm_rows = (await db.execute(text("SELECT id FROM permissions"))).fetchall()
    for (perm_id,) in perm_rows:
        await db.execute(
            text(
                """
                INSERT INTO role_permissions (role_id, permission_id)
                VALUES (:role_id, :permission_id)
                ON CONFLICT (role_id, permission_id) DO NOTHING
                """
            ),
            {"role_id": role_id, "permission_id": perm_id},
        )


async def _ensure_public_wholesaler(db, *, tenant_id: uuid.UUID, tenant_code: str, tenant_name: str) -> None:
    from sqlalchemy import text

    existing = (
        await db.execute(
            text('SELECT id, name FROM public.wholesalers WHERE code = :code'), {"code": tenant_code}
        )
    ).first()

    if existing is None:
        await db.execute(
            text(
                """
                INSERT INTO public.wholesalers (id, code, name)
                VALUES (:id, :code, :name)
                """
            ),
            {"id": tenant_id, "code": tenant_code, "name": tenant_name},
        )
        return

    existing_id, _existing_name = existing
    if str(existing_id) != str(tenant_id):
        raise SystemExit(
            f"Tenant code {tenant_code} already exists with id {existing_id}. "
            f"Expected id {tenant_id}. Refusing to proceed to avoid schema mismatch."
        )

    await db.execute(
        text(
            """
            UPDATE public.wholesalers
            SET name = :name
            WHERE code = :code
            """
        ),
        {"name": tenant_name, "code": tenant_code},
    )


async def seed(*, also_seed_t_dev: bool, allow_production: bool) -> None:
    _require_safe_environment(allow_production=allow_production)

    _add_backend_to_path()

    from core.config import get_settings
    from database.session import AsyncSessionLocal
    from models.wholesaler import Wholesaler

    settings = get_settings()

    if _looks_like_production_db(settings.DATABASE_URL) and not allow_production:
        raise SystemExit(
            "Refusing to run against a non-local DATABASE_URL. "
            "Pass --allow-production to override."
        )

    tenant_id = uuid.UUID("550e8400-e29b-41d4-a716-446655440000")
    tenant_code = "TEST001"
    tenant_name = "Mpango Test Tenant"

    admin_email = "admin@test.com"
    admin_password = "testpassword"
    admin_full_name = "Test Admin"

    permission_codes = [
        ("payments:create", "Create payments"),
        ("payments:read", "Read payments"),
        ("orders:read", "Read orders"),
        ("orders:write", "Write orders"),
        ("users:read", "Read users"),
        ("users:create", "Create users"),
    ]

    async with AsyncSessionLocal() as db:
        await _ensure_public_wholesaler(
            db, tenant_id=tenant_id, tenant_code=tenant_code, tenant_name=tenant_name
        )

        tenant_schema = Wholesaler.derive_schema_from_id(str(tenant_id))

        await _ensure_tenant_tables(db, tenant_schema)
        await _seed_admin_rbac(
            db,
            tenant_schema=tenant_schema,
            admin_email=admin_email,
            admin_password=admin_password,
            admin_full_name=admin_full_name,
            permission_codes=permission_codes,
        )

        if also_seed_t_dev:
            await _ensure_tenant_tables(db, "t_dev")
            await _seed_admin_rbac(
                db,
                tenant_schema="t_dev",
                admin_email=admin_email,
                admin_password=admin_password,
                admin_full_name=admin_full_name,
                permission_codes=permission_codes,
            )

        await db.commit()

    print("✓ Seed complete")
    print(f"- Tenant code: {tenant_code}")
    print(f"- Tenant id: {tenant_id}")
    print(f"- Tenant schema: {Wholesaler.derive_schema_from_id(str(tenant_id))}")
    if also_seed_t_dev:
        print("- Also seeded schema: t_dev")
    print(f"- Admin email: {admin_email}")
    print(f"- Admin password: {admin_password}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed Mpango gold-standard test tenant + admin user")
    parser.add_argument(
        "--no-seed-t-dev",
        action="store_true",
        help="Do not seed the t_dev schema (by default t_dev is seeded too)",
    )
    parser.add_argument(
        "--allow-production",
        action="store_true",
        help="Allow running even when MPANGO_ENV is not test/dev or DATABASE_URL looks non-local",
    )

    args = parser.parse_args()

    asyncio.run(seed(also_seed_t_dev=not args.no_seed_t_dev, allow_production=args.allow_production))


if __name__ == "__main__":
    main()
