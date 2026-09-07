"""Shared fixtures/helpers for MPANGO-MVP-INVARIANTS-R0 regression candidates.

Task: MPANGO-MVP-INVARIANTS-R0 (branch zcode/mpango-mvp-invariants-r0-2026-09-07)

Scope and method (mirrors the external review probes, but as pytest):
- Task-exclusive disposable PostgreSQL is provided OUTSIDE this repo via
  TEST_DATABASE_URL. A loopback guard below refuses non-local database hosts
  so the suite can never point at a shared/rehearsal deployment.
- Tenant schemas are created through the product's own provisioning DDL
  (scripts.bootstrap_tenant_schema.bootstrap) on a fresh, uniquely named
  schema per test, then dropped on teardown.
- No SQL results are mocked. Concurrency interleave points are scheduled by
  pausing a repository/route read with asyncio events across two real
  database sessions/connections (deterministic barriers, no sleeps).
- Direct route-function calls bypass FastAPI dependency authorization (same
  documented limitation as the external review probes); the revocation tests
  exercise the real HTTP stack (JWT middleware + RBAC + tenant context) via
  ASGITransport instead.
"""
from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager
from decimal import Decimal
from urllib.parse import urlparse

import pytest
from sqlalchemy import text

from database.session import AsyncSessionLocal

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def assert_loopback_test_database() -> str:
    """Refuse to run against a non-loopback database host.

    This suite writes and drops schemas; it must only ever run against a
    task-exclusive disposable local database (see task directive: existing
    rehearsal databases must never be touched).
    """
    url = os.environ.get("DATABASE_URL", "")
    host = urlparse(url.replace("postgresql+asyncpg://", "postgresql://", 1)).hostname
    if host not in LOOPBACK_HOSTS:
        pytest.fail(
            "MPANGO_INVARIANTS_R0_ENV_GUARD: DATABASE_URL host "
            f"'{host}' is not loopback. This suite requires a task-exclusive "
            "local PostgreSQL (set TEST_DATABASE_URL)."
        )
    return url


def require_jwt_auth_strategy() -> None:
    """The revocation tests exercise the real JWT middleware.

    MPANGO_ENV=test swaps in MockAuthStrategy (auth/factory.py), which would
    silently bypass the production auth path. Run with MPANGO_ENV=staging.
    """
    env = os.environ.get("MPANGO_ENV", "")
    if env == "test":
        pytest.fail(
            "MPANGO_INVARIANTS_R0_ENV_GUARD: MPANGO_ENV=test selects "
            "MockAuthStrategy. Run these tests with MPANGO_ENV=staging so the "
            "real JwtAuthStrategy is exercised."
        )


class R0Token:
    """Minimal TokenPayload stand-in for direct route-function calls.

    Direct route calls do not resolve Depends(), so no signature check runs
    here (documented limitation, same as external review probes). HTTP tests
    use real signed tokens via core.security.create_contextual_token.
    """

    def __init__(self, *, tenant_id: uuid.UUID, tenant_schema: str, user_id: uuid.UUID):
        self.tenant_id = str(tenant_id)
        self.tenant_schema = tenant_schema
        self.user_id = str(user_id)
        self.roles = ["invariants_r0_admin"]


async def run_public_migrations_once() -> None:
    """Upgrade the public schema to the baseline migration head (037)."""
    import subprocess
    import sys
    from pathlib import Path

    backend_dir = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(backend_dir),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        pytest.fail(
            "MPANGO_INVARIANTS_R0_ENV_GUARD: public alembic upgrade head "
            f"failed:\n{result.stdout}\n{result.stderr}"
        )


async def bootstrap_tenant(schema: str) -> None:
    """Create a full tenant schema via the product's own provisioning DDL."""
    from scripts.bootstrap_tenant_schema import bootstrap

    await bootstrap(schema, os.environ["DATABASE_URL"])


@asynccontextmanager
async def tenant_session(schema: str, tenant_id: uuid.UUID | None = None):
    """Open a tenant-scoped session the same way route dependencies do."""
    async with AsyncSessionLocal() as db:
        db.info["tenant_schema"] = schema
        if tenant_id is not None:
            db.info["tenant_id"] = str(tenant_id)
        await db.execute(text(f'SET search_path TO "{schema}", public'))
        try:
            yield db
            await db.commit()
        except BaseException:
            await db.rollback()
            raise


async def seed_public_tenant_rows(
    *,
    wholesaler_id: uuid.UUID,
    retailer_id: uuid.UUID,
    status: str = "active",
    outstanding: Decimal = Decimal("0.00"),
) -> None:
    """Insert public.wholesalers / retailers / binding rows for one tenant."""
    suffix = uuid.uuid4().hex[:10]
    async with AsyncSessionLocal() as db:
        await db.execute(
            text(
                "INSERT INTO public.wholesalers (id, code, name, status, is_deleted) "
                "VALUES (:wid, :code, :name, :status, FALSE) "
                "ON CONFLICT (id) DO UPDATE SET status = EXCLUDED.status, is_deleted = FALSE"
            ),
            {
                "wid": wholesaler_id,
                "code": f"R0{suffix}",
                "name": "Invariants R0 synthetic tenant",
                "status": status,
            },
        )
        await db.execute(
            text(
                "INSERT INTO public.retailers (id, phone, name, is_deleted) "
                "VALUES (:rid, :phone, :name, FALSE) "
                "ON CONFLICT (id) DO UPDATE SET is_deleted = FALSE"
            ),
            {"rid": retailer_id, "phone": f"+254700{suffix}", "name": "Invariants R0 retailer"},
        )
        await db.execute(
            text(
                "INSERT INTO public.wholesaler_retailer_bindings "
                "(wholesaler_id, retailer_id, status, outstanding_balance, is_deleted) "
                "VALUES (:wid, :rid, 'active', :outstanding, FALSE) "
                "ON CONFLICT (wholesaler_id, retailer_id) DO UPDATE "
                "SET status = 'active', outstanding_balance = :outstanding, is_deleted = FALSE"
            ),
            {"wid": wholesaler_id, "rid": retailer_id, "outstanding": outstanding},
        )
        await db.commit()


async def drop_tenant(schema: str, *, wholesaler_id: uuid.UUID, retailer_id: uuid.UUID) -> None:
    """Best-effort teardown of one synthetic tenant (schema + public rows)."""
    async with AsyncSessionLocal() as db:
        await db.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        await db.execute(
            text("DELETE FROM public.wholesaler_retailer_bindings WHERE wholesaler_id = :w"),
            {"w": wholesaler_id},
        )
        await db.execute(text("DELETE FROM public.retailers WHERE id = :r"), {"r": retailer_id})
        await db.execute(text("DELETE FROM public.wholesalers WHERE id = :w"), {"w": wholesaler_id})
        await db.commit()


def new_tenant_identity() -> tuple[uuid.UUID, uuid.UUID, str]:
    """Return (wholesaler_id, retailer_id, schema) with a unique schema name."""
    wholesaler_id = uuid.uuid4()
    retailer_id = uuid.uuid4()
    return wholesaler_id, retailer_id, "t_" + wholesaler_id.hex


async def seed_sku_with_stock(
    db,
    *,
    sku_code: str,
    quantity_on_hand: Decimal,
    price: Decimal | None = None,
    retailer_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Seed one tenant SKU + stock row (+ optional retailer price) via ORM/SQL."""
    from models import SKU
    from models.inventory_stock import InventoryStock

    sku = SKU(sku_code=sku_code, name="Invariants R0 item", unit="box", is_active=True)
    db.add(sku)
    await db.flush()
    db.add(
        InventoryStock(
            sku_id=sku.id,
            quantity_on_hand=quantity_on_hand,
            quantity_reserved=Decimal("0.00"),
        )
    )
    if price is not None and retailer_id is not None:
        await db.execute(
            text(
                "INSERT INTO retailer_prices (retailer_id, sku_id, price, is_deleted) "
                "VALUES (:rid, :sid, :price, FALSE)"
            ),
            {"rid": retailer_id, "sid": sku.id, "price": price},
        )
    await db.flush()
    return sku.id


async def stock_on_hand(db, *, sku_code: str) -> Decimal:
    row = (
        await db.execute(
            text(
                "SELECT s.quantity_on_hand FROM inventory_stocks s "
                "JOIN skus k ON k.id = s.sku_id WHERE k.sku_code = :code"
            ),
            {"code": sku_code},
        )
    ).scalar()
    return Decimal(str(row))


async def adjustment_movements(db, *, sku_code: str) -> list[dict]:
    rows = (
        await db.execute(
            text(
                "SELECT m.quantity::text AS qty, m.quantity_before::text AS q_before, "
                "m.quantity_after::text AS q_after, m.created_at, m.id "
                "FROM inventory_movements m JOIN skus k ON k.id = m.sku_id "
                "WHERE k.sku_code = :code AND m.movement_type = 'adjustment' "
                "ORDER BY m.created_at, m.id"
            ),
            {"code": sku_code},
        )
    ).mappings().all()
    return [dict(r) for r in rows]
